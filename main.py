import asyncio
import time

from log import setup_logging, get_logger
setup_logging()
log = get_logger("main")
log.info(f"[STARTUP] main.py started")

from dotenv import load_dotenv
load_dotenv()

import anthropic
import pyaudio
import audio as audio_module
from model import Model
from speech import Speech
from pydantic import BaseModel, Field
from typing import Optional
from tools.tools import TOOLS, _end_conversation, _schedule_task, ScheduleTask
from audio import wait_for_wake_word, flush_queues, open_streams, wait_for_speech_start, wait_for_speech_end, mic_buffer, transcribe_audio, play_wav_file
import config
from config import AI_MODEL, INPUT_TOKEN_LIMIT, OUTPUT_TOKEN_LIMIT, CONVERSATION_TIMEOUT, ASSISTANT_QUEUE, SUBAGENT_MAX_RETRIES, SUBAGENT_SUPERVISOR_MODEL

_supervisor_client = anthropic.AsyncAnthropic()

async def run_supervisor(task_description: str, result: str) -> tuple[bool, str]:
    """Reviews subagent output. Returns (approved, feedback_if_rejected)."""
    response = await _supervisor_client.messages.create(
        model=SUBAGENT_SUPERVISOR_MODEL,
        max_tokens=256,
        system=(
            "You are a quality assurance supervisor for an AI assistant. "
            "Evaluate whether the subagent fully and correctly completed the task. "
            "Reply with exactly one of:\n"
            "APPROVED\n"
            "REJECTED: <brief explanation of what is missing or incorrect>"
        ),
        messages=[{
            "role": "user",
            "content": f"Task: {task_description}\n\nSubagent result:\n{result}"
        }]
    )
    text = response.content[0].text.strip()
    if text.upper().startswith("APPROVED"):
        return True, ""
    return False, text.removeprefix("REJECTED:").strip()

async def run_subagent(task_description: str, model: str):
    """Spawns a subagent to complete a task, with supervisor review and retries."""
    t0 = time.monotonic()
    log.info(f"[subagent] Starting task with model '{model}': {task_description}")

    try:
        subagent_client = Model(tools=TOOLS, always_included_tools=[], web_search=True)
        subagent_client.set_model(model)
        subagent_client.set_input_tokens(INPUT_TOKEN_LIMIT)
        subagent_client.set_output_tokens(OUTPUT_TOKEN_LIMIT)

        feedback = ""
        result = None
        total_attempts = SUBAGENT_MAX_RETRIES + 1

        for attempt in range(total_attempts):
            subagent_client.clear_context_window()

            if attempt == 0:
                attempt_prompt = f"You are a subagent tasked to perform the following: {task_description}"
            else:
                attempt_prompt = (
                    f"You are a subagent tasked to perform the following: {task_description}\n\n"
                    f"Your previous attempt was reviewed and rejected. Supervisor feedback: {feedback}\n\n"
                    f"Please address the feedback and redo the task properly."
                )

            result = await subagent_client.call_model(input=attempt_prompt) or "No response generated."

            approved, feedback = await run_supervisor(task_description, result)
            log.info(f"[subagent] Attempt {attempt + 1}/{total_attempts}: {'approved' if approved else f'rejected — {feedback}'}")

            if approved or attempt == SUBAGENT_MAX_RETRIES:
                break

        log.info(f"[subagent] Task finished ({time.monotonic() - t0:.2f}s)")
        prompt = f"Subagent task completed.\n\nOriginal task: {task_description}\n\nResult: {result}"
    except Exception as e:
        log.error(f"[subagent] Task failed ({time.monotonic() - t0:.2f}s): {e}")
        prompt = f"Subagent task failed.\n\nOriginal task: {task_description}\n\nError: {e}"

    await ASSISTANT_QUEUE.put({"prompt": prompt})

class SubAgent(BaseModel):
    task_description: str = Field(description="Describe the task that your subagent needs to perform.")
    model: str = Field(default="sonnet 4.6", description="Model for the subagent. Use 'haiku 4.5' for simple/fast tasks, 'sonnet 4.6' for tasks requiring reasoning or web search (default), 'opus 4.6' for the most complex tasks.")

