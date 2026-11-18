import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import geom, cardlib as C, numpy as np, time
from PIL import Image
NAMES = ['HI_HELMET_C','LOGO_helmet_C','HELMET_C_accessories','FACEMASK12']
def build(mode='modern', size=1024):
    g, parts = geom.load_gltf(mode)
    out = {}
    for side in 'HA':
        t=time.time()
        pid, U, V, zb = geom.raster(parts, NAMES, geom.view_for(side), size)
        out[side] = (pid, U, V, zb)
        np.savez_compressed(C.WORK / f'uvmap_{mode}_{side}_{size}.npz', pid=pid, U=U, V=V, z=zb)
        print(mode, side, time.time()-t, [(n, int((pid==k).sum())) for k,n in enumerate(NAMES)])
    return out
if __name__ == '__main__':
    m = build('modern', 1024)
    for side, card in (('H','helm_h00_0_256'),('A','helm_a00_0_256')):
        pid = m[side][0]
        cov = (pid >= 0).reshape(256,4,256,4).mean(axis=(1,3))
        c = C.cur(card)
        al = c[...,3].astype(float)/255
        al[158:] = 0; cov2 = cov.copy(); cov2[158:] = 0
        inter = np.minimum(al, cov2).sum(); union = np.maximum(al, cov2).sum()
        print(side, 'soft IoU', inter/union, 'card alpha px', (al>0.5).sum(), 'raster px', (cov2>0.5).sum())
        vis = np.zeros((256,256,3), np.uint8); vis[...,0] = (al*255).astype(np.uint8); vis[...,1] = (cov2*255).astype(np.uint8)
        Image.fromarray(C.up(vis,3)).save(C.WORK / f'view_sil_{side}.png')
