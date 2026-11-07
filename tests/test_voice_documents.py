from fastapi.testclient import TestClient

import voice
from app import app

client = TestClient(app)

LAB = """Hemoglobin 13.5 g/dL (13.0-17.0)
White blood cells 12.4 10^9/L (4.0-10.0)
"""


def new_case(email: str = "voice@example.test") -> str:
    data = client.post("/api/intake/start", json={
        "name": "Alex Nguyen", "email": email}).json()
    return data["case"]["case_id"]


def test_voice_turn_returns_transcript_reply_and_audio(monkeypatch):
    monkeypatch.setattr(voice, "transcribe",
                        lambda *args, **kwargs: "I have a cough for 5 days.")
    monkeypatch.setattr(voice, "speech", lambda text: b"ID3fake-mp3")
    case_id = new_case()

    response = client.post(
        f"/api/intake/{case_id}/voice",
        files={"file": ("voice.webm", b"fake-webm", "audio/webm")})

    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "I have a cough for 5 days."
    assert data["reply"]
    assert data["audio"]
    assert data["case"]["patient"]["email"] == "voice@example.test"


def test_voice_error_is_a_400(monkeypatch):
    def fail(*args, **kwargs):
        raise voice.VoiceError("No speech was recognized.")

    monkeypatch.setattr(voice, "transcribe", fail)
    case_id = new_case()

    response = client.post(
        f"/api/intake/{case_id}/voice",
        files={"file": ("voice.webm", b"fake-webm", "audio/webm")})

    assert response.status_code == 400
    assert "No speech" in response.json()["detail"]


def test_document_upload_opens_a_document_aware_reply_and_can_be_downloaded():
    case_id = new_case("documents@example.test")
    uploaded = client.post(
        f"/api/intake/{case_id}/report",
        files={"file": ("labs.txt", LAB, "text/plain")})

    assert uploaded.status_code == 200
    data = uploaded.json()
    assert "I read labs.txt" in data["reply"]
    assert "outside the reference range" in data["reply"]

    download = client.get(f"/api/cases/{case_id}/reports/0/file")
    assert download.status_code == 200
    assert b"Hemoglobin" in download.content


def test_prior_cases_are_linked_by_patient_email():
    first = new_case("history@example.test")
    client.post(f"/api/intake/{first}/message", json={
        "text": "I have a cough for 5 days."})

    second = new_case("history@example.test")
    detail = client.get(f"/api/cases/{second}").json()["case"]

    assert detail["prior_cases"]
    assert detail["prior_cases"][0]["case_id"] == first


def test_diet_is_extracted_from_the_conversation():
    case_id = new_case("diet@example.test")
    turn = client.post(f"/api/intake/{case_id}/message", json={
        "text": "I have had a cough for 8 days. My diet is vegetarian."}).json()

    assert turn["case"]["patient"]["diet"] == "vegetarian"
    assert any("Diet: vegetarian" in line
               for line in turn["case"]["summary"]["key_findings"])
