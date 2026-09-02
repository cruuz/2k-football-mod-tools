#!/usr/bin/env python3
"""Prepare/finalize a hash-bound headless visual proof of the shell candidate."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
from typing import Any, Iterable

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_crest_wrap_patch as p  # noqa: E402


SCHEMA = "apf2k8_helmet_shell_candidate_visual_proof/v1"
EXPECTED_SCNE_SHA256 = "ef04ef4418e4df555d9418db2f6083c7852802428aae0a15dbf81518bff3b5ef"
EXPECTED_MASK_SHA256 = "4913aa6cf62fe6f96a913001ed5ad9d0356a109412e3f1b432fc0fd81eb5750a"
EXPECTED_MATERIAL_SHA256 = "097220afe28be2737539052eb4135f183b49c4c4e0ea7a1d352c5af085dd7d5e"
VIEW_NAMES = ("side-right", "side-left", "front-crown", "rear", "top")
LOW_VIEW_NAME = "lod-low-side-right"


class ProofError(RuntimeError):
    pass


def require(value: object, message: str) -> None:
    if not value:
        raise ProofError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triangles(indices: Iterable[int]) -> list[tuple[int, int, int]]:
    return p._triangles(list(indices))


def compact(
    payload: bytes,
    spec: p.LodSpec,
    faces: list[tuple[int, int, int]],
    *,
    uv: bool,
) -> dict[str, object]:
    used = sorted({index for face in faces for index in face})
    remap = {source: target for target, source in enumerate(used)}
    output: dict[str, object] = {
        "positions_cm": [list(p._decode_position(payload, spec, index)) for index in used],
        "normals": [
            list(p._unit(p._decode_vec3(payload, spec.stream_start + index * p.STRIDE + 8)))
            for index in used
        ],
        "source_vertex_indices": used,
        "triangles": [[remap[index] for index in face] for face in faces],
    }
    if uv:
        values = [p._uv(payload, spec, index) for index in used]
        output["uv_d3d"] = [list(value) for value in values]
        output["uv_blender"] = [[value[0], 1.0 - value[1]] for value in values]
    return output


def bounds(points: Iterable[Iterable[float]]) -> dict[str, list[float]]:
    rows = [tuple(point) for point in points]
    return {
        "minimum": [min(row[axis] for row in rows) for axis in range(3)],
        "maximum": [max(row[axis] for row in rows) for axis in range(3)],
    }


def prepare(scne: Path, mask: Path, material: Path, destination: Path) -> None:
    require(scne.is_file() and mask.is_file() and material.is_file(), "proof input is missing")
    require(sha256(scne) == EXPECTED_SCNE_SHA256, "candidate SCNE hash differs")
    require(sha256(mask) == EXPECTED_MASK_SHA256, "crest mask hash differs")
    require(sha256(material) == EXPECTED_MATERIAL_SHA256, "crest material hash differs")
    require(not destination.exists(), f"proof destination already exists: {destination}")

    payload = scne.read_bytes()
    lod_geometry: dict[str, dict[str, object]] = {}
    expected_counts = {
        "helmet_hi": (2464, 516, 322),
        "helmet_lo": (432, 156, 112),
    }
    for spec in p.LODS:
        indices = p._indices(payload, spec)
        shell_faces = triangles(indices[
            spec.shell_index_start : spec.shell_index_start + spec.shell_index_count
        ])
        carrier_faces = triangles(indices[
            spec.carrier_index_start : spec.carrier_index_start + spec.carrier_index_count
        ])
        shell_count, carrier_count, vertex_count = expected_counts[spec.node_name]
        require(len(shell_faces) == shell_count, f"{spec.node_name} shell triangle count differs")
        require(len(carrier_faces) == carrier_count, f"{spec.node_name} carrier triangle count differs")
        shell = compact(payload, spec, shell_faces, uv=False)
        carrier = compact(payload, spec, carrier_faces, uv=True)
        require(len(carrier["positions_cm"]) == vertex_count, f"{spec.node_name} carrier vertex count differs")
        lod_geometry[spec.node_name] = {"shell": shell, "carrier": carrier}

    with Image.open(mask) as image:
        rgba = image.convert("RGBA")
        require(rgba.size == (512, 512), "mask dimensions differ")
        mask_pixels = list(rgba.getdata())
    active = [
        (number % 512, number // 512)
        for number, pixel in enumerate(mask_pixels)
        if pixel[:3] != (0, 0, 0)
    ]
    require(len(active) == 42_800, "mask active census differs")
    active_bbox = [
        min(point[0] for point in active), min(point[1] for point in active),
        max(point[0] for point in active), max(point[1] for point in active),
    ]
    require(active_bbox == [64, 122, 447, 389], "mask active bbox differs")
    with Image.open(material) as image:
        material_rgba = image.convert("RGBA")
        require(material_rgba.size == (512, 512), "material dimensions differ")
        material_pixels = list(material_rgba.getdata())
    require(all(pixel[3] == 255 for pixel in material_pixels), "material is not opaque")
    material_counts = Counter(material_pixels)
    require(material_counts[(0, 76, 84, 255)] == 219_344, "shell background census differs")

    destination.mkdir(mode=0o700)
    geometry_path = destination / "helmet-shell-candidate.geometry.json"
    mask_path = destination / "helmet-shell-candidate-mask.png"
    material_path = destination / "helmet-shell-candidate-material.png"
    receipt_path = destination / "helmet-shell-candidate-proof.json"
    geometry = {"lods": lod_geometry}
    geometry_path.write_text(
        json.dumps(geometry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copyfile(mask, mask_path)
    shutil.copyfile(material, material_path)
    receipt = {
        "schema": SCHEMA,
        "claim": "headless_static_asset_space_shell_native_helmet_visualization",
        "source": {"candidate_scne_sha256": EXPECTED_SCNE_SHA256},
        "geometry": {
            "file": geometry_path.name,
            "sha256": sha256(geometry_path),
            "lods": {
                name: {
                    "shell_triangle_count": len(group["shell"]["triangles"]),
                    "carrier_triangle_count": len(group["carrier"]["triangles"]),
                    "carrier_vertex_count": len(group["carrier"]["positions_cm"]),
                    "carrier_bounds_cm": bounds(group["carrier"]["positions_cm"]),
                }
                for name, group in lod_geometry.items()
            },
        },
        "crest": {
            "mask": {
                "file": mask_path.name,
                "sha256": sha256(mask_path),
                "active_texel_count": len(active),
                "active_bbox": active_bbox,
            },
            "material": {
                "file": material_path.name,
                "sha256": sha256(material_path),
                "opaque": True,
                "shell_background_texel_count": material_counts[(0, 76, 84, 255)],
                "non_shell_art_texel_count": 512 * 512 - material_counts[(0, 76, 84, 255)],
                "unique_rgba_count": len(material_counts),
            },
        },
        "render_contract": {
            "background": True,
            "centimeters_to_meters": 0.01,
            "carrier_visual_normal_bias_m": 0.0,
            "engine": "EEVEE",
            "antialiasing": "EEVEE temporal antialiasing plus Gaussian pixel filter",
            "texture_interpolation": "Linear",
            "no_emulator": True,
            "resolution": [512, 512],
            "views": list(VIEW_NAMES),
            "low_lod_parity_view": LOW_VIEW_NAME,
        },
    }
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "prepared": True,
        "proof": str(receipt_path),
        "candidate_scne_sha256": EXPECTED_SCNE_SHA256,
        "active_texels": len(active),
        "active_bbox": active_bbox,
        "material_non_shell_texels": 512 * 512 - material_counts[(0, 76, 84, 255)],
    }, indent=2, sort_keys=True))


def finalize(directory: Path) -> None:
    receipt_path = directory / "helmet-shell-candidate-proof.json"
    stage_path = directory / "helmet-shell-candidate-blender-stage.json"
    require(receipt_path.is_file() and stage_path.is_file(), "render stage is incomplete")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt.get("schema") == SCHEMA, "proof receipt schema differs")
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    require(stage.get("source_scne_sha256") == EXPECTED_SCNE_SHA256, "stage source hash differs")
    rows: dict[str, object] = {}
    images: list[Image.Image] = []
    for view in VIEW_NAMES:
        path = directory / f"helmet-shell-candidate-{view}.png"
        require(path.is_file(), f"missing rendered view {view}")
        with Image.open(path) as image:
            image.load()
            require(image.size == (512, 512), f"{view} dimensions differ")
            rgba = image.convert("RGBA")
            pixels = list(rgba.getdata())
            counts = Counter(pixels)
            require(len(counts) > 16, f"{view} render is visually empty")
            background, background_count = counts.most_common(1)[0]
            non_background = 512 * 512 - background_count
            require(non_background > 8_000, f"{view} helmet coverage is too small")
            rows[view] = {
                "file": path.name,
                "sha256": sha256(path),
                "unique_rgba_count": len(counts),
                "dominant_background_rgba": list(background),
                "non_background_pixel_count": non_background,
            }
            images.append(rgba.copy())

    low_path = directory / f"helmet-shell-candidate-{LOW_VIEW_NAME}.png"
    require(low_path.is_file(), "missing low-LOD parity render")
    with Image.open(low_path) as image:
        image.load()
        require(image.size == (512, 512), "low-LOD dimensions differ")
        low_rgba = image.convert("RGBA")
        low_counts = Counter(low_rgba.getdata())
        require(len(low_counts) > 16, "low-LOD render is visually empty")
        low_background_count = low_counts.most_common(1)[0][1]
        require(512 * 512 - low_background_count > 8_000, "low-LOD helmet coverage is too small")
        rows[LOW_VIEW_NAME] = {
            "file": low_path.name,
            "sha256": sha256(low_path),
            "unique_rgba_count": len(low_counts),
            "non_background_pixel_count": 512 * 512 - low_background_count,
        }
        images.append(low_rgba.copy())

    sheet = Image.new("RGBA", (1024, 1536), (3, 5, 8, 255))
    draw = ImageDraw.Draw(sheet)
    for number, (name, image) in enumerate(
        zip((*VIEW_NAMES, LOW_VIEW_NAME), images)
    ):
        x_value, y_value = (number % 2) * 512, (number // 2) * 512
        sheet.alpha_composite(image, (x_value, y_value))
        draw.rectangle((x_value + 8, y_value + 8, x_value + 190, y_value + 34), fill=(3, 5, 8, 220))
        draw.text((x_value + 15, y_value + 14), name.upper(), fill=(255, 255, 255, 255))
    sheet_path = directory / "helmet-shell-candidate-contact-sheet.png"
    sheet.save(sheet_path, format="PNG", optimize=False)
    final = {
        **receipt,
        "render": {
            "verified": True,
            "stage_sha256": sha256(stage_path),
            "blend_sha256": sha256(directory / "helmet-shell-candidate.blend"),
            "contact_sheet": {"file": sheet_path.name, "sha256": sha256(sheet_path)},
            "views": rows,
        },
    }
    final_path = directory / "helmet-shell-candidate-proof.final.json"
    final_path.write_text(
        json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "finalized": True,
        "contact_sheet": str(sheet_path),
        "proof": str(final_path),
        "view_count": len(rows),
    }, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("scne", type=Path)
    prepare_parser.add_argument("mask", type=Path)
    prepare_parser.add_argument("material", type=Path)
    prepare_parser.add_argument("destination", type=Path)
    finalize_parser = commands.add_parser("finalize")
    finalize_parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.scne, args.mask, args.material, args.destination)
    else:
        finalize(args.directory)


if __name__ == "__main__":
    main()
