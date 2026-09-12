"""Offline retail selector arithmetic, with explicit empty-world boundaries.

The preview is a repeatable Monte Carlo sample, not a replay of the game's
55-word RNG state. Raw rating numbers run in the opposite direction from a
conventional 'better' slider. See docs/research/apf_playcall_model.md.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import math
import random
import struct

from . import apf2k8_splb_writer as splb
from .errors import ValidationError as _ValidationError


class PlaycallError(_ValidationError, ValueError):
    """A plain-language authoring refusal, also catchable by existing clients."""


ValidationError = PlaycallError

OFFENSE_CURVE = (1., 1., .85, .5, .05)
DEFENSE_CURVE = (1., .01, 0.)
FORMATION_CURVE = (.5, 2., 1., .5, .1)
CATEGORY_RATING_CURVE = (3., 2., 1., .5, .1)
X_CURVE = (2., 1.4, 1., .5, .1)
ROLE_NAMES = {0: 'QB', 1: 'P', 2: 'K', 3: 'H', 4: 'WR', 5: 'T',
              6: 'C', 7: 'G', 8: 'TE', 9: 'WR', 10: 'HB', 11: 'FB',
              12: 'DE', 13: 'DT', 14: 'ILB', 15: 'OLB', 16: 'FS',
              17: 'SS', 18: 'CB', 19: 'Unassigned'}
DEFAULT_NOTES = (
    'Preview uses empty learned history and neutral player skill; live history and player attributes can change weights.',
    'Preview uses a cold scrimmage context with no cached special call or previous play.',
    'Clock-management urgency, saved USER banks and global book merges are not reconstructed from these inputs.',
    'Kicker-range-dependent branches assume a 50-yard range; that range is not a proved retail default.',
    'Seeds are repeatable preview samples, not the game RNG seed.',
)


def f32(x):
    return struct.unpack('>f', struct.pack('>f', x))[0]


def curve(x, values, start=0):
    """Retail float interpolation (including rounding at each scalar step)."""
    x = f32(x - start)
    if x <= 0:
        return f32(values[0])
    if x >= len(values) - 1:
        return f32(values[-1])
    i = int(x)
    lo, hi = f32(values[i]), f32(values[i + 1])
    return f32(lo + f32(f32(x - i) * f32(hi - lo)))


def _int(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise ValidationError(f'{name} must be an integer from {lo} to {hi}')
    return value


def _finite(value, lo, hi, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValidationError(f'{name} must be a finite number from {lo} to {hi}')
    return float(value)


@dataclass(frozen=True)
class Situation:
    down: int
    distance_yards: float
    yards_to_goal: float
    period: int
    clock_seconds: float
    score_margin: int
    timeouts: int
    phase: str = 'scrimmage'

    def __post_init__(self):
        _int(self.down, 1, 4, 'Down')
        _finite(self.distance_yards, 0, 100, 'Distance')
        _finite(self.yards_to_goal, 0, 100, 'Yards to goal')
        _int(self.period, 1, 20, 'Period')
        _finite(self.clock_seconds, 0, 3600, 'Clock')
        _int(self.score_margin, -999, 999, 'Score margin')
        _int(self.timeouts, 0, 3, 'Timeouts')
        if self.phase != 'scrimmage':
            raise ValidationError('This preview currently supports scrimmage calls only')


@dataclass(frozen=True)
class CategoryRow:
    id: int
    name: str
    row: int
    roles: tuple[str, ...]
    tight_ends: int


@dataclass(frozen=True)
class CallDistribution:
    categories: list[tuple[int, str, float]]
    formations: list[tuple[int, str, float]]
    plays: list[tuple[int, str, float]]
    requested_row: int
    notes: tuple[str, ...]


def _master(master):
    from .apf2k8_formation_alignment_writer import apf_category_count
    if not isinstance(master, bytes):
        raise PlaycallError('MASTER must be immutable decoded bytes')
    try:
        count = apf_category_count(master)
    except _ValidationError as exc:
        raise PlaycallError(str(exc)) from exc
    if count != 28 or len(master) < 0x80C4 + 586 * 100:
        raise ValidationError('Expected the retail MASTER category, formation and play layout')


def _name(master, at):
    target = at + struct.unpack_from('>i', master, at)[0] - 1
    if not 0 <= target < len(master) - 1 or target & 1:
        raise ValidationError('MASTER contains an invalid relative name pointer')
    end = target
    while end + 1 < len(master) and master[end:end + 2] != b'\0\0':
        end += 2
    try:
        return master[target:end].decode('utf-16-be')
    except UnicodeError as exc:
        raise ValidationError('MASTER name is not valid text') from exc


def personnel_roles(master: bytes, category_id: int) -> tuple[str, ...]:
    _master(master)
    _int(category_id, 0, 27, 'Category')
    return tuple(ROLE_NAMES.get(b & 31, f'Role {b & 31}')
                 for b in master[0x49 + 16 * category_id:0x54 + 16 * category_id])


@lru_cache(maxsize=8)
def category_table(master: bytes) -> tuple[CategoryRow, ...]:
    _master(master)
    return tuple(CategoryRow(i, _name(master, 0x44 + 16 * i),
                             master[0x48 + 16 * i] & 63,
                             personnel_roles(master, i), personnel_roles(master, i).count('TE'))
                 for i in range(28))


def _distance(s):
    # Same two rounded vector coordinates as the native harness/game.
    ball = f32(4572 - s.yards_to_goal * 91.44)
    return f32(f32(4572 - s.yards_to_goal * 91.44 + s.distance_yards * 91.44) - ball)


def requested_offense_row(s: Situation, uniform=.5, urgency=0.):
    _finite(uniform, 0, 1, 'Uniform draw')
    yards = _distance(s)
    down = 1 if s.down == 2 and f32(822.96) <= yards <= f32(1005.84) else s.down
    x = f32(f32(max(1., f32(down * .5))) * f32(yards / max(4 - down, 1)))
    points = tuple((f32(a), f32(b)) for a, b in ((91.44, 0), (301.752, 4), (457.2, 4), (1097.28, 11)))
    value = points[-1][1]
    if x <= points[0][0]:
        value = points[0][1]
    else:
        for (a, b), (c, d) in zip(points, points[1:]):
            if x <= c:
                # 8463FC88 multiplies the deltas before dividing. Reordering
                # those operations changes half-integer row boundaries.
                value = f32(b + f32(f32(f32(d - b) * f32(x - a)) / f32(c - a)))
                break
    if s.period > 4 and s.yards_to_goal < 50:
        value = f32(value - f32(1 - s.yards_to_goal / 50) * 2)
    value = f32(value + f32(urgency + f32(uniform * 2 - 1)))
    return min(10, max(0, int(value + (.5 if value >= 0 else -.5))))


def requested_defense_row(offense_row, yards_to_goal, *, urgent=False):
    _int(offense_row, 0, 27, 'Offensive personnel row')
    _finite(yards_to_goal, 0, 100, 'Yards to goal')
    if offense_row <= 4:
        return 11 if yards_to_goal < 5 else 13
    if offense_row <= 7:
        return 13 if yards_to_goal < 5 else (16 if urgent else 14)
    if offense_row <= 10:
        return 14 if yards_to_goal < 5 else (16 if urgent else 15)
    if offense_row == 19:
        # The cold harness supplies the neutral kicker range of 50 yards.
        return 20 if yards_to_goal <= 50 else 13
    return {17: 13, 21: 23, 22: 24}.get(offense_row, 25)


def formation_weight(record, master, situation, *, category=False, urgency=0., run_share=.5):
    word = struct.unpack_from('>I', master, 0x248 + 184 * record.formation_index)[0]
    family = word >> 26
    if family == 0 and run_share >= f32(.9):
        return 0.
    if family <= 3 and word & 0x3000 == 0x2000 and situation.yards_to_goal > 90:
        return f32(.05)
    ratings = tuple((int.from_bytes(record.trailer[:4], 'big') >> shift) & 7 for shift in (14, 11, 8))
    values = CATEGORY_RATING_CURVE if category else FORMATION_CURVE
    if urgency > .5 or urgency < -.5:
        return curve(ratings[2 if urgency > .5 else 0] - 1, values, -2)
    low, high = (2, 7) if situation.down == 3 else (2, 5) if situation.down == 4 else (0, 20)
    t = min(1., max(0., f32(f32(_distance(situation) - f32(low * 91.44)) / f32(f32(high * 91.44) - f32(low * 91.44)))))
    first = 0 if t < .5 else 1
    fraction = f32((t - first * .5) * 2)
    a, b = (curve(ratings[i] - 2, values, -2) for i in (first, first + 1))
    return f32(f32(f32(1 - fraction) * a) + b * fraction)


@lru_cache(maxsize=32)
def _records(book):
    try:
        parsed = splb.parse_book(book, 0)
    except _ValidationError as exc:
        raise PlaycallError(str(exc)) from exc
    result = []
    for record in parsed.records:
        if not record.populated:
            break
        if record.formation_index >= 163 or record.category_index >= 28:
            raise ValidationError('Book refers to a formation or category outside MASTER')
        if any(e.play_index >= 586 for e in record.entries):
            raise ValidationError('Book contains a play outside MASTER')
        result.append(record)
    return tuple(result)


def category_weights(book, master, row, situation, *, run_share=.5, urgency=0., distance_curve=None):
    categories = category_table(master)
    records = _records(book)
    result = []
    for c in categories:
        members = [r for r in records if int.from_bytes(r.trailer[4:], 'big') & (1 << c.id)]
        if not members or (row <= 10 and c.row > 10) or (11 <= row <= 16 and not 11 <= c.row <= 16):
            continue
        if row <= 10:
            distance = abs(c.row - row) * (.5 if situation.down <= 2 and abs(urgency) < .5 else 1)
            weights = [formation_weight(r, master, situation, category=True, urgency=urgency, run_share=run_share) for r in members]
            total = 0.
            for w in weights:
                total = f32(total + w)
            mean = f32(total / len(weights)) if min(weights) > 0 else 0.
            weight = f32(curve(distance, distance_curve or OFFENSE_CURVE) * mean)
        elif 11 <= row <= 16:
            weight = curve(c.row - row, distance_curve or DEFENSE_CURVE) if c.row >= row else 0.
        else:
            if row != 25 and row != c.row:
                continue
            weight = 1.
        result.append((c.id, weight))
    return tuple(result)


def formation_weights(book, master, category_id, situation, *, run_share=.5, urgency=0.):
    records = [r for r in _records(book) if int.from_bytes(r.trailer[4:], 'big') & (1 << category_id)
               and not struct.unpack_from('>I', master, 0x24C + r.formation_index * 184)[0] & 1]
    if any(r.category_index == category_id for r in records):
        records = [r for r in records if r.category_index == category_id]
    return _bounded_candidates((r.formation_index, formation_weight(r, master, situation, urgency=urgency, run_share=run_share)) for r in records)


def _bounded_candidates(candidates, integer=1):
    """The native forty-slot overflow retains 39 with one random overwrite."""
    result = []
    for candidate in candidates:
        result.append(candidate)
        if len(result) == 40:
            result[integer % 40] = result[-1]
            result.pop()
    return tuple(result)


def adjusted_run_share(share, s):
    """8486A1F8's ordinary cold-context arm (no estimated-time history)."""
    _finite(share, 0, 1, 'Run share')
    distance = _distance(s)
    down = 1 if s.down == 2 and f32(822.96) <= distance <= f32(1005.84) else s.down
    value = f32(share)
    if not (down <= 1 and f32(822.96) <= distance <= f32(1005.84)):
        per_down = f32(distance / (4 - min(down, 3)))
        threshold = f32(f32(320.04) - (f32(91.44) if down == 3 else 0))
        correction = f32(f32(threshold - per_down) / f32(threshold * (4 if per_down >= threshold else 2)))
        value = f32(value + correction)
    if s.score_margin > 3:
        value = f32(value + f32(s.score_margin * f32(.005)))
    goal = f32(4572 - f32(4572 - s.yards_to_goal * 91.44))
    if goal > f32(8458.2):
        value = f32(value + f32(goal - f32(8458.2)) * f32(.1))
    return min(1., max(0., value))


