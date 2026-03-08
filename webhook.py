import json
import time
import threading
import asyncio
import requests
import config
from log import get_logger

log = get_logger("webhook")


def _apply_template(template: str | None, ctx: dict) -> str | None:
    if not template:
        return None
    try:
        return template.format_map(ctx)
    except Exception:
        return template  # return unformatted if fields are missing


def _diff(old: dict, new: dict) -> dict:
    """Return only keys whose values differ between old and new."""
    return {k: v for k, v in new.items() if old.get(k) != v}


def _listen(loop: asyncio.AbstractEventLoop, cfg: dict) -> None:
    url  = cfg["url"]
    auth = cfg.get("auth", "")
    prev = {}  # last known state for this endpoint

    while True:
        try:
            log.info(f"[webhook] Connecting to {url}")
            with requests.get(url, headers={"Authorization": auth}, stream=True, timeout=None) as r:
                r.raise_for_status()
                log.info(f"[webhook] Connected to {url}")
                for line in r.iter_lines(chunk_size=1):
                    if line.startswith(b"data: "):
                        try:
                            data = json.loads(line[6:])
                            log.info(f"[webhook] Event from {url}: {data}")
                            changed = _diff(prev, data)
                            prev = data

                            if not changed:
                                continue  # nothing new, skip silently

                            # If "variable" is set, only act when that specific field changed
                            watch = cfg.get("variable")
                            if watch and watch not in changed:
                                continue

                            # Run direct action for the new value of the watched variable
                            # "actions" maps variable values → callable(data) — bypasses the model entirely
                            actions = cfg.get("actions", {})
                            if watch and actions:
                                action = actions.get(data.get(watch))
                                if action:
                                    try:
                                        action(data)
                                        log.info(f"[webhook] Action executed for {watch}={data.get(watch)!r}")
                                    except Exception as e:
                                        log.warning(f"[webhook] Action failed for {watch}={data.get(watch)!r}: {e}")

                            # Templates can reference any top-level key, plus {changed} and {data}
                            ctx = {"data": data, "changed": changed, **changed}
                            item = {
                                "prompt":   _apply_template(cfg.get("prompt"),   ctx),
                                "tts_text": _apply_template(cfg.get("tts_text"), ctx),
                            }
                            if item["prompt"] or item["tts_text"]:
                                loop.call_soon_threadsafe(config.ASSISTANT_QUEUE.put_nowait, item)
                                log.info(f"[webhook] Queued from {url} (changed: {list(changed)}): {item}")
                        except Exception as e:
                            log.warning(f"[webhook] Error handling event from {url}: {e}")
        except Exception as e:
            log.warning(f"[webhook] Stream error on {url}: {e}. Reconnecting in 5s...")
            prev = {}  # reset state on reconnect
            time.sleep(5)


def start(loop: asyncio.AbstractEventLoop) -> list[threading.Thread]:
    threads = []
    for i, cfg in enumerate(config.WEBHOOKS):
        t = threading.Thread(
            target=_listen, args=(loop, cfg), daemon=True, name=f"webhook-{i}"
        )
        t.start()
        threads.append(t)
    return threads
