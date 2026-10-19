"""Optional baseline: naeyn/nobody-pii-de (GLiNER, German). Install: uv sync --extra gliner.

Direct predict_entities covers only person / address / date of birth / organization (no emails, phones,
IBANs...), so expect high leak rates on structured classes. Writes the same preds file as every system:
  uv run python -m pii.gliner_baseline && make eval SYSTEM=gliner
"""
import argparse
import json
import time
from pathlib import Path

THRESHOLDS = {"person": 0.5, "address": 0.05, "date of birth": 0.5}  # model card values
# "address" spans mask street+number+zip+city together, so they are labelled STREET (masking is what the leak check sees).
LABEL = {"address": "STREET", "date of birth": "DATEOFBIRTH"}


def extract(model, text: str) -> list[dict]:
    out = []
    for lab, thr in THRESHOLDS.items():
        for e in model.predict_entities(text, [lab], threshold=thr):
            if lab == "person":
                out += [{"text": p, "label": "GIVENNAME" if i == 0 else "SURNAME"}
                        for i, p in enumerate(e["text"].split())]
            else:
                out.append({"text": e["text"], "label": LABEL[lab]})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split", default="test")
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args()
    from gliner import GLiNER
    model = GLiNER.from_pretrained("naeyn/nobody-pii-de")
    rows = [json.loads(l) for l in Path(f"data/{a.split}.jsonl").open()][:a.n]
    Path("results").mkdir(exist_ok=True)
    with open(f"results/preds_gliner_{a.split}.jsonl", "w") as f:
        for r in rows:
            t0 = time.perf_counter()
            ents = extract(model, r["text"])
            f.write(json.dumps({"uid": r["uid"], "entities": ents, "latency_s": time.perf_counter() - t0,
                                "tokens_in": 0, "tokens_out": 0, "trace_id": None, "error": None},
                               ensure_ascii=False) + "\n")
    print(f"-> results/preds_gliner_{a.split}.jsonl")


if __name__ == "__main__":
    main()
