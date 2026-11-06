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
