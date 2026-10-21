# PII Gateway

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

German PII redaction with a distilled small model. Support emails and call notes are full of names, IBANs, tax IDs
and depot numbers. A small self-hosted model finds the PII, code swaps it for placeholders (`[IBAN_1]`), only the
masked text reaches a frontier LLM, and the reply is rehydrated with the original values.

Built on [distil labs](https://www.distillabs.ai) (train and serve the small model), [Langfuse](https://langfuse.com)
(trace and score every call) and this repository (data, masking, evaluation, demo UI).

```
data ──> teacher (big LLM) ──> eval: leak rate ──> distil labs: train student ──> distil endpoint ──> student eval ──> demo
              │ every call traced in Langfuse; leak-free teacher traces become new training rows ──────────┘ (loop)
```

## Quick start

```bash
git clone https://github.com/rishi-srinivasan/gtc-berlin-week-hackathon.git && cd gtc-berlin-week-hackathon && make setup
```

`make setup` installs [`uv`](https://docs.astral.sh/uv/) and the `distil` CLI if missing, installs Python deps,
creates `.env` from the template, builds `data/` and runs the tests. Then add your keys to `.env` and run:

```bash
make check    # confirms Langfuse and distil labs accept your credentials
make app      # chat UI on http://localhost:8000
```

## Requirements

- macOS or Linux, `curl`, `make`, Python 3.11+ (managed by `uv`)
- A [Langfuse](https://cloud.langfuse.com) project (free tier works): public + secret key
- A [distil labs](https://www.distillabs.ai) account (`distil auth`)
- An API key for any OpenAI-compatible LLM (or Anthropic) for the teacher and the demo's frontier model

## Configuration

Everything lives in `.env` (template: [`.env.example`](.env.example)). `.env` is gitignored: never commit it.

| What | `.env` keys | Where to get it |
|---|---|---|
| Langfuse | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Langfuse project settings → API keys |
| distil labs | none: run `distil auth` | interactive login |
| Teacher LLM | `TEACHER_MODEL`, `TEACHER_BASE_URL`, `TEACHER_API_KEY` | any OpenAI-compatible API (`TEACHER_PROVIDER=anthropic` for Claude) |
| Student | `STUDENT_MODEL`, `STUDENT_API_KEY` | distil inference endpoint (see [Serve](#serve-the-student)) |
| Demo LLM | `FRONTIER_*` | can be the same as the teacher |

Each role (`TEACHER`, `STUDENT`, `FRONTIER`) takes `_PROVIDER`, `_MODEL`, `_BASE_URL`, `_API_KEY` and an optional
`_EXTRA` (JSON request params). Code: [`src/pii/llm.py`](src/pii/llm.py).

## Usage

### Baseline and evaluation

```bash
make teacher N=20            # teacher on 20 test rows, traced in Langfuse (>50 rows needs YES=1)
make eval SYSTEM=teacher     # leak rate (+95% upper bound), critical/high recall, per-class P/R, latency, cost
make review                  # optional: fix noisy gold labels in data/test_review.csv, then
make review-import           #   -> data/test_clean.jsonl, used automatically from now on
```

A **leak** is a gold PII value still readable after masking (digits-only match for numbers). Scores land on each
Langfuse trace as `pii_leak`; reports are written to `results/`.

### Train the student with distil labs

```bash
make distil-prep                                  # writes distil/ from seed rows + test set
make distil-prep ARGS=--from-langfuse             # or: train rows from leak-free teacher traces (pool split)
distil dataset create --data distil               # validates + uploads -> <dataset-id>
distil dataset generate-synthetic-data-train --smoke <dataset-id>   # cheap smoke run (uses credits)
distil dataset generate-synthetic-data-train <dataset-id>           # full synthetic train set
distil slm create-from-dataset <dataset-id>       # train -> <slm-id>; check: distil slm status / metrics <slm-id>
distil slm download --destination model <slm-id> && tar -xf model/model.tar -C model
```

Set `DISTIL_TEACHER` / `DISTIL_STUDENT` in `.env` (must be in distil's model catalog). The task description is the
prompt in [`src/pii/schema.py`](src/pii/schema.py). To train from distil endpoint traces:
`distil inference-endpoint download-traces --all <name>` then `make distil-prep ARGS="--traces <name>-traces.jsonl"`.

### Serve the student

Needs a finished `<slm-id>` trained with `tuning.lora_r` in 8/16/32/64/128/256/320/512. A deployment stops after 6 h
(or 1 h idle), cannot be restarted, and costs a deployment credit (`distil credits-balance`).

```bash
distil deployment create-from-slm <slm-id>                     # prints <deployment-id>
distil deployment status <deployment-id>                       # wait for Success
distil inference-endpoint create-from-deployment --name pii-student \
  --fallback-model "openai/gpt-4.1-mini" <deployment-id>       # prints the unique endpoint name
distil api-keys create pii-key                                 # secret saved to pii-key.json (gitignored)
distil inference-endpoint link-api-key <endpoint-name> pii-key # key works after ~1 min
distil slm download-metadata --destination model <slm-id>      # model/model_client.py
```

In `.env` set `STUDENT_MODEL=<endpoint-name>` and `STUDENT_API_KEY=<secret from pii-key.json>`. Copy any sampling or
`chat_template_kwargs` that `model/model_client.py` sets into `STUDENT_EXTRA`: a small model degrades outside its
training setup. Once the deployment stops, the endpoint silently answers from the fallback model, so check the
reply's model before trusting a score.

```bash
make student N=50 YES=1 && make eval SYSTEM=student
make demo TEXT="Hallo, ich bin Anna Berg, Depot 4829173650, IBAN DE89 3704 0044 0532 0130 00"
make app                                                       # chat UI with student/teacher toggle
```

### Retrain loop

Run the teacher on `SPLIT=pool`, `make eval SPLIT=pool`, then `make distil-prep ARGS=--from-langfuse`, bump
`STUDENT_VERSION`, and repeat training and serving.

All targets: `make help`.

## Results

Fine-tuned Qwen3-1.7B reaches teacher-level text overlap (Rouge 85.6% vs 86.6% for the 120B teacher) and far exceeds
the untuned base. Full numbers and method: [docs/RESULTS.md](docs/RESULTS.md).

## Project structure

```
.
├── src/pii/            library + demo app
│   ├── schema.py       labels, critical/high tiers, the prompt (= distil task description), JSON schema
│   ├── synth.py        synthetic broker messages (add templates / PII types here)
│   ├── data.py         Hugging Face German rows + IBAN injection + synthetic → test / seed / pool splits
│   ├── llm.py          one chat client per role from .env (OpenAI-compatible or Anthropic)
│   ├── extract.py      runs teacher/student over a split, one Langfuse trace per call
│   ├── redact.py       mask() → [LABEL_n] placeholders, rehydrate()
│   ├── evaluate.py     leak rate, recall/precision, cost; pushes scores to Langfuse
│   ├── gateway.py      redact → frontier LLM → rehydrate
│   └── app.py          chat UI (stdlib server, no build step)
├── scripts/            distil_prep.py (builds distil/), review_testset.py, check.py
├── tests/              pytest suite (make test)
├── data/               generated splits (test 300 / seed 100 / pool 2000) and reviewed test labels
├── docs/RESULTS.md     evaluation report
├── Makefile            every workflow as a target
└── .env.example        configuration template
```

Gitignored, generated locally: `.env`, `results/`, `distil/`, `model/`, `local/`.

## Contributing

Issues and pull requests are welcome. Run `make test` before opening a PR.

**Adding a PII type:** add the label to `EXTRA_LABELS` (plus a tier or `NUMERIC` if it is a number) and a rule line in
`SYSTEM_PROMPT` in `schema.py`, a generator in `synth.values()` and a `{LABEL}` slot in a template, then
`make data test`.

## Security

Never commit `.env` or API keys. If you find a leaked credential, rotate it and open an issue.

## License

[MIT](LICENSE)
