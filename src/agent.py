"""The multi-step workflow: intake -> safety gate -> options -> doctor -> email.

The flow is deliberately split so the AI only does the information work. It can
ask questions, extract a structured case, read an uploaded report, and suggest
care paths. It cannot set the doctor's decision, prescribe, or override the
emergency gate.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta, timezone

import case_model
import config
import emailer
import text as copy
import inference
import payments
import reports
import safety
import store


class WorkflowError(ValueError):
    """A request that is valid HTTP but invalid for the case state."""


SYSTEM_PROMPT = """You are the intake assistant for a clinic prototype. You gather
information; a licensed doctor makes every medical decision. Never diagnose, never
prescribe, never give a treatment dose. Be warm, brief, and plain-spoken.

Return ONLY a JSON object with exactly these keys:
{
  "reply": "what to say to the patient next (max 70 words, English)",
  "emergency": false,
  "red_flags": ["..."],
  "patient": {"name": "", "email": "", "age": null, "sex": "",
              "allergies": [], "medications": [], "history": "",
              "diet": ""},
  "chief_complaint": "",
  "symptoms": [],
  "duration_days": null,
  "severity": "mild|moderate|severe|",
  "care_options": [{"name": "", "why": "", "key": ""}],
  "summary": {"one_liner": "", "key_findings": [], "safety_notes": []},
  "ready_for_review": false
}

Rules:
- Keep every field already present in the case; only fill gaps or correct details.
- Write every field, including "reply" and the summary, in English.
- Detect emergency red flags (chest pain, trouble breathing, stroke signs, severe
  bleeding, throat/tongue swelling, self-harm, seizure, severe head injury).
- Ask at most two short follow-up questions. Collect duration, severity, allergies,
  medications, and an email address for the plan.
- If the problem has lasted 7 days or more, or it is gastrointestinal or
  metabolic, ask about appetite and diet and put the answer in patient.diet.
- prior_cases are earlier visits for the same email. Use them for context only;
  do not assume the current problem is the same.
- When you have a complaint, duration, and severity, return 2-3 care_options and
  set ready_for_review true. Options must be care paths, not diagnoses, e.g.
  "Online doctor review", "In-person visit", "Self-care with monitoring".
  Use key "online_review", "in_person", or "self_care" when one of those fits.
