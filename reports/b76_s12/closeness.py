"""Per-element closeness of our sprite bar to the Giants at Rams MNF broadcast.

Both sides are measured by the same code: reports/b76_s12/harvest.py measures the
broadcast composite, and the identical routines measure our own rendered frame.
Jev sees only the compact text of those measurements and never a pixel. Every
call is journaled through tools/scorebug_sprite/jev/session.py, which checks the
job's three-dollar cap before each request.
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
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(OUT)]
from tools.scorebug_sprite.jev.session import Session, write_json
import harvest
from mod_editor.core import nfl2k5_scorebug_sprite as sprite
from tools.scorebug_sprite import gpu, xemu_model
import nfl2k5_scorebug_projection as projection

STATE = dict(away='NYG', home='LAR', away_score=6, home_score=21, clock=829,
             quarter=4, play_clock=39, down=1, distance=10, possession='home',
             away_timeouts=3, home_timeouts=2, broadcast='monday_night')
CLASSES = ('colour_wrong', 'too_large', 'too_small', 'misplaced', 'missing_element',
           'extra_element', 'edge_softness', 'matches')
LEVELS = [
    'Far: the element reads as a different design at player size.',
    'Off: one dimension or the colour is wrong by more than a tenth of the element.',
    'Near: a visible but small difference, under a tenth of the element.',
    'Close: differences are at or below the two-player-pixel visibility floor.',
    'Indistinguishable within the measurement method.',
]


def render_frame(path: Path) -> np.ndarray:
    """Our own bar at the matched state, in the broadcast's 1920 by 1080 frame."""
    preview = sprite.NativePreview()
    geometry, capture = preview.capture(STATE, True)
    try:
        mode = preview.modes[True]
        with tempfile.TemporaryDirectory(prefix='s12-close-') as tmp:
            raster = Path(tmp) / 'hud.png'
            projection.render_native(capture['live_decoded'], mode['atlas'], preview.fonts,
                geometry, raster, texture_spans=capture['texture_spans'],
                # A pitch-like background, so harvest.bar_box() measures our bar
                # with the same pitch-fraction predicate it applies to a broadcast
                # frame. A neutral background equal to the body luma made the
                # bar row measure the whole crop in the first run.
                background=Image.new('RGB', (640, 480), (58, 108, 52)),
                gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(capture)))
            hud = Image.open(raster).convert('RGB').crop((0, 16, 640, 464))
            full = hud.resize((1920, 1080), Image.Resampling.LANCZOS)
        full.save(path)
        return np.asarray(full, dtype=np.float32)
    finally:
        capture['machine'].close()


def size(box):
    return None if not box else [box[2] - box[0], box[3] - box[1]]


def delta(ours, theirs):
    if not ours or not theirs:
        return None
    return [round(float(a - b), 2) for a, b in zip(ours, theirs)]


