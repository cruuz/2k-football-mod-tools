"""Year-to-year stability of every rating component (v2.1): the same player at the same position, his 2024 value
against his 2025 value. A one-season value with volume n has reliability n / (n + k), so each component's shrinkage
constant is k = n_bar (1 - r) / r, r the between-season correlation over players with a real sample in both
seasons (at least half the v2.0 constant, else the full constant, and at least 12 players). True change between
seasons (age, a new team) makes this k an upper bound. Writes <work>/stability.json; model.stable_k reads it.
PROVED OFFLINE (computed from the cited public data)."""
from __future__ import annotations

import collections
import json
import statistics

import common
from common import base, rr, work


def corr(xs, ys):
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy) if sx and sy else None


def main():
    import model
    D = model.Data()
    retail, body_u7, u7, rows = base()
    doc = rr.RosterDocument(body_u7)
    by = {(p.pool, p.index): p for p in doc.players}
    players = model.build_players(D, rows, doc, by)
    model.Model(D, players)                       # the league fits the lineman and kicker measures use
    saved = dict(model.W)
    comps = {}
    try:
        for y in (2024, 2025):
            model.W = {y: 1.0}
            comps[y] = {(p['gsis'], p['pos']): model.components(D, p['gsis'], p['pos']) for p in players}
    finally:
        model.W = saved
    pairs = collections.defaultdict(list)
    for key, now in comps[2025].items():
        before = comps[2024].get(key, {})
        grp = model.GROUP[key[1]]
        for rating, lst in now.items():
            prev = {c[0]: c for c in before.get(rating, [])}
            for c in lst:
                if c[0] in prev:
                    pairs[(grp, rating, c[0])].append((prev[c[0]][1], c[1], prev[c[0]][2], c[2], c[3]))
    out = []
    for (grp, rating, name), v in sorted(pairs.items()):
        k_now = v[0][4]
        sel = []
        for lo in (0.5, 1.0):
            sel = [x for x in v if x[2] >= lo * k_now and x[3] >= lo * k_now]
            if len(sel) >= 12:
                break
        if len(sel) < 12:
            out.append(dict(group=grp, rating=rating, component=name, n_players=len(sel), k_now=k_now, note="too few"))
            continue
        r = corr([x[0] for x in sel], [x[1] for x in sel])
        nbar = statistics.mean((x[2] + x[3]) / 2 for x in sel)
        k = nbar * (1 - r) / r if r and r > 0.02 else None
        out.append(dict(group=grp, rating=rating, component=name, n_players=len(sel),
                        r_2024_2025=round(r, 3) if r is not None else None, mean_volume=round(nbar, 1), k_now=k_now,
                        k_data=round(k, 1) if k else None))
    path = work("stability.json")
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(path, len(out), "components")
    return out
