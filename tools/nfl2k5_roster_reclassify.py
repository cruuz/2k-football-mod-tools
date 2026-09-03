#!/usr/bin/env python3
"""Reclassify NFL 2K5 ROST players into the one-pool defensive positions and re-rank them.

Context (``MODERN_POSITIONS_2026-09-03.md`` section 3.2c).  Under Option B the roster enums mean
``16 = EDGE`` (4-3 ends and 3-4 outside backers), ``15 = DT`` (every interior lineman) and
``11 = LB`` (every off-ball backer); ``10 = OLB`` is retired.  The team record carries a scheme
word at ``+0x150`` (read by ``FUN_000c40f0``: 0 = 4-3, 1 = 3-4, 2 = dual / hybrid; retail: BAL, HOU,
NE, PIT, SD = 1, DAL, MIN, NYJ, OAK = 2, everyone else 0) and its playbook is ``<label
abbreviation>-pb.iff``; the word decides (1 -> 3-4, 0 or 2 -> 4-3), the book's base categories are the
fallback for records with another value (pure 3-4 books BAL, HOU, NE, PIT, SD; dual books DAL, MIN,
NYJ, OAK, GEN, WCO, reference default to 4-3), and ``--three-four`` / ``--four-three`` override both.

Rules (explicit and deterministic; player ``+0x35`` = position enum, ``+0x28`` bits 10-12 = rank
order, bits 13-15 = side order):

* 4-3 team:  OLB (10) -> LB (11); ILB, DE (EDGE) and DT unchanged.
* 3-4 team:  OLB (10) -> EDGE (16); DE (16) -> DT (15); ILB and DT unchanged.
* players on no team (free agents, the draft/FA pool): OLB -> LB, nothing else; their rank bits
  are left alone.  The 68 secondary-pool records (the class generator's templates) stay as they
  are: they are keyed per enum and the generator never frees an enum-10 slot once none exists.
* historic resources (75 x 53 players, no label pair, no 3-4 book): the 4-3 rule.

Re-rank, per team, per new pool, so the recoded categories field the retail starters: the merged
order starts with the retail starters of each source position in the order the new codes expect,
then every remaining player by retail rank (ties: source position order, then roster slot):

* 4-3 LB   = [ILB rank 0 (MIKE), OLB rank 0 (WILL), OLB side 0 (SAM), rest]   -> ``LB0 LB1 LB2``
* 3-4 DT   = [DT rank 0 (nose), DE rank 0 (LDE), DE side 0 (RDE), rest]       -> ``DT0 DT1 DT2``
* every other pool = [rank 0, side 0, rest]                                   (unchanged starters)

then ``rank = index`` (capped at 7 like the game's ``FUN_00243790``) and the side field the way the
franchise auto depth chart writes it (``FUN_002bdcf0``: rank 0 -> 2, rank 1 -> 0, rank 2 -> 1,
else rank), so side row 0 is the #2, row 1 the #3 and the Depth Chart cave's ``chain 3`` (side row
1) shows the #3.  The four front pools are rewritten canonically for every team; other positions'
fields are untouched.  A player shared by several teams (Pro Bowl / alumni squads reuse NFL
players) is ranked by the first team that owns him in table order, which is his NFL team.

Retail check: the sha256 over the record areas (root, team records, both player tables, label
pairs) of all 76 ROST resources must equal the retail value before anything is written; the EDGE
rename only touches name strings, which are outside that area, so a disc with it reads retail.
``inspect`` prints every move per team; ``apply`` writes only the position byte and the rank/side
word of moved or re-ranked players inside the disc COPY and verifies the read-back.

Usage::

    nfl2k5_roster_reclassify.py inspect IMAGE_OR_PACK_DIR [--three-four DAL,MIN] [--team BAL] [--historic]
    nfl2k5_roster_reclassify.py status  IMAGE_OR_PACK_DIR
    nfl2k5_roster_reclassify.py apply   IMAGE.xiso.iso [--three-four ...] [--no-historic] [--receipt PATH]
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Callable, Iterable, Mapping, Sequence

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import nfl_roster as nr  # noqa: E402
from nfl2k5_playbook_position_recode import (  # noqa: E402
    BOOK_NAMES, OuterImage, RESOURCE_HEADER_SIZE, load_books,
)

POSITIONS = ("QB", "K", "P", "WR", "CB", "FS", "SS", "HB", "FB", "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE")
ENUM_OLB, ENUM_ILB, ENUM_DT, ENUM_DE = 10, 11, 15, 16
FRONT_ENUMS = (ENUM_OLB, ENUM_ILB, ENUM_DT, ENUM_DE)
POOL_LABEL = {ENUM_ILB: "LB", ENUM_DT: "DT", ENUM_DE: "EDGE", ENUM_OLB: "OLB"}
PLAYER_POSITION = 0x35
PLAYER_ORDER_WORD = 0x28
RANK_SHIFT, SIDE_SHIFT, ORDER_MASK = 10, 13, 0x7
ROW_CAP = 7
TEAM_KIND_NFL = 0
TEAM_SCHEME_WORD = 0x150            # 0 = 4-3, 1 = 3-4, 2 = dual (FUN_000c40f0's ILB / DT chain rule)
SCHEME_BY_WORD = {0: "4-3", 1: "3-4", 2: "4-3"}
MAIN_ROST_ENTRY = 5
HISTORIC_ROST_ENTRIES = range(113, 188)
PURE_THREE_FOUR_BOOKS = ("BAL", "HOU", "NE", "PIT", "SD")
DUAL_BOOKS = ("DAL", "MIN", "NYJ", "OAK", "GEN", "WCO", "reference")

# sha256 over the record areas of all 76 retail ROST resources, in outer-entry order
RETAIL_RECORD_SHA256 = "2ccb45c529bd7ac95b1a9b3ef99fa4c88db75e47cc35e0915de72f46a6bb164a"
# the same after the default pass (historic included, no scheme overrides)
APPLIED_RECORD_SHA256 = "74bc420124f9a9c7010e1b02601eb587066af8867132255476505b4b1c0f5dee"


class ReclassifyError(ValueError):
    """The roster pass cannot be applied to this image."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReclassifyError(message)


