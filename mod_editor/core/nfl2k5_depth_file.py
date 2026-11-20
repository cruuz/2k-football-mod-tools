"""Finn's depth chart Export / Import and Backup / Restore Punt Returners, in his own file formats (b81 R43, row F13).

The formats were read from Finn's program (lane receipt ``finn-r2/re/RE_FACTS.md`` section 5, ``depth_pr_io.py``):

* ``.2k5dc`` (Depth Chart form, Export / Import), binary: for each player ``k`` of the club's pointer list, in list
  order, four bytes ``k, position (+0x35), depth rank, depth side`` (the Studio's ``depth_rank`` / ``depth_side`` at
  +0x29 bits 2-4 and 5-7); then the club's six special-teams bytes, team +0x194..+0x199 (holder, KR1, KR2, stored
  kicker, stored long snapper, PR; slot indexes into the pointer list, 0xFF = nobody).  Finn's import takes entry
  ``k`` for the club's player ``k`` only when the position byte still matches, and writes the six bytes raw.
* ``.NFL2k5PR`` (Tools > Backup and Restore), text: 32 lines ``i=v``, ``v`` = club ``i``'s PR byte (team +0x199).
  Finn's restore applies a value only when it is inside the club's list and that player is a WR, CB, FS, SS or RB.

Tailored to the mod.  The files stay Finn's, so they move between the two editors.  Applying one goes through the
Studio's own depth and special-teams writers instead of raw bytes: each position is seated with ``settle_depth``
(rows unique and gap-free; a player whose row changed gets the rank or side lock, as the Rosters arrows do, so the
SOFTDRINK weekly pass keeps the chart), and KR1, KR2, PR and the holder go through ``set_special_role``, which also
moves the returner's lock claim (+0x52) that the SOFTDRINK weekly pass follows.  Finn's raw byte write would leave
the claim on the old returner.  The stored kicker and long snapper bytes, which do not decide who plays, are written
as the file has them when they point inside the list.  Matching stays Finn's (list place and position; the file
names nobody), so the preview names every player before anything changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from . import nfl2k5_roster_records as rr

DEPTH_SUFFIX = ".2k5dc"
PR_SUFFIX = ".NFL2k5PR"
ROLE_ORDER = tuple(rr.SPECIAL_TEAM_OFFSETS)                 # h, kr1, kr2, k, ls, pr (team +0x194..+0x199)
NOBODY = 0xFF
CLUBS = 32
FINN_PR_CODES = (3, 4, 5, 6, 7)                             # Finn's restore: WR, CB, FS, SS, RB


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise rr.RosterRecordError(message)


def _club(document: rr.RosterDocument, team_index: int) -> rr.TeamRecord:
    _require(0 <= team_index < len(document.teams), f"club {team_index} is not in this roster")
    team = document.teams[team_index]
    _require(team.is_club, f"{team.display} is not a club")
    return team


# --------------------------------------------------------------------------------------------- depth chart
def export_depth_chart(document: rr.RosterDocument, team_index: int) -> bytes:
    """Finn's ``.2k5dc`` bytes for one club."""

    team = _club(document, team_index)
    _require(len(team.slots) < 256, "a pointer list longer than 255 does not fit Finn's one-byte index")
    out = bytearray()
    for k, offset in enumerate(team.slots):
        values = document.by_offset[offset].record.values
        out += bytes([k, values["position"], values["depth_rank"], values["depth_side"]])
    out += bytes(document._specialists(team))
    return bytes(out)


@dataclass
class DepthImportPlan:
    team: int
    rows: list[dict[str, Any]] = field(default_factory=list)       # one per player whose rank or side changes
    skipped: list[str] = field(default_factory=list)              # players Finn's rule leaves alone, and why
    roles: dict[str, int] = field(default_factory=dict)           # file's role byte per role key
    role_changes: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)             # anything here refuses the whole import

    @property
    def changes(self) -> int:
        return len(self.rows) + len(self.role_changes)


def _parse_depth(data: bytes) -> tuple[list[tuple[int, int, int, int]], list[int]]:
    _require(len(data) >= 6 and (len(data) - 6) % 4 == 0,
             f"this is not a Finn depth chart file: {len(data)} bytes is not 4 per player plus 6")
    count = (len(data) - 6) // 4
    entries = [tuple(data[4 * k:4 * k + 4]) for k in range(count)]
    for k, entry in enumerate(entries):
        _require(entry[0] == k, f"entry {k} of the file is numbered {entry[0]}: not a Finn depth chart file")
    return entries, list(data[-6:])                                    # type: ignore[return-value]


