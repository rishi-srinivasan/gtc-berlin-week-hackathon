from faker import Faker
import random

from pii.synth import generate, steuer_id_valid
from pii.data import SPLITS, build, iban_valid, inject_labels, label_rates


def fake_rows(n):
    return [{"uid": i, "locale": "DE", "source_text": f"Hallo Person{i} aus Berlin.",
             "privacy_mask": [{"label": "GIVEN_NAME", "start": 6, "end": 6 + len(f"Person{i}"),
                               "value": f"Person{i}"}]} for i in range(n)]


def test_iban_checksum():
    assert iban_valid("DE89 3704 0044 0532 0130 00")
    assert not iban_valid("DE89 3704 0044 0532 0130 01")


def test_injected_offsets_and_all_labels():
    from pii.schema import LABELS
    rng, fake = random.Random(1), Faker("de_DE")
    r = inject_labels(fake_rows(1)[0], {l: 1.0 for l in LABELS}, fake, rng)
    for m in r["privacy_mask"]:
        assert r["source_text"][m["start"]:m["end"]] == m["value"]
    assert set(LABELS) <= {m["label"] for m in r["privacy_mask"]}
    assert all(iban_valid(m["value"]) for m in r["privacy_mask"] if m["label"] == "IBAN")


def test_label_rates_normal_and_clipped():
    rates = label_rates(random.Random(0))
    assert all(0.01 <= v <= 0.5 for v in rates.values()) and len(set(rates.values())) > 1


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
    assert {"PORTFOLIO_ID", "IP_ADDRESS", "AGE", "SALARY", "IBAN", "TAX_NUM"} <= {m["label"] for r in rows for m in r["privacy_mask"]}
    ibans = [m["value"] for r in rows for m in r["privacy_mask"] if m["label"] == "IBAN"]
    taxes = [m["value"] for r in rows for m in r["privacy_mask"] if m["label"] == "TAX_NUM"]
    assert all(iban_valid(i) for i in ibans) and all(steuer_id_valid(t) for t in taxes)
    out = build(fake_rows(3000), synth=generate(1500, seed=2), share=0.4)
    assert {k: len(v) for k, v in out.items()} == SPLITS
    assert sum(r["source"] == "synthetic" for r in out["test"]) == 120
