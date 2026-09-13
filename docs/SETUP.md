# Self-hosting guide

One Linux VPS with Docker (about 4 GB RAM is plenty), a domain name pointing at it, and an EVE Online developer application. Nothing else.

This guide describes the intended deployment. Sections marked *Phase 0* refer to functionality that is planned but not yet implemented; see `docs/ARCHITECTURE.md` section 13 for the roadmap.

## 1. Register an EVE SSO application (Phase 0)

1. Go to https://developers.eveonline.com and log in with any EVE character.
2. Create an application:
   - Connection type: **Authentication & API Access**
   - Scopes: `publicData` (more can be added later for fit pushing)
   - Callback URL: `https://YOUR.DOMAIN/auth/callback`
3. Note the **Client ID** and **Secret Key**.

The callback URL must match your domain exactly, including `https://`.

## 2. Install

```bash
git clone <repo> attool && cd attool
make init                 # writes deploy/.env with generated secrets
$EDITOR deploy/.env       # set DOMAIN, ACME_EMAIL, EVE_CLIENT_ID, EVE_CLIENT_SECRET, ESI_CONTACT_EMAIL, TEAM_NAME
make up                   # pulls images and starts caddy, web, scheduler, db, redis
```

Caddy obtains a TLS certificate automatically once DNS for `DOMAIN` resolves to the box. Ports 80 and 443 must be reachable. Watch the first boot with `make logs`.

## 3. Ship data (SDE)

The app mirrors CCP's Static Data Export into Postgres. Three ways to update it, all safe to repeat:

- **Automatic:** the scheduler checks CCP's build pointer daily and imports a newer build when one appears (`SDE_AUTO_DOWNLOAD=true`, the default).
- **Drop folder:** copy a CCP JSONL zip into the `instance` volume at `sde/incoming/`; the scheduler imports it within five minutes and moves it to `sde/archive/` (or `sde/failed/` with a `.error.txt` note).
- **Command line:** `docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec web python manage.py import_sde --path /app/instance/sde/incoming/<file>.zip` (also `--check-latest`, `--scan-incoming`, `--dry-run`, `--files types,groups`).

`/api/health` reports `sde_build` and `sde_stale`. Records are never deleted on re-import, only flagged removed, so your fits and comps keep valid references.

## 4. Operations

| Task | Command |
|---|---|
| Upgrade to the newest release | `make upgrade` (backs up first) |
| Pin a version | set `ATTOOL_VERSION=v1.2.3` in `deploy/.env`, then `make up` |
| Manual backup | `make backup` |
| Logs | `make logs` |

Backups are `pg_dump` files written nightly to the `backups` volume and, if `BACKUP_RCLONE_REMOTE` is set, copied off-box with rclone. The raw SDE layer is excluded (it is reproducible); after a restore, run `import_sde --check-latest` or drop the archived zip into `sde/incoming/`.

Restore:

```bash
docker compose -f deploy/docker-compose.yml --env-file deploy/.env exec -T db pg_restore -U attool -d attool --clean --if-exists < backups/attool-<stamp>.dump
```

## 5. Development

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20.19+ or 22 (Node 20.15 works with the pinned Vite 6), Docker.

```bash
make dev-db                       # Postgres on :5433, Redis on :6380 (5432 is left free for a local PostgreSQL install)
cd backend && uv sync
uv run python manage.py migrate
make dev-backend                  # :8000
make dev-frontend                 # :5173, proxies /api /auth /ws to :8000
```

`backend/.env` for development:

```
DATABASE_URL=postgres://attool:attool@localhost:5433/attool
REDIS_URL=redis://localhost:6380/0
DJANGO_SETTINGS_MODULE=config.settings.dev
```

SDE settings (all optional): `INSTANCE_DIR` (default `backend/instance`), `SDE_INCLUDED_FILES`, `SDE_TYPE_CATEGORIES`, `SDE_AUTO_DOWNLOAD`, `SDE_STALE_DAYS`, `SDE_LATEST_URL`, `SDE_DOWNLOAD_URL`. Load ship data locally with `uv run python manage.py import_sde --check-latest` (about 95 MB download).

Tests: `make test`, with `make dev-db` running. Backend tests use the dev Postgres on :5433 (override with `TEST_DATABASE_URL`). The typed API client is regenerated with `make gen-client` while the backend is running.
