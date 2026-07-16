# living-brain — developer tasks
#
# Everything runs through `uv run` against the local source (PYTHONPATH=src),
# so there is no build step and no third-party install required.

# Force uv to use a discoverable system Python and never phone home for one.
export UV_PYTHON_DOWNLOADS ?= never
export PYTHONPATH := src

UV ?= uv
RUN := $(UV) run --no-project python -m living_brain
SECONDS ?= 60

.PHONY: help sync db migrate ingest search night consolidate test clean

help:
	@echo "living-brain targets:"
	@echo "  make sync         # uv sync (create the venv)"
	@echo "  make db           # initialize the database"
	@echo "  make migrate      # apply migrations"
	@echo "  make ingest       # ingest notes from data/notes"
	@echo "  make consolidate  # run one nightly digest"
	@echo "  make night [SECONDS=60]  # run the nightly loop"
	@echo "  make search Q='your query'"
	@echo "  make test         # run the smoke tests"

sync:
	$(UV) sync

db:
	$(RUN) init-db

migrate:
	$(RUN) migrate

ingest:
	$(RUN) ingest

consolidate:
	$(RUN) consolidate

search:
	$(RUN) search "$(Q)"

night:
	bash scripts/run_night.sh $(SECONDS)

test:
	$(UV) run --no-project python -m unittest discover -s tests -v

clean:
	rm -f data/brain.db data/brain.db-* data/reports/digest-*.md
