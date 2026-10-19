"""Experimental, copy-only NFL 2K5 USR coach-history export.

Native retail serializer: 192610/1401B0. Context: 142370. Offense reader:
17F1D0/F72B0. This is a manual Quick Game opponent, not a franchise binding.
The receipt lists every changed span and every retained template feature.
No game assets, title key, or template are bundled.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import copy
import hashlib
import math
from pathlib import Path
import struct

from . import nfl2k5_playbook_inspector as ip
from . import nfl2k5_playbook_lint as lint
from . import nfl2k5_play_library as library
from . import nfl2k5_play_codec as codec
from . import nfl2k5_coach_diversity as diversity
from .nfl2k5_save_writer import derive_sig_key, sign_save, verify_extra

SIZE, PRIMARY_SIZE, CONTEXT = 0x50F0, 0x1278, 0x2F1C
OFFENSE, POOLS, POOL_SIZE, RECORD_SIZE = 0x3C, 20, 0x80, 14
SCHEMA = "nfl2k5_vip_offense/v1"


def coach_identity(team: str, name: str) -> int:
    """Stable authored identity, independent of a rebuilt playbook's bytes.

    The coach portrait router also accepts the original vp1 book-derived IDs.
    Exact book pins remain in the profile receipt and automatic PLAY payload.
    """
    return int.from_bytes(hashlib.sha256(("nfl2k5_coach_vip/v2\0" + team + "\0" + name).encode()).digest()[:4], "little") or 1


class VipError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise VipError(message)


def save_container_id(name: str) -> str:
    """Xbox save-name hash used for the 12-hex UDATA container directory.

    The directory and SaveMeta Name must agree: the save manager reopens
    members by the name-derived path. This is separate from the USR identity
    and HMAC. Native XAPI 378CBF multiplies by 65536 and reduces modulo
    2**48 - 59 for each UTF-16 unit before formatting twelve hex digits.
    """
    require(isinstance(name, str) and name and not any(c in name for c in "\0\r\n"),
            "Save name must be nonempty and contain no NUL or line breaks")
    raw = name.encode("utf-16le")
    value = 0
    for unit, in struct.iter_unpack("<H", raw):
        value = ((value << 16) + unit) % 0xFFFFFFFFFFC5
    return f"{value:012X}"


@dataclass(frozen=True)
class VipSave:
    """Lossless representation: unknown bytes are never reconstructed."""
    payload: bytes

    @classmethod
    def decode(cls, payload: bytes) -> "VipSave":
        require(len(payload) == SIZE, "USR must contain exactly 20,720 bytes")
        require(struct.unpack_from("<I", payload)[0] != 0, "USR identity is zero")
        for base, count, stride, capacity in ((OFFENSE, 20, 128, 9), (0xA3C, 15, 62, 5)):
            for i in range(count):
                require(payload[CONTEXT + base + i * stride + 1] < capacity,
                        f"Invalid history cursor at context {base + i * stride:#x}")
        value = cls(bytes(payload))
        _ = value.name
        return value

    @property
    def name(self) -> str:
        units = struct.unpack_from("<13H", self.payload, 4)
        require(0 in units, "USR name is not terminated")
        try:
            return self.payload[4:4 + units.index(0) * 2].decode("utf-16le")
        except UnicodeDecodeError as exc:
            raise VipError("USR name is not valid UTF-16") from exc

    @property
    def book_index(self) -> int:
        return struct.unpack_from("<i", self.payload, CONTEXT + 0x34)[0]

    def encode(self) -> bytes:
        return self.payload


@dataclass(frozen=True)
class Choice:
    formation: int
    play: int
    passed: bool
    shotgun: bool
    formation_name: str
    play_name: str
    play_action: bool = False
    screen: bool = False
    deep_primary: bool | None = None
    run_location: str | None = None
    run_gap: str | None = None
    flipped: bool = False
    run_lane: str | None = None
    # Variety metadata (b776 pb2), read from the compiled play, never from its index: the concept family of the
    # play name and the primary target / ball carrier as "KIND:side". Not part of any charted fit.
    concept: str = ""
    target: str = ""

    @property
    def category(self) -> str:
        return ("pass" if self.passed else "run") + ("_gun" if self.shotgun else "_under")


CATEGORIES = ("run_under", "run_gun", "pass_under", "pass_gun")
TARGET_KINDS = {0: "QB", 8: "TE", 9: "WR", 10: "HB", 11: "FB"}
RUN_LANES = ("left_outside", "left_inside", "middle", "right_inside", "right_outside")
# Native 281300's nine-hole -> five-lane table, independently checked in replay.
HOLE_LANES = (2, 4, 3, 3, 2, 2, 1, 1, 0)


def _slot_target(view, slot):
    """"KIND:side" of a formation slot (WR:L, TE:R, HB:C ...), or None for a slot outside the skill spots."""
    if slot is None or not 0 <= slot < len(view.codes):
        return None
    kind = TARGET_KINDS.get(view.codes[slot] & 31)
    return f"{kind}:{diversity.side_of(view.positions[slot][0])}" if kind else None


def _mirror_target(target):
    return target.translate(str.maketrans("LR", "RL")) if target else target


def choices_from_book(resource: bytes) -> tuple[Choice, ...]:
    """Use actual compiled menu references and native type/stance bits.

    Names are descriptive only. A caller must independently run the native
    compatibility accessor before certifying an export for game use.
    """
    book = ip.parse_playbook_resource(resource)
    body = resource[32:]
    views = {(v.formation, v.play): v for v in lint.resource_views(resource)}
    result = {}
    for formation in book.formations:
        flags = struct.unpack_from("<I", body, ip.FORMATION_BASE + formation.index * ip.FORMATION_SIZE + 4)[0]
        if (flags >> 8) & 63 >= 4:
            continue
        gun = flags & 0xC0000 == 0x80000
        for link in formation.play_links:
            play = book.plays[link.play_index]
            if play.family_id != 0 or play.index > 255:
                continue
            # Native assignment family bits: designed run 0x8000, pass 0x2000.
            run, passed = bool(play.flags_or_id & 0x8000), bool(play.flags_or_id & 0x2000)
            if run == passed:
                continue
            view = views[formation.index, play.index]
            pa = passed and any(n.op == 0x14 for n in view.chains[0]) and any(n.op == 0x06 for n in view.chains[0])
            primary = lint.first_read_slot(view) if passed else None
            depth = (lint.route_end_depth(view.chains[primary], view.positions[primary][1])
                     if primary is not None else None)
            screen = passed and (lint.screen_receiver(view) is not None or
                                 ("screen" in play.name.casefold() and primary is not None and
                                  depth is not None and depth <= 2 * 91.44 and
                                  any(n.op == 0x12 and int(n.operands[0]) in (4, 5, 9, 10)
                                      for n in view.chains[primary])))
            location = lane = None
            handoffs = lint.handoff_pairs(view) if run else []
            carrier = (_slot_target(view, handoffs[0][1]) if len(handoffs) == 1
                       else _slot_target(view, lint.qb_slot(view)) if run else None)
            if len(handoffs) == 1:
                hole = handoffs[0][3]
                if 0 <= hole < len(codec.HANDOFF_HOLE_CM):
                    lane = RUN_LANES[HOLE_LANES[hole]]
                    location = lane.split("_")[0]
            result[formation.index, play.index] = Choice(formation.index, play.index, passed, gun,
                                                       formation.name.strip(), play.name.strip(), pa, screen,
                                                       False if screen else depth >= 20 * 91.44 if depth is not None else None,
                                                       location, run_lane=lane,
                                                       concept=diversity.play_family(play.name),
                                                       target=(_slot_target(view, primary) if passed else carrier) or "")
    require(result, "Compiled book has no byte-addressable offensive menu choices")
    normal = tuple(result.values())
    # 17F1D0 returns an unconditional flip for record bit0 with bit2 clear.
    # Native exclusion still compares only formation/play, so a ring must not
    # contain both orientations of the same pair to fake extra precision.
    return normal + tuple(replace(c, flipped=True, run_location="right" if c.run_location == "left" else "left",
                                  run_lane=RUN_LANES[4 - RUN_LANES.index(c.run_lane)],
                                  target=_mirror_target(c.target))
                          for c in normal if not c.passed and c.run_location in ("left", "right"))


def allocate_eight(probabilities: dict[str, float]) -> dict[str, int]:
    require(set(probabilities) == set(CATEGORIES), "Joint target must have four pass/shotgun categories")
    values = [probabilities[k] for k in CATEGORIES]
    require(all(type(x) in (float, int) and math.isfinite(x) and x >= 0 for x in values),
            "Joint probabilities must be finite and nonnegative")
    require(abs(sum(values) - 1) < 1e-8, "Joint probabilities must sum to one")
    counts = [math.floor(x * 8) for x in values]
    order = sorted(range(4), key=lambda i: (-(values[i] * 8 - counts[i]), i))
    for i in order[:8 - sum(counts)]:
        counts[i] += 1
    return dict(zip(CATEGORIES, counts))


def choice_metrics(selected):
    """Called-play proxies. Route target and planned hole are not game outcomes."""
    def observed(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None
    passes = [c for c in selected if c.passed]
    runs = [c for c in selected if not c.passed]
    return dict(play_action=observed([c.play_action for c in passes]),
                screen=observed([c.screen for c in passes]),
                deep_air20=observed([c.deep_primary for c in passes]),
                run_location={k: observed([c.run_location == k if c.run_location is not None else None for c in runs])
                              for k in ("left", "middle", "right")},
                run_gap={k: observed([c.run_gap == k if c.run_gap is not None else None for c in runs])
                         for k in ("guard", "tackle", "end")},
                run_lane={k: observed([c.run_lane == k if c.run_lane is not None else None for c in runs])
                          for k in RUN_LANES})


def feature_error(selected, targets):
    metrics = choice_metrics(selected)
    error = 0.0
    # Do not improve a fit by hiding calls whose planned geometry is unknown.
    error += sum((not c.passed and c.run_location is None) or
                 (c.passed and c.deep_primary is None) for c in selected) / len(selected)
    for feature in ("play_action", "screen", "deep_air20", "run_location", "run_lane"):
        actual = metrics[feature]
        expected = targets.get(feature, {})
        pairs = [(actual, expected.get("rate"))] if not isinstance(actual, dict) else [
            (value, expected.get(key, {}).get("rate")) for key, value in actual.items()]
        for value, goal in pairs:
            if goal is not None:
                error += 1.0 if value is None else (value - goal) ** 2
    return error


def make_pool(choices: tuple[Choice, ...], probabilities: dict[str, float], rotation: int = 0, feature_targets=None):
    counts = allocate_eight(probabilities)
    selected = []
    for category in CATEGORIES:
        options = [c for c in choices if c.category == category and not c.flipped]
        need = counts[category]
        require(len(options) >= need, f"Need {need} distinct {category} choices; compiled book has {len(options)}")
        if need:
            start = rotation % len(options)
            selected += (options + options)[start:start + need]
    require(len(selected) == 8 and len({(c.formation, c.play) for c in selected}) == 8,
            "Pool must have eight distinct formation/play pairs")
    if feature_targets:
        # Deterministic finite coordinate descent. Keep the pass/shotgun joint
        # counts exact while improving the charted secondary marginals.
        for _ in range(24):
            score = feature_error(selected, feature_targets)
            best = None
            for slot, current in enumerate(selected):
                used = {(c.formation, c.play) for i, c in enumerate(selected) if i != slot}
                for candidate in choices:
                    if candidate.category != current.category or (candidate.formation, candidate.play) in used:
                        continue
                    trial = selected[:slot] + [candidate] + selected[slot + 1:]
                    cost = feature_error(trial, feature_targets)
                    if cost < score - 1e-12:
                        score, best = cost, (slot, candidate)
            if best is None:
                break
            selected[best[0]] = best[1]
    row = bytearray(POOL_SIZE)
    row[:2] = bytes((1, 0))  # full ring; cursor slot zero is excluded by native playback
    for index, choice in enumerate(selected, 1):
        start = 2 + index * RECORD_SIZE
        row[start] = int(choice.flipped)
        row[start + 7] = choice.formation
        row[start + 8] = choice.play
    return bytes(row), selected, counts


FEATURE_KEYS = (("play_action", None), ("screen", None), ("deep_air20", None),
                ("run_location", "left"), ("run_location", "middle"), ("run_location", "right"),
                *(("run_lane", k) for k in RUN_LANES))


def _feature_targets(summary):
    return [summary.get(k, {}).get(sub, {}).get("rate") if sub else summary.get(k, {}).get("rate")
            for k, sub in FEATURE_KEYS]


def _feature_terms(choice):
    values = [choice.play_action if choice.passed else None, choice.screen if choice.passed else None,
              choice.deep_primary if choice.passed else None]
    values += [choice.run_location == k if not choice.passed and choice.run_location is not None else None
               for k in ("left", "middle", "right")]
    values += [choice.run_lane == k if not choice.passed and choice.run_lane is not None else None
               for k in RUN_LANES]
    return [float(v) if v is not None else 0.0 for v in values] + [float(v is not None) for v in values]


def fit_secondary_history(pools, choices, overall, *, stance_slack=0.125, variety=None, sweeps=12):
    """Fit the observed pool-weighted marginal as well as each small ring.

    Otherwise a 7% screen target rounds to zero in nearly every four-pass
    ring. The global term distributes such calls across the twenty contexts;
    Pass counts and distinct-pair constraints remain fixed. A stance change
    may move shotgun at most one eighth from the observed target, with a
    penalty for the complete pass/shotgun joint error. This lets inside runs
    use under-center calls when a gun menu has no inside-lane choice.

    ``variety`` (b776 pb2) is None for the fit alone, or ``dict(spec=, lam=, penalty=)``: the same descent then
    minimizes fit objective + lam * ring variety cost (``nfl2k5_coach_diversity``), keeping every pool's category
    counts, so only secondary features can move. ``sweeps=0`` just measures. The result carries ``objective``.
    """
    target = _feature_targets(overall)
    weights = [p["target"].get("observations", {}).get("calls", 0) for p in pools]
    total = sum(weights)
    if not total or all(v is None for v in target):
        return None
    weights = [v / total for v in weights]
    selected = [[Choice(**c) for c in p["choices"]] for p in pools]
    terms = {c: _feature_terms(c) for c in choices}
    unknown = {c: int((not c.passed and c.run_location is None) or
                     (c.passed and c.deep_primary is None)) for c in choices}
    size = len(FEATURE_KEYS)
    sums = [[sum(terms[c][k] for c in calls) for k in range(2 * size)] for calls in selected]
    unknowns = [sum(unknown[c] for c in calls) for calls in selected]
    targets = [_feature_targets(p["secondary_targets"]) for p in pools]
    joints = [[p["target"]["joint"][k] for k in CATEGORIES] for p in pools]
    category_index = {k: i for i, k in enumerate(CATEGORIES)}
    joint_counts = [[sum(c.category == k for c in calls) for k in CATEGORIES] for calls in selected]
    joint_loss = lambda counts, target: sum((n / 8 - t) ** 2 for n, t in zip(counts, target))
    joint_errors = [joint_loss(counts, target) for counts, target in zip(joint_counts, joints)]
    aggregate = [sum(weight * row[k] for weight, row in zip(weights, sums)) for k in range(2 * size)]
    def loss(row, expected):
        return sum((row[k] / row[k + size] - value) ** 2 if row[k + size] else 1.0
                   for k, value in enumerate(expected) if value is not None)
    errors = [loss(row, expected) for row, expected in zip(sums, targets)]
    global_error = loss(aggregate, target)
    ring_state = lam = None
    if variety:
        ring_state = diversity.RingSet(selected, variety["spec"], variety.get("penalty"))
        lam = variety["lam"]
    for _ in range(sweeps):
        improved = False
        for index, calls in enumerate(selected):
            weight = weights[index]
            if not weight:
                continue
            for slot, current in enumerate(calls):
                used = {(c.formation, c.play) for i, c in enumerate(calls) if i != slot}
                best, best_delta = None, 0.0
                for candidate in choices:
                    if candidate.passed != current.passed or (candidate.formation, candidate.play) in used:
                        continue
                    if ring_state is not None and candidate.category != current.category:
                        continue
                    counts = list(joint_counts[index])
                    counts[category_index[current.category]] -= 1
                    counts[category_index[candidate.category]] += 1
                    gun = (counts[1] + counts[3]) / 8
                    if abs(gun - joints[index][1] - joints[index][3]) > stance_slack + 1e-12:
                        continue
                    joint_cost = joint_loss(counts, joints[index])
                    delta = [a - b for a, b in zip(terms[candidate], terms[current])]
                    new_sum = [a + b for a, b in zip(sums[index], delta)]
                    new_global = [a + weight * b for a, b in zip(aggregate, delta)]
                    local_error, global_cost = loss(new_sum, targets[index]), loss(new_global, target)
                    change = weight * (local_error - errors[index] + (unknown[candidate] - unknown[current]) / 8)
                    change += 4 * (global_cost - global_error)
                    change += 4 * weight * (joint_cost - joint_errors[index])
                    if ring_state is not None:
                        change += lam * ring_state.delta(index, current, candidate)
                    if change < best_delta - 1e-12:
                        best_delta, best = change, (candidate, new_sum, new_global, local_error, global_cost, counts, joint_cost)
                if best is not None:
                    candidate, sums[index], aggregate, errors[index], global_error, joint_counts[index], joint_errors[index] = best
                    if ring_state is not None:
                        ring_state.replace(index, slot, candidate)
                    calls[slot] = candidate
                    unknowns[index] += unknown[candidate] - unknown[current]
                    improved = True
        if not improved:
            break
    for pool, calls in zip(pools, selected):
        pool["choices"] = [vars(c) for c in calls]
        pool["secondary_quantized"] = choice_metrics(calls)
        pool["counts"] = {k: sum(c.category == k for c in calls) for k in CATEGORIES}
        pool["quantized_pass"] = sum(c.passed for c in calls) / 8
        pool["quantized_shotgun"] = sum(c.shotgun for c in calls) / 8
    return dict(weight_basis="Observed coach call counts in each projected native pool",
                objective="pool marginal error + 4 * overall marginal error + 4 * pool pass/shotgun joint error; unknown-call penalty",
                constraints=dict(pass_counts="fixed", distinct_pairs=8, shotgun_absolute_target_slack=stance_slack),
                objective_value=sum(w * (e + u / 8 + 4 * j) for w, e, u, j in zip(weights, errors, unknowns, joint_errors))
                + 4 * global_error,
                features=[dict(feature=k, part=sub, target=value,
                               modeled=aggregate[i] / aggregate[i + size] if aggregate[i + size] else None)
                          for i, ((k, sub), value) in enumerate(zip(FEATURE_KEYS, target))])


def fit_class(choice: Choice):
    """Everything the charted fit and each pool's joint can see. Same class means same fit contribution, exactly."""
    return (choice.category, tuple(_feature_terms(choice)))


