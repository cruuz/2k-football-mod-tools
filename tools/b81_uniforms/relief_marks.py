#!/usr/bin/env python3
"""b81-uniforms relief rollout, stage 1: where each kit's relief must follow its own colour textures.

For every 2026 kit package (178) this reads the kit's FINAL colour textures (the released v0.9 textures with this job's
uniform pass applied) and finds, in native texels:
  * the collar opening, as bump_true reads it (the flat fill inside the V), any fill colour;
  * the painted collar shield (its own outline, inside the box the shield pass recorded, or found for the eight kits
    that keep the small 8x10 shield);
  * the painted maker's mark on the sleeve, on the torso shoulder cap where a kit paints it there (with the wrap-over
    slivers), on the pants, and the pants shield. Boxes come from uniforms/audit/swoosh/<TEAM>.json and are checked
    against the texture: the mark is the texels in and just around the box that sit closer to the audited mark colour
    than to the fabric under it (or, with no single colour, that differ clearly from the fabric).

  relief_marks.py BASE_DIR OUT_DIR      (BASE_DIR from RELIEF/tools/export_base.py: <SEL>/torso.png, sleeve.png, pants.png)
writes OUT_DIR/marks.json (boxes, audit boxes, flags) and OUT_DIR/masks/<SEL>.npz (one native mask per mark).
"""
import sys, json, glob, re
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

U = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms')
FIX = U / 'work/fix'
# the eight packages that keep the small shield (no 2026 picture of the look): found below the V by its colours
# boxes read texel by texel (RELIEF/survey/small_shields.png): 07H9/A9 sits inside a silver ring, 25H7/A7 inside the gold
# "Faithful" letters, 28H7/A7 above "Music City", and on 11H4/A4 the black collar tip covers all but its rim.
SMALL = {'07H9': [158, 80, 166, 89], '07A9': [158, 80, 166, 89], '11H4': [157, 76, 165, 81], '11A4': [157, 76, 165, 81],
         '25H7': [157, 71, 164, 80], '25A7': [157, 71, 164, 80], '28H7': [157, 71, 165, 82], '28A7': [157, 71, 165, 82]}


def rgb(path):
    return np.asarray(Image.open(path).convert('RGB')).astype(int)


def hexcol(text):
    m = re.search(r'#([0-9A-Fa-f]{6})', text or '')
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else None


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None


def mode_colour(pixels):
    flat = pixels.reshape(-1, 3)
    colours, counts = np.unique(flat, axis=0, return_counts=True)
    return colours[counts.argmax()]


# -- the collar opening ------------------------------------------------------------------------------------------------

FRONT_SEED, BACK_SEED = (4, 161), (4, 390)
FRONT_COLS, BACK_COLS = (125, 200), (350, 432)


def opening(t):
    """The flat fill inside the collar (front V and back neck), native texels. bump_true read only the stock grey
    (220); kits fill it with their own colour (purple, tan, dark grey, a darker orange), so the fill is taken at a seed
    inside the opening, and the region kept to the opening's own columns so it cannot run into a body of the same
    colour."""
    H, W = t.shape[:2]
    out = np.zeros((H, W), bool)
    for (r, c), (c0, c1) in ((FRONT_SEED, FRONT_COLS), (BACK_SEED, BACK_COLS)):
        colour = t[r, c]
        near = (np.abs(t - colour).max(-1) < 14)
        near[:, :c0] = False; near[:, c1:] = False; near[int(H * 0.62):] = False
        lab, n = ndi.label(near)
        if lab[r, c]:
            out |= lab == lab[r, c]
    return out


# -- painted marks -----------------------------------------------------------------------------------------------------

