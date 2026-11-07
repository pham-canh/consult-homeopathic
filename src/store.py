"""SQLite persistence: cases, audit trail, and the simulated mailbox."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id     TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    data        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id  TEXT NOT NULL,
    at       TEXT NOT NULL,
    actor    TEXT NOT NULL,
    action   TEXT NOT NULL,
    detail   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS emails (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id  TEXT NOT NULL,
    at       TEXT NOT NULL,
    to_addr  TEXT NOT NULL,
    subject  TEXT NOT NULL,
    mode     TEXT NOT NULL,
    path     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS followups (
    case_id   TEXT PRIMARY KEY,
    token     TEXT UNIQUE NOT NULL,
    due_at    TEXT NOT NULL,
    sent_at   TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def save_case(case: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO cases (case_id, status, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(case_id) DO UPDATE SET status=excluded.status, "
            "updated_at=excluded.updated_at, data=excluded.data",
            (case["case_id"], case["status"], case["created_at"],
             case["updated_at"], json.dumps(case, ensure_ascii=False)),
        )


def get_case(case_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT data FROM cases WHERE case_id = ?",
                           (case_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_cases(status: str | None = None, limit: int = 100) -> list[dict]:
    query = "SELECT data FROM cases"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY created_at DESC LIMIT ?"
    params += (int(limit),)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [json.loads(row["data"]) for row in rows]


def add_audit(case_id: str, actor: str, action: str, detail: str, at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit (case_id, at, actor, action, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            (case_id, at, actor, action, detail[:1000]),
        )


def list_audit(case_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT at, actor, action, detail FROM audit WHERE case_id = ? "
            "ORDER BY id ASC", (case_id,)).fetchall()
    return [dict(row) for row in rows]


def save_email(case_id: str, at: str, to_addr: str, subject: str,
               mode: str, path: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO emails (case_id, at, to_addr, subject, mode, path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (case_id, at, to_addr, subject, mode, path),
        )


def list_emails(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, case_id, at, to_addr, subject, mode, path FROM emails "
            "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(row) for row in rows]


def get_email(email_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, case_id, at, to_addr, subject, mode, path FROM emails "
            "WHERE id = ?", (int(email_id),)).fetchone()
    return dict(row) if row else None


def schedule_followup(case_id: str, token: str, due_at: str, created_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO followups (case_id, token, due_at, sent_at, created_at) "
            "VALUES (?, ?, ?, '', ?) "
            "ON CONFLICT(case_id) DO UPDATE SET token=excluded.token, "
            "due_at=excluded.due_at, sent_at='' ",
            (case_id, token, due_at, created_at),
        )


def due_followups(now: str, limit: int = 25) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT case_id, token, due_at FROM followups "
            "WHERE sent_at = '' AND due_at <= ? "
            "ORDER BY due_at ASC LIMIT ?", (now, int(limit))).fetchall()
    return [dict(row) for row in rows]


def claim_followup(case_id: str, sent_at: str) -> bool:
    """Atomically mark a check-in as sent so two workers cannot double-send."""
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE followups SET sent_at = ? WHERE case_id = ? AND sent_at = ''",
            (sent_at, case_id),
        )
        return cur.rowcount > 0


def clear_followup_sent(case_id: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE followups SET sent_at = '' WHERE case_id = ?",
                     (case_id,))


def get_followup_by_token(token: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT case_id, token, due_at, sent_at FROM followups WHERE token = ?",
            (token,)).fetchone()
    return dict(row) if row else None


def get_followup(case_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT case_id, token, due_at, sent_at FROM followups WHERE case_id = ?",
            (case_id,)).fetchone()
    return dict(row) if row else None


def list_followups(limit: int = 500) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT case_id, token, due_at, sent_at, created_at FROM followups "
            "ORDER BY due_at ASC LIMIT ?", (int(limit),)).fetchall()
    return [dict(row) for row in rows]


def health() -> dict:
    path = Path(db_path())
    with _connect() as conn:
        conn.execute("SELECT 1").fetchone()
        cases = conn.execute("SELECT COUNT(*) AS n FROM cases").fetchone()["n"]
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM cases WHERE status = 'pending_review'"
        ).fetchone()["n"]
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        due = conn.execute(
            "SELECT COUNT(*) AS n FROM followups WHERE sent_at = '' "
            "AND due_at <= ?", (now,)).fetchone()["n"]
    return {"database": str(path), "cases": cases, "pending_review": pending,
            "followups_due": due}


def reset_db() -> None:
    """Test helper: delete the database file so the next call starts clean."""
    path = Path(db_path())
    if path.exists():
        path.unlink()
