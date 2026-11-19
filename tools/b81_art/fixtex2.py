"""Old-logo ink on FINAL helmet textures: explained by the retail decal, outside the registered official logo, not part
of a retail piece that is still whole (a logo that never changed)."""
import sys, json; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, texdet2, texdet3, reg, final, fixtex
from scipy import ndimage
from PIL import Image, ImageDraw
MIN_GOOD = 0.54
NEAR = 24      # old ink is looked for this close to the new logo (texels)
OVERRIDES = json.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'overrides.json')))
def zone(fam, vents_cleared=None):
    """Side panels minus the blank helmet's hardware; on helmet02 the painted vents are no longer hardware."""
    hw = texdet.hardware(fam)[0].copy()
    if fam == 'helmet02':
        for m in fixtex.vent_regions(): hw &= ~ndimage.binary_dilation(m, iterations=2)
    return texdet.zone_mask(fam) & ~hw
def old_ink(name, T):
    fam, rest = name.split('_'); code = rest[:2]
    cur = T[..., :3].astype(float)
    z = zone(fam)
    shell_cur = np.median(cur[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
    cur_dev = np.linalg.norm(cur - shell_cur, axis=2)
    ink = z & (cur_dev > 30.0)
    exp = np.zeros((256, 256), bool); intact = np.zeros((256, 256), bool)
    for r in texdet2.refs_for(name):
        ret = C.hretail(r)[..., :3].astype(float)
        zr = texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]
        shell_ret = np.median(ret[zr], axis=0)
        a, ok = texdet2.explained(cur, ret, shell_cur, shell_ret)
        ok &= z
        # retail pieces that are still whole are the logo itself (it never changed), not a leftover
        rdecal = z & (np.linalg.norm(ret - shell_ret, axis=2) > 40.0)
        lab, n = ndimage.label(rdecal, structure=np.ones((3, 3), bool))
        if n:
            idx = np.arange(1, n + 1)
            size = ndimage.sum(rdecal, lab, idx); kept = ndimage.sum(ok & (a >= 0.8), lab, idx)
            whole = [int(i) for i, s, k in zip(idx, size, kept) if s >= 24 and k / s >= 0.8]
            intact |= np.isin(lab, whole)
        exp |= ok
    intact = ndimage.binary_dilation(intact, iterations=1)
    foot = np.zeros((256, 256), bool); panels = {}
    r = texdet3.regs().get(name) or {}
    for panel, v in r.items():
        x0, y0, x1, y1 = reg.PANELS[panel]
        good = v['good'] >= MIN_GOOD
        if good:
            col, al = reg.resized(reg.ORI[v['ori']](reg.official(code)), v['w'], v['h'], key=(code, v['ori']))
            sub = cur[v['y0']:v['y0']+v['h'], v['x0']:v['x0']+v['w']]
            core = al > 0.9
            now = float((core & (np.linalg.norm(sub - col, axis=2) < 45)).sum()) / max(int(core.sum()), 1)
            good = now >= MIN_GOOD - 0.08          # the final texture still carries this logo here
            if good:
                foot[v['y0']:v['y0']+v['h'], v['x0']:v['x0']+v['w']] |= al > 0.04
        panels[panel] = bool(good)
    if len(panels) == 2 and not all(panels.values()):
        panels = {k: False for k in panels}; foot[:] = False     # one side alone is not a registration
    elif len(r) == 2 and abs(r['upper']['w'] - r['lower']['w']) > 3:
        panels = {k: False for k in panels}; foot[:] = False
    footg = ndimage.binary_dilation(foot, iterations=1)
    pz = np.zeros((256, 256), bool)
    for panel, good in panels.items():
        if good:
            x0, y0, x1, y1 = reg.PANELS[panel]; pz[y0:y1, x0:x1] = True
    near = ndimage.binary_dilation(foot, iterations=NEAR) & pz
    near[:, 142:] = False                       # the crown stripes start here
    left = ink & exp & ~footg & ~intact & near
    # drop single specks of one or two texels that are barely off the shell (palette noise)
    lab, n = ndimage.label(left, structure=np.ones((3, 3), bool))
    if n:
        idx = np.arange(1, n + 1)
        size = ndimage.sum(left, lab, idx); peak = ndimage.maximum(cur_dev, lab, idx)
        drop = [int(i) for i, s, p in zip(idx, size, peak) if s <= 2 and p < 60]
        left &= ~np.isin(lab, drop)
    style = name.split('_')[1][3:]
    ov = OVERRIDES.get(f'{code}_{style}:{fam}', {})
    if f'{code}_{style}' not in OVERRIDES.get('old_ink_reviewed', {}).get(fam, []):
        left[:] = False                 # the detector's findings on this texture were not reviewed by eye: left as it is
    for box in ov.get('add', []):       # [x0,y0,x1,y1]: ink in the box is old (reviewed by eye)
        m = np.zeros((256, 256), bool); m[box[1]:box[3], box[0]:box[2]] = True
        left |= m & (cur_dev > float(ov.get('add_dev', 30.0))) & ~foot & texdet.zone_mask(fam)   # reviewed by eye: hardware mask not applied
    for box in ov.get('keep', []):
        left[box[1]:box[3], box[0]:box[2]] = False
    # a loose piece that is mostly old ink is old as a whole (its outline or fringe is not the retail colour any more)
    loose = ink & ~footg & near
    lab, n = ndimage.label(loose, structure=np.ones((3, 3), bool))
    if n and left.any():
        idx = np.arange(1, n + 1)
        size = ndimage.sum(loose, lab, idx); old = ndimage.sum(left, lab, idx)
        whole = [int(i) for i, s, o in zip(idx, size, old) if o >= 3 and o / s >= 0.3 and s <= 400]
        left = left | np.isin(lab, whole)
    grown = ndimage.binary_dilation(left, iterations=int(ov.get('grow', 2))) & ~footg & (cur_dev > float(ov.get('grow_dev', 8.0))) & z
    if ov.get('despeckle') or ov.get('gold'):
        # the dark alternate's drawn logo (beta 80): stray near-white texels all over it, and a gold arc of the 2004 outline
        box = np.zeros((256, 256), bool); box[20:236, 20:142] = True
        box &= texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]
        r_, g_, b_ = cur[..., 0], cur[..., 1], cur[..., 2]
        extra_ = np.zeros((256, 256), bool)
        if ov.get('despeckle'):
            white = box & (cur.min(axis=2) > 105) & (cur.max(axis=2) - cur.min(axis=2) < 40)
            lab, n = ndimage.label(white, structure=np.ones((3, 3), bool))
            if n:
                sizes = ndimage.sum(white, lab, np.arange(1, n + 1))
                extra_ |= np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ <= 5])
        if ov.get('gold'):
            extra_ |= ndimage.binary_dilation(box & (r_ - b_ > 55) & (r_ > 95) & (g_ > 60), iterations=1) & box & ~((r_ > 140) & (g_ < 70))
        left = left | extra_
        grown = grown | extra_
    # squares of the old (black) shell colour left around a screw, the flag or the shield on a recoloured shell
    boxes = np.zeros((256, 256), bool)
    for box in ov.get('shell_boxes', []):
        m = np.zeros((256, 256), bool); m[box[1]:box[3], box[0]:box[2]] = True
        boxes |= m & (cur.max(axis=2) < 30.0)
    for box in ov.get('erase', []):
        # reviewed by eye: everything in the box that is not shell and not inside the official logo goes back to shell
        m = np.zeros((256, 256), bool); m[box[1]:box[3], box[0]:box[2]] = True
        boxes |= m & (cur_dev > 4.0) & ~foot & texdet.zone_mask(fam)
        if ov.get('erase_edge_neutral'):
            # the registered footprint is a texel wide of this club's drawn logo: grey or dark neutral texels on its
            # rim (darker than the shell, so neither the logo's light outline nor its colour) are the old piece too
            band = foot & ~ndimage.binary_erosion(foot, iterations=int(ov['erase_edge_neutral']))
            lum = cur @ np.array([0.299, 0.587, 0.114]); shell_l = float(shell_cur @ np.array([0.299, 0.587, 0.114]))
            boxes |= m & band & (cur.max(axis=2) - cur.min(axis=2) < 45.0) & (lum < shell_l - 14.0) & texdet.zone_mask(fam)
    left = left | boxes
    return dict(left=left, boxes=boxes, paint=left | grown | boxes, foot=foot, panels=panels, other=ink & ~exp & ~footg & pz, ink=ink)
