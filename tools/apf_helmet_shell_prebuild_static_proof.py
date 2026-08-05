#!/usr/bin/env python3
"""Render a cheap headless prebuild proof on APF's exact helmet geometry.

The tool reads a pristine user-owned APF ``0A``, simulates only the v24
whole-shell material-route fields in memory, and renders an external 512x512
semantic atlas with the deterministic software renderer.  It does not build a
game volume, modify the source, launch an emulator, or claim runtime behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
for search_root in (ROOT, ROOT / "tools"):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import apf_helmet_shell_static_proof as core  # noqa: E402
import apf_inner  # noqa: E402
import apf_outer  # noqa: E402


SCHEMA = "apf2k8_helmet_shell_prebuild_static_proof/v1"
CLAIM = "headless_prebuild_static_asset_space_whole_shell_visualization_only"
MAX_PNG_BYTES = 64 * 1024 * 1024


class PrebuildProofError(ValueError):
    """The private atlas or pristine source left the bounded proof contract."""


def require(value: object, message: str) -> None:
    if not value:
        raise PrebuildProofError(message)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return core.sha256_file(path)


def load_semantic_png(path: Path) -> tuple[bytes, Mapping[str, object]]:
    """Read one exact 512x512 APF red/green semantic atlas."""

    source = Path(os.path.abspath(os.fspath(Path(path).expanduser())))
    try:
        info = source.lstat()
    except OSError as exc:
        raise PrebuildProofError(f"semantic PNG cannot be read: {exc}") from exc
    require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        "semantic PNG must be a regular non-symlink file",
    )
    require(info.st_size <= MAX_PNG_BYTES, "semantic PNG exceeds 64 MiB")
    try:
        with Image.open(source) as opened:
            opened.load()
            require(opened.format == "PNG", "semantic atlas must be a PNG")
            require(opened.size == (core.WIDTH, core.HEIGHT),
                    "semantic atlas must be exactly 512x512")
            rgba = opened.convert("RGBA").tobytes()
    except PrebuildProofError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow format exceptions vary
        raise PrebuildProofError(f"semantic PNG decode failed: {exc}") from exc
    try:
        atlas_metrics = core._validate_atlas(rgba)
    except core.ProofError as exc:
        raise PrebuildProofError(str(exc)) from exc
    return rgba, {
        "file_sha256": _sha256_file(source),
        "decoded_rgba_sha256": _sha256_bytes(rgba),
        "file_size": info.st_size,
        "metrics": atlas_metrics,
    }


def simulate_v24_route(system: bytes) -> tuple[bytes, Mapping[str, object]]:
    """Apply only the two exact v24 route field families in memory."""

    require(len(system) == core.HELMET_SYSTEM_LENGTH,
            "helmet system length differs from the exact v24 source contract")
    routed = bytearray(system)
    rows: dict[str, object] = {}
    changed_offsets: set[int] = set()
    for spec in core.LODS:
        material_offset = (
            spec.draw_record_offset
            + core.SHELL_DRAW * core.DRAW_RECORD_SIZE
            + 0x20
        )
        before_material = struct.unpack_from(">I", routed, material_offset)[0]
        before_material_bytes = bytes(routed[material_offset : material_offset + 4])
        struct.pack_into(">I", routed, material_offset, core.CREST_MATERIAL)
        after_material_bytes = bytes(routed[material_offset : material_offset + 4])
        changed_offsets.update(
            material_offset + index
            for index, (before, after) in enumerate(
                zip(before_material_bytes, after_material_bytes, strict=True)
            )
            if before != after
        )

        overlay_start = spec.index_offset + spec.overlay_index_start * 2
        overlay_length = spec.overlay_index_count * 2
        before_overlay = bytes(routed[overlay_start : overlay_start + overlay_length])
        after_overlay = (
            struct.pack(">H", spec.overlay_vertex_start)
            * spec.overlay_index_count
        )
        routed[overlay_start : overlay_start + overlay_length] = after_overlay
        changed_offsets.update(
            overlay_start + index
            for index, (before, after) in enumerate(
                zip(before_overlay, after_overlay, strict=True)
            )
            if before != after
        )
        rows[spec.name] = {
            "draw_1_material_offset": material_offset,
            "draw_1_material_before": before_material,
            "draw_1_material_after": core.CREST_MATERIAL,
            "draw_2_index_offset": overlay_start,
            "draw_2_index_count": spec.overlay_index_count,
            "draw_2_before_sha256": _sha256_bytes(before_overlay),
            "draw_2_after_sha256": _sha256_bytes(after_overlay),
            "draw_2_after_degenerate_vertex": spec.overlay_vertex_start,
        }
    routed_bytes = bytes(routed)
    geometries = [core._decode_geometry(routed_bytes, spec) for spec in core.LODS]
    require(all(item.overlay_triangle_count == 0 for item in geometries),
            "simulated v24 legacy overlays still contain triangles")
    return routed_bytes, {
        "schema": "apf2k8_helmet_shell_route_simulation/v24",
        "source_system_sha256": _sha256_bytes(system),
        "simulated_system_sha256": _sha256_bytes(routed_bytes),
        "changed_byte_count": len(changed_offsets),
        "changed_byte_offsets_sha256": _sha256_bytes(
            b"".join(struct.pack(">I", value) for value in sorted(changed_offsets))
        ),
        "lods": rows,
    }


def prepare(
    input_0a: Path,
    semantic_png: Path,
    output: Path,
    *,
    palette: tuple[int, int, int],
) -> dict[str, object]:
    """Create one exclusive static proof directory without a copied volume."""

    source = Path(os.path.abspath(os.fspath(Path(input_0a).expanduser())))
    destination = Path(os.path.abspath(os.fspath(Path(output).expanduser())))
    require(source.is_file() and not source.is_symlink(),
            "input 0A must be a regular non-symlink file")
    require(not destination.exists() and not destination.is_symlink(),
            f"refusing to overwrite proof destination: {destination}")
    require(destination.parent.is_dir(), "proof parent directory does not exist")
    require(all(type(value) is int and 0 <= value <= 0xFFFFFFFF for value in palette),
            "palette values must be exact ARGB32 integers")

    source_sha256_before = _sha256_file(source)
    semantic_rgba, semantic_receipt = load_semantic_png(semantic_png)
    try:
        archive = apf_outer.parse_archive(source)
    except apf_outer.FormatError as exc:
        raise PrebuildProofError(f"could not parse input archive: {exc}") from exc
    try:
        with apf_inner.ArchiveReader(archive) as reader:
            system, helmet_receipt = core._read_helmet_system(archive, reader)
    except (apf_inner.FormatError, core.ProofError) as exc:
        raise PrebuildProofError(f"could not read exact helmet geometry: {exc}") from exc
    routed, route_receipt = simulate_v24_route(system)
    geometries = [core._decode_geometry(routed, spec) for spec in core.LODS]
    semantic_atlas = np.frombuffer(semantic_rgba, dtype=np.uint8).reshape(
        (core.HEIGHT, core.WIDTH, 4)
    )
    material_atlas = core.colorize_atlas(semantic_rgba, *palette)

    stage = Path(tempfile.mkdtemp(
        prefix=f".{destination.name}.stage-", dir=destination.parent
    ))
    try:
        frames = {name: core._frame(name, geometries) for name in core.VIEW_NAMES}
        renders: dict[str, dict[str, core.Render]] = {
            geometry.spec.name: {} for geometry in geometries
        }
        render_rows: dict[str, dict[str, Any]] = {}
        for geometry in geometries:
            row: dict[str, Any] = {}
            for view_name in core.VIEW_NAMES:
                rendered = core.rasterize(
                    geometry,
                    geometry.faces,
                    semantic_atlas,
                    material_atlas,
                    frames[view_name],
                )
                renders[geometry.spec.name][view_name] = rendered
                path = stage / f"helmet-shell-{geometry.spec.name}-{view_name}.png"
                core._save_png(path, rendered.image)
                row[view_name] = {
                    "file": path.name,
                    "sha256": _sha256_file(path),
                    "shell_pixel_count": int(rendered.shell.sum()),
                    "active_art_pixel_count": int(rendered.active.sum()),
                }
            require(all(render.active.any() for render in renders[geometry.spec.name].values()),
                    f"{geometry.spec.name} has a view with no active art")
            contact = stage / f"helmet-shell-{geometry.spec.name}-contact-sheet.png"
            core._contact_sheet(
                [(name, stage / row[name]["file"]) for name in core.VIEW_NAMES],
                contact,
            )
            row["contact_sheet"] = {
                "file": contact.name,
                "sha256": _sha256_file(contact),
            }
            render_rows[geometry.spec.name] = row

        geometry_rows: dict[str, object] = {}
        for geometry in geometries:
            geometry_rows[geometry.spec.name] = {
                "draw_1_material": geometry.material_before_route,
                "draw_2_triangle_count": geometry.overlay_triangle_count,
                "exterior_triangle_count": len(geometry.faces),
                "triangles_per_side": {
                    side: len(faces) for side, faces in geometry.side_faces.items()
                },
                "surface_coverage": {
                    side: core.sampled_surface_metrics(
                        geometry, geometry.side_faces[side], semantic_atlas
                    )
                    for side in ("right", "left")
                },
                "x_zero_seam": core.seam_metrics(geometry, semantic_atlas),
            }
        source_sha256_after = _sha256_file(source)
        require(source_sha256_after == source_sha256_before,
                "input 0A changed during static proof")
        result: dict[str, object] = {
            "schema": SCHEMA,
            "claim": CLAIM,
            "proof_eligible_for_runtime_or_visual_quality_claim": False,
            "limitations": [
                "prebuild static asset-space software rendering only",
                "v24 route fields are simulated in memory; no game volume is built",
                "no emulator, gameplay, original-hardware, or runtime-consumer proof",
                "visual quality requires a separate human visual review",
            ],
            "source": {
                "input_0a_sha256": source_sha256_before,
                "input_0a_size": source.stat().st_size,
                "opened_read_only": True,
                "source_modified": False,
                "helmet": helmet_receipt,
            },
            "semantic_atlas": semantic_receipt,
            "palette": {
                "shell_argb": f"{palette[0]:08X}",
                "red_region_argb": f"{palette[1]:08X}",
                "green_region_argb": f"{palette[2]:08X}",
            },
            "route_simulation": route_receipt,
            "geometry": geometry_rows,
            "metrics": {
                "bilateral_screen_space": {
                    geometry.spec.name: core.mask_metrics(
                        renders[geometry.spec.name]["side-right"],
                        renders[geometry.spec.name]["side-left"],
                    )
                    for geometry in geometries
                },
                "high_low_screen_space": {
                    name: core.mask_metrics(
                        renders["helmet_hi"][name], renders["helmet_lo"][name]
                    )
                    for name in core.VIEW_NAMES
                },
            },
            "render_contract": {
                "renderer": "deterministic_numpy_orthographic_triangle_zbuffer_v1",
                "resolution": [core.WIDTH, core.HEIGHT],
                "views": list(core.VIEW_NAMES),
                "exact_source_geometry": True,
                "v24_route_fields_simulated_only": True,
                "no_copied_game_volume": True,
                "no_gui": True,
                "no_emulator": True,
            },
            "renders": render_rows,
        }
        (stage / "helmet-shell-prebuild-static-proof.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        stage.rename(destination)
        return result
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-0a", required=True, type=Path)
    parser.add_argument("--semantic-png", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shell-argb", required=True, type=core._parse_argb)
    parser.add_argument("--red-region-argb", required=True, type=core._parse_argb)
    parser.add_argument("--green-region-argb", required=True, type=core._parse_argb)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = prepare(
            args.input_0a,
            args.semantic_png,
            args.output,
            palette=(
                args.shell_argb,
                args.red_region_argb,
                args.green_region_argb,
            ),
        )
    except (OSError, PrebuildProofError, core.ProofError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "ready": True,
        "claim": result["claim"],
        "output": str(args.output.resolve()),
        "receipt": str(
            (args.output / "helmet-shell-prebuild-static-proof.json").resolve()
        ),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
