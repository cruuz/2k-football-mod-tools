#!/usr/bin/env python3
"""Render PRIVATE SPECIAL evidence from retail FONT/ROST and bounded XBE draws.

No emulator, display, audio, network, game-file writes or GPU are used. This
research tool imports the unittest draw harness; it is not a shipped runtime
module. The panel frame is an illustration; cell text is the native callback
output and glyphs come from the user's own FONT resource.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/mod_editor'), str(ROOT / 'tools')]

from test_nfl2k5_depth_chart_rows import DrawProbe, before_special, legacy, rows
from mod_editor.core import nfl2k5_roster_records as rr
from nfl_outer import parse_archive, read_entry_bytes
from nfl_txtr import parse_chunks, decode_chunk
from nfl_scene_probe import record_from_header
from nfl_main_menu_font import parse_font, rgba_from_font


def render(result, font, target, label):
    from PIL import Image, ImageDraw, ImageFont
    canvas = Image.new('RGBA', (640, 480), '#080d22')
    draw = ImageDraw.Draw(canvas)
    ui_font = ImageFont.load_default()
    atlas = Image.frombytes('RGBA', (font.width, font.height), rgba_from_font(font))
    glyphs = {chr(g.codepoint): g for g in font.glyphs}
    def text(at, value):
        x, y = at
        for ch in value:
            glyph = glyphs.get(ch)
            if glyph is None:
                x += font.space_advance
                continue
            u0, v0, u1, v1 = glyph.uv
            crop = atlas.crop(tuple(round(v) for v in
                                    (u0 * font.width, v0 * font.height, u1 * font.width, v1 * font.height)))
            canvas.alpha_composite(crop, (round(x + glyph.left), round(y + glyph.top)))
            x += glyph.advance
    draw.text((17, 13), 'DATA PREVIEW | ' + label + ' | EXPERIMENTAL / UNWITNESSED', font=ui_font, fill='white')
    draw.text((17, 32), 'Retail SF roster, retail font3, native cell text and visibility', font=ui_font, fill='#b1bad0')
    draw.rectangle((15, 56, 625, 75), fill='#737a85')
    draw.text((22, 60), 'DEPTH CHART / SPECIAL', font=ui_font, fill='white')
    draw.rectangle((15, 80, 615, 440), outline='#b5bdcb', width=2)
    draw.rectangle((16, 81, 614, 106), fill='#424853')
    for x, caption in ((65, '1ST TEAM'), (265, '2ND TEAM'), (465, '3RD TEAM')):
        draw.text((x, 88), caption, font=ui_font, fill='white')
    layout = result['layout']
    pitch = result['row_pitch']
    scroll = layout['scroll_row']
    selected = result['row_count'] - 1
    selected_y = layout['top'] + (selected - scroll) * pitch
    draw.rectangle((layout['left'], selected_y, layout['right'], selected_y + pitch - 1), fill='#172766')
    for cell in result['drawn']:
        x = layout['left'] + sum(result['column_widths'][:cell['column']]) + 3
        y = layout['top'] + (cell['row'] - scroll) * pitch
        text((x, y), cell['text'])
    if layout['vertical_scroll']:
        draw.rectangle((600, 110, 610, 433), fill='#7e8186', outline='#dddddd')
        draw.rectangle((601, 397, 609, 430), fill='#be2148')
    if layout['horizontal_scroll']:
        draw.rectangle((158, 435, 595, 445), fill='#7e8186', outline='#dddddd')
        draw.rectangle((160, 436, 195, 444), fill='#be2148')
    draw.text((17, 458), f"{layout['visible_rows']} rows / {layout['visible_columns']} cells per row / pitch {pitch:g}",
              font=ui_font, fill='#b1bad0')
    canvas.convert('RGB').resize((960, 720), Image.Resampling.NEAREST).save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--xbe', type=Path, default=legacy.XBE)
    parser.add_argument('--index', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.scratch')
    args = parser.parse_args()
    index = args.index or args.xbe.parent / 'vc_53450030/0'
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    archive = parse_archive(index)
    resource = read_entry_bytes(archive, archive.entries[3], max_size=3_000_000)
    chunks = parse_chunks(resource)
    font_data, _ = decode_chunk(resource, chunks[2])
    font_hash = hashlib.sha256(font_data).hexdigest()
    if font_hash != '330765bb8482457120520cdb9d354a91d6e615f2ae75c9fa93b4542a3882282c':
        raise ValueError('foreign font3')
    font = parse_font(2, 'font3', record_from_header(archive, 3, 2, chunks[2].offset, 'retail', None),
                      font_data, font_hash)
    document = rr.load_image(index.parent)
    team = next(t for t in document.teams if t.abbreviation == 'SF')
    players = document.team_players(team.index)
    player_rows = [(p.record.values['position'], p.record.values['depth_rank'], p.record.values['depth_side'])
                   for p in players]
    names = [(p.record.values['jersey'], p.first, p.last) for p in players]
    returners = [document.body[team.offset + off] for off in (0x195, 0x196, 0x199)]
    retail = args.xbe.read_bytes()
    patched, receipt = rows.apply(legacy.prepare(retail))
    probe = DrawProbe()
    results = {}
    for key, payload in (('before', before_special(patched)), ('after', patched)):
        result = probe.run_draw(payload, selected=12, names=names, player_rows=player_rows, returners=returners)
        target = output / f'special_tab_{key}.png'
        render(result, font, target, key.upper())
        results[key] = {**result, 'png': target.name, 'png_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'xbe_sha256': hashlib.sha256(payload).hexdigest()}
    report = {'evidence': 'bounded native draw; GPU submission intercepted; frame illustrated',
              'retail_xbe_sha256': hashlib.sha256(retail).hexdigest(), 'font3_sha256': font_hash,
              'roster_body_sha256': hashlib.sha256(document.original).hexdigest(), 'team': team.display,
              'roster_fields': 'identity, position, rank/side and returner indices; normal availability fixture',
              'apply_receipt': receipt, **results}
    (output / 'special_tab_preview.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for key, result in results.items():
        print(key, json.dumps(result['layout']), output / result['png'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
