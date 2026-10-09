"""The retail 2004 reference the model maps onto, and how 2K built its physical ratings. PROVED OFFLINE.

  * tiers: the 32 NFL clubs of the retail ROST, each position pool split per team into starters (the top N by the
    game's own OVR without body terms, N = the 2026 base lineup) and backups; per pool, tier and rating the sorted
    retail values (the scale 2K tuned its engine on). LB = retail ILB + OLB, EDGE = retail DE.
  * physfit: retail speed / agility / jumping / strength of the players who ran the 2000+ combines (nflverse
    combine.csv, matched by name and draft year), least squares on their drills per position group.
  * age: 2K's own slope of each physical rating per year past 29 (position fixed effects from players <= 29).
  * impute: the combine population's own regressions to fill a drill a player skipped (weak; labelled).
Only derived statistics are kept (no retail record bytes)."""
from __future__ import annotations

import collections
import json
import math
import statistics

from common import CFG, nfl, read_csv, rr, work
from ovr import game_ovr

RETAIL_POS = {0: "QB", 1: "K", 2: "P", 3: "WR", 4: "CB", 5: "FS", 6: "SS", 7: "HB", 8: "FB", 9: "TE", 10: "OLB",
              11: "ILB", 12: "C", 13: "G", 14: "T", 15: "DT", 16: "DE"}
POOL = {"QB": ("QB",), "K": ("K",), "P": ("P",), "WR": ("WR",), "CB": ("CB",), "FS": ("FS",), "SS": ("SS",),
        "HB": ("HB",), "FB": ("FB",), "TE": ("TE",), "LB": ("ILB", "OLB"), "C": ("C",), "G": ("G",), "T": ("T",),
        "DT": ("DT",), "EDGE": ("DE",)}
STARTERS = {"QB": 1, "K": 1, "P": 1, "WR": 3, "CB": 3, "FS": 1, "SS": 1, "HB": 1, "FB": 1, "TE": 1, "LB": 2, "C": 1,
            "G": 2, "T": 2, "DT": 2, "EDGE": 2}
GROUP = {"QB": "QB", "HB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "T": "OL", "G": "OL", "C": "OL", "DT": "DL",
         "EDGE": "DL", "LB": "LB", "CB": "DB", "FS": "DB", "SS": "DB", "K": "KP", "P": "KP"}
COMBINE_GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "OT": "OL", "OG": "OL", "C": "OL",
                 "OL": "OL", "G": "OL", "T": "OL", "DT": "DL", "DE": "DL", "DL": "DL", "EDGE": "DL", "NT": "DL",
                 "OLB": "LB", "ILB": "LB", "LB": "LB", "CB": "DB", "S": "DB", "FS": "DB", "SS": "DB", "DB": "DB",
                 "K": "KP", "P": "KP", "LS": "OL"}
SPECS = {"speed": [["forty"]], "agility": [["cone", "shuttle", "forty"], ["shuttle", "forty"], ["forty"]],
         "jumping": [["vertical", "broad"], ["vertical"], ["broad"]], "strength": [["bench", "wt"], ["bench"], ["wt"]]}
IMPUTE = {"forty": ["wt"], "shuttle": ["forty", "wt"], "vertical": ["forty", "wt"], "broad_jump": ["forty", "wt"],
          "bench": ["wt"]}


