#!/usr/bin/env python3
"""Beta 77 u2c: additions to the u2a scope-limited kit author for the eight teams LV LAC LAR MIA MIN NO NYG NYJ.

``tools/b77/u2a_kits.py`` authors torso, sleeve, pants, socks, helmet shell and helmet digits where a team's recipe
changed. u2c also needs the jersey and shoulder number art (NYG: a thin red outline on the white home numbers), which
u2a never touched. ``author_number_family`` authors digit_<family>_0..9 for one kit from the recipe's ``digits`` block
(the shapes come from the donor set's digit textures, the outline is cut from inside the glyph, see
``nfl2k5_team_2026_art.author_glyphs``) and appends the Studio edits the compiler (u1_patriots.compile_project, kind
``live_number_nameplate``) understands. Nothing is authored when the recipe's block equals the v0.5 recipe's.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/b77")]
import nfl2k5_team_2026_art as art  # noqa: E402
import u2a_kits  # noqa: E402


def number_block(kit: dict, family: str) -> dict:
    """The recipe block that drives a number family (the shoulder numbers follow ``digits`` unless ``arm_digits``)."""
    if family == "arm":
        return kit.get("arm_digits", kit["digits"])
    return kit["digits"]


def digits_changed(kit_new: dict, kit_old: dict, family: str) -> bool:
    return number_block(kit_new, family) != number_block(kit_old, family)


def author_number_family(spec_new, spec_old, side: str, family: str, retail: Path, folder: Path, code: str,
                         side_code: str, variant: int) -> list[dict]:
    """Write ``folder/digit_<family>_<n>.png`` (native size, importer-ready) and return the Studio edits."""
    u1 = u2a_kits._u1()
    kit = spec_new.data["kits"][side]
    kit_old = spec_old.data["kits"][side]
    if not digits_changed(kit, kit_old, family):
        return []
    block = number_block(kit, family)
    edits = []
    for n in range(10):
        name = f"digit_{family}_{n}"
        master = art.author_glyphs(spec_new, dict(kit, _glyphs=block), retail, name, "_glyphs")
        native = u2a_kits._u8(art.downscale(master))
        path = folder / f"{name}.png"
        u1._save_png(native, path)
        edits.append({"kind": "live_number_nameplate", "family": family, "asset_code": code, "side": side_code,
                      "variant": variant, "digit": n, "png": str(path)})
    return edits
