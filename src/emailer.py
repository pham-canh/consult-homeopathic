"""Deliver the doctor-approved plan, follow-up check-ins, and alerts.

If SMTP credentials are configured the message is sent for real. Otherwise it is
written to the local mailbox directory and recorded as `file` mode, so the demo
can show the exact email without pretending it left the server.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from config import env, mailbox_dir
import payments


def public_url() -> str:
    return env("CONSULT_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/")


def compose(case: dict) -> tuple[str, str, str]:
    patient = case["patient"]
    to_addr = patient.get("email") or "patient@example.test"
    doctor = case["doctor"]
    subject = f"Your care plan ({case['case_id']}) — Consult Homeopathic Physicians"

    lines = [
        f"Hello {patient.get('name') or 'there'},",
        "",
        "A licensed doctor has reviewed your case and approved this plan.",
        "",
        f"Case: {case['case_id']}",
        f"Summary: {case['summary'].get('one_liner', '')}",
        "",
        "Doctor's advice:",
        (doctor.get("advice") or "(no advice entered)").strip(),
        "",
    ]
    if doctor.get("prescription"):
        lines += ["Prescription:", doctor["prescription"].strip(), ""]
    if doctor.get("notes"):
        lines += ["Doctor notes:", doctor["notes"].strip(), ""]
    if case.get("follow_up", {}).get("token"):
        token = case["follow_up"]["token"]
        pay_link = f"{public_url()}/pay/{token}"
        follow_link = f"{public_url()}/follow-up/{token}"
        lines += [
            f"Consultation fee (demo only — no real charge): {payments.amount_display()}",
            f"Choose a demo payment method here: {pay_link}",
            "",
            "Follow-up check:",
            f"We will check in on you. You can also report how you feel here: {follow_link}",
            "",
        ]
    lines += [
        "This is a hackathon prototype, not a medical device. It does not "
        "provide emergency care. If your symptoms worsen or you feel unsafe, "
        "contact emergency services.",
        "",
        "— Consult Homeopathic Physicians (prototype)",
    ]
    return to_addr, subject, "\n".join(lines)


def compose_followup(case: dict) -> tuple[str, str, str]:
    from text import FOLLOWUP_CHECKIN, fill

    patient = case["patient"]
    to_addr = patient.get("email") or "patient@example.test"
    subject = f"Check-in for case {case['case_id']} — Consult Homeopathic Physicians"
    link = f"{public_url()}/follow-up/{case['follow_up']['token']}"
    lines = [
        fill(FOLLOWUP_CHECKIN, name=patient.get("name") or "there",
             case_id=case["case_id"]),
    ]
    if patient.get("diet") or (case.get("duration_days") or 0) >= 7:
        lines += ["", "Also, how is your appetite and diet? Have you changed "
                      "what you eat or drink since the visit?"]
    lines += [
        "",
        link,
        "",
        "If this is an emergency, call your local emergency number instead of "
        "waiting for a reply.",
        "",
        "— Consult Homeopathic Physicians (prototype)",
    ]
    return to_addr, subject, "\n".join(lines)


def _deliver(to_addr: str, subject: str, body: str, case_id: str,
             kind: str) -> dict:
    host = env("SMTP_HOST")
    message = EmailMessage()
    message["From"] = env("SMTP_FROM", "clinic@example.test")
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body)
    if host:
        port = int(env("SMTP_PORT", "587") or 587)
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if env("SMTP_STARTTLS", "1") not in {"0", "false", "no"}:
                smtp.starttls()
            user = env("SMTP_USER")
            if user:
                smtp.login(user, env("SMTP_PASS"))
            smtp.send_message(message)
        return {"to": to_addr, "subject": subject, "mode": "smtp", "path": "",
                "kind": kind}

    suffix = "" if kind == "plan" else f"-{kind}"
    path = Path(mailbox_dir()) / f"{case_id}{suffix}.eml"
    path.write_text(message.as_string(), encoding="utf-8")
    return {"to": to_addr, "subject": subject, "mode": "file", "path": str(path),
            "kind": kind}


def send(case: dict) -> dict:
    to_addr, subject, body = compose(case)
    return _deliver(to_addr, subject, body, case["case_id"], "plan")


def send_followup_checkin(case: dict) -> dict:
    to_addr, subject, body = compose_followup(case)
    return _deliver(to_addr, subject, body, case["case_id"], "followup")


def send_alert(case: dict, reason: str) -> dict | None:
    """Notify the clinic when a follow-up escalates. Optional in the demo."""
    to_addr = env("CONSULT_DOCTOR_EMAIL")
    if not to_addr:
        return None
    subject = f"ESCALATION {case['case_id']} — patient reported a red flag"
    body = "\n".join([
        f"Case {case['case_id']} needs attention.",
        f"Reason: {reason}",
        f"Patient: {case['patient'].get('name') or 'unnamed'}",
        "",
        "Open the doctor dashboard: " + public_url() + "/doctor?case=" + case["case_id"],
    ])
    return _deliver(to_addr, subject, body, case["case_id"], "alert")
