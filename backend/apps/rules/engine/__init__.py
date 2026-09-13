"""Pure rules engine: no Django, no I/O. Inputs are frozen dataclasses built by apps.rules.adapters."""

from .bans import (
    avalanche_allocation,
    ban_sequence,
    extra_bans_for_unique,
    flagship_uses_remaining,
)
from .comp import evaluate_comp, inflation_points
from .scoring import score_round
from .types import (
    BanInput,
    CompEvaluation,
    FlagshipRules,
    GroupLimit,
    GroupLimitMember,
    HullSpec,
    PointTable,
    RoundScore,
    RulesetSpec,
    SideScore,
    SizeRule,
    SlotEval,
    SlotInput,
    StageSpec,
    Violation,
)

__all__ = [
    "BanInput",
    "CompEvaluation",
    "FlagshipRules",
    "HullSpec",
    "PointTable",
    "GroupLimit",
    "GroupLimitMember",
    "RoundScore",
    "RulesetSpec",
    "SideScore",
    "SizeRule",
    "SlotEval",
    "SlotInput",
    "StageSpec",
    "Violation",
    "avalanche_allocation",
    "ban_sequence",
    "evaluate_comp",
    "extra_bans_for_unique",
    "flagship_uses_remaining",
    "inflation_points",
    "score_round",
]
