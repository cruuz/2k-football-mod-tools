#!/usr/bin/env python3
"""Independently verify the APF dual-LOD helmet material-route copy.

This verifier imports neither dual-LOD writer nor any writer-owned helper.  It
reuses only the prior independent volume/IFF verifier's read-only primitives,
then independently validates both SCNE node routes and the dual-LOD receipt.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_shell_material_route_verify as common  # noqa: E402
import apf_scene  # noqa: E402


PATCH_SCHEMA = "apf2k8_helmet_dual_lod_shell_material_route_patch/v1"
VERIFY_SCHEMA = "apf2k8_helmet_dual_lod_shell_material_route_verify/v1"
OPERATION = "route_helmet_hi_and_lo_draw_1_material_slot_1_to_2"
OUTPUT_OUTER_SHA256 = (
    "01ebbe682019310bc24b138d205e2e3e9058dd7e59b0efbb5ed1c16369fa26f8"
)
OUTPUT_SYSTEM_SHA256 = (
    "4eec61ad512d26c6b68694d6d1564b5e9af92fcd41e52ca5de729cd1455f3178"
)
DRAW_RECORD_INDEX = 1
DRAW_RECORD_SIZE = 0x30
ROUTES = (
    (0, "helmet_hi", 0x000099C0, 0x00009A10, 0x00009A13),
    (32, "helmet_lo", 0x000CCA80, 0x000CCAD0, 0x000CCAD3),
)
CHANGED_BYTE_OFFSETS = [route[4] for route in ROUTES]
CHANGED_BYTE_OFFSET_TEXT = [f"0x{offset:08x}" for offset in CHANGED_BYTE_OFFSETS]
VerifyError = common.VerifyError
require = common.require


def _semantic_material_slots(system: bytes, label: str) -> dict[str, int]:
    try:
        scene = apf_scene.parse_scene_system_part(
            system,
            outer_index=common.OUTER_INDEX,
            inner_index=common.INNER_INDEX,
            capture_geometry=False,
        )
    except apf_scene.SceneError as exc:
        raise VerifyError(f"{label} SCNE semantic parse failed: {exc}") from exc
    nodes = scene.get("nodes")
    require(isinstance(nodes, list), f"{label} helmet node inventory missing")
    result: dict[str, int] = {}
    for node_index, node_name, draw_start, field_offset, _changed_offset in ROUTES:
        require(len(nodes) > node_index, f"{label} {node_name} node missing")
        node = nodes[node_index]
        derived = int(node.get("draw_record_offset", -1)) + DRAW_RECORD_INDEX * DRAW_RECORD_SIZE + 0x20
        require(
            scene.get("root_name") == common.INNER_NAME
            and node.get("name") == node_name
            and node.get("draw_record_offset") == draw_start
            and derived == field_offset,
            f"{label} {node_name} draw-1 field route differs",
        )
        result[node_name] = struct.unpack_from(">I", system, derived)[0]
    return result


def _expected_receipt_routes() -> list[dict[str, Any]]:
    return [
        {
            "draw_record_index": DRAW_RECORD_INDEX,
            "draw_record_start": f"0x{draw_start:08x}",
            "material_field_byte_offset": f"0x{field_offset:08x}",
            "new_material_slot": 2,
            "node_index": node_index,
            "node_name": node_name,
            "old_material_slot": 1,
        }
        for node_index, node_name, draw_start, field_offset, _changed_offset in ROUTES
    ]


def _validate_receipt(
    receipt: dict[str, Any],
    source_sha: str,
    output_sha: str,
    prefix_sha: str,
    suffix_sha: str,
) -> None:
    require(receipt.get("schema") == PATCH_SCHEMA, "writer receipt schema differs")
    require(receipt.get("operation") == OPERATION, "writer receipt operation differs")
    source = receipt.get("source")
    result = receipt.get("result")
    target = receipt.get("target")
    preservation = receipt.get("preservation")
    claims = receipt.get("claim_flags")
    require(isinstance(source, dict) and isinstance(result, dict), "writer receipt source/result missing")
    require(isinstance(target, dict) and isinstance(preservation, dict), "writer receipt target/proof missing")
    require(isinstance(claims, dict), "writer receipt claims missing")
    require(
        source.get("source_volume_sha256") == source_sha
        and source.get("outer_entry_sha256") == common.SOURCE_OUTER_SHA256
        and source.get("source_scne_sha256") == common.SOURCE_SYSTEM_SHA256,
        "writer receipt source hashes differ",
    )
    require(
        result.get("output_volume_sha256") == output_sha
        and result.get("outer_entry_sha256") == OUTPUT_OUTER_SHA256
        and result.get("output_scne_sha256") == OUTPUT_SYSTEM_SHA256
        and result.get("outer_entry_size_bytes") == common.OUTER_SIZE,
        "writer receipt output hashes/size differ",
    )
    require(
        target.get("outer_entry_index") == common.OUTER_INDEX
        and target.get("inner_file_index") == common.INNER_INDEX
        and target.get("routes") == _expected_receipt_routes(),
        "writer receipt routes differ",
    )
    require(
        preservation.get("decoded_scne_changed_offsets") == CHANGED_BYTE_OFFSET_TEXT
        and preservation.get("decoded_scne_changed_byte_count") == 2
        and preservation.get("fixed_outer_allocation_exact") is True
        and preservation.get("sibling_blocks_decoded_exact") is True
        and preservation.get("sibling_blocks_stored_exact") is True
        and preservation.get("whole_volume_outside_outer_1310_exact") is True
        and preservation.get("outside_outer_1310_prefix_sha256") == prefix_sha
        and preservation.get("outside_outer_1310_suffix_sha256") == suffix_sha,
        "writer receipt preservation proof differs",
    )
    require(
        claims.get("high_and_low_lod_material_route_semantics_proved") is True
        and claims.get("visual_eagles_match_proved") is False
        and claims.get("emulator_runtime_visibility_proved") is False,
        "writer receipt claim boundary differs",
    )


def verify(source_path: Path, output_path: Path, receipt_path: Path) -> dict[str, Any]:
    source_meta, source_directory, source_raw = common._read_volume(source_path, "source 0A")
    output_meta, output_directory, output_raw = common._read_volume(output_path, "output 0A")
    receipt_meta = common._regular(receipt_path, "writer receipt")
    require(
        len(
            {
                (source_meta.st_dev, source_meta.st_ino),
                (output_meta.st_dev, output_meta.st_ino),
                (receipt_meta.st_dev, receipt_meta.st_ino),
            }
        )
        == 3,
        "source, output, and receipt alias an inode",
    )
    require(source_directory == output_directory, "outer directory changed")
    source = common._parse_entry(source_raw, common.SOURCE_OUTER_SHA256, "source")
    output = common._parse_entry(output_raw, OUTPUT_OUTER_SHA256, "output")
    require(common.sha256_bytes(source.system) == common.SOURCE_SYSTEM_SHA256, "source SCNE hash differs")
    require(common.sha256_bytes(output.system) == OUTPUT_SYSTEM_SHA256, "output SCNE hash differs")
    changed = [index for index, pair in enumerate(zip(source.system, output.system)) if pair[0] != pair[1]]
    require(
        len(source.system) == len(output.system) and changed == CHANGED_BYTE_OFFSETS,
        "decoded SCNE diff is not exactly the high/low material bytes",
    )
    require(
        _semantic_material_slots(source.system, "source") == {"helmet_hi": 1, "helmet_lo": 1},
        "source high/low material slots are not both 1",
    )
    require(
        _semantic_material_slots(output.system, "output") == {"helmet_hi": 2, "helmet_lo": 2},
        "output high/low material slots are not both 2",
    )
    require(source.blocks[1:] == output.blocks[1:], "decoded sibling blocks differ")
    require(source.stored[1:] == output.stored[1:], "stored sibling blocks differ")
    require(source.record.footer is not None and output.record.footer is not None, "name footer missing")
    source_footer_size = 8 + source.record.footer.payload_size
    output_footer_size = 8 + output.record.footer.payload_size
    require(
        source.raw[source.record.file_length : source.record.file_length + source_footer_size]
        == output.raw[output.record.file_length : output.record.file_length + output_footer_size],
        "name footer differs",
    )
    require(len(output.raw) == common.OUTER_SIZE, "fixed outer allocation differs")

    prefix_source = common._hash_range(source_path, 0, common.OUTER_OFFSET)
    prefix_output = common._hash_range(output_path, 0, common.OUTER_OFFSET)
    suffix_offset = common.OUTER_OFFSET + common.OUTER_SIZE
    suffix_size = common.VOLUME_SIZE - suffix_offset
    suffix_source = common._hash_range(source_path, suffix_offset, suffix_size)
    suffix_output = common._hash_range(output_path, suffix_offset, suffix_size)
    require(prefix_source == prefix_output and suffix_source == suffix_output, "whole volume outside outer 1310 differs")
    source_sha = common._hash_file(source_path)
    output_sha = common._hash_file(output_path)
    receipt = common._strict_receipt(receipt_path)
    _validate_receipt(receipt, source_sha, output_sha, prefix_source, suffix_source)
    return {
        "output": {
            "outer_entry_sha256": OUTPUT_OUTER_SHA256,
            "scne_sha256": OUTPUT_SYSTEM_SHA256,
            "volume_sha256": output_sha,
            "volume_size_bytes": common.VOLUME_SIZE,
        },
        "proof": {
            "decoded_scne_changed_offsets": CHANGED_BYTE_OFFSET_TEXT,
            "fixed_outer_allocation_exact": True,
            "material_slot_routes": ["helmet_hi draw 1: 1 -> 2", "helmet_lo draw 1: 1 -> 2"],
            "sibling_blocks_decoded_and_stored_exact": True,
            "whole_volume_outside_outer_1310_exact": True,
        },
        "schema": VERIFY_SCHEMA,
        "source": {
            "outer_entry_sha256": common.SOURCE_OUTER_SHA256,
            "scne_sha256": common.SOURCE_SYSTEM_SHA256,
            "volume_sha256": source_sha,
        },
        "verified": True,
    }


def _write_report(path: Path, document: dict[str, Any]) -> None:
    require(not path.exists() and not path.is_symlink(), f"refusing to overwrite report: {path}")
    require(path.parent.is_dir(), "report parent directory does not exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = common.canonical_json_bytes(document)
        require(os.write(descriptor, payload) == len(payload), "short report write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--report", type=Path, help="optional new verification JSON")
    args = parser.parse_args(argv)
    try:
        report = verify(args.source, args.output, args.receipt)
        if args.report is not None:
            _write_report(args.report, report)
    except (OSError, VerifyError) as exc:
        parser.exit(2, f"dual-LOD helmet shell material route verification failed: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
