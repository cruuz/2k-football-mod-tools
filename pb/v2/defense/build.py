#!/usr/bin/env python3
"""SOFTDRINK defense generator v2 (beta 77, job p48d).

DESIGN on PROVED OFFLINE inputs:
  * fronts: every lineman on a real technique (design.py), one-gap rush lanes per technique, never two defenders within
    1.7 yd, no standing defender inside the tackles near the ball except the named Mug pressure look;
  * coverages: whole retail 2K5 coverage scripts (with their native 0x1B pre-snap alignment nodes), classified by
    structure (library.py) and renamed with the modern vocabulary; authored only where retail has no such structure;
  * situation: formation ratings (bits 21-29, 0x207EF0) per role and per-play CPU score bands (bits 9-11, 0x203F20)
    fitted to each coordinator's sourced 2025 coverage/blitz rates (pb/research/defense_tendencies_2025.json);
  * the pack pins the exact offense compile it is applied after (Build order: offense, then defense).

Run (job worktree only; it writes data/playbooks/softdrink_<team>_defense.2k5book and pb/v2/defense/out/*):
  python3 pb/v2/defense/build.py [--team KC] [--offense-dir data/playbooks] [--workers 4]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (str(HERE), str(ROOT), str(ROOT / 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)
sys.dont_write_bytecode = True

import library as L  # noqa: E402
import design as D  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as pk  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_defense_lint as dlint  # noqa: E402

OUT = HERE / 'out'
VERSION = '2.0.0'
AUTHOR = 'SOFTDRINK / Claude Opus 5.5 (p48d)'
NEUTRAL_START = (0x1B, [0, 0, 0, 0, 0, 0])
PRESSURE_BIT = 0x10000
BAND_CURVE = (2.0, 1.4, 1.0, 0.5, 0.1, 0.1, 0.1, 0.1)
# 0x203F20 multiplies a pressure-tagged (0x10000) pair by 1.6 - 0.15 * m, m = the native player matchup 0x205660
# (1.525 at m = 0.5, PROVED OFFLINE test_inherited_header_curve).  m depends on the players and the play; the native
# call-mix fixture showed effective multipliers of about 0.6 to 1.2.  DESIGN: the fit assumes 1.0 (m = 4, the middle
# of the scale), so blitz frequency is neither tuned to an optimistic nor a pessimistic matchup.
MATCHUP_MULT = 1.0


def weight(band: int, pressure: bool) -> float:
    return (BAND_CURVE[band] * (MATCHUP_MULT if pressure else 1.0)) ** 3


# ---------------------------------------------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------------------------------------------
def offense_pack_path(team: str, offense_dir: Path) -> Path:
    name = 'giants' if team == 'NYG' else team.lower()
    return offense_dir / f'softdrink_{name}_modern.2k5book'


def compiled_source(team: str, offense_dir: Path, image: Path = L.RETAIL_IMAGE) -> tuple[bytes, Path]:
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    path = offense_pack_path(team, offense_dir)
    with OuterImage(image) as img:
        raw = img.read_entry(BOOK_ENTRIES[team])
        source = pk.apply_pack_to_resource(raw, pk.load_pack(path), xbe=img.path).replacement
    return source, path


# ---------------------------------------------------------------------------------------------------------------
# Roles: which native formation plays which part
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Role:
    key: str                    # base, base2, bear, nickel, dime, nickel_odd, dime_odd, mug
    fi: int | None              # source formation index (None until an appended clone is compiled)
    source_name: str
    name: str                   # display name
    type_code: int
    codes: tuple
    kinds: list
    category_index: int
    category_code: int
    positions: dict = field(default_factory=dict)
    situation: tuple | None = None
    family: str = ''
    donor_fi: int | None = None  # for appended formations, and for the Bear merged into the base personnel group
    keep_geometry: bool = False
    merged: bool = False         # Bear moved into the 4-3 personnel group (same personnel), so ratings choose it


def detect_roles(book, body, team: str, scheme: D.Scheme) -> dict[str, Role]:
    roles = {}
    by_name = {}
    for f in book.formations:
        rec = lib.formation_record(body, f.index)
        if not 4 <= rec.type_code <= 7:
            continue
        info = lib.defense_personnel(book, body, f.index)
        by_name[f.name] = Role('', f.index, f.name, f.name, rec.type_code, tuple(info['codes']),
                               [c & 31 for c in info['codes']], info['category_index'], info['category_code'])
    odd_book = '3-4' in by_name and '4-3' not in by_name
    both = '3-4' in by_name and '4-3' in by_name

    def take(key, src, name):
        if src in by_name:
            r = copy.copy(by_name[src])
            r.key, r.name = key, name
            roles[key] = r

    if odd_book:
        take('base', '3-4', '3-4 Okie')
    elif both:
        if scheme.family == 'odd':
            take('base', '3-4', '3-4 Okie')
            take('base2', '4-3', '4-3 Wide')
        else:
            take('base', '4-3', '4-3 Over')
            take('base2', '3-4', '3-4 Okie')
    else:
        take('base', '4-3', '4-3 Wide' if scheme.family == 'odd' else '4-3 Over')
    nk = by_name.get('Nickel')
    if nk is not None:
        odd = nk.type_code == 4
        take('nickel', 'Nickel', 'Nickel Okie' if odd else ('Nickel Wide' if scheme.family == 'odd' else 'Nickel Over'))
    dm = by_name.get('Dime')
    if dm is not None:
        take('dime', 'Dime', 'Dime Okie' if dm.type_code == 4 else ('Dime Wide' if scheme.family == 'odd' else 'Dime Over'))
    take('bear', 'Bear', 'Bear 46')
    take('nickel_odd', '3-3', 'Nickel 3-3 Okie')
    take('dime_odd', '3-2', 'Dime 3-2 Okie')
    take('dime_odd', 'Dime Odd', 'Dime 3-2 Okie')
    # The 5-2 (OAK) and Goalline/Prevent stay retail.
    return roles


def role_family(role: Role, scheme: D.Scheme) -> D.LineFamily:
    if role.type_code == 4:
        return D.ODD
    if role.key == 'bear':
        return D.BEAR
    if role.key == 'mug':
        return D.MUG
    return D.WIDE if scheme.family == 'odd' else D.OVER


def role_positions(role: Role, scheme: D.Scheme, retail_xy) -> dict:
    fam = role_family(role, scheme)
    role.family = fam.name
    k = role.kinds
    if role.type_code == 4:
        moved = D.odd_front(k, base=role.key in ('base', 'base2'))
    elif role.key in ('base', 'base2'):
        moved = D.base_43(fam, k)
    elif role.key == 'bear':
        moved = D.bear(fam, k)
    elif role.key == 'nickel':
        moved = D.nickel_even(fam, k)
    elif role.key == 'dime':
        moved = D.dime_even(fam, k)
    elif role.key == 'mug':
        moved = D.mug(k)
    else:
        moved = {}
    xy = list(retail_xy)
    for s, p in moved.items():
        xy[s] = (int(p[0]), int(p[1]))
    return xy


ROLE_SITUATION = {'base': 'base', 'base2': 'base', 'bear': 'bear', 'nickel': 'nickel', 'dime': 'dime',
                  'nickel_odd': 'odd_nickel', 'dime_odd': 'odd_dime', 'mug': 'mug'}


# ---------------------------------------------------------------------------------------------------------------
# Coverage targets (DESIGN mapping of sourced 2025 FTN coverage families onto the structure labels)
# ---------------------------------------------------------------------------------------------------------------
FAMILY_OF = {
    'Cover 0 Blitz': 'C0', 'Cover 0 Pressure': 'C0', 'Zero Zone': 'C0',
    'Cover 1': 'C1', 'Cover 1 Robber': 'C1', 'Cover 1 Hole': 'C1', 'Cover 1 Blitz': 'C1', 'Cover 1 Zone': 'C1',
    '2-Man Under': '2M', '2-Man Blitz': '2M',
    'Cover 2': 'C2', 'Cover 2 Hard': 'C2', 'Cover 2 Sim': 'C2', 'Cover 2 Fire': 'C2', 'Tampa 2': 'C2',
    'Cover 3 Sky': 'C3', 'Cover 3 Buzz': 'C3', 'Cover 3 Cloud': 'C3', 'Cover 3 Match': 'C3', 'Fire Zone 3': 'C3',
    'Sim Pressure 3': 'C3',
    'Cover 4 Quarters': 'C4', 'Cover 4 Match': 'C4', 'Quarters Pressure': 'C4',
    'Cover 6': 'C6', 'Cover 6 Pressure': 'C6',
}
BLITZ = {'Cover 0 Blitz', 'Cover 0 Pressure', 'Cover 1 Blitz', '2-Man Blitz', 'Cover 2 Fire', 'Fire Zone 3',
         'Quarters Pressure', 'Cover 6 Pressure', 'Zero Zone', 'Cover 1 Zone'}
SPLIT_IN = {
    'C0': {'Cover 0 Blitz': 1.0},
    'C1': {'Cover 1 Robber': .30, 'Cover 1': .15, 'Cover 1 Blitz': .55},
    '2M': {'2-Man Under': .8, '2-Man Blitz': .2},
    'C2': {'Cover 2': .45, 'Cover 2 Hard': .30, 'Cover 2 Sim': .15, 'Cover 2 Fire': .10},
    'C3': {'Cover 3 Sky': .28, 'Cover 3 Buzz': .22, 'Cover 3 Cloud': .18, 'Cover 3 Match': .07, 'Fire Zone 3': .15,
           'Sim Pressure 3': .10},
    'C4': {'Cover 4 Quarters': .75, 'Cover 4 Match': .25},
    'C6': {'Cover 6': 1.0},
}
ROLE_TILT = {   # multipliers on the FTN family shares, then the blitz share multiplier
    'base': ({'C0': .8, 'C1': 1.1, '2M': .5, 'C2': .9, 'C3': 1.3, 'C4': 1.0, 'C6': .8}, .85),
    'nickel': ({}, 1.0),
    'dime': ({'C0': 1.1, 'C1': .9, '2M': 1.8, 'C2': 1.3, 'C3': .6, 'C4': 1.3, 'C6': 1.3}, 1.1),
    'bear': ({'C0': 2.5, 'C1': 1.6, '2M': .4, 'C2': .5, 'C3': 1.0, 'C4': .4, 'C6': .1}, 1.9),
    'mug': ({'C0': 2.0, 'C1': 1.4, '2M': .6, 'C2': .9, 'C3': 1.2, 'C4': .5, 'C6': .5}, 2.0),
}


def coverage_targets(rates: dict, role_key: str, scheme: D.Scheme) -> dict[str, float]:
    counts = dict(rates['coverage_counts'])
    counts['COVER_6'] = counts.get('COVER_6', 0) + counts.pop('COVER_9', 0)
    counts.pop('COMBO', None)
    fam = {'C0': counts.get('COVER_0', 0), 'C1': counts.get('COVER_1', 0), '2M': counts.get('2_MAN', 0),
           'C2': counts.get('COVER_2', 0), 'C3': counts.get('COVER_3', 0), 'C4': counts.get('COVER_4', 0),
           'C6': counts.get('COVER_6', 0)}
    tilt, blitz_mult = ROLE_TILT.get({'base2': 'base', 'nickel_odd': 'nickel', 'dime_odd': 'dime'}.get(role_key, role_key),
                                     ({}, 1.0))
    fam = {k: v * tilt.get(k, 1.0) for k, v in fam.items()}
    total = sum(fam.values())
    out: dict[str, float] = {}
    for f, v in fam.items():
        for c, share in SPLIT_IN[f].items():
            out[c] = out.get(c, 0) + v / total * share
    # Package emphasis (P6): the coordinator's signature calls.
    for c in scheme.package:
        for k in list(out):
            if k == c or k.startswith(c):
                out[k] *= 1.35
    if 'Tampa 2' in scheme.package:
        out['Tampa 2'] = out.get('Cover 2', 0) * .5
    # Blitz share (5+ rushers) to the sourced rate, tilted by role.
    want = min(.75, rates['rates']['blitz'] / 100 * blitz_mult)
    cur = sum(v for k, v in out.items() if k in BLITZ)
    rest = sum(v for k, v in out.items() if k not in BLITZ)
    if cur > 0 and rest > 0:
        out = {k: (v * want / cur if k in BLITZ else v * (1 - want) / rest) for k, v in out.items()}
    s = sum(out.values())
    return {k: v / s for k, v in sorted(out.items(), key=lambda kv: -kv[1]) if v / s >= .004}


# ---------------------------------------------------------------------------------------------------------------
# Team plan
# ---------------------------------------------------------------------------------------------------------------
ROLE_PRIORITY = ('nickel', 'base', 'dime', 'mug', 'nickel_odd', 'dime_odd', 'base2', 'bear')
SPY_PIN = {'KC': (21,)}      # v0.5 QB-spy runtime intent: book KC, play 21, slot 5


@dataclass
class Slot:
    """One play record the pack rewrites."""
    index: int                      # play index (source book)
    component: str                  # 'front' | 'coverage'
    roles: set
    content: object = None          # FrontCall or Choice
    name: str = ''
    band: int = 2
    pressure: bool = False
    extra_links: set = field(default_factory=set)   # roles this record is newly linked into
    note: str = ''
    appended: bool = False


@dataclass
class Choice:
    concept: str
    script: L.Script | None = None   # retail script (chains + its own retail header)
    chains: list | None = None       # authored chains (when not a whole retail script)
    donor_index: int | None = None   # local donor record supplying header/signature
    spy_slots: tuple = ()
    note: str = ''
    base_flags: int | None = None


def membership(book, body, roles: dict[str, Role]) -> dict[int, Slot]:
    slots: dict[int, Slot] = {}
    for key, role in roles.items():
        if role.fi is None:
            continue
        for p in book.plays_for_formation(role.fi):
            if p.family_id != 1 or (p.flags_or_id & 63) not in (role.type_code, 14):
                continue
            comp = lib.defense_component(lib.decoded_chains(body, p.index))
            if comp not in ('front', 'coverage'):
                continue
            s = slots.setdefault(p.index, Slot(p.index, comp, set()))
            s.roles.add(key)
    return slots


def home_role(roles: set) -> str:
    return next(r for r in ROLE_PRIORITY if r in roles)


def assign_fronts(slots: dict[int, Slot], roles: dict[str, Role], scheme: D.Scheme, team: str, pool: 'RecordPool'):
    """Fronts by sharing group; Bear/Dime/Mug get extra dedicated fronts (appended or spare records)."""
    groups: dict[frozenset, list[int]] = defaultdict(list)
    for s in slots.values():
        if s.component == 'front':
            groups[frozenset(s.roles)].append(s.index)
    plan = []
    for grp, idx in groups.items():
        idx.sort()
        types = {roles[r].type_code for r in grp}
        if types == {4}:
            calls = D.odd_fronts()
        elif grp == frozenset({'bear'}):
            calls = D.bear_fronts(full=True)
        else:
            primary = next(r for r in ROLE_PRIORITY if r in grp and r != 'bear')
            calls = D.four_down_fronts(role_family_obj(roles[primary], scheme))
        if len(idx) > len(calls):
            raise ValueError(f'{team}: front group {sorted(grp)} has {len(idx)} records for {len(calls)} calls')
        for i, call in zip(idx, calls):
            set_front(slots[i], call)
        plan.append((sorted(grp), [(i, slots[i].name) for i in idx]))
    # Dedicated fronts: Bear (when it shares the four-down group), Dime and Mug.
    four_group = next((g for g in groups if 'bear' in g and len(g) > 1), None)
    if four_group is not None:
        for call in D.bear_fronts():
            i = pool.take('bear', 'front')
            if i is None:
                break
            set_front(slots[i], call)
    if 'dime' in roles and roles['dime'].type_code == 5:
        for call in D.dime_fronts():
            i = pool.take('dime', 'front')
            if i is None:
                break
            set_front(slots[i], call)
    if 'mug' in roles:
        for call in D.mug_fronts():
            i = pool.take('mug', 'front')
            if i is None:
                break
            set_front(slots[i], call)
    return plan


def set_front(slot: Slot, call: D.FrontCall) -> None:
    slot.component = 'front'
    slot.content = call
    slot.name = call.name
    slot.band = call.band


class RecordPool:
    """Where extra calls live: appended records while the book has play capacity, otherwise spare records that
    only one formation lists (a spare Bear-only record keeps its Bear link as well)."""

    def __init__(self, slots: dict[int, Slot], book, roles: dict[str, Role]):
        self.slots = slots
        self.roles = roles
        self.capacity = pk.PLAY_CAPACITY - len(book.plays)
        self.next_index = len(book.plays)
        only = lambda key: sorted(i for i, s in slots.items() if s.roles == {key} and s.component == 'coverage')
        self.spare = {'bear': only('bear'), 'dime': only('dime')}
        self.keep = {'bear': 10, 'dime': 3}
        self.appended: list[int] = []

    def can_append(self) -> bool:
        return self.capacity > 0

    def take(self, target: str, component: str) -> int | None:
        if target == 'bear':
            return self._spare('bear')
        if self.capacity > 0:
            i = self.next_index
            self.next_index += 1
            self.capacity -= 1
            self.slots[i] = Slot(i, component, {target}, extra_links={target})
            self.slots[i].appended = True
            self.appended.append(i)
            return i
        if target == 'dime':
            return self._spare('dime', link='dime')
        if target == 'mug' and component == 'coverage':
            return self._spare('bear', link='mug')
        return None

    def _spare(self, key: str, link: str | None = None) -> int | None:
        if len(self.spare[key]) <= self.keep[key]:
            return None
        i = self.spare[key].pop(0)
        if link and link != key:
            self.slots[i].roles.add(link)
            self.slots[i].extra_links.add(link)
        return i


def role_family_obj(role: Role, scheme: D.Scheme) -> D.LineFamily:
    return role_family(role, scheme)


def allocate_counts(targets: dict[str, float], n: int) -> dict[str, int]:
    """Plays per concept for one formation menu: every concept worth >= 2.5% gets one, the rest by largest remainder."""
    keep = {c: v for c, v in targets.items() if v >= .025}
    if len(keep) > n:
        keep = dict(sorted(keep.items(), key=lambda kv: -kv[1])[:n])
    counts = {c: 1 for c in keep}
    left = n - len(counts)
    if left > 0:
        tot = sum(keep.values())
        raw = {c: v / tot * left for c, v in keep.items()}
        add = {c: int(math.floor(x)) for c, x in raw.items()}
        rem = left - sum(add.values())
        for c, _ in sorted(raw.items(), key=lambda kv: -(kv[1] - math.floor(kv[1])))[:rem]:
            add[c] += 1
        for c, k in add.items():
            counts[c] += k
    return counts


def assign_concepts(slots: dict[int, Slot], targets: dict[str, dict[str, float]]) -> dict[str, dict[str, int]]:
    cov = [s for s in slots.values() if s.component == 'coverage' and s.content is None]
    need = {}
    for role, tgt in targets.items():
        n = sum(1 for s in cov if role in s.roles)
        need[role] = allocate_counts(tgt, n) if n else {}
    # Most-shared records first: a shared record must serve every menu that lists it.
    for s in sorted(cov, key=lambda s: (-len(s.roles), s.index)):
        best, score = None, -1e9
        for c in set().union(*(set(targets[r]) for r in s.roles if r in targets)):
            sc = sum(need[r].get(c, 0) * 10 + targets[r].get(c, 0) for r in s.roles if r in targets)
            if any(c not in targets.get(r, {}) for r in s.roles):
                sc -= 50
            if sc > score:
                best, score = c, sc
        s.content = Choice(best)
        for r in s.roles:
            if r in need and need[r].get(best, 0) > 0:
                need[r][best] -= 1
    return need


class Library:
    """League library of retail scripts by formation layout and structure label."""

    def __init__(self, scripts: list[L.Script]):
        self.by_layout: dict[tuple, dict[str, list[L.Script]]] = defaultdict(lambda: defaultdict(list))
        self.own: dict[str, list[L.Script]] = defaultdict(list)
        self.popularity: Counter = Counter()
        books_with = defaultdict(set)
        for sc in scripts:
            books_with[sc.key].add(sc.book)
            self.own[sc.book].append(sc)
        self.popularity.update({k: len(v) for k, v in books_with.items()})
        # One entry per (layout, chainset) per book, so a team's own copy can be preferred.
        seen = set()
        for sc in scripts:
            key = (sc.formation, sc.codes)
            if (key, sc.key, sc.book) in seen:
                continue
            seen.add((key, sc.key, sc.book))
            self.by_layout[key][sc.struct.label].append(sc)

    def candidates(self, formation: str, codes: tuple, label: str) -> list[L.Script]:
        return list(self.by_layout.get((formation, codes), {}).get(label, []))

    def any_layout(self, codes: tuple, label: str) -> list[L.Script]:
        out = []
        for (fname, c), labels in self.by_layout.items():
            if c == codes:
                out.extend(labels.get(label, []))
        return out

    def same_type(self, type_code: int, label: str) -> list[L.Script]:
        out = []
        for (fname, c), labels in self.by_layout.items():
            for sc in labels.get(label, []):
                if sc.type_code == type_code:
                    out.append(sc)
        return out


PRESET_FOR = {
    'Cover 6': ('lib', 'Cover 6 Split Field'), 'Cover 4 Quarters': ('lib', 'Cover 4 Quarters (spot)'),
    'Tampa 2': ('lib', 'Tampa 2 Drop EXPERIMENTAL'), 'Cover 3 Match': ('match', 'Cover 3 Rip exchange EXPERIMENTAL'),
    'Cover 4 Match': ('match', 'Quarters exchange EXPERIMENTAL'), 'Cover 1 Robber': ('match', 'Cover 1 Robber EXPERIMENTAL'),
    'Cover 2': ('lib', 'Cover 2 Soft'), 'Cover 2 Hard': ('lib', 'Cover 2 Hard'), 'Cover 1': ('lib', 'Cover 1'),
    '2-Man Under': ('lib', 'Cover 2 Man'), 'Cover 0 Blitz': ('lib', 'Cover 0'),
    'Fire Zone 3': ('lib', 'Fire 3 Replacement (5 rush)'), 'Sim Pressure 3': ('lib', 'Replacement 3 (4 rush)'),
    'Cover 3 Sky': ('lib', 'Cover 3'), 'Cover 3 Buzz': ('lib', 'Cover 3'), 'Cover 3 Cloud': ('lib', 'Cover 3'),
}


def preset_choice(concept: str, role: Role, book, body):
    kind_name = PRESET_FOR.get(concept)
    if kind_name is None:
        return None
    from mod_editor.core import nfl2k5_match_coverage as match
    kind, preset = kind_name
    try:
        d = (match.make_match_design if kind == 'match' else lib.make_defense_design)(book, body, role.fi, preset)
    except Exception:
        return None
    chains = [[(n[0], list(n[1])) for n in c] if c else c for c in d.chains]
    return Choice(concept, chains=chains, base_flags=book.plays[d.donor_play_index].flags_or_id,
                  note=f'authored preset {preset} on {role.source_name}')


FALLBACK_LABELS = {
    'Cover 1': ('Cover 1 Robber', 'Cover 1 Hole'), 'Cover 1 Robber': ('Cover 1', 'Cover 1 Hole'),
    'Cover 1 Hole': ('Cover 1 Robber', 'Cover 1'),
    'Cover 3 Match': ('Cover 3 Buzz', 'Cover 3 Cloud'), 'Cover 4 Match': ('Cover 4 Quarters', 'Cover 6'),
    'Cover 2 Hard': ('Cover 2',), 'Cover 2': ('Cover 2 Hard',), 'Cover 2 Sim': ('Sim Pressure 3', 'Cover 2'),
    'Sim Pressure 3': ('Cover 2 Sim', 'Fire Zone 3'), 'Cover 2 Fire': ('Fire Zone 3', 'Cover 1 Blitz'),
    'Cover 6': ('Cover 4 Quarters',), 'Cover 4 Quarters': ('Cover 6', 'Cover 3 Cloud'),
    'Cover 3 Sky': ('Cover 3 Cloud', 'Cover 3 Buzz'), 'Cover 3 Buzz': ('Cover 3 Sky', 'Cover 3 Cloud'),
    'Cover 3 Cloud': ('Cover 3 Sky', 'Cover 3 Buzz'), '2-Man Blitz': ('2-Man Under', 'Cover 1 Blitz'),
    '2-Man Under': ('2-Man Blitz', 'Cover 1'), 'Cover 0 Blitz': ('Cover 0 Pressure', 'Cover 1 Blitz'),
    'Fire Zone 3': ('Cover 2 Fire', 'Sim Pressure 3'), 'Cover 1 Blitz': ('Cover 0 Blitz', '2-Man Blitz'),
    'Tampa 2': ('Cover 2',), 'Quarters Pressure': ('Fire Zone 3',), 'Cover 6 Pressure': ('Quarters Pressure',),
}


def front_slots_of(role: Role) -> set[int]:
    return {1, 2, 3} if role.type_code == 4 else {0, 1, 2, 3}


def valid_in_roles(script: L.Script, roles_in: set, roles: dict[str, Role]) -> bool:
    fam = FAMILY_OF.get(script.struct.label)
    for r in roles_in:
        role = roles[r]
        if role.type_code != script.type_code:
            return False
        st = L.structure(script.chains, role.kinds, front_slots_of(role), ('odd:' if role.type_code == 4 else 'even:') + role.source_name)
        if FAMILY_OF.get(st.label) != fam:
            return False
        if (st.n_rush >= 5) != (script.struct.n_rush >= 5):
            return False
    return True


def pick_scripts(slots, roles, library: Library, team: str, book, body, targets_of=None):
    targets_of = targets_of or {}
    used: set[str] = set()
    # Own-book scripts at their own record first (zero node cost, no relocation).
    own_by_index = {}
    for sc in library.own.get(team, []):
        own_by_index.setdefault(sc.play_index, sc)
    order = sorted((s for s in slots.values() if s.component == 'coverage' and isinstance(s.content, Choice)),
                   key=lambda s: (-len(s.roles), s.index))
    misses = []
    for s in order:
        ch: Choice = s.content
        if ch.note.startswith('mug:'):
            continue
        home = roles[home_role(s.roles)]
        labels = [ch.concept, *FALLBACK_LABELS.get(ch.concept, ())]
        pick = None
        authored = None
        for lab in labels:
            home_layout = [c for c in library.candidates(home.source_name, home.codes, lab)]
            other = [c for c in library.same_type(home.type_code, lab) if c not in home_layout]
            for tier, pool in enumerate((home_layout, other)):
                cands = [c for c in pool if c.key not in used and valid_in_roles(c, s.roles, roles)]
                if not cands:
                    continue
                def rank(c):
                    return (0 if (c.book == team and c.play_index == s.index) else 1 if c.book == team else 2,
                            -library.popularity[c.key], c.book, c.play_index)
                pick = min(cands, key=rank)
                break
            if pick is None and ('preset', lab) not in used:
                cand = preset_choice(lab, home, book, body)
                if cand is not None:
                    st = L.structure(cand.chains, home.kinds, front_slots_of(home),
                                     ('odd:' if home.type_code == 4 else 'even:') + home.source_name)
                    if FAMILY_OF.get(st.label) == FAMILY_OF.get(lab):
                        authored = cand
            if pick is not None or authored is not None:
                if lab != ch.concept:
                    ch.note = f'fallback {ch.concept} -> {lab}'
                    ch.concept = lab
                break
        if authored is not None:
            used.add(('preset', ch.concept))
            authored.note = (ch.note + '; ' if ch.note else '') + authored.note
            s.content = authored
            continue
        if pick is None:
            # Last resort: the most wanted concept of these menus that still has an unused, valid retail script.
            wanted = Counter()
            for r in s.roles:
                for c, v in targets_of.get(r, {}).items():
                    wanted[c] += v
            for c, _ in wanted.most_common():
                cands = [x for x in library.candidates(home.source_name, home.codes, c) + library.same_type(home.type_code, c)
                         if x.key not in used and valid_in_roles(x, s.roles, roles)]
                if cands:
                    pick = min(cands, key=lambda x: (x.book != team, -library.popularity[x.key], x.book, x.play_index))
                    ch.note = f'fallback {ch.concept} -> {c} (last resort)'
                    ch.concept = c
                    break
        if pick is None:
            misses.append((s.index, ch.concept, sorted(s.roles)))
            continue
        used.add(pick.key)
        ch.script = pick
    return misses


# ---------------------------------------------------------------------------------------------------------------
# Names (DESIGN): concept + who brings the pressure / which way the safeties rotate.  Unique per book.
# ---------------------------------------------------------------------------------------------------------------
def who(kinds, slot, x_cm) -> str:
    k = kinds[slot]
    if k == D.CB:
        return 'Nickel' if slot == 6 else ('Dime' if slot == 4 else 'Corner')
    if k in (D.FS, D.SS):
        return 'Safety'
    if k == D.MLB:
        return 'Mike'
    if k == D.OLB:
        return 'Will' if x_cm > 0 else 'Sam'
    if k in (D.DE, D.DT):
        return 'Line'
    return '?'


def _press(chains, kinds) -> str:
    """Corner technique from the corners' native man alignment (0x1B a=2 depth): Press at 1 yd or less."""
    depths = []
    for s in range(11):
        if kinds[s] == D.CB and chains[s] and chains[s][0][0] == 0x1B and chains[s][0][1][0] == 2:
            depths.append(chains[s][0][1][3])
    if not depths:
        return ''
    return 'Press' if max(depths) <= YD_ + 1 else 'Off'


