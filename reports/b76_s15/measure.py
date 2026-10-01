"""Beta 76 s15: measure the 2026 ESPN bar's record tab, possession chevron and timeout pips (read-only frames).

The frames are Noah's off-air recording and the highlight reel of the 2026 MNF Giants at Rams game (week 2), plus
the full Broncos at Chiefs game (week 1), all 1920x1080 and never copied into the repository. This script writes
only derived numbers: ``reports/b76_s15/broadcast_marks.json``.

    python3 reports/b76_s15/measure.py --mnf <frames> --obs <frames> --denkc <frames_1s> [--workers 16]

Measured:
* chevron: which score it sits over on every bar frame, its median shape, and a 22x7 RGBA texel map of it (alpha and
  colour solved against the same pixels on frames where the other team has the ball);
* record tab: its navy and its box, from the median of the Giants at Rams frames;
* week 1: whether any Broncos at Chiefs bar frame carries a record (a positive control on Giants at Rams);
* timeout pips: the lit and used colours and the order in which pips dim.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/b76_s15/broadcast_marks.json'
HARVEST = Path('/home/noah/2k-worktrees/b76-s12/reports/b76_s12/harvest.json')
AWAY_SCORE_X, HOME_SCORE_X = 756, 1159            # broadcast score centres (s12 harvest boxes)
PIPS = {'away': (717, 747, 777), 'home': (1120, 1150, 1180)}
CHEVRON_BOX = (721.5, 943.0, 787.5, 962.0)          # glyph box at 1080p, away side
CHEVRON_TEXELS = (22, 7)                              # 3 px per texel across (one 16:9 HUD column), 7.9 HUD rows down


def luma(a):
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def load(path):
    return np.asarray(Image.open(path).convert('RGB')).astype(np.float32)


def bar_present(a):
    L = luma(a)
    return float(L[1012:1030, 905:918].mean()) > 200 and 25 < float(L[1000:1030, 700:712].mean()) < 60


def chevron_side(a):
    """1 away, 2 home, 3 both, 0 none: the chevron's core against the rim beside it (bimodal: ~200 or ~0)."""
    L = luma(a)

    def contrast(cx):
        core = L[949:954, cx - 10:cx + 11].mean()
        side = np.concatenate([L[949:954, cx - 40:cx - 28].ravel(), L[949:954, cx + 28:cx + 40].ravel()]).mean()
        return float(core - side)
    away, home = contrast(AWAY_SCORE_X - 2), contrast(HOME_SCORE_X - 2)
    return int(away > 100) | (int(home > 100) << 1)


def record_ink(a):
    """White text pixels in each record corner (the tab holds 'W-L' on a record frame)."""
    L = luma(a)
    return int((L[1027:1044, 446:480] > 200).sum()), int((L[1027:1044, 1440:1476] > 200).sum())


def pip_levels(a):
    return {side: [float(luma(a[1033:1039, x + 2:x + 16]).mean()) for x in xs] for side, xs in PIPS.items()}


def frame_row(path):
    a = load(path)
    bar = bar_present(a)
    row = dict(path=str(path), bar=bar)
    if bar:
        row.update(chevron=chevron_side(a), ink=record_ink(a), pips=pip_levels(a))
    return row


def scan(paths, workers):
    with ProcessPoolExecutor(workers) as pool:
        return list(pool.map(frame_row, paths, chunksize=24))


def median(paths, rows, cols):
    return np.median(np.stack([load(p)[rows[0]:rows[1], cols[0]:cols[1]] for p in paths]), axis=0)