def _feature_distance(a, b):
    return sum(x != y for x, y in zip(_feature_terms(a), _feature_terms(b)))


def _family(choice):
    return choice.concept or diversity.play_family(choice.play_name)


# Relaxation of the exact-class rule, tried from the largest variety weight down; the first that keeps the fit within
# tolerance is used. Tolerances are on what the charts measure: the pool-weighted marginal of every secondary feature
# (percentage points) and the fit objective (its own units; see fit_secondary_history).
RELAX_LAMBDAS = (3e-4, 1e-4, 3e-5)
RELAX_FEATURE_TOLERANCE = 0.01
RELAX_OBJECTIVE_TOLERANCE = 0.002


def _relax(pools, choices, overall, weights, penalty):
    """Variety/fit trade that keeps pass/run, stance and every pool's category counts and moves secondary features
    only within tolerance. Returns a report; ``pools`` is updated only when a weight is accepted."""
    base = fit_secondary_history(copy.deepcopy(pools), choices, overall, sweeps=0)
    if base is None:
        return dict(status="skipped", reason="no charted secondary targets to hold within tolerance")
    tries = []
    for lam in RELAX_LAMBDAS:
        trial = copy.deepcopy(pools)
        fit = fit_secondary_history(trial, choices, overall, variety=dict(
            spec=diversity.offense_spec(weights), lam=lam, penalty=penalty), sweeps=30)
        drift = max((abs(a["modeled"] - b["modeled"]) for a, b in zip(fit["features"], base["features"])
                     if a["modeled"] is not None and b["modeled"] is not None), default=0.0)
        rise = fit["objective_value"] - base["objective_value"]
        ok = drift <= RELAX_FEATURE_TOLERANCE and rise <= RELAX_OBJECTIVE_TOLERANCE
        tries.append(dict(lam=lam, max_feature_drift=round(drift, 5), objective_rise=round(rise, 6), accepted=ok))
        if ok:
            for pool, done in zip(pools, trial):
                pool.update({k: done[k] for k in ("choices", "secondary_quantized", "counts", "quantized_pass",
                                                  "quantized_shotgun")})
            return dict(status="applied", lam=lam, objective_before=base["objective_value"],
                        objective_after=fit["objective_value"], tries=tries,
                        tolerance=dict(feature=RELAX_FEATURE_TOLERANCE, objective=RELAX_OBJECTIVE_TOLERANCE))
    return dict(status="none_within_tolerance", tries=tries, objective_before=base["objective_value"])


