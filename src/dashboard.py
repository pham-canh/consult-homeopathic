"""Aggregations for the clinic operations dashboard.

Everything is computed from the same SQLite case store the workflow uses, so the
dashboard cannot drift from the patient and doctor APIs. The prototype reads at
most a few thousand rows per refresh; a production build would move these
summaries into SQL or a metrics store.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

import emailer
import store


def _parse(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _labels(case: dict) -> list[str]:
    labels = []
    for flag in case.get("red_flags") or []:
        label = flag.get("label") if isinstance(flag, dict) else str(flag)
        if label:
            labels.append(label)
    return labels


def _case_row(case: dict) -> dict:
    patient = case.get("patient") or {}
    summary = case.get("summary") or {}
    doctor = case.get("doctor") or {}
    email = case.get("email") or {}
    reports = case.get("reports") or []
    follow = case.get("follow_up") or {}
    return {
        "case_id": case.get("case_id", ""),
        "created_at": case.get("created_at", ""),
        "updated_at": case.get("updated_at", ""),
        "status": case.get("status", ""),
        "urgency": case.get("urgency", ""),
        "needs_attention": bool(case.get("needs_attention")),
        "engine": case.get("engine", ""),
        "patient": {"name": patient.get("name", ""),
                    "email": patient.get("email", "")},
        "chief_complaint": case.get("chief_complaint", ""),
        "summary": summary.get("one_liner", ""),
        "selected_option": case.get("selected_option", ""),
        "red_flags": _labels(case),
        "report_count": len(reports),
        "doctor_approved_at": doctor.get("approved_at", ""),
        "email_mode": email.get("mode", ""),
        "email_sent_at": email.get("sent_at", ""),
        "follow_up_due_at": follow.get("due_at", ""),
        "follow_up_sent_at": follow.get("sent_at", ""),
    }


def case_search_blob(case: dict) -> str:
    patient = case.get("patient") or {}
    summary = case.get("summary") or {}
    parts = [
        case.get("case_id", ""),
        patient.get("name", ""),
        patient.get("email", ""),
        case.get("chief_complaint", ""),
        case.get("selected_option", ""),
        summary.get("one_liner", ""),
        " ".join(case.get("symptoms") or []),
        " ".join(_labels(case)),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def overview() -> dict:
    now = _now()
    today = now.date()
    cases = store.list_cases(limit=2000)
    rows = store.list_followups(limit=2000)
    emails = store.list_emails(500)
    status = Counter(case.get("status", "") for case in cases)

    attention_cases = [
        case for case in cases
        if case.get("status") == "emergency" or case.get("needs_attention")
    ]
    attention_cases.sort(key=lambda case: str(case.get("updated_at") or ""),
                         reverse=True)

    unsent = [row for row in rows if not row.get("sent_at")]
    due_rows = [row for row in unsent
                if (_parse(row.get("due_at")) or now) <= now]
    upcoming_rows = [row for row in unsent if row not in due_rows]
    sent_rows = [row for row in rows if row.get("sent_at")]

    durations = []
    for case in cases:
        created = _parse(case.get("created_at"))
        approved = _parse((case.get("doctor") or {}).get("approved_at"))
        if created and approved and approved >= created:
            durations.append((approved - created).total_seconds())
    average_review = round(sum(durations) / len(durations)) if durations else None

    trend = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        count = sum(
            1 for case in cases
            if (created := _parse(case.get("created_at")))
            and created.date() == day
        )
        trend.append({"date": day.isoformat(), "label": day.strftime("%a"),
                      "count": count})

    today_new = sum(
        1 for case in cases
        if (created := _parse(case.get("created_at")))
        and created.date() == today
    )
    today_approved = sum(
        1 for case in cases
        if (approved := _parse((case.get("doctor") or {}).get("approved_at")))
        and approved.date() == today
    )
    today_emergency = sum(
        1 for case in cases
        if (updated := _parse(case.get("updated_at")))
        and updated.date() == today
        and case.get("status") == "emergency"
    )

    mode = Counter(row.get("mode", "") for row in emails)
    recent = sorted(cases, key=lambda case: str(case.get("updated_at") or ""),
                    reverse=True)[:8]

    return {
        "generated_at": now.isoformat(),
        "cases": {
            "total": len(cases),
            "intake": status.get("intake", 0),
            "pending_review": status.get("pending_review", 0),
            "emergency": status.get("emergency", 0),
            "delivered": status.get("delivered", 0),
            "needs_attention": len(attention_cases),
        },
        "followups": {
            "total": len(rows),
            "scheduled": len(upcoming_rows),
            "due": len(due_rows),
            "sent": len(sent_rows),
        },
        "emails": {
            "total": len(emails),
            "file": mode.get("file", 0),
            "smtp": mode.get("smtp", 0),
        },
        "today": {
            "new_cases": today_new,
            "approved": today_approved,
            "emergencies": today_emergency,
        },
        "avg_review_seconds": average_review,
        "trend": trend,
        "attention": [_case_row(case) for case in attention_cases[:8]],
        "recent": [_case_row(case) for case in recent],
    }


def followups_view(limit: int = 500) -> list[dict]:
    now = _now()
    cases = {case["case_id"]: case for case in store.list_cases(limit=2000)}
    out = []
    for row in store.list_followups(limit=limit):
        case = cases.get(row["case_id"]) or {}
        patient = case.get("patient") or {}
        summary = case.get("summary") or {}
        due = _parse(row.get("due_at"))
        if row.get("sent_at"):
            state = "sent"
        elif due and due <= now:
            state = "due"
        else:
            state = "scheduled"
        token = row.get("token") or ""
        out.append({
            "case_id": row["case_id"],
            "token": token,
            "link": (f"{emailer.public_url()}/follow-up/{token}"
                     if token else ""),
            "due_at": row.get("due_at", ""),
            "sent_at": row.get("sent_at", ""),
            "created_at": row.get("created_at", ""),
            "state": state,
            "case_status": case.get("status", ""),
            "needs_attention": bool(case.get("needs_attention")),
            "patient": {"name": patient.get("name", ""),
                        "email": patient.get("email", "")},
            "summary": summary.get("one_liner", ""),
        })
    return out
