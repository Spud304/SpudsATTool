# AT Tool

A self-hosted organizer for EVE Online tournament teams (Alliance Tournament, Anger Games): comps, fits, scrims with live scoring, RSVP, statistics, and EVE SSO access control. Replaces the practice-organizer Google Sheet.

- **Self-host it:** [docs/SETUP.md](docs/SETUP.md); behind an existing proxy: [docs/DEPLOY.md](docs/DEPLOY.md)
- **Architecture and roadmap:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Research behind the design:** `docs/research/` (local only, not committed: contains the source workbook and notes with pilot names)

## Status

Skeleton plus two Phase 1 slices: the SDE loader (`backend/apps/sde`) that mirrors CCP's JSONL Static Data Export into Postgres, and the rules layer (`backend/apps/rules`): tournament rulesets as YAML documents (`docs/rulesets.md`, fixtures in `backend/fixtures/rulesets/`), a validating importer/exporter, a pure rules engine for comp legality, points with duplicate inflation, bans and round scoring, and a `/scratchpad` page that exercises it. EVE SSO login with env-declared admins, invite links, corp/alliance admission rules, roles and an audit log are in (`backend/apps/accounts`, `apps/audit`). The fit library (`backend/apps/library`, `/fits`) parses EFT text and Pyfa stats, runs the Suggested → Active review flow and checks module legality against a ruleset. The comp library (`/comps`) builds and browses team compositions against the season's ruleset with live points, legality and a ban simulator. Phases are built one at a time from `docs/ARCHITECTURE.md` section 13.

## Layout

```
backend/    Django project (config/, apps/{core,accounts,audit,esi,sde,rules,library}, fixtures/rulesets, scripts/, tests/, playwright_tests/)
frontend/   React + TypeScript SPA (Vite)
deploy/     docker-compose.yml, Caddyfile, Dockerfiles, entrypoint, crontab, backup script
docs/       setup guide, architecture plan (research/ is local-only)
```

## Development quick start

```bash
make run               # DB containers + Django :8000 + Vite :5173 in one terminal (see docs/SETUP.md for first-time setup)
make stop              # if Ctrl+C left a uvicorn worker holding port 8000
```

Browse the dev app at `http://127.0.0.1:5173`, not `localhost` (see docs/SETUP.md for why).

## Tests

```bash
make test              # backend pytest (needs the dev DB containers) + frontend tsc/vitest
make test-backend      # cd backend && uv run pytest -q
make test-frontend     # cd frontend && npx tsc -b && npm test
make lint              # ruff, ty, eslint
make playwright        # browser tests; needs `make run` up in another terminal
```

Backend tests run against real Postgres on the dev container (`make dev-db`), never SQLite; `TEST_DATABASE_URL` overrides the target. A single test file:

```bash
cd backend && uv run pytest tests/library/test_comps_api.py -q
```

The browser tests are Python (`pytest-playwright`) in `backend/playwright_tests/` and drive the servers you already have running. They log in through the dev-only `/auth/dev-login`, create rows prefixed `pw_` and use reserved test characters, and `make playwright` wipes those first via `manage.py playwright_cleanup`. Watch a run with:

```bash
cd backend && uv run pytest playwright_tests --browser chromium --headed
```
