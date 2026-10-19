# One command per stage. `uv run` loads the project env; .env is read by python-dotenv.
N ?= 20
SYSTEM ?= teacher
SPLIT ?= test

.PHONY: data baseline eval distil-prep serve demo test
data:       ; uv run python -m pii.data --locale DE
baseline:   ; uv run python -m pii.teacher --n $(N) --split $(SPLIT)
eval:       ; uv run python -m pii.evaluate --system $(SYSTEM) --split $(SPLIT)
distil-prep:; uv run python scripts/distil_prep.py
serve:      ; @cat scripts/runpod_serve.md
demo:       ; uv run python -m pii.gateway "$(TEXT)"
test:       ; uv run pytest -q
