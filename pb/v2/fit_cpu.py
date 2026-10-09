#!/usr/bin/env python3
"""Fit a team package's CPU personnel design to its real 2025 tendencies (beta 77, job p6s). Writes only with --write.

The CPU picks a personnel group (category lottery 0x2093F0: code distance to the down-and-distance target 0x209FE0,
times the mean formation rating of the group's members, cubed), then a formation among the group's owners
(0x2081B0). This tool searches, on the analytic selector ``pb/v2/selection_model.py``, each ordinary formation's
CPU ratings (short, medium, long; flag bits 21-29) and its group ownership and membership among the groups that
field the same eleven players (personnel twins, see ``personnel_groups`` in TEAM_PACKAGES.md), so the book's
personnel and shotgun shares per situation approach the team's 2025 charting (``pb/research/situational_2025.json``).

The shotgun share depends on the engine's shotgun weight (``0x207EF0``: retail 0.05 beyond the 10; job a4 makes it a
per-team value fitted on the final books). The objective uses the weight a4's least-squares fit would choose for the
candidate book (its seven down-and-distance bins), plus a smaller term for the retail 0.05, so the design works
either way. Variety terms keep five or more formations in every ordinary cell and no formation above 30%.

    python3 pb/v2/fit_cpu.py --image RETAIL.iso --team KC [--iters 3000] [--seed 1] [--write]

DESIGN tool on PROVED OFFLINE selector code; check the result natively (u-ai call-mix harness) before shipping.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_complete_offense as full  # noqa: E402
from pb.v2 import build as v2  # noqa: E402
from pb.v2 import selection_model as sm  # noqa: E402

RESEARCH = ROOT / "pb/research/situational_2025.json"
NFLVERSE = {"ARZ": "ARI", "STL": "LA", "SD": "LAC", "OAK": "LV"}
HEAVY = {"13", "22", "23", "03", "02", "31", "32", "14"}
GRID = [  # (cell, situation, research bin, weight within the bin)
    ("1st&10 own25", dict(down=1, distance=10, yard=25), "d1", 0.75), ("1st&10 opp40", dict(down=1, distance=10, yard=60), "d1", 0.25),
    ("2nd&2 own40", dict(down=2, distance=2, yard=40), "d2_short", 1.0), ("2nd&5 own35", dict(down=2, distance=5, yard=35), "d2_mid", 1.0),
    ("2nd&8 mid", dict(down=2, distance=8, yard=50), "d2_long", 0.6), ("2nd&12 own20", dict(down=2, distance=12, yard=20), "d2_long", 0.4),
    ("3rd&1 opp40", dict(down=3, distance=1, yard=60), "d3_short", 0.4), ("3rd&2 own45", dict(down=3, distance=2, yard=45), "d3_short", 0.6),
    ("3rd&4 own45", dict(down=3, distance=4, yard=45), "d3_mid", 0.5), ("3rd&6 mid", dict(down=3, distance=6, yard=50), "d3_mid", 0.5),
    ("3rd&8 mid", dict(down=3, distance=8, yard=50), "d3_long", 0.6), ("3rd&12 own30", dict(down=3, distance=12, yard=30), "d3_long", 0.4),
    ("2nd&6 opp8", dict(down=2, distance=6, yard=92), "red10", 0.5), ("1st&G opp3", dict(down=1, distance=3, yard=97), "red10", 0.5),
]
A4_BINS = {"d1": (1, 10), "d2_short": (2, 2), "d2_mid": (2, 5), "d2_long": (2, 10), "d3_short": (3, 2), "d3_mid": (3, 5), "d3_long": (3, 10)}
NO_VARIETY = {"3rd&1 opp40", "1st&G opp3"}


def pclass(label: str | None) -> str:
    label = (label or "?").rstrip("+")
    return "heavy" if label in HEAVY else label


@contextlib.contextmanager
def gun_weight(value: float):
    original = sm.form_weight

    def patched(flags, sit, which):
        if (flags >> 8) & 0x3F < 4 and flags & 0xC0000 == 0x80000 and (100 - sit["yard"]) * sm.YD > 914.4:
            return value
        t = sm.blend_t(sit["down"], sit["distance"] * sm.YD)
        pts = sm.CURVE_A if which == "A" else sm.CURVE_B
        r = [(flags >> s) & 7 for s in (21, 24, 27)]
        tt, a, b = (t - 0.5, r[1], r[2]) if t >= 0.5 else (t, r[0], r[1])
        return sm.curve(pts, b - 2) * 2 * tt + (1 - 2 * tt) * sm.curve(pts, a - 2)
    sm.form_weight = patched
    try:
        yield
    finally:
        sm.form_weight = original


class Design:
    """Mutable copy of a compiled book's offense lottery inputs."""

    def __init__(self, bk: sm.Book, ordinary: set[int]):
        self.bk = bk
        self.ordinary = sorted(ordinary)
        self.pers = {ci: pclass(c.get("personnel")) for ci, c in bk.cats.items()}       # scoring class
        self.exact = {ci: c.get("personnel") for ci, c in bk.cats.items()}               # who lines up
        self.tags: dict[int, str] = {}

    def flags(self, fi: int, ratings) -> int:
        f = self.bk.forms[fi]
        word = f["flags"] & ~(0x1FF << 21)
        for s, v in zip((21, 24, 27), ratings):
            word |= (v & 7) << s
        return word

    def apply(self, state):
        for fi, (own, mask, ratings) in state.items():
            f = self.bk.forms[fi]
            f["own"], f["mask"], f["flags"] = own, sum(1 << c for c in mask), self.flags(fi, ratings)


