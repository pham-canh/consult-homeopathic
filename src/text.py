"""Patient-facing copy for the deterministic paths.

The model writes its own replies, but these strings are used for the greeting,
the emergency stop, the offline rule engine, and follow-up messages so the
product is complete even without an inference key.
"""
from __future__ import annotations

GREETING = (
    "Hello, I am the intake assistant for Consult Homeopathic Physicians "
    "(a prototype). I can collect your symptoms and prepare a case for a "
    "doctor, but I cannot diagnose or prescribe. What brings you in today?"
)

ASK_MORE = (
    "Thanks. To prepare the case, could you tell me your main symptom, how "
    "long it has lasted, how mild or severe it feels, and an email address "
    "for the plan?"
)

OPTIONS_READY = (
    "Thank you. I have enough to prepare a case. Here are the care options "
    "I suggest; please choose one."
)

CHOSEN = (
    "You chose: {option}. I have sent the structured case to the doctor "
    "dashboard. A clinician will review it before anything reaches you."
)

EMERGENCY = (
    "This may be a medical emergency. Please call your local emergency number "
    "now (115 in Vietnam, 911 in the US, 999 in the UK) or go to the nearest "
    "emergency department. Do not wait for an online review. This prototype "
    "has stopped the automated intake."
)

FOLLOWUP_ACK = (
    "Thank you for the update. The clinic has been notified; a clinician will "
    "contact you if needed."
)

FOLLOWUP_CHECKIN = (
    "Hello {name}, this is a check-in from Consult Homeopathic Physicians "
    "about case {case_id}. How are you feeling? If your symptoms are worse or "
    "you feel unsafe, reply immediately or seek emergency care."
)


def fill(template: str, **values: str) -> str:
    for name, value in values.items():
        template = template.replace("{" + name + "}", str(value))
    return template
