#!/usr/bin/env python3
"""Job f5 report art: the Player Card honors page as the game's own draw calls place it. Not a screenshot.

Runs the honors owner's real code under Unicorn (the retail executable with the owner installed, the card year base
set to 2026) for one player whose career-stat stream carries his sourced honors, captures every text call (string,
font slot, alignment, position) and draws the strings at those positions on a plain 640x480 card-coloured canvas, next
to the retail rating/bio rows for comparison. Fonts are a stand-in (DejaVu Sans): widths and glyphs differ in game.

  python3 tools/b77/f5_render.py --player "Patrick Mahomes" --out f5_honors_page.png
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_honors_history as hh  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import XBE, Machine, _retail, word  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def capture(first: str, last: str, years_pro: int, season_year: int = 2026):
    data = hh.load()
    player = next(p for p in data["players"] if p["first"] == first and p["last"] == last)
    retail = _retail()
    if retail is None:
        raise SystemExit(f"the pinned retail executable is required ({XBE})")
    payload, _ = honors.apply(retail)
    state = honors.allocations(payload)["data"]["va"]
    payload = bytearray(payload)
    struct.pack_into("<I", payload, 0x3204AD - 0x10000, season_year + 11)   # the 2026 year patch's card year base
    m = Machine(bytes(payload))
    words = [word(0, s, 16) for s in range(years_pro)]
    for h in player["honors"]:
        slot = years_pro - (season_year - h["season"])
        if 0 <= slot < years_pro:
            words.append(word(hh.FIELDS[h["honor"]], slot, 1))
    rec = m.roster([(years_pro, words)])[0]
    m.put(0xC90248, rec)
    m.put(0xE576B8, 0)
    for va in (0x3208E0, 0x320500, 0x320760, 0x320640, 0x35B9C0):
        m.record(va, hex(va))
    m.capture_text()
    m.put(state, 1)
    m.call(0x320B70)
    return player, list(m.text)


def render(player, text, out: Path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (1280, 520), (32, 32, 36))
    draw = ImageDraw.Draw(img)
    big = ImageFont.truetype(FONT, 15)
    small = ImageFont.truetype(FONT, 13)
    for panel, x0, title in ((0, 0, "RETAIL PAGE (rating and bio rows, retail labels)"), (1, 640, "HONORS PAGE (captured draw calls)")):
        draw.rectangle([x0 + 150, 80, x0 + 610, 400], fill=(205, 207, 210))
        draw.rectangle([x0 + 162, 195, x0 + 590, 312], fill=(185, 188, 192))
        draw.text((x0 + 170, 200), "season stats table (unchanged)", fill=(90, 90, 90), font=small)
        draw.text((x0 + 300, 92), f"{player['first']} {player['last']}  (header unchanged)", fill=(16, 16, 16), font=big)
        draw.text((x0 + 10, 20), title, fill=(230, 230, 230), font=big)
    retail_rows = [("SPEED", "90"), ("AGILITY", "88"), ("STRENGTH", "70"), ("AWARENESS", "99"), ("THROW POWER", "97"),
                   ("THROW ACCURACY", "95"), ("ELUSIVENESS", "80"), ("CARRYING", "70"), ("STAMINA", "90"), ("INJURY", "85")]
    for i, (label, value) in enumerate(retail_rows):
        x = (310, 490)[i // 5]
        y = (318, 333, 347, 362, 377)[i % 5]
        w = draw.textlength(label, font=small)
        draw.text((x - 8 - w, y - 8), label, fill=(16, 16, 16), font=small)
        draw.text((x, y - 8), value, fill=(16, 16, 16), font=small)
    for i, (label, value) in enumerate((("HT:", "6-2"), ("WT:", "225"), ("DOB:", "9/17/1995"), ("COLLEGE:", "Texas Tech"),
                                        ("YRS PRO:", "9"))):
        x, y = ((198, 137), (198, 154), (198, 171), (320, 137), (320, 154))[i]
        w = draw.textlength(label, font=small)
        draw.text((x, y - 8), label, fill=(16, 16, 16), font=small)
        draw.text((x + w + 8, y - 8), value, fill=(16, 16, 16), font=small)
    for string, font, align, colour, pos in text:
        x, y, _size = pos
        w = draw.textlength(string, font=small)
        x = x - w if align == 2 else x
        draw.text((640 + x, y - 8), string, fill=(16, 16, 16), font=small)
    draw.text((10, 430), "Layout from the game's own text calls (positions, alignment, font slots 3 and 8) run under Unicorn; "
                         "glyphs drawn with a stand-in font, so widths differ in game.", fill=(200, 200, 200), font=small)
    draw.text((10, 450), "Retail rows show example values. Not a screenshot; nothing here was seen in xemu.",
              fill=(200, 200, 200), font=small)
    img.save(out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--player", default="Patrick Mahomes")
    parser.add_argument("--years-pro", type=int, default=9)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    first, last = args.player.split(" ", 1)
    player, text = capture(first, last, args.years_pro)
    render(player, text, args.out)
    for row in text:
        print(row[0], "| font", row[1], "| align", row[2], "| at", tuple(round(v, 1) for v in row[4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
