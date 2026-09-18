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
| Realtime | **REST writes, SSE fan-out** (decided 2026-09-14, replacing the websocket plan). Whole-set snapshot events over `text/event-stream`, Redis pub/sub between workers, presence over a POST heartbeat. Last-write-wins by DB commit order. No CRDT. | Fields are dropdowns/checkboxes; concurrent same-field edits are a tie either way. Keeps validation, rules engine, and audit log in one server-side write path. |
| Database | **Postgres 16** (+ Redis 7 for channel layer, presence, ESI ETag cache). | Row locks and `on_commit` semantics matter for the write path. |
| Rules | **Ruleset as data**: ~12 small typed tables per tournament edition, plus a `JSON extra` for quirks. A pure-Python rules engine (no Django imports) ported to TypeScript for instant UI feedback, both tested against the same JSON fixtures. | AT XXI, AT XXII and Anger Games differ on ~15 knobs (fielded count, cap, inflation, bans, flagship, overtime). Must not become an AT-shaped schema with AG bolted on. |
| Auth | **EVE SSO v2** (authorization code + PKCE, offline JWT validation via JWKS). Admins declared in `ADMIN_CHARACTER_IDS`. Membership via explicit allowlist, invite links, or corp/alliance admission rules. Hourly affiliation re-check via `POST /characters/affiliation/`. | No passwords to store. Public ESI only in v1 (no scopes). |
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
11. Round scorer (entered after each fight): points destroyed per side, unspent-points handicap, differential, colour-coded against a differential threshold.
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
        | HTTPS (REST + one SSE stream per open scrim page)
     Caddy  (auto-TLS; serves frontend/dist; proxies /api /auth /admin /static; no compression on event streams)
        |
   Django ASGI (uvicorn x2): django-ninja REST + async SSE stream view
        |            |
    Postgres 16    Redis 7 (scrim event pub/sub, presence, ESI breaker + ETag cache)
        ^
   scheduler (same image, supercronic): refresh_affiliations hourly, import_sde weekly, backup nightly
