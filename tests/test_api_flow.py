from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

ROUTINE = ("I have had a cough and a mild fever for 5 days. "
           "I am allergic to penicillin. My email is alex@example.test.")

LAB = """Hemoglobin 13.5 g/dL (13.0-17.0)
White blood cells 12.4 10^9/L (4.0-10.0)
"""


def new_case():
    data = client.post("/api/intake/start", json={
        "name": "Alex Nguyen", "email": "alex@example.test"}).json()
    return data["case"]["case_id"], data


def ready_case(monkeypatch):
    monkeypatch.setenv("FOLLOWUP_DAYS", "0")
    case_id, _ = new_case()
    turn = client.post(f"/api/intake/{case_id}/message",
                       json={"text": ROUTINE}).json()
    option = turn["case"]["care_options"][0]["name"]
    chosen = client.post(f"/api/cases/{case_id}/choose",
                         json={"option": option}).json()
    assert chosen["case"]["status"] == "pending_review"
    return case_id


def test_healthz_reports_version_and_scheduler():
    data = client.get("/healthz").json()
    assert data["status"] == "ok"
    assert data["version"] == "2.1.0"
    assert "followups" in data
    assert data["storage"]["cases"] >= 0


def test_english_greeting_and_structured_case():
    case_id, data = new_case()
    assert "Hello" in data["reply"]
    turn = client.post(f"/api/intake/{case_id}/message", json={
        "text": "I have a cough and mild fever for 5 days, allergic to "
                "penicillin, email alex@example.test."}).json()
    assert "cough" in turn["case"]["symptoms"]
    assert turn["case"]["duration_days"] == 5
    assert turn["case"]["severity"] == "mild"
    assert turn["case"]["care_options"]


def test_lab_report_upload_merges_findings():
    case_id, _ = new_case()
    response = client.post(
        f"/api/intake/{case_id}/report",
        files={"file": ("labs.txt", LAB, "text/plain")})
    assert response.status_code == 200
    case = response.json()["case"]
    assert case["reports"][0]["filename"] == "labs.txt"
    assert len(case["reports"][0]["findings"]) == 2
    assert any("Lab report" in line for line in case["summary"]["key_findings"])
    assert "path" not in case["reports"][0]


def test_report_upload_rejects_bad_type():
    case_id, _ = new_case()
    response = client.post(
        f"/api/intake/{case_id}/report",
        files={"file": ("scan.png", b"x", "image/png")})
    assert response.status_code == 400


def test_approve_before_the_patient_chooses_is_409():
    case_id, _ = new_case()
    response = client.post(f"/api/cases/{case_id}/approve",
                           json={"advice": "Rest."})
    assert response.status_code == 409


def test_approve_is_single_use(monkeypatch):
    case_id = ready_case(monkeypatch)
    first = client.post(f"/api/cases/{case_id}/approve",
                        json={"advice": "Rest and fluids."})
    assert first.status_code == 200
    second = client.post(f"/api/cases/{case_id}/approve",
                         json={"advice": "Rest again."})
    assert second.status_code == 409


def test_intake_is_closed_after_the_choice(monkeypatch):
    case_id = ready_case(monkeypatch)
    response = client.post(f"/api/intake/{case_id}/message",
                           json={"text": "One more symptom"})
    assert response.status_code == 409


def test_followup_page_and_public_escalation(monkeypatch):
    case_id = ready_case(monkeypatch)
    approved = client.post(f"/api/cases/{case_id}/approve",
                           json={"advice": "Rest and fluids."}).json()
    link = approved["case"]["follow_up"]["link"]
    token = link.rsplit("/", 1)[-1]

    assert client.get(f"/follow-up/{token}").status_code == 200
    public = client.get(f"/api/follow-up/{token}").json()["follow_up"]
    assert public["case_id"] == case_id
    assert "Rest and fluids." in public["advice"]

    escalated = client.post(f"/api/follow-up/{token}",
                            json={"report": "I now have chest pain"})
    assert escalated.status_code == 200
    assert escalated.json()["follow_up"]["status"] == "emergency"


def test_doctor_can_send_checkin_now(monkeypatch):
    case_id = ready_case(monkeypatch)
    client.post(f"/api/cases/{case_id}/approve",
                json={"advice": "Rest and fluids."})
    sent = client.post(f"/api/cases/{case_id}/follow-up/send")
    assert sent.status_code == 200
    assert sent.json()["follow_up"]["sent_at"]
    mailbox = client.get("/api/mailbox").json()["emails"]
    assert any(email["case_id"] == case_id and "Check-in" in email["subject"]
               for email in mailbox)


def test_unknown_case_choose_is_404():
    response = client.post("/api/cases/C-NOPE/choose", json={"option": "x"})
    assert response.status_code == 404


def test_invalid_care_option_is_409(monkeypatch):
    case_id = ready_case(monkeypatch)
    response = client.post(f"/api/cases/{case_id}/choose",
                           json={"option": "Not a real option"})
    assert response.status_code == 409


def test_invalid_email_and_blank_message_are_422():
    bad_email = client.post("/api/intake/start",
                            json={"email": "not-an-email"})
    assert bad_email.status_code == 422

    case_id, _ = new_case()
    blank = client.post(f"/api/intake/{case_id}/message",
                        json={"text": "   "})
    assert blank.status_code == 422


def test_each_outbox_email_can_be_opened_by_id(monkeypatch):
    case_id = ready_case(monkeypatch)
    client.post(f"/api/cases/{case_id}/approve",
                json={"advice": "Rest and fluids."})
    client.post(f"/api/cases/{case_id}/follow-up/send")

    rows = [row for row in client.get("/api/mailbox").json()["emails"]
            if row["case_id"] == case_id]
    assert len({row["id"] for row in rows}) >= 2
    bodies = []
    for row in rows:
        response = client.get(f"/api/emails/{row['id']}")
        assert response.status_code == 200
        assert response.json()["case_id"] == case_id
        bodies.append(response.json()["content"])
    assert any("Doctor's advice" in body for body in bodies)
    assert any("check-in" in body.lower() for body in bodies)
