"""Configuration, loaded from the environment and an optional local .env file."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Load ROOT/.env once without overriding real environment variables."""
    path = ROOT / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name and name not in os.environ:
            os.environ[name] = value


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def data_dir() -> Path:
    path = Path(env("CONSULT_DATA_DIR", str(ROOT / "out")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return Path(env("CONSULT_DB", str(data_dir() / "consult.db")))


def mailbox_dir() -> Path:
    path = Path(env("CONSULT_MAILBOX", str(data_dir() / "emails")))
    path.mkdir(parents=True, exist_ok=True)
    return path


def demo_mode() -> bool:
    """When true, the LLM layer is replaced by the deterministic rule engine.

    Tests and offline demos use this. It is reported in every response and in
    the audit trail, so a rule-based reply is never presented as a model reply.
    """
    return env("CONSULT_FAKE_LLM").lower() in {"1", "true", "yes", "on"}
