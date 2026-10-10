#!/usr/bin/env python3
"""SOFTDRINK defense v2: retail coverage library, classifier and front geometry.

PROVED OFFLINE inputs only: every coverage script here is a retail 2K5 script (decoded from the 37 retail PLAY
resources); the classifier reads its effective structure (rushers, deep zones, man, exchanges) together with the
formation's native 4-man (even) or 3-man (odd) front. Names are DESIGN labels for those structures, chosen to match
the modern NFL vocabulary (Cover 3 Sky/Buzz/Cloud, Cover 1 Robber, 2-Man, Fire Zone, Sim Pressure, ...).
No gameplay was witnessed.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
for p in (str(ROOT), str(ROOT / 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402

YD = codec.YD_CM
DEEP_CM = 15 * YD - 1
RETAIL_IMAGE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
TEAM_BOOKS = ('ARZ', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX',
              'KC', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'OAK', 'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL', 'TB', 'TEN',
              'WAS')
ORDINARY = ('4-3', '3-4', 'Nickel', 'Dime', 'Bear')
KIND = {12: 'DE', 13: 'DT', 14: 'MLB', 15: 'OLB', 16: 'FS', 17: 'SS', 18: 'CB'}

# ---------------------------------------------------------------------------------------------------------------
# Line geometry (PROVED OFFLINE from 831 retail offensive formations: C 0, G +-152 cm, T +-304 cm; inline TE +-457).
# Authored defensive frame: -x is the strength (retail "Strong Blast" plays rush the -x linebacker, and 412 of 432
# single-TE retail formations put the TE at -x; 0x20B820 mirrors the defense against the offense's mirror bit).
# Technique centres in cm from the ball, strong side negative. DESIGN numbers, one third of a 5-ft OL split per shade.
# ---------------------------------------------------------------------------------------------------------------
TECH = {'0': 0, '1': 50, '2i': 100, '2': 152, '3': 200, '4i': 255, '4': 304, '5': 365, '7': 420, '6': 457,
        '9': 515, 'w5': 430, 'w9': 560}
LANE_CM = codec.LANE_TABLE_CM


def lane_for(x_cm: float) -> int:
    """Nearest rush lane (0..16) to a lateral point."""
    return min(range(17), key=lambda i: (abs(LANE_CM[i] - x_cm), i))


def gap_lane(tech: str, side: int) -> int:
    """The gap a one-gap defender in this technique owns (side -1 strong / +1 weak), as a rush lane.
    A gaps lanes 7/9, B 5/11, C 3/13; D (outside the tight end) 1, strong side only. The weak side has no tight end,
    so its outermost gap is C (outside the tackle)."""
    owns = {'0': 'A', '1': 'A', '2i': 'A', '2': 'B', '3': 'B', '4i': 'B', '4': 'C', '5': 'C', '7': 'C', '6': 'D',
            '9': 'D', 'w5': 'D', 'w9': 'D'}[tech]
    if side > 0 and owns == 'D':
        owns = 'C'
    offset = {'A': 1, 'B': 3, 'C': 5, 'D': 7}[owns]
    return 8 + side * offset


# ---------------------------------------------------------------------------------------------------------------
# Coverage structure
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Structure:
    layout: str                      # formation family key, e.g. 'even:Nickel'
    rushers: list[int]
    dropped_dl: list[int]
    man: list[int]
    deep: list[tuple[int, float, float, int]]      # slot, x, y, mode
    under: list[tuple[int, float, float, int]]
    exchanges: list[int]
    other: list[int]
    family: str = ''
    variant: str = ''
    label: str = ''
    pressure: bool = False
    tags: list[str] = field(default_factory=list)

    @property
    def n_rush(self) -> int:
        return len(self.rushers)


def first_action(chain):
    for op, v, *_ in chain:
        if op in (0x0B, 0x0D, 0x0E, 0x0F, 0x18):
            return op, list(v)
    return None, None


def has_exchange(chain) -> bool:
    ops = [n[0] for n in chain]
    return 0x0D in ops and 0x0E in ops


def structure(chains, kinds: list[int], front_slots: set[int], layout: str) -> Structure:
    """Effective front+coverage structure of a coverage component, the formation's front rushing its slots."""
    active = lib.defense_active(chains)
    st = Structure(layout, [], [], [], [], [], [], [])
    for s in range(11):
        if s in front_slots and s not in active:
            st.rushers.append(s)
            continue
        if s not in active:
            continue
        op, v = first_action(chains[s])
        if has_exchange(chains[s]):
            st.exchanges.append(s)
        if op == 0x0B:
            st.rushers.append(s)
        elif op == 0x0E:
            st.man.append(s)
            if s in front_slots:
                st.dropped_dl.append(s)
        elif op == 0x0D:
            row = (s, v[0], v[1], int(v[4]))
            (st.deep if v[1] >= DEEP_CM else st.under).append(row)
            if s in front_slots:
                st.dropped_dl.append(s)
        else:
            st.other.append(s)
    classify(st, kinds)
    return st


