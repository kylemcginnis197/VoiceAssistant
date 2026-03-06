from pydantic import BaseModel, Field
from typing import Union


class AddCronJob(BaseModel):
    label: str = Field(description="Human-readable name for this job (e.g. 'morning briefing').")
    times: list[str] = Field(description="One or more 24-hour HH:MM times to fire each day, e.g. ['08:00'] or ['08:00', '20:00'].")
    days: Union[str, list[str]] = Field(
        description=(
            "When to run. Options: "
            "'everyday', "
            "'every_other_day', "
            "'weekdays' (Mon–Fri), "
            "'weekends' (Sat–Sun), "
            "or a list of day names e.g. ['monday', 'wednesday', 'friday']."
        )
    )
    prompt: str = Field(description="The full prompt text that will be sent to the model when this job fires.")


class RemoveCronJob(BaseModel):
    job_id: str = Field(description="The ID of the cron job to remove. Get IDs from list_cron_jobs.")


class ListCronJobs(BaseModel):
    pass


def make_cron_tools(scheduler):
    def add_cron_job(args: AddCronJob) -> dict:
        """
        Schedule a recurring daily task.

        Creates a cron job that fires at the specified time(s) and day(s), sending
        the provided prompt to the model for processing. The prompt is saved as a
        markdown file and persists across restarts.
        """
        job_id = scheduler.add_job(
            label=args.label,
            times=args.times,
            days=args.days,
            prompt_content=args.prompt,
        )
        return {"status": "created", "job_id": job_id, "label": args.label, "times": args.times, "days": args.days}

    def remove_cron_job(args: RemoveCronJob) -> dict:
        """
        Remove a scheduled cron job by ID.

        Deletes the job and its associated prompt file. Use list_cron_jobs to find the job ID.
        """
        success = scheduler.remove_job(args.job_id)
        if success:
            return {"status": "removed", "job_id": args.job_id}
        return {"status": "not_found", "job_id": args.job_id}

    def list_cron_jobs(args: ListCronJobs) -> list[dict]:
        """
        List all scheduled cron jobs.

        Returns each job's ID, label, scheduled times, and day pattern.
        """
        jobs = scheduler.list_jobs()
        if not jobs:
            return [{"status": "no cron jobs scheduled"}]
        return jobs

    return add_cron_job, remove_cron_job, list_cron_jobs
