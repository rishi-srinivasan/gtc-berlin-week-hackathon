"""Download the German slice of ai4privacy/pii-masking-400k, inject IBANs, write splits."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from faker import Faker

from . import synth

SPLITS = {"test": 300, "seed": 100, "pool": 2000}
IBAN_RATE = 0.15
PHRASINGS = [
    "IBAN: {}", "Bitte überweisen Sie auf IBAN {}.", "Meine Bankverbindung: {}",
    "Konto (IBAN): {}", "Rückerstattung an {} bitte.",
]


def iban_valid(iban: str) -> bool:
    """ISO 13616 mod-97 check."""
    s = iban.replace(" ", "").upper()
    if len(s) < 15 or not s.isalnum():
        return False
    num = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(num) % 97 == 1


def inject_iban(row: dict, fake: Faker, rng: random.Random) -> dict:
    """Append a sentence with a valid German IBAN (spaced or compact) and add its span."""
    iban = fake.iban()
    assert iban_valid(iban)
    if rng.random() < 0.5:
        iban = " ".join(iban[i:i + 4] for i in range(0, len(iban), 4))
    sentence = rng.choice(PHRASINGS).format(iban)
    text = row["source_text"].rstrip() + " "
    start = len(text) + sentence.index(iban)
    mask = row["privacy_mask"] + [{"label": "IBAN", "start": start,
                                   "end": start + len(iban), "value": iban}]
    return {**row, "source_text": text + sentence, "privacy_mask": mask}


def to_example(row: dict) -> dict:
    ents = list({(m["label"], m["value"]): {"text": m["value"], "label": m["label"]}
                 for m in row["privacy_mask"]}.values())
    return {"uid": row["uid"], "locale": row["locale"], "source": row.get("source", "hf"),
            "text": row["source_text"], "entities": ents, "privacy_mask": row["privacy_mask"]}


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in Path(path).open()]


def load_gold(split: str) -> list[dict]:
    """Gold rows of a split; the test split prefers the hand-reviewed data/test_clean.jsonl."""
    if split == "test" and Path("data/test_clean.jsonl").exists():
        return read_jsonl("data/test_clean.jsonl")
    if split == "test":
        print("note: data/test_clean.jsonl not found, using raw test labels (make review)")
    return read_jsonl(f"data/{split}.jsonl")


def load_german(locale: str | None, max_rows: int):
    from datasets import load_dataset
    ds = load_dataset("ai4privacy/pii-masking-400k", split="train", streaming=True)
    n = 0
    for r in ds:
        if r["language"] != "de" or (locale and r["locale"] != locale):
            continue
        yield r
        n += 1
        if n >= max_rows:
            return


def dedupe(rows):
    seen = set()
    return [r for r in rows if not (r["source_text"] in seen or seen.add(r["source_text"]))]


def build(rows, synth=(), share: float = 0.0, seed: int = 0):
    """Dedupe, inject IBANs into HF rows, mix in `share` synthetic rows per split, split. Pure: easy to test."""
    rng, fake = random.Random(seed), Faker("de_DE")
    Faker.seed(seed)
    hf, syn = dedupe(rows), dedupe(synth)
    rng.shuffle(hf)
    rng.shuffle(syn)
    out = {}
    for name, n in SPLITS.items():
        k = round(share * n)
        if len(hf) < n - k or len(syn) < k:
            raise SystemExit(f"not enough rows for {name}: need {n - k} HF + {k} synthetic; raise --max-rows")
        part = [inject_iban(r, fake, rng) if rng.random() < IBAN_RATE else r for r in hf[:n - k]] + syn[:k]
        hf, syn = hf[n - k:], syn[k:]
        rng.shuffle(part)
        out[name] = [to_example(r) for r in part]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locale", choices=["DE", "CH"], help="DE drops the Swiss rows")
    ap.add_argument("--max-rows", type=int, default=12000)
    ap.add_argument("--synthetic-share", type=float, default=0.4,
                    help="fraction of every split made of synthetic broker-style messages (0 disables)")
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    need = round(sum(SPLITS.values()) * a.synthetic_share) + 200  # spare for dedupe
    splits = build(load_german(a.locale, a.max_rows), synth.generate(need), a.synthetic_share)
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    for name, rows in splits.items():
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        c = Counter(e["label"] for r in rows for e in r["entities"])
        n_syn = sum(r["source"] == "synthetic" for r in rows)
        print(f"{name}: {len(rows)} rows ({n_syn} synthetic)\n  " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))


if __name__ == "__main__":
    main()
