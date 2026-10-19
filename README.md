# PII gateway — German PII redaction with a distilled small model

**Pitch.** Broker/bank support gets emails and call notes full of PII (names, IBANs, tax IDs, depot numbers…).
A small self-hosted model finds the PII, code swaps it for placeholders (`[IBAN_1]`), only the masked text reaches the
frontier LLM / downstream ticket classifier, and the reply is rehydrated. We measure leaks, train the small model with
distil labs, serve it on Runpod, and improve it from Langfuse traces.

```
data ──> teacher (big LLM) ──> eval: leak rate ──> distil labs: train student ──> Runpod: serve ──> student eval ──> demo
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
| Student | `STUDENT_BASE_URL`, `STUDENT_API_KEY` | your Runpod pod (step 5) |
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

## 5. Serve on Runpod (vLLM) and evaluate the student

Pod: 24 GB GPU (RTX 4090 / L4 / A5000), vLLM or PyTorch template, expose HTTP **8000**, disk ≥ 30 GB.
Upload `model/model-adapter` (`runpodctl send model/model-adapter`), then on the pod:

```bash
pip install -U vllm
vllm serve Qwen/Qwen3-1.7B --served-model-name base \
  --enable-lora --lora-modules model=./model-adapter --max-lora-rank 64 --api-key "$VLLM_API_KEY" \
  --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3
```
Base model and `--max-lora-rank` come from `model/config.yaml` (`student_model_name`, `lora_r`). Then set
`STUDENT_BASE_URL=https://<POD_ID>-8000.proxy.runpod.net/v1` and `STUDENT_API_KEY=$VLLM_API_KEY` in `.env`. If
`model/model_client.py` sets sampling or `chat_template_kwargs`, copy them into `STUDENT_EXTRA` (a small model degrades
outside its training setup).

```bash
make student N=50 YES=1 && make eval SYSTEM=student
make demo TEXT="Hallo, ich bin Anna Berg, Depot 4829173650, IBAN DE89 3704 0044 0532 0130 00"
```
Stop the pod when done. Retrain loop: run the teacher on `SPLIT=pool`, `make eval SPLIT=pool`, then
`make distil-prep ARGS=--from-langfuse`, bump `STUDENT_VERSION`, repeat step 4–5.

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