def _bail(chains, kinds) -> str:
    """Zone corners' pre-snap depth from their native 0x1B offset: Press (1 yd or less) or Bail (5 yd or more)."""
    if not chains:
        return ''
    ys = [chains[s][0][1][3] for s in range(11) if kinds[s] == D.CB and chains[s] and chains[s][0][0] == 0x1B
          and chains[s][0][1][0] == 0]
    if not ys:
        return ''
    y = max(ys)
    return 'Bail' if y >= 5 * YD_ - 1 else ('Press' if y <= YD_ + 1 else '')


def name_options(label: str, st: L.Structure, kinds, xy, chains) -> list[str]:
    """Most specific first; the namer takes the first one not used yet in this book."""
    extra = [s for s in st.rushers if s >= 4 or (s == 0 and kinds[0] in (D.MLB, D.OLB))]
    blitzers = [who(kinds, s, xy[s][0]) for s in extra]
    t = set(st.tags)
    press = _press(chains, kinds) if chains else ''
    if label in ('Cover 0 Blitz', 'Cover 0 Pressure', 'Zero Zone'):
        lb = sum(b in ('Mike', 'Will', 'Sam') for b in blitzers)
        tag = 'Double A' if lb >= 2 else ('Safety' if 'Safety' in blitzers else
                                         'Nickel' if 'Nickel' in blitzers else (blitzers[0] if blitzers else 'All'))
        return [f'Cover 0 {tag} Blitz', f'Cover 0 {tag} {press}'.strip(), 'Zero Blitz', 'Cover 0 Max']
    if label == 'Cover 1 Blitz':
        tag = blitzers[0] if len(set(blitzers)) == 1 and blitzers else ('Double' if len(blitzers) >= 2 else 'Line')
        return [f'Cover 1 {tag} Fire', f'Cover 1 {tag} Blitz', f'Cover 1 {tag} {press} Fire'.replace('  ', ' ')]
    if label in ('Cover 1', 'Cover 1 Robber', 'Cover 1 Hole'):
        robber = [u for u in st.under if abs(u[1]) <= 7 * YD_ and 5 * YD_ <= u[2] < L.DEEP_CM]
        rk = kinds[robber[0][0]] if robber else None
        base = 'Cover 1 Robber' if rk in (D.FS, D.SS) else ('Cover 1 Rat' if robber else 'Cover 1 Man')
        return [f'{base} {press}'.strip(), base, f'{base} Lurk', 'Cover 1 Hole']
    if label in ('2-Man Under', '2-Man Blitz'):
        if label == '2-Man Blitz':
            tag = blitzers[0] if blitzers else 'Line'
            return [f'2-Man {tag} Blitz', '2-Man Pressure']
        return [f'2-Man {press}'.strip(), '2-Man Under', '2-Man Trail']
    if label in ('Cover 2', 'Cover 2 Hard', 'Tampa 2', 'Cover 2 Sim', 'Cover 2 Fire'):
        if label == 'Tampa 2':
            return ['Tampa 2', 'Tampa 2 Sink']
        if label == 'Cover 2 Fire':
            tag = blitzers[0] if len(set(blitzers)) == 1 and blitzers else 'Double'
            return [f'Cover 2 {tag} Fire', f'2 Fire {tag}']
        if label == 'Cover 2 Sim':
            tag = blitzers[0] if blitzers else 'Line'
            return [f'Sim 2-Deep {tag}', f'Cover 2 Sim {tag}']
        if 'match' in t:
            return ['Cover 2 Match', '2 Read Match']
        return (['Cover 2 Hard', 'Cover 2 Cloud'] if 'hard' in t else ['Cover 2 Zone', 'Cover 2 Soft', 'Cover 2 Sink'])
    if label.startswith('Cover 3') or label in ('Fire Zone 3', 'Sim Pressure 3'):
        flats = [u for u in st.under if abs(u[1]) >= 9 * YD_]
        side = 'Strong' if any(u[1] < 0 and kinds[u[0]] in (D.FS, D.SS) for u in flats) else 'Weak'
        if label == 'Fire Zone 3':
            tag = blitzers[0] if len(set(blitzers)) == 1 and blitzers else 'Double'
            return [f'Fire Zone 3 {tag}', f'Fire 3 {tag} {side}', f'Fire Zone {tag} Seam']
        if label == 'Sim Pressure 3':
            tag = blitzers[0] if blitzers else 'Line'
            return [f'Sim Pressure {tag}', f'Creeper {tag}', f'Sim 3 {tag} {side}']
        if label == 'Cover 3 Match' or 'match' in t:
            return ['Cover 3 Match', 'Cover 3 Rip', 'Cover 3 Liz']
        if label == 'Cover 3 Cloud':
            side = 'Strong' if any(u[1] < 0 and kinds[u[0]] == D.CB for u in flats) else 'Weak'
        bail = _bail(chains, kinds)
        return [f'{label} {side}', f'{label} {side} {bail}'.strip(), label, f'{label} {bail}'.strip()]
    if label in ('Cover 4 Quarters', 'Cover 4 Match', 'Quarters Pressure'):
        if label == 'Quarters Pressure':
            return ['Quarters Pressure', 'Cover 4 Fire']
        if 'match' in t or label == 'Cover 4 Match':
            return ['Quarters Match', 'Cover 4 Palms']
        if st.n_rush <= 3:
            return ['Quarters Drop 8', 'Cover 4 Drop']
        return ['Cover 4 Quarters', 'Cover 4 Spot', 'Quarters']
    if label in ('Cover 6', 'Cover 6 Pressure'):
        half = [d for d in st.deep if d[3] == 11]
        flip = bool(half) and half[0][1] < 0
        if label == 'Cover 6 Pressure':
            return ['Cover 6 Pressure']
        return ['Cover 6 Flip', 'Cover 6 Split'] if flip else ['Cover 6 Split', 'Cover 6 Flip']
    return [label]


