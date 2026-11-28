#!/usr/bin/env python3
"""Compile the card PNGs with Studio's normal importer, record source and disc pins, and write a separate working project."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from tools.b81_uniforms import apply_cards, cards_unif
from mod_editor.core import nfl2k5_menu_helmet_w2026 as slots
from nfl2k5_playbook_position_recode import OuterImage
import nfl_team_select_card_png_import as importer


def read(path):
    return Path(path).read_text(encoding='utf-8')


def compile_one(job):
    name, source, input_file_sha, expected, index, inventory, folder = job
    if apply_cards.sha(source.read_bytes()) != input_file_sha:
        raise ValueError(f'{name}: authored source file pin differs')
    _, code, style, _ = name.split('_')
    blob, _, receipt = importer.build_import(
        index, inventory, 'unif', code[1:], {'h': 'home', 'a': 'away'}[code[0]], int(style), 256, source
    )
    if receipt['replacement']['rgba_sha256'] != expected or receipt['input_png']['sha256'] != input_file_sha:
        raise ValueError(f'{name}: Studio compiled a different set of RGBA pixels or read another source')
    path = folder / (name + '.txtr.bin')
    temp = path.with_suffix('.tmp')
    temp.write_bytes(blob)
    temp.replace(path)
    return name, receipt['replacement']['span_sha256'], len(blob)


def build(project, payload, reviewed_disc, reviewed_receipt, index, inventory, workers):
    authored = json.loads(read(payload / 'card_receipt.json'))
    if apply_cards.sha(project.read_bytes()) != authored['project_sha256']:
        raise ValueError('Uniform cards were authored from a different working project')
    reviewed = json.loads(read(reviewed_receipt))
    paths = cards_unif.project_cards(project, project.parent)
    changed = {row['selector'] for row in authored['cards'].values()}
    if set(paths) != changed | set(authored['unchanged_kits']) or changed & set(authored['unchanged_kits']):
        raise ValueError('The input inventory does not account for every reviewed project card')
    folder = payload / 'native'
    folder.mkdir(exist_ok=True)
    jobs, rows = [], {}
    for sel, src in sorted(paths.items()):
        name = cards_unif.card_name(sel)
        approved = reviewed[name]
        row = authored['cards'].get(name, {})
        source = apply_cards.sha(cards_unif.rgba(src).tobytes())
        source_native = approved['stored_rgba_sha256']
        if (
            source != approved['new_rgba_sha256']
            or source != row.get('source_rgba_sha256', source)
            or source_native != row.get('source_native_sha256', source_native)
        ):
            raise ValueError(f'{name}: wrong source image or reviewed native card')
        rows[name] = dict(
            selector=sel,
            file=row.get('file'),
            source_rgba_sha256=source,
            source_file_sha256=apply_cards.sha(src.read_bytes()),
            source_native_sha256=source_native,
            master_rgba_sha256=row.get('master_rgba_sha256', source),
            new_rgba_sha256=row.get('new_rgba_sha256', source),
            new_file_sha256=row.get('new_file_sha256'),
            stored_rgba_sha256=row.get('stored_rgba_sha256', source_native),
            changed_pixels=row.get('changed_pixels', 0),
            replacement_sha256=None,
            replacement_size=0,
        )
        if row.get('file'):
            jobs.append(
                (
                    name,
                    payload / 'assets/files' / row['file'],
                    row['new_file_sha256'],
                    row['stored_rgba_sha256'],
                    index,
                    inventory,
                    folder,
                )
            )
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, (name, digest, size) in enumerate(pool.map(compile_one, jobs), 1):
            rows[name].update(replacement_sha256=digest, replacement_size=size)
            if i % 20 == 0 or i == len(jobs):
                print(f'Normal Studio imports {i}/{len(jobs)}', flush=True)
    with OuterImage(reviewed_disc, writable=False) as archive:
        plan, _ = apply_cards.plan_archive(archive, payload, rows)
        if len(plan) != len(jobs):
            raise ValueError('The reviewed disc must be the unmodified input for every authored card')
        for name, _, old, new in plan:
            rows[name].update(reviewed_slot_sha256=apply_cards.sha(old), new_slot_sha256=apply_cards.sha(new))
        for name, row in rows.items():
            if not row['file']:
                _, slot = slots.locate(archive, 'logos', name.removesuffix('_256'))
                row.update(reviewed_slot_sha256=apply_cards.sha(slot), new_slot_sha256=apply_cards.sha(slot))
    return dict(
        schema='nfl2k5_b81_uniform_card_outputs/v1',
        about='The standard 128 MB uniform pass. Each checked name has the incoming project PNG and Xbox colors, the truecolor edit master, the source-pack import PNG, and the native Studio import span. Private artwork belongs in the pack.',
        cards=rows,
    )


def write_project(project, payload, output, pins):
    if output.resolve().is_relative_to(project.parent.resolve()):
        raise ValueError('Choose a separate destination outside the reviewed source')
    source = json.loads(read(project))
    original_cards = cards_unif.project_cards(project, project.parent)
    if set(pins) != {cards_unif.card_name(sel) for sel in original_cards}:
        raise ValueError('The complete input project card set differs')
    checked = set()
    for edit in source['edits']:
        if (edit.get('kind'), edit.get('family'), edit.get('resolution')) == ('team_select', 'unif', 256):
            sel = edit['asset_code'] + {'home': 'H', 'away': 'A'}[edit['side']] + str(int(edit['style']))
            name = cards_unif.card_name(sel)
            row = pins[name]
            path = original_cards[sel]
            if (
                apply_cards.sha(path.read_bytes()) != row['source_file_sha256']
                or apply_cards.sha(cards_unif.rgba(path).tobytes()) != row['source_rgba_sha256']
            ):
                raise ValueError(f'{name}: expected the reviewed source card')
            if row['file']:
                new = (payload / 'assets/files' / row['file']).resolve(strict=True)
                if (
                    apply_cards.sha(new.read_bytes()) != row['new_file_sha256']
                    or apply_cards.sha(cards_unif.rgba(new).tobytes()) != row['new_rgba_sha256']
                ):
                    raise ValueError(f'{name}: private payload PNG differs')
                edit['png'] = str(new)
            checked.add(name)
        for key in ('png', 'clean_png'):
            if key in edit and not Path(edit[key]).is_absolute():
                edit[key] = str((project.parent / edit[key]).resolve(strict=True))
    if checked != set(pins):
        raise ValueError('Project is missing a uniform card')
    text = json.dumps(source, indent=2, sort_keys=True) + '\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and read(output) != text:
        raise FileExistsError(f'An unrelated project already exists at {output}')
    if not output.exists():
        with output.open('x', encoding='utf-8', newline='\n') as f:
            f.write(text)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        'project',
        'payload',
        'reviewed-disc',
        'reviewed-card-receipt',
        'retail-index',
        'inventory',
        'write-pins',
        'working-project',
    ):
        p.add_argument('--' + key, required=True, type=lambda s: Path(s).resolve())
    p.add_argument('--workers', type=int, choices=range(1, 9), default=3)
    a = p.parse_args()
    if a.payload.is_relative_to(a.project.parent) or a.write_pins.is_relative_to(a.project.parent):
        raise ValueError('Outputs must be outside the reviewed source')
    result = build(
        a.project, a.payload, a.reviewed_disc, a.reviewed_card_receipt, a.retail_index, a.inventory, a.workers
    )
    write_project(a.project, a.payload, a.working_project, result['cards'])
    a.write_pins.write_text(
        json.dumps(result, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n'
    )
