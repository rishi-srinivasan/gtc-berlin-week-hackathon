"""One traced entity-extraction call: root span + generation, shared by teacher and student."""
import time

from dotenv import load_dotenv

load_dotenv()  # before langfuse import so credentials are picked up

from langfuse import get_client, propagate_attributes  # noqa: E402

from .schema import parse_entities  # noqa: E402


def traced_extract(system: str, text: str, call, *, model: str, tags: list[str],
                   uid=None, split: str = "", version: str = "") -> dict:
    """Run call(text) -> (raw_reply, tokens_in, tokens_out) inside a Langfuse trace.

    Returns {entities, latency_s, tokens_in, tokens_out, trace_id, error}.
    """
    lf = get_client()
    meta = {"uid": str(uid), "split": split, "system": system, "model_version": version}
    with propagate_attributes(tags=tags, metadata=meta):
        with lf.start_as_current_observation(as_type="span", name=f"{system}-redact", input=text) as root:
            res = {"entities": [], "latency_s": 0.0, "tokens_in": 0, "tokens_out": 0,
                   "trace_id": lf.get_current_trace_id(), "error": None}
            with lf.start_as_current_observation(as_type="generation", name="extract-entities",
                                                 model=model, input=text) as gen:
                t0 = time.perf_counter()
                try:
                    raw, res["tokens_in"], res["tokens_out"] = call(text)
                    res["entities"] = parse_entities(raw)
                except Exception as e:  # keep the run going; the eval counts this row as all-leak
                    raw, res["error"] = "", f"{type(e).__name__}: {e}"[:300]
                    gen.update(level="ERROR", status_message=res["error"])
                res["latency_s"] = time.perf_counter() - t0
                gen.update(output=raw, usage_details={"input": res["tokens_in"], "output": res["tokens_out"]})
            root.update(output={"entities": res["entities"]})
    return res


def run_batch(system: str, call, *, model: str, tags: list[str], version: str = "",
              split: str = "test", n: int = 20, data: str = "data") -> str:
    """Extract entities for the first n rows of a split; write results/preds_<system>_<split>.jsonl."""
    import json
    from pathlib import Path
    rows = [json.loads(l) for l in (Path(data) / f"{split}.jsonl").open()][:n]
    out = Path("results") / f"preds_{system}_{split}.jsonl"
    out.parent.mkdir(exist_ok=True)
    with out.open("w") as f:
        for r in rows:
            res = traced_extract(system, r["text"], call, model=model, tags=tags,
                                 uid=r["uid"], split=split, version=version)
            f.write(json.dumps({"uid": r["uid"], "model": model, **res}, ensure_ascii=False) + "\n")
    get_client().flush()  # short-lived script: send traces before exit
    return str(out)


def batch_args(description: str):
    import argparse
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--split", default="test", choices=["test", "seed", "pool"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--yes", action="store_true", help="allow more than 50 LLM calls")
    a = ap.parse_args()
    if a.n > 50 and not a.yes:
        raise SystemExit(f"{a.n} LLM calls costs money; rerun with --yes if intended.")
    return a
