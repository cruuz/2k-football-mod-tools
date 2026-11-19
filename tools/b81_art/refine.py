"""Last refinements of single kits, each checked against a real reference first (art/refs):
soften   a one-texel stair-stepped outline is anti-aliased along its own path (Bills blue alternate, Broncos white
         alternate): same line, same colours, partial coverage on the texels beside it
interior the Ravens' purple helmet takes the inside of the logo from the home helmet's registered official mark
mark     the Jaguars' teal alternate takes its white jaguar from the 2026 uniform diagram (the real design is black and
         white with a teal tongue), in place of the hard two-colour drawing
outline  the Vikings' horn gets the thin black outline the 2026 helmet has
modern   a Standard-shell logo is replaced by the modern shell's (where the two shells carried different drawings)"""
import sys, functools; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, fixtex, fixes7
from scipy import ndimage
from PIL import Image
LUM = np.array([0.299, 0.587, 0.114])
def shell_of(rgb, fam):
    return np.median(rgb[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
FREE = [False]      # set while a texture is rebuilt as new source art: its colours are not held to the old palette
def snap(T, out, changed):
    if FREE[0]:
        res = T.copy(); res[changed, :3] = np.clip(np.rint(out[changed]), 0, 255).astype(np.uint8)
        return res, 0.0
    pal = np.unique(T[..., :3].reshape(-1, 3), axis=0)
    res = T.copy(); s = fixtex.nearest_palette(out[changed], pal)
    err = float(np.abs(s.astype(np.float64) - out[changed]).max(axis=1).mean()) if changed.any() else 0.0
    res[changed, :3] = s
    return res, round(err, 2)
VENT_BOXES = ((28, 100, 64, 128), (66, 106, 100, 130), (66, 124, 100, 148), (28, 128, 64, 156), (98, 86, 128, 118), (98, 138, 128, 170))
def soften(T, fam, line, sigma=0.55, gain=1.45):
    """Anti-alias the logo's thin outline of colour ``line`` on plain shell. Loose pieces of the same outline colour in
    the painted-vent boxes (this kit drew its 2004 vents as outlines) go back to shell."""
    rgb = T[..., :3].astype(np.float64); shell = shell_of(rgb, fam); line = np.asarray(line, np.float64)
    axis = line - shell; n2 = float(axis @ axis)
    t = ((rgb - shell) @ axis) / n2                       # position on the shell-to-line colour axis
    off = np.linalg.norm(rgb - (shell + np.clip(t, 0, 1)[..., None] * axis), axis=2)
    on_axis = off < 34.0                                  # shell, line, or a blend of the two (not the logo's other colours)
    side = texdet.zone_mask(fam).copy(); side[:, 142:] = False
    hw = texdet.hardware(fam)[0].copy()
    if fam == 'helmet02':
        for v in fixtex.vent_regions(): hw &= ~ndimage.binary_dilation(v, iterations=3)
    ink = on_axis & side & (t > 0.35)
    lab, n = ndimage.label(ink, structure=np.ones((3, 3), bool))
    sizes = ndimage.sum(ink, lab, np.arange(1, n + 1)); out = rgb.copy(); stray = np.zeros((256, 256), bool); logo = np.zeros((256, 256), bool)
    rows = np.arange(256)[:, None]
    boxes = np.zeros((256, 256), bool)
    for (x0, y0, x1, y1) in VENT_BOXES: boxes[y0 - 4:y1 + 4, x0 - 4:x1 + 4] = True
    for upper in (False, True):
        half = (rows < 128) if upper else (rows >= 128)
        ids = [i + 1 for i in range(n) if (half & (lab == i + 1)).any()]
        if not ids: continue
        big = max(ids, key=lambda i: sizes[i - 1]); near = ndimage.binary_dilation(lab == big, iterations=5)
        for i in ids:
            comp = lab == i
            hard = (comp & hw).sum() >= 0.5 * comp.sum()                 # a crease or screw of the blank helmet
            vent = fam == 'helmet02' and sizes[i - 1] < 90 and (comp & boxes).sum() >= 0.6 * comp.sum()
            if i == big or ((near & comp).any() and not vent and not hard): logo |= comp
            elif vent and not hard: stray |= comp
    if stray.any():
        g = ndimage.binary_dilation(stray, iterations=2) & on_axis & side & ~logo & ~hw
        out = fixtex.nn_fill(out, g, keep_out=logo | (np.linalg.norm(rgb - shell, axis=2) > 8.0)); stray = g
    thin = logo & (t > 0.5)
    thin &= ~ndimage.binary_erosion(thin, structure=np.ones((3, 3), bool), iterations=1)      # only lines, not filled areas
    c = np.clip(ndimage.gaussian_filter(np.where(thin, 1.0, 0.0), sigma) * gain, 0, 1)
    region = ndimage.binary_dilation(thin, iterations=1) & on_axis & side & ~stray & ~(hw & ~logo)
    region &= ~((t > 0.5) & logo & ~thin)                  # a filled area of the line colour keeps its texels
    out[region] = shell + c[region][:, None] * axis
    return snap(T, out, region | stray) + (int(region.sum()), int(stray.sum()))
def interior(T, name, donor_tex, donor_name):
    """Inside of the registered logo (its rim stays as it is) from another kit's texture of the same mark."""
    import texdet3
    reg = texdet3.regs(); out = T[..., :3].astype(np.float64); changed = np.zeros((256, 256), bool)
    foot, ok = texdet3.footprint(name)
    for panel in ('lower', 'upper'):
        a, b = reg[name][panel], reg[donor_name][panel]
        dx, dy = b['x0'] - a['x0'], b['y0'] - a['y0']
        m = ndimage.binary_erosion(foot, iterations=3)
        rows = np.arange(256)[:, None]; m &= (rows >= 128) if panel == 'lower' else (rows < 128)
        ys, xs = np.nonzero(m)
        out[ys, xs] = donor_tex[ys + dy, xs + dx, :3]; changed |= m
    return snap(T, out, changed) + (int(changed.sum()),)
REF_JAX = (C.WORK.parent / 'refs' / 'diagrams' / 'Jacksonville_Jaguars.png', (6920, 40, 7360, 400))
@functools.lru_cache(None)
def jax_mark():
    a = np.asarray(Image.open(REF_JAX[0]).convert('RGB').crop(REF_JAX[1])).astype(np.float64)
    teal = np.median(a[:12].reshape(-1, 3), axis=0)
    m = np.linalg.norm(a - teal, axis=2) > 60
    lab, n = ndimage.label(m); sizes = ndimage.sum(m, lab, np.arange(1, n + 1))
    alpha = ndimage.binary_fill_holes(lab == 1 + int(np.argmax(sizes)))
    ys, xs = np.nonzero(alpha); y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return np.clip(np.dstack([a, alpha * 255.0])[y0:y1, x0:x1], 0, 255).astype(np.uint8)
def mark(T, fam, M, wide_vents=False):
    """The reference's mark in place of the drawn logo on both side panels (lower as it is, upper mirrored)."""
    rgb = T[..., :3].astype(np.float64); out = rgb.copy(); shell = shell_of(rgb, fam); zone = texdet.zone_mask(fam)
    dev = np.linalg.norm(rgb - shell, axis=2); changed = np.zeros((256, 256), bool); places = []
    for upper in (False, True):
        neutral = zone & ~texdet.hardware(fam)[0] & (((rgb.max(axis=2) < 48.0) & (rgb.max(axis=2) - rgb.min(axis=2) < 18.0)) | (rgb.min(axis=2) > 185.0))
        rows = np.arange(256)[:, None]; neutral &= (rows < 128) if upper else (rows >= 128); neutral[:, 142:] = False
        lab, n = ndimage.label(ndimage.binary_dilation(neutral, iterations=1)); sizes = ndimage.sum(neutral, lab, np.arange(1, n + 1))
        keep = (lab == 1 + int(np.argmax(sizes))) & neutral
        ys, xs = np.nonzero(keep); x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        places.append((upper, x0, y0, x1, y1))
        changed |= ndimage.binary_dilation(keep, iterations=3) & zone
    if wide_vents and fam == 'helmet02':
        # this kit's painted vents were redrawn wider than the 2004 ones: everything darker than the shell in the vent
        # boxes goes (the modern shell has its own vents in the geometry)
        hw = ndimage.binary_dilation(texdet.hardware(fam)[1] > 8, iterations=1)
        for v in fixtex.vent_regions(): hw &= ~ndimage.binary_dilation(v, iterations=4)
        hw &= ~ndimage.binary_dilation(fixtex.diamond_region(), iterations=4)
        lum = rgb @ LUM; sl = float(shell @ LUM)
        for (bx0, by0, bx1, by1) in ((28, 100, 64, 128), (66, 106, 100, 130), (66, 124, 100, 148), (28, 128, 64, 156), (98, 62, 138, 194)):
            box = np.zeros((256, 256), bool); box[by0:by1, bx0:bx1] = True
            # not hardware; or painted far darker than the blank helmet's faint crease there (a drawn slot, not a crease)
            changed |= box & zone & (dev > 10.0) & (~hw | ((lum < sl - 30.0) & (texdet.hardware(fam)[1] < 60)))
    not_shell = (dev > 12.0) | changed
    a = fixtex.nn_fill(out, changed, keep_out=not_shell); b = fixtex.fill(a, changed, keep_out=not_shell)
    out[changed] = 0.5 * a[changed] + 0.5 * b[changed]
    for upper, x0, y0, x1, y1 in places:
        h = y1 - y0; w = max(1, int(round(h * M.shape[1] / M.shape[0])))
        m = np.asarray(Image.fromarray(M).resize((w, h), Image.LANCZOS)).astype(np.float64)
        if upper: m = m[::-1]
        px = int(round((x0 + x1) / 2.0 - w / 2.0)); py = y0
        al = m[..., 3:4] / 255.0; region = out[py:py + h, px:px + w]
        region[:] = region * (1 - al) + m[..., :3] * al
        changed[py:py + h, px:px + w] |= al[..., 0] > 0.02
    return snap(T, out, changed) + (int(changed.sum()),)
def outline(T, fam, colour=(0, 0, 0)):
    """A thin soft dark outline round the white horn (wherever it runs on the atlas), on shell-coloured texels only."""
    rgb = T[..., :3].astype(np.float64); shell = shell_of(rgb, fam)
    white = ((rgb @ LUM) > 200) & (rgb.max(axis=2) - rgb.min(axis=2) < 40)
    lab, n = ndimage.label(white); sizes = ndimage.sum(white, lab, np.arange(1, n + 1))
    horn = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= 250])
    d = ndimage.distance_transform_edt(~horn)
    a = np.clip(1.7 - d, 0, 1) * 0.9
    gold = (rgb[..., 0] - rgb[..., 2] > 70.0)
    region = (a > 0.03) & ~horn & ~gold & ~ndimage.binary_dilation(gold, iterations=1) & ~(texdet.hardware(fam)[1] > 8)
    out = rgb.copy(); out[region] = rgb[region] * (1 - a[region][:, None]) + np.asarray(colour, np.float64) * a[region][:, None]
    return snap(T, out, region) + (int(region.sum()),)