def side_for_rank(rank: int) -> int:
    """The franchise auto depth chart's side field for a rank (FUN_002bdcf0)."""

    return {0: 2, 1: 0, 2: 1}.get(rank, rank)


# ---------------------------------------------------------------------------------------------
# ROST resources
# ---------------------------------------------------------------------------------------------

@dataclass
class Player:
    offset: int                 # body offset of the 0x54 record
    position: int
    word: int                   # +0x28 (u16)
    name: str
    teams: list[int] = field(default_factory=list)

    @property
    def rank(self) -> int:
        return (self.word >> RANK_SHIFT) & ORDER_MASK

    @property
    def side(self) -> int:
        return (self.word >> SIDE_SHIFT) & ORDER_MASK


@dataclass
class Team:
    index: int
    offset: int
    name: str
    abbreviation: str
    kind: int
    label_abbreviation: str | None
    roster: list[int]           # player body offsets in slot order
    scheme_word: int = 0        # +0x150


@dataclass
class Resource:
    entry: int
    virtual_offset: int         # of the outer entry (wrapper included)
    label: str
    body: bytes
    tables: dict[str, dict[str, object]]
    players: dict[int, Player]  # by body offset
    teams: list[Team]

    def record_area(self) -> bytes:
        root = 0x40
        parts = [self.body[root: root + nr.NFL_ROOT_SIZE]]
        for name in ("primary_players", "secondary_players", "teams", "team_labels"):
            t = self.tables[name]
            parts.append(self.body[int(t["offset"]): int(t["end"])])
        return b"".join(parts)


