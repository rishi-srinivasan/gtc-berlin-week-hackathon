# PII Gateway

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

German PII redaction with a distilled small model. The model finds PII, code swaps it for placeholders (`[IBAN_1]`),
only the masked text reaches a frontier LLM, and the reply is rehydrated. Built on
[distil labs](https://www.distillabs.ai) (train and serve), [Langfuse](https://langfuse.com) (trace and score) and
this repo (data, masking, evaluation, demo UI).

Results from the hackathon demo: [results/DEMO_REPORT_FINAL.md](results/DEMO_REPORT_FINAL.md).

## Quick start

```bash
git clone https://github.com/rishi-srinivasan/gtc-berlin-week-hackathon.git && cd gtc-berlin-week-hackathon && make setup
```

Then put your keys in `.env` (template: [`.env.example`](.env.example)) and run:

```bash
make check    # Langfuse + distil auth
make app      # chat UI on http://localhost:8000
```

Needs `curl`, `make`, a Langfuse project, a distil labs account (`distil auth`) and an OpenAI-compatible (or
Anthropic) API key for the teacher and demo LLM. `make help` lists every target.

## Usage

```bash
make teacher N=20 && make eval SYSTEM=teacher      # baseline, traced in Langfuse
make distil-prep                                   # writes distil/ (add ARGS=--from-langfuse for trace-based rows)
distil dataset create --data distil                # -> <dataset-id>
distil dataset generate-synthetic-data-train <dataset-id>
distil slm create-from-dataset <dataset-id>        # -> <slm-id>
distil deployment create-from-slm <slm-id>         # -> <deployment-id>
distil inference-endpoint create-from-deployment --name pii-student <deployment-id>
distil api-keys create pii-key && distil inference-endpoint link-api-key <endpoint-name> pii-key
# .env: STUDENT_MODEL=<endpoint-name>, STUDENT_API_KEY=<secret from pii-key.json>
make student N=50 YES=1 && make eval SYSTEM=student
make demo TEXT="Hallo, ich bin Anna Berg, IBAN DE89 3704 0044 0532 0130 00"
```

## Project structure

```
src/pii/     schema, synth, data, llm, extract, redact, evaluate, gateway, app
scripts/     distil_prep.py, review_testset.py, check.py
tests/       pytest suite (make test)
data/        test / seed / pool splits
results/     DEMO_REPORT_FINAL.md
```

## License

[MIT](LICENSE)
