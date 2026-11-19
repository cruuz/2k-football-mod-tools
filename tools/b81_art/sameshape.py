"""The 'same shape, offset' test for all 32 clubs (style 0, both shells): retail ink still present beside or around today's
logo. Per texture: official-logo registration, old ink the detector flags with its review gate off (before and after the
cleanup), and for every club retail ink that is neither a still-whole retail piece nor inside the official footprint."""
import sys, json, copy; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, texdet, texdet2, fixtex, fixtex2, final
from scipy import ndimage
OV = copy.deepcopy(fixtex2.OVERRIDES)
allk = sorted({f"{c}_0" for c in C.TEAMS})
OV['old_ink_reviewed'] = {'helmet02': allk, 'helmet00': allk}
def loose(name, T):
    """Retail ink at any strength that is not part of a still-whole retail piece (registration not needed)."""
    fam = name.split('_')[0]; rgb = T[..., :3].astype(float)
    hw = texdet.hardware(fam)[0].copy()
    if fam == 'helmet02':
        for m in fixtex.vent_regions(): hw &= ~ndimage.binary_dilation(m, iterations=2)
    z = texdet.zone_mask(fam) & ~hw; z[:, 142:] = False
    shell = np.median(rgb[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
    exp = np.zeros((256, 256), bool); intact = np.zeros((256, 256), bool)
    for r in texdet2.refs_for(name):
        ret = C.hretail(r)[..., :3].astype(float)
        shell_ret = np.median(ret[texdet.zone_mask(fam) & ~texdet.hardware(fam)[0]], axis=0)
        a, ok = texdet2.explained(rgb, ret, shell, shell_ret); ok &= z
        rdecal = z & (np.linalg.norm(ret - shell_ret, axis=2) > 40)
        lab, n = ndimage.label(rdecal, structure=np.ones((3, 3), bool))
        if n:
            idx = np.arange(1, n + 1); size = ndimage.sum(rdecal, lab, idx); kept = ndimage.sum(ok & (a >= 0.8), lab, idx)
            intact |= np.isin(lab, [int(i) for i, s, k in zip(idx, size, kept) if s >= 24 and k / s >= 0.8])
        exp |= ok
    return exp & ~ndimage.binary_dilation(intact, iterations=1)
def main():
    rows = []
    for code in sorted(C.TEAMS):
        for fam in ('helmet02', 'helmet00'):
            name = f'{fam}_{code}H0'
            T = final.helmet(name); R = C.load(C.WORK.parent / 'out' / 'helmets' / f'{name}.png')
            saved = fixtex2.OVERRIDES; fixtex2.OVERRIDES = OV
            try:
                d0 = fixtex2.old_ink(name, T); d1 = fixtex2.old_ink(name, R)
            finally:
                fixtex2.OVERRIDES = saved
            v = np.zeros((256, 256), bool)
            if fam == 'helmet02':
                for m in fixtex.vent_regions(): v |= ndimage.binary_dilation(m, iterations=2)
            reg_ok = bool(d0['panels']) and all(d0['panels'].values())
            l0 = loose(name, T) & ~v & ~ndimage.binary_dilation(d0['foot'], iterations=1); l1 = loose(name, R) & ~v & ~ndimage.binary_dilation(d1['foot'], iterations=1)
            ov = fixtex2.OVERRIDES.get(f"{code}_0:{fam}", {})
        rebuilt = bool(ov.get('mirror_lower') or ov.get('lower_from_modern'))
        if rebuilt:
            # the left side is now made from the right side (or the modern shell), so the official-logo registration of
            # the released texture no longer fits it: the right side is measured (with the released registration) and
            # counted for both
            up = loose(name, R) & ~v & ~ndimage.binary_dilation(d0['foot'], iterations=1); up[128:] = False
            l1 = up | up[::-1]
            d1 = dict(d1, left=np.zeros((256, 256), bool), boxes=np.zeros((256, 256), bool))
        rows.append(dict(club=C.TEAMS[code], texture=name, registered=reg_ok,
                             flagged_before=int((d0['left'] & ~v).sum()), flagged_after=int((d1['left'] & ~d1['boxes'] & ~v).sum()),
                             loose_retail_ink_before=int(l0.sum()), loose_retail_ink_after=int(l1.sum()),
                         note='left side rebuilt from the right side; old-ink flags not applicable after' if rebuilt else ''))
    json.dump(rows, open(C.WORK.parent / 'out' / 'same_shape.json', 'w'), indent=1)
    print('club tex reg flagged(before>after) loose(before>after)')
    for r in rows:
        if r['flagged_before'] > 12 or r['loose_retail_ink_after'] > 40 or r['flagged_after'] > 12:
            print(r['club'], r['texture'][:8], 'R' if r['registered'] else '-', f"{r['flagged_before']}>{r['flagged_after']}", f"{r['loose_retail_ink_before']}>{r['loose_retail_ink_after']}")

if __name__ == '__main__':
    main()
