from pii.redact import mask, rehydrate


def ents(*pairs):
    return [{"text": t, "label": l} for t, l in pairs]


def test_basic_and_roundtrip():
    text = "Hallo Max Müller, mail an max@x.de bitte."
    masked, m = mask(text, ents(("Max", "GIVEN_NAME"), ("Müller", "SURNAME"), ("max@x.de", "EMAIL")))
    assert masked == "Hallo [GIVEN_NAME_1] [SURNAME_1], mail an [EMAIL_1] bitte."
    assert rehydrate(masked, m) == text


def test_repeated_value_same_placeholder():
    masked, m = mask("Anna sagt: Anna kommt, Eva auch.", ents(("Anna", "GIVEN_NAME"), ("Eva", "GIVEN_NAME")))
    assert masked == "[GIVEN_NAME_1] sagt: [GIVEN_NAME_1] kommt, [GIVEN_NAME_2] auch."
    assert len(m) == 2


def test_overlap_longest_wins():
    text = "Kontakt: Max Mustermann"
    masked, m = mask(text, ents(("Max", "GIVEN_NAME"), ("Max Mustermann", "USER_NAME")))
    assert masked == "Kontakt: [USER_NAME_1]"
    assert rehydrate(masked, m) == text


def test_no_match_inside_longer_word():
    masked, _ = mask("Maximilian und Max", ents(("Max", "GIVEN_NAME")))
    assert masked == "Maximilian und [GIVEN_NAME_1]"


def test_unknown_placeholder_left_alone():
    assert rehydrate("[CITY_9] hi", {}) == "[CITY_9] hi"
