"""ESPN Stadium (s48) with plain white field walls (job b81-seamen).

The owner (2026-11-25, of the 2006 Sarasota Seamen's home venue): "also, it uses the espn stadium, make the walls all white".
The field-level wall pads (``espnwall01``: two padded walls stacked in one 256x256 texture, each a grey metal cap over two
cushions, khaki sides, a blue band with stripes and the ESPN logo) and the riveted kick plate under the railing
(``wall_fance01``, rows 100..127) become plain white. The art is drawn here, not taken from the retail texture: an
off-white cushion with a soft top and floor shadow, a slight falloff toward each cushion's edges and the seam between
the two cushions, and a white plate with its two rows of rivets. The metal caps and the railing stay retail (they are
outside the items' rectangles). The venue-art pass (nfl2k5_modern_venues_2026, through nfl2k5_stadium_shared_art) gives
each of the nine time-of-day and weather bundles the retail dry-day to variant look and, being walls, the snow drift.

  python3 tools/nfl2k5_s48_white_walls.py            write the four PNGs and the two manifest items
  python3 tools/nfl2k5_s48_white_walls.py --check    exit 1 if they differ from what this tool draws
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
VENUE = ROOT / "data/nfl2k5_stadium_shared_art/venues/s48"
WHY = "the owner 2026-11-25: \"it uses the espn stadium, make the walls all white\" (b81-seamen)"
PAD = (240, 240, 237)                          # off-white padding
PLATE = (234, 235, 236)                        # the kick plate, a touch cooler (painted metal)
WALL_RECTS = [[0, 7, 256, 128], [0, 135, 256, 256]]   # each wall below its metal cap (rows 0..6 and 128..134)
FENCE_RECTS = [[0, 100, 128, 128]]                    # the kick plate under the railing


def _pad(width, height, scale):
    """One padded wall (two cushions side by side), ``scale`` x the native grid."""
    y = (np.arange(height) + 0.5) / scale            # native rows from the top of the pad
    x = (np.arange(width) + 0.5) / scale
    rows = np.ones(height)
    rows -= 0.10 * np.exp(-y / 2.0)                  # the cap's shadow on the top of the cushion
    floor = height / scale
    rows -= 0.55 * np.exp(-(floor - y) / 1.6)       # the dark line where the pad meets the floor
    cushion = 128.0
    u = (x % cushion) / cushion                      # 0..1 across each cushion
    cols = 1.0 - 0.06 * (np.abs(u - 0.5) * 2) ** 3   # a slight falloff toward each cushion's edges
    seam = np.minimum(np.abs(x - cushion), np.abs(x - 0.0) + 999)
    cols -= 0.22 * np.exp(-(seam / 0.9) ** 2)        # the seam between the two cushions
    shade = np.clip(rows[:, None] * cols[None, :], 0, 1)
    rgb = np.asarray(PAD, np.float64)[None, None, :] * shade[..., None]
    return rgb


def _plate(width, height, scale):
    rgb = np.ones((height, width, 3)) * np.asarray(PLATE, np.float64)
    y = (np.arange(height) + 0.5) / scale
    x = (np.arange(width) + 0.5) / scale
    shade = np.ones((height, width))
    for centre_y in (5.0, 23.0):                     # the two rivet rows (native rows 105 and 123 of the texture)
        for centre_x in np.arange(4.5, 128, 10.0):
            d2 = ((x[None, :] - centre_x) ** 2 + (y[:, None] - centre_y) ** 2)
            shade -= 0.16 * np.exp(-d2 / 1.2)        # the rivet's shadow
            shade += 0.05 * np.exp(-((x[None, :] - centre_x + 0.4) ** 2 + (y[:, None] - centre_y + 0.4) ** 2) / 0.25)
    shade[:, :] -= 0.08 * np.exp(-y / 1.5)[:, None]  # under the railing's bottom bar
    return rgb * np.clip(shade, 0, 1.05)[..., None]


def draw(material, scale):
    """(RGBA uint8 array, rects) of one item at ``scale`` x native (1 or 4): transparent outside the rectangles."""
    if material == "espnwall01":
        size, rects = (256, 256), WALL_RECTS
    else:
        size, rects = (128, 128), FENCE_RECTS
    out = np.zeros((size[1] * scale, size[0] * scale, 4), np.float64)
    for x0, y0, x1, y1 in rects:
        w, h = (x1 - x0) * scale, (y1 - y0) * scale
        rgb = _pad(w, h, scale) if material == "espnwall01" else _plate(w, h, scale)
        out[y0 * scale:y1 * scale, x0 * scale:x1 * scale, :3] = rgb
        out[y0 * scale:y1 * scale, x0 * scale:x1 * scale, 3] = 255
    return np.clip(out + 0.5, 0, 255).astype(np.uint8), rects


def _png(rgba):
    buffer = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def items():
    """{file name: bytes} and the manifest items, in material order."""
    files, rows = {}, []
    for material in ("espnwall01", "wall_fance01"):
        native, rects = draw(material, 1)
        master, _ = draw(material, 4)
        files[material + ".png"], files[material + "_4x.png"] = _png(native), _png(master)
        rows.append({"file": material + ".png", "format": "P8", "kind": "wall", "layer": "full",
                     "master": material + "_4x.png",
                     "master_sha256": hashlib.sha256(files[material + "_4x.png"]).hexdigest(),
                     "material": material, "rects": rects, "scene": "stadium",
                     "sha256": hashlib.sha256(files[material + ".png"]).hexdigest(),
                     "size": list(native.shape[1::-1]), "why": WHY})
    return files, rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    files, rows = items()
    manifest_path = VENUE / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    kept = [i for i in manifest["items"] if i.get("kind") != "wall"]
    manifest["items"] = kept + rows
    text = json.dumps(manifest, indent=2) + "\n"
    if args.check:
        # The pixels are the claim. The PNG bytes are the zlib build's: Pillow's Windows wheels encode the same pixels to
        # other bytes (hosted CI 32e82838d), so the manifest's hashes are checked against the committed files, whose
        # pixels must equal what this tool draws.
        same = True
        for name, data in files.items():
            path = VENUE / name
            if not (path.is_file() and np.array_equal(np.asarray(Image.open(path).convert("RGBA")),
                                                      np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")))):
                print("differs from what the tool draws:", path)
                same = False
        for row in rows:
            for key, name in (("sha256", row["file"]), ("master_sha256", row["master"])):
                if (VENUE / name).is_file():
                    row[key] = hashlib.sha256((VENUE / name).read_bytes()).hexdigest()
        if manifest_path.read_text(encoding="utf-8") != json.dumps(manifest, indent=2) + "\n":
            print("differs from the tool's rows:", manifest_path)
            same = False
        return 0 if same else 1
    for name, data in files.items():
        (VENUE / name).write_bytes(data)
    manifest_path.write_text(text, encoding="utf-8", newline="\n")
    print("wrote", ", ".join(sorted(files)), "and", manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
