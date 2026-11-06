#!/usr/bin/env python3
"""Consult Homeopathic Physicians — FastAPI app.

Two user flows in one public web app:
  /         patient intake chat
  /doctor   doctor dashboard (review, edit, approve, email)

Runs directly on a Vultr VM. SQLite stores cases, the audit trail, and the
simulated mailbox; every LLM call goes through Vultr Serverless Inference.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import agent  # noqa: E402
import case_model  # noqa: E402
import config  # noqa: E402
import inference  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="Consult Homeopathic Physicians", docs_url="/api/docs")
store.init_db()
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class StartIn(BaseModel):
    name: str = ""
    email: str = ""


class MessageIn(BaseModel):
    text: str


class ChooseIn(BaseModel):
    option: str


class ApproveIn(BaseModel):
    advice: str
    prescription: str = ""
    notes: str = ""
    doctor: str = "Dr. Demo"


class FollowUpIn(BaseModel):
    report: str


def _public_case(case: dict) -> dict:
    return {
        **case,
        "allergy_warnings": case_model.allergy_warnings(case),
        "audit": store.list_audit(case["case_id"]),
    }


def _require(case_id: str) -> dict:
    case = store.get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return case


@app.get("/healthz")
def healthz() -> dict:
    return {
        "status": "ok",
        "service": "consult-homeopathic",
        "storage": str(config.db_path()),
        "llm_key": inference.have_key(),
        "provider": inference.provider(),
        "model": inference.model_name() or None,
        "engine": inference.engine_label(),
        "mode": "rules (demo)" if config.demo_mode() else "live",
        "email": "smtp" if config.env("SMTP_HOST") else "file (simulated mailbox)",
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/doctor")
def doctor() -> FileResponse:
    return FileResponse(STATIC / "doctor.html")


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


@app.post("/api/cases/{case_id}/choose")
def choose(case_id: str, body: ChooseIn) -> dict:
    case = agent.choose_option(case_id, body.option)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return {"case": _public_case(case)}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    return {"case": _public_case(_require(case_id))}


@app.get("/api/doctor/cases")
def doctor_cases(status: str = "") -> dict:
    cases = store.list_cases(status or None)
    return {"cases": [_public_case(c) for c in cases]}


@app.post("/api/cases/{case_id}/approve")
def approve(case_id: str, body: ApproveIn) -> dict:
    _require(case_id)
    case = agent.approve(case_id, advice=body.advice,
                         prescription=body.prescription, notes=body.notes,
                         doctor=body.doctor)
    if not case:
        raise HTTPException(status_code=404, detail="case not found")
    return {"case": _public_case(case)}


@app.post("/api/cases/{case_id}/follow-up")
def follow_up(case_id: str, body: FollowUpIn) -> dict:
    _require(case_id)
    case = agent.follow_up(case_id, body.report)
    return {"case": _public_case(case)}


@app.get("/api/mailbox")
def mailbox() -> dict:
    return {"emails": store.list_emails()}


@app.get("/api/mailbox/{case_id}")
def mailbox_item(case_id: str) -> dict:
    case = _require(case_id)
    path = config.mailbox_dir() / f"{case_id}.eml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no email for this case")
    return {"case_id": case_id, "content": path.read_text(encoding="utf-8"),
            "email": case.get("email", {})}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(config.env("PORT", "8000")))
