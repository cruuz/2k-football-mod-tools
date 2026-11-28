"""Pass 7 texture fixes for in-game defects the old cards hid: a logo mirrored the wrong way on one side, a logo not
mirrored for its island, and detached pieces of the 2004 logo beside a 2026 wordmark."""
import sys; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, texdet2, fixtex
from scipy import ndimage
AXIS = 255          # both atlases mirror their two side islands about y + y' = 255
def shell_dev(rgb, fam):
    z = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]
    shell = np.median(rgb[z], axis=0)
    return np.linalg.norm(rgb - shell, axis=2), shell
def logo_box(rgb, fam, upper, pad=2, x1=142):
    """Bounding box of the logo ink of one side panel (largest piece plus pieces near it)."""
    dev, _ = shell_dev(rgb, fam)
    m = (dev > 40) & texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]
    rows = np.arange(256)[:, None]
    m &= (rows < 128) if upper else (rows >= 128)
    m[:, x1:] = False
    lab, k = ndimage.label(m, structure=np.ones((3, 3), bool))
    sizes = ndimage.sum(m, lab, np.arange(1, k + 1)); big = lab == (1 + int(np.argmax(sizes)))
    near = ndimage.binary_dilation(big, iterations=6)
    keep = np.isin(lab, [i + 1 for i in range(k) if (near & (lab == i + 1)).any() and sizes[i] >= 3])
    ys, xs = np.nonzero(keep)
    return (max(xs.min() - pad, 0), max(ys.min() - pad, 0), min(xs.max() + 1 + pad, 256), min(ys.max() + 1 + pad, 256)), keep
def flip_logo_h(T, fam, upper=True):
    """The logo of one panel mirrored left-right in place (a word that read backwards on that side)."""
    rgb = T[..., :3].astype(np.float64)
    (x0, y0, x1, y1), keep = logo_box(rgb, fam, upper)
    out = T.copy(); out[y0:y1, x0:x1, :3] = T[y0:y1, x0:x1, :3][:, ::-1]
    return out, (x0, y0, x1, y1)
def mirror_upper_from_lower(T, fam):
    """The upper island's logo becomes the lower one's mirror image about the atlas axis (as the retail art has it)."""
    rgb = T[..., :3].astype(np.float64)
    (lx0, ly0, lx1, ly1), _ = logo_box(rgb, fam, False)
    (ux0, uy0, ux1, uy1), _ = logo_box(rgb, fam, True)
    out = T.copy()
    # clear the old upper logo to shell (mirror of the lower island's own shell there), then lay the mirrored lower box
    x0, x1 = min(lx0, ux0), max(lx1, ux1)
    y0, y1 = min(AXIS - ly1 + 1, uy0), max(AXIS - ly0 + 1, uy1)
    src = T[AXIS - y1 + 1:AXIS - y0 + 1, x0:x1, :3][::-1]
    out[y0:y1, x0:x1, :3] = src
    return out, (x0, y0, x1, y1)
def mirror_panel(T, fam, to_upper):
    """One side's logo rebuilt as the mirror image of the other side's (about the atlas axis), texel for texel inside
    the two logos' own shapes grown by 3: nothing else on the panel moves."""
    rgb = T[..., :3].astype(np.float64)
    _b, lk = logo_box(rgb, fam, False, pad=0); _b, uk = logo_box(rgb, fam, True, pad=0)
    src, dst = (lk, uk) if to_upper else (uk, lk)
    m = ndimage.binary_dilation(dst | src[::-1], iterations=3)
    rows = np.arange(256)[:, None]
    m &= (rows < 128) if to_upper else (rows >= 128)
    m &= texdet.zone_mask(fam); m[:, 142:] = False
    out = T.copy(); out[m, :3] = T[::-1][m][:, :3]
    return out, m