External: login.eveonline.com (SSO), esi.evetech.net, developers.eveonline.com (SDE), object storage (backups)
```

Single team per deployment, but a `Team` row exists and every library/session row FKs it; code never hardcodes team identity. Widening to multi-tenant later is a permission-layer change, not a schema migration.

---

## 5. Data model (condensed; full field lists in `datamodel_report.md`)

Five layers. All operational rows carry `created_at, updated_at, updated_by, row_version`.

**(a) SDE mirror, importer-owned (section 10)**
- Raw: `sde_raw_<file>(key, data JSONB, build, removed)` per included SDE file.
- Typed: `sde_category`, `sde_group(groupID PK, categoryID, name, published)`, `sde_meta_group`, `sde_faction`, `sde_race`, `sde_type(typeID PK, groupID, name, published, factionID, metaGroupID, raceID, techLevel, metaLevel, mass, volume, marketGroupID, variationParentTypeID)`.
- Curated hull facts live in the `rules` app, never in `sde` tables: the T1 support hull sizes (Bantam/Burst/Inquisitor/Navitas as LF, Augoror/Osprey/Exequror/Scythe as LC) and the SDE-group-to-size fallback are module constants in `apps/rules/constants.py`; the per-ruleset resolved size sits on `RulesetShip.hull_size`. Links capability is fit-driven (a command burst in the chosen fit), not a hull property.
- `CommandBurstScript(code PK: AE AR RR EH ES SO AS SE SH EM IM RD, name, family)`.
- `HullSize` is a TextChoices enum: `FR DE CR BC BS IN CV LF LC FLAG`.

**(b) Ruleset configuration, one cluster per tournament edition (built 2026-09-13, `apps/rules`)**
- `Tournament(code unique e.g. ATXXII/ATXXI/AG7, name, organiser ccp|community, server tranquility|thunderdome, year, dates, rules_url, verified, notes)`. `owner_team` deferred until `core.Team` exists.
- `Ruleset(tournament 1:1, fielded_pilots, point_cap, max_same_hull, duplicate_inflation_enabled, duplicate_inflation_mode per_copy_all|escalating|flat_additional, six flagship flags, flagship_eligible_sizes JSON, flagship_eligible_meta_groups M2M, unique_ship_extra_bans, unspent_points_to_opponent, kill_points_source comp_cost|kill_table, point_threshold, tiebreak_rule, roster_max, merc_max, ships_inference, extra JSON, revision, source_hash, imported_at)`. `revision` bumps on every import and child edit (signals) and keys the engine-input cache.
- `HullSizeRule(ruleset, hull_size, label, max_per_comp, duplicate_surcharge)`; FLAG is a real row with limit 1 and no surcharge.
- `GroupLimit(ruleset, code, label, max, message)` + `GroupLimitMember(limit, hull_size|ship_class|ship, weight)`: the logistics rule as LC weight 2, LF weight 1, max 2.
- `Stage(ruleset, code, label, best_of, bans_per_side, ban_order_pattern e.g. ABBAABAB, bans_are_blind, ban_targets, ban_deadline_minutes, avalanche_* fields, flagship_uses)`. No chess clock: bans are recorded after the fact.
- `ShipClass(ruleset, name, hull_size, sort_order, active)`: the official points list; never deleted, `active=False` when dropped.
- `RulesetShip(ruleset, ship FK sde.EveType, ship_class, hull_size, hull_size_is_override, legality, flagship_eligible|null, is_unique, mapping_source explicit|inferred_prefix|inferred_alias|manual)`: the edition's ship dimension; the banned-hull list is `legality=banned`.
- `PointTableVersion(ruleset, purpose cost|kill, version_no, label, source_url, effective_from, is_current, content_hash)` + `PointTableEntry(version, ship_class|ship, points)`: class default with hull override, versioned by content hash.
- `ModuleRule(ruleset, scope default|group|flagship, max_meta_level, hull_scope, groups M2M, categories M2M, allowed_meta_groups M2M)`, `BannedModuleType`, `TextSection`: module legality by SDE meta group and meta level, stored now and evaluated with the EFT parser.

Worked example of the same schema holding three editions:

| Knob | ATXXII | ATXXI | AG7 |
|---|---|---|---|
| fielded / cap | 10 / 200 | 10 / 200 | 7 / 75 |
| max_same_hull | 3 | null | 1 |
| inflation | on | off | off |
| BS max_per_comp | 2 (+FLAG row max 1) | null | null |
| flagship | on | on | off |
| stages | prelim Bo1 3 bans; bracket Bo3 4 bans avalanche; final Bo5 flagship x2 | bracket Bo3 4 bans | single, 2 bans ABBA, 45 min deadline |
| tiebreak | potential DPS at t=0 | none | none |

**(c) Team library**
- `Pilot(name, user OneToOne null, status active|inactive, is_merc, roles_text, notes)` in `apps/scrims` (built 2026-09-14): one row per person on the roster, linked to a login when they have one. A row is created automatically when a member with role pilot or above is admitted or promoted (adopting an unlinked pilot of the same name); captains add mercs and alumni by hand. No `PilotCharacter` (alts hang off `User`) and no per-tournament `RosterEntry` yet; `is_merc` sits on the pilot.
- `Opponent(name unique, notes, alliance_id, is_active)` and `WarpInLabel(label unique, sort_order, is_active)` also live in `apps/scrims`; the labels are seeded from the sheet's 48 Configurables in a data migration. `Archetype(name, description, is_retired, sort_order)` stays in `apps/library`.
- `Fit(ship, name, status suggested|active|inactive|retired, eft_text, pyfa_summary, dps, volley, ehp_k, speed_ms, sig_radius_m, cap_stable_pct, cap_lasts_s, targeting_range_km, stats_parse_ok, has_links, unresolved_names, created_by, reviewed_by, reviewed_at)` unique (ship, name); built 2026-09-13 in `apps/library`. No `team` FK: the deployment is single-team and `Membership` has none either. Only `active` fits appear in scrim and comp pickers; `has_links` (a Command Burst in the fit, SDE group 1770) is what comps read for link numbering.
- `Comp(ruleset, name, status suggested|construction|active|inactive|retired, archetype, notes, ban_theory, created_by, reviewed_by, reviewed_at)` unique (ruleset, lower(name)) + `CompSlot(comp, slot_no, ship, is_flagship, is_unique, warp_in_km, default_fit, ship_note, link_scripts JSON list of up to five two-letter codes)`; built 2026-09-13 in `apps/library/comps.py`. N slots are pre-created from `ruleset.fielded_pilots`; slot updates are a full replacement validated server-side (default fit must be for the slot's hull, scripts from the fixed `LINK_SCRIPTS` vocabulary). `has_links` for the engine comes from the default fit, else from having scripts. The scrim comp picker shows `active` comps only (Paige, 2026-09-14: no construction toggle). `suggested` is the entry state for anything a pilot proposes; a theorycrafter or captain promotes it to `construction` or `active`, or retires it. `Archetype(name, description, is_retired, sort_order)` is seeded with the sheet's 16 names; `WarpInLabel` waits for the scrim slice.

**(d) Operational session data (one row per sheet "cell group")**
- `Session(ruleset PROTECT, stage, point_table_version pinned, kind practice|scrim|tournament_match|warmup, title, date, opponent, system_name, moveme_system, motd, default_our_side, is_archived, event_seq, created_by)` (built 2026-09-14 in `apps/scrims/sessions.py`): creation takes the site-wide active ruleset, pins its current cost table (422 if none), pre-creates attendance rows for every active pilot and audits `scrim.created`. `event_seq` is the per-session counter behind the live stream. Importer source tracking waits for Phase 3.
- `SessionAttendance(session, pilot, rsvp yes|no|maybe|none, rsvp_reason, rsvp_at, attendance present|late|absent|no_show|none, removed_by, removed_reason, removed_at)`. RSVP is the pilot's own signup before the scrim (a reason is required for `maybe`); attendance is what actually happened, set on the night. Removing a pilot who said yes but did not appear is an explicit "Remove as no-show" action that sets `attendance=no_show`, records who did it and why, and writes an `AuditLog` row. "# Flown" is derived. Unique (session, pilot).
- `Set(session, index, label, comp, our_archetype, opp_archetype, our_side, tactics_note, link_note, warp_calls JSON list of four labels, deleted_at, deleted_by)`: deletion is soft (2026-09-17); a deleted set is hidden by the default manager and restorable from the history drawer until a new set takes its index. a set is one ban phase plus the series of rounds fought under those bans (normally a Bo3, often more). Creating a set pre-creates ban rows per stage and round 1. The four warp calls (1st..4th) are labels from `WarpInLabel` stored on the set; there is no separate `SetWarpCall` table and no per-set stage override (the stage is the session's).
- `Round(set, round_no, outcome win|loss|draw|none|reset, notes, deleted_at, deleted_by)`; soft-deleted like sets (only the last round can go, and it comes back only while nothing newer is live); no timing columns (the tool is pre/post match). Adding a round copies the previous round's lineup on both sides, so a Bo3 with no changes costs no extra input, while avalanche-ban swaps between games are recorded honestly.
- `Assignment(round, side US|OPP, slot_no, pilot, opp_pilot_name, ship, is_flagship, is_unique, warp_in_km, fit, fit_text_snapshot, load_default, custom_note, repeat_note, link_scripts JSON, died)`: one row per (round, side, slot); check constraint `pilot IS NULL OR side = 'US'`. `repeat_note` is the comp's `ship_note` copied onto the slot when a comp is loaded (shown muted next to the pilot's own `custom_note`). Points, inflation, link index and flags are **derived on read** by the engine when the set document is built, never stored. `died` is a toggle anyone with scoring rights can flip either way. This replaces the earlier separate per-round result table.
- `Ban(set, side A|B, kind standard|avalanche|unique_extra, index, ship, in_effect_from_round)`: standard bans apply from round 1; avalanche bans added after game N apply from round N+1 and persist for the set. The pick order comes from the stage's `ban_order` at read time.
- `ChangeEvent(session, seq, kind, payload JSON, actor, at)`: the SSE replay buffer, trimmed to the newest 500 per session on every write; not shown as history. The payload is a whole document fragment (`{set: ...}`, `{session: ...}`, `{attendance: [...]}`, `{deleted_set: id}`), not a field diff; see section 7.
- `AuditLog(actor, action, target_type, target_id, target_label, reason, before JSON, after JSON, at, scope)`: `scope` (`scrims.session:<id>`) ties every scrim-related row to its scrim so the history drawer is one query. append-only, team-wide record of significant actions: deleting or retiring a comp or fit, changing a comp/fit status, promoting a suggestion, removing a pilot from a scrim (no-show or otherwise), deleting a scrim, set or round, changing roles or admission rules, creating or revoking share links, editing pilot notes. Written by the service layer, never by clients. Retained indefinitely; readable by captains and admins at `/team/audit` and as a History tab on each object.
- `ShareLink(session, token urlsafe 24, created_by, created_at, expires_at, revoked_at)` (2026-09-17): anyone with the token reads the scrim at `/share/<token>` and `/api/share/<token>` (+ `/events`), read-only, fit text stripped, presence withheld; captains create and revoke, both audited; links die with expiry, revocation or archiving.
- Auth: `User` (custom, no password), `EveCharacter(character_id PK, name, owner_hash, corp, alliance, user)`, `Membership(user, role, status, source)`, `AdmissionRule(kind corp|alliance, entity_id, default_role)`, `Invite(token, role, uses_left, expires)`, `ShareLink(session, token, expires, require_login, revoked)`, later `EsiToken`.

**(e) Analytics: SQL views, no precomputation**
`v_match_log` (one row per US assignment per round) reproduces the sheet's export columns in the exact order and names, with extra keys appended, so the R workflow keeps working. Plus `v_round_score`, `v_pilot_round_stats`, `v_pilot_ship_stats`, `v_ship_survival`, `v_comp_results` (comp W/L by opponent and archetype), `v_ban_frequency`, `v_opponent_ship_usage`, `v_opponent_archetypes`, `v_session_attendance`, `v_pilot_reliability` (RSVP answers, attendance rate, no-shows after a yes). Materialise only if slow.

### 5.1 How rules get into the database (decided 2026-09-13)

Rulesets are authored as **YAML documents**, one per tournament edition (`atxxii.yaml`, `atxxi.yaml`, `ag7.yaml`), shipped with the app as the seed fixtures and importable later. An admin or captain pastes or uploads a YAML file on an admin page and the importer propagates it into the layer (b) tables. Rules:

- The importer validates before writing anything (unknown hull names, ban pattern not matching `bans_per_side`, points for an unlisted class, duplicate class names) and reports all problems at once.
- Import is idempotent: re-importing an unchanged file writes nothing; a changed file updates in place and records an `AuditLog` entry with a summary diff.
- Export produces the same YAML from the database, so a ruleset tuned in the UI can be diffed, committed, or shared with another team.
- Point tables inside the YAML create a new `PointTableVersion`; mid-tournament point revisions can also arrive through a dedicated paste screen (official class list or CSV) that shows a diff against the current version and which library comps change total or go over cap before "make current".
- Django admin remains available for one-off corrections (a single banned hull, a hull-to-class mapping); a full in-app rules editor is deferred until admin proves clunky.
- No live-editable JSON blob as the source of truth: it would lose validation, ship foreign keys, and the "which comps did this revision break" question.

**Module legality from SDE meta data (noted 2026-09-13).** `EveType.meta_level` and `EveType.meta_group` come straight from the SDE, and modules, charges, drones, implants and subsystems are imported, so the AT module rules can be data rather than reference text. The YAML gains a `module_rules` block: a default allowed-meta-group set (AT: T1 and T2), per-group overrides with `max_meta_level` and/or `allowed_meta_groups` (damps and disruptors Meta 4 max, T2 rigs banned, hardwirings above Meta 3 banned), explicit `banned_types`, and a `flagship` relaxation (faction/officer/deadspace allowed for listed module families). The rules engine evaluates a parsed EFT fit against it in the library slice. Verify first: whether implant "Meta 03" in CCP's wording maps to `meta_level` on implant types, and how "bonused hulls only" resolves (use `typeBonus`).

**Module legality, built 2026-09-13.** `apps/rules/engine/modules.py` evaluates a resolved fit against `ModuleRulesSpec` (built and cached per ruleset revision by `adapters.module_rules_for`). Findings that shaped it: the default allowed-meta-group rule applies to modules and drones only (subsystems are meta group Tech III, charges and implants have their own rules or none); abyssal modules resolve by SDE name (meta group Abyssal) and fail the default rule naturally; hardwiring implants carry **no** `meta_level` or `meta_group` in the SDE (typed layer and raw `typeDogma` attribute 633 both empty), so the "implants above Meta 3" rule uses the grade digit in the name (`EE-603` is grade 3, `SM-705` grade 5; Paige confirmed this is CCP's meaning, 2026-09-13) and fails as an error; `hulls: bonused_only` rules also report as warnings until a `typeBonus` check exists. Charges (faction ammo rules) stay text-only. `module_rules.banned_groups` bans whole SDE groups; the ATXXII fixture bans `Booster` (drugs of any sort, per Paige 2026-09-13).

The schema is documented in `docs/rulesets.md`; shipped documents are `backend/fixtures/rulesets/{atxxii,atxxi,ag7}.yaml` (`atxxii.yaml` is generated from the team workbook by `backend/scripts/gen_atxxii_from_workbook.py`). Import with `manage.py import_ruleset --path FILE [--dry-run] [--replace-points] [--force]`, export with `manage.py export_ruleset CODE`. Sketch:

```yaml
tournament: { code: ATXXII, name: Alliance Tournament XXII, organiser: ccp, server: tranquility, year: 2026 }
ruleset:
  fielded_pilots: 10
  point_cap: 200
  max_same_hull: 3
  duplicate_inflation: { enabled: true, mode: per_copy_all }
  flagship: { enabled: true, immune_to_bans: true, exempt_from_size_limit: true }
  unspent_points_to_opponent: true
  match: { tiebreak: potential_dps_t0 }
