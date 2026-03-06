import anthropic
import asyncio
import time

from tools import tools
from pydantic import Field, BaseModel
from config import SUBAGENT_MODEL, INPUT_TOKEN_LIMIT, OUTPUT_TOKEN_LIMIT, SUBAGENT_MAX_RETRIES, SUBAGENT_SUPERVISOR_MODEL, ASSISTANT_QUEUE, MODEL_TOOLS
from model import Model
from log import get_logger
log = get_logger("tools")

_supervisor_client = anthropic.AsyncAnthropic()

async def run_supervisor(task_description: str, context: list[str], result: str) -> tuple[bool, str]:
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
        messages=context + [{
            "role": "user",
            "content": f"Everything previously mention is from the subagent, their original task: {task_description}\n\n and subagent result:\n{result}"
        }]
    )
    text = response.content[0].text.strip()
    if text.upper().startswith("APPROVED"):
        return True, ""
    return False, text.removeprefix("REJECTED:").strip()

async def run_subagent(task_description: str, name: str = None):
    """Spawns a subagent to complete a task, with supervisor review and retries."""
    t0 = time.monotonic()
    log.info(f"[subagent] Starting task: {task_description}")

    try:
        subagent_client = Model(tools=MODEL_TOOLS, always_included_tools=[], name="subagent" if name is None else name, web_search=True)
        subagent_client.set_model(SUBAGENT_MODEL)
        subagent_client.set_input_tokens(INPUT_TOKEN_LIMIT)
        subagent_client.set_output_tokens(OUTPUT_TOKEN_LIMIT)

        feedback = ""
        result = None
        total_attempts = SUBAGENT_MAX_RETRIES + 1

        for attempt in range(total_attempts):
            if attempt == 0:
                attempt_prompt = f"You are a subagent tasked to perform the following: {task_description}"
            else:
                attempt_prompt = (
                    f"You are a subagent tasked to perform the following: {task_description}\n\n"
                    f"Your previous attempt was reviewed and rejected. Supervisor feedback: {feedback}\n\n"
                    f"Please address the feedback and redo the task properly."
                )

            result = await subagent_client.call_model(input=attempt_prompt) or "No response generated."

            approved, feedback = await run_supervisor(task_description, subagent_client.context_window, result)
            log.info(f"[subagent] Attempt {attempt + 1}/{total_attempts}: {'approved' if approved else f'rejected — {feedback}'}")

            if approved or attempt == SUBAGENT_MAX_RETRIES:
                break

        log.info(f"[subagent] Task finished ({time.monotonic() - t0:.2f}s)")
        prompt = f"Subagent task completed.\n\nOriginal task: {task_description}\n\nResult: {result}"
    except Exception as e:
        log.error(f"[subagent] Task failed ({time.monotonic() - t0:.2f}s): {e}")
        prompt = f"Subagent task failed.\n\nOriginal task: {task_description}\n\nError: {e}"

    await ASSISTANT_QUEUE.put({"prompt": prompt, "tts_text": None})

class SubAgent(BaseModel):
    name: str = Field(description="Provide a name related to the task the subagent is performing.")
    task_description: str = Field(description="Describe the task that your subagent needs to perform.")

# Still a work in progress...
def _start_subagent(args: SubAgent):
    """Deploy a background subagent to perform a task autonomously. The result will be delivered back when complete."""
    asyncio.create_task(run_subagent(task_description=args.task_description, name=args.name))
    return f"Subagent deployed. Task is being carried out in the background!"