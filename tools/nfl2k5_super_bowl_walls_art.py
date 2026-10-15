#!/usr/bin/env python3
"""Super Bowl event walls for the Anniversary stadium aliases (job me1, N06): deterministic drawings at 4x masters
reduced to each surface's native size.

Every Super Bowl moment keeps its venue model and its permanent venue signs, and its temporary surfaces (the field
wall, the ribbon boards, the board wings, the hanging banners and the crowd's banners) carry that game's own event
identity: the Super Bowl numerals, an authored Lombardi-trophy mark, the host city, the broadcaster in plain type and
the two teams. Nothing is cut from photographs or other mods; the trophy, the shield and all type are drawn here.
Surfaces whose cloth outline must follow the source texture (``alpha: source``) are painted opaque over the tile
rectangles measured from that texture and the compiler keeps the disc's own alpha; ``opaque`` surfaces fill the whole
texture, and ``art`` surfaces carry their own cutout. An entry with ``areas`` paints only those boxes; outside them
the compiler keeps the disc's texels (the PNG is transparent there).

    python3 tools/nfl2k5_super_bowl_walls_art.py OUT_DIR --extract SB_EXTRACT_DIR [--masters DIR]

``--extract`` (author time only) is a folder of the 17 aliases' native stadium textures, used to measure tile
rectangles; no pixel of it is written to OUT_DIR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCALE = 4
SANS = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
SERIF = "/usr/share/fonts/opentype/urw-base35/P052-Bold.otf"
WHITE = (255, 255, 255)
SILVER = (196, 200, 206)
NAVY = (12, 30, 66)

# --- the games ------------------------------------------------------------------------------------------------------
# Team colours are the season's (NFL Record and Fact Book values where they exist). Player banners use players who
# played in that game. Broadcasters are the game's network, in plain type (no partner logo is drawn).
TEAMS = {
    "NYG": ("GIANTS", (11, 34, 101), (167, 25, 48)), "NE": ("PATRIOTS", (0, 34, 68), (198, 12, 48)),
    "PHI": ("EAGLES", (0, 76, 84), (165, 172, 175)), "SF": ("49ERS", (170, 0, 0), (173, 153, 93)),
    "KC": ("CHIEFS", (227, 24, 55), (255, 184, 28)), "LAR": ("RAMS", (0, 53, 148), (255, 209, 0)),
    "CIN": ("BENGALS", (251, 79, 20), (16, 16, 16)), "PIT": ("STEELERS", (16, 16, 16), (255, 182, 18)),
    "ARI": ("CARDINALS", (151, 35, 63), (255, 255, 255)), "NO": ("SAINTS", (16, 16, 16), (211, 188, 141)),
    "IND": ("COLTS", (0, 44, 95), (255, 255, 255)), "BAL": ("RAVENS", (36, 23, 115), (158, 124, 12)),
    "SEA": ("SEAHAWKS", (0, 34, 68), (105, 190, 40)), "ATL": ("FALCONS", (167, 25, 48), (16, 16, 16)),
    "DEN": ("BRONCOS", (0, 34, 68), (251, 79, 20)), "GB": ("PACKERS", (24, 48, 40), (255, 184, 28)),
    "STL": ("RAMS", (0, 35, 85), (200, 170, 90)), "TEN": ("TITANS", (12, 35, 64), (75, 146, 219)),
    "BUF": ("BILLS", (0, 51, 141), (198, 12, 48)), "NYG90": ("GIANTS", (1, 35, 82), (167, 25, 48)),
    "CAR": ("PANTHERS", (0, 133, 202), (16, 16, 16)),
}

#: row -> event. ``style``: classic badge (before 2008), host (2008-2015: trophy before coloured numerals over a band
#: of the host's colours) or standard (2017 on: the silver trophy before silver numerals).
GAMES = {
    14: dict(n="XXIII", city="MIAMI", net="NBC", year=1989, style="classic", away="CIN", home="SF",
             pal=((14, 40, 92), (0, 140, 150), (240, 120, 30)),
             fans={"SF": ("GO NINERS!", "SF FAITHFUL"), "CIN": ("WHO DEY!", "GO BENGALS")},
             players=(("#16", "MONTANA"), ("#80", "RICE"), ("#7", "ESIASON"), ("#30", "ICKEY"))),
    15: dict(n="XXV", city="TAMPA", net="ABC", year=1991, style="classic", away="BUF", home="NYG90",
             pal=((18, 32, 92), (200, 20, 40), (255, 255, 255)),
             fans={"NYG90": ("GO BIG BLUE!", "GIANTS PRIDE"), "BUF": ("GO BILLS!", "SHOUT!")},
             players=(("#24", "O.J. ANDERSON"), ("#56", "L.T."), ("#12", "KELLY"), ("#34", "THURMAN"))),
    21: dict(n="XXXII", city="SAN DIEGO", net="NBC", year=1998, style="classic", away="GB", home="DEN",
             pal=((10, 36, 82), (226, 168, 40), (0, 128, 140)),
             fans={"DEN": ("GO BRONCOS!", "ORANGE CRUSH"), "GB": ("GO PACK GO!", "CHEESEHEADS")},
             players=(("#7", "ELWAY"), ("#30", "T.D."), ("#4", "FAVRE"), ("#92", "REGGIE"))),
    22: dict(n="XXXIV", city="ATLANTA", net="ABC", year=2000, style="classic", away="STL", home="TEN",
             pal=((118, 18, 32), (214, 164, 52), (40, 40, 48)),
             fans={"TEN": ("TITANS!", "GO TITANS"), "STL": ("GO RAMS!", "RAMS RULE")},
             players=(("#9", "McNAIR"), ("#27", "EDDIE"), ("#13", "WARNER"), ("#28", "FAULK"))),
    23: dict(n="XXXVI", city="NEW ORLEANS", net="FOX", year=2002, style="classic", away="STL", home="NE",
             pal=((16, 32, 96), (196, 20, 40), (255, 255, 255)), stars=True,
             fans={"NE": ("GO PATS!", "PATRIOTS"), "STL": ("GO RAMS!", "GREATEST SHOW")},
             players=(("#12", "BRADY"), ("#4", "VINATIERI"), ("#13", "WARNER"), ("#28", "FAULK"))),
    27: dict(n="XLII", city="GLENDALE", net="FOX", year=2008, style="host", away="NYG", home="NE",
             pal=((22, 30, 68), (178, 44, 30), (226, 172, 92)),
             fans={"NE": ("GO PATS!", "PATRIOTS NATION"), "NYG": ("GO BIG BLUE!", "G-MEN")},
             players=(("#12", "BRADY"), ("#81", "MOSS"), ("#10", "ELI"), ("#92", "STRAHAN"))),
    28: dict(n="XLIII", city="TAMPA", net="NBC", year=2009, style="host", away="PIT", home="ARI",
             pal=((10, 42, 78), (0, 120, 140), (240, 112, 34)),
             fans={"ARI": ("GO CARDS!", "BIRD GANG"), "PIT": ("STEELER NATION", "HERE WE GO!")},
             players=(("#13", "WARNER"), ("#11", "FITZGERALD"), ("#7", "BIG BEN"), ("#43", "TROY"))),
    29: dict(n="XLVI", city="INDIANAPOLIS", net="NBC", year=2012, style="host", away="NYG", home="NE",
             pal=((10, 34, 86), (34, 92, 172), (196, 202, 208)),
             fans={"NE": ("GO PATS!", "PATRIOTS NATION"), "NYG": ("GO BIG BLUE!", "G-MEN")},
             players=(("#12", "BRADY"), ("#87", "GRONK"), ("#10", "ELI"), ("#80", "CRUZ"))),
    30: dict(n="LI", city="HOUSTON", net="FOX", year=2017, style="standard", away="NE", home="ATL",
             pal=((12, 30, 62), (190, 30, 46), (196, 202, 208)),
             fans={"ATL": ("RISE UP!", "GO FALCONS"), "NE": ("GO PATS!", "PATRIOTS NATION")},
             players=(("#2", "MATT RYAN"), ("#11", "JULIO"), ("#12", "BRADY"), ("#11", "EDELMAN"))),
    35: dict(n="XLIV", city="SOUTH FLORIDA", net="CBS", year=2010, style="host", away="NO", home="IND",
             pal=((10, 42, 82), (0, 148, 160), (245, 122, 32)),
             fans={"IND": ("GO COLTS!", "BLUE CREW"), "NO": ("WHO DAT!", "GEAUX SAINTS")},
             players=(("#18", "MANNING"), ("#87", "WAYNE"), ("#9", "BREES"), ("#12", "COLSTON"))),
    40: dict(n="XLVII", city="NEW ORLEANS", net="CBS", year=2013, style="host", away="BAL", home="SF",
             pal=((62, 32, 108), (212, 168, 60), (0, 110, 80)),
             fans={"SF": ("GO NINERS!", "FAITHFUL"), "BAL": ("RAVENS NATION", "GO RAVENS!")},
             players=(("#7", "KAEPERNICK"), ("#21", "GORE"), ("#5", "FLACCO"), ("#52", "RAY LEWIS"))),
    42: dict(n="XLIX", city="ARIZONA", net="NBC", year=2015, style="host", away="NE", home="SEA",
             pal=((70, 34, 86), (206, 64, 30), (246, 182, 40)),
             fans={"SEA": ("12TH MAN", "GO HAWKS!"), "NE": ("GO PATS!", "PATRIOTS NATION")},
             players=(("#3", "WILSON"), ("#24", "BEAST MODE"), ("#12", "BRADY"), ("#87", "GRONK"))),
    45: dict(n="LII", city="MINNEAPOLIS", net="NBC", year=2018, style="standard", away="PHI", home="NE",
             pal=((8, 30, 70), (118, 186, 226), (255, 255, 255)), tag="BOLD NORTH",
             fans={"NE": ("GO PATS!", "PATRIOTS NATION"), "PHI": ("FLY EAGLES FLY", "GO BIRDS!")},
             players=(("#12", "BRADY"), ("#87", "GRONK"), ("#9", "FOLES"), ("#86", "ERTZ"))),
    46: dict(n="LIV", city="MIAMI", net="FOX", year=2020, style="standard", away="SF", home="KC",
             pal=((18, 30, 52), (0, 150, 160), (238, 90, 150)),
             fans={"KC": ("CHIEFS KINGDOM", "GO CHIEFS!"), "SF": ("GO NINERS!", "FAITHFUL")},
             players=(("#15", "MAHOMES"), ("#87", "KELCE"), ("#85", "KITTLE"), ("#97", "BOSA"))),
    48: dict(n="LVI", city="LOS ANGELES", net="NBC", year=2022, style="standard", away="LAR", home="CIN",
             pal=((44, 20, 82), (246, 122, 40), (226, 76, 122)),
             fans={"CIN": ("WHO DEY!", "RULE THE JUNGLE"), "LAR": ("RAMS HOUSE", "WHOSE HOUSE?")},
             players=(("#9", "BURROW"), ("#1", "CHASE"), ("#10", "KUPP"), ("#99", "DONALD"))),
    50: dict(n="LVIII", city="LAS VEGAS", net="CBS", year=2024, style="standard", away="SF", home="KC",
             pal=((16, 16, 20), (200, 26, 36), (212, 172, 72)),
             fans={"KC": ("CHIEFS KINGDOM", "GO CHIEFS!"), "SF": ("GO NINERS!", "FAITHFUL")},
             players=(("#15", "MAHOMES"), ("#87", "KELCE"), ("#13", "PURDY"), ("#23", "CMC"))),
}

#: (source kind, source prefix) -> {material: (painter, alpha)}. Permanent venue signs (stadium names, building
#: wordmarks, sponsor panels the stadium owns) are not listed and keep their bytes, except where the name itself
#: is from another era.
BANNERS = {"banner_corp": ("corp", "source"), "banner_home_team": ("fans_home", "source"),
           "banner_away_team": ("fans_away", "source"), "banner_home_player": ("players", "source")}
VENUES = {
    ("built", "s15"): {"usb_wall": ("wall", "opaque"), "LIGHT_usb_ribbon": ("ribbon", "opaque"),
                       "LIGHT_usb_board_wing": ("wing", "opaque"), "LIGHT_usb_signs": ("signs4", "opaque"),
                       "LIGHT_usb_prow_display": ("prow", "opaque")},
    ("built", "s11"): {"los_wall": ("wall", "opaque"), "LIGHT_los_ribbon": ("ribbon", "opaque"),
                       "LIGHT_los_board_wing": ("wing", "opaque"), "los_banners": ("vbanners", "opaque")},
    ("built", "s00"): {"sf_wall": ("wall", "opaque"), "LIGHT_sf_ribbon": ("ribbon", "opaque"),
                       "LIGHT_sf_board_wing": ("wing", "opaque"), "sf_logo": ("uop_name", "art")},
    ("built", "s14"): {"hr_wall": ("wall", "opaque"), "LIGHT_hr_ribbon": ("ribbon", "opaque"),
                       "LIGHT_hr_board_panel": ("panel", "opaque")},
    ("built", "s23"): {"LIGHT_sf_ribbon": ("ribbon", "opaque"), "LIGHT_sf_screen": ("screen", "opaque")},
    ("built", "s20"): {"ag_wall": ("wall", "opaque"), "LIGHT_ag_ribbon": ("ribbon", "opaque"),
                       "LIGHT_ag_board_panel": ("panel", "opaque"), "LIGHT_ag_mesh": ("mesh", "opaque")},
    # Retail venues: the host team's own walls, flags and cloths. ``(alpha, [(box, painter), ...])`` paints only those
    # native-pixel boxes; the rest of the texture (stadium structure, sponsor tiles, the permanent name) keeps its bytes.
    ("retail", "s14"): {"wall05": ("bands2", "opaque"), "wall08": ("bands2", "opaque"),
                        "wall04": ("bands2", "opaque"), "wall07": ("bands2", "opaque")},
    ("retail", "s27"): {"fieldwall": ("opaque", [((0, 62, 128, 128), "band")]),
                        "bigwallbanner2": ("opaque", [((40, 0, 128, 128), "hang")])},
    ("retail", "s24"): {"chargerlogo": ("art", [((0, 0, 256, 64), "word_event"), ((0, 149, 109, 256), "tile_logo")]),
                        "chargerswall02": ("pad", "opaque"), "chargerswall03": ("pad", "opaque")},
    ("retail", "s01"): {"falconswall01": ("bands3", "opaque"), "falconswall02": ("mark", "art"),
                        "falconswall05": ("prow", "opaque"), "logo": ("flag", "opaque")},
    ("retail", "s17"): {"swall1": ("pad", "opaque"), "swall2": ("pad", "opaque"),
                        "new_orleans3_lambert39": ("opaque", [((0, 18, 128, 40), "marquee")]),
                        "new_orleans3_lambert17": ("prow", "opaque"),
                        "swall3": ("art", [((0, 0, 128, 64), "hang_wide"), ((0, 64, 128, 78), "word_event"),
                                           ((0, 78, 64, 128), "shield_mark"), ((64, 78, 128, 128), "mark")])},
    ("retail", "s37"): {"texanswall01": ("bands2", "opaque"), "tunnelcover01": ("opaque", [((0, 0, 82, 128), "hang")]),
                        "stadium_name": ("nrg_name", "art")},
}


# --- drawing primitives ------------------------------------------------------------------------------------------

def font(px, serif=False):
    return ImageFont.truetype(SERIF if serif else SANS, max(4, int(px)))


def text_image(word, colour, px=200, serif=False, stroke=0, stroke_colour=(0, 0, 0)):
    f = font(px, serif)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    box = probe.textbbox((0, 0), word, font=f, stroke_width=stroke)
    im = Image.new("RGBA", (box[2] - box[0] + 8, box[3] - box[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((4 - box[0], 4 - box[1]), word, font=f, fill=tuple(colour) + (255,),
                            stroke_width=stroke, stroke_fill=tuple(stroke_colour) + (255,))
    return im.crop(im.getbbox())


def fit(im, w, h):
    f = min(w / im.width, h / im.height)
    return im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS)


def paste_center(canvas, im, cx, cy):
    canvas.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


def row_of(items, W, H, gap_min, hfrac=0.62):
    """Items scaled to a common height and spread evenly across a W x H band (RGBA)."""
    scaled = [fit(im, 10 ** 6, int(H * im.info.get("h", hfrac))) for im in items]
    total = sum(im.width for im in scaled)
    if total + gap_min * len(scaled) > W:
        f = (W - gap_min * len(scaled)) / total
        scaled = [im.resize((max(1, int(im.width * f)), max(1, int(im.height * f))), Image.LANCZOS) for im in scaled]
        total = sum(im.width for im in scaled)
    gap = (W - total) / len(scaled)
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = gap / 2
    for im in scaled:
        band.alpha_composite(im, (int(x), (H - im.height) // 2))
        x += im.width + gap
    return band


def silver_fill(mask, light=(236, 238, 242), dark=(128, 134, 144), axis=0):
    """A brushed-silver gradient through a mask (L image): light at the centre, darker at the edges."""
    W, H = mask.size
    t = np.abs(np.linspace(-1, 1, W if axis == 0 else H)) ** 1.4
    ramp = (np.asarray(light, float)[None] * (1 - t[:, None]) + np.asarray(dark, float)[None] * t[:, None])
    rgb = np.repeat(ramp[None], H, 0) if axis == 0 else np.repeat(ramp[:, None], W, 1)
    out = np.dstack([rgb.astype(np.uint8), np.asarray(mask)])
    return Image.fromarray(out, "RGBA")


def trophy(H):
    """The Lombardi trophy: a regulation football poised to kick on a tapering stem over a three-step base."""
    W = int(H * 0.56)
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    cx = W / 2
    base_top = H * 0.70
    d.polygon([(cx - W * 0.40, H), (cx + W * 0.40, H), (cx + W * 0.34, H * 0.90), (cx - W * 0.34, H * 0.90)], fill=255)
    d.polygon([(cx - W * 0.31, H * 0.90), (cx + W * 0.31, H * 0.90), (cx + W * 0.25, H * 0.80),
               (cx - W * 0.25, H * 0.80)], fill=255)
    d.polygon([(cx - W * 0.22, H * 0.80), (cx + W * 0.22, H * 0.80), (cx + W * 0.15, base_top),
               (cx - W * 0.15, base_top)], fill=255)
    pts_l, pts_r = [], []
    for k in range(21):
        t = k / 20
        y = base_top - t * (base_top - H * 0.40)
        half = W * (0.12 - 0.075 * math.sin(t * math.pi * 0.85) + 0.02 * t)
        pts_l.append((cx - half, y))
        pts_r.append((cx + half, y))
    d.polygon(pts_l + pts_r[::-1], fill=255)
    ball = Image.new("L", (int(H * 0.52), int(H * 0.30)), 0)
    ImageDraw.Draw(ball).ellipse([0, 0, ball.width - 1, ball.height - 1], fill=255)
    long_axis = H * 0.52
    ball = ball.rotate(38, expand=True, resample=Image.BICUBIC)
    bx, by = int(cx - ball.width * 0.5 + W * 0.02), int(H * 0.40 - ball.height * 0.86)
    m.paste(255, (bx, by), ball)
    fill = silver_fill(m)
    d2 = ImageDraw.Draw(fill)
    # the laces along the ball's long axis (a seam and six stitches), and the base's engraved steps
    ux, uy = math.cos(math.radians(38)), -math.sin(math.radians(38))
    px, py = -uy, ux
    ox, oy = bx + ball.width / 2 - px * H * 0.035, by + ball.height / 2 - py * H * 0.035
    lace = (104, 110, 122, 255)
    half = long_axis * 0.16
    d2.line([(ox - ux * half, oy - uy * half), (ox + ux * half, oy + uy * half)], fill=lace, width=max(1, H // 80))
    for k in range(-3, 3):
        t = (k + 0.5) / 3 * half
        sx, sy = ox + ux * t, oy + uy * t
        d2.line([(sx - px * H * 0.018, sy - py * H * 0.018), (sx + px * H * 0.018, sy + py * H * 0.018)], fill=lace,
                width=max(1, H // 90))
    for y, half_w in ((H * 0.90, 0.33), (H * 0.80, 0.24), (base_top, 0.15)):
        d2.line([(cx - W * half_w, y), (cx + W * half_w, y)], fill=(104, 110, 120, 255), width=max(1, H // 90))
    return fill


def outline(im, colour, radius):
    """A solid outline round an RGBA mark (stroke behind it)."""
    a = im.split()[3].filter(ImageFilter.MaxFilter(radius * 2 + 1))
    back = Image.new("RGBA", (im.width + radius * 2, im.height + radius * 2), (0, 0, 0, 0))
    solid = Image.new("RGBA", im.size, tuple(colour) + (255,))
    pad = Image.new("L", back.size, 0)
    pad.paste(a, (radius, radius))
    back.paste(Image.new("RGBA", back.size, tuple(colour) + (255,)), (0, 0), pad)
    back.alpha_composite(im, (radius, radius))
    del solid
    return back


def nfl_shield(H, modern):
    """The league shield, simplified for distance: the navy crown with its stars and football over the white field
    with NFL. Eight stars from the 2008 season; the many-star crown before."""
    W = int(H * 0.82)
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    pts = [(0, 0), (W * 0.5, H * 0.07), (W, 0), (W, H * 0.62), (W * 0.5, H), (0, H * 0.62)]
    d.polygon(pts, fill=255)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    im.paste((255, 255, 255, 255), (0, 0), m)
    inner = Image.new("L", (W, H), 0)
    s = H * 0.06
    ImageDraw.Draw(inner).polygon([(s, s * 1.2), (W * 0.5, H * 0.07 + s), (W - s, s * 1.2), (W - s, H * 0.6),
                                   (W * 0.5, H - s * 1.6), (s, H * 0.6)], fill=255)
    navy = (1, 51, 105)
    crown = Image.new("L", (W, H), 0)
    ImageDraw.Draw(crown).rectangle([0, 0, W, H * 0.33], fill=255)
    crown = Image.fromarray(np.minimum(np.asarray(crown), np.asarray(inner)))
    im.paste(navy + (255,), (0, 0), crown)
    rim = Image.fromarray(np.where((np.asarray(m) > 0) & (np.asarray(inner) == 0), 255, 0).astype(np.uint8))
    im.paste(navy + (255,), (0, 0), rim)
    d = ImageDraw.Draw(im)
    stars = 8 if modern else 13
    for k in range(stars):
        x = W * (0.16 + 0.68 * (k + 0.5) / stars)
        y = H * (0.21 if modern or k % 2 == 0 else 0.15)
        r = H * (0.028 if modern else 0.02)
        d.ellipse([x - r, y - r, x + r, y + r], fill=WHITE)
    d.ellipse([W * 0.38, H * 0.06, W * 0.62, H * 0.16], fill=(120, 74, 40))
    word = fit(text_image("NFL", navy, px=H, serif=not modern), W * 0.66, H * 0.36)
    paste_center(im, word, W * 0.5, H * 0.57)
    if modern:
        d.line([(W * 0.2, H * 0.36), (W * 0.8, H * 0.36)], fill=(213, 10, 10), width=max(1, H // 40))
    return im


def sb_logo(g, H, on_dark=True):
    """The game's event mark, by period. Classic: a badge in the game's colours with SUPER BOWL and serif numerals;
    host (2008-2015): the trophy before numerals coloured from the host's palette, over a band; standard (2017 on):
    the silver trophy before the silver numerals, SUPER BOWL beneath."""
    dark, mid, acc = g["pal"]
    n = g["n"]
    if g["style"] == "classic":
        W = int(H * 1.45)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        r = H * 0.16
        d.rounded_rectangle([0, 0, W - 1, H - 1], radius=r, fill=WHITE + (255,))
        s = H * 0.05
        d.rounded_rectangle([s, s, W - 1 - s, H - 1 - s], radius=r * 0.8, fill=tuple(dark) + (255,))
        d.rectangle([s * 2, H * 0.70, W - 1 - s * 2, H * 0.78], fill=tuple(mid) + (255,))
        if g.get("stars"):
            for k in range(7):
                x = W * (0.14 + 0.72 * k / 6)
                d.regular_polygon((x, H * 0.88, H * 0.045), 5, fill=WHITE)
        else:
            d.rectangle([s * 2, H * 0.80, W - 1 - s * 2, H * 0.84], fill=tuple(acc) + (255,))
        top = fit(text_image("SUPER BOWL", WHITE, px=H), W * 0.74, H * 0.17)
        paste_center(im, top, W / 2, H * 0.19)
        num = fit(text_image(n, WHITE, px=H * 2, serif=True, stroke=int(H * 0.05), stroke_colour=mid), W * 0.80,
                  H * 0.42)
        paste_center(im, num, W / 2, H * 0.49)
        return im
    if g["style"] == "host":
        W = int(H * 1.5)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.ellipse([W * 0.06, H * 0.10, W * 0.94, H * 0.84], fill=tuple(mid) + (255,))
        d.ellipse([W * 0.12, H * 0.18, W * 0.88, H * 0.78], fill=tuple(dark) + (255,))
        num = fit(text_image(n, tuple(acc), px=H * 2, serif=True, stroke=int(H * 0.06), stroke_colour=WHITE),
                  W * 0.86, H * 0.46)
        paste_center(im, num, W / 2, H * 0.47)
        t = trophy(int(H * 0.74))
        paste_center(im, outline(t, dark, max(1, H // 60)), W / 2, H * 0.43)
        word = fit(text_image("SUPER BOWL", WHITE, px=H, stroke=max(1, H // 40), stroke_colour=dark), W * 0.70,
                   H * 0.14)
        paste_center(im, word, W / 2, H * 0.91)
        return im
    W = int(H * 1.25)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    word = text_image(n, (255, 255, 255), px=H * 2)
    word = fit(word, W * 0.98, H * 0.66)
    mask = word.split()[3]
    silver = silver_fill(mask, axis=1, light=(242, 244, 248), dark=(150, 156, 166))
    silver = outline(silver, (60, 64, 72) if on_dark else (90, 96, 106), max(1, H // 70))
    paste_center(im, silver, W / 2, H * 0.40)
    t = trophy(int(H * 0.80))
    paste_center(im, outline(t, dark, max(1, H // 50)), W / 2, H * 0.41)
    sb = fit(text_image("SUPER BOWL", WHITE if on_dark else dark, px=H), W * 0.74, H * 0.13)
    paste_center(im, sb, W / 2, H * 0.92)
    return im


def cloth(W, H, colour, seed=0, folds=3):
    """A hanging cloth banner: the colour with soft vertical folds and a drape across the top."""
    x = np.linspace(0, 1, W)[None, :]
    y = np.linspace(0, 1, H)[:, None]
    r = np.random.default_rng(seed)
    phase = r.uniform(0, math.tau)
    shade = 1 + 0.06 * np.sin(x * math.tau * folds + phase) + 0.03 * np.sin(x * math.tau * (folds * 2.3) + phase * 2)
    shade = shade - 0.08 * np.exp(-((y - 0.04) / 0.08) ** 2) * (0.5 + 0.5 * np.cos(x * math.tau * 2))
    shade = shade * (0.94 + 0.06 * y)
    rgb = np.clip(np.asarray(colour, float)[None, None] * shade[..., None], 0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb, np.full((H, W), 255, np.uint8)]), "RGBA")


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def contrast_on(bg, a, b=WHITE):
    return a if abs(lum(a) - lum(bg)) > abs(lum(b) - lum(bg)) else b


# --- painters --------------------------------------------------------------------------------------------------------
# Every painter takes (game, W, H, context) at master scale and returns an RGBA image.

def team_name(code):
    return TEAMS[code][0]


def p_wall(g, W, H, ctx):
    """The field wall's pads: the event colour, a light trim along the top, the mark, the words and the shield."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.10)], fill=tuple(mid) + (255,))
    d.rectangle([0, H - int(H * 0.06), W, H], fill=tuple(mid) + (255,))
    band_h = int(H * 0.80)
    logo = sb_logo(g, band_h * 3)
    logo.info["h"] = 0.98
    shield = nfl_shield(band_h * 3, g["year"] >= 2008)
    shield.info["h"] = 0.92
    words = [logo, text_image("SUPER BOWL " + g["n"], WHITE), shield, text_image(g.get("tag", g["city"]), WHITE)]
    band = row_of(words, W, band_h, SCALE * 6, 0.56)
    im.alpha_composite(band, (0, int(H * 0.11)))
    return im


