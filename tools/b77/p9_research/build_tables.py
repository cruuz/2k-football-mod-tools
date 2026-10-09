"""Build the Modern 2 decision tables from published analytics (reproducible).

Inputs
  * ESPN Analytics 4th-down chart ("Typical situations", Seth Walder, Jan 2022): per-yards-to-go window boundaries,
    measured from the published image by digitize_espn4th.py (values below are those measurements).
  * nfl4th (Ben Baldwin / nflverse) pre-computed decisions joined to nflverse play-by-play 2014-2025 (load_nfl4th.py):
    go_boost > 0 means the model recommends going for it.
Outputs (JSON on stdout / --out): LIMIT_X, SHIFT, diagnostics.
Run: venv/bin/python -I build_tables.py <nfl4th_joined.parquet> <out.json>
"""
import json, sys
import numpy as np
import pandas as pd
from scipy.optimize import minimize

# ---- ESPN chart, nominal boundaries in yards to the opponent end zone (x), measured at the gridline of each distance.
# Each entry: list of (kind, left, right) runs; kinds G=Go F=FG P=Punt. Left edges of the chart are the physical limit.
ESPN = {
    1: [("G", -0.9, 92.2), ("P", 92.3, 93.1)],
    2: [("G", 0.0, 89.0), ("P", 89.3, 93.1)],
    3: [("G", 1.2, 76.0), ("P", 76.1, 94.0)],
    4: [("G", 2.1, 68.0), ("P", 68.4, 95.1)],
    5: [("G", 3.1, 16.9), ("F", 17.0, 30.0), ("G", 30.2, 60.9), ("P", 61.2, 96.2)],
    6: [("G", 4.0, 11.8), ("F", 12.0, 32.9), ("G", 33.2, 55.0), ("P", 55.1, 97.1)],
    7: [("G", 5.1, 7.8), ("F", 8.0, 34.9), ("G", 35.2, 51.0), ("P", 51.2, 98.1)],
    8: [("F", 6.0, 36.8), ("G", 37.1, 49.0), ("P", 49.2, 99.1)],
    9: [("F", 7.1, 37.9), ("G", 38.1, 46.0), ("P", 46.1, 100.1)],
    10: [("F", 8.0, 39.9), ("G", 40.1, 42.0), ("P", 42.1, 101.1)],
}

def go_windows(conservative=True):
    """Inclusive integer windows of x where the chart says Go, per distance."""
    out = {}
    for d, runs in ESPN.items():
        wins = []
        for i, (k, l, r) in enumerate(runs):
            if k != "G":
                continue
            prev_kind = runs[i - 1][0] if i else None
            lo = 0 if prev_kind is None else int(round(l)) + (1 if conservative else 0)
            hi = int(round(r)) - (1 if conservative else 0)
            if hi >= lo:
                wins.append((lo, hi))
        out[d] = wins
    return out

def limit_table(windows, xmax=100):
    lim = []
    for x in range(xmax + 1):
        d = 0
        while d + 1 in windows and any(lo <= x <= hi for lo, hi in windows[d + 1]):
            d += 1
        lim.append(d)
    return lim

def logit_cross(sub, minn=40):
    d = sub.ydstogo.clip(upper=25).values.astype(float); y = sub.go.values
    if len(sub) < minn or y.min() == y.max():
        return (np.nan, len(sub))
    def nll(p):
        z = p[0] + p[1] * d
        return np.sum(np.logaddexp(0, z) - y * z) + 0.01 * (p[1] ** 2)
    r = minimize(nll, [2.0, -0.5], method="BFGS"); a, b = r.x
    if b >= -0.01:
        return (np.nan, len(sub))
    return (-a / b, len(sub))

