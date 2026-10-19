"""Demo: redact German text with the student (or teacher), ask the frontier LLM, rehydrate the reply.

  uv run python -m pii.gateway "Hallo, ich bin Anna Berg, IBAN DE89 3704 0044 0532 0130 00" [--teacher]
"""
import argparse

from langfuse import get_client

from .extract import extract
from .llm import make_chat
from .redact import mask, rehydrate

FRONTIER_PROMPT = ("Antworte auf Deutsch, kurz. Platzhalter wie [GIVENNAME_1] stehen für geschützte Daten; "
                   "übernimm sie unverändert in deine Antwort, wo du sie erwähnst.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text", help="German text containing PII")
    ap.add_argument("--teacher", action="store_true", help="redact with the teacher instead of the student")
    a = ap.parse_args()
    role = "teacher" if a.teacher else "student"
    res = extract(role, a.text, *make_chat(role.upper()), split="demo")
    masked, mapping = mask(a.text, res["entities"])
    reply, _, _ = make_chat("FRONTIER")[1]([{"role": "system", "content": FRONTIER_PROMPT},
                                            {"role": "user", "content": masked}])
    get_client().flush()
    print("1. REDACTED (all the frontier LLM sees):\n  ", masked)
    print("2. FRONTIER REPLY:\n  ", reply)
    print("3. REHYDRATED:\n  ", rehydrate(reply, mapping))


if __name__ == "__main__":
    main()
