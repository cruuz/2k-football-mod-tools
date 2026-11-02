"""b780 p2-playcall: the ball spot's words and digits for the 2026 bar (idempotent authoring step).

The play-call screen shows the ball spot after the down and distance ("1st & 10  NYJ 35"). The retail "Ball on"
formatter (0xFBEB0) prints "Ball on\\nNYJ 35"; the sprite engine appends its second line to the down text. Those
characters need glyph cells the atlas never had: the label set held digits, ordinals and the words GOAL and INCHES.

The scene has no spare quads. Every atlas material is full (44 of 44 quads: scores, clocks, records, plates), so the down
field keeps its 8 quads and the spot must fit the ones its text leaves unused: the down text draws at most five glyphs
("1st & 10" is 1, st, &, 1, 0 once the spaces cost nothing), which leaves three. So a team's abbreviation is ONE cell (a
word, like GOAL) and the yard line is two digits: three quads for "NYJ 35".

This step adds, to the label glyph set:
  * one word cell for each of the 36 abbreviations the game's own data uses (retail, 2026 and classic names), drawn small:
    20 px caps against the down text's 24 px (8 texel rows). The tokens are U+0001 followed by the abbreviation, so they can
    never match inside the down text ("STL" is not the ordinals "ST" and "L"). An abbreviation with no cell (a created team
    with its own letters) simply shows no spot.
  * ten digit cells, the same size, from the traced broadcast masks of the label digits (so the yard line matches the "10"
    beside it). Their tokens are U+0010..U+0019 (the plain digits stay the down text's own cells).
  * a narrow space, U+001A.

Source of the letters: the glyph outlines of Roboto Condensed Bold (Apache License 2.0), the face the beta 71 down label
was rasterised from (data/nfl2k5_scorebug_mnf/painted_label_2x.json, reports/b71_s4/raster_label.py). The 2026 broadcast
masks the other label cells were traced from have no B, F, J, K, M, P, U, V, W, Y or Z, and team abbreviations use every
letter, so one face draws all of them. The font is needed only to run this authoring step, never on the player's machine;
the cells it makes are plain pixels in template.png.

Each cell is cropped to its ink and filtered to a whole number of texels with the same rule as the other label cells (the
width never exceeds the footprint: 1/3 texel per layout pixel across, 448/1080 down; coverage ** 0.8 as sbfix), and given
design metrics on the label grid (cap height 30 units; the field scales them by 24/30).

Usage: python3 reports/b780_p2/author_ball_spot.py [--check] [--font PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
RECEIPTS = Path(__file__).with_name('author_receipts.json')
DEFAULT_FONT = '/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf'
TRACED = ROOT / 'reports/b72_s9'    # the broadcast-traced label digit masks
FX, FY = 1 / 3, 448 / 1080          # texels per layout px (16:9 after the 27/32 contraction; the 448-line viewport)
FIELD_SIZE, GRID_CAP = 24, 30       # the down field's size and the label set's design cap height
SPOT_CAP_PX = 20                    # layout px of a spot capital (the down text is 24)
SPOT_ROWS = 8                       # texel rows of that cap: int(20 * 448/1080 + 0.02)
SCALE = FIELD_SIZE / GRID_CAP       # layout px per design unit in the down field (0.8)
GAP = 2.4                           # design units after every spot glyph (the digits keep 2.0 at their larger size)
SPACE = 9.0                         # design units of the narrow spot space (the label space is 11)
TRACKING_PX = 1.6                   # layout px added between the letters of a word (bold capitals read better apart)
SUPER = 16                          # supersamples per texel row
CAP_SAMPLES = SPOT_ROWS * SUPER     # rows of a flat capital in the supersampled render
FONT_PX = round(CAP_SAMPLES / 0.7109375)   # Roboto's cap height is 1456/2048 em
# Every abbreviation the game's own data prints (data/nfl2k5_team_names_2026.json retail and 2026 names, the classic and
# historic team profiles): 36 words. tests/mod_editor/test_nfl2k5_scorebug_ball_spot.py checks the data against this list.
ABBREVIATIONS = ('ARI', 'ARZ', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX',
                 'KC', 'LAC', 'LAR', 'LV', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'OAK', 'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL',
                 'TB', 'TEN', 'WAS')
DIGITS = '0123456789'
WORD_MARK = chr(1)                  # U+0001 + abbreviation = the word token (at most four units)
DIGIT_BASE = 16                     # the spot's digits are U+0010..U+0019 (never U+0020, the label space)
SPACE_TOKEN = chr(26)
ORIGIN = (2, 110)                   # free rows 103..299 of template.png (nothing else is drawn there)
PITCH = 2                           # blank texels between placed cells


def word_token(abbreviation):
    return WORD_MARK + abbreviation


def digit_token(digit):
    return chr(DIGIT_BASE + int(digit))


def cell_name(item):
    return 'spot_' + item


def texels(px, per):
    """Largest whole texel count that never exceeds the footprint (one mip, no minification)."""
    return max(1, int(px * per + 0.02))


def _render(font, word):
    """White-on-black coverage of one word at SUPER samples per texel row, cropped to its ink (float 0..1).

    Drawn letter by letter so the tracking is exact; every letter sits on one baseline.
    """
    canvas = Image.new('L', (FONT_PX * 4 * max(1, len(word)), FONT_PX * 2), 0)
    draw = ImageDraw.Draw(canvas)
    x = FONT_PX // 2
    track = TRACKING_PX * CAP_SAMPLES / SPOT_CAP_PX
    for ch in word:
        draw.text((x, FONT_PX // 4), ch, font=font, fill=255)
        x += font.getlength(ch) + track
    return np.asarray(canvas.crop(canvas.getbbox())).astype(float) / 255


def _cell(alpha, size):
    """Area-filter white coverage to ``size`` texels (box filter on coverage), then the 0.8 coverage exponent."""
    a = Image.fromarray(np.clip(np.rint(alpha * 255), 0, 255).astype(np.uint8), 'L').resize(size, Image.Resampling.BOX)
    cov = (np.asarray(a).astype(float) / 255) ** 0.8
    out = np.dstack([np.full(cov.shape + (3,), 255.0), cov * 255])
    return Image.fromarray(np.rint(out).astype(np.uint8), 'RGBA')


def _traced(digit):
    """The label digit's traced broadcast mask (88 rows at 4x), as coverage 0..1."""
    rows = json.loads((TRACED / 'harvest.json').read_text(encoding='utf-8'))['glyphs']
    return np.asarray(Image.open(TRACED / 'glyphs' / rows['label_' + digit]['file']).convert('L')).astype(float) / 255


