"""Follow-up agent: send a scheduled check-in and record the outcome.

The scheduler is a small daemon thread inside the app (no external queue), which
is enough for a single-VM prototype. `/healthz` reports whether it is running.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone

import case_model
import config
import emailer
import store

STATE: dict = {"running": False, "last_run": "", "sent": 0, "last_error": ""}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _send_one(case_id: str) -> bool:
    case = store.get_case(case_id)
    if not case:
        store.clear_followup_sent(case_id)
        return False
    follow = case.setdefault("follow_up", {})
    token = follow.get("token") or ""
    if not token:
        store.clear_followup_sent(case_id)
        return False
    stamp = _now()
    if not store.claim_followup(case_id, stamp):
        return False
    try:
        delivered = emailer.send_followup_checkin(case)
    except Exception:
        store.clear_followup_sent(case_id)
        raise
    follow["sent_at"] = stamp
    case["updated_at"] = stamp
    store.save_email(case_id, stamp, delivered["to"], delivered["subject"],
                     delivered["mode"], delivered["path"])
    store.add_audit(case_id, "agent", "followup_checkin_sent",
                    f"mode={delivered['mode']} to={delivered['to']}", stamp)
    case["transcript"].append({
        "role": "agent", "at": stamp, "engine": "follow-up agent",
        "text": f"Check-in email sent to {delivered['to']} "
                f"({delivered['mode']} delivery).",
    })
    store.save_case(case)
    return True


def send_due(now: str | None = None) -> list[str]:
    now = now or _now()
    sent: list[str] = []
    for row in store.due_followups(now):
        try:
            if _send_one(row["case_id"]):
                sent.append(row["case_id"])
        except Exception as exc:  # keep the loop alive; record the reason
            STATE["last_error"] = str(exc)[:200]
    STATE["last_run"] = _now()
    STATE["sent"] += len(sent)
    return sent


def send_now(case_id: str) -> dict | None:
    """Doctor-triggered check-in for demos and manual recovery."""
    row = store.get_followup(case_id)
    if not row:
        return None
    if row["sent_at"]:
        return row
    _send_one(case_id)
    return store.get_followup(case_id)


def _loop(stop: threading.Event, interval: float) -> None:
    STATE["running"] = True
    while not stop.wait(interval):
        try:
            send_due()
            STATE["last_error"] = ""
        except Exception as exc:
            STATE["last_error"] = str(exc)[:200]
    STATE["running"] = False


def start() -> tuple[threading.Thread, threading.Event] | None:
    if config.env("CONSULT_DISABLE_SCHEDULER").lower() in {"1", "true", "yes"}:
        return None
    try:
        interval = max(5.0, float(config.env("FOLLOWUP_POLL_SECONDS", "60")))
    except ValueError:
        interval = 60.0
    stop = threading.Event()
    thread = threading.Thread(target=_loop, args=(stop, interval),
                              name="followup-scheduler", daemon=True)
    thread.start()
    return thread, stop


def status() -> dict:
    return dict(STATE)