def mark_in(t, box, colour=None, grow=8, contrast=60, base=None):
    """texels of the painted mark around ``box``: whole components inside the box grown by ``grow`` that overlap the box
    grown by 3 (half their texels or more) and stay clear of the grown region's edge (a stripe or band that runs on past
    the mark is not the mark; the audit boxes are search boxes, a few texels off on some kits)"""
    H, W = t.shape[:2]
    x0, y0, x1, y1 = box
    X0, Y0, X1, Y1 = max(x0 - grow, 0), max(y0 - grow, 0), min(x1 + grow, W), min(y1 + grow, H)
    part = t[Y0:Y1, X0:X1]
    info = {}
    if colour is not None:
        c = np.array(colour)
        if base is None:
            far = np.abs(part - c).max(-1) > 40
            base = mode_colour(part[far]) if far.any() else mode_colour(part)
            sep = int(np.abs(c - base).max())
            if sep < 24:                             # a mark the fabric hides: treat as no single colour
                colour = None
        base = np.array(base)
        info.update(base='#%02X%02X%02X' % tuple(base), separation=int(np.abs(c - base).max()))
        m = np.abs(part - c).sum(-1) < np.abs(part - base).sum(-1)
    if colour is None:
        base = mode_colour(part)
        m = np.abs(part - base).max(-1) > contrast
        info.update(base='#%02X%02X%02X' % tuple(base), method='contrast')
    full = np.zeros((H, W), bool)
    full[Y0:Y1, X0:X1] = m
    lab, n = ndi.label(full, structure=np.ones((3, 3)))
    inner = np.zeros((H, W), bool); inner[max(y0 - 3, 0):y1 + 3, max(x0 - 3, 0):x1 + 3] = True
    edge = np.zeros((H, W), bool)                    # the grown region's own border, not the texture's edge
    if Y0 > 0: edge[Y0, X0:X1] = True
    if Y1 < H: edge[Y1 - 1, X0:X1] = True
    if X0 > 0: edge[Y0:Y1, X0] = True
    if X1 < W: edge[Y0:Y1, X1 - 1] = True
    keep = []
    for i in range(1, n + 1):
        comp = lab == i
        if (comp & inner).sum() >= 0.5 * comp.sum() and not (comp & edge).any():
            keep.append(i)
    full = ndi.binary_fill_holes(np.isin(lab, keep))
    return full, info


# The 12x16 collar shield (170 packages) and the pants shield are one stamp each: their outlines are the texels that are
# shield on every kit with that stamp (RELIEF: the consensus of 170 and 129 kits read one by one, 100 percent each).
COLLAR_STAMP = np.array([[c in cols for c in range(12)] for cols in (
    (5, 6), (4, 5, 6, 7), *[tuple(range(12))] * 11, tuple(range(1, 11)), tuple(range(3, 9)), (5, 6))])
PANTS_STAMP = np.array([[c in cols for c in range(9)] for cols in (
    (4,), *[tuple(range(9))] * 6, tuple(range(1, 8)), (4,))])
PANTS_STAMP_BOX = [406, 29, 415, 38]


def stamp(shape, box, template):
    m = np.zeros(shape, bool)
    m[box[1]:box[3], box[0]:box[2]] = template
    return m


def shield_in(t, box):
    """the painted collar shield: texels in its outline box that differ from the fabric ring around it; filled"""
    H, W = t.shape[:2]
    x0, y0, x1, y1 = box
    ring = np.zeros((H, W), bool); ring[max(y0 - 2, 0):y1 + 2, max(x0 - 2, 0):x1 + 2] = True
    ring[y0:y1, x0:x1] = False
    fabric = mode_colour(t[ring])
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = np.abs(t[y0:y1, x0:x1] - fabric).max(-1) > 12     # the anti-aliased tip counts
    m = ndi.binary_fill_holes(ndi.binary_closing(m, iterations=1)) | m
    m &= np.pad(np.ones((y1 - y0, x1 - x0), bool), ((y0, H - y1), (x0, W - x1)))
    return m, '#%02X%02X%02X' % tuple(fabric)


# Where the audit's box or colour does not find the painted mark (read texel by texel in RELIEF/survey): the Seahawks
# icicle sleeves carry a navy swoosh (#0B2D50) on the dark teal icicles, lower and longer than the audit box says.
OVERRIDES = {sel: {'right_arm': dict(box=[62, 5, 81, 25], colour='#0B2D50', base=(0x16, 0x3D, 0x49)),
                   'left_arm': dict(box=[44, 70, 64, 90], colour='#0B2D50', base=(0x16, 0x3D, 0x49))}
             for sel in ('26H3', '26A3')}
