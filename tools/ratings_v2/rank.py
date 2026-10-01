"""The superstar ranking rule (top 250) on the records as they will be written.

Rule (DESIGN, approved by main 2026-09-24): a star marks the top third of the league's starters at each position,
where "best" is the game's own OVERALL formula (FUN_00246d90, executed natively; ovr.py) with its height/weight
bonus switched off (else a 380-lb tackle outranks better linemen for his size alone). Starter slots per team in the
modern base lineup: QB 1, HB 1, WR 3, TE 1, T 2, G 2, C 1, DT 2, EDGE 2, LB 2, CB 3, FS 1, SS 1, K 1, P 1 = 24 (768
league-wide). A player's score is (rank at his position - 0.5) / (32 x slots); the 250 lowest scores get the star.
So every position gets the same share of its starter slots (250/768 = 32.6%): about 10 QBs, 10 HBs, 31 WRs, 10 TEs,
52 OL, 42 DL, 21 LB, 31 CB, 21 S, 10 K, 10 P. FB has no base-lineup slot (11 personnel) and gets none. Ties: higher
unrounded OVR first, then lower record index."""
from __future__ import annotations

import collections

from common import ONE_POOL
from ovr import game_ovr

SLOTS = {"QB": 1, "HB": 1, "WR": 3, "TE": 1, "T": 2, "G": 2, "C": 1, "DT": 2, "EDGE": 2, "LB": 2, "CB": 3,
         "FS": 1, "SS": 1, "K": 1, "P": 1}
TOP = 250
RULE = __doc__.split("\n\n", 1)[1]


def rank(players):
    """players: (pool, index, position_code, record_bytes, label). Returns (ranked dicts, primary indices tagged)."""
    by_pos = collections.defaultdict(list)
    out = []
    for pool, index, code, rec, label in players:
        ovr, ovr01 = game_ovr(rec)
        in_game, _ = game_ovr(rec, body_terms=True)
        d = dict(pool=pool, index=index, pos=ONE_POOL[code], ovr=ovr, ovr01=ovr01, ovr_in_game=in_game, label=label)
        out.append(d)
        by_pos[d["pos"]].append(d)
    for pos, lst in by_pos.items():
        lst.sort(key=lambda d: (-d["ovr01"], d["index"]))
        for r, d in enumerate(lst, 1):
            d["pos_rank"] = r
            slots = SLOTS.get(pos, 0)
            d["score"] = (r - 0.5) / (32 * slots) if slots else float("inf")
    ranked = sorted(out, key=lambda d: (d["score"], -d["ovr01"], d["index"]))
    for i, d in enumerate(ranked, 1):
        d["league_rank"] = i
        d["star"] = i <= TOP and d["score"] != float("inf")
    tags = sorted(d["index"] for d in ranked if d["star"] and d["pool"] == "primary")
    return ranked, tags
