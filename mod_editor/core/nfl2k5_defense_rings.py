"""Situational, team-specific CPU defensive rings for the automatic coach profile (b779 dp1).

Why.  In a SOFTDRINK build (``coach_ai`` on) every CPU defensive call of a current-NFL team in Play Now, Season,
Franchise and the playoffs comes from the coach profile: native 0xF7450 picks ring ``bin * 5 + group`` (bin: down and
distance, short / medium / long, from 0xF7010; group: the offense's lined-up personnel, 0 not known yet, 1 heavy,
2 two receivers, 3 three receivers, 4 four or more) and 0x17DFC0 draws one of that ring's four (formation, front,
coverage) entries at random, never the one it called last.  The menu bands only matter on 4th down and when there is
no ring.  The beta-78 rings were fitted to ONE marginal (man rate, five-plus rushers) for all fifteen rings, over
type 5/6 formations only, so every 4-3 team called base, nickel and dime about a third of the time each on every
down against every personnel, and the five 3-4 books whose only type 5/6 formation is the Bear (BAL, HOU, NE, PIT,
SD) called the Bear 46 on every CPU snap.

What.  ``build`` fits each ring to that team's own 2025 snaps in that very cell (defensive personnel, coverage family,
man, five-plus rushers, simulated pressure), shrunk toward the league's rate in the cell where the team sample is
small, with the 2026 coordinator's baseline team (``data/vip/defense_identity_2026.json``,
``pb/research/make_defense_identity.py``), a whole-season term so the four-call quantization averages out across
rings, the coordinator's disguise share (a DESIGN knob: single-high calls shown from two-high before the snap), and
a variety term (no ring repeats a (formation, coverage) pair; a call is reused across rings only when it pays).
Three-down (type 4) formations are now eligible, so a 3-4 book's 3-4 / Nickel Okie / Dime Okie take part.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path

from . import nfl2k5_defense_calls as calls

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = ROOT / "data/vip/defense_identity_2026.json"
SCHEMA = "nfl2k5_defense_rings/v1"
PERS = ("base", "nickel", "dime")
FAMS = ("C0", "C1", "2M", "C2", "C3", "C4", "C6")
RING_TYPES = (4, 5, 6)          # three-down, four-down base and sub-package formations (goal line 7 / prevent excluded)
UNKNOWN_SHARE = 0.25            # DESIGN: weight of a not-yet-known-personnel ring against a known one in the season term
K_SNAPS, K_DROPBACKS = 12.0, 15.0
# Loss weights (DESIGN): personnel first (a dime defense against two backs is the worst miss), then blitz, coverage family.
W_PERS, W_FAM, W_MAN, W_BLITZ, W_SIM, W_DISGUISE = 4.0, 2.0, 2.0, 3.0, 1.0, 1.0
W_SEASON = 6.0
W_BIN = 3.0             # the same terms per down-and-distance bin (five rings each), so short / medium / long each land
W_REUSE, W_FRONT_REPEAT, W_PACKAGE = 0.004, 0.01, 0.003
BEAR_OUTSIDE_SHORT = 1.0


@lru_cache(maxsize=1)
def load_identity(path: str = str(IDENTITY)) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def team_identity(team: str) -> dict | None:
    """Identity row for a book team code (ARZ ... WAS), or None."""
    return load_identity()["teams"].get(team)


def _sum(cells: dict, keys) -> Counter:
    out = Counter()
    for k in keys:
        out.update(cells.get(k, {}))
    return out


def rates(c: Counter) -> dict:
    def r(num, den):
        return c[num] / c[den] if c[den] else 0.0
    out = {"p_" + p: r(p, "pers_known") for p in PERS}
    out.update({"f_" + f: r(f, "cov_known") for f in FAMS})
    out.update(man=r("man", "mz_known"), blitz=r("blitz", "rush_known"), sim=r("sim", "sim_known"),
               single=(c["C0"] + c["C1"] + c["C3"]) / c["cov_known"] if c["cov_known"] else 0.0)
    return {k: round(v, 4) for k, v in out.items()}


def real_rates(cells: dict, distance_bin: int | None = None) -> dict:
    keys = [k for k in cells if distance_bin is None or k[0] == str(distance_bin)]
    return rates(_sum(cells, keys))


def _shrunk(team: Counter, league: Counter) -> dict:
    """Cell targets: the team's counts with K pseudo-observations at the league's cell rate."""
    def mix(keys, den, k):
        lt = league[den] or 1
        return {x: (team[x] + k * league[x] / lt) / (team[den] + k) for x in keys}
    out = {"pers": mix(PERS, "pers_known", K_SNAPS), "fam": mix(FAMS, "cov_known", K_DROPBACKS)}
    for x, den in (("man", "mz_known"), ("blitz", "rush_known"), ("sim", "sim_known")):
        out[x] = mix((x,), den, K_DROPBACKS)[x]
    z = sum(out["pers"].values()) or 1
    out["pers"] = {k: v / z for k, v in out["pers"].items()}
    z = sum(out["fam"].values()) or 1
    out["fam"] = {k: v / z for k, v in out["fam"].items()}
    return out


def ring_targets(identity: dict, league_cells: dict) -> tuple[list[dict], list[float]]:
    """Fifteen ring targets (index bin * 5 + group) and their season weights."""
    cells = identity["cells"]
    targets, weights = [None] * 15, [0.0] * 15
    total = sum(c.get("snaps", 0) for c in cells.values()) or 1
    for b in range(3):
        known = []
        for g in range(1, 5):
            key = f"{b}{g}"
            t = _shrunk(Counter(cells.get(key, {})), Counter(league_cells.get(key, {})))
            w = cells.get(key, {}).get("snaps", 0) / total
            targets[b * 5 + g], weights[b * 5 + g] = t, w
            known.append((w, t))
        z = sum(w for w, _ in known) or 1
        blend = {"pers": Counter(), "fam": Counter(), "man": 0.0, "blitz": 0.0, "sim": 0.0}
        for w, t in known:
            for part in ("pers", "fam"):
                for k, v in t[part].items():
                    blend[part][k] += v * w / z
            for k in ("man", "blitz", "sim"):
                blend[k] += t[k] * w / z
        blend["pers"], blend["fam"] = dict(blend["pers"]), dict(blend["fam"])
        targets[b * 5] = blend
        weights[b * 5] = UNKNOWN_SHARE * z
    for t in targets:
        t["disguise"] = identity.get("disguise", 0.0)
    return targets, weights


def eligible(book, body, reachable, pairs_of) -> list[calls.Call]:
    """Every byte-addressable split call of the ring formations (indices <= 255, base / nickel / dime personnel)."""
    from . import nfl2k5_play_library as library
    out = []
    for formation in book.formations:
        if formation.index not in reachable or formation.index > 255:
            continue
        if library.formation_record(body, formation.index).type_code not in RING_TYPES:
            continue
        seen = set()
        for front, cover in pairs_of(book, body, formation.index):
            if front > 255 or cover > 255 or (front, cover) in seen:
                continue
            seen.add((front, cover))
            c = calls.classify(book, body, formation.index, front, cover)
            if c.personnel in PERS:
                out.append(c)
    return out


def _feat(c: calls.Call) -> dict:
    return dict(pers=c.personnel, fam=c.family, man=float(c.man), blitz=float(c.blitz), sim=float(c.sim),
                single=float(c.postsnap == "one"), disg=float(c.postsnap == "one" and c.presnap == "two"))


def _ring_loss(ring, t) -> float:
    n = len(ring)
    if not n:
        return 0.0
    pers, fam = Counter(f["pers"] for f in ring), Counter(f["fam"] for f in ring)
    loss = W_PERS * sum((pers[k] / n - t["pers"].get(k, 0)) ** 2 for k in PERS)
    loss += W_FAM * sum((fam[k] / n - t["fam"].get(k, 0)) ** 2 for k in set(FAMS) | set(fam))
    for k, w in (("man", W_MAN), ("blitz", W_BLITZ), ("sim", W_SIM)):
        loss += w * (sum(f[k] for f in ring) / n - t[k]) ** 2
    single = sum(f["single"] for f in ring)
    if single:
        loss += W_DISGUISE * (sum(f["disg"] for f in ring) / single - t["disguise"]) ** 2 * single / n
    return loss


def _season(rings, weights, feats):
    acc = Counter()
    z = 0.0
    for ring, w in zip(rings, weights):
        for i in ring:
            f = feats[i]
            acc["p_" + f["pers"]] += w / 4
            acc["f_" + f["fam"]] += w / 4
            for k in ("man", "blitz", "sim"):
                acc[k] += f[k] * w / 4
        z += w
    return {k: v / z for k, v in acc.items()} if z else {}


def _season_loss(model: dict, season: dict) -> float:
    loss = W_PERS * sum((model.get("p_" + k, 0) - season["pers"].get(k, 0)) ** 2 for k in PERS)
    loss += W_FAM * sum((model.get("f_" + k, 0) - season["fam"].get(k, 0)) ** 2 for k in FAMS)
    for k, w in (("man", W_MAN), ("blitz", W_BLITZ), ("sim", W_SIM)):
        loss += w * (model.get(k, 0) - season[k]) ** 2
    return W_SEASON * loss


def _season_target(targets, weights) -> dict:
    out = {"pers": Counter(), "fam": Counter(), "man": 0.0, "blitz": 0.0, "sim": 0.0}
    z = sum(weights) or 1
    for t, w in zip(targets, weights):
        for part in ("pers", "fam"):
            for k, v in t[part].items():
                out[part][k] += v * w / z
        for k in ("man", "blitz", "sim"):
            out[k] += t[k] * w / z
    return out


def _package_bonus(c: calls.Call, package) -> float:
    name = c.coverage_name.lower()
    words = []
    for p in package:
        p = p.lower()
        words += {"cover 0 blitz": ["cover 0", "zero"], "cover 1 blitz": ["fire", "cover 1"], "sim pressure": ["sim", "creeper"],
                  "fire zone 3": ["fire zone", "fire 3"], "cover 4 quarters": ["quarters", "cover 4"],
                  "2-read match": ["match", "palms"], "cover 2 invert": ["cover 2"], "mug pressure": ["mug"],
                  "qb spy": ["spy"]}.get(p, [p])
    return W_PACKAGE * sum(1 for w in set(words) if w in name)


def build(book, body, reachable, pairs_of, team: str) -> tuple[list[list[calls.Call]], dict] | None:
    """Fifteen rings of four calls for ``team`` (book code), or None when it has no identity row."""
    identity = team_identity(team)
    if identity is None:
        return None
    league = load_identity()["league_cells"]
    targets, weights = ring_targets(identity, league)
    season = _season_target(targets, weights)
    cands = eligible(book, body, reachable, pairs_of)
    if len({(c.formation, c.coverage) for c in cands}) < 4:
        raise ValueError(f"{team}: fewer than four distinct ring calls in the compiled book")
    feats = [_feat(c) for c in cands]
    package = identity.get("package", ())
    # The book's own front bands carry the coordinator's front style (pb/v2/defense/design.py FRONT_STYLE): prefer them.
    bonus = [_package_bonus(c, package) + W_PACKAGE * max(0, 2 - c.front_band) / 2 for c in cands]
    def bear_cost(i, p):
        return BEAR_OUTSIDE_SHORT if cands[i].bear and not (p // 5 == 0 and p % 5 in (0, 1, 2)) else 0.0
    rings: list[list[int]] = [[] for _ in range(15)]
    uses = Counter()

    def ring_cost(p, ring):
        fronts = Counter(cands[i].front for i in ring)
        return (weights[p] * _ring_loss([feats[i] for i in ring], targets[p])
                + W_FRONT_REPEAT * sum(v - 1 for v in fronts.values())
                + sum(bear_cost(i, p) - bonus[i] for i in ring))

    def reuse_cost():
        return W_REUSE * sum(v - 1 for v in uses.values() if v > 1)

    def key(i):
        return (cands[i].formation, cands[i].coverage)

    # Greedy start, heaviest rings first.
    for p in sorted(range(15), key=lambda p: (-weights[p], p)):
        for _ in range(4):
            taken = {key(i) for i in rings[p]}
            best = None
            for i in range(len(cands)):
                if key(i) in taken:
                    continue
                trial = rings[p] + [i]
                score = ring_cost(p, trial) + W_REUSE * uses[key(i)]
                if best is None or score < best[0] - 1e-12:
                    best = (score, i)
            rings[p].append(best[1])
            uses[key(best[1])] += 1

    zw = sum(weights) or 1.0
    zb = [sum(weights[b * 5:(b + 1) * 5]) or 1.0 for b in range(3)]
    bin_target = [_season_target(targets[b * 5:(b + 1) * 5], weights[b * 5:(b + 1) * 5]) for b in range(3)]
    acc = Counter()
    accb = [Counter() for _ in range(3)]

    def add(i, p, sign):
        f, w = feats[i], sign * weights[p] / 4
        for a, z in ((acc, zw), (accb[p // 5], zb[p // 5])):
            a["p_" + f["pers"]] += w / z
            a["f_" + f["fam"]] += w / z
            for k in ("man", "blitz", "sim"):
                a[k] += f[k] * w / z

    for p in range(15):
        for i in rings[p]:
            add(i, p, +1)
    costs = [ring_cost(p, rings[p]) for p in range(15)]
    bins_now = [W_BIN / W_SEASON * _season_loss(accb[b], bin_target[b]) for b in range(3)]
    season_now = _season_loss(acc, season)
    current = sum(costs) + reuse_cost() + season_now + sum(bins_now)
    for _sweep in range(6):
        improved = False
        for p in range(15):
            if weights[p] <= 0 and p % 5:
                continue
            b = p // 5
            for slot in range(4):
                old = rings[p][slot]
                taken = {key(i) for j, i in enumerate(rings[p]) if j != slot}
                base_now = season_now + bins_now[b]
                best = (0.0, old, costs[p], season_now, bins_now[b])
                add(old, p, -1)
                for i in range(len(cands)):
                    if i == old or key(i) in taken:
                        continue
                    rings[p][slot] = i
                    rc = ring_cost(p, rings[p])
                    add(i, p, +1)
                    sl = _season_loss(acc, season)
                    bl = W_BIN / W_SEASON * _season_loss(accb[b], bin_target[b])
                    add(i, p, -1)
                    reuse = W_REUSE * ((uses[key(i)] >= 1) - (uses[key(old)] >= 2))
                    delta = (rc - costs[p]) + (sl + bl - base_now) + reuse
                    if delta < best[0] - 1e-9:
                        best = (delta, i, rc, sl, bl)
                rings[p][slot] = best[1]
                add(best[1], p, +1)
                if best[1] != old:
                    uses[key(old)] -= 1
                    uses[key(best[1])] += 1
                    costs[p], season_now, bins_now[b] = best[2], best[3], best[4]
                    current += best[0]
                    improved = True
        if not improved:
            break
    model = _season(rings, weights, feats)
    chosen = [[cands[i] for i in ring] for ring in rings]
    receipt = dict(schema=SCHEMA, team=team, dc=identity["dc"], baseline_2025=identity["baseline_2025"],
                   disguise_target=identity.get("disguise"), candidates=len(cands),
                   loss=round(current, 6), season_model={k: round(v, 4) for k, v in sorted(model.items())},
                   season_target=dict(pers={k: round(v, 4) for k, v in season["pers"].items()},
                                      fam={k: round(v, 4) for k, v in season["fam"].items()},
                                      man=round(season["man"], 4), blitz=round(season["blitz"], 4),
                                      sim=round(season["sim"], 4)),
                   distinct_calls=len({(c.formation, c.front, c.coverage) for r in chosen for c in r}),
                   rings=[dict(index=p, bin=p // 5, group=p % 5, weight=round(weights[p], 4),
                               calls=[f"{c.formation_name} | {c.front_name} | {c.coverage_name}" for c in r])
                          for p, r in enumerate(chosen)])
    return chosen, receipt