def diversify_pools(pools, choices, overall=None, weights=diversity.DEFAULT_WEIGHTS, relax=True):
    """Spread the eight-member rings over the callable menu while holding the charted marginals.

    Step 1 swaps members only for members of the same ``fit_class`` (same pass/run, stance, play action, screen, deep
    and run lane/location), so the pool's joint and every secondary marginal are unchanged to the bit (re-verified
    below). Step 2 (``relax`` and ``overall`` given) lets the fit descent trade secondary features for variety inside
    the stated tolerance. Both are deterministic descents on ``nfl2k5_coach_diversity``: no repeated (formation,
    family) pair, at most one screen of a family and two per ring, no Hail Mary-type play outside a late
    trailing pool, few repeated families/formations/targets per ring and few repeats of one play, family or
    formation across the pools. Rings are finally laid out so look-alikes are never neighbours.
    """
    penalty = diversity.situational_penalty(weights)
    spec = diversity.offense_spec(weights)

    def exact():
        rings = [[Choice(**c) for c in pool["choices"]] for pool in pools]
        fits = [(choice_metrics(r), sorted(c.category for c in r)) for r in rings]
        stats = diversity.improve(rings, choices, spec, fit_class=fit_class, penalty=penalty,
                                  escape=(lambda c: (c.category, c.screen), _feature_distance))
        # Pools listed in escaped_pools lost a Hail Mary-type play they may not hold and had no same-class
        # replacement; every other pool must be unchanged to the bit.
        require(all(choice_metrics(r) == m and sorted(c.category for c in r) == k for i, (r, (m, k))
                    in enumerate(zip(rings, fits)) if i not in stats["escaped_pools"])
                and all(len({(c.formation, c.play) for c in r}) == len(r) for r in rings),
                "Variety pass changed a charted marginal")
        for pool, ring in zip(pools, rings):
            pool["choices"] = [vars(c) for c in ring]
        return stats

    rings = [[Choice(**c) for c in pool["choices"]] for pool in pools]
    before = [diversity.ring_metrics(r) for r in rings]
    spread_before = diversity.pool_metrics(rings)
    fit_before = fit_secondary_history(copy.deepcopy(pools), choices, overall, sweeps=0) if overall else None
    stats = exact()
    relaxed = _relax(pools, choices, overall, weights, penalty) if relax and overall else None
    if relaxed and relaxed["status"] == "applied":
        stats = dict(stats, relaxed_then=exact())
    rings = [diversity.order_ring([Choice(**c) for c in pool["choices"]], _family, lambda c: c.screen)
             for pool in pools]
    after = [diversity.ring_metrics(r) for r in rings]
    state = diversity.RingSet(rings, spec, penalty)
    for pool, ring, was, now in zip(pools, rings, before, after):
        pool["choices"] = [vars(c) for c in ring]
        pool["secondary_quantized"] = choice_metrics(ring)
        pool["diversity"] = dict(before=was, after=now)
    fit_after = fit_secondary_history(copy.deepcopy(pools), choices, overall, sweeps=0) if overall else None
    fit = None
    if fit_before and fit_after:
        drift = [dict(feature=a["feature"], part=a["part"], target=a["target"], before=b["modeled"],
                      after=a["modeled"]) for a, b in zip(fit_after["features"], fit_before["features"])]
        fit = dict(objective_before=fit_before["objective_value"], objective_after=fit_after["objective_value"],
                   max_feature_drift=max((abs(d["after"] - d["before"]) for d in drift
                                          if d["after"] is not None and d["before"] is not None), default=0.0),
                   features=drift)
    return dict(schema=diversity.SCHEMA, weights=vars(weights), improve=stats, relaxation=relaxed, fit=fit,
                hard_violations=state.hard_violations(), pools_before=before, pools_after=after,
                spread_before=spread_before, spread_after=diversity.pool_metrics(rings))


