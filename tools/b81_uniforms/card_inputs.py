"""Prepare verified old/new card-material inputs from the release export and the uniform pass receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_relief_2026 as relief
from nfl2k5_playbook_position_recode import OuterImage


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def png(path):
    with Image.open(path) as image:
        return np.array(image.convert('RGBA'), dtype=np.uint8)


def checked(actual, expected, label):
    if actual != expected:
        raise ValueError(f'{label}: expected {expected}, found {actual}')


def prepare(export, compiled, receipts, released_disc, output, retail):
    docs = {
        key: ROOT / 'data' / f'nfl2k5_{key}_2026_b81u.json' for key in ('kit_fixes', 'glyph_fixes', 'relief')
    }
    records = {key: read(path) for key, path in docs.items()}
    by_sel = {}
    for kind, doc in records.items():
        for row in doc.get('textures', doc.get('slots', [])):
            by_sel.setdefault(row['selector'], {}).setdefault(kind, []).append(row)
    native = {row['selector']: row for row in read(export)['sets']}
    cloth = read(receipts / 'kits_receipt.json')
    digits = read(receipts / 'digits_receipt.json')
    rel = records['relief']
    # b81-retail-free-art: the relief ships as differences; the base comes from the retail disc (jersey, sleeve)
    retail_maps = relief.retail_maps(rel, retail)
    if retail_maps is None:
        raise ValueError(f'{retail}: not the retail disc the relief base is pinned to')
    output.mkdir(parents=True, exist_ok=True)
    material_names = (
        'torso',
        'sleeve',
        'pants',
        'digit_jersey_3',
        'digit_jersey_0',
        'digit_arm_3',
        'digit_arm_0',
        'bump_jersey',
        'bump_sleeve',
        'bump_pants',
    )
    report = {
        'schema': 'nfl2k5_uniform_card_inputs/v1',
        'documents': {p.name: sha(p.read_bytes()) for p in docs.values()},
        'source_disc': str(released_disc),
        'source_export_sha256': sha(export.read_bytes()),
        'kits': {},
    }
    with OuterImage(released_disc, writable=False) as archive:
        for sel, changes in sorted(by_sel.items()):
            record = native[sel]
            member = archive.entries[record['outer_index']]
            checked(
                sha(archive.read(member.virtual_offset, member.size)),
                record['resource_sha256'],
                sel + ' released IFF',
            )
            old_assets = {Path(a['png']).stem: a for a in record['assets']}
            materials, old_dir = {}, export.parent / 'uniforms' / sel
            kit_rows = {r['texture']: r for r in changes.get('kit_fixes', [])}
            digit_rows = {r['texture']: r for r in changes.get('glyph_fixes', []) if r['kind'] == 'digit_png'}
            relief_rows = {r['slot']: r for r in changes.get('relief', [])}
            for material in material_names:
                meta = old_assets[material]
                path = old_dir / (material + '.png')
                base = png(path)
                checked(sha(base.tobytes()), meta['rgba_sha256'], sel + ' ' + material + ' original RGBA')
                checked(sha(path.read_bytes()), meta['png_sha256'], sel + ' ' + material + ' original PNG')
                before, after, after_span = meta['rgba_sha256'], path, meta['span_sha256']
                if material in relief_rows:
                    row = relief_rows[material]
                    checked(
                        meta['span_sha256'], row['before_sha256'], sel + ' ' + material + ' original span'
                    )
                    # review F2: a jersey's collar opening comes from the kit's torso as the build holds it
                    torso = png(Path(materials['torso']['new'])) if material == 'bump_jersey' else None
                    rgba = relief.authored_map(rel, row, retail_maps, base, torso)
                    after_hash = sha(rgba.tobytes())
                    checked(after_hash, row['composed_sha256'], sel + ' ' + material + ' relief RGBA')
                    after = output / 'relief' / (after_hash + '.png')
                    after.parent.mkdir(exist_ok=True)
                    if not after.exists():
                        Image.fromarray(rgba, 'RGBA').save(after)
                    checked(sha(png(after).tobytes()), after_hash, str(after))
                    after_span = row['after_sha256']
                else:
                    row = (digit_rows if material.startswith('digit_') else kit_rows).get(meta['name'])
                    after_hash = before
                    if row:
                        result = (
                            digits[sel + '_' + material]
                            if material.startswith('digit_')
                            else cloth[sel + '_' + row['texture']]
                        )
                        checked(
                            meta['span_sha256'], row['before_sha256'], sel + ' ' + material + ' original span'
                        )
                        checked(
                            result['after_sha256'],
                            row['after_sha256'],
                            sel + ' ' + material + ' compiled span',
                        )
                        after = compiled / sel / (material + '.png')
                        after_hash, after_span = result['after_rgba_sha256'], row['after_sha256']
                        checked(
                            sha(png(after).tobytes()), after_hash, sel + ' ' + material + ' compiled RGBA'
                        )
                materials[material] = {
                    'old': str(path),
                    'new': str(after),
                    'old_rgba': before,
                    'new_rgba': after_hash,
                    'old_file': meta['png_sha256'],
                    'new_file': sha(after.read_bytes()),
                    'old_span': meta['span_sha256'],
                    'new_span': after_span,
                }
            report['kits'][sel] = {
                'released_iff_sha256': record['resource_sha256'],
                'materials': materials,
                'change_rows': {k: len(v) for k, v in changes.items()},
                'nameplate_rows': sum(
                    r.get('kind') in ('names_png', 'name_widths') for r in changes.get('glyph_fixes', [])
                ),
            }
    (output / 'inputs.json').write_text(json.dumps(report, indent=1, sort_keys=True) + '\n')
    print(
        f"{len(report['kits'])} kits, {sum(len(k['materials']) for k in report['kits'].values())} checked material pairs"
    )


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('export', 'compiled', 'receipts', 'released-disc', 'output', 'retail'):
        p.add_argument('--' + name, required=True, type=lambda s: Path(s).resolve())
    a = p.parse_args()
    prepare(a.export, a.compiled, a.receipts, a.released_disc, a.output, a.retail)