# Marks that touch a stripe or patch of a near colour, tone-on-tone marks and the faint wrap-over slivers: read inside a
# CLIP box only (RELIEF/survey/misses.png). (texture key) -> (clip box, colour or None for "differs from the fabric",
# contrast for that case)
CLIPS = {
    **{(s, 'right_arm_main'): ([57, 0, 82, 15], '#B87333', None) for s in ('00H7', '00A7')},     # copper, patch below
    **{(s, 'left_arm_main'): ([44, 64, 68, 79], '#B87333', None) for s in ('00H7', '00A7')},
    **{(s, 'right_arm_main'): ([58, 0, 83, 15], '#1C2433', None) for s in ('37A0',)},             # navy, stripe below
    **{(s, 'left_arm_main'): ([44, 64, 70, 79], '#1C2433', None) for s in ('37A0',)},
    **{(s, 'pants_mark'): ([86, 26, 109, 38], None, 3) for s in ('16H4', '16A4')},               # white (f8-fe) on white (f4-f6)
    **{(s, 'pants_mark'): ([86, 26, 109, 38], '#FFFFFF', None) for s in ('17H0', '17A0')},       # audit said black
    **{(s, 'pants_mark'): ([86, 26, 109, 38], '#D0D0D0', None) for s in ('17H8', '17A8')},
    **{(s, 'left_arm_back_sliver'): ([492, 16, 496, 24], None, 20) for s in ('23H11', '23A11')},
    **{(s, 'pants_shield'): ([93, 42, 102, 51], None, 12) for s in ('07H9', '07A9')},           # throwback: own place
    ('27H0', 'right_arm_sleeve_top_sliver'): ([60, 0, 82, 4], None, 20),
    **{(s, 'right_arm_back_sliver'): ([280, 13, 285, 23], None, 20) for s in ('27H0',)},
    **{(s, 'left_arm_back_sliver'): ([497, 15, 501, 23], None, 20) for s in ('27A0',)},
    **{(s, 'right_arm_back_sliver'): ([497, 15, 501, 23], None, 20) for s in ('27H6', '27A6')},
}


def mark_clip(t, box, colour, contrast):
    """the mark inside a clip box: texels closer to its colour than to the fabric (or differing from the fabric by
    more than ``contrast``), filled"""
    H, W = t.shape[:2]
    x0, y0, x1, y1 = box
    part = t[y0:y1, x0:x1]
    base = mode_colour(part)
    if colour:
        c = np.array(hexcol(colour))
        far = np.abs(part - c).max(-1) > 40
        base = mode_colour(part[far]) if far.any() else base
        m = np.abs(part - c).sum(-1) < np.abs(part - base).sum(-1)
    else:
        m = np.abs(part - base).max(-1) >= max(contrast, 1)
    full = np.zeros((H, W), bool); full[y0:y1, x0:x1] = m
    return ndi.binary_fill_holes(full), dict(base='#%02X%02X%02X' % tuple(base), method='clip')


# -- audit -------------------------------------------------------------------------------------------------------------

def audit_rows():
    rows = {}
    for f in sorted(glob.glob(str(U / 'audit/swoosh/*.json'))):
        for k in json.load(open(f))['kits']:
            also = [m.group(0) for a in k.get('also', []) for m in [re.search(r'\b\d\d[HA]\d+\b', a)] if m]
            for s in [k['selector']] + also:
                rows.setdefault(s, k)
    return rows


def torso_or_sleeve(where):
    return 'torso' if where.startswith('shoulder cap of the torso') else 'sleeve'


