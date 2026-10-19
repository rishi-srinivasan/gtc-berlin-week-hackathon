"""Synthetic broker/bank support messages with PII (German), labelled by construction.

Adds the classes the Hugging Face dataset lacks: PORTFOLIOID, IPADDRESS, AGE, SALARY (and IBAN in
realistic context). Also emits ISINs, which are NOT personal data, as negatives.
All values are fake (Faker de_DE); the Steuer-ID is checksum-valid, IBAN/card pass their checks.
"""
import random
import re

from faker import Faker

ISINS = ["US0378331005", "IE00B4L5Y983", "DE0007164600", "IE00BK5BQT80", "DE000BAY0017"]

GREETINGS = ["Guten Tag,", "Hallo liebes Support-Team,", "Sehr geehrte Damen und Herren,", "Hi,", "Hallo,"]
INTROS = [
    "mein Name ist {GIVENNAME} {SURNAME}.",
    "ich bin {GIVENNAME} {SURNAME}, {AGE} Jahre alt.",
    "hier schreibt {GIVENNAME} {SURNAME} (Depotnummer {PORTFOLIOID}).",
    "{SURNAME}, {GIVENNAME}, Depot {PORTFOLIOID}.",
]
BODIES = [
    "Bitte zahlen Sie den Erlös meines Verkaufs auf {IBAN} aus.",
    "Meine Steuer-ID lautet {TAXNUM}, bitte aktualisieren Sie den Freistellungsauftrag.",
    "Meine Karte {CREDITCARDNUMBER} wurde nicht akzeptiert, bitte sperren und neu ausstellen.",
    "Ich bin umgezogen: neue Adresse {STREET} {BUILDINGNUM}, {ZIPCODE} {CITY}.",
    "Sie erreichen mich unter {TELEPHONENUM} oder per Mail an {EMAIL}.",
    "Beim Login von {IPADDRESS} wurde mein Zugang gesperrt.",
    "Mein Jahreseinkommen beträgt {SALARY}, bitte passen Sie mein Anlegerprofil an.",
    "Ich möchte den ETF {ISIN} monatlich besparen und dafür von {IBAN} abbuchen lassen.",
    "Die Order für {ISIN} wurde nicht ausgeführt, mein Depot ist {PORTFOLIOID}.",
    "Für die Kontoeröffnung brauche ich eine Bestätigung an {EMAIL}, Wohnort {ZIPCODE} {CITY}.",
    "Der Anruf kam von {TELEPHONENUM}, bitte rufen Sie mich zurück wegen Depot {PORTFOLIOID}.",
]
NO_PII = ["Wie hoch sind die Gebühren für den ETF {ISIN}?", "Wann wird die Sparplan-Ausführung gebucht?",
          "Gibt es eine App für Android und iOS?"]
CLOSINGS = ["Vielen Dank!", "Mit freundlichen Grüßen, {GIVENNAME} {SURNAME}", "Danke und Gruß", "Bitte um schnelle Hilfe."]

SLOT = re.compile(r"\{([A-Z]+)\}")


def _check_digit(d: list[int]) -> int:
    """ISO 7064 mod 11,10 check digit of the first 10 Steuer-ID digits."""
    product = 10
    for x in d:
        product = (2 * ((x + product) % 10 or 10)) % 11
    return (11 - product) % 10


def steuer_id(rng: random.Random) -> str:
    """11-digit German tax ID: one digit repeated 2-3 times in the first 10, never 3 in a row, valid check digit."""
    while True:
        d = [rng.randint(1 if i == 0 else 0, 9) for i in range(10)]
        counts = sorted((d.count(x) for x in set(d)), reverse=True)
        if counts[0] in (2, 3) and counts[1] == 1 and not any(d[i] == d[i + 1] == d[i + 2] for i in range(8)):
            return "".join(map(str, d)) + str(_check_digit(d))


def steuer_id_valid(s: str) -> bool:
    return len(s) == 11 and s.isdigit() and s[0] != "0" and _check_digit(list(map(int, s[:10]))) == int(s[10])


def values(fake: Faker, rng: random.Random) -> dict:
    """One fresh fake value per label (cached per message so repeated slots stay identical)."""
    group = lambda s: " ".join(s[i:i + 4] for i in range(0, len(s), 4))  # noqa: E731
    amount = rng.choice([rng.randint(18, 95) * 1000, rng.randint(150, 900) * 10 * 12, rng.randint(18, 60) * 100])
    iban, card = fake.iban(), fake.credit_card_number()
    return {
        "GIVENNAME": fake.first_name(), "SURNAME": fake.last_name(),
        "PORTFOLIOID": str(rng.randint(10**9, 10**10 - 1)),
        "IBAN": group(iban) if rng.random() < 0.6 else iban,
        "TAXNUM": steuer_id(rng),
        "CREDITCARDNUMBER": group(card) if rng.random() < 0.6 else card,
        "STREET": fake.street_name(), "BUILDINGNUM": str(fake.building_number()),
        "ZIPCODE": fake.postcode(), "CITY": fake.city(),
        "TELEPHONENUM": fake.phone_number(), "EMAIL": fake.ascii_email(),
        "IPADDRESS": fake.ipv6() if rng.random() < 0.15 else fake.ipv4_public(),
        "AGE": str(rng.randint(18, 85)),
        "SALARY": f"{amount:,}".replace(",", ".") + rng.choice([" €", " Euro", " EUR"]),
        "ISIN": rng.choice(ISINS),  # not PII: stays unlabelled
    }


def render(template: str, vals: dict) -> tuple[str, list[dict]]:
    out, spans, pos = [], [], 0
    for m in SLOT.finditer(template):
        out.append(template[pos:m.start()])
        start = sum(map(len, out))
        label, v = m.group(1), vals[m.group(1)]
        out.append(v)
        if label != "ISIN":
            spans.append({"label": label, "start": start, "end": start + len(v), "value": v})
        pos = m.end()
    out.append(template[pos:])
    return "".join(out), spans


def make_row(uid: int, fake: Faker, rng: random.Random) -> dict:
    parts = [rng.choice(GREETINGS)]
    if rng.random() < 0.08:  # a few messages without any PII
        parts.append(rng.choice(NO_PII))
    else:
        parts.append(rng.choice(INTROS))
        parts += rng.sample(BODIES, rng.randint(1, 3))
        parts.append(rng.choice(CLOSINGS))
    # AGE/PORTFOLIOID may appear in the intro without a body; every slot is filled from vals regardless
    text, spans = render(" ".join(parts), values(fake, rng))
    return {"uid": uid, "locale": "DE", "source_text": text, "privacy_mask": spans, "source": "synthetic"}


def generate(n: int, seed: int = 0) -> list[dict]:
    rng, fake = random.Random(seed), Faker("de_DE")
    Faker.seed(seed)
    return [make_row(10_000_000 + i, fake, rng) for i in range(n)]
