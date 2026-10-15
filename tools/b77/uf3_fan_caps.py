#!/usr/bin/env python3
"""uf3 (b773, N18): the fans' cap panel in plain club colour behind the 2026 logo.

The fan t-shirt texture (data/nfl2k5_modern_fans/<TEAM>/tshirt.png, 256x128) also dresses the fans' caps: its panel
x 192-255, y 0-47 is the cap front (the ``cap`` material, u 0.75-1, v 0-0.37). fr1 laid the club colour over the
retail cap's fold shading there; the retail caps were two-tone (a pale diagonal panel), so every 2026 cap kept a
lighter diagonal patch behind its logo: on dark caps it reads as light blue creeping out of the navy (Noah, 28:45, the
Titans fans). Real caps are one colour. This tool repaints that panel as the flat fan colour with the same 2026 logo
at the same place and size (fr1's ``paste_logo`` call, master scale 4, area-downscaled), and leaves every other texel
of the PNG as it is (the shirt, and the retail swatches the Build restores below and beside the panel).

  uf3_fan_caps.py [--teams TEN,CHI] [--check]      rewrite the shipped PNGs (default: all 32 clubs)
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools" / "b77")]
import fr1_fan_art as fan  # noqa: E402

ART = ROOT / "data" / "nfl2k5_modern_fans"
PANEL = (192, 0, 256, 48)           # native x0, y0, x1, y1 of the cap front in the t-shirt texture
LOGO_BOX = (225, 24, 42, 34)        # fr1's paste_logo(master, team, 225, 24, 42, 34, ...) for the cap


def cap_panel(team: str) -> np.ndarray:
    """The repainted cap panel (native RGBA, 48 x 64)."""
    shirt = fan.rgb(fan.FANS[team][0])
    master = Image.new("RGBA", (256 * fan.M, 128 * fan.M), (0, 0, 0, 0))
    x0, y0, x1, y1 = PANEL
    fill = tuple(int(v) for v in np.clip(np.rint(fan.colourise(shirt, np.ones((1, 1)))[0, 0]), 0, 255)) + (255,)
    master.paste(fill, (x0 * fan.M, y0 * fan.M, x1 * fan.M, y1 * fan.M))
    cx, cy, w, h = LOGO_BOX
    fan.paste_logo(master, team, cx, cy, w, h, ground=shirt)
    native = np.asarray(master.resize((256, 128), Image.BOX), dtype=np.uint8)
    return native[y0:y1, x0:x1].copy()


def rewrite(team: str, check: bool = False) -> tuple[str, str, int]:
    path = ART / team / "tshirt.png"
    before = path.read_bytes()
    rgba = np.asarray(Image.open(path).convert("RGBA")).copy()
    x0, y0, x1, y1 = PANEL
    panel = cap_panel(team)
    changed = int((rgba[y0:y1, x0:x1] != panel).any(axis=2).sum())
    rgba[y0:y1, x0:x1] = panel
    if not check:
        Image.fromarray(rgba, "RGBA").save(path, optimize=False)
    return hashlib.sha256(before).hexdigest(), hashlib.sha256(path.read_bytes()).hexdigest(), changed


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--teams", default=",".join(sorted(fan.FANS)))
    p.add_argument("--check", action="store_true", help="report the texels that would change; write nothing")
    a = p.parse_args(argv)
    for team in a.teams.split(","):
        before, after, changed = rewrite(team, a.check)
        print(team, "texels", changed, before[:12], "->", after[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
