"""All primary marks, all roster labels and both actual native projections."""
import json
import numpy as np
from PIL import Image, ImageDraw
import fit as F
import player_scale as P
from mod_editor.core import nfl2k5_scorebug_teams as teams
from mod_editor.core import nfl2k5_scorebug_runtime as owner
from tools.scorebug_sprite.jev import descriptors


def projected_retention(team, fit, receipt, side):
    """Map complete source ink into the executed quad, before texture clipping.

    Every source pixel contributes its original alpha, and all four footprint
    corners must survive. The native projection is affine, so player scaling
    cancels in the fraction. Report actual player positions and alpha counts.
    """
    geometry = receipt['logo_geometry']
    def bounds(name):
        a = np.asarray(geometry[name])[:, :2]
        return np.r_[a.min(0), a.max(0)]
    logo, wing = bounds(side+'_logo'), bounds(side+'_wing')
    image, _ = F.artwork(team)
    full, (x, y) = F.transform(team, fit)
    alpha = np.asarray(image.getchannel('A'))
    yy, xx = np.nonzero(alpha)
    good = np.ones(len(xx), dtype=bool)
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        u = (x+(xx+dx)*full.width/image.width)/64
        v = (y+(yy+dy)*full.height/image.height)/64
        px = logo[0]+u*(logo[2]-logo[0])
        py = logo[1]+v*(logo[3]-logo[1])
        good &= (u >= 0) & (u <= 1) & (v >= 0) & (v <= 1)
        good &= (px >= wing[0]) & (px <= wing[2]) & (py >= wing[1]) & (py <= wing[3])
        # Rounded outer edge of each wing in the executed coordinate system.
        edge = px-wing[0] if side == 'away' else wing[2]-px
        corner_x = edge*340/(wing[2]-wing[0])
        corner_y = np.minimum(py-wing[1], wing[3]-py)*110/(wing[3]-wing[1])
        good &= np.maximum(8-corner_x, 0)**2+np.maximum(8-corner_y, 0)**2 <= 64
    weights = alpha[yy, xx].astype(np.int64)
    scale = np.array([receipt['display'][0]/640, receipt['display'][1]/448]*2)
    player_box = (logo-np.array([0, 16, 0, 16]))*scale
    return dict(side=side, total_alpha=int(weights.sum()), retained_alpha=int(weights[good].sum()),
        ink_fraction=float(weights[good].sum()/weights.sum()), binary_fraction=float(good.mean()),
        native_logo_box=logo.tolist(), native_wing_box=wing.tolist(), player_logo_box=player_box.tolist())


def main():
    preview = P.sprite.NativePreview()
    spec = preview.compiled.spec
    before = json.loads((F.baseline()/'layout.json').read_text())
    label_rows, ink_rows, receipts = [], [], []
    for row in spec['static']+spec['fields']+spec['events']:
        x, y, r, b = row['box']
        assert 437 <= x < r <= 1478 and 942 <= y < b <= 1052, row['name']
    for wide in (False, True):
        aspect = '169' if wide else '43'
        sheet = Image.new('RGB', (1320, 26*110+48), '#303030')
        draw = ImageDraw.Draw(sheet)
        draw.text((5, 5), f'b72-s11 | {aspect} | 52 slots | OFFLINE native 448-line HUD | 617-pixel bar', fill='white')
        draw.text((5, 23), 'Primary marks: source ink retention 100%; zero permitted crop, including circles and shields.', fill='#ffdb88')
        for i, (name, team) in enumerate(teams.load().items()):
            image, receipt = P.draw(preview, dict(away=name, home=name, down=1, distance=10, play_clock=40), wide)
            receipts.append(dict(team=name, aspect=aspect, **receipt))
            arr = np.asarray(P.aligned(image), dtype=float)
            x, y, r, b = P.box((829, 950, 1089, 980))
            crop = arr[y:b, x:r, :3]
            ink = crop.min(2) > 185
            luma = descriptors.rgb_luma(crop)
            core = float(np.percentile(luma[ink], 75)) if ink.any() else 0.
            contrast = teams.contrast_white(team['plate'])
            passed = core >= 200 and contrast >= 4.5 and int(ink.sum()) >= 100
            label_rows.append(dict(team=name, aspect=aspect, core_luma=round(core, 2),
                white_core_pixels=int(ink.sum()), contrast=round(contrast, 4), passed=passed, runtime_witnessed=False))
            if name in spec['logo_fit']['by_team']:
                fit = spec['logo_fit']['by_team'][name]
                check = F.retained(name, fit)
                projected = [projected_retention(name, fit, receipt, side) for side in ('away', 'home')]
                assert check['passed'] and all(p['ink_fraction'] == p['binary_fraction'] == 1 for p in projected), name
                ink_rows.append(dict(aspect=aspect, **check, projected=projected,
                    before=F.retained(name, before['logo_fit']['by_team'][name])))
                label = name+' | full ink 100%'
            else:
                label = name+' | existing neutral fallback, no primary artwork'
            x, y = i%2*660+5, i//2*110+48
            draw.text((x, y), label, fill='white')
            sheet.paste(P.bar(image), (x, y+18))
        sheet.save(F.OUT/f'all_teams_{aspect}.png')
        print('Completed all 52 slots:', aspect, flush=True)
    F.write('readability.json', label_rows)
    F.write('ink_retention.json', ink_rows)
    F.write('all_team_native_receipts.json', receipts)
    budget = dict(rx_used=len(owner.code_for(0x6000000, 0x6001000)[0].rstrip(b'\xcc')),
        rx_reserved=owner.CODE_SIZE, rw_reserved=owner.DATA_SIZE,
        aspects={str(k): v['volume'] for k, v in preview.modes.items()}, ceiling=P.sprite.MAX_APPEND)
    F.write('budgets.json', budget)
    old_budget = json.loads((F.ROOT/'reports/b72_s10/budgets.json').read_text())
    assert (budget['rx_used'], budget['rx_reserved'], budget['rw_reserved']) == (4086, 4096, 128)
    for aspect, volume in budget['aspects'].items():
        assert volume['appended_bytes'] == old_budget['aspects'][aspect]['appended_bytes'] == 325216
        assert [c['size'] for c in volume['components']] == [c['size'] for c in old_budget['aspects'][aspect]['components']]
    assert len(ink_rows) == 64 and len(label_rows) == 104
    assert all(r['passed'] for r in label_rows)
    print('PASS: 64 primary-team/aspect ink audits, both ends; 104 labels; unchanged appendix and RX/RW.', flush=True)


if __name__ == '__main__':
    main()
