"""Parse the stats block Pyfa copies to the clipboard. Pure; returns None for anything missing."""

import re
from dataclasses import asdict, dataclass

_NUM = r"(?P<num>[\d.,]+)(?P<suffix>[kM])?"
DPS_RE = re.compile(r"DPS:\s*" + _NUM)
VOLLEY_RE = re.compile(r"Volley:\s*" + _NUM)
EHP_RE = re.compile(r"EHP:\s*" + _NUM)
SPEED_RE = re.compile(r"Speed:\s*(?P<num>[\d.,]+)\s*m/s")
SIG_RE = re.compile(r"Signature:\s*" + _NUM + r"\s*m\b")
CAP_RE = re.compile(
    r"Capacitor:\s*"
    + _NUM
    + r"\s*GJ\s*\((?:Stable at (?P<pct>[\d.]+)%|Lasts (?P<lasts>[^)]+)|(?P<unstable>Not stable))"
)
RANGE_RE = re.compile(r"Targeting range:\s*" + _NUM + r"\s*km")
DURATION_RE = re.compile(r"(?:(?P<h>\d+)h)?\s*(?:(?P<m>\d+)m)?\s*(?:(?P<s>\d+)s)?")

_MULTIPLIER = {None: 1.0, "k": 1_000.0, "M": 1_000_000.0}


@dataclass(frozen=True)
class PyfaStats:
    dps: float | None = None
    volley: float | None = None
    ehp_k: float | None = None
    speed_ms: float | None = None
    sig_radius_m: float | None = None
    cap_stable_pct: float | None = None
    cap_lasts_s: int | None = None
    targeting_range_km: float | None = None

    @property
    def ok(self) -> bool:
        """Pyfa omits the DPS block for unarmed fits, so only EHP and speed are mandatory."""
        return self.ehp_k is not None and self.speed_ms is not None

    def as_dict(self) -> dict:
        return asdict(self)


def _num(match: re.Match | None) -> float | None:
    if match is None:
        return None
    try:
        value = float(match.group("num").replace(",", ""))
    except ValueError:
        return None
    suffix = match.groupdict().get("suffix")
    return value * _MULTIPLIER[suffix]


def _duration_s(text: str) -> int | None:
    m = DURATION_RE.fullmatch(text.strip())
    if not m or not any(m.groupdict().values()):
        return None
    return int(m.group("h") or 0) * 3600 + int(m.group("m") or 0) * 60 + int(m.group("s") or 0)


def parse_pyfa_summary(text: str) -> PyfaStats:
    if not text or not text.strip():
        return PyfaStats()
    ehp = _num(EHP_RE.search(text))
    cap = CAP_RE.search(text)
    cap_pct = cap_lasts = None
    if cap:
        if cap.group("pct"):
            cap_pct = float(cap.group("pct"))
        elif cap.group("lasts"):
            cap_lasts = _duration_s(cap.group("lasts"))
    return PyfaStats(
        dps=_num(DPS_RE.search(text)),
        volley=_num(VOLLEY_RE.search(text)),
        ehp_k=ehp / 1000 if ehp is not None else None,
        speed_ms=_num(SPEED_RE.search(text)),
        sig_radius_m=_num(SIG_RE.search(text)),
        cap_stable_pct=cap_pct,
        cap_lasts_s=cap_lasts,
        targeting_range_km=_num(RANGE_RE.search(text)),
    )
