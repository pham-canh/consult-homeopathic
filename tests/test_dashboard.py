from fastapi.testclient import TestClient

import auth
from app import app

client = TestClient(app)

ROUTINE = ("I have had a cough and a mild fever for 5 days. "
           "I am allergic to penicillin. My email is alex@example.test.")


def new_case(name="Alex Nguyen", email="alex@example.test"):
    data = client.post("/api/intake/start", json={
        "name": name, "email": email}).json()
    return data["case"]["case_id"]


def ready_case(monkeypatch):
    monkeypatch.setenv("FOLLOWUP_DAYS", "0")
    case_id = new_case()
    turn = client.post(f"/api/intake/{case_id}/message",
                       json={"text": ROUTINE}).json()
    option = turn["case"]["care_options"][0]["name"]
    client.post(f"/api/cases/{case_id}/choose", json={"option": option})
    return case_id


def test_healthz_reports_dashboard_auth_state():
    data = client.get("/healthz").json()
    assert data["dashboard_auth"] is False
    assert client.get("/api/auth/me").json()["enabled"] is False


def test_login_page_redirects_when_auth_is_disabled():
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/doctor"


def test_dashboard_login_protects_staff_apis(monkeypatch):
    auth.reset_attempts()
    monkeypatch.setenv("CONSULT_DASHBOARD_PASSWORD", "s3cret")
    local = TestClient(app)

    assert local.get("/healthz").json()["dashboard_auth"] is True
    assert local.get("/api/doctor/cases").status_code == 401
    assert local.get("/api/dashboard").status_code == 401
    assert local.get("/api/followups").status_code == 401

    page = local.get("/doctor", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"].startswith("/login")
    assert local.get("/login").status_code == 200

    me = local.get("/api/auth/me").json()
    assert me == {"enabled": True, "authenticated": False, "user": ""}

    bad = local.post("/api/auth/login", json={"password": "wrong"})
    assert bad.status_code == 401
    ok = local.post("/api/auth/login", json={"password": "s3cret"})
    assert ok.status_code == 200
    assert local.get("/api/auth/me").json()["authenticated"] is True
    assert local.get("/api/doctor/cases").status_code == 200
    assert local.get("/api/dashboard").status_code == 200
    assert local.get("/api/followups").status_code == 200

    local.post("/api/auth/logout")
    assert local.get("/api/dashboard").status_code == 401


def test_dashboard_overview_aggregates_cases(monkeypatch):
    ready_case(monkeypatch)
    delivered_id = ready_case(monkeypatch)
    client.post(f"/api/cases/{delivered_id}/approve",
                json={"advice": "Rest and fluids."})
    data = client.get("/api/dashboard").json()
    assert data["cases"]["total"] >= 2
    assert data["cases"]["pending_review"] >= 1
    assert data["cases"]["delivered"] >= 1
    assert len(data["trend"]) == 7
    assert 0 < len(data["recent"]) <= 8
    assert all(row["case_id"] for row in data["recent"])
    assert isinstance(data["attention"], list)
    assert data["followups"]["total"] >= 1


def test_case_search_and_status_filters(monkeypatch):
    case_id = ready_case(monkeypatch)
    found = client.get("/api/doctor/cases",
                       params={"q": case_id, "status": "pending_review"}).json()
    assert found["total"] == 1
    assert found["cases"][0]["case_id"] == case_id
    missing = client.get("/api/doctor/cases",
                         params={"q": "no-such-patient-xyz"}).json()
    assert missing["total"] == 0


def test_followups_endpoint_lists_scheduled_checkin(monkeypatch):
    case_id = ready_case(monkeypatch)
    approved = client.post(f"/api/cases/{case_id}/approve",
                           json={"advice": "Rest and fluids."}).json()
    token = approved["case"]["follow_up"]["link"].rsplit("/", 1)[-1]
    rows = client.get("/api/followups").json()["follow_ups"]
    row = next(item for item in rows if item["case_id"] == case_id)
    assert row["link"].endswith(token)
    assert row["state"] in {"due", "scheduled"}
    due = client.get("/api/followups", params={"state": "due"}).json()
    assert all(item["state"] == "due" for item in due["follow_ups"])
