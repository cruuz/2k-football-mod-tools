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

``default_gadget_receivers`` sets the GAD default (WR side row 3) to the club's fastest receiver. Where he is the Z or
the side slot receiver (side rows 0 and 1, used by the base sets), the default is WR1, the X: on a gadget play he is
already on the field, so the slot keeps its own pick. ``default_special_rows`` applies both defaults in one pass.
"""
from __future__ import annotations

from typing import Any

from . import nfl2k5_roster_records as rr

HB, WR = 7, 3
CLUBS = range(32)


def _receiving(player: rr.Player) -> int:
    return int(player.record.values["catch"]) + int(player.record.values["run_route"])


def _speed(player: rr.Player) -> int:
    return int(player.record.values["speed"])


def _locked(slots, position):
    """The club's players at ``position`` who hold a locked chart row. b780 rst2: an injured player the refresh put back on
    the club is unlocked at the overflow row (rank 7); he is out, so he is never a default third-down back or gadget."""
    return [p for p in slots if p.record.values["position"] == position and p.record.values["depth_rank"] < rr.DEPTH_ROW_CAP]


def _orders(slots, players):
    side = sorted(players, key=lambda p: (p.record.values["depth_side"], slots.index(p)))
    rank = sorted(players, key=lambda p: (p.record.values["depth_rank"], slots.index(p)))
    return side, rank


def _write_side(order) -> int:
    moved = 0
    for row, player in enumerate(order):
        want = min(row, rr.DEPTH_ROW_CAP)
        if player.record.values["depth_side"] != want:
            player.record.values["depth_side"] = want
            moved += 1
    return moved


def _third_down(doc: rr.RosterDocument) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for club in range(min(len(CLUBS), len(doc.teams))):
        slots = doc.team_players(club)
        backs = _locked(slots, HB)
        if len(backs) < 2:
            continue
        side, rank = _orders(slots, backs)
        power = side[0]
        best = min((p for p in backs if p is not power), key=lambda p: (-_receiving(p), rank.index(p)))
        order = [power, best] + [p for p in side[1:] if p is not best]
        if order == side:
            continue                                   # already the default (or the user's own pick)
        changes.append({"club": club, "third_down_back_rank": rank.index(best) + 1,
                        "receiving": _receiving(best), "starter_receiving": _receiving(rank[0]),
                        "records_changed": _write_side(order)})
    return changes


def _gadgets(doc: rr.RosterDocument) -> list[dict[str, Any]]:
    """GAD = WR side row 3. The default is the fastest receiver (a tie goes to the higher-ranked one, starters
    included). Side rows 0 and 1 are the Z and the side slot receiver of the base sets, so a fastest receiver there
    cannot move: those clubs default to WR1, the X. On a gadget play he is already on the field (the X slot fills
    first), so the slot keeps its own pick, the fastest receiver. Moving a receiver from side row 2 (the kick-return
    WR ordinal 5) to row 3 hands that kick-return spot to the old row-3 receiver."""
    rows: list[dict[str, Any]] = []
    for club in range(min(len(CLUBS), len(doc.teams))):
        slots = doc.team_players(club)
        wrs = _locked(slots, WR)
        if len(wrs) < 4:
            rows.append({"club": club, "gad_rank": None, "reason": "fewer than four receivers", "changed": False})
            continue
        side, rank = _orders(slots, wrs)
        fastest = min(wrs, key=lambda p: (-_speed(p), rank.index(p)))
        exception = side.index(fastest) < 2
        target = rank[0] if exception else fastest
        row = {"club": club, "fastest_rank": rank.index(fastest) + 1, "fastest_side_row": side.index(fastest),
               "exception": exception}
        if side.index(target) < 2:                     # the X is a base-set side receiver here: leave the row alone
            rows.append({**row, "gad_rank": rank.index(side[3]) + 1, "reason": "the X is in side row 0 or 1",
                         "changed": False})
            continue
        order = [p for p in side if p is not target]
        order.insert(3, target)
        moved = _write_side(order) if order != side else 0
        rows.append({**row, "gad_rank": rank.index(target) + 1, "gad_speed": _speed(target), "changed": bool(moved),
                     "records_changed": moved})
    return rows


def default_third_down_backs(body: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    """(the new body, one row per club whose running back side order changed)."""
    doc = rr.RosterDocument(body)
    changes = _third_down(doc)
    return doc.to_body(normalise_commentary=False), changes


def default_gadget_receivers(body: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    """(the new body, one row per club: its GAD default, whether it is one of the exceptions, whether it changed)."""
    doc = rr.RosterDocument(body)
    rows = _gadgets(doc)
    return doc.to_body(normalise_commentary=False), rows


def default_special_rows(body: bytes) -> tuple[bytes, dict[str, list[dict[str, Any]]]]:
    """Both shipped defaults in one pass (RST2 runs this last on the final roster): the 3DRB (RB side row 1) and the
    GAD (WR side row 3). Only the side field of club running backs and receivers changes. Running it again changes
    nothing."""
    doc = rr.RosterDocument(body)
    report = {"third_down_backs": _third_down(doc), "gadgets": _gadgets(doc)}
    return doc.to_body(normalise_commentary=False), report