# Still a work in progress...
def _start_subagent(args: SubAgent):
    """Deploy a background subagent to perform a task autonomously. The result will be delivered back when complete."""
    asyncio.create_task(run_subagent(task_description=args.task_description, model=args.model))
    return f"Subagent deployed with model '{args.model}'. Task is being carried out in the background!"


# Define model parameters
client = Model(tools=TOOLS, always_included_tools=[_end_conversation, _schedule_task], web_search=True)
client.set_model(AI_MODEL)
client.set_input_tokens(INPUT_TOKEN_LIMIT)
client.set_output_tokens(OUTPUT_TOKEN_LIMIT)

# initalize audio
pya = pyaudio.PyAudio()

async def run():
    # Define startup time to measure load times performance
    t0 = time.monotonic()

    mic_stream, speaker_stream = open_streams(pya)
    mic_stream.start_stream()
    speaker_stream.start_stream()
    log.info(f"[STARTUP] Streams open ({time.monotonic()-t0:.2f}s)")

    # Load all heavy models in parallel background threads
    oww_task     = asyncio.create_task(asyncio.to_thread(audio_module.create_wake_word_model))
    whisper_task = asyncio.create_task(asyncio.to_thread(audio_module.init_whisper_and_vad))
    speech_task  = asyncio.create_task(asyncio.to_thread(Speech))

    oww_model = await oww_task
    log.info(f"[STARTUP] Wake word model ready ({time.monotonic()-t0:.2f}s)")

    await whisper_task
    log.info(f"[STARTUP] Whisper model ready ({time.monotonic()-t0:.2f}s)")

    speech_obj = await speech_task
    log.info(f"[STARTUP] Speech output (TTS) model ready ({time.monotonic()-t0:.2f}s)")

    # Everything is a go.
    log.info(f"[STARTUP] All models ready. Waiting for wake word. ({time.monotonic()-t0:.2f}s)")

    try:
        while True:
            wake_task = asyncio.create_task(wait_for_wake_word(oww_model))
            queue_task = asyncio.create_task(ASSISTANT_QUEUE.get())
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
                    await play_wav_file(wav_path)
                    continue  # back to waiting
                elif model_prompt is not None:
                    queue_prompt = model_prompt
                else:
                    # shouldn't ever happen but handle edge cases.
                    continue

            # Clear audio queues
            flush_queues()
            mic_buffer.clear()

            # queue_prompt being defined means that a scheduled task is running
            if queue_prompt is None:
                log.info(f"Listening...")

            config.ASSISTANT_STATE = "LISTENING"

            while config.ASSISTANT_STATE == "LISTENING":
                # queue_prompt being defined means that a scheduled task is running, no need to listen to microphone input.
                if queue_prompt is None:
                    try:
                        await asyncio.wait_for(wait_for_speech_start(), timeout=CONVERSATION_TIMEOUT)
                    except asyncio.TimeoutError:
                        log.info(f"No speech detected for {CONVERSATION_TIMEOUT}s, returning to WAITING")
                        config.ASSISTANT_STATE = "WAITING"
                        break

                    await wait_for_speech_end()

                ts = time.monotonic()

                # consume queue_prompt once, then fall back to normal voice listening
                text = queue_prompt
                queue_prompt = None

                if text is None:
                    audio_snapshot = bytes(mic_buffer)

                    # Transcribe Audio
                    text = await transcribe_audio(audio_snapshot)
                    log.info(f"Transcribed ({(time.monotonic() - ts):.2}s) {text}")

                # Call model
                response = await client.call_model(text)
                log.info(f"Model response ({(time.monotonic() - ts):.2}s): {response}")

                # Output response via TTS if conversation is still going.
                if response and config.ASSISTANT_STATE == "LISTENING":
                    wav_path = await asyncio.to_thread(speech_obj.speak, response)
                    await play_wav_file(wav_path)

                # Clear mics after speaker output to avoid model talking to itself.
                flush_queues()
                mic_buffer.clear()

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
