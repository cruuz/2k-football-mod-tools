"""Author the league-wide 2026 field-level sponsor sheet for the 2026 venue art (data/nfl2k5_modern_venues_2026/league/).

The retail ``banner_corp`` texture (256x256, eleven cloth banners hung at field level) is byte-identical in every
home venue and carries 2004 sponsors. Riddell, Gatorade and NFL.com stay (their NFL.com shield takes the current mark
through the league marks). The eight other cloths become plain type, no logos (main, 2026-09-24):

  ESPN VIDEOGAMES -> ESPN            (ESPN carries Monday Night Football)
  VISUAL CONCEPTS -> NFL+            (the league's streaming service)
  TEAM NFL        -> PLAY 60         (the league's youth fitness campaign)
  PLAY FOOTBALL   -> NFL FLAG        (the league's youth flag football)
  COACHES ASSN    -> SUPER BOWL LXI  (the 2026 season's championship, 2027-02-14, SoFi Stadium;
                                      https://en.wikipedia.org/wiki/Super_Bowl_LXI)
  PLAYERS INC x2  -> NFLPA           (the players' association)
  SEGA            -> NFL NETWORK

Each cloth is drawn at 4x, shaded by the retail cloth's own folds (a heavily blurred luminance, so no retail
lettering survives) and cut by the retail cloth outline, then reduced to the retail size; pixels outside the
eight cells are left clear (the writer replaces only the ``RECTS``). Input: the user's own retail dry-day export of
any venue (``<prefix>dd_stadium_t*_banner_corp.png``). Run by the author; the PNG ships in the reviewed catalog.

    python3 tools/nfl2k5_modern_venues_2026_art.py --retail-export DIR [--masters DIR]

It also authors one venue's name fix (st2, 2026-09-28): the Buccaneers' s27 stadium texture lambert12 (a cloth
hung on Buccaneer Cove's ship) reads TAMPA BAY STADIUM, the name of the building the stadium replaced in 1998.
Its top cloth becomes RAYMOND JAMES STADIUM in plain type, shaded by the retail cloth's own folds and cut by
its outline; every other pixel stays clear, so the venue table's overlay extra (venues.json, s27) paints only
that cloth. Input: the user's own retail dry-day lambert12 export (64 x 64).

    python3 tools/nfl2k5_modern_venues_2026_art.py --tb-ship-banner RETAIL_LAMBERT12_PNG [--masters DIR]

And Washington's defunct 2004 sponsor cells (st2, 2026-09-28; main's call under u4's league sponsor policy,
U4_MODERN_VENUES section 10d): u4's s29 art keeps them in banner01 (the club-level fascia ring, 97.5 % of it drawn)
and exit01 (the header over every exit tunnel). MOTOROLA becomes NFL NETWORK, Reebok PLAY 60 and ESPN VIDEOGAMES
ESPN, in u4's type panels (NFL NETWORK white on navy; PLAY 60 navy and ESPN red on the panel's own light colour, the
median of the retail cell's lightest 40 %), Roboto Black, no marks. Only the cells in the table's rects are drawn;
every other pixel is clear, and the table lays these extras under u4's own banner01 slots.

    python3 tools/nfl2k5_modern_venues_2026_art.py --was-sponsor-cells RETAIL_EXPORT_DIR [--masters DIR]

And Tampa Bay's sideline fascia name (st2, 2026-09-28; the SN stale-name audit): s27's lambert63 draws two rows,
TAMPA B and AY STADIUM, which the scene lays end to end along both sideline fascias (x +-88, y 19.6 to 21.2: the
first row from u 0 to 126.7 px, the second from u 11.1 to 137.8 px, wrapping). One line of RAYMOND JAMES STADIUM is
drawn along that 253-pixel run and cut back into the two rows, in plain condensed type in the sign's own blue (the
median of the rows' most saturated tenth) on its own background (the median of their lightest 40 %). The rest of
the texture (the 2004 league marks, which the scene does not draw) stays clear.

    python3 tools/nfl2k5_modern_venues_2026_art.py --tb-fascia-name RETAIL_LAMBERT63_PNG [--masters DIR]

And Pittsburgh's scoreboard marks (st2, 2026-09-28; main's call): d2's board art for s22 draws the Acrisure A mark
and three Nike swooshes where the retail had HEINZ FIELD and Reebok. Over the team's art, the name block becomes
ACRISURE over STADIUM in plain white type on black, and each swoosh cell a PLAY 60 type panel (u4's, navy on the
cell's own light colour); the two ad_bb01 column cells are drawn turned a quarter clockwise, as the retail Reebok
there reads, since the scene lays that column along the scoreboard's lower-left panel.

    python3 tools/nfl2k5_modern_venues_2026_art.py --pit-cells RETAIL_EXPORT_DIR [--masters DIR]

And Kansas City's ad01 (st2, 2026-09-28): the team folder's own ad01 item keeps Modern Arrowhead's fallback off, so
the retail sponsors around u4's two slots stay; the defunct ones become u4's type panels (ESPN, NFL NETWORK, NFLPA,
NFL+), each cell only where u4's slots leave it in view.

    python3 tools/nfl2k5_modern_venues_2026_art.py --kc-cells RETAIL_EXPORT_DIR [--masters DIR]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nfl2k5_modern_venues_2026" / "league" / "banner_corp.png"
TB_SHIP_OUT = ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / "s27_lambert12.png"
WAS_OUT = {"banner01": ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / "s29_banner01.png",
           "exit01": ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / "s29_exit01.png"}
#: Washington's defunct cells, by the table's rects (nfl2k5_modern_venues_2026.WAS_BANNER01_RECTS, WAS_EXIT01_RECTS):
#: (text, text colour, panel colour: an RGB or "light", the median of the retail cell's lightest 40 %)
WAS_CELLS = {
    "banner01": {(1, 49, 125, 74): ("ESPN", "espn"), (128, 49, 255, 74): ("ESPN", "espn"),          # ESPN VIDEOGAMES
                 (129, 96, 206, 124): ("PLAY 60", "play60"),                                         # Reebok
                 (129, 126, 192, 141): ("ESPN", "espn"), (192, 126, 255, 141): ("ESPN", "espn"),   # ESPN VIDEOGAMES
                 (1, 160, 99, 179): ("NFL NETWORK", "net"), (100, 160, 198, 179): ("NFL NETWORK", "net"),  # MOTOROLA
                 (1, 180, 130, 203): ("NFL NETWORK", "net"),                                          # MOTOROLA
                 (129, 233, 188, 256): ("PLAY 60", "play60")},                                        # Reebok
    "exit01": {(0, 0, 64, 13): ("NFL NETWORK", "net")},                                              # MOTOROLA
}
#: u4's type panels (U4 supplement's LEAGUE_SPONSOR_RECIPES): (text colour, panel colour)
WAS_STYLE = {"net": ((255, 255, 255), (1, 51, 105)), "play60": ((1, 51, 105), "light"), "espn": ((204, 0, 0), "light")}
#: the dark-panel ESPN (u4's _espn(bg="dark")) and Seattle's message board (its own yellow on black, medians of the
#: retail message)
PANEL_STYLE = dict(WAS_STYLE, espn_dark=((204, 0, 0), "dark"), message=((220, 205, 34), (11, 11, 11)),
                   nflpa=((1, 51, 105), (242, 242, 238)), plus=((255, 255, 255), (1, 51, 105)))
TB_FASCIA_OUT = ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / "s27_lambert63.png"
#: s27 lambert63's two rows (the table's rects, nfl2k5_modern_venues_2026.TB_LAMBERT63_RECTS) and where the scene's
#: run of the name starts in each (u px): row one from 0 for 126.7 px, row two from 11.1 for 126.7 px (wrapping)
TB_FASCIA_ROWS = (((0, 2, 128, 19), 0.0), ((0, 23, 128, 40), 11.1))
TB_FASCIA_RUN = 126.7
TB_FASCIA_TEXT = "RAYMOND JAMES STADIUM"
SEA_OUT = {key: ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / f"s26_{key}.png"
           for key in ("lambert69", "lambert70", "lambert73", "lambert74")}
#: Seattle's defunct cells, by the table's rects (nfl2k5_modern_venues_2026.SEA_*_RECTS)
SEA_CELLS = {
    "lambert70": {(0, 2, 128, 24): ("NFL NETWORK", "net"),                  # MOTOROLA (the tower's panels)
                  (0, 104, 128, 126): ("ESPN", "espn")},                     # ESPN VIDEOGAMES
    "lambert69": {(0, 0, 64, 39): ("NFL+", "message")},                      # the Visual Concepts welcome
    "lambert74": {(0, 0, 64, 32): ("PLAY 60", "play60"),                     # Reebok
                  (0, 32, 64, 64): ("ESPN", "espn_dark")},                   # ESPN THE MAGAZINE
}
#: the tower's name band in lambert73: its rect, its two lines and the width of the band the tower's sign draws (u px)
SEA_NAME = ((0, 92, 128, 128), ("LUMEN", "FIELD"), 124.3)
#: its own colours (medians of the retail band): the lettering, the lettering's outline and the band
SEA_NAME_COLOURS = ((255, 255, 253), (107, 115, 117), (168, 174, 172))
PIT_OUT = {key: ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / f"s22_{key}.png" for key in ("ad_bb01", "ad_bb02")}
#: Pittsburgh's swoosh cells, by the table's rects (nfl2k5_modern_venues_2026.PIT_AD_BB0x_RECTS): (text, style[, turn])
PIT_CELLS = {
    "ad_bb01": {(192, 0, 240, 96): ("PLAY 60", "play60", -90), (192, 96, 240, 192): ("PLAY 60", "play60", -90)},
    "ad_bb02": {(130, 86, 254, 162): ("PLAY 60", "play60")},
}
#: the name block of ad_bb01: its rect, its two lines, the lettering and the block
PIT_NAME = ((0, 0, 191, 76), ("ACRISURE", "STADIUM"), (255, 255, 255), (12, 12, 12))
KC_OUT = {"ad01": ROOT / "data" / "nfl2k5_modern_venues_2026" / "extras" / "s13_ad01.png"}
#: Kansas City's defunct cells in ad01, by the table's rects (nfl2k5_modern_venues_2026.KC_AD01_RECTS)
KC_CELLS = {"ad01": {(128, 2, 206, 57): ("ESPN", "espn_dark"),            # ESPN THE MAGAZINE (the part u4's slot leaves)
                     (0, 148, 104, 171): ("NFL NETWORK", "net"),           # MOTOROLA
                     (0, 173, 103, 208): ("ESPN", "espn"),                 # ESPN VIDEOGAMES
                     (158, 172, 206, 192): ("NFLPA", "nflpa"),             # PLAYERS INC (above u4's slot)
                     (105, 209, 128, 233): ("NFL+", "plus")}}              # VISUAL CONCEPTS (left of u4's slot)
#: the top cloth of s27's lambert12 (64 x 64): the connected opaque region round this seed pixel
TB_SHIP_SEED = (32, 8)
S = 4
FONT_BLACK = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Black.ttf"
FONT_COND = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
NAVY, RED, WHITE, CLOTH, ESPN_RED = (1, 51, 105), (213, 10, 10), (255, 255, 255), (242, 242, 238), (204, 0, 0)
# (x0, y0, x1, y1) retail pixels of the eight replaced cloths, from the retail alpha (connected opaque regions)
CELLS = {
    "espn": (5, 2, 123, 61), "nfl_plus": (5, 66, 123, 125), "play60": (131, 67, 190, 126),
    "nfl_flag": (195, 67, 254, 126), "super_bowl": (131, 131, 190, 190), "nflpa_1": (195, 131, 254, 190),
    "nfl_network": (5, 194, 123, 253), "nflpa_2": (195, 195, 254, 254),
}
RECTS = [list(CELLS[k]) for k in ("espn", "nfl_plus", "play60", "nfl_flag", "super_bowl", "nflpa_1", "nfl_network",
                                   "nflpa_2")]
DESIGN = {  # cell: (cloth colour, [(text, colour, font)] lines)
    "espn": (CLOTH, [("ESPN", ESPN_RED, FONT_BLACK)]),
    "nfl_plus": (NAVY, [("NFL+", WHITE, FONT_BLACK)]),
    "play60": (CLOTH, [("PLAY", NAVY, FONT_BLACK), ("60", RED, FONT_BLACK)]),
    "nfl_flag": (CLOTH, [("NFL", NAVY, FONT_BLACK), ("FLAG", RED, FONT_BLACK)]),
    "super_bowl": (NAVY, [("SUPER BOWL", WHITE, FONT_COND), ("LXI", WHITE, FONT_BLACK)]),
    "nflpa_1": (CLOTH, [("NFLPA", NAVY, FONT_BLACK)]),
    "nfl_network": (NAVY, [("NFL", WHITE, FONT_BLACK), ("NETWORK", WHITE, FONT_COND)]),
    "nflpa_2": (CLOTH, [("NFLPA", NAVY, FONT_BLACK)]),
    "tb_ship_banner": (CLOTH, [("RAYMOND JAMES", NAVY, FONT_COND), ("STADIUM", NAVY, FONT_COND)]),
}


def _fit(draw, text, font_path, box_w, box_h):
    size = int(box_h * 1.3)
    while size > 6:
        font = ImageFont.truetype(font_path, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= box_w and b - t <= box_h:
            return font, (l, t, r, b)
        size -= max(1, size // 24)
    font = ImageFont.truetype(font_path, 6)
    return font, draw.textbbox((0, 0), text, font=font)


def draw_cloth(cell, width, height):
    """One cloth at 4x: its colour and its centred lines of type (padding 12% across, 18% down)."""
    colour, lines = DESIGN[cell]
    im = Image.new("RGBA", (width * S, height * S), colour + (255,))
    d = ImageDraw.Draw(im)
    pad_x, pad_y = width * S * 0.12, height * S * 0.18
    inner_w, inner_h = width * S - 2 * pad_x, height * S - 2 * pad_y
    gap = inner_h * 0.08
    line_h = (inner_h - gap * (len(lines) - 1)) / len(lines)
    y = pad_y
    for text, fill, font_path in lines:
        font, (l, t, r, b) = _fit(d, text, font_path, inner_w, line_h)
        d.text(((width * S - (r - l)) / 2 - l, y + (line_h - (b - t)) / 2 - t), text, font=font, fill=fill + (255,))
        y += line_h + gap
    return im


def _blur(values, radius):
    """Three passes of a (2r+1) box mean with edge clamping: close to a Gaussian, numpy only."""
    out = np.asarray(values, dtype=np.float64)
    k = 2 * radius + 1
    for _ in range(3):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (radius + 1, radius)
            c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis)
            out = (np.take(c, range(k, c.shape[axis]), axis=axis) - np.take(c, range(0, c.shape[axis] - k), axis=axis)) / k
    return out


def folds(retail_rgba, box):
    """Low-frequency fold shading of one retail cloth, as a 4x brightness ratio. Only the plain cloth counts: the
    printed logo and lettering (pixels far from the cloth colour, grown by two pixels) are left out of a masked
    blur, so no trace of the retail printing survives."""
    x0, y0, x1, y1 = box
    sub = retail_rgba[y0:y1, x0:x1].astype(np.float64)
    solid = sub[..., 3] > 128
    rgb = sub[..., :3]
    lum = rgb.mean(axis=-1)
    chroma = rgb.max(axis=-1) - rgb.min(axis=-1)
    cloth_lum = float(np.percentile(lum[solid], 75)) if solid.any() else 128.0
    printed = (chroma > 40.0) | (lum < 0.72 * cloth_lum)  # coloured print, or dark print; folds are neither
    printed = _blur(printed.astype(np.float64), 2) > 0.02
    keep = (solid & ~printed).astype(np.float64)
    if keep.sum() < 0.1 * max(1, solid.sum()):
        return np.ones(((y1 - y0) * S, (x1 - x0) * S))  # a cloth that is all print has no folds to read
    smooth = _blur(lum * keep, 4) / np.maximum(_blur(keep, 4), 1e-3)
    reference = float(np.percentile(smooth[keep > 0], 75))
    ratio = np.clip(1.0 + (smooth / max(reference, 1.0) - 1.0) * 0.6, 0.85, 1.1)
    return np.asarray(Image.fromarray(np.float32(ratio)).resize(((x1 - x0) * S, (y1 - y0) * S), Image.BILINEAR),
                      dtype=np.float64)


def reduce(master, width, height):
    """4x master -> retail size, premultiplied so clear edges do not darken."""
    a = np.asarray(master, dtype=np.float64) / 255.0
    pre = np.concatenate([a[..., :3] * a[..., 3:4], a[..., 3:4]], axis=-1)
    small = pre.reshape(height, S, width, S, 4).mean(axis=(1, 3))
    alpha = small[..., 3:4]
    rgb = np.where(alpha > 0, small[..., :3] / np.maximum(alpha, 1e-6), 0.0)
    return Image.fromarray(np.uint8(np.clip(np.concatenate([rgb, alpha], -1) * 255 + 0.5, 0, 255)), "RGBA")


def author(retail_png, masters=None):
    retail = np.asarray(Image.open(retail_png).convert("RGBA"))
    height, width = retail.shape[:2]
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    alpha_up = np.asarray(Image.fromarray(retail[..., 3]).resize((width * S, height * S), Image.NEAREST))
    for cell, box in CELLS.items():
        x0, y0, x1, y1 = box
        cloth = np.asarray(draw_cloth(cell, x1 - x0, y1 - y0), dtype=np.float64)
        cloth[..., :3] *= folds(retail, box)[..., None]
        cloth[..., 3] = alpha_up[y0 * S:y1 * S, x0 * S:x1 * S]
        sheet.paste(Image.fromarray(np.uint8(np.clip(cloth, 0, 255)), "RGBA"), (x0 * S, y0 * S))
    native = reduce(sheet, width, height)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    native.save(OUT, optimize=True)
    if masters:
        Path(masters).mkdir(parents=True, exist_ok=True)
        sheet.save(Path(masters) / "banner_corp_4x.png", optimize=True)
    return hashlib.sha256(OUT.read_bytes()).hexdigest()



def _region(alpha, seed):
    """The connected opaque region (alpha over 128, 4-neighbours) round ``seed`` (x, y), as a boolean mask."""
    solid = alpha > 128
    height, width = solid.shape
    mask = np.zeros_like(solid)
    stack = [seed[::-1]]
    while stack:
        y, x = stack.pop()
        if 0 <= y < height and 0 <= x < width and solid[y, x] and not mask[y, x]:
            mask[y, x] = True
            stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
    return mask


def author_tb_ship_banner(retail_png, masters=None):
    """s27's lambert12 overlay: the top cloth redrawn as RAYMOND JAMES STADIUM (plain type), the rest clear."""
    retail = np.asarray(Image.open(retail_png).convert("RGBA"))
    height, width = retail.shape[:2]
    mask = _region(retail[..., 3], TB_SHIP_SEED)
    ys, xs = np.nonzero(mask)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    x0, y0, x1, y1 = box
    cloth = np.asarray(draw_cloth("tb_ship_banner", x1 - x0, y1 - y0), dtype=np.float64)
    cloth[..., :3] *= folds(retail, box)[..., None]
    alpha = np.where(mask, retail[..., 3], 0).astype(np.uint8)
    alpha_up = np.asarray(Image.fromarray(alpha).resize((width * S, height * S), Image.NEAREST))
    cloth[..., 3] = alpha_up[y0 * S:y1 * S, x0 * S:x1 * S]
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    sheet.paste(Image.fromarray(np.uint8(np.clip(cloth, 0, 255)), "RGBA"), (x0 * S, y0 * S))
    native = reduce(sheet, width, height)
    TB_SHIP_OUT.parent.mkdir(parents=True, exist_ok=True)
    native.save(TB_SHIP_OUT, optimize=True)
    if masters:
        Path(masters).mkdir(parents=True, exist_ok=True)
        sheet.save(Path(masters) / "s27_lambert12_4x.png", optimize=True)
    return hashlib.sha256(TB_SHIP_OUT.read_bytes()).hexdigest()