MIRROR_ORI = {'id': 'fv', 'fh': 'r180', 'fv': 'id', 'r180': 'fh'}
def official(T, fam, code, panel, body_to_shell=False, old_line=None):
    """Both side logos rebuilt from the pack's official mark, resampled once to the texture's size (Lanczos, clean
    partial coverage on every edge), at the place, size and facing the home helmet's registered logo has on this
    shell. ``panel`` names the side whose registration is right on this shell; the other side is its mirror image.
    ``body_to_shell``: the mark's outer white keyline is dropped and its main body colour becomes the shell (the Bills'
    blue helmet shows the horn, the eye and the charge streak only, no buffalo outline)."""
    import reg, texdet3, keyline
    rgb = T[..., :3].astype(np.float64); out = rgb.copy(); shell = shell_of(rgb, fam); zone = texdet.zone_mask(fam)
    dev = np.linalg.norm(rgb - shell, axis=2); changed = np.zeros((256, 256), bool)
    hw = ndimage.binary_dilation(texdet.hardware(fam)[1] > 8, iterations=1)
    if fam == 'helmet02':
        for v in fixtex.vent_regions(): hw &= ~ndimage.binary_dilation(v, iterations=4)
        hw &= ~ndimage.binary_dilation(fixtex.diamond_region(), iterations=4)
    for upper in (False, True):
        _b, keep = fixes7.logo_box(rgb, fam, upper, pad=0)
        changed |= ndimage.binary_dilation(keep, iterations=3) & zone
    if fam == 'helmet02':
        for (bx0, by0, bx1, by1) in VENT_BOXES:          # what is left of this kit's outlined 2004 vents
            box = np.zeros((256, 256), bool); box[by0 - 4:by1 + 4, bx0 - 4:bx1 + 4] = True
            changed |= box & zone & (dev > 25.0) & ~hw
    ring = np.zeros((256, 256), bool)
    if fam == 'helmet02':
        # the dotted outline of the 2004 flag place (the kit's flag sits elsewhere): plain shell on a rebuilt helmet
        dm = fixtex.diamond_region()
        ring = ndimage.binary_dilation(dm, iterations=6) & ~ndimage.binary_erosion(dm, iterations=3)
        changed |= ring & zone & (dev > 12.0) & ~hw
    if old_line is not None:
        # loose pieces of the old drawn outline (its colour only, not touching any other colour, not a screw or decal of
        # the blank helmet) anywhere on the side panels
        line = np.asarray(old_line, np.float64); axis = line - shell
        t = ((rgb - shell) @ axis) / float(axis @ axis)
        off = np.linalg.norm(rgb - (shell + np.clip(t, 0, 1)[..., None] * axis), axis=2)
        side = zone.copy(); side[:, 138:] = False
        tdev = texdet.hardware(fam)[1].copy()
        if fam == 'helmet02':                               # the painted vents and the old flag diamond are not hardware now
            gone = ndimage.binary_dilation(fixtex.diamond_region(), iterations=4)
            for v in fixtex.vent_regions(): gone |= ndimage.binary_dilation(v, iterations=4)
            tdev[gone] = 0.0
        resid = side & (off < 34.0) & (t > 0.45) & (tdev < 60.0)
        other = side & (dev > 40.0) & ~((off < 34.0)) & (rgb.max(axis=2) - rgb.min(axis=2) > 60.0)     # a coloured decal (the flag)
        if float(shell.max() - shell.min()) > 60.0:         # a coloured shell: its own darker shading is not a decal
            other &= rgb.argmax(axis=2) != int(np.argmax(shell))
        other &= ~ring
        loose = resid & ~ndimage.binary_dilation(other, iterations=6)       # never part of a coloured decal (the flag)
        changed |= ndimage.binary_dilation(loose, iterations=1) & side & ~other
    not_shell = (dev > 12.0) | changed
    a = fixtex.nn_fill(out, changed, keep_out=not_shell); b = fixtex.fill(a, changed, keep_out=not_shell)
    out[changed] = 0.5 * a[changed] + 0.5 * b[changed]
    logo = reg.official(code); la = np.asarray(logo).astype(np.float64)
    # the mark file carries a soft drop shadow: only its solid shape counts, with a one-texel soft edge of its own colour
    solid = la[..., 3] >= 250.0
    dist, idx = ndimage.distance_transform_edt(~solid, return_indices=True)
    cov = np.clip(1.25 - dist, 0.0, 1.0)
    colour = la[idx[0], idx[1], :3]
    if body_to_shell:
        white = (colour.min(axis=2) > 190) & (colour.max(axis=2) - colour.min(axis=2) < 40)
        red = (colour[..., 0] > 150) & (colour[..., 1] < 90) & (colour[..., 2] < 110)
        inner = np.asarray(keyline.without_keyline(logo)[0])[..., 3] > 200          # the mark without its outer white ring
        border = float(ndimage.distance_transform_edt(white & inner & ~ndimage.binary_dilation(red, iterations=1) | (white & inner)).max())
        # white that stays: the horn and the streak's own white edge (inside the body, and the same width outside it)
        lab, n = ndimage.label(white & inner, structure=np.ones((3, 3), bool))
        at_streak = np.unique(lab[ndimage.binary_dilation(red, iterations=2) & (lab > 0)])
        keep_w = np.isin(lab, at_streak) | (white & (ndimage.distance_transform_edt(~red) <= max(2.0, 2.0 * border)))
        # the helmet decal's white edge is broader than the logo file's hairline (club photo of the 2026 helmet): two
        # mark pixels wider, never into the red
        keep_w = ndimage.binary_dilation(keep_w, iterations=2) & ~red
        layers = [np.where(keep_w, cov, 0.0), np.where(red, cov, 0.0)]
        paints = [np.array([255.0, 255.0, 255.0]), colour[red].mean(axis=0)]
    else:
        layers = None
        clean = Image.fromarray(np.dstack([colour, cov * 255.0]).astype(np.uint8), 'RGBA')
    r = texdet3.regs()[f'{fam}_{code}H0'][panel]
    places = {panel: (r['x0'], r['y0'], r['w'], r['h'], r['ori'])}
    other = 'upper' if panel == 'lower' else 'lower'
    places[other] = (r['x0'], 256 - r['y0'] - r['h'], r['w'], r['h'], MIRROR_ORI[r['ori']])
    FLIP = {'id': lambda m: m, 'fh': lambda m: m[:, ::-1], 'fv': lambda m: m[::-1], 'r180': lambda m: m[::-1, ::-1]}
    for x0, y0, w, h, ori in places.values():
        region = out[y0:y0 + h, x0:x0 + w]
        ok = ~hw[y0:y0 + h, x0:x0 + w] & zone[y0:y0 + h, x0:x0 + w]
        if layers is not None:
            small = [np.clip(np.asarray(Image.fromarray(FLIP[ori](m).astype(np.float32), 'F').resize((w, h), Image.LANCZOS), dtype=np.float64), 0, 1) for m in layers]
            tot = small[0] + small[1]; over = tot > 1
            for m in small: m[over] /= tot[over]
            blend = region * (1 - small[0] - small[1])[..., None] + paints[0] * small[0][..., None] + paints[1] * small[1][..., None]
            hit = (small[0] + small[1]) > 0.01
        else:
            col, al = reg.resized(reg.ORI[ori](clean), w, h); al3 = al[..., None]
            blend = region * (1 - al3) + col * al3; hit = al > 0.01
        region[ok] = blend[ok]
        changed[y0:y0 + h, x0:x0 + w] |= hit & ok
    return snap(T, out, changed) + (int(changed.sum()),)
