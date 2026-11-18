"""An official logo file's white outer keyline (drawn for dark backgrounds; the real helmet decal has none) and its
removal on a helmet texture: the keyline ring, at the registered placement, goes back to shell and the logo's own
outline keeps a clean edge."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, reg, texdet, texdet3
from scipy import ndimage
from PIL import Image
def without_keyline(logo):
    """The logo with its outer white ring made transparent: white texels reachable from outside through white."""
    a = np.asarray(logo, dtype=np.uint8).copy()
    rgb = a[..., :3].astype(int); al = a[..., 3]
    white = (al > 40) & (rgb.min(axis=2) > 190) & (rgb.max(axis=2) - rgb.min(axis=2) < 40)
    outside = al <= 40
    # grow the outside region through white texels only
    reach = outside.copy()
    for _ in range(64):
        grown = ndimage.binary_dilation(reach, structure=np.ones((3, 3), bool)) & (white | outside)
        if (grown == reach).all(): break
        reach = grown
    ring = reach & white
    # semi-transparent rim texels next to the ring belong to it as well
    rim = ndimage.binary_dilation(ring, iterations=1) & (al < 250) & ~ring & (rgb.min(axis=2) > 150)
    out = a.copy(); out[ring | rim, 3] = 0
    return Image.fromarray(out, 'RGBA'), int(ring.sum()), float(ndimage.distance_transform_edt(ring).max())
def remove(name, T, grow=0):
    """Texture with the registered logo's keyline ring repainted: de-keylined logo over the shell rebuilt there."""
    fam, rest = name.split('_'); code = rest[:2]
    r = texdet3.regs()[name]
    rgb = T[..., :3].astype(np.float64); out = rgb.copy()
    z = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]
    shell = np.median(rgb[z], axis=0)
    changed = np.zeros((256, 256), bool)
    lg = reg.official(code); lg2, n, width = without_keyline(lg)
    for panel, v in r.items():
        col, al = reg.resized(reg.ORI[v['ori']](lg), v['w'], v['h'])
        col2, al2 = reg.resized(reg.ORI[v['ori']](lg2), v['w'], v['h'])
        band = (al - al2) > 0.03
        if grow: band = ndimage.binary_dilation(band, iterations=grow) & (al2 < 0.98)
        sub = out[v['y0']:v['y0']+v['h'], v['x0']:v['x0']+v['w']]
        # band texels take the de-keylined logo over the shell (the outline's own colour and coverage from the logo file)
        new = col2 * al2[..., None] + shell * (1 - al2[..., None])
        sub[band] = new[band]
        changed[v['y0']:v['y0']+v['h'], v['x0']:v['x0']+v['w']] |= band
    return out, changed
if __name__ == '__main__':
    import final, fixtex
    code = sys.argv[1]
    lg = reg.official(code); lg2, n, width = without_keyline(lg)
    print('keyline texels in the logo file', n, 'max half width', width, 'logo', lg.size)
    a = C.over(np.asarray(lg), (40, 40, 40)); b = C.over(np.asarray(lg2), (40, 40, 40))
    tiles = [C.up(a, 2), C.up(b, 2)]
    name = f'helmet02_{code}H0'
    T = final.helmet(name); out, ch = remove(name, T)
    res = T.copy(); pal = np.unique(T[..., :3].reshape(-1, 3), axis=0)
    res[ch, :3] = fixtex.nearest_palette(out[ch], pal)
    box = (30, 136, 126, 200); x0, y0, x1, y1 = box
    tiles += [C.up(T[y0:y1, x0:x1, :3], 6), C.up(res[y0:y1, x0:x1, :3], 6)]
    Image.fromarray(C.hstack(tiles)).save(C.WORK / f'view_keyline_{code}.png')
    print('texels changed', int(ch.sum()))
