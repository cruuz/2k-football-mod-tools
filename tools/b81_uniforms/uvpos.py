#!/usr/bin/env python3
"""b81-uniforms: per-texel 3D position of the jersey / sleeve / pants textures (the Studio's hi_body export, rest pose).
uvpos.py OUTDIR  -> uvpos_<part>.npz (pos[h,w,3] in game cm: x = player's left(+)/right, y = up, z = front(+)?; mask) + previews"""
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image
MODELS = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/work/models')
CT = {5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}
NC = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
def load(path):
    g = json.load(open(path)); blob = (path.parent / g['buffers'][0]['uri']).read_bytes()
    def acc(i):
        a = g['accessors'][i]; bv = g['bufferViews'][a['bufferView']]
        fmt, size = CT[a['componentType']]; n = NC[a['type']]
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0); stride = bv.get('byteStride') or size * n; cnt = a['count']
        raw = np.frombuffer(blob, dtype=np.uint8, count=(cnt - 1) * stride + size * n, offset=off)
        arr = np.stack([np.frombuffer(raw[i * stride:i * stride + size * n].tobytes(), dtype='<' + fmt) for i in range(cnt)]).astype(np.float64)
        if a.get('normalized'): arr = arr / {'b':127.0,'B':255.0,'h':32767.0,'H':65535.0}[fmt]
        return arr
    mats = [m['name'] for m in g['materials']]; parts = {}
    for mesh in g['meshes']:
        for prim in mesh['primitives']:
            name = mats[prim['material']]
            if 'TEXCOORD_0' not in prim['attributes']: continue
            pos = acc(prim['attributes']['POSITION']); uv = acc(prim['attributes']['TEXCOORD_0'])
            nrm = acc(prim['attributes']['NORMAL']) if 'NORMAL' in prim['attributes'] else np.zeros_like(pos)
            raw = acc(prim['indices']).astype(np.int64).reshape(-1); mode = prim.get('mode', 4)
            idx = raw.reshape(-1, 3) if mode == 4 else np.array([(raw[i], raw[i+1], raw[i+2]) if i % 2 == 0 else (raw[i+1], raw[i], raw[i+2]) for i in range(len(raw) - 2)], np.int64)
            if name in parts:
                q = parts[name]; base = len(q['pos'])
                q['pos'] = np.concatenate([q['pos'], pos]); q['uv'] = np.concatenate([q['uv'], uv]); q['nrm'] = np.concatenate([q['nrm'], nrm]); q['tris'] = np.concatenate([q['tris'], idx + base])
            else: parts[name] = dict(pos=pos, uv=uv, nrm=nrm, tris=idx)
    return parts
def raster(part, w, h):
    pos = np.zeros((h, w, 3)); nrm = np.zeros((h, w, 3)); mask = np.zeros((h, w), bool)
    uv = part['uv'] * np.array([w, h])
    for t in part['tris']:
        a, b, c = uv[t]
        x0, x1 = int(np.floor(min(a[0], b[0], c[0]))), int(np.ceil(max(a[0], b[0], c[0])))
        y0, y1 = int(np.floor(min(a[1], b[1], c[1]))), int(np.ceil(max(a[1], b[1], c[1])))
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0: continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12: continue
        l0 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l1 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        l2 = 1 - l0 - l1
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        if not inside.any(): continue
        P = l0[..., None] * part['pos'][t[0]] + l1[..., None] * part['pos'][t[1]] + l2[..., None] * part['pos'][t[2]]
        N = l0[..., None] * part['nrm'][t[0]] + l1[..., None] * part['nrm'][t[1]] + l2[..., None] * part['nrm'][t[2]]
        yy, xx = np.nonzero(inside)
        pos[y0 + yy, x0 + xx] = P[yy, xx]; nrm[y0 + yy, x0 + xx] = N[yy, xx]; mask[y0 + yy, x0 + xx] = True
    return pos, nrm, mask
if __name__ == '__main__':
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    parts = load(MODELS / 'hi_body_o3c114.gltf')
    print({k: (len(v['pos']), len(v['tris']), v['uv'].min(0).round(3).tolist(), v['uv'].max(0).round(3).tolist()) for k, v in parts.items() if k.startswith('UNIF') or k.startswith('SOCK')})
    for name, (w, h) in (('UNIF_jersey', (512, 256)), ('UNIF_sleeve', (128, 128)), ('UNIF_pants', (512, 256))):
        p = parts[name]; S = 2
        pos, nrm, mask = raster(p, w * S, h * S)
        np.savez_compressed(out / f'uvpos_{name}.npz', pos=pos.astype(np.float32), nrm=nrm.astype(np.float32), mask=mask)
        print(name, 'covered', round(mask.mean(), 3), 'pos min', pos[mask].min(0).round(1), 'max', pos[mask].max(0).round(1))
        # preview: R = x, G = y (height), B = z, with height contour lines
        lo, hi = pos[mask].min(0), pos[mask].max(0)
        rgb = ((pos - lo) / (hi - lo) * 255).clip(0, 255).astype(np.uint8); rgb[~mask] = 40
        Image.fromarray(rgb).save(out / f'uvpos_{name}.png')
