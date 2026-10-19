"""Run the teacher or the student over a data split; every call is one Langfuse trace.

  uv run python -m pii.extract teacher --n 20 --split test   # -> results/preds_teacher_test.jsonl
"""
import argparse
import json
import os
import time
from pathlib import Path

from langfuse import get_client, propagate_attributes

from .llm import make_chat
from .schema import OUTPUT_SCHEMA, SYSTEM_PROMPT, parse_entities


def extract(role: str, text: str, model: str, chat, uid=None, split: str = "") -> dict:
    """Entities for one text, traced as span '<role>-redact' with a generation inside.

    Returns {entities, latency_s, tokens_in, tokens_out, trace_id, error}.
    """
    lf, version = get_client(), os.getenv(f"{role.upper()}_VERSION", "")
    tags = [role, f"model:{model}"] + ([f"version:{version}"] if version else [])
    with propagate_attributes(tags=tags, metadata={"uid": str(uid), "split": split, "model_version": version}):
        with lf.start_as_current_observation(as_type="span", name=f"{role}-redact", input=text) as root:
            res = {"entities": [], "latency_s": 0.0, "tokens_in": 0, "tokens_out": 0,
                   "trace_id": lf.get_current_trace_id(), "error": None}
            with lf.start_as_current_observation(as_type="generation", name="extract-entities",
                                                 model=model, input=text) as gen:
                t0 = time.perf_counter()
                raw = ""
                try:
                    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]
                    raw, res["tokens_in"], res["tokens_out"] = chat(messages, OUTPUT_SCHEMA)
                    res["entities"] = parse_entities(raw)
                except Exception as e:  # keep the run going; the eval counts this row as all-leak
                    res["error"] = f"{type(e).__name__}: {e}"[:300]
                    gen.update(level="ERROR", status_message=res["error"])
                res["latency_s"] = time.perf_counter() - t0
                gen.update(output=raw, usage_details={"input": res["tokens_in"], "output": res["tokens_out"]})
            root.update(output={"entities": res["entities"]})
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("role", choices=["teacher", "student"])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--split", default="test", choices=["test", "seed", "pool"])
    ap.add_argument("--yes", action="store_true", help="allow more than 50 calls (paid APIs cost money)")
    a = ap.parse_args()
    if a.n > 50 and not a.yes:
        raise SystemExit(f"{a.n} calls may cost money; rerun with --yes (make ... YES=1) if intended.")
    model, chat = make_chat(a.role.upper())
    rows = [json.loads(line) for line in Path(f"data/{a.split}.jsonl").open()][:a.n]
    out = Path(f"results/preds_{a.role}_{a.split}.jsonl")
    out.parent.mkdir(exist_ok=True)
    with out.open("w") as f:
        for r in rows:
            res = extract(a.role, r["text"], model, chat, uid=r["uid"], split=a.split)
            f.write(json.dumps({"uid": r["uid"], "model": model, **res}, ensure_ascii=False) + "\n")
    get_client().flush()  # short-lived script: send traces before exit
    print(f"{len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
