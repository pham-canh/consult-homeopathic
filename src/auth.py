"""Shared-password access control for the staff dashboard.

Set CONSULT_DASHBOARD_PASSWORD to turn on the login page and protect every
staff-only read/write API. When it is empty the dashboard stays open for local
demos and automated tests. Session cookies are signed with
CONSULT_SESSION_SECRET, or a key derived from the password when that is unset.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

import config

COOKIE = "consult_session"
SESSION_SECONDS = 8 * 3600
MAX_FAILURES = 5
WINDOW_SECONDS = 60

_FAILURES: dict[str, deque[float]] = defaultdict(deque)


def enabled() -> bool:
    return bool(config.env("CONSULT_DASHBOARD_PASSWORD"))


def user() -> str:
    return config.env("CONSULT_DASHBOARD_USER", "doctor") or "doctor"


def _password() -> str:
    return config.env("CONSULT_DASHBOARD_PASSWORD")


def _secret() -> bytes:
    value = config.env("CONSULT_SESSION_SECRET")
    if value:
        return value.encode("utf-8")
    return hashlib.sha256(
        ("consult-dashboard:" + _password()).encode("utf-8")).digest()


def _sign(body: str) -> str:
    return hmac.new(_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()


def issue() -> str:
    payload = {
        "sub": user(),
        "exp": int(time.time()) + SESSION_SECONDS,
    }
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"{body}.{_sign(body)}"


def read(token: str) -> str:
    if not token or "." not in token:
        return ""
    body, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(body)):
        return ""
    try:
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    try:
        expires = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return ""
    if expires < int(time.time()):
        return ""
    return str(payload.get("sub") or "")


def current_user(request: Request) -> str:
    return read(request.cookies.get(COOKIE, ""))


def check_password(value: str) -> bool:
    password = _password()
    return bool(password) and hmac.compare_digest(value or "", password)


def _client(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def blocked(request: Request) -> bool:
    bucket = _FAILURES[_client(request)]
    cutoff = time.monotonic() - WINDOW_SECONDS
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    return len(bucket) >= MAX_FAILURES


def note_failure(request: Request) -> None:
    _FAILURES[_client(request)].append(time.monotonic())


def clear_failures(request: Request) -> None:
    _FAILURES.pop(_client(request), None)


def reset_attempts() -> None:
    _FAILURES.clear()


def require(request: Request) -> None:
    if not enabled():
        return
    if not current_user(request):
        raise HTTPException(status_code=401, detail="Sign in to the dashboard.")
