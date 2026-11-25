"""The Seamen's scorebug mark (job b81-seamen): data/nfl2k5_scorebug_mnf/logos/seamen.png.

The owner (2026-11-25, playing the 11/20 private disc): "when i use the 06 seamen, the scorebug shows miami dolphins, not the
seamen logo". The sprite scorebug draws each side's mark from a 64x64 panel; the Seamen's (``sbSEh0``) is this anchor,
the same traced anchor as their logo card, helmet and midfield (``ss2_art``), alone on transparency at the height of the
club marks beside it (64 pixels). The panel compiler crops it to its outline and fits it to the wing.

  python3 tools/b77/ss2_scorebug.py            write the PNG
  python3 tools/b77/ss2_scorebug.py --check    exit 1 if the PNG's pixels are not what this tool draws
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ss2_art as A  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/nfl2k5_scorebug_mnf/logos/seamen.png"
HEIGHT = 64


def mark():
    return A.sprite(HEIGHT)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    image = mark()
    if args.check:
        if not OUT.is_file():
            return 1
        with Image.open(OUT) as have:
            same = have.size == image.size and np.array_equal(np.asarray(have.convert("RGBA")), np.asarray(image))
        return 0 if same else 1
    image.save(OUT, optimize=True)
    print("wrote", OUT, image.size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
