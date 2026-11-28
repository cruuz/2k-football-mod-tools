#!/usr/bin/env python3
"""Take a 2004 jersey relief map apart: where the open mesh is, and the sculpted folds without it.
bump_study.py RETAIL_BUMP.png OUTDIR  -> mesh_mask.png, folds.png (normal map: the sculpt with the mesh lifted out)"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
def split(path):
    a = np.asarray(Image.open(path).convert('RGB')).astype(np.float64) / 127.5 - 1.0
    xy = a[..., :2]
    # the mesh is a fine lattice (about 4 texels): what a 1.2 texel blur removes is almost only mesh and thin piping
    lo = np.stack([ndi.gaussian_filter(xy[..., i], 1.6) for i in range(2)], -1)
    hi = xy - lo
    energy = ndi.gaussian_filter((hi ** 2).sum(-1), 3.0)
    mesh = energy > 0.035
    mesh = ndi.binary_opening(mesh, iterations=2)
    lab, n = ndi.label(mesh)
    sizes = ndi.sum(mesh, lab, np.arange(1, n + 1))
    mesh = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 2500])        # the two panels, not a collar rib
    mesh = ndi.binary_fill_holes(ndi.binary_closing(mesh, iterations=3))
    return a, lo, hi, energy, mesh
if __name__ == '__main__':
    a, lo, hi, energy, mesh = split(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mesh * 255).astype(np.uint8)).save(out / 'mesh_mask.png')
    print('mesh texels', int(mesh.sum()), 'boxes', [tuple(int(v) for v in (s[1].start, s[0].start, s[1].stop, s[0].stop)) for s in ndi.find_objects(ndi.label(mesh)[0])])
    t = np.hypot(a[..., 0], a[..., 1]) * 127.5
    print('tilt inside mesh p50/p90', np.percentile(t[mesh], [50, 90]).round(1), 'outside (on the jersey)', np.percentile(t[~mesh & (t > 0.5)], [50, 90]).round(1))
    tl = np.hypot(lo[..., 0], lo[..., 1]) * 127.5
    print('low-pass tilt inside mesh p50/p90', np.percentile(tl[mesh], [50, 90]).round(1))
