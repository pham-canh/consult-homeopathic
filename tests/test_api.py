from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

ROUTINE = ("I have had a cough and a mild fever for 5 days. "
           "I am allergic to penicillin. My email is alex@example.test.")


def test_healthz_reports_the_stack():
    data = client.get("/healthz").json()
    assert data["status"] == "ok"
    assert data["service"] == "consult-homeopathic"
    assert data["mode"] == "rules (demo)"
    assert data["llm_key"] is False


def test_pages_are_served():
    assert client.get("/").status_code == 200
    assert "Start intake" in client.get("/").text
    assert client.get("/doctor").status_code == 200


def test_end_to_end_api_flow():
    start = client.post("/api/intake/start",
                        json={"name": "Alex Nguyen",
                              "email": "alex@example.test"}).json()
    case_id = start["case"]["case_id"]

    turn = client.post(f"/api/intake/{case_id}/message",
                       json={"text": ROUTINE}).json()
    assert turn["emergency"] is False
    assert turn["case"]["care_options"]
    option = turn["case"]["care_options"][0]["name"]

    chosen = client.post(f"/api/cases/{case_id}/choose",
                         json={"option": option}).json()
    assert chosen["case"]["status"] == "pending_review"

    pending = client.get("/api/doctor/cases?status=pending_review").json()
    assert any(c["case_id"] == case_id for c in pending["cases"])

    approved = client.post(f"/api/cases/{case_id}/approve", json={
        "advice": "Rest, fluids, review in 48 hours.",
        "prescription": "", "notes": "Synthetic demo.", "doctor": "Dr. Demo",
    }).json()
    assert approved["case"]["status"] == "delivered"
    assert approved["case"]["email"]["mode"] == "file"

    mail = client.get(f"/api/mailbox/{case_id}").json()
    assert "review in 48 hours" in mail["content"].lower() or \
           "Rest, fluids" in mail["content"]

    audit = client.get(f"/api/cases/{case_id}").json()["case"]["audit"]
    assert any(a["action"] == "email_delivered" for a in audit)


def test_api_emergency_stops_the_flow():
    start = client.post("/api/intake/start", json={"name": "Sam"}).json()
    case_id = start["case"]["case_id"]
    turn = client.post(f"/api/intake/{case_id}/message",
                       json={"text": "I have severe chest pain"}).json()
    assert turn["emergency"] is True
    assert turn["case"]["status"] == "emergency"
    assert turn["case"]["care_options"] == []


def test_unknown_case_is_404():
    assert client.get("/api/cases/C-NOPE").status_code == 404
