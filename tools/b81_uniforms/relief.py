#!/usr/bin/env python3
"""relief.py OUT.png SCALE NORMALMAP.png [...] : show tangent-space relief maps as lit surfaces (light from the upper left, R = +u,
G = up), side by side, so wrinkles, mesh holes, seams and embossed marks can be read."""
import sys
import numpy as np
from PIL import Image
out, scale = sys.argv[1], float(sys.argv[2]); ims = []
L = np.array([-0.55, 0.55, 0.63]); L /= np.linalg.norm(L)
for p in sys.argv[3:]:
    a = np.asarray(Image.open(p).convert('RGB')).astype(np.float64) / 127.5 - 1.0
    n = a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9)
    s = np.clip((n * L).sum(-1), 0, 1) ** 0.9
    im = Image.fromarray((40 + 215 * s / max(L[2], 1e-6) * 0.62).clip(0, 255).astype(np.uint8))
    ims.append(im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS))
W = sum(i.width for i in ims) + 6 * (len(ims) - 1); H = max(i.height for i in ims)
o = Image.new('L', (W, H), 0); x = 0
for i in ims: o.paste(i, (x, 0)); x += i.width + 6
o.save(out); print(out, o.size)