def play_name(label: str, st: L.Structure, kinds, xy, chains=None, used=None) -> str:
    opts = name_options(label, st, kinds, xy, chains)
    used = used if used is not None else set()
    for o in opts:
        if o not in used:
            return o
    return opts[0]


YD_ = 91.44


def unique(name: str, used: set) -> str:
    base = name[:36]
    n, out = 2, base
    while out in used:
        out = f'{base} {n}'
        n += 1
    used.add(out)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Chains
# ---------------------------------------------------------------------------------------------------------------
PLACEHOLDER = [(0x01, [1, 3, 0, 0, 0, 0]), (0x01, [0, 0, 0, .1, 0, 0])]
CLASS_BITS = 0x0C914000 | 0x10000 | 0x80000 | 0x100000 | 0x800000


def front_chains(call: D.FrontCall, role: Role) -> list:
    if role.type_code == 4:
        mapping = {'WE': 1, 'SE': 2, 'N': 3}
    else:
        mapping = {'WE': 0, 'SE': 1, 'WT': 2, 'ST': 3}
    chains = [None] * 11
    for r, (mode, lane, delay) in call.lanes.items():
        chains[mapping[r]] = [(NEUTRAL_START[0], list(NEUTRAL_START[1])), (0x0B, [mode, max(0, min(16, lane)), delay])]
    return chains


