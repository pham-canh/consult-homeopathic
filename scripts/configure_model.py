#!/usr/bin/env python3
"""Configure the inference provider without editing source code.

Usage:
    python3 scripts/configure_model.py                 # interactive prompts
    python3 scripts/configure_model.py --provider claude --model claude-sonnet-4-5
    python3 scripts/configure_model.py --provider openai-compatible \
        --model my-model --base-url http://localhost:11434/v1

The API key is read with a hidden prompt by default. It is written only to the
gitignored `.env` file (mode 600) and is never printed or committed.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

PROVIDERS = {
    "vultr": ("VULTR_API_KEY", "VULTR_MODEL"),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL"),
    "openai-compatible": ("INFERENCE_API_KEY", "INFERENCE_MODEL"),
}
ALIASES = {
    "chatgpt": "openai",
    "gpt": "openai",
    "claude": "anthropic",
    "google": "gemini",
    "custom": "openai-compatible",
    "compatible": "openai-compatible",
    "openai_compatible": "openai-compatible",
    "openrouter": "openai-compatible",
    "ollama": "openai-compatible",
    "vllm": "openai-compatible",
}
EXAMPLES = {
    "vultr": "e.g. deepseek-v4.1-flash-1017",
    "openai": "e.g. gpt-4o-mini or a current ChatGPT model id",
    "anthropic": "e.g. claude-sonnet-4-5",
    "gemini": "e.g. gemini-2.5-flash",
    "openai-compatible": "the model id your endpoint exposes",
}


def normalize_provider(value: str) -> str:
    name = (value or "").strip().lower()
    name = ALIASES.get(name, name)
    return name if name in PROVIDERS else ""


def update_env(lines: list[str], values: dict[str, str]) -> list[str]:
    """Replace existing keys in place, then append any missing ones."""
    remaining = dict(values)
    out: list[str] = []
    for raw in lines:
        stripped = raw.lstrip()
        body = stripped[7:] if stripped.startswith("export ") else stripped
        if "=" in body and not stripped.startswith("#"):
            name = body.split("=", 1)[0].strip()
            if name in remaining:
                value = remaining.pop(name)
                out.append(f"{name}={value}")
                continue
        out.append(raw)
    if remaining:
        if out and out[-1].strip():
            out.append("")
        out.append("# Set by scripts/configure_model.py")
        out.extend(f"{name}={value}" for name, value in remaining.items())
    return out


def write_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    path.write_text("\n".join(update_env(lines, values)) + "\n",
                    encoding="utf-8")
    path.chmod(0o600)


def prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Configure a provider, model, and API key in .env")
    parser.add_argument("--provider", default="",
                        help="vultr, openai, anthropic, gemini, openai-compatible")
    parser.add_argument("--model", default="", help="model id for that provider")
    parser.add_argument("--key", default="", help="API key (omit for hidden prompt)")
    parser.add_argument("--base-url", default="",
                        help="custom base URL for an OpenAI-compatible endpoint")
    parser.add_argument("--env-file", default=str(ROOT / ".env"))
    parser.add_argument("--no-input", action="store_true",
                        help="fail instead of prompting for missing values")
    parser.add_argument("--test", action="store_true",
                        help="make one tiny chat call before saving")
    args = parser.parse_args()

    provider = normalize_provider(args.provider)
    if not provider:
        if args.no_input:
            parser.error("--provider is required with --no-input")
        print("Providers: vultr, openai (ChatGPT), anthropic (Claude), "
              "gemini (Google), openai-compatible")
        provider = normalize_provider(prompt("Provider", "vultr"))
    if not provider:
        parser.error("unknown provider")

    key_env, model_env = PROVIDERS[provider]
    model = args.model.strip()
    if not model:
        if args.no_input:
            parser.error("--model is required with --no-input")
        model = prompt(f"Model id ({EXAMPLES[provider]})")
    if not model:
        parser.error("a model id is required; this repo bundles none")

    base_url = args.base_url.strip().rstrip("/")
    if provider == "openai-compatible" and not base_url:
        if args.no_input:
            parser.error("--base-url is required for openai-compatible")
        base_url = prompt("Base URL", "http://localhost:11434/v1").rstrip("/")
    if provider == "openai-compatible" and not base_url.startswith(
            ("http://", "https://")):
        parser.error("base URL must start with http:// or https://")

    key = args.key.strip()
    if not key:
        if args.no_input:
            parser.error("--key is required with --no-input")
        key = getpass.getpass(f"{key_env} (input hidden): ").strip()
    if not key:
        parser.error("an API key is required")

    values = {
        "INFERENCE_PROVIDER": provider,
        key_env: key,
        model_env: model,
    }
    if provider == "openai-compatible":
        values["INFERENCE_BASE_URL"] = base_url
    else:
        # Clear a previous custom endpoint so the standard default is used.
        values["INFERENCE_BASE_URL"] = base_url

    env_path = Path(args.env_file)
    if args.test:
        os.environ.update(values)
        sys.path.insert(0, str(SRC))
        try:
            import inference
            reply = inference.chat([
                {"role": "user", "content": "Reply with the single word OK."}
            ], temperature=0, timeout=30)
        except Exception as exc:
            print(f"Connection test failed: {type(exc).__name__}: {exc}")
            print(f"Not saved; {env_path} is unchanged.")
            return 1
        print(f"Connection test: {reply.strip()[:80] or '(empty reply)'}")

    write_env(env_path, values)
    print(f"Saved {provider} / {model} to {env_path} (key not printed).")
    print("Restart the app, then check /healthz for the active provider.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