def _qqh(deep) -> bool:
    if len(deep) != 3:
        return False
    halves = [d for d in deep if d[3] == 11]
    quarters = [d for d in deep if d[3] in (9, 10) or (d[3] == 8 and abs(d[1]) > 3 * YD)]
    if len(halves) != 1 or len(quarters) != 2:
        return False
    hx = halves[0][1]
    return all((q[1] < 0) != (hx < 0) or abs(q[1]) < 2 * YD for q in quarters) and abs(hx) >= 6 * YD


def classify(st: Structure, kinds: list[int]) -> None:
    deep = len(st.deep)
    man = len(st.man)
    rush = st.n_rush
    k = lambda s: KIND.get(kinds[s] & 31, '?')
    st.pressure = rush >= 5
    if st.layout.endswith('Prevent'):
        st.family, st.label = 'PREVENT', 'Prevent'
        return
    if st.layout.endswith('Goalline'):
        st.family = 'GOALLINE'
        st.label = 'Goal Line'
        return
    if st.exchanges and man <= 4:
        st.tags.append('match')
    if deep == 0:
        if man >= 4:
            st.family = 'C0'
        else:
            st.family = 'ZONE0'
    elif deep == 1:
        st.family = 'C1' if man >= 3 else 'ZONE1'
        if st.family == 'C1':
            mids = [u for u in st.under if abs(u[1]) <= 7 * YD and 5 * YD <= u[2] < DEEP_CM]
            if mids:
                st.tags.append('robber')
                if k(mids[0][0]) in ('FS', 'SS'):
                    st.tags.append('safety-robber')
            if any(u[2] < 5 * YD and abs(u[1]) < 3 * YD for u in st.under):
                st.tags.append('spy-hole')
    elif deep == 2:
        st.family = '2M' if man >= 4 else 'C2'
        if st.family == 'C2':
            cbs = [u for u in st.under if k(u[0]) == 'CB']
            if cbs and all(u[2] <= 3 * YD for u in cbs):
                st.tags.append('hard')
            elif cbs:
                st.tags.append('soft')
            mid_lb = [d for d in st.deep if k(d[0]) in ('MLB', 'OLB')]
            if mid_lb:
                st.family = 'TAMPA'
    elif deep == 3:
        if _qqh(st.deep):
            st.family = 'C6'
        elif man >= 4:
            st.family = 'C1'
            st.tags.append('3-deep-man')
        else:
            st.family = 'C3'
            flats = [u for u in st.under if abs(u[1]) >= 9 * YD]
            hooks = [u for u in st.under if abs(u[1]) < 9 * YD]
            if any(k(u[0]) == 'CB' for u in flats):
                st.tags.append('cloud')
            elif any(k(u[0]) in ('FS', 'SS') for u in flats):
                st.tags.append('sky')
            elif any(k(u[0]) in ('FS', 'SS') for u in hooks):
                st.tags.append('buzz')
            else:
                st.tags.append('sky')
    else:
        st.family = 'C4' if man < 4 else 'C1'
    # pressures and sims
    if st.dropped_dl and rush == 4 and any(r not in range(4) or r in st.dropped_dl for r in st.rushers):
        st.tags.append('sim')
    if st.dropped_dl and rush >= 5:
        st.tags.append('zone-dog')
    if rush >= 6:
        st.tags.append('all-out')
    st.label = label(st, kinds)