def local_donor(book, body, type_code: int, component: str, want_flags: int, exclude=()) -> int:
    """A record of this book whose header matches the wanted class (outside the CPU band), same type code."""
    best, score = None, None
    for p in book.plays:
        if p.family_id != 1 or (p.flags_or_id & 63) != type_code or p.index in exclude:
            continue
        chains = lib.decoded_chains(body, p.index)
        if lib.defense_component(chains) != component:
            continue
        f = p.flags_or_id
        sc = (bin((f ^ want_flags) & ~0xE00 & 0xFFFFFFC0).count('1'), p.index)
        if score is None or sc < score:
            best, score = p.index, sc
    if best is None:
        raise ValueError(f'No local {component} donor of type {type_code}')
    return best


def frozen(chains) -> tuple:
    return tuple(None if c is None else tuple((int(n[0]), tuple(float(v) for v in n[1])) for n in c) for c in chains)


def diff_against(chains, donor_chains) -> list:
    """Author only the slots whose chain differs from the donor's; placeholders where the donor is active but the
    script is not."""
    out = []
    d_active = lib.defense_active(donor_chains)
    s_active = lib.defense_active(chains)
    for s in range(11):
        mine = chains[s]
        if s not in s_active:
            out.append(None if s not in d_active else [list(n) for n in PLACEHOLDER])
            continue
        if frozen([mine]) == frozen([donor_chains[s]]):
            out.append(None)
        else:
            out.append([(n[0], list(n[1])) for n in mine])
    return out


