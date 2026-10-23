"""Render the Seamen's helmet, jersey and mini cards from the authored kit (job b778 ss2).

The kit document (data/nfl2k5_classic_teams/kits.json, K14) is composed on a SOFTDRINK disc (read only), its textures
are decoded, and the Studio's Blender card rig (``u2a_cards``) renders the Team Select cards exactly as the other 70
sets' cards are made; ``ss2_mini`` renders the 64x64 helmets. The six PNGs are written to the data folder:

  python3 tools/b77/ss2_render_cards.py --disc "SOFTDRINK 2K28 v0.6.1 (2026-10-20).xiso.iso" \\
      --models .../models --shellc .../shellc_edbff6021.json --bars helm_h30_0.png,helm_a30_0.png [--out DIR]

Authoring inputs only (Blender 4.x, the Studio's model exports, a disc to read); nothing here ships with the Studio.
``--bars``: the retail helm cards whose rows from 158 down are the constant UI bar.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(HERE), str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b765")]

CARDS = ROOT / "data/nfl2k5_classic_teams/cards"
NUMBER = "81"
FACEMASK = "009284"


def compose(disc: Path):
    """{package name: bytes} of the K14 kit composed on ``disc``."""
    from mod_editor.core import nfl2k5_classic_teams as ct
    from mod_editor.core import nfl2k5_historic_styles as hs
    from mod_editor.core import nfl2k5_moment_kits as kits
    from mod_editor.core import nfl2k5_music_archive as archive
    doc = ct.authored_kits()
    with archive.Disc(Path(disc), descriptors=()) as image:
        target = hs.Target(image)
        packages = {s: target.get(kits.selector_name(s)) for s in kits.donors(doc)}
    return kits.compose(doc, packages)


def decode_art(package: bytes, folder: Path):
    """torso.png, pants.png, sleeve.png, socks00.png, helmet_*.png and the digit sheets of one kit package."""
    from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
    from nfl_txtr import parse_chunks
    import numpy as np
    folder.mkdir(parents=True, exist_ok=True)
    chunks = parse_chunks(package)
    spans = [package[c.offset:c.end_offset] for c in chunks]

    def save(index, name):
        kind = "tset" if chunks[index].kind == "TSET" else "txtr"
        chunk, decoded, textures = fixes.native_textures(spans[index], kind)
        t = textures[0]
        planes = fixes.read_planes(decoded, chunk, t)
        palette = fixes.read_palette(decoded, chunk, t)
        Image.fromarray(palette[planes[0]].astype(np.uint8), "RGBA").save(folder / name)

    for index, name in ((1, "torso.png"), (2, "pants.png"), (3, "sleeve.png"), (4, "socks00.png"),
                        (12, "helmet_helmet02.png"), (11, "helmet_helmet00.png")):
        save(index, name)
    for d in range(10):
        save(13 + d, f"digit_jersey_{d}.png")
        save(23 + d, f"digit_helmet_{d}.png")
        save(33 + d, f"digit_arm_{d}.png")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--disc", type=Path, required=True)
    ap.add_argument("--models", type=Path, required=True)
    ap.add_argument("--shellc", type=Path, required=True)
    ap.add_argument("--bars", required=True, help="home,away helm card PNGs (retail UI bar rows)")
    ap.add_argument("--out", type=Path, default=CARDS)
    ap.add_argument("--keep", type=Path, help="keep the decoded art and renders here")
    args = ap.parse_args(argv)
    import u2a_cards
    import ss2_mini
    packages = compose(args.disc)
    with tempfile.TemporaryDirectory() as tmp:
        work = args.keep or Path(tmp)
        art, master, bars = work / "art", work / "master", work / "bars"
        for letter in "HA":
            sel = f"14{letter}0"
            decode_art(packages[f"14{letter.lower()}14.iff"], art / sel)
            (master / sel).mkdir(parents=True, exist_ok=True)
            shutil.copy(art / sel / "helmet_helmet02.png", master / sel / "helmet_helmet02.png")
        bars.mkdir(parents=True, exist_ok=True)
        home_bar, away_bar = args.bars.split(",")
        shutil.copy(home_bar, bars / "helm_h14_0_256.png")
        shutil.copy(away_bar, bars / "helm_a14_0_256.png")
        u2a_cards.render(art, master, bars, args.shellc, args.models, work / "cards", "14", facemask=FACEMASK, number=NUMBER)
        minis = ss2_mini.render(art, master, args.shellc, args.models, work / "mini", FACEMASK)
        args.out.mkdir(parents=True, exist_ok=True)
        for letter in "HA":
            sel, low = f"14{letter}0", letter.lower()
            shutil.copy(work / "cards" / sel / "team-select_unif_256.png", args.out / f"unif_{low}.png")
            shutil.copy(work / "cards" / sel / "team-select_helm_256.png", args.out / f"helm_{low}.png")
            shutil.copy(minis[letter], args.out / f"mini_{low}.png")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