def plan_depth_import(document: rr.RosterDocument, team_index: int, data: bytes) -> DepthImportPlan:
    """What importing ``data`` onto the club would change, by Finn's matching rule; nothing is written."""

    team = _club(document, team_index)
    entries, roles = _parse_depth(data)
    plan = DepthImportPlan(team_index)
    if len(entries) != len(team.slots):
        plan.skipped.append(f"The file has {len(entries)} players and {team.display} has {len(team.slots)}; "
                            "players are matched by list place, as in Finn's editor.")
    for k, offset in enumerate(team.slots):
        player = document.by_offset[offset]
        values = player.record.values
        if k >= len(entries):
            plan.skipped.append(f"{player.display} (place {k + 1}): not in the file")
            continue
        _k, position, rank, side = entries[k]
        if position != values["position"]:
            plan.skipped.append(f"{player.display} (place {k + 1}): the file has a "
                                f"{rr.position_name(position, document.scheme)} there")
            continue
        if (rank, side) != (values["depth_rank"], values["depth_side"]):
            plan.rows.append({"player": player, "offset": offset, "position": position,
                              "rank": (values["depth_rank"], rank), "side": (values["depth_side"], side)})
    current = document._specialists(team)
    for key, value, now in zip(ROLE_ORDER, roles, current):
        if value != NOBODY and value >= len(team.slots):
            plan.problems.append(f"the file's {key.upper()} points at place {value + 1}; "
                                 f"{team.display} has {len(team.slots)} players")
            continue
        plan.roles[key] = value
        if value != now:
            who = document.by_offset[team.slots[value]].display if value != NOBODY else "nobody"
            plan.role_changes.append(f"{_ROLE_WORDS[key]}: {who}")
    for key in rr.RosterDocument.RETURNER_ROLES:
        value = plan.roles.get(key, NOBODY)
        if value != NOBODY:
            player = document.by_offset[team.slots[value]]
            if player.record.values["position"] not in rr.RosterDocument.RETURNER_CODES:
                plan.problems.append(f"the file makes {player.display} ({player.record.position_name}) "
                                     f"{_ROLE_WORDS[key]}; returners are WR, CB, FS, SS, HB or FB")
    return plan


_ROLE_WORDS = {"h": "holder", "kr1": "KR1", "kr2": "KR2", "k": "stored kicker", "ls": "stored long snapper",
               "pr": "PR"}


def apply_depth_import(document: rr.RosterDocument, plan: DepthImportPlan) -> dict[str, Any]:
    """Write a plan made by ``plan_depth_import`` through the Studio's depth and special-teams writers.

    Returns ``{"snapshot": ...}`` for ``RosterDocument.restore_special_teams`` (undo)."""

    _require(not plan.problems, "; ".join(plan.problems))
    team = _club(document, plan.team)
    snapshot = document.special_teams_snapshot(plan.team)
    try:
        by_code: dict[int, list[dict[str, Any]]] = {}
        for row in plan.rows:
            by_code.setdefault(row["position"], []).append(row)
        for code, rows in by_code.items():
            wanted = {row["offset"]: row for row in rows}
            fields = rr.DEPTH_FIELDS if code in rr.PAIRED_DEPTH_CODES else ("depth_rank",)
            for name in fields:
                column = 0 if name == "depth_rank" else 1
                order = document.depth_order(plan.team, code, name)
                place = {p.offset: i for i, p in enumerate(order)}
                target = {p.offset: (wanted[p.offset]["rank" if column == 0 else "side"][1] if p.offset in wanted
                                     else p.record.values[name]) for p in order}
                # rows unique and gap-free from 0 (row 7 is the game's shared overflow row), as settle_depth seats them
                seated = sorted(order, key=lambda p: (target[p.offset], place[p.offset]))
                for row_number, player in enumerate(seated):
                    new = min(row_number, rr.DEPTH_ROW_CAP)
                    if player.record.values[name] != new:
                        player.record.values[name] = new
                        player.record.values["unknown_52"] |= rr.DEPTH_LOCK_BITS[name]   # kept by the weekly pass
            if code in rr.PAIRED_DEPTH_CODES:
                ranks, sides = (document.depth_order(plan.team, code, name) for name in rr.DEPTH_FIELDS)
                _require(len(ranks) < 2 or ranks[0] is not sides[0],
                         f"the file would start {ranks[0].display if ranks else ''} on both sides at "
                         f"{rr.position_name(code, document.scheme)}; nothing was changed")
        for key in ("h",) + rr.RosterDocument.RETURNER_ROLES:
            if key in plan.roles:
                value = plan.roles[key]
                player = document.by_offset[team.slots[value]] if value != NOBODY else None
                document.set_special_role(plan.team, "holder" if key == "h" else key, player)
        values = document._specialists(team)
        for key in ("k", "ls"):
            if key in plan.roles:
                values[ROLE_ORDER.index(key)] = plan.roles[key]
        document._set_specialists(team, values)
        document.check_depth_locks()
    except Exception:
        document.restore_special_teams(snapshot)
        raise
    return {"snapshot": snapshot}


