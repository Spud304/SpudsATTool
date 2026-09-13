.PHONY: init dev dev-db dev-backend dev-frontend test test-backend test-frontend lint gen-client build up upgrade backup logs

COMPOSE     = docker compose -f deploy/docker-compose.yml --env-file deploy/.env
COMPOSE_DEV = docker compose -f deploy/docker-compose.dev.yml

## ---- self-hosting (production, one VPS) ----

init:            ## create deploy/.env with generated secrets (does not overwrite an existing one)
	@test -f deploy/.env && echo "deploy/.env already exists" || ( \
	  cp deploy/.env.example deploy/.env && \
	  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$$(openssl rand -base64 48 | tr -d '\n=/+')|" deploy/.env && \
	  sed -i "s|^FIELD_ENCRYPTION_KEY=.*|FIELD_ENCRYPTION_KEY=$$(openssl rand -base64 32 | tr -d '\n=/+')|" deploy/.env && \
	  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$$(openssl rand -base64 24 | tr -d '\n=/+')|" deploy/.env && \
	  echo "wrote deploy/.env; now set DOMAIN, ACME_EMAIL, EVE_CLIENT_ID, EVE_CLIENT_SECRET, ESI_CONTACT_EMAIL, TEAM_NAME" )

up:              ## start (or update) the production stack
	$(COMPOSE) pull
	$(COMPOSE) up -d --remove-orphans

build:           ## build images locally instead of pulling
	$(COMPOSE) build --build-arg APP_VERSION=$$(git describe --tags --always)

upgrade: backup up   ## backup, then pull and restart with the newest images

backup:          ## take a database backup now
	$(COMPOSE) exec scheduler /app/deploy/backup.sh

logs:            ## follow production logs
	$(COMPOSE) logs -f --tail=200

## ---- development ----

dev-db:          ## start Postgres and Redis for local development (ports 5433 / 6380)
	$(COMPOSE_DEV) up -d

dev-backend:     ## run the Django ASGI server with reload on :8000
	cd backend && DJANGO_SETTINGS_MODULE=config.settings.dev uv run uvicorn config.asgi:application --reload --port 8000

dev-frontend:    ## run the Vite dev server on :5173 (proxies /api, /auth, /ws to :8000)
	cd frontend && npm run dev

dev: dev-db      ## print the two commands to run in separate terminals
	@echo "run in two terminals:  make dev-backend   and   make dev-frontend"

test: test-backend test-frontend

test-backend:     ## needs `make dev-db` running (tests use Postgres on :5433)
	cd backend && uv run pytest -q

test-frontend:
	cd frontend && npx tsc -b && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run ty check
	cd frontend && npm run lint

gen-client:      ## regenerate the typed API client from the running backend
	cd frontend && npm run gen:api
