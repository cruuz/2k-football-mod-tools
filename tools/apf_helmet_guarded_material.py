#!/usr/bin/env python3
"""Derive the exact opaque review material from the guarded Eagles mask."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_eagles_crest_region_mask as region  # noqa: E402
from nfl_txtr import encode_rgba_png  # noqa: E402


MASK_PNG_SHA256 = "4913aa6cf62fe6f96a913001ed5ad9d0356a109412e3f1b432fc0fd81eb5750a"
MASK_RGBA_SHA256 = "cf937ff797e4e5ae94b5c456babf298fa20436716b6ef2b708faac70b293d40e"


class MaterialError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise MaterialError(message)


def build(mask: Path) -> tuple[bytes, dict[str, object]]:
    payload = mask.read_bytes()
    require(hashlib.sha256(payload).hexdigest() == MASK_PNG_SHA256, "mask PNG hash drift")
    with Image.open(mask) as image:
        rgba = image.convert("RGBA")
        require(rgba.size == (512, 512), "mask dimensions differ")
        mask_rgba = rgba.tobytes()
    require(hashlib.sha256(mask_rgba).hexdigest() == MASK_RGBA_SHA256, "mask RGBA hash drift")
    material = bytearray(512 * 512 * 4)
    active = 0
    for offset in range(0, len(mask_rgba), 4):
        red, green, blue, alpha = mask_rgba[offset : offset + 4]
        require(blue == 0 and alpha == region.MASK_ALPHA, "mask palette contract differs")
        require(red + green <= 255, "mask weights exceed one coverage unit")
        if red or green:
            active += 1
        material[offset : offset + 4] = bytes(region._material_pixel(red, green))
    require(active == 42_800, "guarded active census differs")
    material_rgba = bytes(material)
    material_png = encode_rgba_png(512, 512, material_rgba)
    counts = Counter(
        tuple(material_rgba[offset : offset + 4])
        for offset in range(0, len(material_rgba), 4)
    )
    require(counts[region.MATERIAL_SHELL] == 219_344, "guarded shell census differs")
    return material_png, {
        "active_art_texels": active,
        "height": 512,
        "mask_png_sha256": MASK_PNG_SHA256,
        "mask_rgba_sha256": MASK_RGBA_SHA256,
        "material_png_sha256": hashlib.sha256(material_png).hexdigest(),
        "material_rgba_sha256": hashlib.sha256(material_rgba).hexdigest(),
        "opaque": True,
        "schema": "apf2k8_helmet_guarded_material/v1",
        "shell_background_texels": counts[region.MATERIAL_SHELL],
        "unique_rgba_count": len(counts),
        "width": 512,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mask", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), f"output exists: {args.output}")
    require(not args.receipt.exists(), f"receipt exists: {args.receipt}")
    payload, report = build(args.mask)
    args.output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    args.receipt.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        with args.output.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        with args.receipt.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        args.output.unlink(missing_ok=True)
        args.receipt.unlink(missing_ok=True)
        raise
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
