# AT / Anger Games Team Organizer: Web App Scaffold Plan

## Context

Paige (Spud) ran the AT XXII team's practices and prelim matches out of "Pysno's Arian's ATXXII Practice Organizer v1.0" (a Google Sheet by Arian Felou, exported to `.xlsx`; kept locally in `docs/research/`, not committed). It worked until Google Sheets lag made it painful: the workbook is 42 sheets, 71 MB of XML uncompressed, and ~500,000 formulas, 80% of which are 30 cloned copies of a 16,500-formula practice page. Essentially every formula is a hand-rolled foreign-key lookup (`CONCATENATE` + array `MATCH`) or a per-sheet mirror of lookup tables. The data itself is tiny: 279 hulls, 145 fits, 125 comps, 25 pilots, 30 sessions.

Goal: rebuild it as a self-hostable website with the same functionality, a real backend, live multi-user editing, EVE SSO access control, richer statistics, and a ruleset model that covers both the CCP Alliance Tournament and the community Anger Games.

Decisions Paige has already made:
- Single-team deployment, packaged (Docker Compose) so other teams can self-host their own copy.
- Python backend, TypeScript frontend. Paige asked "Django or Flask?" (answered below).
- Live multi-user editing during a practice night is essential.
- Own VPS with Docker.

Research inputs (kept locally in `docs/research/`, not committed):
- Workbook dissection: `docs/research/workbook_analysis.md`
- Data model + rules engine design: `docs/research/datamodel_design.md`
- The architecture design and the AT/AG/ESI research are summarised in this plan.

---

## 1. Headline recommendations

| Decision | Recommendation | Why |
|---|---|---|
| Backend framework | **Django 5.2 LTS + django-ninja + Django Channels**. Not Flask, not FastAPI. | Django admin gives free CRUD for rules/point tables; ORM + migrations; auth/sessions/CSRF built in; Channels + Redis solves multi-worker websocket fan-out; Alliance Auth precedent means the EVE community knows the stack. Flask would need ~8 add-on libraries to reach Django's baseline and has the weakest websocket story (Flask-SocketIO on eventlet). FastAPI has nicer typing for a pure API, but no admin, no ORM, and its native websockets do not fan out across workers without hand-rolled Redis pub/sub. django-ninja closes ~90% of the FastAPI typing gap (Pydantic schemas, auto OpenAPI). |
| Frontend | **React 19 + Vite + TypeScript**, TanStack Router + Query, Zustand for the live scrim document, Tailwind + shadcn/ui, cmdk command palette, Recharts for stats. Desktop-first, dense, minimal imagery. | A workflow-driven app (Scrims, Comps, Fits, Opponents, Stats, Rules, Team) rather than a rehosted sheet. The scrim page is built around how a night runs: bans per set, a Bo3-or-more of rounds per set, a scoreboard per round. See section 9. |
| Realtime | **REST writes, WebSocket fan-out**. Field-level patch events via Channels + Redis groups. Per-field last-write-wins ordered by DB commit. No CRDT. | Fields are dropdowns/checkboxes; concurrent same-field edits are a tie either way. Keeps validation, rules engine, and audit log in one server-side write path. |
| Database | **Postgres 16** (+ Redis 7 for channel layer, presence, ESI ETag cache). | Row locks and `on_commit` semantics matter for the write path. |
| Rules | **Ruleset as data**: ~12 small typed tables per tournament edition, plus a `JSON extra` for quirks. A pure-Python rules engine (no Django imports) ported to TypeScript for instant UI feedback, both tested against the same JSON fixtures. | AT XXI, AT XXII and Anger Games differ on ~15 knobs (fielded count, cap, inflation, bans, flagship, overtime). Must not become an AT-shaped schema with AG bolted on. |
| Auth | **EVE SSO v2** (authorization code + PKCE, offline JWT validation via JWKS). First login becomes admin. Membership via explicit allowlist, invite links, or corp/alliance admission rules. Hourly affiliation re-check via `POST /characters/affiliation/`. | No passwords to store. Public ESI only in v1 (no scopes). |
| Hosting | **Docker Compose**: Caddy (auto-TLS, serves SPA) + Django ASGI (uvicorn, 2 workers) + scheduler (supercronic) + Postgres + Redis. Nightly `pg_dump` to object storage. | One `.env`, one `docker compose up`. Fits a 4 GB Hetzner/DO box. |
| Background jobs | Management commands on cron in v1; **Django-Q2** (ORM broker, no new infra) when Phase 3's xlsx import needs request-decoupled jobs. | Celery is disproportionate. |
| Repo | Monorepo: `backend/`, `frontend/`, `deploy/`, `docs/`. | |

---

## 2. What the sheet does (features to preserve)

Verified from the workbook. Each maps to a screen or service below.

1. Rules config panel (point cap 200, 10 ships, hull-size limits + duplicate surcharges, overtime threshold, archetype and warp-call vocabularies, links-capable hull list).
2. Points table: official class list (156 classes) + per-hull dimension (279 hulls) with hull-size and links flags.
3. Fit library: EFT text per (hull, fit name), pasted Pyfa summary, regex-parsed DPS/EHP/speed, Active/Inactive/Retired lifecycle, uniqueness per hull.
4. Comp builder with live legality: total vs cap, duplicate inflation, hull-size limits, flagship promotion to a "Flag" size with limit 1, exactly-10-slots integrity.
5. Comp stat rollups from default fits (sum DPS, sum EHP, avg/min speed).
6. Comp browser filtered by status and a comma-separated ban list ("which comps survive these bans").
7. Comp notes and ban theory per comp.
8. Practice sessions: header (date, opponent, system, moveme, MotD, our side A/B), attendance roster with auto "# Flown", up to 8 sets.
9. Per set: our 10 slots (pilot, ship, fit, warp-in, notes, flagship), opponent 10 slots, 4+4 bans + 2 avalanche bans, 4 rounds with Win/Loss/Draw/None/Reset + notes, per-slot per-round "died" checkboxes.
10. One-click comp load into a set (ships, warp-ins, default fits, ship notes, link scripts), with manual override blanking dependent defaults and a per-slot "load default" toggle.
11. Live scorer: points destroyed per side, unspent-points handicap, running differential, colour-coded vs overtime threshold.
12. Ban legality highlighting (flagship exempt) and hull-limit highlighting on the live page.
13. Link/command-burst coordinator: auto-detect links hulls, number link pilots, pull 5 scripts per link pilot from the comp.
14. Per-pilot fit delivery: each pilot copies the full EFT text for their slot, with a dropdown of alternate active fits for that hull.
15. Analysis export: one row per (set, slot, round) with a stable schema (`date, pilot, ship, fate, set, round, outcome, flag, opponent, opp_ship1..10, opp_flag_is, our_archetype, opp_archetype, our_ban_side, team_a_ban1..6, team_b_ban1..6, tournament`) consumed in R.
16. Opsec mode: a single night's page can be shared without exposing the comp/fit libraries.
17. Opponent registry with notes; archetype taxonomy with long definitions.

