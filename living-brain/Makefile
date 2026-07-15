# Living Brain — developer tasks.
#
# Uses `uv run` when uv is available (the recommended path); otherwise falls
# back to the system python3 with src/ on PYTHONPATH so targets still work.

UV := $(shell command -v uv 2>/dev/null)
ifdef UV
PY := uv run python
else
PY := python3
export PYTHONPATH := src:$(PYTHONPATH)
endif

DB ?= ./data/brain.db

.DEFAULT_GOAL := help
.PHONY: help install db migrate seed status night brief test clean reset

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Sync dependencies with uv
	uv sync

db: ## Create the database file (and its directory)
	@mkdir -p $(dir $(DB))
	$(PY) -m living_brain.cli createdb
	@echo "database ready: $(DB)"

migrate: ## Apply pending SQL migrations
	$(PY) -m living_brain.cli migrate

seed: ## Load sample memories if the brain is empty
	$(PY) -m living_brain.cli seed

status: ## Show counts, backend, and migration state
	$(PY) -m living_brain.cli status

night: ## Run one consolidation pass (make night DURATION=60)
	$(PY) -m living_brain.cli night --duration $(or $(DURATION),60)

brief: ## Print the morning brief
	$(PY) -m living_brain.cli brief

test: ## Run the test suite
	$(PY) -m pytest

clean: ## Remove caches
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache

reset: ## Delete the database (destructive)
	rm -f $(DB) $(DB)-wal $(DB)-shm
	@echo "removed $(DB)"
