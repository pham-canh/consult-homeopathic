"""Server-side speech-to-text and text-to-speech for the intake agent.

The browser sends a short recording and receives a base64 audio reply; the
provider key never reaches the client. Gemini is the default voice provider when
its key is present; OpenAI is supported as an alternative.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
import uuid

from config import env

OPENAI_BASE = "https://api.openai.com/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024


class VoiceError(RuntimeError):
    """A voice request that could not be completed."""


def openai_key() -> str:
    return env("OPENAI_API_KEY") or env("VOICE_API_KEY")


def gemini_key() -> str:
    return env("GEMINI_API_KEY") or env("GOOGLE_API_KEY")


def provider() -> str:
    explicit = env("VOICE_PROVIDER").strip().lower()
    if explicit in {"gemini", "google"}:
        return "gemini" if gemini_key() else ""
    if explicit == "openai":
        return "openai" if openai_key() else ""
    if gemini_key():
        return "gemini"
    if openai_key():
        return "openai"
    return ""


def api_key() -> str:
    prov = provider()
    if prov == "gemini":
        return gemini_key()
    if prov == "openai":
        return openai_key()
    return ""


def enabled() -> bool:
    return bool(provider())


def stt_model() -> str:
    default = "gemini-3.5-transcribe" if provider() == "gemini" else "whisper-1"
    return env("VOICE_STT_MODEL", default)


def tts_model() -> str:
    default = "gemini-3.8-flash-tts" if provider() == "gemini" else "tts-1"
    return env("VOICE_TTS_MODEL", default)


def tts_voice() -> str:
    default = "Kore" if provider() == "gemini" else "alloy"
    return env("VOICE_TTS_VOICE", default)


def speech_mime() -> str:
    return "audio/wav" if provider() == "gemini" else "audio/mpeg"


def language() -> str:
    return env("VOICE_LANGUAGE", "en")


def max_bytes() -> int:
    try:
        return max(1, int(env("VOICE_MAX_BYTES", str(DEFAULT_MAX_BYTES))))
    except ValueError:
        return DEFAULT_MAX_BYTES


def _multipart(fields: dict[str, str],
               files: list[tuple[str, str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "----consult" + uuid.uuid4().hex
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8"))
    for name, filename, content_type, content in files:
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\n'
            f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n")
        chunks.append(header.encode("utf-8"))
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _post(url: str, body: bytes, content_type: str,
          timeout: int = 90) -> bytes:
    key = api_key()
    if not key:
        raise VoiceError("Voice is not configured on the server.")
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": content_type},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise VoiceError(f"OpenAI audio HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise VoiceError(f"Could not reach the voice service: {exc.reason}") from exc
    except TimeoutError as exc:
        raise VoiceError("The voice service timed out.") from exc


def _gemini_generate(model: str, payload: dict) -> dict:
    key = gemini_key()
    if not key:
        raise VoiceError("Gemini voice is not configured on the server.")
    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    body = json.dumps(payload).encode("utf-8")
    last_error = ""
    for attempt in range(2):
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json",
                     "x-goog-api-key": key},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            last_error = f"Gemini audio HTTP {exc.code}: {detail}"
            if exc.code in {429, 503} and attempt == 0:
                time.sleep(1)
                continue
            raise VoiceError(last_error) from exc
        except urllib.error.URLError as exc:
            raise VoiceError(
                f"Could not reach Gemini: {exc.reason}") from exc
        except (TimeoutError, json.JSONDecodeError) as exc:
            raise VoiceError(f"Bad response from Gemini: {exc}") from exc
    raise VoiceError(last_error or "Gemini voice request failed.")


def _gemini_parts(data: dict) -> list[dict]:
    candidates = data.get("candidates") or []
    if not candidates:
        error = (data.get("error") or {}).get("message")
        raise VoiceError(error or "Gemini returned no candidate.")
    content = candidates[0].get("content") or {}
    return content.get("parts") or []


def transcribe(content: bytes, filename: str = "voice.webm",
               content_type: str = "audio/webm") -> str:
    """Return the spoken text from a short audio recording."""
    if not content:
        raise VoiceError("The recording is empty.")
    if len(content) > max_bytes():
        raise VoiceError("The recording is too large.")
    prov = provider()
    if not prov:
        raise VoiceError(
            "Voice is not configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")
    if prov == "gemini":
        mime_type = (content_type or "audio/webm").split(";", 1)[0].strip()
        payload = {
            "contents": [{"parts": [
                {"text": "Transcribe this audio exactly. Return only the "
                         "transcript in English."},
                {"inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(content).decode("ascii"),
                }},
            ]}],
        }
        data = _gemini_generate(stt_model(), payload)
        for part in _gemini_parts(data):
            text = ((part.get("audioTranscription") or {}).get("text")
                    or part.get("text") or "").strip()
            if text:
                return text[:2000]
        raise VoiceError("No speech was recognized. Please try again.")

    fields = {"model": stt_model(), "response_format": "json"}
    if language():
        fields["language"] = language()
    body, multipart_type = _multipart(
        fields, [("file", filename, content_type, content)])
    raw = _post(OPENAI_BASE + "/audio/transcriptions", body, multipart_type,
                timeout=90)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VoiceError(
            "The transcription service returned an invalid response.") from exc
    text = (data.get("text") or "").strip()
    if not text:
        raise VoiceError("No speech was recognized. Please try again.")
    return text[:2000]


def speech(text: str) -> bytes:
    """Return a recording of the reply."""
    text = (text or "").strip()
    if not text:
        raise VoiceError("There is no text to speak.")
    prov = provider()
    if not prov:
        raise VoiceError(
            "Voice is not configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")
    if prov == "gemini":
        payload = {
            "contents": [{"parts": [
                {"text": "Read this message aloud in a warm, clear voice: "
                         + text[:4000]},
            ]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": tts_voice()},
                    },
                },
            },
        }
        data = _gemini_generate(tts_model(), payload)
        for part in _gemini_parts(data):
            inline = part.get("inlineData") or part.get("inline_data") or {}
            encoded = inline.get("data") or ""
            if encoded:
                try:
                    audio = base64.b64decode(encoded)
                except ValueError as exc:
                    raise VoiceError("Gemini returned invalid audio.") from exc
                if len(audio) < 100:
                    raise VoiceError("The speech service returned empty audio.")
                return audio
        raise VoiceError("Gemini returned no audio.")

    payload = {
        "model": tts_model(),
        "voice": tts_voice(),
        "input": text[:4000],
        "response_format": "mp3",
    }
    body = json.dumps(payload).encode("utf-8")
    audio = _post(OPENAI_BASE + "/audio/speech", body, "application/json",
                  timeout=90)
    if len(audio) < 100:
        raise VoiceError("The speech service returned an empty recording.")
    return audio