Known sheet defects not to carry over: a live `#REF!` in the link counter, stale named ranges, the date cell never filled in (tab names carry dates), empty "Pilot Tracking" stub, all Google-only functions (`FILTER`, `REGEXEXTRACT`, `LET/LAMBDA`, `COUNTUNIQUE`) frozen at cached values in the xlsx.

---

## 3. Verified tournament facts the design must accommodate (as of 2026-09-12)

**AT XXII (in progress: Swiss prelims 29 Aug to 13 Sep 2026, 16-team finals 31 Oct to 1 Nov).** Rules: https://www.eveonline.com/news/view/alliance-tournament-xxii-rules-and-regulations
- 10 fielded, 200 cap, 10 min, 125 km arena. Points per ship class with per-hull overrides ("the more specific value applies"). No official machine-readable points table; the community "Quick Comp Creator" Google Sheet (id `1AVYlWlvuMKnA3yuqqDCcAkia8pvhpb9OBcM29WFw5rM`) is the de facto source and had 5 revisions during AT XXII. Point tables must be versioned.
- Duplicate-hull inflation by size: FR +0 (logi/T1 support FR +1), DE +1, CR/IN +2, BC +3, BS +4.
- Max 3 per hull size, battleships max 2 (flagship exempt), max 3 of the same hull. Logistics: 1 logi cruiser OR 1 T1 support cruiser OR 2 logi/support frigates.
- Under-fielded points count for the opponent.
- Bans: 3 per side in prelims, 4 in main, specific hulls, alternating order with a chess-clock pool. Best-of series add "Avalanche bans": loser bans 2, winner bans 1 of the opponent's fielded ships, blind, persisting across the series. Flagships immune to bans. Declaring a "unique" prize hull gives the opponent 2 extra bans.
- Flagship: one pre-declared T1/T2/faction BS (not Bhaalgorn), relaxed module meta rules, 1 use per Bo1 / 1 per Bo3 round / 2 per Bo5, permanently lost if destroyed.
- Tiebreak at 15 min: higher team potential DPS at t=0.
- Roster max 40, max 10 mercs. Format changed from AT XXI (32-team double elim, no BS cap, no inflation, no avalanche).

**Anger Games 7 (April 2026, community, Thunderdome).** Rules live in a Google Doc via Discord (the old eve-nt.uk rules site is dead). From archived text, unverified for AG7: 7 fielded, 75 cap, max 1 of any hull, same logi rule, 2 bans per side snake order ABBA 45 min before match, 10 min + 5 min overtime with increasing game speed, unspent points to opponent, pirate faction ammo banned, no flagship, bracket format varies per edition. Possibly a separate per-kill scoring table (unverified).

**Structured results data:** none from CCP (no ESI tournament routes). Challonge brackets (public API) and community Google Sheets are the only sources. This app's own match log is the team's only structured history, which is the strongest argument for building it.

**EVE SSO/ESI (2026):** discovery doc at `login.eveonline.com/.well-known/oauth-authorization-server`; v2 authorize/token endpoints; JWT `sub = "CHARACTER:EVE:<id>"`, `owner` hash changes on character transfer, `scp` may be string or array, `iss` may or may not include `https://`, `aud` includes client id and `"EVE Online"`; access tokens 20 min. `/verify` was removed March 2026: validate JWTs offline. ESI uses `X-Compatibility-Date` header versioning, OpenAPI 3.1 spec at `esi.evetech.net/meta/openapi.json`, token-bucket rate limits with `X-Ratelimit-*` headers (4xx costs 5 tokens, 3xx costs 1: use ETags). Public: `GET /characters/{id}/`, `POST /characters/affiliation/`. Later scopes: `esi-fittings.write_fittings.v1` (push a fit into the in-game fitting window).

**SDE:** reworked Sept 2025, not backwards compatible. JSONL zip at `https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip`; integer keys encoded as `_key`/`_value`; build pointer at `.../static-data/tranquility/latest.jsonl`; per-build change feeds. Fuzzwork SQLite dumps remain an alternative.

---

## 4. System architecture

```
Browsers (captain / scorer / pilot phone)
        | HTTPS + WSS
     Caddy  (auto-TLS; serves frontend/dist; proxies /api /auth /ws /admin /static)
        |
   Django ASGI (uvicorn x2): django-ninja REST + Channels websocket consumer
        |            |
    Postgres 16    Redis 7 (channel layer, presence, ESI ETag cache)
        ^
   scheduler (same image, supercronic): refresh_affiliations hourly, import_sde weekly, backup nightly
External: login.eveonline.com (SSO), esi.evetech.net, developers.eveonline.com (SDE), object storage (backups)
```

Single team per deployment, but a `Team` row exists and every library/session row FKs it; code never hardcodes team identity. Widening to multi-tenant later is a permission-layer change, not a schema migration.

---

## 5. Data model (condensed; full field lists in `datamodel_report.md`)

Five layers. All operational rows carry `created_at, updated_at, updated_by, row_version`.

**(a) SDE reference, global, replaced by `import_sde`**
- `ShipGroup(group_id PK, name, category_id, default_hull_size, default_can_fit_links, is_tournament_relevant)` with curated columns preserved across re-imports.
- `Ship(type_id PK, name unique, group FK, faction_id, meta_group_id, race_id, tech_level, is_published, hull_size_override, can_fit_links_override, sde_version)`. T1 support hulls (Bantam/Burst/Inquisitor/Navitas → LF; Augoror/Osprey/Exequror/Scythe → LC) are overrides here.
- `CommandBurstScript(code PK: AE AR RR EH ES SO AS SE SH EM IM RD, name, family)`.
- `HullSize` is a TextChoices enum: `FR DE CR BC BS IN CV LF LC FLAG`.

