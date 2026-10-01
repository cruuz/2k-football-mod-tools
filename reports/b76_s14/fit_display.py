"""Broadcast display shades: measured for the teams on air, fitted for the rest, checked leave-one-out.

Inputs:
- reports/b76_s14/broadcast_colours.json (reports/b76_s14/broadcast_colours.py): per-row on-air wing colours at
  each wing's outer end and the plate colour by possession, for NYG, LAR, DEN, KC, LV and HOU.
- The current sprite data folder (run ``author.py --steps wingcell`` first): our own response is read from two
  offline renders in which the NYG and LAR wing and plate carry the probe tints #000000 and #808080. The palette
  validator is widened in-process for those two probe renders only (the probe tints are not team colours); it is
  restored before anything is written, and nothing from the probe folder is kept.

Measured shade: the tint whose render reproduces the broadcast wing at the outer end of the bar (rows 948 to 1020,
12 columns inside each bar end) in the least-squares sense through our own wing coverage, clipped to 0..255. The
plate is measured the same way over the plate body without the label (for the record; see the report).

Transfer: ``nfl2k5_scorebug_teams.broadcast_shade_rgb``: HSV hue kept, value 1, saturation scaled by one fitted
factor; chromatic results capped at the lightest measured chromatic wing (OKLab L). Leave-one-out refits the factor
and the cap without the held-out team. Alternatives are fitted and reported for comparison only.

Writes data/nfl2k5_scorebug_sprite/broadcast_display.json and reports/b76_s14/display_fit.json.
"""
from __future__ import annotations

import contextlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.optimize import least_squares, minimize_scalar

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_sprite as sprite  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_teams as teams  # noqa: E402
from tools.scorebug_sprite import gpu, xemu_model  # noqa: E402
import nfl2k5_scorebug_projection as projection  # noqa: E402

DATA = ROOT / 'data/nfl2k5_scorebug_sprite'
CROP = (420, 930, 1500, 1065)
ROWS = (948, 1021)
OURS = dict(away=(440, 452), home=(1463, 1475))
PLATE = (845, 953, 1075, 972)
PROBES = ('#000000', '#808080')
NEUTRAL_CHROMA = 0.02
BOUND_MARGIN = 1.5


@contextlib.contextmanager
def probe_folder():
    """A scratch copy of the data folder with probe tints, accepted by a widened validator in-process only."""
    original_variants, original_contrast, original_data = teams.variants, teams.contrast_white, teams.DATA
    with tempfile.TemporaryDirectory(prefix='s14-probe-') as tmp:
        folders = {}
        for tint in PROBES:
            folder = Path(tmp) / tint[1:]
            shutil.copytree(DATA, folder)
            accents = json.loads((folder / 'team_accents.json').read_text())
            for name in ('NYG', 'LAR'):
                accents['teams'][name].update(wing=tint, plate=tint)
                accents['teams'][name].pop('display', None)
            (folder / 'team_accents.json').write_text(json.dumps(accents))
            folders[tint] = folder
        teams.variants = lambda colours: original_variants(colours) | set(PROBES)
        teams.contrast_white = lambda value: 21.0 if value in PROBES else original_contrast(value)
        try:
            yield folders
        finally:
            teams.variants, teams.contrast_white, teams.DATA = original_variants, original_contrast, original_data


def render(preview, state):
    geometry, capture = preview.capture(state, True)
    try:
        mode = preview.modes[True]
        with tempfile.TemporaryDirectory(prefix='s14-fit-') as tmp:
            raster = Path(tmp) / 'hud.png'
            projection.render_native(capture['live_decoded'], mode['atlas'], preview.fonts, geometry, raster,
                                     texture_spans=capture['texture_spans'],
                                     background=Image.new('RGB', (640, 480), (58, 108, 52)),
                                     gpu_pipeline=xemu_model.Pipeline(gpu.capture_state(capture)))
            hud = Image.open(raster).convert('RGB').crop((0, 16, 640, 464))
            frame = np.asarray(hud.resize((1920, 1080), Image.Resampling.LANCZOS), dtype=np.float64)
        return frame[CROP[1]:CROP[3], CROP[0]:CROP[2]]
    finally:
        capture['machine'].close()


