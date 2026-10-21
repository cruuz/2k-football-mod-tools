#!/usr/bin/env python3
"""SOFTDRINK defense v2: odd-front (3-4 Okie) coverage scripts where the edges rush (beta 77 wave b776, job de2).

Why this module exists.  The v2 generator reused the retail three-down coverage scripts.  In those scripts the two OLB
slots (the edge rushers) drop into the flats on most calls: after the position recode they are EDGE players, so a 3-4
team's edges covered 40 to 100 percent of the time (b776 de1 drop audit).  Noah's rule (10/18): EDGE players line up on
the edge and drop into coverage only when the play is designed for it (a zone blitz or sim pressure), as a minority of
calls.

What it does (DESIGN on PROVED OFFLINE inputs only; every chain below is a retail chain or a retail chain with one slot
re-assigned):
  * a retail odd script's dropping slot can be turned into a rusher (``to_rush``).  The zone that slot vacated is not
    left empty: the nearest underneath defender on that side takes half the distance toward it (``rehome``), the
    classic fire-zone compression (three deep, three under, five or six rushing);
  * ``variants(script)`` enumerates every rush pattern over the odd front's re-assignable slots (0, 4, 5, 6) that
    contains the script's own rushers;
  * ``classify_for_role`` judges one variant on one formation: BASE (no edge covers), DESIGNED (exactly one edge covers
    while a non-edge, non-lineman blitzes: a zone blitz or sim pressure), or BAD (every other shape, which includes the
    retail four-man rush where the strong edge covers the flat).
A play record is listed in every formation menu of its book that lists it, so one chain set must satisfy all of them:
``eligible`` returns the per-role verdicts, and build.py only picks variants that are BASE or DESIGNED in every role.

Gameplay is unwitnessed (Noah tests).  The football rule is data here (``DESIGNED_SHARE``), not buried in the picks.
"""
from __future__ import annotations

from dataclasses import dataclass
import itertools
import math

import library as L

YD = 91.44
RE_ASSIGNABLE = (0, 4, 5, 6)      # odd layouts: weak edge, inside backers / sub-package slots, strong edge
NEUTRAL_START = (0x1B, [0, 0, 0, 0, 0, 0])
MAX_RUSHERS = 6                   # three linemen plus at most three more
OVERLAP = 5 * YD                  # a neighbour within 5 yd already covers the vacated spot: nobody moves
# Share of a menu's calls that may be DESIGNED for one role (an edge covers while a back blitzes).  The even fronts'
# EDGE drops average 3.3 percent with a 16.7 percent maximum (de1), so the odd fronts are held to the same range.
DESIGNED_SHARE = 0.12


def _clone(chains):
    return [[(n[0], list(n[1])) for n in c] if c else c for c in chains]


def action(chain):
    return L.first_action(chain) if chain else (None, None)


def is_rush(chain) -> bool:
    return action(chain)[0] == 0x0B


def is_zone(chain) -> bool:
    return action(chain)[0] == 0x0D


def rush_chain(slot: int, x_cm: float) -> list:
    """A retail-style rush chain (neutral start, 0x0B) for a slot whose zone sat at lateral ``x_cm``.  Flat zones
    (9 yd or wider) come from edge and flat defenders: speed-rush the outside lanes (15 weak, 1 strong).  Hook zones
    come from inside backers: the B gaps (11 weak, 5 strong).  Slot 0 is always the weak edge."""
    if slot == 0:
        lane = 15
    elif abs(x_cm) >= 9 * YD:
        lane = 15 if x_cm >= 0 else 1
    else:
        lane = 11 if x_cm >= 0 else 5
    return [(NEUTRAL_START[0], list(NEUTRAL_START[1])), (0x0B, [2, lane, 0])]


