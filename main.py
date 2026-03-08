import audio as audio_module
import asyncio
import pyaudio
import time
import config
from model import Model
from speech import Speech, Qwen3Speech
from tools.tools import _end_conversation
from tools.scheduler import _schedule_task
from tools.subagents import _start_subagent
from cron import cron_scheduler
from webhook import start as start_webhook
from log import get_logger

# Add logger
log = get_logger("main")
log.info(f"[STARTUP] main.py started")

# Define model parameters
client = Model(tools=config.MODEL_TOOLS, always_included_tools=[_end_conversation, _schedule_task, _start_subagent], name="voice", web_search=True)
client.set_model(config.AI_MODEL)
client.set_input_tokens(config.INPUT_TOKEN_LIMIT)
client.set_output_tokens(config.OUTPUT_TOKEN_LIMIT)

# initalize audio
pya = pyaudio.PyAudio()

async def run():
    # Define startup time to measure load times performance
    t0 = time.monotonic()

    mic_stream, speaker_stream = audio_module.open_streams(pya)
    mic_stream.start_stream()
    speaker_stream.start_stream()
    log.info(f"[STARTUP] Streams open ({time.monotonic()-t0:.2f}s)")

    # Load all heavy models in parallel background threads
    oww_task     = asyncio.create_task(asyncio.to_thread(audio_module.create_wake_word_model))
    whisper_task = asyncio.create_task(asyncio.to_thread(audio_module.init_whisper_and_vad))
    if config.TTS_BACKEND == "qwen3":
        speech_task = asyncio.create_task(
            asyncio.to_thread(Qwen3Speech, config.QWEN3_VOICE_SAMPLE, config.QWEN3_MODEL)
        )
    else:
        speech_task  = asyncio.create_task(asyncio.to_thread(Speech))

    oww_model = await oww_task
    
    log.info(f"[STARTUP] Wake word model ready ({time.monotonic()-t0:.2f}s)")
    await whisper_task
    log.info(f"[STARTUP] Whisper model ready ({time.monotonic()-t0:.2f}s)")

    speech_obj = await speech_task
    log.info(f"[STARTUP] Speech output (TTS) model ready ({time.monotonic()-t0:.2f}s)")

    # Everything is a go.
    log.info(f"[STARTUP] All models ready. Waiting for wake word. ({time.monotonic()-t0:.2f}s)")
    asyncio.create_task(cron_scheduler.run())
    if config.WEBHOOKS:
        start_webhook(asyncio.get_event_loop())
        log.info(f"[STARTUP] {len(config.WEBHOOKS)} webhook listener(s) started")

    try:
        while True:
            wake_task = asyncio.create_task(audio_module.wait_for_wake_word(oww_model))
            queue_task = asyncio.create_task(config.ASSISTANT_QUEUE.get())
            queue_prompt = None

            done, pending = await asyncio.wait(
                {wake_task, queue_task},
                return_when=asyncio.FIRST_COMPLETED
            )

            for p in pending:
                p.cancel()
                try:
                    await p
                except asyncio.CancelledError:
                    pass

            if queue_task in done:
                # Background task wants to speak
                msg = queue_task.result()

                model_prompt = msg.get("prompt", None)
                tts_text = msg.get("tts_text", None)

                if tts_text is not None:
                    wav_path = await asyncio.to_thread(speech_obj.speak, tts_text)
                    await audio_module.play_wav_file(wav_path)
                    continue  # back to waiting
                elif model_prompt is not None:
                    queue_prompt = model_prompt
                else:
                    # shouldn't ever happen but handle edge cases.s
                    continue
            elif wake_task in done:
                await audio_module.play_mp3_file("sounds/wake_sound.mp3")

            # Clear audio queues
            audio_module.flush_queues()
            audio_module.mic_buffer.clear()

            # queue_prompt being defined means that a scheduled task is running
            if queue_prompt is None:
                log.info(f"Listening...")

            config.ASSISTANT_STATE = "LISTENING"

            while config.ASSISTANT_STATE == "LISTENING":
                # queue_prompt being defined means that a scheduled task is running, no need to listen to microphone input.
                if queue_prompt is None:
                    try:
                        await asyncio.wait_for(audio_module.wait_for_speech_start(), timeout=config.CONVERSATION_TIMEOUT)
                    except asyncio.TimeoutError:
                        log.info(f"No speech detected for {config.CONVERSATION_TIMEOUT}s, returning to WAITING")
                        config.ASSISTANT_STATE = "WAITING"
                        break

                    await audio_module.wait_for_speech_end()

                ts = time.monotonic()

                # consume queue_prompt once, then fall back to normal voice listening
                text = queue_prompt
                queue_prompt = None

                if text is None:
                    audio_snapshot = bytes(audio_module.mic_buffer)

                    # Transcribe Audio
                    text = await audio_module.transcribe_audio(audio_snapshot)
                    log.info(f"Transcribed ({(time.monotonic() - ts):.2}s) {text}")

                # Call model
                response = await client.call_model(text)
                log.info(f"[{client.name}] Response ({(time.monotonic() - ts):.2}s): {response}")

                # After each call, output context.
                client.dump_context_window()

                # Output response via TTS if conversation is still going.
                if response:
                    wav_path = await asyncio.to_thread(speech_obj.speak, response)
                    log.info(f"[tts] Latency: {round(time.monotonic() - ts)}s")
                    await audio_module.play_wav_file(wav_path)

                # Clear mics after speaker output to avoid model talking to itself.
                audio_module.flush_queues()
                audio_module.mic_buffer.clear()

            mic_stream.stop_stream()
            mic_stream.start_stream()
    except asyncio.CancelledError:
        pass
    finally:
        mic_stream.stop_stream()
        mic_stream.close()
        speaker_stream.stop_stream()
        speaker_stream.close()
        pya.terminate()
        log.info("Connection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