**(b) Ruleset configuration, one cluster per tournament edition**
- `Tournament(code unique e.g. ATXXII/ATXXI/AG7, name, organiser ccp|community, year, server tranquility|thunderdome, dates, rules_url)`.
- `Ruleset(tournament 1:1, fielded_pilots, point_cap, max_same_hull, duplicate_inflation_enabled, duplicate_inflation_mode per_copy_all|escalating|flat_additional, flagship_enabled + 5 flagship behaviour booleans, unique_ship_extra_bans, unspent_points_to_opponent, kill_points_source comp_cost|kill_table, match_length_seconds, overtime_mode none|fixed_extension|gamespeed_ramp, overtime_seconds, overtime_point_threshold, tiebreak_rule, roster_max, merc_max, extra JSON)`.
- `RulesetHullSizeRule(ruleset, hull_size, label, max_per_comp, duplicate_surcharge)`: direct port of `Configurables!J8:M17`.
- `CompQuota(ruleset, code, label, max_units)` + `CompQuotaMember(quota, hull_size|ship_class|ship, weight)`: expresses "1 LC or 2 LF" as weights 2/1 against max 2, which the sheet could not.
- `ShipClass(ruleset, name, hull_size, source_text)`: the official class list (156 rows).
- `RulesetShip(ruleset, ship, ship_class, hull_size, legality legal|banned|unlisted, flagship_eligible, can_fit_links, mapping_confidence)`: the edition's ship dimension (the sheet's `Point values!F:K`, 279 rows). Banned-hull list = rows with `legality=banned`.
- `PointTableVersion(ruleset, purpose cost|kill, version_no, label, source_url, effective_from, is_current, raw_text)` + `PointTableEntry(version, ship_class|ship, points)`: class default with hull override, versioned.
- `Stage(ruleset, code prelim|bracket|final|single, best_of, bans_per_side, ban_order_pattern e.g. "ABBAAB", bans_are_blind, ban_targets, ban_deadline_minutes_before, chess_clock_seconds, avalanche_* fields, flagship_uses)`.
- `RulesetTextSection(ruleset, heading, body_markdown)`: module/implant/booster rules as reference text, not evaluated in v1.

Worked example of the same schema holding three editions:

| Knob | ATXXII | ATXXI | AG7 |
|---|---|---|---|
| fielded / cap | 10 / 200 | 10 / 200 | 7 / 75 |
| max_same_hull | 3 | null | 1 |
| inflation | on | off | off |
| BS max_per_comp | 2 (+FLAG row max 1) | null | null |
| flagship | on | on | off |
| stages | prelim Bo1 3 bans; bracket Bo3 4 bans avalanche; final Bo5 flagship x2 | bracket Bo3 4 bans | single, 2 bans ABBA, 45 min deadline |
| overtime | none (tiebreak potential DPS) | none | gamespeed_ramp 300 s |

**(c) Team library**
- `Pilot(team, name, status, roles_text, notes)` + `PilotCharacter(pilot, character, is_main)` (a pilot may have many alts or none) + `RosterEntry(team, tournament, pilot, is_merc, is_captain)`.
- `Opponent(team, name, notes, alliance_id?, corporation_id?)`, `Archetype(team, name, description, is_retired)`, `WarpInLabel(team, label)`.
- `Fit(team, ship, name, status suggested|active|inactive|retired, eft_text, pyfa_summary, dps, volley, ehp_k, speed_ms, sig_radius_m, cap_stable_pct, targeting_range_km, stats_parse_ok, created_by, reviewed_by)` unique (team, ship, name). Only `active` fits appear in scrim and comp pickers.
- `Comp(team, ruleset, name, status suggested|construction|active|inactive|retired, archetype, notes, ban_theory, created_by, reviewed_by)` + `CompSlot(comp, slot_no, ship, is_flagship, is_unique_ship, warp_in_km, default_fit, ship_note, link_script_1..5)`; N slots pre-created from `ruleset.fielded_pilots`. The scrim comp picker shows `active` comps only, with a toggle to include `construction`. `suggested` is the entry state for anything a pilot proposes; a theorycrafter or captain promotes it to `construction` or `active`, or retires it.

**(d) Operational session data (one row per sheet "cell group")**
- `Session(team, ruleset, stage, point_table_version pinned, kind practice|scrim|tournament_match|warmup, title, date, opponent, system_name, moveme_system, motd, default_our_side, is_archived, import_source)`.
- `SessionAttendance(session, pilot, rsvp yes|no|maybe|none, rsvp_reason, rsvp_at, attendance present|late|absent|no_show|none, removed_by, removed_reason, removed_at)`. RSVP is the pilot's own signup before the scrim (a reason is required for `maybe`); attendance is what actually happened, set on the night. Removing a pilot who said yes but did not appear is an explicit "Remove as no-show" action that sets `attendance=no_show`, records who did it and why, and writes an `AuditLog` row. "# Flown" is derived. Unique (session, pilot).
- `Set(session, index, label, comp, our_archetype, opp_archetype, our_side, stage override, tactics_note, link_note)`: a set is one ban phase plus the series of rounds fought under those bans (normally a Bo3, often more). Creating a set pre-creates ban rows per stage, 4 `SetWarpCall`, and round 1.
- `Round(set, round_no, outcome win|loss|draw|none|reset, notes, started_at, ended_at, went_to_overtime)`. Adding a round copies the previous round's lineup on both sides, so a Bo3 with no changes costs no extra input, while avalanche-ban swaps between games are recorded honestly.
- `Assignment(round, side US|OPP, slot_no, pilot, opp_pilot_name, ship, is_flagship, is_unique_ship, warp_in_km, fit, fit_text_snapshot, load_default, custom_note, repeat_note, link_script_1..5, died, died_at_seconds, + server-owned cached: points, base_points, inflation, effective_hull_size, link_index, flags[])`: one row per (round, side, slot). `died` is a toggle anyone with scoring rights can flip either way. This replaces the earlier separate per-round result table.
- `Ban(set, side A|B, kind standard|avalanche|unique_extra, index, ship|ship_class, sequence_no, in_effect_from_round)`: standard bans apply from round 1; avalanche bans added after game N apply from round N+1 and persist for the set.
- `ChangeEvent(team, session, seq, table, pk, field, old, new, actor, op_id, at)`: append-only field-level stream for scrim edits; doubles as the websocket replay buffer.
- `AuditLog(team, actor, action, target_type, target_id, target_label, reason, before JSON, after JSON, at)`: append-only, team-wide record of significant actions: deleting or retiring a comp or fit, changing a comp/fit status, promoting a suggestion, removing a pilot from a scrim (no-show or otherwise), deleting a scrim, set or round, changing roles or admission rules, creating or revoking share links, editing pilot notes. Written by the service layer, never by clients. Retained indefinitely; readable by captains and admins at `/team/audit` and as a History tab on each object.
- Auth: `User` (custom, no password), `EveCharacter(character_id PK, name, owner_hash, corp, alliance, user)`, `Membership(user, role, status, source)`, `AdmissionRule(kind corp|alliance, entity_id, default_role)`, `Invite(token, role, uses_left, expires)`, `ShareLink(session, token, expires, require_login, revoked)`, later `EsiToken`.