def parse_resource(entry_index: int, virtual_offset: int, raw: bytes) -> Resource:
    magic, stored, sys_bytes, video_bytes, comp, _scratch, r0, r1 = struct.unpack_from("<4s7I", raw, 0)
    _require(magic == b"ROST" and comp == 0 and video_bytes == 0 and sys_bytes == stored and r0 == 0 and r1 == 0
             and len(raw) == RESOURCE_HEADER_SIZE + stored, f"outer {entry_index}: not an uncompressed ROST resource")
    body = raw[RESOURCE_HEADER_SIZE:]
    _require(body[0x0C:0x10] == b"ROST" and nr.u32(body, 0x10) == 17, f"outer {entry_index}: ROST preamble")
    root = nr.relative_pointer(body, 0x14, "root")
    _require(root == 0x40, f"outer {entry_index}: root at 0x{root:x}")
    label = nr.utf16z(body, 0x20, "label") or ""
    tables = nr.parse_tables(body, root, entry_index)
    players: dict[int, Player] = {}
    for pool in ("primary_players", "secondary_players"):
        t = tables[pool]
        for i in range(int(t["count"])):
            off = int(t["offset"]) + i * nr.NFL_PLAYER_STRIDE
            _, first = nr.string_pointer(body, off + 0x10, "first name")
            _, last = nr.string_pointer(body, off + 0x14, "last name")
            players[off] = Player(off, body[off + PLAYER_POSITION], struct.unpack_from("<H", body, off + PLAYER_ORDER_WORD)[0],
                                  f"{first or ''} {last or ''}".strip())
    labels = tables["team_labels"]
    label_abbrs: list[str | None] = []
    for i in range(int(labels["count"])):
        _, abbr = nr.string_pointer(body, int(labels["offset"]) + i * 8 + 4, "label abbreviation")
        label_abbrs.append(abbr)
    teams: list[Team] = []
    t = tables["teams"]
    for i in range(int(t["count"])):
        off = int(t["offset"]) + i * nr.NFL_TEAM_STRIDE
        size = body[off + 0x11C]
        roster = []
        for slot in range(min(size, nr.NFL_TEAM_SLOT_COUNT)):
            ptr = nr.relative_pointer(body, off + slot * 4, "roster slot")
            _require(ptr in players, f"outer {entry_index}: team {i} slot {slot} is not a player")
            roster.append(ptr)
            players[ptr].teams.append(i)
        _, nickname = nr.string_pointer(body, off + 0x104, "nickname")
        _, abbreviation = nr.string_pointer(body, off + 0x108, "abbreviation")
        _, city = nr.string_pointer(body, off + 0x138, "city")
        label_ptr = nr.relative_pointer(body, off + 0x110, "label pair")
        label_index = nr.index_for(label_ptr, labels)
        teams.append(Team(i, off, f"{city or ''} {nickname or ''}".strip(), abbreviation or "", nr.u32(body, off + 0x128),
                          label_abbrs[label_index] if label_index is not None else None, roster,
                          nr.u32(body, off + TEAM_SCHEME_WORD)))
    return Resource(entry_index, virtual_offset, label, body, tables, players, teams)


def load_resources(archive: OuterImage, *, historic: bool = True) -> list[Resource]:
    indices = [MAIN_ROST_ENTRY] + (list(HISTORIC_ROST_ENTRIES) if historic else [])
    out = []
    for index in indices:
        _require(index < len(archive.entries), f"archive has no outer entry {index}")
        entry = archive.entries[index]
        out.append(parse_resource(index, entry.virtual_offset, archive.read_entry(index)))
    _require(out[0].label == "roster", "outer entry 5 is not the main roster")
    return out


def record_digest(resources: Iterable[Resource]) -> str:
    h = hashlib.sha256()
    for r in resources:
        h.update(r.record_area())
    return h.hexdigest()


# ---------------------------------------------------------------------------------------------
# Scheme per team
# ---------------------------------------------------------------------------------------------

def book_schemes(archive: OuterImage, names: Sequence[str] | None = None) -> dict[str, str]:
    """'3-4', '4-3' or 'dual' per stock book, from its base category names."""

    out = {}
    for book in load_books(archive, names):
        names = {c.name for c in book.categories if (c.formation_type & 0x3F) == 0x0D}
        odd, even = "3-4" in names, "4-3" in names          # Bear / Defensive Drills are packages, not a base
        out[book.name] = "dual" if (odd and even) else "3-4" if odd else "4-3"
    return out


def team_scheme(team: Team, schemes: Mapping[str, str], three_four: Sequence[str] = (), four_three: Sequence[str] = ()) -> str:
    if team.abbreviation in three_four or team.label_abbreviation in three_four:
        return "3-4"
    if team.abbreviation in four_three or team.label_abbreviation in four_three:
        return "4-3"
    if team.scheme_word in SCHEME_BY_WORD:
        return SCHEME_BY_WORD[team.scheme_word]
    book = schemes.get(team.label_abbreviation or "")
    return "3-4" if book == "3-4" else "4-3"


