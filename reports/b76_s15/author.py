"""Beta 76 s15: author the Franchise record, record tab, possession chevron and used-timeout cells and fields.

Edits ``data/nfl2k5_scorebug_sprite/template.png`` and ``layout.json`` in place and writes
``reports/b76_s15/author_receipts.json``. Idempotent: it owns template rows 64..127, the cells named ``record_*``,
``record_tab``, ``chevron`` and ``timeouts_*``, the glyph sets ``record``, ``record_tab``, ``chevron`` and ``ticks``,
the quarter token ``OT1`` and the fields listed in FIELDS; everything else is left as it is.

    python3 reports/b76_s15/author.py [--folder data/nfl2k5_scorebug_sprite]

Measured inputs come from ``reports/b76_s15/broadcast_marks.json`` (``measure.py``; derived numbers only):
* the record tab's navy and box, and where ESPN puts the record text (2026 MNF Giants at Rams, week 2);
* the chevron's alpha and colour, solved per pixel and area-filtered to 22x7 texels;
* the used-pip grey against the lit pip (dims from the right).

Design decisions made for Noah (brief): digit size 17 (a crisp 5x7 face: one texel is one 16:9 HUD column and one
HUD row, the atlas rule every cell follows), the regular-season record in the playoffs, no FINAL update (the retail
bar is not drawn after the game).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
MARKS = ROOT / 'reports/b76_s15/broadcast_marks.json'
RECEIPTS = ROOT / 'reports/b76_s15/author_receipts.json'
REGION = (0, 64, 1536, 128)     # template rows this script owns (free in the beta 76 template)
TX = 3.0                        # source px per texel horizontally: one HUD column at 16:9 (the atlas rule, all cells)
FACE = 17                       # decided: record digit size 17, a 5x7 face in HUD pixels
TY = FACE / 7                   # source px per texel vertically: 17 px = 7.05 HUD rows
DIGIT_W, DASH_W, GAP = 5, 3, 1  # texels
PAD_OUTER, PAD_INNER = 5.0, 4.0  # px between the tab edge and the text (outer: the bar end side)
TAB_ROWS = (1024, 1047)         # 23 px: equal HUD margins around the 7 text rows (1027 is HUD row 442.0)
TEXT_TOP = 1027
TEXT_BOX = 94                   # px: holds 'W-L-T' up to '10-6-1' (93 px) without the runtime's compression
AWAY_TAB_LEFT, HOME_TAB_RIGHT = 442, 1477
CHEVRON_ANCHORS = (754.5, 1157.75)  # measured chevron centres over the away / home score
CHEVRON_TOP = 943

FONT = {  # 5x7, one-texel strokes; the '1' carries ESPN's foot so every digit fills its cell (tabular)
    '0': ('.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'),
    '1': ('..#..', '.##..', '..#..', '..#..', '..#..', '..#..', '.###.'),
    '2': ('.###.', '#...#', '....#', '...#.', '..#..', '.#...', '#####'),
    '3': ('.###.', '#...#', '....#', '..##.', '....#', '#...#', '.###.'),
    '4': ('...#.', '..##.', '.#.#.', '#..#.', '#####', '...#.', '...#.'),
    '5': ('#####', '#....', '####.', '....#', '....#', '#...#', '.###.'),
    '6': ('..##.', '.#...', '#....', '####.', '#...#', '#...#', '.###.'),
    '7': ('#####', '....#', '...#.', '..#..', '.#...', '.#...', '.#...'),
    '8': ('.###.', '#...#', '#...#', '.###.', '#...#', '#...#', '.###.'),
    '9': ('.###.', '#...#', '#...#', '.####', '....#', '...#.', '.##..'),
    '-': ('...', '...', '...', '###', '...', '...', '...'),
}
NUMBERS = range(0, 18)          # regular season: at most 17 games, so W, L and T are 0..17
FIELDS = ('away_record_tab', 'home_record_tab', 'away_record', 'home_record', 'possession')


def run_width(tokens):
    """Texels of a record run: tokens abut with one gap texel."""
    return sum(tokens) + GAP * (len(tokens) - 1)


def token_texels(token):
    widths = [DASH_W if c == '-' else DIGIT_W for c in token]
    return sum(widths) + GAP * (len(widths) - 1)


def draw_token(token):
    image = Image.new('RGBA', (token_texels(token), 7), (255, 255, 255, 0))
    x = 0
    for c in token:
        rows = FONT[c]
        for y, row in enumerate(rows):
            for dx, bit in enumerate(row):
                if bit == '#':
                    image.putpixel((x + dx, y), (255, 255, 255, 255))
        x += len(rows[0]) + GAP
    return image


def widest_record(length):
    """Texel width of the widest 'W-L' or 'W-L-T' of this many characters (tokens: number, then '-number')."""
    best = 0
    for fields in (2, 3):
        digits = length - (fields - 1)
        for split in range(1 << fields):
            counts = [1 + ((split >> i) & 1) for i in range(fields)]
            if sum(counts) != digits:
                continue
            widths = [token_texels('9' * counts[0])] + [token_texels('-' + '9' * n) for n in counts[1:]]
            best = max(best, run_width(widths))
    return best


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--folder', type=Path, default=FOLDER)
    args = parser.parse_args(argv)
    marks = json.loads(MARKS.read_text(encoding='utf-8'))
    layout_path, template_path = args.folder / 'layout.json', args.folder / 'template.png'
    spec = json.loads(layout_path.read_text(encoding='utf-8'))
    template = Image.open(template_path).convert('RGBA')
    # Own the region: clear it and every cell/set/field this script writes.
    template.paste(Image.new('RGBA', (REGION[2] - REGION[0], REGION[3] - REGION[1]), (0, 0, 0, 0)), REGION[:2])
    for name in [n for n in spec['cells'] if n.startswith(('record_', 'timeouts_')) or n in ('record_tab', 'chevron')]:
        del spec['cells'][name]
    for name in ('record', 'record_tab', 'chevron'):
        spec['glyph_sets'].pop(name, None)
    spec['fields'] = [f for f in spec['fields'] if f['name'] not in FIELDS]
    # The static centre notch stood in for the possession chevron; ESPN has no centre notch.
    spec['static'] = [s for s in spec['static'] if s['name'] != 'pointer']
    spec['cells'].pop('pointer', None)

    cursor = [REGION[0] + 1, REGION[1] + 1]
    receipts = dict(cells={})

    def place(name, image):
        if cursor[0] + image.width + 1 > REGION[2]:
            cursor[0], cursor[1] = REGION[0] + 1, cursor[1] + 12
        x, y = cursor
        if y + image.height > REGION[3]:
            raise SystemExit('the owned template region is full')
        template.paste(image, (x, y))
        spec['cells'][name] = dict(box=[x, y, x + image.width, y + image.height])
        receipts['cells'][name] = spec['cells'][name]['box']
        cursor[0] = x + image.width + 2

    # Record digits: whole numbers and dash-numbers, so any record is at most three quads.
    glyphs = {}
    for n in NUMBERS:
        for token in (str(n), '-' + str(n)):
            cell = 'record_' + ('m' + token[1:] if token[0] == '-' else 'd' + token)
            place(cell, draw_token(token))
            width = token_texels(token) * TX
            glyphs[token] = dict(cell=cell, size=[round(width, 4), FACE], advance=round(width + GAP * TX, 4), raise_=0)
    spec['glyph_sets']['record'] = dict(cap_height=FACE, glyphs={t: {k if k != 'raise_' else 'raise': v for k, v in g.items()}
                                                                for t, g in sorted(glyphs.items(), key=lambda kv: (len(kv[0]), kv[0]))})

    # Record tab: one navy cell drawn at the width of the text (one token per text length, 3..8 characters).
    navy = tuple(int(round(v)) for v in marks['record_tab']['navy_rgb'])
    place('record_tab', Image.new('RGBA', (18, 9), (*navy, 255)))   # no larger than the shortest tab's 16:9 footprint
    tab_height = TAB_ROWS[1] - TAB_ROWS[0]
    tab = {}
    for length in range(3, 9):
        width = min(widest_record(length) * TX, TEXT_BOX) + PAD_OUTER + PAD_INNER
        tab[str(length)] = dict(cell='record_tab', size=[round(width, 4), tab_height], advance=round(width, 4), raise_=0)
    spec['glyph_sets']['record_tab'] = dict(cap_height=tab_height, glyphs={t: {k if k != 'raise_' else 'raise': v for k, v in g.items()}
                                                                          for t, g in tab.items()})

    # Possession chevron: the measured coverage (measure.py) in the measured core colour, one glyph. One colour and
    # 16 coverage levels keep the shared P8 palette for the cells that were already there (134 measured RGBA values
    # re-quantized the plate and label edges); the glow's faint cyan tint is the only thing given up.
    rows = marks['chevron']['cell_rgba']
    core = tuple(int(round(v)) for v in marks['chevron']['core_rgb'])
    chevron = Image.new('RGBA', (len(rows[0]), len(rows)))
    for y, row in enumerate(rows):
        for x, (_r, _g, _b, a) in enumerate(row):
            chevron.putpixel((x, y), (*core, min(255, int(round(a / 17)) * 17)))
    place('chevron', chevron)
    box = marks['chevron']['glyph_box']
    spec['glyph_sets']['chevron'] = dict(cap_height=round(box[3] - box[1], 4), glyphs={'^': dict(
        cell='chevron', size=[round(box[2] - box[0], 4), round(box[3] - box[1], 4)], advance=round(box[2] - box[0], 4), **{'raise': 0})})

    # Timeouts: one pre-composited cell per state, remaining pips lit, used pips grey, dimming from the right.
    tick = spec['cells']['tick']['box']
    pip = template.crop(tick)
    lit, used = marks['timeouts']['lit_rgb'], marks['timeouts']['used_rgb']
    grey = int(round(255 * (sum(used) / 3) / (sum(lit) / 3)))
    step = 10                    # the retail-sized pips: 18 px at 3 px per texel, one every 30 px
    width = 2 * step + pip.width
    ticks = {}
    for remaining in range(4):
        cell = Image.new('RGBA', (width, pip.height), (255, 255, 255, 0))
        for i in range(3):
            shade = 255 if i < remaining else grey
            for y in range(pip.height):
                for x in range(pip.width):
                    a = pip.getpixel((x, y))[3]
                    cell.putpixel((i * step + x, y), (shade, shade, shade, a))
        place('timeouts_' + str(remaining), cell)
        ticks[str(remaining)] = dict(cell='timeouts_' + str(remaining), size=[width * 3, 6], advance=width * 3)
    spec['glyph_sets']['ticks'] = dict(cap_height=6, glyphs=ticks)
    for field in spec['fields']:
        if field['source'] in ('home timeouts', 'away timeouts'):
            field['slots'] = 1
        if field['source'] == 'quarter':
            # The retail quarter formatter prints 'OT%d' in overtime; 'OT1' is ESPN's 'OT'. Every text is one token.
            field['slots'] = 1
    quarter = spec['glyph_sets']['quarter']['glyphs']
    quarter['OT1'] = dict(quarter['OT'])

    # Fields. ESPN draws its logo over the tab, but its record face is 14 px; ours is 17 (decided for legibility) and
    # reaches into marks such as the Giants' 'y' tail, so the tab covers the logo corner and the text sits on navy.
    tab_box_width = TEXT_BOX + PAD_OUTER + PAD_INNER
    text_left = AWAY_TAB_LEFT + PAD_OUTER
    text_right = HOME_TAB_RIGHT - PAD_OUTER
    new = [
        dict(name='away_record_tab', source='away record tab', box=[AWAY_TAB_LEFT, TAB_ROWS[0], AWAY_TAB_LEFT + tab_box_width, TAB_ROWS[1]],
             glyph_set='record_tab', slots=1, material=9, colour='#FFFFFF', alignment='left', anchor=[AWAY_TAB_LEFT, TAB_ROWS[0]],
             size=tab_height, z=-17.5),
        dict(name='home_record_tab', source='home record tab', box=[HOME_TAB_RIGHT - tab_box_width, TAB_ROWS[0], HOME_TAB_RIGHT, TAB_ROWS[1]],
             glyph_set='record_tab', slots=1, material=9, colour='#FFFFFF', alignment='right', anchor=[HOME_TAB_RIGHT, TAB_ROWS[0]],
             size=tab_height, z=-17.5),
        dict(name='away_record', source='away record', box=[text_left, TEXT_TOP, text_left + TEXT_BOX, TEXT_TOP + FACE],
             glyph_set='record', slots=3, material=7, colour='#FFFFFF', alignment='left', anchor=[text_left, TEXT_TOP], size=FACE, z=-15),
        dict(name='home_record', source='home record', box=[text_right - TEXT_BOX, TEXT_TOP, text_right, TEXT_TOP + FACE],
             glyph_set='record', slots=3, material=7, colour='#FFFFFF', alignment='right', anchor=[text_right, TEXT_TOP], size=FACE, z=-15),
        dict(name='possession', source='possession', box=[box[0], box[1], box[2], box[3]], glyph_set='chevron', slots=1, material=4,
             colour='#FFFFFF', alignment='center', anchor=[CHEVRON_ANCHORS[0], CHEVRON_TOP], alt_anchor=[CHEVRON_ANCHORS[1], CHEVRON_TOP],
             size=round(box[3] - box[1], 4), z=-16),
    ]
    spec['fields'].extend(new)
    receipts.update(
        tab_navy=navy, used_pip_grey=grey, used_over_lit=[used, lit],
        tab_widths_px={t: g['size'][0] for t, g in tab.items()},
        record_widths_px={length: round(min(widest_record(length) * TX, TEXT_BOX), 3) for length in range(3, 9)},
        fields=[f['name'] for f in new], chevron_anchors=list(CHEVRON_ANCHORS),
        text=dict(left_away=text_left, right_home=text_right, top=TEXT_TOP, face=FACE, texel_px=[TX, round(TY, 4)]))
    template.save(template_path)
    layout_path.write_text(json.dumps(spec, indent=1) + '\n', encoding='utf-8', newline='\n')
    RECEIPTS.write_text(json.dumps(receipts, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(layout_path)
    print(template_path)


if __name__ == '__main__':
    raise SystemExit(main())
