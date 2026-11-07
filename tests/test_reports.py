import pytest

import reports


TEXT = """Complete blood count
Hemoglobin: 13.5 g/dL (13.0-17.0)
White blood cells 12.4 10^9/L (4.0-10.0)
Glucose 95 mg/dL (70-100)
"""


def test_parses_values_and_flags_abnormal_results():
    parsed = reports.parse_with_rules(TEXT)
    by_test = {item["test"].lower(): item for item in parsed["findings"]}
    assert by_test["hemoglobin"]["value"] == 13.5
    assert by_test["white blood cells"]["flag"] == "high"
    assert by_test["glucose"]["flag"] == ""
    assert "outside" in parsed["summary"]


def test_rejects_unsupported_file_type():
    with pytest.raises(reports.ReportError):
        reports.text_from_bytes("scan.png", b"not an image")


def test_rejects_empty_file():
    with pytest.raises(reports.ReportError):
        reports.text_from_bytes("empty.txt", b"")


def test_safe_name_strips_paths_and_odd_characters():
    assert reports.safe_name("../../my report!.txt") == "my report_.txt"


def test_model_cannot_remove_or_overwrite_rule_findings(monkeypatch):
    monkeypatch.setattr(reports, "parse_with_model", lambda text: {
        "summary": "Model summary.",
        "findings": [
            {"test": "White blood cells", "value": 99.0, "unit": "",
             "reference": "", "flag": ""},
            {"test": "New marker", "value": 1.0, "unit": "mg/L",
             "reference": "", "flag": "high"},
        ],
    })
    parsed = reports.parse_report(TEXT)
    by_test = {item["test"].lower(): item for item in parsed["findings"]}
    assert by_test["white blood cells"]["value"] == 12.4
    assert by_test["white blood cells"]["flag"] == "high"
    assert by_test["new marker"]["value"] == 1.0
    assert "Model summary." in parsed["summary"]
    assert "Deterministic check" in parsed["summary"]


def test_model_summary_is_used_when_rules_find_no_numbers(monkeypatch):
    monkeypatch.setattr(reports, "parse_with_model", lambda text: {
        "summary": "Narrative report looks unremarkable.",
        "findings": [],
    })
    parsed = reports.parse_report("A narrative report with no numeric values.")
    assert parsed["findings"] == []
    assert "Narrative report looks unremarkable." in parsed["summary"]
