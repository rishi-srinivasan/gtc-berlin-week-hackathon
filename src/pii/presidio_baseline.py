"""Optional rule/NER baseline (Microsoft Presidio + spaCy German). Install: uv sync --extra presidio
then: uv run python -m spacy download de_core_news_md"""
import time


# Presidio entity -> our label. PERSON is split into given name + surname below.
MAP = {"EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "TELEPHONENUM", "IBAN_CODE": "IBAN",
       "CREDIT_CARD": "CREDITCARDNUMBER", "LOCATION": "CITY", "DATE_TIME": "DATEOFBIRTH"}


def make_analyzer():
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "de", "model_name": "de_core_news_md"}]}).create_engine()
    return AnalyzerEngine(nlp_engine=nlp, supported_languages=["de"])


def extract(analyzer, text: str) -> list[dict]:
    out = []
    for r in analyzer.analyze(text=text, language="de"):
        value = text[r.start:r.end]
        if r.entity_type == "PERSON":
            parts = value.split()
            out += [{"text": p, "label": "GIVENNAME" if i == 0 else "SURNAME"} for i, p in enumerate(parts)]
        elif r.entity_type in MAP:
            out.append({"text": value, "label": MAP[r.entity_type]})
    return out


if __name__ == "__main__":
    import json
    from pathlib import Path
    analyzer = make_analyzer()
    rows = [json.loads(l) for l in Path("data/test.jsonl").open()]
    Path("results").mkdir(exist_ok=True)
    with open("results/preds_presidio_test.jsonl", "w") as f:
        for r in rows:
            t0 = time.perf_counter()
            ents = extract(analyzer, r["text"])
            f.write(json.dumps({"uid": r["uid"], "entities": ents, "latency_s": time.perf_counter() - t0,
                                "tokens_in": 0, "tokens_out": 0, "trace_id": None, "error": None}) + "\n")
    print("-> results/preds_presidio_test.jsonl")