def build_offense(template: VipSave, resource: bytes, tendency: dict, name: str, book_index: int, *,
                  varied: bool = True):
    """Return an experimental candidate and a byte-scope receipt, never write input."""
    require(type(book_index) is int and 0 <= book_index < 36, "Unsupported native book-label index")
    encoded = name.encode("utf-16le")
    require(name and "\0" not in name and len(encoded) <= 24, "Profile name must fit twelve UTF-16 units")
    save_container_id(name)  # The external SaveMeta name must be one line.
    require(tendency.get("schema") == "nfl2k5_coach_tendencies/v1", "Unknown tendency schema")
    targets = tendency.get("native_offense_pools", [])
    require(len(targets) == POOLS, "Exactly twenty offensive targets are required")
    choices = choices_from_book(resource)
    data = bytearray(template.payload)
    book_hash = hashlib.sha256(resource).hexdigest()
    identity = int.from_bytes(hashlib.sha256((tendency["team"] + name + book_hash).encode()).digest()[:4], "little") or 1
    if identity == struct.unpack_from("<I", template.payload)[0]:
        identity = identity % 0xFFFFFFFF + 1
    struct.pack_into("<I", data, 0, identity)
    data[4:30] = encoded + bytes(26 - len(encoded))
    struct.pack_into("<i", data, CONTEXT + 0x34, book_index)
    # Suppress the template's Coach's Pick fallback lottery for these pools.
    struct.pack_into("<HH", data, CONTEXT + 0xDF6, 1, 0)
    # Native 17E9FD also uses DF6 as the audible denominator, with E02 as
    # numerator. Retaining a personal template's numerator after setting DF6
    # to one makes every eligible snap audible away from the authored play.
    # PBP does not measure audibles, so neutralize this mapped counter.
    struct.pack_into("<H", data, CONTEXT + 0xE02, 0)
    pool_receipts = []
    for i, target in enumerate(targets):
        require(target.get("index") == i, "Pool indices must be ordered 0..19")
        observed = target.get("observations", {})
        feature_targets = {}
        for feature in ("play_action", "screen", "deep_air20", "run_location", "run_lane"):
            candidate = observed.get(feature, {})
            denominator = (sum(v.get("numerator", 0) or 0 for v in candidate.values())
                           if feature in ("run_location", "run_lane") else candidate.get("denominator", 0))
            feature_targets[feature] = candidate if denominator >= 32 and not target.get("fallback") else tendency.get("overall", {}).get(feature, {})
        row, selected, counts = make_pool(choices, target["joint"], i * 7, feature_targets)
        start = CONTEXT + OFFENSE + i * POOL_SIZE
        data[start:start + POOL_SIZE] = row
        pool_receipts.append(dict(index=i, target=target, counts=counts,
                                  choices=[vars(c) for c in selected],
                                  secondary_targets=feature_targets, secondary_quantized=choice_metrics(selected),
                                  quantized_pass=sum(c.passed for c in selected) / 8,
                                  quantized_shotgun=sum(c.shotgun for c in selected) / 8))
    secondary_fit = fit_secondary_history(pool_receipts, choices, tendency.get("overall", {}))
    weights = varied if isinstance(varied, diversity.Weights) else diversity.DEFAULT_WEIGHTS
    variety = diversify_pools(pool_receipts, choices, tendency.get("overall", {}), weights) if varied else None
    if secondary_fit or variety:
        for pool in pool_receipts:
            start = CONTEXT + OFFENSE + pool["index"] * POOL_SIZE
            for index, choice in enumerate(pool["choices"], 1):
                data[start + 2 + index * RECORD_SIZE] = int(choice["flipped"])
                data[start + 2 + index * RECORD_SIZE + 7] = choice["formation"]
                data[start + 2 + index * RECORD_SIZE + 8] = choice["play"]
    spans = ((0, 30), (CONTEXT + 0x34, 4), (CONTEXT + OFFENSE, POOLS * POOL_SIZE),
             (CONTEXT + 0xDF6, 4), (CONTEXT + 0xE02, 2))
    changed = [i for i, (a, b) in enumerate(zip(template.payload, data)) if a != b]
    require(all(any(start <= i < start + length for start, length in spans) for i in changed), "Edit escaped byte scope")
    result = VipSave.decode(bytes(data))
    receipt = dict(schema=SCHEMA, status="EXPERIMENTAL_OFFENSE_ONLY", team=tendency["team"],
                   coach=tendency["coach"], name=name, book_index=book_index, book_sha256=book_hash,
                   template_sha256=hashlib.sha256(template.payload).hexdigest(),
                   save_sha256=hashlib.sha256(result.payload).hexdigest(),
                   allowed_spans=[dict(offset=a, size=n) for a, n in spans], changed_bytes=len(changed),
                   pools=pool_receipts, attachment="manual Quick Game VIP Coaches; unpaired exact book only",
                   secondary_fit=secondary_fit, variety=variety,
                   portrait="vip_logo_a1", native_replay_verified=False,
                   audible_policy="Disabled: unmeasured template numerator cleared because Coach's Pick shares its denominator",
                   preserved_template_features=["defense", "no_huddle_and_timing", "fourth_down", "two_point", "onside", "Crib", "preferences", "statistics"],
                   secondary_mapping="PA fake/throw chain, screen assignment, first-read endpoint; native 281300 five run lanes with NFL guard/tackle collapsed to inside; exact gaps remain unsupported",
                   unsupported_target_mappings=["actual_throw_depth", "actual_run_gap_after_snap", "defensive_calls"])
    receipt["compiled_availability"] = dict(
        pass_choices=sum(c.passed and not c.flipped for c in choices),
        play_action=sum(c.play_action for c in choices), screens=sum(c.screen for c in choices),
        run_lanes={lane: sum(c.run_lane == lane for c in choices) for lane in RUN_LANES})
    receipt["unrepresented_observed_features"] = [
        dict(feature=key, target=tendency.get("overall", {}).get(key, {}).get("rate"),
             reason="No matching callable assignment in the exact compiled book")
        for key, field in (("screen", "screen"), ("play_action", "play_action"))
        if (tendency.get("overall", {}).get(key, {}).get("rate") or 0) > 0 and not any(getattr(c, field) for c in choices)]
    return result, receipt


