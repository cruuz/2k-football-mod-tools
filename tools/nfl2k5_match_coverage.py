#!/usr/bin/env python3
"""Reproduce the offline match census, play-art gallery and experimental pack."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
for entry in (ROOT, ROOT / 'tools'):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_match_coverage as match
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_codec as codec
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')


def image_name(team, play, formation):
    return f'{team}-p{play:03d}-f{formation:02d}.png'


def render_play(book, body, play_index, formation_index, path, *, team, note=''):
    """The Studio FieldScene and codec art on QImage; never opens a window.

    Cyan arrows are our explicit explanatory overlay between paired defenders,
    not native route art. Both phases remain drawn by the original renderer.
    """
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt5.QtCore import QPointF, QRectF, Qt
    from PyQt5.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.play_designer_qt import FieldScene, to_scene
    app = QApplication.instance() or QApplication([])
    scene = FieldScene(offense=False)
    form = lib.formation_record(body, formation_index)
    positions = [(s.x[0], s.z[0]) for s in form.slots]
    labels = [codec.position_label(c) for c in
              lib.category_positions(body, lib.formation_category(body, formation_index))]
    chains = lib.exact_play_chains(body, play_index)
    analysis = match.analyze_chains(chains)
    # Native coverage is a menu component, so include a compatible front and
    # name it. Never display the four inactive placeholders as actual defenders.
    fronts = [f for f, c in lib.defense_pairs(book, body, formation_index) if c == play_index]
    if not fronts:
        raise ValueError(f'{team} p{play_index} f{formation_index}: no legal preview front')
    front = min(fronts, key=lambda f: (book.plays[f].name not in ('Base', 'Base Odd'), f))
    effective = lib.effective_defense(lib.exact_play_chains(body, front), chains)
    active = lib.defense_active(chains)
    scene.set_tokens(positions, [f'{s} {p}' for s, p in enumerate(labels)], False, lambda _: None, lambda _: None)
    for slot, chain in enumerate(effective):
        nodes = codec.encode_chain(chain)
        scene.draw_art(codec.play_art(nodes, positions[slot], side=1 if positions[slot][0] >= 0 else -1),
                       QColor('#ffde69') if slot in active else QColor('#cbd5e1'))
    import math
    for pair in analysis['pairs']:
        m, z = pair['man_slot'], pair['zone_slot']
        a, b = to_scene(*positions[m]), to_scene(*positions[z])
        pen = QPen(QColor('#67e8f9'), 2.5, Qt.DashLine)
        line = scene.addLine(a.x(), a.y(), b.x(), b.y(), pen)
        line.setZValue(5)
        angle = math.atan2(b.y() - a.y(), b.x() - a.x())
        scene.addPolygon(QPolygonF([b,
            QPointF(b.x() - 12 * math.cos(angle - .5), b.y() - 12 * math.sin(angle - .5)),
            QPointF(b.x() - 12 * math.cos(angle + .5), b.y() - 12 * math.sin(angle + .5))]),
            pen, QBrush(QColor('#67e8f9'))).setZValue(5)
        scene.tokens[m].setBrush(QBrush(QColor('#ffb454')))
        scene.tokens[z].setBrush(QBrush(QColor('#67e8f9')))
    img = QImage(1280, 940, QImage.Format_ARGB32)
    img.fill(QColor('#101b2b'))
    painter = QPainter(img)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    def text(rect, value, size=12, color='#e2e8f0', bold=False):
        painter.setPen(QColor(color))
        painter.setFont(QFont('DejaVu Sans', size, QFont.Bold if bold else QFont.Normal))
        painter.drawText(QRectF(*rect), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignTop, value)
    text((24, 18, 1230, 45), f'{team}  |  {book.formations[formation_index].name}  |  {book.plays[play_index].name}', 21, bold=True)
    text((24, 68, 1230, 45), f'Play {play_index}, formation {formation_index}; preview front: {book.plays[front].name} (play {front})', 12)
    scene.render(painter, QRectF(20, 118, 865, 680), QRectF(-450, -500, 940, 700))
    text((22, 815, 860, 90), 'Yellow: coverage assignments   Gray: compatible front\n'
         'Orange: man first   Cyan: zone first and handoff arrows\n'
         'Both assignment phases shown. Cyan links are explanatory annotations.', 11)
    detail = match._formation_row(book, body, book.formations[formation_index], analysis)
    y = 120
    if detail['pairs']:
        height = 570 / len(detail['pairs'])
        for pair in detail['pairs']:
            text((907, y, 347, height - 12), pair['description'], 11)
            y += height
    elif detail['warnings']:
        text((907, y, 347, 570), '\n\n'.join(detail['warnings']), 11, '#fbbf24')
    else:
        text((907, y, 347, 300), 'No explicit exchange. This authored robber call uses five man assignments, '
             'one deep safety and a shallow middle zone with native receiver pickup.', 12)
    if note:
        text((907, 700, 347, 205), note, 10, '#fbbf24')
    text((24, 913, 1230, 23), 'OFFLINE STUDIO ART | EXPERIMENTAL / UNWITNESSED | Not a gameplay capture', 10, '#94a3b8')
    painter.end()
    if not img.save(str(path), 'PNG'):
        raise ValueError(f'Could not save {path}')
    scene.clear()
    del scene
    # Keep the application alive until every Qt-owned object has been released.
    del app
    return dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                width=img.width(), height=img.height(), front=front)


def census_markdown(document):
    t = document['totals']
    lines = ['# Retail match-coverage census', '',
        f"All {t['books']} books, {t['plays']:,} plays and {t['defensive_plays']:,} defensive plays decoded. "
        f"{t['matched_plays']} play records have explicit exchanges across {t['matched_menu_entries']} formation menus. "
        f"Reciprocal plays: {t['reciprocal_plays']}; plays with unpaired rules: {t['unresolved']}; "
        f"unclassified plays: {t['unclassified_plays']}; defensive 0x1A nodes: {t['predicate_nodes']}.", '',
        'PROVED refers to bytes and static consumers. These are offscreen Studio diagrams, '
        'with all linked formations shown. Cyan handoff arrows are annotations. '
        'They are not gameplay captures. All slots and indices are zero-based.', '',
        '| Book | Formation | Play | Defenders and rule | Art |', '| --- | --- | --- | --- | --- |']
    for book in document['books']:
        if not book['matches']:
            lines.append(f"| {book['book']} | All | No explicit exchange | Ordinary man and zone are excluded. | |")
        for play in book['matches']:
            for f in play['formations']:
                src = f.get('image', {}).get('file')
                art = f'[![{book["book"]} {play["name"]}]({src})]({src})' if src else 'Render with --render'
                text = '<br><br>'.join([p['description'] for p in f['pairs']] + f['warnings'])
                lines.append(f"| {book['book']} | {f['name']} (f{f['index']}) | {play['name']} (p{play['play']}) | {text} | {art} |")
    return '\n'.join(lines) + '\n'


def export_census(image, output, *, render=False):
    result = match.census(image)
    output.mkdir(parents=True, exist_ok=True)
    if render:
        with OuterImage(image) as archive:
            for row in result['books']:
                raw = archive.read_entry(BOOK_ENTRIES[row['book']])
                book = inspector.parse_playbook_resource(raw, asset_id='book:' + row['book'])
                for play in row['matches']:
                    for f in play['formations']:
                        f['image'] = render_play(book, raw[32:], play['play'], f['index'],
                            output / image_name(row['book'], play['play'], f['index']), team=row['book'])
    write_json(output / 'census.json', result)
    (output / 'census.md').write_text(census_markdown(result), encoding='utf-8')
    with (output / 'census.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('book', 'formation_index', 'formation', 'play_index', 'play', 'man_slot',
                         'man_position', 'zone_slot', 'zone_position', 'boundary', 'rule', 'image'))
        for b in result['books']:
            for p in b['matches']:
                for f in p['formations']:
                    for pair in f['pairs']:
                        writer.writerow((b['book'], f['index'], f['name'], p['play'], p['name'],
                            pair['man_slot'], pair['man_position'], pair['zone_slot'], pair['zone_position'],
                            pair['boundary'], pair['description'], f.get('image', {}).get('file', '')))
                    for warning in f['warnings']:
                        writer.writerow((b['book'], f['index'], f['name'], p['play'], p['name'],
                            '', '', '', '', '', warning, f.get('image', {}).get('file', '')))
    return result


def evidence(xbe, corpus):
    """Pin complete native function bytes and available decompiler blocks.

    This checks identity, not execution; the tiny constants are independently
    decoded from the XBE. Retail code and decompiler text are never exported.
    """
    from mod_editor.core.nfl2k5_bump_strength import _sections
    from mod_editor.core.nfl2k5_play_rules import reference
    import struct
    with xbe.open('rb') as stream:
        payload = stream.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024 or hashlib.sha256(payload).hexdigest() != reference()['retail_xbe_sha256']:
        raise ValueError('Evidence requires the pinned retail XBE')
    sections = _sections(payload)
    def read(va, size):
        s = next(s for s in sections if s.virtual_address <= va and va + size <= s.virtual_address + s.raw_size)
        offset = s.raw_offset + va - s.virtual_address
        return payload[offset:offset + size]
    ranges = {0x19FA10: 0x19FC55, 0x1A2E70: 0x1A2F7D, 0x1A5090: 0x1A578E,
              0x1A5BC0: 0x1A621C, 0x1A6220: 0x1A66E1, 0x1A05B0: 0x1A05EC}
    functions = {f'0x{start:08x}': dict(end_exclusive=f'0x{end:08x}',
        native_sha256=hashlib.sha256(read(start, end - start)).hexdigest()) for start, end in ranges.items()}
    for path in sorted((corpus / 'pseudo_c').glob('*.c')):
        text = path.read_text(encoding='utf-8')
        blocks = list(re.finditer(r'/\*\n \* index:.*?\n \* address: (0x[0-9A-Fa-f]+)', text))
        for i, block in enumerate(blocks):
            key = f'0x{int(block[1], 16):08x}'
            if key in functions:
                end = blocks[i + 1].start() if i + 1 < len(blocks) else len(text)
                functions[key].update(corpus_path=str(path.relative_to(corpus)),
                    line=text.count('\n', 0, block.start()) + 1,
                    corpus_sha256=hashlib.sha256(text[block.start():end].encode()).hexdigest())
    if any('corpus_sha256' not in f for f in functions.values()):
        raise ValueError('A required native consumer is missing from the corpus')
    boundary = list(struct.unpack('<16I', read(0x50A4C8, 64)))
    if boundary != list(range(16)):
        raise ValueError('Boundary table differs from the audited identity mapping')
    return dict(schema='nfl2k5_match_coverage_evidence/v1', evidence=match.EVIDENCE,
        proof_scope='Static native dataflow and exact byte identity; no native execution or gameplay witness',
        retail_xbe_sha256=hashlib.sha256(payload).hexdigest(), functions=functions,
        boundary_table=dict(address='0x0050a4c8', values=boundary,
                            sha256=hashlib.sha256(read(0x50A4C8, 64)).hexdigest()),
        lookahead_seconds=struct.unpack('<f', read(0x4E6C58, 4))[0],
        depth_threshold_cm=struct.unpack('<f', read(0x4F689C, 4))[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('census', 'pack'):
        p = sub.add_parser(name)
        p.add_argument('--image', required=True, type=Path, help='Read-only extracted tree or XISO')
        p.add_argument('--output', required=True, type=Path)
        p.add_argument('--render', action='store_true', help='Offscreen Studio PNGs')
        if name == 'pack':
            p.add_argument('--team', default='BAL', choices=tuple(BOOK_ENTRIES))
    p = sub.add_parser('evidence')
    p.add_argument('--xbe', required=True, type=Path)
    p.add_argument('--corpus', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == 'evidence':
        result = evidence(args.xbe, args.corpus)
        write_json(args.output, result)
    elif args.command == 'census':
        result = export_census(args.image, args.output, render=args.render)
        print(json.dumps(result['totals'], sort_keys=True))
        return int(result['totals']['unclassified_plays'] != 0)
    else:
        with OuterImage(args.image) as archive:
            raw = archive.read_entry(BOOK_ENTRIES[args.team])
        book = inspector.parse_playbook_resource(raw, asset_id='book:' + args.team)
        pack = match.match_coverage_pack(book, raw[32:], args.team)
        check = packs.check_pack(pack, resource=raw)
        if not check.ok:
            parser.error(check.text())
        compiled = packs.apply_pack_to_resource(raw, pack)
        packs.save_pack(pack, args.output)
        result = dict(schema='nfl2k5_match_coverage_pack_receipt/v1', team=args.team,
            evidence=match.EVIDENCE, check=check.to_json(), compiler=compiled.report,
            source_sha256=hashlib.sha256(raw).hexdigest(), replacement_sha256=compiled.replacement_sha256)
        if args.render:
            images = args.output.parent / 'match_coverage_art'
            images.mkdir(exist_ok=True)
            result['images'] = []
            for i, p in enumerate(pack.plays):
                fi = next(f.index for f in book.formations if f.name == p.defense_formation)
                pi = p.replace_index if p.replace_index is not None else len(book.plays) + i
                result['images'].append(render_play(compiled.parsed_replacement, compiled.replacement[32:],
                    pi, fi, images / f'sd-match-{i:02d}.png', team=args.team, note=match.RECIPE_LIMITS[i]))
        write_json(args.output.with_suffix('.receipt.json'), result)
    print(json.dumps({k: v for k, v in result.items() if k in ('schema', 'team', 'evidence')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
