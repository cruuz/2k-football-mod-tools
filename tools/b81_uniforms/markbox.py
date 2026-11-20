#!/usr/bin/env python3
"""markbox.py TEXTURE.png X0 Y0 X1 Y1 [TOL] : list the marks painted inside a box of a kit texture (native texels).
A mark = a connected group of texels whose colour differs from the box's most common colour by more than TOL
(default 36 levels in any channel). Prints each group's box (x0 y0 x1 y1, x1/y1 exclusive), width, height, texel count
and mean colour, largest first. Use it to get exact game-side boxes instead of reading them off an enlarged crop."""
import sys
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
im = np.asarray(Image.open(sys.argv[1]).convert('RGB')).astype(int)
x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6]); tol = int(sys.argv[6]) if len(sys.argv) > 6 else 36
reg = im[y0:y1, x0:x1]
cols, counts = np.unique(reg.reshape(-1, 3), axis=0, return_counts=True); base = cols[counts.argmax()]
m = np.abs(reg - base).max(-1) > tol
lab, n = ndi.label(m, structure=np.ones((3, 3)))
out = []
for i, sl in enumerate(ndi.find_objects(lab), 1):
    sel = lab[sl] == i; c = reg[sl][sel].mean(0)
    out.append((int(sel.sum()), x0 + sl[1].start, y0 + sl[0].start, x0 + sl[1].stop, y0 + sl[0].stop, c))
print('base colour #%02X%02X%02X' % tuple(base))
for cnt, a, b, c, d, col in sorted(out, key=lambda t: -t[0])[:12]:
    if cnt >= 4:
        print(f'box {a} {b} {c} {d}  w {c - a} h {d - b}  texels {cnt}  mean #%02X%02X%02X' % tuple(int(v) for v in col))
