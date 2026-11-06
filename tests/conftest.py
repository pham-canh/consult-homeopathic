import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Isolate every test run and force the deterministic engine: no network, no key.
os.environ["CONSULT_FAKE_LLM"] = "1"
os.environ["CONSULT_DATA_DIR"] = tempfile.mkdtemp(prefix="consult-test-")
os.environ.pop("INFERENCE_API_KEY", None)
os.environ.pop("SMTP_HOST", None)
