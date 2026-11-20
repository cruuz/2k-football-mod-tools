"""Helmet C geometry from the Studio's head export, and a small z-buffer rasteriser for the Team Select helm card pose."""
import json, struct, math
from pathlib import Path
import numpy as np
WORK = Path(__import__('os').environ.get('B81_ART_WORK', '/home/noah/2k-worktrees/.b77-scratch/b81/art/work'))
CT = {5120:('b',1),5121:('B',1),5122:('h',2),5123:('H',2),5125:('I',4),5126:('f',4)}
NC = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
def load_gltf(mode='modern'):
    d = WORK / f'head_{mode}'
    g = json.load(open(d / 'hi_head_o3c115.gltf'))
    blob = (d / g['buffers'][0]['uri']).read_bytes()
    def acc(i):
        a = g['accessors'][i]; bv = g['bufferViews'][a['bufferView']]
        fmt, size = CT[a['componentType']]; n = NC[a['type']]
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = bv.get('byteStride') or size * n
        cnt = a['count']
        if stride == size * n:
            arr = np.frombuffer(blob, dtype=np.dtype('<' + fmt), count=cnt * n, offset=off).reshape(cnt, n)
        else:
            arr = np.stack([np.frombuffer(blob, dtype=np.dtype('<' + fmt), count=n, offset=off + i * stride) for i in range(cnt)])
        arr = arr.astype(np.float64)
        if a.get('normalized'):
            arr = arr / {'b':127.0,'B':255.0,'h':32767.0,'H':65535.0}[fmt]
        return arr
    parts = {}
    mats = [m['name'] for m in g['materials']]
    for mesh in g['meshes']:
        for prim in mesh['primitives']:
            name = mats[prim['material']]
            pos = acc(prim['attributes']['POSITION'])
            uv = acc(prim['attributes']['TEXCOORD_0']) if 'TEXCOORD_0' in prim['attributes'] else None
            raw = acc(prim['indices']).astype(np.int64).reshape(-1)
            mode = prim.get('mode', 4)
            if mode == 4:
                idx = raw.reshape(-1, 3)
            elif mode == 5:
                idx = np.array([(raw[i], raw[i+1], raw[i+2]) if i % 2 == 0 else (raw[i+1], raw[i], raw[i+2]) for i in range(len(raw) - 2)], np.int64).reshape(-1, 3)
            else:
                raise ValueError(mode)
            if name in parts:   # several primitives of one material: merge
                q = parts[name]; base = len(q['pos'])
                q['pos'] = np.concatenate([q['pos'], pos]); q['uv'] = None if uv is None else np.concatenate([q['uv'], uv])
                q['tris'] = np.concatenate([q['tris'], idx + base])
            else:
                parts[name] = dict(pos=pos, uv=uv, tris=idx)
    return g, parts
def to_blender(pos_gltf, scale=0.01, offset=(0.0, 0.0455, 0.339)):
    """glTF (Y up, game cm under the root's 0.01 scale) -> Blender metres, with the card job's head offset."""
    p = pos_gltf * scale
    return np.stack([p[:, 0] + offset[0], -p[:, 2] + offset[1], p[:, 1] + offset[2]], axis=1)
HELM_VIEW = {"yaw": 100, "pitch": 12, "roll": 8, "dist": 1.0, "target": [0, -0.0545, 0.784],
             "fov": 18.00322428256025, "shift_x": -0.06435351995565419, "shift_y": -0.07434000831485588}
def view_for(side):
    v = dict(HELM_VIEW)
    if side == 'A':
        v["yaw"], v["roll"], v["shift_x"] = -v["yaw"], -v["roll"], -v["shift_x"]
    return v
def camera(view):
    t = np.array(view['target'], float)
    yaw, pitch, dist = math.radians(view['yaw']), math.radians(view['pitch']), view['dist']
    pos = t + np.array([dist*math.cos(pitch)*math.sin(yaw), -dist*math.cos(pitch)*math.cos(yaw), dist*math.sin(pitch)])
    fwd = (t - pos); fwd /= np.linalg.norm(fwd)
    # Blender to_track_quat('-Z','Y'): camera -Z along fwd, +Y as close to world Z as possible
    up = np.array([0, 0, 1.0])
    right = np.cross(fwd, up); right /= np.linalg.norm(right)
    upc = np.cross(right, fwd)
    r = math.radians(view.get('roll', 0.0))
    # roll about the camera's local Z (which is -fwd): rotate right/up
    right2 = right*math.cos(r) + upc*math.sin(r)
    up2 = -right*math.sin(r) + upc*math.cos(r)
    return pos, right2, up2, fwd
def project(P, view, size):
    pos, right, up, fwd = camera(view)
    d = P - pos
    x, y, z = d @ right, d @ up, d @ fwd
    f = 0.5 / math.tan(math.radians(view['fov']) / 2.0)   # in frame units (frame width 1)
    sx = f * x / z - view.get('shift_x', 0.0)
    sy = f * y / z - view.get('shift_y', 0.0)
    px = (sx + 0.5) * size
    py = (0.5 - sy) * size
    return px, py, z
def raster(parts, names, view, size):
    """Returns part id (-1 none), u, v, depth, per pixel (pixel centres)."""
    pid = np.full((size, size), -1, np.int32); zb = np.full((size, size), np.inf)
    U = np.zeros((size, size)); V = np.zeros((size, size))
    for k, name in enumerate(names):
        p = parts[name]
        P = to_blender(p['pos'])
        px, py, z = project(P, view, size)
        uv = p['uv']
        for a, b, c in p['tris']:
            if a == b or b == c or a == c: continue
            x0, y0, x1, y1, x2, y2 = px[a], py[a], px[b], py[b], px[c], py[c]
            minx = max(int(math.floor(min(x0, x1, x2))), 0); maxx = min(int(math.ceil(max(x0, x1, x2))), size - 1)
            miny = max(int(math.floor(min(y0, y1, y2))), 0); maxy = min(int(math.ceil(max(y0, y1, y2))), size - 1)
            if minx > maxx or miny > maxy: continue
            den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(den) < 1e-12: continue
            xs = np.arange(minx, maxx + 1) + 0.5; ys = np.arange(miny, maxy + 1) + 0.5
            X, Y = np.meshgrid(xs, ys)
            w0 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / den
            w1 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
            if not inside.any(): continue
            # perspective-correct
            iz = w0 / z[a] + w1 / z[b] + w2 / z[c]
            zz = 1.0 / iz
            sub_z = zb[miny:maxy + 1, minx:maxx + 1]
            win = inside & (zz < sub_z)
            if not win.any(): continue
            sub_z[win] = zz[win]
            pid[miny:maxy + 1, minx:maxx + 1][win] = k
            if uv is not None:
                uu = (w0 * uv[a, 0] / z[a] + w1 * uv[b, 0] / z[b] + w2 * uv[c, 0] / z[c]) * zz
                vv = (w0 * uv[a, 1] / z[a] + w1 * uv[b, 1] / z[b] + w2 * uv[c, 1] / z[c]) * zz
                U[miny:maxy + 1, minx:maxx + 1][win] = uu[win]
                V[miny:maxy + 1, minx:maxx + 1][win] = vv[win]
    return pid, U, V, zb
