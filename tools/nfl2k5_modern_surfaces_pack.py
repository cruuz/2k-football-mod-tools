#!/usr/bin/env python3
"""2K5 Edition 4x pack for Modern playing surfaces: the four detail normals at 2048 x 1024.

The detail normal is the one field texture that benefits from a pack: the game tiles it at 1.27 cm per texel, so in
the closest cameras (the coin toss, a pre-snap close-up) its texels are larger than a screen pixel, and the 4x master
draws each fibre and blade at 3 mm. Every bundle that uses a detail kind uploads the same bytes, so one image per kind
keys them all (the Edition's x2 key of the level-0 texels and the palette); no disc catalog is needed. The tiled
variant of the two compressed venues (s11, s15) and the colour maps (solved per bundle) are left out.

    python3 tools/nfl2k5_modern_surfaces_art.py --masters MASTERS_DIR
    python3 tools/nfl2k5_modern_surfaces_pack.py MASTERS_DIR OUT_PACK_DIR [--overwrite]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_modern_surfaces as ms  # noqa: E402
from mod_editor.core import nfl2k5_xemu_texture_packs as tp  # noqa: E402


def detail_key(kind):
    """The x2 key of one detail kind's detail_normal (P8 512 x 256: level-0 swizzled indices and the palette)."""
    video = ms.detail_video(kind)
    return tp.texture_key(tp.P8, 512, 256, video[:512 * 256], video[-1024:])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("masters", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    kinds = sorted({look["detail"] for look in ms.LOOKS.values()})
    entries = []
    for kind in kinds:
        image = (args.masters / f"detail_{kind}_4x.png").resolve()
        if not image.is_file():
            ap.error(f"missing master {image}")
        entries.append(dict(image=str(image), target=dict(key=detail_key(kind), label=f"detail_normal {kind}"),
                            group="surfaces"))
    manifest = dict(name="Modern playing surfaces 4x", priority=0,
                    description="The field detail normals of Modern playing surfaces at 4x (fibres and blades).",
                    entries=entries)
    path = args.masters / "surfaces_pack_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    pack = tp.build_pack(path, [], args.out, disc_label="any disc built with modern_surfaces", overwrite=args.overwrite)
    for key, entry in pack["textures"].items():
        print(key, entry["asset"], entry["guest"], "x", entry["scale"], "; ".join(entry["notes"]) or "ok")
    print(f"{len(pack['textures'])} images -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