@dataclass(frozen=True)
class DefenseChoice:
    formation: int
    front: int
    coverage: int
    man: bool
    rushers: int
    formation_name: str
    front_name: str
    coverage_name: str


def vip_defense_formations(book, body):
    """Formations reachable by native VIP menu navigation, ADFC0/E10D0.

    The menu visits the first matching formation in each defensive personnel
    category. A later formation sharing that category can be callable by the
    low-level selector yet unreachable by VIP playback's menu navigation.
    Mirror E0BF0 membership and E1060's first-category fallback here; no native
    execution dependency is needed by the compiler.
    """
    flags = {c.index: body[ip.CATEGORY_BASE + c.index * ip.CATEGORY_SIZE + 4]
             for c in book.categories}
    first = {}
    for index, value in flags.items():
        first.setdefault(value & 63, index)
    reachable = set()
    # Native defensive menu filter at 510304; 25 terminates the list.
    for index, value in flags.items():
        code = value & 63
        if code not in (13, 14, 15, 12, 11, 16, 18, 20):
            continue
        for formation in book.formations:
            aux = ip.FORMATION_AUX_BASE + formation.index * ip.FORMATION_AUX_SIZE
            own, membership = struct.unpack_from("<II", body, aux + 0x48)
            own_flags = flags.get(own & 63, 0)
            fallback = (index == first[code] and own_flags & 0xC0 == 0x40
                        and own_flags & 63 == code)
            if membership & (1 << index) or fallback:
                reachable.add(formation.index)
                break
    return reachable


