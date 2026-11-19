"""Detector for outline-only or colour-inverted logos: helmet textures whose side logo is mostly one-texel lines of a
single colour on the shell (the line stair-steps in game and on the cards)."""
import sys, json, glob, os; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, fixtex, final
from scipy import ndimage
def scan(name, T):
    fam = name.split('_')[0]; rgb = T[..., :3].astype(np.float64)
    hw = texdet.hardware(fam)[0].copy()
    if fam == 'helmet02':
        for v in fixtex.vent_regions(): hw |= ndimage.binary_dilation(v, iterations=3)
    z = texdet.zone_mask(fam) & ~hw; z[:, 142:] = False
    shell = np.median(rgb[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
    ink = z & (np.linalg.norm(rgb - shell, axis=2) > 40.0)
    if ink.sum() < 250: return None
    # texels of lines one or two texels wide: ink that a 3x3 opening removes
    thin = ink & ~ndimage.binary_opening(ink, structure=np.ones((3, 3), bool))
    # hard edges: share of ink texels with a plain-shell 4-neighbour and no blended texel between (no anti-aliasing)
    dev = np.linalg.norm(rgb - shell, axis=2)
    blend = z & (dev > 12.0) & (dev <= 40.0)
    edge = ink & ndimage.binary_dilation(z & (dev <= 12.0), structure=ndimage.generate_binary_structure(2, 1))
    return dict(texture=name, ink=int(ink.sum()), thin_share=round(float(thin.sum()) / float(ink.sum()), 3),
                hard_edge_share=round(float(edge.sum()) / float(ink.sum()), 3), blended=int(blend.sum()))
if __name__ == '__main__':
    rows = []
    src = C.WORK.parent / 'out' / 'helmets_assigned'
    for p in sorted(glob.glob(str(src / 'helmet0?_*H*.png'))):
        n = os.path.basename(p)[:-4]
        r = scan(n, final.helmet(n))
        if r: rows.append(r)
    json.dump(rows, open(C.WORK.parent / 'out' / 'outline_scan.json', 'w'), indent=1)
    for r in sorted(rows, key=lambda r: -r['thin_share'])[:16]: print(C.TEAMS[r['texture'][9:11]], r)
