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
    ("pregnancy bleeding", r"\bpregnan\w*\b.*\bbleeding\b|\bbleeding\b.*\bpregnan\w*\b"),
]

NEGATIONS = re.compile(
    r"\b(no|not|without|denies|never|don'?t|do\s+not|doesn'?t|isn'?t|wasn'?t)\b[^.]{0,24}$",
    re.IGNORECASE,
)

EMERGENCY_MESSAGE = (
    "This may be a medical emergency. Please call your local emergency number "
    "now (for example 115 in Vietnam, 911 in the US, 999 in the UK) or go to the "
    "nearest emergency department. Do not wait for an online review. "
    "This prototype has stopped the automated intake."
)


def detect_red_flags(text: str) -> list[dict]:
    """Return matched red flags, skipping phrases that are explicitly negated."""
    found: list[dict] = []
    seen: set[str] = set()
    for label, pattern in RULES:
        for match in re.finditer(pattern, text or "", re.IGNORECASE):
            before = text[max(0, match.start() - 40):match.start()]
            if NEGATIONS.search(before):
                continue
            if label in seen:
                continue
            seen.add(label)
            found.append({"label": label, "phrase": match.group(0).strip()})
            break
    return found


def is_emergency(text: str) -> bool:
    return bool(detect_red_flags(text))
