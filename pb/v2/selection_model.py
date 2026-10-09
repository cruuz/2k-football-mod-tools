#!/usr/bin/env python3
"""Analytic model of the native CPU personnel + formation choice (beta 77, job p48o). Read only.

Re-implements, from the decompiled retail code, the two lotteries that pick an offensive personnel
group (category) and formation, so formation situation ratings can be checked without the emulator.
Checked against u-ai's native call-mix harness (Unicorn, real 0x20B670) on the v2 KC book: category
and formation shares agree within sampling noise in all 11 harness situations.

  target    0x209FE0  x = ytg / max(4 - down, 1) * max(0.5 * down, 1) (cm); T = curve 0x50AED0(x) + U(-1, 1),
                      rounded half away from zero, clamped 0..10 (urgency 0, not overtime)
  category  0x2093F0  candidates: category id 0..10 with members, not 0x204C80's special categories;
                      w = curve 0x50AEF4(|id - T|, halved on downs 1-2) * mean over members of 0x207EF0 (curve B),
                      then cubed
  members   0xE10D0   formations whose category mask (aux+0x4C) carries the category
  formation 0x2081B0  candidates: mask members, not special, own category == the pick when any formation owns it,
                      flag bit 30 clear; w = 0x207EF0 (curve A); power 1
  0x207EF0            shotgun/pistol sets (type < 4, flags & 0xC0000 == 0x80000) score 0.05 more than 10 yards from
                      the goal; otherwise the short/medium/long ratings (bits 21-29) blended by 0x207E30's yards-to-go
                      position (downs 1-2: 5-15 yd, 3: 3-7, 4: 3-5), x = rating - 2

Usage: selection_model.py BOOK.play [BOOK.play ...]   (composed books, e.g. pb/v2/verify.py --books output)
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402

YD = 91.44
CURVE_A = [(-2, 0.5), (-1, 2.0), (0, 1.0), (1, 0.5), (2, 0.1)]
CURVE_B = [(-2, 3.0), (-1, 2.0), (0, 1.0), (1, 0.5), (2, 0.1)]
CURVE_DIST = [(0, 1.0), (1, 1.0), (2, 0.85), (3, 0.5), (4, 0.05)]
CURVE_TARGET = [(91.44, 0.0), (301.752, 4.0), (457.2, 4.0), (1097.28, 11.0)]
SITUATIONS = [
    ("1st&10 own25", dict(down=1, distance=10, yard=25)),
    ("2nd&2 own40", dict(down=2, distance=2, yard=40)),
    ("2nd&8 mid", dict(down=2, distance=8, yard=50)),
    ("3rd&1 opp40", dict(down=3, distance=1, yard=60)),
    ("3rd&4 own45", dict(down=3, distance=4, yard=45)),
    ("3rd&8 mid", dict(down=3, distance=8, yard=50)),
    ("3rd&15 own30", dict(down=3, distance=15, yard=30)),
    ("4th&1 opp35", dict(down=4, distance=1, yard=65)),
    ("1st&G opp3", dict(down=1, distance=3, yard=97)),
    ("3rd&G opp1", dict(down=3, distance=1, yard=99)),
    # extra early-down cells for tuning
    ("1st&10 opp40", dict(down=1, distance=10, yard=60)),
    ("2nd&5 own35", dict(down=2, distance=5, yard=35)),
    ("2nd&12 own20", dict(down=2, distance=12, yard=20)),
    ("1st&10 opp15", dict(down=1, distance=10, yard=85)),
    ("2nd&6 opp8", dict(down=2, distance=6, yard=92)),
]


def curve(points, x):
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[-1][1]


def blend_t(down, ytg_cm):
    lo, hi = {3: (274.32, 640.08), 4: (274.32, 457.2)}.get(down, (457.2, 1371.6))
    return min(1.0, max(0.0, (ytg_cm - lo) / (hi - lo)))


def form_weight(flags, sit, which):
    """0x207EF0 in normal play (urgency 0). which: 'A' (formation lottery) or 'B' (category mean)."""
    pts = CURVE_A if which == 'A' else CURVE_B
    ftype = (flags >> 8) & 0x3F
    to_goal = (100 - sit['yard']) * YD
    if ftype < 4 and flags & 0xC0000 == 0x80000 and to_goal > 914.4:
        return 0.05
    ytg = sit['distance'] * YD
    t = blend_t(sit['down'], ytg)
    r = [(flags >> s) & 7 for s in (21, 24, 27)]
    if t >= 0.5:
        tt, a, b = t - 0.5, r[1], r[2]
    else:
        tt, a, b = t, r[0], r[1]
    return curve(pts, b - 2) * 2 * tt + (1 - 2 * tt) * curve(pts, a - 2)


def target_dist(sit):
    down, d = sit['down'], sit['distance'] * YD
    x = d / max(4 - down, 1) * max(0.5 * down, 1)
    c = curve(CURVE_TARGET, x)
    # T = round_half_away(c + u), u ~ U(-1, 1); all values >= -1 so rounding is floor(v + 0.5) for v >= 0
    probs = {}
    import math
    lo, hi = c - 1, c + 1
    k = math.floor(lo + 0.5) if lo >= 0 else -math.floor(-lo + 0.5)
    for k in range(int(math.floor(lo)) - 1, int(math.ceil(hi)) + 2):
        a, b = max(lo, k - 0.5), min(hi, k + 0.5)
        if b > a:
            kk = min(10, max(0, k))
            probs[kk] = probs.get(kk, 0) + (b - a) / 2.0
    return probs


class Book:
    def __init__(self, raw: bytes, special_forms=(), special_cats=()):
        self.raw = raw
        body = raw[32:]
        self.book = ip.parse_playbook_resource(raw)
        self.cats = {}
        for c in self.book.categories:
            b4 = body[ip.CATEGORY_BASE + c.index * 16 + 4]
            self.cats[c.index] = dict(name=c.name.strip(), id=b4 & 0x3F, flag=b4 & 0xC0,
                                      personnel=personnel_label(body[ip.CATEGORY_BASE + c.index * 16 + 5:
                                                                     ip.CATEGORY_BASE + c.index * 16 + 16]))
        self.forms = []
        for f in self.book.formations:
            fl = struct.unpack_from('<I', body, ip.FORMATION_BASE + f.index * ip.FORMATION_SIZE + 4)[0]
            aux = ip.FORMATION_AUX_BASE + f.index * ip.FORMATION_AUX_SIZE
            own, mask = struct.unpack_from('<II', body, aux + 0x48)
            self.forms.append(dict(index=f.index, name=f.name.strip(), flags=fl, own=own & 0x3F, mask=mask,
                                   type=(fl >> 8) & 0x3F))
        self.special_forms = set(special_forms)
        self.special_cats = set(special_cats)

    def set_flags(self, index, flags):
        self.forms[index]['flags'] = flags

    def members(self, ci):
        return [f for f in self.forms if f['mask'] >> ci & 1 or (f['own'] == ci and self.cats[ci]['flag'] == 0x40)]

    def distribution(self, sit):
        tdist = target_dist(sit)
        pcat, pform = {}, {}
        cand = [ci for ci, c in self.cats.items() if c['id'] <= 10 and ci not in self.special_cats and self.members(ci)]
        means = {}
        for ci in cand:
            mem = self.members(ci)
            means[ci] = sum(form_weight(f['flags'], sit, 'B') for f in mem) / len(mem)
        for T, pt in tdist.items():
            w = {}
            for ci in cand:
                dist = abs(self.cats[ci]['id'] - T)
                if sit['down'] < 3:
                    dist *= 0.5
                w[ci] = (curve(CURVE_DIST, dist) * means[ci]) ** 3
            tot = sum(w.values())
            for ci, v in w.items():
                pcat[ci] = pcat.get(ci, 0) + pt * v / tot
        for ci, p in pcat.items():
            fs = [f for f in self.forms if f['mask'] >> ci & 1 and f['index'] not in self.special_forms
                  and not f['flags'] & 0x40000000 and f['type'] < 4]
            owners = [f for f in fs if f['own'] == ci]
            if any(f['own'] == ci for f in self.forms if f['index'] not in self.special_forms):
                fs = owners
            ws = {f['index']: form_weight(f['flags'], sit, 'A') for f in fs}
            tot = sum(ws.values())
            for fi, v in ws.items():
                pform[fi] = pform.get(fi, 0) + p * v / tot if tot else 0
        return pcat, pform, means


SPECIAL_NAMES = {"Hail Mary", "Clock", "Prevent"}
CLASS = {0: "heavy", 1: "heavy", 2: "22", 3: "12", 4: "21", 6: "11", 7: "20", 8: "01", 9: "10", 10: "00"}


def book_from(raw: bytes) -> Book:
    """Special formations by name (0x204C80 picks the Clock / Hail Mary / Prevent records)."""
    bk = Book(raw)
    bk.special_forms = {f["index"] for f in bk.forms if f["name"] in SPECIAL_NAMES}
    # 0x204C80 also takes the special formations' categories out of the lottery when nothing else plays
    # in them (v0.5's Jokers held only the Clock formation)
    bk.special_cats = {ci for ci in bk.cats if bk.members(ci)
                       and all(f["index"] in bk.special_forms for f in bk.members(ci))}
    return bk


def personnel_label(codes) -> str | None:
    """'11', '12', ... from a category's eleven position codes (kinds: 8 TE, 9 WR, 10 HB, 11 FB); None for
    non-offense groups. b77 p6s: twins (e.g. 11 personnel at lottery code 9) are labelled by who plays."""
    kinds = [c & 31 for c in codes]
    if kinds.count(9) + kinds.count(8) + kinds.count(10) + kinds.count(11) != 5:
        return None
    return f"{kinds.count(10) + kinds.count(11)}{kinds.count(8)}"


def personnel_shares(bk: Book, sit: dict) -> dict:
    pcat, pform, _ = bk.distribution(sit)
    out = {}
    for ci, p in pcat.items():
        lab = bk.cats[ci].get("personnel")
        key = {"23": "heavy", "32": "heavy", "13": "13"}.get(lab, lab) if lab else CLASS.get(bk.cats[ci]["id"], "other")
        out[key] = out.get(key, 0.0) + 100 * p
    return out


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("books", nargs="+", type=Path)
    args = ap.parse_args(argv)
    books = [book_from(p.read_bytes()) for p in args.books]
    for name, sit in SITUATIONS:
        mean, top = {}, []
        for bk in books:
            for k, v in personnel_shares(bk, sit).items():
                mean[k] = mean.get(k, 0.0) + v / len(books)
            _, pform, _ = bk.distribution(sit)
            top.append(100 * max(pform.values()) if pform else 0.0)
        line = " ".join(f"{k}:{v:.0f}" for k, v in sorted(mean.items(), key=lambda kv: -kv[1]) if v >= 0.5)
        print(f"{name:14s} {line} | busiest formation {max(top):.0f}%")


if __name__ == "__main__":
    main()