KEEP_IOU = 0.80
KEEP_CORR = 0.92
KEPT_CORR = {}
_applies = {}
def standard_follows_modern(name, T):
    """Whether a Standard-shell texture's side logo is rebuilt from the modern shell's. Not when its logo still sits where
    the retail art has it (same ink for the most part: the retail placement reads level on the model already), not for
    the retail-art kits that have no league-project helmet, and not when there is no logo."""
    if name not in _applies:
        import json
        fam, sel = name.split('_')
        extra = json.load(open(C.WORK / 'extra_kits.json'))
        def ink(rgb):
            z = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]; shell = np.median(rgb[z], axis=0)
            m = z & (np.linalg.norm(rgb - shell, axis=2) > 40.0); m[:, 142:] = False; return m
        a = ink(T[..., :3].astype(np.float64)); b = ink(C.hretail(name)[..., :3].astype(np.float64))
        iou = float((a & b).sum()) / max(1.0, float((a | b).sum()))
        _applies[name] = bool(fam == 'helmet00' and sel not in extra and a.sum() >= 150 and iou < 0.8)
    return _applies[name]
def old_logo(rgb, fam, upper):
    """The old logo of one side with the parts of its outline that lie on the rim of the blank helmet's hardware."""
    zone = texdet.zone_mask(fam); shell = shell_of(rgb, fam); dev = np.linalg.norm(rgb - shell, axis=2)
    core = texdet.hardware(fam)[1] > 8
    rows = np.arange(256)[:, None]; half = (rows < 128) if upper else (rows >= 128)
    _b, lk = fixes7.logo_box(rgb, fam, upper, pad=0)
    if lk.sum() < 150: return np.zeros((256, 256), bool)
    rim = (dev > 40.0) & ~core & ndimage.binary_dilation(lk, iterations=6) & half & zone
    lab, n = ndimage.label(lk | rim, structure=np.ones((3, 3), bool))
    ids = np.unique(lab[lk]); whole = np.isin(lab, ids[ids > 0])
    return ndimage.binary_dilation(whole, iterations=3) & zone & half & ~core
