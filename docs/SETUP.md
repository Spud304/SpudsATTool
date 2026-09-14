# Self-hosting guide

One Linux VPS with Docker (about 4 GB RAM is plenty), a domain name pointing at it, and an EVE Online developer application. Nothing else.

## 1. Register an EVE SSO application

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
$EDITOR deploy/.env       # set DOMAIN, ACME_EMAIL, EVE_CLIENT_ID, EVE_CLIENT_SECRET, ESI_CONTACT_EMAIL, TEAM_NAME, ADMIN_CHARACTER_IDS
make up                   # pulls images and starts caddy, web, scheduler, db, redis
```

### Admins and first login

Admins are declared, not first-come: `ADMIN_CHARACTER_IDS` lists the EVE character ids that get the admin role when they log in. While it is empty nobody can log in, and the page a denied character sees shows that character's id so you can add it. Everyone else gets in one of three ways, all managed on the Team page by a captain or admin:

- an **invite link** (role, number of uses, expiry),
- an **admission rule** for a corporation or alliance (members are re-checked against ESI hourly and suspended after the grace period if they leave),
- being added explicitly.

Locked out? `docker compose ... exec web python manage.py grant_admin <character id>` grants admin to any character, logged in before or not.

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

## 5. Roles

| Role | Can |
|---|---|
| admin | everything, including granting admin and team settings |
| captain | members, invites, admission rules (below admin), scrims |
| theorycrafter | comps and fits, any scrim field |
| pilot | RSVP, own slot, suggest comps and fits, score if the team allows |
| guest | only scrims they are assigned to, own fits |
| viewer | read-only |

Any member can also carry the **leadership** flag, which unlocks the audit log and pilot notes without full captain rights. Every membership change is written to the audit log with who did it and why.

## 6. Development

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20.19+ or 22 (Node 20.15 works with the pinned Vite 6), Docker.

```bash
cd backend && uv sync && cd ../frontend && npm install && cd ..
make dev-db && (cd backend && uv run python manage.py migrate)
make run                          # DB containers, backend on :8000, frontend on :5173, one terminal
```

`make run` needs GNU Make (`choco install make` on Windows) and Docker Desktop running. The pieces are also available separately: `make dev-db` (Postgres :5433, Redis :6380), `make dev-backend`, `make dev-frontend`.

`backend/.env` for development:

```
DATABASE_URL=postgres://attool:attool@localhost:5433/attool
REDIS_URL=redis://localhost:6380/0
DJANGO_SETTINGS_MODULE=config.settings.dev
ADMIN_CHARACTER_IDS=<your character id>
EVE_CLIENT_ID=<dev app id>          # dev app callback must be exactly http://localhost:5173/auth/callback
EVE_CLIENT_SECRET=<dev app secret>
```

Without an EVE application you can still log in locally: dev settings enable `/auth/dev-login?character_id=1&name=Spud` (goes through normal admission, so put `1` in `ADMIN_CHARACTER_IDS`) or `...&role=pilot` to force a role. The endpoint does not exist under production settings.

Dev settings pin `EVE_CALLBACK_URL` to `http://localhost:5173/auth/callback`; the Vite proxy rewrites the Host header to `:8000`, so the redirect URI cannot be derived from the request in development.

SDE settings (all optional): `INSTANCE_DIR` (default `backend/instance`), `SDE_INCLUDED_FILES`, `SDE_TYPE_CATEGORIES`, `SDE_AUTO_DOWNLOAD`, `SDE_STALE_DAYS`, `SDE_LATEST_URL`, `SDE_DOWNLOAD_URL`. Load ship data locally with `uv run python manage.py import_sde --check-latest` (about 95 MB download).

With both servers up, `http://localhost:5173/scratchpad` evaluates comps against the imported rulesets (`import_ruleset --path fixtures/rulesets/atxxii.yaml` first), and `/fits` holds the fit library. To seed it from the old practice organizer: `python manage.py import_workbook_fits <workbook.xlsx> [--dry-run]` reads its `Fit library` sheet and reports unknown items.

Tests: `make test`, with `make dev-db` running. Backend tests use the dev Postgres on :5433 (override with `TEST_DATABASE_URL`). The typed API client is regenerated with `make gen-client` while the backend is running.
