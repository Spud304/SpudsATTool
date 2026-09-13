# AT Tool

A self-hosted organizer for EVE Online tournament teams (Alliance Tournament, Anger Games): comps, fits, scrims with live scoring, RSVP, statistics, and EVE SSO access control. Replaces the practice-organizer Google Sheet.

- **Self-host it:** [docs/SETUP.md](docs/SETUP.md)
- **Architecture and roadmap:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Research behind the design:** `docs/research/` (local only, not committed: contains the source workbook and notes with pilot names)

## Status

Skeleton plus the first Phase 1 slice: the SDE loader (`backend/apps/sde`) that mirrors CCP's JSONL Static Data Export into Postgres, with automatic download, a drop folder, and build tracking on `/api/health`. Phases are built one at a time from `docs/ARCHITECTURE.md` section 13.

## Layout

```
backend/    Django project (config/, apps/core, apps/sde, tests/)
frontend/   React + TypeScript SPA (Vite)
deploy/     docker-compose.yml, Caddyfile, Dockerfiles, entrypoint, crontab, backup script
docs/       setup guide, architecture plan (research/ is local-only)
```

## Development quick start

```bash
make dev-db            # Postgres :5433 and Redis :6380 in Docker
make dev-backend       # Django on :8000 (needs backend/.env, see docs/SETUP.md)
make dev-frontend      # Vite on :5173
make test
```