hull_sizes:
  - { size: BS, label: Battleship, max_per_comp: 2, duplicate_surcharge: 4 }
group_limits:
  - { code: logistics, max: 2, members: [{ hull_size: LC, weight: 2 }, { hull_size: LF, weight: 1 }] }
stages:
  - { code: prelim, best_of: 1, bans_per_side: 3, ban_order: ABBAAB }
  - { code: bracket, best_of: 3, bans_per_side: 4, ban_order: ABBAABBA, avalanche: { loser: 2, winner: 1, blind: true } }
banned_hulls: [Nestor, Marshal, Enforcer, Pacifier, Monitor, Cenotaph, Odysseus]
point_table:
  label: "Rev 1 (rules post)"
  classes:
    - { name: "Command Ship", size: BC, points: 33 }
  hull_overrides: []
module_rules:
  default: { allowed_meta_groups: [1, 2] }
  by_group:
    - { groups: [Sensor Dampener, Weapon Disruptor], max_meta_level: 4, hulls: bonused_only }
    - { groups: [Rig Armor, Rig Shield], allowed_meta_groups: [1] }
    - { groups: [Cyber Implant], max_meta_level: 3 }
  banned_types: [Bastion Module I]
  flagship: { allowed_meta_groups: [1, 2, 4, 5, 6], groups: [Energy Weapon, Stasis Web] }
text_sections:
  - { heading: Module restrictions, body: "..." }
