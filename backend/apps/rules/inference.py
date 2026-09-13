"""Map hulls to official class names without listing every ship: hull-prefixed classes, then group aliases."""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from apps.sde import constants as sde

from .constants import T1_SUPPORT_HULL_SIZES

PREFIX_RE = re.compile(r"^(?P<hull>.+?) \(")

T1_DISRUPTION_FRIGATES = {"Crucifier", "Griffin", "Maulus", "Vigil"}
T1_DISRUPTION_CRUISERS = {"Arbitrator", "Blackbird", "Celestis", "Bellicose"}


@dataclass(frozen=True)
class HullFacts:
    type_id: int
    name: str
    group_id: int
    meta_group: str | None  # "Tech I", "Tech II", "Faction", ...
    faction_id: int | None


def hull_prefix(class_name: str) -> str | None:
    """'Keres (Electronic Attack Frigate)' -> 'Keres'; generic classes give None."""
    match = PREFIX_RE.match(class_name)
    return match.group("hull") if match else None


def infer_prefix(hulls: Iterable[HullFacts], class_names: Iterable[str]) -> dict[int, str]:
    by_prefix: dict[str, str] = {}
    for name in class_names:
        prefix = hull_prefix(name)
        if prefix is not None and prefix not in by_prefix:
            by_prefix[prefix] = name
    return {h.type_id: by_prefix[h.name] for h in hulls if h.name in by_prefix}


def _empire(h: HullFacts) -> bool:
    return h.faction_id in sde.EMPIRE_FACTIONS


def _pirate(h: HullFacts) -> bool:
    return h.faction_id in sde.PIRATE_FACTIONS


def _t1(h: HullFacts) -> bool:
    return h.meta_group == "Tech I"


def _faction_meta(h: HullFacts) -> bool:
    return h.meta_group == "Faction"


def _in(*groups: int) -> Callable[[HullFacts], bool]:
    return lambda h: h.group_id in groups


def _named(names: set[str]) -> Callable[[HullFacts], bool]:
    return lambda h: h.name in names


def _all(*preds: Callable[[HullFacts], bool]) -> Callable[[HullFacts], bool]:
    return lambda h: all(p(h) for p in preds)


def _plain_t1(group: int, excluded: set[str]) -> Callable[[HullFacts], bool]:
    return lambda h: h.group_id == group and _t1(h) and h.name not in excluded


