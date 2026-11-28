#!/usr/bin/env python3
"""markmeasure.py PART X0 Y0 X1 Y1 : how large a box of a kit texture is on the player model, in game centimetres
(PART = jersey | sleeve | pants; box in native texels of torso.png 512x256, sleeve.png 128x128, pants.png 512x256).
Prints width and height on the body, and the box centre's place (x left(+)/right, y up, z front(+)/back).
The model's own number panels for scale: chest and back digit panels are printed by --numbers."""
import sys
import numpy as np
from pathlib import Path
UV = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/uvpos')
if sys.argv[1] == '--numbers':
    print(open(UV / 'number_panels.txt').read()); sys.exit()
part = {'jersey': 'UNIF_jersey', 'sleeve': 'UNIF_sleeve', 'pants': 'UNIF_pants'}[sys.argv[1]]
x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
d = np.load(UV / f'uvpos_{part}.npz'); pos, mask = d['pos'], d['mask']       # stored at 2x
def at(x, y):
    return pos[min(int(y * 2), pos.shape[0] - 1), min(int(x * 2), pos.shape[1] - 1)].astype(float)
def path(a, b, n=24):
    pts = [at(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]
    return float(sum(np.linalg.norm(pts[i + 1] - pts[i]) for i in range(n)))
cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
w = path((x0, cy), (x1, cy)); h = path((cx, y0), (cx, y1)); c = at(cx, cy)
print(f'{sys.argv[1]} box {x0},{y0},{x1},{y1}: width {w:.1f} cm, height {h:.1f} cm on the body; centre x {c[0]:.1f} y {c[1]:.1f} z {c[2]:.1f} ; {w / max(x1 - x0, 1):.2f} cm per texel across, {h / max(y1 - y0, 1):.2f} down')