def mug_variant(base_chains, kinds, role_kind: str, book, body, fi) -> list:
    """Mug pressure from a retail nickel script: the two mugged backers keep a neutral start (they stay in the A gaps
    until the snap) and either rush their A gap or drop to the hook."""
    chains = [[(n[0], list(n[1])) for n in c] if c else c for c in base_chains]
    lbs = [s for s in range(4, 7) if kinds[s] in (D.MLB, D.OLB)][:2]
    weak, strong = lbs[0], lbs[1]

    def rush(slot, lane):
        _, ch = lib.defense_slot_donor(book, body, fi, slot, 0x0B)
        ch = [(n[0], list(n[1])) for n in ch]
        ch[0] = (NEUTRAL_START[0], list(NEUTRAL_START[1]))
        ch[1][1][:3] = [2, lane, 0]
        return ch

    def hook(slot, x):
        _, ch = lib.defense_slot_donor(book, body, fi, slot, 0x0D)
        ch = [(n[0], list(n[1])) for n in ch]
        ch[0] = (NEUTRAL_START[0], list(NEUTRAL_START[1]))
        ch[1][1][:2] = [x * YD_, 8 * YD_]
        ch[1][1][4:] = [4, 0, 0]
        return ch

    if role_kind == 'zero':
        # Cover 0: the backers' man assignments go to the two safeties, the backers rush the A gaps.
        safeties = [s for s in range(7, 9) if kinds[s] in (D.FS, D.SS)]
        for back, saf in zip((weak, strong), safeties):
            if L.first_action(chains[back])[0] != 0x0E:
                raise ValueError('Mug zero needs a man script with both backers in man')
            chains[saf] = [(n[0], list(n[1])) for n in chains[back]]
        chains[weak] = rush(weak, 9)
        chains[strong] = rush(strong, 7)
    elif role_kind == 'sim':
        chains[weak] = rush(weak, 9)
        chains[strong] = rush(strong, 7)
    elif role_kind == 'fire':
        chains[strong] = rush(strong, 7)
        chains[weak] = hook(weak, 5)
    else:   # bail
        chains[weak] = hook(weak, 5)
        chains[strong] = hook(strong, -5)
    if role_kind == 'sim':
        for s, x in ((0, 14), (1, -14)):          # both ends drop to the flats (four rush: two backers + tackles)
            _, ch = lib.defense_slot_donor(book, body, fi, s, 0x0D) if _has_dl_drop(book, body, fi, s) else (None, None)
            if ch is None:
                _, z = lib.defense_slot_donor(book, body, fi, 5, 0x0D)
                ch = [(NEUTRAL_START[0], list(NEUTRAL_START[1])), (z[1][0], list(z[1][1]))]
            ch = [(n[0], list(n[1])) for n in ch]
            ch[0] = (NEUTRAL_START[0], list(NEUTRAL_START[1]))
            ch[1][1][:2] = [x * YD_, 6 * YD_]
            ch[1][1][4:] = [5 if x > 0 else 6, 0, 0]
            chains[s] = ch
    for c in chains:
        if c:
            codec.validate_defense_operands(c)
    return chains


def _has_dl_drop(book, body, fi, slot) -> bool:
    try:
        lib.defense_slot_donor(book, body, fi, slot, 0x0D)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------------------------------------------
# Bands (DESIGN fit to the per-role targets under the native cubed lottery; PROVED OFFLINE score model)
# ---------------------------------------------------------------------------------------------------------------
ROLE_WEIGHT = {'nickel': 1.0, 'base': .7, 'dime': .6, 'base2': .3, 'bear': .4, 'mug': .4, 'nickel_odd': .4,
               'dime_odd': .3}


def fit_bands(cov: list[Slot], targets: dict[str, dict[str, float]], concept_of, rushers_of=None) -> float:
    """Coordinate descent over CPU score bands 1..3 (never 4: x0.001 after the cube would silently delete a call, and
    variety is half of the brief).  Loss per menu: concept shares + 3x coverage-family shares + 4x blitz (5+ rushers)
    share."""
    rushers_of = rushers_of or (lambda s: 0)
    for s in cov:
        s.band = 3 if s.pressure else 2
    members_of = {role: [s for s in cov if role in s.roles] for role in targets}
    fam_t = {role: Counter() for role in targets}
    blitz_t = {}
    for role, tgt in targets.items():
        for c, v in tgt.items():
            fam_t[role][FAMILY_OF.get(c, c)] += v
        blitz_t[role] = sum(v for c, v in tgt.items() if c in BLITZ)

    def loss():
        total = 0.0
        for role, tgt in targets.items():
            members = members_of[role]
            if not members:
                continue
            w = {s.index: weight(s.band, s.pressure) for s in members}
            z = sum(w.values())
            share, fam = Counter(), Counter()
            blitz = 0.0
            for s in members:
                c = concept_of(s)
                share[c] += w[s.index] / z
                fam[FAMILY_OF.get(c, c)] += w[s.index] / z
                if rushers_of(s) >= 5:
                    blitz += w[s.index] / z
            keys = set(tgt) | set(share)
            fk = set(fam_t[role]) | set(fam)
            total += ROLE_WEIGHT.get(role, .3) * (sum((share[k] - tgt.get(k, 0)) ** 2 for k in keys)
                                                  + 3 * sum((fam[k] - fam_t[role].get(k, 0)) ** 2 for k in fk)
                                                  + 4 * (blitz - blitz_t[role]) ** 2)
        return total

    cur = loss()
    for _ in range(20):
        improved = False
        for s in cov:
            best = (cur, s.band)
            for b in (1, 2, 3):          # band 4 (x0.001 after the cube) would silently delete a call
                if b == s.band:
                    continue
                old = s.band
                s.band = b
                v = loss()
                s.band = old
                if v < best[0] - 1e-12:
                    best = (v, b)
            if best[1] != s.band:
                s.band = best[1]
                cur = best[0]
                improved = True
        if not improved:
            break
    return cur


