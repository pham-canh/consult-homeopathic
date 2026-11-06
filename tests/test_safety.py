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


def test_routine_symptoms_are_not_emergency():
    assert safety.detect_red_flags("cough and mild fever for five days") == []
