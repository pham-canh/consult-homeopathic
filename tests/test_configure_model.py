import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "configure_model", ROOT / "scripts" / "configure_model.py")
configure_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure_model)


def test_provider_aliases_are_accepted():
    assert configure_model.normalize_provider("claude") == "anthropic"
    assert configure_model.normalize_provider("ChatGPT") == "openai"
    assert configure_model.normalize_provider("openrouter") == "openai-compatible"
    assert configure_model.normalize_provider("nope") == ""


def test_update_env_replaces_in_place_and_appends_missing():
    lines = [
        "# team config",
        "INFERENCE_PROVIDER=vultr",
        "VULTR_API_KEY=old",
        "OTHER=keep",
    ]
    updated = configure_model.update_env(lines, {
        "INFERENCE_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "new-key",
        "ANTHROPIC_MODEL": "claude-test",
        "INFERENCE_BASE_URL": "",
    })
    text = "\n".join(updated)
    assert "INFERENCE_PROVIDER=anthropic" in text
    assert "VULTR_API_KEY=old" in text
    assert "OTHER=keep" in text
    assert "ANTHROPIC_API_KEY=new-key" in text
    assert "ANTHROPIC_MODEL=claude-test" in text
    assert "INFERENCE_BASE_URL=" in text
    assert text.count("INFERENCE_PROVIDER=") == 1


def test_write_env_sets_private_permissions(tmp_path):
    path = tmp_path / ".env"
    configure_model.write_env(path, {"OPENAI_API_KEY": "secret"})
    assert "OPENAI_API_KEY=secret" in path.read_text()
    assert path.stat().st_mode & 0o777 == 0o600
