#!/usr/bin/env python3
"""A transient-free ESPN bar reference: per-pixel temporal median over many frames.

frame_012001 alone carries a moving specular sweep across the bar's top edge, so a
single-frame spec bakes in a highlight that is not part of the design. This takes the
median of the bar rectangle over every Nth frame that actually has the bar up.

  python3 espn_bar_temporal_median.py <out_dir> [step]
Writes espn_bar_median.png (1041x110 source pixels) and prints the design profiles.
"""
import sys
from pathlib import Path
from PIL import Image
import numpy as np

OUT = Path(sys.argv[1]); step = int(sys.argv[2]) if len(sys.argv) > 2 else 60
FRAMES = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames')
BOX = (437, 942, 1478, 1052)
names = sorted(FRAMES.glob('frame_*.jpg'))[::step]
stack = []
for p in names:
    a = np.asarray(Image.open(p).convert('RGB').crop(BOX), dtype=np.uint8)
    # the bar is present when the charcoal body column x=1230 is dark and neutral
    col = a[40:100, 1230 - 437].astype(float)
    if col.mean() < 70 and (col.max(-1) - col.min(-1)).mean() < 12:
        stack.append(a)
print(f'{len(stack)} of {len(names)} sampled frames carry the bar', file=sys.stderr)
med = np.median(np.stack(stack), axis=0)
Image.fromarray(med.astype('uint8')).save(OUT / 'espn_bar_median.png')

def show(title, values):
    print(title)
    for k, v in values:
        print(' ', k, [round(float(x), 1) for x in v])

show('body column, source x=1230 (design, no specular):',
     [(y, med[y - 942, 1230 - 437]) for y in range(942, 1053, 4)])
show('body column, source x=700:',
     [(y, med[y - 942, 700 - 437]) for y in range(942, 1053, 8)])
show('away wing row, source y=1046:',
     [(x, med[1046 - 942, x - 437]) for x in range(437, 665, 16)])
show('home wing row, source y=1046:',
     [(x, med[1046 - 942, x - 437]) for x in range(1265, 1479, 16)])
print('body flat rgb  ', [round(float(v), 1) for v in med[50:95, 1200:1250].reshape(-1, 3).mean(0)])
print('top rim rgb y942-944', [round(float(v), 1) for v in med[0:3, 700 - 437:820 - 437].reshape(-1, 3).mean(0)])
print('row y945-950   ', [round(float(v), 1) for v in med[3:9, 700 - 437:820 - 437].reshape(-1, 3).mean(0)])
print('bottom rim y1048-1051', [round(float(v), 1) for v in med[106:110, 700 - 437:820 - 437].reshape(-1, 3).mean(0)])
