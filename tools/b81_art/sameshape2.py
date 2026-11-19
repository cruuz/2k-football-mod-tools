"""Second half of the same-shape test. Clubs whose style 0 logo does not register to the pack's official mark: is the
helmet logo simply the retail art still in place (no second logo, so nothing can show beside it)? And one sheet of the
flagged texels of the registered clubs for an eye check."""
import sys, json, copy; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, fixtex, fixtex2, final
from scipy import ndimage
from PIL import Image, ImageDraw
rows = json.load(open(C.WORK.parent / 'out' / 'same_shape.json'))
def inkmask(rgb, fam):
    z = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]; z2 = z.copy(); z2[:, 142:] = False
    shell = np.median(rgb[z], axis=0)
    return (np.linalg.norm(rgb - shell, axis=2) > 40) & z2
out = []
for r in rows:
    if r['registered']: continue
    name = r['texture']; fam = name.split('_')[0]
    T = C.load(C.WORK.parent / 'out' / 'helmets' / f'{name}.png')[..., :3].astype(float)
    R = C.hretail(name)[..., :3].astype(float)
    v = np.zeros((256, 256), bool)
    if fam == 'helmet02':
        for m in fixtex.vent_regions(): v |= ndimage.binary_dilation(m, iterations=3)
    a = inkmask(T, fam) & ~v; b = inkmask(R, fam) & ~v
    u = a | b
    same = float((np.abs(T - R).max(axis=2)[u] < 24).mean()) if u.any() else 1.0
    iou = float((a & b).sum() / max(1, u.sum()))
    # best shift of the retail ink onto today's ink: a non-zero shift with a high overlap is a same shape at an offset
    best = (iou, 0, 0)
    for dy in range(-10, 11):
        for dx in range(-10, 11):
            s = np.roll(np.roll(b, dy, 0), dx, 1); i = (a & s).sum() / max(1, (a | s).sum())
            if i > best[0] + 1e-9: best = (float(i), dx, dy)
    r.update(retail_same=round(same, 3), retail_iou=round(iou, 3), best_shift=[best[1], best[2]], best_shift_iou=round(best[0], 3))
    out.append(r)
json.dump(rows, open(C.WORK.parent / 'out' / 'same_shape.json', 'w'), indent=1)
print('club tex  same-as-retail  iou  best-shift iou')
for r in out:
    print(r['club'], r['texture'][:8], r['retail_same'], r['retail_iou'], r['best_shift'], r['best_shift_iou'])
# eye sheet for the registered clubs that still flag
OV = copy.deepcopy(fixtex2.OVERRIDES); allk = sorted({f"{c}_0" for c in C.TEAMS}); OV['old_ink_reviewed'] = {'helmet02': allk, 'helmet00': allk}
tiles = []
for r in rows:
    if not r['registered'] or r['flagged_after'] <= 12: continue
    name = r['texture']; R = C.load(C.WORK.parent / 'out' / 'helmets' / f'{name}.png')
    saved = fixtex2.OVERRIDES; fixtex2.OVERRIDES = OV
    try: d = fixtex2.old_ink(name, R)
    finally: fixtex2.OVERRIDES = saved
    v = np.zeros((256, 256), bool)
    if name.startswith('helmet02'):
        for m in fixtex.vent_regions(): v |= ndimage.binary_dilation(m, iterations=2)
    fl = d['left'] & ~v
    ys, xs = np.nonzero(fl & (np.arange(256)[:, None] >= 128))
    if not len(ys): ys, xs = np.nonzero(fl)
    cx, cy = int(np.median(xs)), int(np.median(ys))
    ys2, xs2 = np.nonzero(d['foot'] & (np.arange(256)[:, None] >= 128))
    x0, x1 = max(0, min(xs.min(), xs2.min() if len(xs2) else 255) - 4), min(256, max(xs.max(), xs2.max() if len(xs2) else 0) + 5)
    y0, y1 = max(0, min(ys.min(), ys2.min() if len(ys2) else 255) - 4), min(256, max(ys.max(), ys2.max() if len(ys2) else 0) + 5)
    a = R[y0:y1, x0:x1, :3].copy(); b = a.copy(); b[fl[y0:y1, x0:x1]] = (255, 0, 255)
    im = Image.fromarray(C.hstack([C.up(a, 3), C.up(b, 3)], gap=2)); ImageDraw.Draw(im).text((2, 2), f"{r['club']} {name[:8]} {r['flagged_after']}", fill=(255, 255, 0))
    tiles.append(np.asarray(im))
if tiles:
    W = max(t.shape[1] for t in tiles); H = max(t.shape[0] for t in tiles)
    tiles = [np.pad(t, ((0, H - t.shape[0]), (0, W - t.shape[1]), (0, 0))) for t in tiles]
    if len(tiles) % 2: tiles.append(np.zeros_like(tiles[0]))
    Image.fromarray(np.concatenate([np.concatenate(tiles[i:i + 2], axis=1) for i in range(0, len(tiles), 2)], axis=0)).save(C.WORK / 'view_sameshape_flagged.png')
    print('sheet', len(tiles), W, H)
