"""Demo: redact German text with the student (or teacher), ask a frontier LLM, rehydrate the reply."""
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from .redact import mask, rehydrate  # noqa: E402


def frontier_reply(masked: str) -> str:
    """Ask the frontier LLM about the already-masked text (FRONTIER_PROVIDER: ollama|anthropic|openai)."""
    system = ("Antworte auf Deutsch, kurz. Platzhalter wie [GIVENNAME_1] stehen für geschützte Daten; "
              "übernimm sie unverändert in deine Antwort, wo du sie erwähnst.")
    provider = os.getenv("FRONTIER_PROVIDER", "ollama")
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": masked}]
    if provider == "ollama":
        from . import ollama
        return ollama.chat(os.getenv("FRONTIER_MODEL", "gemma4:12b"), msgs, schema=None)[0]
    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic().messages.create(
            model=os.getenv("FRONTIER_MODEL", "claude-sonnet-5-5"), max_tokens=500, system=system,
            messages=msgs[1:])
        return r.content[0].text
    if provider == "openai":
        import openai
        r = openai.OpenAI().chat.completions.create(model=os.getenv("FRONTIER_MODEL", "gpt-5-mini"), messages=msgs)
        return r.choices[0].message.content
    raise SystemExit(f"FRONTIER_PROVIDER must be ollama|anthropic|openai, got {provider!r}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text", help="German text containing PII")
    ap.add_argument("--teacher", action="store_true", help="redact with the teacher instead of the student")
    a = ap.parse_args()
    if a.teacher:
        from .teacher import redact_entities
    else:
        from .student_client import redact_entities
    res = redact_entities(a.text, split="demo")
    masked, mapping = mask(a.text, res["entities"])
    reply = frontier_reply(masked)
    print("1. REDACTED (sent to frontier LLM):\n  ", masked)
    print("2. FRONTIER REPLY (placeholders):\n  ", reply)
    print("3. REHYDRATED:\n  ", rehydrate(reply, mapping))
    from langfuse import get_client
    get_client().flush()


if __name__ == "__main__":
    main()
