import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import geom, cardlib as C, numpy as np, bljob, uvmap
sys.path.insert(0, str(C.WT / 'tools' / 'b77'))
import u1_cards as U
g, parts = geom.load_gltf('modern')
v = dict(U.LAYOUT['helmet']['view']); v.update(U.CAMERAS['helmet'])
pid, Uu, Vv, z = geom.raster(parts, uvmap.NAMES, v, 1024)
np.savez_compressed(C.WORK / 'uvmap_modern_unif_1024.npz', pid=pid, U=Uu, V=Vv, z=z)
print([(n, int((pid == k).sum())) for k, n in enumerate(uvmap.NAMES)])
# check against a rendered layer's alpha
import post
from pathlib import Path
p = C.WORK / 'bl' / 'r' / 'old' / '00H0_unif.png'
if p.exists():
    a = post.layer256(p)[..., 3]; cov = (pid >= 0).reshape(256, 4, 256, 4).mean(axis=(1, 3))
    print('soft IoU', np.minimum(a, cov).sum() / np.maximum(a, cov).sum())
