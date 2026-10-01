"""Author the Modern MetLife texture set (data/nfl2k5_modern_metlife/art/*, rules.json).

Inputs (all private, none ship): the retail texture exports of the s18/s19 bundles (read for sizes, alpha
layouts and cloth shading), the team marks rasterized from the public-domain SVGs (Jets 2024 logo and
wordmark, Giants wordmark, MetLife logo), and job u1's Giants handoff (metlife_team_art/v1: the Giants end
zones, midfield ny and fan banners). Every output is an exact-size RGBA8 PNG for one embedded P8 texture
(or a rectangle of one), drawn at 4x and reduced; the 4x masters go to --masters for the 2K5 Edition packs.
Run by the author; the retail-size PNGs ship in the reviewed catalog and rules.json names where they go.

    python3 tools/nfl2k5_modern_metlife_art.py --retail DIR --logos DIR --giants DIR --masters DIR --midfield-photo JPG
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nfl2k5_modern_metlife"
S = 4  # master scale
FONT_COND = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
FONT_COND_IT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-BoldItalic.ttf"
FONT_BLACK = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Black.ttf"
FONT_BLACK_IT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-BlackItalic.ttf"

WHITE = (255, 255, 255)
LED_BG = (12, 14, 19)
STEEL = (150, 156, 162)
STEEL_DARK = (70, 75, 82)
METLIFE_BLUE, METLIFE_SKY, METLIFE_GREEN, METLIFE_TEXT = (21, 99, 169), (35, 157, 224), (153, 213, 56), (35, 31, 32)
# marker_lightShapeN: (SHA-256 of the retail 16 position bytes, authored position in metres x, y, z).
# Authored on each marker's retail bearing: y = rim top 58.3 m + 1.5 m, radius = the rim's outer edge on that
# bearing (a vertical section through the retail bowl) - 2 m. The same bytes in all eighteen bundles.
LIGHT_MARKERS = {
    1: ("f49a7bb91a0cd44e120c235a08b48ec7da10623c4bb4a7115b4eb5be0cf44a3b", (80.95, 59.8, -93.45)),
    2: ("5fb9e12dbaae015c1a0d196d3d5efd43cae9ba425a46f8c2264722fd8434b6f6", (90.5, 59.8, -74.65)),
    3: ("4983ba5353cff328d3648866f90bcfbb0e0abb12e975c1ae6254b50d0515ba8b", (94.86, 59.8, -56.41)),
    4: ("fb6d7caddc09f018035ea1b5d14eb8a5d4c73f0eacd3d53fc9977935d856b54c", (97.58, 59.8, -36.55)),
    5: ("916893d6a2b02f826064453c1aef785ab70968438e5cb3a7d79572cd630cf264", (97.59, 59.8, 36.41)),
    6: ("cda10384e0d097a68fbcc9ea4d8acddefe762b5ed84ce5461d05c8c487db5f03", (94.89, 59.8, 56.18)),
    7: ("7faf28af099ed5e14ea2def57b9385f61df393a5a46ffd6c8921110e6ec8751c", (90.54, 59.8, 74.47)),
    8: ("bd722470a21a4ab85fc743cc3b3deb95ec0b1867562884f5c97e19980452dc99", (80.98, 59.8, 93.41)),
    9: ("f1b827af307e9f4b09afb85c711eb6fbd09d4e87176686d698de84be6b1409fe", (-82.56, 59.8, 90.8)),
    10: ("f8e597938e040af622043f65517f12dd6c36460ebae912976d98dfdbc12bec6e", (-96.54, 59.8, 45.76)),
    11: ("03fdb1bb797719f708660ed0a64a6f867ecbab7f2de8e6479c6b99f32d6c9bf2", (-97.91, 59.8, 33.08)),
    12: ("041c6b1b64f86a487bc4ea768bb2b5dfd323ff4c14f45368334478bce124677f", (-97.88, 59.8, -33.32)),
    13: ("90c838b7431d862adbf9d508bb49fc6dd9428941ce7a82eeb0ff1b0587bf86d2", (-96.5, 59.8, -46.01)),
    14: ("8caa09249dbbe221b2cba82f7c6487dd22a96112b96aa5fa6c77515e253124c3", (-82.61, 59.8, -90.72)),
}

# The four flare markers (0x0007F210 registers a lens flare at each, 0x00097B80 copies them as the player-shadow
# light positions of shadow mode 2) sat with the lamp banks too; they move onto the rim the same way.
FLARE_MARKERS = {
    "marker_flare1Shape": ("4c45f627560fb6ae50b84b06d44a7db383768adc01624853b921a46e692df4e9", (90.5, 59.8, -74.62)),
    "marker_flare2Shape": ("8ecd63f32dc4e2aa040b0afa7e64d0c176500f8443e634c346162ebe5fe95cad", (90.53, 59.8, 74.52)),
    "marker_flareShape3": ("30205edd512721522251102b6876ad347cd457dc0e491676216a6766cd28f392", (-97.29, 59.8, 39.66)),
    "marker_flareShape4": ("4e863c9282d3aedf1a2a27f6a94b671f41f4fc6f677f4f2730d806d1079248ea", (-97.3, 59.8, -39.54)),
}

TEAMS = {
    "s18": dict(team="giants", primary=(28, 60, 158), dark=(11, 34, 101), accent=(167, 25, 48), text=WHITE,
                wordmark="GIANTS", city="NEW YORK", chant="GO BIG BLUE", nickname="BIG BLUE"),
    "s19": dict(team="jets", primary=(17, 87, 64), dark=(10, 52, 38), accent=WHITE, text=WHITE,
                wordmark="JETS", city="NEW YORK", chant="J-E-T-S! JETS! JETS! JETS!", nickname="GANG GREEN"),
}
# Sponsors seen on MetLife signage in the 2022-2025 reference photos (refs/SOURCES.md); drawn as plain
# type treatments, not copied logos.
SPONSORS = [("verizon", (0, 0, 0), (255, 255, 255), (205, 4, 11)), ("Bud Light", (255, 255, 255), (0, 58, 150), None),
            ("pepsi", (255, 255, 255), (0, 72, 160), None)]


# --- helpers --------------------------------------------------------------------------------------------

def font(path, size):
    return ImageFont.truetype(path, max(6, int(size)))


def canvas(w, h, colour=(0, 0, 0, 0)):
    return Image.new("RGBA", (w * S, h * S), colour if len(colour) == 4 else colour + (255,))


def reduce(master, w, h):
    """4x master -> retail size, premultiplied so transparent edges do not darken."""
    a = np.asarray(master, dtype=np.float64) / 255.0
    rgb, alpha = a[..., :3] * a[..., 3:4], a[..., 3:4]
    pre = Image.fromarray(np.uint8(np.clip(np.concatenate([rgb, alpha], -1) * 255, 0, 255)), "RGBA")
    small = np.asarray(pre.resize((w, h), Image.Resampling.BOX), dtype=np.float64) / 255.0
    al = small[..., 3:4]
    col = np.where(al > 0, small[..., :3] / np.maximum(al, 1e-6), 0)
    return Image.fromarray(np.uint8(np.clip(np.concatenate([col, al], -1) * 255 + 0.5, 0, 255)), "RGBA")


def text_box(draw, box, text, fill, path=FONT_COND, *, stroke=0, stroke_fill=None, align="center", max_size=None, pad=0.08):
    """Largest font size that fits ``text`` in ``box`` (master pixels)."""
    x0, y0, x1, y1 = box
    bw, bh = (x1 - x0) * (1 - 2 * pad), (y1 - y0) * (1 - 2 * pad)
    size = int(max_size or bh * 1.25)
    while size > 6:
        f = font(path, size)
        bb = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
        if bb[2] - bb[0] <= bw and bb[3] - bb[1] <= bh:
            break
        size -= max(1, size // 20)
    bb = draw.textbbox((0, 0), text, font=f, stroke_width=stroke)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    x = x0 + ((x1 - x0) - w) / 2 - bb[0] if align == "center" else x0 + (x1 - x0) * pad - bb[0]
    y = y0 + ((y1 - y0) - h) / 2 - bb[1]
    draw.text((x, y), text, font=f, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)


def load_mark(path):
    im = Image.open(path).convert("RGBA")
    return im.crop(im.getbbox())


def tint(mark, colour):
    """A single-colour version of a mark (its alpha as coverage)."""
    out = Image.new("RGBA", mark.size, colour + (255,))
    out.putalpha(mark.getchannel("A"))
    return out


def place(dst, mark, box, *, pad=0.08, xscale=1.0):
    x0, y0, x1, y1 = box
    bw, bh = (x1 - x0) * (1 - 2 * pad), (y1 - y0) * (1 - 2 * pad)
    w, h = mark.size[0] * xscale, mark.size[1]
    k = min(bw / w, bh / h)
    m = mark.resize((max(1, int(w * k)), max(1, int(h * k))), Image.Resampling.LANCZOS)
    dst.alpha_composite(m, (int(x0 + ((x1 - x0) - m.size[0]) / 2), int(y0 + ((y1 - y0) - m.size[1]) / 2)))


def led_grid(im, box, strength=0.18):
    """A faint LED pixel pitch over a rectangle (averages out at retail size, visible in the 4x master)."""
    x0, y0, x1, y1 = box
    region = np.asarray(im.crop(box), dtype=np.float64)
    yy, xx = np.mgrid[0:region.shape[0], 0:region.shape[1]]
    mask = ((xx % 4 == 3) | (yy % 4 == 3)).astype(np.float64)[..., None]
    region[..., :3] *= 1 - strength * mask
    im.paste(Image.fromarray(np.uint8(np.clip(region, 0, 255)), "RGBA"), (x0, y0))


def retail(args, bundle, scene, material):
    hits = sorted((Path(args.retail) / bundle[:-4] / scene).glob(f"t*_{material}_*.png"))
    if not hits:
        hits = sorted((Path(args.retail) / bundle[:-4] / scene).glob(f"t*_{material},*.png"))
    if not hits:
        raise SystemExit(f"retail export missing: {bundle} {scene} {material}")
    return Image.open(hits[0]).convert("RGBA")


def cloth(content_master, retail_small):
    """Put new banner content on the retail cloth: retail alpha and fold shading, content colours."""
    w, h = retail_small.size
    alpha = np.asarray(retail_small.getchannel("A"), dtype=np.float64)
    solid = alpha > 128
    # Folds are low frequency and the printed retail art is not: shade from a heavily blurred luminance
    # (inside the cloth only) so no retail lettering survives, at a reduced amplitude.
    lum = np.asarray(retail_small.convert("L"), dtype=np.float64)
    med0 = np.median(lum[solid]) if solid.any() else 128.0
    filled = np.where(solid, lum, med0)
    blurred = np.asarray(Image.fromarray(np.uint8(np.clip(filled, 0, 255))).filter(ImageFilter.GaussianBlur(4)),
                         dtype=np.float64)
    med = np.median(blurred[solid]) if solid.any() else 128.0
    shade = np.clip(1.0 + (blurred / max(med, 1.0) - 1.0) * 0.6, 0.8, 1.12)
    shade = np.asarray(Image.fromarray(np.uint8(np.clip(shade * 100, 0, 255))).resize((w * S, h * S), Image.Resampling.BILINEAR),
                       dtype=np.float64) / 100.0
    c = np.asarray(content_master, dtype=np.float64)
    c[..., :3] *= shade[..., None]
    c[..., 3] = np.asarray(Image.fromarray(np.uint8(alpha)).resize((w * S, h * S), Image.Resampling.NEAREST))
    return Image.fromarray(np.uint8(np.clip(c, 0, 255)), "RGBA")


# --- signage content --------------------------------------------------------------------------------------

def metlife_logo_panel(im, box, logos, *, bg=(250, 250, 250)):
    d = ImageDraw.Draw(im)
    d.rectangle(box, fill=bg + (255,))
    place(im, load_mark(Path(logos) / "MetLife_logo.png"), box, pad=0.14)


def team_mark_panel(im, box, venue, logos, giants, kind="logo"):
    t = TEAMS[venue]
    d = ImageDraw.Draw(im)
    d.rectangle(box, fill=t["primary"] + (255,))
    if venue == "s18":
        if kind == "logo":
            ny = load_mark(Path(giants) / "marks" / "ny_logo_silhouette_white.png")
            place(im, ny, box, pad=0.14)
            place(im, tint(load_mark(Path(giants) / "marks" / "ny_logo_fill_white.png"), t["dark"]), box, pad=0.14)
        else:
            place(im, load_mark(Path(giants) / "marks" / "giants_wordmark_white.png"), box, pad=0.14)
    else:
        if kind == "logo":
            place(im, load_mark(Path(logos) / "New_York_Jets_2024.png"), box, pad=0.1)
        else:
            place(im, tint(load_mark(Path(logos) / "New_York_Jets_2024_wordmark.png"), WHITE), box, pad=0.14)


def led_text_panel(im, box, text, fg, *, bg=LED_BG, italic=False, path=None):
    d = ImageDraw.Draw(im)
    d.rectangle(box, fill=bg + (255,))
    text_box(d, box, text, fg + (255,), path=path or (FONT_BLACK_IT if italic else FONT_COND), pad=0.12)
    led_grid(im, box)


def sponsor_panel(im, box, index):
    name, fg, bg, dot = SPONSORS[index % len(SPONSORS)]
    d = ImageDraw.Draw(im)
    d.rectangle(box, fill=bg + (255,))
    label = name + (" ✓" if dot else "")
    text_box(d, box, name, fg + (255,), path=FONT_COND if name != "verizon" else FONT_BLACK, pad=0.14)
    if dot:  # the Verizon check mark as a plain red chevron after the word
        x0, y0, x1, y1 = box
        cx, cy, s = x1 - (x1 - x0) * 0.08, y0 + (y1 - y0) * 0.35, (y1 - y0) * 0.16
        d.line([(cx - s, cy), (cx - s * 0.3, cy + s * 0.8), (cx + s * 0.9, cy - s * 0.9)], fill=dot + (255,),
               width=max(2, int(s * 0.35)))


def frame(im, box, colour=(40, 44, 50), width=1):
    d = ImageDraw.Draw(im)
    d.rectangle(box, outline=colour + (255,), width=width * S)


# --- textures ----------------------------------------------------------------------------------------------

def ribbon_strip(im, y0, y1, segments, venue, logos, giants):
    """Fill one fascia strip (master rows y0..y1) with LED ribbon segments [(x0, x1, kind)]."""
    t = TEAMS[venue]
    for i, (x0, x1, kind) in enumerate(segments):
        box = (x0 * S, y0 * S, x1 * S - 1, y1 * S - 1)
        if kind == "metlife":
            metlife_logo_panel(im, box, logos)
        elif kind == "wordmark":
            team_mark_panel(im, box, venue, logos, giants, kind="wordmark")
        elif kind == "logo":
            team_mark_panel(im, box, venue, logos, giants, kind="logo")
        elif kind == "chant":
            led_text_panel(im, box, t["chant"] if len(t["chant"]) < 14 else t["nickname"], WHITE, bg=t["primary"], italic=True)
        elif kind == "city":
            led_text_panel(im, box, f"{t['city']} {t['wordmark']}", WHITE, bg=t["dark"])
        elif kind.startswith("sponsor"):
            sponsor_panel(im, box, int(kind[7:] or 0))
        elif kind == "stadium":
            led_text_panel(im, box, "METLIFE STADIUM", WHITE, bg=LED_BG)
        elif kind == "nfl":
            led_text_panel(im, box, "NFL", WHITE, bg=(1, 51, 105))
        elif kind == "scores":
            led_text_panel(im, box, "NFL SCORES", (255, 196, 64), bg=LED_BG)
        elif kind == "down":
            led_text_panel(im, box, "1ST & 10", (255, 255, 255), bg=LED_BG)
        frame(im, box)


def banner01(venue, logos, giants):
    im = canvas(256, 256, LED_BG)
    rows = [(0, 45, [(0, 256, "wordmark")]),
            (45, 75, [(0, 128, "metlife"), (128, 256, "scores")]),
            (75, 105, [(0, 118, "down"), (118, 256, "sponsor0")]),
            (105, 137, [(0, 125, "logo"), (125, 256, "scores")]),
            (137, 167, [(0, 115, "chant"), (115, 256, "sponsor1")]),
            (167, 199, [(0, 138, "sponsor2"), (138, 256, "stadium")]),
            (199, 229, [(0, 112, "city"), (112, 256, "metlife")]),
            (229, 256, [(0, 30, "logo"), (30, 256, "nfl")])]
    for y0, y1, segs in rows:
        ribbon_strip(im, y0, y1, segs, venue, logos, giants)
    return im


def banner02(venue, logos, giants):
    im = canvas(256, 256, LED_BG)
    rows = [(0, 32, [(0, 130, "sponsor0"), (130, 256, "scores")]),
            (32, 62, [(0, 125, "down"), (125, 256, "metlife")]),
            (62, 92, [(0, 139, "wordmark"), (139, 256, "logo")]),
            (92, 118, [(0, 139, "chant")]),
            (118, 150, [(0, 139, "sponsor1")]),
            (150, 180, [(0, 139, "metlife")]),
            (180, 210, [(0, 139, "stadium")]),
            (210, 240, [(0, 139, "sponsor2")])]
    for y0, y1, segs in rows:
        ribbon_strip(im, y0, y1, segs, venue, logos, giants)
    # the three vertical boards and the two dark window strips to the right
    d = ImageDraw.Draw(im)
    for x0, x1, kind in ((139, 168, "metlife_v"), (168, 197, "team_v"), (197, 227, "stadium_v")):
        box = (x0 * S, 92 * S, x1 * S - 1, 225 * S - 1)
        tall = canvas(133, 29, LED_BG)
        tb = (0, 0, 133 * S - 1, 29 * S - 1)
        if kind == "metlife_v":
            metlife_logo_panel(tall, tb, logos)
        elif kind == "team_v":
            team_mark_panel(tall, tb, venue, logos, giants, kind="wordmark")
        else:
            led_text_panel(tall, tb, "METLIFE STADIUM", WHITE)
        im.alpha_composite(tall.rotate(90, expand=True).resize((box[2] - box[0] + 1, box[3] - box[1] + 1)), (box[0], box[1]))
        frame(im, box)
    for y0, y1 in ((62, 92), (225, 256)):
        box = (139 * S, y0 * S, 256 * S - 1, y1 * S - 1)
        d.rectangle(box, fill=(20, 22, 26, 255))
        for k in range(4):
            cx0 = (145 + k * 28) * S
            d.rectangle((cx0, (y0 + 5) * S, cx0 + 22 * S, (y1 - 5) * S), fill=(8, 9, 11, 255), outline=(52, 56, 62, 255), width=S)
    return im


def banner04(venue, logos, giants):
    im = canvas(256, 128, LED_BG)
    rows = [(0, 32, [(0, 128, "metlife"), (128, 256, "wordmark")]),
            (32, 64, [(0, 128, "stadium"), (128, 256, "stadium")]),
            (64, 96, [(0, 128, "sponsor0"), (128, 256, "logo")]),
            (96, 128, [(0, 128, "chant"), (128, 256, "sponsor1")])]
    for y0, y1, segs in rows:
        ribbon_strip(im, y0, y1, segs, venue, logos, giants)
    return im


def boards_ad_bb02(venue, logos, giants):
    """North end-zone video board panels (rows 0..168); the field-level panels below stay retail."""
    t = TEAMS[venue]
    im = canvas(256, 256, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = (0, 0, 256 * S - 1, 52 * S - 1)
    d.rectangle(top, fill=(26, 28, 32, 255))
    text_box(d, top, "METLIFE STADIUM", WHITE + (255,), path=FONT_COND, pad=0.1)
    team_mark_panel(im, (0, 52 * S, 122 * S - 1, 111 * S - 1), venue, logos, giants, kind="logo")
    team_mark_panel(im, (122 * S, 52 * S, 256 * S - 1, 111 * S - 1), venue, logos, giants, kind="wordmark")
    metlife_logo_panel(im, (0, 111 * S, 122 * S - 1, 167 * S - 1), logos)
    led_text_panel(im, (122 * S, 111 * S, 256 * S - 1, 167 * S - 1), t["chant"] if venue == "s18" else "J-E-T-S!", WHITE,
                   bg=t["primary"], italic=True)
    # the board panel beside the centre screen (retail Gatorade/ESPN) and the steel structure beside it
    side = (0, 167 * S, 106 * S - 1, 256 * S - 1)
    d.rectangle(side, fill=LED_BG + (255,))
    metlife_logo_panel(im, (6 * S, 175 * S, 100 * S - 1, 205 * S - 1), logos)
    team_mark_panel(im, (6 * S, 212 * S, 100 * S - 1, 250 * S - 1), venue, logos, giants, kind="wordmark")
    steel = (106 * S, 167 * S, 211 * S - 1, 256 * S - 1)
    d.rectangle(steel, fill=STEEL + (255,))
    for x in range(106, 211, 6):
        d.line([(x * S, 167 * S), (x * S, 256 * S)], fill=(128, 134, 141, 255), width=S)
    for box in ((0, 52 * S, 122 * S - 1, 111 * S - 1), (122 * S, 52 * S, 256 * S - 1, 111 * S - 1),
                (0, 111 * S, 122 * S - 1, 167 * S - 1), (122 * S, 111 * S, 256 * S - 1, 167 * S - 1), side):
        led_grid(im, box, 0.12)
        frame(im, box, (8, 8, 10), 2)
    return im, [[0, 0, 256, 167], [0, 167, 211, 256]]


def boards_ad_bb01(venue, logos, giants):
    """South end-zone board, the big video screen and the LED marquee; field-level panels stay retail."""
    t = TEAMS[venue]
    im = canvas(256, 256, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    top = (0, 0, 256 * S - 1, 63 * S - 1)
    d.rectangle(top, fill=(26, 28, 32, 255))
    text_box(d, top, "METLIFE STADIUM", WHITE + (255,), path=FONT_COND, pad=0.1)
    sponsor_panel(im, (0, 63 * S, 127 * S - 1, 112 * S - 1), 1)
    team_mark_panel(im, (127 * S, 63 * S, 256 * S - 1, 112 * S - 1), venue, logos, giants, kind="wordmark")
    screen = (97 * S, 152 * S, 207 * S - 1, 224 * S - 1)
    d.rectangle(screen, fill=(4, 5, 8, 255))
    team_mark_panel(im, (101 * S, 156 * S, 203 * S - 1, 220 * S - 1), venue, logos, giants, kind="logo")
    marquee = (0, 224 * S, 207 * S - 1, 256 * S - 1)
    led_text_panel(im, marquee, f"WELCOME TO METLIFE STADIUM  {t['city']} {t['wordmark']}", (255, 214, 120))
    vert = (226 * S, 112 * S, 256 * S - 1, 256 * S - 1)
    tall = canvas(144, 30, (250, 250, 250))
    metlife_logo_panel(tall, (0, 0, 144 * S - 1, 30 * S - 1), logos)
    im.alpha_composite(tall.rotate(-90, expand=True).resize((vert[2] - vert[0] + 1, vert[3] - vert[1] + 1)), (vert[0], vert[1]))
    for box in ((0, 63 * S, 127 * S - 1, 112 * S - 1), (127 * S, 63 * S, 256 * S - 1, 112 * S - 1), screen, marquee):
        led_grid(im, box, 0.12)
        frame(im, box, (8, 8, 10), 2)
    return im, [[0, 0, 256, 112], [97, 152, 207, 224], [0, 224, 207, 256], [226, 112, 256, 256]]


def wall_pad(venue, args, material, size):
    """Field-level wall pads: team colour, bold white type, a red base band for the Giants (2026 preseason)."""
    t = TEAMS[venue]
    w, h = size
    ret = retail(args, f"{venue}dd.iff", "stadium", material)
    im = canvas(w, h, t["primary"])
    d = ImageDraw.Draw(im)
    alpha = np.asarray(ret.getchannel("A"))
    top = int(np.argmax(alpha.min(axis=1) > 128)) if (alpha < 128).any() else 0  # the retail top cut-out rows
    # seams between pads, under the band and the type
    for x in range(0, w, max(16, w // 4)):
        d.line([(x * S, 0), (x * S, h * S)], fill=tuple(max(0, c - 18) for c in t["primary"]) + (255,), width=S)
    if venue == "s18":
        # faint diagonal stripes, as on the 2026 pads
        for k in range(-h, w, 10):
            d.line([(k * S, h * S), ((k + h) * S, 0)], fill=tuple(min(255, c + 9) for c in t["primary"]) + (255,), width=3 * S)
        d.rectangle((0, int((h - h * 0.12) * S), w * S, h * S), fill=t["accent"] + (255,))
        mid = (top + int(h * 0.88)) // 2
        text_box(d, (0, (top + 6) * S, w * S, mid * S), "NEW YORK", WHITE + (255,), path=FONT_BLACK, pad=0.06)
        text_box(d, (0, mid * S, w * S, int(h * 0.86) * S), "GIANTS", WHITE + (255,), path=FONT_BLACK, pad=0.06)
    else:
        d.rectangle((0, int(h * 0.80 * S), w * S, int(h * 0.86 * S)), fill=WHITE + (255,))
        d.rectangle((0, int(h * 0.89 * S), w * S, int(h * 0.92 * S)), fill=WHITE + (255,))
        place(im, tint(load_mark(Path(args.logos) / "New_York_Jets_2024_wordmark.png"), WHITE),
              (0, (top + 4) * S, w * S, int(h * 0.78) * S), pad=0.12)
    out = np.asarray(im).copy()
    out[..., 3] = np.asarray(Image.fromarray(alpha).resize((w * S, h * S), Image.Resampling.NEAREST))
    return Image.fromarray(out, "RGBA")


def jets_wall01(args, size):
    """s19 wall01 (256x256): the top half is the field wall band (J-E-T-S banners); the lower half is unused."""
    w, h = size
    t = TEAMS["s19"]
    im = canvas(w, h, t["primary"])
    d = ImageDraw.Draw(im)
    band = (0, 0, w * S, 128 * S)
    d.rectangle(band, fill=t["primary"] + (255,))
    d.rectangle((0, 108 * S, w * S, 114 * S), fill=WHITE + (255,))
    d.rectangle((0, 118 * S, w * S, 121 * S), fill=WHITE + (255,))
    place(im, load_mark(Path(args.logos) / "New_York_Jets_2024.png"), (88 * S, 6 * S, 168 * S, 100 * S), pad=0.04)
    text_box(d, (0, 20 * S, 86 * S, 90 * S), "NEW YORK", WHITE + (255,), path=FONT_BLACK_IT, pad=0.06)
    text_box(d, (170 * S, 20 * S, w * S, 90 * S), "JETS", WHITE + (255,), path=FONT_BLACK_IT, pad=0.06)
    d.rectangle((0, 128 * S, w * S, h * S), fill=t["dark"] + (255,))
    text_box(d, (0, 150 * S, w * S, 230 * S), "GANG GREEN", WHITE + (255,), path=FONT_BLACK_IT, pad=0.08)
    return im


def jets_wall04(args, size):
    """s19 wall04: the round wall sign, now the 2024 Jets logo on a white disc (retail alpha kept)."""
    w, h = size
    ret = retail(args, "s19dd.iff", "stadium", "wall04")
    im = canvas(w, h, WHITE)
    place(im, load_mark(Path(args.logos) / "New_York_Jets_2024.png"), (0, 0, w * S, h * S), pad=0.12)
    # The retail sign is a white disc with the letters cut out; the new sign is the whole disc.
    alpha = np.asarray(ret.getchannel("A")) > 128
    ys, xs = np.nonzero(alpha)
    cx, cy = (xs.min() + xs.max() + 1) / 2 * S, (ys.min() + ys.max() + 1) / 2 * S
    r = max(xs.max() - xs.min() + 1, ys.max() - ys.min() + 1) / 2 * S
    yy, xx = np.mgrid[0:h * S, 0:w * S]
    disc = ((xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2) <= r * r
    out = np.asarray(im).copy()
    out[..., 3] = np.where(disc, 255, 0)
    return Image.fromarray(out, "RGBA")


def fan_banners_jets(args, material, size):
    w, h = size
    ret = retail(args, "s19dd.iff", "stadium", material)
    t = TEAMS["s19"]
    im = canvas(w, h, WHITE)
    d = ImageDraw.Draw(im)
    half = h // 2
    if material == "banner_home_team":
        d.rectangle((0, 0, w * S, half * S), fill=t["primary"] + (255,))
        text_box(d, (0, 0, w * S, half * S), "J-E-T-S!", WHITE + (255,), path=FONT_BLACK_IT, pad=0.14)
        text_box(d, (0, half * S, w * S, h * S), "GANG GREEN", t["primary"] + (255,), path=FONT_BLACK, pad=0.14)
    elif material == "banner_away_team":
        text_box(d, (0, 0, w * S, half * S), "NEW YORK", t["primary"] + (255,), path=FONT_BLACK, pad=0.16)
        d.rectangle((0, half * S, w * S, h * S), fill=t["primary"] + (255,))
        text_box(d, (0, half * S, w * S, h * S), "JETS", WHITE + (255,), path=FONT_BLACK_IT, pad=0.16)
    else:  # banner_home_player: four cloths
        cells = [(0, 0, w // 2, half), (w // 2, 0, w, half), (0, half, w // 2, h), (w // 2, half, w, h)]
        for i, (a, b, c, e) in enumerate(cells):
            box = (a * S, b * S, c * S, e * S)
            if i == 0:
                d.rectangle(box, fill=t["primary"] + (255,))
                place(im, tint(load_mark(Path(args.logos) / "New_York_Jets_2024_wordmark.png"), WHITE), box, pad=0.16)
            elif i == 1:
                place(im, load_mark(Path(args.logos) / "New_York_Jets_2024.png"), box, pad=0.14)
            elif i == 2:
                text_box(d, box, "TAKE FLIGHT", t["primary"] + (255,), path=FONT_BLACK, pad=0.14)
            else:
                d.rectangle(box, fill=t["primary"] + (255,))
                text_box(d, box, "GREEN & WHITE", WHITE + (255,), path=FONT_BLACK, pad=0.14)
    return cloth(im, ret)


def corp_banners(args, venue, size):
    """Field-level sponsor banners (2 x 4 cloths) on the retail cloth."""
    w, h = size
    ret = retail(args, f"{venue}dd.iff", "stadium", "banner_corp")
    im = canvas(w, h, WHITE)
    cw, ch = w // 2, h // 4
    kinds = ["metlife", "sponsor0", "nfl", "sponsor1", "sponsor2", "wordmark", "logo", "stadium"]
    for i, kind in enumerate(kinds):
        c, r = i % 2, i // 2
        box = (c * cw * S, r * ch * S, (c + 1) * cw * S - 1, (r + 1) * ch * S - 1)
        if kind == "metlife":
            metlife_logo_panel(im, box, args.logos)
        elif kind.startswith("sponsor"):
            sponsor_panel(im, box, int(kind[7:]))
        elif kind == "nfl":
            # NFL navy at Giants games; on Jets green at Jets games, where Bud Light and Pepsi already bring
            # two blue cloths (Jev's colour audit flagged the Jets set's blue share at 31 percent)
            d = ImageDraw.Draw(im)
            d.rectangle(box, fill=((1, 51, 105) if venue == "s18" else TEAMS[venue]["primary"]) + (255,))
            text_box(d, box, "NFL", WHITE + (255,), path=FONT_BLACK, pad=0.2)
        elif kind == "stadium":
            d = ImageDraw.Draw(im)
            d.rectangle(box, fill=(26, 28, 32, 255))
            text_box(d, box, "METLIFE STADIUM", WHITE + (255,), path=FONT_COND, pad=0.12)
        else:
            team_mark_panel(im, box, venue, args.logos, args.giants, kind=kind)
    return cloth(im, ret)


def away_generic(args, venue, size):
    w, h = size
    ret = retail(args, f"{venue}dd.iff", "stadium", "banner_away_team")
    im = canvas(w, h, WHITE)
    d = ImageDraw.Draw(im)
    half = h // 2
    d.rectangle((0, 0, w * S, half * S), fill=(1, 51, 105, 255))
    text_box(d, (0, 0, w * S, half * S), "NFL", WHITE + (255,), path=FONT_BLACK, pad=0.18)
    text_box(d, (0, half * S, w * S, h * S), "PLAY 60", (213, 10, 10, 255), path=FONT_BLACK, pad=0.16)
    return cloth(im, ret)


#: The Jets' end zones as painted for 2026 home games (newyorkjets.com gallery "MetLife Stadium Ready for the Jets
#: White Out", 2026-09-20, photo q99xuauee1ju4cbxpyav): rectified through a homography fitted on six yard lines
#: crossed with the hash rows and the far sideline (mean error 1.0 px; both back pylons land on the end zone's
#: corners). Seen from the field, left to right: the plane roundel (the 2024 oval with the plane alone: a white rim,
#: a green ring, the white field and the green plane), then JETS in the 2024 wordmark's letters without the plane,
#: white on the green paint. Boxes in yards from the end zone's left edge (as seen from the field) and the end line.
JETS_EZ_ROUNDEL_YD = (2.85, 1.65, 14.30, 8.62)
JETS_EZ_LETTERS_YD = (15.65, 2.17, 50.08, 7.95)
#: the plane inside the oval's box (fractions): the tail tip and the nose, from the same photo (the wall wraps'
#: roundels agree within 0.03); it is the wordmark's own plane (apex to nose 825 x 178 px there, 7.58 x 1.61 yd here)
JETS_PLANE_TIP = (0.224, 0.290)
JETS_PLANE_NOSE = (0.886, 0.518)
WORDMARK_APEX, WORDMARK_NOSE_X, WORDMARK_BAR_Y = (775, 0), 1600, 190
WORDMARK_LETTERS_Y0 = 237                # the letters start below the plane and the J's connector


def jets_plane_roundel(logos, w, h, style="field"):
    """RGBA (w, h): the Jets' plane roundel. 'field': a white rim, a green ring, the white field and the green plane
    (the painted end zones); 'wrap': a green outline and the green plane on white (the wall wraps)."""
    from scipy import ndimage as ndi
    green = np.array(TEAMS["s19"]["primary"], float)
    white = np.array((245, 246, 244), float)
    oval_img = load_mark(Path(logos) / "New_York_Jets_2024.png").resize((w, h), Image.Resampling.LANCZOS)
    oval = np.asarray(oval_img, dtype=np.float64)[..., 3] / 255.0
    inside = oval > 0.5
    depth = ndi.distance_transform_edt(np.pad(inside, 2))[2:-2, 2:-2]     # the oval touches the image's edges
    wm = load_mark(Path(logos) / "New_York_Jets_2024_wordmark.png")
    k = (JETS_PLANE_NOSE[0] - JETS_PLANE_TIP[0]) * w / (WORDMARK_NOSE_X - WORDMARK_APEX[0])
    blade = wm.crop((WORDMARK_APEX[0] - 4, 0, WORDMARK_NOSE_X, WORDMARK_BAR_Y))
    blade = blade.resize((max(1, int(blade.width * k)), max(1, int(blade.height * k))), Image.Resampling.LANCZOS)
    plane = Image.new("L", (w, h), 0)
    plane.paste(blade.getchannel("A"), (int(round(JETS_PLANE_TIP[0] * w - 4 * k)), int(round(JETS_PLANE_TIP[1] * h))))
    pl = np.asarray(plane, dtype=np.float64) / 255.0
    bar = np.zeros((h, w))                   # the fuselage runs on to the ring, on the mark's own bar rows
    top = JETS_PLANE_TIP[1] * h + (WORDMARK_BAR_Y - 25) * k
    y0, y1 = int(round(top)), int(round(top + 25 * k))
    bar[y0:y1, :int(round(JETS_PLANE_TIP[0] * w + 100 * k))] = 1.0
    pl = np.maximum(pl, bar)
    rgb = np.empty((h, w, 3)); rgb[:] = white
    if style == "field":
        ring = (depth > 0.029 * w) & (depth <= 0.053 * w)
        fill = depth > 0.053 * w
        cover = np.clip(ndi.gaussian_filter(ring.astype(float), 0.6) + pl * fill, 0, 1)[..., None]
    else:
        ring = depth <= 0.027 * w
        cover = np.clip(ndi.gaussian_filter(ring.astype(float), 0.6) * inside + pl * inside, 0, 1)[..., None]
    rgb = rgb * (1 - cover) + green * cover
    return Image.fromarray(np.dstack([rgb, oval * 255]).clip(0, 255).astype(np.uint8), "RGBA")


def jets_endzones(args):
    """Three 256x128 overlays across the end zone: the green paint (opaque), the plane roundel
    and JETS (the 2024 letters without the plane) where the 2026 photo has them (JETS_EZ_*). The strip covers
    53.33 x 10 yards."""
    t = TEAMS["s19"]
    W, H = 768, 128
    px, py = W * S / 53.333, H * S / 10.0
    im = canvas(W, H, t["primary"] + (255,))
    x0, y0, x1, y1 = JETS_EZ_ROUNDEL_YD
    roundel = jets_plane_roundel(args.logos, int(round((x1 - x0) * px)), int(round((y1 - y0) * py)), "field")
    im.alpha_composite(roundel, (int(round(x0 * px)), int(round(y0 * py))))
    wm = load_mark(Path(args.logos) / "New_York_Jets_2024_wordmark.png")
    letters = tint(wm.crop((0, WORDMARK_LETTERS_Y0, wm.width, wm.height)).crop(
        wm.crop((0, WORDMARK_LETTERS_Y0, wm.width, wm.height)).getbbox()), WHITE)
    x0, y0, x1, y1 = JETS_EZ_LETTERS_YD
    im.alpha_composite(letters.resize((int(round((x1 - x0) * px)), int(round((y1 - y0) * py))), Image.Resampling.LANCZOS),
                       (int(round(x0 * px)), int(round(y0 * py))))
    arr = np.asarray(im, dtype=np.float64).copy()
    arr[..., 3] = 255
    im = Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGBA")
    return [im.crop((k * 256 * S, 0, (k + 1) * 256 * S, H * S)) for k in range(3)]


#: The Jets' midfield as painted for 2026 home games (newyorkjets.com gallery "MetLife Stadium Ready for the Jets
#: White Out", 2026-09-20): the 2024 logo with its colours reversed (a white oval, a thin green ring just inside
#: the white rim, green JETS and plane), about 14.8 yards along the field (measured against the yard lines around
#: it) and 8.85 across: the logo keeps its own 1.67:1 oval, which the hash rows at 10 ft 3 in confirm. The retail center_logo quad is 10 x 9.26 yards; the s19 quad rule makes it 15.2 x 9.26.
JETS_MIDFIELD_YD = (14.8, 8.85)
JETS_QUAD_YD = (7.6, 4.63)             # half extents: along, across


def jets_midfield(args):
    from scipy import ndimage as ndi
    logo = np.asarray(load_mark(Path(args.logos) / "New_York_Jets_2024.png"), dtype=np.float64)
    a = logo[..., 3] / 255.0
    ys, xs = np.where(a > 0.5)
    logo, a = logo[ys.min():ys.max() + 1, xs.min():xs.max() + 1], a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    white = (logo[..., :3].min(-1) > 180) & (a > 0.5)
    inside = ndi.binary_fill_holes((a > 0.5) & ~white)            # the green interior with the letters in it
    letters = white & inside
    ring_px = logo.shape[1] * 0.25 / JETS_MIDFIELD_YD[0]          # the painted green line, about 0.25 yd
    line = inside & ~letters & (ndi.distance_transform_edt(inside) <= ring_px)
    green = np.array([17, 87, 64], float)
    rgb = np.empty(logo.shape[:2] + (3,))
    rgb[:] = (245, 246, 244)
    m = ndi.gaussian_filter((letters | line).astype(float), 1.0)[..., None]
    rgb = rgb * (1 - m) + green * m
    mark = Image.fromarray(np.dstack([rgb, a * 255]).clip(0, 255).astype(np.uint8), "RGBA")
    W, H = 256 * S, 256 * S
    w = int(round(W * JETS_MIDFIELD_YD[0] / (2 * JETS_QUAD_YD[0])))
    h = int(round(H * JETS_MIDFIELD_YD[1] / (2 * JETS_QUAD_YD[1])))
    im = canvas(256, 256, (0, 0, 0, 0))
    im.alpha_composite(mark.resize((w, h), Image.LANCZOS), ((W - w) // 2, (H - h) // 2))
    return im


# --- the Giants midfield helmet (b76-u5b) ------------------------------------------------------------

#: The official photo the painted midfield is measured from: Giants (@Giants), 2024-08-08, "New look at mid-field",
#: https://x.com/Giants/status/1821636498338320575 (pbs.twimg.com/media/GUfALkeXkAAV7Z2.jpg, 1920x1080). The
#: helmet (the current helmet design with the white ny, 2024-present; the Legacy Games use the classic helmet) is
#: painted from about one 42-yard line to the other. The homography maps field yards (X along the field from the
#: 50, + toward the end the facemask faces; Y across, + the far side) to photo pixels; fitted on 38 points: the
#: yard lines from the 35 to the 35 crossed with the two hash rows (the rows through the 2-ft marks' centres, 10 ft
#: 3 in either side of the centre line, as the marks run from 9 ft 3 in to 11 ft 3 in) and 24 points on the
#: sidelines' inner edges (26.67 yd out). Reprojection error under 2 px, mean 0.6 px. (The first fit put the hash
#: rows at 9 ft 3 in and read the whole field 11% narrow; the Jets' 2026 end-zone photo confirms the rows: its
#: fit drops from a 5.5 px to a 1.0 px mean error with them.)
MIDFIELD_PHOTO_SHA256 = "c474da9cbc31c9a6e300a465fc857cb2af10a550e89d1359663a39649ca47828"
MIDFIELD_H = [[10.588278340863134, 10.10876491476528, 963.7679636174207],
              [-0.05288419878829021, 3.3223829166668475, 740.6496527803732],
              [-0.00012570602058484463, 0.010500874825490126, 1.0]]
#: The midfield quad the helmet needs (yards): the retail center_logo quad is 10 x 9.26 yd; the helmet with its
#: outline and facemask spans about 16.1 yd along the field and 14.6 yd across (shell 13.0)
MIDFIELD_QUAD_YD = (8.4, 8.3)            # half extents: X along the field, Y across
YARD_M = 0.9144


def giants_midfield_helmet(args):
    """The 2024-present Giants midfield helmet as a 1024x1024 RGBA master (the center_logo texture, 256x256).

    Measured, not guessed: the official photo is rectified to a top-down view at 60 px/yd through the fitted
    homography; the shell, its white outline, the red stripe along its top edge, the ear hole, the snaps and the
    back patch are traced from the paint colours and redrawn with clean edges; the facemask keeps the photo's own
    paint lightness (a soft alpha, grey bars inside white rims), with the yard line and hash ticks that show through
    it filtered out; the ny is the official mark (u1's white fill), fitted to the painted letter box, with the thin
    navy edge the painted letters have. Texture axes: u runs along the field toward the end the facemask faces,
    v across from the far side (the retail center_logo mapping, upright from the broadcast side).
    """
    from scipy import ndimage as ndi
    photo_path = Path(args.midfield_photo)
    assert hashlib.sha256(photo_path.read_bytes()).hexdigest() == MIDFIELD_PHOTO_SHA256, "midfield photo differs"
    photo = np.asarray(Image.open(photo_path).convert("RGB"), dtype=np.float64)
    H = np.array(MIDFIELD_H)
    ppy = 60
    hx, hy = MIDFIELD_QUAD_YD
    X0, Y0 = -hx, hy
    Wd_, Hd_ = int(round(2 * hx * ppy)), int(round(2 * hy * ppy))
    GX, GY = np.meshgrid(X0 + (np.arange(Wd_) + 0.5) / ppy, Y0 - (np.arange(Hd_) + 0.5) / ppy)
    P = H @ np.stack([GX.ravel(), GY.ravel(), np.ones(GX.size)])
    u = (P[0] / P[2]).reshape(GX.shape)
    v = (P[1] / P[2]).reshape(GX.shape)
    u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    raw = (photo[v0, u0] * (1 - fu) * (1 - fv) + photo[v0, u0 + 1] * fu * (1 - fv)
           + photo[v0 + 1, u0] * (1 - fu) * fv + photo[v0 + 1, u0 + 1] * fu * fv)
    img = ndi.gaussian_filter(raw, (1.2, 1.2, 0))
    r_, g_, b_ = img[..., 0], img[..., 1], img[..., 2]
    bright = img.min(-1) > 140

    def disk(r):
        y, x = np.ogrid[-r:r + 1, -r:r + 1]
        return x * x + y * y <= r * r

    def smoothstep(a, b, x):
        t = np.clip((x - a) / (b - a), 0, 1)
        return t * t * (3 - 2 * t)

    def largest(mask):
        lab, n = ndi.label(mask)
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        return lab == sizes.argmax()

    blue = (b_ > r_ + 45) & (b_ > g_ + 15)
    red = (r_ > g_ + 45) & (r_ > b_ + 25)
    shell = largest(ndi.binary_fill_holes(ndi.binary_closing(blue | red, structure=disk(4))))
    shell = ndi.gaussian_filter(shell.astype(float), 6.0) > 0.5
    # facemask: the photo's paint lightness in front of the ear hole; thin bright lines with turf both sides
    # (the yard line, the hash ticks) are the field showing through, not the mask
    zone = (GX > 1.3) & (GY < 2.59) & (~ndi.binary_erosion(shell, structure=disk(36)) | (GY < 1.08))
    lum = ndi.gaussian_filter(raw.min(-1), 0.8)
    mask = smoothstep(118, 172, lum) * zone
    thin = (lum > 140) & (np.roll(lum, 8, axis=1) < 115) & (np.roll(lum, -8, axis=1) < 115)
    mask = mask * ~ndi.binary_dilation(thin, structure=np.ones((1, 7)))
    mask = mask * ndi.binary_dilation(largest(mask > 0.5), structure=disk(3))
    mask_white = smoothstep(196, 226, lum)
    # red stripe: a band of constant width inside the shell edge wherever the paint is red along it
    # (k2, 2026-09-24: the photo's red paint reaches 0.32 yd in from the shell edge at p90 and 0.35 at p95 on this
    # rectification, so the band is 0.34 yd; it was 0.24)
    stripe = shell & (ndi.distance_transform_edt(shell) <= 0.34 * ppy) & ndi.binary_dilation(red, structure=disk(18))
    stripe = ndi.gaussian_filter(stripe.astype(float), 1.5) > 0.5
    # white details: ear hole and snaps inside the shell, the back patch at its lower rear rim
    ny_zone = (GX > -4.6) & (GX < 1.7) & (GY > 0.86) & (GY < 5.99)
    details = bright & ndi.binary_erosion(shell, structure=disk(8)) & ~ny_zone & (GX < 1.3)
    details = ndi.gaussian_filter(ndi.binary_opening(details, structure=disk(2)).astype(float), 1.6) > 0.5
    back = bright & (GX < -5.5) & (GY < 0.30) & (GY > -2.82) & ~ndi.binary_erosion(shell, structure=disk(3))
    back = ndi.gaussian_filter(ndi.binary_opening(back, structure=disk(3)).astype(float), 2.0) > 0.5
    rr, cc = np.where(bright & ny_zone & shell)
    ny_box = (cc.min(), rr.min(), cc.max() + 1, rr.max() + 1)
    outline = ndi.binary_fill_holes((ndi.distance_transform_edt(~shell) <= 0.33 * ppy) | back)
    outline = ndi.gaussian_filter(outline.astype(float), 1.5) > 0.5

    white = np.array([244, 245, 247], float)
    # the painted blue measured on the rectified photo's shell (13, 55, 107), at the luminance of the earlier value
    # (24, 55, 140), which was bluer and more saturated than the paint (k2, 2026-09-24)
    blue_paint = np.array([14, 60, 117], float)
    red_paint = np.array([167, 25, 48], float)         # Giants red, #A71930
    grey = np.array([165, 172, 175], float)            # facemask grey, #A5ACAF
    navy = np.array([10, 26, 72], float)

    def soft(m, s=0.9):
        return np.clip(ndi.gaussian_filter(m.astype(float), s), 0, 1)

    rgb = np.empty((Hd_, Wd_, 3))
    rgb[:] = white
    alpha = soft(outline)

    def paint(m, colour, s=0.9):
        a = soft(m, s)[..., None]
        rgb[:] = rgb * (1 - a) + colour * a

    paint(shell, blue_paint)
    paint(stripe, red_paint)
    paint(details, white)
    decal = load_mark(Path(args.giants) / "marks" / "ny_logo_fill_white.png")
    bx0, by0, bx1, by1 = ny_box
    letters = np.asarray(decal.resize((bx1 - bx0, by1 - by0), Image.LANCZOS), dtype=np.float64)[..., 3] / 255.0
    edge = ndi.binary_dilation(letters > 0.5, structure=disk(2)) & ~(letters > 0.5)
    sub = rgb[by0:by1, bx0:bx1]
    e = soft(edge, 0.6)[..., None]
    sub[:] = sub * (1 - e) + navy * e
    sub[:] = sub * (1 - letters[..., None]) + white * letters[..., None]
    colour = grey * (1 - mask_white[..., None]) + white * mask_white[..., None]
    rgb[:] = rgb * (1 - mask[..., None]) + colour * mask[..., None]
    alpha = np.maximum(alpha, mask)
    out = Image.fromarray(np.dstack([rgb, alpha * 255]).clip(0, 255).astype(np.uint8), "RGBA")
    return out.resize((256 * S, 256 * S), Image.LANCZOS)


def giants_endzones(args):
    """The Giants' end zones (2023-present regular design): three 256x128 overlays across the end zone.

    From the official 2024-08-08 photo, rectified through the midfield homography (reading orientation, from the
    goal line): royal blue paint; the 1976 GIANTS wordmark with its underline centred, about 15.5 yards wide;
    the white ny near each sideline, centred about 18.9 yards from the middle and 5.2 yards wide; every white mark
    edged in dark navy (the letter edges run white -> near-black navy -> blue in the photo, no red). The 2026
    week 1 photos show the same royal blue paint and white letters. Drawn in yards at the texture's own
    anisotropy (the strip is 53.44 x 10.06 yards on 768x128 texels), so the marks keep their true proportions.
    """
    from scipy import ndimage as ndi
    W, H = 768 * S, 128 * S
    yd_w, yd_h = 53.44, 10.06
    sx, sy = W / yd_w, H / yd_h
    paint = (28, 63, 158)
    white = (245, 246, 248)
    navy = (10, 26, 72)
    marks = Image.new("L", (W, H), 0)

    def put(mark, cx_yd, cy_yd, w_yd, h_yd):
        m = mark.resize((int(round(w_yd * sx)), int(round(h_yd * sy))), Image.LANCZOS).getchannel("A")
        marks.paste(Image.fromarray(np.maximum(np.asarray(marks.crop(
            (int(round(cx_yd * sx - m.width / 2)), int(round(cy_yd * sy - m.height / 2)),
             int(round(cx_yd * sx - m.width / 2)) + m.width, int(round(cy_yd * sy - m.height / 2)) + m.height))),
            np.asarray(m))), (int(round(cx_yd * sx - m.width / 2)), int(round(cy_yd * sy - m.height / 2))))

    word = load_mark(Path(args.logos) / "New_York_Giants_wordmark.png")
    ny = load_mark(Path(args.giants) / "marks" / "ny_logo_fill_white.png")
    ww = 15.5
    put(word, yd_w / 2, 4.66, ww, ww * word.height / word.width)
    for side in (-1, 1):
        put(ny, yd_w / 2 + side * 18.9, 4.76, 5.2, 5.2 * ny.height / ny.width)
    a = np.asarray(marks, dtype=np.float64) / 255.0
    # the navy edge: 0.13 yd around every mark (elliptical in texels because the strip is anisotropic)
    ry, rx = 0.13 * sy, 0.13 * sx
    yy, xx = np.ogrid[-int(ry) - 1:int(ry) + 2, -int(rx) - 1:int(rx) + 2]
    edge = ndi.grey_dilation(a, footprint=(xx / rx) ** 2 + (yy / ry) ** 2 <= 1.0)
    rgb = np.empty((H, W, 3))
    rgb[:] = paint
    rgb = rgb * (1 - edge[..., None]) + np.array(navy) * edge[..., None]
    rgb = rgb * (1 - a[..., None]) + np.array(white) * a[..., None]
    # opaque (b76-u5b): the overlay composites over the retail end zone, and the old 235 alpha let 8% of it through,
    # the retail wordmark included, as a faint offset ghost that read as a drop shadow
    alpha = np.full((H, W), 255.0)
    im = Image.fromarray(np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8), "RGBA")
    return [im.crop((k * 256 * S, 0, (k + 1) * 256 * S, H)) for k in range(3)]


# --- driver ----------------------------------------------------------------------------------------------

def save(master, w, h, rel, args, record):
    out = OUT / "art" / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    small = reduce(master, w, h)
    small.save(out, optimize=True)
    mpath = Path(args.masters) / rel
    mpath.parent.mkdir(parents=True, exist_ok=True)
    master.save(mpath, optimize=True)
    record.append(dict(art=f"art/{rel}", master=str(mpath), size=[w, h],
                       sha256=hashlib.sha256(out.read_bytes()).hexdigest()))
    return f"art/{rel}"


def copy_giants(args, record):
    """u1's Giants items (metlife_team_art/v1) become the s18 overlays and fan banners."""
    manifest = json.loads((Path(args.giants) / "manifest.json").read_text())
    assert manifest["schema"] == "metlife_team_art/v1" and manifest["venue_prefix"] == "s18"
    items = []
    for item in manifest["items"]:
        if item["material"] == "center_logo" or item["material"].startswith("endzone_N_"):
            continue                     # b76-u5b: the midfield helmet and the navy-edged end zones replace u1's
        src = Path(args.giants) / item["file"]
        data = src.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], f"{src} differs from its manifest"
        rel = f"s18/{item['scene']}/{item['material']}.png"
        out = OUT / "art" / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        record.append(dict(art=f"art/{rel}", master=str(Path(args.giants) / item["master"]), size=item["size"],
                           sha256=item["sha256"], source="u1 metlife_team_art/v1"))
        items.append((item, f"art/{rel}"))
    return items


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--retail", required=True)
    parser.add_argument("--logos", required=True)
    parser.add_argument("--giants", required=True)
    parser.add_argument("--masters", required=True)
    parser.add_argument("--midfield-photo", required=True, help="the official 2024-08-08 Giants midfield photo")
    args = parser.parse_args(argv)
    record = []
    patches, overlays = [], []
    for venue in ("s18", "s19"):
        for name, fn, size in (("banner01", banner01, (256, 256)), ("banner02", banner02, (256, 256)),
                               ("banner04", banner04, (256, 128))):
            rel = save(fn(venue, args.logos, args.giants), *size, f"{venue}/stadium/{name}.png", args, record)
            patches.append(dict(scene="stadium", material=name, venues=[venue], art=rel))
        m, rects = boards_ad_bb02(venue, args.logos, args.giants)
        rel = save(m, 256, 256, f"{venue}/stadium/ad_bb02.png", args, record)
        patches.append(dict(scene="stadium", material="ad_bb02", aliases=["LIGHT_ad_bb02"], venues=[venue], art=rel, rects=rects))
        m, rects = boards_ad_bb01(venue, args.logos, args.giants)
        rel = save(m, 256, 256, f"{venue}/stadium/ad_bb01.png", args, record)
        patches.append(dict(scene="stadium", material="ad_bb01", aliases=["LIGHT_ad_bb01"], venues=[venue], art=rel, rects=rects))
        rel = save(corp_banners(args, venue, (256, 256)), 256, 256, f"{venue}/stadium/banner_corp.png", args, record)
        patches.append(dict(scene="stadium", material="banner_corp", venues=[venue], art=rel))
    # Giants pads and away banners; Jets walls, banners and field
    rel = save(wall_pad("s18", args, "wall01", (128, 128)), 128, 128, "s18/stadium/wall01.png", args, record)
    patches.append(dict(scene="stadium", material="wall01", venues=["s18"], art=rel, snow_drift=True))
    rel = save(away_generic(args, "s18", (128, 128)), 128, 128, "s18/stadium/banner_away_team.png", args, record)
    patches.append(dict(scene="stadium", material="banner_away_team", venues=["s18"], art=rel))
    rel = save(jets_wall01(args, (256, 256)), 256, 256, "s19/stadium/wall01.png", args, record)
    patches.append(dict(scene="stadium", material="wall01", venues=["s19"], art=rel, rects=[[0, 0, 256, 128]],
                        snow_drift=True))
    rel = save(jets_wall04(args, (128, 128)), 128, 128, "s19/stadium/wall04.png", args, record)
    patches.append(dict(scene="stadium", material="wall04", venues=["s19"], art=rel))
    for material, size in (("banner_home_team", (128, 128)), ("banner_home_player", (256, 128)),
                           ("banner_away_team", (128, 128))):
        rel = save(fan_banners_jets(args, material, size), *size, f"s19/stadium/{material}.png", args, record)
        patches.append(dict(scene="stadium", material=material, venues=["s19"], art=rel))
    for material, img in zip(("endzone_N_L", "endzone_N_M", "endzone_N_R"), jets_endzones(args)):
        rel = save(img, 256, 128, f"s19/field/{material}.png", args, record)
        overlays.append(dict(scene="field", material=material, aliases=[material.replace("_N_", "_S_")], venues=["s19"], art=rel))
    rel = save(jets_midfield(args), 256, 256, "s19/field/center_logo.png", args, record)
    # The midfield mark replaces the retail NFL shield outright (its own alpha); the end zones are paint
    # composited over each variant's turf.
    patches.append(dict(scene="field", material="center_logo", venues=["s19"], art=rel))
    rel = save(giants_midfield_helmet(args), 256, 256, "s18/field/center_logo.png", args, record)
    patches.append(dict(scene="field", material="center_logo", venues=["s18"], art=rel))
    for material, img in zip(("endzone_N_L", "endzone_N_M", "endzone_N_R"), giants_endzones(args)):
        rel = save(img, 256, 128, f"s18/field/{material}.png", args, record)
        overlays.append(dict(scene="field", material=material, aliases=[material.replace("_N_", "_S_")],
                             venues=["s18"], art=rel))
    for item, rel in copy_giants(args, record):
        entry = dict(scene=item["scene"], material=item["material"], venues=["s18"], art=rel)
        if item["material"].startswith("endzone_N_"):
            entry["aliases"] = [item["material"].replace("_N_", "_S_")]
            overlays.append(entry)
        else:
            patches.append(entry)
    palette_kinds = {
        "seat_charcoal": dict(kind="grey_ramp", scale=1.45, tint=[0.97, 1.0, 1.05], hue=[-40, 60], min_sat=0.12,
                              neutral_scale=1.0, neutralize=0.6, max=230),
        "steel_silver": dict(kind="neutral", amount=0.75, gain=1.12, lift=6.0, tint=[0.97, 1.0, 1.04]),
        "structure_neutral": dict(kind="neutral", amount=0.55, gain=1.0, lift=0.0, tint=[0.98, 1.0, 1.03]),
        "glass_cool": dict(kind="neutral", amount=0.35, gain=0.92, lift=0.0, tint=[0.92, 1.0, 1.12]),
    }
    palette_rules = [
        dict(scene="stadium", material="seat01", rule="seat_charcoal"),
        dict(scene="stadium", material="seat02", rule="seat_charcoal"),
        dict(scene="stadium", material="seat03", rule="seat_charcoal"),
        dict(scene="stadium", material="roof01", rule="steel_silver"),
        dict(scene="stadium", material="cement01", rule="structure_neutral"),
        dict(scene="stadium", material="lite02", rule="steel_silver"),
        dict(scene="stadium", material="suite01", aliases=["LIGHT_suite01"], rule="glass_cool"),
        dict(scene="stadium", material="suite02", aliases=["LIGHT_suite02"], rule="glass_cool"),
        dict(scene="stadium", material="suite03", aliases=["LIGHT_suite03"], rule="glass_cool"),
        dict(scene="stadium", material="suite04", aliases=["LIGHT_suite04"], rule="glass_cool"),
    ]
    # MetLife has no rooftop press box and no light towers (its lights sit under the roof ring). The west
    # press box with its two lamp banks (group41, group43, group44), the four corner towers (group40, 42,
    # 45, 50) and the two east banks (group47, s19_8) collapse: every vertex goes to the shape's retail
    # bounding-sphere centre, so the triangles have no area and every vertex stays inside the sphere the
    # culling reads (moving or lowering them was refused: the retail spheres are tight). Same shapes, same
    # vertex counts and streams in both venues and all eighteen bundles.
    geometry = [dict(scene="stadium", shape=name, mode="collapse", note=note) for name, note in (
        ("group41", "press box north half and its lamp bank"), ("group43", "press box south half and its lamp bank"),
        ("group44", "press box centre"), ("group40", "light tower, north-west corner"),
        ("group42", "light tower, south-west corner"), ("group45", "light tower, north-east corner"),
        ("group50", "light tower, south-east corner"), ("group47", "lamp bank, east rim north"),
        ("s19_8", "lamp bank, east rim south"))]
    # The fourteen light-glow markers and the four lens-flare markers sat on those lamps; each moves onto
    # the roof rim on its own bearing (1.5 m above the rim top at 58.3 m, 2 m inside the rim's outer edge
    # measured on that bearing), so glows and flares come from the ring, not from the air where a lamp
    # was. The flare markers are also the player-shadow lights of shadow mode 2: those lights drop from
    # 67 to 82 m to 59.8 m on the same bearings (longer shadows, same directions).
    # b76-u5b: the Giants' midfield helmet is painted about 16 x 14 yards (one 42-yard line to the other); the
    # retail center_logo quad is 10 x 9.26 yards, so its four corners move out (same vertices, same UVs).
    geometry.append(dict(scene="field", material="center_logo", venues=["s19"], mode="quad",
                         retail_half_extent_m=[4.233, 4.576],
                         half_extent_m=[round(JETS_QUAD_YD[1] * YARD_M, 3), round(JETS_QUAD_YD[0] * YARD_M, 3)],
                         note="the Jets' midfield oval at its painted size (x across, z along)"))
    geometry.append(dict(scene="field", material="center_logo", venues=["s18"], mode="quad",
                         retail_half_extent_m=[4.233, 4.576],
                         half_extent_m=[round(MIDFIELD_QUAD_YD[1] * YARD_M, 3), round(MIDFIELD_QUAD_YD[0] * YARD_M, 3)],
                         note="the midfield helmet at its painted size (x across, z along)"))
    markers = [dict(scene="stadium", marker=f"marker_lightShape{k}", retail_sha256=[digest], position_m=list(xyz))
               for k, (digest, xyz) in LIGHT_MARKERS.items()]
    markers += [dict(scene="stadium", marker=name, retail_sha256=[digest], position_m=list(xyz))
                for name, (digest, xyz) in FLARE_MARKERS.items()]
    rules = dict(schema="nfl2k5_modern_metlife_rules/v1", palette_kinds=palette_kinds, palette_rules=palette_rules,
                 patches=patches, overlays=overlays, geometry=geometry, markers=markers,
                 notes="Authored by tools/nfl2k5_modern_metlife_art.py; see docs/modern_metlife/README.md")
    (OUT / "rules.json").write_text(json.dumps(rules, indent=1) + "\n", encoding="utf-8", newline="\n")
    (Path(args.masters) / "masters.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    print(f"{len(record)} textures, {len(patches)} patches, {len(overlays)} overlays, {len(palette_rules)} palette rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
