"""Host-only MyCareer pre-draft event scoring and earned-rating projects.

The proposal's thresholds are inclusive. Negative yardage earns zero; completion
percentages use exact Decimal comparisons (64.99 earns one, 65 earns two).
Positive finite dash seconds round to hundredths, half-up: 4.495 becomes 4.50.
This closes the sub-hundredth gaps between chart rows without float ambiguity.
The faster of exactly two attempts wins; a rounded tie selects attempt one.
Speed clamps to 95 below 4.34 and 75 above 4.82; a dash above 4.82 earns zero.
A speed rating's inverse is its inclusive time interval, not an invented time.

One Senior Bowl result and one pre-draft result may be recorded per project.
Undrafted prospects cannot earn either. No Pro Day or playable event is implied.
Each point buys one attribute increment, not played-game XP. Each scoring bucket
funds only its listed purchasable attributes; SCR is recorded in the proposal
but excluded from purchases because existing progression treats it as a style
byte with throw parity. SEC maps to hold_onto_ball. Dash speed obeys min(chart, progression
cap). Purchases never lower existing ratings, including ratings above a cap.
All credits and debits are derived by replay, never trusted serialized totals.
Transaction IDs and event slots are unique. Atomic purchases require the exact
replayed record; stale records and replayed purchases fail without mutation.

Projects persist the baseline and ordered journal together. Reload replays every
entry and checks every permission, cap and debit. Saving over a project requires
its existing journal to be a prefix, preventing a stale copy from refunding a
spend. This is local bookkeeping for supplied results, not authentication of
played statistics or protection against deliberate replacement of local files.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import os
from pathlib import Path
import tempfile

from . import nfl2k5_my_career_progression as progression
from . import nfl2k5_roster_records as roster

SENIOR_PASS_BANDS = ((200, 1), (300, 2), (400, 3))
SENIOR_RUSH_BANDS = ((50, 1), (75, 2), (100, 3))
DASH_BANDS = ((449, 5), (454, 4), (459, 3), (469, 2), (482, 1))
SKELETON_YARDS_BANDS = ((100, 1), (150, 2), (200, 3))
SKELETON_COMPLETION_BANDS = ((60, 1), (65, 2), (70, 3))
SENIOR_BOWL_CAP, COMBINE_CAP = 6, 11
MAX_SPEED_CHART = (
    (434, 435, 95), (436, 437, 94), (438, 439, 93), (440, 441, 92),
    (442, 443, 91), (444, 446, 90), (447, 449, 89), (450, 452, 88),
    (453, 454, 87), (455, 457, 86), (458, 459, 85), (460, 461, 84),
    (462, 463, 83), (464, 466, 82), (467, 468, 81), (469, 472, 80),
    (473, 474, 79), (475, 476, 78), (477, 478, 77), (479, 480, 76),
    (481, 482, 75),
)
PASS_FIELDS = ('pass_arm_strength', 'pass_accuracy', 'pass_read_coverage', 'composure', 'consistency')
PROPOSED_RUSH_FIELDS = ('break_tackle', 'scramble', 'agility', 'hold_onto_ball')
RUSH_FIELDS = tuple(field for field in PROPOSED_RUSH_FIELDS if field not in roster.STYLE_RATINGS)
PERMISSIONS = {
    'senior_pass': PASS_FIELDS, 'senior_rush': RUSH_FIELDS,
    'dash': ('speed',) + RUSH_FIELDS,
    'skeleton_yards': PASS_FIELDS, 'skeleton_completion': PASS_FIELDS,
}
SCHEMA = 'nfl2k5_my_career_events/v1'
MAX_PROJECT_BYTES = 65536


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def validate_tables():
    for bands in (SENIOR_PASS_BANDS, SENIOR_RUSH_BANDS, SKELETON_YARDS_BANDS,
                  SKELETON_COMPLETION_BANDS):
        _require(len(bands) == 3 and tuple(p for _, p in bands) == (1, 2, 3)
                 and all(a[0] < b[0] for a, b in zip(bands, bands[1:])), 'Invalid scoring bands.')
    _require(tuple(p for _, p in DASH_BANDS) == (5, 4, 3, 2, 1)
             and all(a[0] < b[0] for a, b in zip(DASH_BANDS, DASH_BANDS[1:])), 'Invalid dash bands.')
    _require(len(MAX_SPEED_CHART) == 21 and
             tuple(p for _, _, p in MAX_SPEED_CHART) == tuple(range(95, 74, -1)) and
             all(lo <= hi for lo, hi, _ in MAX_SPEED_CHART) and
             all(a[1] + 1 == b[0] for a, b in zip(MAX_SPEED_CHART, MAX_SPEED_CHART[1:])),
             'Invalid Max Speed chart.')
    _require(SENIOR_BOWL_CAP == 6 and COMBINE_CAP == 11, 'Invalid event caps.')
    fields = {key for _, key, _ in progression.FIELDS}
    _require(all(set(names) <= fields for names in PERMISSIONS.values()), 'Invalid event attributes.')


def _decimal(value, label):
    _require(type(value) in (int, float, str, Decimal), f'{label} must be a finite number.')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f'{label} must be a finite number.') from exc
    _require(result.is_finite(), f'{label} must be a finite number.')
    return result


def _integer(value, label):
    _require(type(value) is int, f'{label} must be an integer.')
    return value


def _points(value, bands):
    return max((points for threshold, points in bands if value >= threshold), default=0)


def dash_hundredths(seconds):
    value = _decimal(seconds, 'Dash time')
    _require(0 < value <= 3600, 'Dash time must be positive and at most 3600 seconds.')
    return int((value * 100).to_integral_value(rounding=ROUND_HALF_UP))


def dash_points(seconds):
    time = dash_hundredths(seconds)
    return next((points for limit, points in DASH_BANDS if time <= limit), 0)


def max_speed(seconds):
    time = dash_hundredths(seconds)
    return next((speed for _, hi, speed in MAX_SPEED_CHART if time <= hi), 75)


def speed_interval(speed):
    _integer(speed, 'Speed')
    for lo, hi, rating in MAX_SPEED_CHART:
        if rating == speed:
            return Decimal(lo) / 100, Decimal(hi) / 100
    raise ValueError('The Max Speed chart contains ratings 75 through 95.')


def senior_bowl_points(pass_yards, rush_yards):
    result = {'senior_pass': _points(_integer(pass_yards, 'Pass yards'), SENIOR_PASS_BANDS),
              'senior_rush': _points(_integer(rush_yards, 'Rush yards'), SENIOR_RUSH_BANDS)}
    _require(sum(result.values()) <= SENIOR_BOWL_CAP, 'Senior Bowl cap exceeded.')
    return result


def pre_draft_points(attempts, pass_yards, completion_percent):
    _require(isinstance(attempts, (list, tuple)) and len(attempts) == 2, 'Enter exactly two dash attempts.')
    times = tuple(dash_hundredths(t) for t in attempts)
    best = min(range(2), key=times.__getitem__)
    percent = _decimal(completion_percent, 'Completion percentage')
    _require(0 <= percent <= 100, 'Completion percentage must be between 0 and 100.')
    credits = {'dash': dash_points(attempts[best]),
               'skeleton_yards': _points(_integer(pass_yards, 'Pass yards'), SKELETON_YARDS_BANDS),
               'skeleton_completion': _points(percent, SKELETON_COMPLETION_BANDS)}
    _require(sum(credits.values()) <= COMBINE_CAP, 'Pre-draft event cap exceeded.')
    return {'credits': credits, 'speed_cap': max_speed(attempts[best]), 'best_attempt': best + 1}


def new_ledger(record, *, prospect_tier=0):
    from .nfl2k5_my_career_prospects import tier_id
    result = {'schema': SCHEMA, 'baseline': record.encode().hex(),
              'prospect_tier': tier_id(prospect_tier), 'entries': []}
    replay(result)
    return result


def _keys(value, expected):
    _require(isinstance(value, dict) and set(value) == set(expected), 'Invalid earned-rating journal fields.')


def replay(ledger):
    """Return the only record and balances this journal permits, without writes."""
    _keys(ledger, ('schema', 'baseline', 'prospect_tier', 'entries'))
    _require(ledger['schema'] == SCHEMA, 'Unsupported earned-rating project.')
    baseline = ledger['baseline']
    _require(isinstance(baseline, str) and len(baseline) == 168, 'Invalid MyPlayer baseline.')
    record = roster.PlayerRecord.decode(bytes.fromhex(baseline))
    position = record.get('position')
    _require(0 <= position < 17, 'Invalid MyPlayer position.')
    _require(type(ledger['prospect_tier']) is int and 0 <= ledger['prospect_tier'] <= 4, 'Invalid prospect tier.')
    entries = ledger['entries']
    _require(isinstance(entries, list) and len(entries) <= 19, 'Earned-rating journal exceeds its bound.')
    balance = dict.fromkeys(PERMISSIONS, 0)
    earned = dict(balance)
    seen = set()
    speed_cap = None
    caps = dict((key, progression.CAPS[position][i]) for i, (_, key, _) in enumerate(progression.FIELDS))
    for entry in entries:
        _require(isinstance(entry, dict), 'Invalid earned-rating entry.')
        kind = entry.get('kind')
        if kind in ('senior_bowl', 'pre_draft'):
            _require(ledger['prospect_tier'] != 4, 'Undrafted prospects are not invited to these pre-draft events.')
            _require(kind not in seen, 'This event result is already recorded.')
            seen.add(kind)
            if kind == 'senior_bowl':
                _keys(entry, ('kind', 'pass_yards', 'rush_yards'))
                credits = senior_bowl_points(entry['pass_yards'], entry['rush_yards'])
            else:
                _keys(entry, ('kind', 'attempts', 'pass_yards', 'completion_percent'))
                scored = pre_draft_points(entry['attempts'], entry['pass_yards'], entry['completion_percent'])
                speed_cap, credits = scored['speed_cap'], scored['credits']
            for bucket, points in credits.items():
                earned[bucket] += points
                balance[bucket] += points
        elif kind == 'spend':
            _keys(entry, ('kind', 'id', 'purchases'))
            tx = entry['id']
            _require(isinstance(tx, str) and 0 < len(tx) <= 80, 'Give this purchase a transaction ID (1 to 80 characters).')
            _require(('spend', tx) not in seen, 'This purchase was already spent.')
            seen.add(('spend', tx))
            purchases = entry['purchases']
            _require(isinstance(purchases, dict) and purchases and set(purchases) <= set(PERMISSIONS), 'Choose earned event buckets.')
            for bucket in sorted(purchases):
                fields = purchases[bucket]
                _require(isinstance(fields, dict) and fields and set(fields) <= set(PERMISSIONS[bucket]), 'This event cannot fund that attribute.')
                _require(all(type(v) is int and v > 0 for v in fields.values()), 'Buy positive whole rating points.')
                debit = sum(fields.values())
                _require(debit <= balance[bucket], 'Purchase exceeds the points earned in this event bucket.')
                for field, amount in sorted(fields.items()):
                    cap = caps[field]
                    if field == 'speed':
                        _require(speed_cap is not None, 'Speed requires a recorded dash result.')
                        cap = min(cap, speed_cap)
                    value = record.get(field) + amount
                    _require(value <= cap, f'{roster.RATING_LABELS[field]} purchase exceeds its progression or event cap.')
                    record.set(field, value)
                balance[bucket] -= debit
        else:
            raise ValueError('Unknown earned-rating journal entry.')
    return record, {'earned': sum(earned.values()), 'spent': sum(earned.values()) - sum(balance.values()),
                    'available': sum(balance.values()), 'buckets': balance, 'speed_cap': speed_cap}


def earn(ledger, *, event, **result):
    """Commit supplied host-side results once; points are always recomputed."""
    _require(event in ('senior_bowl', 'pre_draft'), 'Choose a supported pre-draft event.')
    candidate = deepcopy(ledger)
    if event == 'senior_bowl':
        _keys(result, ('pass_yards', 'rush_yards'))
    if event == 'pre_draft':
        _keys(result, ('attempts', 'pass_yards', 'completion_percent'))
        pre_draft_points(result['attempts'], result['pass_yards'], result['completion_percent'])
        result['attempts'] = [str(x) for x in result['attempts']]
        result['completion_percent'] = str(result['completion_percent'])
    candidate['entries'].append({'kind': event, **result})
    _, totals = replay(candidate)
    ledger.clear()
    ledger.update(candidate)
    return totals


def apply_earned(record, ledger, purchases, *, transaction_id):
    """Atomically increase ratings and debit their earned buckets, or change nothing."""
    expected, _ = replay(ledger)
    _require(record.encode() == expected.encode(), 'MyPlayer changed since this journal. Reload the matching project.')
    candidate = deepcopy(ledger)
    candidate['entries'].append({'kind': 'spend', 'id': transaction_id, 'purchases': deepcopy(purchases)})
    after, totals = replay(candidate)
    record.values.update(after.values)
    ledger.clear()
    ledger.update(candidate)
    return totals


def validated_ledger(ledger):
    """Detached, replay-checked metadata for a Studio project; None means absent."""
    if ledger is None:
        return None
    replay(ledger)
    return deepcopy(ledger)


def require_extension(prior, ledger):
    _require(all(prior[key] == ledger[key] for key in ('schema', 'baseline', 'prospect_tier')) and
             ledger['entries'][:len(prior['entries'])] == prior['entries'],
             'This project has newer or different results. Reload it before saving.')


def project_bytes(record, ledger):
    expected, _ = replay(ledger)
    _require(record.encode() == expected.encode(), 'MyPlayer does not match the earned-rating journal.')
    return (json.dumps(ledger, sort_keys=True, indent=2) + '\n').encode('utf-8')


def load_project(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_PROJECT_BYTES + 1)
    _require(len(raw) <= MAX_PROJECT_BYTES, 'Earned-rating project exceeds 64 KiB.')
    ledger = json.loads(raw)
    record, _ = replay(ledger)
    return record, ledger


def save_project(path, record, ledger):
    """Save record and journal atomically; never replace a newer spend with stale state."""
    payload = project_bytes(record, ledger)
    _require(len(payload) <= MAX_PROJECT_BYTES, 'Earned-rating project exceeds 64 KiB.')
    path = Path(path)
    # Exclusive sidecar prevents two stale writers passing the prefix check.
    lock = path.with_name(path.name + '.lock')
    try:
        lock_stream = lock.open('xb')
    except FileExistsError as exc:
        raise ValueError('This earned-rating project is being saved. Retry after the other save finishes.') from exc
    temporary = None
    try:
        with lock_stream:
            if path.exists():
                _, prior = load_project(path)
                require_extension(prior, ledger)
            handle, temporary = tempfile.mkstemp(prefix='.mycareer-events-', dir=path.parent)
            with os.fdopen(handle, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)
        lock.unlink()


validate_tables()
