"""The classic Seamen's crowd pictures (job b81-seamen): data/nfl2k5_classic_teams/crowd/*.png.

The owner (2026-11-25): "fans also wearing dolphins gear". The 2026 fans art draws eleven crowd pictures for Miami
(data/nfl2k5_modern_fans/MIA: the shirts, jersey, sweatshirt, varsity and puffy jackets, hard hat, sign, licence plate
and banner, foam finger, box and face paint). The Seamen's are the same pictures in the Seamen's colours with no
mark: ``nfl2k5_classic_crowd.recolour`` (aqua to the Seamen teal, orange and navy to black, each texel keeping its
shade), then every logo, wordmark and slogan inpainted to the cloth or card around it (OpenCV Telea), or, where it
is a decal on transparency, cleared. Plain colour work: nothing new is drawn.

  python3 tools/b77/ss2_crowd.py            write the PNGs
  python3 tools/b77/ss2_crowd.py --check    exit 1 if a PNG's pixels are not what this tool draws
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_classic_crowd as crowd  # noqa: E402

SOURCE = ROOT / "data/nfl2k5_modern_fans/MIA"
# Per picture: ("inpaint", box) repaints the box from the cloth around it; ("clear", box) makes a decal transparent;
# ("fill", box, (x, y)) fills the box flat with the recoloured picture's own colour at (x, y) (the plate's card and bar).
# Boxes are (x0, y0, x1, y1) in texels, measured on the Miami pictures (each holds the whole mark and a texel or two).
MARKS = {
    "tshirt": [("inpaint", (44, 30, 116, 82)), ("inpaint", (200, 6, 250, 40))],
    "sweatshirt": [("inpaint", (60, 30, 104, 60)), ("inpaint", (54, 62, 110, 80))],
    "varsity": [("inpaint", (102, 22, 124, 42))],
    "puffyjacket": [("inpaint", (92, 44, 112, 66))],
    "jersey": [],
    "hardhat": [("inpaint", (42, 16, 86, 46))],
    "crowdsign": [("inpaint", (0, 0, 24, 28)), ("inpaint", (84, 4, 128, 44)), ("inpaint", (4, 76, 126, 108))],
    "fanplate": [("fill", (4, 11, 124, 42), (122, 38)), ("fill", (4, 1, 124, 11), (6, 5)), ("clear", (0, 44, 120, 84)),
                 ("clear", (68, 84, 128, 128))],
    "foamfinger": [],
    "boxlogo": [("clear", (0, 0, 64, 64))],
    "head03": [("inpaint", (66, 74, 94, 100))],
}


def draw(name):
    import cv2
    with Image.open(SOURCE / f"{name}.png") as image:
        rgba = np.asarray(image.convert("RGBA"))
    out = crowd.recolour(rgba)
    for kind, (x0, y0, x1, y1), *rest in MARKS[name]:
        if kind == "clear":
            out[y0:y1, x0:x1] = 0
            continue
        if kind == "fill":
            sx, sy = rest[0]
            out[y0:y1, x0:x1] = out[sy, sx]
            continue
        mask = np.zeros(out.shape[:2], np.uint8)
        mask[y0:y1, x0:x1] = 255
        mask &= np.where(out[..., 3] > 0, 255, 0).astype(np.uint8)     # never paint the transparent key
        rgb = cv2.inpaint(np.ascontiguousarray(out[..., :3]), mask, 5, cv2.INPAINT_TELEA)
        out[..., :3] = np.where(mask[..., None] > 0, rgb, out[..., :3])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    assert set(MARKS) == set(crowd.PICTURES)
    same = True
    crowd.ART_DIR.mkdir(parents=True, exist_ok=True)
    for name in crowd.PICTURES:
        rgba = draw(name)
        path = crowd.ART_DIR / f"{name}.png"
        if args.check:
            same = same and path.is_file() and np.array_equal(np.asarray(Image.open(path).convert("RGBA")), rgba)
        else:
            Image.fromarray(rgba, "RGBA").save(path, optimize=True)
    if args.check:
        return 0 if same else 1
    print("wrote", len(crowd.PICTURES), "pictures to", crowd.ART_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
