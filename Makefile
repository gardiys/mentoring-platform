COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
PROD_COMPOSE := docker compose -f infra/docker-compose.prod.yml --env-file .env.production
first_name ?= Администратор

.PHONY: install up down backend frontend worker worker-ai worker-media migrate docker-migrate migration seed test test-backend test-frontend lint format typecheck api-generate check-nexara prod-check-nexara backfill-question-embeddings prod-backfill-question-embeddings check-s3-multipart prod-check-s3-multipart tochka-webhook prod-tochka-webhook ensure-test-db prod-init prod-volume-check prod-config prod-migrate prod-up prod-down prod-logs prod-ps prod-admin prod-backup

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

worker:
	cd backend && poetry run arq app.interviews.intelligence_jobs.TranscriptionWorkerSettings

worker-ai:
	cd backend && poetry run arq app.interviews.intelligence_jobs.AIWorkerSettings

worker-media:
	cd backend && poetry run arq app.media.normalization_jobs.ContentMediaWorkerSettings

check-nexara:
	cd backend && poetry run python -m app.check_nexara

prod-check-nexara:
	$(PROD_COMPOSE) run --rm --no-deps intelligence-worker python -m app.check_nexara

backfill-question-embeddings: docker-migrate
	$(COMPOSE) run --rm --build --no-deps intelligence-ai-worker python -m app.backfill_question_embeddings

prod-backfill-question-embeddings: prod-migrate
	$(PROD_COMPOSE) build intelligence-ai-worker
	$(PROD_COMPOSE) run --rm --no-deps intelligence-ai-worker python -m app.backfill_question_embeddings

check-s3-multipart:
	$(COMPOSE) up -d --wait minio
	$(COMPOSE) run --rm minio-init
	$(COMPOSE) run --rm --no-deps \
		-e S3_PUBLIC_ENDPOINT_URL=http://minio:9000 \
		backend python -m app.check_s3_multipart --confirm

prod-check-s3-multipart: prod-config
	$(PROD_COMPOSE) run --rm --no-deps backend python -m app.check_s3_multipart --confirm

tochka-webhook:
	$(COMPOSE) exec backend python -m app.configure_tochka_webhook

prod-tochka-webhook: prod-config
	$(PROD_COMPOSE) exec backend python -m app.configure_tochka_webhook

migrate:
	cd backend && poetry run alembic upgrade head

docker-migrate:
	$(COMPOSE) up -d --wait postgres
	$(COMPOSE) run --rm --build --no-deps backend alembic upgrade head

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

prod-init:
	docker volume create mentoring-platform-production_postgres_data >/dev/null
	docker volume create mentoring-platform-production_redis_data >/dev/null

prod-volume-check:
	docker volume inspect mentoring-platform-production_postgres_data >/dev/null
	docker volume inspect mentoring-platform-production_redis_data >/dev/null

prod-config:
	$(PROD_COMPOSE) config --quiet

prod-migrate: prod-volume-check prod-config
	$(PROD_COMPOSE) build migrate
	$(PROD_COMPOSE) up -d --wait --wait-timeout 120 postgres
	$(PROD_COMPOSE) run --rm --no-deps migrate

prod-up: prod-volume-check prod-config
	$(PROD_COMPOSE) build migrate backend intelligence-worker intelligence-ai-worker content-media-worker frontend
	$(PROD_COMPOSE) up -d --wait --wait-timeout 120 postgres redis
	$(PROD_COMPOSE) run --rm migrate
	$(PROD_COMPOSE) up -d --no-deps --force-recreate --wait --wait-timeout 180 backend intelligence-worker intelligence-ai-worker content-media-worker frontend
	$(PROD_COMPOSE) up -d --no-deps --force-recreate --wait --wait-timeout 60 caddy
	$(PROD_COMPOSE) ps

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
