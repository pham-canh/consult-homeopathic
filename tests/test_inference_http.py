"""HTTP-level checks for every supported provider.

The tests use a local mock server, so CI never needs a real API key or network
access to OpenAI, Anthropic, Google, or Vultr.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

import inference

MESSAGES = [
    {"role": "system", "content": "be brief"},
    {"role": "user", "content": "hello"},
]


class MockServer:
    def __init__(self, responder):
        self.calls: list[dict] = []
        self.responder = responder
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 - http.server API
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                body = json.loads(raw or b"{}")
                parsed = urlsplit(self.path)
                call = {
                    "path": parsed.path,
                    "query": parsed.query,
                    "headers": {key.lower(): value
                                for key, value in self.headers.items()},
                    "body": body,
                }
                outer.calls.append(call)
                status, payload = outer.responder(call)
                encoded = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *args):  # keep test output clean
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.thread = threading.Thread(target=self.http.serve_forever,
                                       daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.http.shutdown()
        self.http.server_close()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("INFERENCE_API_KEY", "VULTR_API_KEY", "OPENAI_API_KEY",
                 "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                 "INFERENCE_MODEL", "VULTR_MODEL", "OPENAI_MODEL",
                 "ANTHROPIC_MODEL", "GEMINI_MODEL", "INFERENCE_PROVIDER",
                 "INFERENCE_BASE_URL"):
        monkeypatch.setenv(name, "")


@pytest.fixture
def mock_server():
    servers: list[MockServer] = []

    def make(responder):
        server = MockServer(responder)
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.close()


def _openai_response():
    return 200, {"choices": [{"message": {"content": "ok"}}]}


def test_openai_chat_uses_bearer_auth(monkeypatch, mock_server):
    server = mock_server(lambda call: _openai_response())
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("INFERENCE_BASE_URL", server.url + "/v1")

    assert inference.chat(MESSAGES) == "ok"
    call = server.calls[0]
    assert call["path"] == "/v1/chat/completions"
    assert call["headers"]["authorization"] == "Bearer sk-test"
    assert call["body"]["model"] == "gpt-test"


def test_openai_retries_without_temperature(monkeypatch, mock_server):
    def responder(call):
        if "temperature" in call["body"]:
            return 400, {"error": {
                "message": "Unsupported value: 'temperature' is not supported"}}
        return _openai_response()

    server = mock_server(responder)
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "reasoning-test")
    monkeypatch.setenv("INFERENCE_BASE_URL", server.url + "/v1")

    assert inference.chat(MESSAGES) == "ok"
    assert len(server.calls) == 2
    assert "temperature" not in server.calls[1]["body"]


def test_anthropic_chat_uses_messages_api(monkeypatch, mock_server):
    server = mock_server(
        lambda call: (200, {"content": [{"type": "text", "text": "ok"}]}))
    monkeypatch.setenv("INFERENCE_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    monkeypatch.setenv("INFERENCE_BASE_URL", server.url + "/v1")

    assert inference.chat(MESSAGES) == "ok"
    call = server.calls[0]
    assert call["path"] == "/v1/messages"
    assert call["headers"]["x-api-key"] == "sk-ant-test"
    assert call["headers"]["anthropic-version"] == inference.ANTHROPIC_VERSION
    assert call["body"]["system"] == "be brief"
    assert [m["role"] for m in call["body"]["messages"]] == ["user"]


def test_gemini_chat_uses_api_key_header(monkeypatch, mock_server):
    server = mock_server(lambda call: (
        200, {"candidates": [{"content": {
            "parts": [{"text": "ok"}]}}]}))
    monkeypatch.setenv("INFERENCE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "goog-test")
    monkeypatch.setenv("GEMINI_MODEL", "models/gemini-test")
    monkeypatch.setenv("INFERENCE_BASE_URL", server.url + "/v1beta")

    assert inference.chat(MESSAGES) == "ok"
    call = server.calls[0]
    assert call["path"] == "/v1beta/models/gemini-test:generateContent"
    assert "key=" not in call["query"]
    assert call["headers"]["x-goog-api-key"] == "goog-test"
    assert call["body"]["systemInstruction"]["parts"][0]["text"] == "be brief"


def test_custom_openai_compatible_endpoint(monkeypatch, mock_server):
    server = mock_server(lambda call: _openai_response())
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai-compatible")
    monkeypatch.setenv("INFERENCE_API_KEY", "local-test")
    monkeypatch.setenv("INFERENCE_MODEL", "local-model")
    monkeypatch.setenv("INFERENCE_BASE_URL", server.url + "/v1")

    assert inference.chat(MESSAGES) == "ok"
    call = server.calls[0]
    assert call["path"] == "/v1/chat/completions"
    assert call["headers"]["authorization"] == "Bearer local-test"


def test_provider_http_error_is_reported(monkeypatch, mock_server):
    server = mock_server(lambda call: (401, {"error": "bad key"}))
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "bad")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("INFERENCE_BASE_URL", server.url + "/v1")

    with pytest.raises(inference.InferenceError, match="HTTP 401"):
        inference.chat(MESSAGES)
