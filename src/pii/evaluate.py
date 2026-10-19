"""Score a system's predictions: leak rate, per-class P/R, tiered recall, latency, cost. Pushes scores to Langfuse."""
import argparse
import json
import math
import os
import re
import statistics
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from .redact import PLACEHOLDER, mask  # noqa: E402
from .schema import CRITICAL, HIGH, LABELS, NUMERIC  # noqa: E402


def norm(label: str, value: str) -> str:
    """Comparison key: digits only for numeric classes, else casefolded with collapsed whitespace."""
    if label in NUMERIC:
        d = re.sub(r"\D", "", value)
        if len(d) >= 4:
            return d
    return " ".join(value.casefold().split())


def leaked(label: str, value: str, masked: str) -> bool:
    """True if the gold value is still readable in the masked text."""
    visible = PLACEHOLDER.sub("\x00", masked)  # placeholder digits must not count as PII
    key = norm(label, value)
    if label in NUMERIC and key.isdigit():
        return re.search(r"\D*".join(key), visible) is not None
    return key in " ".join(visible.casefold().split())


def upper95(k: int, n: int) -> float:
    """95% upper bound on a rate: rule of three at 0, Wilson otherwise."""
    if n == 0:
        return float("nan")
    if k == 0:
        return min(1.0, 3 / n)
    z, p = 1.96, k / n
    return (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


TIERS = (("critical", CRITICAL), ("high", HIGH))


def score_row(g: dict, p: dict):
    """Return (gold keys -> entity, predicted keys, leaked gold keys) for one message."""
    masked, _ = mask(g["text"], p["entities"])
    gold = {(e["label"], norm(e["label"], e["text"])): e for e in g["entities"]}
    pred = {(e["label"], norm(e["label"], e["text"])) for e in p["entities"]}
    return gold, pred, {k for k, e in gold.items() if leaked(e["label"], e["text"], masked)}


def evaluate(gold_rows: list[dict], preds: dict[int, dict]):
    leak_msgs, per_label, tier, rows_out = [], Counter(), Counter(), []
    for g in gold_rows:
        if g["uid"] not in preds:
            continue
        p = preds[g["uid"]]
        gold, pred, leaks = score_row(g, p)
        leak_msgs.append(bool(leaks))
        for k in gold:
            per_label[k[0], "gold"] += 1
            per_label[k[0], "tp"] += k in pred
        for k in pred:
            per_label[k[0], "pred"] += 1
        for name, labels in TIERS:
            ks = [k for k in gold if k[0] in labels]
            tier[name, "gold"] += len(ks)
            tier[name, "tp"] += sum(k in pred for k in ks)
            tier[name, "leaked"] += sum(k in leaks for k in ks)
        rows_out.append({"trace_id": p.get("trace_id"), "leaked": len(leaks), "n_gold": len(gold)})
    return leak_msgs, per_label, tier, rows_out


def cost_per_1k(preds: list[dict]) -> str:
    pin, pout = os.getenv("TEACHER_PRICE_IN_PER_M"), os.getenv("TEACHER_PRICE_OUT_PER_M")
    if not (pin and pout):
        return "n/a (local = $0; for cloud set TEACHER_PRICE_IN_PER_M / TEACHER_PRICE_OUT_PER_M, USD per 1M tokens)"
    usd = sum(p["tokens_in"] * float(pin) + p["tokens_out"] * float(pout) for p in preds) / 1e6
    return f"${usd / len(preds) * 1000:.2f}"


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "n/a"


def report(system: str, split: str, gold_rows, preds: dict) -> str:
    leak_msgs, per_label, tier, _ = evaluate(gold_rows, preds)
    n, k = len(leak_msgs), sum(leak_msgs)
    pl = [p for p in preds.values()]
    lat = sorted(p["latency_s"] for p in pl)
    errs = sum(bool(p.get("error")) for p in pl)
    lines = [f"# {system} on {split} (n={n})", "",
             f"- **Message leak rate:** {pct(k, n)} ({k}/{n}); 95% upper bound {100 * upper95(k, n):.1f}%",
             f"- Critical recall: {pct(tier['critical', 'tp'], tier['critical', 'gold'])}"
             f" (leaked values: {tier['critical', 'leaked']}/{tier['critical', 'gold']})",
             f"- High recall: {pct(tier['high', 'tp'], tier['high', 'gold'])}"
             f" (leaked values: {tier['high', 'leaked']}/{tier['high', 'gold']})",
             f"- Latency: median {statistics.median(lat):.2f}s, p95 {lat[int(0.95 * (len(lat) - 1))]:.2f}s",
             f"- Cost per 1k messages: {cost_per_1k(pl)}",
             f"- Failed calls: {errs}", "",
             "| Label | Gold | Pred | Recall | Precision |", "|---|---|---|---|---|"]
    for lab in LABELS:
        g, p_, tp = per_label[lab, "gold"], per_label[lab, "pred"], per_label[lab, "tp"]
        if g or p_:
            lines.append(f"| {lab} | {g} | {p_} | {pct(tp, g)} | {pct(tp, p_)} |")
    return "\n".join(lines) + "\n"


def push_scores(system: str, rows_out: list[dict]):
    from langfuse import get_client
    lf = get_client()
    for r in rows_out:
        if not r["trace_id"]:
            continue
        lf.create_score(trace_id=r["trace_id"], name="pii_leak", value=float(r["leaked"] > 0),
                        data_type="NUMERIC", comment=f"{r['leaked']}/{r['n_gold']} gold values leaked")
        lf.create_score(trace_id=r["trace_id"], name="pii_leaked_values", value=float(r["leaked"]),
                        data_type="NUMERIC")
    lf.flush()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--system", default="teacher", help="teacher | student | presidio")
    ap.add_argument("--split", default="test")
    ap.add_argument("--data", default="data")
    ap.add_argument("--no-push", action="store_true", help="skip pushing scores to Langfuse")
    a = ap.parse_args()
    gold_path = Path(a.data) / f"{a.split}.jsonl"
    clean = Path(a.data) / "test_clean.jsonl"
    if a.split == "test" and clean.exists():
        gold_path = clean
        print("using hand-reviewed", clean)
    gold = [json.loads(l) for l in gold_path.open()]
    preds = {}
    for l in Path(f"results/preds_{a.system}_{a.split}.jsonl").open():
        r = json.loads(l)
        preds[r["uid"]] = r
    md = report(a.system, a.split, gold, preds)
    Path("results").mkdir(exist_ok=True)
    out = Path(f"results/eval_{a.system}_{a.split}.md")
    out.write_text(md)
    print(md)
    if not a.no_push:
        push_scores(a.system, evaluate(gold, preds)[3])
        print("scores pushed to Langfuse")


if __name__ == "__main__":
    main()
