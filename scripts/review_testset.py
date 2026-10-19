"""Export the test set to CSV for hand review, then re-import the fixed CSV as data/test_clean.jsonl.

  uv run python scripts/review_testset.py export   # -> data/test_review.csv
  uv run python scripts/review_testset.py import   # data/test_review.csv -> data/test_clean.jsonl

In the CSV edit `gold_entities` (JSON list of {"text","label"}); every value must appear in `text`.
`predicted_entities` is filled from results/preds_teacher_test.jsonl when it exists.
"""
import csv
import json
import sys
from pathlib import Path

DATA = Path("data")
CSV = DATA / "test_review.csv"


def export():
    preds = {}
    p = Path("results/preds_teacher_test.jsonl")
    if p.exists():
        preds = {r["uid"]: r["entities"] for r in map(json.loads, p.open())}
    with CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, ["uid", "locale", "text", "gold_entities", "predicted_entities"])
        w.writeheader()
        for r in map(json.loads, (DATA / "test.jsonl").open()):
            w.writerow({"uid": r["uid"], "locale": r["locale"], "text": r["text"],
                        "gold_entities": json.dumps(r["entities"], ensure_ascii=False),
                        "predicted_entities": json.dumps(preds.get(r["uid"], []), ensure_ascii=False)})
    print("wrote", CSV)


def reimport():
    from pii.schema import LABELS
    rows = []
    with CSV.open(newline="") as f:
        for r in csv.DictReader(f):
            ents = json.loads(r["gold_entities"])
            for e in ents:
                assert e["label"] in LABELS, f"uid {r['uid']}: bad label {e['label']}"
                assert e["text"] in r["text"], f"uid {r['uid']}: {e['text']!r} not in text"
            rows.append({"uid": int(r["uid"]), "locale": r["locale"], "text": r["text"], "entities": ents})
    (DATA / "test_clean.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"wrote data/test_clean.jsonl ({len(rows)} rows)")


if __name__ == "__main__":
    {"export": export, "import": reimport}[sys.argv[1] if len(sys.argv) > 1 else ""]()
