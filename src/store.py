"""SQLite persistence: cases, audit trail, and the simulated mailbox."""
from __future__ import annotations

import json
import sqlite3
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
            "SELECT case_id, at, to_addr, subject, mode, path FROM emails "
            "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(row) for row in rows]


def reset_db() -> None:
    """Test helper: delete the database file so the next call starts clean."""
    path = Path(db_path())
    if path.exists():
        path.unlink()
