"""What a CPU defensive call IS, read from its executable assignments (b779 dp1).

A defensive call is a (formation, front, coverage) triple of one PLAY book.  The coach profile rings
(``nfl2k5_vip``) and the call-mix measurement both need to know, for every triple, the things the 2025 charting
counts: the defensive personnel (base / nickel / dime from the formation's category code), the coverage family
(Cover 0 / 1 / 2 / 2-Man / 3 / 4 / 6), man or zone, how many rush (five or more is a blitz; a three-down front's two
edge rushers count as one, the established project rule from b776 de2), simulated pressure (four rush but a
non-lineman is one of them), and the pre-snap shell against the post-snap one (a disguise).

PROVED OFFLINE: the inputs are the book's own bytes (assignment first actions 0x0B rush / 0x0D zone / 0x0E man, zone
depth, formation spots and each slot's leading Defense Start 0x1B).  DESIGN: the family thresholds are the ones the
SOFTDRINK defense generator classifies its library with (``pb/v2/defense/library.py``): 0 deep defenders with 4+ man
is Cover 0, 1 deep is Cover 1 (3+ man) or Cover 3 (zone), 2 deep is 2-Man (4+ man) or Cover 2, 3 deep is Cover 3,
Cover 6 (a half and two quarters) or a three-deep man, 4 deep is Cover 4.  No gameplay is claimed here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from . import nfl2k5_play_library as library
from . import nfl2k5_play_codec as codec
from . import nfl2k5_playbook_inspector as ip

YD = codec.YD_CM
DEEP_CM = 15 * YD - 1
DE, DT, MLB, OLB, FS, SS, CB = 12, 13, 14, 15, 16, 17, 18
LINE = (DE, DT)
SAFETIES = (FS, SS)
PERSONNEL = {13: "base", 14: "nickel", 15: "dime", 11: "goal_line", 16: "prevent", 12: "base"}
SINGLE_HIGH = ("C0", "C1", "C3")
TWO_HIGH = ("C2", "2M", "C4", "C6")
# Pre-snap shell: a safety at least this deep counts as "high"; two high safeties must stand this far apart.
HIGH_CM = 9 * YD
SPLIT_CM = 6 * YD


@dataclass(frozen=True)
class Call:
    formation: int
    front: int
    coverage: int
    formation_name: str
    front_name: str
    coverage_name: str
    type_code: int
    category_code: int
    personnel: str            # base / nickel / dime / goal_line / prevent
    bear: bool                # a Bear / 46 look (base personnel, eight in the box)
    family: str               # C0 C1 2M C2 C3 C4 C6 (or ZONE0 / ZONE1 for rare zero-deep / one-deep zone shells)
    man: bool                 # four or more man assignments
    rushers: int              # effective rushers (an odd front's two rushing edges count as one)
    raw_rushers: int
    blitz: bool               # five or more effective rushers
    sim: bool                 # four effective rushers, at least one of them not a lineman (sim / creeper)
    dl_drop: bool             # a lineman drops into coverage
    presnap: str              # "two" or "one" (high safeties before the snap) or "" when unknown
    postsnap: str             # "two" or "one" from the coverage family
    disguise: bool            # pre-snap shell differs from the post-snap shell
    front_band: int = 2       # the front's CPU score band (header bits 9-11; lower is called more by the native lottery)

    def to_json(self) -> dict:
        return asdict(self)


def _first(chain):
    for node in chain or ():
        if node[0] in (0x0B, 0x0D, 0x0E, 0x0F, 0x18):
            return node[0], list(node[1])
    return None, None


def _qqh(deep) -> bool:
    if len(deep) != 3:
        return False
    halves = [d for d in deep if d[3] == 11]
    quarters = [d for d in deep if d[3] in (9, 10) or (d[3] == 8 and abs(d[1]) > 3 * YD)]
    if len(halves) != 1 or len(quarters) != 2:
        return False
    hx = halves[0][1]
    return all((q[1] < 0) != (hx < 0) or abs(q[1]) < 2 * YD for q in quarters) and abs(hx) >= 6 * YD


def family_of(deep, man: int) -> str:
    n = len(deep)
    if n == 0:
        return "C0" if man >= 4 else "ZONE0"
    if n == 1:
        return "C1" if man >= 3 else "C3"
    if n == 2:
        return "2M" if man >= 4 else "C2"
    if n == 3:
        if _qqh(deep):
            return "C6"
        return "C1" if man >= 4 else "C3"
    return "C4" if man < 4 else "C1"


def presnap_point(spot, chain):
    """(x, z) cm where a defender stands before the snap, or None when the engine places him on a receiver."""
    x, z = float(spot[0]), float(spot[1])
    if not chain or chain[0][0] != 0x1B:
        return x, z
    ops = chain[0][1]
    mode = int(round(float(ops[0])))
    if mode == 0:
        return x + float(ops[2]), z + float(ops[3])
    if mode == 1:
        return float(ops[2]), float(ops[3])
    return None   # mode 2/3: aligned on a receiver (man leverage, press): not a high safety


def shell(points) -> str:
    """'two' when two safeties stand high and split, 'one' when at most one does, '' when a safety is unknown."""
    if any(p is None for p in points):
        high = [p for p in points if p is not None and p[1] >= HIGH_CM]
        return "one" if len(high) <= 1 else ""
    high = [p for p in points if p[1] >= HIGH_CM]
    if len(high) >= 2 and max(p[0] for p in high) - min(p[0] for p in high) >= SPLIT_CM:
        return "two"
    return "one"


def classify(book, body, formation: int, front: int, coverage: int) -> Call:
    rec = library.formation_record(body, formation)
    category = library.formation_category(body, formation)
    code = body[ip.CATEGORY_BASE + category * ip.CATEGORY_SIZE + 4] & 63
    kinds = [c & 31 for c in library.category_positions(body, category)]
    front_chains = library.decoded_chains(body, front)
    cover_chains = library.decoded_chains(body, coverage)
    chains = library.effective_defense(front_chains, cover_chains)
    odd = rec.type_code == 4
    rushers, man, deep = [], 0, []
    dl_drop = False
    for s in range(11):
        op, v = _first(chains[s])
        if op == 0x0B:
            rushers.append(s)
        elif op == 0x0E:
            man += 1
            dl_drop = dl_drop or kinds[s] in LINE
        elif op == 0x0D:
            if v[1] >= DEEP_CM:
                deep.append((s, v[0], v[1], int(v[4])))
            dl_drop = dl_drop or kinds[s] in LINE
    # A three-down front's edge rushers: the OLB-kind slots of the retail layout, which the SOFTDRINK position recode
    # turns into EDGE (DE kind) players; the front call rushes slots 1-3, so any DE/OLB in 0, 4, 5, 6 is an edge.
    edges = [s for s in (0, 4, 5, 6) if kinds[s] in (DE, OLB)] if odd else []
    credit = max(0, len([e for e in edges if e in rushers]) - 1)
    n = len(rushers) - credit
    non_line = [s for s in rushers if s not in edges and (kinds[s] not in LINE or (odd and s not in (1, 2, 3)))]
    family = family_of(deep, man)
    safeties = [s for s in range(11) if kinds[s] in SAFETIES]
    spots = [(rec.slots[s].x[0], rec.slots[s].z[0]) for s in safeties]
    pre = shell([presnap_point(spot, cover_chains[s] or front_chains[s]) for spot, s in zip(spots, safeties)])
    post = "one" if family in SINGLE_HIGH or family == "ZONE1" else "two" if family in TWO_HIGH else ""
    name = book.formations[formation].name.strip()
    return Call(formation, front, coverage, name, book.plays[front].name.strip(), book.plays[coverage].name.strip(),
                rec.type_code, code, PERSONNEL.get(code, "other"), "bear" in name.lower() or "46" in name,
                family, man >= 4, n, len(rushers), n >= 5, n == 4 and bool(non_line), dl_drop, pre, post,
                bool(pre and post and pre != post), (book.plays[front].flags_or_id >> 9) & 7)