def defense_choices_from_book(resource):
    """Use executable assignments; imported labels and header bits can disagree."""
    book = ip.parse_playbook_resource(resource)
    body = resource[32:]
    reachable = vip_defense_formations(book, body)
    result = []
    for formation in book.formations:
        if (formation.index not in reachable or
                library.formation_record(body, formation.index).type_code not in (5, 6)):
            continue
        used = set()
        for front, cover in library.defense_pairs(book, body, formation.index):
            if front > 255 or cover > 255 or cover in used:
                continue
            used.add(cover)
            chains = library.effective_defense(library.decoded_chains(body, front),
                                                library.decoded_chains(body, cover))
            assignments = [next((n[0] for n in chain if n[0] in (0x0B, 0x0D, 0x0E)), None) for chain in chains]
            result.append(DefenseChoice(formation.index, front, cover, assignments.count(0x0E) >= 4,
                                        assignments.count(0x0B), formation.name.strip(),
                                        book.plays[front].name.strip(), book.plays[cover].name.strip()))
    require(len(result) >= 4, "Compiled book has too few byte-addressable split defensive calls")
    return tuple(result)


def defense_metrics(selected):
    return dict(man=sum(c.man for c in selected) / len(selected),
                rush_five_plus=sum(c.rushers >= 5 for c in selected) / len(selected))


