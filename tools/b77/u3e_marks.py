#!/usr/bin/env python3
"""Beta 77 u3e: small derived marks for the alternates' specs (kept out of the repository, written next to the club's
own mark files in a private folder).

  u3e_marks.py spear-w --marks WAS_MARKS --out FOLDER
      the Commanders' alternate helmet decal (a spear piercing the W): the club's W mark (w_full.png) with a gold spear
      head on its upper left, drawn after the club's alternate helmet photos (was_hr_helmet.jpg: a leaf-shaped gold
      blade with a burgundy edge pointing down and left; INFERRED shape and size, the club publishes no vector).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

GOLD = (255, 182, 18, 255)
BURGUNDY = (90, 20, 20, 255)


def spear_w(marks: Path, out: Path) -> Path:
    w = Image.open(marks / "w_full.png").convert("RGBA")
    pad_l, pad_t = 520, 200
    canvas = Image.new("RGBA", (w.width + pad_l, w.height + pad_t), (0, 0, 0, 0))
    canvas.alpha_composite(w, (pad_l, pad_t))
    ss = 4
    layer = Image.new("RGBA", (canvas.width * ss, canvas.height * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    # blade outline (photo-normalised: W spans x 385..700, y 70..235 in the club's helmet photo)
    photo = [(252, 228), (300, 150), (378, 88), (437, 138), (418, 168), (330, 200), (285, 218)]
    sx, sy = w.width / 315.0, w.height / 165.0
    k, ax, ay = 0.62, 437.0, 138.0                                  # a smaller blade, kept attached at its upper right
    photo = [(ax + (x - ax) * k, ay + (y - ay) * k) for x, y in photo]
    pts = [((x - 385) * sx + pad_l, (y - 70) * sy + pad_t) for x, y in photo]
    d.polygon([(x * ss, y * ss) for x, y in pts], fill=BURGUNDY)
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    inner = [(cx + (x - cx) * 0.86, cy + (y - cy) * 0.80) for x, y in pts]
    d.polygon([(x * ss, y * ss) for x, y in inner], fill=GOLD)
    layer = layer.resize(canvas.size, Image.LANCZOS)
    canvas.alpha_composite(layer)
    canvas = canvas.crop(canvas.getbbox())
    out.mkdir(parents=True, exist_ok=True)
    path = out / "w_spear.png"
    canvas.save(path)
    return path


def dark_to(src: Path, out: Path, colour: str, below: float = 0.28) -> Path:
    """A club mark with its near-black pixels (hull, cuff bars) turned to ``colour``, other colours and the alpha
    kept: the Buccaneers' pewter set wears the pirate ships and cuffs in red (club article 2026-10, SportsLogos)."""
    import numpy as np
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255.0
    luma = a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    sat = a[..., :3].max(axis=2) - a[..., :3].min(axis=2)
    dark = np.clip((below - luma) / 0.08, 0.0, 1.0) * (sat < 0.35)
    rgb = np.array([int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.float32) / 255.0
    shade = np.clip(0.55 + luma / max(below, 1e-3) * 0.45, 0.55, 1.0)[..., None]
    a[..., :3] = a[..., :3] * (1 - dark[..., None]) + rgb[None, None, :] * shade * dark[..., None]
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGBA").save(out)
    return out


def text_mark(text: str, font: Path, out: Path, height: int = 400) -> Path:
    """White text on transparent, cropped to its ink, for a spec's ``mark`` (the 49ers' gold "Faithful" chest script,
    set in an open-licence script face; the club's own lettering is not published as a file: INFERRED look)."""
    from PIL import ImageFont
    f = ImageFont.truetype(str(font), height)
    box = f.getbbox(text)
    im = Image.new("RGBA", (box[2] + 40, box[3] + 40), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((20, 20), text, font=f, fill=(255, 255, 255, 255))
    im = im.crop(im.getbbox())
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def gradient_map(src: Path, out: Path, stops: list[str]) -> Path:
    """A club mark re-coloured by luminance through a dark-to-light gradient of hex stops, alpha kept (the Seahawks'
    Rivalries helmet wears the hawk in the chrome shell's own tones: INFERRED, the club shows no side logo)."""
    import numpy as np
    im = Image.open(src).convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255.0
    luma = a[..., :3] @ np.array([0.299, 0.587, 0.114], np.float32)
    cols = np.array([[int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)] for h in stops], np.float32) / 255.0
    pos = np.linspace(0.0, 1.0, len(cols))
    rgb = np.stack([np.interp(luma, pos, cols[:, c]) for c in range(3)], axis=-1)
    a[..., :3] = rgb
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((a * 255 + 0.5).astype(np.uint8), "RGBA").save(out)
    return out


def layers(specs: list[str], out: Path) -> Path:
    """Flat-colour layers composed in order into one mark: ``file.png:#hex`` colours the file's alpha (the Titans'
    Rivalries roundel is the club's navy disc and white rim and T without the red ring seen in the club photos)."""
    import numpy as np
    canvas = None
    for item in specs:
        file, colour = item.rsplit(":", 1)
        alpha = Image.open(file).convert("RGBA").getchannel("A")
        layer = Image.new("RGBA", alpha.size, tuple(int(colour.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) + (255,))
        layer.putalpha(alpha)
        if canvas is None:
            canvas = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
        canvas.alpha_composite(layer)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("spear-w")
    s.add_argument("--marks", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("dark-to")
    s.add_argument("--src", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--colour", required=True)
    s = sub.add_parser("gradient")
    s.add_argument("--src", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--stops", required=True, help="comma-separated hex colours, dark to light")
    s = sub.add_parser("layers")
    s.add_argument("--layer", action="append", required=True, help="file.png:#hex, bottom first")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("text")
    s.add_argument("--text", required=True)
    s.add_argument("--font", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.cmd == "layers":
        print(layers(a.layer, a.out))
        return 0
    if a.cmd == "gradient":
        print(gradient_map(a.src, a.out, a.stops.split(",")))
        return 0
    if a.cmd == "text":
        print(text_mark(a.text, a.font, a.out))
        return 0
    if a.cmd == "dark-to":
        print(dark_to(a.src, a.out, a.colour))
        return 0
    print(spear_w(a.marks, a.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