# ---------------------------------------------------------------------------------------------------------------
# Team build
# ---------------------------------------------------------------------------------------------------------------
def load_research():
    profiles = json.loads((ROOT / 'pb/research/defense_profiles.json').read_text())
    rates = json.loads((ROOT / 'pb/research/defense_tendencies_2025.json').read_text())['teams']
    return profiles, rates


MUG_SET = (('zero', 'Cover 0 Blitz', 'Mug Zero'), ('fire', 'Fire Zone 3', 'Mug Fire 3'),
           ('sim', 'Sim Pressure 3', 'Mug Sim 3'), ('bail', 'Cover 3 Sky', 'Mug Bail 3'))
MUG_BASES = {'zero': ('2-Man Under', 'Cover 1 Robber', 'Cover 1'), 'fire': ('Cover 3 Sky', 'Cover 3 Cloud', 'Cover 3 Buzz'),
             'sim': ('Cover 3 Sky', 'Cover 3 Cloud', 'Cover 3 Buzz'), 'bail': ('Cover 3 Sky', 'Cover 3 Cloud', 'Cover 3 Buzz')}


def plan_team(team: str, source: bytes, library: Library, profiles, rates_all) -> dict:
    scheme = D.SCHEMES[team]
    profile = profiles[team]
    rates = rates_all[profile['baseline_team'] or profile['design_fallback_team']]
    book = ip.parse_playbook_resource(source)
    body = source[ip.RESOURCE_HEADER_SIZE:]
    roles = detect_roles(book, body, team, scheme)
    nickel = roles.get('nickel')
    mug_note = ''
    if scheme.mug and nickel is not None and nickel.type_code == 5:
        if pk.PLAY_CAPACITY - len(book.plays) >= 2 and len(book.formations) < pk.FORMATION_CAPACITY:
            mug = copy.copy(nickel)
            mug.key, mug.name, mug.fi, mug.donor_fi = 'mug', 'Nickel Mug', None, nickel.fi
            roles['mug'] = mug
        elif 'nickel_odd' in roles:
            mug_note = 'no play capacity for a Mug clone: the 3-3 odd nickel is the passing-down pressure look'
            roles['nickel_odd'].key = 'nickel_odd'
            roles['nickel_odd'].name = 'Nickel 3-3 Pressure'
        else:
            mug_note = 'no play capacity for a Mug clone; double-A pressure stays a nickel call'
    elif scheme.mug:
        mug_note = 'odd nickel personnel: double-A pressure stays a nickel call'
    bear = roles.get('bear')
    if bear is not None:
        # PROVED OFFLINE (0x2093F0, defensive branch): same-code personnel groups are drawn with equal weight and no
        # formation rating, so a Bear in its own code-13 group is a coin flip on every base-personnel snap.  When the
        # 4-3 group fields the same personnel, the Bear joins it (donor = the 4-3 record: its personnel words) and the
        # formation ratings pick it on short yardage.
        host = next((roles[k] for k in ('base', 'base2') if k in roles and roles[k].type_code == 5
                     and roles[k].codes == bear.codes), None)
        if host is not None:
            bear.merged = True
            bear.donor_fi = host.fi
            bear.category_index = host.category_index
    for r in roles.values():
        donor = r.fi if r.fi is not None else r.donor_fi
        rec = lib.formation_record(body, donor)
        partners = [x.mirror_partner for x in rec.slots]
        r.keep_geometry = any(m != codec.NO_MIRROR and (m > 10 or partners[m] != k) for k, m in enumerate(partners))
        if r.keep_geometry:
            # Retail record with a one-way mirror pair (NE Nickel): the writer refuses to re-author it, and retail
            # geometry already passes the alignment linter, so it keeps its retail spots, name and ratings.
            r.name = r.source_name
            r.positions = [(x.x[0], x.z[0]) for x in rec.slots]
            r.situation = None
            r.family = 'retail'
            continue
        r.positions = role_positions(r, scheme, [(s.x[0], s.z[0]) for s in rec.slots])
        r.situation = D.SITUATION[ROLE_SITUATION[r.key]]
        if r.key == 'nickel_odd' and r.name.endswith('Pressure'):
            r.situation = D.SITUATION['mug']
    slots = membership(book, body, {k: v for k, v in roles.items() if v.fi is not None})
    if 'mug' in roles:
        for s in slots.values():
            if 'nickel' in s.roles:
                s.roles.add('mug')
    for s in slots.values():
        s.pressure = bool(book.plays[s.index].flags_or_id & PRESSURE_BIT)
    pool = RecordPool(slots, book, roles)
    front_plan = assign_fronts(slots, roles, scheme, team, pool)
    # Mug pressure calls, carried by spare Bear-only records (also legal Bear calls: double-A pressure).
    mug_calls = []
    if 'mug' in roles:
        for kind, concept, name in MUG_SET:
            i = pool.take('mug', 'coverage')
            if i is None:
                break
            s = slots[i]
            s.content = Choice(concept, note=f'mug:{kind}')
            s.name = name
            mug_calls.append((i, kind))
    targets = {k: coverage_targets(rates, 'base' if (k == 'bear' and not roles[k].merged) else k, scheme)
               for k in roles if k != 'mug'}
    cov_targets = {k: v for k, v in targets.items()}
    # Concepts: Mug inherits the nickel menu, so it is fitted only through its own calls' bands.
    saved = {i: set(s.roles) for i, s in slots.items()}
    for s in slots.values():
        s.roles.discard('mug')
    need = assign_concepts(slots, cov_targets)
    for i, r in saved.items():
        slots[i].roles = r
    misses = pick_scripts(slots, roles, library, team, book, body, cov_targets)
    # Mug chains (need the nickel script library for the base).
    for i, kind in mug_calls:
        s = slots[i]
        base = None
        for lab in MUG_BASES[kind]:
            lbs2 = [k for k in range(4, 7) if nickel.kinds[k] in (D.MLB, D.OLB)][:2]
            cands = [c for c in library.candidates(nickel.source_name, nickel.codes, lab)
                     if c.struct.n_rush == 4 and (kind != 'zero' or all(L.first_action(c.chains[k])[0] == 0x0E for k in lbs2))]
            cands.sort(key=lambda c: (c.book != team, -library.popularity[c.key], c.book, c.play_index))
            if cands:
                base = cands[0]
                break
        if base is None:
            misses.append((i, f'mug {kind}', ['mug']))
            continue
        chains = mug_variant(base.chains, nickel.kinds, kind, book, body, nickel.fi)
        st = L.structure(chains, nickel.kinds, {0, 1, 2, 3}, 'even:Nickel')
        s.content = Choice(st.label, script=None, chains=chains, note=f'mug:{kind} from {base.book} {base.name}')
        s.content.base_flags = base.flags
    # KC: one situational QB spy (existing runtime intent; pb/research/SPY.md).  It stays on play 21, slot 5, the
    # record v0.5 already declares to the QB-spy runtime table, so the shipped default.xbe table stays valid.
    spy = None
    if 'QB Spy' in scheme.package and nickel is not None:
        pinned = [slots[i] for i in SPY_PIN.get(team, ()) if i in slots]
        for s in pinned + sorted(slots.values(), key=lambda s: s.index):
            ch = s.content
            mlb = next((k for k, c in enumerate(nickel.kinds) if c == D.MLB), None)
            if mlb is None:
                break
            if s.component == 'coverage' and isinstance(ch, Choice) and pinned and s is pinned[0] and ch.script is not None:
                # make the pinned record a Cover 3/Cover 1 call with an underneath MLB first
                home_r = roles[home_role(s.roles)]
                for lab in ('Cover 3 Sky', 'Cover 3 Buzz', 'Cover 3 Cloud', 'Cover 1 Robber'):
                    cands = [c for c in library.candidates(home_r.source_name, home_r.codes, lab)
                             if L.first_action(c.chains[mlb])[0] == 0x0D and L.first_action(c.chains[mlb])[1][1] < 10 * YD_
                             and valid_in_roles(c, s.roles, roles)]
                    if cands:
                        ch.script = min(cands, key=lambda c: (c.book != team, -library.popularity[c.key], c.book, c.play_index))
                        ch.concept = lab
                        break
            if (s.component == 'coverage' and isinstance(ch, Choice) and ch.script is not None
                    and ('nickel' in s.roles or s in pinned)
                    and ch.concept in ('Cover 3 Sky', 'Cover 3 Buzz', 'Cover 3 Cloud', 'Cover 1', 'Cover 1 Robber')
                    and all(roles[r].kinds[mlb] == D.MLB for r in s.roles)
                    and L.first_action(ch.script.chains[mlb])[0] == 0x0D
                    and L.first_action(ch.script.chains[mlb])[1][1] < 10 * YD_):
                _, spy_chain = lib.spy_fallback(book, body, nickel.fi, mlb, 4)
                chains = [[(n[0], list(n[1])) for n in c] if c else c for c in ch.script.chains]
                chains[mlb] = [(n[0], list(n[1])) for n in spy_chain]
                s.content = Choice(ch.concept, chains=chains, spy_slots=(mlb,), note='QB spy (MLB) on ' + ch.script.name)
                s.content.base_flags = ch.script.flags
                spy = s.index
                break
    return dict(team=team, scheme=scheme, profile=profile, rates=rates, book=book, body=body, roles=roles,
                slots=slots, targets=targets, front_plan=front_plan, misses=misses, need=need, spy=spy,
                mug_note=mug_note, appended=list(pool.appended))


