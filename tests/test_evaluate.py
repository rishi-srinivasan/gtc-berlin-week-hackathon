from pii.evaluate import evaluate, leaked, upper95
from pii.redact import mask


def test_leak_text_and_numeric():
    assert leaked("SURNAME", "Müller", "Hallo müller")
    assert not leaked("SURNAME", "Müller", "Hallo [SURNAME_1]")
    assert leaked("IBAN", "DE89 3704 0044 0532 0130 00", "IBAN DE89370400440532013000")
    assert not leaked("IBAN", "DE89 3704 0044 0532 0130 00", "IBAN [IBAN_1]")


def test_upper95():
    assert upper95(0, 100) == 0.03
    assert 0.05 < upper95(2, 100) < 0.1


def test_evaluate_counts_missed_entity_as_leak():
    gold = [{"uid": 1, "text": "Anna Berg wohnt in Ulm",
             "entities": [{"label": "GIVENNAME", "text": "Anna"}, {"label": "CITY", "text": "Ulm"}]}]
    preds = {1: {"entities": [{"label": "GIVENNAME", "text": "Anna"}], "trace_id": None}}
    leaks, per_label, tier, _ = evaluate(gold, preds)
    assert leaks == [True] and per_label["CITY", "tp"] == 0 and per_label["GIVENNAME", "tp"] == 1