def from_modern_shell(T, name, modern_tex):
    """Both side logos of a Standard-shell texture taken from the modern shell's finished texture through the surface
    map (shelltransfer.py): the same place, angle and size on the helmet, each side from its own side."""
    import shelltransfer
    fam = 'helmet00'; rgb = T[..., :3].astype(np.float64); out = rgb.copy(); shell = shell_of(rgb, fam); zone = texdet.zone_mask(fam)
    mrgb = modern_tex[..., :3].astype(np.float64); mask = np.zeros((256, 256), bool)
    for upper in (False, True):
        try: _b, mk = fixes7.logo_box(mrgb, 'helmet02', upper, pad=0)
        except Exception: continue
        if mk.sum() < 150: continue
        # the logo itself: its largest piece and the loose pieces that do not sit on a screw of the modern shell (a
        # recoloured shell can keep a dark square round a screw right beside the logo)
        lab, n = ndimage.label(mk, structure=np.ones((3, 3), bool)); sizes = ndimage.sum(mk, lab, np.arange(1, n + 1))
        strong = texdet.hardware('helmet02')[1] >= 60.0
        ids = []
        for i in range(n):
            comp = lab == i + 1; ys, xs = np.nonzero(comp); h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
            box = strong[max(0, ys.min() - 1):ys.max() + 2, max(0, xs.min() - 1):xs.max() + 2]
            square_round_a_screw = i != int(np.argmax(sizes)) and sizes[i] <= 260 and 0.6 <= w / h <= 1.7 and box.sum() >= 6
            if not square_round_a_screw: ids.append(i + 1)
        mk = np.isin(lab, ids)
        mask |= ndimage.binary_dilation(ndimage.binary_fill_holes(ndimage.binary_closing(mk, iterations=2)), iterations=1)
    screws = (texdet.hardware('helmet02')[1] >= 60.0) & mask          # never carry a modern-shell screw across
    for v in fixtex.vent_regions(): screws &= ~ndimage.binary_dilation(v, iterations=4)
    if screws.any(): mrgb = fixtex.nn_fill(mrgb, screws)
    col, al = shelltransfer.transfer(mrgb, mask)
    # a Standard-shell logo that already sits where the modern shell's does (same silhouette, both sides) stays as it
    # is: it is the sharper of the two
    same = True; rows = np.arange(256)[:, None]
    for upper in (False, True):
        half = (rows < 128) if upper else (rows >= 128)
        try: _b, k0 = fixes7.logo_box(rgb, fam, upper, pad=0)
        except Exception: k0 = np.zeros((256, 256), bool)
        cur = ndimage.binary_fill_holes(ndimage.binary_closing(k0, iterations=2)) if k0.sum() >= 150 else np.zeros((256, 256), bool)
        new = (al > 0.5) & half
        if cur.sum() < 150 and new.sum() < 150: continue
        # ... and shows the same picture there (a logo facing the other way can have nearly the same outline): the two
        # pictures, lightly blurred so a texel of shift does not count, must correlate
        region = ndimage.binary_dilation(cur | new, iterations=2) & half & zone
        prev = out * (1 - al[..., None]) + col * al[..., None]
        ga = np.stack([ndimage.gaussian_filter(rgb[..., c], 1.6) for c in range(3)], axis=-1)[region].ravel()
        gb = np.stack([ndimage.gaussian_filter(prev[..., c], 1.6) for c in range(3)], axis=-1)[region].ravel()
        corr = float(np.corrcoef(ga, gb)[0, 1]) if ga.std() > 1 and gb.std() > 1 else 1.0
        KEPT_CORR[(name, upper)] = round(corr, 3)
        if corr < KEEP_CORR: same = False
    if same: return T, 0.0, 0
    changed = np.zeros((256, 256), bool)
    for upper in (False, True):
        try: changed |= old_logo(rgb, fam, upper)
        except Exception: pass
    not_shell = (np.linalg.norm(rgb - shell, axis=2) > 12.0) | changed
    if changed.any():
        a = fixtex.nn_fill(out, changed, keep_out=not_shell); b = fixtex.fill(a, changed, keep_out=not_shell)
        out[changed] = 0.5 * a[changed] + 0.5 * b[changed]
    al = np.where(texdet.hardware(fam)[1] >= 60.0, 0.0, al) * zone
    out = out * (1 - al[..., None]) + col * al[..., None]
    changed |= al > 0.01
    return snap(T, out, changed) + (int(changed.sum()),)