def p_ribbon(g, W, H, ctx):
    """Two ribbon bands a texture: the event words over the matchup, plain type and the mark."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    half = H // 2
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, half], fill=tuple(dark) + (255,))
    top = [sb_logo(g, half * 3), text_image("SUPER BOWL " + g["n"], WHITE), text_image(g["city"], tuple(mid) if
           lum(mid) > 90 else WHITE), text_image(g["net"], WHITE)]
    top[0].info["h"] = 0.96
    im.alpha_composite(row_of(top, W, half, SCALE * 8, 0.52), (0, 0))
    away, home = g["away"], g["home"]
    seg = W // 2
    for k, code in enumerate((away, home)):
        _, c1, c2 = TEAMS[code]
        d.rectangle([k * seg, half, (k + 1) * seg, H], fill=tuple(c1) + (255,))
        word = text_image(team_name(code), contrast_on(c1, c2))
        band = row_of([word], seg, half, SCALE * 6, 0.56)
        im.alpha_composite(band, (k * seg, half))
    d.line([(seg, half), (seg, H)], fill=tuple(acc) + (255,), width=SCALE * 2)
    return im


def p_wing(g, W, H, ctx):
    """The board wings: black with the stat grid (the game's digits sit on them), the event colour and words."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), (8, 10, 16, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.14)], fill=tuple(mid if lum(mid) < 200 else dark) + (255,))
    for y in range(int(H * 0.22), int(H * 0.62), int(H * 0.10)):
        d.line([SCALE * 2, y, W - SCALE * 2, y], fill=(40, 46, 60, 255), width=SCALE)
    words = row_of([text_image("SUPER BOWL", WHITE)], W, int(H * 0.12), SCALE * 3, 0.7)
    im.alpha_composite(words, (0, int(H * 0.66)))
    num = row_of([text_image(g["n"], tuple(acc) if lum(acc) > 60 else WHITE)], W, int(H * 0.16), SCALE * 3, 0.8)
    im.alpha_composite(num, (0, int(H * 0.78)))
    return im


def p_panel(g, W, H, ctx):
    """The corner boards (128 x 128): the black screen over the event colour, SUPER BOWL and the numerals, and the
    down-and-distance line as the venue's boards show it."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([int(W * 0.08), int(H * 0.08), int(W * 0.92), int(H * 0.46)], fill=(6, 8, 12, 255))
    d.rectangle([0, int(H * 0.50), W, int(H * 0.53)], fill=tuple(mid) + (255,))
    im.alpha_composite(row_of([text_image("SUPER BOWL " + g["n"], WHITE)], W, int(H * 0.2), SCALE * 4, 0.7),
                       (0, int(H * 0.55)))
    im.alpha_composite(row_of([text_image("1ST & 10", tuple(acc) if lum(acc) > 60 else WHITE)], W, int(H * 0.2),
                              SCALE * 4, 0.7), (0, int(H * 0.76)))
    return im


def p_signs4(g, W, H, ctx):
    """Four sign bands (U.S. Bank's bowl signs): HOME OF SUPER BOWL LII, the numerals, the tag, the city."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    q = H // 4
    rows = [[text_image("HOME OF", tuple(mid)), text_image("SUPER BOWL " + g["n"], WHITE)],
            [sb_logo(g, q * 3), text_image("SUPER BOWL " + g["n"], WHITE), sb_logo(g, q * 3)],
            [text_image(g.get("tag", g["city"]), WHITE)],
            [text_image(g["city"], tuple(mid)), nfl_shield(q * 3, True), text_image(g["net"], WHITE)]]
    rows[1][0].info["h"] = rows[1][2].info["h"] = 0.94
    rows[3][1].info["h"] = 0.86
    d = ImageDraw.Draw(im)
    for k, items in enumerate(rows):
        if k % 2:
            d.rectangle([0, k * q, W, (k + 1) * q], fill=(4, 18, 44, 255))
        im.alpha_composite(row_of(items, W, q, SCALE * 8, 0.62), (0, k * q))
    return im


def p_prow(g, W, H, ctx):
    """A square display: the event mark on the event colour."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(H * 0.88), W, H], fill=tuple(mid) + (255,))
    logo = fit(sb_logo(g, H), W * 0.86, H * 0.78)
    paste_center(im, logo, W / 2, H * 0.44)
    tag = row_of([text_image(g.get("tag", g["city"]), dark if lum(mid) > 120 else WHITE)], W, int(H * 0.12),
                 SCALE * 4, 0.7)
    im.alpha_composite(tag, (0, int(H * 0.88)))
    return im


def p_vbanners(g, W, H, ctx):
    """Four banners from the roof (Lucas Oil's championship-banner cloths): the game's own event banners, the mark
    and the numerals on the event colour, a white border."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    d = ImageDraw.Draw(im)
    q = W // 4
    for k in range(4):
        x0 = k * q
        d.rectangle([x0 + SCALE * 2, SCALE * 2, x0 + q - SCALE * 2, H - SCALE * 2], outline=WHITE + (255,),
                    width=SCALE * 2)
        col = Image.new("RGBA", (q, H), (0, 0, 0, 0))
        if k % 2 == 0:
            logo = fit(sb_logo(g, H), q * 0.84, H * 0.56)
            paste_center(col, logo, q / 2, H * 0.36)
            word = row_of([text_image(g["n"], WHITE)], q, int(H * 0.2), SCALE * 3, 0.8)
            col.alpha_composite(word, (0, int(H * 0.70)))
        else:
            word = row_of([text_image("SUPER", WHITE)], q, int(H * 0.2), SCALE * 3, 0.7)
            col.alpha_composite(word, (0, int(H * 0.14)))
            word = row_of([text_image("BOWL", WHITE)], q, int(H * 0.2), SCALE * 3, 0.7)
            col.alpha_composite(word, (0, int(H * 0.36)))
            word = row_of([text_image(g["city"], tuple(mid))], q, int(H * 0.14), SCALE * 2, 0.7)
            col.alpha_composite(word, (0, int(H * 0.66)))
        im.alpha_composite(col, (x0, 0))
    return im


def p_screen(g, W, H, ctx):
    """SoFi's ring screen (512 x 64): the mark, SUPER BOWL LVI, the two teams and the city."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    d = ImageDraw.Draw(im)
    for k in range(H):
        t = k / H
        c = tuple(int(dark[i] * (1 - t) + mid[i] * t * 0.35 + dark[i] * t * 0.65) for i in range(3))
        d.line([(0, k), (W, k)], fill=c + (255,))
    away, home = g["away"], g["home"]
    items = [sb_logo(g, H * 3), text_image("SUPER BOWL " + g["n"], WHITE),
             text_image(team_name(away), contrast_on(dark, TEAMS[away][2], TEAMS[away][1])),
             text_image("VS", tuple(acc)), text_image(team_name(home), contrast_on(dark, TEAMS[home][1],
                                                                                  TEAMS[home][2])),
             text_image(g["city"], WHITE), sb_logo(g, H * 3)]
    items[0].info["h"] = items[-1].info["h"] = 0.92
    im.alpha_composite(row_of(items, W, H, SCALE * 8, 0.5), (0, 0))
    return im


def p_mesh(g, W, H, ctx):
    """Allegiant's mesh banner: the event words between the marks."""
    dark, mid, acc = g["pal"]
    im = Image.new("RGBA", (W, H), tuple(dark) + (255,))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=tuple(acc) + (255,))
    d.rectangle([0, H - int(H * 0.06), W, H], fill=tuple(acc) + (255,))
    items = [sb_logo(g, H * 3), text_image("SUPER BOWL " + g["n"], WHITE), text_image(g["city"], tuple(acc))]
    items[0].info["h"] = 0.86
    im.alpha_composite(row_of(items, W, H, SCALE * 8, 0.44), (0, 0))
    return im


def p_uop_name(g, W, H, ctx):
    """The stadium's name as it was in 2006-2017 (University of Phoenix Stadium), plain red type in two lines on the
    sign's transparent ground."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    red = (176, 20, 38)
    a = row_of([text_image("UNIVERSITY OF", red)], W, int(H * 0.46), SCALE * 4, 0.84)
    b = row_of([text_image("PHOENIX STADIUM", red)], W, int(H * 0.46), SCALE * 4, 0.84)
    im.alpha_composite(a, (0, int(H * 0.03)))
    im.alpha_composite(b, (0, int(H * 0.51)))
    return im


def wall_band(g, W, H, k):
    """One retail wall band: the event colour with soft cloth shading, a light rule at the top and the pad's dark
    trim at the bottom, carrying one of the event's word lines."""
    dark, mid, acc = g["pal"]
    im = cloth(W, H, dark, seed=k, folds=5)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.06)], fill=tuple(mid) + (255,))
    trim = int(H * 0.10)
    d.rectangle([0, H - trim, W, H], fill=(28, 30, 36, 255))
    modern = g["year"] >= 2008
    lines = [
        [sb_logo(g, H * 3), text_image("SUPER BOWL " + g["n"], WHITE), sb_logo(g, H * 3)],
        [nfl_shield(H * 3, modern), text_image(g["city"], WHITE), nfl_shield(H * 3, modern)],
        [sb_logo(g, H * 3), text_image(g.get("tag", "SUPER BOWL"), tuple(acc) if lum(acc) > 60 else WHITE),
         text_image(g["n"], WHITE), nfl_shield(H * 3, modern)],
    ]
    items = lines[k % len(lines)]
    for it in items:
        if it.width < it.height * 2.2:
            it.info["h"] = 0.92
    body = H - trim - int(H * 0.06)
    im.alpha_composite(row_of(items, W, body, SCALE * 8, 0.56), (0, int(H * 0.06)))
    return im


