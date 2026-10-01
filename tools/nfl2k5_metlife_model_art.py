#!/usr/bin/env python3
"""Draw the MetLife model's own textures (u5): the aluminium louvres, the limestone base and the Solar Ring
panels, procedurally, at their retail-size P8 targets. Deterministic (fixed seed); no web art or retail bytes.

  python3 tools/nfl2k5_metlife_model_art.py [OUT_DIR]   (default data/nfl2k5_metlife_model/art)
  python3 tools/nfl2k5_metlife_model_art.py --masters DIR   (the 4x masters for the 2K5 Edition pack)

The louvre spacing, the stone coursing and the panel grid follow the reference photos listed in the u5 report.
"""
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))


def louvres(rng):
    """128x128 = 8 x 8 m of facade (the model maps 1/8 of the texture per metre): aluminium louvres 0.5 m apart
    (8 px): a thin bright fin face, its shadow and the dark gap behind; a heavier storey line every 4 m (64 px) and
    a mullion every 4 m (64 px). Coarse enough to read at a distance without shimmering. Tone from the Commons
    exterior photos (MetLife_Stadium_2022, MetLife_Stadium_East_Rutherford_NJ): the louvre field averages about
    (76, 81, 88) with the fin faces near 210 and the gaps near black."""
    a = np.zeros((128, 128, 3), float)
    for y in range(128):
        ph = y % 8
        a[y, :] = {0: (214, 217, 223), 1: (190, 194, 201), 2: (124, 129, 137), 3: (58, 62, 70),
                   4: (36, 40, 48), 5: (30, 34, 42), 6: (30, 34, 42), 7: (34, 38, 46)}[ph]
    for y0 in range(0, 128, 64):
        a[y0 + 60:y0 + 64, :] = (40, 43, 50)
    for x in range(0, 128, 64):
        a[:, x:x + 2] = a[:, x:x + 2] * 0.55 + np.array([50, 54, 60]) * 0.45
    return a + rng.normal(0, 2.0, a.shape)


