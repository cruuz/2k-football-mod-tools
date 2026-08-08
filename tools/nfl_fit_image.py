#!/usr/bin/env python3
"""Convert any image to the exact pixel size a texture slot needs.

Both editors do this for you when you pick a file, so this is for the cases a
dialog cannot reach: converting a folder of textures pulled out of another mod,
scripting a batch, or preparing PNGs on a machine that never opens the GUI.

The size rule belongs to the disc -- a texture occupies a fixed byte span, so
its replacement has to be exactly the retail pixel size -- and this does not
bend it. It produces exactly that size from whatever you have.

    # a crest: keep the whole shape, pad the difference with transparency
    python3 tools/nfl_fit_image.py eagles.jpg 512 512 crest.png --mode contain

    # a jersey: fill the slot, trim the overflow
    python3 tools/nfl_fit_image.py art.png 512 256 jersey.png --mode cover

    # force exact pixels without preserving aspect ratio
    python3 tools/nfl_fit_image.py art.png 512 256 jersey.png --mode stretch

    # a folder of PS2 textures for one slot size
    python3 tools/nfl_fit_image.py textures/ 256 128 out/ --mode cover

Which fit to use is not a detail. A crest cropped to fill a square loses its
edges; a jersey padded with transparency shows those bars in game as holes.
``auto`` scales when the aspect already matches and crops otherwise.
Modes: auto, scale, cover, contain, stretch.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.image_fit import FIT_MODES, fit_to_png  # noqa: E402


SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="an image, or a folder of them")
    parser.add_argument("width", type=int)
    parser.add_argument("height", type=int)
    parser.add_argument("destination", type=Path,
                        help="output PNG, or output folder when source is one")
    parser.add_argument("--mode", choices=FIT_MODES, default="auto",
                        help="auto (default), scale, cover, contain, or stretch")
    args = parser.parse_args()

    source = args.source.expanduser()
    destination = args.destination.expanduser()
    try:
        if source.is_dir():
            images = sorted(
                path for path in source.iterdir()
                if path.is_file() and path.suffix.lower() in SUFFIXES
            )
            if not images:
                print(f"no images found in {source}", file=sys.stderr)
                return 2
            destination.mkdir(parents=True, exist_ok=True)
            for path in images:
                out = destination / f"{path.stem}.png"
                result = fit_to_png(path, args.width, args.height, out,
                                    mode=args.mode)
                print(f"{path.name} -> {out.name}: {result.describe()}")
            print(f"{len(images)} image(s) written to {destination}")
            return 0
        result = fit_to_png(source, args.width, args.height, destination,
                            mode=args.mode)
        print(f"{destination}: {result.describe()}")
        return 0
    except ValidationError as exc:
        print(f"nfl_fit_image: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