def league_bins() -> dict:
    """Snap-weighted league means of every bin (personnel shares, shotgun share, snaps per team)."""
    teams = json.loads(RESEARCH.read_text(encoding="utf-8"))["teams"]
    out = {}
    for b in {b for t in teams.values() for b in t["bins"]}:
        rows = [t["bins"][b] for t in teams.values() if b in t["bins"]]
        n = sum(r["snaps"] for r in rows)
        pers = {}
        for r in rows:
            for k, v in r["personnel"].items():
                pers[k] = pers.get(k, 0) + v * r["snaps"] / n
        out[b] = dict(snaps=round(n / len(teams)), gun_pct=round(sum(r["gun_pct"] * r["snaps"] for r in rows) / n, 1),
                      personnel=pers)
    return out


def targets(team: str, league: bool = False) -> tuple[dict, dict]:
    data = league_bins() if league else \
        json.loads(RESEARCH.read_text(encoding="utf-8"))["teams"][NFLVERSE.get(team, team)]["bins"]
    cells = {}
    for cell, sit, b, wt in GRID:
        row = data.get(b)
        if not row:
            continue
        pers = {}
        for k, v in row["personnel"].items():
            pers[pclass(k)] = pers.get(pclass(k), 0) + v
        share = row["snaps"] / sum(r["snaps"] for r in data.values())
        cells[cell] = (sit, pers, row["gun_pct"], wt * (0.3 + 4.0 * share))
    gun_bins = {}
    for b, (d, dist) in A4_BINS.items():
        if b in data:
            gun_bins[b] = (dict(down=d, distance=dist, yard=50), data[b]["snaps"], data[b]["gun_pct"])
    return cells, gun_bins


def gun_share(bk, sit) -> float:
    _pc, pform, _m = bk.distribution(sit)
    return 100 * sum(p for fi, p in pform.items() if bk.forms[fi]["flags"] & 0xC0000 == 0x80000)


def fit_w(bk, gun_bins) -> float:
    def err(w):
        with gun_weight(w):
            return sum(n * (gun_share(bk, sit) - g) ** 2 for sit, n, g in gun_bins.values())
    lo, hi = 0.05, 4.0
    for _ in range(18):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if err(m1) <= err(m2):
            hi = m2
        else:
            lo = m1
    return max(0.05, min(4.0, round(round((lo + hi) / 2 / 0.05) * 0.05, 2)))