def defense_row(selected):
    row = bytearray(62)
    row[:2] = bytes((1, 0))
    for index, choice in enumerate(selected, 1):
        start = 2 + index * 12
        row[start + 3:start + 6] = bytes((choice.formation, choice.front, choice.coverage))
    return bytes(row)


def make_defense_pool(choices, target, rotation):
    selected = [(choices + choices)[rotation % len(choices) + i] for i in range(4)]
    def error(calls):
        metrics = defense_metrics(calls)
        return sum((metrics[k] - target[k]["rate"]) ** 2 for k in metrics
                   if target.get(k, {}).get("rate") is not None)
    for _ in range(8):
        score, best = error(selected), None
        for slot in range(4):
            used = {(c.formation, c.coverage) for i, c in enumerate(selected) if i != slot}
            for candidate in choices:
                if (candidate.formation, candidate.coverage) in used:
                    continue
                trial = selected[:slot] + [candidate] + selected[slot + 1:]
                cost = error(trial)
                if cost < score - 1e-12:
                    score, best = cost, (slot, candidate)
        if best is None:
            break
        selected[best[0]] = best[1]
    return defense_row(selected), selected


def defense_fit_class(choice):
    return (choice.man, choice.rushers >= 5)


def diversify_defense(rings, choices, weights=diversity.DEFAULT_WEIGHTS):
    """Same idea for the four-record defensive rings: swap within the (man, five-plus rushers) class, so the
    charted man and pressure rates of every ring are unchanged to the bit, to spread formations, fronts and
    coverages inside a ring and across the fifteen situation pools."""
    metrics = [defense_metrics(r) for r in rings]
    before = [dict(formations=len({c.formation for c in r}), fronts=len({c.front for c in r}),
                   coverages=len({c.coverage for c in r})) for r in rings]
    spread = lambda rs: dict(distinct_triples=len({(c.formation, c.front, c.coverage) for r in rs for c in r}),
                             distinct_formations=len({c.formation for r in rs for c in r}),
                             distinct_fronts=len({c.front for r in rs for c in r}),
                             distinct_coverages=len({c.coverage for r in rs for c in r}))
    spread_before = spread(rings)
    stats = diversity.improve(rings, choices, diversity.defense_spec(weights), fit_class=defense_fit_class,
                              identity=lambda c: (c.formation, c.coverage))
    for index, ring in enumerate(rings):
        rings[index] = diversity.order_ring(ring, lambda c: (c.formation, c.front))
    require(all(defense_metrics(r) == m for r, m in zip(rings, metrics)), "Variety pass changed a defensive rate")
    after = [dict(formations=len({c.formation for c in r}), fronts=len({c.front for c in r}),
                  coverages=len({c.coverage for c in r})) for r in rings]
    return dict(schema=diversity.SCHEMA, rule="swap only within the (man, five-plus rushers) class",
                improve=stats, pools_before=before, pools_after=after,
                spread_before=spread_before, spread_after=spread(rings))


