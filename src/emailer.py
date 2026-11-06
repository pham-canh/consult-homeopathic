"""Deliver the doctor-approved plan.

If SMTP credentials are configured the message is sent for real. Otherwise it is
written to the local mailbox directory and recorded as `file` mode, so the demo
can show the exact email without pretending it left the server.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from config import env, mailbox_dir


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
    lines += [
        "This is a hackathon prototype, not a medical device. It does not "
        "provide emergency care. If your symptoms worsen or you feel unsafe, "
        "contact emergency services.",
        "",
        "— Consult Homeopathic Physicians (prototype)",
    ]
    return to_addr, subject, "\n".join(lines)


def send(case: dict) -> dict:
    to_addr, subject, body = compose(case)
    host = env("SMTP_HOST")
    if host:
        message = EmailMessage()
        message["From"] = env("SMTP_FROM", "clinic@example.test")
        message["To"] = to_addr
        message["Subject"] = subject
        message.set_content(body)
        port = int(env("SMTP_PORT", "587") or 587)
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if env("SMTP_STARTTLS", "1") not in {"0", "false", "no"}:
                smtp.starttls()
            user = env("SMTP_USER")
            if user:
                smtp.login(user, env("SMTP_PASS"))
            smtp.send_message(message)
        return {"to": to_addr, "subject": subject, "mode": "smtp", "path": ""}

    path = Path(mailbox_dir()) / f"{case['case_id']}.eml"
    message = EmailMessage()
    message["From"] = env("SMTP_FROM", "clinic@example.test")
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(body)
    path.write_text(message.as_string(), encoding="utf-8")
    return {"to": to_addr, "subject": subject, "mode": "file", "path": str(path)}
