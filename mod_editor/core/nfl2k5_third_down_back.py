"""The default SPECIAL third-down back in a shipped roster (b780 sub1; option (c), chosen by the coordinator 11/03).

The SPECIAL 3DRB row is the running back side order from its second place (side row 1, SPECIAL rows revision 3).
nfl2k5_lineup_roles brings that back in for the lead back on obvious passing downs. The 2026 roster tools write the
side order from the rank order (``DEPTH_SIDE_FOR_RANK``: RB2, RB3, the starter, ...). That made RB3 the third-down back
of every club with three or more backs (23 clubs on the v0.9 roster), and he would have taken those downs on a human
club whose user never set the row.

``default_third_down_backs`` puts each club's best receiving back at side row 1: the highest catch + route running,
the starter included and the power back (side row 0) excluded, with a tie going to the higher-ranked back. Side row 0
(the power back, RB2 by default) stays, and everyone else keeps his order. A backup therefore takes obvious passing
downs by default only when he is the better receiver. Only the side field of club running backs changes. Ranks,
locks, other positions and the non-club teams (all-star and historic) are untouched. Running it again changes
nothing.
"""
from __future__ import annotations

from typing import Any

from . import nfl2k5_roster_records as rr

HB = 7
CLUBS = range(32)


def _receiving(player: rr.Player) -> int:
    return int(player.record.values["catch"]) + int(player.record.values["run_route"])


def default_third_down_backs(body: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    """(the new body, one row per club whose running back side order changed)."""
    doc = rr.RosterDocument(body)
    changes: list[dict[str, Any]] = []
    for club in range(min(len(CLUBS), len(doc.teams))):
        slots = doc.team_players(club)
        backs = [p for p in slots if p.record.values["position"] == HB]
        if len(backs) < 2:
            continue
        side = sorted(backs, key=lambda p: (p.record.values["depth_side"], slots.index(p)))
        rank = sorted(backs, key=lambda p: (p.record.values["depth_rank"], slots.index(p)))
        power = side[0]
        best = min((p for p in backs if p is not power), key=lambda p: (-_receiving(p), rank.index(p)))
        order = [power, best] + [p for p in side[1:] if p is not best]
        if order == side:
            continue                                   # already the default (or the user's own pick)
        moved = 0
        for row, player in enumerate(order):
            want = min(row, rr.DEPTH_ROW_CAP)
            if player.record.values["depth_side"] != want:
                player.record.values["depth_side"] = want
                moved += 1
        if moved:
            changes.append({"club": club, "third_down_back_rank": rank.index(best) + 1,
                            "receiving": _receiving(best), "starter_receiving": _receiving(rank[0]),
                            "records_changed": moved})
    return doc.to_body(normalise_commentary=False), changes