def response():
    """Our per-pixel response to the wing and plate tint: frame = A + B * tint / 128 per probe step."""
    frames = {}
    with probe_folder() as folders:
        for tint, folder in folders.items():
            teams.DATA = folder
            preview = sprite.NativePreview(folder=folder)
            for side in ('away', 'home'):
                state = dict(away='NYG', home='LAR', away_score=6, home_score=21, clock=829, quarter=4, play_clock=39,
                             down=1, distance=10, possession=side, away_timeouts=3, home_timeouts=2)
                frames[tint, side] = render(preview, state)
    return {side: (frames['#000000', side], (frames['#808080', side] - frames['#000000', side]) / 128.0)
            for side in ('away', 'home')}


def dilate(mask, steps=2):
    for _ in range(steps):
        padded = np.pad(mask, 1)
        mask = np.max([padded[dy:dy + mask.shape[0], dx:dx + mask.shape[1]] for dy in range(3) for dx in range(3)],
                      axis=0)
    return mask


def measured_shades(colours, resp):
    out = {}
    for team, entry in colours['teams'].items():
        for source, m in entry.items():
            side = m['side']
            rows = np.array(m['wing_rows']['rgb'])
            first = m['wing_rows']['first_row']
            observed = rows[ROWS[0] - first:ROWS[1] - first]
            x0, x1 = OURS[side]
            a, b = (r[ROWS[0] - CROP[1]:ROWS[1] - CROP[1], x0 - CROP[0]:x1 - CROP[0]].mean(1) for r in resp['home'])
            wing = (b * (observed - a)).sum(0) / (b * b).sum(0)
            X0, Y0, X1, Y1 = PLATE
            pa, pb = (r[Y0 - CROP[1]:Y1 - CROP[1], X0 - CROP[0]:X1 - CROP[0]] for r in resp[side])
            ours_label = dilate((pa + 128 * pb).min(-1) > 200)
            keep = ~ours_label
            plate_on_air = np.array(m['plate']['rgb']) if m.get('plate') else None
            plate = None
            if plate_on_air is not None:
                a_med = np.median(pa[keep], axis=0)
                b_med = np.median(pb[keep], axis=0)
                plate = (plate_on_air - a_med) / b_med
            out[team] = dict(source=source, side=side, frames=m['wing']['frames'],
                             wing=[int(round(v)) for v in np.clip(wing, 0, 255)],
                             wing_unclipped=[round(float(v), 1) for v in wing],
                             plate=None if plate is None else [int(round(v)) for v in np.clip(plate, 0, 255)],
                             plate_frames=m['plate']['frames'] if m.get('plate') else 0,
                             on_air_wing_rows=dict(top=[round(float(v), 1) for v in observed[:10].mean(0)],
                                                   middle=[round(float(v), 1) for v in observed[30:50].mean(0)]))
    return out


# ---------------------------------------------------------------- colour error measures
def to_lab(rgb):
    lin = np.array([[teams._linear(c) for c in px] for px in np.atleast_2d(rgb)])
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], -1)


def de2000(rgb1, rgb2):
    """CIEDE2000 (Sharma, Wu and Dalal 2005)."""
    L1, a1, b1 = to_lab(rgb1).T
    L2, a2, b2 = to_lab(rgb2).T
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cb ** 7 / (Cb ** 7 + 25 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(C1p * C2p == 0, 0, np.where(dhp > 180, dhp - 360, np.where(dhp < -180, dhp + 360, dhp)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))
    Lbp, Cbp, hs = (L1 + L2) / 2, (C1p + C2p) / 2, h1p + h2p
    hbp = np.where(C1p * C2p == 0, hs, np.where(np.abs(h1p - h2p) <= 180, hs / 2,
                                                np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    Rc = 2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25 ** 7))
    Sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * 30 * np.exp(-(((hbp - 275) / 25) ** 2)))) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def hexof(rgb):
    return '#' + ''.join('%02X' % int(round(float(c))) for c in rgb)


