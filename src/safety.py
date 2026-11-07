"""Deterministic emergency screening.

The rule layer runs before any model call and cannot be overridden by the LLM:
if a red flag matches, the automated flow stops and the patient is told to seek
emergency care. A regex list is intentionally boring and auditable.
"""
from __future__ import annotations

import re

# (label, pattern). Patterns are case-insensitive and match phrases a patient
# would actually type, not clinical codes.
RULES: list[tuple[str, str]] = [
    ("chest pain", r"\bchest\s+(pain|pressure|tightness|heaviness)\b|"
                   r"\bpain\s+in\s+(my\s+|the\s+)?chest\b|"
                   r"\bcrushing\s+chest\b"),
    ("breathing difficulty", r"\b(can'?t|cannot|difficulty|trouble)\s+(to\s+)?breath(e|ing)\b|"
                             r"\bshort(ness)?\s+of\s+breath\b|"
                             r"\bnot\s+breathing\b|\bgasping\b|\bchoking\b"),
    ("stroke signs", r"\bface\s+(droop|drooping|numb)\b|\barm\s+(weak|numb)\b|"
                     r"\bslurred\s+speech\b|\bsudden\s+(confusion|vision\s+loss)\b|"
                     r"\bcan'?t\s+speak\b"),
    ("severe bleeding", r"\b(heavy|severe|uncontrolled)\s+bleeding\b|"
                        r"\bbleeding\s+(won'?t|will\s+not|doesn'?t)\s+stop\b|"
                        r"\bvomiting\s+blood\b|\bblood\s+in\s+(my\s+)?(vomit|stool)\b"),
    ("severe allergic reaction", r"\b(throat|tongue|lips)\s+(swelling|swollen)\b|"
                                 r"\bcan'?t\s+swallow\b|\banaphyla\w*\b|"
                                 r"\bsevere\s+allergic\s+reaction\b"),
    ("self-harm risk", r"\bsuicid\w*\b|\bkill\s+myself\b|\bself[-\s]?harm\b|"
                       r"\bend\s+my\s+life\b|\bwant\s+to\s+die\b"),
    ("seizure or unconsciousness", r"\bseizure\b|\bconvuls\w*\b|\bunconscious\b|"
                                   r"\bpassed\s+out\b|\bnot\s+waking\s+up\b"),
    ("severe head injury", r"\bhead\s+injury\b.*\b(vomit|confus|unconscious)\w*|"
                           r"\bhit\s+(my\s+)?head\b.*\b(vomit|confus|unconscious)\w*"),
    ("sudden severe headache", r"\b(worst|thunderclap|sudden\s+severe)\s+headache\b"),
    ("stiff neck or confusion", r"\bstiff\s+neck\b|"
                                r"\bneck\s+(?:is\s+|feels?\s+)?stiff\b|"
                                r"\bconfus(?:ed|ion)\b|\bdisoriented\b|"
                                r"\baltered\s+mental\s+status\b"),
    ("pregnancy bleeding", r"\bpregnan\w*\b.*\bbleeding\b|\bbleeding\b.*\bpregnan\w*\b"),
]

# Negation only applies inside the current clause. A contrast word ("but",
# "however") or a new clause starts a fresh scope, so "no fever but chest pain"
# is still an emergency. "or" deliberately stays inside the scope because
# "no chest pain or shortness of breath" negates both symptoms.
CLAUSE_BREAK = re.compile(
    r"[.;,]\s*|\b(?:but|however|although|though|except|yet|instead|and)\b",
    re.IGNORECASE,
)
NEGATIONS = re.compile(
    r"\b(?:no|not|without|denies|denied|never|no\s+longer)\b"
    r"(?:\s+\w+){0,3}\s*$"
    r"|\b(?:don'?t|doesn'?t|didn'?t|isn'?t|wasn'?t|weren'?t|"
    r"hasn'?t|haven'?t|hadn'?t)\b(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE,
)

EMERGENCY_MESSAGE = (
    "This may be a medical emergency. Please call your local emergency number "
    "now (for example 115 in Vietnam, 911 in the US, 999 in the UK) or go to the "
    "nearest emergency department. Do not wait for an online review. "
    "This prototype has stopped the automated intake."
)

# Backstop for free-text model replies. The system prompt already forbids
# prescribing, but a prompt is not a hard guarantee; this blocks the most
# explicit treatment instructions before they reach a patient.
REPLY_GUARD = [
    ("dose instruction", re.compile(
        # "take/start ... 500 mg" anywhere except a patient-history sentence
        # such as "You take metformin 500 mg daily, is that correct?".
        r"(?<!you\s)\b(?:take|start|use|try)\b[^.]{0,60}\d+(?:\.\d+)?\s*"
        r"(?:mg|mcg|µg|g|ml)\b|"
        r"(?<!you\s)\b(?:take|start|use|try)\s+"
        r"(?:\d+|one|two|three|four|five|six)\s+"
        r"(?:tablets?|capsules?|pills?|doses?)\b|"
        # A bare prescription line such as "Amoxicillin 500 mg twice daily."
        r"(?:^|[.!?:]\s*)[A-Z][A-Za-z-]{2,}\s+\d+(?:\.\d+)?\s*"
        r"(?:mg|mcg|µg|g|ml)\b(?!\s*/)|"
        r"\b(?:i|we)\s+(?:can|could|will|would|have|'ve)\s+prescrib|"
        r"\b(?:i|we)\s+(?:recommend|suggest)\b[^.]{0,80}"
        r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml)\b|"
        r"\b(?:dose|dosage)\s*(?:is|:)\s*\d+(?:\.\d+)?\s*"
        r"(?:mg|mcg|µg|g|ml)\b|"
        r"\bprescription\s*:|"
        r"\b(?:the\s+)?prescription\s+is\b[^.]{0,60}"
        r"\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml)\b",
        re.IGNORECASE)),
    ("diagnosis statement", re.compile(
        r"\b(?:my|the)\s+diagnosis\s+is\b|\bdiagnosis\s*[:\-]|"
        r"\bi\s+diagnose\b|\byou\s+are\s+diagnosed\b|"
        r"\b(?:i|we)\s+(?:think|believe|suspect)\s+you\b|"
        r"\byou\s+(?:likely|probably)\s+have\b",
        re.IGNORECASE)),
]

SAFE_REPLY = (
    "I cannot provide a diagnosis or a treatment plan. A licensed doctor will "
    "review your case and decide what is appropriate."
)


def guard_reply(text: str) -> tuple[str, str]:
    """Return (safe_text, reason). reason is empty when the reply is allowed."""
    for reason, pattern in REPLY_GUARD:
        if pattern.search(text or ""):
            return SAFE_REPLY, reason
    return text, ""


def _is_negated(text: str, start: int) -> bool:
    before = text[max(0, start - 60):start]
    clause = CLAUSE_BREAK.split(before)[-1]
    return bool(NEGATIONS.search(clause))


def detect_red_flags(text: str) -> list[dict]:
    """Return matched red flags, skipping phrases that are explicitly negated."""
    found: list[dict] = []
    seen: set[str] = set()
    source = text or ""
    for label, pattern in RULES:
        for match in re.finditer(pattern, source, re.IGNORECASE):
            if _is_negated(source, match.start()):
                continue
            if label in seen:
                continue
            seen.add(label)
            found.append({"label": label, "phrase": match.group(0).strip()})
            break
    return found


def is_emergency(text: str) -> bool:
    return bool(detect_red_flags(text))
