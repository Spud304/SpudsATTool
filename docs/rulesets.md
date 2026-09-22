# Ruleset documents

A tournament edition's rules are one YAML file. The shipped files import themselves once the SDE is loaded (`manage.py load_rulesets`, run after every SDE import and on web start; a tournament code already in the database is left alone). Admins import a changed or new file with `manage.py import_ruleset --path FILE` (an upload page is still to come); the database is derived from it, and `manage.py export_ruleset CODE` produces the same canonical document back. Names everywhere (hulls, classes, SDE group and meta-group names), never ids. Unknown keys are errors. Every problem in a document is reported at once as `path: message`.

Shipped documents live in `backend/fixtures/rulesets/`: `atxxii.yaml`, `atxxi.yaml` and `ag7.yaml`, all hand-written (`atxxi` and `ag7` are `verified: false`).

## Top level

| Key | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Always `1`. |
| `verified` | no (true) | `false` marks a transcription from unverified sources. Importing an unverified document over a verified ruleset needs `--force`. |
| `notes` | no | Provenance text. |
| `tournament` | yes | Identity, see below. |
| `ruleset` | yes | The knobs the engine reads. |
| `hull_sizes` | yes | Size codes with per-comp limits and duplicate surcharges. |
| `group_limits` | no | Max count over a group of sizes, classes or hulls, weighted (the logistics rule). |
| `stages` | yes | Ban structure per stage of the tournament. |
| `ship_classes` | no | The official points list, in order. |
| `ships` | no | Hull to class mapping and per-hull overrides. |
| `point_table` | no | Metadata for the cost table plus hull overrides; class points sit on `ship_classes`. |
| `kill_table` | no | Only when `ruleset.kill_points_source` is `kill_table`. |
| `banned_hulls`, `unique_hulls` | no | Shorthand lists of hull names. |
| `module_rules` | no | Module legality by SDE meta group and meta level; evaluated against every fit on `/fits/:id`. |
| `text_sections` | no | Human-readable rule text. |

## `tournament`

`code` (`^[A-Z][A-Z0-9_]{1,15}$`, e.g. `ATXXII`), `name`, `organiser` (`ccp` or `community`), `server` (`tranquility` or `thunderdome`), `year`, optional `starts_on`, `ends_on` (dates), `rules_url`.

## `ruleset`

