# Living Brain — developer tasks
#
#   make db        # ensure the database exists
#   make migrate   # apply pending migrations
#   make seed      # ingest bundled seed observations
#   make night     # run one nightly consolidation pass (MINUTES=60)
#   make test      # run the test suite
#   make stats     # show memory statistics

MINUTES ?= 60

# Prefer uv so we use the synced virtualenv; fall back to plain python.
UV := $(shell command -v uv 2>/dev/null)
ifeq ($(UV),)
RUN := python -m living_brain.cli
PYTEST := python -m pytest
else
RUN := uv run brain
PYTEST := uv run pytest
endif

.PHONY: db migrate seed night stats test clean help

help:
	@grep -E '^#   make' $(MAKEFILE_LIST) | sed 's/^#   //'

db:
	$(RUN) db-init

migrate: db
	$(RUN) migrate

seed: migrate
	$(RUN) ingest --seed

night: migrate
	bash scripts/run_night.sh $(MINUTES)

stats:
	$(RUN) stats

test:
	$(PYTEST)

clean:
	rm -rf data *.db *.sqlite3 .pytest_cache
