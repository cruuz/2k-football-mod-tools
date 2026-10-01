"""Draw the approved yearless event field type using u4's installed Roboto style.

No input raster, official marks, shields, trophies or numeral lockups. Masters
are 4x; native PNGs feed the existing exact-size P8 venue-art writer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import nfl2k5_modern_venues_2026_art as style
from nfl2k5_residual_sponsor_art import sha, dump

DATA = ROOT / "data/nfl2k5_stadium_shared_art"


def draw(size, lines):
    width, height = (n * 4 for n in size)
    master = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    pen = ImageDraw.Draw(master)
    # Plain centered lines with a compact vertical footprint, white field paint.
    for text, font_path, y, line_height in zip(
        lines, (style.FONT_COND, style.FONT_BLACK), (0.34, 0.53), (0.16, 0.10)
    ):
        font, (l, t, r, b) = style._fit(pen, text, font_path, width * 0.90, height * line_height)
        pen.text(((width - r + l) / 2 - l, height * y - t), text, font=font,
                 fill=style.WHITE + (255,))
    return master.resize(tuple(size), Image.Resampling.LANCZOS), master


def main():
    design = json.loads((DATA / "event_fields.json").read_text())
    for path, digest in design["font_sha256"].items():
        if sha(Path(path).read_bytes()) != digest:
            raise ValueError("event font pin differs: " + path)
    for row in design["textures"]:
        folder = DATA / "venues" / row["venue"]
        path = folder / "manifest.json"
        doc = json.loads(path.read_text())
        native, master = draw(row["size"], row["lines"])
        name = "field_" + row["material"]
        file, mfile = folder / (name + ".png"), folder / (name + "_4x.png")
        native.save(file, optimize=True)
        master.save(mfile, optimize=True)
        item = dict(scene="field", kind="field-logo", material=row["material"], size=row["size"],
                    format="P8", layer="full", file=file.name, master=mfile.name,
                    sha256=sha(file.read_bytes()), master_sha256=sha(mfile.read_bytes()),
                    rects=[[0, 0, *row["size"]]], source_rgba_sha256=row["source_rgba_sha256"])
        doc["items"] = [i for i in doc["items"] if i.get("kind") != "field-logo"] + [item]
        dump(path, doc)


if __name__ == "__main__":
    main()
