"""How legible each team's mark is against that team's own wing, by three measures.

1. ``texel_share``: the s12 survey (reports/b76_s12/mark_contrast.py), unchanged: the share of opaque mark texels
   (alpha above 128) whose WCAG contrast against the team's wing tint is at least 3:1.
2. ``edge_share``: the same test on the mark's silhouette only (opaque texels with a transparent 4-neighbour).
   A mark reads as a shape when its outline stands off the wing, even where its fill matches the wing.
3. ``rendered``: the offline native render of the team against itself (the all-teams sheet state) three times:
   with the mark, with an empty mark cell, and with the mark's own silhouette in flat white. The mark's footprint
   is every 1080p pixel the white silhouette changes, so parts of a mark that vanish into the wing still count.
   Each footprint pixel is compared with the empty render at the same pixel (the wing there), so the wing's own
   coverage, the P8 atlas and the display resampling are all included. ``rendered_share`` is the share of
   footprint pixels at 3:1 or better; ``standoff`` (the measure the threshold uses) also counts a pixel whose
   colour differs from the wing by OKLab distance 0.20 or more, a hue change such as the Giants' red keyline on
   a blue wing that luminance contrast alone misses. Each is the lower of the two sides.

The threshold is the lowest ``standoff`` among the marks ESPN draws unchanged on its 2026 bar (DEN, KC, LV and
HOU in the 2026 broadcasts measured here). A mark below it is recoloured only when a cited on-dark colourway
differs from the primary (reports/b76_s14/author.py MARKS).

No in-game behaviour is measured or claimed; the render is the offline model whose calibration gate reports FAIL.

Usage: python3 reports/b76_s14/mark_legibility.py --tag before [--no-render]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
LOGOS = ROOT / 'data/nfl2k5_scorebug_mnf/logos'
THRESHOLD = 3.0
DELTA_OKLAB = 0.20
# Marks ESPN draws unchanged on the 2026 bar in the broadcasts this job measured.
ESPN_UNCHANGED = ('DEN', 'KC', 'LV', 'HOU')
# Marks ESPN replaced on the 2026 bar (their primaries measured with --logos-rev 3dd4087d5).
ESPN_REPLACED = ('NYG', 'LAR')
# The logo quads at 1080p (layout.json away_logo and home_logo).
QUADS = dict(away=(437, 942, 667, 1052), home=(1248, 942, 1478, 1052))


def linear(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb):
    return linear(rgb) @ np.array([0.2126, 0.7152, 0.0722])


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    return (np.maximum(la, lb) + 0.05) / (np.minimum(la, lb) + 0.05)


def hexrgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def oklab_array(rgb):
    lin = linear(rgb)
    m1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566],
                   [0.0883024619, 0.2817188376, 0.6299787005]])
    m2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099],
                   [0.0259040371, 0.7827717662, -0.8086757660]])
    return np.cbrt(lin @ m1.T) @ m2.T


def edge_mask(opaque):
    padded = np.pad(opaque, 1)
    inner = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    return opaque & ~inner


def erode(mask, steps):
    for _ in range(steps):
        padded = np.pad(mask, 1)
        mask = mask & padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    return mask


def texel_measures(mark, wing):
    a = np.asarray(mark.convert('RGBA')).astype(np.float64)
    opaque = a[..., 3] > 128
    ratio = contrast(a[..., :3], np.array(wing, dtype=np.float64)[None, None])
    edge = edge_mask(opaque)
    return dict(texel_share=round(float((ratio[opaque] >= THRESHOLD).mean()), 3),
                edge_share=round(float((ratio[edge] >= THRESHOLD).mean()), 3),
                median_contrast=round(float(np.median(ratio[opaque])), 2),
                mark_median_rgb=[int(v) for v in np.median(a[..., :3][opaque], axis=0)])


def rendered_measures(with_mark, without_mark, silhouette):
    shares = {}
    for side, (x0, y0, x1, y1) in QUADS.items():
        on = with_mark[y0:y1, x0:x1]
        off = without_mark[y0:y1, x0:x1]
        footprint = np.abs(silhouette[y0:y1, x0:x1] - off).max(-1) > 24
        if not footprint.any():
            shares[side] = dict(rendered_share=0.0, mark_pixels=0)
            continue
        ratio = contrast(on, off)
        distance = np.linalg.norm(oklab_array(on) - oklab_array(off), axis=-1)
        stands = (ratio >= THRESHOLD) | (distance >= DELTA_OKLAB)
        shares[side] = dict(rendered_share=round(float((ratio[footprint] >= THRESHOLD).mean()), 3),
                            standoff=round(float(stands[footprint].mean()), 3),
                            median_contrast=round(float(np.median(ratio[footprint])), 2),
                            median_oklab_distance=round(float(np.median(distance[footprint])), 3),
                            mark_pixels=int(footprint.sum()))
    return shares


def render_all(teams_to_render):
    """Offline native renders of every team against itself, with and without the mark cell."""
    from unittest.mock import patch
    from mod_editor.core import nfl2k5_scorebug_sprite as sprite, nfl2k5_scorebug_exact as exact
    from tools.scorebug_sprite import gpu, xemu_model
    import nfl2k5_scorebug_projection as projection

    def draw(preview, team):
        state = sprite.normalize_state(dict(away=team, home=team, down=1, distance=10, possession='home'))
        geometry, capture = preview.capture(state, True)
        try:
            mode = preview.modes[True]
            with tempfile.TemporaryDirectory(prefix='s14-legible-') as tmp:
                raster = Path(tmp) / 'hud.png'
                projection.render_native(capture['live_decoded'], mode['atlas'], preview.fonts, geometry, raster,
                                         texture_spans=capture['texture_spans'],
                                         background=Image.new('RGB', (640, 480), (58, 108, 52)),
                                         gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(capture)))
                hud = Image.open(raster).convert('RGB').crop((0, 16, 640, 464))
                return np.asarray(hud.resize((1920, 1080), Image.Resampling.LANCZOS), dtype=np.float64)
        finally:
            capture['machine'].close()

    real = sprite.NativePreview()
    original = exact.mnf_panel

    def empty(team, side, fit=None):
        image = original(team, side, fit=fit)
        return Image.new('RGBA', image.size, (0, 0, 0, 0))

    def white(team, side, fit=None):
        image = np.asarray(original(team, side, fit=fit)).copy()
        image[..., :3] = 255
        return Image.fromarray(image, 'RGBA')
    with patch.object(exact, 'mnf_panel', empty):
        blank = sprite.NativePreview()
    with patch.object(exact, 'mnf_panel', white):
        flat = sprite.NativePreview()
    out = {}
    for team in teams_to_render:
        out[team] = rendered_measures(draw(real, team), draw(blank, team), draw(flat, team))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tag', default='now')
    p.add_argument('--no-render', action='store_true')
    p.add_argument('--teams', help='Comma list of teams to survey (default: all 32)')
    p.add_argument('--logos-rev', help='Survey the marks as they were at this git revision (restored afterwards)')
    a = p.parse_args(argv)
    if a.logos_rev:
        return with_logos(a.logos_rev, a.teams, lambda: survey(a))
    return survey(a)


def with_logos(rev, teams, run):
    """Swap the listed teams' marks for a revision's bytes for one survey; the current bytes always come back."""
    import subprocess
    from mod_editor.core.nfl2k5_scorebug_assets import TEAM_FILES
    stems = [TEAM_FILES[t] for t in (teams.split(',') if teams else TEAM_FILES)]
    saved = {stem: (LOGOS / (stem + '.png')).read_bytes() for stem in stems}
    try:
        for stem in stems:
            (LOGOS / (stem + '.png')).write_bytes(subprocess.check_output(
                ['git', 'show', rev + ':data/nfl2k5_scorebug_mnf/logos/' + stem + '.png'], cwd=ROOT))
        return run()
    finally:
        for stem, data in saved.items():
            (LOGOS / (stem + '.png')).write_bytes(data)


def survey(a):
    from mod_editor.core.nfl2k5_scorebug_assets import TEAM_FILES
    accents = json.loads((ROOT / 'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())['teams']
    rows = []
    wanted = set(a.teams.split(',')) if a.teams else set(TEAM_FILES)
    for team, stem in sorted(TEAM_FILES.items()):
        if team not in wanted:
            continue
        mark = Image.open(LOGOS / (stem + '.png'))
        wing = hexrgb(accents[team]['wing'])
        rows.append(dict(team=team, wing=accents[team]['wing'], **texel_measures(mark, wing)))
    if not a.no_render:
        rendered = render_all([r['team'] for r in rows])
        for r in rows:
            r['rendered'] = rendered[r['team']]
            r['rendered_share'] = min(v['rendered_share'] for v in rendered[r['team']].values())
            r['standoff'] = min(v['standoff'] for v in rendered[r['team']].values())
    rows.sort(key=lambda r: (r.get('standoff', r['texel_share']), r['texel_share']))
    by_team = {r['team']: r for r in rows}
    unchanged = {t: by_team[t]['standoff'] for t in ESPN_UNCHANGED if t in by_team and 'standoff' in by_team[t]}
    threshold = min(unchanged.values()) if len(unchanged) == len(ESPN_UNCHANGED) else None
    result = dict(schema='b76-s14-mark-legibility/v1', tag=a.tag, logos_rev=a.logos_rev,
                  contrast_ratio=THRESHOLD, oklab_distance=DELTA_OKLAB,
                  espn_unchanged=unchanged, threshold=threshold,
                  below_threshold=[r['team'] for r in rows if threshold is not None and r['standoff'] < threshold],
                  method='\n\n'.join(__doc__.split('\n\n')[1:3]).strip(), rows=rows,
                  note='Offline model only; the calibration gate reports FAIL. No in-game result is claimed.')
    (OUT / ('mark_legibility_%s.json' % a.tag)).write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8',
                                                           newline='\n')
    for r in rows:
        print('%-4s wing %s texel %.3f edge %.3f rendered %s standoff %s' % (
            r['team'], r['wing'], r['texel_share'], r['edge_share'], r.get('rendered_share'), r.get('standoff')))
    print('threshold', threshold, 'below', result['below_threshold'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
