"""The s10/s11 player-size residual, measured against the Giants at Rams MNF bar.

Every definition here is copied unchanged from reports/b72_s10/player_scale.py
and reports/b72_s11: the 617-pixel player bar, the same six feature regions, the
same feature masks and the same 2-by-2 player-pixel core filter. Only the
reference broadcast and the two measured states are new, so a b76-s12 number is
directly comparable with the s10 and s11 rows.

Alignment: these frames are already 1:1 with the layout's own frame. The pill
(839..1081 measured against the layout's 839..1082), the away timeout rail
(717..796 against 717..797) and the quarter cell's left edge (846 against 846)
agree to a pixel with no rescaling, so the reference is scaled by the same
617/1041 factor as the render and pasted at zero offset. That is a tighter
calibration than fitting the outer bar edge, whose soft border is threshold
dependent.

Run ``baseline`` before authoring and ``final`` after. No emulator is launched
and no in-game behaviour is measured or claimed.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys
import tempfile

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from tools.scorebug_sprite import gpu, xemu_model
import nfl2k5_scorebug_projection as projection

# 617 visible columns in the first supplied disc capture, x=260..877: the scale
# reports/b72_s10 established. Never renormalize this against a glyph.
SCALE = 617 / 1041
PLAYER = {False: (round(1440 * SCALE), round(1080 * SCALE)),
          True: (round(1920 * SCALE), round(1080 * SCALE))}
FRAMES = Path(os.environ.get(
    'B76_S12_FRAMES',
    '/tmp/claude-1000/-home-noah-Desktop-2K5-8-Editors/db909074-2fcd-484b-bae4-c8c664621524/scratchpad/b76/mnf/frames'))
# Two measured states from the read-only broadcast. Possession is read from the
# plate tint, which separates cleanly into the two team blues across the game.
CASES = {
    'NYG_LAR_q1': (FRAMES / 'frame_000120.png',
        dict(away='NYG', home='LAR', away_score=0, home_score=0, clock=217,
             quarter=1, play_clock=40, down=1, distance=10, possession='home',
             away_timeouts=3, home_timeouts=3, broadcast='monday_night')),
    'NYG_LAR_q4': (FRAMES / 'frame_000620.png',
        dict(away='NYG', home='LAR', away_score=6, home_score=21, clock=829,
             quarter=4, play_clock=39, down=1, distance=10, possession='home',
             away_timeouts=3, home_timeouts=2, broadcast='monday_night')),
}
# The layout's own bar box: see the alignment note above.
REFERENCE_BOUNDS = {'frame_000120.png': (437, 942, 1478, 1052),
                    'frame_000620.png': (437, 942, 1478, 1052)}
# Independent surface ROIs, not a claim of exact segmentation. Identical to s10.
REGIONS = {
    'wing_colour': [(438, 948, 686, 1050), (1230, 948, 1477, 1050)],
    'logo': [(438, 944, 656, 1050), (1260, 944, 1477, 1050)],
    'score': [(696, 955, 816, 1026), (1100, 955, 1220, 1026)],
    'down_capsule': [(819, 942, 1100, 989)],
    'housing_rim': [(438, 942, 1477, 948), (438, 1046, 1477, 1052), (831, 989, 1089, 999)],
    'pill': [(839, 999, 1082, 1043)],
}


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def draw(preview, state, wide):
    geometry, capture = preview.capture(state, wide)
    try:
        mode = preview.modes[wide]
        with tempfile.TemporaryDirectory(prefix='s12-raster-') as tmp:
            path = Path(tmp) / 'hud.png'
            receipt = projection.render_native(capture['live_decoded'], mode['atlas'], preview.fonts,
                geometry, path, texture_spans=capture['texture_spans'],
                background=Image.new('RGB', (640, 480), '#303030'),
                gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(capture)))
            hud = Image.open(path).convert('RGB').crop((0, 16, 640, 464))
            display = hud.resize(PLAYER[wide], Image.Resampling.LANCZOS)
        return display, dict(state=sprite.normalize_state(state), raster=receipt,
            hud=[640, 448], display=list(PLAYER[wide]), filter='Lanczos display approximation',
            runtime_witnessed=False, calibrated_gpu_capture=False)
    finally:
        capture['machine'].close()


def aligned(im):
    canvas = Image.new('RGB', PLAYER[True], '#303030')
    canvas.paste(im, ((canvas.width - im.width) // 2, 0))
    return canvas


def box(b):
    return tuple(round(v * SCALE) for v in b)


def reference(path):
    source = Image.open(path).convert('RGB')
    x, y, right, bottom = REFERENCE_BOUNDS[path.name]
    factor = 617 / (right - x)
    resized = source.resize((round(source.width * factor), round(source.height * factor)),
                            Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', PLAYER[True], '#303030')
    target_x, target_y, _, _ = box((437, 942, 1478, 1052))
    canvas.paste(resized, (target_x - round(x * factor), target_y - round(y * factor)))
    return canvas


def visible(mask):
    """Retain only disagreement with a 2 by 2 player-pixel core."""
    core = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
    result = np.zeros_like(mask)
    for y in range(2):
        for x in range(2):
            result[y:y + core.shape[0], x:x + core.shape[1]] |= core
    return result


def metrics(im, ref):
    actual = np.asarray(aligned(im), dtype=float)
    target = np.asarray(ref, dtype=float)
    bright_a = actual.min(2) > 155
    bright_b = target.min(2) > 155
    rows = []
    for name, regions in REGIONS.items():
        roi = np.zeros(actual.shape[:2], bool)
        for r in regions:
            x, y, right, bottom = box(r)
            roi[y:bottom, x:right] = True
        rgb_diff = np.max(abs(actual - target), axis=2) >= 24
        if name == 'wing_colour':
            roi &= ~(bright_a | bright_b)
            colour_a = (actual.max(2) - actual.min(2) > 14) | (actual.min(2) > 53)
            colour_b = (target.max(2) - target.min(2) > 14) | (target.min(2) > 53)
            diff = colour_a ^ colour_b
        elif name in ('logo', 'score'):
            diff = bright_a ^ bright_b
        elif name == 'pill':
            diff = (actual.min(2) > 185) ^ (target.min(2) > 185)
        elif name == 'down_capsule':
            surface_a = (np.max(abs(actual - 37), axis=2) > 24) & ~bright_a
            surface_b = (np.max(abs(target - 37), axis=2) > 24) & ~bright_b
            diff = surface_a ^ surface_b
        else:
            surface_a = (actual.mean(2) > 65) | (actual.max(2) - actual.min(2) > 35)
            surface_b = (target.mean(2) > 65) | (target.max(2) - target.min(2) > 35)
            diff = surface_a ^ surface_b
        counted = visible(roi & diff)
        rows.append(dict(feature=name, visible_area_px=int(counted.sum()),
            rgb_diagnostic_px=int(visible(roi & rgb_diff).sum()),
            measured_area_px=int(roi.sum()),
            threshold='Feature occupancy with a 2x2 player-pixel core; exact thresholds in metrics()',
            method='Visible feature occupancy XOR, filtered to 2x2 player-pixel cores. RGB mismatch retained only as a diagnostic.',
            caveat='White logo ink only; coloured silhouette also changes the wing ROI.' if name == 'logo'
                   else 'Surface/shape proxy; not a perceptual identity verdict.'))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase')
    args = parser.parse_args()
    preview = sprite.NativePreview()
    rows = []
    receipts = {}
    for name, (path, state) in CASES.items():
        ref = reference(path)
        for wide in (False, True):
            aspect = '169' if wide else '43'
            im, receipt = draw(preview, state, wide)
            im.save(OUT / f'{args.phase}_{name}_{aspect}.png')
            receipts[name + '_' + aspect] = receipt
            rows.extend(dict(matchup=name, aspect=aspect, **r) for r in metrics(im, ref))
    ranked = []
    for feature in REGIONS:
        values = [r['visible_area_px'] for r in rows if r['feature'] == feature]
        ranked.append(dict(feature=feature, visible_area_px=round(sum(values) / len(values), 2),
            maximum_area_px=max(values),
            metric='mean player pixels across two measured Giants at Rams states and both aspects'))
    ranked.sort(key=lambda r: -r['visible_area_px'])
    for i, r in enumerate(ranked):
        r['rank'] = i + 1
    write(args.phase + '_measurements.json', dict(
        player_sizes={str(k): v for k, v in PLAYER.items()}, bar_width_px=617, rows=rows, ranked=ranked,
        provenance={name: dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               state=state, bar_bounds=REFERENCE_BOUNDS[path.name])
                    for name, (path, state) in CASES.items()},
        limitation='Proxy counts overlap between logo and wing and must not be summed. '
                   'Broadcast frames stay read-only and outside the repository. '
                   'No 4:3 broadcast exists; the 4:3 row reuses the 16:9 reference at the same bar width.'))
    write(args.phase + '_native_receipts.json', receipts)
    print(json.dumps(ranked, indent=2))


if __name__ == '__main__':
    main()