def gold_to_white(T, fam):
    """The logo's gold fur becomes white with its own shading (the Jaguars' teal alternate carries the white jaguar):
    same drawing, same outline, spots and tongue; only texels of the logo that are gold or brown change."""
    rgb = T[..., :3].astype(np.float64); changed = np.zeros((256, 256), bool); out = rgb.copy()
    for upper in (False, True):
        _b, keep = fixes7.logo_box(rgb, fam, upper, pad=0)
        gold = ndimage.binary_dilation(keep, iterations=1) & (rgb[..., 0] - rgb[..., 2] > 38.0) & (rgb[..., 0] > 80.0) & (rgb[..., 0] >= rgb[..., 1] - 6.0)
        v = np.clip((rgb @ LUM) * 1.5, 0, 250)
        out[gold] = np.stack([v, v, v * 0.97], axis=-1)[gold]; changed |= gold
    return snap(T, out, changed) + (int(changed.sum()),)
def modern(T, name, modern_tex):
    """Both side logos of a Standard-shell texture replaced by the modern shell's own (same kit)."""
    fam = 'helmet00'; rgb = T[..., :3].astype(np.float64); out = rgb.copy(); shell = shell_of(rgb, fam); zone = texdet.zone_mask(fam)
    mrgb = modern_tex[..., :3].astype(np.float64); changed = np.zeros((256, 256), bool); jobs = []
    for upper in (False, True):
        (mx0, my0, mx1, my1), mk = fixes7.logo_box(mrgb, 'helmet02', upper, pad=0)
        (x0, y0, x1, y1), lk = fixes7.logo_box(rgb, fam, upper, pad=0)
        shape = ndimage.binary_dilation(ndimage.binary_fill_holes(ndimage.binary_closing(mk[my0:my1, mx0:mx1], iterations=2)), iterations=1)
        core = texdet.hardware(fam)[1] > 8                      # the blank helmet's own screws, ear hole, creases
        dev = np.linalg.norm(rgb - shell, axis=2)
        rows = np.arange(256)[:, None]; half = (rows < 128) if upper else (rows >= 128)
        # the old logo with the part of its outline that lies on the hardware's rim (not the hardware itself)
        rim = (dev > 40.0) & ~core & ndimage.binary_dilation(lk, iterations=6) & half & zone
        lab, n = ndimage.label(lk | rim, structure=np.ones((3, 3), bool))
        whole = np.isin(lab, np.unique(lab[lk])[1:] if (lab[lk] == 0).any() else np.unique(lab[lk]))
        old = ndimage.binary_dilation(whole, iterations=3) & zone & half & ~core
        # the old outline where it ran over the blank helmet's shading by the ear hole: thin black pieces only (the ear
        # hole's own disc is thick and stays)
        black = (rgb.max(axis=2) < 80.0) & ndimage.binary_dilation(lk, iterations=10) & half & zone
        thick = ndimage.binary_opening(black, structure=np.ones((3, 3), bool), iterations=3)
        thick = ndimage.binary_dilation(thick, structure=np.ones((3, 3), bool), iterations=1) & black
        old |= ndimage.binary_dilation(black & ~thick, iterations=1) & ~thick & half & zone
        changed |= old
        other = (dev > 25.0) & ~ndimage.binary_dilation(whole, iterations=3) & half       # the flag, screws, the ear hole
        px0 = int(round((x0 + x1) / 2.0 - shape.shape[1] / 2.0)); py0 = int(round((y0 + y1) / 2.0 - shape.shape[0] / 2.0))
        best = None
        for sx in range(0, -7, -1):
            for sy in ((0, 1, 2, 3, 4) if not upper else (0, -1, -2, -3, -4)):
                px, py = px0 + sx, py0 + sy
                if px < 24 or py < 2 or py + shape.shape[0] > 254: continue
                hit = int((other[py:py + shape.shape[0], px:px + shape.shape[1]] & shape).sum())
                cost = 2.0 * hit + abs(sx) + abs(sy)
                if best is None or cost < best[0]: best = (cost, px, py, hit)
        if best is None: best = (0, px0, py0, 0)
        clear = shape & ~other[best[2]:best[2] + shape.shape[0], best[1]:best[1] + shape.shape[1]]
        if not upper: jobs.append((clear, mrgb[my0:my1, mx0:mx1], best[1], best[2]))
    not_shell = (np.linalg.norm(rgb - shell, axis=2) > 12.0) | changed
    a = fixtex.nn_fill(out, changed, keep_out=not_shell); b = fixtex.fill(a, changed, keep_out=not_shell)
    out[changed] = 0.5 * a[changed] + 0.5 * b[changed]
    for shape, block, px, py in jobs:
        h, w = shape.shape; region = out[py:py + h, px:px + w]; region[shape] = block[shape]
        changed[py:py + h, px:px + w] |= shape
    res, err = snap(T, out, changed)
    res, m = fixes7.mirror_panel(res, fam, True)          # the right side is the left side's mirror image, as on the modern shell
    return res, err, int(changed.sum() + m.sum())
