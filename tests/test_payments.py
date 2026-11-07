from fastapi.testclient import TestClient

from app import app

client = TestClient(app)

ROUTINE = ("I have had a cough and a mild fever for 5 days. "
           "No allergies. No medications. My email is pay@example.test.")


def ready_case(monkeypatch) -> str:
    monkeypatch.setenv("FOLLOWUP_DAYS", "0")
    data = client.post("/api/intake/start", json={
        "name": "Pay Demo", "email": "pay@example.test"}).json()
    case_id = data["case"]["case_id"]
    turn = client.post(f"/api/intake/{case_id}/message",
                       json={"text": ROUTINE}).json()
    option = turn["case"]["care_options"][0]["name"]
    client.post(f"/api/cases/{case_id}/choose", json={"option": option})
    return case_id


def approved_case(monkeypatch) -> tuple[str, str, dict]:
    case_id = ready_case(monkeypatch)
    approved = client.post(f"/api/cases/{case_id}/approve",
                           json={"advice": "Rest and fluids."}).json()["case"]
    link = approved["payment"]["link"]
    token = link.rsplit("/", 1)[-1]
    return case_id, token, approved


def test_payment_page_and_api_are_public(monkeypatch):
    _, token, approved = approved_case(monkeypatch)
    assert approved["payment"]["status"] == "unpaid"
    assert approved["payment"]["demo"] is True
    assert approved["payment"]["amount_display"] == "$29.00"

    page = client.get(f"/pay/{token}")
    assert page.status_code == 200
    assert "Consultation fee" in page.text

    data = client.get(f"/api/pay/{token}")
    assert data.status_code == 200
    body = data.json()
    assert body["payment"]["status"] == "unpaid"
    assert body["case"]["case_id"]
    assert body["payment"]["methods"]


def test_demo_payment_records_a_receipt_and_audit(monkeypatch):
    case_id, token, _ = approved_case(monkeypatch)
    response = client.post(f"/api/pay/{token}", json={"method": "card"})
    assert response.status_code == 200
    data = response.json()
    assert data["payment"]["status"] == "paid_demo"
    assert data["payment"]["method_label"] == "Card (demo)"
    assert data["receipt"]["demo"] is True

    again = client.post(f"/api/pay/{token}", json={"method": "card"})
    assert again.status_code == 200
    assert again.json()["payment"]["status"] == "paid_demo"

    case = client.get(f"/api/cases/{case_id}").json()["case"]
    assert case["payment"]["status"] == "paid_demo"
    assert any(entry["action"] == "payment_demo_paid"
               for entry in case["audit"])


def test_payment_rejects_unknown_method_and_token(monkeypatch):
    _, token, _ = approved_case(monkeypatch)
    bad = client.post(f"/api/pay/{token}", json={"method": "cash"})
    assert bad.status_code == 400
    assert client.get("/api/pay/not-a-token").status_code == 404


def test_plan_email_contains_the_demo_payment_link(monkeypatch):
    _, token, approved = approved_case(monkeypatch)
    mailbox = client.get("/api/mailbox").json()["emails"]
    email = next(item for item in mailbox
                 if item["case_id"] == approved["case_id"])
    body = client.get(f"/api/emails/{email['id']}").json()["body"]
    assert "Consultation fee" in body
    assert f"/pay/{token}" in body