**(e) Analytics: SQL views, no precomputation**
`v_match_log` (one row per US assignment per round) reproduces the sheet's export columns in the exact order and names, with extra keys appended, so the R workflow keeps working. Plus `v_round_score`, `v_pilot_round_stats`, `v_pilot_ship_stats`, `v_ship_survival`, `v_comp_results` (comp W/L by opponent and archetype), `v_ban_frequency`, `v_opponent_ship_usage`, `v_opponent_archetypes`, `v_session_attendance`, `v_pilot_reliability` (RSVP answers, attendance rate, no-shows after a yes). Materialise only if slow.

---

## 6. Rules engine

Pure Python package `backend/apps/rules/engine/` (stdlib dataclasses only, no Django), mirrored in `frontend/src/engine/`, both run the same JSON fixtures.

- `evaluate_comp(spec, point_table, hulls, slots, bans=(), our_side=None) -> CompEvaluation`: per-slot base points (hull override else class), inflation by mode, effective hull size (FLAG for flagship), violations (`OVER_CAP, UNDER_CAP info, OVER_SIZE_LIMIT, OVER_SAME_HULL, QUOTA_EXCEEDED, BANNED, ILLEGAL_HULL, UNLISTED_HULL, MULTIPLE_FLAGSHIPS, FLAGSHIP_NOT_ELIGIBLE, EMPTY_SLOT, WRONG_SLOT_COUNT`), link indexes, unspent points.
- `score_round(spec, us_eval, opp_eval, us_dead, opp_dead, elapsed, ...) -> RoundScore`: points conceded per side including the unspent handicap, differential (theirs minus ours, as the sheet's `U21`), phase regulation|overtime|ended, overtime indicator vs threshold, tiebreak hint.
- `ban_sequence(stage, first_side)`, `avalanche_allocation(stage, winner)`, `extra_bans_for_unique(...)`, `flagship_uses_remaining(...)`.
- `parse_pyfa_summary(text)`, `parse_eft_header(eft)` (server only).
- Server is authoritative: every write to a set recomputes the whole set's cached values and broadcasts a compact `derived` block; the TS port gives instant feedback before the round trip.

**Inflation discovery to resolve before implementing legality:** the sheet charges `(copies - 1) x surcharge` on every copy (two Astartes = 36 + 36 = 72, and OF 99 set 1 totals exactly 200 under that reading). The official text is ambiguous between that, escalating (33/36/39), and flat per extra copy. The engine supports all three via `duplicate_inflation_mode`; Paige should check one real AT XXII comp total against the Quick Comp Creator before Phase 1 ships. The xlsx importer cross-checks every imported set's total under `per_copy_all` as an acceptance test.

Golden tests transcribed from the workbook: OF 99 set 1 (200 exact, two Astartes, two Deacons), over-cap comp, 1 LC + 1 LF quota violation, flagship BS as third battleship, banned flagship exempt, AG7 7-slot comp with duplicate hull, 190-point comp handicap, overtime colour thresholds.

---

## 7. Realtime design

- **Write path:** client optimistic-applies → `PATCH /api/sessions/{s}/assignments/{id}` `{fields, base_version, op_id}` → service: `SELECT ... FOR UPDATE`, apply per-field LWW, bump `row_version`, assign session-monotonic `seq`, recompute the set through the engine, insert `ChangeEvent`, commit → `transaction.on_commit` group-sends to Channels group `session.{s}` → all clients apply.
- **Events (Pydantic models, JSON Schema exported → TS types):** `entity.patch {seq, entity, id, version, fields, derived?, actor, ts, op_id}`, `entity.bulk` (comp load, clear set), `entity.create/delete`, `presence.state/update/leave`, `resync_required`, `auth.revoked`. Uplink only: `subscribe {session_id, since_seq?}`, `focus`, `ping`.
- **Conflicts:** per-field LWW by commit order; response flags `stale: true` if `base_version` was behind so the UI can flash cells changed underneath. Text notes get a 400 ms debounce and a presence soft-lock. `op_id` makes retries idempotent.
- **Presence:** Redis hash per session, 25 s ping / 60 s TTL, coloured focus outlines on cells (also the soft lock).
- **Resync:** subscribe before snapshot, buffer, `GET /api/sessions/{id}/full` returns document + `event_seq`, apply buffered events above it; gap detection requests replay from `ChangeEvent` (cap 500, else full resync); exponential backoff reconnect; inputs disabled after 5 s offline.
- Rejected: SSE (no uplink for presence), Postgres CDC realtime (raw rows, not derived state), Yjs/CRDT (moves authority to clients, overkill for dropdown data).

---

## 8. Auth and roles

- **Login:** `/auth/login` → SSO authorize (PKCE + client secret, scope `publicData`) → `/auth/callback` → token exchange → offline JWT validation (`PyJWKClient`, accept both `iss` forms, `aud` includes client id) → upsert `EveCharacter` (detach from user if `owner_hash` changed) → fetch corp/alliance → admission → Django session login. Same-origin session cookie + CSRF header; Channels `AuthMiddlewareStack` reuses the cookie. No bearer tokens in the browser.
- **Admission order:** no admin exists → this login is admin (first-run bootstrap); explicit active `Membership`; valid `Invite` token; matching `AdmissionRule` (corp/alliance); else "ask your captain" page.
- **Roles:** admin, captain, theorycrafter, pilot, guest, viewer, plus a per-member `is_leadership` flag (granted by captain or admin) that unlocks pilot notes and the audit log for selected co-captains without giving them full captain rights. Admin/captain: settings, rulesets, sessions, the audit log, pilot notes. Theorycrafter: libraries (including promoting or retiring suggested comps and fits) and any session field. Pilot: RSVP to any upcoming scrim, own slot fields (fit choice, own note), toggle deaths when `Team.pilots_can_score` is on (default on), read sessions, browse the library when `Team.pilots_can_browse_library` is on (default on), and **create or edit their own `suggested` comps and fits** (cannot set any other status). Guest: only sessions where a linked pilot is assigned, only own fit text. Enforcement in one module `accounts/permissions.py`, tested against the matrix.
- **Alts:** `/auth/link` attaches another character to the current user. `Pilot` stays distinct from `EveCharacter` (mercs and historical pilots may never log in) with an optional link that powers the "my fit" view.
- **Affiliation re-check:** hourly bulk `POST /characters/affiliation/`; rule-sourced memberships that no longer match are suspended after a 24 h grace, sessions killed, `auth.revoked` pushed.
- **Opsec share links** replace the sheet's per-page lookup mirror: `/share/{token}` renders one session read-only with fit text only for assigned slots, no library navigation, revocable.

---

## 9. Frontend

Design principles: a desktop web app built around the team's workflow, not a rehosted sheet. Dense and fast, minimal imagery (16 px type icons in pickers at most), monospace numbers, dark and light themes, keyboard-first (command palette on Ctrl+K to jump to any comp, fit, pilot, opponent, or scrim), every derived value shown with the reason behind it (hover a points figure to see base + inflation; hover a red badge to see the rule). Realtime is ambient: presence avatars in the header, a coloured outline on a field someone else is editing, a brief highlight when a remote change lands.

### 9.1 Information architecture

Top nav: **Dashboard · Scrims · Comps · Fits · Opponents · Stats · Rules · Team**, plus a ruleset switcher (ATXXII / AG7) that scopes Comps, Rules and Stats, and the user menu.

| Area | Routes | Purpose |
|---|---|---|
| Dashboard | `/` | Upcoming scrims with the pilot's own RSVP buttons (Attending / Unable / Maybe + reason) and the RSVP tally, last scrims with per-set W-L, a review queue of suggested comps and fits (theorycrafters and captains), library health alerts (comps made illegal by a points revision, comps containing newly banned hulls, fits without Pyfa stats), attendance summary. |
| Scrims | `/scrims`, `/scrims/new`, `/scrims/:id`, `/scrims/:id/sets/:set` | Upcoming list with RSVP per pilot and a roll-call view for the captain (who is in, out, maybe and why); past list with results. The live tool is section 9.2. |
| Comps | `/comps`, `/comps/:id`, `/comps/compare?a=&b=` | Library, builder, ban simulator, compare. Section 9.3. |
| Fits | `/fits`, `/fits/:id` | Library grouped by hull; EFT editor; parsed stats; usage. Section 9.4. |
| Opponents | `/opponents`, `/opponents/:id` | Notes, history against them, hulls and bans they have shown. |
| Stats | `/stats`, `/stats/pilots`, `/stats/ships`, `/stats/comps`, `/stats/bans`, `/stats/export` | Dashboards and the match-log export. Section 9.5. |
| Rules | `/rules/:ruleset` | Active ruleset knobs, hull-size table, point table with version history and diff, banned hulls, text sections. Edit via Django admin link in v1. |
| Team | `/team/members`, `/team/pilots`, `/team/notes`, `/team/audit`, `/team/vocab`, `/team/settings` | Members and roles (including the leadership flag), invites, admission rules, pilot roster with character links, archetype and warp-call vocabularies, team toggles. **Notes** (leadership only): one page per pilot with dated notes, plus that pilot's reliability summary alongside. **Audit** (captains, admins, leadership): filterable log of who did what, when, and why, with links to the affected object. |
| Share | `/share/:token` | Read-only single scrim for opsec sharing. |
| Pilot card | `/scrims/:id/me` | Simple page showing the logged-in pilot's slot in the current round. Low priority; desktop is primary. |

### 9.2 Scrim page (the core)

Layout: a left rail with scrim context, a main area for the selected set, and a collapsible right drawer for fits.

**Left rail**
- Scrim header: opponent, date, kind, system and moveme, MotD, ruleset and stage badge, our side (Team A / B), share link, history, export.
- Attendance: pilot list pre-sorted by RSVP (attending, maybe with reason shown, unable, no answer) with present/late/absent toggles for the night, a "Remove as no-show" action that asks for a reason and is audited, and a "# flown tonight" count; presence dots for pilots who are logged in. The pilot dropdown in lineups groups attending pilots first.
- Set stepper: one card per set showing label, comp name, ban summary (our 4 · their 4 · avalanche), and round results as W/L pips. "+ New set" offers "copy previous set" (comp and pilots carried, bans cleared) as the default.

**Main area, one set at a time.** Three stacked panels, all always visible (captains bounce between them), each with a compact and an expanded state:

1. **Ban board.** Two columns (Team A, Team B) of ban chips laid out in the stage's ban order (`ABBAAB` etc.) with the order number on each chip; a third row for avalanche bans labelled "after R1", "after R2". Adding a ban is a typeahead over legal hulls. Banned hulls immediately show struck through with a red badge everywhere in this set (comp picker, lineup rows, opponent rows), and the comp picker filters to comps that survive the bans by default with a toggle to show all. A "we are A/B" switch flips which column counts against us. After a round is marked, the app prompts the avalanche allocation from the stage rules (loser bans 2, winner bans 1) and pre-creates the chips.

2. **Lineups.** Side by side: **Ours** and **Theirs**, each N rows for the selected round (round tabs across the top of the panel: R1 R2 R3 +; a new round copies the previous lineup and highlights any cell later changed from the prior round).
   - Ours: comp picker at the top (shows points, status, archetype, "3 hulls banned" warnings); rows: pilot dropdown with a "Suggested" group (who flew this hull or a hull of the same size most recently, how many times), ship typeahead, fit select (active fits for that hull, default from comp), warp-in, links number and scripts (auto-numbered, editable), note, flagship toggle, points with inflation shown as "33 +3". Row-level badges: over size limit, banned, quota exceeded. A budget bar under the table: total / cap with per-size segments and unspent points called out. Load-default toggle per row, override-blanks-defaults semantics preserved from the sheet.
   - Theirs: archetype select, rows of ship typeahead + flagship toggle + note, same budget bar. "Paste lineup" accepts ten ship names from chat and resolves them.
   - Warp calls (1st to 4th) and tactics note live in the panel header.

3. **Round scoreboard.** For the selected round: two columns of ship chips (ours labelled with pilot name), one click toggles dead and moves the chip's points to the other side's total; toggling again undoes it. Big numbers: points destroyed by us, by them, differential with colour vs the overtime threshold, unspent-points handicap shown explicitly, a timer (start, pause, reset) that displays regulation / overtime / ended per the ruleset, outcome buttons (Win / Loss / Draw / Reset), round note. A **Focus mode** button expands the scoreboard to full screen for the scorer during the fight; everything else in the app keeps updating underneath. Anyone with scoring rights can toggle a death; the audit drawer shows who toggled what.

**Right drawer: Fits for this round.** One card per our slot: pilot, ship, fit name, warp-in, scripts, notes, EFT text in a monospace block, Copy button (Phase 4: Push to EVE). Filter "mine" highlights the logged-in pilot's card; the pilot's own row in the lineup is also highlighted so a pilot with EVE open on another monitor finds their fit in one glance.

**Post-scrim:** a Review tab on the scrim summarising sets, rounds, W-L, points differential per round, deaths per pilot, and the bans, with one-click export to CSV.

### 9.3 Comps

- **List**: table with status, archetype, points, DPS, EHP, min speed, hull chips (text), last used, W-L; filters by status (default Active + Construction), archetype, ruleset; a **ban simulator** input at the top ("Sleipnir, Curse, Sentinel") that greys out affected comps with the offending hulls named, replacing the sheet's Comp View. A **Suggested** tab lists member proposals with who suggested them and Promote / Retire actions for theorycrafters; any member can open the builder and save a comp, which lands in Suggested.
- **Builder / detail**: left, the N slot rows (ship typeahead, flagship toggle, warp-in, default fit, note, five script selects); right, a sticky panel with the budget bar and per-size counts (BS 2/2, BC 3/3, ...), the legality list (each violation names the rule and the slots), stat rollups (sum DPS, sum EHP, avg and min speed, total potential DPS for the t=0 tiebreak), and tabs for Notes, Ban theory, and History (every set the comp was fielded in with results). Actions: clone, clone to another ruleset, retire, "use in scrim".
- **Compare**: two comps side by side with slot diffs and stat deltas.

### 9.4 Fits

- List grouped by hull with status, DPS, EHP, speed, "used in N comps", last flown, survival rate.
- Detail: EFT textarea (monospace) with header validation against the hull, Pyfa summary paste with parsed stats displayed, lifecycle, usage list.
- "New from clipboard": paste an EFT block, the app resolves hull and name from the header. Any member can submit a fit this way; it lands in Suggested until a theorycrafter activates it, and suggested fits never appear in scrim pickers.

### 9.5 Stats

Filters everywhere: tournament, date range, opponent, kind (practice vs tournament match). Views:
- Overview: rounds won/lost over time, points differential distribution, attendance per session.
- Pilots: rounds flown, sessions attended, survival rate, win rate, distinct hulls; drill into a pilot's per-hull record.
- Reliability (per pilot, per period): RSVP counts by answer (yes / no / maybe / no answer), attendance rate, times attended after a "maybe", times marked absent or removed as no-show after saying yes, late count. Backed by `v_pilot_reliability` over `SessionAttendance`. Shown on the Stats page for leadership and next to the pilot's notes.
- Ships: fielded count, deaths, survival by side (ours vs theirs).
- Comps: W-L and average differential by comp, by opponent, by opponent archetype (a matchup matrix of our archetype vs theirs).
- Bans: what we ban and what gets banned against us, by opponent.
- Opponents: hull usage and archetype tendencies per opponent.
- Export: the match log CSV in the sheet's column order, plus a per-view CSV.
Charts with Recharts; tables with TanStack Table (sortable, filterable, column visibility).

### 9.6 Technical shape

- Routes via TanStack Router; server state via TanStack Query with long stale times for lookups (ships, fits per hull, comps, pilots, vocabularies) invalidated by a team-wide `library.changed` event.
- One Zustand store per open scrim holding the normalised live document (`sets, rounds, assignments, bans, warpCalls, derived, presence, seq, pending`), reducers `applyPatch / applyBulk / rollback / setPresence`; each field component subscribes to its own slice so a remote change re-renders one control.
- Optimistic updates through `useMutateField`, the TS rules-engine port gives instant budget and legality feedback before the server's authoritative evaluation arrives.
- Components: shadcn/ui primitives, `cmdk` for typeaheads and the command palette, virtualised lists for the ~300-hull picker. Tables are semantic `<table>` elements with a small keyboard hook (arrows move focus, Enter opens a picker, Space toggles, Ctrl+C copies a fit).
- API client generated with `openapi-typescript` + `openapi-fetch`; WS event types generated from exported JSON Schema; CI fails on drift.
- Desktop-first (1280 px and up). Below that, panels stack and the fit drawer becomes a sheet. Phone support is limited to the pilot card and read-only views.

---

## 10. SDE, ESI, fits

- `manage.py import_sde`: compare build from `latest.jsonl` with `SdeBuild`; stream the JSONL zip to disk; decode `_key/_value`; import category 6 (Ship) groups and published types with `bulk_create(update_conflicts=True)`; mark missing types unpublished instead of deleting; `--with-modules` and `--with-dogma` optional for future fit parsing. Weekly on the scheduler; admin "import now" later. Group → hull-size seed keyed by group name (Frigate/Assault Frigate/Interceptor/Covert Ops/EAF/Bomber/Expedition → FR; Logistics Frigate → LF; Destroyer/Interdictor/Command Destroyer/Tactical Destroyer → DE; Cruiser/HAC/Recons/HIC/T3C/Flag Cruiser → CR; Logistics → LC; Combat BC/Attack BC/Command Ship → BC; Battleship/Black Ops/Marauder → BS; Industrial/Blockade Runner/DST → IN; Corvette → CV; capitals and shuttles not relevant). Verify ids by name at seed time, not from memory.
- Ship-class auto-mapping for `RulesetShip.ship_class`: (1) class name starts with `"{ship.name} ("`; (2) alias dict by group and faction set (empire vs pirate faction ids verified against `factions.jsonl`); (3) admin review queue for the rest.
- ESI client (`httpx`): fixed `X-Compatibility-Date` from settings, contact-info User-Agent, Redis ETag cache with `If-None-Match`, honour `X-Ratelimit-Remaining`/`Retry-After`, circuit breaker on 5xx. v1 endpoints: `GET /characters/{id}/`, `POST /characters/affiliation/`.
- Fits: v1 keeps Pyfa paste parsing (same three regexes plus volley, sig, cap, range). Future stats engine options ranked: `dogma-engine` (Rust) compiled to WASM in the browser, Rust sidecar, or keep paste parsing. Pyfa-as-library is not recommended. `stats_source` column keeps all options open.
- Phase 4 ESI fit push: `esi-fittings.write_fittings.v1`, encrypted refresh tokens on `EsiToken`, per-character consent.

---

## 11. Deployment and ops (`deploy/`)

| Service | Notes |
|---|---|
| `caddy` | Caddy + baked `frontend/dist`; auto-TLS; ~15-line Caddyfile: proxy `/api /auth /ws /admin /static` to `web:8000`, SPA fallback otherwise. |
| `web` | `uvicorn config.asgi:application --workers 2 --proxy-headers`; entrypoint waits for db → `migrate` → `collectstatic` → `bootstrap` → serve; healthcheck `/api/health`. |
| `scheduler` | same image, `supercronic`: hourly `refresh_affiliations`, weekly `import_sde`, nightly `backup.sh` (`pg_dump -Fc` → volume → optional `rclone` to B2/S3/Hetzner), hourly `cleanup_expired`. |
| `db` | `postgres:16-alpine`, `shared_buffers=256MB`, volume `pgdata`. |
| `redis` | `redis:7-alpine`, 64 MB, no persistence. |

`.env` is the only file a self-hoster edits: `DOMAIN, ACME_EMAIL, SECRET_KEY, FIELD_ENCRYPTION_KEY, POSTGRES_PASSWORD, EVE_CLIENT_ID, EVE_CLIENT_SECRET, ESI_CONTACT_EMAIL, TEAM_NAME`, optional `BACKUP_RCLONE_REMOTE, ESI_COMPAT_DATE, ATTOOL_VERSION`. `bootstrap` creates the `Team`, loads the ATXXII starter ruleset fixture (values from `Configurables`), runs `import_sde` if `Ship` is empty, refuses placeholder secrets. First EVE login becomes admin and lands on a setup checklist. `make upgrade` = backup → pull → up. Images tagged `vX.Y.Z` on GHCR (amd64 + arm64). Self-hosters must register their own EVE SSO application with their callback URL: document this in `docs/SETUP.md`, it is where a non-developer captain will get stuck.

Dev: `docker-compose.dev.yml` runs Postgres + Redis only; Django and Vite run natively with Vite proxying `/api /auth /ws`. `DEV_LOGIN_AS=<character_id>` local-only login shortcut for Playwright, refused when `DEBUG=False`.

---

## 12. Repo layout

```
<repo>/
  backend/
    pyproject.toml (uv: django, django-ninja, channels, channels-redis, httpx, pyjwt[crypto], psycopg[binary], environs, cryptography, openpyxl)
    manage.py  config/{settings/,asgi.py,urls.py,api.py,routing.py}
    apps/accounts (User, EveCharacter, Membership, AdmissionRule, Invite, ShareLink, sso.py, permissions.py)
    apps/audit (AuditLog, record() helper called from every service)
    apps/esi (client.py, refresh_affiliations)      apps/sde (ShipGroup, Ship, SdeBuild, import_sde)
    apps/rules (Tournament, Ruleset, ..., engine/, admin.py)
    apps/library (Fit, Comp, CompSlot, Pilot, PilotNote, Opponent, Archetype, WarpInLabel, eft.py, pyfa.py)
    apps/sessions (Session, Set, Round, Assignment, Ban, ChangeEvent, services.py, events.py, consumers.py)
    apps/analytics (views SQL, match_log export)     apps/importer (xlsx.py + per-sheet modules)
    apps/core (Team, bootstrap, health)              fixtures/ruleset_atxxii.json   tests/
  frontend/  (Vite, React 19, TS strict; src/routes, src/features/{session,library,auth,stats}, src/engine (TS port), src/lib/{api,ws} generated)
  deploy/    docker-compose.yml, docker-compose.dev.yml, Caddyfile, crontab, backup.sh, Dockerfile.backend, Dockerfile.frontend, .env.example
  docs/      SETUP.md, ARCHITECTURE.md, CHANGELOG.md, research/ (the two scratchpad reports)
  .github/workflows/ ci.yml, release.yml      Makefile (init, dev, test, gen-client, upgrade, backup)
  docs/research/  (local only, gitignored: the source .xlsx and raw analysis notes)
```

Testing: pytest golden + Hypothesis tests for the engine; pytest-django against real Postgres for services (concurrency test: two threads patch one row → versions 1 and 2, two events in seq order); Channels `WebsocketCommunicator` tests for subscribe/replay/resync; parametrised permission-matrix test; SSO JWT tests with a local RSA key and fake JWKS; vitest for reducers and the TS engine port on the shared fixtures; Playwright smoke with two browser contexts (A changes a ship, B sees it within 1 s, totals update; `/me` shows the fit). CI: ruff, mypy (strict on engine and services), pytest with Postgres/Redis services, tsc, eslint, vitest, build, generated-client drift check, Compose-based e2e, release images on tag.

---

## 13. Phased roadmap

Sizes relative; assume a solo dev at ~10 h/week. Phase 2 is the critical path; start a thin vertical slice of it (one set, ships + death ticks + totals, two browsers) right after Phase 0 to de-risk realtime before the bulk of Phase 1 CRUD.

| Phase | Scope | Size | Exit criterion |
|---|---|---|---|
| **0 Skeleton + auth** | git init; monorepo; Compose with Caddy TLS; Django + ninja + Channels hello; EVE SSO login/callback/link; first-login admin; Team/Membership/roles/invites/admission rules; generated TS client; SPA shell; CI green; `docs/SETUP.md`; copy research reports into `docs/research/`. | M | A stranger self-hosts from the README and logs in with an EVE character; a second character is rejected until invited. |
| **1 Libraries + validation** | `import_sde`; Tournament/Ruleset/hull-size/quota/stage tables in Django admin with the ATXXII fixture; official points paste importer → ShipClass + PointTableVersion; RulesetShip auto-mapping + review queue; Fit library (EFT + Pyfa parse, lifecycle incl. Suggested → Active flow); Comp builder with live evaluation and stat rollups, open to all members with the Suggested status and a review queue; Comp browser with status + ban filter; comp notes/ban theory; pilot roster; opponent registry; scrim creation with RSVP (attending / unable / maybe + reason) on the dashboard; `AuditLog` written by every library and membership service action, with `/team/audit` and per-object History tabs; leadership flag and `/team/notes`; rules engine in Python and TS with shared fixtures. | L | Every validation the sheet performs is reproduced and tested; all 145 fits and 125 comps can be loaded (via the Phase 3 importer run early, or CSV). |
| **2 Live scrim page** | Session/Set/Round/Assignment/Ban/ChangeEvent; write service with locking, LWW, seq, recompute, broadcast; consumer, presence, resync; the scrim page per section 9.2: set stepper, ban board with avalanche prompts, per-round lineups copied forward with pilot suggestions, comp load with override-blanks-defaults, link numbering + scripts, round scoreboard with click-to-toggle deaths, timer and focus mode; fits drawer; review tab; share links; audit drawer. Pilot card page only if cheap. | XL | A real weekly scrim is run entirely in the app with three simultaneous editors. |
| **3 History + analytics** | openpyxl importer for the workbook (libraries + 30 sessions; set blocks located by scanning column Y for "Set #"; dates from tab names; hidden sheets archived; hidden column M ban codes; cross-checks against cached totals and the sheet's own data-log rows); Django-Q2 for the long-running import; `v_match_log` CSV/API export; stats pages (pilot survival, ship death rates, comp W/L by opponent and archetype, ban frequency, attendance over time, per-opponent history). | M-L | Historical OF 99 renders identically to the sheet; the R users get the same CSV. |
| **4 Nice-to-haves** | ESI fit push; Anger Games ruleset row (exercises data-driven rules; add code rules only if needed); Challonge bracket import; opponent scouting (zKillboard lookups); `dogma-engine` WASM fit stats; team-wide library change notifications; flagship series tracking. | S-M each | Independent; ship as demanded. |

---

## 14. Decisions still open (recommended defaults in bold; the plan proceeds on these unless Paige says otherwise)

1. **Duplicate inflation semantics:** sheet = every copy pays `(copies-1) x surcharge`. Verify against a real AT XXII comp; **default `per_copy_all` to match the team's existing 200-point comps**.
2. Flagship counts toward same-hull limit and inflation: **yes to both** (toggles exist).
3. Kill points when a duplicated hull dies: **base + inflation** (what the sheet sums).
4. Anger Games: separate kill table, flagship, ban granularity: **unknown until the AG Google Doc is obtained from the AG Discord**; schema supports either.
5. Our side A/B: **per set with a session default** (as the sheet).
6. Rounds per set: **a set starts with round 1 and rounds are added as fought**, each copying the previous lineup; the sheet's fixed 4 disappears.
7. Sessions pin the point-table version at creation; re-evaluating under a newer revision: **offered as an explicit UI action, not automatic**.
8. Comps belong to exactly one ruleset; **"clone to ruleset" service** for AG variants.
9. Who ticks death checkboxes: **any pilot by default** (`pilots_can_score`).
10. Shared text notes with soft lock vs per-user notes: **shared + soft lock**; revisit if it bites.
11. Opsec share links: **yes, in Phase 2**.
12. Dates for tabs without one (`Prelims Day 1-5`, `Ivy League Warmup`): **importer takes a `--dates` JSON override**; Paige supplies them.
13. Point table import UX: **paste the official text / CSV of `class, points, size` with optional hull-override rows**; the class-line regex from the existing sheet layout handles the official format.
14. Multi-tenant on Paige's own box later: **not designed for, but `Team` FK is everywhere so it stays possible**.
15. Phase 4 ordering: **ESI fit push first** (removes copy-paste for every pilot every set), then Anger Games.
16. **Deployment behind Paige's existing containerised nginx (TODO, needed before first deploy):** the server already runs an nginx container that routes to other sites' containers. Plan: Caddy drops TLS and published ports, serves plain HTTP on the internal network, and the stack joins the existing proxy network as `external: true`; Caddy-owns-80/443 stays available as a Compose override for other self-hosters. Open until Paige checks: (a) whether that nginx is hand-configured or an automatic proxy (`nginx-proxy` + `acme-companion`, driven by `VIRTUAL_HOST` / `LETSENCRYPT_HOST` env vars), and (b) the shared Docker network name (`docker network ls`).

---

## 15. Verification (end to end, per phase)

- Phase 0: `docker compose up` on a fresh VM with a throwaway domain; login with Paige's character becomes admin; a second character is refused, then admitted via invite link; `/api/openapi.json` generates the TS client with no diff.
- Phase 1: pytest golden fixtures pass in Python and vitest; build OF 99 set 1's comp by hand in the builder and see 200 exact with the two Astartes at 36 each; ban "Astarte" in the comp browser and see that comp disappear; paste the ATXXII class list and see 156 classes with hull mapping confidence counts; log in as a pilot, save a comp and a fit and see them land in Suggested and stay out of the scrim pickers until a theorycrafter promotes them; RSVP "maybe" without a reason is rejected, and the captain's roll-call shows the reason once given; retiring a fit and removing a pilot as a no-show both appear in `/team/audit` with actor and reason, and the no-show shows up in that pilot's reliability stats; a pilot without the leadership flag gets a 403 on `/team/notes` and never sees notes in any API response.
- Phase 2: Playwright two-context test (A toggles a death, B's scoreboard and differential update within 1 s; A adds an avalanche ban, B's lineup shows the struck-through hull); a live scrim night with three editors; pull the network cable on one client and confirm resync with no lost or duplicated events (seq gap test); add round 3 to a set and confirm the lineup copies forward with changes highlighted.
- Phase 3: run `import_workbook` on the xlsx; importer report shows zero unmatched ships except `-`, every set total matches the sheet's cached `Y{h+13}`, and `v_match_log` diffed against the sheet's cached rows 844 to 1003 matches for every session; export CSV opens in R with the old script unchanged.
- Ops: nightly backup file appears in object storage; `make upgrade` on a new tag migrates cleanly; `refresh_affiliations` suspends a test character moved out of the alliance after the grace period.
