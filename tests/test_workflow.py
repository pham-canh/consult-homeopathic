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
