"""Laboratory report ingestion.

Supports plain text, Markdown, CSV, and PDF. The deterministic parser is the
baseline and always runs; when a model key is configured the model may add a
short summary, but it cannot remove parsed values. Images are rejected rather
than silently ignored, because this build has no vision model wired in.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from config import data_dir

MAX_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".md", ".csv", ".pdf"}

VALUE_LINE = re.compile(
    r"^\s*(?P<test>[A-Za-z][A-Za-z0-9 /%().\-]{1,60}?)"
    r"\s*[:\-]?\s+(?P<value>-?\d+(?:[.,]\d+)?)"
    r"\s*(?P<unit>[A-Za-z%/µμ^0-9.\-]{0,20})"
    r"(?:\s*[\(\[]\s*(?P<reference>[^)\]\n]{1,40})\s*[\)\]])?\s*$"
)


class ReportError(ValueError):
    pass


def safe_name(name: str) -> str:
    base = Path(name or "report").name
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .")
    return (base or "report")[:120]


def text_from_bytes(name: str, content: bytes) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ReportError(
            "Unsupported report type. Upload a .txt, .md, .csv, or .pdf file."
        )
    if len(content) > MAX_BYTES:
        raise ReportError("Report is larger than 5 MB.")
    if not content:
        raise ReportError("Report is empty.")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ReportError(
                "PDF support needs the pypdf package; run pip install -r requirements.txt."
            ) from exc
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [(page.extract_text() or "") for page in reader.pages[:20]]
            text = "\n".join(pages)
        except Exception as exc:
            raise ReportError(f"Could not read the PDF: {exc}") from exc
    else:
        text = content.decode("utf-8", "replace")
    text = text.replace("\x00", " ").strip()
    if not text:
        raise ReportError("No text could be read from the report.")
    return text[:50_000]


def _reference_range(reference: str) -> tuple[float, float] | None:
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:[.,]\d+)?)",
        reference or "", re.IGNORECASE)
    if not match:
        return None
    try:
        low = float(match.group(1).replace(",", "."))
        high = float(match.group(2).replace(",", "."))
    except ValueError:
        return None
    return (min(low, high), max(low, high))


def parse_findings(text: str, limit: int = 30) -> list[dict]:
    findings: list[dict] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or len(line) > 160:
            continue
        match = VALUE_LINE.match(line)
        if not match:
            continue
        test = match.group("test").strip(" :-")
        value_text = match.group("value").replace(",", ".")
        try:
            value = float(value_text)
        except ValueError:
            continue
        unit = (match.group("unit") or "").strip()
        reference = (match.group("reference") or "").strip()
        key = test.lower()
        if key in seen:
            continue
        seen.add(key)
        flag = ""
        bounds = _reference_range(reference)
        if bounds:
            low, high = bounds
            if value < low:
                flag = "low"
            elif value > high:
                flag = "high"
        findings.append({
            "test": test,
            "value": value,
            "unit": unit,
            "reference": reference,
            "flag": flag,
        })
        if len(findings) >= limit:
            break
    return findings


def store_file(case_id: str, name: str, content: bytes) -> str:
    """Save the original upload under the data directory; return its path."""
    folder = data_dir() / "reports" / case_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe_name(name)
    path.write_bytes(content)
    return str(path)


def parse_with_rules(text: str) -> dict:
    findings = parse_findings(text)
    abnormal = [f for f in findings if f["flag"]]
    summary = (
        f"Lab report read: {len(findings)} value(s); "
        f"{len(abnormal)} outside the printed reference range."
        if findings else
        "Lab report read, but no numeric results were recognized."
    )
    return {"summary": summary, "findings": findings}


def parse_with_model(text: str) -> dict | None:
    """Optional model pass. Returns None instead of breaking the upload."""
    import config
    import inference

    if not inference.have_key() or config.demo_mode():
        return None
    system = (
        "You extract laboratory results from a patient-provided report. "
        "Return ONLY JSON: {\"summary\": \"one short English sentence\", "
        "\"findings\": [{\"test\": \"English test name\", \"value\": 0, "
        "\"unit\": \"\", \"reference\": \"\", \"flag\": \"high|low|\"}]}. "
        "Copy numbers exactly; do not invent values. Summary must be English."
    )
    user = f"Report text:\n{text[:12000]}"
    try:
        data = inference.ask_json(system, user)
    except inference.InferenceError:
        return None
    findings = []
    for item in data.get("findings") or []:
        if not isinstance(item, dict):
            continue
        test = str(item.get("test") or "").strip()[:80]
        if not test:
            continue
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        flag = str(item.get("flag") or "").lower()
        findings.append({
            "test": test,
            "value": value,
            "unit": str(item.get("unit") or "").strip()[:20],
            "reference": str(item.get("reference") or "").strip()[:40],
            "flag": flag if flag in {"high", "low"} else "",
        })
    if not findings:
        return None
    summary = str(data.get("summary") or "").strip()[:400]
    return {"summary": summary or "Lab report read.", "findings": findings[:30]}