```

---

## 6. Rules engine (built 2026-09-13)

Pure Python package `backend/apps/rules/engine/` (stdlib dataclasses only, no Django), to be mirrored in `frontend/src/engine/` against the same golden fixture (`backend/tests/rules/fixtures/of99_set1.json`). `apps/rules/adapters.py` builds the inputs from ORM rows and caches them per `(ruleset, revision, point version)`.

- `evaluate_comp(spec, point_table, hulls, slots, bans=()) -> CompEvaluation`: per-slot base points (hull override else class), inflation by mode, effective hull size (FLAG for an exempt flagship), violations as errors (`WRONG_SLOT_COUNT, UNLISTED_HULL, ILLEGAL_HULL, BANNED, OVER_CAP, OVER_SIZE_LIMIT, OVER_SAME_HULL, GROUP_LIMIT_EXCEEDED, MULTIPLE_FLAGSHIPS, FLAGSHIP_DISABLED, FLAGSHIP_NOT_ELIGIBLE`), warnings (`EMPTY_SLOT, UNIQUE_NOT_UNIQUE_HULL`) and info (`UNDER_CAP, UNIQUE_DECLARED`), link indexes from the caller's per-slot `has_links` (fit-driven), unspent points. Inflation with `copies` copies of a hull and surcharge `s`: `per_copy_all` every copy pays `(copies-1)*s`; `escalating` copy N pays `(N-1)*s`; `flat_additional` every copy after the first pays `s`.
- `score_round(spec, us_eval, opp_eval, us_dead, opp_dead, ...) -> RoundScore`: points conceded per side including the unspent handicap, differential (theirs minus ours, as the sheet's `U21`), a decisive-lead indicator against `point_threshold`, tiebreak hint. No match timing anywhere: results are entered after the fight.
- `ban_sequence(stage, first_side)`, `avalanche_allocation(stage, winner)`, `extra_bans_for_unique(...)`, `flagship_uses_remaining(...)`.
- `parse_pyfa_summary(text)`, `parse_eft_header(eft)` (server only).
- Server is authoritative: every write to a set recomputes the whole set's cached values and broadcasts a compact `derived` block; the TS port gives instant feedback before the round trip.

**Inflation:** `per_copy_all` is the confirmed AT rule (two Ashimmus at 18 with +2 cost 20 each); OF 99 set 1 totals exactly 200 under it and is the golden fixture. The xlsx importer will cross-check every imported set's total as an acceptance test.

Golden tests transcribed from the workbook: OF 99 set 1 (200 exact, two Astartes, two Deacons), over-cap comp, 1 LC + 1 LF group-limit violation, flagship BS as third battleship, banned flagship exempt, AG7 7-slot comp with duplicate hull, 190-point comp handicap, overtime colour thresholds.

---

## 7. Realtime design (revised 2026-09-14: SSE, whole-set snapshots)

Sized for one team: at most 40 members and about 100 open streams. Simplicity wins over generality.

- **Transport:** every write is a small REST call (`PATCH /api/scrims/{s}/sets/{set}/...`); every open scrim page holds one `GET /api/scrims/{s}/events` `text/event-stream` (browser `EventSource`, plain HTTP, reconnects on its own with `Last-Event-ID`). The old objection to SSE ("no uplink for presence") is answered by a `POST /api/scrims/{s}/presence {focus?}` heartbeat every 15 s. Channels stays installed only until nothing else needs it.
- **Write path:** service runs in `transaction.atomic()`, locks the `Session` row (`select_for_update`), applies the change, increments `session.event_seq`, inserts `ChangeEvent(kind, payload)` where the payload is the **full set document** (10 slots × rounds, ~20 KB) rebuilt through the engine, commits, and on commit publishes the event to the broker (`broker.py`: Redis pub/sub channel `scrim:{id}` in dev and prod, an in-memory asyncio broker in tests). The REST response carries the same document, so the writer sees the result without waiting for its own event.
- **Client:** the live document lives in the TanStack Query cache; `useScrimStream` applies `set` / `session` / `attendance` / `presence` events with `setQueryData`, replacing whole fragments. No field-level patch protocol, no `base_version`, no `op_id`: last-write-wins falls out of commit order. Free-text fields are the one place two people can trample each other; the client keeps the focused field's draft, debounces saves 400 ms, and shows the other editor's focus outline (amber).
- **Replay and resync:** the stream view authenticates via the session cookie, reads `since` from `Last-Event-ID` (or the query string), replays `ChangeEvent` rows with `seq > since` (cap 500, else emits `resync` and the client refetches the whole session), then relays broker messages; `id:` is the seq, `: keepalive` every 20 s, `Cache-Control: no-cache`, `X-Accel-Buffering: no`. A seq gap on the client triggers a refetch. Offline badge after 5 s without a keepalive.
- **Presence:** Redis hash per session with a 45 s TTL fed by the POST heartbeat; each heartbeat publishes a `presence` event with the viewer list and focus cells; the stream sends the current list on connect.
- **Share stream:** `GET /api/share/<token>/events` runs the same generator with `public=True`: no presence frames and every set document has `fit_text` blanked.
- **Deployment:** Caddy must not buffer or compress the event stream (`encode` excludes `text/event-stream`); the Vite dev proxy streams it as is. Two uvicorn workers share state only through Redis and Postgres.
- Rejected: websockets via Channels (a second protocol and auth path for no gain at this scale), field-level patches with versions (more protocol for the same LWW outcome), Postgres CDC (raw rows, not derived state), Yjs/CRDT (client authority, overkill for dropdown data).

---

## 8. Auth and roles

- **Login:** `/auth/login` → SSO authorize (PKCE + client secret, scope `publicData`) → `/auth/callback` → token exchange → offline JWT validation (`PyJWKClient`, accept both `iss` forms, `aud` includes client id) → upsert `EveCharacter` (detach from user if `owner_hash` changed) → fetch corp/alliance → admission → Django session login. Same-origin session cookie + CSRF header; Channels `AuthMiddlewareStack` reuses the cookie. No bearer tokens in the browser.
- **Admission order (built 2026-09-13):** character id in `ADMIN_CHARACTER_IDS` → admin (declared in the env file; first-login-wins was rejected as a race on a public URL); explicit active `Membership`; valid `Invite` token; matching `AdmissionRule` (corp/alliance); else a denied page showing the character id (and a hint when no admins are configured). `manage.py grant_admin` is the recovery path.
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

Layout agreed on a static mockup (v7, 2026-09-14, following Paige's sketch): a CSS grid of four columns, rail 230 · results 210 · main fluid · fits 290, with named areas: row 1 `scrim | bans bans | fits`, row 2 `attendance | results | ours | fits`, row 3 `sets | results | theirs | fits`. The left rail holds the scrim header, the attendance list and the set stepper. The results column holds the round tabs (R1 R2 R3 +) that drive the whole middle of the page, our ten ships as compact click-to-toggle-death rows, the score block, then their ten ships. The main area holds the ban board (one compact left-to-right pick sequence in `ban_order`, our picks blue, no A/B tags, an avalanche row and a collapsible tactics line), then our lineup at full width with the four warp calls in its header, then their lineup. The fits column on the right has a Mine/All toggle. Notes are inline (ship note as a lineup column, round note under the score, set tactics as the collapsible line), never popups; deaths are toggled in the results column, not on lineup rows. Desktop only (sideways scroll below ~1180 px). Exact sizes get tuned on the working page. Built in three parts: **A (done 2026-09-14)** roster, opponents, sessions, RSVP, attendance, `/scrims` list and the page shell; **B** sets, bans, rounds, lineups, derived scores, comp load, SSE + presence, the page per the mockup; **C** share links, review tab + CSV, history drawer, pilot card.

**Comp load and the override-blanks-defaults rule (from the sheet, written down).** Loading a comp fills, for every slot with `load_default = true`: `ship, is_flagship, is_unique, warp_in_km, fit` (the comp's default fit), `repeat_note` (the comp's ship note), `link_scripts`, and snapshots `fit_text_snapshot`. Changing a slot's ship to something other than the comp's ship sets `load_default = false` and clears the dependent defaults (`fit, fit_text_snapshot, repeat_note, link_scripts`); `pilot, warp_in_km, custom_note` survive. Re-ticking `load_default` re-applies the comp's values for that slot. Slots on a set without a comp are plain fields.

The prose below predates the mockup and describes the same content in its older three-panel arrangement; where they differ, the mockup wins.

**Left rail**
- Scrim header: opponent, date, kind, system and moveme, MotD, ruleset and stage badge, our side (Team A / B), share link, history, export.
- Attendance: pilot list pre-sorted by RSVP (attending, maybe with reason shown, unable, no answer) with present/late/absent toggles for the night, a "Remove as no-show" action that asks for a reason and is audited, and a "# flown tonight" count; presence dots for pilots who are logged in. The pilot dropdown in lineups groups attending pilots first.
- Set stepper: one card per set showing label, comp name, ban summary (our 4 · their 4 · avalanche), and round results as W/L pips. "+ New set" offers "copy previous set" (comp and pilots carried, bans cleared) as the default.

**Main area, one set at a time.** Three stacked panels, all always visible (captains bounce between them), each with a compact and an expanded state:

1. **Ban board.** Two columns (Team A, Team B) of ban chips laid out in the stage's ban order (`ABBAAB` etc.) with the order number on each chip; a third row for avalanche bans labelled "after R1", "after R2". Adding a ban is a typeahead over legal hulls. Banned hulls immediately show struck through with a red badge everywhere in this set (comp picker, lineup rows, opponent rows), and the comp picker filters to comps that survive the bans by default with a toggle to show all. A "we are A/B" switch flips which column counts against us. After a round is marked, the app prompts the avalanche allocation from the stage rules (loser bans 2, winner bans 1) and pre-creates the chips.

2. **Lineups.** Side by side: **Ours** and **Theirs**, each N rows for the selected round (round tabs across the top of the panel: R1 R2 R3 +; a new round copies the previous lineup and highlights any cell later changed from the prior round).
   - Ours: comp picker at the top (shows points, status, archetype, "3 hulls banned" warnings); rows: pilot dropdown with a "Suggested" group (who flew this hull or a hull of the same size most recently, how many times), ship typeahead, fit select (active fits for that hull, default from comp), warp-in, links number and scripts (auto-numbered, editable), note, flagship toggle, points with inflation shown as "33 +3". Row-level badges: over size limit, banned, limit exceeded. A budget bar under the table: total / cap with per-size segments and unspent points called out. Load-default toggle per row, override-blanks-defaults semantics preserved from the sheet.
   - Theirs: archetype select, rows of ship typeahead + flagship toggle + note, same budget bar. "Paste lineup" accepts ten ship names from chat and resolves them.
   - Warp calls (1st to 4th) and tactics note live in the panel header.

3. **Round result.** For the selected round, entered after the fight: two columns of ship chips (ours labelled with pilot name), one click toggles dead and moves the chip's points to the other side's total; toggling again undoes it. Totals: points destroyed by us, by them, differential with colour against the point threshold, unspent-points handicap shown explicitly, outcome buttons (Win / Loss / Draw / Reset), round note. No timer and no live-update expectation: pilots are flying during the match. Anyone with scoring rights can toggle a death; the audit drawer shows who toggled what.

**Right drawer: Fits for this round.** One card per our slot: pilot, ship, fit name, warp-in, scripts, notes, EFT text in a monospace block, Copy button (Phase 4: Push to EVE). Filter "mine" highlights the logged-in pilot's card; the pilot's own row in the lineup is also highlighted so a pilot with EVE open on another monitor finds their fit in one glance.

**Post-scrim:** a Review tab on the scrim summarising sets, rounds, W-L, points differential per round, deaths per pilot, and the bans, with one-click export to CSV.

### 9.3 Comps

- **List**: table with status, archetype, points, DPS, EHP, min speed, hull chips (text), last used, W-L; filters by status (default Active + Construction), archetype, ruleset; a **ban simulator** input at the top ("Sleipnir, Curse, Sentinel") that greys out affected comps with the offending hulls named, replacing the sheet's Comp View. A **Suggested** tab lists member proposals with who suggested them and Promote / Retire actions for theorycrafters; any member can open the builder and save a comp, which lands in Suggested.
- **Builder / detail**: left, the N slot rows (ship typeahead, flagship toggle, warp-in, default fit, note, five script selects); right, a sticky panel with the budget bar and per-size counts (BS 2/2, BC 3/3, ...), the legality list (each violation names the rule and the slots), stat rollups (sum DPS, sum EHP, avg and min speed, total potential DPS for the t=0 tiebreak), and tabs for Notes, Ban theory, and History (every set the comp was fielded in with results). Actions: clone, clone to another ruleset, retire, "use in scrim".
- **Compare**: two comps side by side with slot diffs and stat deltas.

- Built 2026-09-13 (utilitarian): `/comps` scoped to the team's active ruleset with status, archetype and search filters and a "New comp" panel (the ban simulator moved to the scrim page per Paige; `GET /api/comps?banned=` stays for the scrim comp picker); `/comps/:id` builder with the slot table (hull picker, flagship, unique, warp-in, default fit from the fit library with stale-status badges, five link-script selects, ship note), live evaluation through the dry-run rules endpoint, budget with per-size counts, violations, stat rollups from default fits, archetype/notes/ban theory, status control with audit reason, explicit Save, Clone. Compare view and History tab are still open.

### 9.4 Fits

- List grouped by hull with status, DPS, EHP, speed, "used in N comps", last flown, survival rate.
- Detail: EFT textarea (monospace) with header validation against the hull, Pyfa summary paste with parsed stats displayed, lifecycle, usage list.
- "New from clipboard": paste an EFT block, the app resolves hull and name from the header. Any member can submit a fit this way; it lands in Suggested until a theorycrafter activates it, and suggested fits never appear in scrim pickers.
- Built 2026-09-13 (utilitarian): `/fits` list grouped by hull with status filter and search, paste panel with a live server-side parse preview (hull, unknown items, links, stats), `/fits/:id` with editable EFT and Pyfa blocks, stats, status control with an audit reason, and a module-legality panel per ruleset with a flagship toggle. Usage counts, last flown and survival rate wait for comps and scrims. `manage.py import_workbook_fits <xlsx>` loads the sheet's `Fit library` (145 fits, all resolved).

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

**SDE (decided 2026-09-13): a hybrid JSONL-to-Postgres loader in a dedicated `sde` app.** Goal: drop a new CCP JSONL zip and the project updates itself, with no per-file code.

- **Raw layer, generic.** One table for every included file, `sde_raw_record(file, key, data JSONB, build, removed)`, unique on `(file, key)`. One model, one migration, no per-file code. The loader streams each `.jsonl` member from the zip, decodes the `_key`/`_value` pair encoding recursively, and upserts in batches. Which files land is a configured include list (`SDE_INCLUDED_FILES`), defaulting to categories, groups, metaGroups, factions, races, types, marketGroups, typeBonus, typeDogma, dogmaAttributes, dogmaEffects; anything else is a config line, not code. The full archive is ~570 MB uncompressed, dominated by mapMoons and missions, so "everything" is deliberately not the default.
- **Typed layer, derived.** Models `EveCategory`, `EveGroup`, `EveMetaGroup`, `EveFaction`, `EveRace`, `EveType` (tables `sde_eve_*`) are filled from the raw table in Python with batched upserts, all six plus the `SdeBuild` row in one transaction so readers switch builds atomically. Types are limited to categories 6 Ship, 7 Module, 8 Charge, 18 Drone, 20 Implant, 22 Deployable, 32 Subsystem (`SDE_TYPE_CATEGORIES`), so every item an EFT fit can name is present. SDE ids are the primary keys; names are stored as `name` (English). `techLevel`, `metaLevel`, `metaGroupID` are direct fields in the current SDE; no dogma lookup needed.
- **Never delete.** A record missing from a new build gets `removed = true` in both layers; `published` stays exactly what CCP shipped (many legitimate hulls are unpublished). Lookups use `published=True, removed=False`. Importing a build older than the current one is refused without `--force`. App tables (`RulesetShip`, `Fit`, `CompSlot`, `Assignment`) use **real foreign keys** to `sde_type`; the never-delete rule keeps them valid. Curated per-hull data (hull-size overrides, links capability) lives in `rules` tables keyed by type, never in `sde` tables. Exported documents (YAML rulesets, CSV) carry hull names, not type ids.
- **Triggers, all feeding the same importer:** `manage.py import_sde --path <zip or folder>` for a manual drop and offline use; a drop folder `instance/sde/incoming/` polled by the scheduler (import, then move to `archive/`); a scheduled check of CCP's `latest.jsonl` (`{"_key":"sde","buildNumber":...,"releaseDate":...}`) that downloads `eve-online-static-data-latest-jsonl.zip` when the build is newer than the last import; later an admin upload page. Each run holds a Postgres advisory lock (cron and CLI cannot overlap), is one transaction per raw file, idempotent, logs row counts, records `SdeBuild(build, release_date, imported_at, last_checked_at, files, counts)`, and is shown on `/api/health` as `sde_build` / `sde_stale` (stale when neither an import nor a successful CCP check happened within `SDE_STALE_DAYS`). Nightly `pg_dump` excludes `sde_raw_record` data because it is reproducible from the archived zips; the typed tables are backed up.
- **Verified against build 3503375 (2026-09-10):** all 102 files sit at the zip root; `_key` is a JSON number; names are `{de,en,es,fr,ja,ko,ru,zh}` objects; group 28 is now "Hauler"; category 6 has 50 groups (including Capsule 29, Citizen Ships 2001, Expedition Command Ship 4902, Special Edition Yachts 5087, Command Carrier 5120), so the ship-group set is derived from `groups` where `categoryID == 6`, not hardcoded; Society of Conscious Thought is faction 500017 and Deathless Circle 500029.
- **Conventions carried from evecapnav / eveindyapp:** SDE data is read-only and importer-owned; constants are module-level `UPPER_SNAKE` ints and sets with the in-game name in a comment, no enums; lookups are loaded once into dicts where hot; defensive checks fail with a remediation message (`ImportFailed.remediation`); `ty` for type checking, ruff for lint. Shared importer plumbing (`ImportReport`, `ImportFailed`, `advisory_lock`) lives in `apps/core` for the YAML ruleset and xlsx importers to reuse. Tests run on Postgres only.
- Ship-class auto-mapping for `RulesetShip.ship_class`: (1) class name starts with `"{ship.name} ("`; (2) alias dict by group and faction set (empire vs pirate faction ids from `factions`); (3) admin review queue for the rest.
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

Dev: `docker-compose.dev.yml` runs Postgres + Redis only; Django and Vite run natively with Vite proxying `/api /auth /ws`. `/auth/dev-login?character_id=&name=&role=` is the local-only login shortcut (404 unless `DEV_LOGIN_ENABLED`, which only dev settings turn on); it is the seam the Playwright suite logs in through, so EVE SSO and ESI are never in the loop.

---

## 12. Repo layout

```
<repo>/
  backend/
    pyproject.toml (uv: django, django-ninja, channels, channels-redis, httpx, pyjwt[crypto], psycopg[binary], environs, cryptography, openpyxl)
    manage.py  config/{settings/,asgi.py,urls.py,api.py,routing.py}
    apps/accounts (User, EveCharacter, Membership, AdmissionRule, Invite, ShareLink, sso.py, permissions.py)
    apps/audit (AuditLog, record() helper called from every service)
    apps/esi (client.py, refresh_affiliations)      apps/sde (SdeRawRecord, SdeBuild, EveCategory, EveGroup, EveMetaGroup, EveFaction, EveRace, EveType; jsonl.py, loader.py, derive.py, download.py, incoming.py; import_sde)
    apps/rules (Tournament, Ruleset, HullSizeRule, GroupLimit, Stage, ShipClass, RulesetShip, PointTableVersion, ModuleRule; yaml_io.py, inference.py, importer.py, exporter.py, adapters.py, engine/; import_ruleset, export_ruleset)
    fixtures/rulesets/{atxxii,atxxi,ag7}.yaml   scripts/gen_atxxii_from_workbook.py
    apps/library (Fit, Comp, CompSlot, Archetype, eft.py, pyfa.py, services.py, comps.py)
    apps/scrims (Pilot, Opponent, WarpInLabel, Session, SessionAttendance, Set, Round, Assignment, Ban, ChangeEvent; roster.py, sessions.py, api.py; part B adds sets.py, derived.py, events.py, broker.py, stream.py)
    apps/analytics (views SQL, match_log export)     apps/importer (xlsx.py + per-sheet modules)
    apps/core (Team, bootstrap, health)              fixtures/ruleset_atxxii.json   tests/
  frontend/  (Vite, React 19, TS strict; src/routes, src/features/{session,library,auth,stats}, src/engine (TS port), src/lib/{api,ws} generated)
  deploy/    docker-compose.yml, docker-compose.dev.yml, Caddyfile, crontab, backup.sh, Dockerfile.backend, Dockerfile.frontend, .env.example
  docs/      SETUP.md, ARCHITECTURE.md, CHANGELOG.md, research/ (the two scratchpad reports)
  .github/workflows/ ci.yml, release.yml      Makefile (init, dev, test, gen-client, upgrade, backup)
  docs/research/  (local only, gitignored: the source .xlsx and raw analysis notes)