# ---------------------------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------------------------

@dataclass
class Move:
    player: Player
    old_position: int
    new_position: int
    old_word: int
    new_word: int
    reason: str
    team: int | None = None     # the team whose order produced the move (None = unattached rule)

    @property
    def changed(self) -> bool:
        return self.old_position != self.new_position or self.old_word != self.new_word


def _ordered(players: Sequence[Player], key: str) -> list[Player]:
    return sorted(players, key=(lambda p: (p.rank, p.offset)) if key == "rank" else (lambda p: (p.side, p.offset)))


def merged_order(groups: Sequence[Sequence[Player]], starters: Sequence[tuple[int, str]]) -> list[Player]:
    """``starters`` = (group index, 'rank'|'side') picks in order; then every remaining player by
    retail rank, ties by group order then roster offset."""

    order: list[Player] = []
    for group, chain in starters:
        candidates = [p for p in _ordered(groups[group], chain) if p not in order]
        if candidates:
            order.append(candidates[0])
    rest = [(p.rank, g, p.offset, p) for g, group in enumerate(groups) for p in group if p not in order]
    order.extend(p for _r, _g, _o, p in sorted(rest, key=lambda t: t[:3]))
    return order


def pool_plan(scheme: str) -> dict[int, tuple[list[int], list[tuple[int, str]]]]:
    """new enum -> (source enums in group order, starter picks)."""

    if scheme == "3-4":
        return {ENUM_DE: ([ENUM_OLB], [(0, "rank"), (0, "side")]),
                ENUM_DT: ([ENUM_DT, ENUM_DE], [(0, "rank"), (1, "rank"), (1, "side")]),
                ENUM_ILB: ([ENUM_ILB], [(0, "rank"), (0, "side")])}
    return {ENUM_DE: ([ENUM_DE], [(0, "rank"), (0, "side")]),
            ENUM_DT: ([ENUM_DT], [(0, "rank"), (0, "side")]),
            ENUM_ILB: ([ENUM_ILB, ENUM_OLB], [(0, "rank"), (1, "rank"), (1, "side")])}


def plan_team(resource: Resource, team: Team, scheme: str, claimed: set[int]) -> list[Move]:
    """Moves for one team; players already ``claimed`` by an earlier team keep their fields."""

    moves: list[Move] = []
    by_position: dict[int, list[Player]] = {e: [] for e in FRONT_ENUMS}
    for off in team.roster:
        p = resource.players[off]
        if p.position in by_position:
            by_position[p.position].append(p)
    for new_enum, (sources, starters) in pool_plan(scheme).items():
        groups = [by_position[e] for e in sources]
        order = merged_order(groups, starters)
        for index, p in enumerate(order):
            rank = min(index, ROW_CAP)
            side = min(side_for_rank(rank), ROW_CAP)
            word = (p.word & ~((ORDER_MASK << RANK_SHIFT) | (ORDER_MASK << SIDE_SHIFT))) | (rank << RANK_SHIFT) | (side << SIDE_SHIFT)
            if p.offset in claimed:
                continue
            claimed.add(p.offset)
            reason = f"{scheme} {POSITIONS[p.position]}->{POOL_LABEL[new_enum]} #{index + 1}"
            moves.append(Move(p, p.position, new_enum, p.word, word, reason, team.index))
    return moves


def plan_resource(resource: Resource, schemes: Mapping[str, str], *, three_four: Sequence[str] = (),
                  four_three: Sequence[str] = ()) -> tuple[list[Move], dict[int, str]]:
    claimed: set[int] = set()
    moves: list[Move] = []
    team_schemes: dict[int, str] = {}
    for team in resource.teams:
        scheme = team_scheme(team, schemes, three_four, four_three) if resource.label == "roster" else "4-3"
        team_schemes[team.index] = scheme
        moves.extend(plan_team(resource, team, scheme, claimed))
    secondary = int(resource.tables["secondary_players"]["offset"])
    secondary_end = int(resource.tables["secondary_players"]["end"])
    for p in resource.players.values():
        if secondary <= p.offset < secondary_end:
            continue                        # the 68 class-generator templates stay keyed per enum
        if p.offset not in claimed and not p.teams and p.position == ENUM_OLB:
            moves.append(Move(p, ENUM_OLB, ENUM_ILB, p.word, p.word, "unattached OLB->LB"))
    return moves, team_schemes


