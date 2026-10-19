from faker import Faker
import random

from pii.synth import generate, steuer_id_valid
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


def test_synthetic_rows_offsets_labels_and_share():
    from pii.schema import LABELS
    rows = generate(300, seed=1)
    for r in rows:
        for m in r["privacy_mask"]:
            assert r["source_text"][m["start"]:m["end"]] == m["value"] and m["label"] in LABELS
        assert "ISIN" not in {m["label"] for m in r["privacy_mask"]}
    assert {"PORTFOLIOID", "IPADDRESS", "AGE", "SALARY", "IBAN", "TAXNUM"} <= {m["label"] for r in rows for m in r["privacy_mask"]}
    ibans = [m["value"] for r in rows for m in r["privacy_mask"] if m["label"] == "IBAN"]
    taxes = [m["value"] for r in rows for m in r["privacy_mask"] if m["label"] == "TAXNUM"]
    assert all(iban_valid(i) for i in ibans) and all(steuer_id_valid(t) for t in taxes)
    out = build(fake_rows(3000), synth=generate(1500, seed=2), share=0.4)
    assert {k: len(v) for k, v in out.items()} == SPLITS
    assert sum(r["source"] == "synthetic" for r in out["test"]) == 120