def ols(X, y):
    """Least squares by Gauss-Jordan on the normal equations (standard library only)."""
    k = len(X[0])
    A = [[sum(X[i][a] * X[i][b] for i in range(len(X))) + (1e-9 if a == b else 0) for b in range(k)] for a in range(k)]
    v = [sum(X[i][a] * y[i] for i in range(len(X))) for a in range(k)]
    M = [row[:] + [v[i]] for i, row in enumerate(A)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [x / piv for x in M[c]]
        for r in range(k):
            if r != c:
                fac = M[r][c]
                M[r] = [a - fac * b for a, b in zip(M[r], M[c])]
    beta = [M[i][k] for i in range(k)]
    pred = [sum(b * x for b, x in zip(beta, row)) for row in X]
    res = [yy - pp for yy, pp in zip(y, pred)]
    sd = math.sqrt(sum(e * e for e in res) / max(1, len(y) - k))
    ybar = statistics.mean(y)
    r2 = 1 - sum(e * e for e in res) / sum((yy - ybar) ** 2 for yy in y) if len(y) > 1 else 0
    return beta, sd, r2


def retail_players():
    doc = rr.load_image(CFG["retail"])
    out = []
    for team in doc.teams[:32]:
        for p in doc.team_players(team.index):
            v = p.record.values
            ovr, ovr01 = game_ovr(p.record.encode())
            rpos = RETAIL_POS[v["position"]]
            # NOTE (f12, beta 77): the retail record's years pro counts the season in progress (rookie = 1) but the
            # candidates ranked against this reference use completed seasons (nflverse years_exp, rookie = 0), so their
            # experience percentile (composure / leadership / consistency) is one year low. Left as shipped because
            # changing it moves every mental rating; use rr.accrued_seasons(v["years_pro"]) when ratings are regenerated.
            out.append(dict(team=team.abbreviation, first=p.first, last=p.last, rpos=rpos,
                            pool=next(k for k, pos in POOL.items() if rpos in pos), years=v["years_pro"],
                            birth=p.record.get("birth_year"), ovr01=ovr01, ratings=p.record.ratings()))
    by = collections.defaultdict(list)
    for d in out:
        by[(d["team"], d["pool"])].append(d)
    for (_team, pool), lst in by.items():
        lst.sort(key=lambda d: -d["ovr01"])
        for i, d in enumerate(lst):
            d["tier"] = "starter" if i < STARTERS[pool] else "backup"
    return out


def tiers(players):
    ref = {}
    for pool in POOL:
        ref[pool] = {}
        for tier in ("starter", "backup", "all"):
            grp = [d for d in players if d["pool"] == pool and (tier == "all" or d["tier"] == tier)]
            ref[pool][tier] = {"n": len(grp), "ratings": {r: sorted(d["ratings"][r] for d in grp)
                                                        for r in rr.RATING_BYTE_ORDER}}
    return ref


def combine_rows():
    from mod_editor.core.nfl2k5_ratings_model import name_key
    rows = []
    for r in read_csv(nfl("combine.csv.gz")):
        rows.append(dict(key=name_key(r["player_name"]), year=int(float(r["season"] or r["draft_year"] or 0)),
                         pos=r["pos"], **{k: _f(r.get(c)) for k, c in (("forty", "forty"), ("bench", "bench"),
                                                                       ("vertical", "vertical"), ("broad", "broad_jump"),
                                                                       ("cone", "cone"), ("shuttle", "shuttle"),
                                                                       ("wt", "wt"))}))
    return rows


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def physfit(players, comb):
    from mod_editor.core.nfl2k5_ratings_model import name_key
    by = collections.defaultdict(list)
    for c in comb:
        by[c["key"]].append(c)
    pairs = []
    for p in players:
        cands = by.get(name_key(f"{p['first']} {p['last']}"), [])
        if cands:
            want = 2004 - p["years"]
            c = min(cands, key=lambda c: abs(c["year"] - want))
            if abs(c["year"] - want) <= 1:
                pairs.append((p, c))
    fits = {}
    for rating, specs in SPECS.items():
        fits[rating] = {}
        for grp in sorted(set(GROUP.values())):
            rows = [(p, c) for p, c in pairs if GROUP.get(p["pool"]) == grp]
            for feats in specs:
                use = [(p, c) for p, c in rows if all(c.get(x) is not None for x in feats)]
                if len(use) < 25:
                    continue
                beta, sd, r2 = ols([[1.0] + [c[x] for x in feats] for p, c in use], [p["ratings"][rating] for p, c in use])
                fits[rating].setdefault(grp, []).append({"features": feats, "beta": beta, "n": len(use),
                                                         "sd": round(sd, 2), "r2": round(r2, 3)})
    return len(pairs), fits


def age_slopes(players):
    out = {}
    for rating in ("speed", "agility", "jumping", "strength"):
        young = collections.defaultdict(list)
        for p in players:
            if p["birth"] and 2004 - p["birth"] <= 29 and p["pool"] not in ("K", "P"):
                young[p["pool"]].append(p["ratings"][rating])
        mu = {k: statistics.mean(v) for k, v in young.items()}
        xs, ys = [], []
        for p in players:
            if p["birth"] and p["pool"] not in ("K", "P") and 2004 - p["birth"] > 29:
                xs.append(2004 - p["birth"] - 29)
                ys.append(p["ratings"][rating] - mu[p["pool"]])
        out[rating] = {"slope_per_year_past_29": round(sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs), 3),
                       "n_over_29": len(xs)}
    return out


def impute_fits():
    rows = collections.defaultdict(list)
    for r in read_csv(nfl("combine.csv.gz")):
        g = COMBINE_GROUP.get((r["pos"] or "").upper())
        if g:
            rows[g].append({k: _f(r.get(k)) for k in ("forty", "bench", "vertical", "broad_jump", "cone", "shuttle", "wt")})
    out = {}
    for g, lst in rows.items():
        out[g] = {}
        for target, feats in IMPUTE.items():
            use = [r for r in lst if r[target] is not None and all(r[x] is not None for x in feats)]
            if len(use) >= 30:
                beta, sd, r2 = ols([[1.0] + [r[x] for x in feats] for r in use], [r[target] for r in use])
                out[g][target] = {"features": feats, "beta": beta, "n": len(use), "sd": round(sd, 3), "r2": round(r2, 3)}
    return out


def build(path=None):
    players = retail_players()
    n_pairs, fits = physfit(players, combine_rows())
    ref = {"schema": "nfl2k5.ratings_v2_reference.v1", "evidence": "PROVED OFFLINE: derived statistics of the retail "
           "2004 rosters (no record bytes) and of the public nflverse combine file",
           "tiers": tiers(players), "physfit": {"pairs": n_pairs, "fits": fits}, "age": age_slopes(players),
           "impute": impute_fits()}
    out = path or work("ratings_v2_reference.json")
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(ref, indent=1, sort_keys=True) + "\n")
    return ref
