"""Build the directory `distil dataset create --data` expects (question-answering, JSON output).

  uv run python scripts/distil_prep.py                  # seed.jsonl + test_clean.jsonl -> distil/
  uv run python scripts/distil_prep.py --from-langfuse  # train rows from teacher traces scored pii_leak=0
  uv run python scripts/distil_prep.py --traces FILE    # add distil-endpoint traces (langfuse format)

Formats follow the distil-cli skill (question-answering task, JSON answers). Nothing is submitted.
"""
import argparse
import json
import os
from itertools import islice
from pathlib import Path

from pii.data import load_gold, read_jsonl
from pii.schema import SYSTEM_PROMPT

CONFIG = """\
base:
  task: question-answering
  student_model_name: {student}
  teacher_model_name: {teacher}
  random_seed: 123
tuning:
  num_train_epochs: 4
  max_completion_length: 1024
synthgen:
  output_is_json: true
  train_generation_target: 5000
  mutators:
    - name: document_type
      description: kind of German text the PII appears in
      values:
        - "a short customer-support email or chat message"
        - "a form or onboarding record with labelled fields"
        - "a free-text paragraph that mentions PII in passing"
        - "a broker or bank support request (depot number, payout IBAN, tax exemption, card, login problem, income)"
        - "a text with no PII at all, so the answer is an empty entity list"
    - name: pii_mix
      description: which kinds of PII appear
      values:
        - "dominated by names and contact details"
        - "dominated by bank, tax, ID and payment numbers (IBAN, tax ID, credit card)"
        - "a mix of address parts (street, house number, postcode, city) and dates of birth"
trace_processing:
  observation_format: langfuse   # records of a distil inference endpoint (traces.jsonl)
"""

JOB = {
    "task_description": SYSTEM_PROMPT,
    "llm_as_a_judge_instructions": (
        "Output 'good' if the predicted JSON lists every PII value that the reference lists, with the "
        "same label, and invents no extra PII; otherwise output 'bad'. Ignore entity order and "
        "duplicates. Values must be copied exactly from the input text. Missing a value is worse "
        "than a wrong label."),
    "synthetic_data_generation_instructions": (
        "Generate German texts (customer support, forms, emails, chat) containing realistic but fake "
        "PII: German names, phone numbers, addresses, dates of birth, German IBANs (with and without "
        "spaces), tax IDs, social insurance numbers, credit cards, ID card and driving licence "
        "numbers, passwords and usernames, plus broker-specific data: depot/portfolio numbers, IP "
        "addresses, ages and salaries. Include ISINs/WKNs as non-PII distractors that must not be listed. Vary length and formatting. The answer is the JSON object "
        "described in the task, with values copied exactly from the text."),
}


def to_row(text: str, entities: list[dict]) -> dict:
    answer = json.dumps({"entities": entities}, ensure_ascii=False)
    return {"messages": [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]}


def unjson(x):
    try:
        return json.loads(x) if isinstance(x, str) else x
    except ValueError:
        return x


def clean_trace_ids(lf):
    """Trace ids of teacher calls scored pii_leak == 0, paging through Langfuse scores."""
    cursor = None
    while True:
        page = lf.api.scores.get_many(name="pii_leak", limit=100, cursor=cursor, fields="subject")
        yield from (s.subject.id for s in page.data if s.value == 0 and s.subject.kind == "trace")
        cursor = getattr(page.meta, "cursor", None)
        if not cursor:
            return


def teacher_row(lf, trace_id: str, allowed: set[str]) -> dict | None:
    obs = lf.api.observations.get_many(trace_id=trace_id, name="teacher-redact", fields="core,io", limit=1).data
    if not obs:
        return None
    text, out = unjson(obs[0].input), unjson(obs[0].output)  # v2 API returns io as raw JSON strings
    return to_row(text, out["entities"]) if text in allowed and isinstance(out, dict) else None


def langfuse_rows(pool: list[dict], blocked: set[str], limit: int) -> list[dict]:
    """Teacher outputs from Langfuse traces with pii_leak == 0, restricted to pool inputs (never test)."""
    from langfuse import get_client
    lf, allowed = get_client(), {r["text"] for r in pool} - blocked
    rows = (teacher_row(lf, tid, allowed) for tid in clean_trace_ids(lf))
    return list(islice((r for r in rows if r), limit))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-langfuse", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--traces", help="traces.jsonl downloaded from a distil inference endpoint")
    a = ap.parse_args()
    test = load_gold("test")
    if a.from_langfuse:
        train = langfuse_rows(read_jsonl("data/pool.jsonl"), {r["text"] for r in test}, a.limit)
    else:
        train = [to_row(r["text"], r["entities"]) for r in read_jsonl("data/seed.jsonl")]
    out = Path("distil")
    out.mkdir(exist_ok=True)
    (out / "config.yaml").write_text(CONFIG.format(student=os.getenv("DISTIL_STUDENT", "Qwen3-1.7B"),
                                                   teacher=os.getenv("DISTIL_TEACHER", "openai.gpt-oss-120b")))
    (out / "job_description.json").write_text(json.dumps(JOB, ensure_ascii=False, indent=2))
    for name, rows in (("train", train), ("test", [to_row(r["text"], r["entities"]) for r in test])):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    if a.traces:
        (out / "traces.jsonl").write_text(Path(a.traces).read_text())
    print(f"distil/: {len(train)} train, {len(test)} test rows. Nothing submitted; next: README step 4.")


if __name__ == "__main__":
    main()
