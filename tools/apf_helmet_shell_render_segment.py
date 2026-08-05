#!/usr/bin/env python3
"""Cheap deterministic silhouette/parity gates for the helmet proof renders."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def require(value: object, message: str) -> None:
    if not value:
        raise RuntimeError(f"helmet render segmentation: {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image.load()
        require(image.size == (512, 512), f"dimensions differ: {path.name}")
        return np.asarray(image.convert("RGBA"), dtype=np.uint8)


def metrics(mask: np.ndarray) -> dict[str, object]:
    rows, columns = np.nonzero(mask)
    require(len(columns) > 0, "segmentation is empty")
    return {
        "bbox_xyxy": [
            int(columns.min()), int(rows.min()), int(columns.max()), int(rows.max()),
        ],
        "centroid_xy": [float(columns.mean()), float(rows.mean())],
        "pixel_count": int(len(columns)),
    }


def parity(first: np.ndarray, second: np.ndarray) -> dict[str, object]:
    intersection = int(np.logical_and(first, second).sum())
    union = int(np.logical_or(first, second).sum())
    return {
        "intersection_over_union": intersection / union,
        "xor_pixel_count": int(np.logical_xor(first, second).sum()),
        "area_fraction_difference": abs(int(first.sum()) - int(second.sum())) / int(first.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory
    paths = {
        "high_right": root / "helmet-shell-candidate-side-right.png",
        "high_left": root / "helmet-shell-candidate-side-left.png",
        "low_right": root / "helmet-shell-candidate-lod-low-side-right.png",
    }
    images = {name: load(path) for name, path in paths.items()}
    # Emitted shell/background have red near zero; silver/white wing weights do not.
    art = {name: image[:, :, 0] > 32 for name, image in images.items()}
    helmet = {
        name: (image[:, :, 0] > 8) | (image[:, :, 1] > 20) | (image[:, :, 2] > 20)
        for name, image in images.items()
    }
    mirrored_left = np.fliplr(art["high_left"])
    high_low = parity(art["high_right"], art["low_right"])
    bilateral = parity(art["high_right"], mirrored_left)
    high_art = metrics(art["high_right"])
    low_art = metrics(art["low_right"])
    high_helmet = metrics(helmet["high_right"])
    art_bbox = high_art["bbox_xyxy"]
    helmet_bbox = high_helmet["bbox_xyxy"]
    art_width = art_bbox[2] - art_bbox[0] + 1
    art_height = art_bbox[3] - art_bbox[1] + 1
    helmet_width = helmet_bbox[2] - helmet_bbox[0] + 1
    require(art_width >= 360, f"wing is too short in side render: {art_width}px")
    require(art_height >= 140, f"wing is too shallow in side render: {art_height}px")
    require(art_width / helmet_width >= 0.85, "wing does not span the helmet shell")
    require(high_low["intersection_over_union"] >= 0.99, "high/low wing silhouette pops")
    require(bilateral["intersection_over_union"] >= 0.995, "mirrored wing silhouettes differ")
    report = {
        "art_threshold": "rendered red channel > 32",
        "bilateral_parity": bilateral,
        "high_low_parity": high_low,
        "high_right": {"art": high_art, "helmet": high_helmet},
        "inputs": {
            name: {"file": path.name, "sha256": sha256(path)}
            for name, path in paths.items()
        },
        "low_right": {"art": low_art, "helmet": metrics(helmet["low_right"])},
        "schema": "apf2k8_helmet_shell_render_segment/v1",
        "verified": True,
    }
    output = root / "helmet-shell-candidate-segmentation.json"
    require(not output.exists(), f"refusing to overwrite {output}")
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
