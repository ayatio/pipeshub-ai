.PHONY: db db-local migrate down psql health capture mcp test test-db test-ollama fmt

# Bring up Postgres + pgvector and wait for it to be healthy.
db:
	docker compose up -d db
	@echo "waiting for Postgres to be healthy..."
	@until [ "$$(docker inspect -f '{{.State.Health.Status}}' living-brain-db 2>/dev/null)" = "healthy" ]; do sleep 1; done
	@echo "db is healthy on localhost:5433"

# Fallback when there is no Docker daemon: a native PG16+pgvector cluster.
db-local:
	bash scripts/pg_local.sh

# Apply every migration in order.
migrate:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	for f in migrations/*.sql; do \
		echo "applying $$f"; \
		psql "$${DATABASE_URL:-postgresql://brain:brain@localhost:5433/brain}" -v ON_ERROR_STOP=1 -f "$$f"; \
	done

down:
	docker compose down

psql:
	@set -a; [ -f .env ] && . ./.env; set +a; \
	psql "$${DATABASE_URL:-postgresql://brain:brain@localhost:5433/brain}"

health:
	uv run brain health

capture:
	uv run brain capture $(f)

mcp:
	uv run brain mcp

test:
	uv run pytest -q

test-db:
	uv run pytest -q -m db

test-ollama:
	uv run pytest -q -m ollama