OP_PROPERTIES = (0x200f, 0xf, 0x8c5, 0x1805, 0x3081, 0x20c4, 0x20c1,
                 0x20c4, 0x2044, 0x2348, 0x2004, 0x2002, 0x2008, 0x210a,
                 0x210a, 0x210a, 0x2008, 0x200d, 0x2101, 0x20c1, 0x2481,
                 0x2089, 0x2141, 0x2501, 0x200f, 0x220a, 0x2205, 0x80a, 0x210a)


@lru_cache(maxsize=4096)
def play_carrier_slot(master, play_id):
    """84A87B38 assignment classifier, independent of roster/player objects."""
    from .apf2k8_play_codec import Node
    at = 0x80C4 + play_id * 100
    family, flags = struct.unpack_from('>II', master, at + 4)
    if family >> 28 in (2, 4, 6):
        return 0
    if family >> 28:
        return -1
    slots = []
    for slot in range(11):
        field = at + 12 + 8 * slot
        count = struct.unpack_from('>I', master, field)[0] >> 28
        target = field + 4 + struct.unpack_from('>i', master, field + 4)[0] - 1
        if count and not 0 <= target <= len(master) - count * 8:
            raise ValidationError('Play assignment chain is outside MASTER')
        slots.append(tuple(Node.from_bytes(master[target + i * 8:target + i * 8 + 8]) for i in range(count)))
    if flags & 2:
        for slot, nodes in enumerate(slots):
            for n in nodes:
                if n.op == 6:
                    return slot if flags & 0x402 == 0x402 else int(n.operands[1]) + 5
    links = [-1] * 11
    for slot, nodes in enumerate(slots):
        previous = False
        for node in nodes:
            prop = OP_PROPERTIES[node.op]
            special = not node.flags & 0x80 and (node.flags & 0x20 or node.op in (0x13, 0x16))
            if not special:
                previous = bool(prop & 0x80)
                continue
            if not prop & 0x80 and not (previous and node.op == 0x1A):
                break
            if node.op == 6:
                return int(node.operands[1]) + 5
            if not prop & 0x40 or node.op == 0x16:
                return slot
            if node.op == 0x13:
                links[slot] = int(node.operands[0])
            break
    for linked in links:
        if 0 <= linked < 11 and links[linked] == -1:
            return linked
    return 0


