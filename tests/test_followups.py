import agent
import case_model
import followups
import store

ROUTINE = ("I have had a cough and a mild fever for 5 days. "
           "I am allergic to penicillin. My email is alex@example.test.")


def delivered_case(monkeypatch):
    monkeypatch.setenv("FOLLOWUP_DAYS", "0")
    store.init_db()
    case = agent.start_case("Alex Nguyen", "alex@example.test")
    case = agent.handle_message(case, ROUTINE)["case"]
    case = agent.choose_option(case["case_id"], case["care_options"][0]["name"])
    return agent.approve(case["case_id"], advice="Rest and fluids.")


def test_approval_schedules_a_checkin(monkeypatch):
    case = delivered_case(monkeypatch)
    row = store.get_followup(case["case_id"])
    assert row and row["token"]
    assert case["follow_up"]["due_at"]


def test_due_checkin_sends_email_and_marks_sent(monkeypatch):
    case = delivered_case(monkeypatch)
    sent = followups.send_due(case_model.now())
    assert case["case_id"] in sent
    row = store.get_followup(case["case_id"])
    assert row["sent_at"]
    emails = store.list_emails()
    assert any("Check-in" in email["subject"] for email in emails)
    updated = store.get_case(case["case_id"])
    assert updated["follow_up"]["sent_at"]


def test_doctor_can_send_checkin_now(monkeypatch):
    case = delivered_case(monkeypatch)
    row = followups.send_now(case["case_id"])
    assert row["sent_at"]
    again = followups.send_now(case["case_id"])
    assert again["sent_at"] == row["sent_at"]


def test_followup_token_escalates_on_red_flag(monkeypatch):
    case = delivered_case(monkeypatch)
    token = store.get_followup(case["case_id"])["token"]
    updated = agent.follow_up_by_token(token, "Now I have severe chest pain")
    assert updated["status"] == case_model.STATUS_EMERGENCY
    assert updated["needs_attention"] is True
    assert updated["follow_up"]["reports"][-1]["red_flags"]
    assert "emergency" in updated["transcript"][-1]["text"].lower()




def test_followup_escalates_on_stiff_neck_and_confusion(monkeypatch):
    case = delivered_case(monkeypatch)
    token = store.get_followup(case["case_id"])["token"]
    updated = agent.follow_up_by_token(
        token, "Fever is now 39.6 C and my neck feels stiff. I am confused.")
    assert updated["status"] == case_model.STATUS_EMERGENCY
    assert updated["needs_attention"] is True
    assert updated["follow_up"]["reports"][-1]["red_flags"]
