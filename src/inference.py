"""Vultr Serverless Inference client (OpenAI-compatible chat completions).

Every model call in the submitted demo goes through
https://api.vultrinference.com/v1. Configuration comes from the environment:

  INFERENCE_PROVIDER   vultr (default) | openai
  INFERENCE_BASE_URL   default https://api.vultrinference.com/v1
  INFERENCE_MODEL      required; no model id is bundled with the repo
  INFERENCE_API_KEY    required for calls

Failures raise InferenceError. Nothing is mocked: callers that want an offline
path use the deterministic rule engine explicitly and label the result.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from config import env

DEFAULT_BASE_URL = "https://api.vultrinference.com/v1"


class InferenceError(RuntimeError):
    pass


def provider() -> str:
    return env("INFERENCE_PROVIDER", "vultr").lower() or "vultr"


def base_url() -> str:
    return env("INFERENCE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def model_name() -> str:
    return env("INFERENCE_MODEL")


def have_key() -> bool:
    return bool(env("INFERENCE_API_KEY"))


def engine_label() -> str:
    model = model_name() or "(no model)"
    return f"{provider()} / {model}"


def chat(messages: list[dict], *, temperature: float = 0.2,
         timeout: int = 90) -> str:
    if not have_key():
        raise InferenceError("INFERENCE_API_KEY is not set")
    model = model_name()
    if not model:
        raise InferenceError("INFERENCE_MODEL is not set")
    payload = {"model": model, "messages": messages, "temperature": temperature}
    req = urllib.request.Request(
        base_url() + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {env('INFERENCE_API_KEY')}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        raise InferenceError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise InferenceError(f"could not reach {base_url()}: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise InferenceError(f"bad inference response: {exc}") from exc
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise InferenceError(f"unexpected response: {json.dumps(data)[:300]}") from exc


def _extract_json(raw: str) -> dict:
    """Parse a JSON object from a model reply, tolerating fences or leading prose."""
    text = raw.strip()
    if "```" in text:
        for chunk in text.split("```"):
            body = chunk.split("\n", 1)
            if len(body) == 2:
                text = body[1].strip()
                break
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise InferenceError(f"model did not return JSON: {raw[:200]}")
    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise InferenceError(f"invalid JSON from model: {exc}") from exc
    if not isinstance(parsed, dict):
        raise InferenceError("model returned JSON that is not an object")
    return parsed


def ask_json(system: str, user: str) -> dict:
    raw = chat([{"role": "system", "content": system},
                {"role": "user", "content": user}])
    return _extract_json(raw)
