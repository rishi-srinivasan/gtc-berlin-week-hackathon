# pii-gateway

German PII detection for a GDPR gateway: a small model finds PII, code masks it (`[SURNAME_1]`), a frontier LLM
sees only the masked text, and the reply is rehydrated. Loop: Langfuse traces + evals -> distil labs trains a student
-> serve on Runpod -> trace -> retrain.

**Profiles** (`config.toml`): `local` (default; Ollama teacher gemma4:12b + student qwen3:1.7b, no keys, free) and `hackathon`
(cloud teacher + student served on Runpod; fill the `<placeholders>`). Switch with `PII_PROFILE=hackathon` (shell or `.env`);
override any single value with an env var of the same name. `uv run python -m pii.config` shows the effective settings,
which keys are missing, and which Ollama models still need pulling. Secrets stay in `.env`. Local GGUF import: `scripts/ollama_import.md`.

Setup: `uv sync`, copy `.env.example` to `.env` (the repo-root `.env` is picked up too), fill the names. Never commit `.env`.

| Stage | Command | Notes |
|---|---|---|
| Tests | `make test` | masking, IBAN, splits, eval, distil rows |
| Data | `make data` | German DE-locale rows -> `data/{test,seed,pool}.jsonl` (gitignored), IBANs injected |
| Baseline | `make baseline N=20` | teacher traced in Langfuse -> `results/preds_teacher_test.jsonl`; `SPLIT=pool` for training traces. More than 50 calls needs `--yes` |
| Eval | `make eval SYSTEM=teacher` | leak rate, per-class P/R, tiers, latency, cost; scores pushed to Langfuse; `results/eval_*.md` |
| Review test set | `uv run python scripts/review_testset.py export` / `import` | fix labels by hand -> `data/test_clean.jsonl` (eval and distil-prep use it automatically) |
| distil prep | `make distil-prep` (or `uv run python scripts/distil_prep.py --from-langfuse`) | writes `distil/`, prints the `distil` commands, submits nothing |
| Serve | `make serve` | prints `scripts/runpod_serve.md` |
| Student | `uv run python -m pii.student_client --n 20` then `make eval SYSTEM=student` | needs `STUDENT_*` env |
| Presidio (optional) | `uv sync --extra presidio` then `uv run python -m pii.presidio_baseline` | then `make eval SYSTEM=presidio` |
| GLiNER (optional) | `uv sync --extra gliner` then `uv run python -m pii.gliner_baseline` | then `make eval SYSTEM=gliner` |
| Demo | `make demo TEXT="Hallo, ich bin Anna Berg, IBAN DE89 3704 0044 0532 0130 00"` | add `--teacher` via `uv run python -m pii.gateway --teacher "..."` |

Traces contain the raw (synthetic) input text on purpose: distil needs it to build training rows. For real user text,
add a Langfuse `mask=` function before tracing.