def limestone(rng):
    """64x64: limestone-like courses, 16 px high, running bond."""
    b = np.full((64, 64, 3), (196, 188, 172), float)
    for y in range(0, 64, 16):
        b[y:y + 1] *= 0.82
    for y0 in range(0, 64, 16):
        off = 0 if (y0 // 16) % 2 == 0 else 16
        for x in range(off, 64, 32):
            b[y0:y0 + 16, x:x + 1] *= 0.85
    return b + rng.normal(0, 5, b.shape)


def ring_panel(rng):
    """128x64: the Solar Ring's photovoltaic glass seen from above: two rows of eight panels, light grey-blue
    glass with a sky sheen, silver frames (the aerials show the ring light, not black)."""
    c = np.full((64, 128, 3), (118, 130, 150), float)
    yy = np.linspace(0, 1, 64)[:, None]
    c += (yy * 30)[..., None] * np.array([1.0, 1.0, 1.1])
    for x in range(0, 128, 16):
        c[:, x:x + 1] = (196, 200, 206)
    for y in range(0, 64, 32):
        c[y:y + 1, :] = (196, 200, 206)
    for x in range(0, 128, 4):
        c[:, x] = c[:, x] * 0.95
    return c + rng.normal(0, 3, c.shape)


FONT = "/usr/share/fonts/truetype/roboto/unhinted/RobotoCondensed-Bold.ttf"
LOGO = Path("/media/noah/Storage/.b76-research/u2/refs/logos/MetLife_logo.png")   # Commons, public domain


def letters(_rng, master=False):
    """512x64 RGBA: METLIFE STADIUM in silver-white condensed capitals (drawn at 4x, reduced; ``master`` returns
    the 4x drawing for the 2K5 Edition pack)."""
    from PIL import ImageDraw, ImageFont
    W, H = 2048, 256
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(FONT, 236)
    text = "METLIFE STADIUM"
    w = d.textlength(text, font=font)
    x0 = (W - w) / 2
    d.text((x0, -18), text, font=font, fill=(236, 238, 242, 255))
    if master:
        return np.asarray(im).astype(float)
    return np.asarray(im.resize((512, 64), Image.LANCZOS)).astype(float)


def logo(_rng, master=False):
    """256x64 RGBA: the MetLife mark on a dark panel (the end-zone and facade signs); ``master`` returns the 4x
    panel."""
    panel = Image.new("RGBA", (1024, 256), (22, 26, 34, 255))
    if LOGO.is_file():
        mark = Image.open(LOGO).convert("RGBA")
        mark.thumbnail((900, 200))
        # the wordmark is blue on transparent; the signs show it white beside the coloured squares
        a = np.asarray(mark).astype(float)
        blue = (a[..., 2] > a[..., 1] + 30) & (a[..., 0] < 80) & (a[..., 3] > 0)
        cols = np.where(blue.any(axis=0))[0]
        text_start = int(cols.max() * 0.30) if cols.size else 0
        a[:, text_start:, :3] = np.where(a[:, text_start:, 3:4] > 0, 245, a[:, text_start:, :3])
        mark = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
        panel.alpha_composite(mark, ((1024 - mark.size[0]) // 2, (256 - mark.size[1]) // 2))
    if master:
        return np.asarray(panel).astype(float)
    return np.asarray(panel.resize((256, 64), Image.LANCZOS)).astype(float)


def portal(_rng):
    """32x32: a vomitory opening, dark inside with a lit soffit and a concrete frame."""
    a = np.full((32, 32, 3), (18, 20, 24), float)
    a[:3, :, :] = (150, 150, 145)
    a[:, :3, :] = (150, 150, 145)
    a[:, -3:, :] = (150, 150, 145)
    a[3:6, 6:26, :] = (210, 205, 180)
    return a


GIANTS_NY = Path("/media/noah/Storage/.b76-research/u1/metlife_handoff/giants/marks/ny_logo_decal_white_red.png")
JETS_LOGO = Path("/media/noah/Storage/.b76-research/u1/teams/NYJ/marks/nyj_logo_full.png")
GIANTS_BLUE = (0, 19, 85, 255)          # the helmet shell blue the retail atlas uses


def _fit(mark, box):
    """The mark scaled to fit the box (w, h), centred on a transparent canvas of the box size."""
    m = mark.copy()
    m.thumbnail(box, Image.LANCZOS)
    canvas = Image.new("RGBA", box, (0, 0, 0, 0))
    canvas.alpha_composite(m, ((box[0] - m.size[0]) // 2, (box[1] - m.size[1]) // 2))
    return canvas


def crowd_hats18(_rng):
    """128x128 overlay for the Giants superfan helmet (crowds18 hats18): Giants blue over the two retail 1976
    wordmarks (rects y 31-49 / 79-96, x 27-78) and the 2026 ny helmet logo in each, the upper one turned 180 degrees
    like the retail wordmark it replaces (the other side of the shell)."""
    out = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    ny = Image.open(GIANTS_NY).convert("RGBA")
    for (x0, y0, x1, y1), turn in (((25, 29, 80, 51), True), ((25, 77, 80, 98), False)):
        box = (x1 - x0, y1 - y0)
        out.paste(Image.new("RGBA", box, GIANTS_BLUE), (x0, y0))
        logo = _fit(ny, (box[0] - 8, box[1] - 2))
        if turn:
            logo = logo.rotate(180)
        out.alpha_composite(logo, (x0 + 4, y0 + 1))
    return np.asarray(out).astype(float)


def crowd_hats19(_rng):
    """128x128 overlay for the Jets superfan hard hat (crowds19 hats19): the retail 'jetfan GO JETS' crest box (y 0-46,
    x 80-127) becomes a white panel with the 2024 Jets logo."""
    out = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (48, 47), (236, 238, 236, 255)), (80, 0))
    out.alpha_composite(_fit(Image.open(JETS_LOGO).convert("RGBA"), (44, 40)), (82, 3))
    return np.asarray(out).astype(float)


# --- the corner boards (b76-u5b) -----------------------------------------------------------------------
#: Each 35 x 9.1 m corner board is a live-video window (the game's jumbo_tron feed, cropped to the window's own
#: aspect) and, on its inner side, an 11.5 m game-information panel, as the MetLife boards show them on game day
#: (Commons MetLifeStadiumJets3, 2022: TIME / QTR / DOWN beside the video). The panel's labels and slots are
#: drawn here; the game's own digit quads (score, clock, play clock) are placed over the slots by the model.
PANEL_M = (11.5, 9.1)
#: slot boxes on the panel in metres from its top-left corner: (material, x0, y0, x1, y1)
PANEL_SLOTS = [
    ("digit_home_score_L", 7.70, 0.70, 8.80, 2.40), ("digit_home_score_R", 8.95, 0.70, 10.05, 2.40),
    ("digit_away_score_L", 7.70, 2.90, 8.80, 4.60), ("digit_away_score_R", 8.95, 2.90, 10.05, 4.60),
    ("digit_clock_1", 5.95, 5.10, 7.05, 6.80), ("digit_clock_2", 7.15, 5.10, 8.25, 6.80),
    ("digit_clock_3", 8.65, 5.10, 9.75, 6.80), ("digit_clock_4", 9.85, 5.10, 10.95, 6.80),
    ("digit_playclock_L", 7.70, 7.30, 8.80, 9.00), ("digit_playclock_R", 8.95, 7.30, 10.05, 9.00),
]
FONT_BLACK = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Black.ttf"
PANEL_TEAM = {"s18": dict(name="GIANTS", top=(12, 30, 92), bottom=(4, 10, 32), accent=(167, 25, 48)),
              "s19": dict(name="JETS", top=(10, 66, 46), bottom=(3, 18, 12), accent=(236, 240, 238))}


def _text(draw, box, text, font_path, fill, max_h):
    from PIL import ImageFont
    x0, y0, x1, y1 = box
    size = int(max_h)
    while size > 8:
        font = ImageFont.truetype(font_path, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= x1 - x0 and b - t <= y1 - y0:
            break
        size -= 2
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text((x0 - l, (y0 + y1) / 2 - (t + b) / 2), text, font=font, fill=fill)


def board_panel(venue, master=False):
    """256x128 (1024x512 master) RGBA: the game-information panel of a corner board, drawn at 100 px/m on its
    true 11.5 x 9.1 m aspect and resampled to the texture the panel quad maps."""
    from PIL import ImageDraw
    t = PANEL_TEAM[venue]
    ppm = 100
    W, H = int(PANEL_M[0] * ppm), int(PANEL_M[1] * ppm)
    y = np.linspace(0, 1, H)[:, None, None]
    bg = np.array(t["top"], float) * (1 - y) + np.array(t["bottom"], float) * y
    im = Image.fromarray(np.broadcast_to(bg, (H, W, 3)).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, int(0.22 * ppm)], fill=t["accent"] + (255,))
    for material, x0, y0, x1, y1 in PANEL_SLOTS:            # dark LED slots under the game's digits
        d.rectangle([int(x0 * ppm) - 6, int(y0 * ppm) - 6, int(x1 * ppm) + 6, int(y1 * ppm) + 6], fill=(6, 7, 10, 255))
    white = (242, 244, 246, 255)
    if venue == "s18" and GIANTS_NY.is_file():
        mark = _fit(Image.open(GIANTS_NY).convert("RGBA"), (int(2.2 * ppm), int(1.6 * ppm)))
        im.alpha_composite(mark, (int(0.35 * ppm), int(0.75 * ppm)))
        _text(d, (int(2.75 * ppm), int(0.8 * ppm), int(7.3 * ppm), int(2.3 * ppm)), t["name"], FONT_BLACK, white, 1.4 * ppm)
    elif venue == "s19" and JETS_LOGO.is_file():
        mark = _fit(Image.open(JETS_LOGO).convert("RGBA"), (int(2.6 * ppm), int(1.6 * ppm)))
        im.alpha_composite(mark, (int(0.3 * ppm), int(0.75 * ppm)))
        _text(d, (int(3.1 * ppm), int(0.8 * ppm), int(7.3 * ppm), int(2.3 * ppm)), t["name"], FONT_BLACK, white, 1.4 * ppm)
    else:
        _text(d, (int(0.4 * ppm), int(0.8 * ppm), int(7.3 * ppm), int(2.3 * ppm)), t["name"], FONT_BLACK, white, 1.4 * ppm)
    _text(d, (int(0.4 * ppm), int(3.0 * ppm), int(7.3 * ppm), int(4.5 * ppm)), "VISITORS", FONT, white, 1.25 * ppm)
    _text(d, (int(0.4 * ppm), int(5.2 * ppm), int(5.6 * ppm), int(6.7 * ppm)), "TIME", FONT, white, 1.25 * ppm)
    _text(d, (int(0.4 * ppm), int(7.4 * ppm), int(7.3 * ppm), int(8.9 * ppm)), "PLAY CLOCK", FONT, white, 1.1 * ppm)
    for cy in (5.62, 6.28):                                   # the clock's colon between the slots
        d.ellipse([int(8.33 * ppm), int(cy * ppm) - 11, int(8.33 * ppm) + 22, int(cy * ppm) + 11], fill=(255, 196, 64, 255))
    size = (1024, 512) if master else (256, 128)
    return np.asarray(im.resize(size, Image.LANCZOS)).astype(float)


# --- signage atlas: Ring of Honor plates and the fascia / gate signs (b76-u5b) ----------------------------
#: One 256x512 atlas per venue. Rows 0-299: the Ring of Honor plates, 128x12 cells (10.67:1, the plates are
#: 8.0 x 0.75 m on the 300-level fascia), two columns, up to 50 names, white with dark type as the 2022 Jets2 and
#: the 2026 Jets photos show them ("99 MARK GASTINEAU", "12 JOE NAMATH"). Rows 304-511: 26 sign cells of 128x16
#: (8:1) for the LED ribbon, the club fascia and the gate buildings. Every cell is drawn at its own aspect and the
#: model maps it onto geometry of the same aspect, so nothing is stretched.
ROH_CELL = (128, 12)
SIGN_CELL = (128, 16)
SIGN_Y0 = 304
ROH_JSON = Path(__file__).resolve().parents[1] / "data" / "nfl2k5_metlife_model" / "ring_of_honor.json"
LOGOS = Path("/media/noah/Storage/.b76-research/u2/refs/logos")
SIGNS = ["metlife_white", "metlife_dark", "team_wordmark", "team_logo", "slogan", "metlife_stadium", "verizon",
         "bud_light", "pepsi", "hcltech", "team_city", "team_extra"]


def roh_names(venue):
    data = json.loads(ROH_JSON.read_text(encoding="utf-8"))
    rows = data["giants" if venue == "s18" else "jets"]
    out = []
    for number, name, _year in rows:
        num = str(number).split("<br")[0].split(",")[0].strip()
        label = name.replace('"OJ" ', "").upper()
        out.append(label if num in ("", "—", "-") else f"{num} {label}")
    return out


def signage_atlas(venue, master=False):
    from PIL import ImageDraw
    k = 4 if master else 1
    W, H = 256 * k, 512 * k
    im = Image.new("RGBA", (W, H), (10, 11, 14, 255))
    d = ImageDraw.Draw(im)
    cw, ch = ROH_CELL[0] * k, ROH_CELL[1] * k
    for i, text in enumerate(roh_names(venue)):
        x0, y0 = (i % 2) * cw, (i // 2) * ch
        d.rectangle([x0 + k, y0 + k, x0 + cw - k - 1, y0 + ch - k - 1], fill=(240, 241, 242, 255))
        _text(d, (x0 + 5 * k, y0 + 2 * k, x0 + cw - 5 * k, y0 + ch - 2 * k), text, FONT, (16, 18, 22, 255), ch)
    spec = json.loads(WALL_JSON.read_text(encoding="utf-8"))["venues"][venue].get("number_decals")
    for cell_name, (bx0, by0, bx1, by1) in (spec["cells"].items() if spec else ()):
        number_box(d, (bx0 * k, by0 * k, bx1 * k, by1 * k), cell_name[4:])
    team = TEAM_SIGNS[venue]
    sw, sh = SIGN_CELL[0] * k, SIGN_CELL[1] * k
    for j, key in enumerate(SIGNS):
        x0, y0 = (j % 2) * sw, SIGN_Y0 * k + (j // 2) * sh
        box = (x0, y0, x0 + sw, y0 + sh)
        _sign(im, d, box, key, team, k)
    return np.asarray(im).astype(float)


#: the team cells run end to end on the LED ribbon, so they share one background: the Giants' ribbon in royal blue
#: with white type (the 2025 game photos), the Jets' in black with white type (the 2026-09-20 White Out photos:
#: "JETS", "NEW YORK JETS")
TEAM_SIGNS = {
    "s18": dict(bg=(10, 48, 168), fg=(255, 255, 255), accent=(167, 25, 48), word="GIANTS", city="NEW YORK GIANTS",
                slogan="GO BIG BLUE", extra="SINCE 1925"),
    "s19": dict(bg=(8, 9, 12), fg=(255, 255, 255), accent=(255, 255, 255), word="JETS", city="NEW YORK JETS",
                slogan="J-E-T-S!", extra="NEW YORK JETS"),
}


def _paste_mark(im, path, box, pad, tint=None):
    if not Path(path).is_file():
        return False
    mark = Image.open(path).convert("RGBA")
    if tint is not None:
        a = np.asarray(mark)
        t = np.zeros_like(a); t[..., :3] = tint; t[..., 3] = a[..., 3]
        mark = Image.fromarray(t, "RGBA")
    x0, y0, x1, y1 = box
    fit = _fit(mark, (int((x1 - x0) * (1 - pad)), int((y1 - y0) * (1 - pad))))
    im.alpha_composite(fit, (x0 + ((x1 - x0) - fit.width) // 2, y0 + ((y1 - y0) - fit.height) // 2))
    return True


def _sign(im, d, box, key, team, k):
    x0, y0, x1, y1 = box
    inner = (x0 + 4 * k, y0 + 2 * k, x1 - 4 * k, y1 - 2 * k)
    if key == "metlife_white":
        d.rectangle(box, fill=(250, 250, 250, 255))
        _paste_mark(im, LOGO, box, 0.18)
    elif key == "metlife_dark":
        d.rectangle(box, fill=(12, 14, 19, 255))
        mark = LOGO
        if Path(mark).is_file():                  # the wordmark white beside the coloured squares, as u5's logo sign
            a = np.asarray(Image.open(mark).convert("RGBA")).astype(float)
            blue = (a[..., 2] > a[..., 1] + 30) & (a[..., 0] < 80) & (a[..., 3] > 0)
            cols = np.where(blue.any(axis=0))[0]
            start = int(cols.max() * 0.30) if cols.size else 0
            a[:, start:, :3] = np.where(a[:, start:, 3:4] > 0, 245, a[:, start:, :3])
            m = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
            fit = _fit(m, (int((x1 - x0) * 0.8), int((y1 - y0) * 0.8)))
            im.alpha_composite(fit, (x0 + ((x1 - x0) - fit.width) // 2, y0 + ((y1 - y0) - fit.height) // 2))
    elif key == "team_wordmark":
        d.rectangle(box, fill=team["bg"] + (255,))
        path = LOGOS / ("New_York_Giants_wordmark.png" if team["word"] == "GIANTS" else "New_York_Jets_2024_wordmark.png")
        if not _paste_mark(im, path, box, 0.2, tint=(255, 255, 255)):
            _text(d, inner, team["word"], FONT_BLACK, (255, 255, 255, 255), y1 - y0)
    elif key == "team_logo":
        d.rectangle(box, fill=team["bg"] + (255,))
        half = (x0, y0, x0 + (x1 - x0) // 3, y1)
        _paste_mark(im, GIANTS_NY if team["word"] == "GIANTS" else JETS_LOGO, half, 0.12)
        _text(d, (x0 + (x1 - x0) // 3 + 2 * k, y0 + 2 * k, x1 - 4 * k, y1 - 2 * k), team["city"], FONT, (255, 255, 255, 255), y1 - y0)
    elif key == "slogan":
        d.rectangle(box, fill=team["bg"] + (255,))
        _ctext(d, inner, team["slogan"], FONT_BLACK_ITALIC if team["word"] == "GIANTS" else FONT_BLACK,
               (255, 255, 255, 255), y1 - y0)
    elif key == "metlife_stadium":
        d.rectangle(box, fill=(12, 14, 19, 255))
        _ctext(d, inner, "METLIFE STADIUM", FONT, (245, 245, 245, 255), y1 - y0)
    elif key == "verizon":
        d.rectangle(box, fill=(0, 0, 0, 255))
        _text(d, (x0 + 18 * k, y0 + 2 * k, x1 - 26 * k, y1 - 2 * k), "verizon", FONT, (255, 255, 255, 255), y1 - y0)
        cx = x1 - 20 * k
        d.line([(cx, y0 + 8 * k), (cx + 4 * k, y0 + 12 * k), (cx + 12 * k, y0 + 3 * k)], fill=(205, 4, 11, 255), width=2 * k)
    elif key == "bud_light":
        d.rectangle(box, fill=(0, 52, 140, 255))
        _text(d, inner, "BUD LIGHT", FONT_BLACK, (255, 255, 255, 255), y1 - y0)
    elif key == "pepsi":
        d.rectangle(box, fill=(0, 40, 120, 255))
        cx, cy, r = x0 + 18 * k, (y0 + y1) // 2, 5 * k
        d.pieslice([cx - r, cy - r, cx + r, cy + r], 180, 360, fill=(220, 30, 50, 255))
        d.pieslice([cx - r, cy - r, cx + r, cy + r], 0, 180, fill=(20, 80, 190, 255))
        d.rectangle([cx - r, cy - k, cx + r, cy + k], fill=(255, 255, 255, 255))
        _text(d, (x0 + 30 * k, y0 + 2 * k, x1 - 8 * k, y1 - 2 * k), "pepsi", FONT_BLACK, (255, 255, 255, 255), y1 - y0)
    elif key == "hcltech":
        d.rectangle(box, fill=(8, 10, 18, 255))
        _text(d, inner, "HCLTech", FONT_BLACK, (255, 255, 255, 255), y1 - y0)
    elif key == "team_city":
        d.rectangle(box, fill=team["bg"] + (255,))
        _ctext(d, inner, team["city"], FONT_BLACK, team["fg"] + (255,), y1 - y0)
    elif key == "team_extra":
        d.rectangle(box, fill=team["bg"] + (255,))
        _ctext(d, inner, team["extra"], FONT_BLACK, (255, 255, 255, 255), y1 - y0)


# --- the field wall (b76-u5b) -----------------------------------------------------------------------------
#: One 512x256 atlas per venue (data/nfl2k5_metlife_model/wall.json gives the cells and the layout): four rows of
#: 64 px, each the wall's full 1.8 m, every cell at its own aspect. Drawn at 4x (the Edition master) and reduced.
WALL_JSON = ROOT / "data" / "nfl2k5_metlife_model" / "wall.json"
GIANTS_WORD_WHITE = Path("/media/noah/Storage/.b76-research/u1/metlife_handoff/giants/marks/giants_wordmark_white.png")
FONT_BLACK_ITALIC = "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-BlackItalic.ttf"
WALL_BLUE = (18, 56, 176)            # the padded wall's royal blue (the 2025 game photos; brighter than #0B2265)
WALL_RAY = (40, 86, 204)             # the lighter rays of the GO BIG BLUE sunburst
GIANTS_RED = (167, 25, 48)           # #A71930
WALL_WHITE = (238, 240, 238)         # the Jets' white wraps
WALL_GREEN = (18, 84, 62)            # the Jets' green stripes and type (#115740 family, as the wraps read)
STRIPES = ((0.18, 0.42), (0.66, 0.90))   # the Jets wraps' two stripes, fractions of the wall height from the top
#                                          (measured on the frontal 2026 wrap photo mkm1psg68xrqkcqjxxba)


def _ctext(draw, box, text, font_path, fill, max_h):
    """Text fitted to the box and centred in it."""
    from PIL import ImageFont
    x0, y0, x1, y1 = box
    size = int(max_h)
    while size > 8:
        font = ImageFont.truetype(font_path, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        if r - l <= x1 - x0 and b - t <= y1 - y0:
            break
        size -= 2
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    draw.text(((x0 + x1) / 2 - (l + r) / 2, (y0 + y1) / 2 - (t + b) / 2), text, font=font, fill=fill)
    return ((x0 + x1) / 2 - (r - l) / 2, (y0 + y1) / 2 - (b - t) / 2, (x0 + x1) / 2 + (r - l) / 2, (y0 + y1) / 2 + (b - t) / 2)


def _stripes(d, box, gaps=()):
    """The Jets wraps' two green stripes across the box, broken where the gaps (x0, x1) are."""
    x0, y0, x1, y1 = box
    h = y1 - y0
    spans, x = [], x0
    for g0, g1 in sorted(gaps):
        if g0 > x:
            spans.append((x, g0))
        x = max(x, g1)
    if x < x1:
        spans.append((x, x1))
    for a, b in spans:
        for f0, f1 in STRIPES:
            d.rectangle([a, y0 + f0 * h, b - 1, y0 + f1 * h], fill=WALL_GREEN + (255,))


def _mark_at(im, path, box, height_frac, tint=None):
    """The mark scaled to height_frac of the box height (or the box width), centred; returns its x extent."""
    if not Path(path).is_file():
        return None
    mark = Image.open(path).convert("RGBA")
    if tint is not None:
        a = np.asarray(mark).copy()
        a[..., :3] = tint
        mark = Image.fromarray(a, "RGBA")
    x0, y0, x1, y1 = box
    bb = mark.getbbox()
    mark = mark.crop(bb)
    h = int((y1 - y0) * height_frac)
    w = int(mark.width * h / mark.height)
    if w > (x1 - x0) * 0.94:
        w = int((x1 - x0) * 0.94); h = int(mark.height * w / mark.width)
    mark = mark.resize((w, h), Image.LANCZOS)
    at = (x0 + ((x1 - x0) - w) // 2, y0 + ((y1 - y0) - h) // 2)
    im.alpha_composite(mark, at)
    return at[0], at[0] + w


def _circle_text(im, centre, radius, text, font_path, size, fill, start_deg, end_deg):
    """Text set along an arc (degrees clockwise from 12 o'clock), upright to a reader outside the arc's centre."""
    from PIL import ImageDraw, ImageFont
    font = ImageFont.truetype(font_path, size)
    n = len(text)
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        a = start_deg + (end_deg - start_deg) * (i + 0.5) / n
        glyph = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glyph)
        l, t, r, b = gd.textbbox((0, 0), ch, font=font)
        gd.text((size - (l + r) / 2, size - (t + b) / 2), ch, font=font, fill=fill)
        rot = -a if -90 <= ((a + 180) % 360 - 180) <= 90 else 180 - a
        glyph = glyph.rotate(rot, resample=Image.BICUBIC)
        rad = np.radians(a)
        cx, cy = centre[0] + radius * np.sin(rad), centre[1] - radius * np.cos(rad)
        im.alpha_composite(glyph, (int(cx - size), int(cy - size)))


def _wall_cell(im, d, box, name, venue, k):
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    if venue == "s18":
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=WALL_BLUE + (255,))
        if name == "nyfg":                      # NEW YORK FOOTBALL GIANTS in heavy condensed type, half the wall's height
            _squeezed_text(im, (x0 + W * 0.03, y0 + H * 0.22, x1 - W * 0.03, y0 + H * 0.72), "NEW YORK FOOTBALL GIANTS",
                           FONT_BLACK, (255, 255, 255, 255))
        if name == "logo":                      # 'ny GIANTS' in white, as the sideline wall shows it
            _mark_at(im, GIANTS_NY, (x0, y0, x0 + int(W * 0.36), y1), 0.74)
            _mark_at(im, GIANTS_WORD_WHITE, (x0 + int(W * 0.34), y0, x1 - int(W * 0.04), y1), 0.70)
        elif name == "slogan":                  # GO BIG BLUE over the sunburst
            cx, cy = x0 + W / 2, y0 + H * 1.9
            for r in range(48):
                a0, a1 = np.radians(r * 7.5 - 90), np.radians(r * 7.5 - 90 + 3.75)
                R = W * 1.2
                d.polygon([(cx, cy), (cx + R * np.cos(a0), cy + R * np.sin(a0)), (cx + R * np.cos(a1), cy + R * np.sin(a1))],
                          fill=WALL_RAY + (255,))
            d.rectangle([x0 - W, y0 - H, x0 - 1, y1 + H], fill=(0, 0, 0, 0))
            _ctext(d, (x0 + W * 0.08, y0 + H * 0.16, x1 - W * 0.08, y1 - H * 0.14), "GO BIG BLUE", FONT_BLACK_ITALIC,
                   (255, 255, 255, 255), H * 0.72)
        elif name == "roundel":                 # the SINCE 1925 roundel (DESIGN: ring text, ny in the centre)
            cx, cy, R = x0 + W / 2, y0 + H / 2, H * 0.47
            d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(255, 255, 255, 255))
            r1 = R * 0.95
            d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], fill=(11, 34, 101, 255))
            r2 = R * 0.66
            d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(255, 255, 255, 255))
            r3 = R * 0.62
            d.ellipse([cx - r3, cy - r3, cx + r3, cy + r3], fill=WALL_BLUE + (255,))
            size = max(6, int(R * 0.24))
            _circle_text(im, (cx, cy), R * 0.8, "SINCE", FONT_BLACK, size, (255, 255, 255, 255), -52, 52)
            _circle_text(im, (cx, cy), R * 0.8, "1925", FONT_BLACK, size, (255, 255, 255, 255), 222, 138)
            _mark_at(im, GIANTS_NY, (int(cx - r3), int(cy - r3), int(cx + r3), int(cy + r3)), 0.62)
        # the red base pad along the foot of the wall (7% of its height), in 1.8 m pads (the 2025 photos)
        top = y1 - H * 0.075
        d.rectangle([x0, top, x1 - 1, y1 - 1], fill=GIANTS_RED + (255,))
        pad = H                                    # one wall height, 1.8 m
        k = 0
        while x0 + k * pad < x1:
            gx = x0 + k * pad
            d.rectangle([gx, top, gx + max(1, H * 0.02), y1 - 1], fill=(40, 8, 18, 255))
            k += 1
    else:
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=WALL_WHITE + (255,))
        gaps = []
        if name == "logo":                      # the JETS wordmark, the stripes broken around it
            ext = _mark_at(im, LOGOS / "New_York_Jets_2024_wordmark.png", (x0, y0, x1, y1), 0.80, tint=WALL_GREEN)
            if ext:
                gaps.append((ext[0] - W * 0.02, ext[1] + W * 0.02))
        elif name == "slogan":                  # NEW YORK JETS in the wraps' heavy condensed type
            gaps.append((x0 + W * 0.17, x1 - W * 0.17))
        elif name == "oval":                    # the plane roundel of the wraps (the 2026 photos), drawn by the skin tool
            from nfl2k5_modern_metlife_art import jets_plane_roundel
            rh = int(H * 0.86); rw = int(rh * 1.672)
            r = jets_plane_roundel(LOGOS, rw, rh, "wrap")
            im.alpha_composite(r, (x0 + (W - rw) // 2, y0 + (H - rh) // 2))
            gaps.append((x0 + (W - rw) / 2 - W * 0.04, x0 + (W + rw) / 2 + W * 0.04))
        elif name == "chant":                   # J-E-T-S on the wraps (the 2026 photos)
            gaps.append((x0 + W * 0.3, x1 - W * 0.3))
        _stripes(d, (x0, y0, x1, y1), gaps)
        if name == "slogan":
            _squeezed_text(im, (x0 + W * 0.2, y0 + H * 0.12, x1 - W * 0.2, y1 - H * 0.12), "NEW YORK JETS",
                           FONT_BLACK, WALL_GREEN + (255,))
        if name == "chant":
            _squeezed_text(im, (x0 + W * 0.33, y0 + H * 0.12, x1 - W * 0.33, y1 - H * 0.12), "J-E-T-S",
                           FONT_BLACK, WALL_GREEN + (255,))


def _squeezed_text(im, box, text, font_path, fill):
    """Heavy type condensed to fit: the text drawn at the box's height, then narrowed (never widened) to its width."""
    from PIL import ImageDraw, ImageFont
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    h = y1 - y0
    font = ImageFont.truetype(font_path, int(h * 1.3))
    probe = ImageDraw.Draw(im)
    l, t, r, b = probe.textbbox((0, 0), text, font=font)
    tmp = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text((2 - l, 2 - t), text, font=font, fill=fill)
    tmp = tmp.crop(tmp.getbbox())
    tmp = tmp.resize((tmp.width, h), Image.LANCZOS) if tmp.height != h else tmp
    w = min(tmp.width, x1 - x0)
    tmp = tmp.resize((w, h), Image.LANCZOS)
    im.alpha_composite(tmp, (x0 + ((x1 - x0) - w) // 2, y0))


def number_box(d, box, number):
    """A retired number as the Giants' sideline wall shows it: black numerals in a white box with a black border."""
    bx0, by0, bx1, by1 = box
    bh = by1 - by0
    d.rectangle([bx0, by0, bx1 - 1, by1 - 1], fill=(0, 0, 0, 255))
    e = max(1, bh * 0.08)
    d.rectangle([bx0 + e, by0 + e, bx1 - 1 - e, by1 - 1 - e], fill=(250, 250, 250, 255))
    _ctext(d, (bx0 + 2 * e, by0 + 1.5 * e, bx1 - 2 * e, by1 - 1.5 * e), str(number), FONT_BLACK, (8, 8, 10, 255), bh * 0.8)


def wall_atlas(venue, master=False):
    """512x256 RGBA (2048x1024 master): the venue's field-wall cells (wall.json)."""
    from PIL import ImageDraw
    spec = json.loads(WALL_JSON.read_text(encoding="utf-8"))
    cells = spec["venues"][venue]["cells"]
    k = 4
    im = Image.new("RGBA", (512 * k, 256 * k), (0, 0, 0, 255))
    for name, (x0, y0, x1, y1) in cells.items():
        cell = Image.new("RGBA", ((x1 - x0) * k, (y1 - y0) * k), (0, 0, 0, 255))
        _wall_cell(cell, ImageDraw.Draw(cell), (0, 0, cell.width, cell.height), name, venue, k)
        im.paste(cell, (x0 * k, y0 * k))
    if not master:
        im = im.resize((512, 256), Image.LANCZOS)
    return np.asarray(im).astype(float)


#: the 4x masters for the 2K5 Edition pack (tools/nfl2k5_metlife_model_pack.py): the textures drawn from type and
#: marks; the louvres, stone, glass and portals are pixel patterns with nothing to add at 4x
MASTERS = {"ml_letters": lambda: letters(None, master=True), "ml_logo": lambda: logo(None, master=True),
           "ml_board_panel_s18": lambda: board_panel("s18", master=True),
           "ml_board_panel_s19": lambda: board_panel("s19", master=True),
           "ml_signs_s18": lambda: signage_atlas("s18", master=True),
           "ml_signs_s19": lambda: signage_atlas("s19", master=True),
           "ml_wall_s18": lambda: wall_atlas("s18", master=True),
           "ml_wall_s19": lambda: wall_atlas("s19", master=True)}


def write_masters(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in MASTERS.items():
        img = np.clip(fn(), 0, 255).astype(np.uint8)
        Image.fromarray(img, "RGBA").save(out / f"{name}_4x.png")
        print("wrote", out / f"{name}_4x.png")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--masters"]:
        write_masters(argv[1])
        return 0
    out = Path(argv[0]) if argv else ROOT / "data" / "nfl2k5_metlife_model" / "art"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    for name, fn in (("ml_louvre", louvres), ("ml_limestone", limestone), ("ml_ring_panel", ring_panel),
                     ("ml_letters", letters), ("ml_logo", logo), ("ml_portal", portal),
                     ("crowd_hats18", crowd_hats18), ("crowd_hats19", crowd_hats19),
                     ("ml_board_panel_s18", lambda r: board_panel("s18")), ("ml_board_panel_s19", lambda r: board_panel("s19")),
                     ("ml_signs_s18", lambda r: signage_atlas("s18")), ("ml_signs_s19", lambda r: signage_atlas("s19")),
                     ("ml_wall_s18", lambda r: wall_atlas("s18")), ("ml_wall_s19", lambda r: wall_atlas("s19"))):
        if name.startswith("crowd_hats") and not (GIANTS_NY.is_file() and JETS_LOGO.is_file()):
            print("skipped", name, "(the team marks are not on this machine; the committed PNG stays)")
            continue
        img = np.clip(fn(rng), 0, 255).astype(np.uint8)
        Image.fromarray(img, "RGBA" if img.shape[-1] == 4 else "RGB").save(out / f"{name}.png")
        print("wrote", out / f"{name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
