#!/usr/bin/env python3
"""Inventory exact SCNE material/submesh ownership for 25 Crib electronics textures."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any

from nfl_scene_probe import ResourceRecord, decode_resource
from nfl_scne_inventory import parse_scene
from nfl_txtr import HEADER
import nfl_uniform_color_xiso_direct_patch as common


SCHEMA = "nfl2k5_crib_electronics_ownership/v1"
CATALOG_SCHEMA = "2k5_mod_studio_crib_catalog/v1"
SCNE_SCHEMA = "nfl2k5_scne_inventory/v1"
PACK_PATH = "vc_53450030/C"
PACK_SECTOR = 2_554_593
PACK_SIZE = 315_131_904
PACK_SHA256 = "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090"
OUTER_INDEX = 4248
OUTER_ID = "0xc61a9833"
OUTER_SIZE = 5_131_344
OUTER_PACK_OFFSET = 167_442_432

CANDIDATES: dict[str, set[int] | None] = {
    "air_hockey": set(range(7)),
    "dart_machine": {0, 1},
    "phone": set(range(5)),
    "room": {22, 31, 32, 39, 40},
    "soda_machine": {0, 1},
    "ticker": {0},
    "trivia_machine": {0, 1, 2},
}


class OwnershipError(ValueError):
    """The pinned catalogs, source XISO, or SCNE ownership failed closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OwnershipError(message)


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path, schema: str, label: str) -> tuple[Path, bytes, dict[str, Any]]:
    resolved = path.resolve(strict=True)
    payload = resolved.read_bytes()
    value = json.loads(payload)
    require(value.get("schema") == schema, f"{label} schema changed")
    return resolved, payload, value


