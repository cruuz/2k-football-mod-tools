"""The board kit's authored art (st3, job st5 pass 2): the LED ribbons' atlas, repainted into a freed retail slot.

    python3 tools/nfl2k5_board_kit_art.py [--check]

Plain type in the team's colours only (no marks, no sponsors), four rows of 32 pixels in a 128 x 128 atlas, each row
seamless when it repeats along a ribbon (the kit maps one repeat to 128 / 32 x the ribbon's height, so the type keeps
its shape). --check rebuilds every image in memory and compares it with the file.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "data" / "nfl2k5_board_kit" / "art"
FONT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"

#: the Browns' colours (orange, brown, white)
ORANGE, BROWN, WHITE = (255, 60, 0), (49, 29, 0), (255, 255, 255)


def _text_row(text, fg, bg, size, width=128, height=32):
    """One seamless row: the text centred on its background (the row repeats end to end along the ribbon)."""
    row = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(row)
    font = ImageFont.truetype(FONT, size)
    box = draw.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    if w > width - 8:
        raise SystemExit(f"{text!r} is {w} px wide at {size} px; the row holds {width - 8}")
    draw.text(((width - w) / 2 - box[0], (height - h) / 2 - box[1]), text, font=font, fill=fg)
    # two small separators at the row's ends, so the repeats read as one running ribbon
    for x in (2, width - 4):
        draw.rectangle((x, height // 2 - 1, x + 1, height // 2), fill=fg)
    return row


def _stripe_row(width=128, height=32):
    """The sleeve stripes: brown, orange, white, orange, brown bands across the row."""
    row = Image.new("RGB", (width, height), BROWN)
    draw = ImageDraw.Draw(row)
    for y0, y1, colour in ((8, 12, ORANGE), (13, 18, WHITE), (19, 23, ORANGE)):
        draw.rectangle((0, y0, width - 1, y1), fill=colour)
    return row


def cle_ribbons():
    """Cleveland's atlas: BROWNS, DAWG POUND, the stripes, CLEVELAND."""
    atlas = Image.new("RGB", (128, 128), BROWN)
    rows = [_text_row("BROWNS", ORANGE, BROWN, 26), _text_row("DAWG POUND", WHITE, BROWN, 21), _stripe_row(),
            _text_row("CLEVELAND", WHITE, ORANGE, 22)]
    for k, row in enumerate(rows):
        atlas.paste(row, (0, 32 * k))
    return atlas.convert("RGBA")


IMAGES = {"s30_ribbons.png": cle_ribbons}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    ART.mkdir(parents=True, exist_ok=True)
    bad = []
    for name, make in IMAGES.items():
        image = make()
        path = ART / name
        if args.check:
            with Image.open(path) as have:
                if have.convert("RGBA").tobytes() != image.tobytes():
                    bad.append(name)
        else:
            image.save(path, optimize=True)
            print("wrote", path.relative_to(ROOT))
    if bad:
        print("DIFFERS:", ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
