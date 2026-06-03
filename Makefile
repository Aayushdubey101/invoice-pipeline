.PHONY: setup dev test seed lint migrate clean build

setup:
	cp -n .env.example .env || true
	cd apps/api && uv sync --extra dev --extra docs
	cd apps/web && pnpm install

dev:
	docker compose up -d postgres chromadb
	@echo "Starting API and web in foreground..."
	@(cd apps/api && uv run uvicorn invoice_pipeline.api.main:app --reload --host 0.0.0.0 --port 8000 &)
	cd apps/web && pnpm dev

dev-docker:
	docker compose up -d postgres chromadb
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up api web

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

migrate:
	cd apps/api && uv run alembic upgrade head

migrate-create:
	cd apps/api && uv run alembic revision --autogenerate -m "$(MSG)"

seed:
	./scripts/seed.sh

test:
	cd apps/api && uv run pytest --cov=invoice_pipeline --cov-report=term-missing -v

test-web:
	cd apps/web && pnpm test

test-api:
	cd apps/api && uv run pytest tests/test_api.py -v

lint:
	cd apps/api && uv run ruff check src/ tests/
	cd apps/api && uv run mypy src/
	cd apps/web && pnpm lint

format:
	cd apps/api && uv run ruff format src/ tests/
	cd apps/web && pnpm prettier --write .

clean:
	docker compose down -v
	cd apps/api && rm -rf .venv __pycache__ .mypy_cache .ruff_cache .pytest_cache
	cd apps/web && rm -rf .next node_modules