def cleanup(name):
    T = final.helmet(name)
    d = old_ink(name, T)
    res, masks = fixtex.cleanup(name, tex=T, foot=ndimage.binary_dilation(d['foot'], iterations=1), extra=d['paint'], shell_only=d['boxes'])
    fam = name.split('_')[0]; key = name.split('_')[1][:2] + '_' + name.split('_')[1][3:]
    ov2 = OVERRIDES.get(f'{key}:{fam}', {})
    if ov2.get('real_mark'):
        # the dark alternate: the real front-facing mark replaces the stand-in drawing (see realmark.py for the source)
        import realmark
        res, ch, _info = realmark.apply(name, res)
        masks['real_mark'] = ch
        return T, res, d, masks
    if key in OVERRIDES.get('keyline', {}).get(fam, []):
        # the logo file's white outer keyline (the real decal has none): the ring goes back to shell
        import keyline
        out, ch = keyline.remove(name, res, grow=int(OVERRIDES.get('keyline_grow', {}).get(key, 0)))
        pal = np.unique(T[..., :3].reshape(-1, 3), axis=0)
        res = res.copy(); res[ch, :3] = fixtex.nearest_palette(out[ch], pal)
        masks['keyline'] = ch
    if ov2.get('rot180_upper') or ov2.get('mirror_upper') or ov2.get('mirror_lower') or ov2.get('lower_from_modern'):
        import fixes7
        before = res.copy()
        if ov2.get('rot180_upper'):
            # the right-side logo was laid the wrong way round for its island (its word read backwards in game)
            (x0, y0, x1, y1), keep = fixes7.logo_box(res[..., :3].astype(np.float64), fam, True, pad=0)
            # only the logo's own texels turn (the filled logo shape and its half-turn image), never a screw beside it
            shape = ndimage.binary_fill_holes(ndimage.binary_closing(keep[y0:y1, x0:x1], iterations=2))
            both = shape & shape[::-1, ::-1]
            res = res.copy(); block = before[y0:y1, x0:x1, :3]
            res[y0:y1, x0:x1, :3] = np.where(both[..., None], block[::-1, ::-1], block)
        if ov2.get('mirror_upper'):
            # the right-side logo was not mirrored for its island (upside down in game): the left side's, mirrored
            res, _box = fixes7.mirror_upper_from_lower(res, fam)
        if ov2.get('mirror_lower'):
            # standard shell: the left-side logo was laid facing the back of the helmet (the modern shell and the retail
            # art have it facing forward on both sides): it becomes the right side's mirror image
            res, _m = fixes7.mirror_panel(res, fam, False)
        if ov2.get('lower_from_modern'):
            res, _m = fixes7.lower_from_modern(res, name)
        masks['reoriented'] = (res[..., :3] != before[..., :3]).any(axis=2)
    rf = ov2.get('refine')
    if rf:
        import refine
        before = res.copy()
        refine.FREE[0] = bool(rf.get('free'))
        if rf.get('official'):
            o_ = rf['official']
            line = None
            if o_.get('old_line') == 'white': line = (255, 255, 255)
            elif o_.get('old_line') == 'dark': line = np.median(res[..., :3][(res[..., :3].astype(np.float64) @ refine.LUM) < 70], axis=0)
            res = refine.official(res, fam, name.split('_')[1][:2], o_['panel'], body_to_shell=bool(o_.get('body_to_shell')), old_line=line)[0]
        if rf.get('soften'):
            line = (255, 255, 255) if rf['soften'] == 'white' else np.median(res[..., :3][(res[..., :3].astype(np.float64) @ refine.LUM) < 70], axis=0)
            res = refine.soften(res, fam, line)[0]
        if rf.get('interior_from'):
            donor = name[:11] + 'H' + rf['interior_from'][3:] if False else f"{fam}_{rf['interior_from'][:2]}H{rf['interior_from'][3:]}"
            res = refine.interior(res, name[:11] + 'H' + name[12:], cleanup(donor)[1], donor)[0]
        if rf.get('mark') == 'jax':
            res = refine.mark(res, fam, refine.jax_mark(), wide_vents=True)[0]
        if rf.get('outline'):
            res = refine.outline(res, fam)[0]
        if rf.get('gold_to_white'):
            res = refine.gold_to_white(res, fam)[0]
        if rf.get('modern'):
            res = refine.modern(res, name, cleanup('helmet02_' + name.split('_')[1])[1])[0]
        refine.FREE[0] = False
        masks['refined'] = (res[..., :3] != before[..., :3]).any(axis=2)
    return T, res, d, masks
def pair(name, s=3, box=(0, 16, 150, 240)):
    T, res, d, masks = cleanup(name)
    x0, y0, x1, y1 = box
    a = T[y0:y1, x0:x1, :3]; b = res[y0:y1, x0:x1, :3]
    mk = a.copy(); mk[d['paint'][y0:y1, x0:x1]] = (255, 0, 255)
    t = C.hstack([C.up(a, s), C.up(mk, s), C.up(b, s)], gap=2)
    im = Image.fromarray(t); dr = ImageDraw.Draw(im)
    dr.text((3, 2), f"{name[6:]} {C.TEAMS[name[9:11]]} old={int(d['left'].sum())} reg={d['panels']}", fill=(255, 255, 0))
    return np.asarray(im), int(d['left'].sum())
if __name__ == '__main__':
    out = sys.argv[1]; names = sys.argv[2:]
    tiles = [pair(n)[0] for n in names]
    rows = [C.hstack(tiles[i:i+2], gap=10) for i in range(0, len(tiles), 2)]
    W = max(r.shape[1] for r in rows)
    Image.fromarray(np.concatenate([np.pad(r, ((0, 8), (0, W - r.shape[1]), (0, 0))) for r in rows], axis=0)).save(C.WORK / out)
