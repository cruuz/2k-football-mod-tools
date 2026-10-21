#!/usr/bin/env python3
"""fr1: author the 2026 fan look for the close-up crowd people of the fan-reaction cutaways.

The close-up crowd scenes (crowda .. crowdn, crowdv3, propscrowdsign in the cutscene archives) carry no clothing
texture of their own: the game binds their ``tshirt``, ``jersey``, ``sweatshirt``, ``varsity``, ``puffyjacket``,
``hardhat``, ``crowdsign``, ``foamfinger``, ``boxlogo``, ``noshirtns0N`` and ``fanplate`` materials to the textures
of that name in the club's crowd texture sets (four sets per club, see nfl2k5_modern_fans). This tool authors one
image per club and texture name, at 4x (masters) and area-downscaled to the native slot.

Inputs (read only): a folder of the club's retail textures exported from the user's own disc (``<TEAM>/<set>_<name>
.png``; the retail art is the layout and fabric-fold template, nothing retail is written to the repository), the
2026 team logos (data/nfl2k5_scorebug_assets/logos, 128 px) and the fan palette below (from the 2026 official
colours in data/nfl2k5_scorebug_sprite/team_colors_official_2026.json).

What each image becomes (every 2004 mark is gone; the fabric folds keep the retail shading):
  tshirt       the club's fan colour with the 2026 logo on the chest and on the cap panel (u 0.75-1, v 0-0.37,
               the ``cap`` material); the sneaker and the two swatches beside the cap ship flat grey and the Build
               takes them from the disc (KEEP_RECTS; likewise the hard hat's corner swatches and the plate's bar)
  sweatshirt   a heather-grey hoodie front: 2026 logo, the 2026 nickname, drawstrings and a pouch pocket
  jersey       a replica of the club's 2026 home jersey colours: body, collar trim and two sleeve stripes; the
               2004 maker mark at the collar is gone
  varsity      body in the club colour, cream leather sleeves, trims in the second colour, a plain white tee
               under the open jacket (the 2004 graphic on it is gone)
  puffyjacket  the club colour, the hood lining in the second colour, a small 2026 chest logo; the 2004 maker
               mark is gone
  hardhat      the club colour with the 2026 logo
  boxlogo      the 2026 logo on a clear ground
  crowdsign    a white poster board: '#', the 2026 logo and a harmless club chant in marker capitals
  foamfinger   the foam finger in the club colour and the second colour
  fanplate     a vanity licence plate (state, short text, 'NICKNAME FAN'), the 2026 nickname, a cloth patch in the
               club colour and the 2026 logo
  noshirtns0N  (only where the 2004 letters no longer fit: WAS, LAR, SEA, LAC) the painted-chest letters
  head01/03    (only WAS 01+03, DET 03, MIA 03, NYJ 03, SEA 01) a face-paint layer (alpha = paint) the Build lays
               over the disc's own head: 2026 colours split down the face, small logo

  python3 tools/b77/fr1_fan_art.py --retail DIR --out ART [--masters DIR] [--teams GB,WAS]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
LOGOS = ROOT / "data" / "nfl2k5_scorebug_assets" / "logos"
LOGO_FILE = {"WAS": "wsh"}
M = 4  # master scale
IMPACT = "/home/noah/.local/share/fonts/Unknown Vendor/TrueType/Impact/Impact_Regular.ttf"
ROUND = "/usr/share/fonts/truetype/msttcorefonts/Comic_Sans_MS_Bold.ttf"
FONTS = {"block": [IMPACT, "/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
         "round": [ROUND, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]}

# team: (fan colour, second colour, jersey body, jersey trim, stripe 1, stripe 2, nickname, chant, state, vanity)
# Fan colour: what most 2025-26 fans of the club wear (the club primary except where the crowd wears the second:
# LV, NO, CAR in black). Jersey: the club's 2026 home jersey colour (DAL white).
FANS = {
    "ARI": ("#97233F", "#000000", "#97233F", "#FFFFFF", "#000000", "#FFFFFF", "CARDINALS", "RED SEA RISING!", "ARIZONA", "BIRDS"),
    "ATL": ("#A71930", "#000000", "#000000", "#A71930", "#A71930", "#FFFFFF", "FALCONS", "RISE UP!", "GEORGIA", "RISEUP"),
    "BAL": ("#24135F", "#9A7611", "#24135F", "#000000", "#000000", "#9A7611", "RAVENS", "FLOCK UP!", "MARYLAND", "RAVENS"),
    "BUF": ("#00338D", "#C60C30", "#00338D", "#FFFFFF", "#C60C30", "#FFFFFF", "BILLS", "LET'S GO BUFFALO!", "NEW YORK", "BILLS"),
    "CAR": ("#000000", "#0085CF", "#000000", "#0085CF", "#0085CF", "#B2B4BB", "PANTHERS", "KEEP POUNDING", "NORTH CAROLINA", "KEEPPND"),
    "CHI": ("#0B162A", "#E64100", "#0B162A", "#FFFFFF", "#E64100", "#FFFFFF", "BEARS", "BEAR DOWN!", "ILLINOIS", "BEARDWN"),
    "CIN": ("#FB4F14", "#000000", "#000000", "#FB4F14", "#FB4F14", "#FFFFFF", "BENGALS", "WHO DEY!", "OHIO", "WHODEY"),
    "DAL": ("#002244", "#869397", "#FFFFFF", "#003594", "#003594", "#869397", "COWBOYS", "HOW 'BOUT THEM COWBOYS!", "TEXAS", "BOYS"),
    "DEN": ("#FC4C02", "#0A2343", "#FC4C02", "#0A2343", "#0A2343", "#FFFFFF", "BRONCOS", "BRONCOS COUNTRY!", "COLORADO", "BRONCS"),
    "DET": ("#0076B6", "#B0B7BC", "#0076B6", "#FFFFFF", "#B0B7BC", "#FFFFFF", "LIONS", "ONE PRIDE!", "MICHIGAN", "1PRIDE"),
    "GB": ("#203731", "#FFB612", "#203731", "#FFB612", "#FFB612", "#FFFFFF", "PACKERS", "GO PACK GO!", "WISCONSIN", "PAKRS"),
    "IND": ("#013369", "#FFFFFF", "#013369", "#FFFFFF", "#FFFFFF", "#A5ACAF", "COLTS", "FOR THE SHOE!", "INDIANA", "COLTS"),
    "JAX": ("#006778", "#D7A22A", "#006778", "#000000", "#D7A22A", "#000000", "JAGUARS", "DUUUVAL!", "FLORIDA", "DUUUVAL"),
    "KC": ("#E31837", "#FFB612", "#E31837", "#FFFFFF", "#FFB612", "#FFFFFF", "CHIEFS", "CHIEFS KINGDOM!", "MISSOURI", "KINGDOM"),
    "MIA": ("#008E97", "#FC4C02", "#008E97", "#FFFFFF", "#FC4C02", "#FFFFFF", "DOLPHINS", "FINS UP!", "FLORIDA", "FINSUP"),
    "MIN": ("#4F2683", "#FFC62F", "#4F2683", "#FFFFFF", "#FFC62F", "#FFFFFF", "VIKINGS", "SKOL!", "MINNESOTA", "SKOL"),
    "NE": ("#002244", "#C60C30", "#002244", "#C60C30", "#C60C30", "#B0B7BC", "PATRIOTS", "LET'S GO PATS!", "MASSACHUSETTS", "PATS"),
    "NO": ("#000000", "#D3BC8D", "#000000", "#D3BC8D", "#D3BC8D", "#FFFFFF", "SAINTS", "WHO DAT!", "LOUISIANA", "WHODAT"),
    "NYG": ("#0B2265", "#A71930", "#0B2265", "#A71930", "#A71930", "#FFFFFF", "GIANTS", "GO BIG BLUE!", "NEW JERSEY", "BIGBLUE"),
    "NYJ": ("#115740", "#FFFFFF", "#115740", "#FFFFFF", "#FFFFFF", "#000000", "JETS", "J-E-T-S JETS JETS JETS!", "NEW JERSEY", "JETS"),
    "LV": ("#000000", "#C8C7C7", "#000000", "#C8C7C7", "#C8C7C7", "#FFFFFF", "RAIDERS", "RAIDER NATION!", "NEVADA", "RAIDERS"),
    "PHI": ("#004851", "#A2AAAD", "#004851", "#FFFFFF", "#000000", "#A2AAAD", "EAGLES", "FLY EAGLES FLY!", "PENNSYLVANIA", "EAGLES"),
    "PIT": ("#000000", "#FFB612", "#000000", "#FFB612", "#FFB612", "#FFFFFF", "STEELERS", "HERE WE GO!", "PENNSYLVANIA", "STLRS"),
    "LAR": ("#003594", "#FFD100", "#003594", "#FFD100", "#FFD100", "#FFFFFF", "RAMS", "WHOSE HOUSE? RAMS HOUSE!", "CALIFORNIA", "RAMS"),
    "LAC": ("#0080C6", "#FFC20E", "#0080C6", "#FFFFFF", "#FFC20E", "#FFFFFF", "CHARGERS", "BOLT UP!", "CALIFORNIA", "BOLTUP"),
    "SF": ("#AA0000", "#B3995D", "#AA0000", "#FFFFFF", "#B3995D", "#FFFFFF", "49ERS", "GO NINERS!", "CALIFORNIA", "NINERS"),
    "SEA": ("#002244", "#69BE28", "#002244", "#69BE28", "#69BE28", "#A5ACAF", "SEAHAWKS", "GO HAWKS! 12", "WASHINGTON", "GOHAWKS"),
    "TB": ("#A71930", "#322F2B", "#A71930", "#FFFFFF", "#322F2B", "#DC4405", "BUCCANEERS", "FIRE THE CANNONS!", "FLORIDA", "BUCS"),
    "TEN": ("#0C2340", "#4495D2", "#0C2340", "#4495D2", "#4495D2", "#D50A0A", "TITANS", "TITAN UP!", "TENNESSEE", "TITANUP"),
    "WAS": ("#5A1414", "#FFB612", "#5A1414", "#FFB612", "#FFB612", "#FFFFFF", "COMMANDERS", "HAIL TO THE COMMANDERS!", "WASHINGTON DC", "HTTC"),
    "CLE": ("#311D00", "#FF3C00", "#311D00", "#FF3C00", "#FF3C00", "#FFFFFF", "BROWNS", "DAWG POUND!", "OHIO", "DAWGS"),
    "HOU": ("#021018", "#EB0028", "#021018", "#EB0028", "#EB0028", "#FFFFFF", "TEXANS", "LET'S GO TEXANS!", "TEXAS", "HTOWN"),
}
# painted-chest letters where the 2004 letters no longer fit (name or colours changed); slots past the word keep the
# game's own unused-slot convention (the retail green cross is left in place)
LETTERS = {"WAS": "HAIL!!!!", "LAR": "RAMS", "SEA": "SEAHAWKS", "LAC": "CHARGERS"}
VARSITY_SLEEVE = "#E9E1CC"
GREY = "#B4B4B4"


def rgb(hexcode: str) -> np.ndarray:
    hexcode = hexcode.lstrip("#")
    return np.array([int(hexcode[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float64)


def lum(a: np.ndarray) -> np.ndarray:
    return a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONTS[kind]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def load_retail(folder: Path, team: str, name: str) -> np.ndarray:
    for prefix in ("A", "B", "ns", "tg"):
        path = folder / team / f"{prefix}_{name}.png"
        if path.is_file():
            return np.asarray(Image.open(path).convert("RGBA"), dtype=np.float64)
    raise FileNotFoundError(f"{team}: no retail {name} in {folder}")


def logo(team: str) -> Image.Image:
    return Image.open(LOGOS / f"{LOGO_FILE.get(team, team.lower())}.png").convert("RGBA")


def up(a: np.ndarray) -> np.ndarray:
    """Native array -> master size (bicubic)."""
    h, w = a.shape[:2]
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA" if a.shape[2] == 4 else "RGB")
    return np.asarray(img.resize((w * M, h * M), Image.BICUBIC), dtype=np.float64)


def inpaint(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    import cv2
    v8 = np.clip(values, 0, 255).astype(np.uint8)
    out = cv2.inpaint(v8, mask.astype(np.uint8) * 255, 5, cv2.INPAINT_TELEA)
    return out.astype(np.float64)


def graphic_mask(rgba: np.ndarray, windows, base=None, chroma=34.0, contrast=38.0) -> np.ndarray:
    """Pixels inside ``windows`` (x0, y0, x1, y1, native) that are printed graphics, not fabric: off the fabric's
    chroma or off its local brightness."""
    import cv2
    rgb_ = rgba[..., :3]
    L = lum(rgb_)
    mask = np.zeros(L.shape, bool)
    Lm = cv2.medianBlur(np.clip(L, 0, 255).astype(np.uint8), 15).astype(np.float64)
    for x0, y0, x1, y1 in windows:
        win = (slice(y0, y1), slice(x0, x1))
        if base is None:
            ring = np.concatenate([rgb_[y0:y1, max(x0 - 3, 0):x0].reshape(-1, 3), rgb_[y0:y1, x1:x1 + 3].reshape(-1, 3),
                                   rgb_[max(y0 - 3, 0):y0, x0:x1].reshape(-1, 3), rgb_[y1:y1 + 3, x0:x1].reshape(-1, 3)])
            b = np.median(ring if len(ring) else rgb_[win].reshape(-1, 3), axis=0)
        else:
            b = base
        bl = max(float(lum(b[None])[0]), 1.0)
        scaled = b[None, None, :] * (L[win][..., None] / bl)
        dev = np.sqrt(((rgb_[win] - scaled) ** 2).sum(-1))
        m = (dev > chroma) | (np.abs(L[win] - Lm[win]) > contrast)
        mask[win] |= m
    k = np.ones((3, 3), np.uint8)
    return cv2.dilate(mask.astype(np.uint8), k, iterations=1).astype(bool)


def shading(rgba: np.ndarray, mask: np.ndarray, region: np.ndarray) -> np.ndarray:
    """Fabric folds: luminance (graphics inpainted) over its mean in ``region``."""
    L = lum(rgba[..., :3])
    if mask.any():
        L = inpaint(L, mask)
    mean = max(float(L[region].mean()), 1.0)
    return np.clip(L / mean, 0.25, 1.9)


def colourise(colour: np.ndarray, s: np.ndarray) -> np.ndarray:
    """A flat colour under fold shading ``s``; dark colours still show highlights."""
    lift = (1.0 - float(lum(colour[None])[0]) / 255.0) * 70.0
    out = colour[None, None, :] * s[..., None] + (s[..., None] - 1.0) * lift
    return np.clip(out, 0, 255)


def paste_logo(canvas: Image.Image, team: str, cx: float, cy: float, w: float, h: float, *, shade=None,
               image: Image.Image | None = None, ground=None) -> None:
    """Fit the 2026 logo (or ``image``) in a w x h native box centred on (cx, cy), at master scale."""
    src = image if image is not None else logo(team)
    box = src.getbbox() or (0, 0, src.width, src.height)
    src = src.crop(box)
    scale = min(w * M / src.width, h * M / src.height)
    size = (max(1, round(src.width * scale)), max(1, round(src.height * scale)))
    src = src.resize(size, Image.LANCZOS)
    if ground is not None:
        a = np.asarray(src, dtype=np.float64)
        opaque = a[..., 3] > 128
        if opaque.any():
            dark_share = (np.abs(a[..., :3][opaque] - np.asarray(ground, dtype=np.float64)).sum(-1) < 110).mean()
            if dark_share > 0.35:  # most of the mark is the ground colour: give it a white keyline
                from PIL import ImageFilter as _F
                alpha = src.getchannel("A")
                ring = alpha.filter(_F.MaxFilter(2 * M + 1)).filter(_F.MaxFilter(2 * M + 1))
                pad = Image.new("RGBA", src.size, (255, 255, 255, 0))
                pad.putalpha(ring)
                pad.alpha_composite(src)
                src = pad
    if shade is not None:  # fold shading (native) over the logo, softened
        x0, y0 = round(cx * M - size[0] / 2), round(cy * M - size[1] / 2)
        s = np.asarray(Image.fromarray(np.clip(shade * 128, 0, 255).astype(np.uint8), "L").resize(
            (shade.shape[1] * M, shade.shape[0] * M), Image.BICUBIC), dtype=np.float64) / 128.0
        crop = s[max(y0, 0):y0 + size[1], max(x0, 0):x0 + size[0]]
        a = np.asarray(src, dtype=np.float64)
        if crop.shape[:2] == a.shape[:2]:
            f = 0.55 + 0.45 * np.clip(crop, 0.5, 1.4)
            a[..., :3] = np.clip(a[..., :3] * f[..., None], 0, 255)
            src = Image.fromarray(a.astype(np.uint8), "RGBA")
    canvas.alpha_composite(src, (round(cx * M - size[0] / 2), round(cy * M - size[1] / 2)))


def draw_text(canvas: Image.Image, text: str, box, fill, *, outline=None, kind="block", stroke=2, max_size=200,
              lines=None) -> None:
    """Centred text fitted to ``box`` (native x0, y0, x1, y1), drawn at master scale; wraps to ``lines`` lines."""
    x0, y0, x1, y1 = (v * M for v in box)
    draw = ImageDraw.Draw(canvas)
    words = text.split()
    candidates = [[text]]
    if lines and lines > 1 and len(words) > 1:
        for n in range(2, min(lines, len(words)) + 1):
            # balanced split into n lines
            best = None
            import itertools
            for cuts in itertools.combinations(range(1, len(words)), n - 1):
                parts = [" ".join(words[a:b]) for a, b in zip((0,) + cuts, cuts + (len(words),))]
                score = max(len(p) for p in parts)
                if best is None or score < best[0]:
                    best = (score, parts)
            candidates.append(best[1])
    best = None
    for parts in candidates:
        size = max_size * M
        while size > 6:
            f = font(kind, size)
            widths = [draw.textbbox((0, 0), p, font=f, stroke_width=stroke * M)[2:] for p in parts]
            total_h = sum(h for _w, h in widths) + (len(parts) - 1) * size * 0.12
            if max(w for w, _h in widths) <= (x1 - x0) and total_h <= (y1 - y0):
                break
            size -= max(1, size // 20)
        if best is None or size > best[0]:
            best = (size, parts)
    size, parts = best
    f = font(kind, size)
    boxes = [draw.textbbox((0, 0), p, font=f, stroke_width=stroke * M) for p in parts]
    heights = [b[3] - b[1] for b in boxes]
    total = sum(heights) + (len(parts) - 1) * size * 0.12
    y = y0 + ((y1 - y0) - total) / 2
    for p, b, h in zip(parts, boxes, heights):
        w = b[2] - b[0]
        draw.text((x0 + ((x1 - x0) - w) / 2 - b[0], y - b[1]), p, font=f, fill=fill,
                  stroke_width=(stroke * M if outline else 0), stroke_fill=outline)
        y += h + size * 0.12


def to_image(a: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype(np.uint8), "RGBA")


def finish(master: Image.Image, native_size, keep=()) -> tuple[Image.Image, Image.Image]:
    """Area-downscale the master; ``keep`` rects (native) ship flat grey: the Build restores them from the disc."""
    native = master.resize(native_size, Image.BOX)
    if keep:
        d = ImageDraw.Draw(native)
        for x0, y0, x1, y1 in keep:
            d.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(128, 128, 128, 255))
    return master, native


# the retail details the Build restores from the disc (mod_editor/core/nfl2k5_modern_fans.KEEP_RECTS)
KEEP_RECTS = {"tshirt": ((158, 0, 192, 74), (192, 48, 256, 74)), "hardhat": ((0, 0, 10, 10), (114, 0, 128, 8)),
              "fanplate": ((118, 44, 128, 86),)}


def rect_mask(shape, *rects) -> np.ndarray:
    m = np.zeros(shape[:2], bool)
    for x0, y0, x1, y1 in rects:
        m[y0:y1, x0:x1] = True
    return m


# --- the textures -------------------------------------------------------------------------------------------------

def tshirt(team, retail):
    shirt = rgb(FANS[team][0])
    a = retail.copy()
    keep = rect_mask(a.shape, (158, 0, 192, 74), (192, 48, 256, 74))
    windows = [(20, 16, 140, 108), (40, 108, 130, 128), (160, 76, 256, 100), (194, 0, 256, 48)]
    g = graphic_mask(a, windows) & ~keep
    body = ~keep
    s = shading(a, g, body & ~g)
    out = a.copy()
    out[..., :3] = np.where(body[..., None], colourise(shirt, s), a[..., :3])
    out[..., 3] = 255
    master = to_image(up(out))
    paste_logo(master, team, 80, 56, 66, 54, shade=s, ground=shirt)
    paste_logo(master, team, 225, 24, 42, 34, shade=s, ground=shirt)
    return finish(master, (256, 128), KEEP_RECTS["tshirt"])


def sweatshirt(team, retail):
    a = retail.copy()
    g = graphic_mask(a, [(22, 18, 140, 108)], base=None)
    s = shading(a, g, np.ones(a.shape[:2], bool) & ~g)
    out = a.copy()
    out[..., :3] = colourise(rgb(GREY), s)
    out[..., 3] = 255
    master = to_image(up(out))
    d = ImageDraw.Draw(master)
    string = (200, 200, 200, 255)
    for x in (73, 91):  # drawstrings from the neck
        d.line([(x * M, 14 * M), ((x + (-2 if x < 82 else 2)) * M, 42 * M)], fill=string, width=M)
        d.ellipse([((x + (-2 if x < 82 else 2)) * M - 3, 42 * M - 3), ((x + (-2 if x < 82 else 2)) * M + 3, 42 * M + 3)],
                  fill=(150, 150, 150, 255))
    pocket = [(46 * M, 92 * M), (118 * M, 92 * M), (126 * M, 116 * M), (38 * M, 116 * M)]
    d.line(pocket + [pocket[0]], fill=(120, 120, 120, 255), width=M)
    paste_logo(master, team, 82, 44, 44, 32, shade=s)
    # the 2004 wordmark sat in u 0.23-0.41; wider letters wrap round the side of the body
    draw_text(master, FANS[team][6], (56, 64, 108, 80), FANS[team][0], kind="block", stroke=0)
    return finish(master, (256, 128))


def jersey(team, retail):
    body_c, trim_c, s1, s2 = (rgb(FANS[team][i]) for i in (2, 3, 4, 5))
    a = retail.copy()
    base = np.median(a[60:120, 10:80, :3].reshape(-1, 3), axis=0)
    g_mark = graphic_mask(a, [(86, 22, 108, 40)])
    dev = graphic_mask(a, [(0, 0, 256, 128)], base=base, chroma=45.0, contrast=255.0)
    body = rect_mask(a.shape, (0, 0, 192, 128))
    sleeve = rect_mask(a.shape, (192, 0, 250, 128))
    cuff = rect_mask(a.shape, (250, 0, 256, 128))
    collar = dev & rect_mask(a.shape, (82, 0, 112, 34)) & ~g_mark
    # the body: every 2004 design pixel (yokes, side panels, maker mark) is fabric again
    s_body = shading(a, (dev | g_mark) & body, body & ~dev & ~g_mark)
    # the sleeve on its own folds; the 2004 stripe columns are where the new stripes go
    sleeve_dev = dev & sleeve
    cols = sleeve_dev.sum(0) > 20
    colour = np.array([np.median(a[:, x, :3][sleeve_dev[:, x]], axis=0) if cols[x] else np.zeros(3)
                       for x in range(a.shape[1])])
    runs, start = [], None
    for x in range(196, 251):
        split = start is not None and cols[x] and np.abs(colour[x] - colour[x - 1]).sum() > 60
        if start is not None and (not cols[x] or split or x == 250):
            runs.append((start, x if not cols[x] or split else x + 1))
            start = None
        if cols[x] and start is None:
            start = x
    runs = [(x0, x1) for x0, x1 in runs if x1 - x0 <= 8][:5]
    L = lum(a[..., :3])
    # sleeve patches (2004 logos on the sleeve): every large blob off the sleeve's own colour, boxed, becomes plain
    import cv2
    sbase = np.median(a[:, 196:230, :3][~sleeve_dev[:, 196:230]], axis=0)
    blobs = graphic_mask(a, [(192, 0, 250, 128)], base=sbase, chroma=45.0, contrast=45.0) & sleeve
    patch = np.zeros(a.shape[:2], bool)
    count, labels, stats, _c = cv2.connectedComponentsWithStats(blobs.astype(np.uint8), 8)
    for k in range(1, count):
        x, y, w, h, area = stats[k]
        if area >= 40 and w > 8:
            patch[max(y - 2, 0):y + h + 2, max(x - 2, 192):min(x + w + 2, 250)] = True
    flat = float(np.median(L[sleeve & ~sleeve_dev & ~patch])) if (sleeve & ~sleeve_dev & ~patch).any() else 128.0
    Ls = L.copy()
    Ls[patch] = flat
    rest = sleeve_dev & ~patch
    Ls = inpaint(Ls, rest) if rest.any() else Ls
    if patch.any():
        soft = cv2.GaussianBlur(Ls, (7, 7), 0)
        grown = cv2.dilate(patch.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        Ls = np.where(grown, soft, Ls)
    s_sleeve = np.clip(Ls / max(float(np.median(Ls[sleeve])), 1.0), 0.25, 1.9)
    out = a.copy()
    out[..., :3] = colourise(body_c, s_body)
    out[..., :3] = np.where((sleeve | cuff)[..., None], colourise(body_c, s_sleeve), out[..., :3])
    out[..., :3] = np.where(collar[..., None], colourise(trim_c, s_body), out[..., :3])
    for i, (x0, x1) in enumerate(runs):
        band = rect_mask(a.shape, (x0, 0, x1, 128))
        out[..., :3] = np.where(band[..., None], colourise(s1 if i % 2 == 0 else s2, s_sleeve), out[..., :3])
    out[..., :3] = np.where(cuff[..., None], colourise(trim_c, np.clip(s_sleeve, 0.5, 1.2) * 0.9), out[..., :3])
    out[..., 3] = 255
    return finish(to_image(up(out)), (256, 128))


def varsity(team, retail):
    body_c, second = rgb(FANS[team][0]), rgb(FANS[team][1])
    if team == "NYJ":
        second = rgb("#000000")
    a = retail.copy()
    tee = rect_mask(a.shape, (66, 20, 90, 98))
    tee_bands = rect_mask(a.shape, (66, 0, 90, 20), (66, 98, 90, 128))
    sleeves = rect_mask(a.shape, (158, 0, 256, 128))
    front = rect_mask(a.shape, (0, 0, 158, 128)) & ~tee & ~tee_bands
    base = np.median(a[30:90, 10:60, :3].reshape(-1, 3), axis=0)
    chest = rect_mask(a.shape, (90, 12, 132, 54))   # the 2004 chest logo (wearer's left)
    marks = graphic_mask(a, [(90, 12, 132, 54)], base=base, chroma=40.0, contrast=60.0) & chest
    trims = graphic_mask(a, [(0, 0, 66, 128), (90, 0, 158, 128)], base=base, chroma=48.0, contrast=255.0) & front
    trims &= ~marks
    s_body = shading(a, trims | marks, front & ~trims & ~marks)
    yy = np.linspace(-1.0, 1.0, a.shape[0])[:, None]
    xx = np.arange(a.shape[1], dtype=np.float64)[None, :]
    s_tee = np.clip(0.97 - 0.12 * ((xx - 78.0) / 12.0) ** 2 - 0.04 * yy ** 2, 0.7, 1.0)
    s_sleeve = shading(a, np.zeros(a.shape[:2], bool), sleeves)
    out = a.copy()
    out[..., :3] = np.where(front[..., None], colourise(body_c, s_body), out[..., :3])
    out[..., :3] = np.where(trims[..., None], colourise(second, np.clip(s_body, 0.6, 1.3)), out[..., :3])
    out[..., :3] = np.where(tee[..., None], colourise(rgb("#F2F2F2"), s_tee), out[..., :3])
    cuff = rect_mask(a.shape, (158, 0, 256, 11))
    out[..., :3] = np.where((sleeves & ~cuff)[..., None], colourise(rgb(VARSITY_SLEEVE), s_sleeve), out[..., :3])
    out[..., :3] = np.where(cuff[..., None], colourise(second, s_sleeve), out[..., :3])
    out[..., 3] = 255
    master = to_image(up(out))
    paste_logo(master, team, 111, 33, 22, 20, shade=s_body, ground=body_c)
    return finish(master, (256, 128))


def puffyjacket(team, retail):
    body_c, second = rgb(FANS[team][0]), rgb(FANS[team][1])
    a = retail.copy()
    base = np.median(a[90:120, 10:60, :3].reshape(-1, 3), axis=0)
    hood = graphic_mask(a, [(196, 0, 256, 128)], base=base, chroma=50.0, contrast=255.0)
    import cv2
    hood = cv2.morphologyEx(hood.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
    g = graphic_mask(a, [(38, 38, 72, 64), (80, 34, 120, 80)])
    s = shading(a, g | hood, ~(g | hood))
    s_hood = shading(a, np.zeros(a.shape[:2], bool), hood) if hood.any() else s
    out = a.copy()
    out[..., :3] = colourise(body_c, s)
    out[..., :3] = np.where(hood[..., None], colourise(second, s_hood), out[..., :3])
    out[..., 3] = 255
    master = to_image(up(out))
    paste_logo(master, team, 100, 55, 22, 20, shade=s, ground=body_c)
    return finish(master, (256, 128))


def hardhat(team, retail):
    a = retail.copy()
    keep = rect_mask(a.shape, (0, 0, 10, 10), (114, 0, 128, 8))
    g = graphic_mask(a, [(36, 10, 92, 62)]) & ~keep
    s = shading(a, g, ~keep & ~g)
    out = a.copy()
    out[..., :3] = np.where(keep[..., None], a[..., :3], colourise(rgb(FANS[team][0]), s))
    out[..., 3] = 255
    master = to_image(up(out))
    paste_logo(master, team, 64, 33, 40, 32, shade=s, ground=rgb(FANS[team][0]))
    return finish(master, (128, 64), KEEP_RECTS["hardhat"])


def boxlogo(team, retail):
    master = Image.new("RGBA", (64 * M, 64 * M), (0, 0, 0, 0))
    paste_logo(master, team, 32, 32, 60, 60)
    return finish(master, (64, 64))


def crowdsign(team, retail):
    a = retail.copy()
    s = shading(a, graphic_mask(a, [(0, 0, 128, 128)], chroma=40.0, contrast=40.0), np.ones(a.shape[:2], bool))
    board = colourise(rgb("#F4F1E8"), np.clip(0.94 + (s - 1) * 0.25, 0.85, 1.05))
    out = np.concatenate([board, np.full(a.shape[:2] + (1,), 255.0)], axis=2)
    master = to_image(up(out))
    ink = FANS[team][0] if lum(rgb(FANS[team][0])[None])[0] < 170 else "#202020"
    draw_text(master, "#", (1, 1, 16, 17), ink, kind="round", stroke=0)
    paste_logo(master, team, 106, 19, 36, 32)
    # the chant sits in the lower half, where the 2004 sign wrote; the '#' corner and the strip above stay clear for
    # the sign's own number and name quads
    draw_text(master, FANS[team][7], (6, 64, 122, 124), ink, kind="round", stroke=0, lines=3)
    return finish(master, (128, 128))


def foamfinger(team, retail):
    """Two-colour foam finger: the 2004 line drawing's brightness over the ground blends the club colour into the
    second colour (anti-aliased edges kept)."""
    a = retail.copy()
    c1, c2 = rgb(FANS[team][0]), rgb(FANS[team][1])
    if np.abs(c1 - c2).sum() < 120:
        c2 = rgb("#FFFFFF")
    L = lum(a[..., :3])
    lo, hi = np.percentile(L, 50), np.percentile(L, 92)
    t = np.clip((L - lo - 8.0) / max(hi - lo - 8.0, 1.0), 0.0, 1.0)[..., None]
    ground = colourise(c1, np.clip(L / max(lo, 1.0), 0.6, 1.4))
    out = a.copy()
    out[..., :3] = ground * (1 - t) + c2[None, None, :] * t
    out[..., 3] = 255
    return finish(to_image(up(out)), (128, 64))


def fanplate(team, retail):
    a = retail.copy()
    nick, state, vanity = FANS[team][6], FANS[team][8], FANS[team][9]
    c1, c2 = FANS[team][0], FANS[team][1]
    out = a.copy()
    out[..., 3] = np.where(out[..., 3] > 0, 255, 0)
    # cloth patch (x 0-62, y 86-124): the club colour on the retail folds
    cloth = rect_mask(a.shape, (0, 86, 62, 126)) & (a[..., 3] > 0)
    s = shading(a, np.zeros(a.shape[:2], bool), cloth)
    out[..., :3] = np.where(cloth[..., None], colourise(rgb(c1), s), out[..., :3])
    # clear the plate, the wordmark row and the logo corner; keep the grey bar (x 118-128, y 46-84)
    clear_rows = rect_mask(a.shape, (0, 44, 118, 86), (62, 86, 128, 128))
    out[clear_rows] = 0
    plate = rect_mask(a.shape, (0, 0, 128, 44))
    out[plate] = 0
    master = to_image(up(out))
    d = ImageDraw.Draw(master)
    d.rounded_rectangle([1 * M, 1 * M, 127 * M, 43 * M], radius=4 * M, fill=(246, 246, 240, 255),
                        outline=(40, 40, 40, 255), width=M)
    d.rectangle([3 * M, 3 * M, 125 * M, 11 * M], fill=c1)
    draw_text(master, state, (6, 3, 122, 11), "#FFFFFF", kind="block", stroke=0)
    paste_logo(master, team, 14, 25, 18, 16)
    draw_text(master, vanity, (26, 12, 124, 34), c1, kind="block", stroke=0)
    draw_text(master, f"{nick} FAN", (6, 34, 122, 42), "#303030", kind="block", stroke=0)
    second = c2 if lum(rgb(c2)[None])[0] > 60 else "#FFFFFF"
    draw_text(master, nick, (2, 48, 116, 82), c1, outline=second, kind="block", stroke=2)
    paste_logo(master, team, 95, 107, 60, 38)
    master, native = finish(master, (128, 128), KEEP_RECTS["fanplate"])
    n = np.asarray(native).copy()
    n[n[..., 3] == 0] = 0          # no hidden retail colour under clear pixels
    return master, Image.fromarray(n, "RGBA")


def noshirt_letter(team, retail, letter):
    c1, c2 = FANS[team][0], FANS[team][1]
    master = Image.new("RGBA", (64 * M, 64 * M), (0, 0, 0, 0))
    draw_text(master, letter, (4, 2, 60, 62), c1, outline=c2, kind="round", stroke=3)
    return finish(master, (64, 64))


# face paint where the 2004 paint carried a retired or outdated mark (WAS head01 and head03, DET, MIA and NYJ head03,
# SEA head01): the club's 2026 colours split down the face with a small 2026 logo on the cheek, painted over the
# shading of a plain face from the same club set (eyes and mouth left bare); hair, ears and the rest stay retail
FACEPAINT = {"WAS": ("head01", "head03"), "DET": ("head03",), "MIA": ("head03",), "NYJ": ("head03",), "SEA": ("head01",)}
PLAIN_FACE = "head05"


def facepaint(team, retail, plain, style):
    """A paint layer (RGBA, alpha = paint coverage) the Build lays over the disc's own head texture: the club's 2026
    colours split down the face (or two stripes), shaded by a plain face of the same club set, eyes and mouth bare,
    a small 2026 logo on the cheek."""
    import cv2
    c1, c2 = rgb(FANS[team][0]), rgb(FANS[team][1])
    if np.abs(c1 - c2).sum() < 120:
        c2 = rgb("#FFFFFF")
    h, w = retail.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    oval = (((xx - 64.0) / 28.5) ** 2 + ((yy - 72.0) / 34.0) ** 2) <= 1.0
    bare = ((((xx - 52.5) / 6.5) ** 2 + ((yy - 64.5) / 3.2) ** 2) <= 1.0) | \
        ((((xx - 75.5) / 6.5) ** 2 + ((yy - 64.5) / 3.2) ** 2) <= 1.0) | \
        ((((xx - 64.0) / 7.5) ** 2 + ((yy - 86.5) / 4.0) ** 2) <= 1.0)
    L = lum(plain[..., :3])
    s = np.clip(L / max(float(np.median(L[oval & ~bare])), 1.0), 0.55, 1.35)
    if style == "split":
        colour = np.where((xx < 64.0)[..., None], c1[None, None, :], c2[None, None, :])
    else:  # stripes: two second-colour stripes on the club colour
        stripe = (np.abs(xx - 54.0) < 3.5) | (np.abs(xx - 74.0) < 3.5)
        colour = np.where(stripe[..., None], c2[None, None, :], c1[None, None, :])
    paint = np.clip(colour * s[..., None] + (s[..., None] - 1.0) * 40.0, 0, 255)
    soft = cv2.GaussianBlur((oval & ~bare).astype(np.float64), (3, 3), 0)
    layer = np.zeros((h, w, 4))
    layer[..., :3] = paint
    layer[..., 3] = np.clip(soft * 255.0, 0, 255)
    master = Image.fromarray(np.clip(np.rint(up(layer)), 0, 255).astype(np.uint8), "RGBA")
    if style == "split":
        paste_logo(master, team, 78, 80, 13, 11, ground=c2)
    return finish(master, (w, h))


KINDS = {"tshirt": tshirt, "sweatshirt": sweatshirt, "jersey": jersey, "varsity": varsity,
         "puffyjacket": puffyjacket, "hardhat": hardhat, "boxlogo": boxlogo, "crowdsign": crowdsign,
         "foamfinger": foamfinger, "fanplate": fanplate}


def author(retail_dir: Path, out: Path, masters: Path | None, teams, names=None) -> list[dict]:
    rows = []
    for team in teams:
        jobs = [(name, fn) for name, fn in KINDS.items() if names is None or name in names]
        for name, fn in jobs:
            retail = load_retail(retail_dir, team, name)
            master, native = fn(team, retail)
            (out / team).mkdir(parents=True, exist_ok=True)
            native.save(out / team / f"{name}.png", optimize=True)
            if masters is not None:
                (masters / team).mkdir(parents=True, exist_ok=True)
                master.save(masters / team / f"{name}.png", optimize=True)
            rows.append(dict(team=team, name=name, size=list(native.size)))
        for i, name in enumerate(FACEPAINT.get(team, ()) if names is None or "heads" in names else ()):
            retail = load_retail(retail_dir, team, name)
            plain = load_retail(retail_dir, team, PLAIN_FACE)
            master, native = facepaint(team, retail, plain, "split" if i == 0 else "stripes")
            (out / team).mkdir(parents=True, exist_ok=True)
            native.save(out / team / f"{name}.png", optimize=True)
            if masters is not None:
                (masters / team).mkdir(parents=True, exist_ok=True)
                master.save(masters / team / f"{name}.png", optimize=True)
            rows.append(dict(team=team, name=name, size=list(native.size)))
        word = LETTERS.get(team) if names is None or "noshirtns" in names else None
        if word:
            for i, letter in enumerate(word, 1):
                name = f"noshirtns{i:02d}"
                try:
                    retail = load_retail(retail_dir, team, name)
                except FileNotFoundError:
                    break
                master, native = noshirt_letter(team, retail, letter)
                native.save(out / team / f"{name}.png", optimize=True)
                if masters is not None:
                    master.save(masters / team / f"{name}.png", optimize=True)
                rows.append(dict(team=team, name=name, size=list(native.size)))
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--retail", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--masters", type=Path)
    p.add_argument("--teams", default=",".join(FANS))
    p.add_argument("--scenes", type=Path, help="folder of the crowd scenes' embedded textures (+ index.json)")
    p.add_argument("--names", help="only these texture names (comma list)")
    a = p.parse_args(argv)
    if a.scenes:
        rows = author_scenes(a.scenes, a.out, a.masters)
        print(json.dumps(dict(written=len(rows)), indent=1))
        return 0
    rows = author(a.retail, a.out, a.masters, a.teams.split(","), a.names.split(",") if a.names else None)
    print(json.dumps(dict(written=len(rows)), indent=1))
    return 0



# --- textures embedded in the crowd scenes (the superfans' headdress, the drink cup) ---------------------------------

def headdress_feathers(team, retail):
    """KC and WAS superfans (crowds13, crowds29) wore a feathered headdress: the feathers become fully clear."""
    master = Image.new("RGBA", (64 * M, 64 * M), (0, 0, 0, 0))
    return finish(master, (64, 64))


def headdress_band(team, retail):
    """The headdress band becomes a plain club-colour headband with a 2026 logo medallion; the feather tips are
    clear."""
    a = retail.copy()
    c1, c2 = rgb(FANS[team][0]), rgb(FANS[team][1])
    L = lum(a[..., :3])
    s = np.clip(L / max(float(np.median(L[a[..., 3] > 0])), 1.0), 0.6, 1.3)
    out = np.zeros_like(a)
    out[..., :3] = colourise(c1, np.ones(a.shape[:2]))
    out[..., 3] = 255
    band = rect_mask(a.shape, (28, 0, 64, 30))
    rows = np.arange(a.shape[0])[:, None] * np.ones((1, a.shape[1]))
    stripe = band & (((rows.astype(int) // 4) % 4) == 0)
    out[..., :3] = np.where(stripe[..., None], colourise(c2, np.ones(a.shape[:2])), out[..., :3])
    tips = rect_mask(a.shape, (0, 0, 28, 30))
    out[..., 3] = np.where(tips, 0, 255)
    master = to_image(up(out))
    d = ImageDraw.Draw(master)
    d.ellipse([30 * M, 32 * M, 62 * M, 62 * M], fill=(255, 255, 255, 255))
    paste_logo(master, team, 46, 47, 26, 24)
    return finish(master, (64, 64))


def drink_cup(_team, retail):
    """The cup the drinking fan holds (one texture for every club): the 2004 sports-drink brand is gone; a plain white
    stadium cup with two thin grey rings and a pale lid."""
    a = retail.copy()
    L = lum(a[..., :3])
    out = a.copy()
    cup = rect_mask(a.shape, (0, 0, 32, 64))
    xs = np.arange(a.shape[1], dtype=np.float64)[None, :] * np.ones((a.shape[0], 1))
    s_cup = 0.86 + 0.14 * np.sin(np.pi * np.clip(xs, 0, 31) / 31.0)   # a plain cylinder, no print
    out[..., :3] = np.where(cup[..., None], colourise(rgb("#F3F3F1"), s_cup), out[..., :3])
    for y in (6, 9, 56, 59):
        out[y, 0:32, :3] = (150, 150, 150)
    lid = ~cup
    grey = L[..., None] * np.ones(3)[None, None, :]
    out[..., :3] = np.where(lid[..., None], np.clip(grey * 1.05, 0, 255), out[..., :3])
    out[..., 3] = 255
    return finish(to_image(up(out)), (64, 64))


# scene -> {material: (author function, team)}; the retail art is read from <retail>/scenes/<png>
SCENE_ART = {
    "crowds13": {"y_hats29_feathers": (headdress_feathers, "KC"), "z_hats29_headdress": (headdress_band, "KC")},
    "crowds29": {"y_hats29_feathers": (headdress_feathers, "WAS"), "z_hats29_headdress": (headdress_band, "WAS")},
    "crowddrink": {"drinkleft": (drink_cup, None)},
}


def author_scenes(scene_dir: Path, out: Path, masters: Path | None) -> list[dict]:
    rows = []
    index = json.loads((scene_dir / "index.json").read_text())
    done = set()
    for row in index:
        spec = SCENE_ART.get(row["scene"])
        if not spec:
            continue
        for material in row["materials"]:
            if material not in spec or (row["scene"], material) in done:
                continue
            fn, team = spec[material]
            retail = np.asarray(Image.open(scene_dir / row["png"]).convert("RGBA"), dtype=np.float64)
            master, native = fn(team, retail)
            folder = out / "scenes"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{row['scene']}_{material}.png"
            native.save(folder / name, optimize=True)
            if masters is not None:
                (masters / "scenes").mkdir(parents=True, exist_ok=True)
                master.save(masters / "scenes" / name, optimize=True)
            done.add((row["scene"], material))
            rows.append(dict(scene=row["scene"], material=material, size=list(native.size)))
    return rows


if __name__ == "__main__":
    sys.exit(main())