def rehome(chains: list, vacated: int, taken: set) -> bool:
    """The zone ``vacated`` held goes to the nearest underneath defender on that side (halfway, or unchanged when his
    zone already overlaps it).  False when the slot does not hold an underneath zone or nobody can take it."""
    op, v = action(chains[vacated])
    if op != 0x0D or v[1] >= L.DEEP_CM:
        return False
    xv, yv = v[0], v[1]
    cands = []
    for s in range(4, 11):
        if s == vacated or not chains[s]:
            continue
        o, w = action(chains[s])
        if o == 0x0D and w[1] < L.DEEP_CM:
            cands.append(s)
    if not cands:
        return False
    def zone(s):
        # the live operand list of the slot's zone node (first_action hands back a copy)
        return next(n[1] for n in chains[s] if n[0] == 0x0D)
    same = [s for s in cands if abs(xv) < 3 * YD or (zone(s)[0] >= 0) == (xv >= 0)]
    pool = same or cands
    dist = lambda s: math.hypot(zone(s)[0] - xv, zone(s)[1] - yv)
    u = min(pool, key=lambda s: (s in taken, dist(s), s))
    taken.add(u)
    if dist(u) > OVERLAP:
        w = zone(u)
        w[0], w[1] = (w[0] + xv) / 2, (w[1] + yv) / 2
    return True


def to_rush(chains: list, slots, taken: set | None = None):
    """Chains with every slot of ``slots`` rushing, or None when one of them cannot be converted (man coverage, a deep
    zone, or a vacated zone nobody can take)."""
    out = _clone(chains)
    taken = taken if taken is not None else set()
    for s in sorted(slots):
        if is_rush(out[s]):
            continue
        op, v = action(out[s])
        if op != 0x0D:
            return None
        x = v[0]
        if not rehome(out, s, taken):
            return None
        out[s] = rush_chain(s, x)
    return out


@dataclass
class Variant:
    source: object                  # the retail L.Script this came from
    pattern: frozenset              # re-assignable slots that rush
    converted: tuple                # slots turned from coverage to rush
    chains: list
    key: str

    @property
    def flags(self) -> int:
        return self.source.flags


_CACHE: dict = {}


def variants(script) -> list[Variant]:
    """Every rush pattern over (0, 4, 5, 6) containing the script's own rushers (cached per retail chain set)."""
    cacheable = script.play_index >= 0        # authored presets (play_index -1) are per team: never shared
    if cacheable and script.key in _CACHE:
        return _CACHE[script.key]
    base = frozenset(s for s in RE_ASSIGNABLE if is_rush(script.chains[s]))
    out, seen = [], set()
    free = [s for s in RE_ASSIGNABLE if s not in base]
    for n in range(len(free) + 1):
        for extra in itertools.combinations(free, n):
            if len(script.struct.rushers) + n > MAX_RUSHERS:
                continue
            chains = script.chains if not extra else to_rush(script.chains, extra)
            if chains is None:
                continue
            key = L.chains_key(chains)
            if key in seen:
                continue
            seen.add(key)
            out.append(Variant(script, base | frozenset(extra), tuple(extra), chains, key))
    if cacheable:
        _CACHE[script.key] = out
    return out


def role_layout(role) -> str:
    return 'odd:' + role.source_name


def classify_for_role(chains, role, front_slots) -> tuple:
    """(verdict, structure) of one chain set on one odd formation: 'base' | 'designed' | 'bad'."""
    st = L.structure(chains, role.kinds, front_slots, role_layout(role))
    if not st.edge_drops:
        return 'base', st
    if len(st.edge_drops) == 1 and st.extra:
        return 'designed', st
    return 'bad', st


def judge(chains, roles_in: list, front_slots_of) -> dict | None:
    """Per-role verdicts of one chain set on every given odd role, or None when the roles disagree about the coverage
    family (they cannot share the record).  {'verdicts': {role key: (verdict, structure)}}."""
    verdicts, fams = {}, set()
    for role in roles_in:
        verdicts[role.key] = classify_for_role(chains, role, front_slots_of(role))
        fams.add(verdicts[role.key][1].family)
    if len(fams) != 1:
        return None
    return dict(verdicts=verdicts)
