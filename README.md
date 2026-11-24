# AT Tool

A self-hosted organizer for EVE Online tournament teams (Alliance Tournament, Anger Games): comps, fits, scrims with live scoring, RSVP, statistics, and EVE SSO access control. Replaces the practice-organizer Google Sheet.

- **Self-host it:** [docs/SETUP.md](docs/SETUP.md); behind an existing proxy: [docs/DEPLOY.md](docs/DEPLOY.md)
- **Architecture and roadmap:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Research behind the design:** `docs/research/` (local only, not committed: contains the source workbook and notes with pilot names)

## Status

Deployed and in use for the AT XXII season (first production install 2026-09-18, see `docs/DEPLOY.md`). Built so far, in the order of `docs/ARCHITECTURE.md` section 13:

- **Foundations:** EVE SSO login with env-declared admins, invite links, corp/alliance admission rules re-checked hourly, roles plus a leadership flag, an audit log (`apps/accounts`, `apps/audit`); the SDE mirror with automatic CCP downloads (`apps/sde`); tournament rulesets as YAML documents with a validating importer/exporter and a pure rules engine for comp legality, points with duplicate inflation, bans, round scoring and module legality (`apps/rules`, `docs/rulesets.md`). The three shipped rulesets load themselves once the SDE is in.
- **Libraries:** the fit library (`/fits`: EFT and Pyfa parsing, Suggested to Active review, module legality per ruleset) and the comp library (`/comps`: builder with live evaluation, stat rollups, ban theory), both importable from the old workbook (`apps/library`).
- **Scrims** (`apps/scrims`, `/scrims`): roster and opponents, scrim creation with RSVP and roll call, sets with bans in stage order and avalanche bans, rounds copied forward, lineups with comp load, derived points and scores, live updates over server-sent events with presence, soft delete with restore and a per-scrim history drawer, a review tab, the match-log CSV, read-only share links (`/share/<token>`) and a pilot card (`/scrims/:id/me`).
- **Tools:** the comp scratchpad (`/scratchpad`) and the points viewer (`/points`).

Not built yet: the workbook importer for past sessions and the stats pages (Phase 3), the Phase 1 leftovers (ruleset upload page, points-revision importer, hull mapping review, per-object history tabs, team notes, TypeScript engine port) and the small items in section 13.1.

## Layout

```
backend/    Django project (config/, apps/{core,accounts,audit,esi,sde,rules,library,scrims}, fixtures/rulesets, scripts/, tests/, playwright_tests/)
frontend/   React + TypeScript SPA (Vite)
deploy/     docker-compose.yml, Caddyfile, Dockerfiles, entrypoint, crontab, backup script
docs/       SETUP.md (self-hosting), DEPLOY.md (behind an existing proxy), ARCHITECTURE.md (plan and roadmap), rulesets.md (YAML schema); research/ is local-only
```

## Development quick start

```bash
make run               # DB containers + Django :8000 + Vite :5173 in one terminal (see docs/SETUP.md for first-time setup)
make stop              # if Ctrl+C left a uvicorn worker holding port 8000
```

Browse the dev app at `http://127.0.0.1:5173`, not `localhost` (see docs/SETUP.md for why).

## Tests

```bash
make test              # backend pytest (needs the dev DB containers) + frontend tsc (no vitest suites exist yet)
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

## License

The code is under the [MIT License](LICENSE).

EVE Online, the EVE logo, and all associated names, data and imagery (including ship and module names, static data from the SDE, and the tournament rules that the shipped rulesets encode) are the property of CCP hf. They are not covered by this project's license. This project is not affiliated with or endorsed by CCP Games.
