import pytest

import inference

MESSAGES = [
    {"role": "system", "content": "be brief"},
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "hi"},
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("INFERENCE_API_KEY", "VULTR_API_KEY", "OPENAI_API_KEY",
                 "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
                 "INFERENCE_MODEL", "VULTR_MODEL", "OPENAI_MODEL",
                 "ANTHROPIC_MODEL", "GEMINI_MODEL", "INFERENCE_PROVIDER",
                 "INFERENCE_BASE_URL"):
        monkeypatch.setenv(name, "")


def test_no_model_is_bundled_and_no_key_is_required_up_front():
    assert inference.provider() == "vultr"
    assert inference.have_key() is False
    assert inference.model_name() == ""
    assert inference.engine_label() == "vultr / (no model set)"


def test_openai_is_selected_by_its_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    assert inference.provider() == "openai"
    assert inference.base_url() == "https://api.openai.com/v1"
    assert inference.model_name() == "gpt-test"
    assert inference.engine_label() == "openai / gpt-test"


def test_claude_alias_and_provider_specific_model(monkeypatch):
    monkeypatch.setenv("INFERENCE_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    assert inference.provider() == "anthropic"
    assert inference.model_name() == "claude-test"
    assert inference.base_url() == "https://api.anthropic.com/v1"


def test_gemini_falls_back_to_google_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-test")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    assert inference.provider() == "gemini"
    assert inference.have_key() is True
    assert "generativelanguage" in inference.base_url()


def test_generic_model_env_works_for_any_provider(monkeypatch):
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("INFERENCE_MODEL", "shared-model")
    assert inference.model_name() == "shared-model"


def test_provider_specific_model_beats_the_generic_one(monkeypatch):
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "specific")
    monkeypatch.setenv("INFERENCE_MODEL", "generic")
    assert inference.model_name() == "specific"


def test_openai_compatible_requires_a_base_url(monkeypatch):
    monkeypatch.setenv("INFERENCE_PROVIDER", "openai-compatible")
    monkeypatch.setenv("INFERENCE_API_KEY", "k")
    monkeypatch.setenv("INFERENCE_MODEL", "m")
    with pytest.raises(inference.InferenceError):
        inference.base_url()
    monkeypatch.setenv("INFERENCE_BASE_URL", "http://localhost:11434/v1/")
    assert inference.base_url() == "http://localhost:11434/v1"


def test_configured_providers_reports_only_filled_slots(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    rows = inference.configured_providers()
    assert {"provider": "openai", "key": True, "model": "gpt-test"} in rows
    assert all(row["provider"] != "anthropic" for row in rows)


def test_custom_provider_needs_a_base_url(monkeypatch):
    monkeypatch.setenv("INFERENCE_API_KEY", "k")
    monkeypatch.setenv("INFERENCE_MODEL", "m")
    rows = inference.configured_providers()
    assert [row["provider"] for row in rows] == ["vultr"]
    monkeypatch.setenv("INFERENCE_BASE_URL", "https://api.vultrinference.com/v1")
    rows = inference.configured_providers()
    assert [row["provider"] for row in rows] == ["vultr"]
    monkeypatch.setenv("INFERENCE_BASE_URL", "http://localhost:11434/v1")
    rows = inference.configured_providers()
    assert [row["provider"] for row in rows] == ["vultr", "openai-compatible"]


def test_payload_shapes_for_each_api():
    openai = inference._openai_payload(MESSAGES, "m", 0.1)
    assert openai["messages"][0]["role"] == "system"

    anthropic = inference._anthropic_payload(MESSAGES, "m", 0.1)
    assert anthropic["system"] == "be brief"
    assert [m["role"] for m in anthropic["messages"]] == ["user", "assistant"]

    gemini = inference._gemini_payload(MESSAGES, 0.1)
    assert gemini["systemInstruction"]["parts"][0]["text"] == "be brief"
    assert [m["role"] for m in gemini["contents"]] == ["user", "model"]