# --------------------------------------------------------------------------------------------- punt returners
def export_punt_returners(document: rr.RosterDocument) -> str:
    """Finn's ``.NFL2k5PR`` text: ``i=v`` for the 32 clubs, ``v`` = the PR byte."""

    lines = []
    for index in range(min(CLUBS, len(document.teams))):
        lines.append(f"{index}={document._specialists(document.teams[index])[ROLE_ORDER.index('pr')]}")
    return "\r\n".join(lines) + "\r\n"


def plan_punt_returner_restore(document: rr.RosterDocument, text: str) -> dict[str, Any]:
    """Which clubs get which PR back, by Finn's rule (inside the list, WR/CB/FS/SS/RB), and which are refused."""

    values: dict[int, int] = {}
    for line in text.replace("\r", "").split("\n"):
        key, sep, value = line.partition("=")
        if not sep:
            continue
        try:
            values[int(key.strip())] = int(value.strip())
        except ValueError:
            continue
    restore: list[tuple[int, int]] = []
    refused: list[str] = []
    for index in range(min(CLUBS, len(document.teams))):
        team = document.teams[index]
        if index not in values or values[index] in (-1, NOBODY):
            continue
        value = values[index]
        if not 0 <= value < len(team.slots):
            refused.append(f"{team.display}: place {value + 1} is outside its {len(team.slots)} players")
            continue
        player = document.by_offset[team.slots[value]]
        if player.record.values["position"] not in FINN_PR_CODES:
            refused.append(f"{team.display}: {player.display} is a {player.record.position_name}")
            continue
        if document._specialists(team)[ROLE_ORDER.index("pr")] != value:
            restore.append((index, value))
    return {"restore": restore, "refused": refused}


def apply_punt_returner_restore(document: rr.RosterDocument, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Set each planned PR through ``set_special_role`` (the claim moves with him). Returns the undo snapshots."""

    snapshots = []
    try:
        for index, value in plan["restore"]:
            snapshots.append(document.special_teams_snapshot(index))
            team = document.teams[index]
            document.set_special_role(index, "pr", document.by_offset[team.slots[value]])
        document.check_depth_locks()
    except Exception:
        for snapshot in reversed(snapshots):
            document.restore_special_teams(snapshot)
        raise
    return snapshots


def depth_import_text(document: rr.RosterDocument, plan: DepthImportPlan) -> str:
    """The preview, in words."""

    team = document.teams[plan.team]
    lines = [f"Depth chart file onto {team.display}: {len(plan.rows)} player(s) change row, "
             f"{len(plan.role_changes)} special-teams role(s) change."]
    for row in plan.rows:
        name = row["player"].display
        position = rr.position_name(row["position"], document.scheme)
        (rank_before, rank_after), (side_before, side_after) = row["rank"], row["side"]
        words = []
        if rank_before != rank_after:
            words.append(f"{position} row {rank_before + 1} -> {rank_after + 1}")
        if side_before != side_after:
            words.append(f"side order {side_before + 1} -> {side_after + 1}")
        lines.append(f"  {name}: {', '.join(words)}")
    lines += [f"  {text}" for text in plan.role_changes]
    if plan.skipped:
        lines.append("Left as they are:")
        lines += [f"  {text}" for text in plan.skipped]
    if plan.problems:
        lines.append("Refused:")
        lines += [f"  {text}" for text in plan.problems]
    return "\n".join(lines)


__all__ = ["DEPTH_SUFFIX", "PR_SUFFIX", "DepthImportPlan", "export_depth_chart", "plan_depth_import",
           "apply_depth_import", "export_punt_returners", "plan_punt_returner_restore", "apply_punt_returner_restore",
           "depth_import_text"]