# Ordered most-specific first; the first alias whose class exists in the document wins.
CLASS_ALIASES: tuple[tuple[str, Callable[[HullFacts], bool]], ...] = (
    ("Tech 1 Support Frigate", _named({n for n, s in T1_SUPPORT_HULL_SIZES.items() if s == "LF"})),
    ("Tech 1 Support Cruiser", _named({n for n, s in T1_SUPPORT_HULL_SIZES.items() if s == "LC"})),
    ("Tech 1 Disruption Frigate", _named(T1_DISRUPTION_FRIGATES)),
    ("Tech 1 Disruption Cruiser", _named(T1_DISRUPTION_CRUISERS)),
    ("Command Ship", _in(sde.GROUP_COMMAND_SHIP)),
    ("Command Destroyer", _in(sde.GROUP_COMMAND_DESTROYER)),
    ("Logistics Cruiser", _in(sde.GROUP_LOGISTICS)),
    ("Logistics Frigate", _in(sde.GROUP_LOGISTICS_FRIGATE)),
    ("Heavy Assault Cruiser", _in(sde.GROUP_HEAVY_ASSAULT_CRUISER)),
    ("Heavy Interdictor", _in(sde.GROUP_HEAVY_INTERDICTION_CRUISER)),
    ("Strategic Cruiser", _in(sde.GROUP_STRATEGIC_CRUISER)),
    ("Recon Ship", _in(sde.GROUP_FORCE_RECON, sde.GROUP_COMBAT_RECON)),
    ("Electronic Attack Frigate", _in(sde.GROUP_ELECTRONIC_ATTACK_SHIP)),
    ("Assault Frigate", _all(_in(sde.GROUP_ASSAULT_FRIGATE), lambda h: h.meta_group == "Tech II")),
    ("Interceptor", _in(sde.GROUP_INTERCEPTOR)),
    ("Interdictor", _in(sde.GROUP_INTERDICTOR)),
    ("Stealth Bomber", _in(sde.GROUP_STEALTH_BOMBER)),
    ("Covert Ops Ship", _in(sde.GROUP_COVERT_OPS)),
    ("Tactical Destroyer", _in(sde.GROUP_TACTICAL_DESTROYER)),
    ("Marauder", _in(sde.GROUP_MARAUDER)),
    ("Black Ops Battleship", _in(sde.GROUP_BLACK_OPS)),
    ("Battleship, Pirate Faction", _all(_in(sde.GROUP_BATTLESHIP), _pirate)),
    ("Battleship, Navy Faction", _all(_in(sde.GROUP_BATTLESHIP), _empire, _faction_meta)),
    ("Battleship", _plain_t1(sde.GROUP_BATTLESHIP, set())),
    (
        "Battlecruiser, Pirate Faction",
        _all(_in(sde.GROUP_COMBAT_BATTLECRUISER, sde.GROUP_ATTACK_BATTLECRUISER), _pirate),
    ),
    (
        "Battlecruiser, Navy Faction",
        _all(
            _in(sde.GROUP_COMBAT_BATTLECRUISER, sde.GROUP_ATTACK_BATTLECRUISER),
            _empire,
            _faction_meta,
        ),
    ),
    ("Combat Battlecruiser", _plain_t1(sde.GROUP_COMBAT_BATTLECRUISER, set())),
    ("Attack Battlecruiser", _plain_t1(sde.GROUP_ATTACK_BATTLECRUISER, set())),
    ("Cruiser, Pirate Faction", _all(_in(sde.GROUP_CRUISER), _pirate)),
    ("Cruiser, Navy Faction", _all(_in(sde.GROUP_CRUISER), _empire, _faction_meta)),
    ("Cruiser", _plain_t1(sde.GROUP_CRUISER, T1_DISRUPTION_CRUISERS | set(T1_SUPPORT_HULL_SIZES))),
    ("Destroyer, Pirate Faction", _all(_in(sde.GROUP_DESTROYER), _pirate)),
    ("Destroyer, Navy Faction", _all(_in(sde.GROUP_DESTROYER), _empire, _faction_meta)),
    ("Destroyer", _plain_t1(sde.GROUP_DESTROYER, set())),
    ("Frigate, Pirate Faction", _all(_in(sde.GROUP_FRIGATE), _pirate)),
    ("Frigate, Navy Faction", _all(_in(sde.GROUP_FRIGATE), _empire, _faction_meta)),
    ("Frigate", _plain_t1(sde.GROUP_FRIGATE, T1_DISRUPTION_FRIGATES | set(T1_SUPPORT_HULL_SIZES))),
    ("Tech 1 Industrial Ships", _all(_in(sde.GROUP_HAULER), _t1)),
    ("Tech 2 Industrial Ships", _in(sde.GROUP_BLOCKADE_RUNNER, sde.GROUP_DEEP_SPACE_TRANSPORT)),
    ("Rookie Ship, Pirate Faction", _all(_in(sde.GROUP_CORVETTE), _pirate)),
)


def infer_aliases(
    hulls: Iterable[HullFacts], class_names: Iterable[str]
) -> tuple[dict[int, str], list[str]]:
    """Assign generic classes by SDE facts. Returns (type_id -> class, warnings)."""
    present = set(class_names)
    aliases = [(name, pred) for name, pred in CLASS_ALIASES if name in present]
    out: dict[int, str] = {}
    warnings: list[str] = []
    for hull in hulls:
        matches = [name for name, pred in aliases if pred(hull)]
        if not matches:
            continue
        if len(matches) > 1:
            warnings.append(f"{hull.name}: matches {matches}; using {matches[0]}")
        out[hull.type_id] = matches[0]
    return out, warnings
