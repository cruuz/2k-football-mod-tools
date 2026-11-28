"""Texture-level detector v3: ink in the side panels outside the registered official logo, split into ink that the
retail decal explains (old logo left behind) and other ink (flags, shields, stripes, anything else)."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, texdet2, reg
from scipy import ndimage
from PIL import Image, ImageDraw
REG = None
def regs():
    global REG
    if REG is None: REG = json.load(open(C.WORK / 'reg_results.json'))
    return REG
def footprint(name, grow=1, min_good=0.35):
    """Official-logo footprint of both panels (alpha > 0.04, grown), or None for a panel that did not register."""
    code = name.split('_')[1][:2]
    r = regs().get(name)
    foot = np.zeros((256, 256), bool); ok = {}
    if r is None: return foot, ok
    for panel, v in r.items():
        ok[panel] = v['good'] >= min_good
        if not ok[panel]: continue
        col, al = reg.resized(reg.ORI[v['ori']](reg.official(code)), v['w'], v['h'])
        m = np.zeros((256, 256), bool); m[v['y0']:v['y0']+v['h'], v['x0']:v['x0']+v['w']] = al > 0.04
        foot |= m
    if grow: foot = ndimage.binary_dilation(foot, iterations=grow)
    return foot, ok
def analyse(name):
    a = texdet2.analyse(name)
    foot, ok = footprint(name)
    panel_ok = np.zeros((256, 256), bool)
    for panel, good in ok.items():
        if good:
            x0, y0, x1, y1 = reg.PANELS[panel]; panel_ok[y0:y1, x0:x1] = True
    out_ink = a['ink'] & ~foot & panel_ok
    old = out_ink & a['exp']
    other = out_ink & ~a['exp']
    return dict(a, foot=foot, ok=ok, old=old, other=other, n_old=int(old.sum()), n_other=int(other.sum()))
def pair(name, box=(8,124,146,238), s=3):
    a = analyse(name)
    cur = C.hcur(name)[..., :3]
    x0,y0,x1,y1 = box
    crop = cur[y0:y1, x0:x1]
    mk = crop.copy()
    edge = a['foot'] ^ ndimage.binary_erosion(a['foot'])
    mk[a['other'][y0:y1, x0:x1]] = (0, 255, 255)
    mk[a['old'][y0:y1, x0:x1]] = (255, 0, 255)
    mk2 = C.up(mk, s)
    e = C.up(edge[y0:y1, x0:x1].astype(np.uint8)[..., None].repeat(3, 2) * 255, s)[..., 0] > 0
    # thin the edge marking to one screen pixel in three
    yy, xx = np.nonzero(e); sel = ((yy % s) == 1) & ((xx % s) == 1); mk2 = mk2.copy(); mk2[yy[sel], xx[sel]] = (0, 255, 0)
    t = C.hstack([C.up(crop, s), mk2], gap=2)
    im = Image.fromarray(t); d = ImageDraw.Draw(im)
    d.text((3, 2), f"{name[6:]} {C.TEAMS[name[9:11]]} old={a['n_old']} other={a['n_other']} reg={a['ok']}", fill=(255,255,0))
    return np.asarray(im)
def sheet(names, cols, out):
    tiles = [pair(n) for n in names]
    rows = [C.hstack(tiles[i:i+cols], gap=8) for i in range(0, len(tiles), cols)]
    W = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0,6),(0,W-r.shape[1]),(0,0))) for r in rows]
    Image.fromarray(np.concatenate(rows, axis=0)).save(out)
if __name__ == '__main__':
    names = sys.argv[2:]
    sheet(names, 3, C.WORK / sys.argv[1])
