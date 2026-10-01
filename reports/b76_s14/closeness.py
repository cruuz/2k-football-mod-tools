"""Jev's closeness verdicts for what this pass changed, before and after.

1. Wing colour, per measured team (NYG, LAR, DEN, KC, LV, HOU): the broadcast's per-row wing colour just inside
   the bar end (reports/b76_s14/broadcast_colours.json) against the same rows of our own render of that matchup,
   measured by the same code (the outer 12 columns of our bar, rows 948 to 1020: top, middle and bottom thirds and
   the mean colour difference). Jev gets these numbers as text and returns a closeness level (0 far to 4
   indistinguishable), a defect class and whether a change would be visible at the 617-pixel player bar.
2. With ``--rubric``, the s12 per-element rubric (reports/b76_s12/closeness.py rows_for, unchanged) for the
   Giants at Rams state against the s12 harvest, for the whole bar.

Every call goes through tools/scorebug_sprite/jev/session.py (journal reports/b76_s14/jev_calls.jsonl, the job's
three-dollar cap checked before each request). All arithmetic is in Python; Jev sees text only. The renders are
the offline native model; no in-game result is claimed.

Usage: python3 reports/b76_s14/closeness.py --tag before|after [--rubric]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from tools.scorebug_sprite.jev.session import Session, write_json  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from tools.scorebug_sprite import gpu, xemu_model  # noqa: E402
import nfl2k5_scorebug_projection as projection  # noqa: E402

ROWS = (948, 1021)
OURS = dict(away=(440, 452), home=(1463, 1475))
MATCHUPS = dict(
    nyg_lar=dict(away='NYG', home='LAR', away_score=6, home_score=21, clock=829, quarter=4, play_clock=39, down=1,
                 distance=10, possession='home', away_timeouts=3, home_timeouts=2),
    den_kc=dict(away='DEN', home='KC', away_score=0, home_score=0, clock=897, quarter=1, play_clock=40, down=1,
                distance=10, possession='away'),
    lv_hou=dict(away='LV', home='HOU', away_score=0, home_score=7, clock=515, quarter=1, play_clock=10, down=1,
                distance=10, possession='away'))
LEVELS = [
    'Far: the element reads as a different colour at player size.',
    'Off: clearly darker, lighter or of another hue than the broadcast.',
    'Near: a visible but small difference.',
    'Close: differences at or below what a viewer notices at the 617-pixel player bar.',
    'Indistinguishable within the measurement method.',
]
CLASSES = ('too_dark', 'too_light', 'wrong_hue', 'too_saturated', 'too_grey', 'gradient_shape', 'matches')


def render(preview, state):
    geometry, capture = preview.capture(state, True)
    try:
        mode = preview.modes[True]
        with tempfile.TemporaryDirectory(prefix='s14-close-') as tmp:
            raster = Path(tmp) / 'hud.png'
            projection.render_native(capture['live_decoded'], mode['atlas'], preview.fonts, geometry, raster,
                                     texture_spans=capture['texture_spans'],
                                     background=Image.new('RGB', (640, 480), (58, 108, 52)),
                                     gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(capture)))
            hud = Image.open(raster).convert('RGB').crop((0, 16, 640, 464))
            return np.asarray(hud.resize((1920, 1080), Image.Resampling.LANCZOS), dtype=np.float64)
    finally:
        capture['machine'].close()


def thirds(rows):
    n = len(rows) // 3
    return [[round(float(v), 1) for v in rows[i * n:(i + 1) * n].mean(0)] for i in range(3)]


def wing_rows(frame, side):
    x0, x1 = OURS[side]
    return frame[ROWS[0]:ROWS[1], x0:x1].mean(1)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--tag', required=True)
    p.add_argument('--rubric', action='store_true')
    a = p.parse_args(argv)
    colours = json.loads((OUT / 'broadcast_colours.json').read_text())
    accents = json.loads((ROOT / 'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())['teams']
    preview = sprite.NativePreview()
    session = Session(OUT)
    rows = []
    for key, state in MATCHUPS.items():
        frame = render(preview, sprite.normalize_state(state))
        for side in ('away', 'home'):
            team = state[side]
            measured = colours['teams'][team][key]
            first = measured['wing_rows']['first_row']
            broadcast = np.array(measured['wing_rows']['rgb'])[ROWS[0] - first:ROWS[1] - first]
            ours = wing_rows(frame, side)
            row = dict(element='%s_wing_colour' % team, side=side, our_tint=accents[team]['wing'],
                       broadcast_rgb_top_middle_bottom=thirds(broadcast), our_rgb_top_middle_bottom=thirds(ours),
                       mean_abs_rgb_difference=round(float(np.abs(ours - broadcast).mean()), 1),
                       max_row_rgb_difference=round(float(np.abs(ours - broadcast).max()), 1),
                       player_bar_width_px=617)
            request = dict(tool='jev_ask', state=row, questions=dict(
                closeness=dict(type='score', criteria=list(LEVELS),
                               instructions='Rate how close our wing colour is to the broadcast wing colour, using '
                                            'only the measured RGB rows given (top, middle and bottom thirds of '
                                            'the wing at the bar end, 0 to 255).'),
                defect=dict(type='choice', criteria={c: None for c in CLASSES},
                            instructions='Name the main way our wing colour differs from the broadcast, from the '
                                         'numbers alone. Differences under about 12 RGB levels are matches.'),
                visible=dict(type='noul', instructions='Would a viewer notice the difference between the two '
                                                        'wing colours at the 617-pixel player bar?')))
            answers = session.replay(request, tool='b76-s14-wing-closeness')
            rows.append(dict(row, closeness=answers.get('closeness', {}).get('score'),
                             closeness_confidence=answers.get('closeness', {}).get('confidence'),
                             defect=answers.get('defect', {}).get('choice'),
                             visible=answers.get('visible', {}).get('noul'), answers=answers))
    result = dict(schema='b76-s14-closeness/v1', tag=a.tag, levels=LEVELS, classes=list(CLASSES), wings=rows,
                  method=__doc__.split('\n\n')[1].strip())
    if a.rubric:
        spec = importlib.util.spec_from_file_location('b76_s12_closeness', ROOT / 'reports/b76_s12/closeness.py')
        s12 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s12)
        broadcast = json.loads((ROOT / 'reports/b76_s12/harvest.json').read_text())
        ours = s12.render_frame(OUT / ('our_frame_%s.png' % a.tag))
        judged = []
        for row in s12.rows_for(ours, broadcast):
            request = dict(tool='jev_ask', state=s12.compact(row), questions=dict(
                defect=dict(type='choice', criteria={k: None for k in s12.CLASSES},
                            instructions='Classify how our authored element differs from the broadcast element, '
                                         'using only the measured numbers given. Differences at or below two '
                                         'player pixels are matches. Do not infer a cause that the numbers do not '
                                         'show.'),
                closeness=dict(type='score', criteria=list(s12.LEVELS),
                               instructions='Rate how close our element is to the broadcast element on these '
                                            'measured numbers alone.'),
                worth_changing=dict(type='noul', instructions='Would changing this element measurably reduce the '
                                                              'visible difference at the 617-pixel player bar, '
                                                              'given that a difference must cover a 2 by 2 '
                                                              'player-pixel core to count?')))
            answers = session.replay(request, tool='b76-s14-rubric')
            judged.append(dict(element=row['element'], measurements=row,
                               closeness_level=answers.get('closeness', {}).get('score'),
                               defect=answers.get('defect', {}).get('choice'),
                               worth_changing=answers.get('worth_changing', {}).get('noul')))
        judged.sort(key=lambda r: r['closeness_level'] if r['closeness_level'] is not None else 9)
        result['rubric'] = judged
        result['rubric_mean_level'] = round(float(np.mean([r['closeness_level'] for r in judged
                                                           if r['closeness_level'] is not None])), 2)
    result['cost_usd'] = round(session.spent(), 6)
    write_json(OUT / ('closeness_%s.json' % a.tag), result)
    for r in rows:
        print('%-14s level %.2f defect %-14s visible %.2f mean|d| %.1f' % (
            r['element'], r['closeness'] or 0, r['defect'], r['visible'] or 0, r['mean_abs_rgb_difference']))
    if a.rubric:
        print('rubric mean level', result['rubric_mean_level'])
    print('Jev spend so far: $%.4f' % session.spent())
    # Written by render_frame for the rubric only; the report keeps just the JSON.
    frame = OUT / ('our_frame_%s.png' % a.tag)
    if frame.exists():
        frame.unlink()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
