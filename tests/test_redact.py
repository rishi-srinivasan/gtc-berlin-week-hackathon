from pii.redact import mask, rehydrate


def ents(*pairs):
    return [{"text": t, "label": l} for t, l in pairs]


def test_basic_and_roundtrip():
    text = "Hallo Max Müller, mail an max@x.de bitte."
    masked, m = mask(text, ents(("Max", "GIVENNAME"), ("Müller", "SURNAME"), ("max@x.de", "EMAIL")))
    assert masked == "Hallo [GIVENNAME_1] [SURNAME_1], mail an [EMAIL_1] bitte."
    assert rehydrate(masked, m) == text


def test_repeated_value_same_placeholder():
    masked, m = mask("Anna sagt: Anna kommt, Eva auch.", ents(("Anna", "GIVENNAME"), ("Eva", "GIVENNAME")))
    assert masked == "[GIVENNAME_1] sagt: [GIVENNAME_1] kommt, [GIVENNAME_2] auch."
    assert len(m) == 2


def test_overlap_longest_wins():
    text = "Kontakt: Max Mustermann"
    masked, m = mask(text, ents(("Max", "GIVENNAME"), ("Max Mustermann", "USERNAME")))
    assert masked == "Kontakt: [USERNAME_1]"
    assert rehydrate(masked, m) == text


def test_no_match_inside_longer_word():
    masked, _ = mask("Maximilian und Max", ents(("Max", "GIVENNAME")))
    assert masked == "Maximilian und [GIVENNAME_1]"


def test_unknown_placeholder_left_alone():
    assert rehydrate("[CITY_9] hi", {}) == "[CITY_9] hi"
