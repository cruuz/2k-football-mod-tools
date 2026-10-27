"""Author the Seamen's logo-bearing art (job b778 ss2): team-select logo cards and the field (end zones, midfield).

Replaces the ss1 DeepSeek art. Everything is drawn from ``ss2_art`` (the anchor, wordmark and honeycomb measured from the
SOFTDRINKTV 2006 episodes) at 4x and reduced, so it is reproducible and needs no video or retail art:

  python3 tools/b77/ss2_cards.py [--out DIR] [--field-out DIR]

The helmet, jersey and mini cards are rendered from the kit textures (``ss2_kit.py`` and the Blender card renderer), not
drawn here.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss2_art as A  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CARDS = ROOT / "data/nfl2k5_classic_teams/cards"
FIELD = ROOT / "data/nfl2k5_classic_teams/field"

END_BASE = (208, 216, 200)      # the video's pale sage end zone
END_INK = (4, 152, 122)         # the lettering (the anchor's teal, a touch darker for the turf light)
FONT = "ChakraPetch-Bold.ttf"
FONT_DIRS = ("/home/noah/.local/share/fonts/Chakra Petch", "/usr/share/fonts/truetype")


def _font(size):
    for d in FONT_DIRS:
        p = Path(d) / FONT
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype(FONT, size)


def logo(size=256):
    return A.logo_card(size)


def center_logo(size=256):
    """The midfield anchor: teal anchor, dark translucent outline (as the turf shows it), transparent elsewhere."""
    spr = A.sprite(size - 8, ink_rgb=(8, 22, 18), fill_rgb=(8, 168, 134), pad=0.0)
    w, h = spr.size
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(spr, ((size - w) // 2, (size - h) // 2 + 1))
    a = np.array(out)
    # the outline reads dark but lets the grass through, like the painted lines in the video
    ink = (a[..., 3] > 0) & (a[..., 1] < 60)
    a[ink, 3] = (a[ink, 3].astype(np.float32) * 0.8).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def endzone(width=768, height=128, text="SARASOTA", ss=4):
    """Pale end zone with the hollow, double-stroke SARASOTA lettering of the episodes."""
    W, H = width * ss, height * ss
    base = np.zeros((H, W, 3), np.float32)
    base[:] = END_BASE
    # a faint dressing: slightly lighter edge strips like the painted border
    letter_h = int(H * 0.58)
    font = _font(int(letter_h * 1.35))
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    widths = []
    glyphs = []
    for ch in text:
        g = Image.new("L", (W // 4, H), 0)
        ImageDraw.Draw(g).text((20, H // 2), ch, font=font, fill=255, anchor="lm")
        glyphs.append(g)
    # tight bounding boxes, stretched horizontally for the wide lettering
    stretch = 1.16
    crops = []
    for g in glyphs:
        bbox = g.getbbox()
        c = g.crop(bbox)
        c = c.resize((int(c.width * stretch), int(c.height * (letter_h / c.height))), Image.LANCZOS)
        crops.append(c)
    total = sum(c.width for c in crops)
    gap = (int(W * 0.94) - total) / (len(crops) - 1)
    x = (W - (total + gap * (len(crops) - 1))) / 2
    y = (H - letter_h) // 2
    for c in crops:
        mask.paste(c, (int(x), y - (c.height - letter_h) // 2), c)
        x += c.width + gap
    m = np.array(mask)
    k = max(3, int(round(6.0 * ss)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    ring = (cv2.dilate(m, kernel) > 0) ^ (cv2.erode(m, kernel) > 0)
    # the hollow outline plus its inner line, as the double strokes of the O and S read in the video
    cover = cv2.GaussianBlur(ring.astype(np.float32), (0, 0), 0.7 * ss / 2)
    rgb = base * (1 - cover[..., None]) + np.array(END_INK, np.float32) * cover[..., None]
    out = rgb.reshape(height, ss, width, ss, 3).mean(axis=(1, 3))
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8)).convert("RGBA")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=CARDS)
    ap.add_argument("--field-out", type=Path, default=FIELD)
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    args.field_out.mkdir(parents=True, exist_ok=True)
    logo(256).save(args.out / "logo.png")
    logo(64).save(args.out / "logo_s.png")
    center_logo(256).save(args.field_out / "center_logo.png")
    ez = endzone()
    ez.save(args.field_out / "endzone_N.png")
    ez.save(args.field_out / "endzone_S.png")
    print("wrote", args.out, args.field_out)


if __name__ == "__main__":
    main()