def main():
    base, out = Path(sys.argv[1]), Path(sys.argv[2]); (out / 'masks').mkdir(parents=True, exist_ok=True)
    kits = [k['selector'] for k in json.load(open(base / 'base.json'))['kits']]
    audit = audit_rows()
    shield_boxes = {k: v['outline_box'] for k, v in json.load(open(FIX / 'SHIELD/check.json')).items()}
    shield_boxes.update({'04H2': [155, 71, 167, 87], '04A2': [155, 71, 167, 87],     # MARKS3 B1: the one shield kept
                         '03H8': [155, 82, 167, 98], '03A8': [155, 82, 167, 98]})    # MARKS3 C2: the shield moved down
    report = {}
    for sel in kits:
        tex = {p: rgb(base / sel / f'{p}.png') for p in ('torso', 'sleeve', 'pants')}
        masks, row = {}, dict(flags=[])
        hole = opening(tex['torso'])
        rows_, cols_ = np.nonzero(hole[:, :200])
        vtip = int(rows_.max()); row['opening'] = dict(texels=int(hole.sum()), front_texels=int(hole[:, :200].sum()),
                                                       v_tip_row=vtip, v_tip_col=float(cols_[rows_ == vtip].mean()))
        masks['opening'] = hole
        # collar shield
        sbox = shield_boxes.get(sel) or SMALL[sel]
        if (sbox[2] - sbox[0], sbox[3] - sbox[1]) == (12, 16):
            m, fabric = stamp(hole.shape, sbox, COLLAR_STAMP), None
        else:
            m, fabric = shield_in(tex['torso'], sbox)
        masks['shield'] = m
        row['shield'] = dict(recorded_box=sbox, box=bbox(m), size=[bbox(m)[2] - bbox(m)[0], bbox(m)[3] - bbox(m)[1]],
                             fill=round(float(m.sum()) / ((sbox[2] - sbox[0]) * (sbox[3] - sbox[1])), 2), fabric=fabric)
        if bbox(m) != list(sbox):
            row['flags'].append('shield box differs from the recorded box')
        # maker's marks
        a = audit[sel]['game']
        marks = []
        for arm in ('right_arm', 'left_arm'):
            v = a['jersey_mark'].get(arm)
            if not v:
                continue
            fix = OVERRIDES.get(sel, {}).get(arm)
            if fix:
                v = dict(v, box=fix['box'], colour=fix['colour'])
                row['flags'].append(f'{arm}: audit box and colour replaced by the texel reading')
            colour = hexcol(v.get('colour'))
            parts = [(torso_or_sleeve(v['where']), 'main', v['box'])]
            for name, box in (v.get('also') or {}).items():
                parts.append(('sleeve' if name.startswith('sleeve') else 'torso', name, box))
            for tex_name, name, box in parts:
                key = f'{arm}_{name}'
                if (sel, key) in CLIPS:
                    box, ccol, contrast = CLIPS[(sel, key)]
                    mm, info = mark_clip(tex[tex_name], box, ccol, contrast)
                else:
                    mm, info = mark_in(tex[tex_name], box, colour, base=(fix or {}).get('base') if name == 'main' else None)
                marks.append(dict(key=key, texture=tex_name, audit_box=box, box=bbox(mm), texels=int(mm.sum()), **info))
                masks[f'{tex_name}:{key}'] = mm
        for name, v in (('pants_mark', a.get('pants_mark')), ('pants_shield', a.get('pants_shield'))):
            if not v:
                continue
            colour = hexcol(v.get('colour')) if name == 'pants_mark' else None
            if (sel, name) in CLIPS:
                box, ccol, contrast = CLIPS[(sel, name)]
                mm, info = mark_clip(tex['pants'], box, ccol, contrast)
            elif name == 'pants_shield':
                mm, info = stamp(tex['pants'].shape[:2], PANTS_STAMP_BOX, PANTS_STAMP), dict(method='stamp')
            else:
                mm, info = mark_in(tex['pants'], v['box'], colour)
            marks.append(dict(key=name, texture='pants', audit_box=v['box'], box=bbox(mm), texels=int(mm.sum()), **info))
            masks[f'pants:{name}'] = mm
        for mk in marks:
            key = f"{mk['texture']}:{mk['key']}"
            lab, n = ndi.label(masks[key], structure=np.ones((3, 3)))
            sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
            clean = np.isin(lab, [i + 1 for i, z in enumerate(sizes) if z >= 3])
            if clean.sum() < 4:                       # a stray texel or two: nothing a relief can follow
                if mk['box'] is not None:
                    mk['skipped'] = f"{int(masks[key].sum())} texels, too small to emboss"
                clean[:] = False
            masks[key] = clean
            mk['box'], mk['texels'] = bbox(clean), int(clean.sum())
            if mk.get('skipped'):
                continue
            if mk['box'] is None:
                row['flags'].append(f"{mk['key']}: no mark found in its box")
            elif max(abs(p - q) for p, q in zip(mk['box'], mk['audit_box'])) > 1:
                row['flags'].append(f"{mk['key']}: painted box {mk['box']} vs audit {mk['audit_box']}")
        row['marks'] = marks
        report[sel] = row
        np.savez_compressed(out / 'masks' / f'{sel}.npz', **{k.replace(':', '__'): v for k, v in masks.items()})
    (out / 'marks.json').write_text(json.dumps(report, indent=1))
    flagged = {k: v['flags'] for k, v in report.items() if v['flags']}
    print(len(report), 'kits;', len(flagged), 'with flags')
    for k, v in flagged.items():
        print(k, '; '.join(v))


if __name__ == '__main__':
    main()
