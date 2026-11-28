import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np
from PIL import Image
_maps = {}
def uvmap(side, mode='modern', size=1024):
    k=(side,mode,size)
    if k not in _maps:
        d=np.load(C.WORK/f'uvmap_{mode}_{side}_{size}.npz'); _maps[k]=(d['pid'],d['U'],d['V'],d['z'])
    return _maps[k]
def bilinear(tex, U, V):
    """tex HxWxC float, U,V in 0..1 (top-left origin, texel centres at (i+0.5)/N), repeat wrap."""
    h, w = tex.shape[:2]
    x = U * w - 0.5; y = V * h - 0.5
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[..., None]; fy = (y - y0)[..., None]
    def at(yy, xx): return tex[yy % h, xx % w]
    return (at(y0, x0)*(1-fx)*(1-fy) + at(y0, x0+1)*fx*(1-fy) + at(y0+1, x0)*(1-fx)*fy + at(y0+1, x0+1)*fx*fy)
def flat(tex_rgba, side, facemask=(128,128,128), size=1024, mode='modern'):
    pid, U, V, z = uvmap(side, mode, size)
    t = tex_rgba.astype(np.float64)
    s = bilinear(t, U, V)
    out = np.zeros((size, size, 4))
    tex_part = (pid >= 0) & (pid <= 2)
    out[tex_part, :3] = s[tex_part, :3]; out[tex_part, 3] = 255
    # LOGO_helmet_C and accessories are alpha CLIP in the card render (alpha < 0.5 -> hole)
    fm = pid == 3
    out[fm, :3] = facemask; out[fm, 3] = 255
    return out, pid, s
def reduce(a, f):
    h, w = a.shape[:2]
    return a.reshape(h//f, f, w//f, f, -1).mean(axis=(1,3))
if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else '00H0'
    side = name[2]
    tex = C.hcur(f'helmet02_{name}')
    out, pid, s = flat(tex, side)
    card = C.cur(f"helm_{side.lower()}{name[:2]}_{name[3:]}_256")
    f256 = reduce(out, 4)
    cols = np.array([[200,200,200],[255,0,0],[0,160,255],[255,220,0]])
    pv = np.zeros((1024,1024,3)); 
    for k in range(4): pv[pid==k] = cols[k]
    pv = reduce(pv,4)
    Image.fromarray(C.hstack([C.up(C.over(card),3), C.up(C.over(np.clip(f256+0.5,0,255).astype(np.uint8)),3), C.up(pv.astype(np.uint8),3)])).save(C.WORK/f'view_flat_{name}.png')
