import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import geom, cardlib as C, numpy as np, flat
from PIL import Image
NAMES = ['HI_HELMET_C','LOGO_helmet_C','HELMET_C_accessories','FACEMASK12']
VIEWS = {
 'side_L': {"yaw": 90, "pitch": 5, "roll": 0, "dist": 1.0, "target": [0, -0.03, 0.79], "fov": 22},
 'top':    {"yaw": 90, "pitch": 80, "roll": 0, "dist": 1.0, "target": [0, -0.03, 0.79], "fov": 22},
 'rear34': {"yaw": 150, "pitch": 25, "roll": 0, "dist": 1.0, "target": [0, -0.03, 0.79], "fov": 22},
 'front34':{"yaw": 40, "pitch": 15, "roll": 0, "dist": 1.0, "target": [0, -0.03, 0.79], "fov": 22},
}
_cache = {}
def maps(mode='modern', size=512):
    key=(mode,size)
    if key in _cache: return _cache[key]
    f = C.WORK/f'viewmaps_{mode}_{size}.npz'
    if f.exists():
        d = np.load(f); out = {k: (d[k+'_pid'], d[k+'_U'], d[k+'_V']) for k in VIEWS}
    else:
        g, parts = geom.load_gltf(mode); out = {}; save = {}
        for k, v in VIEWS.items():
            pid, U, V, z = geom.raster(parts, NAMES, v, size)
            out[k] = (pid, U, V); save[k+'_pid']=pid; save[k+'_U']=U; save[k+'_V']=V
        np.savez_compressed(f, **save)
    _cache[key] = out
    return out
def render(tex, mark_details=None, facemask=(120,120,120), mode='modern', size=512, bg=(128,128,128)):
    tiles = []
    t = tex.astype(np.float64)
    for k, (pid, U, V) in maps(mode, size).items():
        s = flat.bilinear(t, U, V)
        img = np.zeros((size, size, 3)); img[:] = bg
        m = (pid >= 0) & (pid <= 2); img[m] = s[m, :3]
        img[pid == 3] = facemask
        if mark_details is not None:
            d = pid == 1
            img[d] = img[d]*(1-mark_details) + np.array([255, 0, 0])*mark_details
        tiles.append(np.clip(img, 0, 255).astype(np.uint8))
    return tiles
if __name__ == '__main__':
    name = sys.argv[1]
    tex = C.hcur(name)
    a = render(tex); b = render(tex, mark_details=0.6)
    Image.fromarray(np.concatenate([C.hstack(a), C.hstack(b)], axis=0)).save(C.WORK/f'view_multi_{name}.png')
