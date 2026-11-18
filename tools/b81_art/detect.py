"""The detector table: for every helmet texture and every Team Select card, how much old art it shows, before and after.

Texture level (texels): painted 2004 vents present (of the 6 the Revolution art carried), the 2004 flag's outline, old-logo
ink (only where the official logo registered on both sides), old shell-colour squares.
Card level (card pixels, through the card pose's UV map): pixels that show those texels, and pixels that show art a build
pass redrew after the card was rendered (the card no longer matched the game)."""
import sys, json, csv; sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
import cardlib as C, numpy as np, final, fixtex, fixtex2, compose, assign
from scipy import ndimage
OUT = C.WORK.parent / 'out'
def vents_present(T):
    """How many of the six painted vents a helmet02 level 0 still shows (ink against the shell rebuilt across it)."""
    rgb = T[..., :3].astype(np.float64); n = 0
    for m in fixtex.vent_regions():
        filled = fixtex.fill(rgb, m)
        dev = np.abs(rgb - filled).max(axis=2)
        core = ndimage.binary_erosion(m, iterations=1)
        if (dev[core] > 22).mean() > 0.12: n += 1
    return n
def texture_row(name, T, cleaned):
    fam = name.split('_')[0]
    extra = json.load(open(C.WORK / 'extra_kits.json'))
    row = dict(texture=name)
    if fam == 'helmet02':
        row['painted_vents_before'] = vents_present(T); row['painted_vents_after'] = vents_present(cleaned)
    if name[9:] in extra:
        row.update(old_logo_texels_before=None, old_logo_texels_after=None, registered=False)
        return row
    d0 = fixtex2.old_ink(name, T); d1 = fixtex2.old_ink(name, cleaned)
    v = np.zeros((256, 256), bool)
    if fam == 'helmet02':
        for m in fixtex.vent_regions(): v |= ndimage.binary_dilation(m, iterations=1)
    row.update(old_logo_texels_before=int((d0['left'] & ~v).sum()), old_logo_texels_after=int((d1['left'] & ~v).sum()),
               registered=bool(d0['panels'] and all(d0['panels'].values())))
    return row
def project(mask, view, side):
    pid, u, v = compose.uv(view, side)
    hit = (pid >= 0) & (pid <= 2) & mask[v, u]
    return hit.reshape(256, 4, 256, 4).any(axis=(1, 3))
def card_rows(sel):
    code, S, style = sel[:2], sel[2], sel[3:]
    fin_p = C.WORK / 'final' / 'helmets' / f'helmet02_{sel}.png'
    T = C.load(fin_p)
    new = C.load(assign.new_tex_path('helmet02', sel))
    old_png = C.hindex().get(f'helmet02_{sel}')
    pack = C.load(old_png) if old_png else T
    cleaned = (C.load(OUT / 'helmets' / f'helmet02_{sel}.png')[..., :3] != T[..., :3]).any(axis=2)
    redrawn = ndimage.binary_opening(np.abs(T[..., :3].astype(int) - pack[..., :3].astype(int)).max(axis=2) > 40, structure=np.ones((2, 2), bool))
    reassigned = sel in assign.REASSIGN
    rows = []
    for fam, view in (('helm', 'helm'), ('unif', 'unif')):
        live = np.ones((256, 256), bool)
        if fam == 'helm': live[compose.BAR_TOP:] = False
        rows.append(dict(card=f"{fam}_{S.lower()}{code}_{style}_256",
                         shows_old_art_pixels=int((project(cleaned, view, S) & live).sum()),
                         shows_art_the_game_no_longer_has_pixels=int((project(redrawn, view, S) & live).sum()),
                         new_helmet_design=reassigned))
    return rows
if __name__ == '__main__':
    tex_rows, crows = [], []
    names = sorted(p.stem for p in (OUT / 'helmets').glob('helmet0?_*.png'))
    seen = {}
    for name in names:
        T = final.helmet(name); cleaned = C.load(OUT / 'helmets' / f'{name}.png')
        key = (T.tobytes(), name.split('_')[0], name[9:11])
        if key not in seen: seen[key] = texture_row(name, T, cleaned)
        tex_rows.append(dict(seen[key], texture=name))
    for sel in sorted({n.split('_')[1] for n in names}):
        crows += card_rows(sel)
    rec = json.load(open(OUT / 'card_receipt.json')) if (OUT / 'card_receipt.json').exists() else {}
    for r in crows:
        c = rec.get(r['card'], {})
        r['card_pixels_changed'] = c.get('changed_pixels'); r['visible_change_vs_built'] = c.get('visible_change_vs_built')
    json.dump(dict(textures=tex_rows, cards=crows), open(OUT / 'detector.json', 'w'), indent=1)
    with open(OUT / 'detector_cards.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(crows[0].keys())); w.writeheader(); w.writerows(crows)
    with open(OUT / 'detector_textures.csv', 'w', newline='') as f:
        keys = ['texture', 'painted_vents_before', 'painted_vents_after', 'old_logo_texels_before', 'old_logo_texels_after', 'registered']
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader(); w.writerows([{k: r.get(k) for k in keys} for r in tex_rows])
    h2 = [r for r in tex_rows if r['texture'].startswith('helmet02')]
    print('helmet02 textures', len(h2), 'with painted vents before', sum(1 for r in h2 if r['painted_vents_before']), 'after', sum(1 for r in h2 if r['painted_vents_after']))
    print('vents before', sum(r['painted_vents_before'] for r in h2), 'after', sum(r['painted_vents_after'] for r in h2))
    print('old logo texels before', sum(r['old_logo_texels_before'] or 0 for r in tex_rows), 'after', sum(r['old_logo_texels_after'] or 0 for r in tex_rows))
    print('after residue:', [(r['texture'], r['painted_vents_after']) for r in h2 if r['painted_vents_after']][:20])
    print('old after:', [(r['texture'], r['old_logo_texels_after']) for r in tex_rows if r['old_logo_texels_after']][:20])
