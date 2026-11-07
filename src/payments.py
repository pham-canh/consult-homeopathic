"""Demo-only consultation fee.

No card details are collected, no network call is made, and no money moves.
The case stores a small receipt so the patient page and doctor dashboard can
show the full demo flow. Real payments belong in a separate, compliant build.
"""
from __future__ import annotations

from datetime import datetime, timezone

from config import env

DEMO_NOTE = ("Demo only — no real charge. No card details are collected or "
             "stored.")
METHODS = [
    ("card", "Card (demo)"),
    ("bank_transfer", "Bank transfer (demo)"),
    ("pay_at_clinic", "Pay at clinic (demo)"),
]
_METHODS = dict(METHODS)


def amount_cents() -> int:
    try:
        return max(0, int(env("CONSULTATION_FEE_CENTS", "2900")))
    except ValueError:
        return 2900


def currency() -> str:
    return (env("CONSULTATION_FEE_CURRENCY", "USD") or "USD").upper()[:8]


def amount_display() -> str:
    amount = amount_cents() / 100
    if currency() == "USD":
        return f"${amount:,.2f}"
    return f"{amount:,.2f} {currency()}"


def new_payment() -> dict:
    return {
        "status": "unpaid",
        "amount_cents": amount_cents(),
        "currency": currency(),
        "amount_display": amount_display(),
        "method": "",
        "method_label": "",
        "paid_at": "",
        "demo": True,
    }


def ensure(case: dict) -> dict:
    payment = case.get("payment")
    if not isinstance(payment, dict):
        payment = new_payment()
        case["payment"] = payment
    payment.setdefault("status", "unpaid")
    payment.setdefault("amount_cents", amount_cents())
    payment.setdefault("currency", currency())
    payment.setdefault("amount_display", amount_display())
    payment.setdefault("method", "")
    payment.setdefault("method_label", "")
    payment.setdefault("paid_at", "")
    payment["demo"] = True
    return payment


def public(case: dict) -> dict:
    payment = dict(ensure(case))
    payment["amount_display"] = payment.get("amount_display") or amount_display()
    payment["methods"] = [
        {"value": value, "label": label} for value, label in METHODS
    ]
    payment["note"] = DEMO_NOTE
    return payment


def pay(case: dict, method: str) -> dict:
    key = (method or "").strip().lower()
    if key not in _METHODS:
        raise ValueError("Choose a valid demo payment method.")
    payment = ensure(case)
    if payment.get("status") == "paid_demo":
        return payment
    payment.update({
        "status": "paid_demo",
        "method": key,
        "method_label": _METHODS[key],
        "paid_at": datetime.now(timezone.utc).replace(
            microsecond=0).isoformat(),
    })
    return payment
