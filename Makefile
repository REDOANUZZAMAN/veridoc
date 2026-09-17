# ============================================================================
# VeriDoc — developer commands
#   make help    to list them
# ============================================================================
SHELL := /bin/bash
PY    := ../.venv/bin/python
PIP   := ../.venv/bin/pip

.DEFAULT_GOAL := help
.PHONY: help up down logs ps infra build seed seed-reset reset-db migrate migration \
        drift api worker web install test test-fast cover typecheck front-build \
        walkthrough purge-dry clean

help: ## List the available commands
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- docker ----------------------------------------------------------------
up: ## Start the whole stack (build if needed)
	docker compose up -d --build

infra: ## Start only PostgreSQL, Redis and MinIO (for local dev)
	docker compose up -d postgres redis minio minio-init

down: ## Stop the stack (volumes are kept)
	docker compose down

logs: ## Follow the API and worker logs
	docker compose logs -f api worker

ps: ## Show container status
	docker compose ps

build: ## Build the images
	docker compose build

# --- database --------------------------------------------------------------
migrate: ## Apply migrations
	cd backend && $(PY) -m alembic upgrade head

migration: ## Create a migration:  make migration m="add x"
	cd backend && $(PY) -m alembic revision --autogenerate -m "$(m)"

drift: ## Fail if the models have drifted from the migrations
	cd backend && $(PY) -m alembic check

seed: ## Seed/refresh the demo environment
	cd backend && $(PY) -m app.db.seed

seed-reset: ## Drop, recreate and seed everything (destructive)
	cd backend && $(PY) -m app.db.seed --reset

reset-db: seed-reset ## Alias for seed-reset

# --- run -------------------------------------------------------------------
api: ## Run the API with reload on :8088
	cd backend && $(PY) -m uvicorn app.main:app --reload --port 8088

worker: ## Run an analysis worker
	cd backend && $(PY) -m app.workers.worker

web: ## Run the console on :3010
	cd frontend && npm run dev

install: ## Install backend and frontend dependencies
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install

# --- quality ---------------------------------------------------------------
test: ## Run the full backend test suite
	cd backend && $(PY) -m pytest

test-fast: ## Skip the pipeline tests
	cd backend && $(PY) -m pytest -m "not slow"

cover: ## Test with a coverage report
	cd backend && $(PY) -m pytest --cov=app --cov-report=term-missing

typecheck: ## Typecheck the frontend
	cd frontend && npm run typecheck

front-build: ## Production build of the console
	cd frontend && npm run build

walkthrough: ## Exercise every product requirement against a running instance
	cd backend && $(PY) scripts/walkthrough.py

purge-dry: ## Show what the retention job would remove
	cd backend && $(PY) -c "from app.workers.tasks import purge_expired_documents_task as p; import json; print(json.dumps(p(), indent=2))"

clean: ## Remove build and cache artifacts (not data)
	find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf backend/.pytest_cache frontend/.next frontend/out
