COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
PROD_COMPOSE := docker compose -f infra/docker-compose.prod.yml --env-file .env.production
first_name ?= Администратор

.PHONY: install up down backend frontend migrate migration seed test test-backend test-frontend lint format typecheck api-generate ensure-test-db prod-config prod-up prod-down prod-logs prod-ps prod-admin prod-backup

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

prod-config:
	$(PROD_COMPOSE) config --quiet

prod-up: prod-config
	$(PROD_COMPOSE) up --build -d

prod-down:
	$(PROD_COMPOSE) down

prod-logs:
	$(PROD_COMPOSE) logs -f --tail=200

prod-ps:
	$(PROD_COMPOSE) ps

prod-admin:
	@test -n "$(telegram_id)" || (echo "Usage: make prod-admin telegram_id=123456789" && exit 1)
	$(PROD_COMPOSE) exec backend python -m app.bootstrap_admin --telegram-id "$(telegram_id)" --first-name "$(first_name)"

prod-backup:
	@mkdir -p backups
	$(PROD_COMPOSE) exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -Fc' > "backups/mentoring-$$(date +%Y%m%d-%H%M%S).dump"
