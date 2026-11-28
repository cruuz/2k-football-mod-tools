"""The Bills' blue alternate: the charge streak carried on round the back of the helmet, as the real one runs.

Painted in 3D, not in the atlas: every sub-texel of the shell is taken to its direction from the helmet's centre
(angle round the head from the front, and elevation), the side streak's own line and width are measured there, and the
band is continued from its rear end to the centre of the back, easing level, on both halves. So it is one continuous
band on the helmet whatever islands the atlas cuts the back into."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, geom, texdet, fixtex, shelltransfer as st
from scipy import ndimage
S = 3
_pos = {}
LINES = {}                  # kit -> the band measured on the modern shell, reused for that kit's Standard shell
def angles(fam):
    """(phi, theta, on_shell) per sub-texel: phi 0 at the front to pi at the back, theta the elevation."""
    if fam not in _pos:
        f = C.WORK / f'shellpos_{fam}_{S}.npy'
        g, parts = geom.load_gltf('retail')
        A = parts['HI_HELMET_A']; used = np.unique(A['tris']); centre = (A['pos'][used].min(axis=0) + A['pos'][used].max(axis=0)) / 2.0
        if f.exists(): pos = np.load(f).astype(np.float64)
        else:
            pos = st._uv_raster(parts['HI_HELMET_A' if fam == 'helmet00' else 'HI_HELMET_C'], np.ones((256, 256), bool), S)
            np.save(f, pos.astype(np.float32))
        ok = ~np.isnan(pos[..., 0]); d = np.where(ok[..., None], pos - centre, 1.0); d /= np.linalg.norm(d, axis=2)[..., None]
        _pos[fam] = (np.arctan2(np.abs(d[..., 0]), d[..., 2]), np.arcsin(np.clip(d[..., 1], -1, 1)), ok, d[..., 0])
    return _pos[fam]
def wrap(T, fam, line=None):
    """T with the streak continued to the back centre. ``line``: (phi_end, theta_end, slope, half_width) measured on the
    modern shell, reused for the Standard shell so both carry the same band. Returns (texture, line, texels)."""
    phi, theta, ok, side_x = angles(fam)
    rgb = T[..., :3].astype(np.float64); zone = texdet.zone_mask(fam)
    shell = np.median(rgb[zone & ~texdet.hardware(fam)[0]], axis=0); dev = np.linalg.norm(rgb - shell, axis=2)
    red = (rgb[..., 0] > 150) & (rgb[..., 1] < 90) & (rgb[..., 2] < 110) & zone
    red[:, 142:] = False; red[214:] = False; red[:42] = False          # the streak, not the flag's stripes
    c = S // 2; p1 = phi[c::S, c::S]; t1 = theta[c::S, c::S]; ok1 = ok[c::S, c::S]
    if line is None:
        m = red & ok1; ph = p1[m]; th = t1[m]
        far = ph >= np.quantile(ph, 0.55)
        b, a = np.polyfit(ph[far], th[far], 1); resid = th[far] - (a + b * ph[far])
        phi_e = float(np.quantile(ph, 0.97)); line = (phi_e, float(a + b * phi_e), float(b), float((np.quantile(resid, 0.96) - np.quantile(resid, 0.04)) / 2.0))
    phi_e, th_e, b, hw = line
    L = np.pi - phi_e; dl = np.clip(phi - phi_e, 0.0, L)
    centre_line = th_e + b * dl * (1.0 - dl / (2.0 * L))               # the slope eases to level at the back centre
    dist = np.abs(theta - centre_line); edge = 0.34 * hw
    sel = ok & (phi > phi_e - 0.22)                                    # from a little before the old slanted end
    r = (sel & (dist < hw)).reshape(256, S, 256, S).mean(axis=(1, 3)); w = (sel & (dist >= hw) & (dist < hw + edge)).reshape(256, S, 256, S).mean(axis=(1, 3))
    # only plain shell (or the streak's own end) is painted: decals and screws stay
    paintable = (dev < 26.0) | red | ((rgb.min(axis=2) > 170) & ndimage.binary_dilation(red, iterations=3))
    c = S // 2
    paintable |= np.abs(side_x[c::S, c::S]) < 0.30                     # the centre strip of the back: the band crosses it
    paintable &= ~(texdet.hardware(fam)[1] >= 60.0)
    cov = (r + w) * paintable
    redc = np.median(rgb[red], axis=0)
    out = rgb * (1 - cov[..., None]) + (redc * r[..., None] + 255.0 * w[..., None]) * paintable[..., None]
    changed = cov > 0.02
    res = T.copy(); res[changed, :3] = np.clip(np.rint(out[changed]), 0, 255).astype(np.uint8)
    blocked = int((((r + w) > 0.5) & ~paintable).sum())
    return res, line, dict(texels=int(changed.sum()), blocked_by_decals_or_hardware=blocked, line=[round(float(v), 4) for v in line])
if __name__ == '__main__':
    import fixtex2, flat
    from PIL import Image
    g, parts = geom.load_gltf('retail')
    T, res, d, m = fixtex2.cleanup('helmet02_03H8'); a, line, info = wrap(res, 'helmet02'); print('modern', info)
    T0, res0, d0, m0 = fixtex2.cleanup('helmet00_03H8'); a0, line0, info0 = wrap(res0, 'helmet00', line); print('standard', info0)
    tiles = []
    for tex, names in ((a, ['HI_HELMET_C', 'LOGO_helmet_C']), (a0, ['HI_HELMET_A', 'LOGO_helmet'])):
        row = []
        for yaw in (90, 135, 180, 225, 270):
            view = {"yaw": yaw, "pitch": 5, "roll": 0, "dist": 1.0, "target": [0, -0.03, 0.79], "fov": 22}
            pid, U, V, z = geom.raster(parts, names, view, 256)
            s = flat.bilinear(tex.astype(float), U, V); img = np.full((256, 256, 3), 128.0); mm = pid >= 0; img[mm] = s[mm, :3]
            row.append(np.clip(img, 0, 255).astype(np.uint8)[20:190, 30:226])
        tiles.append(np.concatenate(row, axis=1))
    Image.fromarray(np.concatenate(tiles, axis=0)).save(C.WORK / 'view_streak.png')