def glyphs(font_path):
    """{item: dict(ink_px, cell, design_w)}: a word cell per abbreviation and a digit cell per digit, 8 texel rows tall."""
    font = ImageFont.truetype(str(font_path), FONT_PX)
    body = _render(font, 'O').shape[0]                    # round capitals overshoot the flat cap by about 3 %
    out = {}
    for item in ABBREVIATIONS + tuple(DIGITS):
        if item in DIGITS:
            mask = _traced(item)
            ink_px = mask.shape[1] * SPOT_CAP_PX / mask.shape[0]       # the digit's own aspect at the 20 px cap
        else:
            mask = _render(font, item)
            if mask.shape[0] > body * 1.04:               # a stray descender: keep the capitals' body
                mask = mask[:body]
            ink_px = mask.shape[1] * SPOT_CAP_PX / CAP_SAMPLES    # layout px at the 20 px spot cap
        width = texels(ink_px, FX)
        out[item] = dict(ink_px=ink_px, cell=_cell(mask, (width, SPOT_ROWS)), design_w=round(ink_px / SCALE, 3))
    return out


def build(layout, template, font_path=DEFAULT_FONT):
    """Return the new (layout, template, receipts); the inputs are not modified."""
    layout = json.loads(json.dumps(layout))
    image = template.copy()
    made = glyphs(font_path)
    items = ABBREVIATIONS + tuple(DIGITS)
    names = {cell_name(i) for i in items}
    # A pass that authored different cells (an older word list) leaves nothing behind: clear and drop every spot_ cell first.
    for name in [n for n in layout['cells'] if n.startswith('spot_')]:
        ob = layout['cells'].pop(name)['box']
        image.paste(Image.new('RGBA', (ob[2] - ob[0], ob[3] - ob[1]), (0, 0, 0, 0)), tuple(ob[:2]))
    label = layout['glyph_sets']['label']['glyphs']
    for token in [t for t, g in label.items() if g['cell'].startswith('spot_') or t == SPACE_TOKEN]:
        del label[token]
    others = [tuple(v['box']) for n, v in layout['cells'].items() if n not in names]

    def overlaps(box):
        return any(max(box[0], b[0]) < min(box[2], b[2]) and max(box[1], b[1]) < min(box[3], b[3]) for b in others)
    x, y = ORIGIN
    receipts = {}
    for item in items:
        cell = made[item]['cell']
        if x + cell.width > 1536:
            x, y = ORIGIN[0], y + SPOT_ROWS + PITCH
        box = [x, y, x + cell.width, y + cell.height]
        assert not overlaps(box), item
        image.paste(cell, (x, y))
        layout['cells'][cell_name(item)] = {'box': box}
        others.append(tuple(box))
        x += cell.width + PITCH
        receipts[item] = dict(ink_px=round(made[item]['ink_px'], 3), texels=list(cell.size), cell=box,
                              design_w=made[item]['design_w'], sha256=hashlib.sha256(cell.tobytes()).hexdigest())
    height, raise_ = SPOT_CAP_PX / SCALE, -(GRID_CAP - SPOT_CAP_PX / SCALE)
    for item in items:
        w = made[item]['design_w']
        token = digit_token(item) if item in DIGITS else word_token(item)
        label[token] = {'cell': cell_name(item), 'size': [w, round(height, 3)], 'advance': round(w + GAP, 3),
                        'raise': round(raise_, 3)}
    label[SPACE_TOKEN] = {'cell': 'tick', 'size': [0, 0], 'advance': SPACE}
    for field in layout['fields']:
        if field['name'] == 'down':
            # The plate's vertical sides are 246 apart; the box is the room the text may use before the field squeezes
            # it: 232 leaves 7 px at each side (the widest down text, "3rd & Inches", needs 207, so no existing line
            # changes). Same centre, 961.
            field['box'] = [845, field['box'][1], 1077, field['box'][3]]
    layout['provenance']['b780_p2_ball_spot'] = {
        'job': 'b780 p2-playcall 2026-11-02',
        'request': 'nwostar 10/24 (#2k5-ideas): "Add down distance and field position to play call screen." '
                   'The 2026 bar showed the down and distance only.',
        'method': 'words: glyph outlines of Roboto Condensed Bold (Apache License 2.0), one cell per team abbreviation; '
                  'digits: the traced broadcast label digit masks (reports/b72_s9/glyphs). Rasterised at 16x the target rows, '
                  'cropped to ink, box-filtered to whole texels (width never above the 1/3 texel per layout px footprint), '
                  'coverage ** 0.8; design metrics on the label grid, cap 25 against the down text\'s 30',
        'font_sha256': hashlib.sha256(Path(font_path).read_bytes()).hexdigest(),
        'tokens': 'word = U+0001 + abbreviation, digit d = U+0010 + d, narrow space = U+001A',
        'abbreviations': list(ABBREVIATIONS),
        'cap_px': SPOT_CAP_PX, 'rows': SPOT_ROWS, 'gap_design': GAP, 'space_design': SPACE, 'tracking_px': TRACKING_PX,
        'cells': {cell_name(i): receipts[i]['cell'] for i in items},
        'author': 'reports/b780_p2/author_ball_spot.py'}
    return layout, image, receipts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='Rebuild in memory and report whether the folder matches; write nothing')
    ap.add_argument('--font', default=DEFAULT_FONT)
    a = ap.parse_args(argv)
    layout = json.loads((FOLDER / 'layout.json').read_text(encoding='utf-8'))
    template = Image.open(FOLDER / 'template.png').convert('RGBA')
    new_layout, new_image, receipts = build(layout, template, a.font)
    same = new_layout == layout and new_image.tobytes() == template.tobytes()
    if a.check:
        print(json.dumps(dict(current=same), indent=1))
        return 0 if same else 1
    new_image.save(FOLDER / 'template.png')
    (FOLDER / 'layout.json').write_text(json.dumps(new_layout, indent=1) + '\n', encoding='utf-8', newline='\n')
    RECEIPTS.write_text(json.dumps(receipts, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({c: receipts[c]['texels'] for c in receipts}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
