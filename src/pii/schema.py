"""Entity labels, tiers, and the JSON output schema shared by every system."""

DATASET_LABELS = [
    "ACCOUNT_NUM", "BUILDING_NUM", "CITY", "CREDIT_CARD_NUMBER", "DATE_OF_BIRTH",
    "DRIVER_LICENSE_NUM", "EMAIL", "GIVEN_NAME", "ID_CARD_NUM", "PASSWORD",
    "SOCIAL_NUM", "STREET", "SURNAME", "TAX_NUM", "TELEPHONE_NUM", "USER_NAME",
    "ZIP_CODE",
]
# Not in the dataset: IBAN is injected by data.py; the rest come from synth.py (broker-style messages).
EXTRA_LABELS = ["IBAN", "PORTFOLIO_ID", "IP_ADDRESS", "AGE", "SALARY"]
LABELS = DATASET_LABELS + EXTRA_LABELS
# The Hugging Face dataset spells these without underscores (ACCOUNTNUM); data.py renames on load.
HF_RENAME = {l.replace("_", ""): l for l in DATASET_LABELS if "_" in l}

CRITICAL = {"IBAN", "PORTFOLIO_ID", "ACCOUNT_NUM", "CREDIT_CARD_NUMBER", "ID_CARD_NUM", "TAX_NUM",
            "SOCIAL_NUM", "PASSWORD", "DRIVER_LICENSE_NUM"}
HIGH = {"GIVEN_NAME", "SURNAME", "USER_NAME", "EMAIL", "TELEPHONE_NUM", "STREET", "IP_ADDRESS", "SALARY"}

# Classes compared by digits only when checking for leaks.
NUMERIC = {"TELEPHONE_NUM", "IBAN", "CREDIT_CARD_NUMBER", "ACCOUNT_NUM", "ID_CARD_NUM",
           "TAX_NUM", "SOCIAL_NUM", "DRIVER_LICENSE_NUM", "PORTFOLIO_ID"}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "label": {"type": "string", "enum": LABELS},
                },
                "required": ["text", "label"],
            },
        }
    },
    "required": ["entities"],
}


SYSTEM_PROMPT = f"""You find personal data (PII) in German text so it can be redacted.
Return ONLY a JSON object: {{"entities": [{{"text": "...", "label": "..."}}]}}

Rules:
- "text" must be copied EXACTLY (character for character) from the input.
- List every occurrence's value once is enough; do not invent or normalise values.
- Split names: first names are GIVEN_NAME, family names SURNAME (also for "Dr. Müller": only "Müller").
- German formats: phone numbers (+49 ..., 0171 ...), IBAN (DE.. with or without spaces),
  tax ID (TAX_NUM), social insurance number (SOCIAL_NUM), street names WITHOUT the house number
  (house number = BUILDING_NUM), postcode = ZIP_CODE, dates of birth = DATE_OF_BIRTH.
- Broker/bank texts: depot or portfolio numbers = PORTFOLIO_ID; IPv4/IPv6 addresses = IP_ADDRESS;
  age = AGE (only the number, e.g. "42" in "42 Jahre alt"); salary or income = SALARY (the amount with its currency).
- Other identifiers: PIN = PASSWORD; passport and IMEI numbers = ID_CARD_NUM; MAC address = IP_ADDRESS; crypto wallet address = ACCOUNT_NUM.
- ISIN, WKN, ticker symbols and product names are NOT personal data: never list them.
- Do not label generic words, company names, countries or dates that are not a birth date.
- If there is no PII return {{"entities": []}}.

Allowed labels: {", ".join(LABELS)}"""


def parse_entities(raw: str) -> list[dict]:
    """Pull the entity list out of a model reply; drop malformed items and unknown labels."""
    import json
    start, end = raw.find("{"), raw.rfind("}")
    try:
        items = json.loads(raw[start:end + 1])["entities"]
    except (ValueError, KeyError, TypeError):
        return []
    return [{"text": e["text"], "label": e["label"]} for e in items
            if isinstance(e, dict) and isinstance(e.get("text"), str) and e.get("label") in LABELS]
