"""Derive zero-crop fits from complete artwork, before the native cell clips it.

Development-only authoring and independent measurement. Runtime remains the
existing 64-square texture and per-team layout contract.
"""
from pathlib import Path
from functools import lru_cache
import copy
import hashlib
import json
import subprocess
import sys

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_assets as assets

BASE = 'c3b3b53a2'
DATA = ROOT/'data/nfl2k5_scorebug_sprite'
# Even enclosing ovals with lettering take zero crop tolerance. These classes
# are explanatory, never permission to discard an identifying interior stroke.
WORDMARKS = {'CIN', 'GB', 'KC', 'LAR', 'LV', 'NYG', 'NYJ', 'SF', 'WAS'}
SYMMETRIC = {'DAL', 'IND', 'NO', 'PIT', 'TEN'}


def write(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8', newline='\n')


def baseline():
    dest = ROOT/'.scratch/s11_before'
    dest.mkdir(parents=True, exist_ok=True)
    for name in ('layout.json', 'template.png', 'team_accents.json', 'team_colors_official_2026.json'):
        value = subprocess.check_output(['git', 'show', BASE+':data/nfl2k5_scorebug_sprite/'+name], cwd=ROOT)
        path = dest/name
        if path.exists():
            assert path.read_bytes() == value, name
        else:
            path.write_bytes(value)
    return dest


@lru_cache(None)
def artwork(team):
    key = 'wsh' if team == 'WAS' else team.lower()
    path = ROOT/'data/nfl2k5_scorebug_mnf/logos'/(key+'.png')
    image = Image.open(path).convert('RGBA')
    bounds = image.getchannel('A').getbbox()
    return image.crop(bounds), dict(path=path.relative_to(ROOT).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(), ink_bbox=list(bounds),
        artwork_size=list(image.size), ink_aspect=(bounds[2]-bounds[0])/(bounds[3]-bounds[1]))


def dimensions(team, fit):
    """Legacy transform dimensions, before resampling or the clipping paste."""
    image, _ = artwork(team)
    scale = min(200/image.width, 107*fit.get('height', 1)/image.height)
    width = max(1, round(min(200, image.width*scale*fit.get('fill_x', 1))*64/200*fit.get('zoom', 1)))
    height = max(1, round(image.height*scale*64/107*fit.get('zoom', 1)))
    x = (64-width)//2 + round(fit.get('shift_x', 0)*64)
    y = (64-height)//2 + round(fit.get('shift_y', 0)*64)
    return (width, height), (x, y)


def transform(team, fit):
    """Reconstruct the *unclipped* legacy transform, independently of mnf_panel."""
    image, _ = artwork(team)
    size, origin = dimensions(team, fit)
    return assets.resample_logo(image.copy(), size), origin


def retained(team, fit, inset=0):
    """Count alpha-weighted and binary ink before cropping, including all colours.

    The same logo cell serves both ends. Intersect both rounded outer wing
    corners in physical source units, then bound to its 64x64 texture window.
    Source alpha includes even faint tails; filtered alpha is checked separately.
    The author uses a one-texel sampling guard, the audit uses the actual window.
    """
    full, (x, y) = transform(team, fit)
    source, provenance = artwork(team)

    def count(alpha, width, height):
        yy, xx = np.nonzero(alpha)
        # Include the entire source pixel footprint, not only its centre.
        good = np.ones(len(xx), dtype=bool)
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            u = x+(xx+dx)*full.width/width
            v = y+(yy+dy)*full.height/height
            good &= (u >= inset) & (u <= 64-inset) & (v >= inset) & (v <= 64-inset)
            # Both 230x110 wells meet the outer wing edge, radius 8 source px.
            corner_x = np.minimum(u, 64-u)*230/64
            corner_y = np.minimum(v, 64-v)*110/64
            good &= np.maximum(8-corner_x, 0)**2 + np.maximum(8-corner_y, 0)**2 <= 8**2
        mass = alpha[yy, xx].astype(np.int64)
        total, surviving = int(mass.sum()), int(mass[good].sum())
        return dict(total_ink_pixels=len(xx), retained_ink_pixels=int(good.sum()),
            total_alpha=total, retained_alpha=surviving,
            ink_fraction=surviving/total, binary_fraction=float(good.mean()))

    source_counts = count(np.asarray(source.getchannel('A')), source.width, source.height)
    texture_counts = count(np.asarray(full.getchannel('A')), full.width, full.height)
    actual = exact.mnf_panel(team, 'home', fit=fit)
    expected = Image.new('RGBA', (64, 64))
    expected.paste(full, (x, y))
    assert actual.getchannel('A').tobytes() == expected.getchannel('A').tobytes()
    return dict(team=team, category='wordmark_or_letters' if team in WORDMARKS else
        'symmetric_enclosure_or_symbol' if team in SYMMETRIC else 'asymmetric',
        tolerance=0, fit=fit, provenance=provenance, transformed_size=list(full.size),
        texture_origin=[x, y], source=source_counts, texture=texture_counts,
        actual_texture_alpha=int(np.asarray(actual.getchannel('A'), dtype=np.int64).sum()),
        passed=source_counts['ink_fraction'] == texture_counts['ink_fraction'] == 1)


def safe_fit(team, old):
    # Keep the existing team aspect and height. First retain a safe old fit,
    # then shrink in native-size steps. Choose a centred safe placement close
    # to the old offset. Each candidate is judged on this team's complete ink.
    if retained(team, old, inset=1)['passed']:
        return old
    seen = set()
    for milli in range(round(old.get('zoom', 1)*1000), 499, -1):
        fit = dict(old, zoom=milli/1000, shift_x=0., shift_y=0.)
        signature = dimensions(team, fit)
        if signature in seen:
            continue
        seen.add(signature)
        if retained(team, fit, inset=1)['passed']:
            return fit
    raise ValueError('No safe fit for '+team)


def main():
    src = baseline()
    spec = json.loads((src/'layout.json').read_text())
    before = copy.deepcopy(spec)
    selected_path = OUT/'selected_fits.json'
    selected = json.loads(selected_path.read_text()) if selected_path.exists() else {}
    rows = []
    for team, old in before['logo_fit']['by_team'].items():
        fit = selected.get(team) or safe_fit(team, old)
        assert retained(team, fit, inset=1)['passed'], team
        spec['logo_fit']['by_team'][team] = fit
        rows.append(dict(team=team, before=retained(team, old), after=retained(team, fit)))
        print(team, old['zoom'], '->', fit['zoom'], rows[-1]['before']['source']['ink_fraction'], flush=True)
    # A fallback cannot silently reintroduce the old global enlargement.
    spec['logo_fit']['default'] = dict(fill_x=.92, height=1., zoom=.96)
    accents = json.loads((src/'team_accents.json').read_text())
    for team, row in accents['teams'].items():
        if team in spec['logo_fit']['by_team']:
            row['logo_fit'] = spec['logo_fit']['by_team'][team]
    for name, value in (('layout.json', spec), ('team_accents.json', accents)):
        (DATA/name).write_text(json.dumps(value, indent=1 if name == 'layout.json' else 2)+'\n', encoding='utf-8', newline='\n')
    write('fit_derivation.json', rows)


if __name__ == '__main__':
    main()
