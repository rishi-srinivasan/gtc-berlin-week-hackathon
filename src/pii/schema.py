"""Entity labels, tiers, and the JSON output schema shared by every system."""

DATASET_LABELS = [
    "ACCOUNTNUM", "BUILDINGNUM", "CITY", "CREDITCARDNUMBER", "DATEOFBIRTH",
    "DRIVERLICENSENUM", "EMAIL", "GIVENNAME", "IDCARDNUM", "PASSWORD",
    "SOCIALNUM", "STREET", "SURNAME", "TAXNUM", "TELEPHONENUM", "USERNAME",
    "ZIPCODE",
]
LABELS = DATASET_LABELS + ["IBAN"]  # the dataset has no IBAN class; data.py injects it

CRITICAL = {"IBAN", "ACCOUNTNUM", "CREDITCARDNUMBER", "IDCARDNUM", "TAXNUM",
            "SOCIALNUM", "PASSWORD", "DRIVERLICENSENUM"}
HIGH = {"GIVENNAME", "SURNAME", "USERNAME", "EMAIL", "TELEPHONENUM", "STREET"}

# Classes compared by digits only when checking for leaks.
NUMERIC = {"TELEPHONENUM", "IBAN", "CREDITCARDNUMBER", "ACCOUNTNUM", "IDCARDNUM",
           "TAXNUM", "SOCIALNUM", "DRIVERLICENSENUM"}

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
- Split names: first names are GIVENNAME, family names SURNAME (also for "Dr. Müller": only "Müller").
- German formats: phone numbers (+49 ..., 0171 ...), IBAN (DE.. with or without spaces),
  tax ID (TAXNUM), social insurance number (SOCIALNUM), street names WITHOUT the house number
  (house number = BUILDINGNUM), postcode = ZIPCODE, dates of birth = DATEOFBIRTH.
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
