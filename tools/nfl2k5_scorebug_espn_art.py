#!/usr/bin/env python3
"""Pixel-coded art for the modern ESPN scorebug (NFL 2K5, local research).

Everything the bar looks like comes from three tiny palettized textures, so the design is
written as code against the exact atlas regions the mesh samples:

  score_buga   64x64  the frame atlas.  Rows 15..37 are the single bar row the layout keeps
                      (cols 1..9 left cap, 10..47 body, 48..63 right cap); rows 0..13 cols 39..63
                      are the box art shared by the drop boxes (down & distance, play clock);
                      rows 0..14 cols 1..38 and rows 38..63 are the collapsed top strip / row 2.
                      Pixel (62,62) is reserved as pure white for the team-colour cells.
  shield_espn  128x64 the ESPN mark in the retail two-row wrap (silhouette and letter mask
                      kept, recoloured flat red / white) so the scorebug, the replay overlay
                      and the presentation overlays all reassemble it correctly.
  digital_font 128x128 4x4 grid of 32x32 cells: 0-9, colon, bolt, and FINAL across row 3.
                      Repainted as a bold sans (shared with other screens: they modernise too).

usage: nfl2k5_scorebug_espn_art.py OUT_DIR [--retail-atlas PNG] [--retail-font PNG] [--retail-espn PNG]
Writes score_buga_modern.png, shield_espn_modern.png, digital_font_modern.png and x8/x4 previews.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CHARCOAL = (22, 22, 26, 255)
CHARCOAL_EDGE = (58, 58, 66, 255)
CHARCOAL_SHADE = (8, 8, 10, 255)
ESPN_RED = (208, 2, 27, 255)
ESPN_RED_DARK = (150, 0, 18, 255)
WHITE = (255, 255, 255, 255)
CELL_SLATE = (52, 54, 66, 255)
CLEAR = (0, 0, 0, 0)
FONT_BOLD = "DejaVuSans-Bold.ttf"
FONT_BOLD_OBLIQUE = "DejaVuSans-BoldOblique.ttf"
# Where DejaVu lives on the platforms the studio runs on.  The digit sheet is drawn with real
# glyphs, so the art is only reproducible where the same face is installed; ``have_text_font``
# lets a caller skip that one atlas instead of silently shipping PIL's bitmap fallback, which
# would look nothing like the published patch.
FONT_DIRECTORIES = (
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/TTF",
    "/usr/local/share/fonts",
    "/opt/homebrew/share/fonts",
    str(Path.home() / ".fonts"),
    str(Path.home() / "Library" / "Fonts"),
    "C:/Windows/Fonts",
)


def font_file(name: str) -> Path | None:
    """The installed DejaVu face ``name``, or ``None``.  Absolute names are honoured as given."""

    candidate = Path(name)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for directory in FONT_DIRECTORIES:
        found = Path(directory) / name
        if found.is_file():
            return found
    return None


def have_text_font() -> bool:
    """Whether the faces the digit sheet is drawn with are installed on this machine."""

    return font_file(FONT_BOLD) is not None


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    found = font_file(path)
    try:
        return ImageFont.truetype(str(found), size) if found is not None else ImageFont.load_default()
    except OSError:
        return ImageFont.load_default()


def atlas(retail: Image.Image) -> Image.Image:
    """Flat charcoal bar, keeping the retail alpha silhouette (rounded caps and box shapes)."""

    src = retail.convert("RGBA")
    out = Image.new("RGBA", src.size, CLEAR)
    sp, op = src.load(), out.load()
    w, h = src.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = sp[x, y]
            if a == 0:
                continue
            lum = (r + g + b) // 3
            if 0 <= y <= 13 and x >= 39:
                # drop-box art: red pill, thin lighter rim on the first opaque row, darker last row
                colour = ESPN_RED
                if y <= 1 or lum > 200:
                    colour = (232, 60, 80, a)
                if y >= 12:
                    colour = ESPN_RED_DARK
                op[x, y] = (colour[0], colour[1], colour[2], a)
            elif 15 <= y <= 37:
                colour = CHARCOAL
                if y == 15:
                    colour = CHARCOAL_EDGE
                elif y == 37:
                    colour = CHARCOAL_SHADE
                elif x <= 2 and lum > 150:
                    colour = CHARCOAL_EDGE
                op[x, y] = (colour[0], colour[1], colour[2], a)
            else:
                op[x, y] = (CHARCOAL[0], CHARCOAL[1], CHARCOAL[2], a)
    # reserved sample block for the team cells: slate, so white text reads on it whether or not
    # the game recolours the palette entry (v2's pure white came through untinted in game)
    for y in (61, 62, 63):
        for x in (61, 62, 63):
            op[x, y] = CELL_SLATE
    return out


def espn_mark(retail: Image.Image | None = None) -> Image.Image:
    """Modern flat ESPN mark in the retail wrap.

    The retail 128x64 ``shield_espn`` stores the logo in two rows (top row: red cap + "ES" on the
    right, bottom row: "PN" + the pill's end on the left) and every consumer -- the scorebug's
    triangle pair, the replay overlay (``i_espn_logo_shader1``) and the presentation overlays
    (``espnLogo1``, the sideline-reporter cut-in among them) -- reassembles it with the same
    slanted geometry.  A fresh rounded rectangle drawn across the whole texture (v2..v5) therefore
    read as a torn logo on those overlays.  v6 keeps the retail alpha silhouette and letter mask:
    the silver pill and its red swoosh become flat ESPN red, the black letters become white, with
    the retail anti-aliasing kept as a blend.  Without the retail image a schematic wrap is drawn.
    """

    if retail is None:
        im = Image.new("RGBA", (128, 64), CLEAR)
        dr = ImageDraw.Draw(im)
        dr.rounded_rectangle([56, 2, 127, 30], radius=8, fill=ESPN_RED)
        dr.rounded_rectangle([0, 34, 76, 62], radius=8, fill=ESPN_RED)
        f = font(FONT_BOLD_OBLIQUE, 22)
        dr.text((78, 3), "ES", fill=WHITE, font=f)
        dr.text((6, 35), "PN", fill=WHITE, font=f)
        return im
    src = retail.convert("RGBA")
    out = Image.new("RGBA", src.size, CLEAR)
    sp, op = src.load(), out.load()
    w, h = src.size

    def neutral(r: int, g: int, b: int) -> bool:
        return abs(r - g) < 40 and abs(g - b) < 40 and abs(r - b) < 40

    # letter mask: neutral dark pixels, closed by one pixel so the retail highlight line inside
    # the glyphs does not leave red streaks through the white letters
    mask = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r, g, b, a = sp[x, y]
            if a and neutral(r, g, b) and (r + g + b) / 3.0 < 115:
                mask[y][x] = 1

    def bridged(m: list[list[int]]) -> list[list[int]]:
        """Fill the retail highlight line: gaps of at most two rows (or one column) between glyph
        pixels become glyph; the letter counters are wider and stay open."""

        res = [row[:] for row in m]
        for y in range(h):
            for x in range(w):
                if m[y][x] or sp[x, y][3] == 0:
                    continue
                up = any(0 <= y - k and m[y - k][x] for k in (1, 2))
                down = any(y + k < h and m[y + k][x] for k in (1, 2))
                left = 0 <= x - 1 and m[y][x - 1]
                right = x + 1 < w and m[y][x + 1]
                if (up and down) or (left and right):
                    res[y][x] = 1
        return res

    closed = bridged(mask)
    for y in range(h):
        for x in range(w):
            r, g, b, a = sp[x, y]
            if a == 0:
                continue
            lum = (r + g + b) / 3.0
            if closed[y][x] and sp[x, y][3] > 0:
                col = WHITE[:3]
            elif neutral(r, g, b):
                # silver pill body -> red; the dark anti-aliased rim of a glyph -> soft white edge
                t = max(0.0, min(1.0, (150.0 - lum) / 70.0))
                col = tuple(int(round(ESPN_RED[i] * (1.0 - t) + WHITE[i] * t)) for i in range(3))
            else:
                # red family (swoosh, shaded rim): flat red, the darkest rim a shade darker
                col = ESPN_RED_DARK[:3] if lum < 70 else ESPN_RED[:3]
            op[x, y] = (col[0], col[1], col[2], a)
    return out


def digits(retail: Image.Image) -> Image.Image:
    """Bold sans digits in the retail 32x32 cells; the bolt cell is copied from retail."""

    src = retail.convert("RGBA")
    im = Image.new("RGBA", (128, 128), CLEAR)
    dr = ImageDraw.Draw(im)
    f = font(FONT_BOLD, 31)
    glyphs = "0123456789:"
    for i, ch in enumerate(glyphs):
        cx, cy = (i % 4) * 32, (i // 4) * 32
        bbox = dr.textbbox((0, 0), ch, font=f)
        gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        dr.text((cx + (32 - gw) / 2 - bbox[0], cy + (32 - gh) / 2 - bbox[1]), ch, fill=WHITE, font=f)
    # bolt (cell 3,2) from retail
    im.paste(src.crop((96, 64, 128, 96)), (96, 64))
    f2 = font(FONT_BOLD, 26)
    text = "FINAL"
    tw = dr.textlength(text, font=f2)
    bbox = dr.textbbox((0, 0), text, font=f2)
    dr.text(((128 - tw) / 2, 96 + (32 - (bbox[3] - bbox[1])) / 2 - bbox[1]), text, fill=WHITE, font=f2)
    return im


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir")
    ap.add_argument("--retail-atlas", default="/tmp/opencode/scorebug/score_buga_retail.png")
    ap.add_argument("--retail-font", default="/tmp/opencode/scorebug/digital_font_retail.png")
    ap.add_argument("--retail-espn", default=str(Path(__file__).resolve().parents[1]
                    / "assets/intermediate/nfl2k5/textures/outer_0346_00b6926c/0026_shield_espn.png"))
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    def preview(im: Image.Image, scale: int, path: Path) -> None:
        big = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        bg = Image.new("RGBA", big.size, (30, 90, 40, 255))
        bg.alpha_composite(big)
        bg.convert("RGB").save(path)

    a = atlas(Image.open(args.retail_atlas))
    a.save(out / "score_buga_modern.png")
    preview(a, 8, out / "score_buga_modern_x8.png")
    e = espn_mark(Image.open(args.retail_espn) if Path(args.retail_espn).exists() else None)
    e.save(out / "shield_espn_modern.png")
    preview(e, 6, out / "shield_espn_modern_x6.png")
    d = digits(Image.open(args.retail_font))
    d.save(out / "digital_font_modern.png")
    preview(d, 4, out / "digital_font_modern_x4.png")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
