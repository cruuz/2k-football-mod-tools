"""Register the official logo on a helmet texture panel: uniform scale + centre + orientation, by matched ink."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet
from PIL import Image
from scipy import ndimage
P8 = json.load(open(C.WORK/'p8_index.json'))
PANELS = {'upper': (8, 18, 146, 128), 'lower': (8, 128, 146, 238)}
ORI = {'id': lambda im: im, 'fh': lambda im: im.transpose(Image.FLIP_LEFT_RIGHT), 'fv': lambda im: im.transpose(Image.FLIP_TOP_BOTTOM),
       'r180': lambda im: im.rotate(180)}
_off = {}
def official(code):
    if code not in _off:
        k = [k for k in P8 if k.endswith(f':logo_{code}_0')][0]
        im = Image.open(P8[k][0]).convert('RGBA')
        a = np.asarray(im)
        ys, xs = np.nonzero(a[..., 3] > 8)
        _off[code] = im.crop((xs.min(), ys.min(), xs.max()+1, ys.max()+1))
    return _off[code]
_rz = {}
def resized(logo, w, h, key=None):
    if key is not None and (key, w, h) in _rz: return _rz[(key, w, h)]
    pre = np.asarray(logo, dtype=np.float64) / 255.0
    pre[..., :3] *= pre[..., 3:4]
    planes = [np.asarray(Image.fromarray(pre[..., c].astype(np.float32), 'F').resize((w, h), Image.LANCZOS), dtype=np.float64) for c in range(4)]
    s = np.clip(np.stack(planes, axis=-1), 0, 1)
    al = s[..., 3]
    col = np.where(al[..., None] > 1e-6, s[..., :3] / np.maximum(al[..., None], 1e-6), 0) * 255.0
    if key is not None: _rz[(key, w, h)] = (col, al)
    return col, al
def score_at(cur, col, al, x0, y0, tol=45.0, pen=0.6):
    h, w = al.shape
    if x0 < 0 or y0 < 0 or x0 + w > 256 or y0 + h > 256: return -1e9
    sub = cur[y0:y0+h, x0:x0+w]
    core = al > 0.9
    d = np.linalg.norm(sub - col, axis=2)
    return float((core & (d < tol)).sum() - pen * (core & (d >= tol)).sum())
def ink_centre(cur, fam, panel):
    hw = texdet.hardware(fam)[0]
    z = texdet.zone_mask(fam) & ~hw
    shell = np.median(cur[z], axis=0)
    x0, y0, x1, y1 = PANELS[panel]
    m = np.zeros((256, 256), bool); m[y0:y1, x0:x1] = True
    ink = m & z & (np.linalg.norm(cur - shell, axis=2) > 40)
    lab, n = ndimage.label(ink)
    if n == 0: return None
    sizes = ndimage.sum(ink, lab, np.arange(1, n + 1))
    big = lab == (1 + int(np.argmax(sizes)))
    ys, xs = np.nonzero(big)
    return (xs.min() + xs.max() + 1) / 2.0, (ys.min() + ys.max() + 1) / 2.0, xs.max() + 1 - xs.min(), ys.max() + 1 - ys.min()
def register(cur, logo, panel, fam, code, reach=9):
    x0p, y0p, x1p, y1p = PANELS[panel]
    c = ink_centre(cur, fam, panel)
    centres = [((x0p + x1p) / 2.0 - 1, (y0p + y1p) / 2.0)]
    if c is not None: centres.insert(0, (c[0], c[1]))
    best = (-1e9,)
    aspect = logo.height / logo.width
    for ori, fn in ORI.items():
        lg = fn(logo)
        for w in range(34, 118, 2):
            h = max(1, int(round(w * aspect)))
            if h > (y1p - y0p): continue
            col, al = resized(lg, w, h, key=(code, ori))
            seen = set()
            for cx, cy in centres:
                bx, by = int(round(cx - w / 2.0)), int(round(cy - h / 2.0))
                for y0 in range(by - reach, by + reach + 1):
                    for x0 in range(bx - reach, bx + reach + 1):
                        if (x0, y0) in seen: continue
                        seen.add((x0, y0))
                        s = score_at(cur, col, al, x0, y0)
                        if s > best[0]: best = (s, ori, w, h, x0, y0)
    s, ori, w, h, x0, y0 = best
    lg = ORI[ori](logo)
    for w2 in range(w - 2, w + 3):
        h2 = max(1, int(round(w2 * aspect)))
        for dh in (-1, 0, 1):
            col, al = resized(lg, w2, h2 + dh, key=(code, ori))
            for yy in range(y0 - 2, y0 + 3):
                for xx in range(x0 - 2, x0 + 3):
                    sc = score_at(cur, col, al, xx, yy)
                    if sc > best[0]: best = (sc, ori, w2, h2 + dh, xx, yy)
    s, ori, w, h, x0, y0 = best
    col, al = resized(ORI[ori](logo), w, h, key=(code, ori))
    full = np.zeros((256, 256)); full[y0:y0+h, x0:x0+w] = al
    core = int((al > 0.9).sum())
    sub = cur[y0:y0+h, x0:x0+w]
    good = float(((al > 0.9) & (np.linalg.norm(sub - col, axis=2) < 45)).sum()) / max(core, 1)
    return dict(score=s, ori=ori, w=w, h=h, x0=x0, y0=y0, core=core, good=round(good, 3)), full
def run(name):
    fam, rest = name.split('_'); code = rest[:2]
    cur = C.hcur(name)[..., :3].astype(float)
    lg = official(code)
    out = {}
    for panel in PANELS:
        r, full = register(cur, lg, panel, fam, code)
        out[panel] = r
    return name, out
if __name__ == '__main__':
    import multiprocessing as mp, time
    names = sorted(C.hindex()) if sys.argv[1] == 'all' else [n for n in sorted(C.hindex()) if any(n.startswith(p) for p in sys.argv[1:])]
    t = time.time()
    with mp.Pool(14) as pool:
        res = dict(pool.map(run, names, chunksize=2))
    json.dump(res, open(C.WORK / 'reg_results.json', 'w'), indent=1, sort_keys=True)
    print('done', len(res), round(time.time() - t, 1))
    for n in names:
        print(n, C.TEAMS[n[9:11]], {p: (v['good'], v['ori'], v['w'], v['h'], v['x0'], v['y0']) for p, v in res[n].items()})
