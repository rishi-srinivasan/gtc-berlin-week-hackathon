# PII gateway — German PII redaction with a distilled small model

**Pitch.** Broker/bank support gets emails and call notes full of PII (names, IBANs, tax IDs, depot numbers…).
A small self-hosted model finds the PII, code swaps it for placeholders (`[IBAN_1]`), only the masked text reaches the
frontier LLM / downstream ticket classifier, and the reply is rehydrated. We measure leaks, train the small model with
distil labs, serve it from a distil labs endpoint, and improve it from Langfuse traces.

```
data ──> teacher (big LLM) ──> eval: leak rate ──> distil labs: train student ──> distil endpoint ──> student eval ──> demo
              │ every call traced in Langfuse; leak-free teacher traces become new training rows ──────────┘ (loop)
```

## 1. Setup (once, ~2 min)

```bash
git clone <repo-url> && cd gtc-berlin-week-hackathon
make setup
```
Installs `uv` and the `distil` CLI if missing, Python deps, creates `.env`, builds `data/`, runs the tests.

## 2. Configure (hackathon day)

Everything lives in **`.env`** (template: `.env.example`). Paste what the organisers share, then `make check`.

| What | `.env` keys | Source |
|---|---|---|
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | organisers |
| distil labs | run `distil auth` (interactive login) | organisers |
| Teacher LLM | `TEACHER_MODEL`, `TEACHER_BASE_URL`, `TEACHER_API_KEY` | any OpenAI-compatible API (`TEACHER_PROVIDER=anthropic` for Claude) |
| Student | `STUDENT_BASE_URL`, `STUDENT_API_KEY` | distil inference endpoint (step 5) |
| Demo LLM | `FRONTIER_*` | same as teacher is fine |

Each role (`TEACHER`, `STUDENT`, `FRONTIER`) takes `_PROVIDER`, `_MODEL`, `_BASE_URL`, `_API_KEY` and optional
`_EXTRA` (JSON request params). Code: `src/pii/llm.py`.

## 3. Baseline + eval

```bash
make teacher N=20            # teacher on 20 test rows, traced in Langfuse (>50 rows needs YES=1)
make eval SYSTEM=teacher     # leak rate (+95% upper bound), critical/high recall, per-class P/R, latency, cost
make review                  # optional: fix noisy gold labels in data/test_review.csv, then
make review-import           #   -> data/test_clean.jsonl, used automatically from now on
```
A **leak** = a gold PII value still readable after masking (digits-only match for numbers). Scores land on each
Langfuse trace as `pii_leak`; reports in `results/`.

## 4. distil labs: train the student

