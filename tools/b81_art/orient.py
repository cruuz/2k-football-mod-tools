"""Orientation test for every helmet texture: the right-side (upper island) logo must be the left side's mirror image
about the atlas axis. Flags a right-side logo that is the same way up as the left one, turned half round, or mirrored
left-right instead (in game: upside down or reading backwards on the right side of the helmet)."""
import sys, json, glob, os; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, fixes7
from PIL import Image
def test(name, T):
    fam = name.split('_')[0]; rgb = T[..., :3].astype(np.float64)
    try:
        (lx0, ly0, lx1, ly1), lk = fixes7.logo_box(rgb, fam, False, pad=0)
        (ux0, uy0, ux1, uy1), uk = fixes7.logo_box(rgb, fam, True, pad=0)
    except Exception:
        return None
    if lk.sum() < 150 or uk.sum() < 150: return None
    g = rgb @ np.array([0.3, 0.59, 0.11])
    L = g[ly0:ly1, lx0:lx1]; U = g[uy0:uy1, ux0:ux1]
    if abs(L.shape[0] - U.shape[0]) > 6 or abs(L.shape[1] - U.shape[1]) > 6: return dict(texture=name, verdict='different logos or sizes', lower=[int(v) for v in (lx0, ly0, lx1, ly1)], upper=[int(v) for v in (ux0, uy0, ux1, uy1)])
    Ur = np.asarray(Image.fromarray(U.astype(np.float32)).resize((L.shape[1], L.shape[0]), Image.BILINEAR)).astype(np.float64)
    if L.std() < 4 or Ur.std() < 4: return None
    c = {k: float(np.corrcoef(f(L).ravel(), Ur.ravel())[0, 1]) for k, f in (('mirror', lambda x: x[::-1]), ('same', lambda x: x), ('half_turn', lambda x: x[::-1, ::-1]), ('flip_lr', lambda x: x[:, ::-1]))}
    best = max(c, key=c.get)
    if best != 'mirror' and c[best] - c['mirror'] > 0.06:
        return dict(texture=name, verdict=best, corr={k: round(v, 3) for k, v in c.items()})
    return None
if __name__ == '__main__':
    src = C.WORK.parent / 'out' / 'helmets_assigned'
    out = []
    for p in sorted(glob.glob(str(src / 'helmet0?_*.png'))):
        r = test(os.path.basename(p)[:-4], C.load(p))
        if r: out.append(r)
    json.dump(out, open(C.WORK.parent / 'out' / 'orientation.json', 'w'), indent=1)
    for r in out: print(r['texture'], r['verdict'], r.get('corr', ''), r.get('lower', ''), r.get('upper', ''))
    print(len(out), 'flagged')
def relation(T, fam):
    """How the right-side logo relates to the left one: ('mirror' | 'half_turn' | 'same' | 'flip_lr' | None, scores)."""
    rgb = T[..., :3].astype(np.float64); g = rgb @ np.array([0.3, 0.59, 0.11])
    try:
        (lx0, ly0, lx1, ly1), lk = fixes7.logo_box(rgb, fam, False, pad=0)
        (ux0, uy0, ux1, uy1), uk = fixes7.logo_box(rgb, fam, True, pad=0)
    except Exception:
        return None, {}
    if lk.sum() < 150 or uk.sum() < 150: return None, {}
    if abs((ly1 - ly0) - (uy1 - uy0)) <= 8 and abs((lx1 - lx0) - (ux1 - ux0)) <= 8:
        L = g[ly0:ly1, lx0:lx1]; U = g[uy0:uy1, ux0:ux1]
        U = np.asarray(Image.fromarray(U.astype(np.float32)).resize((L.shape[1], L.shape[0]), Image.BILINEAR)).astype(np.float64)
    else:
        from scipy import ndimage
        def centre(k):
            ys, xs = np.nonzero(ndimage.binary_opening(k, iterations=1)); return int(round(np.median(xs))), int(round(np.median(ys)))
        (cx, cy), (dx, dy) = centre(lk), centre(uk)
        L = g[cy - 20:cy + 20, cx - 28:cx + 28]; U = g[dy - 20:dy + 20, dx - 28:dx + 28]
        if L.shape != (40, 56) or U.shape != (40, 56): return None, {}
    if L.std() < 4 or U.std() < 4: return None, {}
    c = {k: round(float(np.corrcoef(f(L).ravel(), U.ravel())[0, 1]), 3) for k, f in (('mirror', lambda x: x[::-1]), ('same', lambda x: x), ('half_turn', lambda x: x[::-1, ::-1]), ('flip_lr', lambda x: x[:, ::-1]))}
    return max(c, key=c.get), c
