"""Download the German slice of ai4privacy/pii-masking-400k, inject every label (random per-label rate), write splits."""
import argparse
import json
import random
from collections import Counter
from pathlib import Path

from faker import Faker

from . import synth
from .schema import HF_RENAME, LABELS

SPLITS = {"test": 300, "seed": 100, "pool": 2000}
# Per label, the share of rows that get one injected sentence is drawn from N(INJECT_MEAN, INJECT_SD).
INJECT_MEAN, INJECT_SD, INJECT_MIN = 0.05, 0.02, 0.01
PHRASINGS = {
    "IBAN": ["IBAN: {IBAN}", "Bitte überweisen Sie auf IBAN {IBAN}.", "Meine Bankverbindung: {IBAN}",
             "Konto (IBAN): {IBAN}", "Rückerstattung an {IBAN} bitte."],
    "ACCOUNT_NUM": ["Meine Kontonummer ist {ACCOUNT_NUM}.", "Konto-Nr. {ACCOUNT_NUM}"],
    "AGE": ["Ich bin {AGE} Jahre alt.", "Alter: {AGE} Jahre"],
    "BUILDING_NUM": ["Hausnummer: {BUILDING_NUM}", "Ich wohne im Haus Nr. {BUILDING_NUM}."],
    "CITY": ["Ich wohne in {CITY}.", "Wohnort: {CITY}"],
    "CREDIT_CARD_NUMBER": ["Meine Kreditkarte {CREDIT_CARD_NUMBER} wurde belastet.", "Kartennummer: {CREDIT_CARD_NUMBER}"],
    "DATE_OF_BIRTH": ["Geboren am {DATE_OF_BIRTH}.", "Geburtsdatum: {DATE_OF_BIRTH}"],
    "DRIVER_LICENSE_NUM": ["Führerschein-Nr. {DRIVER_LICENSE_NUM}", "Mein Führerschein hat die Nummer {DRIVER_LICENSE_NUM}."],
    "EMAIL": ["Schreiben Sie mir an {EMAIL}.", "E-Mail: {EMAIL}"],
    "GIVEN_NAME": ["Vorname: {GIVEN_NAME}", "Ich heiße {GIVEN_NAME}."],
    "ID_CARD_NUM": ["Personalausweis-Nr. {ID_CARD_NUM}", "Meine Ausweisnummer lautet {ID_CARD_NUM}."],
    "IP_ADDRESS": ["Zugriff von IP {IP_ADDRESS}.", "Meine IP-Adresse: {IP_ADDRESS}"],
    "PASSWORD": ["Mein Passwort lautet {PASSWORD}.", "PIN/Passwort: {PASSWORD}"],
    "PORTFOLIO_ID": ["Depotnummer {PORTFOLIO_ID}", "Betrifft Depot {PORTFOLIO_ID}."],
    "SALARY": ["Mein Gehalt beträgt {SALARY}.", "Jahreseinkommen: {SALARY}"],
    "SOCIAL_NUM": ["Sozialversicherungsnummer: {SOCIAL_NUM}", "Meine Rentenversicherungsnummer ist {SOCIAL_NUM}."],
    "STREET": ["Meine Straße ist die {STREET}.", "Straße: {STREET}"],
    "SURNAME": ["Nachname: {SURNAME}", "Mein Familienname ist {SURNAME}."],
    "TAX_NUM": ["Steuer-ID: {TAX_NUM}", "Meine Steuernummer lautet {TAX_NUM}."],
    "TELEPHONE_NUM": ["Rufen Sie mich an unter {TELEPHONE_NUM}.", "Tel.: {TELEPHONE_NUM}"],
    "USER_NAME": ["Mein Benutzername ist {USER_NAME}.", "Login: {USER_NAME}"],
    "ZIP_CODE": ["Postleitzahl: {ZIP_CODE}", "Ich wohne in {ZIP_CODE}."],
}
assert set(PHRASINGS) == set(LABELS)


def iban_valid(iban: str) -> bool:
    """ISO 13616 mod-97 check."""
    s = iban.replace(" ", "").upper()
    if len(s) < 15 or not s.isalnum():
        return False
    num = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(num) % 97 == 1


def label_rates(rng: random.Random) -> dict[str, float]:
    """Injection rate per label, normally distributed around INJECT_MEAN (clipped to [INJECT_MIN, 0.5])."""
    return {l: min(max(rng.gauss(INJECT_MEAN, INJECT_SD), INJECT_MIN), 0.5) for l in LABELS}


def inject(row: dict, label: str, vals: dict, rng: random.Random) -> dict:
    """Append a sentence carrying a fake `label` value (from synth.values) and add its span."""
    sentence, spans = synth.render(rng.choice(PHRASINGS[label]), vals)
    text = row["source_text"].rstrip() + " "
    mask = row["privacy_mask"] + [{**s, "start": s["start"] + len(text), "end": s["end"] + len(text)}
                                  for s in spans]
    return {**row, "source_text": text + sentence, "privacy_mask": mask}


def inject_labels(row: dict, rates: dict, fake: Faker, rng: random.Random) -> dict:
    """Each label independently joins the row with its own rate."""
    chosen = [l for l in LABELS if rng.random() < rates[l]]
    if not chosen:
        return row
    vals = synth.values(fake, rng)
    rng.shuffle(chosen)
    for l in chosen:
        row = inject(row, l, vals, rng)
    return row


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
        yield {**r, "privacy_mask": [{**m, "label": HF_RENAME.get(m["label"], m["label"])}
                                     for m in r["privacy_mask"]]}
        n += 1
        if n >= max_rows:
            return


def dedupe(rows):
    seen = set()
    return [r for r in rows if not (r["source_text"] in seen or seen.add(r["source_text"]))]


def build(rows, synth=(), share: float = 0.0, seed: int = 0):
    """Dedupe, inject label sentences into HF rows, mix in `share` synthetic rows per split, split. Pure: easy to test."""
    rng, fake = random.Random(seed), Faker("de_DE")
    Faker.seed(seed)
    rates = label_rates(rng)
    hf, syn = dedupe(rows), dedupe(synth)
    rng.shuffle(hf)
    rng.shuffle(syn)
    out = {}
    for name, n in SPLITS.items():
        k = round(share * n)
        if len(hf) < n - k or len(syn) < k:
            raise SystemExit(f"not enough rows for {name}: need {n - k} HF + {k} synthetic; raise --max-rows")
        part = [inject_labels(r, rates, fake, rng) for r in hf[:n - k]] + syn[:k]
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
