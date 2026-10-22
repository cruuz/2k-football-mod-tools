"""Zoom the scorebar team marks so they fill the wing and bleed slightly past its top and bottom, as ESPN draws them.

Noah, stream 10/21 (c2-15): "the logos ... should be zoomed in a bit more and like slightly cut off". On the 2026 ESPN
bar every mark reaches the wing's top and bottom rails and the larger ones run past them (Raiders at Texans: the bull
is cut at both rails, the shield touches both; Bills at Chiefs: the buffalo is cut at the rails). The Studio draws
each mark into the shared 64x64 logo cell, which the home and away quads stretch over the wing (230 x 110 layout px),
so anything past the cell is cut at the wing's rails.

Each team's zoom rises to TARGET (the mark's natural height is TARGET times the wing height, so about 7% of it is cut
at each rail) unless a limit stops it first:

* the mark keeps a WIDTH_MARGIN of empty cell on each side, so it is never cut by the cell's inner edge inside the
  bar (the cell is shared by both sides and the home quad is not mirrored, so a cut would show next to a score);
* the home mark stays inside the rounded upper-right corner (hu1 N27, alpha >= 64 within the curve).

A zoom never falls, and a mark that cannot pass 1.0 within those limits keeps its fit (the wide wordmarks and heads
already fill the cell's width).
Writes ``logo_fit`` in layout.json and team_accents.json (they carry the same fit) and records the result.

python3 tools/scorebug_sprite/logo_zoom.py [--folder FOLDER] [--check]
"""
from pathlib import Path
import argparse
import json
import math
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools/scorebug_sprite')]
DEFAULT_FOLDER = ROOT/'data/nfl2k5_scorebug_sprite'
TARGET = 1.15
WIDTH_MARGIN = 3          # cell texels (about 11 layout px) kept clear at each side of the cell
CLEAR_ALPHA = 64
STEP = 0.0025
RECORD = 'b778_sb2_logo_zoom'


def _round(value):
    return round(math.floor(value/STEP+1e-6)*STEP, 4)


def mark_width(team, fit):
    """Drawn width of the mark in cell texels (the cell is 64 wide)."""
    from PIL import Image
    from mod_editor.core import nfl2k5_scorebug_exact as exact
    a, b, c, d = exact.MNF_SOURCE['home_logo']
    key = {'WAS': 'wsh'}.get(team, team.lower())
    logo = Image.open(ROOT/'data/nfl2k5_scorebug_mnf/logos'/f'{key}.png').convert('RGBA')
    logo = logo.crop(logo.getchannel('A').getbbox())
    scale = min((c-a)/logo.width, (d-b)*fit.get('height', 1.0)/logo.height)
    src_w = min(c-a, logo.width*scale*fit.get('fill_x', 1.0))
    return max(1, round(src_w*64/(c-a)*fit.get('zoom', 1.0)))


def corner_overreach(spec, team, fit):
    """Largest distance (layout px) an opaque home-mark texel reaches past the rounded corner; <= 0 is clear."""
    import numpy as np
    import corner_shape as cs
    from mod_editor.core import nfl2k5_scorebug_exact as exact
    x0, y0, x1, y1 = next(r['box'] for r in spec['static'] if r['name'] == 'home_logo')
    box = cs.bar_box(spec)
    r = cs.RADIUS
    cx, cy = box[2]-r, box[1]+r
    alpha = np.asarray(exact.mnf_panel(team, 'home', fit=fit))[..., 3]
    worst = -1e9
    for v, u in zip(*np.nonzero(alpha >= CLEAR_ALPHA)):
        x, y = x0+(u+.5)*(x1-x0)/64, y0+(v+.5)*(y1-y0)/64
        if x > cx and y < cy:
            worst = max(worst, math.hypot(x-cx, y-cy)-r)
    return worst


def side_margins(team, fit):
    """Empty cell texels left and right of the mark, placed the way exact.mnf_panel pastes it."""
    w = mark_width(team, fit)
    left = (64-w)//2+round(fit.get('shift_x', 0.0)*64)
    return left, 64-w-left


def fits(spec, team, fit):
    return min(side_margins(team, fit)) >= WIDTH_MARGIN and corner_overreach(spec, team, fit) <= 0.0


def zoom_for(spec, team, fit):
    """The largest zoom up to TARGET that fits, never below the current one. Only a zoom past 1.0 is worth taking:
    below it the mark still sits inside the wing, and exact.mnf_panel keeps its clear border only past 1.0."""
    current = fit.get('zoom', 1.0)
    best = current
    z = _round(TARGET)
    while z > max(current, 1.0):
        trial = dict(fit, zoom=round(z, 4))
        if fits(spec, team, trial):
            best = round(z, 4)
            break
        z -= STEP
    return best


def plan(spec):
    from mod_editor.core.nfl2k5_scorebug_resources import TEAM_LOGOS, logo_fit_for
    rows = {}
    for team in sorted(TEAM_LOGOS):
        fit = logo_fit_for(team, spec['logo_fit'])
        rows[team] = dict(before=fit.get('zoom', 1.0), after=zoom_for(spec, team, fit))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    parser.add_argument('--check', action='store_true', help='report the plan without writing')
    args = parser.parse_args()
    layout = args.folder/'layout.json'
    spec = json.loads(layout.read_text(encoding='utf-8'))
    if spec['provenance'].get(RECORD):
        print('already zoomed:', json.dumps(spec['provenance'][RECORD]['zoom']))
        return 0
    rows = plan(spec)
    for team, row in rows.items():
        print(f"{team:4} {row['before']:.4f} -> {row['after']:.4f}")
    if args.check:
        return 0
    accents_path = args.folder/'team_accents.json'
    accents = json.loads(accents_path.read_text(encoding='utf-8'))
    for team, row in rows.items():
        spec['logo_fit']['by_team'][team]['zoom'] = row['after']
        accents['teams'][team]['logo_fit']['zoom'] = row['after']
    spec['provenance'][RECORD] = dict(
        job='b778 sb2 2026-10-22', request='Noah 10/21 stream c2-15: logos zoomed in a bit more and slightly cut off',
        target=TARGET, width_margin_texels=WIDTH_MARGIN, corner_alpha=CLEAR_ALPHA,
        reference='2026 ESPN NFL Raiders at Texans and Bills at Chiefs bars (measurement only, no broadcast pixels)',
        zoom={team: [row['before'], row['after']] for team, row in rows.items()})
    accents_path.write_text(json.dumps(accents, indent=2)+'\n', encoding='utf-8', newline='\n')
    layout.write_text(json.dumps(spec, indent=1)+'\n', encoding='utf-8', newline='\n')
    print('zoomed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
