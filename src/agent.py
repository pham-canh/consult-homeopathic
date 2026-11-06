"""The multi-step workflow: intake -> safety gate -> options -> doctor -> email.

The flow is deliberately split so the AI only does the information work. It can
ask questions, extract a structured case, and suggest care paths. It cannot set
the doctor's decision, cannot prescribe, and cannot override the emergency gate.
"""
from __future__ import annotations

import re

import case_model
import emailer
import inference
import safety
import store

SYSTEM_PROMPT = """You are the intake assistant for a clinic prototype. You gather
information; a licensed doctor makes every medical decision. Never diagnose, never
prescribe, never give a treatment dose. Be warm, brief, and plain-spoken.

Return ONLY a JSON object with exactly these keys:
{
  "reply": "what to say to the patient next (max 70 words)",
  "emergency": false,
  "red_flags": ["..."],
  "patient": {"name": "", "email": "", "age": null, "sex": "",
              "allergies": [], "medications": [], "history": ""},
  "chief_complaint": "",
  "symptoms": [],
  "duration_days": null,
  "severity": "mild|moderate|severe|",
  "care_options": [{"name": "", "why": ""}],
  "summary": {"one_liner": "", "key_findings": [], "safety_notes": []},
  "ready_for_review": false
}

Rules:
- Keep every field already present in the case; only fill gaps or correct details.
- Detect emergency red flags (chest pain, trouble breathing, stroke signs, severe
  bleeding, throat/tongue swelling, self-harm, seizure, severe head injury).
- Ask at most two short follow-up questions. Collect duration, severity, allergies,
  medications, and an email address for the plan.
- When you have a complaint, duration, and severity, return 2-3 care_options and
  set ready_for_review true. Options must be care paths, not diagnoses, e.g.
  "Online doctor review", "In-person visit", "Self-care with monitoring".
- summary.key_findings and safety_notes must be short factual strings.
"""

GREETING = (
    "Hello, I am the intake assistant for Consult Homeopathic Physicians "
    "(a prototype). I can collect your symptoms and prepare a case for a doctor, "
    "but I cannot diagnose or prescribe. What brings you in today?"
)

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


def start_case(name: str = "", email: str = "") -> dict:
    store.init_db()
    case = case_model.new_case(name)
    if email.strip():
        case["patient"]["email"] = email.strip()[:160]
    _say(case, GREETING, engine="template")
    case["transcript"].append({
        "role": "patient", "at": case_model.now(),
        "text": f"(new case started by {name or 'a patient'})",
    })
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

    if not case.get("chief_complaint") and data["symptoms"]:
        data["chief_complaint"] = data["symptoms"][0][0].upper() + \
            data["symptoms"][0][1:] + " reported by the patient"

    has_basics = bool(case.get("chief_complaint") or data.get("chief_complaint"))
    has_duration = case.get("duration_days") is not None or \
        data.get("duration_days") is not None
    has_severity = bool(case.get("severity") or data.get("severity"))
    if has_basics and has_duration and has_severity:
        data["care_options"] = DEFAULT_OPTIONS
        data["ready_for_review"] = True
        data["summary"] = {
            "one_liner": (data.get("chief_complaint") or case.get("chief_complaint")
                          or "Case summary")[:200] + (
                              f", {data.get('duration_days') or case.get('duration_days')} day(s)"
                              if (data.get("duration_days") or case.get("duration_days")) else ""),
            "key_findings": [],
            "safety_notes": [],
        }
        data["reply"] = ("Thank you. I have enough to prepare a case. Here are "
                         "the care options I suggest; please choose one.")
    else:
        missing = []
        if not has_basics:
            missing.append("your main symptom")
        if not has_duration:
            missing.append("how long it has lasted")
        if not has_severity:
            missing.append("how mild or severe it feels")
        if not (case["patient"].get("email") or data["patient"].get("email")):
            missing.append("an email address for the plan")
        data["reply"] = ("Thanks. To prepare the case, could you tell me " +
                         ", ".join(missing) + "?")
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
    text = (text or "").strip()[:2000]
    case["transcript"].append({"role": "patient", "at": case_model.now(),
                               "text": text})
    _audit(case, "patient", "patient_message", text[:300])

    # 1. Deterministic gate. Runs before the model and cannot be overridden.
    flags = safety.detect_red_flags(text)
    if flags:
        _merge_red_flags(case, flags)
        case["status"] = case_model.STATUS_EMERGENCY
        case["urgency"] = "emergency"
        case["engine"] = "rule gate (deterministic)"
        _say(case, safety.EMERGENCY_MESSAGE, engine="safety-rules")
        _audit(case, "safety", "red_flag_halt",
               "Matched: " + ", ".join(f["label"] for f in flags))
        store.save_case(case)
        return {"case": case, "reply": safety.EMERGENCY_MESSAGE,
                "emergency": True, "engine": case["engine"]}

    # 2. Model turn, with an explicit offline fallback.
    engine = ""
    data: dict
    if inference.have_key():
        try:
            user = ("Current case:\n" + _case_brief(case) +
                    "\n\nConversation so far:\n" + _transcript(case) +
                    "\n\nPatient's latest message:\n" + text)
            data = inference.ask_json(SYSTEM_PROMPT, user)
            engine = inference.engine_label()
        except inference.InferenceError as exc:
            data = _rule_analyze(text, case)
            engine = f"rules (LLM unavailable: {str(exc)[:120]})"
    else:
        data = _rule_analyze(text, case)
        engine = "rules (no inference key configured)"

    # 3. The model may also raise a red flag; the gate still wins.
    model_flags = []
    for item in data.get("red_flags") or []:
        label = item.get("label") if isinstance(item, dict) else str(item)
        if label:
            model_flags.append({"label": label[:80], "phrase": "model flag"})
    if data.get("emergency") or model_flags:
        _merge_red_flags(case, model_flags or [{"label": "model emergency flag",
                                               "phrase": "model flag"}])
        case["status"] = case_model.STATUS_EMERGENCY
        case["urgency"] = "emergency"
        case["engine"] = engine
        _say(case, safety.EMERGENCY_MESSAGE, engine=engine)
        _audit(case, "safety", "red_flag_halt", "Model flagged an emergency")
        store.save_case(case)
        return {"case": case, "reply": safety.EMERGENCY_MESSAGE,
                "emergency": True, "engine": engine}

    case_model.merge_analysis(case, data)
    case["engine"] = engine
    reply = (data.get("reply") or "").strip() or \
        "Thank you. Could you tell me a little more about your symptoms?"
    _say(case, reply, engine=engine)

    if case.get("care_options"):
        case["summary"] = case["summary"] or case_model.rule_summary(case)
        _audit(case, "agent", "options_presented",
               "; ".join(o["name"] for o in case["care_options"]))
    store.save_case(case)
    return {"case": case, "reply": reply, "emergency": False, "engine": engine}


