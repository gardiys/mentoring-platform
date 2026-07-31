COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env

.PHONY: install up down backend frontend migrate migration seed test test-backend test-frontend lint format typecheck api-generate ensure-test-db

install:
	cd backend && poetry install
	cd frontend && corepack enable && pnpm install

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

backend:
	cd backend && poetry run uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && pnpm dev

migrate:
	cd backend && poetry run alembic upgrade head

migration:
	cd backend && poetry run alembic revision --autogenerate -m "$(name)"

seed:
	cd backend && poetry run python -m app.seed

ensure-test-db:
	-$(COMPOSE) exec -T postgres createdb -U mentoring mentoring_test

test: test-backend test-frontend

test-backend: ensure-test-db
	cd backend && poetry run pytest

test-frontend:
	cd frontend && pnpm test

lint:
	cd backend && poetry run ruff check app tests
	cd frontend && pnpm lint

format:
	cd backend && poetry run ruff format app tests
	cd frontend && pnpm format

typecheck:
	cd backend && poetry run mypy app
	cd frontend && pnpm typecheck

api-generate:
	cd frontend && pnpm api:generate
