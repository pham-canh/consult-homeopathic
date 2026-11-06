import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Isolate every test run and force the deterministic engine: no network, no key.
# Empty strings (not deletes) stop .env from filling these back in on import.
os.environ["CONSULT_FAKE_LLM"] = "1"
os.environ["CONSULT_DATA_DIR"] = tempfile.mkdtemp(prefix="consult-test-")
for name in ("INFERENCE_API_KEY", "VULTR_API_KEY", "OPENAI_API_KEY",
             "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
             "INFERENCE_MODEL", "VULTR_MODEL", "OPENAI_MODEL",
             "ANTHROPIC_MODEL", "GEMINI_MODEL", "INFERENCE_PROVIDER",
             "INFERENCE_BASE_URL", "SMTP_HOST"):
    os.environ[name] = ""
