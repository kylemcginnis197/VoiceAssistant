import asyncio
import json
import uuid
from datetime import datetime, date
from pathlib import Path

import config
from log import get_logger

log = get_logger("cron")

DAYS_MAP = {
    "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    "weekends": ["saturday", "sunday"],
}

class CronScheduler:
    JOBS_FILE = "cron/jobs.json"
    PROMPTS_DIR = "cron"

    def __init__(self):
        self.jobs: list[dict] = []
        self._last_fired: dict[str, str] = {}  # "{job_id}_{HH:MM}" -> "YYYY-MM-DD"
        Path(self.PROMPTS_DIR).mkdir(exist_ok=True)
        self._load()

    def _load(self):
        path = Path(self.JOBS_FILE)
        if path.exists():
            self.jobs = json.loads(path.read_text())
            log.info(f"Loaded {len(self.jobs)} cron job(s)")

    def _save(self):
        Path(self.JOBS_FILE).write_text(json.dumps(self.jobs, indent=2))

    def _prompt_path(self, job_id: str) -> Path:
        return Path(self.PROMPTS_DIR) / f"{job_id}.md"

    def _should_fire(self, job: dict, today_name: str, today_str: str) -> bool:
        days = job["days"]

        if days == "everyday":
            return True

        if days == "every_other_day":
            # Find the most recent fire date for this job across any time slot
            last = None
            for key, fired_date in self._last_fired.items():
                if key.startswith(job["id"] + "_"):
                    d = date.fromisoformat(fired_date)
                    if last is None or d > last:
                        last = d
            if last is None:
                return True
            return (date.fromisoformat(today_str) - last).days >= 2

        # Normalize to a flat list of day names
        if isinstance(days, str):
            days = DAYS_MAP.get(days, [days])

        expanded = []
        for d in days:
            expanded.extend(DAYS_MAP.get(d, [d]))

        return today_name in expanded

    def add_job(self, label: str, times: list[str], days: str | list[str], prompt_content: str) -> str:
        job_id = uuid.uuid4().hex[:8]
        self.jobs.append({
            "id": job_id,
            "label": label,
            "times": times,
            "days": days,
        })
        self._prompt_path(job_id).write_text(prompt_content)
        self._save()
        log.info(f"Added cron job '{label}' ({job_id}) at {times} on {days}")
        return job_id

    def remove_job(self, job_id: str) -> bool:
        before = len(self.jobs)
        self.jobs = [j for j in self.jobs if j["id"] != job_id]
        if len(self.jobs) == before:
            return False
        prompt_file = self._prompt_path(job_id)
        if prompt_file.exists():
            prompt_file.unlink()
        self._save()
        log.info(f"Removed cron job {job_id}")
        return True

    def list_jobs(self) -> list[dict]:
        result = []
        for job in self.jobs:
            result.append({
                "id": job["id"],
                "label": job["label"],
                "times": job["times"],
                "days": job["days"],
            })
        return result

    async def run(self):
        log.info("Cron scheduler started")
        while True:
            await asyncio.sleep(30)
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            today_name = now.strftime("%A").lower()
            current_hhmm = now.strftime("%H:%M")

            for job in self.jobs:
                if current_hhmm not in job["times"]:
                    continue

                fire_key = f"{job['id']}_{current_hhmm}"
                if self._last_fired.get(fire_key) == today_str:
                    continue

                if not self._should_fire(job, today_name, today_str):
                    continue

                prompt_file = self._prompt_path(job["id"])
                if not prompt_file.exists():
                    log.warning(f"Prompt file missing for job '{job['label']}' ({job['id']}), skipping")
                    continue

                self._last_fired[fire_key] = today_str
                prompt = prompt_file.read_text()
                await config.ASSISTANT_QUEUE.put({"prompt": prompt, "tts_text": None})
                log.info(f"Fired cron job '{job['label']}' at {current_hhmm}")


cron_scheduler = CronScheduler()
