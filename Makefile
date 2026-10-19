# Run `make help`. Local Ollama testing: append ENV_FILE=local/.env to any target.
UV     := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
N      ?= 20
SPLIT  ?= test
SYSTEM ?= teacher
ROLE   ?= student
export ENV_FILE

.PHONY: help setup check data teacher student eval review review-import distil-prep demo app test

help:          ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

setup:         ## one-time: install uv + distil CLI, deps, .env, data, run tests
	@command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
	@command -v distil >/dev/null || [ -x $(HOME)/.local/bin/distil ] || curl -fsSL https://cli-assets.distillabs.ai/install.sh | sh
	$(UV) sync
	@[ -f .env ] || (cp .env.example .env && echo "created .env - fill it in (README: Configure)")
	$(MAKE) data test

check:         ## which settings are filled in; Langfuse + distil auth
	$(UV) run python scripts/check.py

data:          ## download German rows + synthetic broker messages -> data/{test,seed,pool}.jsonl
	$(UV) run python -m pii.data --locale DE

teacher:       ## teacher over N rows of SPLIT, traced -> results/preds_teacher_SPLIT.jsonl
	$(UV) run python -m pii.extract teacher --n $(N) --split $(SPLIT) $(if $(YES),--yes)

student:       ## student (distil endpoint) over N rows of SPLIT, traced
	$(UV) run python -m pii.extract student --n $(N) --split $(SPLIT) $(if $(YES),--yes)

eval:          ## score SYSTEM on SPLIT -> results/eval_*.md + Langfuse scores
	$(UV) run python -m pii.evaluate --system $(SYSTEM) --split $(SPLIT)

review:        ## export test set to data/test_review.csv for hand-fixing labels
	$(UV) run python scripts/review_testset.py export

review-import: ## fixed CSV -> data/test_clean.jsonl (used by eval + distil-prep)
	$(UV) run python scripts/review_testset.py import

distil-prep:   ## write distil/ (config, job description, train, test); submits nothing
	$(UV) run python scripts/distil_prep.py $(ARGS)

demo:          ## gateway demo: make demo TEXT="..." [ROLE=teacher]
	$(UV) run python -m pii.gateway "$(TEXT)" $(if $(filter teacher,$(ROLE)),--teacher)

app:           ## PII redactor chat UI on http://localhost:8000
	$(UV) run python -m pii.app

test:          ## unit tests
	$(UV) run pytest -q