RETAIL_XBE = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')


def source_front_index(book, body, fi: int) -> int:
    for p in book.plays_for_formation(fi):
        if p.family_id == 1 and lib.defense_component(lib.decoded_chains(body, p.index)) == 'front':
            return p.index
    raise ValueError(f'formation {fi} has no source front')


def make_pack(plan: dict) -> tuple[pk.PlaybookPack, list[dict], dict]:
    team, book, body, roles, slots = plan['team'], plan['book'], plan['body'], plan['roles'], plan['slots']
    scheme = plan['scheme']
    # 1. donors and final chains per record
    rows = {}
    for s in sorted(slots.values(), key=lambda s: s.index):
        if s.content is None:
            continue
        src_roles = [r for r in ROLE_PRIORITY if r in s.roles and r not in s.extra_links and roles[r].fi is not None]
        if src_roles:
            home = roles[src_roles[0]]
        else:   # appended record: validated against the formation it is cloned from
            key = next(iter(s.extra_links))
            home = roles['nickel'] if key == 'mug' else roles[key]
        if s.component == 'front':
            call = s.content
            if s.extra_links:
                target_key = next(iter(s.extra_links))
            elif call.family == 'bear' or s.roles == {'bear'}:
                target_key = 'bear'
            else:
                target_key = next(r for r in ROLE_PRIORITY if r in s.roles and r != 'bear')
            target = roles[target_key]
            chains = front_chains(call, target)
            src_is_front = (not s.appended) and lib.defense_component(lib.decoded_chains(body, s.index)) == 'front'
            donor = s.index if src_is_front else local_donor(book, body, home.type_code, 'front',
                                                              book.plays[source_front_index(book, body, home.fi)].flags_or_id)
            donor_chains = lib.decoded_chains(body, donor)
            chains = [None if c is None or frozen([c]) == frozen([donor_chains[k]]) else c for k, c in enumerate(chains)]
            if s.index == 0 and chains[0] is not None:
                # The pool's node zero is play 0 slot 0 (repack order); the native parser needs it referenced.
                chains[0] = None
                s.note = 'slot 0 keeps the source chain (node zero)' 
            label, concept = call.name, 'Front: ' + call.name
            st = None
        else:
            ch: Choice = s.content
            if ch.script is not None and ch.chains is None:
                sc = ch.script
                if sc.book == team:
                    donor, chains = sc.play_index, [None] * 11
                else:
                    donor = local_donor(book, body, home.type_code, 'coverage', sc.flags)
                    chains = diff_against(sc.chains, lib.decoded_chains(body, donor))
                full = sc.chains
            elif ch.chains is not None:
                donor = local_donor(book, body, home.type_code, 'coverage', getattr(ch, 'base_flags', 0x00900445))
                chains = diff_against(ch.chains, lib.decoded_chains(body, donor))
                full = ch.chains
            else:
                continue
            st = L.structure(full, home.kinds, front_slots_of(home), ('odd:' if home.type_code == 4 else 'even:') + home.source_name)
            label, concept = st.label, st.label
        rows[s.index] = dict(slot=s, donor=donor, chains=chains, home=home, label=label, concept=concept, st=st,
                             donor_flags=book.plays[donor].flags_or_id)
        s.pressure = bool(rows[s.index]['donor_flags'] & PRESSURE_BIT)
    # 2. bands (coverages; fronts keep their call band)
    cov = [r['slot'] for r in rows.values() if r['slot'].component == 'coverage']
    concept_of = lambda s: rows[s.index]['concept']
    fit_targets = dict(plan['targets'])
    if 'mug' in roles:
        fit_targets['mug'] = coverage_targets(plan['rates'], 'mug', scheme)
    mug_calls = [x for x in cov if isinstance(x.content, Choice) and x.content.note.startswith('mug:')]
    loss = fit_bands([x for x in cov if x not in mug_calls], {k: v for k, v in fit_targets.items() if k != 'mug'},
                     concept_of, lambda x: rows[x.index]['st'].n_rush if rows[x.index]['st'] is not None else 0)
    for x in mug_calls:
        # DESIGN: the Mug look exists to run these four calls; band 0 makes them about two thirds of the calls made
        # from the Mug formation (the nickel menu it inherits keeps the rest), and the formation itself is chosen
        # only on long yardage.
        x.band = 0
    modeled = {}
    for role, tgt in fit_targets.items():
        members = [x for x in cov if role in x.roles]
        if not members:
            continue
        w = {x.index: weight(x.band, x.pressure) for x in members}
        z = sum(w.values())
        fam_m, fam_t = Counter(), Counter()
        blitz = 0.0
        for x in members:
            c = concept_of(x)
            fam_m[FAMILY_OF.get(c, c)] += w[x.index] / z
            st = rows[x.index]['st']
            if st is not None and st.n_rush >= 5:
                blitz += w[x.index] / z
        for c, v in tgt.items():
            fam_t[FAMILY_OF.get(c, c)] += v
        modeled[role] = dict(model={k: round(v, 3) for k, v in sorted(fam_m.items())},
                             target={k: round(v, 3) for k, v in sorted(fam_t.items())},
                             blitz_model=round(blitz, 3),
                             blitz_target=round(sum(v for c, v in tgt.items() if c in BLITZ), 3),
                             calls=len(members))
    # 3. names and plays
    used = {f.name for f in book.formations}
    plays, catalog = [], []
    for i, r in sorted(rows.items()):
        s = r['slot']
        home = r['home']
        if s.component == 'front':
            name = unique(s.name, used)
        elif s.name:
            name = unique(s.name, used)
        else:
            full = (s.content.chains if isinstance(s.content, Choice) and s.content.chains is not None else
                    (s.content.script.chains if isinstance(s.content, Choice) and s.content.script else None))
            if isinstance(s.content, Choice) and s.content.spy_slots:
                name = unique(r['label'].replace('Sky', '').replace('Buzz', '').replace('Cloud', '').strip() + ' Spy', used)
            else:
                name = unique(play_name(r['label'], r['st'], home.kinds, home.positions, full, used), used)
        flags = (r['donor_flags'] & ~0xE00) | (s.band << 9)
        link = None
        if s.extra_links:
            key = next(iter(s.extra_links))
            link = 'mug' if key == 'mug' else roles[key].fi
        ch = s.content if s.component == 'coverage' else None
        spy = tuple(ch.spy_slots) if ch is not None else ()
        donor = book.plays[r['donor']]
        play = pk.PackPlay(
            (f'n{i}' if s.appended else f'd{i}'), name, 'defense',
            frozen(r['chains']) if any(c is not None for c in r['chains']) else tuple([None] * 11),
            pk.PackDonor(donor.index, donor.name, donor.flags_or_id, lib.defense_signature(body, donor.index)),
            flags, None if s.appended else i, '' if s.appended else book.plays[i].name, concept=r['concept'],
            link_formation=link, link_group=None,
            defense_formation=home.source_name, front_index=source_front_index(book, body, home.fi),
            component=s.component, spy_slots=spy)
        plays.append(play)
        catalog.append(dict(play=i, appended=s.appended, name=name, component=s.component, concept=r['concept'], band=s.band,
                            pressure=s.pressure, roles=sorted(s.roles), new_links=sorted(s.extra_links),
                            donor=donor.index, donor_name=donor.name,
                            source=(None if s.component == 'front' else
                                    (dict(book=ch.script.book, play=ch.script.play_index, name=ch.script.name)
                                     if ch is not None and ch.script is not None else dict(authored=ch.note if ch else ''))),
                            rushers=(r['st'].n_rush if r['st'] else None), spy_slots=list(spy),
                            authored_nodes=sum(len(c) for c in r['chains'] if c)))
    formations = []
    for key in ('base', 'base2', 'bear', 'nickel', 'dime', 'nickel_odd', 'dime_odd'):
        r = roles.get(key)
        if r is None or getattr(r, 'keep_geometry', False):
            continue
        donor_fi = r.donor_fi if r.merged else r.fi
        formations.append(pk.PackFormation(f'f{r.fi}', r.name, tuple(tuple(p) for p in r.positions), tuple(r.codes),
                                           pk.PackDonor(donor_fi, plan['book'].formations[donor_fi].name), r.fi,
                                           r.source_name, r.category_index, None, tuple(r.situation)))
    if 'mug' in roles:
        r = roles['mug']
        formations.append(pk.PackFormation('mug', r.name, tuple(tuple(p) for p in r.positions), tuple(r.codes),
                                           pk.PackDonor(r.donor_fi, roles['nickel'].source_name), None, '',
                                           r.category_index, None, tuple(r.situation)))
    prof = plan['profile']
    notes = (f'DESIGN: {prof["dc"]} ({prof["family"]}); 2025 baseline {prof["baseline_team"] or prof["design_fallback_team"]}. '
             'Clean technique fronts (pb/v2/defense/design.py), retail 2K5 coverage scripts with native pre-snap '
             'alignment, situational formation ratings and CPU score bands fitted to the sourced 2025 coverage and '
             'blitz rates. Exact offense source required. Gameplay unwitnessed.')
    pack = pk.PlaybookPack(pk.PackBook(team, f'NFL 2K28 {team} Defense v2', AUTHOR, VERSION, 'CC0-1.0', (), notes),
                           pk.PackBase(pk.book_fingerprint(body), len(book.formations), len(book.plays), book.node_count),
                           tuple(formations), tuple(plays), pk.DEFENSE_SCHEMA)
    return pack, catalog, dict(band_loss=loss, modeled=modeled)