def play_weights(book, master, formation_id, situation, *, run_share=.5, integer=1):
    """Empty-history, null-player 68C70 arm, including two ordinary variants."""
    record = next((r for r in _records(book) if r.formation_index == formation_id), None)
    if record is None:
        return ()
    result = []
    pass_sum = run_sum = 0.
    for entry in sorted(record.entries, key=lambda e: e.play_index):
        # BA78/A0E0 enumerate the book's stored global play bitmap first.
        # Membership insertion alone need not have rebuilt this cache yet.
        mask = struct.unpack_from('>I', book, 0x7DB0 + 4 * (entry.play_index // 32))[0]
        if not mask & (1 << (entry.play_index % 32)):
            continue
        at = 0x80C4 + entry.play_index * 100
        if entry.play_index >= 586:
            raise ValidationError('Book contains a play outside MASTER')
        family, flags = struct.unpack_from('>II', master, at + 4)
        if flags & 0x401 or family >> 28 > 1:
            continue
        if flags & 2 and run_share == 1 or flags & 8 and run_share == 0:
            continue
        x = curve(entry.x, X_CURVE)
        kind = play_carrier_slot(master, entry.play_index)
        distance = _distance(situation)
        suitability = 1.
        if kind < 6:
            if distance >= f32(365.76):
                suitability = 0.
            elif distance <= f32(182.88):
                suitability = f32(f32(f32(f32(182.88) - distance) * f32(.01093613263219595)) * f32(.1) + f32(.02))
            elif distance <= f32(914.4):
                suitability = f32(.005)
            else:
                suitability = 0.
        weight = f32(x * suitability)
        if flags & 1:
            weight = f32(weight * f32(.025))
        if flags & 0x200:
            weight = f32(weight * .5)  # neutral attribute object's null return
        for variant in ((0, 3) if family >> 28 == 0 else (0,)):
            if family >> 28 == 0:
                if flags & 2:
                    pass_sum = f32(pass_sum + weight)
                elif flags & 8:
                    run_sum = f32(run_sum + weight)
                else:
                    continue
            result.append((entry.play_index, variant, flags, weight))
            if len(result) == 40:
                result[integer % 40] = result[-1]
                result.pop()
    return tuple(((p, v), f32(w * f32((1 - run_share) / pass_sum)) if flags & 2 and pass_sum
                  else f32(w * f32(run_share / run_sum)) if flags & 8 and run_sum else w)
                 for p, v, flags, w in result)


def draw(candidates, uniform, *, power=1, integer=1):
    """84863388 positive-sum draw; zero draw can pick a leading zero."""
    _finite(uniform, 0, 1, 'Uniform draw')
    if not candidates:
        return None
    weights = []
    for _, weight in candidates:
        value = weight
        for _ in range(power - 1):
            value = f32(value * weight)
        weights.append(value)
    total = 0.
    for weight in weights:
        total = f32(total + weight)
    if total <= 0:
        return candidates[integer % len(candidates)][0]
    target = f32(uniform * total)
    for (identifier, _), weight in zip(candidates, weights):
        if weight >= target:
            return identifier
        target = f32(target - weight)
    return candidates[-1][0]


def _component_mask(master, play):
    return sum(1 << slot for slot in range(11)
               if struct.unpack_from('>I', master, 0x80D0 + play * 100 + slot * 8)[0] & 0x800)


def defense_pairs(book, master, formation_id):
    """Native component coverage gates; all serialized plays must be validated."""
    record = next((r for r in _records(book) if r.formation_index == formation_id), None)
    if record is None:
        return ()
    plays = sorted({e.play_index for e in record.entries
                    if struct.unpack_from('>I', book, 0x7DB0 + 4 * (e.play_index // 32))[0] & (1 << (e.play_index % 32))})
    masks = {p: _component_mask(master, p) for p in plays}
    families = {p: struct.unpack_from('>I', master, 0x80C8 + p * 100)[0] >> 28 for p in plays}
    def first_count(p):
        mask = masks[p]
        return 0 if mask & 0x600 else mask.bit_count()
    def second_count(p):
        mask = masks[p]
        return (mask & 0x1FF).bit_count() + 2 if mask & 0x600 else 0
    result = []
    for p in plays:
        if not first_count(p) and second_count(p) != 11:
            continue
        partners = tuple(q for q in plays if families[q] == families[p]
                         and masks[p] | masks[q] == 0x7FF
                         and first_count(p) + second_count(q) >= 11)
        if partners:
            result.append((p, partners))
    return tuple(result)


def defense_pair_weight(book, master, formation_id, first, second, *, lineup_feature=4.):
    """63F58's X product, conditional on the supplied lineup feature scalar."""
    record = next(r for r in _records(book) if r.formation_index == formation_id)
    ratings = {e.play_index: e.x for e in record.entries}
    weight = f32(curve(ratings[first], X_CURVE) * curve(ratings[second], X_CURVE))
    a, b = (struct.unpack_from('>I', master, 0x80CC + p * 100)[0] for p in (first, second))
    if b & 0x4000:
        weight = f32(weight * f32(.8))
    if (a | b) & 0x10:
        weight = f32(weight * f32(1 - f32(lineup_feature - 4) * f32(.15)))
    return weight


def defense_play_weights(book, master, formation_id, first=None, *, lineup_feature=4., integer=1):
    pairs = dict(defense_pairs(book, master, formation_id))
    candidates = pairs if first is None else pairs.get(first, ())
    return _bounded_candidates(((p, defense_pair_weight(book, master, formation_id,
                                p if first is None else first, p, lineup_feature=lineup_feature))
                                for p in candidates), integer)


def predict_offense(book: bytes, master: bytes, tendency_run_share: float, situation: Situation, *, seeds: int = 256) -> CallDistribution:
    _int(seeds, 1, 65536, 'Seeds')
    if not isinstance(book, bytes):
        raise PlaycallError('Book must be immutable decoded SPLB bytes')
    if not isinstance(situation, Situation):
        raise PlaycallError('Supply a Situation for the offense preview')
    _master(master)
    share = adjusted_run_share(tendency_run_share, situation)
    counters = [Counter(), Counter(), Counter()]
    cache = {}
    for seed in range(seeds):
        rng = random.Random(seed)
        row = requested_offense_row(situation, rng.random())
        # Native tendency preparation first chooses run or pass, then the
        # ordinary selector receives that 0/1 outcome at H+67C.
        run = float(rng.random() <= share)
        key = row, run
        if key not in cache:
            cache[key] = category_weights(book, master, row, situation, run_share=run)
        cat = draw(cache[key], rng.random(), power=3)
        if cat is None:
            continue
        counters[0][cat] += 1
        key = 'f', cat, run
        if key not in cache:
            cache[key] = formation_weights(book, master, cat, situation, run_share=run)
        form = draw(cache[key], rng.random())
        if form is None:
            continue
        counters[1][form] += 1
        key = 'p', form, run
        if key not in cache:
            cache[key] = play_weights(book, master, form, situation, run_share=run)
        play = draw(cache[key], rng.random(), power=3)
        if play is not None:
            counters[2][play[0]] += 1
    def rows(counter, base, stride):
        return [(i, _name(master, base + i * stride), n / seeds) for i, n in sorted(counter.items(), key=lambda x: (-x[1], x[0]))]
    notes = DEFAULT_NOTES + tuple(f'{c.name} carries no tight end' for c in category_table(master) if c.id in counters[0] and c.tight_ends == 0)
    stored = {e.play_index for r in _records(book) for e in r.entries}
    if any(not struct.unpack_from('>I', book, 0x7DB0 + 4 * (p // 32))[0] & (1 << (p % 32)) for p in stored):
        notes += ('This book has memberships missing from its stored play cache; normalize after insertion to make those plays reachable.',)
    return CallDistribution(rows(counters[0], 0x44, 16), rows(counters[1], 0x244, 184), rows(counters[2], 0x80C4, 100), requested_offense_row(situation), notes)


def predict_defense(book: bytes, master: bytes, offense_category_row: int, yards_to_goal: float, *, seeds: int = 256) -> CallDistribution:
    _int(seeds, 1, 65536, 'Seeds')
    if not isinstance(book, bytes):
        raise PlaycallError('Book must be immutable decoded SPLB bytes')
    _master(master)
    row = requested_defense_row(offense_category_row, yards_to_goal)
    situation = Situation(1, 10, yards_to_goal, 1, 900, 0, 3)
    categories = category_weights(book, master, row, situation)
    cats, forms, plays = Counter(), Counter(), Counter()
    cache = {}
    for seed in range(seeds):
        rng = random.Random(seed)
        category = draw(categories, rng.random(), power=3)
        if category is None:
            continue
        cats[category] += 1
        if category not in cache:
            cache[category] = formation_weights(book, master, category, situation)
        form = draw(cache[category], rng.random())
        if form is not None:
            forms[form] += 1
            key = 'firsts', form
            if key not in cache:
                cache[key] = defense_play_weights(book, master, form)
            first = draw(cache[key], rng.random(), power=3)
            if first is not None:
                key = 'seconds', form, first
                if key not in cache:
                    cache[key] = defense_play_weights(book, master, form, first)
                second = draw(cache[key], rng.random(), power=3)
                # Each component's probability is its probability of occurring
                # in the selected pair. These marginals can sum to two.
                plays[first] += 1
                if second is not None and second != first:
                    plays[second] += 1
    def rows(count, base, stride):
        return [(i, _name(master, base + i * stride), n / seeds) for i, n in sorted(count.items(), key=lambda x: (-x[1], x[0]))]
    return CallDistribution(rows(cats, 0x44, 16), rows(forms, 0x244, 184), rows(plays, 0x80C4, 100), row,
                            DEFAULT_NOTES + ('Defensive play estimates are conditional on a lineup feature value of four; that neutral value is a hypothesis, not a proved retail default.',
                                             'Defensive play probabilities count both components and can total more than one.',))