```

Testing: pytest golden + Hypothesis tests for the engine; pytest-django against real Postgres for services (concurrency test: two threads patch one row → versions 1 and 2, two events in seq order); SSE stream tests against the in-memory broker (connect with `since`, replay, gap → resync, keepalive); parametrised permission-matrix test; SSO JWT tests with a local RSA key and fake JWKS; vitest for reducers and the TS engine port on the shared fixtures; Playwright smoke with two browser contexts (A changes a ship, B sees it within 1 s, totals update; `/me` shows the fit). CI: ruff, mypy (strict on engine and services), pytest with Postgres/Redis services, tsc, eslint, vitest, build, generated-client drift check, Compose-based e2e, release images on tag.

Playwright harness (built 2026-09-14, Python `pytest-playwright` in `backend/playwright_tests/` so Paige can maintain it): runs against the servers `make run` already started; `make playwright` first runs `manage.py playwright_cleanup`, which deletes `pw_`-prefixed rows and the reserved test characters 900000001..900000099. Per-role sessions come from a `login_as("pilot")` fixture (its own browser context through dev-login), so one test can drive an admin and a pilot side by side. Test ids follow `area.element[.qualifier]` (`fits.new.save`, `comp.slot.3.hull`, `team.members.row.<id>`). First specs: navigation per role, fit suggest-and-promote with the audit trail, comp build/save/clone, invite join plus member management and admission rules, season switch, and (2026-09-14) a scrim night from creation through RSVP, roll call and no-show, the roster page, the viewer/guest permission edges, and a three-browser live test (a theorycrafter fills a slot, bans a hull, toggles a death and adds a round while a pilot's page follows over the event stream and the captain's attendance rail shows who is online). Chromium only; CI job deferred.

---

## 13. Phased roadmap

Sizes relative; assume a solo dev at ~10 h/week. Phase 2 is the critical path; start a thin vertical slice of it (one set, ships + death ticks + totals, two browsers) right after Phase 0 to de-risk realtime before the bulk of Phase 1 CRUD.

| Phase | Scope | Size | Exit criterion |
|---|---|---|---|
| **0 Skeleton + auth** | DONE (2026-09-13): monorepo, Compose, Django + ninja + Channels, EVE SSO login/callback/link with env-declared admins, Team/Membership/roles/invites/admission rules with hourly ESI re-check, audit log, generated TS client, SPA shell with Team and Audit pages, CI. | M | A stranger self-hosts from the README and logs in with an EVE character listed in `ADMIN_CHARACTER_IDS`; a second character is rejected until invited. |
| **1 Libraries + validation** | DONE: the comp library (section 9.3: browser, builder with live evaluation and stat rollups, Suggested review queue on the dashboard, notes/ban theory, `import_workbook_comps`), the site-wide active ruleset (`Team.active_ruleset`), the fit library (section 9.4: `apps/library`, EFT and Pyfa parsers, module legality via `engine/modules.py`, workbook fit import), the hybrid SDE loader (section 10), the rules layer (sections 5(b), 5.1, 6: YAML schema, validating importer/exporter, ATXXII/ATXXI/AG7 fixtures, pure engine with golden tests), and a comp scratchpad: read-only `GET /api/rulesets`, `GET /api/rulesets/{code}/ships`, `POST /api/rulesets/{code}/evaluate` (DEBUG-only until SSO lands) behind a utilitarian `/scratchpad` page with the generated `openapi-fetch` client. REMAINING: admin upload page; official points paste importer → ShipClass + PointTableVersion; RulesetShip auto-mapping + review queue; per-object History tabs; `/team/notes`; TS port of the rules engine with shared fixtures. Pilot roster, opponent registry and scrim creation with RSVP moved into Phase 2 part A and are done. | L | Every validation the sheet performs is reproduced and tested; all 145 fits and 125 comps can be loaded (via the Phase 3 importer run early, or CSV). |
| **2 Live scrim page** | **Part A DONE (2026-09-14):** `apps/scrims` with Pilot (auto-created for members of rank pilot+), Opponent, WarpInLabel seed, Session/SessionAttendance, RSVP rules (maybe needs a reason, closed once the day has passed), attendance with the audited no-show removal, `/api/scrims` `/api/pilots` `/api/opponents`, `/scrims` list with roll call and a new-scrim form, the `/scrims/:id` shell (header, attendance rail), `/team/pilots`, the dashboard's upcoming-scrims panel with RSVP buttons, Playwright coverage. **Part B DONE (2026-09-14):** `apps/scrims/{sets,derived,events,broker,stream,presence}.py`: sets pre-create bans per stage and round 1, comp load with the override-blanks-defaults rule, bans in stage order with avalanche chips pre-created after a decided round, rounds copied forward with deaths cleared, opponent lineup paste, derived points/scores on every read, session-locked writes with a per-session `event_seq`, whole-set `ChangeEvent`s replayed and relayed over SSE (Redis pub/sub between workers, `ping` keepalives, gap → `resync`), presence heartbeat with focus outlines; permissions: theorycrafter+ edits sets, pilots edit their own slot's fit/warp/note and toggle deaths when `pilots_can_score`, captains create/delete sets and rounds, guests read only scrims they are assigned in. The page follows the mockup v7 grid (rail, results column with click-to-toggle death lists and the score block, ban board over ours over theirs, fits column with Mine/All). **Part C DONE (2026-09-17):** Board/Review toggle on the scrim page (record, bans, per-round table, deaths per pilot), `GET /api/scrims/{id}/export.csv` in the sheet's match-log column order, soft delete with restore for sets and rounds, scrim-scoped audit rows behind a History drawer, share links (`ShareLink`, public token read + stream, `PUBLIC_ORIGIN` for the URL), pilot suggestions (`/api/pilots/history?type_id=`) grouped at the top of the pilot dropdown, and the pilot card at `/scrims/:id/me`. Flagship-use tracking dropped (unlimited in scrims; one use then dead in matches). | XL | A real weekly scrim is run entirely in the app with three simultaneous editors. |
| **3 History + analytics** | openpyxl importer for the workbook (libraries + 30 sessions; set blocks located by scanning column Y for "Set #"; dates from tab names; hidden sheets archived; hidden column M ban codes; cross-checks against cached totals and the sheet's own data-log rows); Django-Q2 for the long-running import; `v_match_log` CSV/API export; stats pages (pilot survival, ship death rates, comp W/L by opponent and archetype, ban frequency, attendance over time, per-opponent history). | M-L | Historical OF 99 renders identically to the sheet; the R users get the same CSV. |
| **4 Nice-to-haves** | ESI fit push; Anger Games ruleset row (exercises data-driven rules; add code rules only if needed); Challonge bracket import; opponent scouting (zKillboard lookups); `dogma-engine` WASM fit stats, extended to comp-level numbers (Paige, 2026-09-17: with the SDE and every fit in the lineup known, apply command bursts, links and other fleet effects across the comp and show real EHP/DPS/speed per slot instead of the pasted Pyfa summary); team-wide library change notifications; flagship series tracking. | S-M each | Independent; ship as demanded. |


### 13.1 Small items (QoL backlog)

- Members must not be able to change their own role or status. Today `PATCH /api/team/members/{user_id}` only protects the last active admin; a captain or admin can demote or suspend themselves. Reject `user_id == request.user` with 403 and hide the controls on the Team page for the viewer's own row. (Paige, 2026-09-18)
- Theme toggle in the header (light is the default; dark tokens exist).
- MotD field grows with its text instead of a fixed height.

---

## 14. Decisions still open (recommended defaults in bold; the plan proceeds on these unless Paige says otherwise)

1. **Duplicate inflation semantics: resolved 2026-09-13.** Every copy pays `(copies-1) x surcharge`; Paige confirmed from play (two Ashimmus at 18 base with a +2 cruiser surcharge cost 20 each). ATXXII uses `duplicate_inflation_mode: per_copy_all`; the other two modes stay in the engine for other rulesets.
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
13. Rules and point-table import: **YAML ruleset documents pasted or uploaded on an admin page (section 5.1)**, plus a paste screen for mid-tournament point revisions.
14. Multi-tenant on Paige's own box later: **not designed for, but `Team` FK is everywhere so it stays possible**.
15. Phase 4 ordering: **ESI fit push first** (removes copy-paste for every pilot every set), then Anger Games.
16. **Site-wide active ruleset (2026-09-13):** the team works one season at a time, so `Team.active_ruleset` (admin-set in the header, audited) scopes comps, fit legality and comp creation; nothing is chosen per fit or per comp. Comps keep a `ruleset` FK because AT and Anger Games differ in points and pilot counts. **Open:** what happens to the library when the season changes. Two cases to design: (a) a points or rules revision inside one tournament (comps stay relevant; library health alerts flag the ones that went over cap or illegal); (b) a different tournament altogether (whole library effectively archived; "clone to ruleset" is the migration path). Paige wants older material archived or marked out of date rather than silently left behind.
16. **Deployment behind Paige's existing containerised nginx (TODO, needed before first deploy):** the server already runs an nginx container that routes to other sites' containers. Plan: Caddy drops TLS and published ports, serves plain HTTP on the internal network, and the stack joins the existing proxy network as `external: true`; Caddy-owns-80/443 stays available as a Compose override for other self-hosters. Open until Paige checks: (a) whether that nginx is hand-configured or an automatic proxy (`nginx-proxy` + `acme-companion`, driven by `VIRTUAL_HOST` / `LETSENCRYPT_HOST` env vars), and (b) the shared Docker network name (`docker network ls`).

---

## 15. Verification (end to end, per phase)

- Phase 0: `docker compose up` on a fresh VM with a throwaway domain; login with Paige's character becomes admin; a second character is refused, then admitted via invite link; `/api/openapi.json` generates the TS client with no diff.
- Phase 1: pytest golden fixtures pass in Python and vitest; build OF 99 set 1's comp by hand in the builder and see 200 exact with the two Astartes at 36 each; ban "Astarte" in the comp browser and see that comp disappear; paste the ATXXII class list and see 156 classes with hull mapping confidence counts; log in as a pilot, save a comp and a fit and see them land in Suggested and stay out of the scrim pickers until a theorycrafter promotes them; RSVP "maybe" without a reason is rejected, and the captain's roll-call shows the reason once given; retiring a fit and removing a pilot as a no-show both appear in `/team/audit` with actor and reason, and the no-show shows up in that pilot's reliability stats; a pilot without the leadership flag gets a 403 on `/team/notes` and never sees notes in any API response.
- Phase 2: Playwright two-context test (A toggles a death, B's scoreboard and differential update within 1 s; A adds an avalanche ban, B's lineup shows the struck-through hull); a live scrim night with three editors; pull the network cable on one client and confirm resync with no lost or duplicated events (seq gap test); add round 3 to a set and confirm the lineup copies forward with changes highlighted.
- Phase 3: run `import_workbook` on the xlsx; importer report shows zero unmatched ships except `-`, every set total matches the sheet's cached `Y{h+13}`, and `v_match_log` diffed against the sheet's cached rows 844 to 1003 matches for every session; export CSV opens in R with the old script unchanged.
- Ops: nightly backup file appears in object storage; `make upgrade` on a new tag migrates cleanly; `refresh_affiliations` suspends a test character moved out of the alliance after the grace period.