def chevron_cell(with_away, with_home):
    """Solve alpha and colour of the chevron: fg = alpha*C + (1-alpha)*bg, with bg the same pixels when the other
    team has the ball. Alpha from luma against the core's white; colour per pixel where alpha is meaningful. The
    away and home solutions are averaged (403 px apart), then area-filtered to the texel grid in premultiplied form."""
    fields = []
    for fg, bg, x0 in ((with_away, with_home, AWAY_SCORE_X - 38), (with_home, with_away, HOME_SCORE_X - 38)):
        f, b = fg[:, x0:x0 + 76], bg[:, x0:x0 + 76]
        core = 251.0
        alpha = np.clip((luma(f) - luma(b)) / np.maximum(core - luma(b), 1.0), 0.0, 1.0)
        colour = np.where(alpha[..., None] > 0.05,
                          (f - (1 - alpha[..., None]) * b) / np.maximum(alpha[..., None], 0.05), 255.0)
        fields.append((alpha, np.clip(colour, 0, 255)))
    alpha = (fields[0][0] + fields[1][0]) / 2
    premultiplied = (fields[0][0][..., None] * fields[0][1] + fields[1][0][..., None] * fields[1][1]) / 2
    # Crop to the glyph box (rows from 930, columns from AWAY_SCORE_X-38) and area-filter to the texels.
    x0, y0, x1, y1 = CHEVRON_BOX
    tw, th = CHEVRON_TEXELS
    ox, oy = AWAY_SCORE_X - 38, 930
    out = np.zeros((th, tw, 4))
    for ty in range(th):
        for tx in range(tw):
            ax0, ax1 = x0 + (x1 - x0) * tx / tw - ox, x0 + (x1 - x0) * (tx + 1) / tw - ox
            ay0, ay1 = y0 + (y1 - y0) * ty / th - oy, y0 + (y1 - y0) * (ty + 1) / th - oy
            wsum, asum, csum = 0.0, 0.0, np.zeros(3)
            for py in range(int(np.floor(ay0)), int(np.ceil(ay1))):
                wy = min(ay1, py + 1) - max(ay0, py)
                for px in range(int(np.floor(ax0)), int(np.ceil(ax1))):
                    w = wy * (min(ax1, px + 1) - max(ax0, px))
                    if w <= 0:
                        continue
                    wsum += w
                    asum += w * alpha[py, px]
                    csum += w * premultiplied[py, px]
            a = asum / wsum
            out[ty, tx, 3] = a
            out[ty, tx, :3] = csum / wsum / a if a > 1e-3 else 255.0
    return [[[int(round(v)) for v in (*px[:3], px[3] * 255)] for px in row] for row in out]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--mnf', type=Path, required=True)
    parser.add_argument('--obs', type=Path, required=True)
    parser.add_argument('--denkc', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=16)
    args = parser.parse_args(argv)
    mnf = sorted(args.mnf.glob('*.png')) + sorted(args.obs.glob('*.png'))
    denkc = sorted(args.denkc.glob('*.jpg'))
    rows = scan(mnf, args.workers)
    week1 = scan(denkc, args.workers)
    bars = [r for r in rows if r['bar']]
    week1_bars = [r for r in week1 if r['bar']]

    def count(rs, value):
        return sum(r['chevron'] == value for r in rs)
    away = [Path(r['path']) for r in bars if r['chevron'] == 1]
    home = [Path(r['path']) for r in bars if r['chevron'] == 2]
    with_away = median(away[::max(1, len(away) // 150)][:150], (930, 975), (0, 1920))
    with_home = median(home[::max(1, len(home) // 150)][:150], (930, 975), (0, 1920))
    shape = {}
    for name, image, cx in (('away', with_away, AWAY_SCORE_X), ('home', with_home, HOME_SCORE_X)):
        L = luma(image)
        rows_ = []
        for y in range(946, 958):
            idx = np.nonzero(L[y - 930, cx - 40:cx + 40] >= 200)[0]
            if len(idx):
                rows_.append(dict(y=y, x0=int(cx - 40 + idx.min()), x1=int(cx - 40 + idx.max()),
                                  centre=float(cx - 40 + (idx.min() + idx.max()) / 2)))
        shape[name] = rows_
    core = with_away[952 - 930, AWAY_SCORE_X - 6:AWAY_SCORE_X + 7].mean(0)
    edge = with_away[948 - 930, AWAY_SCORE_X - 16:AWAY_SCORE_X + 16].mean(0)

    tab_frames = [Path(r['path']) for r in bars if r['ink'][0] > 30][:300:3]
    tab_away = median(tab_frames, (1015, 1052), (435, 500))
    tab_home = median(tab_frames, (1015, 1052), (1420, 1485))
    navy = np.concatenate([tab_away[1029 - 1015:1042 - 1015, 443 - 435:449 - 435].reshape(-1, 3),
                           tab_home[1029 - 1015:1042 - 1015, 1473 - 1420:1477 - 1420].reshape(-1, 3)])
    lit, used, states = [], [], {}
    for r in bars + week1_bars:
        for side, levels in r['pips'].items():
            key = ''.join('W' if v > 180 else 'g' if 55 < v < 110 else '?' for v in levels)
            states[key] = states.get(key, 0) + 1
    for r in bars[::7]:
        a = load(r['path'])
        for side, xs in PIPS.items():
            for x in xs:
                c = a[1033:1039, x + 2:x + 16].reshape(-1, 3).mean(0)
                (lit if luma(c) > 180 else used if 55 < luma(c) < 110 else []).append(c)
    document = dict(
        schema='b76-s15-broadcast-marks/v1',
        sources=dict(mnf=str(args.mnf), obs=str(args.obs), denkc=str(args.denkc), read_only=True,
                     note='Frames are evidence only; nothing here is a frame.'),
        frames=dict(nyg_lar=len(rows), nyg_lar_bar=len(bars), den_kc_week1=len(week1), den_kc_week1_bar=len(week1_bars)),
        chevron=dict(
            counts=dict(nyg_lar=dict(away=count(bars, 1), home=count(bars, 2), none=count(bars, 0), both=count(bars, 3)),
                        den_kc=dict(away=count(week1_bars, 1), home=count(week1_bars, 2), none=count(week1_bars, 0),
                                    both=count(week1_bars, 3))),
            rows_at_or_above_200=shape,
            core_rgb=[round(float(v), 1) for v in core], top_edge_rgb=[round(float(v), 1) for v in edge],
            glyph_box=list(CHEVRON_BOX), texels=list(CHEVRON_TEXELS), cell_rgba=chevron_cell(with_away, with_home),
            home_offset_px=round(float(np.mean([r['centre'] for r in shape['home']]) -
                                       np.mean([r['centre'] for r in shape['away']])), 2),
            frames_used=dict(away=min(150, len(away)), home=min(150, len(home)))),
        record_tab=dict(
            navy_rgb=[round(float(v), 1) for v in np.median(navy, axis=0)], rows=[1026, 1048],
            away_left=442, home_right=1477, text_ink_nyg_lar=dict(away=[451, 476], home=[1447, 1473], rows=[1029, 1042]),
            frames_used=len(tab_frames),
            week1_den_kc_frames_with_record_ink=sum(r['ink'][0] > 30 or r['ink'][1] > 30 for r in week1_bars),
            nyg_lar_frames_with_record_ink=sum(r['ink'][0] > 30 and r['ink'][1] > 30 for r in bars)),
        timeouts=dict(
            lit_rgb=[round(float(v), 1) for v in np.median(np.array(lit), axis=0)],
            used_rgb=[round(float(v), 1) for v in np.median(np.array(used), axis=0)],
            states=dict(sorted(states.items(), key=lambda kv: -kv[1])),
            order='used pips dim from the right: WWW, WWg, Wgg, ggg'),
    )
    OUT.write_text(json.dumps(document, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(OUT)


if __name__ == '__main__':
    raise SystemExit(main())