def apply_moves(body: bytearray, moves: Iterable[Move]) -> int:
    changed = 0
    for m in moves:
        if not m.changed:
            continue
        body[m.player.offset + PLAYER_POSITION] = m.new_position
        struct.pack_into("<H", body, m.player.offset + PLAYER_ORDER_WORD, m.new_word)
        changed += 1
    return changed


# ---------------------------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------------------------

def team_report(resource: Resource, team: Team, scheme: str, moves: Sequence[Move]) -> dict[str, object]:
    mine = [m for m in moves if m.team == team.index]
    pools: dict[str, list[str]] = {}
    for m in sorted(mine, key=lambda m: (m.new_position, (m.new_word >> RANK_SHIFT) & ORDER_MASK, m.player.offset)):
        label = POOL_LABEL[m.new_position]
        tag = "" if m.old_position == m.new_position else f" (was {POSITIONS[m.old_position]})"
        pools.setdefault(label, []).append(f"{m.player.name}{tag}")
    counts = Counter(f"{POSITIONS[m.old_position]}->{POOL_LABEL[m.new_position]}" for m in mine if m.old_position != m.new_position)
    return {"team": team.name, "abbreviation": team.abbreviation, "kind": team.kind, "book": team.label_abbreviation,
            "scheme": scheme, "scheme_word": team.scheme_word, "moves": dict(counts),
            "reranked": sum(1 for m in mine if m.old_word != m.new_word), "pools": pools}


def format_report(reports: Iterable[dict[str, object]]) -> str:
    lines = []
    for r in reports:
        lines.append(f"== {r['team']} ({r['abbreviation']}, book {r['book']}, {r['scheme']}) moves {r['moves']} re-ranked {r['reranked']}")
        for label, names in r["pools"].items():  # type: ignore[union-attr]
            lines.append(f"   {label:<4} " + ", ".join(names))
    return "\n".join(lines)


def _open(path: Path | str, writable: bool) -> OuterImage:
    return OuterImage(path, writable=writable)


def status(path: Path | str, *, historic: bool = True) -> dict[str, object]:
    with _open(path, False) as archive:
        resources = load_resources(archive, historic=historic)
    digest = record_digest(resources)
    main = resources[0]
    nfl_olb = sum(1 for t in main.teams if t.kind == TEAM_KIND_NFL for off in t.roster if main.players[off].position == ENUM_OLB)
    state = ("retail" if digest == RETAIL_RECORD_SHA256 else "applied" if digest == APPLIED_RECORD_SHA256
             else "applied-custom" if nfl_olb == 0 else "foreign")
    return {"status": state, "record_sha256": digest, "nfl_olb_players": nfl_olb, "resources": len(resources)}


def inspect(path: Path | str, *, three_four: Sequence[str] = (), four_three: Sequence[str] = (),
            historic: bool = False, teams: Sequence[str] | None = None,
            schemes: Mapping[str, str] | None = None) -> list[dict[str, object]]:
    with _open(path, False) as archive:
        resources = load_resources(archive, historic=historic)
        schemes = book_schemes(archive) if schemes is None else dict(schemes)
    reports = []
    for resource in resources:
        moves, team_schemes = plan_resource(resource, schemes, three_four=three_four, four_three=four_three)
        for team in resource.teams:
            if teams and team.abbreviation not in teams and (team.label_abbreviation or "") not in teams:
                continue
            reports.append(team_report(resource, team, team_schemes[team.index], moves))
    return reports