| Key | Default | Meaning |
|---|---|---|
| `fielded_pilots` | required | Pilots per team in the arena. |
| `point_cap` | required | Points per comp. |
| `max_same_hull` | null | Max copies of one hull; null means no limit. |
| `duplicate_inflation.enabled` | false | |
| `duplicate_inflation.mode` | `per_copy_all` | `per_copy_all`: every copy of a duplicated hull pays `(copies - 1) x surcharge` (AT). `escalating`: copy N pays `(N - 1) x surcharge`. `flat_additional`: every copy after the first pays the surcharge once. |
| `flagship.enabled` | false | |
| `flagship.immune_to_bans` | true | |
| `flagship.exempt_from_size_limit` | true | Requires a `FLAG` entry in `hull_sizes`; the flagship counts against `FLAG` instead of its natural size. |
| `flagship.counts_for_same_hull`, `counts_for_inflation` | true | Whether the flagship slot counts toward those checks. |
| `flagship.lost_permanently` | true | |
| `flagship.eligible_sizes` | `[BS]` | Default eligibility, with `eligible_meta_groups` (default `[Tech I, Tech II, Faction]`). Per-hull `flagship_eligible` in `ships` overrides. |
| `unique_ship_extra_bans` | 0 | Extra bans the opponent gets when a unique prize hull is declared. |
| `unspent_points_to_opponent` | true | Fielding under the cap concedes the difference. |
| `kill_points_source` | `comp_cost` | Or `kill_table`. |
| `match.tiebreak` | `none` | `potential_dps_t0`, `points_remaining`, `custom`. |
| `match.point_threshold` | null | Differential at which the scoreboard shows a decisive lead (the sheet's colour band). No match timing is modelled; results are entered after the fight. |
| `roster.max`, `roster.merc_max` | null | |
| `ships_inference` | `prefix` | `none`, `prefix` (a class named `"Keres (Electronic Attack Frigate)"` maps hull Keres), or `prefix_and_aliases` (also generic classes such as `Command Ship` by SDE group and faction). Explicit `ships` entries always win. |
| `extra` | `{}` | Edition quirks the engine does not read. |

## `hull_sizes[]`

`{ size, label, max_per_comp, duplicate_surcharge }`. Sizes: `FR DE CR BC BS IN CV LF LC FLAG`. `FLAG` may not carry a surcharge and is required exactly when the flagship is exempt from its size limit. Every size referenced elsewhere must be listed.

## `group_limits[]`

`{ code, label, max, message, members: [{ hull_size | class | hull, weight }] }`. Each slot matches at most one member per limit, the most specific (hull, then class, then size). AT logistics: `LC` weight 2, `LF` weight 1, `max` 2.

## `stages[]`

`{ code, label, best_of (1|3|5|7), bans_per_side, ban_order, blind, ban_targets (hull|class), deadline_minutes, avalanche: { loser, winner, blind, persists }, flagship_uses }`. `ban_order` is a string of `A` and `B` with exactly `bans_per_side` of each; `A` is the side that bans first. AT XXII main bracket: `ABBAABAB`. `avalanche` is only allowed in a best-of series. `flagship_uses` is how many matches of the series a flagship may be fielded in: AT XXII allows it in every main-tournament match until destroyed, so bracket and final carry their `best_of`, and prelims 0 (flagships banned there).

## `ship_classes[]` and `ships[]`

`ship_classes`: `{ name, size, points }` in the official order. `points` is required when `point_table` is present and forbidden otherwise.

`ships`: `{ hull, class, size, legality (legal|banned), flagship_eligible, unique }`. `class` must exist in `ship_classes`. The effective hull size is `size`, else the class size, else the T1 support hull table (Bantam, Burst, Inquisitor, Navitas are `LF`; Augoror, Osprey, Exequror, Scythe are `LC`), else the SDE group's natural size. `banned_hulls` and `unique_hulls` are shorthand; a hull marked `legality: legal` and listed in `banned_hulls` is an error. Export writes every hull explicitly, sorted, with default values omitted.

## `point_table`

`{ label, source_url, effective_from, hull_overrides: [{ hull, points }] }`. A hull override beats its class points. Re-importing with changed points creates a new version and keeps the old one (matches will pin versions); `--replace-points` rewrites the current version in place.

## `module_rules`

```yaml
module_rules:
  default: { allowed_meta_groups: [Tech I, Tech II] }
  by_group:
    - { groups: [Sensor Dampener, Weapon Disruptor], max_meta_level: 4, hulls: bonused_only }
    - { categories: [Implant], max_meta_level: 3 }
  banned_types: [Gecko, Aralez]
  banned_groups: [Booster]   # drugs of any sort
  allowed_name_patterns: ["Cerebral Accelerator$"]        # exempt from every check
  banned_name_patterns: ["^'(Augmented|Integrated)'\s"]    # regex on the item name
  flagship: { allowed_meta_groups: [Tech I, Tech II, Faction, Deadspace, Officer], groups: [] }
```

`by_group` entries need `groups` or `categories` (SDE names) and at least one of `max_meta_level`, `allowed_meta_groups`. `hulls: bonused_only` restricts the module to hulls with a bonus to it. A rule that names the item's SDE group replaces any rule that only names its category (so `Cyber Leadership` mindlinks escape the `Implant` meta cap).

`allowed_name_patterns` and `banned_name_patterns` are Python regular expressions matched against the item name, for distinctions the SDE does not carry: navy drones and `'Augmented'` drones share the Faction meta group, and cerebral accelerators sit in the banned `Booster` group. An allowed match skips every other check; a banned match is a `BANNED_TYPE` error. Patterns are trimmed like every other string in the document, so write `\s` rather than a trailing space.

How a fit is checked (`apps/rules/engine/modules.py`):

- Every EFT line (modules, charges, drones, implants, cargo) is resolved to an SDE type; unknown names are `UNRESOLVED_ITEM` warnings and never make a fit illegal.
- `allowed_name_patterns` first: a match is legal and skips the rest. Then `banned_name_patterns` and `banned_types` → `BANNED_TYPE` error; `banned_groups` (whole SDE groups, e.g. `Booster` for drugs) → `BANNED_GROUP` error.
- `default.allowed_meta_groups` applies to **modules and drones only**. Charges, implants, subsystems and deployables are checked only by `by_group` entries that name them.
- A `by_group` entry with `allowed_meta_groups` replaces the default set for its groups or categories. With the flagship toggle on, `flagship.allowed_meta_groups` is added on top (for every family when `groups` is empty, which would include drones; the AT XXII document lists the families the rules post names as SDE groups). Meta group misses are `META_GROUP_NOT_ALLOWED` errors.
- `max_meta_level` compares against the SDE `metaLevel`. Hardwiring implants have none, so the grade digit in the name is used (`EE-603` is 3, which is what CCP means by Meta 3). `hulls: bonused_only` misses are warnings until hull bonuses are checked. Elsewhere `META_LEVEL_TOO_HIGH` is an error; a missing level is `META_LEVEL_UNKNOWN`.

## Minimal example

```yaml
schema_version: 1
tournament: { code: AG7, name: Anger Games 7, organiser: community, server: thunderdome, year: 2026 }
ruleset:
  fielded_pilots: 7
  point_cap: 75
  max_same_hull: 1
hull_sizes:
  - { size: BS, label: Battleship }
  - { size: CR, label: Cruiser }
  - { size: FR, label: Frigate }
stages:
  - { code: single, best_of: 1, bans_per_side: 2, ban_order: ABBA, deadline_minutes: 45 }
```
