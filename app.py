#!/usr/bin/env python3
"""Consult Homeopathic Physicians — FastAPI app.

Two user flows in one public web app:
  /              patient intake chat (optional lab report)
  /doctor        doctor dashboard (review, edit, approve, email)
  /follow-up/... patient follow-up check-in

SQLite stores cases, the audit trail, the follow-up schedule, and the simulated
mailbox. Every model call goes through the configured inference provider.
"""
from __future__ import annotations

import base64
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fastapi import (Depends, FastAPI, File, HTTPException, Request, Response,  # noqa: E402
                     UploadFile)
from fastapi.responses import (FileResponse, JSONResponse,  # noqa: E402
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

import agent  # noqa: E402
import auth  # noqa: E402
import case_model  # noqa: E402
import config  # noqa: E402
import dashboard  # noqa: E402
import emailer  # noqa: E402
import followups  # noqa: E402
import inference  # noqa: E402
import reports  # noqa: E402
import store  # noqa: E402
import voice  # noqa: E402

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
VERSION = "2.3.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init_db()
    started = followups.start()
    yield
    if started:
        thread, stop = started
        stop.set()
        thread.join(timeout=3)


app = FastAPI(title="Consult Homeopathic Physicians", docs_url="/api/docs",
              version=VERSION, lifespan=lifespan)
store.init_db()
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; img-src 'self' data:; "
        "media-src 'self' data: blob:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(agent.WorkflowError)
async def workflow_error(_: Request, exc: agent.WorkflowError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(reports.ReportError)
async def report_error(_: Request, exc: reports.ReportError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(voice.VoiceError)
async def voice_error(_: Request, exc: voice.VoiceError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


class StartIn(BaseModel):
    name: str = Field(default="", max_length=120)
    email: str = Field(default="", max_length=160)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if value and not case_model.is_email(value):
            raise ValueError("Enter a valid email address.")
        return value


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be empty.")
        return value


class ChooseIn(BaseModel):
    option: str = Field(min_length=1, max_length=120)

    @field_validator("option")
    @classmethod
    def _option(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Choose a care option.")
        return value


class ApproveIn(BaseModel):
    advice: str = Field(min_length=1, max_length=4000)
    prescription: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)
    doctor: str = Field(default="Dr. Demo", max_length=120)


class FollowUpIn(BaseModel):
    report: str = Field(min_length=1, max_length=2000)


class LoginIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)


def _public_case(case: dict, *, staff: bool = False) -> dict:
    follow = dict(case.get("follow_up") or {})
    token = follow.pop("token", "")
    if staff and token:
        follow["link"] = f"{emailer.public_url()}/follow-up/{token}"
    public_reports = [
        {key: value for key, value in report.items() if key != "path"}
        for report in case.get("reports", [])
    ]
    return {
        **case,
        "reports": public_reports,
        "follow_up": follow,
        "allergy_warnings": case_model.allergy_warnings(case),
        "interaction_warnings": case_model.interaction_warnings(case),
        "audit": store.list_audit(case["case_id"]),
    }


def _require(case_id: str) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@app.get("/healthz")
def healthz() -> dict:
    try:
        db = store.health()
    except Exception as exc:  # surface storage trouble instead of a false "ok"
        return JSONResponse(status_code=503,
                            content={"status": "error", "detail": str(exc)})
    return {
        "status": "ok",
        "service": "consult-homeopathic",
        "version": VERSION,
        "storage": db,
        "llm_key": inference.have_key(),
        "provider": inference.provider(),
        "model": inference.model_name() or None,
        "engine": inference.engine_label(),
        "providers": inference.configured_providers(),
        "mode": "rules (demo)" if config.demo_mode() else "live",
        "email": "smtp" if config.env("SMTP_HOST") else "file (simulated mailbox)",
        "dashboard_auth": auth.enabled(),
        "voice": {
            "enabled": voice.enabled(),
            "provider": voice.provider() or None,
            "stt_model": voice.stt_model() if voice.enabled() else None,
            "tts_model": voice.tts_model() if voice.enabled() else None,
            "tts_voice": voice.tts_voice() if voice.enabled() else None,
        },
        "followups": {**followups.status(),
                      "poll_seconds": config.env("FOLLOWUP_POLL_SECONDS", "60")},
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/doctor")
def doctor(request: Request):
    if auth.enabled() and not auth.current_user(request):
        return RedirectResponse("/login?next=/doctor", status_code=303)
    return FileResponse(STATIC / "doctor.html")


@app.get("/login")
def login_page(request: Request):
    if not auth.enabled() or auth.current_user(request):
        return RedirectResponse("/doctor", status_code=303)
    return FileResponse(STATIC / "login.html")


@app.post("/api/auth/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    if not auth.enabled():
        return {"enabled": False, "authenticated": True, "user": auth.user()}
    if auth.blocked(request):
        raise HTTPException(status_code=429,
                            detail="Too many attempts. Try again in a minute.")
    if not auth.check_password(body.password):
        auth.note_failure(request)
        raise HTTPException(status_code=401, detail="Incorrect password.")
    auth.clear_failures(request)
    secure = emailer.public_url().startswith("https://")
    response.set_cookie(auth.COOKIE, auth.issue(), max_age=auth.SESSION_SECONDS,
                        httponly=True, samesite="lax", secure=secure, path="/")
    return {"enabled": True, "authenticated": True, "user": auth.user()}


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict:
    if not auth.enabled():
        return {"enabled": False, "authenticated": True, "user": auth.user()}
    user = auth.current_user(request)
    return {"enabled": True, "authenticated": bool(user), "user": user}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE, path="/")
    return {"enabled": auth.enabled(), "authenticated": False, "user": ""}


@app.get("/follow-up/{token}")
def followup_page(token: str) -> FileResponse:
    if not store.get_followup_by_token(token):
        raise HTTPException(status_code=404, detail="follow-up link not found")
    return FileResponse(STATIC / "followup.html")


@app.post("/api/intake/start")
def start(body: StartIn) -> dict:
    case = agent.start_case(body.name, body.email)
    return {"case": _public_case(case), "reply": case["transcript"][0]["text"]}


@app.post("/api/intake/{case_id}/message")
def message(case_id: str, body: MessageIn) -> dict:
    case = _require(case_id)
    if case["status"] == case_model.STATUS_EMERGENCY:
        return {"case": _public_case(case), "reply": case["transcript"][-1]["text"],
                "emergency": True, "engine": case.get("engine", "")}
    result = agent.handle_message(case, body.text)
    return {"case": _public_case(result["case"]), "reply": result["reply"],
            "emergency": result["emergency"], "engine": result["engine"]}


@app.post("/api/intake/{case_id}/voice")
async def voice_message(case_id: str, file: UploadFile = File(...)) -> dict:
    """Push-to-talk turn: audio in, transcript + reply + audio out."""
    case = _require(case_id)
    if case["status"] == case_model.STATUS_EMERGENCY:
        return {"case": _public_case(case), "reply": case["transcript"][-1]["text"],
                "transcript": "", "emergency": True,
                "engine": case.get("engine", ""), "audio": ""}
    content = await file.read(voice.max_bytes() + 1)
    if len(content) > voice.max_bytes():
        raise voice.VoiceError("The recording is too large.")
    text = voice.transcribe(content, file.filename or "voice.webm",
                            file.content_type or "audio/webm")
    result = agent.handle_message(case, text)
    audio = ""
    try:
        audio = base64.b64encode(voice.speech(result["reply"])).decode("ascii")
    except voice.VoiceError:
        # The text turn still succeeded; the browser can show the reply.
        audio = ""
    return {"case": _public_case(result["case"]), "reply": result["reply"],
            "transcript": text, "emergency": result["emergency"],
            "engine": result["engine"], "audio": audio,
            "audio_mime": voice.speech_mime()}


async def _read_upload(file: UploadFile) -> bytes:
    limit = reports.MAX_BYTES + 1
    content = await file.read(limit)
    if len(content) > reports.MAX_BYTES:
        raise reports.ReportError("Report is larger than 5 MB.")
    return content


@app.post("/api/intake/{case_id}/report")
@app.post("/api/cases/{case_id}/report")
async def upload_report(case_id: str, file: UploadFile = File(...)) -> dict:
    _require(case_id)
    content = await _read_upload(file)
    case = agent.attach_report(case_id, file.filename or "report",
                               content, file.content_type or "")
    return {"case": _public_case(case),
            "reply": case["transcript"][-1]["text"] if case["transcript"] else ""}


@app.post("/api/cases/{case_id}/choose")
def choose(case_id: str, body: ChooseIn) -> dict:
    _require(case_id)
    case = agent.choose_option(case_id, body.option)
    return {"case": _public_case(case)}


@app.get("/api/cases/{case_id}", dependencies=[Depends(auth.require)])
def get_case(case_id: str) -> dict:
    case = _require(case_id)
    public = _public_case(case, staff=True)
    public["prior_cases"] = store.prior_cases(case, limit=5)
    return {"case": public}


@app.get("/api/cases/{case_id}/reports/{index}/file",
         dependencies=[Depends(auth.require)])
def report_file(case_id: str, index: int):
    case = _require(case_id)
    items = case.get("reports") or []
    if index < 0 or index >= len(items):
        raise HTTPException(status_code=404, detail="document not found")
    report = items[index]
    raw_path = report.get("path") or ""
    try:
        resolved = Path(raw_path).resolve()
        root = config.data_dir().resolve()
        if not resolved.is_file() or not resolved.is_relative_to(root):
            raise ValueError
    except (OSError, ValueError):
        raise HTTPException(status_code=404, detail="document file not found")
    return FileResponse(
        resolved,
        media_type=report.get("content_type") or "application/octet-stream",
        filename=report.get("filename") or "document")


@app.get("/api/doctor/cases", dependencies=[Depends(auth.require)])
def doctor_cases(status: str = "", q: str = "", urgency: str = "",
                 limit: int = 50, offset: int = 0) -> dict:
    cases = store.list_cases(status or None, limit=2000)
    if urgency:
        cases = [case for case in cases if case.get("urgency") == urgency]
    query = q.strip().lower()
    if query:
        cases = [case for case in cases
                 if query in dashboard.case_search_blob(case)]
    total = len(cases)
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    page = cases[offset:offset + limit]
    return {"cases": [_public_case(case, staff=True) for case in page],
            "total": total, "limit": limit, "offset": offset}


@app.get("/api/dashboard", dependencies=[Depends(auth.require)])
def dashboard_stats() -> dict:
    return dashboard.overview()


@app.get("/api/followups", dependencies=[Depends(auth.require)])
def followup_list(state: str = "") -> dict:
    rows = dashboard.followups_view()
    if state:
        rows = [row for row in rows if row["state"] == state]
    return {"follow_ups": rows, "total": len(rows)}


@app.post("/api/cases/{case_id}/approve",
          dependencies=[Depends(auth.require)])
def approve(case_id: str, body: ApproveIn) -> dict:
    _require(case_id)
    case = agent.approve(case_id, advice=body.advice,
                         prescription=body.prescription, notes=body.notes,
                         doctor=body.doctor)
    return {"case": _public_case(case, staff=True)}


@app.post("/api/cases/{case_id}/follow-up",
          dependencies=[Depends(auth.require)])
def follow_up(case_id: str, body: FollowUpIn) -> dict:
    _require(case_id)
    case = agent.follow_up(case_id, body.report)
    return {"case": _public_case(case, staff=True)}


@app.post("/api/cases/{case_id}/follow-up/send",
          dependencies=[Depends(auth.require)])
def send_follow_up_now(case_id: str) -> dict:
    case = _require(case_id)
    if case["status"] != case_model.STATUS_DELIVERED:
        raise agent.WorkflowError("Only delivered cases have a check-in.")
    row = followups.send_now(case_id)
    if not row:
        raise agent.WorkflowError("No follow-up is scheduled for this case.")
    return {"follow_up": row, "case": _public_case(_require(case_id), staff=True)}


def _public_followup(token: str) -> dict:
    row = store.get_followup_by_token(token)
    if not row:
        raise HTTPException(status_code=404, detail="follow-up link not found")
    case = store.get_case(row["case_id"])
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return {
        "case_id": case["case_id"],
        "name": case["patient"].get("name", ""),
        "status": case["status"],
        "summary": case["summary"].get("one_liner", ""),
        "advice": case["doctor"].get("advice", ""),
        "prescription": case["doctor"].get("prescription", ""),
        "follow_up": {"due_at": row["due_at"], "sent_at": row["sent_at"]},
        "reports": [{key: value for key, value in item.items() if key != "path"}
                    for item in case.get("follow_up", {}).get("reports", [])],
    }


@app.get("/api/follow-up/{token}")
def get_followup(token: str) -> dict:
    return {"follow_up": _public_followup(token)}


@app.post("/api/follow-up/{token}")
def post_followup(token: str, body: FollowUpIn) -> dict:
    case = agent.follow_up_by_token(token, body.report)
    if not case:
        raise HTTPException(status_code=404, detail="follow-up link not found")
    return {"follow_up": _public_followup(token)}


def _email_body(raw: str) -> str:
    from email import message_from_string, policy

    try:
        message = message_from_string(raw, policy=policy.default)
        part = message.get_body(preferencelist=("plain",))
        if part is not None:
            return part.get_content().strip() or raw
    except (ValueError, KeyError):
        pass
    return raw


@app.get("/api/mailbox", dependencies=[Depends(auth.require)])
def mailbox() -> dict:
    return {"emails": store.list_emails()}


@app.get("/api/mailbox/{case_id}", dependencies=[Depends(auth.require)])
def mailbox_item(case_id: str, kind: str = "") -> dict:
    _require(case_id)
    rows = [row for row in store.list_emails(500) if row["case_id"] == case_id]
    if kind:
        rows = [row for row in rows if row["subject"].lower().find(kind) >= 0]
    if not rows:
        raise HTTPException(status_code=404, detail="no email for this case")
    row = rows[0]
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="email file is missing")
    content = path.read_text(encoding="utf-8")
    return {"case_id": case_id, "content": content,
            "body": _email_body(content),
            "email": _require(case_id).get("email", {})}


@app.get("/api/emails/{email_id}", dependencies=[Depends(auth.require)])
def email_item(email_id: int) -> dict:
    row = store.get_email(email_id)
    if not row:
        raise HTTPException(status_code=404, detail="email not found")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="email file is missing")
    case = store.get_case(row["case_id"])
    content = path.read_text(encoding="utf-8")
    return {"id": row["id"], "case_id": row["case_id"], "content": content,
            "body": _email_body(content),
            "email": (case or {}).get("email", {})}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(config.env("PORT", "8000")))