- summary.key_findings and safety_notes must be short factual strings.
"""

DEFAULT_OPTIONS = [
    {"name": "Online doctor review",
     "why": "A clinician reviews this case remotely and sends a plan, usually "
            "without a full appointment slot."},
    {"name": "In-person visit",
     "why": "Best if an examination or test is likely to be needed."},
    {"name": "Self-care with monitoring",
     "why": "Reasonable for mild, stable symptoms, with a check-in later."},
]

SYMPTOM_WORDS = [
    "cough", "fever", "headache", "sore throat", "runny nose", "fatigue",
    "nausea", "vomiting", "diarrhea", "abdominal pain", "stomach pain",
    "rash", "itching", "dizziness", "back pain", "joint pain", "ear pain",
    "shortness of breath", "chest pain", "sneezing", "chills", "body ache",
]

DURATION = re.compile(r"(\d+)\s*(day|week|month)s?\b", re.IGNORECASE)
AGE = re.compile(r"\b(?:i(?:'m| am)\s+)?(\d{1,3})\s*(?:years?|yrs?)\s*old\b|"
                 r"\bi(?:'m| am)\s+(\d{1,3})\b", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ALLERGY = re.compile(r"(?:allergic to|allergy to|allergies?:)\s*([^.,;\n]+)",
                     re.IGNORECASE)
MEDICATION = re.compile(r"(?:taking|on|using)\s+([A-Za-z][A-Za-z0-9 \-]{2,30})",
                        re.IGNORECASE)
DIET = re.compile(r"(?:my\s+)?diet(?:\s+is|\s*:)?\s*([^.,;\n]{2,120})",
                  re.IGNORECASE)
NAME = re.compile(r"(?:my name is|i am|i'm|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)")


def _audit(case: dict, actor: str, action: str, detail: str) -> None:
    stamp = case_model.now()
    case["updated_at"] = stamp
    store.add_audit(case["case_id"], actor, action, detail, stamp)


def _say(case: dict, text: str, *, engine: str | None = None) -> dict:
    entry = {"role": "assistant", "at": case_model.now(), "text": text}
    if engine:
        entry["engine"] = engine
    case["transcript"].append(entry)
    return entry


TRUE_VALUES = {"1", "true", "yes", "y", "emergency", "urgent"}


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUE_VALUES
    return False


def _reply_text(value) -> str:
    return value.strip()[:1200] if isinstance(value, str) else ""


def _flag_labels(value) -> list[dict]:
    """Normalize model red flags without turning a string into characters."""
    if isinstance(value, dict):
        items = [value]
    elif isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"none", "no", "false", "n/a"}:
            return []
        items = [text]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return []
    flags = []
    for item in items:
        label = item.get("label") if isinstance(item, dict) else item
        if isinstance(label, str) and label.strip():
            flags.append({"label": label.strip()[:80], "phrase": "model flag"})
    return flags[:12]


def start_case(name: str = "", email: str = "") -> dict:
    store.init_db()
    case = case_model.new_case(name)
    if email.strip():
        case["patient"]["email"] = email.strip()[:160]
    _say(case, copy.GREETING, engine="template")
    _audit(case, "system", "intake_started", "Patient opened a new intake")
    store.save_case(case)
    return case


def _rule_analyze(text: str, case: dict) -> dict:
    """Deterministic fallback and the baseline used for safety-critical fields."""
    data: dict = {"patient": {}, "symptoms": [], "care_options": [],
                  "summary": {}, "red_flags": [], "emergency": False}

    lowered = text.lower()
    for word in SYMPTOM_WORDS:
        if word in lowered and word not in case["symptoms"]:
            data["symptoms"].append(word)

    match = DURATION.search(text)
    if match:
        amount, unit = int(match.group(1)), match.group(2).lower()
        data["duration_days"] = amount * {"day": 1, "week": 7, "month": 30}[unit]

    for level in ("severe", "moderate", "mild"):
        if level in lowered:
            data["severity"] = level
            break

    email = EMAIL.search(text)
    if email:
        data["patient"]["email"] = email.group(0).rstrip(".,;:")

    age = AGE.search(text)
    if age:
        data["patient"]["age"] = int(age.group(1) or age.group(2))

    name = NAME.search(text)
    if name and not case["patient"].get("name"):
        data["patient"]["name"] = name.group(1)

    allergy = ALLERGY.search(text)
    if allergy:
        data["patient"]["allergies"] = [part.strip(" .") for part in
                                        re.split(r",| and ", allergy.group(1))
                                        if part.strip(" .")]

    med = MEDICATION.search(text)
    if med and "taking" in lowered:
        data["patient"]["medications"] = [med.group(1).strip()]

    diet = DIET.search(text)
    if diet:
        data["patient"]["diet"] = diet.group(1).strip(" .")

    if not case.get("chief_complaint") and data["symptoms"]:
        data["chief_complaint"] = data["symptoms"][0][0].upper() + \
            data["symptoms"][0][1:] + " reported by the patient"

    has_basics = bool(case.get("chief_complaint") or data.get("chief_complaint"))
    has_duration = case.get("duration_days") is not None or \
        data.get("duration_days") is not None
    has_severity = bool(case.get("severity") or data.get("severity"))
    if has_basics and has_duration and has_severity:
        data["care_options"] = [dict(o) for o in DEFAULT_OPTIONS]
        data["ready_for_review"] = True
        data["summary"] = {
            "one_liner": (data.get("chief_complaint") or case.get("chief_complaint")
                          or "Case summary")[:200] + (
                              f", {data.get('duration_days') or case.get('duration_days')} day(s)"
                              if (data.get("duration_days") or case.get("duration_days")) else ""),
            "key_findings": [],
            "safety_notes": [],
        }
        data["reply"] = copy.OPTIONS_READY
    else:
        data["reply"] = copy.ASK_MORE
        data["ready_for_review"] = False
    return data


def _merge_red_flags(case: dict, flags: list[dict]) -> None:
    existing = {(f.get("label") if isinstance(f, dict) else str(f))
                for f in case.get("red_flags", [])}
    for flag in flags:
        label = flag.get("label") if isinstance(flag, dict) else str(flag)
        if label and label not in existing:
            case["red_flags"].append(flag)


def handle_message(case: dict, text: str) -> dict:
    """Process one patient turn. Returns {case, reply, emergency, engine}."""
    if case["status"] in {case_model.STATUS_PENDING, case_model.STATUS_DELIVERED}:
        raise WorkflowError("This intake is closed; the case is already with a doctor.")
    text = (text or "").strip()[:2000]
    case["transcript"].append({"role": "patient", "at": case_model.now(),
                               "text": text})
    _audit(case, "patient", "patient_message", text[:300])

    # 1. Deterministic gate. Runs before the model and cannot be overridden.
    flags = safety.detect_red_flags(text)
    if flags:
        message = copy.EMERGENCY
        _merge_red_flags(case, flags)
        case["status"] = case_model.STATUS_EMERGENCY
        case["urgency"] = "emergency"
        case["engine"] = "rule gate (deterministic)"
        _say(case, message, engine="safety-rules")
        _audit(case, "safety", "red_flag_halt",
               "Matched: " + ", ".join(f["label"] for f in flags))
        store.save_case(case)
        return {"case": case, "reply": message,
                "emergency": True, "engine": case["engine"]}

    # 2. Model turn, with an explicit offline fallback.
    engine = ""
    data: dict
    if inference.have_key() and not config.demo_mode():
        try:
            user = ("Current case:\n" + _case_brief(case) +
                    "\n\nConversation so far:\n" + _transcript(case) +
                    "\n\nPatient's latest message:\n" + text)
            data = inference.ask_json(SYSTEM_PROMPT, user)
            engine = inference.engine_label()
        except inference.InferenceError as exc:
            data = _rule_analyze(text, case)
            engine = "rules (LLM unavailable)"
            _audit(case, "system", "inference_fallback", str(exc)[:300])
    else:
        data = _rule_analyze(text, case)
        engine = ("rules (demo mode)" if config.demo_mode()
                  else "rules (no inference key configured)")

    # 3. The model may also raise a red flag; the gate still wins.
    model_flags = _flag_labels(data.get("red_flags"))
    if _truthy(data.get("emergency")) or model_flags:
        message = copy.EMERGENCY
        _merge_red_flags(case, model_flags or [{"label": "model emergency flag",
                                               "phrase": "model flag"}])
        case["status"] = case_model.STATUS_EMERGENCY
        case["urgency"] = "emergency"
        case["engine"] = engine
        _say(case, message, engine=engine)
        _audit(case, "safety", "red_flag_halt", "Model flagged an emergency")
        store.save_case(case)
        return {"case": case, "reply": message,
                "emergency": True, "engine": engine}

    case_model.merge_analysis(case, data)
    case_model.ensure_summary(case)
    case["engine"] = engine
    reply = _reply_text(data.get("reply")) or copy.ASK_MORE
    reply, guarded = safety.guard_reply(reply)
    if guarded:
        _audit(case, "safety", "model_reply_guarded",
               f"Blocked {guarded} in a model reply")
    _say(case, reply, engine=engine)

    if case.get("care_options"):
        case_model.ensure_summary(case)
        _audit(case, "agent", "options_presented",
               "; ".join(o["name"] for o in case["care_options"]))
    store.save_case(case)
    return {"case": case, "reply": reply, "emergency": False, "engine": engine}


def attach_report(case_id: str, filename: str, content: bytes,
                  content_type: str = "") -> dict | None:
    """Read a patient report and merge the findings into the shared case."""
    case = store.get_case(case_id)
    if not case:
        return None
    if case["status"] in {case_model.STATUS_EMERGENCY,
                          case_model.STATUS_DELIVERED}:
        raise WorkflowError("Reports can only be attached before delivery.")

    text = reports.text_from_bytes(filename, content)
    parsed = reports.parse_report(text)
    path = reports.store_file(case_id, filename, content)
    entry = {
        "filename": reports.safe_name(filename),
        "content_type": (content_type or "")[:80],
        "size": len(content),
        "uploaded_at": case_model.now(),
        "summary": parsed["summary"],
        "findings": parsed["findings"],
        "path": path,
    }
    case.setdefault("reports", []).append(entry)
    case_model.ensure_summary(case)
    findings = case["summary"].setdefault("key_findings", [])
    line = f"Document {entry['filename']}: {parsed['summary']}"
    if line not in findings:
        findings.append(line[:400])
    abnormal = [f for f in parsed["findings"] if f.get("flag")]
    if abnormal:
        case["summary"].setdefault("safety_notes", []).append(
            "Abnormal lab values: " + ", ".join(
                f"{f['test']} {f['value']} ({f['flag']})" for f in abnormal)[:400])
    _audit(case, "patient", "report_uploaded",
           f"{entry['filename']} ({entry['size']} bytes, "
           f"{len(parsed['findings'])} findings)")
    _say(case, _document_question(entry, parsed), engine="report-reader")
    store.save_case(case)
    return case


def _document_question(entry: dict, parsed: dict) -> str:
    """Open a document-aware conversation without inventing a diagnosis."""
    name = entry.get("filename") or "the document"
    findings = parsed.get("findings") or []
    abnormal = [item for item in findings if item.get("flag")]
    if abnormal:
        first = abnormal[0]
        unit = f" {first.get('unit')}" if first.get("unit") else ""
        return (f"I read {name}. I can see {len(abnormal)} value(s) outside the "
                f"reference range, including {first.get('test')} "
                f"{first.get('value')}{unit} ({first.get('flag')}). Is this "
                "report related to your current symptoms, and when was it taken?")
    if findings:
        return (f"I read {name} and found {len(findings)} result(s). Is this "
                "related to your current symptoms, and when was the test taken?")
    return (f"I read {name}. Is it related to your current symptoms? What did "
            "your doctor say about it?")


def choose_option(case_id: str, option: str) -> dict | None:
    case = store.get_case(case_id)
    if not case:
        return None
    if case["status"] == case_model.STATUS_EMERGENCY:
        raise WorkflowError("This case was stopped by the emergency gate.")
    if case["status"] == case_model.STATUS_DELIVERED:
        raise WorkflowError("This case has already been delivered.")
    if case["status"] == case_model.STATUS_PENDING:
        if not option or option == case.get("selected_option"):
            return case
        raise WorkflowError("A care option is already being reviewed.")
    names = [o["name"] for o in case.get("care_options", [])]
    if not names:
        raise WorkflowError("No care options are available for this case yet.")
    if option not in names:
        raise WorkflowError("That care option is not available for this case.")
    case["selected_option"] = option
    case_model.ensure_summary(case)
    case["status"] = case_model.STATUS_PENDING
    _say(case, copy.fill(copy.CHOSEN, option=option), engine="template")
    _audit(case, "patient", "option_chosen", option)
    _audit(case, "agent", "case_ready_for_review", case["summary"]["one_liner"])
    store.save_case(case)
    return case


def _prepare_follow_up(case: dict) -> dict:
    days = 2.0
    try:
        days = max(0.0, float(config.env("FOLLOWUP_DAYS", "2")))
    except ValueError:
        pass
    due = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=days)
    token = secrets.token_urlsafe(24)
    case["follow_up"] = {
        "due_at": due.isoformat(),
        "token": token,
        "sent_at": "",
        "reports": case.get("follow_up", {}).get("reports", []),
    }
    return case["follow_up"]


def approve(case_id: str, *, advice: str, prescription: str = "",
            notes: str = "", doctor: str = "Dr. Demo") -> dict | None:
    case = store.get_case(case_id)
    if not case:
        return None
    if case["status"] == case_model.STATUS_EMERGENCY:
        raise WorkflowError("An emergency case cannot be approved here.")
    if case["status"] == case_model.STATUS_DELIVERED:
        raise WorkflowError("This case has already been approved and delivered.")
    if case["status"] != case_model.STATUS_PENDING:
        raise WorkflowError("The patient must choose a care option first.")
    if not (advice or "").strip():
        raise WorkflowError("Advice is required before approval.")

    case_model.ensure_summary(case)
    payments.ensure(case)
    case["doctor"] = {
        "notes": (notes or "").strip()[:2000],
        "advice": advice.strip()[:4000],
        "prescription": (prescription or "").strip()[:2000],
        "approved_by": (doctor or "Doctor").strip()[:120],
        "approved_at": case_model.now(),
    }
    previous_reports = list(case.get("follow_up", {}).get("reports", []))
    case["status"] = case_model.STATUS_DELIVERED
    follow = _prepare_follow_up(case)

    # Send before persisting delivery. If email fails, the case stays pending so
    # a doctor can retry instead of a half-delivered record appearing complete.
    try:
        delivered = emailer.send(case)
    except Exception as exc:
        case["status"] = case_model.STATUS_PENDING
        case["follow_up"] = {"due_at": "", "token": "", "sent_at": "",
                             "reports": previous_reports}
        _audit(case, "system", "email_failed",
               f"{type(exc).__name__}: {str(exc)[:300]}")
        store.save_case(case)
        raise WorkflowError(
            "The plan could not be emailed. The case is still pending; check "
            "the email settings and try again.") from exc

    stamp = case_model.now()
    store.schedule_followup(case["case_id"], follow["token"], follow["due_at"],
                            stamp)
    case["email"] = {"to": delivered["to"], "subject": delivered["subject"],
                     "mode": delivered["mode"], "sent_at": stamp}
    store.save_email(case["case_id"], stamp, delivered["to"],
                     delivered["subject"], delivered["mode"], delivered["path"])
    _audit(case, "doctor", "case_approved",
           f"Approved by {case['doctor']['approved_by']}")
    _audit(case, "agent", "followup_scheduled", follow["due_at"])
    _audit(case, "agent", "email_delivered",
           f"mode={delivered['mode']} to={delivered['to']}")
    _say(case, f"The approved plan was sent to {delivered['to']} "
               f"({delivered['mode']} delivery).", engine="template")
    store.save_case(case)
    return case


def follow_up(case_id: str, report: str) -> dict | None:
    case = store.get_case(case_id)
    if not case:
        return None
    if (case["status"] not in {case_model.STATUS_DELIVERED,
                               case_model.STATUS_EMERGENCY}
            or not case.get("doctor", {}).get("approved_at")):
        raise WorkflowError(
            "A follow-up is only available after a doctor has delivered a plan.")
    report = (report or "").strip()[:2000]
    if not report:
        raise WorkflowError("A follow-up report is required.")
    flags = safety.detect_red_flags(report)
    _audit(case, "patient", "follow_up_report", report[:300])
    entry = {"at": case_model.now(), "text": report,
             "red_flags": [f["label"] for f in flags]}
    case.setdefault("follow_up", {}).setdefault("reports", []).append(entry)
    if flags:
        case["status"] = case_model.STATUS_EMERGENCY
        case["urgency"] = "emergency"
        case["needs_attention"] = True
        _say(case, copy.EMERGENCY, engine="safety-rules")
        _audit(case, "safety", "follow_up_escalated",
               "Matched: " + ", ".join(f["label"] for f in flags))
        try:
            emailer.send_alert(case, "Follow-up red flags: " +
                               ", ".join(f["label"] for f in flags))
        except OSError:
            _audit(case, "system", "alert_failed", "SMTP delivery failed")
    else:
        _say(case, copy.FOLLOWUP_ACK, engine="template")
        _audit(case, "agent", "follow_up_logged", "No emergency flag in report")
    store.save_case(case)
    return case


def follow_up_by_token(token: str, report: str) -> dict | None:
    row = store.get_followup_by_token(token)
    if not row:
        return None
    return follow_up(row["case_id"], report)


def _case_brief(case: dict) -> str:
    import json
    brief = {key: case.get(key) for key in
             ("patient", "chief_complaint", "symptoms", "duration_days",
              "severity", "red_flags")}
    brief["reports"] = [
        {key: value for key, value in report.items() if key != "path"}
        for report in case.get("reports", [])
    ]
    brief["prior_cases"] = store.prior_cases(case, limit=4)
    return json.dumps(brief, ensure_ascii=False)


def _transcript(case: dict) -> str:
    lines = []
    for entry in case.get("transcript", [])[-12:]:
        lines.append(f"{entry['role']}: {entry['text']}")
    return "\n".join(lines)