def p_bands2(g, W, H, ctx):
    """Two stacked wall bands (the retail field walls)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    for k in range(2):
        im.alpha_composite(wall_band(g, W, H // 2, ctx["variant"] * 2 + k), (0, k * (H // 2)))
    return im


def p_bands3(g, W, H, ctx):
    """Three stacked wall bands (the Georgia Dome's rings)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    q = H // 3
    for k in range(3):
        im.alpha_composite(wall_band(g, W, q if k < 2 else H - 2 * q, ctx["variant"] * 3 + k), (0, k * q))
    return im


def p_band(g, W, H, ctx):
    return wall_band(g, W, H, ctx["variant"])


def p_hang(g, W, H, ctx):
    """A tall hanging event banner: the mark over SUPER BOWL, the numerals and the city, a light border."""
    dark, mid, acc = g["pal"]
    im = cloth(W, H, dark, seed=ctx["variant"] + 3, folds=2)
    d = ImageDraw.Draw(im)
    b = max(SCALE, int(W * 0.04))
    d.rectangle([b, b, W - 1 - b, H - 1 - b], outline=tuple(mid) + (255,), width=b)
    paste_center(im, fit(sb_logo(g, H), W * 0.80, H * 0.50), W / 2, H * 0.32)
    im.alpha_composite(row_of([text_image(g["city"], WHITE)], W, int(H * 0.13), SCALE * 6, 0.8), (0, int(H * 0.62)))
    im.alpha_composite(row_of([text_image(str(g["year"]), tuple(acc) if lum(acc) > 60 else WHITE)], W, int(H * 0.11),
                              SCALE * 6, 0.8), (0, int(H * 0.78)))
    return im


def p_hang_wide(g, W, H, ctx):
    """A wide hanging event banner: the mark between SUPER BOWL and the city."""
    dark, mid, acc = g["pal"]
    im = cloth(W, H, dark, seed=ctx["variant"] + 5, folds=3)
    d = ImageDraw.Draw(im)
    d.rectangle([0, H - int(H * 0.12), W, H], fill=tuple(mid) + (255,))
    logo = sb_logo(g, H * 3)
    logo.info["h"] = 0.86
    items = [text_image("SUPER BOWL", WHITE), logo, text_image(g["city"], WHITE)]
    im.alpha_composite(row_of(items, W, int(H * 0.88), SCALE * 4, 0.34), (0, 0))
    return im


def p_word_event(g, W, H, ctx):
    """SUPER BOWL and the numerals in white type with a dark outline, on the surface's transparent ground."""
    dark = g["pal"][0]
    word = text_image("SUPER BOWL " + g["n"], WHITE, px=H * 2, stroke=max(2, H // 10), stroke_colour=dark)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    paste_center(im, fit(word, W * 0.96, H * 0.80), W / 2, H / 2)
    return im


def p_tile_logo(g, W, H, ctx):
    """A square cloth tile carrying the event mark."""
    im = cloth(W, H, g["pal"][0], seed=ctx["variant"] + 9)
    paste_center(im, fit(sb_logo(g, H), W * 0.86, H * 0.80), W / 2, H / 2)
    return im


def p_pad(g, W, H, ctx):
    """A square wall pad: the event colour, the mark and the numerals or the city beneath."""
    dark, mid, acc = g["pal"]
    im = cloth(W, H, dark, seed=ctx["variant"] + 11, folds=2)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(H * 0.05)], fill=tuple(mid) + (255,))
    d.rectangle([0, H - int(H * 0.05), W, H], fill=tuple(mid) + (255,))
    paste_center(im, fit(sb_logo(g, H), W * 0.84, H * 0.62), W / 2, H * 0.40)
    word = g["city"] if ctx["variant"] % 2 == 0 else str(g["year"])
    im.alpha_composite(row_of([text_image(word, WHITE)], W, int(H * 0.16), SCALE * 4, 0.8), (0, int(H * 0.76)))
    return im


def p_mark(g, W, H, ctx):
    """The event mark alone on the surface's transparent ground."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    paste_center(im, fit(sb_logo(g, H), W * 0.94, H * 0.94), W / 2, H / 2)
    return im


def p_shield_mark(g, W, H, ctx):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    paste_center(im, fit(nfl_shield(H, g["year"] >= 2008), W * 0.92, H * 0.92), W / 2, H / 2)
    return im


def p_flag(g, W, H, ctx):
    """A hanging cloth with a white border and the event mark."""
    im = cloth(W, H, g["pal"][0], seed=ctx["variant"] + 13)
    d = ImageDraw.Draw(im)
    b = max(SCALE, int(W * 0.04))
    d.rectangle([b, b, W - 1 - b, H - 1 - b], outline=WHITE + (255,), width=b)
    paste_center(im, fit(sb_logo(g, H), W * 0.78, H * 0.78), W / 2, H / 2)
    return im


def p_marquee(g, W, H, ctx):
    """The concourse marquee: amber dot-matrix-style type on black, WELCOME TO over SUPER BOWL and the numerals."""
    im = Image.new("RGBA", (W, H), (6, 6, 8, 255))
    amber = (236, 196, 64)
    im.alpha_composite(row_of([text_image("WELCOME TO", amber)], W, H // 2, SCALE * 4, 0.70), (0, 0))
    im.alpha_composite(row_of([text_image("SUPER BOWL " + g["n"], amber)], W, H // 2, SCALE * 4, 0.70), (0, H // 2))
    a = np.asarray(im).copy()
    a[::SCALE, :, :3] = (a[::SCALE, :, :3] * 0.55).astype(np.uint8)
    a[:, ::SCALE, :3] = (a[:, ::SCALE, :3] * 0.55).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def p_nrg_name(g, W, H, ctx):
    """The stadium's name from 2014 (NRG Stadium), plain cream type in two lines on the sign's transparent ground."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cream = (244, 238, 214)
    im.alpha_composite(row_of([text_image("NRG", cream)], W, int(H * 0.50), SCALE * 4, 0.86), (0, 0))
    im.alpha_composite(row_of([text_image("STADIUM", cream)], W, int(H * 0.46), SCALE * 4, 0.86), (0, int(H * 0.52)))
    return im


# --- the crowd banners: tiles measured from the source texture's alpha -----------------------------------------

def tiles(alpha, scale):
    """Bounding boxes (x0, y0, x1, y1) of the opaque cloth tiles of a source texture, at master scale, in reading
    order. Author-time only (scipy)."""
    from scipy import ndimage
    mask = alpha > 96
    lab, count = ndimage.label(mask)
    boxes = []
    for sl in ndimage.find_objects(lab):
        y, x = sl
        if (x.stop - x.start) * (y.stop - y.start) < 120:
            continue
        boxes.append((x.start, y.start, x.stop, y.stop))
    boxes.sort(key=lambda b: (round(b[1] / 16), b[0]))
    pad = 2
    return [(max(0, (x0 - pad)) * scale, max(0, (y0 - pad)) * scale, (x1 + pad) * scale, (y1 + pad) * scale)
            for x0, y0, x1, y1 in boxes]


def corp_designs(g):
    """The event's banner set: the mark, the league, the broadcaster, the city and the numerals."""
    dark, mid, acc = g["pal"]
    modern = g["year"] >= 2008

    def logo_tile(w, h, k):
        c = cloth(w, h, dark, seed=k)
        paste_center(c, fit(sb_logo(g, h), w * 0.88, h * 0.86), w / 2, h / 2)
        return c

    def words_tile(words, bg, fg):
        def make(w, h, k):
            c = cloth(w, h, bg, seed=k)
            lines = len(words)
            for i, word in enumerate(words):
                band = row_of([text_image(word, fg)], w, int(h / lines * 0.9), SCALE * 4, 0.74)
                c.alpha_composite(band, (0, int(h * (0.05 + i / lines * 0.92))))
            return c
        return make

    def shield_tile(w, h, k):
        c = cloth(w, h, (246, 246, 246), seed=k)
        paste_center(c, fit(nfl_shield(h, modern), w * 0.8, h * 0.84), w / 2, h / 2)
        return c

    wide = [logo_tile, words_tile(["SUPER BOWL", g["n"]], mid if lum(mid) < 200 else dark, WHITE),
            words_tile([g["net"]], (246, 246, 246), dark), words_tile([g["city"]], dark, WHITE),
            words_tile([g.get("tag", "NFL")], mid if lum(mid) < 200 else dark, WHITE), logo_tile]
    small = [shield_tile, words_tile([g["n"]], dark, WHITE), logo_tile, words_tile([g["net"]], dark, WHITE),
             shield_tile, words_tile(["NFL"], (246, 246, 246), (1, 51, 105))]
    return wide, small


def fan_designs(g, code):
    name, c1, c2 = TEAMS[code]
    phrases = g["fans"][code]
    out = []
    for k, phrase in enumerate(phrases):
        bg, fg = (c1, contrast_on(c1, c2)) if k == 0 else ((246, 246, 246), c1 if lum(c1) < 200 else c2)

        def make(w, h, seed, phrase=phrase, bg=bg, fg=fg):
            c = cloth(w, h, bg, seed=seed)
            words = phrase.split(" ")
            lines = [phrase] if len(phrase) <= 10 or len(words) == 1 else [
                " ".join(words[:len(words) // 2]), " ".join(words[len(words) // 2:])]
            for i, line in enumerate(lines):
                band = row_of([text_image(line, fg)], w, int(h / len(lines) * 0.86), SCALE * 4, 0.76)
                c.alpha_composite(band, (0, int(h * (0.06 + i / len(lines) * 0.9))))
            return c
        out.append(make)
    return out


def player_designs(g):
    out = []
    teams = (g["home"], g["home"], g["away"], g["away"])
    for k, ((num, name), code) in enumerate(zip(g["players"], teams)):
        _, c1, c2 = TEAMS[code]
        bg, fg = (c1, contrast_on(c1, c2)) if k % 2 == 0 else ((246, 246, 246), c1 if lum(c1) < 200 else c2)

        def make(w, h, seed, num=num, name=name, bg=bg, fg=fg):
            c = cloth(w, h, bg, seed=seed)
            a = row_of([text_image(num, fg)], w, int(h * 0.44), SCALE * 4, 0.8)
            b = row_of([text_image(name, fg)], w, int(h * 0.40), SCALE * 4, 0.74)
            c.alpha_composite(a, (0, int(h * 0.06)))
            c.alpha_composite(b, (0, int(h * 0.52)))
            return c
        out.append(make)
    return out


def paint_tiles(W, H, boxes, designs):
    """Designs into the measured tiles; the space between stays a neutral cloth grey (the compiler's alpha hides it)."""
    im = Image.new("RGBA", (W, H), (200, 200, 200, 255))
    for k, (x0, y0, x1, y1) in enumerate(boxes):
        if callable(designs):
            make = designs(k, x1 - x0, y1 - y0)
        else:
            make = designs[k % len(designs)]
        im.alpha_composite(make(x1 - x0, y1 - y0, k + 7), (x0, y0))
    return im


def p_corp(g, W, H, ctx):
    wide, small = corp_designs(g)
    counters = dict(w=0, s=0)

    def choose(k, w, h):
        key = "w" if w > h * 1.4 else "s"
        pool = wide if key == "w" else small
        f = pool[counters[key] % len(pool)]
        counters[key] += 1
        return lambda ww, hh, seed: f(ww, hh, seed)
    return paint_tiles(W, H, ctx["tiles"], choose)


def p_fans_home(g, W, H, ctx):
    return paint_tiles(W, H, ctx["tiles"], fan_designs(g, g["home"]))


def p_fans_away(g, W, H, ctx):
    return paint_tiles(W, H, ctx["tiles"], fan_designs(g, g["away"]))


def p_players(g, W, H, ctx):
    return paint_tiles(W, H, ctx["tiles"], player_designs(g))


PAINTERS = {k[2:]: v for k, v in globals().items() if k.startswith("p_")}


def targets(row, source_kind, source_prefix):
    """{material: (painter, alpha)} for one Super Bowl row."""
    out = dict(BANNERS)
    out.update(VENUES.get((source_kind, source_prefix), {}))
    return out


def reduce(master, size):
    return master.resize(size, Image.LANCZOS)


def main(argv=None):
    import sys
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--extract", required=True, help="native stadium textures of the 17 aliases (author time only)")
    ap.add_argument("--masters")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    catalog = json.loads((Path(__file__).resolve().parents[1] / "data/nfl2k5_espn25_fields.json").read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    masters = Path(a.masters) if a.masters else None
    extract = Path(a.extract)
    rows = []
    for m in catalog["moments"]:
        if not m.get("super_bowl") or m["row"] not in GAMES:
            continue
        g = GAMES[m["row"]]
        if g["n"] != m["super_bowl"]:
            raise SystemExit(f"row {m['row']}: event {g['n']} != catalog {m['super_bowl']}")
        alias_dir = next(extract.glob(f"a{m['row'] - 1:02d}*"))
        entries = []
        for variant, (material, spec) in enumerate(targets(m["row"], m["source_kind"],
                                                           m["source_prefix"]).items()):
            found = sorted(p for p in alias_dir.glob("stadium_*.png") if p.stem.split("_t", 1)[1].split("_", 1)[1]
                           == material)
            if len(found) != 1:
                raise SystemExit(f"row {m['row']}: {material} found {len(found)} times in {alias_dir}")
            src = Image.open(found[0]).convert("RGBA")
            size = src.size
            if isinstance(spec[1], list):
                alpha, areas = spec
            else:
                painter, alpha = spec
                areas = [((0, 0) + tuple(size), painter)]
            native = Image.new("RGBA", size, (0, 0, 0, 0))
            for k, (box, painter) in enumerate(areas):
                x0, y0, x1, y1 = box
                if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
                    raise SystemExit(f"row {m['row']}: {material} area {box} outside {size}")
                ctx = {"variant": variant + k}
                if alpha == "source":
                    ctx["tiles"] = tiles(np.asarray(src)[y0:y1, x0:x1, 3], SCALE)
                master = PAINTERS[painter](g, (x1 - x0) * SCALE, (y1 - y0) * SCALE, ctx)
                part = reduce(master, (x1 - x0, y1 - y0))
                if alpha in ("source", "opaque"):
                    part.putalpha(255)
                native.paste(part, (x0, y0))
                if masters:
                    (masters / f"row{m['row']:02d}").mkdir(parents=True, exist_ok=True)
                    master.save(masters / f"row{m['row']:02d}" / f"{material}_{k}.png", optimize=True)
            rel = f"row{m['row']:02d}/{material}.png"
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            native.save(path, optimize=True)
            entry = dict(material=material, file=rel, size=list(size), alpha=alpha,
                         painter="+".join(p for _, p in areas), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            if areas[0][0] != (0, 0) + tuple(size) or len(areas) > 1:
                entry["areas"] = [list(box) for box, _ in areas]
            entries.append(entry)
        rows.append(dict(row=m["row"], event=g["n"], date=m["date"], venue=m["venue"], city=g["city"],
                         network=g["net"], source_kind=m["source_kind"], source_prefix=m["source_prefix"],
                         textures=entries))
        print(m["row"], g["n"], len(entries), flush=True)
    doc = dict(schema="nfl2k5_super_bowl_walls/v1", held_rows=[34],
               note="Authored event surfaces; permanent venue signs keep their bytes. Row 34 is held unchanged.",
               rows=rows)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", newline="\n")
    print("SUPER_BOWL_WALLS_ART_OK", sum(len(r["textures"]) for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
