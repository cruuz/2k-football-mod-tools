#!/usr/bin/env python3
"""Super Bowl event walls for the Anniversary stadium aliases (me1 N06, redesigned by sb2): deterministic drawings at
4x masters reduced to each surface's native size.

Every Super Bowl moment keeps its venue model and its permanent venue signs, and its temporary surfaces (the field
wall, the ribbon boards, the board wings, the hanging banners and the crowd's banners) carry that game's event
dressing. The design is original: an authored event plate (a chamfered championship plate with the game's numerals in
chrome, a host-colour treatment or a 1990s block serif, by era), condensed broadcast type with metal numerals,
gradients, sheen and cloth folds, ribbon boards laid out as event and matchup bands, and the host city and network.
No Super Bowl or broadcaster logo is copied or traced; the network appears as plain type in a chip.

Each surface is written as two PNGs: the base (background, type, plates) and a layer with the authored marks of its
slots. The manifest lists the slots (``shield``, ``event``, ``brand``, ``team``) with their boxes. At build time
``mod_editor/core/nfl2k5_super_bowl_walls.py`` puts the season's NFL shield in every shield slot (the mod's official
2008 shield, or the period shield from the user's retail disc) and fills the other slots from the authored layer or
from the user's own optional folder. Team slots carry the mod's own team logos
(``data/nfl2k5_scorebug_assets/logos``, baked here at the native slot size) or the team name where the mod has no
logo of that season.

    python3 tools/nfl2k5_super_bowl_walls_art.py OUT_DIR --extract SB_EXTRACT_DIR [--masters DIR]

``--extract`` (author time only) is a folder of the 17 aliases' native stadium textures, used to measure tile
rectangles; no pixel of it is written to OUT_DIR.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_super_bowl_walls as walls  # noqa: E402

SCALE = 4
FONT_DIR = Path("/usr/share/fonts/truetype/roboto/unhinted")
COND = FONT_DIR / "RobotoCondensed-Bold.ttf"
COND_IT = FONT_DIR / "RobotoCondensed-BoldItalic.ttf"
BLACK = FONT_DIR / "RobotoTTF/Roboto-Black.ttf"
BLACK_IT = FONT_DIR / "RobotoTTF/Roboto-BlackItalic.ttf"
SERIF = Path("/usr/share/fonts/opentype/urw-base35/URWBookman-Demi.otf")
LOGOS = ROOT / "data/nfl2k5_scorebug_assets/logos"
WHITE = (255, 255, 255)
BLACKC = (0, 0, 0)

# --- the games ------------------------------------------------------------------------------------------------------
#: code -> (display name, primary, secondary, mod logo file or None). Colours are the season's.
TEAMS = {
    "SF": ("49ERS", (170, 0, 0), (179, 153, 93), "sf"), "CIN": ("BENGALS", (251, 79, 20), (16, 16, 16), "cin"),
    "BUF": ("BILLS", (0, 51, 141), (198, 12, 48), "buf"), "NYG": ("GIANTS", (11, 34, 101), (167, 25, 48), "nyg"),
    "GB": ("PACKERS", (24, 48, 40), (255, 184, 28), "gb"), "DEN": ("BRONCOS", (0, 34, 68), (251, 79, 20), "den"),
    "STL": ("RAMS", (0, 35, 85), (200, 170, 90), None), "TEN": ("TITANS", (12, 35, 64), (75, 146, 219), "ten"),
    "NE": ("PATRIOTS", (0, 34, 68), (198, 12, 48), "ne"), "PIT": ("STEELERS", (16, 16, 16), (255, 182, 18), "pit"),
    "ARI": ("CARDINALS", (151, 35, 63), (255, 255, 255), "ari"), "IND": ("COLTS", (0, 44, 95), (255, 255, 255), "ind"),
    "NO": ("SAINTS", (16, 16, 16), (211, 188, 141), "no"), "BAL": ("RAVENS", (36, 23, 115), (158, 124, 12), "bal"),
    "SEA": ("SEAHAWKS", (0, 34, 68), (105, 190, 40), "sea"), "ATL": ("FALCONS", (167, 25, 48), (16, 16, 16), "atl"),
    "PHI": ("EAGLES", (0, 76, 84), (165, 172, 175), "phi"), "KC": ("CHIEFS", (227, 24, 55), (255, 184, 28), "kc"),
    "LAR": ("RAMS", (0, 53, 148), (255, 209, 0), "lar"),
}
#: (row, team) whose logo that season is not the one the mod carries: the authored team name shows instead
PERIOD_LOGO_GAPS = {(14, "CIN"): "the 1988 Bengals logo", (15, "NYG"): "the 1990 Giants logo",
                    (22, "STL"): "the 1999 Rams logo", (23, "STL"): "the 2001 Rams logo"}
#: season colours that differ from the table above
SEASON_COLOURS = {(15, "NYG"): ((1, 35, 82), (167, 25, 48)), (22, "STL"): ((0, 51, 160), (255, 205, 0))}

#: row -> event. ``style``: classic (before 2008: a block-serif plate with stars), host (2008-2015: the host city's
#: colours sweep through the plate) or standard (2017 on: chrome numerals on a dark plate). ``pal`` = (dark, mid,
#: accent) of the event dressing; ``motif`` is the background accent.
GAMES = {
    14: dict(n="XXIII", city="MIAMI", net="NBC", year=1989, style="classic", away="CIN", home="SF", motif="sun",
             pal=((14, 40, 92), (0, 140, 150), (240, 120, 30)),
             fans={"SF": ("GO NINERS!", "SF FAITHFUL"), "CIN": ("WHO DEY!", "GO BENGALS")},
             players=(("#16", "MONTANA"), ("#80", "RICE"), ("#7", "ESIASON"), ("#30", "ICKEY"))),
    15: dict(n="XXV", city="TAMPA", net="ABC", year=1991, style="classic", away="BUF", home="NYG", motif="stars",
             pal=((18, 32, 92), (200, 20, 40), (255, 255, 255)), stars=True,
             fans={"NYG": ("GO BIG BLUE!", "GIANTS PRIDE"), "BUF": ("GO BILLS!", "SHOUT!")},
             players=(("#24", "O.J. ANDERSON"), ("#56", "L.T."), ("#12", "KELLY"), ("#34", "THURMAN"))),
    21: dict(n="XXXII", city="SAN DIEGO", net="NBC", year=1998, style="classic", away="GB", home="DEN", motif="waves",
             pal=((10, 36, 82), (226, 168, 40), (0, 128, 140)),
             fans={"DEN": ("GO BRONCOS!", "ORANGE CRUSH"), "GB": ("GO PACK GO!", "CHEESEHEADS")},
             players=(("#7", "ELWAY"), ("#30", "T.D."), ("#4", "FAVRE"), ("#92", "REGGIE"))),
    22: dict(n="XXXIV", city="ATLANTA", net="ABC", year=2000, style="classic", away="STL", home="TEN", motif="sun",
             pal=((118, 18, 32), (214, 164, 52), (40, 40, 48)),
             fans={"TEN": ("TITANS!", "GO TITANS"), "STL": ("GO RAMS!", "RAMS RULE")},
             players=(("#9", "McNAIR"), ("#27", "EDDIE"), ("#13", "WARNER"), ("#28", "FAULK"))),
    23: dict(n="XXXVI", city="NEW ORLEANS", net="FOX", year=2002, style="classic", away="STL", home="NE",
             motif="stars", pal=((16, 32, 96), (196, 20, 40), (255, 255, 255)), stars=True,
             fans={"NE": ("GO PATS!", "PATRIOTS"), "STL": ("GO RAMS!", "GREATEST SHOW")},
             players=(("#12", "BRADY"), ("#4", "VINATIERI"), ("#13", "WARNER"), ("#28", "FAULK"))),
    27: dict(n="XLII", city="GLENDALE", net="FOX", year=2008, style="host", away="NYG", home="NE", motif="sun",
             pal=((22, 30, 68), (178, 44, 30), (226, 172, 92)),
             fans={"NE": ("GO PATS!", "PATRIOTS NATION"), "NYG": ("GO BIG BLUE!", "G-MEN")},
             players=(("#12", "BRADY"), ("#81", "MOSS"), ("#10", "ELI"), ("#92", "STRAHAN"))),
    28: dict(n="XLIII", city="TAMPA", net="NBC", year=2009, style="host", away="PIT", home="ARI", motif="waves",
             pal=((10, 42, 78), (0, 120, 140), (240, 112, 34)),
             fans={"ARI": ("GO CARDS!", "BIRD GANG"), "PIT": ("STEELER NATION", "HERE WE GO!")},
             players=(("#13", "WARNER"), ("#11", "FITZGERALD"), ("#7", "BIG BEN"), ("#43", "TROY"))),
    29: dict(n="XLVI", city="INDIANAPOLIS", net="NBC", year=2012, style="host", away="NYG", home="NE", motif="checker",
             pal=((10, 34, 86), (34, 92, 172), (196, 202, 208)),
             fans={"NE": ("GO PATS!", "PATRIOTS NATION"), "NYG": ("GO BIG BLUE!", "G-MEN")},
             players=(("#12", "BRADY"), ("#87", "GRONK"), ("#10", "ELI"), ("#80", "CRUZ"))),
    30: dict(n="LI", city="HOUSTON", net="FOX", year=2017, style="standard", away="NE", home="ATL", motif="stars",
             pal=((12, 30, 62), (190, 30, 46), (196, 202, 208)),
             fans={"ATL": ("RISE UP!", "GO FALCONS"), "NE": ("GO PATS!", "PATRIOTS NATION")},
             players=(("#2", "MATT RYAN"), ("#11", "JULIO"), ("#12", "BRADY"), ("#11", "EDELMAN"))),
    35: dict(n="XLIV", city="SOUTH FLORIDA", net="CBS", year=2010, style="host", away="NO", home="IND", motif="waves",
             pal=((10, 42, 82), (0, 148, 160), (245, 122, 32)),
             fans={"IND": ("GO COLTS!", "BLUE CREW"), "NO": ("WHO DAT!", "GEAUX SAINTS")},
             players=(("#18", "MANNING"), ("#87", "WAYNE"), ("#9", "BREES"), ("#12", "COLSTON"))),
    40: dict(n="XLVII", city="NEW ORLEANS", net="CBS", year=2013, style="host", away="BAL", home="SF", motif="none",
             pal=((62, 32, 108), (0, 110, 80), (226, 182, 72)),
             fans={"SF": ("GO NINERS!", "FAITHFUL"), "BAL": ("RAVENS NATION", "GO RAVENS!")},
             players=(("#7", "KAEPERNICK"), ("#21", "GORE"), ("#5", "FLACCO"), ("#52", "RAY LEWIS"))),
    42: dict(n="XLIX", city="ARIZONA", net="NBC", year=2015, style="host", away="NE", home="SEA", motif="sun",
             pal=((70, 34, 86), (206, 64, 30), (246, 182, 40)),
             fans={"SEA": ("12TH MAN", "GO HAWKS!"), "NE": ("GO PATS!", "PATRIOTS NATION")},
             players=(("#3", "WILSON"), ("#24", "BEAST MODE"), ("#12", "BRADY"), ("#87", "GRONK"))),
    45: dict(n="LII", city="MINNEAPOLIS", net="NBC", year=2018, style="standard", away="PHI", home="NE",
             motif="snow", pal=((8, 30, 70), (118, 186, 226), (255, 255, 255)), tag="BOLD NORTH",
             fans={"NE": ("GO PATS!", "PATRIOTS NATION"), "PHI": ("FLY EAGLES FLY", "GO BIRDS!")},
             players=(("#12", "BRADY"), ("#87", "GRONK"), ("#9", "FOLES"), ("#86", "ERTZ"))),
    46: dict(n="LIV", city="MIAMI", net="FOX", year=2020, style="standard", away="SF", home="KC", motif="waves",
             pal=((18, 30, 52), (0, 150, 160), (238, 90, 150)),
             fans={"KC": ("CHIEFS KINGDOM", "GO CHIEFS!"), "SF": ("GO NINERS!", "FAITHFUL")},
             players=(("#15", "MAHOMES"), ("#87", "KELCE"), ("#85", "KITTLE"), ("#97", "BOSA"))),
    48: dict(n="LVI", city="LOS ANGELES", net="NBC", year=2022, style="standard", away="LAR", home="CIN", motif="sun",
             pal=((44, 20, 82), (246, 122, 40), (226, 76, 122)),
             fans={"CIN": ("WHO DEY!", "RULE THE JUNGLE"), "LAR": ("RAMS HOUSE", "WHOSE HOUSE?")},
             players=(("#9", "BURROW"), ("#1", "CHASE"), ("#10", "KUPP"), ("#99", "DONALD"))),
    50: dict(n="LVIII", city="LAS VEGAS", net="CBS", year=2024, style="standard", away="SF", home="KC", motif="neon",
             pal=((16, 16, 20), (200, 26, 36), (212, 172, 72)),
             fans={"KC": ("CHIEFS KINGDOM", "GO CHIEFS!"), "SF": ("GO NINERS!", "FAITHFUL")},
             players=(("#15", "MAHOMES"), ("#87", "KELCE"), ("#13", "PURDY"), ("#23", "CMC"))),
}
for _row, _g in GAMES.items():
    _g["row"] = _row
    _g["season"] = _g["year"] - 1

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


# --- drawing kit ---------------------------------------------------------------------------------------------------

def font(path, px):
    return ImageFont.truetype(str(path), max(4, int(px)))


def text_mask(word, px=200, path=COND, tracking=0.0):
    """L mask of a word, tight-cropped; ``tracking`` in em."""
    f = font(path, px)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    widths = [probe.textlength(c, font=f) for c in word]
    total = sum(widths) + tracking * px * max(0, len(word) - 1)
    asc, desc = f.getmetrics()
    m = Image.new("L", (int(total + 32), asc + desc + 16), 0)
    d = ImageDraw.Draw(m)
    if tracking == 0:
        d.text((16, 8), word, font=f, fill=255)
    else:
        x = 16.0
        for c, w in zip(word, widths):
            d.text((x, 8), c, font=f, fill=255)
            x += w + tracking * px
    return m.crop(m.getbbox())


def solid(mask, colour):
    im = Image.new("RGBA", mask.size, tuple(colour[:3]) + (255,))
    im.putalpha(mask)
    return im


def vgrad(W, H, stops):
    """RGBA vertical gradient through [(t, (r, g, b)), ...]."""
    t = np.linspace(0, 1, max(1, H))
    ts = [s[0] for s in stops]
    cols = np.array([s[1][:3] for s in stops], float)
    rgb = np.stack([np.interp(t, ts, cols[:, i]) for i in range(3)], 1)
    a = np.repeat(rgb[:, None, :], W, 1)
    return Image.fromarray(np.dstack([a.clip(0, 255).astype(np.uint8), np.full((H, W), 255, np.uint8)]), "RGBA")


def hgrad(W, H, stops):
    t = np.linspace(0, 1, max(1, W))
    ts = [s[0] for s in stops]
    cols = np.array([s[1][:3] for s in stops], float)
    rgb = np.stack([np.interp(t, ts, cols[:, i]) for i in range(3)], 1)
    a = np.repeat(rgb[None, :, :], H, 0)
    return Image.fromarray(np.dstack([a.clip(0, 255).astype(np.uint8), np.full((H, W), 255, np.uint8)]), "RGBA")


def fill_mask(mask, fill_img):
    out = fill_img.resize(mask.size) if fill_img.size != mask.size else fill_img.copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), mask))
    return out


METALS = {
    "chrome": [(0.0, (252, 253, 255)), (0.44, (204, 210, 219)), (0.50, (112, 120, 134)), (0.60, (170, 177, 189)),
               (1.0, (238, 241, 246))],
    "gold": [(0.0, (255, 243, 196)), (0.44, (234, 192, 96)), (0.50, (146, 100, 28)), (0.60, (204, 156, 60)),
             (1.0, (252, 226, 146))],
    "white": [(0.0, (255, 255, 255)), (1.0, (222, 227, 234))],
}


def metal(mask, kind="chrome"):
    stops = METALS[kind] if isinstance(kind, str) else kind
    return fill_mask(mask, vgrad(mask.width, mask.height, stops))


def grow(mask, r):
    if r <= 0:
        return mask
    pad = Image.new("L", (mask.width + 2 * r, mask.height + 2 * r), 0)
    pad.paste(mask, (r, r))
    return pad.filter(ImageFilter.MaxFilter(2 * r + 1))


def shrink(mask, r):
    """Erode a mask, treating outside the canvas as empty."""
    if r <= 0:
        return mask
    pad = Image.new("L", (mask.width + 2 * r, mask.height + 2 * r), 0)
    pad.paste(mask, (r, r))
    return pad.filter(ImageFilter.MinFilter(2 * r + 1)).crop((r, r, r + mask.width, r + mask.height))


def outline(im, colour, r):
    """A stroke behind an RGBA (dilated alpha); the canvas grows by r."""
    if r <= 0:
        return im
    back = solid(grow(im.getchannel("A"), r), colour)
    back.alpha_composite(im, (r, r))
    return back


def shadow(im, dx, dy, blur, opacity=0.6, colour=BLACKC):
    """The image over its soft drop shadow (the canvas grows to hold the shadow, centred on the image)."""
    pad = blur * 2 + max(abs(dx), abs(dy))
    W, H = im.width + 2 * pad, im.height + 2 * pad
    a = Image.new("L", (W, H), 0)
    a.paste(im.getchannel("A"), (pad + dx, pad + dy))
    if blur:
        a = a.filter(ImageFilter.GaussianBlur(blur))
    a = a.point(lambda v: int(v * opacity))
    out = solid(a, colour)
    out.alpha_composite(im, (pad, pad))
    return out


def fit(im, w, h):
    f = min(w / im.width, h / im.height)
    return im.resize((max(1, round(im.width * f)), max(1, round(im.height * f))), Image.LANCZOS)


def fit_h(im, h):
    return im.resize((max(1, round(im.width * h / im.height)), max(1, round(h))), Image.LANCZOS)


def paste_c(canvas, im, cx, cy):
    canvas.alpha_composite(im, (int(round(cx - im.width / 2)), int(round(cy - im.height / 2))))


def chamfer(W, H, c):
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([(c, 0), (W - 1 - c, 0), (W - 1, c), (W - 1, H - 1 - c), (W - 1 - c, H - 1),
                               (c, H - 1), (0, H - 1 - c), (0, c)], fill=255)
    return m


def poly_mask(W, H, pts):
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m


def sheen(W, H, strength=0.16, centre=0.32, width=0.22):
    """A soft diagonal light band (white with alpha)."""
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    u = xx / max(1, W) + (yy / max(1, H)) * 0.35
    d = np.exp(-((u - centre) / width) ** 2)
    a = (d * strength * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(np.dstack([np.full((H, W, 3), 255, np.uint8), a]), "RGBA")


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def mix(a, b, t):
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))


def darker(c, t=0.35):
    return mix(c, BLACKC, t)


def lighter(c, t=0.25):
    return mix(c, WHITE, t)


def contrast_on(bg, a, b=WHITE):
    return a if abs(lum(a) - lum(bg)) > abs(lum(b) - lum(bg)) else b


def star_pts(cx, cy, r, ratio=0.42):
    pts = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * ratio
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts


def cloth_shade(W, H, seed=0, folds=3):
    """(H, W) brightness of a hanging cloth: soft vertical folds and a drape across the top."""
    x = np.linspace(0, 1, W)[None, :]
    y = np.linspace(0, 1, H)[:, None]
    r = np.random.default_rng(seed)
    phase = r.uniform(0, math.tau)
    shade = 1 + 0.07 * np.sin(x * math.tau * folds + phase) + 0.03 * np.sin(x * math.tau * (folds * 2.3) + phase * 2)
    shade = shade - 0.08 * np.exp(-((y - 0.04) / 0.08) ** 2) * (0.5 + 0.5 * np.cos(x * math.tau * 2))
    return shade * (0.95 + 0.05 * y)


def apply_shade(im, shade):
    a = np.asarray(im).astype(np.float32)
    a[..., :3] = np.clip(a[..., :3] * shade[..., None], 0, 255)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def cloth(W, H, colour, seed=0, folds=3):
    base = Image.new("RGBA", (W, H), tuple(colour) + (255,))
    return apply_shade(base, cloth_shade(W, H, seed, folds))


# --- event identity --------------------------------------------------------------------------------------------------

def numeral_colour(g):
    """The host style's numeral colour: the lightest of the event's two accents."""
    dark, mid, acc = g["pal"]
    return max((mid, acc), key=lum)


def numerals(g, H, on=None):
    """The game's Roman numerals at cap height H with depth: chrome (2017 on), the host colour (2008-2015) or a block
    serif with an extruded shadow and gold keyline (before 2008)."""
    H = max(4, int(round(H)))
    dark, mid, acc = g["pal"]
    r = max(1, H // 36)
    if g["style"] == "classic":
        m = text_mask(g["n"], H * 1.6, SERIF)
        m = m.resize((int(m.width * H / m.height * 0.80), H), Image.LANCZOS)  # condensed by 20 percent
        face = metal(m, "white")
        depth = r * 3
        ext = Image.new("RGBA", (m.width + depth + 1, m.height + depth + 1), (0, 0, 0, 0))
        block = solid(m, darker(mid, 0.30))
        for k in range(depth, 0, -1):
            ext.alpha_composite(block, (k, k))
        ext.alpha_composite(face, (0, 0))
        return outline(ext, (250, 226, 150) if lum(on or dark) < 140 else darker(dark, 0.4), r)
    m = fit_h(text_mask(g["n"], H * 1.5, COND), H)
    if g["style"] == "host":
        c = numeral_colour(g)
        face = metal(m, [(0, lighter(c, 0.60)), (0.46, lighter(c, 0.10)), (0.50, darker(c, 0.25)),
                         (0.62, c), (1, lighter(c, 0.30))])
    else:
        face = metal(m, "chrome")
    face = outline(face, darker(dark, 0.55), r)
    return shadow(face, r, 2 * r, 2 * r, 0.65)


def emblem(g, H, variant="full"):
    """The game's event plate, an original design: a chamfered championship plate with a metal rim, the event's
    gradient field and sheen, SUPER BOWL across the top, the numerals at the centre and the host city and year on a
    ribbon. ``compact`` drops the ribbon; ``mini`` keeps only the plate and the numerals."""
    H = max(4, int(round(H)))
    dark, mid, acc = g["pal"]
    style = g["style"]
    W = int(H * (1.42 if variant != "mini" else 1.34))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cut = int(H * 0.16)
    rim = max(2, int(H * 0.045))
    outer = chamfer(W, H, cut)
    inner = shrink(outer, rim)
    im.alpha_composite(metal(outer, "gold" if style == "classic" else "chrome"))
    deep = darker(dark, 0.45)
    field = vgrad(W, H, [(0, mix(dark, mid, 0.20)), (0.55, dark), (1, deep)])
    if style == "host":
        field.alpha_composite(fill_mask(poly_mask(W, H, [(0, H * 0.60), (W * 0.64, H), (0, H)]),
                                        vgrad(W, H, [(0, mid), (1, darker(mid, 0.4))])))
        field.alpha_composite(fill_mask(poly_mask(W, H, [(0, H * 0.50), (0, H * 0.555), (W * 0.70, H), (W * 0.62, H)]),
                                        vgrad(W, H, [(0, acc), (1, darker(acc, 0.3))])))
    elif style == "classic":
        for k, c in enumerate((mid, acc)):
            y0 = H * (0.66 + 0.035 * k)
            field.alpha_composite(fill_mask(poly_mask(W, H, [(0, y0), (W, y0), (W, y0 + H * 0.022), (0, y0 + H * 0.022)]),
                                            Image.new("RGBA", (W, H), tuple(c) + (255,))))
    field.alpha_composite(sheen(W, H, 0.15, 0.30, 0.22))
    im.alpha_composite(fill_mask(inner, field))
    key = ImageChops.subtract(inner, shrink(inner, max(1, H // 90)))
    im.alpha_composite(solid(key, (255, 236, 170) if style == "classic" else lighter(mid, 0.35)))
    if variant == "mini":
        paste_c(im, fit(numerals(g, int(H * 0.6)), W * 0.82, H * 0.70), W / 2, H * 0.50)
        return im
    if style == "classic":
        band = ImageChops.multiply(poly_mask(W, H, [(0, H * 0.08), (W, H * 0.08), (W, H * 0.29), (0, H * 0.29)]), inner)
        im.alpha_composite(fill_mask(band, vgrad(W, H, [(0, lighter(mid, 0.1)), (1, darker(mid, 0.25))])))
        sb = solid(text_mask("SUPER BOWL", 200, COND, 0.10), WHITE)
        paste_c(im, fit(sb, W * 0.62, H * 0.13), W / 2, H * 0.185)
    else:
        sb = solid(text_mask("SUPER BOWL", 200, COND, 0.16), WHITE)
        paste_c(im, fit(sb, W * 0.60, H * 0.115), W / 2, H * 0.19)
        rule = Image.new("RGBA", (int(W * 0.44), max(1, int(H * 0.02))), tuple(acc if style == "host" else mid) + (255,))
        paste_c(im, rule, W / 2, H * 0.275)
    ny = H * (0.55 if variant == "full" else 0.60)
    nh = H * (0.38 if variant == "full" else 0.46)
    num = numerals(g, int(H * 0.5))
    paste_c(im, fit(num, W * (0.70 if style == "classic" else 0.78), nh), W / 2, ny)
    if style == "classic" or g.get("stars"):
        d = ImageDraw.Draw(im)
        for sx in (W * 0.115, W * 0.885):
            d.polygon(star_pts(sx, ny, H * 0.05), fill=(255, 236, 170, 255) if style == "classic" else WHITE + (255,))
    if variant == "full":
        rib = ImageChops.multiply(poly_mask(W, H, [(0, H * 0.80), (W, H * 0.80), (W, H * 0.915), (0, H * 0.915)]), inner)
        im.alpha_composite(fill_mask(rib, vgrad(W, H, [(0, lighter(mid, 0.12)), (1, mid)])))
        city = solid(text_mask(f"{g['city']}  {g['year']}", 200, COND, 0.12), WHITE if lum(mid) < 150 else dark)
        paste_c(im, fit(city, W * 0.72, H * 0.075), W / 2, H * 0.858)
    return im


def emblem_for(g, w, h):
    """The event plate variant that reads at a native box of h texels."""
    native = h / SCALE
    variant = "full" if native >= 44 else "compact" if native >= 24 else "mini"
    return fit(emblem(g, int(h * 1.6), variant), w, h)


def word(text, H, colour=WHITE, path=COND, tracking=0.02, stroke=0, stroke_colour=BLACKC, depth=True):
    """Display type at cap height H with an optional keyline and a soft shadow for depth."""
    H = max(4, int(round(H)))
    m = fit_h(text_mask(text, H * 1.5, path, tracking), H)
    im = solid(m, colour)
    if colour == WHITE or lum(colour) > 200:
        im = metal(m, "white")
    if stroke:
        im = outline(im, stroke_colour, stroke)
    if depth:
        r = max(1, H // 18)
        im = shadow(im, r // 2 + 1, r, r, 0.55)
    return im


def lockup(g, H, sb_colour=WHITE):
    """SUPER BOWL in tracked white type beside the metal numerals, sharing one cap height H."""
    H = max(4, int(round(H)))
    sb = word("SUPER BOWL", H, sb_colour, COND, 0.04)
    num = numerals(g, int(H * (1.0 if g["style"] != "classic" else 0.96)))
    gap = int(H * 0.30)
    W = sb.width + gap + num.width
    out = Image.new("RGBA", (W, max(sb.height, num.height)), (0, 0, 0, 0))
    out.alpha_composite(sb, (0, (out.height - sb.height) // 2))
    out.alpha_composite(num, (sb.width + gap, (out.height - num.height) // 2))
    return out


def stacked_lockup(g, H):
    """SUPER BOWL over the numerals, the pair H tall."""
    H = max(8, int(round(H)))
    sb = word("SUPER BOWL", H * 0.30, WHITE, COND, 0.10)
    num = numerals(g, int(H * 0.56))
    W = max(sb.width, num.width)
    out = Image.new("RGBA", (W, sb.height + num.height + int(H * 0.02)), (0, 0, 0, 0))
    out.alpha_composite(sb, ((W - sb.width) // 2, 0))
    out.alpha_composite(num, ((W - num.width) // 2, sb.height + int(H * 0.02)))
    return out


def best_lockup(g, w, h):
    """The single-line or the stacked lockup, whichever shows the numerals larger in a w x h box."""
    one = lockup(g, 100)
    two = stacked_lockup(g, 200)
    s1 = min(w / one.width, h / one.height) * 100
    s2 = min(w / two.width, h / two.height) * 200 * 0.56
    return fit(one, w, h) if s1 >= s2 * 0.9 else fit(two, w, h)


def chip(text, w, h, fg=WHITE, bg=(24, 26, 32), edge=(150, 156, 168)):
    """A broadcaster in plain type on a rounded chip (no network logo is drawn)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    r = int(h * 0.22)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
    im.alpha_composite(fill_mask(m, vgrad(w, h, [(0, edge), (1, darker(edge, 0.35))])))
    inner = shrink(m, max(2, h // 14))
    im.alpha_composite(fill_mask(inner, vgrad(w, h, [(0, lighter(bg, 0.12)), (1, darker(bg, 0.3))])))
    t = solid(fit_h(text_mask(text, 300, BLACK, 0.04), 100), fg)
    paste_c(im, fit(t, w * 0.74, h * 0.52), w / 2, h / 2)
    return im


def logo_mark(code):
    """The mod's own 2026 team logo (RGBA array), or None where the mod has no logo of the game's season."""
    name = TEAMS[code][3]
    if name is None:
        return None
    with Image.open(LOGOS / f"{name}.png") as im:
        return np.asarray(im.convert("RGBA")).copy()


def roundel(g, code, w, h):
    """A plain club roundel (the club's colours and its abbreviation) for a season whose logo the mod lacks."""
    c1, c2 = team_colours(g, code)
    d = int(min(w, h) * 0.92)
    im = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    m = Image.new("L", (d, d), 0)
    ImageDraw.Draw(m).ellipse([0, 0, d - 1, d - 1], fill=255)
    im.alpha_composite(solid(m, WHITE))
    inner = shrink(m, max(2, d // 14))
    im.alpha_composite(fill_mask(inner, vgrad(d, d, [(0, lighter(c1, 0.15)), (1, darker(c1, 0.3))])))
    ring = ImageChops.subtract(inner, shrink(inner, max(1, d // 24)))
    im.alpha_composite(solid(ring, c2 if lum(c2) > 40 else lighter(c1, 0.5)))
    t = solid(fit_h(text_mask(code, 300, BLACK, 0.0), 100), contrast_on(c1, WHITE, c2))
    paste_c(im, fit(t, d * 0.66, d * 0.40), d / 2, d / 2)
    return im


def team_colours(g, code):
    return SEASON_COLOURS.get((g["row"], code), TEAMS[code][1:3])


# --- the surface canvas: base art plus slots ---------------------------------------------------------------------

class Canvas:
    """A surface at master scale. ``slot`` reserves a native-aligned box and records its authored mark."""

    def __init__(self, g, W, H, ctx):
        self.g, self.W, self.H, self.ctx = g, W, H, ctx
        self.im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.slots = []

    def snap(self, box):
        x0, y0, x1, y1 = (int(round(v / SCALE)) for v in box)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(self.W // SCALE, max(x0 + 1, x1)), min(self.H // SCALE, max(y0 + 1, y1))
        return [x0, y0, x1, y1]

    def slot(self, kind, key, box, *, make=None, mark=None, authored="authored", **opts):
        """Reserve a slot. ``make(w, h)`` draws the authored mark at master size; ``mark`` is an RGBA array the
        compiler's own fitter places at native size (the mod's team logos)."""
        native = self.snap(box)
        self.slots.append(dict(kind=kind, key=key, box=native, make=make, mark=mark, authored=authored, opts=opts))
        return [v * SCALE for v in native]

    def event(self, box, **opts):
        g = self.g
        return self.slot("event", g["n"], box, make=lambda w, h: emblem_for(g, w, h), authored="authored_event_plate",
                         **opts)

    def shield(self, box, **opts):
        return self.slot("shield", "nfl", box, **opts)

    def brand(self, key, box, text=None, **opts):
        text = text or key.upper()
        if key == "espn":
            make = lambda w, h: chip(text, w, h, (255, 255, 255), (178, 10, 30), (232, 232, 236))  # noqa: E731
        else:
            make = lambda w, h: chip(text, w, h)  # noqa: E731
        return self.slot("brand", key, box, make=make, authored="authored_network_type", **opts)

    def team(self, code, box, colour=WHITE, **opts):
        """The club's mod logo where it is the season's, else its name in type."""
        g = self.g
        if (g["row"], code) not in PERIOD_LOGO_GAPS and logo_mark(code) is not None:
            opts.setdefault("margin", 0.04)
            return self.slot("team", code, box, mark=logo_mark(code), authored="mod_team_logo", **opts)
        return self.slot("team", code, box, make=lambda w, h: roundel(g, code, w, h), authored="authored_team_roundel",
                         **opts)


def band_bg(W, H, g, k=0, cloth_folds=None):
    """The event field: a vertical gradient of the dark colour with a mid-colour lift, a soft sheen and the motif."""
    dark, mid, acc = g["pal"]
    bg = vgrad(W, H, [(0, mix(dark, mid, 0.22)), (0.5, dark), (1, darker(dark, 0.45))])
    motif = g.get("motif", "none")
    if motif == "stars":
        d = ImageDraw.Draw(bg)
        r = H * 0.035
        for i in range(int(W / (H * 0.30)) + 1):
            x = i * H * 0.30 + (H * 0.15 if i % 2 else 0)
            d.polygon(star_pts(x, H * (0.12 if i % 2 else 0.20), r), fill=mix(dark, WHITE, 0.16) + (255,))
    elif motif == "checker":
        a = np.asarray(bg).copy()
        s = max(2, H // 8)
        yy, xx = np.mgrid[0:H, 0:W]
        chk = ((xx // s + yy // s) % 2 == 0) & (yy < s * 2)
        a[chk, :3] = np.clip(a[chk, :3].astype(int) + 14, 0, 255).astype(np.uint8)
        bg = Image.fromarray(a, "RGBA")
    elif motif in ("waves", "sun", "snow", "neon"):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = {"waves": mid, "sun": acc, "snow": WHITE, "neon": mid}[motif]
        alpha = {"waves": 40, "sun": 46, "snow": 34, "neon": 60}[motif]
        if motif == "waves":
            for j in range(3):
                pts = [(x, H * (0.80 + 0.06 * j) + H * 0.05 * math.sin(x / W * math.tau * 2 + j)) for x in
                       range(0, W + 8, 8)]
                d.line(pts, fill=tuple(c) + (alpha,), width=max(1, H // 24))
        elif motif == "sun":
            for j in range(5):
                x0 = W * (0.15 + 0.18 * j) - H * 0.4
                d.polygon([(x0, H), (x0 + H * 0.5, H), (x0 + H * 1.1, 0), (x0 + H * 0.9, 0)], fill=tuple(c) + (alpha // 2,))
        elif motif == "snow":
            for j in range(int(W / (H * 0.45)) + 1):
                x, y = j * H * 0.45 + H * 0.2, H * (0.25 if j % 2 else 0.70)
                for ang in range(0, 180, 60):
                    dx, dy = math.cos(math.radians(ang)) * H * 0.07, math.sin(math.radians(ang)) * H * 0.07
                    d.line([(x - dx, y - dy), (x + dx, y + dy)], fill=tuple(c) + (alpha,), width=max(1, H // 40))
        else:
            d.line([(0, H * 0.84), (W, H * 0.84)], fill=tuple(c) + (alpha * 2,), width=max(1, H // 30))
        bg.alpha_composite(layer)
    bg.alpha_composite(sheen(W, H, 0.10, 0.25 + 0.17 * (k % 3), 0.22))
    if cloth_folds:
        bg = apply_shade(bg, cloth_shade(W, H, k + 3, cloth_folds))
    return bg


def trims(c, top_px, bottom_px, top_colour, bottom_colour):
    d = ImageDraw.Draw(c.im)
    if top_px:
        d.rectangle([0, 0, c.W, top_px - 1], fill=tuple(top_colour) + (255,))
    if bottom_px:
        d.rectangle([0, c.H - bottom_px, c.W, c.H], fill=tuple(bottom_colour) + (255,))


def place_row(c, items, y0, y1, x0=None, x1=None, gap=None):
    """Lay out [(kind, payload)] across a band: ('img', RGBA) is pasted; ('slot', (fn, w)) reserves a slot of width w
    (master) via fn(box). Items are spread with equal gaps."""
    x0 = 0 if x0 is None else x0
    x1 = c.W if x1 is None else x1
    widths = [p.width if k == "img" else p[1] for k, p in items]
    free = (x1 - x0) - sum(widths)
    gap = free / len(items) if gap is None else gap
    x = x0 + max(0, (free - gap * (len(items) - 1)) / 2) if gap is not None else x0
    if free < 0:
        x = x0
    for (kind, p), w in zip(items, widths):
        if kind == "img":
            c.im.alpha_composite(p, (int(round(x)), int(round((y0 + y1) / 2 - p.height / 2))))
        else:
            p[0]([x, y0, x + w, y1])
        x += w + gap


# --- painters ------------------------------------------------------------------------------------------------------
# Every painter takes a Canvas (master scale) and draws its base art and slots.

def p_wall(c):
    """The field wall (256 x 32, repeating round the field): the event plate, SUPER BOWL and the numerals, the shield
    and the host city on a raked colour block."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g))
    block = poly_mask(W, H, [(170 * u, 0), (W, 0), (W, H), (160 * u, H)])
    c.im.alpha_composite(fill_mask(block, vgrad(W, H, [(0, lighter(mid, 0.08)), (1, darker(mid, 0.35))])))
    edge = poly_mask(W, H, [(166 * u, 0), (170 * u, 0), (160 * u, H), (156 * u, H)])
    c.im.alpha_composite(fill_mask(edge, Image.new("RGBA", (W, H), tuple(acc) + (255,))))
    trims(c, 2 * u, 2 * u, acc, darker(dark, 0.5))
    c.event([3 * u, 3 * u, 40 * u, 30 * u])
    lk = fit(lockup(g, 14 * u), 92 * u, 24 * u)
    c.im.alpha_composite(lk, (43 * u + (92 * u - lk.width) // 2, int(H / 2 - lk.height / 2)))
    c.shield([137 * u, 3 * u, 156 * u, 30 * u], keyline=(255, 255, 255))
    city_c = WHITE if lum(mid) < 150 else darker(dark, 0.3)
    city = fit(word(g["city"], 13 * u, city_c, COND, 0.06), 82 * u, 20 * u)
    paste_c(c.im, city, 211 * u, H / 2)


def p_ribbon(c):
    """The LED ribbon (256 x 64, two 32-texel bands): the event band (shield, SUPER BOWL and the numerals, the city,
    the network) over the matchup band (the two clubs on their colours, the numerals between them)."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    half = H // 2
    u = SCALE
    top = vgrad(W, half, [(0, (14, 16, 22)), (0.5, (6, 7, 10)), (1, (2, 2, 4))])
    top.alpha_composite(fill_mask(poly_mask(W, half, [(0, 0), (W * 0.62, 0), (W * 0.58, half), (0, half)]),
                                  vgrad(W, half, [(0, mix(dark, mid, 0.2)), (1, darker(dark, 0.3))])))
    c.im.alpha_composite(top, (0, 0))
    c.shield([4 * u, 3 * u, 26 * u, 30 * u], keyline=(255, 255, 255))
    lk = fit(lockup(g, 13 * u), 104 * u, 24 * u)
    c.im.alpha_composite(lk, (30 * u, int(half / 2 - lk.height / 2)))
    cityw = fit(word(g["city"], 11 * u, lighter(mid, 0.2) if lum(mid) < 170 else mid, COND, 0.08), 72 * u, 18 * u)
    paste_c(c.im, cityw, 176 * u, half / 2)
    c.brand(g["net"].lower(), [220 * u, 6 * u, 252 * u, 27 * u])
    d = ImageDraw.Draw(c.im)
    d.rectangle([0, half - u, W, half], fill=tuple(acc) + (255,))
    seg = W // 2
    for k, code in enumerate((g["away"], g["home"])):
        c1, c2 = team_colours(g, code)
        x0 = k * seg
        panel = vgrad(seg, half, [(0, lighter(c1, 0.12)), (0.55, c1), (1, darker(c1, 0.4))])
        panel.alpha_composite(sheen(seg, half, 0.12, 0.3, 0.3))
        c.im.alpha_composite(panel, (x0, half))
        d.rectangle([x0, H - u, x0 + seg, H], fill=tuple(c2) + (255,))
        lx = x0 + (5 * u if k == 0 else seg - 33 * u)
        c.team(code, [lx, half + 2 * u, lx + 28 * u, H - 2 * u], keyline=(255, 255, 255), shadow=True)
        name = fit(word(TEAMS[code][0], 13 * u, contrast_on(c1, WHITE, c2), COND, 0.05), 70 * u, 20 * u)
        area0 = x0 + (35 * u if k == 0 else 20 * u)
        nx = area0 + (70 * u - name.width) // 2
        c.im.alpha_composite(name, (nx, int(half + half / 2 - name.height / 2)))
    badge = Image.new("RGBA", (36 * u, half), (0, 0, 0, 0))
    bm = poly_mask(36 * u, half, [(8 * u, 0), (28 * u, 0), (36 * u, half / 2), (28 * u, half), (8 * u, half),
                                  (0, half / 2)])
    badge.alpha_composite(fill_mask(bm, vgrad(36 * u, half, [(0, (30, 32, 40)), (1, (4, 4, 6))])))
    paste_c(badge, fit(numerals(g, 14 * u), 26 * u, 20 * u), 18 * u, half / 2)
    c.im.alpha_composite(badge, (W // 2 - 18 * u, half))


def p_wing(c):
    """The board wings (64 x 128): the shield over the event plate, SUPER BOWL and the numerals on a dark screen."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(vgrad(W, H, [(0, (16, 18, 24)), (1, (4, 5, 8))]))
    c.im.alpha_composite(band_bg(W, int(H * 0.36), g), (0, int(H * 0.64)))
    trims(c, 3 * u, 2 * u, mid if lum(mid) < 200 else acc, acc)
    c.shield([18 * u, 6 * u, 46 * u, 38 * u], keyline=(255, 255, 255))
    c.event([4 * u, 42 * u, 60 * u, 80 * u])
    sb = fit(word("SUPER BOWL", 9 * u, WHITE, COND, 0.06), 58 * u, 12 * u)
    paste_c(c.im, sb, W / 2, 93 * u)
    paste_c(c.im, fit(numerals(g, 18 * u), 56 * u, 24 * u), W / 2, 111 * u)


def p_panel(c):
    """The corner boards (128 x 128): the event plate, then the shield, the city and the network on a dark bar."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g))
    trims(c, 3 * u, 0, acc, acc)
    c.event([8 * u, 8 * u, 120 * u, 86 * u])
    bar = vgrad(W, 36 * u, [(0, (20, 22, 28)), (1, (4, 4, 6))])
    c.im.alpha_composite(bar, (0, H - 36 * u))
    ImageDraw.Draw(c.im).rectangle([0, H - 37 * u, W, H - 36 * u], fill=tuple(mid) + (255,))
    c.shield([4 * u, 94 * u, 26 * u, 124 * u], keyline=(255, 255, 255))
    city = fit(word(g["city"], 10 * u, WHITE, COND, 0.05), 62 * u, 16 * u)
    c.im.alpha_composite(city, (30 * u, int(H - 18 * u - city.height / 2)))
    c.brand(g["net"].lower(), [94 * u, 100 * u, 124 * u, 118 * u])


def p_signs4(c):
    """Four bowl sign bands (U.S. Bank, 256 x 128): HOME OF SUPER BOWL LII, the matchup, the host tag and the city,
    the network and the event plate."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    q = H // 4
    for k in range(4):
        c.im.alpha_composite(band_bg(W, q, g, k), (0, k * q))
        ImageDraw.Draw(c.im).rectangle([0, k * q, W, k * q + u - 1], fill=tuple(acc if k % 2 else mid) + (255,))
    home = fit(word("HOME OF", 11 * u, lighter(mid, 0.1) if lum(mid) < 170 else mid, COND, 0.06), 60 * u, 18 * u)
    lk = fit(lockup(g, 12 * u), 140 * u, 22 * u)
    c.im.alpha_composite(home, (8 * u, int(q / 2 - home.height / 2)))
    c.im.alpha_composite(lk, (8 * u + home.width + 6 * u, int(q / 2 - lk.height / 2)))
    c.shield([226 * u, 2 * u, 250 * u, 30 * u], keyline=(255, 255, 255))
    seg = W // 2
    for k, code in enumerate((g["away"], g["home"])):
        c1, c2 = team_colours(g, code)
        x0 = k * seg
        c.im.alpha_composite(vgrad(seg, q, [(0, lighter(c1, 0.1)), (1, darker(c1, 0.35))]), (x0, q))
        lx = x0 + (6 * u if k == 0 else seg - 32 * u)
        c.team(code, [lx, q + 3 * u, lx + 26 * u, 2 * q - 3 * u], keyline=(255, 255, 255), shadow=True)
        name = fit(word(TEAMS[code][0], 12 * u, contrast_on(c1, WHITE, c2), COND, 0.05), 80 * u, 20 * u)
        nx = x0 + (36 * u if k == 0 else seg - 36 * u - name.width)
        c.im.alpha_composite(name, (nx, int(q + q / 2 - name.height / 2)))
    vs = fit(word("VS", 9 * u, WHITE, BLACK_IT, 0.0), 18 * u, 14 * u)
    paste_c(c.im, vs, W / 2, q + q / 2)
    tag = fit(word(g.get("tag", g["city"]), 14 * u, WHITE, COND, 0.10), 200 * u, 24 * u)
    paste_c(c.im, tag, W / 2, 2 * q + q / 2)
    c.brand(g["net"].lower(), [10 * u, 3 * q + 6 * u, 46 * u, 4 * q - 5 * u])
    city = fit(word(g["city"], 12 * u, lighter(mid, 0.1) if lum(mid) < 170 else mid, COND, 0.08), 130 * u, 20 * u)
    paste_c(c.im, city, W / 2, 3 * q + q / 2)
    c.event([210 * u, 3 * q + 2 * u, 252 * u, 4 * q - 2 * u])


def p_prow(c):
    """A square display (128 x 128): the event plate over the host city and year on a colour band."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g, 1))
    c.event([6 * u, 6 * u, 122 * u, 100 * u])
    c.im.alpha_composite(vgrad(W, 24 * u, [(0, lighter(mid, 0.1)), (1, darker(mid, 0.3))]), (0, H - 24 * u))
    ImageDraw.Draw(c.im).rectangle([0, H - 25 * u, W, H - 24 * u], fill=tuple(acc) + (255,))
    tag = fit(word(g.get("tag", f"{g['city']} {g['year']}"), 10 * u, WHITE if lum(mid) < 150 else dark, COND, 0.08),
              116 * u, 16 * u)
    paste_c(c.im, tag, W / 2, H - 12 * u)


def p_vbanners(c):
    """Four banners from the roof (Lucas Oil, 128 x 64 as four 32 x 64 cloths): the event plate, the two clubs and
    the shield with SUPER BOWL, each with a white border."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    q = W // 4
    for k in range(4):
        x0 = k * q
        colour = dark if k in (0, 3) else team_colours(g, (g["away"], g["home"])[k - 1])[0]
        c.im.alpha_composite(cloth(q, H, darker(colour, 0.05), seed=k, folds=2), (x0, 0))
        d = ImageDraw.Draw(c.im)
        d.rectangle([x0 + u, u, x0 + q - 1 - u, H - 1 - u], outline=WHITE + (255,), width=u)
        if k == 0:
            c.event([x0 + 3 * u, 6 * u, x0 + q - 3 * u, 36 * u])
            paste_c(c.im, fit(numerals(g, 12 * u), 24 * u, 16 * u), x0 + q / 2, 48 * u)
        elif k in (1, 2):
            code = (g["away"], g["home"])[k - 1]
            c1, c2 = team_colours(g, code)
            c.team(code, [x0 + 3 * u, 8 * u, x0 + q - 3 * u, 34 * u], keyline=(255, 255, 255))
            name = fit(word(TEAMS[code][0], 7 * u, contrast_on(c1, WHITE, c2), COND, 0.02), 26 * u, 10 * u)
            paste_c(c.im, name, x0 + q / 2, 46 * u)
        else:
            c.shield([x0 + 6 * u, 8 * u, x0 + q - 6 * u, 32 * u], keyline=(255, 255, 255))
            paste_c(c.im, fit(word("SUPER", 7 * u, WHITE, COND, 0.04), 26 * u, 9 * u), x0 + q / 2, 41 * u)
            paste_c(c.im, fit(word("BOWL", 7 * u, WHITE, COND, 0.04), 26 * u, 9 * u), x0 + q / 2, 51 * u)


def p_screen(c):
    """SoFi's ring screen (512 x 64): the event plate, SUPER BOWL and the numerals, the two clubs, the city and the
    shield on the event's sunset gradient."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    bg = hgrad(W, H, [(0, darker(dark, 0.3)), (0.35, dark), (0.65, mix(dark, acc, 0.35)), (1, mix(dark, mid, 0.45))])
    bg.alpha_composite(sheen(W, H, 0.10, 0.4, 0.3))
    c.im.alpha_composite(bg)
    trims(c, u, u, acc, mid)
    c.event([6 * u, 4 * u, 86 * u, 60 * u])
    lk = fit(lockup(g, 16 * u), 140 * u, 26 * u)
    c.im.alpha_composite(lk, (94 * u, 9 * u))
    city = fit(word(g["city"], 9 * u, lighter(mid, 0.1), COND, 0.14), lk.width, 13 * u)
    c.im.alpha_composite(city, (94 * u + (lk.width - city.width) // 2, 40 * u))
    x = 244 * u
    for k, code in enumerate((g["away"], g["home"])):
        c1, c2 = team_colours(g, code)
        c.im.alpha_composite(vgrad(100 * u, 50 * u, [(0, lighter(c1, 0.1)), (1, darker(c1, 0.35))]), (x, 7 * u))
        c.team(code, [x + 2 * u, 9 * u, x + 38 * u, 55 * u], keyline=(255, 255, 255), shadow=True)
        name = fit(word(TEAMS[code][0], 12 * u, contrast_on(c1, WHITE, c2), COND, 0.03), 58 * u, 18 * u)
        c.im.alpha_composite(name, (x + 40 * u + (58 * u - name.width) // 2, int(H / 2 - name.height / 2)))
        if k == 0:
            paste_c(c.im, fit(word("VS", 10 * u, WHITE, BLACK_IT), 12 * u, 16 * u), x + 107 * u, H / 2)
        x += 114 * u
    c.shield([474 * u, 5 * u, 506 * u, 59 * u], keyline=(255, 255, 255))


def p_mesh(c):
    """Allegiant's mesh banner (256 x 64): the event plate, SUPER BOWL and the numerals over the city, the shield."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g, 2))
    trims(c, 2 * u, 2 * u, acc, acc)
    c.event([6 * u, 5 * u, 86 * u, 59 * u])
    lk = fit(lockup(g, 15 * u), 130 * u, 26 * u)
    c.im.alpha_composite(lk, (92 * u, 10 * u))
    city = fit(word(g["city"], 10 * u, acc, COND, 0.12), 130 * u, 16 * u)
    c.im.alpha_composite(city, (92 * u + (lk.width - city.width) // 2, 40 * u))
    c.shield([226 * u, 8 * u, 252 * u, 56 * u], keyline=(255, 255, 255))


def p_uop_name(c):
    """The stadium's name as it was in 2006-2017 (University of Phoenix Stadium): plain red letters in two lines on
    the sign's transparent ground (the sign's cut-out keeps only the letters)."""
    W, H = c.W, c.H
    red = (178, 22, 40)
    for text, y, h in (("UNIVERSITY OF", 0.03, 0.44), ("PHOENIX STADIUM", 0.51, 0.44)):
        t = fit(metal(text_mask(text, 300, COND, 0.02), [(0, (206, 40, 56)), (1, red)]), W * 0.98, H * h)
        c.im.alpha_composite(t, (int(W / 2 - t.width / 2), int(H * y)))


def p_nrg_name(c):
    """The stadium's name from 2014 (NRG Stadium): cream letters with a dark edge, in two lines."""
    W, H = c.W, c.H
    cream = (244, 238, 214)
    for text, y, h in (("NRG", 0.0, 0.50), ("STADIUM", 0.53, 0.44)):
        t = fit(outline(solid(text_mask(text, 300, COND, 0.04), cream), (40, 42, 48), SCALE), W * 0.98, H * h)
        c.im.alpha_composite(t, (int(W / 2 - t.width / 2), int(H * y)))


def wall_band(c, y0, y1, k):
    """One retail wall pad band (cloth folds): four layouts that rotate round the field."""
    g = c.g
    dark, mid, acc = g["pal"]
    W = c.W
    H = y1 - y0
    u = SCALE
    layout = k % 4
    if layout == 2:
        seg = W // 2
        for j, code in enumerate((g["away"], g["home"])):
            c1, c2 = team_colours(g, code)
            panel = vgrad(seg, H, [(0, lighter(c1, 0.1)), (1, darker(c1, 0.35))])
            c.im.alpha_composite(apply_shade(panel, cloth_shade(seg, H, k + j, 3)), (j * seg, y0))
    else:
        c.im.alpha_composite(band_bg(W, H, g, k, cloth_folds=4), (0, y0))
    d = ImageDraw.Draw(c.im)
    d.rectangle([0, y0, W, y0 + max(u, H // 18)], fill=tuple(acc if layout != 1 else mid) + (255,))
    d.rectangle([0, y1 - max(u, H // 10), W, y1], fill=(24, 26, 32, 255))
    body0, body1 = y0 + max(u, H // 18) + u, y1 - max(u, H // 10) - u
    bh = body1 - body0
    cap = bh * 0.50
    if layout == 0:
        sw, shw = min(bh * 1.28, W * 0.34), min(bh * 0.80, W * 0.16)
        c.event([2 * u, (body0 + body1) / 2 - sw / 2.56, 2 * u + sw, (body0 + body1) / 2 + sw / 2.56], shade=True)
        c.shield([W - 3 * u - shw, (body0 + body1) / 2 - shw * 0.62, W - 3 * u, (body0 + body1) / 2 + shw * 0.62],
                 keyline=(255, 255, 255), shade=True)
        x0, x1 = 2 * u + sw + 6 * u, W - 3 * u - shw - 6 * u
        lk = best_lockup(g, x1 - x0, bh * 0.86)
        paste_c(c.im, lk, (x0 + x1) / 2, (body0 + body1) / 2)
    elif layout == 1:
        shw = min(bh * 0.80, W * 0.16)
        sy0, sy1 = (body0 + body1) / 2 - shw * 0.62, (body0 + body1) / 2 + shw * 0.62
        c.shield([4 * u, sy0, 4 * u + shw, sy1], keyline=(255, 255, 255), shade=True)
        text = f"{g['city']}  {g['year']}" if W / bh > 5 else g["city"]
        tw = fit(word(text, cap, WHITE, COND, 0.08), W - 2 * shw - 20 * u, min(bh * 0.72, W * 0.16))
        paste_c(c.im, tw, W / 2, (body0 + body1) / 2)
        c.shield([W - 4 * u - shw, sy0, W - 4 * u, sy1], keyline=(255, 255, 255), shade=True)
    elif layout == 2:
        seg = W // 2
        for j, code in enumerate((g["away"], g["home"])):
            c1, c2 = team_colours(g, code)
            lw = min(bh, seg * 0.42)
            lx = j * seg + (2 * u if j == 0 else seg - 2 * u - lw)
            mid_y = (body0 + body1) / 2
            c.team(code, [lx, mid_y - lw / 2, lx + lw, mid_y + lw / 2], keyline=(255, 255, 255), shadow=True,
                   shade=True)
            name = fit(word(TEAMS[code][0], cap * 0.9, contrast_on(c1, WHITE, c2), COND, 0.04), seg - lw - 10 * u,
                       min(bh * 0.7, seg * 0.2))
            nx = j * seg + (lw + 6 * u if j == 0 else seg - lw - 6 * u - name.width)
            c.im.alpha_composite(name, (int(nx), int((body0 + body1) / 2 - name.height / 2)))
    else:
        cw, sw = min(bh * 1.5, W * 0.26), min(bh * 1.28, W * 0.34)
        my = (body0 + body1) / 2
        c.brand(g["net"].lower(), [3 * u, my - cw * 0.26, 3 * u + cw, my + cw * 0.26], shade=True)
        c.event([W - 2 * u - sw, my - sw / 2.56, W - 2 * u, my + sw / 2.56], shade=True)
        x0, x1 = 3 * u + cw + 6 * u, W - 2 * u - sw - 6 * u
        lk = best_lockup(g, x1 - x0, bh * 0.86)
        paste_c(c.im, lk, (x0 + x1) / 2, (body0 + body1) / 2)


def p_bands2(c):
    """Two stacked wall pad bands (the retail field walls)."""
    for k in range(2):
        wall_band(c, k * c.H // 2, (k + 1) * c.H // 2, c.ctx["variant"] * 2 + k)


def p_bands3(c):
    """Three stacked wall bands (the Georgia Dome's rings)."""
    q = c.H // 3
    for k in range(3):
        wall_band(c, k * q, (k + 1) * q if k < 2 else c.H, c.ctx["variant"] * 3 + k)


def p_band(c):
    wall_band(c, 0, c.H, c.ctx["variant"])


def p_hang(c):
    """A tall hanging event banner (cloth): the event plate, the host city and year, the shield, a light border."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g, c.ctx["variant"], cloth_folds=2))
    b = max(u, int(W * 0.04))
    ImageDraw.Draw(c.im).rectangle([b, b, W - 1 - b, H - 1 - b], outline=tuple(mid) + (255,), width=b)
    c.event([b * 2, b * 2, W - b * 2, H * 0.46], shade=True)
    paste_c(c.im, fit(word(g["city"], 10 * u, WHITE, COND, 0.05), W * 0.82, H * 0.12), W / 2, H * 0.56)
    paste_c(c.im, fit(word(str(g["year"]), 9 * u, acc if lum(acc) > 60 else WHITE, COND, 0.10), W * 0.6, H * 0.09),
            W / 2, H * 0.67)
    c.shield([W / 2 - H * 0.12, H * 0.73, W / 2 + H * 0.12, H * 0.94], keyline=(255, 255, 255), shade=True)


def p_hang_wide(c):
    """A wide hanging event banner: SUPER BOWL, the event plate and the city."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g, c.ctx["variant"], cloth_folds=3))
    ImageDraw.Draw(c.im).rectangle([0, H - int(H * 0.12), W, H], fill=tuple(mid) + (255,))
    c.event([W * 0.30, 3 * u, W * 0.70, H * 0.86], shade=True)
    paste_c(c.im, fit(word("SUPER BOWL", 8 * u, WHITE, COND, 0.04), W * 0.27, H * 0.5), W * 0.15, H * 0.44)
    paste_c(c.im, fit(word(g["city"], 8 * u, WHITE, COND, 0.04), W * 0.27, H * 0.5), W * 0.85, H * 0.44)


def p_word_event(c):
    """SUPER BOWL and the numerals with a dark keyline, on the surface's transparent ground."""
    g = c.g
    lk = lockup(g, int(c.H * 0.5))
    lk = outline(lk, darker(g["pal"][0], 0.3), max(2, c.H // 16))
    paste_c(c.im, fit(lk, c.W * 0.96, c.H * 0.86), c.W / 2, c.H / 2)


def p_tile_logo(c):
    """A square cloth tile carrying the event plate."""
    g = c.g
    c.im.alpha_composite(band_bg(c.W, c.H, g, c.ctx["variant"], cloth_folds=2))
    c.event([c.W * 0.06, c.H * 0.10, c.W * 0.94, c.H * 0.90], shade=True)


def p_pad(c):
    """A square wall pad: the event plate, the city or the year, and the shield."""
    g = c.g
    dark, mid, acc = g["pal"]
    W, H = c.W, c.H
    u = SCALE
    c.im.alpha_composite(band_bg(W, H, g, c.ctx["variant"], cloth_folds=2))
    trims(c, 3 * u, 3 * u, mid, mid)
    c.event([8 * u, 8 * u, 120 * u, 86 * u], shade=True)
    text = g["city"] if c.ctx["variant"] % 2 == 0 else str(g["year"])
    tw = fit(word(text, 12 * u, WHITE, COND, 0.06), 86 * u, 20 * u)
    c.im.alpha_composite(tw, (8 * u, int(106 * u - tw.height / 2)))
    c.shield([98 * u, 90 * u, 122 * u, 122 * u], keyline=(255, 255, 255), shade=True)


def p_mark(c):
    """The event plate alone on the surface's transparent ground."""
    c.event([0, 0, c.W, c.H], margin=0.02)


def p_shield_mark(c):
    """The shield alone on the surface's transparent ground."""
    c.shield([0, 0, c.W, c.H], margin=0.04)


def p_flag(c):
    """A hanging cloth with a light border and the event plate."""
    g = c.g
    W, H = c.W, c.H
    c.im.alpha_composite(band_bg(W, H, g, c.ctx["variant"], cloth_folds=3))
    b = max(SCALE, int(W * 0.04))
    ImageDraw.Draw(c.im).rectangle([b, b, W - 1 - b, H - 1 - b], outline=WHITE + (255,), width=b)
    c.event([b * 3, b * 3, W - b * 3, H - b * 3], shade=True)


def p_marquee(c):
    """The concourse marquee: amber LED type on black, WELCOME TO over SUPER BOWL and the numerals."""
    g = c.g
    W, H = c.W, c.H
    c.im.alpha_composite(Image.new("RGBA", (W, H), (6, 6, 8, 255)))
    amber = (246, 196, 64)
    for text, y in (("WELCOME TO", 0.25), (f"SUPER BOWL {g['n']}", 0.73)):
        t = fit(solid(text_mask(text, 300, COND, 0.06), amber), W * 0.94, H * 0.40)
        glow = solid(grow(t.getchannel("A"), SCALE // 2).filter(ImageFilter.GaussianBlur(SCALE // 2)), (120, 70, 10))
        paste_c(c.im, glow, W / 2, H * y)
        paste_c(c.im, t, W / 2, H * y)
    a = np.asarray(c.im).copy()
    a[::SCALE, :, :3] = (a[::SCALE, :, :3] * 0.55).astype(np.uint8)
    a[:, ::SCALE, :3] = (a[:, ::SCALE, :3] * 0.55).astype(np.uint8)
    c.im = Image.fromarray(a, "RGBA")


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


def tile_cloth(c, box, colour, seed, folds=3, border=None):
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    base = vgrad(w, h, [(0, lighter(colour, 0.06)), (1, darker(colour, 0.12))])
    base = apply_shade(base, cloth_shade(w, h, seed, folds))
    c.im.alpha_composite(base, (x0, y0))
    if border:
        ImageDraw.Draw(c.im).rectangle([x0 + 2 * SCALE, y0 + 2 * SCALE, x1 - 2 * SCALE, y1 - 2 * SCALE],
                                       outline=tuple(border) + (255,), width=SCALE)
    return x0, y0, w, h


def inset(box, fx, fy=None):
    fy = fx if fy is None else fy
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    return [x0 + w * fx, y0 + h * fy, x1 - w * fx, y1 - h * fy]


def corp_designs(g):
    """The event's printed banner set: the plate, the wordmark, the network, ESPN, the city, the shield."""
    dark, mid, acc = g["pal"]
    paper = (244, 245, 247)

    def plate(c, box, k):
        tile_cloth(c, box, dark, k)
        c.event(inset(box, 0.06, 0.08), shade=True)

    def wordmark(c, box, k):
        x0, y0, w, h = tile_cloth(c, box, mid if lum(mid) < 200 else dark, k)
        a = fit(word("SUPER BOWL", h * 0.3, WHITE, COND, 0.06), w * 0.86, h * 0.36)
        b = fit(numerals(g, int(h * 0.4)), w * 0.8, h * 0.48)
        paste_c(c.im, a, x0 + w / 2, y0 + h * 0.27)
        paste_c(c.im, b, x0 + w / 2, y0 + h * 0.66)

    def network(c, box, k):
        tile_cloth(c, box, paper, k)
        c.brand(g["net"].lower(), inset(box, 0.10, 0.18), shade=True)

    def espn(c, box, k):
        tile_cloth(c, box, paper, k)
        c.brand("espn", inset(box, 0.10, 0.18), shade=True)

    def city(c, box, k):
        x0, y0, w, h = tile_cloth(c, box, dark, k)
        paste_c(c.im, fit(word(g["city"], h * 0.4, WHITE, COND, 0.05), w * 0.88, h * 0.5), x0 + w / 2, y0 + h * 0.42)
        paste_c(c.im, fit(word(str(g["year"]), h * 0.2, acc if lum(acc) > 60 else WHITE, COND, 0.2), w * 0.5, h * 0.22),
                x0 + w / 2, y0 + h * 0.76)

    def shield_tile(c, box, k):
        tile_cloth(c, box, paper, k)
        c.shield(inset(box, 0.12, 0.10), shade=True)

    def numerals_tile(c, box, k):
        x0, y0, w, h = tile_cloth(c, box, dark, k)
        paste_c(c.im, fit(numerals(g, int(h * 0.5)), w * 0.84, h * 0.66), x0 + w / 2, y0 + h / 2)

    wide = [plate, wordmark, network, city, espn, plate]
    small = [shield_tile, numerals_tile, plate, network, shield_tile, espn]
    return wide, small


def fan_designs(g, code):
    """Two fan-made banners: the club colour with the club logo and the first chant, white cloth with the second
    chant lettered by hand in the club colour."""
    name, _, _, _ = TEAMS[code]
    c1, c2 = team_colours(g, code)
    phrases = g["fans"][code]

    def lines_of(phrase):
        words = phrase.split(" ")
        return [phrase] if len(phrase) <= 10 or len(words) == 1 else [
            " ".join(words[:len(words) // 2]), " ".join(words[len(words) // 2:])]

    def first(c, box, k):
        x0, y0, w, h = tile_cloth(c, box, c1, k, border=c2 if lum(c2) > 40 else None)
        lw = h * 0.80
        c.team(code, [x0 + 3 * SCALE, y0 + h * 0.10, x0 + 3 * SCALE + lw, y0 + h * 0.90], keyline=(255, 255, 255),
               shade=True)
        fg = contrast_on(c1, WHITE, c2)
        rows = lines_of(phrases[0])
        for i, line in enumerate(rows):
            t = fit(word(line, h * 0.3, fg, COND_IT, 0.0, depth=False), w - lw - 10 * SCALE, h * 0.8 / len(rows))
            t = t.rotate(3 if i % 2 == 0 else -2, Image.BICUBIC, expand=True)
            paste_c(c.im, t, x0 + lw + (w - lw) / 2, y0 + h * (0.5 if len(rows) == 1 else 0.3 + 0.4 * i))

    def second(c, box, k):
        x0, y0, w, h = tile_cloth(c, box, (246, 244, 238), k)
        fg = c1 if lum(c1) < 200 else c2
        rows = lines_of(phrases[1])
        for i, line in enumerate(rows):
            m = fit_h(text_mask(line, 300, COND_IT, 0.0), h * 0.32)
            t = outline(solid(m, fg), contrast_on(fg, c2, (40, 40, 40)) if lum(c2) < 230 else (40, 40, 40), SCALE)
            t = fit(t, w * 0.9, h * 0.84 / len(rows)).rotate(-3 if i % 2 == 0 else 2, Image.BICUBIC, expand=True)
            paste_c(c.im, t, x0 + w / 2, y0 + h * (0.5 if len(rows) == 1 else 0.3 + 0.4 * i))

    return [first, second]


def player_designs(g):
    out = []
    teams = (g["home"], g["home"], g["away"], g["away"])
    for k, ((num, name), code) in enumerate(zip(g["players"], teams)):
        c1, c2 = team_colours(g, code)
        bg, fg = (c1, contrast_on(c1, WHITE, c2)) if k % 2 == 0 else ((246, 244, 238), c1 if lum(c1) < 200 else c2)

        def make(c, box, seed, num=num, name=name, bg=bg, fg=fg, c2=c2):
            x0, y0, w, h = tile_cloth(c, box, bg, seed)
            a = fit(word(num, h * 0.36, fg, BLACK_IT, 0.0, depth=False), w * 0.6, h * 0.42)
            b = fit(word(name, h * 0.26, fg, COND_IT, 0.03, depth=False), w * 0.9, h * 0.36)
            paste_c(c.im, a.rotate(2, Image.BICUBIC, expand=True), x0 + w / 2, y0 + h * 0.30)
            paste_c(c.im, b.rotate(-2, Image.BICUBIC, expand=True), x0 + w / 2, y0 + h * 0.72)
        out.append(make)
    return out


def paint_tiles(c, choose):
    c.im.alpha_composite(Image.new("RGBA", (c.W, c.H), (200, 200, 200, 255)))
    for k, box in enumerate(c.ctx["tiles"]):
        choose(k, box)(c, box, k + 7)


def p_corp(c):
    wide, small = corp_designs(c.g)
    counters = dict(w=0, s=0)

    def choose(k, box):
        w, h = box[2] - box[0], box[3] - box[1]
        key = "w" if w > h * 1.4 else "s"
        pool = wide if key == "w" else small
        f = pool[counters[key] % len(pool)]
        counters[key] += 1
        return f
    paint_tiles(c, choose)


def p_fans_home(c):
    d = fan_designs(c.g, c.g["home"])
    paint_tiles(c, lambda k, box: d[k % len(d)])


def p_fans_away(c):
    d = fan_designs(c.g, c.g["away"])
    paint_tiles(c, lambda k, box: d[k % len(d)])


def p_players(c):
    d = player_designs(c.g)
    paint_tiles(c, lambda k, box: d[k % len(d)])


PAINTERS = {k[2:]: v for k, v in globals().items() if k.startswith("p_")}


def targets(row, source_kind, source_prefix):
    """{material: (painter, alpha)} for one Super Bowl row."""
    out = dict(BANNERS)
    out.update(VENUES.get((source_kind, source_prefix), {}))
    return out


# --- rendering ---------------------------------------------------------------------------------------------------

def render_area(g, size, painter, alpha, ctx):
    """(base RGBA, layer RGBA, slots) of one area at native size."""
    W, H = size
    c = Canvas(g, W * SCALE, H * SCALE, ctx)
    PAINTERS[painter](c)
    base = c.im.resize((W, H), Image.LANCZOS)
    if alpha in ("source", "opaque"):
        base.putalpha(255)
    base_a = np.asarray(base).copy()
    layer = np.zeros((H, W, 4), np.uint8)
    slots = []
    for s in c.slots:
        x0, y0, x1, y1 = s["box"]
        w, h = x1 - x0, y1 - y0
        content = None
        if s["mark"] is not None:
            o = s["opts"]
            content = walls.fit_mark(s["mark"], w, h, margin=o.get("margin", 0.06), budget=o.get("budget", 48),
                                     keyline=o.get("keyline"), shadow=o.get("shadow", False))
        elif s["make"] is not None:
            drawn = _centered(s["make"](w * SCALE, h * SCALE), w * SCALE, h * SCALE)
            content = np.asarray(drawn.resize((w, h), Image.LANCZOS)).copy()
        if content is not None and s["opts"].get("shade"):
            content = walls.shade_like(content, base_a[y0:y1, x0:x1])
        if content is not None:
            layer[y0:y1, x0:x1] = content
        spec = dict(kind=s["kind"], key=s["key"], box=s["box"], surface=painter)
        for k in ("margin", "budget", "keyline", "shadow", "shade"):
            if k in s["opts"]:
                spec[k] = list(s["opts"][k]) if isinstance(s["opts"][k], tuple) else s["opts"][k]
        if s["kind"] != "shield":
            spec["authored"] = s["authored"]
        slots.append(spec)
    return base_a, layer, slots


def _centered(im, w, h):
    """An RGBA drawn for a (w, h) box, centred on a clear canvas of exactly that size."""
    out = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    paste_c(out, im if im.width <= w and im.height <= h else fit(im, w, h), w / 2, h / 2)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--extract", required=True, help="native stadium textures of the 17 aliases (author time only)")
    ap.add_argument("--rows", help="comma-separated rows to draw (preview; the manifest needs all)")
    a = ap.parse_args(argv)
    catalog = json.loads((ROOT / "data/nfl2k5_espn25_fields.json").read_text())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    extract = Path(a.extract)
    only = {int(r) for r in a.rows.split(",")} if a.rows else None
    rows = []
    for m in catalog["moments"]:
        if not m.get("super_bowl") or m["row"] not in GAMES or (only and m["row"] not in only):
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
            base = np.zeros((size[1], size[0], 4), np.uint8)
            layer = np.zeros((size[1], size[0], 4), np.uint8)
            slots = []
            for k, (box, painter) in enumerate(areas):
                x0, y0, x1, y1 = box
                if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
                    raise SystemExit(f"row {m['row']}: {material} area {box} outside {size}")
                ctx = {"variant": variant + k}
                if alpha == "source":
                    ctx["tiles"] = tiles(np.asarray(src)[y0:y1, x0:x1, 3], SCALE)
                b, lyr, sl = render_area(g, (x1 - x0, y1 - y0), painter, alpha, ctx)
                base[y0:y1, x0:x1] = b
                layer[y0:y1, x0:x1] = lyr
                for s in sl:
                    s["box"] = [s["box"][0] + x0, s["box"][1] + y0, s["box"][2] + x0, s["box"][3] + y0]
                    slots.append(s)
            rel = f"row{m['row']:02d}/{material}.png"
            path = out / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(base, "RGBA").save(path, optimize=True)
            entry = dict(material=material, file=rel, size=list(size), alpha=alpha,
                         painter="+".join(p for _, p in areas), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            if areas[0][0] != (0, 0) + tuple(size) or len(areas) > 1:
                entry["areas"] = [list(box) for box, _ in areas]
            if any(s["kind"] != "shield" for s in slots):
                lrel = f"row{m['row']:02d}/{material}.marks.png"
                Image.fromarray(layer, "RGBA").save(out / lrel, optimize=True)
                entry["layer"] = lrel
                entry["layer_sha256"] = hashlib.sha256((out / lrel).read_bytes()).hexdigest()
            if slots:
                entry["slots"] = slots
            entries.append(entry)
        teams = dict(away=g["away"], home=g["home"])
        team_logos = {code: ("authored" if (m["row"], code) in PERIOD_LOGO_GAPS else "mod") for code in teams.values()}
        rows.append(dict(row=m["row"], event=g["n"], date=m["date"], season=g["season"], venue=m["venue"],
                         city=g["city"], network=g["net"], source_kind=m["source_kind"],
                         source_prefix=m["source_prefix"], teams=teams, team_logos=team_logos,
                         shield="mod_shield_2008" if g["season"] >= walls.MODERN_SHIELD_FROM_SEASON else
                         "disc_period_shield", textures=entries))
        print(m["row"], g["n"], len(entries), sum(len(e.get("slots", ())) for e in entries), flush=True)
    doc = dict(schema=walls.SCHEMA, held_rows=[34],
               note=("Authored event surfaces (sb2): base art plus authored slot marks; the build puts the season's "
                     "NFL shield in every shield slot and fills the other slots from the marks layer or the user's "
                     "optional folder. Permanent venue signs keep their bytes. Row 34 is held unchanged."),
               rows=rows)
    (out / "manifest.json").write_text(json.dumps(doc, indent=1) + "\n", newline="\n")
    print("SUPER_BOWL_WALLS_ART_OK", sum(len(r["textures"]) for r in rows),
          sum(len(t.get("slots", ())) for r in rows for t in r["textures"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