def pav(values, weights, increasing=True):
    """Weighted pool-adjacent-violators; returns monotone fit."""
    v = list(values); w = list(weights)
    if not increasing:
        v = [-a for a in v]
    blocks = [[v[i], w[i], 1] for i in range(len(v))]
    out = []
    for b in blocks:
        out.append(b)
        while len(out) > 1 and out[-2][0] > out[-1][0]:
            a, c = out[-2], out[-1]
            tw = a[1] + c[1]
            out[-2:] = [[(a[0] * a[1] + c[0] * c[1]) / tw, tw, a[2] + c[2]]]
    fit = []
    for val, wt, cnt in out:
        fit += [val] * cnt
    return [(-a if not increasing else a) for a in fit]

def region(x): return 0 if x > 60 else (1 if x > 40 else 2)   # P (own<40), M (40-60), F (opp<40)
REG = ["P", "M", "F"]
def tcls(T):
    return 0 if T > 1800 else 1 if T > 900 else 2 if T > 600 else 3 if T > 300 else 4 if T > 120 else 5
def mcls(D):
    return 0 if D <= -9 else 1 if D <= -4 else 2 if D <= -1 else 3 if D == 0 else 4 if D <= 3 else 5 if D <= 8 else 6

def main():
    df = pd.read_parquet(sys.argv[1])
    df = df.dropna(subset=["go_boost", "yardline_100", "ydstogo", "score_differential", "game_seconds_remaining", "wp", "half_seconds_remaining"])
    import os
    lo, hi = float(os.environ.get("WP_LO", "0.05")), float(os.environ.get("WP_HI", "0.95"))   # sensitivity runs only
    df = df[(df.wp > lo) & (df.wp < hi) & (df.qtr <= 4)].copy()
    df["go"] = (df.go_boost > 0).astype(float)
    df["x"] = df.yardline_100; df["D"] = df.score_differential; df["Tg"] = df.game_seconds_remaining
    df["r"] = df.x.map(region); df["t"] = df.Tg.map(tcls); df["m"] = df.D.map(mcls)
    ref = df[(df.t == 0) & (df.D.abs() <= 8) & (df.half_seconds_remaining > 120)]
    dtyp = {r: logit_cross(g, 100)[0] for r, g in ref.groupby("r")}
    est = np.full((6, 7, 3), np.nan); cnt = np.zeros((6, 7, 3))
    for (t, m, r), g in df.groupby(["t", "m", "r"]):
        c, n = logit_cross(g)
        cnt[t, m, r] = n
        if c == c:
            est[t, m, r] = c - dtyp[r]
    # direction of monotonicity along time (t=1..5): +1 nondecreasing, -1 nonincreasing
    def direction(m, r):
        if m in (0, 1): return +1
        if m in (2, 3): return +1 if r in (0, 1) else -1
        return -1
    smooth = np.zeros((6, 7, 3))
    for m in range(7):
        for r in range(3):
            vals, wts = [], []
            last = 0.0
            for t in range(1, 6):
                v = est[t, m, r]; n = cnt[t, m, r]
                if v != v:
                    vals.append(last); wts.append(1e-6)
                else:
                    vals.append(v); wts.append(max(n, 1)); last = v
            fit = pav(vals, wts, increasing=direction(m, r) > 0)
            for i, t in enumerate(range(1, 6)):
                smooth[t, m, r] = fit[i]
    final = np.zeros((6, 7, 3), dtype=int)
    for t in range(6):
        for m in range(7):
            for r in range(3):
                v = 0.0 if t == 0 else smooth[t, m, r]
                final[t, m, r] = int(np.sign(v) * np.floor(abs(v) + 0.5))
    final = np.clip(final, -4, 12)
    for m in (0, 1):                       # trailing by a touchdown or more with two minutes left: go on every fourth down
        final[5, m, :] = 100
    win = go_windows(True); nominal = go_windows(False)
    LIM = limit_table(win)
    LIM_nom = limit_table(nominal)
    LIM_ship = [0 if x > 80 else LIM[x] for x in range(101)]
    # ---- validation against nfl4th on all joined states (WP-filtered)
    def policy_go(row, shifts=True):
        x = int(np.floor(row.x + 1e-6)); base = LIM_ship[min(max(x, 0), 100)]
        s = int(final[row.t, row.m, row.r]) if shifts else 0
        return row.ydstogo <= base + s
    sub = df.copy()
    sub["p2"] = sub.apply(policy_go, axis=1); sub["p2_typ"] = sub.apply(lambda r: policy_go(r, False), axis=1)
    v05_bands = [(0, 20, 0), (20, 40, 1), (40, 60, 2), (60, 80, 3), (80, 95, 2), (95, 100.01, 2)]
    def v05(row):
        own = 100 - row.x
        lim = 0
        for lo, hi, l in v05_bands:
            if lo <= own < hi: lim = l
        if own < 20: return False
        if row.qtr == 4 and row.Tg <= 300:
            if row.D >= 9: lim -= 1
            elif row.D <= -4 and row.Tg <= 120: lim += 4
            elif row.D <= -9: lim += 2
        if row.qtr == 2 and row.half_seconds_remaining <= 30: return False
        if row.qtr == 4 and row.Tg <= 120 and row.D >= -3: return False
        return row.ydstogo <= lim
    sub["v05"] = sub.apply(v05, axis=1)
    def stats(col):
        tp = ((sub[col]) & (sub.go > 0)).sum(); fp = ((sub[col]) & (sub.go == 0)).sum()
        fn = ((~sub[col]) & (sub.go > 0)).sum(); tn = ((~sub[col]) & (sub.go == 0)).sum()
        return dict(accuracy=round((tp + tn) / len(sub), 4), precision=round(tp / max(tp + fp, 1), 4), recall=round(tp / max(tp + fn, 1), 4),
                    go_rate=round(float(sub[col].mean()), 4), tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn))
    diag = dict(rows=len(sub), nfl4th_go_rate=round(float(sub.go.mean()), 4), modern2=stats("p2"), modern2_typical_only=stats("p2_typ"), v05_modern=stats("v05"))
    # how aggressive is that, compared with what NFL coaches actually did in the same states (rows with a clear play type)
    clear = sub[sub.play_type.isin(["run", "pass", "punt", "field_goal"])].copy()
    clear["coach_go"] = clear.play_type.isin(["run", "pass"])
    by_season = {}
    for season, g in clear.groupby("season"):
        by_season[int(season)] = dict(states=len(g), coaches_went=round(float(g.coach_go.mean()), 4), nfl4th_go=round(float(g.go.mean()), 4),
                                      modern2_go=round(float(g.p2.mean()), 4), v05_modern_go=round(float(g.v05.mean()), 4))
    diag["real_state_go_rates"] = dict(
        all_seasons=dict(states=len(clear), coaches_went=round(float(clear.coach_go.mean()), 4), nfl4th_go=round(float(clear.go.mean()), 4),
                         modern2_go=round(float(clear.p2.mean()), 4), v05_modern_go=round(float(clear.v05.mean()), 4)),
        by_season=by_season,
        note="Fraction of the real NFL fourth downs in the data on which each policy goes for it. Modern 2 is a model-optimal policy: it goes about "
             "twice as often as the 2025 coaches did; the engine's own conversion rates are unmeasured.")
    out = dict(
        typical_dstar_nfl4th={REG[r]: round(float(v), 2) for r, v in dtyp.items()},
        espn_windows_conservative={str(d): w for d, w in win.items()},
        espn_windows_nominal={str(d): w for d, w in nominal.items()},
        limit_x_nominal=LIM_nom, limit_x_conservative=LIM, limit_x_shipped=LIM_ship,
        shift_raw=np.round(np.nan_to_num(est, nan=-99), 2).tolist(), shift_n=cnt.astype(int).tolist(),
        shift_smoothed=np.round(smooth, 2).tolist(), shift_final=final.tolist(), diagnostics=diag)
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(diag, indent=1))
    print("LIMIT_X shipped (x=0..100):", LIM_ship)
    print("SHIFT final [t][m][r in P,M,F]:")
    for t in range(6):
        print("t", t, [final[t, m].tolist() for m in range(7)])

if __name__ == "__main__":
    main()
