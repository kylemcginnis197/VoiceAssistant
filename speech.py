import os
import numpy as np
import soundfile as sf
import torch
from kokoro import KPipeline
from kokoro import KPipeline
from config import RECEIVE_SAMPLE_RATE, TTS_SPEED, TTS_VOICE, QWEN3_MODEL
from log import get_logger
from datetime import datetime

log = get_logger("speech")

if not hasattr(torch, "_orig_load"):
    torch._orig_load = torch.load

def _patched_torch_load(*args, **kwargs):
    kwargs.setdefault("weights_only", False)
    return torch._orig_load(*args, **kwargs)

torch.load = _patched_torch_load

OUTPUT_DIR = "session"

def _select_device() -> str:
    return "cuda:0" if torch.cuda.is_available() else "cpu:0"

class Speech:
    """
    Kokoro TTS → RVC voice conversion pipeline.

    All heavy models are loaded in __init__ so subsequent calls to speak()
    are as fast as possible. Each call to speak() saves a timestamped .wav
    file under speech_output/.
    """
    def __init__(
        self,
        voice: str = TTS_VOICE,
        speed: float = TTS_SPEED,
    ):
        self.voice = voice
        self.speed = speed
        self.device = _select_device()

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # --- Kokoro TTS ---
        try:
            self.pipeline = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
        except Exception as e:
            raise RuntimeError(f"[Speech] Kokoro init failed: {e}") from e

    def speak(self, text: str) -> str:
        """
        Convert text → Kokoro TTS → RVC voice conversion → timestamped .wav.

        Saves the file to speech_output/YYYY-MM-DD_HH-MM-SS.wav and returns
        the path. On RVC failure, saves raw TTS audio instead of crashing.
        """
        if not text or not text.strip():
            raise ValueError("[Speech] speak() called with empty text.")

        tts_audio = self._tts(text)
        out_path = os.path.join(OUTPUT_DIR, "model_output.wav")
        sf.write(out_path, tts_audio, RECEIVE_SAMPLE_RATE)
        return out_path

    def _tts(self, text: str) -> np.ndarray:
        chunks = []
        for _gs, _ps, chunk in self.pipeline(text=text, voice=self.voice, speed=self.speed):
            if chunk is not None and len(chunk):
                if isinstance(chunk, torch.Tensor):
                    chunk = chunk.cpu().numpy()
                chunks.append(np.asarray(chunk, dtype=np.float32))
        if not chunks:
            raise RuntimeError("[Speech] Kokoro returned no audio chunks.")
        return np.concatenate(chunks)


class Qwen3Speech:
    """
    Qwen3-TTS voice cloning pipeline.

    Clones the voice from a reference MP3/WAV file supplied at init time.
    The reference audio is auto-transcribed with Whisper so the user only
    needs to provide the audio file path.
    """

    def __init__(self, voice_sample: str, model_id: str = QWEN3_MODEL):
        import io
        import contextlib
        import whisper as _whisper
        with contextlib.redirect_stdout(io.StringIO()):
            from qwen_tts import Qwen3TTSModel

        if not voice_sample:
            raise ValueError("[Qwen3Speech] QWEN3_VOICE_SAMPLE must be set in config.py")

        self.voice_sample = voice_sample
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        device = _select_device()
        # Qwen3TTSModel expects "cuda" or "cpu", not "cuda:0"
        device_map = "cuda" if device.startswith("cuda") else "cpu"

        log.info(f"[Qwen3Speech] Loading model {model_id} on {device_map}...")
        self.model = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map=device_map,
            torch_dtype=torch.bfloat16,
        )

        # Suppress transformers generation info messages (e.g. pad_token_id warnings)
        import logging as _logging
        _logging.getLogger("transformers.generation.utils").setLevel(_logging.ERROR)

        log.info("[Qwen3Speech] Transcribing reference audio with Whisper...")
        w_model = _whisper.load_model("base")
        result = w_model.transcribe(voice_sample)
        self.ref_text = result["text"].strip()
        log.info(f"[Qwen3Speech] Reference text: {self.ref_text!r}")

        # Pre-encode the reference audio once so every speak() call skips that work
        log.info("[Qwen3Speech] Pre-building voice clone prompt...")
        self.voice_prompt = self.model.create_voice_clone_prompt(
            ref_audio=voice_sample,
            ref_text=self.ref_text,
        )
        log.info("[Qwen3Speech] Voice clone prompt ready.")

    def speak(self, text: str) -> str:
        if not text or not text.strip():
            raise ValueError("[Qwen3Speech] speak() called with empty text.")

        import librosa

        wavs, sr = self.model.generate_voice_clone(
            text=text,
            language="English",
            voice_clone_prompt=self.voice_prompt,
        )

        # Resample from model output rate (12000 Hz) to playback rate (24000 Hz)
        audio = librosa.resample(np.asarray(wavs, dtype=np.float32).squeeze(), orig_sr=sr, target_sr=RECEIVE_SAMPLE_RATE)
        out_path = os.path.join(OUTPUT_DIR, "model_output.wav")
        sf.write(out_path, audio, RECEIVE_SAMPLE_RATE)
        return out_path