def label(st: Structure, kinds) -> str:
    f = st.family
    t = set(st.tags)
    rush = st.n_rush
    if f == 'C0':
        return 'Cover 0 Blitz' if rush >= 6 else 'Cover 0 Pressure'
    if f == 'C1':
        if rush >= 5:
            return 'Cover 1 Blitz'
        if 'robber' in t:
            return 'Cover 1 Robber'
        if 'spy-hole' in t:
            return 'Cover 1 Hole'
        return 'Cover 1'
    if f == '2M':
        return '2-Man Blitz' if rush >= 5 else '2-Man Under'
    if f == 'TAMPA':
        return 'Tampa 2'
    if f == 'C2':
        if rush >= 5:
            return 'Cover 2 Fire'
        if 'sim' in t:
            return 'Cover 2 Sim'
        return 'Cover 2 Hard' if 'hard' in t else 'Cover 2'
    if f == 'C3':
        if rush >= 5:
            return 'Fire Zone 3'
        if 'sim' in t:
            return 'Sim Pressure 3'
        if 'match' in t:
            return 'Cover 3 Match'
        return {'cloud': 'Cover 3 Cloud', 'buzz': 'Cover 3 Buzz'}.get(next((x for x in ('cloud', 'buzz') if x in t), ''),
                                                                       'Cover 3 Sky')
    if f == 'C6':
        return 'Cover 6 Pressure' if rush >= 5 else 'Cover 6'
    if f == 'C4':
        if rush >= 5:
            return 'Quarters Pressure'
        return 'Cover 4 Match' if 'match' in t else 'Cover 4 Quarters'
    if f == 'ZONE0':
        return 'Zero Zone'
    if f == 'ZONE1':
        return 'Cover 1 Zone'
    return f.title()


# ---------------------------------------------------------------------------------------------------------------
# Retail library
# ---------------------------------------------------------------------------------------------------------------
def layout_key(book, body, fi) -> tuple[str, tuple[int, ...], int]:
    rec = lib.formation_record(body, fi)
    codes = tuple(lib.category_positions(body, lib.formation_category(body, fi)))
    return book.formations[fi].name, codes, rec.type_code


def front_slots_for(book, body, fi) -> set[int]:
    """Slots the formation's retail fronts activate (union over its front menu)."""
    slots = set()
    for p in book.plays_for_formation(fi):
        if p.family_id != 1:
            continue
        chains = lib.decoded_chains(body, p.index)
        if lib.defense_component(chains) == 'front':
            slots |= lib.defense_active(chains)
    return slots


@dataclass
class Script:
    book: str
    play_index: int
    name: str
    flags: int
    formation: str
    codes: tuple[int, ...]
    type_code: int
    chains: list
    struct: Structure
    key: str

    def to_json(self):
        return dict(book=self.book, play=self.play_index, name=self.name, flags=self.flags, formation=self.formation,
                    family=self.struct.family, label=self.struct.label, tags=self.struct.tags, rushers=self.struct.rushers,
                    dropped=self.struct.dropped_dl, man=self.struct.man, deep=[d[0] for d in self.struct.deep], key=self.key)


def chains_key(chains) -> str:
    return json.dumps([[(n[0], [round(float(x), 2) for x in n[1]]) for n in c] for c in chains])


def scan_book(team: str, raw: bytes) -> list[Script]:
    book = ip.parse_playbook_resource(raw)
    body = raw[ip.RESOURCE_HEADER_SIZE:]
    out = []
    for f in book.formations:
        rec = lib.formation_record(body, f.index)
        if not 4 <= rec.type_code <= 7:
            continue
        fname, codes, tcode = layout_key(book, body, f.index)
        fslots = front_slots_for(book, body, f.index)
        kinds = [c & 31 for c in codes]
        lay = ('odd:' if tcode == 4 else 'even:') + fname
        for p in book.plays_for_formation(f.index):
            if p.family_id != 1 or (p.flags_or_id & 63) not in (tcode, 14):
                continue
            chains = lib.decoded_chains(body, p.index)
            if lib.defense_component(chains) != 'coverage':
                continue
            st = structure(chains, kinds, fslots, lay)
            out.append(Script(team, p.index, p.name, p.flags_or_id, fname, codes, tcode, chains, st, chains_key(chains)))
    return out


def retail_library(image: Path = RETAIL_IMAGE, books=TEAM_BOOKS) -> list[Script]:
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    rows = []
    with OuterImage(image) as img:
        for t in books:
            rows.extend(scan_book(t, img.read_entry(BOOK_ENTRIES[t])))
    return rows


if __name__ == '__main__':  # quick census
    rows = retail_library()
    fam = Counter((r.formation, r.struct.label) for r in rows)
    for k, v in sorted(fam.items()):
        print(k, v)
