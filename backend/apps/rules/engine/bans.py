"""Ban-phase helpers: order, avalanche allocation, unique-hull extra bans, flagship uses."""

from collections.abc import Sequence

from . import codes
from .types import RulesetSpec, SlotInput, StageSpec


def ban_sequence(stage: StageSpec, first_side: str) -> tuple[str, ...]:
    """Expand the stage's A/B pattern into the sides that ban, in order."""
    other = codes.SIDE_B if first_side == codes.SIDE_A else codes.SIDE_A
    return tuple(first_side if ch == "A" else other for ch in stage.ban_order_pattern)


def avalanche_allocation(stage: StageSpec, game_winner: str) -> dict[str, int]:
    """Extra bans each side adds after a game in a series: loser more, winner fewer."""
    loser = codes.SIDE_B if game_winner == codes.SIDE_A else codes.SIDE_A
    if not stage.avalanche_enabled:
        return {game_winner: 0, loser: 0}
    return {game_winner: stage.avalanche_winner_bans, loser: stage.avalanche_loser_bans}


def extra_bans_for_unique(slots: Sequence[SlotInput], spec: RulesetSpec) -> int:
    return spec.unique_ship_extra_bans if any(s.is_unique for s in slots) else 0


def flagship_uses_remaining(
    stage: StageSpec, uses_so_far: int, destroyed: bool, spec: RulesetSpec
) -> int:
    if not spec.flagship.enabled or (destroyed and spec.flagship.lost_permanently):
        return 0
    return max(stage.flagship_uses - uses_so_far, 0)
