"""Download the German slice of ai4privacy/pii-masking-400k, inject IBANs, write splits."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from faker import Faker

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
    return {"uid": row["uid"], "locale": row["locale"], "text": row["source_text"],
            "entities": ents, "privacy_mask": row["privacy_mask"]}


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


def build(rows, seed: int = 0):
    """Dedupe, inject IBANs, split. Pure function: easy to test."""
    rng, fake = random.Random(seed), Faker("de_DE")
    Faker.seed(seed)
    seen, uniq = set(), []
    for r in rows:
        if r["source_text"] in seen:
            continue
        seen.add(r["source_text"])
        uniq.append(r)
    rng.shuffle(uniq)
    need = sum(SPLITS.values())
    if len(uniq) < need:
        raise SystemExit(f"only {len(uniq)} unique rows, need {need}; raise --max-rows")
    uniq = [inject_iban(r, fake, rng) if rng.random() < IBAN_RATE else r for r in uniq[:need]]
    out, i = {}, 0
    for name, n in SPLITS.items():
        out[name] = [to_example(r) for r in uniq[i:i + n]]
        i += n
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--locale", choices=["DE", "CH"], help="DE drops the Swiss rows")
    ap.add_argument("--max-rows", type=int, default=12000)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    splits = build(load_german(a.locale, a.max_rows))
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    for name, rows in splits.items():
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        c = Counter(e["label"] for r in rows for e in r["entities"])
        print(f"{name}: {len(rows)} rows\n  " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))


if __name__ == "__main__":
    main()