def rows_for(ours: np.ndarray, broadcast: dict) -> list:
    mine = harvest.measure(ours)
    rows = []
    for name in ('bar', 'plate', 'capsule', 'housing_rail', 'away_score', 'home_score',
                 'away_timeouts', 'home_timeouts', 'quarter', 'clock', 'play_clock',
                 'away_logo', 'home_logo', 'rim_top', 'rim_bottom'):
        theirs = broadcast['composite']['boxes'].get(name)
        row = dict(element=name, broadcast_box=theirs, our_box=mine.get(name),
                   broadcast_size=size(theirs), our_size=size(mine.get(name)),
                   size_delta_px=delta(size(mine.get(name)), size(theirs)),
                   position_delta_px=delta(mine.get(name), theirs))
        if row['size_delta_px']:
            row['size_delta_player_px'] = [round(v * harvest.SCALE, 2) for v in row['size_delta_px']]
        rows.append(row)
    for side in ('away', 'home'):
        theirs = broadcast['wings'][side]
        ourwing = harvest.wing_profile(ours, side)
        rows.append(dict(element=side + '_wing_falloff',
                         broadcast_peak_signal=theirs['peak_signal'], our_peak_signal=ourwing['peak_signal'],
                         broadcast_decay_px=theirs.get('decay_px'), our_decay_px=ourwing.get('decay_px'),
                         broadcast_peak_rgb=theirs['peak_rgb'], our_peak_rgb=ourwing['peak_rgb'],
                         broadcast_fall_to_25_px=theirs.get('fall_to_25_percent_px'),
                         our_fall_to_25_px=ourwing.get('fall_to_25_percent_px')))
    for name, kinds in (('away_logo', ('light', 'red')), ('home_logo', ('gold', 'blue'))):
        x0, y0, x1, y1 = harvest.WINDOWS[name]
        patch = ours[y0:y1, x0:x1]
        entry = dict(element=name + '_mark_colour')
        for kind in kinds:
            mask = harvest.ink(patch, kind)
            entry['our_' + kind + '_pixels'] = int(mask.sum())
            entry['broadcast_' + kind + '_pixels'] = broadcast['marks'][name][kind]['pixels']
            entry['broadcast_' + kind + '_rgb'] = broadcast['marks'][name][kind]['median_rgb']
            entry['our_' + kind + '_rgb'] = [round(float(v), 2) for v in np.median(patch[mask], axis=0)] if mask.any() else None
        rows.append(entry)
    for name, region in (('body', (1215, 1000, 1245, 1035)), ('capsule_surface', (900, 1012, 916, 1030)),
                         ('plate_top', (900, 949, 1010, 954)), ('plate_bottom', (900, 974, 1010, 980)),
                         ('rim_top_colour', (1150, 946, 1230, 956)), ('rim_bottom_colour', (1150, 1046, 1230, 1051))):
        x0, y0, x1, y1 = region
        ourrgb = [round(float(v), 2) for v in np.median(ours[y0:y1, x0:x1].reshape(-1, 3), axis=0)]
        key = name if name in broadcast['colours'] else {'capsule_surface': 'capsule',
                                                         'rim_top_colour': 'rim_top',
                                                         'rim_bottom_colour': 'rim_bottom'}.get(name, name)
        theirs = broadcast['colours'][key]['median']
        rows.append(dict(element=name + '_rgb', broadcast_rgb=theirs, our_rgb=ourrgb,
                         rgb_delta=[round(a - b, 2) for a, b in zip(ourrgb, theirs)],
                         max_channel_delta=round(max(abs(a - b) for a, b in zip(ourrgb, theirs)), 2)))
    mark = broadcast['watermark']
    rows.append(dict(element='watermark', broadcast_box=mark['box'], broadcast_opacity=mark['opacity'],
                     our_box=json.loads((ROOT / 'data/nfl2k5_scorebug_sprite/layout.json').read_text())['brand'][0]['box'],
                     our_opacity=json.loads((ROOT / 'data/nfl2k5_scorebug_sprite/layout.json').read_text())['brand'][0]['opacity']))
    return rows


def compact(row: dict) -> dict:
    """Text only, with the numbers already reduced to what a judge can use."""
    out = {k: v for k, v in row.items() if k != 'element'}
    out['element'] = row['element']
    out['player_bar_width_px'] = 617
    out['visibility_floor_player_px'] = 2
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, default=OUT)
    p.add_argument('--tag', default='before')
    a = p.parse_args(argv)
    broadcast = json.loads((a.report / 'harvest.json').read_text())
    ours = render_frame(a.report / ('our_frame_%s.png' % a.tag))
    rows = rows_for(ours, broadcast)
    session = Session(a.report)
    judged = []
    for row in rows:
        request = dict(tool='jev_ask', state=compact(row), questions=dict(
            defect=dict(type='choice',
                instructions='Classify how our authored element differs from the broadcast element, using only the measured numbers given. '
                             'Differences at or below two player pixels are matches. Do not infer a cause that the numbers do not show.',
                criteria={k: None for k in CLASSES}),
            closeness=dict(type='score',
                instructions='Rate how close our element is to the broadcast element on these measured numbers alone.',
                criteria=list(LEVELS)),
            worth_changing=dict(type='noul',
                instructions='Would changing this element measurably reduce the visible difference at the 617-pixel player bar, '
                             'given that a difference must cover a 2 by 2 player-pixel core to count?')))
        answers = session.replay(request, tool='b76-s12-closeness')
        judged.append(dict(element=row['element'], measurements=row, answers=answers,
                           defect=answers.get('defect', {}).get('choice'),
                           defect_confidence=answers.get('defect', {}).get('confidence'),
                           closeness_level=answers.get('closeness', {}).get('score'),
                           closeness_confidence=answers.get('closeness', {}).get('confidence'),
                           worth_changing=answers.get('worth_changing', {}).get('noul')))
    ranked = sorted(judged, key=lambda r: ((r['closeness_level'] if r['closeness_level'] is not None else 9.0),
                                           -(r['worth_changing'] or 0)))
    for i, r in enumerate(ranked):
        r['rank'] = i + 1
    write_json(a.report / ('closeness_%s.json' % a.tag), dict(
        schema='b76-s12-closeness/v1', state=STATE, levels=LEVELS, classes=list(CLASSES),
        cost_usd=round(session.spent(), 6), calls=len(rows), ranked=ranked,
        method='Both sides measured by reports/b76_s12/harvest.py. Jev receives text only; all arithmetic is in Python.'))
    for r in ranked[:14]:
        print('%2d %-26s level=%.2f conf=%.2f defect=%-16s worth=%.2f' % (
            r['rank'], r['element'], r['closeness_level'] or 0., r['closeness_confidence'] or 0,
            r['defect'], r['worth_changing'] or 0))
    print('Jev spend so far: $%.4f' % session.spent())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