def inventory(source_xiso: Path, catalog_path: Path,
              scne_path: Path) -> dict[str, Any]:
    catalog, catalog_payload, catalog_value = load_json(
        catalog_path, CATALOG_SCHEMA, "Crib catalog"
    )
    scne_report, scne_payload, scne_value = load_json(
        scne_path, SCNE_SCHEMA, "SCNE inventory"
    )
    selected = [
        item for item in catalog_value["assets"]
        if item.get("storage") == "scene_embedded"
        and item.get("outer_index") == OUTER_INDEX
        and item.get("scene_name") in CANDIDATES
        and (
            CANDIDATES[str(item["scene_name"])] is None
            or int(item["texture_index"]) in CANDIDATES[str(item["scene_name"])]
        )
    ]
    selected.sort(key=lambda item: (int(item["chunk_index"]), int(item["texture_index"])))
    require(len(selected) == 25 and len({item["selector"] for item in selected}) == 25,
            "electronics candidate set is no longer exactly 25 unique textures")
    scenes_by_chunk = {
        (int(item["outer_index"]), int(item["chunk_index"])): item
        for item in scne_value["scenes"]
        if int(item["outer_index"]) == OUTER_INDEX
    }

    source = source_xiso.resolve(strict=True)
    source_fd = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        require(os.fstat(source_fd).st_size == common.EXPECTED_XISO_SIZE and
                common.sha256_fd(source_fd) == common.EXPECTED_XISO_SHA256,
                "source must be the pinned untouched NFL 2K5 XISO")
        entries, directory = common.parse_xdvdfs(source_fd, common.EXPECTED_XISO_SIZE)
        pack = entries.get(PACK_PATH.casefold())
        require(pack is not None and (pack.sector, pack.size) == (PACK_SECTOR, PACK_SIZE),
                "pack C extent changed")
        assert pack is not None
        require(common.sha256_fd(source_fd, pack.byte_offset, pack.size) == PACK_SHA256,
                "pack C hash changed")

        parsed_by_chunk: dict[int, tuple[dict[str, Any], bytes, bytes, dict[str, Any]]] = {}
        resource_rows: list[dict[str, Any]] = []
        for chunk_index in sorted({int(item["chunk_index"]) for item in selected}):
            metadata = scenes_by_chunk.get((OUTER_INDEX, chunk_index))
            require(metadata is not None, f"SCNE metadata missing for chunk {chunk_index}")
            assert metadata is not None
            chunk_offset = int(metadata["chunk_offset"])
            stored_size = int(metadata["stored_size"])
            absolute = pack.byte_offset + OUTER_PACK_OFFSET + chunk_offset
            span = common.read_exact(source_fd, absolute, HEADER.size + stored_size)
            fields = HEADER.unpack_from(span)
            require(fields[0] == b"SCNE" and fields[1] == stored_size and
                    fields[2] == int(metadata["system_bytes"]) and fields[6:] == (0, 0),
                    f"SCNE wrapper changed for chunk {chunk_index}")
            record = ResourceRecord(
                outer_index=OUTER_INDEX,
                outer_id=OUTER_ID,
                outer_size=OUTER_SIZE,
                chunk_index=chunk_index,
                chunk_offset=chunk_offset,
                kind="SCNE",
                stored_size=stored_size,
                word_08=fields[2],
                word_0c=fields[3],
                word_10=fields[4],
                word_14=fields[5],
            )
            decoded, decode_detail = decode_resource(span, record)
            require(sha256(decoded) == metadata["decoded_sha256"],
                    f"decoded SCNE identity changed for chunk {chunk_index}")
            scene, _names, mappings, _sample = parse_scene(
                int(metadata["scene_index"]), record, decoded, {}
            )
            require(scene["name"] == metadata["name"],
                    f"SCNE name changed for chunk {chunk_index}")
            parsed_by_chunk[chunk_index] = (scene, span, decoded, decode_detail)
            resource_rows.append({
                "outer_index": OUTER_INDEX,
                "outer_id": OUTER_ID,
                "chunk_index": chunk_index,
                "chunk_offset": chunk_offset,
                "scene_index": int(metadata["scene_index"]),
                "scene_name": scene["name"],
                "xiso_absolute_span_offset": absolute,
                "span_size": len(span),
                "span_sha256": sha256(span),
                "stored_size": stored_size,
                "system_bytes": fields[2],
                "video_bytes": fields[3],
                "compression_magic": f"0x{fields[4]:08x}",
                "overlap_scratch_bytes": fields[5],
                "decoded_size": len(decoded),
                "decoded_sha256": sha256(decoded),
                "lz": decode_detail.get("lz"),
            })

        rows: list[dict[str, Any]] = []
        for item in selected:
            chunk_index = int(item["chunk_index"])
            texture_index = int(item["texture_index"])
            scene, _span, decoded, _detail = parsed_by_chunk[chunk_index]
            texture = scene["embedded_textures"][texture_index]
            require(
                texture["descriptor_offset"] == int(item["descriptor_offset"])
                and texture["format_name"] == item["format_name"]
                and texture["width"] == int(item["width"])
                and texture["height"] == int(item["height"])
                and texture.get("rgba_sha256") == item["rgba_sha256"],
                f"catalog/SCNE texture mismatch for {item['selector']}",
            )
            materials = [
                material for material in scene["materials"]
                if material["texture_index"] == texture_index
            ]
            require(materials and
                    sorted(material["name"] for material in materials) ==
                    sorted(item["material_names"]),
                    f"material ownership changed for {item['selector']}")
            material_indices = {int(material["index"]) for material in materials}
            submeshes = [
                submesh for submesh in scene["submeshes"]
                if int(submesh["material_index"]) in material_indices
            ]
            require(submeshes, f"no consuming submesh for {item['selector']}")
            consumers: list[dict[str, Any]] = []
            for submesh in submeshes:
                shape = scene["shapes"][int(submesh["shape_index"])]
                nodes = [
                    node for node in scene["nodes"]
                    if int(shape["index"]) in node["matching_shape_indices"]
                ]
                consumers.append({
                    "shape_index": int(shape["index"]),
                    "shape_name": shape["name"],
                    "shape_record_offset": int(shape["record_offset"]),
                    "shape_record_sha256": sha256(decoded[
                        int(shape["record_offset"]):int(shape["record_offset"]) + 0x100
                    ]),
                    "vertex_count": int(shape["vertex_count"]),
                    "vertex_streams": shape["vertex_streams"],
                    "shape_total_submeshes": int(shape["submesh_count"]),
                    "submesh_index": int(submesh["submesh_index"]),
                    "submesh_record_offset": int(submesh["record_offset"]),
                    "submesh_record_sha256": sha256(decoded[
                        int(submesh["record_offset"]):int(submesh["record_offset"]) + 0x80
                    ]),
                    "material_index": int(submesh["material_index"]),
                    "material_name": submesh["material_name"],
                    "command_offset": submesh["command_offset"],
                    "primary_command_word_count": int(submesh["primary_command_word_count"]),
                    "primitive_mode_counts": submesh["primitive_mode_counts"],
                    "index_element_count": int(submesh["index_element_count"]),
                    "draw_array_vertex_count": int(submesh["draw_array_vertex_count"]),
                    "maximum_vertex_index": submesh["maximum_vertex_index"],
                    "node_indices": [int(node["index"]) for node in nodes],
                    "node_names": [node["name"] for node in nodes],
                })
            rows.append({
                "selector": item["selector"],
                "asset_id": item["asset_id"],
                "scene_name": item["scene_name"],
                "chunk_index": chunk_index,
                "texture_index": texture_index,
                "descriptor_offset": int(texture["descriptor_offset"]),
                "descriptor_sha256": sha256(decoded[
                    int(texture["descriptor_offset"]):int(texture["descriptor_offset"]) + 0x20
                ]),
                "pixel_offset": int(texture["pixel_offset"]),
                "palette_offset": int(texture["palette_offset"]),
                "packed_format": f"0x{int(texture['packed_format']):08x}",
                "format_name": texture["format_name"],
                "width": int(texture["width"]),
                "height": int(texture["height"]),
                "mip_levels": int(texture["mip_levels"]),
                "rgba_sha256": texture["rgba_sha256"],
                "material_indices": sorted(material_indices),
                "material_names": [material["name"] for material in materials],
                "consumers": consumers,
                "exact_material_and_submesh_ownership": True,
                "writer_status": (
                    "bounded_png_to_copied_xiso_writer_proved_offline"
                    if item["selector"] == "crib_scene_texture:room:22"
                    else "preview_export_only_no_fixed_span_writer"
                ),
            })
        require(len(rows) == 25 and all(row["consumers"] for row in rows),
                "electronics ownership report is incomplete")
        return {
            "schema": SCHEMA,
            "source": {
                "xiso_path": str(source),
                "xiso_size": common.EXPECTED_XISO_SIZE,
                "xiso_sha256": common.EXPECTED_XISO_SHA256,
                "pack_path": PACK_PATH,
                "pack_sector": PACK_SECTOR,
                "pack_size": PACK_SIZE,
                "pack_sha256": PACK_SHA256,
                "opened_read_only": True,
                "modified": False,
            },
            "catalog": {
                "path": str(catalog),
                "size": len(catalog_payload),
                "sha256": sha256(catalog_payload),
            },
            "scne_inventory": {
                "path": str(scne_report),
                "size": len(scne_payload),
                "sha256": sha256(scne_payload),
            },
            "selection": {
                "rule": "electronics/console-like texture-only reskin candidates",
                "scene_texture_indices": {
                    key: ("all" if value is None else sorted(value))
                    for key, value in CANDIDATES.items()
                },
                "texture_count": len(rows),
                "scene_resource_count": len(resource_rows),
            },
            "resources": resource_rows,
            "textures": rows,
            "claims": {
                "all_25_have_exact_material_and_submesh_consumers": True,
                "bar_monitor_has_safe_offline_fixed_span_writer": True,
                "runtime_visibility_proved": False,
                "general_model_import_proved": False,
                "retail_bytes_embedded_in_report": False,
            },
        }
    finally:
        os.close(source_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument(
        "--catalog", type=Path,
        default=Path("mod_editor/data/nfl2k5_crib_catalog.v1.json"),
    )
    parser.add_argument(
        "--scne-inventory", type=Path,
        default=Path("reports/assets/nfl2k5_scne_inventory.json"),
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = inventory(args.source_xiso, args.catalog, args.scne_inventory)
        output = args.output.resolve(strict=False)
        require(output.parent.resolve(strict=True) == output.parent and not output.exists(),
                "output parent must exist and output must be new")
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        descriptor = os.open(
            output,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY |
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
            0o644,
        )
        success = False
        try:
            cursor = 0
            while cursor < len(payload):
                written = os.write(descriptor, payload[cursor:])
                require(written > 0, "short ownership report write")
                cursor += written
            os.fsync(descriptor)
            success = True
        finally:
            os.close(descriptor)
            if not success and output.exists():
                output.unlink()
    except (OSError, ValueError, KeyError, TypeError, struct.error,
            json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "output": str(output),
        "sha256": sha256(payload),
        "textures": len(report["textures"]),
        "resources": len(report["resources"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["CANDIDATES", "OwnershipError", "SCHEMA", "inventory"]
