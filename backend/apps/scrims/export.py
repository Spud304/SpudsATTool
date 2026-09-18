"""The match-log CSV: one row per fielded slot of ours per fought round, in the sheet's column order.

The sheet's R users read these columns by name and position, so the leading block keeps the
sheet's names exactly (`docs/ARCHITECTURE.md` section 2); the identifiers after it are additions.
"""

import csv
import io
from collections.abc import Iterable

from .models import Outcome, Session
from .sets_api import set_documents

SHEET_COLUMNS = [
    "date",
    "pilot",
    "ship",
    "fate",
    "set",
    "round",
    "outcome",
    "flag",
    "opponent",
    *[f"opp_ship{i}" for i in range(1, 11)],
    "opp_flag_is",
    "our_archetype",
    "opp_archetype",
    "our_ban_side",
    *[f"team_a_ban{i}" for i in range(1, 7)],
    *[f"team_b_ban{i}" for i in range(1, 7)],
    "tournament",
]
EXTRA_COLUMNS = [
    "session_id",
    "set_id",
    "round_id",
    "assignment_id",
    "kind",
    "ship_points",
    "hull_size",
    "comp_name",
    "stage_code",
    "point_table_version",
]
COLUMNS = SHEET_COLUMNS + EXTRA_COLUMNS

OUTCOME_CODES = {Outcome.WIN: "1", Outcome.LOSS: "0"}


def _bans_for_side(doc: dict, side: str) -> list[str]:
    """Standard bans in pick order, then avalanche bans; padded to six as the sheet has six columns."""
    standard = [b["ship_name"] or "" for b in doc["bans"] if b["side"] == side]
    avalanche = [b["ship_name"] or "" for b in doc["avalanche_bans"] if b["side"] == side]
    names = (standard + avalanche)[:6]
    return names + [""] * (6 - len(names))


def match_log_rows(session: Session, archetypes: dict[int, str] | None = None) -> Iterable[dict]:
    archetypes = archetypes or {}
    date = session.date.date().isoformat()
    for doc in set_documents(session):
        team_a = _bans_for_side(doc, "A")
        team_b = _bans_for_side(doc, "B")
        for rnd in doc["rounds"]:
            if rnd["outcome"] == Outcome.RESET:
                continue
            opp_ships = [s["ship_name"] or "" for s in rnd["opp"]["slots"]]
            opp_flag = next((s["ship_name"] for s in rnd["opp"]["slots"] if s["is_flagship"]), "")
            for slot in rnd["us"]["slots"]:
                if slot["type_id"] is None:
                    continue
                yield {
                    "date": date,
                    "pilot": slot["pilot_name"] or "",
                    "ship": slot["ship_name"] or "",
                    "fate": "0" if slot["died"] else "1",
                    "set": doc["index"],
                    "round": rnd["round_no"],
                    "outcome": OUTCOME_CODES.get(rnd["outcome"], "NA"),
                    "flag": "1" if slot["is_flagship"] else "0",
                    "opponent": session.opponent.name if session.opponent else "",
                    **{
                        f"opp_ship{i}": (opp_ships[i - 1] if i <= len(opp_ships) else "")
                        for i in range(1, 11)
                    },
                    "opp_flag_is": opp_flag or "",
                    "our_archetype": archetypes.get(doc["our_archetype_id"] or -1, ""),
                    "opp_archetype": archetypes.get(doc["opp_archetype_id"] or -1, ""),
                    "our_ban_side": f"Team {doc['our_side']}",
                    **{f"team_a_ban{i}": team_a[i - 1] for i in range(1, 7)},
                    **{f"team_b_ban{i}": team_b[i - 1] for i in range(1, 7)},
                    "tournament": session.ruleset.code,
                    "session_id": session.pk,
                    "set_id": doc["id"],
                    "round_id": rnd["id"],
                    "assignment_id": slot["id"],
                    "kind": session.kind,
                    "ship_points": slot["total_points"],
                    "hull_size": slot["hull_size"] or "",
                    "comp_name": doc["comp_name"] or "",
                    "stage_code": session.stage.code if session.stage else "",
                    "point_table_version": session.point_table_version_id or "",
                }


def match_log_csv(session: Session, archetypes: dict[int, str] | None = None) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in match_log_rows(session, archetypes):
        writer.writerow(row)
    return out.getvalue()


def csv_filename(session: Session) -> str:
    safe = (
        "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in session.title)
        .strip()
        .replace(" ", "-")
    )
    return f"{safe or 'scrim'}-{session.date.date().isoformat()}.csv"