# Formation appropriateness (the engine has no other notion of it): goal-line and short-yardage sets keep poor
# medium/long ratings so the CPU never calls them on first and ten at midfield; empty sets stay a change-up on early downs.
RATING_FLOOR = {"goal": (0, 4, 4), "short": (0, 3, 4)}
EARLY_CELLS = {"1st&10 own25", "1st&10 opp40", "2nd&5 own35", "2nd&8 mid"}
EMPTY_CAP = 8.0


def clamp(tag: str, ratings) -> tuple:
    """Floors for heavy sets plus the catalog's ordering rule (tests/mod_editor/test_nfl2k5_offense_concepts.py):
    goal-line and short-yardage sets are best on short yardage (short <= medium <= long), spread and empty sets
    best on long yardage (long <= medium <= short)."""
    floor = RATING_FLOOR.get(tag, (0, 0, 0))
    s, m, l = (min(7, max(f, v)) for f, v in zip(floor, ratings))
    if tag in ("goal", "short"):
        m = max(m, s)
        l = max(l, m)
    elif tag in ("spread", "empty"):
        m = max(m, l)
        s = max(s, m)
    return (s, m, l)


def score(design: Design, cells, w) -> tuple[float, dict]:
    bk, total, rows = design.bk, 0.0, {}
    with gun_weight(w):
        for cell, (sit, tp, tg, wt) in cells.items():
            pcat, pform, _m = bk.distribution(sit)
            pers = {}
            for ci, p in pcat.items():
                pers[design.pers[ci]] = pers.get(design.pers[ci], 0) + 100 * p
            gun = 100 * sum(p for fi, p in pform.items() if bk.forms[fi]["flags"] & 0xC0000 == 0x80000)
            e = sum((pers.get(k, 0) - tp.get(k, 0)) ** 2 for k in set(pers) | set(tp)) + (gun - tg) ** 2
            busiest = 100 * max(pform.values()) if pform else 100
            nform = sum(1 for p in pform.values() if p >= 0.02)
            e += max(0, busiest - 30) ** 2
            if cell not in NO_VARIETY:
                e += 400 * max(0, 5 - nform) ** 2
            if cell in EARLY_CELLS:
                empty = 100 * sum(p for fi, p in pform.items() if design.tags.get(fi) == "empty")
                e += 4 * max(0, empty - EMPTY_CAP) ** 2
            total += wt * e / 100
            rows[cell] = dict(personnel={k: round(v) for k, v in sorted(pers.items(), key=lambda kv: -kv[1]) if v >= 0.5},
                              gun=round(gun), formations=nform, busiest=round(busiest),
                              target=dict(personnel={k: round(v) for k, v in tp.items()}, gun=tg))
    return total, rows


def objective(design, state, cells, gun_bins, retail_weight=0.2):
    design.apply(state)
    w = fit_w(design.bk, gun_bins)
    e1, _ = score(design, cells, w)
    e2, _ = score(design, cells, 0.05)
    return e1 + retail_weight * e2, w