if __name__ == '__main__':
    import fixtex2, final
    inv = {v: k for k, v in C.TEAMS.items()}
    tiles = []
    def show(label, before, after, box):
        y0, y1, x0, x1 = box
        t = C.hstack([C.up(before[y0:y1, x0:x1, :3], 4), C.up(after[y0:y1, x0:x1, :3], 4)], gap=2); tiles.append(t)
    T, r, d, m = fixtex2.cleanup('helmet02_03H8'); a, err, n, st = soften(r, 'helmet02', (255, 255, 255)); print('BUF 8 soften', err, n, st); show('BUF', r, a, (138, 205, 30, 136))
    T, r, d, m = fixtex2.cleanup('helmet02_08H5'); a, err, n, st = soften(r, 'helmet02', np.median(r[..., :3][(r[..., :3].astype(float) @ LUM) < 70], axis=0)); print('DEN 5 soften', err, n, st); show('DEN', r, a, (140, 205, 30, 136))
    T, r, d, m = fixtex2.cleanup('helmet02_02H2'); T0, r0, d0, m0 = fixtex2.cleanup('helmet02_02H0'); a, err, n = interior(r, 'helmet02_02H2', r0, 'helmet02_02H0'); print('BAL 2 interior', err, n); show('BAL', r, a, (144, 190, 30, 120))
    T, r, d, m = fixtex2.cleanup('helmet02_12H6'); a, err, n = mark(r, 'helmet02', jax_mark(), wide_vents=True); print('JAX 6 mark', err, n, jax_mark().shape); show('JAX', r, a, (100, 215, 26, 132)); jm = a
    T, r, d, m = fixtex2.cleanup(f"helmet02_{inv['MIN']}H0"); a, err, n = outline(r, 'helmet02'); print('MIN outline', err, n); show('MIN', r, a, (150, 215, 30, 136))
    T, r, d, m = fixtex2.cleanup('helmet00_12H6'); a, err, n = modern(r, 'helmet00_12H6', jm); print('JAX 6 standard', err, n); show('JAX00', r, a, (125, 215, 26, 132))
    W = max(t.shape[1] for t in tiles)
    Image.fromarray(np.concatenate([np.pad(t, ((0, 6), (0, W - t.shape[1]), (0, 0))) for t in tiles], axis=0)).save(C.WORK / 'view_refine.png')
