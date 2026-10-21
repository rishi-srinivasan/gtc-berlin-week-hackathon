# PII Gateway

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

German PII redaction with a distilled small model. The model finds PII, code swaps it for placeholders (`[IBAN_1]`),
only the masked text reaches a frontier LLM, and the reply is rehydrated. Built on
[distil labs](https://www.distillabs.ai) (train and serve), [Langfuse](https://langfuse.com) (trace and score) and
this repo (data, masking, evaluation, demo UI).

## Why

Teams in the EU building consumer-facing apps with LLMs must keep personal data out of places it doesn't need to be.
PII Gateway is an open-source building block for that: it masks personal data **before** text leaves your
infrastructure, using a small self-hosted model you can run yourself. It supports data minimisation under the GDPR and
can help financial-sector teams with their ICT third-party risk work under DORA. **It does not make an application
compliant with GDPR, DORA or any other regulation**, and it can miss PII (see the results). Compliance needs
a legal review, a DPIA where required, and your own controls around it.

Built at the GTC Berlin week hackathon, 2026-10-19. History and results: [HACKATHON.md](HACKATHON.md),
[results/DEMO_REPORT_FINAL.md](results/DEMO_REPORT_FINAL.md).

## Quick start

```bash
git clone https://github.com/rishi-srinivasan/pii-gateway.git && cd pii-gateway && make setup
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
HACKATHON.md hackathon history and summary
```

## License

[MIT](LICENSE)
