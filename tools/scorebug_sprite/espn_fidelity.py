"""b778 sb3: deepen the scorebar's team gradient, give the plate a real bevel and light its rim like ESPN.

Noah (10/23 ~00:45): "The border and glow of the real score bug is still better than the one we're using in-game,
as well as the gradient color being deeper and more over the logo. It's just not accurate enough." and "it doesn't
even have a gradient on the down and distance". The measurements come from the 2026 ESPN bars at 1920x1080
(reports/b72_s9/broadcast_away_median.png and broadcast_home_median.png, and the read-only stills in
.b77-scratch/b778/sb2/ref_bars.png). No broadcast pixel is copied: each cell is rebuilt from the measured profile.

Changes, all inside the existing template cell sizes and quad budget:

wing     The s12 coverage field keeps its fit near the outer rail but the top and bottom glow are re-measured
         (a2 .45 -> 1.05, d2 13.82 -> 14, d3 461.6 -> 350; a3 1.5 -> 2.0, d4 2.839 -> 3.2, d5 83.55 -> 95). A
         window clears the glow before the score column, where the broadcast shows the body again; this keeps
         the white score/timeout/record glyphs on the dark body the way ESPN draws them. The result is more
         team colour over the mark and a darker falloff between the mark and the score.
plate    A 38-row source profile with the measured top bevel (0.62, 0.84, 0.82 after the outline), a body at
         about 0.70 of the possession tint and a dark lower edge (0.24 at the bottom). The texture is a neutral
         multiplier, so the runtime's per-team possession tint produces the reference's red and blue gradient
         states rather than the old flat red sheet. A one-texel dark outline and a light inner top line make the
         bevel read at the atlas footprint.
capsule  The measured 1 px rim (about 110 dark at the edge, 248 inside, 120 at the bottom) and a dark outline
         instead of the old soft gray ramp, with the same cell and quad. The score digits also get a one-texel
         light bevel; the traced broadcast face and metrics are unchanged.
rim      The two rim cells are re-authored as bright coverage: the 2026 bars keep a team-coloured light on the
         outer rail and lower lip. The runtime lightens each rim tint from the wing's own shade (the pre-accent
         default) and the white coverage lays it over the wing and body. No new quad is added.
buf      The standing buffalo is Buffalo's alternate. The shipped mark is replaced with the charging primary
         buffalo from the already-shipped official 128 px set, resampled to the 64 px cell.

python3 tools/scorebug_sprite/espn_fidelity.py [--folder FOLDER] [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tools/scorebug_sprite')]
DEFAULT_FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
LOGOS = ROOT / 'data/nfl2k5_scorebug_mnf' / 'logos'
ASSET_LOGOS = ROOT / 'data/nfl2k5_scorebug_assets' / 'logos'
RECORD = 'b778_sb3_espn_fidelity'

WING = dict(a1=0.8761, d1=41.19, v1=0.2879, a2=1.05, d2=14.0, d3=350.0,
            a3=2.0, d4=3.2, d5=95.0, window_start=250.0, window_end=330.0)
# Rows 0..37 of the 38 px plate, measured on the 2026 bars. The first and last
# rows are the dark outline; row 3 is the bevel crest.
PLATE_ROWS = [0.34, 0.42, 0.62, 0.84, 0.82, 0.79, 0.77, 0.75, 0.74, 0.73, 0.72,
              0.71, 0.71, 0.70, 0.70, 0.70, 0.70, 0.70, 0.69, 0.69, 0.69, 0.69,
              0.68, 0.68, 0.68, 0.68, 0.67, 0.67, 0.67, 0.66, 0.66, 0.65, 0.63,
              0.60, 0.55, 0.47, 0.36, 0.24]
PLATE_SOURCE = (274, 38)
CAPSULE_SOURCE = (183, 40)
RIM_SOURCE = (523, 110)
WING_SOURCE = (340, 110)


def _box(spec, name):
    return spec['cells'][name]['box']


def _filter(image, size):
    return image.resize(size, Image.Resampling.BOX)


def _white(size, alpha):
    image = Image.new('RGBA', size, (255, 255, 255, 255))
    image.putalpha(Image.fromarray(np.rint(np.clip(alpha, 0, 1) * 255).astype('uint8'), 'L'))
    return image


def rounded_mask(size, radius, supersample=4):
    width, height = size
    image = Image.new('L', (width * supersample, height * supersample), 0)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width * supersample - 1, height * supersample - 1),
                           radius * supersample, fill=255)
    return np.asarray(image.resize((width, height), Image.Resampling.BOX), dtype=float) / 255


def wing_alpha(size=WING_SOURCE, params=WING):
    width, height = size
    y, x = np.mgrid[0:height, 0:width].astype(float)
    edge = params['a1'] * np.exp(-x / params['d1']) * (1 - params['v1'] * y / max(1, height - 1))
    window = np.clip((params['window_end'] - x) / (params['window_end'] - params['window_start']), 0, 1)
    top = params['a2'] * np.exp(-y / params['d2']) * np.exp(-x / params['d3']) * window
    bottom = params['a3'] * np.exp(-(height - 1 - y) / params['d4']) * np.exp(-x / params['d5'])
    cover = np.clip(edge + top + bottom, 0, 1)
    shape = rounded_mask((width, height), 8)
    return cover * shape, cover


def wing_cell(size):
    cover, _ = wing_alpha()
    image = _filter(_white(WING_SOURCE, cover), size)
    arr = np.asarray(image).copy()
    arr[:, -1, 3] = 0
    arr[..., 3] = np.minimum.accumulate(arr[..., 3], axis=1)
    return Image.fromarray(arr, 'RGBA'), cover


def plate_cell(size):
    width, height = PLATE_SOURCE
    rows = np.interp(np.arange(height), np.arange(len(PLATE_ROWS)), PLATE_ROWS)
    rgb = np.rint(rows * 255).astype('uint8')
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    pixels = np.asarray(image).copy()
    mask = rounded_mask((width, height), 5)
    pixels[..., 0] = rgb[:, None]
    pixels[..., 1] = rgb[:, None]
    pixels[..., 2] = rgb[:, None]
    pixels[..., 3] = np.rint(mask * 255).astype('uint8')
    # One dark outline and one light inner bevel line, both inside the rounded mask.
    outline = mask - rounded_mask((width, height), 4)
    inner = rounded_mask((width, height), 4) - rounded_mask((width, height), 3)
    pixels[..., :3] = np.where(outline[..., None] > .35, 88, pixels[..., :3])
    pixels[..., :3] = np.where(inner[..., None] > .35, 255, pixels[..., :3])
    return _filter(Image.fromarray(pixels, 'RGBA'), size)


def capsule_cell(size):
    width, height = CAPSULE_SOURCE
    mask = rounded_mask((width, height), height // 2)
    rgb = np.full((height, width, 3), 248.0)
    rgb[0:1, :] = 150
    rgb[1:2, :] = 210
    rgb[2:3, :] = 245
    rgb[-4:-3, :] = 230
    rgb[-3:-2, :] = 200
    rgb[-2:-1, :] = 160
    rgb[-1:, :] = 130
    ring = np.clip(mask - rounded_mask((width, height), height // 2 - 1), 0, 1)
    rgb = np.where(ring[..., None] > .35, 150, rgb)
    arr = np.dstack([rgb, mask * 255]).astype('uint8')
    return _filter(Image.fromarray(arr, 'RGBA'), size)


def rim_cell(size, side):
    """White coverage cell for the bright rail the runtime tint supplies.

    The 2026 bars keep a bright team-coloured light on the outer rail and the lower lip; a white coverage
    cell under a lifted team tint reproduces it without inventing white paint. The top light is strong at the
    outer corners and fades before the centre; the lower lip is strongest at the centre. The outer one or two
    source pixels stay faint, so the wing's own colour is still the outermost edge.
    """
    width, height = RIM_SOURCE
    outer = np.arange(width, dtype=float)
    if side == 'home':
        outer = width - 1 - outer
    inner = width - 1 - outer
    centre = np.exp(-inner / 170.0)
    y = np.arange(height, dtype=float)[:, None]

    amplitude = 0.80 if side == 'away' else 0.55
    side = amplitude * np.exp(-outer[None, :] / 3.0)
    side = side * (0.84 + 0.16 * np.exp(-((y - 6.0) / 10.0) ** 2))
    top = 0.34 * np.exp(-y / 2.8) * np.exp(-outer[None, :] / 130.0)
    bottom = 0.30 * np.exp(-(height - 1 - y) / 2.4) * (0.35 + 0.65 * centre[None, :])
    alpha = np.clip(np.maximum(side, np.maximum(top, bottom)), 0, 1)
    pixels = np.dstack([np.full((height, width, 3), 255.0), alpha * 255]).astype('uint8')
    return _filter(Image.fromarray(pixels, 'RGBA'), size)


def buf_mark():
    source = Image.open(ASSET_LOGOS / 'buf.png').convert('RGBA')
    bounds = source.getchannel('A').getbbox()
    if bounds is None:
        raise ValueError('The official Buffalo mark is empty')
    source = source.crop(bounds)
    scale = 62 / max(source.width, source.height)
    mark = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))),
                         Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    canvas.alpha_composite(mark, ((64 - mark.width) // 2, (64 - mark.height) // 2))
    return canvas


def bevel_score_cell(cell):
    """One-texel light bevel on the traced score digit; the reference digits are not flat white."""
    arr = np.asarray(cell).copy()
    solid = arr[..., 3] > 128
    if solid.sum() < 8:
        return cell
    padded = np.pad(solid, 1)
    eroded = np.ones_like(solid)
    for dy in range(3):
        for dx in range(3):
            eroded &= padded[dy:dy + solid.shape[0], dx:dx + solid.shape[1]]
    edge = solid & ~eroded
    arr[..., :3][edge] = 218
    arr[..., :3][solid & ~edge] = 255
    return Image.fromarray(arr, 'RGBA')


def measurements(spec, sheet):
    cells = spec['cells']
    wing = np.asarray(sheet.crop(tuple(cells['wing']['box'])))[..., 3]
    plate = np.asarray(sheet.crop(tuple(cells['plate']['box'])))[..., :3]
    capsule = np.asarray(sheet.crop(tuple(cells['capsule']['box'])))[..., :3]
    away_rim = np.asarray(sheet.crop(tuple(cells['away_rim']['box'])))
    return dict(
        wing_outer=float(wing[len(wing) // 2, 0]),
        wing_logo_top=float(wing[int(len(wing) * .06), int(len(wing[0]) * .06)]),
        wing_inner=float(wing[len(wing) // 2, -1]),
        plate_top=[int(v) for v in plate[1, len(plate[0]) // 2]],
        plate_body=[int(v) for v in plate[len(plate) // 2, len(plate[0]) // 2]],
        plate_bottom=[int(v) for v in plate[-2, len(plate[0]) // 2]],
        capsule_top=int(capsule[0, len(capsule[0]) // 2].mean()),
        capsule_middle=int(capsule[len(capsule) // 2, len(capsule[0]) // 2].mean()),
        capsule_bottom=int(capsule[-1, len(capsule[0]) // 2].mean()),
        rim_side=float(away_rim[len(away_rim) // 2, 0, 3]),
        rim_side_rgb=[int(v) for v in away_rim[len(away_rim) // 2, 0, :3]],
        rim_top_rgb=[int(v) for v in away_rim[1, len(away_rim[0]) // 8, :3]],
        rim_centre=float(away_rim[len(away_rim) // 2, len(away_rim[0]) // 2, 3]),
    )


def apply(folder=DEFAULT_FOLDER, check=False):
    spec = json.loads((folder / 'layout.json').read_text(encoding='utf-8'))
    with Image.open(folder / 'template.png') as image:
        sheet = image.convert('RGBA')
    logos_before = (LOGOS / 'buf.png').read_bytes()
    buf = buf_mark()

    spec['cells']['capsule'] = {'box': [1398, 12, 1518, 44]}
    sizes = {name: (_box(spec, name)[2] - _box(spec, name)[0], _box(spec, name)[3] - _box(spec, name)[1])
             for name in ('wing', 'home_wing', 'plate', 'capsule', 'away_rim', 'home_rim')}
    spec['cells'].pop('highlight', None)
    spec['static'][:] = [row for row in spec['static'] if row['name'] != 'highlight']
    for name, expected in (('wing', (113, 45)), ('home_wing', (113, 45)), ('plate', (91, 15)),
                           ('capsule', (120, 32)), ('away_rim', (174, 45)), ('home_rim', (174, 45))):
        if sizes[name] != expected:
            raise SystemExit('The %s cell changed size; refusing to re-author (%s)' % (name, sizes[name]))

    import io, subprocess
    base = Image.open(io.BytesIO(subprocess.check_output(
        ['git', 'show', 'HEAD:data/nfl2k5_scorebug_sprite/template.png'], cwd=ROOT))).convert('RGBA')
    body_box = _box(spec, 'body')
    sheet.paste(base.crop(tuple(body_box)), tuple(body_box[:2]))
    for name in [*(f'score_{d}' for d in '0123456789'), *(f'clock_{d}' for d in '0123456789'), 'colon']:
        box = _box(spec, name)
        sheet.paste(base.crop(tuple(box)), tuple(box[:2]))

    wing, _ = wing_cell(sizes['wing'])
    for name in ('wing', 'home_wing'):
        sheet.paste(wing, tuple(_box(spec, name)[:2]))
    sheet.paste(plate_cell(sizes['plate']), tuple(_box(spec, 'plate')[:2]))
    sheet.paste(capsule_cell(sizes['capsule']), tuple(_box(spec, 'capsule')[:2]))
    sheet.paste(rim_cell(sizes['away_rim'], 'away'), tuple(_box(spec, 'away_rim')[:2]))
    sheet.paste(rim_cell(sizes['home_rim'], 'home'), tuple(_box(spec, 'home_rim')[:2]))
    for digit in '0123456789':
        name = 'score_' + digit
        box = _box(spec, name)
        sheet.paste(bevel_score_cell(sheet.crop(tuple(box))), tuple(box[:2]))

    from tools.scorebug_sprite import logo_zoom as lz
    accents_path = folder / 'team_accents.json'
    accents = json.loads(accents_path.read_text(encoding='utf-8')) if accents_path.is_file() else None
    plan = lz.plan(spec)['BUF']
    if plan['after'] != spec['logo_fit']['by_team']['BUF']['zoom']:
        spec['logo_fit']['by_team']['BUF']['zoom'] = plan['after']
        if accents is not None:
            accents['teams']['BUF']['logo_fit']['zoom'] = plan['after']
        previous = spec['provenance'].get('b778_sb2_logo_zoom')
        if previous:
            previous.setdefault('zoom', {})['BUF'] = [plan['before'], plan['after']]
    spec['provenance'][RECORD] = dict(
        job='b778 sb3 2026-10-23',
        request='Noah 10/23: border/glow, deeper team gradient over the logo, down-and-distance gradient',
        wing={k: WING[k] for k in WING},
        plate_rows=PLATE_ROWS,
        plate_source=list(PLATE_SOURCE),
        capsule_source=list(CAPSULE_SOURCE),
        rim=dict(
            cells=['away_rim', 'home_rim'],
            tint='the runtime lightens the wing shade for the rail; the sourced accent rim stays in the table',
            method='white coverage: outer rail glint, top corners and a centre-weighted lower lip; no new quad'),
        buf_zoom=dict(before=spec['provenance'].get('b778_sb2_logo_zoom', {}).get('zoom', {}).get('BUF', [plan['before']])[0],
                      after=plan['after']),
        buf='charging primary buffalo from data/nfl2k5_scorebug_assets/logos/buf.png',
        reference='reports/b72_s9/broadcast_away_median.png, broadcast_home_median.png and '
                  '.b77-scratch/b778/sb2/ref_bars.png (measurement only, no broadcast pixels)')
    note = ('The sb3 rim cells are white coverage; the runtime lifts the wing shade for the rail, and the wing '
            'and plate remain coverage cells the native tints multiply.')
    if note not in spec.get('sampling', ''):
        spec['sampling'] = (spec.get('sampling', '') + ' ' + note).strip()

    from tools.scorebug_sprite import corner_shape as corner
    body = next(row for row in spec['static'] if row['name'] == 'body')
    shape_spec = dict(spec, static=[dict(body, cell='logo')] +
                      [row for row in spec['static'] if row['name'] in ('home_wing', 'body_right')])
    sheet = corner.shape(sheet, shape_spec)
    if not check:
        sheet.save(folder / 'template.png')
        (folder / 'layout.json').write_text(json.dumps(spec, indent=1) + '\n', encoding='utf-8', newline='\n')
        if accents is not None:
            accents_path.write_text(json.dumps(accents, indent=2) + '\n', encoding='utf-8', newline='\n')
        (LOGOS / 'buf.png').write_bytes(_png(buf))
    report = measurements(spec, sheet)
    report['buf_changed'] = _png(buf) != logos_before
    return report, spec


def _png(image):
    import io
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    parser.add_argument('--check', action='store_true', help='measure without writing')
    parser.add_argument('--apply', action='store_true', help='write the cells (the default)')
    args = parser.parse_args(argv)
    report, spec = apply(args.folder, args.check)
    print(json.dumps(report, indent=1))
    if not args.check:
        print('authored', RECORD)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
