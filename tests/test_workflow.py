import pytest

import agent
import case_model
import emailer
import store

ROUTINE = ("I have had a cough and a mild fever for 5 days. "
           "I am allergic to penicillin. My email is alex@example.test.")


def fresh_case():
    store.init_db()
    return agent.start_case("Alex Nguyen", "alex@example.test")


def test_emergency_gate_stops_the_flow():
    case = fresh_case()
    result = agent.handle_message(case, "I have chest pain and cannot breathe")
    assert result["emergency"] is True
    assert result["case"]["status"] == case_model.STATUS_EMERGENCY
    assert result["case"]["red_flags"]
    assert "emergency" in result["reply"].lower()


def test_routine_intake_extracts_a_structured_case():
    case = fresh_case()
    result = agent.handle_message(case, ROUTINE)
    case = result["case"]
    assert result["emergency"] is False
    assert case["duration_days"] == 5
    assert case["severity"] == "mild"
    assert "penicillin" in case["patient"]["allergies"]
    assert case["patient"]["email"] == "alex@example.test"
    assert len(case["care_options"]) >= 2
    assert case["status"] == case_model.STATUS_INTAKE


def test_choose_then_approve_delivers_email_and_audit():
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    option = case["care_options"][0]["name"]
    case = agent.choose_option(case["case_id"], option)
    assert case["status"] == case_model.STATUS_PENDING
    assert case["selected_option"] == option
    assert case["summary"]["one_liner"]

    case = agent.approve(case["case_id"], advice="Rest, fluids, and review in 48h.",
                         prescription="", notes="Synthetic demo.", doctor="Dr. Demo")
    assert case["status"] == case_model.STATUS_DELIVERED
    assert case["doctor"]["approved_by"] == "Dr. Demo"
    assert case["email"]["mode"] == "file"
    assert case["email"]["to"] == "alex@example.test"

    audit_actions = {a["action"] for a in store.list_audit(case["case_id"])}
    assert {"intake_started", "patient_message", "option_chosen",
            "case_approved", "email_delivered"} <= audit_actions

    emails = store.list_emails()
    assert any(e["case_id"] == case["case_id"] for e in emails)


def test_allergy_check_warns_about_a_conflict():
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    case["doctor"]["prescription"] = "Amoxicillin 500 mg"
    warnings = case_model.allergy_warnings(case)
    assert warnings and "penicillin" in warnings[0].lower()


def test_follow_up_escalates_when_the_patient_reports_a_red_flag():
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    case = agent.choose_option(case["case_id"], case["care_options"][0]["name"])
    case = agent.approve(case["case_id"], advice="Review in 48h.")
    case = agent.follow_up(case["case_id"], "Now I have severe chest pain")
    assert case["status"] == case_model.STATUS_EMERGENCY


def test_email_contains_the_doctor_plan(monkeypatch):
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    case = agent.choose_option(case["case_id"], case["care_options"][0]["name"])
    case = agent.approve(case["case_id"], advice="Drink water and rest.")
    to_addr, subject, body = emailer.compose(store.get_case(case["case_id"]))
    assert to_addr == "alex@example.test"
    assert "Drink water and rest." in body
    assert "not a medical device" in body


def test_bad_model_shapes_do_not_crash_or_trigger_a_false_emergency(monkeypatch):
    monkeypatch.setattr(agent.config, "demo_mode", lambda: False)
    monkeypatch.setattr(agent.inference, "have_key", lambda: True)
    monkeypatch.setattr(agent.inference, "engine_label", lambda: "test / model")
    monkeypatch.setattr(agent.inference, "ask_json", lambda system, user: {
        "reply": ["not", "a", "string"],
        "emergency": "false",
        "red_flags": "none",
        "care_options": "Online doctor review",
        "patient": {},
        "summary": {},
    })
    case = fresh_case()
    result = agent.handle_message(case, "I have a cough for 2 days")
    assert result["emergency"] is False
    assert result["reply"] == agent.copy.ASK_MORE
    assert result["case"]["status"] == case_model.STATUS_INTAKE
    assert result["case"]["care_options"] == [
        {"name": "Online doctor review", "why": ""}]


def test_model_summary_keeps_deterministic_lab_findings(monkeypatch):
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    case = agent.attach_report(
        case["case_id"], "labs.txt",
        b"White blood cells 12.4 10^9/L (4.0-10.0)\n", "text/plain")
    lab_line = next(line for line in case["summary"]["key_findings"]
                    if line.startswith("Lab report"))

    monkeypatch.setattr(agent.config, "demo_mode", lambda: False)
    monkeypatch.setattr(agent.inference, "have_key", lambda: True)
    monkeypatch.setattr(agent.inference, "engine_label", lambda: "test / model")
    monkeypatch.setattr(agent.inference, "ask_json", lambda system, user: {
        "reply": "Thanks, noted.",
        "summary": {"one_liner": "Updated summary",
                    "key_findings": ["Model finding"],
                    "safety_notes": ["Model note"]},
    })
    updated = agent.handle_message(
        case, "The cough is still mild. My email is alex@example.test.")["case"]
    assert lab_line in updated["summary"]["key_findings"]
    assert "Model finding" in updated["summary"]["key_findings"]
    assert case_model.SAFETY_NOTE in updated["summary"]["safety_notes"]


def test_follow_up_requires_an_approved_plan():
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    case = agent.choose_option(case["case_id"], case["care_options"][0]["name"])
    with pytest.raises(agent.WorkflowError, match="follow-up"):
        agent.follow_up(case["case_id"], "I feel worse")


def test_email_failure_leaves_the_case_pending(monkeypatch):
    case = fresh_case()
    case = agent.handle_message(case, ROUTINE)["case"]
    case = agent.choose_option(case["case_id"], case["care_options"][0]["name"])

    def fail(_case):
        raise OSError("smtp is down")

    monkeypatch.setattr(agent.emailer, "send", fail)
    with pytest.raises(agent.WorkflowError, match="could not be emailed"):
        agent.approve(case["case_id"], advice="Rest and fluids.")

    saved = store.get_case(case["case_id"])
    assert saved["status"] == case_model.STATUS_PENDING
    assert store.get_followup(case["case_id"]) is None
    assert any(item["action"] == "email_failed"
               for item in store.list_audit(case["case_id"]))
    with pytest.raises(agent.WorkflowError, match="delivered a plan"):
        agent.follow_up(case["case_id"], "I feel worse")
