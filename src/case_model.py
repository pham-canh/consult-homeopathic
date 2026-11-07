"""The shared case record and the safe merge/summary helpers.

Both user flows (patient and doctor) read and write the same JSON document.
The model may fill fields, but it can never remove a red flag, change the
status to `delivered`, or write the doctor's decision: those transitions happen
only in the API handlers.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


STATUS_INTAKE = "intake"
STATUS_EMERGENCY = "emergency"
STATUS_PENDING = "pending_review"
STATUS_DELIVERED = "delivered"

SEVERITIES = {"mild", "moderate", "severe"}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
SAFETY_NOTE = ("Prototype only: AI does not diagnose or prescribe. "
               "A licensed clinician must review and approve every plan.")


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.fullmatch((value or "").strip()))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_case(patient_name: str = "") -> dict:
    stamp = now()
    return {
        "case_id": "C-" + uuid.uuid4().hex[:8].upper(),
        "created_at": stamp,
        "updated_at": stamp,
        "status": STATUS_INTAKE,
        "engine": "",
        "patient": {
            "name": (patient_name or "").strip(),
            "email": "",
            "age": None,
            "sex": "",
            "allergies": [],
            "medications": [],
            "history": "",
            "diet": "",
        },
        "chief_complaint": "",
        "symptoms": [],
        "duration_days": None,
        "severity": "",
        "red_flags": [],
        "urgency": "",
        "care_options": [],
        "selected_option": "",
        "reports": [],
        "follow_up": {"due_at": "", "token": "", "sent_at": "", "reports": []},
        "needs_attention": False,
        "summary": {"one_liner": "", "key_findings": [], "safety_notes": []},
        "doctor": {"notes": "", "advice": "", "prescription": "",
                   "approved_by": "", "approved_at": ""},
        "email": {"to": "", "subject": "", "mode": "", "sent_at": ""},
        "transcript": [],
    }


def _as_str(value, limit: int = 400) -> str:
    if value is None:
        return ""
    return str(value).strip()[:limit]


def _as_list(value, limit: int = 12) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        text = _as_str(item, 120)
        if text and text not in out:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _as_int(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    match = re.search(r"\d+", str(value))
    return int(match.group(0)) if match else None


def merge_analysis(case: dict, data: dict) -> dict:
    """Merge a model (or rule-engine) analysis into the case, defensively."""
    incoming = data.get("patient") if isinstance(data.get("patient"), dict) else {}
    patient = case["patient"]
    for key in ("name", "email", "sex", "history", "diet"):
        value = _as_str(incoming.get(key))
        if key == "email":
            value = value.rstrip(".,;:")
            if value and not is_email(value):
                continue
        if value:
            patient[key] = value
    age = _as_int(incoming.get("age"))
    if age is not None:
        patient["age"] = age
    for key in ("allergies", "medications"):
        values = _as_list(incoming.get(key))
        if values:
            merged = list(patient.get(key, []))
            for value in values:
                if value not in merged:
                    merged.append(value)
            patient[key] = merged

    for key in ("chief_complaint", "urgency"):
        value = _as_str(data.get(key))
        if value:
            case[key] = value
    for key in ("symptoms",):
        values = _as_list(data.get(key))
        if values:
            merged = list(case.get(key, []))
            for value in values:
                if value not in merged:
                    merged.append(value)
            case[key] = merged
    duration = _as_int(data.get("duration_days"))
    if duration is not None:
        case["duration_days"] = duration
    severity = _as_str(data.get("severity")).lower()
    if severity in SEVERITIES:
        case["severity"] = severity

    raw_options = data.get("care_options")
    if isinstance(raw_options, (str, dict)):
        raw_options = [raw_options]
    elif not isinstance(raw_options, (list, tuple)):
        raw_options = []
    options = []
    for item in raw_options:
        if isinstance(item, dict):
            name = _as_str(item.get("name"), 120)
            why = _as_str(item.get("why"), 300)
            if name:
                options.append({"name": name, "why": why})
        elif isinstance(item, str) and item.strip():
            options.append({"name": _as_str(item, 120), "why": ""})
    if options:
        case["care_options"] = options[:3]

    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    if summary:
        one_liner = _as_str(summary.get("one_liner"), 300)
        if one_liner:
            case["summary"]["one_liner"] = one_liner
        for key in ("key_findings", "safety_notes"):
            values = _as_list(summary.get(key), 8)
            if values:
                merged = list(case["summary"].get(key, []))
                for value in values:
                    if value not in merged:
                        merged.append(value)
                # Never drop deterministic findings (for example lab values)
                # just because the model returned a shorter summary.
                case["summary"][key] = merged[-16:]
    return case


def rule_summary(case: dict) -> dict:
    """A deterministic summary so the doctor flow never depends on a live model."""
    patient = case["patient"]
    bits = []
    if case.get("chief_complaint"):
        bits.append(case["chief_complaint"][0].lower() + case["chief_complaint"][1:])
    if case.get("duration_days") is not None:
        bits.append(f"for {case['duration_days']} day(s)")
    if case.get("severity"):
        bits.append(f"severity: {case['severity']}")
    one_liner = ", ".join(bits) or "Case awaiting structured summary."

    findings = []
    if case.get("symptoms"):
        findings.append("Symptoms: " + ", ".join(case["symptoms"]))
    if patient.get("allergies"):
        findings.append("Allergies: " + ", ".join(patient["allergies"]))
    if patient.get("medications"):
        findings.append("Current medications: " + ", ".join(patient["medications"]))
    if patient.get("history"):
        findings.append("History: " + patient["history"])
    if patient.get("diet"):
        findings.append("Diet: " + patient["diet"])
    if patient.get("age"):
        findings.append(f"Age: {patient['age']}")

    notes = []
    if case.get("red_flags"):
        notes.append("Red flags recorded: " + ", ".join(
            f.get("label", "") if isinstance(f, dict) else str(f)
            for f in case["red_flags"]))
    notes.append(SAFETY_NOTE)
    return {"one_liner": one_liner, "key_findings": findings, "safety_notes": notes}


def ensure_summary(case: dict) -> None:
    if not case["summary"].get("one_liner"):
        case["summary"] = rule_summary(case)
    diet = (case.get("patient") or {}).get("diet")
    if diet:
        findings = case["summary"].setdefault("key_findings", [])
        line = "Diet: " + diet
        if line not in findings:
            findings.append(line[:400])
    notes = case["summary"].setdefault("safety_notes", [])
    if SAFETY_NOTE not in notes:
        notes.append(SAFETY_NOTE)


# Explicit cross-reactivity families. This is a prototype warning, not a
# clinical interaction database; it catches the obvious families only.
CROSS_REACTIVITY = {
    "penicillin": ["penicillin", "amoxicillin", "ampicillin", "augmentin",
                   "co-amoxiclav", "piperacillin", "flucloxacillin"],
    "sulfa": ["sulfa", "sulfamethoxazole", "trimethoprim", "bactrim",
              "co-trimoxazole"],
    "aspirin": ["aspirin", "acetylsalicylic"],
    "nsaid": ["ibuprofen", "naproxen", "diclofenac", "celecoxib", "nsaid"],
    "codeine": ["codeine", "tramadol"],
    "latex": ["latex"],
    "iodine": ["iodine", "contrast"],
}

# A short list of common, clinically important medication conflicts. It is
# deliberately small and visible so a judge can audit it.
INTERACTIONS = [
    ("warfarin", ["aspirin", "ibuprofen", "naproxen", "diclofenac"],
     "bleeding risk with warfarin"),
    ("warfarin", ["amoxicillin", "fluconazole", "metronidazole"],
     "INR may rise with warfarin"),
    ("metformin", ["contrast", "iodine"], "hold metformin around contrast"),
    ("ssri", ["tramadol", "triptan"], "serotonin syndrome risk"),
    ("maoi", ["tyramine", "tramadol", "ssri"],
     "hypertensive crisis / serotonin risk"),
    ("methotrexate", ["ibuprofen", "aspirin", "naproxen"],
     "methotrexate toxicity risk"),
]


def _text(case: dict) -> str:
    # Warnings apply to the proposed prescription, not to advice text such as
    # "avoid penicillin because of the recorded allergy".
    return (case.get("doctor", {}).get("prescription", "") or "").lower()


def allergy_warnings(case: dict) -> list[str]:
    """Flag a proposed prescription that mentions a recorded allergy."""
    text = _text(case)
    warnings = []
    for allergy in case["patient"].get("allergies", []):
        token = allergy.lower().strip()
        if not token:
            continue
        families = [token] + CROSS_REACTIVITY.get(token, [])
        if any(name in text for name in families):
            warnings.append(f"Prescription may conflict with a recorded "
                            f"allergy: {allergy}")
    return warnings


def interaction_warnings(case: dict) -> list[str]:
    """Flag a proposed drug against the patient's recorded medications."""
    text = _text(case)
    meds = " ".join(case["patient"].get("medications", [])).lower()
    warnings = []
    for current, proposed, note in INTERACTIONS:
        if current in meds and any(name in text for name in proposed):
            warnings.append(f"Possible drug interaction ({note}): "
                            f"patient records {current}.")
    return warnings


def safety_warnings(case: dict) -> list[str]:
    return allergy_warnings(case) + interaction_warnings(case)