# ---------------------------------------------------------------- the transfer and its alternatives
def chroma(colour):
    _l, a, b = teams.oklab(teams.rgb(colour))
    return float(np.hypot(a, b))


def cap_of(names, shades, parents):
    return max(teams.oklab(shades[n])[0] for n in names if chroma(parents[n]) >= NEUTRAL_CHROMA)


def fit_transfer(names, shades, parents):
    cap = cap_of(names, shades, parents)

    def loss(s):
        tr = dict(saturation=s, value=1.0, lightness_cap=cap, neutral_chroma=NEUTRAL_CHROMA)
        return sum(float(np.sum((np.array(teams.broadcast_shade_rgb(parents[n], tr)) - np.array(shades[n])) ** 2))
                   for n in names)
    s = minimize_scalar(loss, bounds=(0.3, 1.0), method='bounded', options=dict(xatol=1e-6)).x
    return dict(saturation=round(float(s), 4), value=1.0, lightness_cap=round(float(cap), 4),
                neutral_chroma=NEUTRAL_CHROMA)


def hsv3(p, parent):
    hue, sat, val = teams._hsv(teams.rgb(parent))
    return teams._from_hsv(hue, min(1.0, p[0] * sat), min(1.0, max(0.0, p[1] + p[2] * val)))


def affine6(p, parent):
    rgb = np.array(teams.rgb(parent), float)
    norm = rgb * 255 / max(rgb.max(), 1)
    return np.clip(np.array(p[:3]) + np.array(p[3:]) * norm, 0, 255)


def fit_alternative(model, p0, names, shades, parents):
    def res(p):
        return np.concatenate([np.array(model(p, parents[n])) - np.array(shades[n]) for n in names])
    return least_squares(res, p0).x


def leave_one_out(names, shades, parents):
    rows = {}
    for held in names:
        keep = [n for n in names if n != held]
        tr = fit_transfer(keep, shades, parents)
        rows[held] = dict(transfer=tr, predicted=[round(v, 1) for v in teams.broadcast_shade_rgb(parents[held], tr)])
        for key, (model, p0) in dict(hsv3=(hsv3, [0.87, 0.9, 0.2]), affine6=(affine6, [40, 20, 50, .8, .9, .8])).items():
            p = fit_alternative(model, p0, keep, shades, parents)
            rows[held][key] = [round(float(v), 1) for v in model(p, parents[held])]
    return rows


def errors(predicted, measured):
    p, m = np.array(predicted, float), np.array(measured, float)
    return dict(de2000=round(float(de2000(p, m)[0]), 2),
                oklab=round(float(np.linalg.norm(np.array(teams.oklab(p)) - np.array(teams.oklab(m)))), 4),
                rgb_max=int(round(float(np.abs(p - m).max()))))


