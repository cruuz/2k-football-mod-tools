"""Publish original synthetic renders and metadata from the retail quality test.

Run test_nfl2k5_digit_sheet_quality.py with NUMBER_SHEET_QUALITY_ARTIFACTS set
first. Retail pixels and palettes are never copied to the published evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from PIL import Image
from mod_editor.core.nfl2k5_digit_preview import DecodedDigitTexture, render_digit_sheet_preview
from nfl_tset_png_import import MipLevel


def publish(source: Path, destination: Path) -> None:
    def read(name):
        path = source / name
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Quality metadata exceeds its bounded fixture size")
        return json.loads(path.read_text())

    rows = read("synthetic.json")
    retail = read("retail.json")
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for case in sorted({row["case"] for row in rows}):
        for label in ("before", "after"):
            textures = []
            for row in (row for row in rows if row["case"] == case):
                digit = int(row["selector"].rsplit(":", 1)[1])
                metadata = row[label]
                levels = []
                for mip in metadata["mips"]:
                    path = source / f"{case}_{digit}_{label}_mip{mip['level']}.png"
                    with Image.open(path) as image:
                        if list(image.size) != mip["size"] or max(image.size) > 64:
                            raise ValueError(f"Unexpected fixture dimensions: {path.name}")
                        rgba = image.convert("RGBA").tobytes()
                    if hashlib.sha256(rgba).hexdigest() != mip["rgba_sha256"]:
                        raise ValueError(f"Fixture pixels differ from encoded receipt: {path.name}")
                    levels.append(MipLevel(mip["level"], *mip["size"], rgba))
                textures.append((digit, DecodedDigitTexture(
                    metadata["format"], int(metadata["packed_format"], 16), metadata["alpha_bits"],
                    tuple(tuple(c) for c in metadata["palette_rgba"]), tuple(levels), metadata["span_sha256"],
                )))
            png = render_digit_sheet_preview(textures)
            name = f"{case}_{label}.png"
            (destination / name).write_bytes(png)
            artifacts[name] = hashlib.sha256(png).hexdigest()

    # Publish format/alpha/level facts and hashes, without retail palette data.
    for row in retail:
        del row["palette_rgba"]
    for row in rows:
        for label in ("before", "after"):
            del row[label]["palette_rgba"]
    evidence = {
        "schema": "number_sheet_quality_evidence/v1",
        "status": "EXPERIMENTAL / UNWITNESSED",
        "sampling_assumptions": "Straight-alpha bilinear, clamp to edge; size views use trilinear LOD log2(base height / cell height). No material, lighting, UV or camera trace.",
        "before_policy": "Pre-fix majority mips and generic bounded palette, after the same cell split as the corrected writer.",
        "after_policy": "Premultiplied area from base, one shared BGRA8888 palette, 16-entry minimum budget.",
        "retail": retail,
        "synthetic": rows,
        "render_png_sha256": artifacts,
    }
    (destination / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    publish(arguments.source, arguments.destination)
