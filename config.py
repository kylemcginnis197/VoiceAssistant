import pyaudio
import asyncio
from tools.available_webhooks import WEBHOOKS

# USER SETTINGS -------------------------------------------------------

CONVERSATION_TIMEOUT	= 10                                    # seconds of silence before requiring wake word again
SILENCE_DURATION		= 1                                   # seconds of continuous silence before stopping recording

AI_MODEL			= "claude-haiku-4-5-20251001"               # model used for the main voice agent

INPUT_TOKEN_LIMIT		= 75_000                                # max input tokens before context is compacted via summarization
OUTPUT_TOKEN_LIMIT		= 4_096                                 # max tokens the model can generate per response

TOOL_EMBEDDINGS_RAG		= False                                 # dynamically include tools in context based on user query
TOOL_RAG_TOP_K			= 10                                    # number of tools to retrieve when RAG is enabled

SUBAGENT_MAX_RETRIES		= 2                                 # how many times the supervisor can reject before giving up
SUBAGENT_SUPERVISOR_MODEL	= "claude-sonnet-4-6"               # model used to review subagent output
SUBAGENT_MODEL				= "claude-haiku-4-5-20251001"       # model the subagent performs work with

# ---------------------------------------------------------------------

# DEVELOPER SETTINGS -------------------------------------------------- DO NOT TOUCH

FORMAT				= pyaudio.paInt16                           # audio sample format
CHANNELS			= 1                                         # mono audio input
SEND_SAMPLE_RATE	= 16000                                     # sample rate for microphone input (Hz)
RECEIVE_SAMPLE_RATE	= 24000                                     # sample rate for audio output (Hz)
CHUNK_SIZE			= 4096                                      # audio buffer size in samples

VAD_SPEECH_THRESHOLD	= 0.65                                  # Silero probability above which a window counts as speech
VAD_WINDOW_SIZE			= 512                                   # minimum chunk size (samples) the model accepts at 16 kHz

WAKE_WORD_THRESHOLD		= 0.7                                   # confidence threshold to trigger the assistant

TTS_BACKEND			= "kokoro"                                   # "kokoro" | "qwen3"
TTS_VOICE	= "am_puck"                                         # Kokoro voice ID
TTS_SPEED	= 1.3                                               # playback speed multiplier

QWEN3_VOICE_SAMPLE	= "sounds/voice.mp3"                        # path to reference MP3/WAV for voice cloning
QWEN3_MODEL			= "Qwen/Qwen3-TTS-12Hz-0.6B-Base"           # Qwen3-TTS HuggingFace model ID (0.6B-Base or 1.7B-Base)


# ---------------------------------------------------------------------

# MODEL STATE ---------------------------------------------------------

ASSISTANT_STATE		= "WAITING"
ASSISTANT_QUEUE: asyncio.Queue[dict] = asyncio.Queue()
MODEL_TOOLS			= []