def build_coach(template: VipSave, resource: bytes, tendency: dict, name: str, book_index: int, *,
                varied: bool = True):
    """Coach-derived offense history plus measured defensive pressure/coverage.

    The fifteen defensive contexts currently share the observed coach marginal;
    no unsupported situation or formation-conditioned charting is invented.
    """
    offense, receipt = build_offense(template, resource, tendency, name, book_index, varied=varied)
    data = bytearray(offense.payload)
    choices = defense_choices_from_book(resource)
    target = tendency.get("defense", {})
    require(target.get("rush_five_plus", {}).get("rate") is not None,
            "Defensive history requires charted pass-rusher counts")
    for key in ("man", "rush_five_plus"):
        value = target.get(key, {}).get("rate")
        require(value is None or type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
                f"Invalid defensive {key} rate")
    defense, rings = [], []
    for index in range(15):
        row, selected = make_defense_pool(choices, target, index * 7)
        rings.append(selected)
    defense_variety = (diversify_defense(rings, choices, varied if isinstance(varied, diversity.Weights)
                                         else diversity.DEFAULT_WEIGHTS) if varied else None)
    for index, selected in enumerate(rings):
        start = CONTEXT + 0xA3C + index * 62
        data[start:start + 62] = defense_row(selected)
        defense.append(dict(index=index, choices=[vars(c) for c in selected],
                            quantized=defense_metrics(selected),
                            targets={k: target.get(k) for k in ("man", "rush_five_plus")},
                            formation_scope="native_vip_menu_reachable",
                            situation_fallback="coach_overall_charted_pass_defense"))
    struct.pack_into("<HH", data, CONTEXT + 0xDFA, 1, 0)
    receipt["allowed_spans"] += [dict(offset=CONTEXT + 0xA3C, size=15 * 62), dict(offset=CONTEXT + 0xDFA, size=4)]
    statistics = tendency.get("native_statistics")
    if statistics:
        def pair(offset, numerator, denominator):
            require(type(numerator) is int and type(denominator) is int and 0 <= numerator <= denominator,
                    "Invalid observed statistics")
            scale = min(1, 65535 / denominator) if denominator else 1
            struct.pack_into("<HH", data, CONTEXT + 0x20B8 + offset,
                             round(denominator * scale), round(numerator * scale))
        passes, runs = statistics["pass_calls"], statistics["run_calls"]
        require(type(passes) is int and type(runs) is int and min(passes, runs) >= 0, "Invalid call counts")
        scale = min(1, 65535 / max(passes, runs)) if max(passes, runs) else 1
        struct.pack_into("<HH", data, CONTEXT + 0x20B8, round(passes * scale), round(runs * scale))
        require(len(statistics["score"]) == 6 and len(statistics["down_distance"]) == 16, "Invalid native statistic rows")
        for index, row in enumerate(statistics["score"]):
            pair(4 + 4 * index, row["numerator"], row["denominator"])
        row = statistics["redzone"]
        pair(0x1C, row["numerator"], row["denominator"])
        for index, row in enumerate(statistics["down_distance"]):
            pair(0x20 + 4 * index, row["numerator"], row["denominator"])
        receipt["allowed_spans"].append(dict(offset=CONTEXT + 0x20B8, size=0x60))
        receipt["native_statistics"] = statistics
        receipt["preserved_template_features"].remove("statistics")
        receipt["preserved_template_features"].append("unmapped_statistics")
    decisions = {}
    projections = tendency.get("native_decision_projections", {})
    for key, offset in (("fourth_down", 0xE94), ("two_point", 0xE90), ("no_huddle", 0x20B8 + 0xCE)):
        target = projections.get(key, {})
        probability = target.get("rate")
        fallback = None
        if probability is None and key in ("fourth_down", "two_point"):
            target = tendency.get(key, {})
            probability = target.get("rate")
            fallback = "coach_all_decisions_no_projected_observations"
        if probability is None:
            decisions[key] = dict(written=False, reason="No observations; template preserved")
            continue
        require(math.isfinite(probability) and 0 <= probability <= 1, f"Invalid {key} target")
        denominator = 10000
        roll = probability
        if key == "no_huddle":
            # 281800 starts a run of 1 + uniform(2,4) hurry-up calls. In a
            # continuously eligible stream r = 4p/(1+3p), so p = r/(4-3r).
            roll = probability / (4 - 3 * probability)
            numerator = min(denominator, round(roll * (denominator + 1)))
            native_roll = numerator / (denominator + 1)
            effective = 4 * native_roll / (1 + 3 * native_roll)
        else:
            numerator = round(roll * denominator)
            native_roll = effective = numerator / denominator
        struct.pack_into("<HH", data, CONTEXT + offset, denominator, numerator)
        receipt["allowed_spans"].append(dict(offset=CONTEXT + offset, size=4))
        decisions[key] = dict(written=True, observations=target, fallback=fallback,
                              projection_scope=projections.get(key + "_scope"), offset=CONTEXT + offset,
                              denominator=denominator, numerator=numerator, native_roll=native_roll,
                              continuous_eligible_rate=effective,
                              scope="Conditional native policy; not an unconditional full-game frequency")
    struct.pack_into("<I", data, 0, coach_identity(tendency["team"], name))
    receipt.update(schema="nfl2k5_coach_vip/v1", status="EXPERIMENTAL_NATIVE_VIP_CANDIDATE", defense_pools=defense,
                   defense_variety=defense_variety,
                   identity_scheme="stable_team_and_profile_name_v2",
                   decisions=decisions,
                   defense_mapping="Five-plus first-assignment rushers and four-plus man assignments in the effective front/coverage union; call proxies, not post-snap outcomes",
                   changed_bytes=sum(a != b for a, b in zip(template.payload, data)),
                   save_sha256=hashlib.sha256(data).hexdigest())
    receipt["preserved_template_features"].remove("defense")
    for key in ("fourth_down", "two_point", "no_huddle"):
        if decisions.get(key, {}).get("written"):
            old = "no_huddle_and_timing" if key == "no_huddle" else key
            receipt["preserved_template_features"].remove(old)
            if key == "no_huddle":
                receipt["preserved_template_features"].append("snap_and_playcall_timing")
    receipt["unsupported_target_mappings"].remove("defensive_calls")
    receipt["unsupported_target_mappings"] += ["exact_coverage_family", "defensive_situation_conditional_rates"]
    result = VipSave.decode(data)
    allowed = receipt["allowed_spans"]
    require(all(a == b or any(s["offset"] <= i < s["offset"] + s["size"] for s in allowed)
                for i, (a, b) in enumerate(zip(template.payload, data))), "Coach edit escaped byte scope")
    return result, receipt


def load_signed(folder: Path, xbe: bytes) -> VipSave:
    require((folder / "TYPE").read_bytes() == b"U\0S\0R\0\0\0", "Save TYPE is not USR")
    payload, extra = (folder / "SAVEGAME.DAT").read_bytes(), (folder / "EXTRA").read_bytes()
    require(verify_extra(derive_sig_key(xbe), payload, extra), "USR EXTRA signature does not verify")
    return VipSave.decode(payload)


def executable_compatibility(xbe: bytes) -> dict:
    """Refuse known native policy conflicts before exporting decision counters."""
    from . import nfl2k5_cpu_money_downs as money
    from . import nfl2k5_playbook_pair as pair
    policy, pairing = money.status(xbe), pair.status(xbe)
    require(policy != "foreign" and pairing != "foreign", "Unrecognized CPU-policy or playbook-pair executable")
    settings = money.read_settings(xbe)
    require(settings is None or settings.get("vip_policy"),
            "Installed CPU policy overrides VIP decisions; use Retail or upgrade a copy to VIP-aware Modern 2")
    return dict(xbe_sha256=hashlib.sha256(xbe).hexdigest(), cpu_policy=settings or {"level": "retail"},
                playbook_pair=pairing, requirement="Same offense/defense book; paired sides bypass VIP playback")


def write_signed(folder: Path, value: VipSave, xbe: bytes) -> None:
    """Fresh directory only. Caller supplies template and executable locally."""
    folder.mkdir(parents=False, exist_ok=False)
    key = derive_sig_key(xbe)
    extra = sign_save(key, value.payload)
    files = {"SAVEGAME.DAT": value.payload, "EXTRA": extra, "TYPE": b"U\0S\0R\0\0\0",
             "SaveMeta.xbx": b"\xff\xfe" + ("Name=" + value.name + "\r\n").encode("utf-16le")}
    for name, content in files.items():
        with (folder / name).open("xb") as handle:
            handle.write(content)
    require(load_signed(folder, xbe).payload == value.payload, "Written USR did not verify")
