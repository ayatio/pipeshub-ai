# living-brain — developer tasks
# Default DB is a local SQLite file (zero dependencies). For the Postgres +
# pgvector backend, set DATABASE_URL in .env and use `make db-postgres`.

UV ?= uv
RUN = $(UV) run

.DEFAULT_GOAL := help

.PHONY: help
help: ## show this help
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: sync
sync: ## install dependencies (uv sync)
	$(UV) sync

.PHONY: db
db: ## provision the database (creates SQLite dir, or brings up Postgres if configured)
	@if grep -qE '^DATABASE_URL=postgres' .env 2>/dev/null; then \
		$(MAKE) db-postgres; \
	else \
		mkdir -p data; \
		echo "db: using local SQLite at ./data/ (no server needed)"; \
	fi

.PHONY: db-postgres
db-postgres: ## start Postgres + pgvector via docker compose
	docker compose up -d db
	@echo "db: waiting for postgres to become healthy..."
	@for i in $$(seq 1 30); do \
		docker compose exec -T db pg_isready -U brain >/dev/null 2>&1 && break; \
		sleep 1; \
	done
	@echo "db: postgres ready on localhost:5433"

.PHONY: migrate
migrate: ## apply database migrations
	$(RUN) python -m living_brain.migrate

.PHONY: ingest
ingest: ## ingest notes from NOTES_DIR (default ./data/notes)
	$(RUN) brain ingest

.PHONY: night
night: ## run a 60s consolidation pass
	bash scripts/run_night.sh 60

.PHONY: stats
stats: ## show brain stats
	$(RUN) brain stats

.PHONY: test
test: ## run the test suite
	$(RUN) --extra dev pytest -q

.PHONY: demo
demo: db migrate ## ingest sample notes + run a night pass end-to-end
	$(RUN) brain ingest data/notes
	bash scripts/run_night.sh 30
	$(RUN) brain stats

.PHONY: down
down: ## stop docker services
	docker compose down

.PHONY: clean
clean: ## remove local sqlite db + caches
	rm -f data/*.db data/*.db-* ; find . -name __pycache__ -type d -prune -exec rm -rf {} +