```bash
make distil-prep                                  # writes distil/ from seed rows + test set
make distil-prep ARGS=--from-langfuse             # or: train rows from leak-free teacher traces (pool split)
distil dataset create --data distil               # validates + uploads -> <dataset-id> (free)
distil dataset generate-synthetic-data-train --smoke <dataset-id>   # cheap smoke run (credits)
distil dataset generate-synthetic-data-train <dataset-id>           # full synthetic train set
distil slm create-from-dataset <dataset-id>       # train -> <slm-id>; check: distil slm status / metrics <slm-id>
distil slm download --destination model <slm-id> && tar -xf model/model.tar -C model
```
Models: `DISTIL_TEACHER` / `DISTIL_STUDENT` in `.env` (must be in distil's catalog). Task description = the prompt in
`src/pii/schema.py`. distil's own endpoint traces (`observation_format: langfuse`): `distil inference-endpoint
download-traces --all <name>` then `make distil-prep ARGS="--traces <name>-traces.jsonl"`.

## 5. Serve with distil labs and evaluate the student

Needs a finished `<slm-id>` trained with `tuning.lora_r` in 8/16/32/64/128/256/320/512. A deployment stops after 6 h
(or 1 h idle), cannot be restarted, and costs a deployment credit (`distil credits-balance`).

```bash
distil deployment create-from-slm <slm-id>                     # prints <deployment-id>
distil deployment status <deployment-id>                       # wait for Success
distil inference-endpoint create-from-deployment --name pii-student \
  --fallback-model "openai/gpt-4.1-mini" <deployment-id>       # prints the unique Endpoint Name
distil api-keys create pii-key                                 # secret saved to pii-key.json
distil inference-endpoint link-api-key <endpoint-name> pii-key # key works after ~1 min
distil slm download-metadata --destination model <slm-id>      # model/model_client.py
```
In `.env`: `STUDENT_MODEL=<endpoint-name>`, `STUDENT_API_KEY=<secret from pii-key.json>`
(`STUDENT_BASE_URL` is already `https://inference.distillabs.ai/v1`). Copy any sampling or `chat_template_kwargs` that
`model/model_client.py` sets into `STUDENT_EXTRA`: a small model degrades outside its training setup. Once the
deployment stops, the endpoint silently answers from the fallback model, so check the reply's model before trusting a score.

```bash
make student N=50 YES=1 && make eval SYSTEM=student
make demo TEXT="Hallo, ich bin Anna Berg, Depot 4829173650, IBAN DE89 3704 0044 0532 0130 00"
```
Retrain loop: run the teacher on `SPLIT=pool`, `make eval SPLIT=pool`, then
`make distil-prep ARGS=--from-langfuse`, bump `STUDENT_VERSION`, repeat step 4–5.

## Results

### distil teacher evaluation (2026-10-19)
Teacher `openai.gpt-oss-120b` on the 300-row test set, run from dataset `2b765fd1-7d70-42e5-a927-5e4a8936f624`
(evaluation `45824391-7935-4b98-86e1-e8d9fbfd9a89`). Test labels were not yet hand-reviewed.

| Metric | Score |
|---|---|
| Rouge | 86.63% |
| Binary (exact match of the whole entity list) | 8.33% |
| LLM-as-a-Judge (vs. reference) | 55.67% |
| LLM-as-a-Judge (reference-free) | 84.67% |

Binary is low because entity order and span splitting rarely match exactly; ignore it. The gap between the two judge
scores means the teacher's answers look reasonable but often disagree with the gold labels (label noise or prompt
mismatch). These are not the headline metric: leak rate and critical recall come from `make eval`.

## Repo map

| Path | What it does |
|---|---|
| `src/pii/schema.py` | Labels, critical/high tiers, **the prompt** (= distil task description), JSON schema |
| `src/pii/synth.py` | Synthetic broker messages — **add templates / PII types here** |
| `src/pii/data.py` | Hugging Face German rows + IBAN injection + 40% synthetic → test 300 / seed 100 / pool 2000 |
| `src/pii/llm.py` | One chat client per role from `.env` (OpenAI-compatible or Anthropic) |
| `src/pii/extract.py` | Runs teacher/student over a split, one Langfuse trace per call |
| `src/pii/redact.py` | `mask()` → `[LABEL_n]` placeholders, `rehydrate()` |
| `src/pii/evaluate.py` | Leak rate, recall/precision, cost; pushes scores to Langfuse |
| `src/pii/gateway.py` | Demo: redact → frontier LLM → rehydrate |
| `scripts/distil_prep.py` | Builds `distil/` (config, job description, train/test) |
| `scripts/review_testset.py`, `scripts/check.py` | Label review CSV round-trip; readiness check |

**Adding a PII type:** add the label to `EXTRA_LABELS` (+ a tier / `NUMERIC` if it's a number) and a rule line in
`SYSTEM_PROMPT` in `schema.py`, a generator in `synth.values()` and a `{LABEL}` slot in a template, then `make data test`.

Generated (gitignored): `data/`, `results/`, `distil/`, `model/`. Personal local testing (Ollama/GLiNER) lives in
the gitignored `local/` folder.