def choose_option(case_id: str, option: str) -> dict | None:
    case = store.get_case(case_id)
    if not case:
        return None
    if case["status"] == case_model.STATUS_EMERGENCY:
        return case
    names = [o["name"] for o in case.get("care_options", [])]
    if option not in names:
        option = names[0] if names else option
    case["selected_option"] = option
    case_model.ensure_summary(case)
    case["status"] = case_model.STATUS_PENDING
    _say(case, f"You chose: {option}. I have sent the structured case to the "
               "doctor dashboard. A clinician will review it before anything "
               "reaches you.", engine="template")
    _audit(case, "patient", "option_chosen", option)
    _audit(case, "agent", "case_ready_for_review", case["summary"]["one_liner"])
    store.save_case(case)
    return case


def approve(case_id: str, *, advice: str, prescription: str = "",
            notes: str = "", doctor: str = "Dr. Demo") -> dict | None:
    case = store.get_case(case_id)
    if not case:
        return None
    case_model.ensure_summary(case)
    case["doctor"] = {
        "notes": (notes or "").strip()[:2000],
        "advice": (advice or "").strip()[:4000],
        "prescription": (prescription or "").strip()[:2000],
        "approved_by": (doctor or "Doctor").strip()[:120],
        "approved_at": case_model.now(),
    }
    case["status"] = case_model.STATUS_DELIVERED
    _audit(case, "doctor", "case_approved",
           f"Approved by {case['doctor']['approved_by']}")
    delivered = emailer.send(case)
    case["email"] = {"to": delivered["to"], "subject": delivered["subject"],
                     "mode": delivered["mode"], "sent_at": case_model.now()}
    store.save_email(case["case_id"], case["email"]["sent_at"], delivered["to"],
                     delivered["subject"], delivered["mode"], delivered["path"])
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
    flags = safety.detect_red_flags(report)
    _audit(case, "patient", "follow_up_report", report[:300])
    if flags:
        case["status"] = case_model.STATUS_EMERGENCY
        case["urgency"] = "emergency"
        _say(case, safety.EMERGENCY_MESSAGE, engine="safety-rules")
        _audit(case, "safety", "follow_up_escalated",
               "Matched: " + ", ".join(f["label"] for f in flags))
    else:
        _say(case, "Thank you for the update. The clinic has been notified; "
                   "a clinician will contact you if needed.", engine="template")
        _audit(case, "agent", "follow_up_logged", "No emergency flag in report")
    store.save_case(case)
    return case


def _case_brief(case: dict) -> str:
    import json
    brief = {key: case.get(key) for key in
             ("patient", "chief_complaint", "symptoms", "duration_days",
              "severity", "red_flags")}
    return json.dumps(brief, ensure_ascii=False)


def _transcript(case: dict) -> str:
    lines = []
    for entry in case.get("transcript", [])[-12:]:
        lines.append(f"{entry['role']}: {entry['text']}")
    return "\n".join(lines)