def apply(path: Path | str, *, three_four: Sequence[str] = (), four_three: Sequence[str] = (), historic: bool = True,
          expected_digest: str | None = "retail", schemes: Mapping[str, str] | None = None,
          progress: Callable[[str], None] | None = None) -> dict[str, object]:
    """Reclassify and re-rank inside the image at ``path`` (a COPY).  Refuses non-retail record areas
    (``expected_digest``: "retail" = the embedded retail digest, a hex digest, or None to skip)."""

    say = progress or (lambda _m: None)
    with _open(path, True) as archive:
        resources = load_resources(archive, historic=historic)
        before = record_digest(resources)
        if expected_digest is not None:
            wanted = RETAIL_RECORD_SHA256 if expected_digest == "retail" else expected_digest
            _require(before == wanted, f"refusing: ROST record areas are not retail (sha256 {before[:16]}...)")
        schemes = book_schemes(archive) if schemes is None else dict(schemes)
        per_team: list[dict[str, object]] = []
        totals: Counter[str] = Counter()
        written = []
        for resource in resources:
            moves, team_schemes = plan_resource(resource, schemes, three_four=three_four, four_three=four_three)
            body = bytearray(resource.body)
            changed = apply_moves(body, moves)
            for team in resource.teams:
                per_team.append({"resource": resource.entry, **team_report(resource, team, team_schemes[team.index], moves)})
            totals.update(f"{POSITIONS[m.old_position]}->{POOL_LABEL[m.new_position]}" for m in moves if m.old_position != m.new_position)
            spans = []
            for m in moves:
                if not m.changed:
                    continue
                off = m.player.offset
                for rel, size in ((PLAYER_ORDER_WORD, 2), (PLAYER_POSITION, 1)):
                    virtual = resource.virtual_offset + RESOURCE_HEADER_SIZE + off + rel
                    count = archive.write(virtual, bytes(body[off + rel: off + rel + size]))
                    _require(count == size, f"outer {resource.entry}: short write")
                    spans.append(virtual)
            check = archive.read_entry(resource.entry)[RESOURCE_HEADER_SIZE:]
            _require(check == bytes(body), f"outer {resource.entry}: read-back differs")
            written.append({"resource": resource.entry, "label": resource.label, "players_changed": changed,
                            "spans": len(spans), "first_image_offset": f"0x{archive.image_offset(spans[0]):x}" if spans else None})
            say(f"outer {resource.entry} ({resource.label}): {changed} players rewritten")
        after_resources = load_resources(archive, historic=historic)
        after = record_digest(after_resources)
    main = after_resources[0]
    nfl_olb = sum(1 for t in main.teams if t.kind == TEAM_KIND_NFL for off in t.roster if main.players[off].position == ENUM_OLB)
    return {"schema": "nfl2k5_roster_reclassify/v1", "image": str(path), "three_four": list(three_four),
            "four_three": list(four_three), "historic": historic, "before_sha256": before, "after_sha256": after,
            "status": "applied" if after == APPLIED_RECORD_SHA256 else "applied-custom" if nfl_olb == 0 else "foreign",
            "totals": dict(totals), "resources": written, "teams": per_team,
            "changed_bytes": sum(3 for w in written for _ in range(int(w["players_changed"])))}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "apply"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("--three-four", default="", help="comma-separated team abbreviations forced to the 3-4 rule")
        p.add_argument("--four-three", default="", help="comma-separated team abbreviations forced to the 4-3 rule")
    sub.choices["inspect"].add_argument("--team", action="append", help="limit the listing to these teams")
    sub.choices["inspect"].add_argument("--historic", action="store_true", help="include the 75 historic resources")
    sub.choices["inspect"].add_argument("--json", action="store_true")
    sub.choices["apply"].add_argument("--no-historic", action="store_true", help="leave the 75 historic resources alone")
    sub.choices["apply"].add_argument("--receipt")
    p_status = sub.add_parser("status")
    p_status.add_argument("path")
    args = parser.parse_args(argv)
    split = lambda s: tuple(x for x in s.split(",") if x)  # noqa: E731
    if args.command == "status":
        print(json.dumps(status(args.path), indent=1))
        return 0
    if args.command == "inspect":
        reports = inspect(args.path, three_four=split(args.three_four), four_three=split(args.four_three),
                          historic=args.historic, teams=args.team)
        print(json.dumps(reports, indent=1) if args.json else format_report(reports))
        return 0
    receipt = apply(args.path, three_four=split(args.three_four), four_three=split(args.four_three),
                    historic=not args.no_historic, progress=print)
    if args.receipt:
        Path(args.receipt).write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "totals", "changed_bytes")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
