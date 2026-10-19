from faker import Faker
import random

from pii.data import SPLITS, build, iban_valid, inject_iban


def fake_rows(n):
    return [{"uid": i, "locale": "DE", "source_text": f"Hallo Person{i} aus Berlin.",
             "privacy_mask": [{"label": "GIVENNAME", "start": 6, "end": 6 + len(f"Person{i}"),
                               "value": f"Person{i}"}]} for i in range(n)]


def test_iban_checksum():
    assert iban_valid("DE89 3704 0044 0532 0130 00")
    assert not iban_valid("DE89 3704 0044 0532 0130 01")


def test_injected_offsets_and_validity():
    rng, fake = random.Random(1), Faker("de_DE")
    for _ in range(50):
        r = inject_iban(fake_rows(1)[0], fake, rng)
        span = r["privacy_mask"][-1]
        assert r["source_text"][span["start"]:span["end"]] == span["value"]
        assert iban_valid(span["value"])


def test_splits_disjoint_and_sized():
    out = build(fake_rows(3000) + fake_rows(50))  # 50 duplicates must be dropped
    assert {k: len(v) for k, v in out.items()} == SPLITS
    uids = [r["uid"] for v in out.values() for r in v]
    texts = [r["text"] for v in out.values() for r in v]
    assert len(set(uids)) == len(uids) and len(set(texts)) == len(texts)
    assert any(e["label"] == "IBAN" for v in out.values() for r in v for e in r["entities"])
