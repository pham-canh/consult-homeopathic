"""Provider-agnostic LLM client.

No model id is hard-coded. Fill in whichever provider you have and set its key
and model in `.env`; the app picks it up. An explicit `INFERENCE_PROVIDER` wins,
otherwise the first provider with a key in the order below is used.

  provider            key env                         model env
  vultr               VULTR_API_KEY / INFERENCE_API_KEY  VULTR_MODEL / INFERENCE_MODEL
  openai (ChatGPT)    OPENAI_API_KEY                 OPENAI_MODEL / INFERENCE_MODEL
  anthropic (Claude)  ANTHROPIC_API_KEY              ANTHROPIC_MODEL / INFERENCE_MODEL
  gemini (Google)     GEMINI_API_KEY / GOOGLE_API_KEY GEMINI_MODEL / INFERENCE_MODEL
  openai-compatible   INFERENCE_API_KEY              INFERENCE_MODEL (+ INFERENCE_BASE_URL)

The submitted Vultr demo uses `vultr`, but the same code runs locally on any of
the providers above. A missing key is reported, never mocked; callers that want
an offline path use the deterministic rule engine explicitly.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from config import env

PROVIDER_ORDER = ["vultr", "openai", "anthropic", "gemini", "openai-compatible"]

DEFAULT_BASE = {
    "vultr": "https://api.vultrinference.com/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "openai-compatible": "",
}

KEY_ENVS = {
    "vultr": ["VULTR_API_KEY", "INFERENCE_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "openai-compatible": ["INFERENCE_API_KEY"],
}

MODEL_ENVS = {
    "vultr": ["VULTR_MODEL", "INFERENCE_MODEL"],
    "openai": ["OPENAI_MODEL", "INFERENCE_MODEL"],
    "anthropic": ["ANTHROPIC_MODEL", "INFERENCE_MODEL"],
    "gemini": ["GEMINI_MODEL", "INFERENCE_MODEL"],
    "openai-compatible": ["INFERENCE_MODEL"],
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

ANTHROPIC_VERSION = "2023-06-01"


class InferenceError(RuntimeError):
    pass


def _first(names: list[str]) -> str:
    for name in names:
        value = env(name)
        if value:
            return value
    return ""


def normalize_provider(name: str) -> str:
    name = (name or "").strip().lower()
    name = ALIASES.get(name, name)
    return name if name in PROVIDER_ORDER else ""


def known_bases() -> set[str]:
    return {url.rstrip("/") for url in DEFAULT_BASE.values() if url}


def custom_base() -> str:
    value = env("INFERENCE_BASE_URL").rstrip("/")
    return value if value and value not in known_bases() else ""


def provider() -> str:
    explicit = normalize_provider(env("INFERENCE_PROVIDER"))
    if explicit:
        return explicit
    if _first(["VULTR_API_KEY"]):
        return "vultr"
    for name in ("openai", "anthropic", "gemini"):
        if _first(KEY_ENVS[name]):
            return name
    if _first(["INFERENCE_API_KEY"]):
        # A generic key with a custom base URL means an OpenAI-compatible
        # endpoint; without a custom URL it is treated as the Vultr key.
        return "openai-compatible" if custom_base() else "vultr"
    return "vultr"


def key_name() -> str:
    return KEY_ENVS[provider()][0]


def _key() -> str:
    prov = provider()
    value = _first(KEY_ENVS[prov])
    if not value:
        slots = " or ".join(KEY_ENVS[prov])
        raise InferenceError(
            f"No key for provider '{prov}'. Set {slots} in .env.\n"
            "Supported providers: vultr, openai (ChatGPT), anthropic (Claude), "
            "gemini (Google), openai-compatible."
        )
    return value


def have_key() -> bool:
    return bool(_first(KEY_ENVS[provider()]))


def model_name() -> str:
    """The model supplied in .env for the active provider. Empty means unset."""
    return _first(MODEL_ENVS[provider()])


def base_url() -> str:
    prov = provider()
    if prov == "openai-compatible":
        custom = env("INFERENCE_BASE_URL")
        if not custom:
            raise InferenceError(
                "provider 'openai-compatible' needs INFERENCE_BASE_URL "
                "(for example https://host/v1)."
            )
        return custom.rstrip("/")
    return (env("INFERENCE_BASE_URL") or DEFAULT_BASE[prov]).rstrip("/")


def engine_label() -> str:
    return f"{provider()} / {model_name() or '(no model set)'}"


def configured_providers() -> list[dict]:
    """Providers that actually have a usable key (and a base URL if custom)."""
    out = []
    for name in PROVIDER_ORDER:
        if name == "vultr":
            has_key = bool(_first(["VULTR_API_KEY"])) or (
                bool(_first(["INFERENCE_API_KEY"])) and not custom_base())
        elif name == "openai-compatible":
            has_key = bool(_first(["INFERENCE_API_KEY"])) and bool(custom_base())
        else:
            has_key = bool(_first(KEY_ENVS[name]))
        if not has_key:
            continue
        out.append({"provider": name, "key": True,
                    "model": _first(MODEL_ENVS[name])})
    return out


def _require_model() -> str:
    model = model_name()
    if not model:
        raise InferenceError(
            f"No model set for provider '{provider()}'. Add "
            f"{MODEL_ENVS[provider()][0]} (or INFERENCE_MODEL) to .env. "
            "No model id is bundled with this repo."
        )
    return model


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n".join(m.get("content", "") for m in messages
                       if m.get("role") == "system")
    convo = [m for m in messages if m.get("role") != "system"]
    return system, convo


def _openai_payload(messages: list[dict], model: str,
                    temperature: float) -> dict:
    return {"model": model, "messages": messages, "temperature": temperature}


def _anthropic_payload(messages: list[dict], model: str,
                       temperature: float) -> dict:
    system, convo = _split_system(messages)
    return {"model": model, "max_tokens": 4096, "temperature": temperature,
            "system": system, "messages": convo}


def _gemini_payload(messages: list[dict], temperature: float) -> dict:
    system, convo = _split_system(messages)
    contents = [{"role": "model" if m.get("role") == "assistant" else "user",
                 "parts": [{"text": m.get("content", "")}]} for m in convo]
    payload: dict = {"contents": contents,
                     "generationConfig": {"temperature": temperature}}
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    return payload


def _request(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:400]
        raise InferenceError(f"HTTP {exc.code} ({provider()}): {body}") from exc
    except urllib.error.URLError as exc:
        raise InferenceError(
            f"Could not reach {url}: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise InferenceError(f"Bad response from {provider()}: {exc}") from exc


def chat(messages: list[dict], *, temperature: float = 0.2,
         timeout: int = 90) -> str:
    prov = provider()
    model = _require_model()
    api_key = _key()
    if prov in {"vultr", "openai", "openai-compatible"}:
        payload = _openai_payload(messages, model, temperature)
        try:
            data = _request(base_url() + "/chat/completions", payload,
                            {"Authorization": f"Bearer {api_key}"}, timeout)
        except InferenceError as exc:
            # Newer OpenAI reasoning models reject `temperature`; retry once
            # without it so a valid key/model is not reported as broken.
            if "temperature" not in str(exc).lower():
                raise
            payload.pop("temperature", None)
            data = _request(base_url() + "/chat/completions", payload,
                            {"Authorization": f"Bearer {api_key}"}, timeout)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceError(
                f"Unexpected response: {json.dumps(data)[:300]}") from exc

    if prov == "anthropic":
        data = _request(
            base_url() + "/messages",
            _anthropic_payload(messages, model, temperature),
            {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION},
            timeout)
        try:
            return "".join(block.get("text", "") for block in data["content"]
                           if block.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise InferenceError(
                f"Unexpected response: {json.dumps(data)[:300]}") from exc

    if prov == "gemini":
        model = model.removeprefix("models/")
        data = _request(
            f"{base_url()}/models/{model}:generateContent",
            _gemini_payload(messages, temperature),
            {"x-goog-api-key": api_key}, timeout)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceError(
                f"Unexpected response: {json.dumps(data)[:300]}") from exc

    raise InferenceError(f"Unsupported provider: {prov}")


def _extract_json(raw: str) -> dict:
    """Parse a JSON object from a model reply, tolerating fences or leading prose."""
    text = raw.strip()
    if "```" in text:
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if fenced:
            text = fenced.group(1).strip()
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
