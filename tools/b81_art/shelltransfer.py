"""Standard-shell logos by geometry: where a point of the modern shell's side decal sits on the Standard shell.

Both shells live in one head model. Every sub-texel of the Standard shell's side panels (helmet00 atlas) is taken to its
3D point on shell A, a ray from the helmet's centre through that point is cut with shell C, and the hit's own UV says
which helmet02 texel shows at the same place on the modern helmet. A logo copied through this map has the modern
shell's position, angle and size on the Standard shell, on both sides, whatever the two atlases' layouts are."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, geom, texdet
from scipy import ndimage
S = 3                       # sub-samples per texel side
CACHE = C.WORK / 'shelltransfer_map.npz'
def _uv_raster(part, mask, s):
    """Per sub-texel of ``mask`` (256x256 bool): 3D position on the part's surface, by its UV triangles."""
    n = 256 * s; pos = np.full((n, n, 3), np.nan)
    P, UV, T = part['pos'], part['uv'] * 256.0, part['tris']
    big = np.kron(mask, np.ones((s, s), bool))
    for t in T:
        if len(set(t.tolist())) < 3: continue
        (ax, ay), (bx, by), (cx, cy) = UV[t]
        x0, x1 = int(np.floor(min(ax, bx, cx) * s)), int(np.ceil(max(ax, bx, cx) * s)) + 1
        y0, y1 = int(np.floor(min(ay, by, cy) * s)), int(np.ceil(max(ay, by, cy) * s)) + 1
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, n), min(y1, n)
        if x1 <= x0 or y1 <= y0 or not big[y0:y1, x0:x1].any(): continue
        ys, xs = np.mgrid[y0:y1, x0:x1]; px = (xs + 0.5) / s; py = (ys + 0.5) / s
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12: continue
        w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / den
        w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / den
        w2 = 1 - w0 - w1
        ins = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6) & big[y0:y1, x0:x1]
        if not ins.any(): continue
        p = w0[..., None] * P[t[0]] + w1[..., None] * P[t[1]] + w2[..., None] * P[t[2]]
        sub = pos[y0:y1, x0:x1]; sub[ins] = p[ins]
    return pos
def build():
    g, parts = geom.load_gltf('retail')
    A, Cc = parts['HI_HELMET_A'], parts['HI_HELMET_C']
    used = np.unique(A['tris']); centre = (A['pos'][used].min(axis=0) + A['pos'][used].max(axis=0)) / 2.0
    za = texdet.zone_mask('helmet00'); zc = texdet.zone_mask('helmet02')
    pos = _uv_raster(A, za, S)
    ok = ~np.isnan(pos[..., 0]); pts = pos[ok]; d = pts - centre; d /= np.linalg.norm(d, axis=1)[:, None]
    # shell C triangles whose UVs touch the modern side panels
    UVc = Cc['uv'] * 256.0; best_t = np.full(len(pts), np.inf); src = np.full((len(pts), 2), np.nan)
    zc_big = ndimage.binary_dilation(zc, iterations=3)
    for t in Cc['tris']:
        if len(set(t.tolist())) < 3: continue
        uv = UVc[t]; cx, cy = uv.mean(axis=0)
        if not (0 <= int(cy) < 256 and 0 <= int(cx) < 256 and zc_big[int(cy), int(cx)]): continue
        a, b, c = Cc['pos'][t]; e1, e2 = b - a, c - a
        h = np.cross(d, e2); det = h @ e1
        good = np.abs(det) > 1e-12; inv = np.where(good, 1.0 / np.where(good, det, 1.0), 0.0)
        s_ = centre - a; u = (h @ s_) * inv
        q = np.cross(s_, e1); v = (d @ q) * inv; tt = (q @ e2) * inv
        hit = good & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6) & (tt > 0) & (tt < best_t)
        if not hit.any(): continue
        best_t[hit] = tt[hit]
        src[hit] = (1 - u[hit] - v[hit])[:, None] * uv[0] + u[hit][:, None] * uv[1] + v[hit][:, None] * uv[2]
    n = 256 * S; sx = np.full((n, n), np.nan); sy = np.full((n, n), np.nan)
    sx[ok] = src[:, 0]; sy[ok] = src[:, 1]
    np.savez_compressed(CACHE, sx=sx.astype(np.float32), sy=sy.astype(np.float32))
    cov = np.kron(za, np.ones((S, S), bool))
    return dict(zone_subtexels=int(cov.sum()), on_shell_a=int(ok.sum()), with_modern_source=int((~np.isnan(sx)).sum()))
_map = {}
def mapping():
    if 'm' not in _map:
        if not CACHE.exists(): build()
        z = np.load(CACHE); _map['m'] = (z['sx'].astype(np.float64), z['sy'].astype(np.float64))
    return _map['m']
def bilinear(img, x, y):
    """img[H,W,(C)] sampled at float texel coordinates (texel centres at +0.5)."""
    x = x - 0.5; y = y - 0.5
    x0 = np.clip(np.floor(x).astype(int), 0, 254); y0 = np.clip(np.floor(y).astype(int), 0, 254)
    fx = np.clip(x - x0, 0, 1); fy = np.clip(y - y0, 0, 1)
    if img.ndim == 3: fx = fx[..., None]; fy = fy[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)
def transfer(modern_rgb, modern_mask):
    """(colour[256,256,3], alpha[256,256]) on the helmet00 atlas of what ``modern_mask`` selects on the helmet02 one."""
    sx, sy = mapping(); ok = ~np.isnan(sx)
    x = np.where(ok, sx, 1.0); y = np.where(ok, sy, 1.0)
    # cubic sampling (texel centres at +0.5): the copy keeps the source's edge contrast
    coords = np.stack([y - 0.5, x - 0.5])
    a = np.where(ok, np.clip(ndimage.map_coordinates(modern_mask.astype(np.float64), coords, order=1, mode='nearest'), 0, 1), 0.0)
    col = np.stack([np.clip(ndimage.map_coordinates(modern_rgb[..., c].astype(np.float64), coords, order=3, mode='nearest'), 0, 255) for c in range(3)], axis=-1) * a[..., None]
    a2 = a.reshape(256, S, 256, S).mean(axis=(1, 3)); c2 = col.reshape(256, S, 256, S, 3).mean(axis=(1, 3))
    return np.where(a2[..., None] > 1e-6, c2 / np.maximum(a2[..., None], 1e-6), 0.0), a2
if __name__ == '__main__':
    print(build())
    # validation with the retail art: the retail helmet02 logo through the map against the retail helmet00 logo
    import fixes7
    for sel in ('00H0', '03H0', '09H0', '26H0', '21H0'):
        R2 = C.hretail('helmet02_' + sel)[..., :3].astype(np.float64); R0 = C.hretail('helmet00_' + sel)[..., :3].astype(np.float64)
        def ink(rgb, fam):
            z = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]; shell = np.median(rgb[z], axis=0)
            m = z & (np.linalg.norm(rgb - shell, axis=2) > 40); m[:, 142:] = False; return m
        col, al = transfer(R2, ink(R2, 'helmet02')); got = al > 0.5; want = ink(R0, 'helmet00')
        print(C.TEAMS[sel[:2]], 'retail modern-shell logo through the map vs retail standard-shell logo: IoU', round(float((got & want).sum() / max(1, (got | want).sum())), 3), 'ink', int(got.sum()), int(want.sum()))