def main(argv=None) -> int:
    colours = json.loads((OUT / 'broadcast_colours.json').read_text())
    accents = json.loads((DATA / 'team_accents.json').read_text())['teams']
    resp = response()
    measured = measured_shades(colours, resp)
    names = sorted(measured)

    def parent_of(name):
        team = accents[name]
        if 'display' in team:
            return team['display']['parent']
        return next(c for c in team['official'] if team['wing'] in teams.variants([c]))
    parents = {n: parent_of(n) for n in accents if accents[n]['slot'] < 32}
    shades = {n: tuple(measured[n]['wing']) for n in names}
    transfer = fit_transfer(names, shades, parents)
    loo = leave_one_out(names, shades, parents)
    table = {}
    for n in names:
        fitted = teams.broadcast_shade_rgb(parents[n], transfer)
        table[n] = dict(parent=parents[n], measured=hexof(shades[n]), fitted_all=hexof(fitted),
                        fit_error=errors(fitted, shades[n]),
                        loo_error=errors(loo[n]['predicted'], shades[n]),
                        loo_hsv3=errors(loo[n]['hsv3'], shades[n]), loo_affine6=errors(loo[n]['affine6'], shades[n]),
                        loo_prediction=hexof(loo[n]['predicted']))
    summary = {key: dict(mean=round(float(np.mean([table[n][key]['de2000'] for n in names])), 2),
                         max=round(float(np.max([table[n][key]['de2000'] for n in names])), 2),
                         rgb_max=int(np.max([table[n][key]['rgb_max'] for n in names])))
               for key in ('fit_error', 'loo_error', 'loo_hsv3', 'loo_affine6')}
    bound = round(BOUND_MARGIN * max(table[n]['loo_error']['oklab'] for n in names), 4)
    transfer['measured_bound'] = bound
    display = dict(
        schema='scorebug-broadcast-display/v1',
        scope='Scorebug-only display layer: the on-air shade of each NFL team\'s sourced wing colour. '
              'team_colors_official_2026.json is unchanged; team_accents.json records, per team, the class, '
              'whether the shade was measured or fitted, its official parent and the sourced accent it replaces.',
        roles=list(teams.DISPLAY_ROLES),
        transfer=dict(transfer, form='HSV hue kept, value 1, saturation times the factor; a chromatic result '
                                     'lighter than lightness_cap (OKLab L) is scaled down in linear light to the '
                                     'cap; measured shades must lie within measured_bound (OKLab distance) of '
                                     'their parent\'s fitted shade',
                      fitted_on=names, leave_one_out_de2000=summary['loo_error'],
                      report='reports/b76_s14/display_fit.json'),
        measured={n: dict(wing=hexof(shades[n]), parent=parents[n],
                          evidence='%s broadcast, %d frames; reports/b76_s14/broadcast_colours.json' % (
                              dict(nyg_lar='2026 Giants at Rams Monday Night Football (ESPN)',
                                   den_kc='2026 Broncos at Chiefs Monday Night Football (ESPN), full game',
                                   lv_hou='2026 preseason Raiders at Texans (ESPN)')[measured[n]['source']],
                              measured[n]['frames'])) for n in names})
    (DATA / 'broadcast_display.json').write_text(json.dumps(display, indent=1) + '\n', encoding='utf-8',
                                                 newline='\n')
    fitted_all = {n: dict(parent=parents[n], sourced=accents[n].get('display', {}).get('sourced', accents[n]['wing']),
                          shade=teams.broadcast_shade(parents[n], transfer),
                          parent_oklab_chroma=round(chroma(parents[n]), 4),
                          capped=bool(chroma(parents[n]) >= NEUTRAL_CHROMA and teams.oklab(teams._from_hsv(
                              teams._hsv(teams.rgb(parents[n]))[0],
                              min(1.0, transfer['saturation'] * teams._hsv(teams.rgb(parents[n]))[1]), 1.0))[0]
                              > transfer['lightness_cap']))
                  for n in sorted(parents)}
    plate_names = [n for n in names if measured[n]['plate']]
    report = dict(schema='b76-s14-display-fit/v1', transfer=transfer, measured=measured, table=table,
                  summary=summary, all_teams=fitted_all,
                  plate=dict(measured={n: hexof(measured[n]['plate']) for n in plate_names},
                             sourced={n: accents[n]['plate'] for n in plate_names},
                             applied=False,
                             note='Measured for the record; not applied. See B76_S14_REPORT.md: every trial that put '
                                  'the measured plates on the bar raised a pinned residual.'),
                  method=__doc__.split('\n\n')[1:4])
    (OUT / 'display_fit.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(transfer=transfer, summary=summary), indent=1))
    for n in names:
        print(n, table[n]['measured'], 'fit', table[n]['fitted_all'], 'LOO', table[n]['loo_prediction'],
              table[n]['loo_error'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
