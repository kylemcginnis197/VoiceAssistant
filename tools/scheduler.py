from pydantic import BaseModel, Field
from typing import Optional
from config import ASSISTANT_QUEUE
from datetime import timedelta
from log import get_logger
log = get_logger("")
import asyncio

class ScheduleTask(BaseModel):
    hours: int = Field(description="Hours until task should occur")
    minutes: int = Field(description="Minutes until task should occur")
    seconds: int = Field(description="Seconds until task should occur")
    model_prompt: Optional[str] = Field(default=None, description="Prompt to pass to the model so you can access the internet or tools as needed to complete task. If no model prompt is provided, be sure to provide a text output for the TTS model to tell the user.")
    tts_text: Optional[str] = Field(default=None, description="Provide text that will be spoken to the user. Useful let the user know a timer is done or for reminders. If no text is provided, be sure to provide a task for the model prompt.")

async def schedule_task_tool(delay_seconds: float, payload: dict): 
    await asyncio.sleep(delay_seconds)
    await ASSISTANT_QUEUE.put(item=payload)
    log.info(f"Scheduled task fired: {payload}")

def _schedule_task(args: ScheduleTask):
    """Schedules a task that will occur after a set amount of time"""
    hours = args.hours
    minutes = args.minutes
    seconds = args.seconds
     
    # convert time to total seconds
    total_seconds = timedelta(hours=hours, minutes=minutes, seconds=seconds).total_seconds()

    if args.model_prompt or args.tts_text:
        asyncio.create_task(schedule_task_tool(delay_seconds=total_seconds, payload={
            "prompt": args.model_prompt,
            "tts_text": args.tts_text
        }))
    else:
        return "Failed to schedule task, Pass an input for either model_prompt or tts_text"