def search(design: Design, state: dict, groups: dict, cells, gun_bins, iters: int, seed: int, log=print):
    rnd = random.Random(seed)
    best = objective(design, state, cells, gun_bins)
    keys = list(state)
    for it in range(iters):
        cand = copy.deepcopy(state)
        fi = rnd.choice(keys)
        own, mask, r = cand[fi]
        options = groups[design.exact[own]]
        move = rnd.random()
        if move < 0.6 or len(options) == 1:
            r = list(r)
            r[rnd.randrange(3)] = rnd.randrange(5)
            cand[fi] = (own, mask, clamp(design.tags.get(fi, ""), r))
        elif move < 0.8:
            new = rnd.choice(options)
            cand[fi] = (new, sorted(set(mask) - {own} | {new}), r)
            # every group that owns a formation keeps one (a personnel twin is declared by its owners)
            if not any(o == own for o, _m, _r in cand.values()):
                continue
        else:
            c = rnd.choice(options)
            if c == own:
                continue
            cand[fi] = (own, sorted(set(mask) ^ {c}), r)
        value = objective(design, cand, cells, gun_bins)
        if value[0] < best[0] - 1e-6:
            state, best = cand, value
        if it % 500 == 0:
            log(f"  it {it} objective {best[0]:.1f} (fitted shotgun weight {best[1]})")
    design.apply(state)
    return state, best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, required=True, help="retail ISO (read only)")
    ap.add_argument("--team", required=True)
    ap.add_argument("--iters", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--write", action="store_true", help="write formation_groups / formation_ratings into the package")
    ap.add_argument("--league", action="store_true",
                    help="fit the shared core instead: league-mean 2025 targets on this team's book; with --write the "
                         "ratings go to core.json formation_ratings and the 11 personnel groups to formation_groups_default")
    args = ap.parse_args(argv)
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(args.image) as image:
        retail = image.read_entry(BOOK_ENTRIES[args.team])
    core, pkg = v2.load_core(), v2.load_package(args.team)
    pack, catalog = v2.build_team(retail, args.team, core, pkg)
    compiled = full.compile_offense(retail, pack, asset_id="book:" + args.team).replacement
    bk = sm.book_from(compiled)
    fs = {f.replace_index for f in pack.formations}
    design = Design(bk, fs)
    design.tags = {f.replace_index: v2.oc.FORMATIONS[f.custom_name].tag for f in pack.formations
                   if f.custom_name in v2.oc.FORMATIONS}
    names = {ci: c["name"] for ci, c in bk.cats.items()}
    groups = {}
    for ci, c in bk.cats.items():
        if c["id"] <= 10 and c.get("personnel") and ci not in bk.special_cats:
            groups.setdefault(design.exact[ci], []).append(ci)
    state = {}
    for fi in sorted(fs):
        f = bk.forms[fi]
        mask = [c for c in range(26) if f["mask"] >> c & 1 and design.exact.get(c) == design.exact[f["own"]]] or [f["own"]]
        state[fi] = (f["own"], sorted(set(mask) | {f["own"]}),
                     clamp(design.tags.get(fi, ""), tuple((f["flags"] >> s) & 7 for s in (21, 24, 27))))
    cells, gun_bins = targets(args.team, args.league)
    before = objective(design, state, cells, gun_bins)
    print(f"{args.team}: start objective {before[0]:.1f} (fitted shotgun weight {before[1]})")
    state, best = search(design, state, groups, cells, gun_bins, args.iters, args.seed)
    _e, rows = score(design, cells, best[1])
    for cell, row in rows.items():
        print(f"  {cell:13s} gun {row['gun']:3d}/{row['target']['gun']:5.1f}  {row['personnel']}  want {row['target']['personnel']}")
    fnames = {f.replace_index: f.custom_name for f in pack.formations}
    out_groups = {fnames[fi]: {"own": names[own], "mask": [names[c] for c in mask]} for fi, (own, mask, _r) in state.items()}
    out_ratings = {fnames[fi]: list(r) for fi, (_o, _m, r) in state.items()}
    print(f"{args.team}: final objective {best[0]:.1f}, fitted shotgun weight {best[1]}")
    if args.write and args.league:
        core["formation_ratings"].update(out_ratings)
        eleven = {n: g for n, g in out_groups.items() if v2.oc.FORMATIONS[n].personnel == "11"}
        core["formation_groups_default"].update(eleven)
        v2.CORE.write_text(json.dumps(core, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("wrote", v2.CORE)
    elif args.write:
        pkg["formation_groups"] = out_groups
        pkg["formation_ratings"] = out_ratings
        path = v2.TEAMS_DIR / f"{args.team}.json"
        path.write_text(json.dumps(pkg, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("wrote", path)
    else:
        print(json.dumps(dict(formation_groups=out_groups, formation_ratings=out_ratings), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
