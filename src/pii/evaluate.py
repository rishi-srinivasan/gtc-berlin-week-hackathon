"""Score a system's predictions: leak rate, per-class P/R, tiered recall, latency, cost. Pushes scores to Langfuse."""
import argparse
import math
import os
import re
import statistics
from collections import Counter
from pathlib import Path

from .data import load_gold, read_jsonl
from .redact import PLACEHOLDER, mask
from .schema import CRITICAL, HIGH, LABELS, NUMERIC


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
        return re.search(r"(?<!\d)" + r"\D*".join(key) + r"(?!\d)", visible) is not None
    return re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", " ".join(visible.casefold().split())) is not None


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
        rows_out.append({"trace_id": p.get("trace_id"), "leaked": len(leaks), "n_gold": len(gold),
                         "source": g.get("source", "hf")})
    return leak_msgs, per_label, tier, rows_out


def cost_per_1k(system: str, preds: list[dict]) -> str:
    """Token cost for API-priced systems; set <SYSTEM>_PRICE_IN_PER_M / _OUT_PER_M (USD per 1M tokens) in .env."""
    pin, pout = os.getenv(f"{system.upper()}_PRICE_IN_PER_M"), os.getenv(f"{system.upper()}_PRICE_OUT_PER_M")
    if not (pin and pout):
        return f"n/a (set {system.upper()}_PRICE_IN_PER_M / _OUT_PER_M; self-hosted = GPU time)"
    usd = sum(p["tokens_in"] * float(pin) + p["tokens_out"] * float(pout) for p in preds) / 1e6
    return f"${usd / len(preds) * 1000:.2f}"


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "n/a"


def by_source(rows_out: list[dict]) -> str:
    """Message leak rate per data source (hf vs synthetic)."""
    parts = []
    for src in sorted({r["source"] for r in rows_out}):
        rs = [r for r in rows_out if r["source"] == src]
        parts.append(f"{src} {pct(sum(r['leaked'] > 0 for r in rs), len(rs))} (n={len(rs)})")
    return ", ".join(parts)


def report(system: str, split: str, result, preds: dict) -> str:
    leak_msgs, per_label, tier, rows_out = result
    n, k = len(leak_msgs), sum(leak_msgs)
    pl = list(preds.values())
    lat = sorted(p["latency_s"] for p in pl)
    lines = [f"# {system} on {split} (n={n})", "",
             f"- **Message leak rate:** {pct(k, n)} ({k}/{n}); 95% upper bound {100 * upper95(k, n):.1f}%",
             f"- Leak rate by source: {by_source(rows_out)}"]
    lines += [f"- {name.capitalize()} recall: {pct(tier[name, 'tp'], tier[name, 'gold'])}"
              f" (leaked values: {tier[name, 'leaked']}/{tier[name, 'gold']})" for name, _ in TIERS]
    lines += [f"- Latency: median {statistics.median(lat):.2f}s, p95 {lat[int(0.95 * (len(lat) - 1))]:.2f}s",
              f"- Cost per 1k messages: {cost_per_1k(system, pl)}",
              f"- Failed calls: {sum(bool(p.get('error')) for p in pl)}", "",
              "| Label | Gold | Pred | Recall | Precision |", "|---|---|---|---|---|"]
    lines += [f"| {lab} | {g} | {p_} | {pct(tp, g)} | {pct(tp, p_)} |" for lab in LABELS
              for g, p_, tp in [(per_label[lab, "gold"], per_label[lab, "pred"], per_label[lab, "tp"])] if g or p_]
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
    ap.add_argument("--system", default="teacher", help="any results/preds_<system>_<split>.jsonl: teacher, student, gliner")
    ap.add_argument("--split", default="test")
    ap.add_argument("--no-push", action="store_true", help="skip pushing scores to Langfuse")
    a = ap.parse_args()
    preds = {r["uid"]: r for r in read_jsonl(f"results/preds_{a.system}_{a.split}.jsonl")}
    result = evaluate(load_gold(a.split), preds)
    md = report(a.system, a.split, result, preds)
    Path(f"results/eval_{a.system}_{a.split}.md").write_text(md)
    print(md)
    if not a.no_push:
        push_scores(a.system, result[3])
        print("scores pushed to Langfuse")


if __name__ == "__main__":
    main()
