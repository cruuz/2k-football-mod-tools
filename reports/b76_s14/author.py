"""Targeted b76-s14 art revision: broadcast display shades on the wings and legible marks for every team.

Builds on reports/b76_s12/author.py (cells replaced inside the current template at their existing boxes, never
a regenerated sheet), so the atlas stays 256 by 512, all 91 cells keep their sizes, all 47 quads keep their count
and the appended payload keeps its size. It always starts from the s12 bytes at ``--base`` (git) and applies only
the selected steps, so any subset can be re-authored and measured on its own. A file no step touches is written
back byte for byte. It never runs tools/scorebug_sprite/author_default.py or the s10 author.

Steps (the default runs all three; reports/b76_s14/AUTHOR_STEPS.json holds every measured trial):

wingcell  The shared wing coverage cell is s12's three-term field (reports/b76_s12/author.py wing_cell) with the
          top-glow amplitude re-measured for the broadcast display shades: 0.60 to 0.45. With the brighter
          shades the s12 glow drew colour along the top rows well past where the broadcast shows it.
display   The scorebug-only display layer: every NFL team's wing (and the wash, which mirrors it) becomes its
          broadcast display shade from data/nfl2k5_scorebug_sprite/broadcast_display.json, written by
          reports/b76_s14/fit_display.py: measured on air for NYG, LAR, DEN, KC, LV and HOU, fitted from the
          sourced colour for the other 26. Each team records the class, the source, the official parent and the
          sourced accent it replaces. The rim and plate keep their sourced accents (measured, see the report).
marks     Marks that stay illegible on their own new wing are recoloured on their existing silhouettes (fills and
          keylines only, never a redrawn letterform), with ESPN's treatment where a 2026-package broadcast shows it
          and the team's cited on-dark colourway otherwise. The table is MARKS below.

Run order when the evidence or the wing cell changes: ``author.py --steps wingcell``, then fit_display.py, then
``author.py``. No broadcast pixel is copied: cells are synthesized from measured numbers, marks are recoloured.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE = '30db13952'
SPRITE = 'data/nfl2k5_scorebug_sprite'
LOGOS = 'data/nfl2k5_scorebug_mnf/logos'
STEPS = ('wingcell', 'display', 'marks')
ACCEPTED = STEPS
sys.path[:0] = [str(ROOT)]
from mod_editor.core import nfl2k5_scorebug_teams as teams  # noqa: E402


def _s12_author():
    spec = importlib.util.spec_from_file_location('b76_s12_author', ROOT / 'reports/b76_s12/author.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S12 = _s12_author()
# The s12 field with only the top-glow amplitude changed (AUTHOR_STEPS.json: 0.35 to 0.60 measured).
WING = dict(S12.WING, a2=0.45)
# The marks under the legibility threshold whose cited on-dark colourway differs from the primary mark
# (reports/b76_s14/mark_legibility_before.json; sources and the threshold are in the report). Every colour is
# an official colour of the team in team_colors_official_2026.json. No 2026-package ESPN broadcast shows these.
MARKS = {
    'nyj': dict(team='NYJ', fill='#FFFFFF',
                treatment='white mark on the team green',
                sources=['https://a.espncdn.com/i/teamlogos/nfl/500-dark/nyj.png (ESPN on-dark logo: white)',
                         'https://www.youtube.com/channel/UCROj9vBjc4ZW3AL4cd_BjHg (New York Jets channel mark: '
                         'white on green)']),
    'dal': dict(team='DAL', keyline='#FFFFFF', keyline_texels=1,
                treatment='white outer keyline around the unchanged navy border, white stripe and navy star',
                sources=['https://a.espncdn.com/i/teamlogos/nfl/500-dark/dal.png (ESPN on-dark logo: white outer '
                         'keyline)',
                         'https://www.youtube.com/channel/UCC0BPKJxAyxjQoRTYbpW0FQ (Dallas Cowboys channel mark: '
                         'white outer keyline on navy)']),
    'ind': dict(team='IND', map=[['#013369', '#A5ACAF'], ['#FFFFFF', '#013369']], keyline='#A5ACAF',
                keyline_texels=2,
                treatment='Facemask Gray horseshoe, Speed Blue grommets, no white outline',
                sources=['https://www.youtube.com/channel/UCyYn26HPC4HIedifGnNbjBw (Indianapolis Colts channel '
                         'mark: gray horseshoe, dark grommets, on black)',
                         'https://www.colts.com/team/brand/ (Speed Blue #013369, Facemask Gray #A5ACAF, '
                         'Pantone 429 C)']),
    'no': dict(team='NO', keyline='#FFFFFF', keyline_texels=1,
               treatment='white outer keyline outside the black border, gold fleur unchanged',
               sources=['https://www.youtube.com/channel/UCwuddf1JrodMlc5fYpVlrQA (New Orleans Saints channel mark: '
                        'gold, black border, white outer keyline, on black)']),
    'jax': dict(team='JAX', keyline='#FFFFFF', keyline_texels=1,
                treatment='light outer keyline outside the black outline (the channel mark draws it cream, about '
                          '#E8E0C8; the official White trim is used, the mark\'s own light fur colour)',
                sources=['https://www.youtube.com/channel/UCsGacW6z0GedR-Wv45SBRZg (Jacksonville Jaguars channel '
                         'mark: light outer keyline around the black outline, on black)']),
}


def git_bytes(rel, base=BASE):
    return subprocess.check_output(['git', 'show', base + ':' + rel], cwd=ROOT)


def encode_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _morph(field, texels, op):
    for _ in range(texels):
        padded = np.pad(field, 1)
        field = op([padded[dy:dy + field.shape[0], dx:dx + field.shape[1]] for dy in range(3) for dx in range(3)],
                   axis=0)
    return field


def recolour(image, spec):
    """Recolour one mark on its own silhouette; alpha is never changed.

    The interior colour of every texel is its source colour, unless ``fill`` replaces it with one colour or
    ``map`` moves each texel to the target of its nearest listed source colour (OKLab), which keeps every region
    (a grommet, a stripe) where the source drew it. ``keyline`` then colours the silhouette's boundary band, the
    ``keyline_texels`` a 3 by 3 erosion removes (s12's inside keyline), composited exactly as
    reports/b76_s12/author.py recolour_mark does, so the mark's outer silhouette stays the source silhouette.
    Faint texels (alpha below 16, the runtime's own Lanczos cut) are left out of the keyline shape.
    """
    a = np.asarray(image.convert('RGBA')).astype(np.float64)
    rgb = a[..., :3].copy()
    if 'fill' in spec:
        rgb[:] = np.array(teams.rgb(spec['fill']), dtype=np.float64)
    if 'map' in spec:
        sources = np.array([teams.oklab(teams.rgb(src)) for src, _dst in spec['map']])
        targets = np.array([teams.rgb(dst) for _src, dst in spec['map']], dtype=np.float64)
        lab = np.array([teams.oklab(px) for px in rgb.reshape(-1, 3)]).reshape(rgb.shape)
        nearest = np.linalg.norm(lab[..., None, :] - sources[None, None], axis=-1).argmin(-1)
        rgb = targets[nearest]
    if 'keyline' not in spec:
        out = np.dstack([rgb, a[..., 3]])
        return Image.fromarray(np.clip(np.rint(out), 0, 255).astype('uint8'), 'RGBA')
    alpha = a[..., 3] / 255.0
    clean = np.where(a[..., 3] < 16, 0.0, alpha)
    top = _morph(clean, spec.get('keyline_texels', 1), np.min)
    under = clean
    key = np.array(teams.rgb(spec['keyline']), dtype=np.float64)
    out_alpha = top + under * (1 - top)
    premult = rgb * top[..., None] + key[None, None] * (under * (1 - top))[..., None]
    straight = np.where(out_alpha[..., None] > 0, premult / np.maximum(out_alpha[..., None], 1e-9), key)
    # The colour is the keyline composite; the alpha stays the source alpha texel for texel.
    out = np.dstack([straight, a[..., 3]])
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype('uint8'), 'RGBA')


def author(steps, base=BASE):
    rel_files = [SPRITE + '/template.png', SPRITE + '/layout.json', SPRITE + '/team_accents.json']
    raw = {rel: git_bytes(rel, base) for rel in rel_files}
    logo_rels = {key: LOGOS + '/' + key + '.png' for key in MARKS}
    raw.update({rel: git_bytes(rel, base) for rel in logo_rels.values()})
    spec = json.loads(raw[SPRITE + '/layout.json'])
    accents = json.loads(raw[SPRITE + '/team_accents.json'])
    sheet = Image.open(io.BytesIO(raw[SPRITE + '/template.png'])).convert('RGBA')
    receipts = dict(base=base, steps=list(steps))
    changed = set()
    outputs = {}

    if 'wingcell' in steps:
        box = spec['cells']['wing']['box']
        cell = S12.wing_cell((box[2] - box[0], box[3] - box[1]), WING)
        for name in ('wing', 'home_wing'):
            b = tuple(spec['cells'][name]['box'])
            if cell.size != (b[2] - b[0], b[3] - b[1]):
                raise ValueError('The wing cell must keep its size')
            sheet.paste(cell, b[:2])
        prov = spec['provenance']
        prov['wing_model'] = dict(prov['wing_model'], a2=WING['a2'])
        receipts['wingcell'] = dict(previous_a2=S12.WING['a2'], a2=WING['a2'])
        changed.update({'template', 'layout'})

    if 'display' in steps:
        display = teams.load_display(ROOT / SPRITE)
        if display is None:
            raise SystemExit('Run reports/b76_s14/fit_display.py first: broadcast_display.json is missing')
        receipts['display'] = {}
        for name, team in accents['teams'].items():
            if team['slot'] >= 32:
                continue
            sourced = team['wing']
            parent = next(c for c in team['official'] if sourced in teams.variants([c]))
            source = 'measured' if name in display.get('measured', {}) else 'fitted'
            layer = dict(**{'class': 'broadcast'}, source=source, parent=parent, sourced=sourced)
            team['display'] = layer
            shade = teams.display_shade(name, team, display)
            team['wing'] = team['wash'] = shade
            team['candidates']['broadcast_display'] = dict(
                hex=shade, parent=parent, variant='broadcast_' + source,
                contrast_white=round(teams.contrast_white(shade), 4),
                facts=dict(role='wing and wash only', label='no label is drawn over the wing'))
            receipts['display'][name] = dict(source=source, parent=parent, sourced=sourced, shade=shade)
        accents['display_layer'] = dict(
            file=DISPLAY_NOTE, roles=list(teams.DISPLAY_ROLES),
            rule='Wing and wash carry the broadcast display shade; rim and plate keep the sourced accents.')
        changed.add('accents')

    if 'marks' in steps and MARKS:
        receipts['marks'] = {}
        for key, mark in sorted(MARKS.items()):
            before = Image.open(io.BytesIO(raw[logo_rels[key]])).convert('RGBA')
            after = recolour(before, mark)
            if list(np.asarray(after)[..., 3].ravel()) != list(np.asarray(before)[..., 3].ravel()) \
                    and mark.get('keyline_mode', 'inside') == 'inside':
                raise ValueError('An inside recolour must keep the alpha: ' + key)
            outputs[logo_rels[key]] = encode_png(after)
            receipts['marks'][key] = dict({k: v for k, v in mark.items()},
                                          ink_before=int((np.asarray(before)[..., 3] > 0).sum()),
                                          ink_after=int((np.asarray(after)[..., 3] > 0).sum()))

    if steps:
        prov = spec['provenance']
        prov.update(author='reports/b76_s14/author.py', revision='b76-s14',
                    fidelity_report='reports/b76_s14/AUTHOR_STEPS.json',
                    geometry_steps=list(dict.fromkeys(list(prov.get('geometry_steps', [])) + list(steps))),
                    display_layer='data/nfl2k5_scorebug_sprite/broadcast_display.json (wing and wash)',
                    base_author='reports/b76_s12/author.py (cells replaced in place, not regenerated)')
        changed.add('layout')
    outputs[SPRITE + '/template.png'] = encode_png(sheet) if 'template' in changed else raw[SPRITE + '/template.png']
    outputs[SPRITE + '/layout.json'] = ((json.dumps(spec, indent=1) + '\n').encode('utf-8')
                                        if 'layout' in changed else raw[SPRITE + '/layout.json'])
    outputs[SPRITE + '/team_accents.json'] = ((json.dumps(accents, indent=2) + '\n').encode('utf-8')
                                              if 'accents' in changed else raw[SPRITE + '/team_accents.json'])
    for rel in logo_rels.values():
        outputs.setdefault(rel, raw[rel])
    receipts['outputs'] = {rel: dict(sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                                     changed=data != raw[rel]) for rel, data in outputs.items()}
    return outputs, receipts


DISPLAY_NOTE = 'broadcast_display.json'


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--steps', default=','.join(ACCEPTED), help='Comma list from: ' + ', '.join(STEPS))
    p.add_argument('--base', default=BASE)
    p.add_argument('--receipts', type=Path, default=OUT / 'author_receipts.json')
    a = p.parse_args(argv)
    steps = [s for s in STEPS if s in [x for x in a.steps.split(',') if x]]
    unknown = [s for s in a.steps.split(',') if s and s not in STEPS]
    if unknown:
        raise SystemExit('Unknown step(s): ' + ', '.join(unknown))
    outputs, receipts = author(steps, a.base)
    for rel, data in outputs.items():
        (ROOT / rel).write_bytes(data)
    receipts['wing'] = WING
    a.receipts.write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf-8', newline='\n')
    # The result must pass the palette validator as shipped.
    teams.load()
    print('Authored steps:', steps or 'none (base bytes restored)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
