"""Build the directory `distil dataset create --data` expects (question-answering, JSON output).

  uv run python scripts/distil_prep.py                  # seed.jsonl + test_clean.jsonl -> distil/
  uv run python scripts/distil_prep.py --from-langfuse  # train rows from teacher traces scored pii_leak=0

Formats follow distil-cli-skill references (data-preparation/question-answering.md, job-description.md,
configuration.md). Nothing is submitted; the commands to run are printed at the end.
"""
import argparse
import json
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from pii.schema import SYSTEM_PROMPT  # noqa: E402

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
        - "a text with no PII at all, so the answer is an empty entity list"
    - name: pii_mix
      description: which kinds of PII appear
      values:
        - "dominated by names and contact details"
        - "dominated by bank, tax, ID and payment numbers (IBAN, tax ID, credit card)"
        - "a mix of address parts (street, house number, postcode, city) and dates of birth"
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
        "numbers, passwords and usernames. Vary length and formatting. The answer is the JSON object "
        "described in the task, with values copied exactly from the text."),
}


def to_row(text: str, entities: list[dict]) -> dict:
    answer = json.dumps({"entities": entities}, ensure_ascii=False)
    return {"messages": [{"role": "user", "content": text}, {"role": "assistant", "content": answer}]}


def read(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.open()]


def unjson(x):
    try:
        return json.loads(x) if isinstance(x, str) else x
    except ValueError:
        return x


def langfuse_rows(pool: list[dict], blocked: set[str], limit: int) -> list[dict]:
    """Teacher outputs from Langfuse traces with pii_leak == 0, restricted to pool inputs."""
    from langfuse import get_client
    lf, pool_texts, rows, cursor = get_client(), {r["text"] for r in pool}, [], None
    while len(rows) < limit:
        page = lf.api.scores.get_many(name="pii_leak", limit=100, cursor=cursor, fields="subject")
        for s in page.data:
            if s.value != 0 or s.subject.kind != "trace":
                continue
            obs = lf.api.observations.get_many(trace_id=s.subject.id, name="teacher-redact",
                                               fields="core,io", limit=1).data
            if not obs:
                continue
            text, out = unjson(obs[0].input), unjson(obs[0].output)  # v2 API returns io as raw JSON strings
            if isinstance(text, str) and text in pool_texts and text not in blocked and isinstance(out, dict):
                rows.append(to_row(text, out["entities"]))
        cursor = getattr(page.meta, "cursor", None)
        if not cursor:
            break
    return rows[:limit]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-langfuse", action="store_true")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="distil")
    a = ap.parse_args()
    data, out = Path(a.data), Path(a.out)
    clean = data / "test_clean.jsonl"
    if not clean.exists():
        print("WARNING: data/test_clean.jsonl missing, using raw data/test.jsonl (review it first!)")
    test = read(clean if clean.exists() else data / "test.jsonl")
    blocked = {r["text"] for r in test}
    if a.from_langfuse:
        train = langfuse_rows(read(data / "pool.jsonl"), blocked, a.limit)
    else:
        train = [to_row(r["text"], r["entities"]) for r in read(data / "seed.jsonl")]
    out.mkdir(exist_ok=True)
    (out / "config.yaml").write_text(CONFIG.format(
        student=os.getenv("DISTIL_STUDENT", "Qwen3-1.7B"), teacher=os.getenv("DISTIL_TEACHER", "openai.gpt-oss-120b")))
    (out / "job_description.json").write_text(json.dumps(JOB, ensure_ascii=False, indent=2))
    for name, rows in (("train.jsonl", train), ("test.jsonl", [to_row(r["text"], r["entities"]) for r in test])):
        (out / name).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"{out}/: {len(train)} train rows, {len(test)} test rows. Not submitted. Next (costs credits):")
    print(f"  distil dataset create --data {out}                       # validates, prints <dataset-id>")
    print("  distil dataset generate-synthetic-data-train --smoke <dataset-id>   # cheap smoke first")
    print("  distil dataset generate-synthetic-data-train <dataset-id>")
    print("  distil slm create-from-dataset <dataset-id>")


if __name__ == "__main__":
    main()