def compile_and_check(source: bytes, pack: pk.PlaybookPack, xbe: bytes):
    book = ip.parse_playbook_resource(source)
    check = pk.check_pack(pack, book=book, body=source[ip.RESOURCE_HEADER_SIZE:], xbe=xbe)
    if not check.ok:
        raise ValueError(check.text())
    result = pk.apply_pack_to_resource(source, pack, xbe=xbe)
    lint = [f for f in dlint.lint_resource(result.replacement) if f.severity == 'error']
    return check, result, lint


def semantic(pack) -> str:
    return hashlib.sha256(json.dumps(dict(forms=[(f.slot_positions, f.position_codes, f.situation) for f in pack.formations],
                                          plays=[(p.replace_index, p.assignments, p.play_flags, p.custom_name)
                                                 for p in pack.plays]), sort_keys=True).encode()).hexdigest()


def run_team(team: str, offense_dir: Path, library: Library, *, write: bool = True, xbe: bytes | None = None) -> dict:
    profiles, rates = load_research()
    source, offense_path = compiled_source(team, offense_dir)
    plan = plan_team(team, source, library, profiles, rates)
    pack, catalog, fit = make_pack(plan)
    xbe = xbe or RETAIL_XBE.read_bytes()
    check, result, lint = compile_and_check(source, pack, xbe)
    if lint:
        raise ValueError(f'{team} lint: ' + '; '.join(f.message for f in lint))
    receipt = dict(team=team, offense_pack=str(offense_path.relative_to(ROOT)) if offense_path.is_relative_to(ROOT) else str(offense_path),
                   offense_pack_sha256=hashlib.sha256(offense_path.read_bytes()).hexdigest(),
                   source_fingerprint=pk.book_fingerprint(source[ip.RESOURCE_HEADER_SIZE:]),
                   replacement_sha256=hashlib.sha256(result.replacement).hexdigest(),
                   semantic_sha256=semantic(pack), plays=len(pack.plays), formations=len(pack.formations),
                   nodes=result.report['new_node_count'], node_capacity=pk.NODE_CAPACITY,
                   formation_count=result.report['new_formation_count'], play_count=result.report['new_play_count'],
                   misses=plan['misses'], band_loss=round(fit['band_loss'], 5), spy_play=plan['spy'],
                   native_scoring_faults=result.report.get('native_scoring', {}).get('fault_count'))
    if write:
        dest = ROOT / f'data/playbooks/softdrink_{team.lower()}_defense.2k5book'
        pk.save_pack(pack, dest)
        receipt['pack'] = str(dest.relative_to(ROOT))
        receipt['pack_sha256'] = hashlib.sha256(dest.read_bytes()).hexdigest()
        OUT.mkdir(exist_ok=True)
        roles = {k: dict(name=r.name, source=r.source_name, index=r.fi, family=r.family, situation=r.situation,
                         merged_into_category=r.category_index if r.merged else None,
                         positions=r.positions, codes=list(r.codes))
                 for k, r in plan['roles'].items()}
        (OUT / f'{team}.json').write_text(json.dumps(dict(team=team, dc=plan['profile']['dc'], roles=roles,
                                                          targets=plan['targets'], modeled=fit['modeled'],
                                                          mug_note=plan['mug_note'], plays=catalog, receipt=receipt),
                                                     indent=1) + '\n', newline='\n')
    receipt['_resource'] = result.replacement
    return receipt


def build_library() -> Library:
    return Library(L.retail_library())


_WORKER = {}


def _work(job):
    team, offense_dir, write = job
    try:
        r = run_team(team, offense_dir, _WORKER['library'], write=write, xbe=_WORKER['xbe'])
    except Exception as exc:  # reported per team, the run continues
        import traceback
        return dict(team=team, error=f'{type(exc).__name__}: {str(exc)[-600:]}', trace=traceback.format_exc()[-1500:])
    resource = r.pop('_resource')
    if _WORKER.get('compiled_dir'):
        Path(_WORKER['compiled_dir'], f'{team}.bin').write_bytes(resource)
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--team', default='', help='comma-separated teams (default all 32)')
    ap.add_argument('--offense-dir', type=Path, default=ROOT / 'data/playbooks')
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--compiled-dir', type=Path, help='also write each compiled PLAY resource here (scratch)')
    args = ap.parse_args(argv)
    _WORKER['library'] = build_library()
    _WORKER['xbe'] = RETAIL_XBE.read_bytes()
    if args.compiled_dir:
        args.compiled_dir.mkdir(parents=True, exist_ok=True)
        _WORKER['compiled_dir'] = str(args.compiled_dir)
    teams = args.team.split(',') if args.team else list(L.TEAM_BOOKS)
    jobs = [(t, args.offense_dir, not args.no_write) for t in teams]
    receipts = []
    if args.workers > 1 and len(jobs) > 1:
        import multiprocessing as mp
        with mp.get_context('fork').Pool(min(args.workers, len(jobs))) as pool:
            results = pool.map(_work, jobs, chunksize=1)
    else:
        results = [_work(j) for j in jobs]
    for r in results:
        receipts.append(r)
        if 'error' in r:
            print(r['team'], 'ERROR', r['error'].replace('\n', ' | ')[-400:], flush=True)
            continue
        print(r['team'], 'plays', r['plays'], 'nodes', r['nodes'], 'forms', r['formation_count'], 'misses',
              len(r['misses']), 'loss', r['band_loss'], flush=True)
    if args.team and not args.no_write and (OUT / 'manifest.json').is_file():
        # merge single-team rebuilds into the league manifest
        manifest = json.loads((OUT / 'manifest.json').read_text())
        fresh = {r['team']: r for r in receipts if 'error' not in r}
        manifest['teams'] = [fresh.get(r['team'], r) for r in manifest['teams']]
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=1) + '\n', newline='\n')
    if not args.team and not args.no_write:
        OUT.mkdir(exist_ok=True)
        (OUT / 'manifest.json').write_text(json.dumps(dict(status='PROVED OFFLINE (compile, checks, lint); DESIGN (football)',
                                                           generator='pb/v2/defense/build.py', version=VERSION,
                                                           teams=receipts), indent=1) + '\n', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