def lower_from_modern(T, name):
    """Standard shell, left side: the logo exactly as the modern shell's left side has it. For a club whose left-side
    decal is not the right side's mirror image (the Chiefs: the arrowhead points forward on both sides and reads KC on
    both, as in the retail art), so a mirror copy would turn the letters."""
    import final
    fam = 'helmet00'; rgb = T[..., :3].astype(np.float64)
    mrgb = final.helmet('helmet02_' + name.split('_')[1])[..., :3].astype(np.float64)
    (mx0, my0, mx1, my1), mk = logo_box(mrgb, 'helmet02', False, pad=0)
    (x0, y0, x1, y1), lk = logo_box(rgb, fam, False, pad=0)
    shape = ndimage.binary_dilation(ndimage.binary_fill_holes(ndimage.binary_closing(mk[my0:my1, mx0:mx1], iterations=2)), iterations=1)
    old = ndimage.binary_dilation(lk, iterations=3) & texdet.zone_mask(fam)
    shell = np.median(rgb[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
    not_shell = (np.linalg.norm(rgb - shell, axis=2) > 12.0) | old
    out = fixtex.nn_fill(rgb, old, keep_out=not_shell); sm = fixtex.fill(out, old, keep_out=not_shell)
    out[old] = 0.5 * out[old] + 0.5 * sm[old]
    h, w = shape.shape; px = int(round((x0 + x1) / 2.0 - w / 2.0)); py = int(round((y0 + y1) / 2.0 - h / 2.0))
    region = out[py:py + h, px:px + w]; region[shape] = mrgb[my0:my1, mx0:mx1][shape]
    changed = old.copy(); changed[py:py + h, px:px + w] |= shape
    pal = np.unique(T[..., :3].reshape(-1, 3), axis=0)
    res = T.copy(); res[changed, :3] = fixtex.nearest_palette(out[changed], pal)
    return res, changed
def detached_old(name, T):
    """Pieces of retail ink that touch no new ink: separate leftovers of the 2004 logo beside a 2026 wordmark."""
    fam = name.split('_')[0]
    rgb = T[..., :3].astype(np.float64)
    dev, shell = shell_dev(rgb, fam)
    hw = texdet.hardware(fam)[0].copy()
    if fam == 'helmet02':
        for m in fixtex.vent_regions(): hw &= ~ndimage.binary_dilation(m, iterations=2)
    z = texdet.zone_mask(fam) & ~hw; z[:, 142:] = False
    ink = z & (dev > 30)
    exp = np.zeros((256, 256), bool)
    for r in texdet2.refs_for(name):
        ret = C.hretail(r)[..., :3].astype(np.float64)
        shell_ret = np.median(ret[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
        a, ok = texdet2.explained(rgb, ret, shell, shell_ret); exp |= ok & z
    new = ink & ~exp
    lab, k = ndimage.label(ink, structure=np.ones((3, 3), bool))
    old = np.zeros((256, 256), bool)
    for i in range(1, k + 1):
        comp = lab == i
        if (comp & exp).sum() >= 0.6 * comp.sum() and not (ndimage.binary_dilation(comp, iterations=2) & new).any() and comp.sum() >= 4:
            old |= comp
    return old
if __name__ == '__main__':
    import final, flat
    from PIL import Image
    def prev(tex, side, crop=(5, 150, 20, 236)):
        out, pid, s = flat.flat(tex, side); f = flat.reduce(out, 4)
        return C.up(C.over(np.clip(f + 0.5, 0, 255).astype(np.uint8))[crop[0]:crop[1], crop[2]:crop[3]], 2)
    rows = []
    T = final.helmet('helmet02_22H5'); F, box = flip_logo_h(T, 'helmet02', True); print('PIT box', box)
    rows.append(C.hstack([prev(T, 'A'), prev(F, 'A')], gap=4))
    T = final.helmet('helmet02_19H7'); old = detached_old('helmet02_19H7', T); print('NYJ detached old texels', int(old.sum()))
    rgb = fixtex.fill(T[..., :3].astype(float), ndimage.binary_dilation(old, iterations=2) & texdet.zone_mask('helmet02'))
    F = T.copy(); m = ndimage.binary_dilation(old, iterations=2) & texdet.zone_mask('helmet02'); F[m, :3] = np.clip(rgb[m] + 0.5, 0, 255).astype(np.uint8)
    rows.append(C.hstack([prev(T, 'H'), prev(F, 'H'), prev(T, 'A'), prev(F, 'A')], gap=4))
    W = max(r.shape[1] for r in rows)
    Image.fromarray(np.concatenate([np.pad(r, ((0, 6), (0, W - r.shape[1]), (0, 0))) for r in rows], axis=0)).save(C.WORK / 'view_fixes7.png')
