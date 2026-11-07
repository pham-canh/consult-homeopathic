import safety


def labels(text):
    return {flag["label"] for flag in safety.detect_red_flags(text)}


def test_chest_pain_is_a_red_flag():
    assert "chest pain" in labels("I have chest pain since this morning")


def test_breathing_difficulty_is_a_red_flag():
    assert "breathing difficulty" in labels("I cannot breathe properly")


def test_stroke_signs_are_a_red_flag():
    assert "stroke signs" in labels("Her face drooping and slurred speech")


def test_stiff_neck_and_confusion_are_red_flags():
    assert "stiff neck or confusion" in labels("My neck feels stiff and I am confused")


def test_self_harm_is_a_red_flag():
    assert "self-harm risk" in labels("I want to die")


def test_explicit_negation_is_not_a_red_flag():
    assert safety.detect_red_flags("I have no chest pain and no trouble breathing") == []
    assert safety.detect_red_flags("I do not have chest pain") == []
    assert safety.detect_red_flags("No chest pain or shortness of breath") == []
    assert safety.detect_red_flags("I have never had a seizure") == []


def test_negation_does_not_hide_a_later_positive_red_flag():
    assert "chest pain" in labels("I have no fever but chest pain")
    assert "chest pain" in labels("No fever, chest pain since morning")
    assert "chest pain" in labels("No cough but I have chest pain")
    assert "chest pain" in labels("I have no fever and chest pain")
    assert "chest pain" in labels("Not sure if I have chest pain")


def test_reply_guard_blocks_explicit_prescribing():
    guarded, reason = safety.guard_reply("Take 500 mg amoxicillin twice daily.")
    assert guarded == safety.SAFE_REPLY
    assert reason

    guarded, reason = safety.guard_reply(
        "The diagnosis is a chest infection. I recommend 500 mg amoxicillin.")
    assert guarded == safety.SAFE_REPLY
    assert reason

    for text in (
        "You can take 500 mg amoxicillin twice daily.",
        "You may start amoxicillin 500 mg now.",
        "Amoxicillin 500 mg twice daily.",
        "The dose is 500 mg twice daily.",
        "Diagnosis: chest infection.",
        "I think you have a chest infection.",
    ):
        guarded, reason = safety.guard_reply(text)
        assert guarded == safety.SAFE_REPLY, text
        assert reason, text


def test_reply_guard_allows_doctor_decisions_and_medication_history():
    text = "A licensed doctor will decide whether a prescription is needed."
    assert safety.guard_reply(text) == (text, "")
    text = "You take metformin 500 mg daily, is that correct?"
    assert safety.guard_reply(text) == (text, "")
    text = "Glucose 95 mg/dL is within the printed reference range."
    assert safety.guard_reply(text) == (text, "")


def test_routine_symptoms_are_not_emergency():
    assert safety.detect_red_flags("cough and mild fever for five days") == []
