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

import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

import agent  # noqa: E402
import case_model  # noqa: E402
import config  # noqa: E402
import emailer  # noqa: E402
import followups  # noqa: E402
import inference  # noqa: E402
import reports  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
VERSION = "2.1.0"


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
        "script-src 'self'; img-src 'self' data:; connect-src 'self'; "
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
        "followups": {**followups.status(),
                      "poll_seconds": config.env("FOLLOWUP_POLL_SECONDS", "60")},
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/doctor")
def doctor() -> FileResponse:
    return FileResponse(STATIC / "doctor.html")


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
    return {"case": _public_case(case)}


@app.post("/api/cases/{case_id}/choose")
def choose(case_id: str, body: ChooseIn) -> dict:
    _require(case_id)
    case = agent.choose_option(case_id, body.option)
    return {"case": _public_case(case)}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return {"case": _public_case(_require(case_id), staff=True)}


@app.get("/api/doctor/cases")
def doctor_cases(status: str = "") -> dict:
    cases = store.list_cases(status or None)
    return {"cases": [_public_case(c, staff=True) for c in cases]}


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, body: ApproveIn) -> dict:
    _require(case_id)
    case = agent.approve(case_id, advice=body.advice,
                         prescription=body.prescription, notes=body.notes,
                         doctor=body.doctor)
    return {"case": _public_case(case, staff=True)}


@app.post("/api/cases/{case_id}/follow-up")
def follow_up(case_id: str, body: FollowUpIn) -> dict:
    _require(case_id)
    case = agent.follow_up(case_id, body.report)
    return {"case": _public_case(case, staff=True)}


@app.post("/api/cases/{case_id}/follow-up/send")
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


@app.get("/api/mailbox")
def mailbox() -> dict:
    return {"emails": store.list_emails()}


@app.get("/api/mailbox/{case_id}")
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
    return {"case_id": case_id, "content": path.read_text(encoding="utf-8"),
            "email": _require(case_id).get("email", {})}


@app.get("/api/emails/{email_id}")
def email_item(email_id: int) -> dict:
    row = store.get_email(email_id)
    if not row:
        raise HTTPException(status_code=404, detail="email not found")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="email file is missing")
    case = store.get_case(row["case_id"])
    return {"id": row["id"], "case_id": row["case_id"],
            "content": path.read_text(encoding="utf-8"),
            "email": (case or {}).get("email", {})}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(config.env("PORT", "8000")))
