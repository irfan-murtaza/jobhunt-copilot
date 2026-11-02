.DEFAULT_GOAL := help
API := cd api && uv run

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install API and web dependencies
	cd api && uv sync --extra dev
	cd web && npm install
	cp -n .env.example .env || true

up: ## Start everything with Docker Compose
	docker compose up --build -d

down: ## Stop Docker Compose services
	docker compose down

api: ## Run the API with reload (expects Postgres and Redis)
	$(API) jobhunt api --reload

worker: ## Run the background worker
	$(API) jobhunt worker

web: ## Run the Next.js dev server
	cd web && npm run dev

migrate: ## Apply database migrations
	$(API) alembic upgrade head

migration: ## Autogenerate a migration: make migration m="add foo"
	$(API) alembic revision --autogenerate -m "$(m)"

lint: ## Lint and type-check API and web
	$(API) ruff check . && $(API) ruff format --check . && $(API) mypy src
	cd web && npm run lint && npx tsc --noEmit

fmt: ## Format code
	$(API) ruff format . && $(API) ruff check --fix .

test: ## Run the API test suite
	$(API) pytest -q

evals: ## Run the evaluation suite (writes api/evals/results/*.json)
	$(API) python -m evals.run

.PHONY: help setup up down api worker web migrate migration lint fmt test evals
