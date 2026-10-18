"""Variety rules for the automatic CPU coach's recorded play rings (b776, job pb2).

Every offensive situation pool of a coach profile is a ring of exactly eight (formation, play) records and every
defensive pool a ring of four (formation, front, coverage) records. The native CPU draws a ring member at random,
never the one it called last, so the ring's content IS the CPU's play-calling variety. The charted-marginal fit in
``nfl2k5_vip`` chooses members by coordinate descent against pass/run, shotgun/under-center, play-action, screen,
deep, run-lane and defensive man/rush rates. Nothing in that fit prefers one member over an equally good one, so
the same staples win every pool and a ring can hold several look-alike plays.

This module adds the variety half and never touches the fit:

* ``play_family`` turns a play name into a concept family (team code, personnel numbers and left/right/strong/weak
  words dropped), so "CHI Post Wheel", "Strong Counter" and "Weak Counter" compare by what they are.
* ``RingSet`` scores a set of rings: hard rules (no repeated (formation, family) pair, at most one screen of a
  family and two screens per ring), soft per-ring rules (repeated family, repeated formation, repeated primary
  target) and soft cross-pool rules (the same pair, family or formation recurring in many pools).
* ``improve`` swaps ring members only for members of the same fit class (same pass/run, stance, play-action,
  screen, deep, run-lane and run-location flags), so every charted marginal and every pool's pass/shotgun joint is
  bit-for-bit unchanged while variety rises. A caller that also wants a measured trade against the fit passes a wider
  ``fit_class``.
* ``order_ring`` lays a ring out so look-alike records (same family, adjacent screens) are never neighbours.

Everything reads only the choice's own metadata (names and geometry read from the compiled book), never play
indices, so it re-runs unchanged on any rebuilt book. Records keep play index <= 255 because the candidates come
from ``choices_from_book`` / ``defense_choices_from_book``, which already refuse larger indices.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Callable, Hashable, Iterable, Sequence

SCHEMA = "nfl2k5_coach_diversity/v1"

TEAM_CODES = frozenset("""ARZ ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LV LAR LAC MIA MIN NE NO NYG NYJ
OAK PHI PIT SD SEA SF STL TB TEN WAS WSH""".split())
# Direction words do not make a different concept: Strong Counter and Weak Counter are one family.
DIRECTION_WORDS = frozenset("strong weak left right flip flipped lt rt".split())
_WORD = re.compile(r"[A-Za-z0-9/+&'-]+")


def play_family(name: str) -> str:
    """Concept family of a play name: lower case, no team code, personnel number or direction word."""
    words = _WORD.findall(name or "")
    while words and (words[0].upper() in TEAM_CODES or words[0].isdigit()):
        words = words[1:]
    kept = [w.casefold() for w in words if w.casefold() not in DIRECTION_WORDS and not w.isdigit()]
    return " ".join(kept) or " ".join(w.casefold() for w in words) or (name or "").strip().casefold()


def side_of(x_cm: float, band_cm: float = 182.88) -> str:
    """Left/centre/right of a formation spot (offense's right is positive x)."""
    return "L" if x_cm < -band_cm else "R" if x_cm > band_cm else "C"


@dataclass(frozen=True)
class Weights:
    """Costs. Hard rules dominate; soft rules are small enough to be traded against each other."""
    hard: float = 1000.0
    ring_family: float = 4.0       # each repeat of a family inside one ring
    ring_formation: float = 1.5    # each repeat of a formation inside one ring
    ring_target: float = 1.0       # each primary-target repeat beyond two in one ring
    pool_pair: float = 0.5         # per pair of pools sharing a (formation, play) pair
    pool_family: float = 0.1       # per pair of ring slots across pools sharing a family
    pool_formation: float = 0.02   # per pair of ring slots across pools sharing a formation
    situational: bool = True       # keep Hail Mary-type plays and kneels to the pools that can use them


DEFAULT_WEIGHTS = Weights()


@dataclass(frozen=True)
class Term:
    """One counted rule: ``key(choice)`` groups members; ``free`` repeats of a key cost nothing."""
    name: str
    key: Callable[[object], Hashable | None]
    weight: float
    free: int = 1
    hard: bool = False


@dataclass(frozen=True)
class Spec:
    ring: tuple[Term, ...]
    pool: tuple[Term, ...]     # Cross-pool: cost weight * C(uses, 2) over every ring slot of every pool.


def offense_spec(weights: Weights = DEFAULT_WEIGHTS) -> Spec:
    fam = lambda c: getattr(c, "concept", "") or play_family(getattr(c, "play_name", ""))
    return Spec(
        ring=(
            Term("repeated_formation_family", lambda c: (c.formation, fam(c)), weights.hard, 1, True),
            Term("screen_family", lambda c: fam(c) if c.screen else None, weights.hard, 1, True),
            Term("screens", lambda c: "screen" if c.screen else None, weights.hard, 2, True),
            Term("family", fam, weights.ring_family, 1),
            Term("formation", lambda c: c.formation, weights.ring_formation, 1),
            Term("target", lambda c: getattr(c, "target", "") or None, weights.ring_target, 2),
        ),
        pool=(
            Term("pair", lambda c: (c.formation, c.play), weights.pool_pair),
            Term("family", fam, weights.pool_family),
            Term("formation", lambda c: c.formation, weights.pool_formation),
        ))


def defense_spec(weights: Weights = DEFAULT_WEIGHTS) -> Spec:
    return Spec(
        ring=(
            Term("formation", lambda c: c.formation, weights.ring_formation, 1),
            Term("front", lambda c: c.front, weights.ring_family, 1),
            Term("coverage", lambda c: c.coverage, weights.ring_family, 1),
        ),
        pool=(
            Term("triple", lambda c: (c.formation, c.front, c.coverage), weights.pool_pair),
            Term("coverage", lambda c: c.coverage, weights.pool_family),
            Term("front", lambda c: (c.formation, c.front), weights.pool_family),
        ))


def _repeat_cost(counter: Counter, free: int) -> int:
    return sum(max(0, n - free) for n in counter.values())


class RingSet:
    """Incremental variety cost of several rings (lists of choices, mutated in place by ``replace``)."""

    def __init__(self, rings: Sequence[list], spec: Spec,
                 penalty: Callable[[int, object], float] | None = None):
        """``penalty(ring_index, choice)`` is an extra hard per-member cost (members a pool may not hold)."""
        self.rings = rings
        self.spec = spec
        self.penalty = penalty or (lambda index, choice: 0.0)
        self.ring_counts = [[Counter(k for c in ring if (k := t.key(c)) is not None) for t in spec.ring]
                            for ring in rings]
        self.pool_counts = [Counter(k for ring in rings for c in ring if (k := t.key(c)) is not None)
                            for t in spec.pool]

    # --- cost -----------------------------------------------------------------------------------------------
    def ring_cost(self, index: int) -> float:
        return (sum(t.weight * _repeat_cost(counter, t.free)
                    for t, counter in zip(self.spec.ring, self.ring_counts[index]))
                + sum(self.penalty(index, c) for c in self.rings[index]))

    def hard_violations(self, index: int | None = None) -> int:
        rows = range(len(self.rings)) if index is None else (index,)
        return (sum(_repeat_cost(counter, t.free)
                    for i in rows for t, counter in zip(self.spec.ring, self.ring_counts[i]) if t.hard)
                + sum(1 for i in rows for c in self.rings[i] if self.penalty(i, c) > 0))

    def total(self) -> float:
        cost = sum(self.ring_cost(i) for i in range(len(self.rings)))
        for t, counter in zip(self.spec.pool, self.pool_counts):
            cost += t.weight * sum(n * (n - 1) // 2 for n in counter.values())
        return cost

    def delta(self, index: int, current, candidate) -> float:
        """Cost change of replacing ``current`` by ``candidate`` in ring ``index`` (no state change)."""
        change = self.penalty(index, candidate) - self.penalty(index, current)
        for t, counter in zip(self.spec.ring, self.ring_counts[index]):
            out, into = t.key(current), t.key(candidate)
            if out == into:
                continue
            if out is not None:
                change -= t.weight * (1 if counter[out] > t.free else 0)
            if into is not None:
                change += t.weight * (1 if counter[into] - (out == into) >= t.free else 0)
        for t, counter in zip(self.spec.pool, self.pool_counts):
            out, into = t.key(current), t.key(candidate)
            if out == into:
                continue
            if out is not None:
                change -= t.weight * (counter[out] - 1)
            if into is not None:
                change += t.weight * counter[into]
        return change

    def replace(self, index: int, slot: int, candidate) -> None:
        ring = self.rings[index]
        current = ring[slot]
        for t, counter in zip(self.spec.ring, self.ring_counts[index]):
            self._move(counter, t.key(current), t.key(candidate))
        for t, counter in zip(self.spec.pool, self.pool_counts):
            self._move(counter, t.key(current), t.key(candidate))
        ring[slot] = candidate

    @staticmethod
    def _move(counter: Counter, out, into) -> None:
        if out is not None:
            counter[out] -= 1
            if not counter[out]:
                del counter[out]
        if into is not None:
            counter[into] += 1


def improve(rings: list[list], candidates: Sequence, spec: Spec, *,
            fit_class: Callable[[object], Hashable], identity=lambda c: (c.formation, c.play),
            sweeps: int = 40, penalty: Callable[[int, object], float] | None = None,
            escape: tuple[Callable[[object], Hashable], Callable[[object, object], float]] | None = None) -> dict:
    """Deterministic descent on variety cost using only fit-class-preserving swaps.

    ``candidates`` is the whole callable menu in a fixed order. A swap needs the same ``fit_class`` and an
    ``identity`` not already in the ring (native exclusion compares formation and play only).

    ``escape=(coarse_class, distance)`` is the one exception: a member a pool may not hold (``penalty`` > 0) with no
    class-mate to swap to may become the nearest (``distance``) member of the same ``coarse_class`` instead. Such
    pools are listed in ``escaped_pools``; their fit class changed on purpose and the caller must say so.
    """
    by_class: dict[Hashable, list] = {}
    by_escape: dict[Hashable, list] = {}
    for c in candidates:
        by_class.setdefault(fit_class(c), []).append(c)
        if escape:
            by_escape.setdefault(escape[0](c), []).append(c)
    state = RingSet(rings, spec, penalty)
    before = state.total()
    swaps, escaped = 0, set()
    for sweep in range(sweeps):
        moved = False
        for index, ring in enumerate(rings):
            for slot in range(len(ring)):
                current = ring[slot]
                used = {identity(c) for i, c in enumerate(ring) if i != slot}
                best, best_rank, forced = None, (-1e-9, 0.0), False
                for candidate in by_class.get(fit_class(current), ()):
                    if identity(candidate) in used or identity(candidate) == identity(current):
                        continue
                    rank = (state.delta(index, current, candidate), 0.0)
                    if rank < best_rank:
                        best, best_rank = candidate, rank
                if escape and state.penalty(index, current) > 0 and (best is None or state.penalty(index, best) > 0):
                    best, best_rank, forced = None, (0.0, float("inf")), True
                    for candidate in by_escape.get(escape[0](current), ()):
                        if (identity(candidate) in used or identity(candidate) == identity(current)
                                or state.penalty(index, candidate) > 0):
                            continue
                        rank = (state.delta(index, current, candidate), escape[1](current, candidate))
                        if best is None or rank < best_rank:
                            best, best_rank = candidate, rank
                if best is not None:
                    state.replace(index, slot, best)
                    swaps += 1
                    moved = True
                    if forced:
                        escaped.add(index)
        if not moved:
            break
    return dict(swaps=swaps, sweeps=sweep + 1, cost_before=round(before, 6), cost_after=round(state.total(), 6),
                hard_violations=state.hard_violations(), escaped_pools=sorted(escaped))


# --- situational plays ----------------------------------------------------------------------------------------
# Plays that only make sense late in a half. The twenty offensive pools follow nfl2k5_coach_tendencies.projected_pool:
# pools 0..17 are 3 * (2 * distance_bin + urgent) + score_bin (urgent = last two minutes of a half; score_bin 0 =
# leading in the second half, 1 = trailing, 2 = otherwise), 18 = backed up inside the 5, 19 = goal line.
_HAIL = re.compile(r"hail mary|chuck and pray|angelical salutation|spike", re.I)
_KNEEL = re.compile(r"kneel|take knee", re.I)
URGENT_POOLS = frozenset(p for p in range(18) if (p // 3) % 2 == 1)
URGENT_TRAILING_OR_TIED = frozenset(p for p in URGENT_POOLS if p % 3 != 0)
URGENT_LEADING = frozenset(p for p in URGENT_POOLS if p % 3 == 0)


def situational_penalty(weights: Weights = DEFAULT_WEIGHTS) -> Callable[[int, object], float]:
    """Hard cost of a Hail Mary-type or spike play in an ordinary pool, or a kneel outside a late lead.

    Names are read from the compiled play and formation, never from indices. With no allowed pool a play of that kind
    is simply never recorded, which is also what a coach that never charted one would show.
    """
    def penalty(index: int, choice) -> float:
        if not weights.situational:
            return 0.0
        text = f"{getattr(choice, 'play_name', '')} {getattr(choice, 'formation_name', '')}"
        if _HAIL.search(text) and index not in URGENT_TRAILING_OR_TIED:
            return weights.hard
        if _KNEEL.search(text) and index not in URGENT_LEADING:
            return weights.hard
        return 0.0
    return penalty


# --- ordering -----------------------------------------------------------------------------------------------

def order_ring(ring: Sequence, key: Callable[[object], Hashable], screen: Callable[[object], bool] = lambda c: False):
    """Reorder so no two circular neighbours share ``key`` and no two screens touch, when that is possible.

    The input order is kept where it already satisfies the rules; the search is a bounded depth-first walk, so the
    result is deterministic. Returns a new list (a permutation of ``ring``).
    """
    items = list(ring)
    n = len(items)

    def clash(a, b):
        return key(a) == key(b) or (screen(a) and screen(b))

    def bad(seq):
        return sum(clash(seq[i], seq[(i + 1) % n]) for i in range(n)) if n > 1 else 0

    if bad(items) == 0:
        return items
    best, best_bad = items, bad(items)
    budget = [20000]

    def walk(seq, rest):
        nonlocal best, best_bad
        if budget[0] <= 0:
            return
        budget[0] -= 1
        if not rest:
            b = bad(seq)
            if b < best_bad:
                best, best_bad = list(seq), b
            return
        for i, item in enumerate(rest):
            if seq and clash(seq[-1], item):
                continue
            walk(seq + [item], rest[:i] + rest[i + 1:])
            if best_bad == 0:
                return

    walk([], items)
    return best


# --- metrics ------------------------------------------------------------------------------------------------

def ring_metrics(ring: Sequence, family: Callable[[object], str] | None = None) -> dict:
    """Variety counts of one offensive ring (what the receipts and tests report)."""
    fam = family or (lambda c: getattr(c, "concept", "") or play_family(getattr(c, "play_name", "")))
    fams = [fam(c) for c in ring]
    forms = [c.formation for c in ring]
    screens = [bool(getattr(c, "screen", False)) for c in ring]
    n = len(ring)
    run = best = 1
    for i in range(1, n + (1 if n > 1 else 0)):
        run = run + 1 if fams[i % n] == fams[i - 1] else 1
        best = max(best, run)
    return dict(slots=n, distinct_pairs=len({(c.formation, c.play) for c in ring}),
                distinct_plays=len({c.play for c in ring}), distinct_families=len(set(fams)),
                distinct_formations=len(set(forms)),
                distinct_targets=len({getattr(c, "target", "") for c in ring if getattr(c, "target", "")}),
                screens=sum(screens), screen_families=len({f for f, s in zip(fams, screens) if s}),
                adjacent_screens=sum(screens[i] and screens[(i + 1) % n] for i in range(n)) if n > 1 else 0,
                max_same_family=max(Counter(fams).values()) if n else 0,
                max_same_formation=max(Counter(forms).values()) if n else 0,
                longest_family_run=min(best, n),
                repeated_formation_family=_repeat_cost(Counter(zip(forms, fams)), 1))


def pool_metrics(rings: Iterable[Sequence]) -> dict:
    """Cross-pool spread: distinct pairs, plays, families and formations over all rings, and the heaviest reuse."""
    slots = [c for ring in rings for c in ring]
    pairs = Counter((c.formation, c.play) for c in slots)
    return dict(slots=len(slots), distinct_pairs=len(pairs), distinct_plays=len({c.play for c in slots}),
                distinct_families=len({getattr(c, "concept", "") or play_family(getattr(c, "play_name", ""))
                                       for c in slots}),
                distinct_formations=len({c.formation for c in slots}),
                most_reused_pair=max(pairs.values()) if pairs else 0)
