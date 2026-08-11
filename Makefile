COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
PROD_ENV_FILE ?= .env.production
PROD_ENV_EXAMPLE_FILE ?= .env.production.example
PROD_COMPOSE = docker compose -f infra/docker-compose.prod.yml --env-file $(PROD_ENV_FILE)
first_name ?= Администратор

.PHONY: install up down backend frontend worker worker-ai worker-media migrate docker-migrate migration seed test test-backend test-frontend lint format typecheck api-generate check-nexara prod-check-nexara backfill-question-embeddings prod-backfill-question-embeddings check-s3-multipart prod-check-s3-multipart tochka-webhook prod-tochka-webhook ensure-test-db prod-env-sync prod-preflight prod-init prod-volume-check prod-config prod-migrate prod-up prod-down prod-logs prod-ps prod-admin prod-backup

install:
	cd backend && poetry install
	cd frontend && corepack enable && pnpm install

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

backend:
	cd backend && DEV_AUTH_ENABLED=true poetry run uvicorn app.main:app --reload --port 8000

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
	$(PROD_COMPOSE) run --rm --build --no-deps backend python -m app.configure_tochka_webhook

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

prod-env-sync:
	@test -f "$(PROD_ENV_EXAMPLE_FILE)" || (echo "Missing $(PROD_ENV_EXAMPLE_FILE)" && exit 1)
	@umask 077; touch "$(PROD_ENV_FILE)"; chmod 600 "$(PROD_ENV_FILE)"
	@added_count=$$(awk -F= '\
		FILENAME == ARGV[1] { \
			if ($$0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/) existing[$$1] = 1; \
			next; \
		} \
		$$0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && !($$1 in existing) { print; } \
	' "$(PROD_ENV_FILE)" "$(PROD_ENV_EXAMPLE_FILE)" | wc -l | tr -d ' '); \
	if [ "$$added_count" -eq 0 ]; then \
		echo "$(PROD_ENV_FILE) already contains every example variable"; \
	else \
		printf '\n' >> "$(PROD_ENV_FILE)"; \
		awk -F= '\
			FILENAME == ARGV[1] { \
				if ($$0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/) existing[$$1] = 1; \
				next; \
			} \
			$$0 ~ /^[A-Za-z_][A-Za-z0-9_]*=/ && !($$1 in existing) { print; } \
		' "$(PROD_ENV_FILE)" "$(PROD_ENV_EXAMPLE_FILE)" >> "$(PROD_ENV_FILE)"; \
		echo "Added $$added_count missing variables to $(PROD_ENV_FILE)"; \
	fi
	@chmod 600 "$(PROD_ENV_FILE)"

prod-preflight:
	@sh infra/prod-preflight.sh "$(PROD_ENV_FILE)"

prod-init:
	docker volume create mentoring-platform-production_postgres_data >/dev/null
	docker volume create mentoring-platform-production_redis_data >/dev/null

prod-volume-check:
	docker volume inspect mentoring-platform-production_postgres_data >/dev/null
	docker volume inspect mentoring-platform-production_redis_data >/dev/null

prod-config: prod-preflight
	$(PROD_COMPOSE) config --quiet

prod-migrate: prod-preflight prod-volume-check prod-config
	$(PROD_COMPOSE) build postgres migrate
	$(PROD_COMPOSE) run --rm --no-deps postgres-permissions
	$(PROD_COMPOSE) up -d --wait --wait-timeout 120 postgres
	$(PROD_COMPOSE) run --rm --no-deps migrate

prod-up: prod-preflight prod-volume-check prod-config
	$(PROD_COMPOSE) build postgres migrate backend intelligence-worker intelligence-ai-worker content-media-worker frontend caddy
	$(PROD_COMPOSE) run --rm --no-deps postgres-permissions
	$(PROD_COMPOSE) up -d --wait --wait-timeout 120 postgres redis
	$(PROD_COMPOSE) run --rm migrate
	$(PROD_COMPOSE) up -d --no-deps --force-recreate --wait --wait-timeout 180 backend intelligence-worker intelligence-ai-worker content-media-worker frontend
	$(PROD_COMPOSE) run --rm --no-deps caddy-permissions
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

prod-backup: prod-preflight
	@set -eu; \
		umask 077; \
		mkdir -p backups; \
		chmod 700 backups; \
		backup_file="backups/mentoring-$$(date +%Y%m%d-%H%M%S).dump"; \
		if [ -e "$$backup_file" ]; then echo "Backup already exists: $$backup_file" >&2; exit 1; fi; \
		tmp_file=$$(mktemp "backups/.mentoring-backup.XXXXXX"); \
		trap 'rm -f "$$tmp_file"' 0 HUP INT TERM; \
		$(PROD_COMPOSE) exec -T postgres sh -c 'pg_dump -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -Fc' > "$$tmp_file"; \
		chmod 600 "$$tmp_file"; \
		mv "$$tmp_file" "$$backup_file"; \
		trap - 0 HUP INT TERM; \
		echo "Backup saved to $$backup_file (mode 0600)"