def _type_image(text, colour, box_w, box_h, turn=0):
    """One line of Roboto Black fitted to 90 % of the box's width and 80 % of its height (u4's type panels); with
    ``turn`` (degrees, -90 a quarter clockwise) fitted to the turned box and turned."""
    if turn:
        return _type_image(text, colour, box_h, box_w).rotate(turn, expand=True)
    probe = ImageDraw.Draw(Image.new("L", (8, 8)))
    size = int(box_h * 1.2)
    while size > 6:
        font = ImageFont.truetype(FONT_BLACK, size)
        l, t, r, b = probe.textbbox((0, 0), text, font=font)
        if r - l <= box_w * 0.9 and b - t <= box_h * 0.8:
            break
        size -= max(1, size // 20)
    im = Image.new("RGBA", (int(r - l) + 8, int(b - t) + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=font, fill=tuple(colour) + (255,))
    return im


def _light_panel(retail, rect, mode="light"):
    """The median colour of a retail cell's lightest 40 % (the panel behind its lettering), or with ``mode`` "dark" its
    darkest 40 % (a dark panel with light lettering), as u4's ring_colour."""
    x0, y0, x1, y1 = rect
    flat = retail[y0:y1, x0:x1, :3].reshape(-1, 3).astype(np.float64)
    lum = flat.mean(axis=1)
    pick = lum >= np.percentile(lum, 60) if mode == "light" else lum <= np.percentile(lum, 40)
    return tuple(int(v) for v in np.median(flat[pick], axis=0))


def _retail(export_dir, prefix, key):
    found = (sorted(Path(export_dir).glob(f"{prefix}dd_stadium_t*_{key}.png"))
             or sorted(Path(export_dir).glob(f"{prefix}dd_stadium_t*_{key}_*.png")))
    if not found:
        raise SystemExit(f"no {prefix}dd_stadium_t*_{key}.png in {export_dir}")
    return np.asarray(Image.open(found[0]).convert("RGBA"))


def _save(sheet, width, height, out, masters, master_name):
    native = reduce(sheet, width, height)
    out.parent.mkdir(parents=True, exist_ok=True)
    native.save(out, optimize=True)
    if masters:
        Path(masters).mkdir(parents=True, exist_ok=True)
        sheet.save(Path(masters) / master_name, optimize=True)
    return hashlib.sha256(out.read_bytes()).hexdigest()


def author_cells(prefix, cells, outs, export_dir, masters=None, sheets=None):
    """Type-panel extras: each listed cell a panel in its style at 4x, reduced; every other pixel clear."""
    digests = {}
    for key, table in cells.items():
        retail = _retail(export_dir, prefix, key)
        height, width = retail.shape[:2]
        sheet = (sheets or {}).get(key) or Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        for rect, (text, style, *turn) in table.items():
            x0, y0, x1, y1 = (v * S for v in rect)
            fg, bg = PANEL_STYLE[style]
            bg = _light_panel(retail, rect, bg) if bg in ("light", "dark") else bg
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=tuple(bg) + (255,))
            type_ = _type_image(text, fg, x1 - x0, y1 - y0, *turn)
            sheet.alpha_composite(type_, (int(x0 + ((x1 - x0) - type_.width) / 2), int(y0 + ((y1 - y0) - type_.height) / 2)))
        digests[key] = _save(sheet, width, height, outs[key], masters, f"{prefix}_{key}_4x.png")
    return digests


def author_was_sponsor_cells(export_dir, masters=None):
    """s29's banner01 and exit01 extras: each defunct cell a u4 type panel at 4x, reduced; the rest clear."""
    return author_cells("s29", WAS_CELLS, WAS_OUT, export_dir, masters)


def author_sea_cells(export_dir, masters=None):
    """s26's extras: the tower's name band in lambert73 (LUMEN over FIELD in the band's own colours, centred on the
    part of the band the sign draws) and the defunct cells of lambert69, lambert70 and lambert74 as type panels."""
    retail = _retail(export_dir, "s26", "lambert73")
    height, width = retail.shape[:2]
    (x0, y0, x1, y1), lines, drawn = SEA_NAME
    ink, outline, band = SEA_NAME_COLOURS
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((x0 * S, y0 * S, x1 * S - 1, y1 * S - 1), fill=band + (255,))
    box_h = (y1 - y0) * S
    shares = (0.56, 0.28)                                  # LUMEN large, FIELD below it, as the tower's own sign
    gap = box_h * 0.05
    top = y0 * S + (box_h - sum(shares) * box_h * 0.92 - gap) / 2
    for line, share in zip(lines, shares):
        h = share * box_h * 0.92
        font, (l, t, r, b) = _fit(draw, line, FONT_BLACK, drawn * S * 0.8, h)
        x = drawn * S / 2 - (r - l) / 2 - l
        draw.text((x, top + (h - (b - t)) / 2 - t), line, font=font, fill=ink + (255,), stroke_width=S,
                  stroke_fill=outline + (255,))
        top += h + gap
    out = author_cells("s26", {k: v for k, v in SEA_CELLS.items()}, SEA_OUT, export_dir, masters)
    out["lambert73"] = _save(sheet, width, height, SEA_OUT["lambert73"], masters, "s26_lambert73_4x.png")
    return out


def author_tb_fascia_name(retail_png, masters=None):
    """s27's lambert63 extra: RAYMOND JAMES STADIUM along the two rows' run, in the sign's own colours."""
    retail = np.asarray(Image.open(retail_png).convert("RGBA"))
    height, width = retail.shape[:2]
    (r1, _), (r2, _) = TB_FASCIA_ROWS
    rows = np.concatenate([retail[r[1]:r[3], r[0]:r[2], :3].reshape(-1, 3) for r in (r1, r2)]).astype(np.float64)
    lum = rows.mean(axis=1)
    background = tuple(int(v) for v in np.median(rows[lum >= np.percentile(lum, 60)], axis=0))
    sat = rows.max(axis=1) - rows.min(axis=1)
    ink = tuple(int(v) for v in np.median(rows[sat >= np.percentile(sat, 90)], axis=0))   # the lettering's blue
    row_h = r1[3] - r1[1]
    run_w = int(round(2 * TB_FASCIA_RUN * S))
    strip = Image.new("RGBA", (run_w, row_h * S), background + (255,))
    draw = ImageDraw.Draw(strip)
    font, (l, t, r, b) = _fit(draw, TB_FASCIA_TEXT, FONT_COND, run_w * 0.86, row_h * S * 0.78)
    draw.text(((run_w - (r - l)) / 2 - l, (row_h * S - (b - t)) / 2 - t), TB_FASCIA_TEXT, font=font, fill=ink + (255,))
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    pixels = np.asarray(strip)
    for index, (rect, start) in enumerate(TB_FASCIA_ROWS):
        x0, y0, x1, y1 = rect
        cols = (np.arange(width * S) + 0.5) / S          # texture u (px) of each 4x column
        run = (cols - start) % width + index * TB_FASCIA_RUN   # position along the name's run
        take = np.clip(np.rint(run * S - 0.5).astype(int), 0, run_w - 1)
        row = pixels[:, take]
        inside = (run >= index * TB_FASCIA_RUN) & (run < (index + 1) * TB_FASCIA_RUN)
        row = np.where(inside[None, :, None], row, np.array(background + (255,), np.uint8))
        sheet.paste(Image.fromarray(np.ascontiguousarray(row[:, x0 * S:x1 * S]), "RGBA"), (x0 * S, y0 * S))
    native = reduce(sheet, width, height)
    TB_FASCIA_OUT.parent.mkdir(parents=True, exist_ok=True)
    native.save(TB_FASCIA_OUT, optimize=True)
    if masters:
        Path(masters).mkdir(parents=True, exist_ok=True)
        sheet.save(Path(masters) / "s27_lambert63_4x.png", optimize=True)
    return hashlib.sha256(TB_FASCIA_OUT.read_bytes()).hexdigest()


def author_pit_cells(export_dir, masters=None):
    """s22's extras over d2's board art: ACRISURE over STADIUM in plain type on black, and the swoosh cells as PLAY 60
    type panels (the ad_bb01 column turned a quarter clockwise)."""
    retail = _retail(export_dir, "s22", "ad_bb01")
    height, width = retail.shape[:2]
    (x0, y0, x1, y1), lines, ink, block = PIT_NAME
    sheet = Image.new("RGBA", (width * S, height * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    draw.rectangle((x0 * S, y0 * S, x1 * S - 1, y1 * S - 1), fill=block + (255,))
    box_w, box_h = (x1 - x0) * S, (y1 - y0) * S
    shares = (0.42, 0.24)
    gap = box_h * 0.07
    top = y0 * S + (box_h - sum(shares) * box_h - gap) / 2
    for line, share in zip(lines, shares):
        h = share * box_h
        font, (l, t, r, b) = _fit(draw, line, FONT_BLACK, box_w * 0.84, h)
        draw.text((x0 * S + (box_w - (r - l)) / 2 - l, top + (h - (b - t)) / 2 - t), line, font=font, fill=ink + (255,))
        top += h + gap
    return author_cells("s22", PIT_CELLS, PIT_OUT, export_dir, masters, sheets={"ad_bb01": sheet})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--retail-export", help="a retail venue export folder (u4 naming)")
    ap.add_argument("--tb-ship-banner", help="the retail s27 dry-day lambert12 texture (64 x 64 PNG)")
    ap.add_argument("--tb-fascia-name", help="the retail s27 dry-day lambert63 texture (128 x 128 PNG)")
    ap.add_argument("--was-sponsor-cells", help="a retail s29 export folder (u4 naming: s29dd_stadium_t*_<key>.png)")
    ap.add_argument("--sea-cells", help="a retail s26 export folder (u4 naming: s26dd_stadium_t*_<key>.png)")
    ap.add_argument("--pit-cells", help="a retail s22 export folder (u4 naming: s22dd_stadium_t*_<key>*.png)")
    ap.add_argument("--kc-cells", help="a retail s13 export folder (u4 naming: s13dd_stadium_t*_<key>.png)")
    ap.add_argument("--masters", help="where to keep the 4x master (outside the repository)")
    a = ap.parse_args(argv)
    if a.tb_ship_banner:
        digest = author_tb_ship_banner(a.tb_ship_banner, a.masters)
        print(f"{TB_SHIP_OUT.relative_to(ROOT)} sha256 {digest}")
        return 0
    if a.tb_fascia_name:
        digest = author_tb_fascia_name(a.tb_fascia_name, a.masters)
        print(f"{TB_FASCIA_OUT.relative_to(ROOT)} sha256 {digest}")
        return 0
    if a.was_sponsor_cells:
        for key, digest in author_was_sponsor_cells(a.was_sponsor_cells, a.masters).items():
            print(f"{WAS_OUT[key].relative_to(ROOT)} sha256 {digest}")
        return 0
    if a.sea_cells:
        for key, digest in author_sea_cells(a.sea_cells, a.masters).items():
            print(f"{SEA_OUT[key].relative_to(ROOT)} sha256 {digest}")
        return 0
    if a.pit_cells:
        for key, digest in author_pit_cells(a.pit_cells, a.masters).items():
            print(f"{PIT_OUT[key].relative_to(ROOT)} sha256 {digest}")
        return 0
    if a.kc_cells:
        for key, digest in author_cells("s13", KC_CELLS, KC_OUT, a.kc_cells, a.masters).items():
            print(f"{KC_OUT[key].relative_to(ROOT)} sha256 {digest}")
        return 0
    if not a.retail_export:
        raise SystemExit("--retail-export, --tb-ship-banner, --tb-fascia-name, --was-sponsor-cells, --sea-cells, --pit-cells or --kc-cells is required")
    found = sorted(Path(a.retail_export).glob("*dd_stadium_t*_banner_corp.png"))
    if not found:
        raise SystemExit("no <prefix>dd_stadium_t*_banner_corp.png in the export")
    digest = author(found[0], a.masters)
    print(f"{OUT.relative_to(ROOT)} sha256 {digest}; rects {RECTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
