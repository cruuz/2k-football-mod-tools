"""Helmet texture cleanup on the FINAL (built-disc) textures: painted Revolution vents, the old flag diamond, and
old-logo ink outside the registered official logo. Prototype of tools/b81_helmet_cleanup.py."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, texdet2, reg, final
from scipy import ndimage
WT = C.WT
sys.path.insert(0, str(WT / 'tools'))
import b780_team_select_old_logo_cleanup as art1   # harmonic_fill, dilate
# ---- fixed regions of the Revolution atlas (helmet02), from the blank retail helmet
def vent_regions():
    """The six painted vents of the 2004 Revolution art: 4 crown crescents and 2 rear slits (dark core + light rim)."""
    hw, dev = texdet.hardware('helmet02')
    boxes = [(32, 104, 60, 124), (70, 110, 96, 126), (70, 128, 96, 144), (32, 132, 60, 152),   # crescents
             (102, 90, 124, 114), (102, 142, 124, 166)]                                           # rear slits
    out = []
    for x0, y0, x1, y1 in boxes:
        m = np.zeros((256, 256), bool); m[y0:y1, x0:x1] = dev[y0:y1, x0:x1] > 10
        lab, n = ndimage.label(m)
        if n > 1:
            sizes = ndimage.sum(m, lab, np.arange(1, n + 1)); m = lab == (1 + int(np.argmax(sizes)))
        out.append(ndimage.binary_dilation(m, iterations=2))
    return out
def diamond_region():
    """Where the 2004 flag sat on the back of the Revolution shell (the 2026 art keeps its alpha at 0)."""
    a = C.hcur('helmet02_30H0')[..., 3]
    m = np.zeros((256, 256), bool); m[90:165, 95:150] = a[90:165, 95:150] < 128
    return m
def nn_fill(rgb, paint, keep_out=None):
    """Every painted texel takes the colour of the nearest texel outside the region (edges of a pattern carry on)."""
    src = ~paint
    if keep_out is not None: src &= ~keep_out
    idx = ndimage.distance_transform_edt(~src, return_distances=False, return_indices=True)
    out = rgb.copy(); out[paint] = rgb[idx[0][paint], idx[1][paint]]
    return out
def patterned(rgb, region, keep_out=None, thr=40.0):
    """Whether the shell around a region carries a pattern (two or more distinct colours) rather than plain shading."""
    band = art1.dilate(region, 3) & ~region
    if keep_out is not None: band &= ~keep_out
    if band.sum() < 8: return False
    v = rgb[band]
    return float(np.linalg.norm(v - np.median(v, axis=0), axis=1).max()) > thr and float((np.linalg.norm(v - np.median(v, axis=0), axis=1) > thr).mean()) > 0.08
def nearest_palette(rgb_f, palette):
    d = ((rgb_f[:, None, :] - palette[None, :, :].astype(np.float64)) ** 2).sum(axis=2)
    return palette[np.argmin(d, axis=1)]
def fill(rgb, paint, keep_out=None):
    """Harmonic fill of ``paint`` from the pixels around it (not ``keep_out``)."""
    band = art1.dilate(paint, 2) & ~paint
    if keep_out is not None: band &= ~keep_out
    if band.sum() < 6:
        band = art1.dilate(paint, 4) & ~paint
        if keep_out is not None: band &= ~keep_out
    return art1.harmonic_fill(rgb.astype(np.float64), paint, band)
def cleanup(name, tex=None, foot=None, extra=None, do_logo=True, shell_only=None):
    fam = name.split('_')[0]
    T = (final.helmet(name) if tex is None else tex)
    rgb = T[..., :3].astype(np.float64)
    out = rgb.copy(); masks = {}
    if foot is None:
        import texdet3
        foot, ok = texdet3.footprint(name)
    if fam == 'helmet02':
        vents = np.zeros((256, 256), bool)
        for m in vent_regions():
            m = m & ~foot
            if not m.any(): continue
            out = nn_fill(out, m, keep_out=foot) if patterned(out, m, foot) else fill(out, m, keep_out=foot)
            vents |= m
        masks['vents'] = vents
        d = diamond_region()
        ring = ndimage.binary_dilation(d, iterations=3) & ~ndimage.binary_erosion(d, iterations=2)
        shell_out = np.median(out[ndimage.binary_dilation(d, iterations=5) & ~ndimage.binary_dilation(d, iterations=2)], axis=0)
        inner = ndimage.binary_erosion(d, iterations=2)
        shell_in = np.median(out[inner], axis=0)
        paint = ring.copy()
        if np.abs(shell_in - shell_out).max() > 18: paint |= d
        # a diamond that still holds the flag (a retail-art throwback) stays as it is
        flag = float(np.linalg.norm(out[inner] - shell_in, axis=1).std()) > 30.0
        if flag: paint[:] = False
        if paint.any(): out = nn_fill(out, paint) if patterned(out, paint) else fill(out, paint)
        masks['diamond'] = paint
    if shell_only is not None and shell_only.any():
        # old shell-colour squares: only texels that are today's shell colour may fill them
        z = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]
        shell = np.median(rgb[z], axis=0)
        not_shell = np.linalg.norm(out - shell, axis=2) > 45.0
        out = nn_fill(out, shell_only, keep_out=not_shell | foot)
        sm = fill(out, shell_only, keep_out=not_shell | foot)
        out[shell_only] = 0.5 * out[shell_only] + 0.5 * sm[shell_only]
        masks['shell_boxes'] = shell_only
        if extra is not None: extra = extra & ~shell_only
    if extra is not None and extra.any():
        out = fill(out, extra, keep_out=foot); masks['old'] = extra
    changed = np.zeros((256, 256), bool)
    for m in masks.values(): changed |= m
    # the texture is P8: every repainted texel takes the nearest colour the texture already has
    pal = np.unique(T[..., :3].reshape(-1, 3), axis=0)
    res = T.copy()
    res[changed, :3] = nearest_palette(out[changed], pal)
    return res, masks
if __name__ == '__main__':
    from PIL import Image
    names = sys.argv[1:]
    tiles = []
    for n in names:
        a = final.helmet(n); b, masks = cleanup(n)
        tiles.append(C.hstack([C.up(a[16:240, 0:150, :3], 3), C.up(b[16:240, 0:150, :3], 3)], gap=3))
    rows = [C.hstack(tiles[i:i+3], gap=10) for i in range(0, len(tiles), 3)]
    W = max(r.shape[1] for r in rows)
    Image.fromarray(np.concatenate([np.pad(r, ((0, 8), (0, W - r.shape[1]), (0, 0))) for r in rows], axis=0)).save(C.WORK / 'view_fixtex.png')
