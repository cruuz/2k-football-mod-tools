#!/usr/bin/env python3
"""Create the fixed APF dual-LOD helmet-shell material-route witness.

The only supported operation is the source-bound ``helmet_hi`` and
``helmet_lo`` draw-record 1 material word change from slot 1 to slot 2 in
``global.iff`` outer 1310, ``helmet_00`` inner 128.  The source 0A is never
opened writable.  Publication is an exclusive copy to a new 0A plus a
hash-only JSON receipt.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_shell_material_route_patch as base  # noqa: E402
import apf_inner  # noqa: E402
import apf_scene  # noqa: E402


SCHEMA = "apf2k8_helmet_dual_lod_shell_material_route_patch/v1"
OPERATION = "route_helmet_hi_and_lo_draw_1_material_slot_1_to_2"
RECEIPT_SUFFIX = ".apf-helmet-dual-lod-shell-material-route.json"
OUTPUT_SYSTEM_SHA256 = (
    "4eec61ad512d26c6b68694d6d1564b5e9af92fcd41e52ca5de729cd1455f3178"
)
OUTPUT_OUTER_SHA256 = (
    "01ebbe682019310bc24b138d205e2e3e9058dd7e59b0efbb5ed1c16369fa26f8"
)


@dataclass(frozen=True)
class LodRoute:
    node_index: int
    node_name: str
    draw_record_start: int
    material_field_offset: int
    changed_byte_offset: int


LOD_ROUTES = (
    LodRoute(0, "helmet_hi", 0x000099C0, 0x00009A10, 0x00009A13),
    LodRoute(32, "helmet_lo", 0x000CCA80, 0x000CCAD0, 0x000CCAD3),
)
CHANGED_BYTE_OFFSETS = tuple(route.changed_byte_offset for route in LOD_ROUTES)


def _validate_semantic_routes(system: bytes, wanted_slot: int) -> None:
    try:
        scene = apf_scene.parse_scene_system_part(
            system,
            outer_index=base.OUTER_INDEX,
            inner_index=base.INNER_INDEX,
            capture_geometry=False,
        )
    except apf_scene.SceneError as exc:
        raise base.PatchError(f"helmet_00 SCNE semantic parse failed: {exc}") from exc
    nodes = scene.get("nodes")
    if not isinstance(nodes, list):
        raise base.PatchError("helmet node inventory is missing")
    for route in LOD_ROUTES:
        if len(nodes) <= route.node_index:
            raise base.PatchError(f"{route.node_name} node is missing")
        node = nodes[route.node_index]
        derived = (
            int(node.get("draw_record_offset", -1))
            + base.DRAW_RECORD_INDEX * base.DRAW_RECORD_SIZE
            + 0x20
        )
        if (
            scene.get("root_name") != base.INNER_NAME
            or node.get("name") != route.node_name
            or node.get("draw_record_offset") != route.draw_record_start
            or derived != route.material_field_offset
            or struct.unpack_from(">I", system, derived)[0] != wanted_slot
        ):
            raise base.PatchError(
                f"{route.node_name} draw-1 material route drift"
            )


def replace_material_words(system: bytes) -> bytes:
    """Replace both guarded big-endian material words and no other bytes."""

    for route in LOD_ROUTES:
        if route.material_field_offset + 4 > len(system):
            raise base.PatchError(
                f"{route.node_name} material field is outside the SCNE system part"
            )
        actual = struct.unpack_from(">I", system, route.material_field_offset)[0]
        if actual != base.SOURCE_MATERIAL_SLOT:
            raise base.PatchError(
                f"{route.node_name} material source drift: expected "
                f"{base.SOURCE_MATERIAL_SLOT}, found {actual}"
            )
    output = bytearray(system)
    for route in LOD_ROUTES:
        struct.pack_into(
            ">I", output, route.material_field_offset, base.OUTPUT_MATERIAL_SLOT
        )
    changed = base.difference_offsets(system, output)
    if changed != list(CHANGED_BYTE_OFFSETS):
        raise base.PatchError(
            f"dual-LOD material route changed {changed!r}, "
            f"expected {list(CHANGED_BYTE_OFFSETS)!r}"
        )
    return bytes(output)


def build_patch(source_0a: Path) -> base.BuiltPatch:
    source = base.read_source_entry(Path(source_0a))
    _validate_semantic_routes(source.system, base.SOURCE_MATERIAL_SLOT)
    output_system = replace_material_words(source.system)
    new_block0 = bytearray(source.blocks[0])
    new_block0[
        base.SYSTEM_PART_OFFSET : base.SYSTEM_PART_OFFSET + base.SYSTEM_LENGTH
    ] = output_system
    rebuilt, metrics, file_length = base._rebuild_entry(source, bytes(new_block0))

    reader = base.BytesReader(rebuilt)
    try:
        record = apf_inner.parse_iff(reader, source.entry)
        output_blocks = tuple(
            apf_inner.decode_block(reader, record, index, base.MAX_DECOMPRESSED)
            for index in range(record.block_count)
        )
    except apf_inner.FormatError as exc:
        raise base.PatchError(f"rebuilt global.iff failed reopen: {exc}") from exc
    item = record.files[base.INNER_INDEX]
    part = item.parts[0]
    reopened_system = output_blocks[part.block_index][
        part.offset : part.offset + part.length
    ]
    if reopened_system != output_system:
        raise base.PatchError("reopened helmet_00 SCNE differs")
    if base.difference_offsets(source.system, reopened_system) != list(
        CHANGED_BYTE_OFFSETS
    ):
        raise base.PatchError("reopened SCNE changed outside the two LOD fields")
    _validate_semantic_routes(reopened_system, base.OUTPUT_MATERIAL_SLOT)
    if output_blocks[1:] != source.blocks[1:]:
        raise base.PatchError("decoded sibling blocks changed")
    output_stored = tuple(
        reader.read(source.entry, block.start_offset, block.stored_length)
        for block in record.blocks
    )
    if output_stored[1:] != source.stored[1:]:
        raise base.PatchError("stored sibling blocks changed")
    if len(rebuilt) != base.OUTER_SIZE:
        raise base.PatchError("rebuilt outer allocation length changed")
    if base.sha256_bytes(output_system) != OUTPUT_SYSTEM_SHA256:
        raise base.PatchError("dual-LOD SCNE output identity differs")
    if base.sha256_bytes(rebuilt) != OUTPUT_OUTER_SHA256:
        raise base.PatchError("dual-LOD outer output identity differs")
    return base.BuiltPatch(source, rebuilt, output_system, file_length, metrics)


def _receipt_document(
    built: base.BuiltPatch,
    *,
    source_volume_sha256: str,
    output_volume_sha256: str,
    prefix_sha256: str,
    suffix_sha256: str,
    copy_method: str,
    output_name: str,
) -> dict[str, Any]:
    sibling_stored = {
        str(index): base.sha256_bytes(payload)
        for index, payload in enumerate(built.source.stored[1:], start=1)
    }
    routes = [
        {
            "draw_record_index": base.DRAW_RECORD_INDEX,
            "draw_record_start": f"0x{route.draw_record_start:08x}",
            "material_field_byte_offset": f"0x{route.material_field_offset:08x}",
            "new_material_slot": base.OUTPUT_MATERIAL_SLOT,
            "node_index": route.node_index,
            "node_name": route.node_name,
            "old_material_slot": base.SOURCE_MATERIAL_SLOT,
        }
        for route in LOD_ROUTES
    ]
    return {
        "claim_flags": {
            "editor_gui_integrated": False,
            "emulator_runtime_visibility_proved": False,
            "high_and_low_lod_material_route_semantics_proved": True,
            "original_xbox_360_hardware_proved": False,
            "visual_eagles_match_proved": False,
        },
        "compression": dict(sorted(built.h7a_metrics.items())),
        "operation": OPERATION,
        "preservation": {
            "authorized_scne_field_ranges": [
                [f"0x{route.material_field_offset:08x}", f"0x{route.material_field_offset + 3:08x}"]
                for route in LOD_ROUTES
            ],
            "decoded_scne_changed_byte_count": len(CHANGED_BYTE_OFFSETS),
            "decoded_scne_changed_offsets": [
                f"0x{offset:08x}" for offset in CHANGED_BYTE_OFFSETS
            ],
            "fixed_outer_allocation_bytes": base.OUTER_SIZE,
            "fixed_outer_allocation_exact": True,
            "outside_outer_1310_prefix_sha256": prefix_sha256,
            "outside_outer_1310_suffix_sha256": suffix_sha256,
            "sibling_blocks_decoded_exact": True,
            "sibling_blocks_stored_exact": True,
            "sibling_stored_sha256": sibling_stored,
            "whole_volume_outside_outer_1310_exact": True,
        },
        "result": {
            "copy_method": copy_method,
            "file_length_after": built.file_length_after,
            "outer_allocation_tail_bytes": (
                base.OUTER_SIZE
                - built.file_length_after
                - (8 + built.source.record.footer.payload_size)  # type: ignore[union-attr]
            ),
            "outer_entry_sha256": OUTPUT_OUTER_SHA256,
            "outer_entry_size_bytes": len(built.rebuilt_entry),
            "output_name": output_name,
            "output_scne_sha256": OUTPUT_SYSTEM_SHA256,
            "output_volume_sha256": output_volume_sha256,
            "output_volume_size_bytes": base.VOLUME_SIZE,
        },
        "schema": SCHEMA,
        "source": {
            "outer_directory_sha256": base.OUTER_DIRECTORY_SHA256,
            "outer_entry_sha256": base.SOURCE_OUTER_SHA256,
            "source_scne_sha256": base.SOURCE_SYSTEM_SHA256,
            "source_volume_name": base.VOLUME_NAME,
            "source_volume_sha256": source_volume_sha256,
            "source_volume_size_bytes": base.VOLUME_SIZE,
        },
        "target": {
            "inner_file_index": base.INNER_INDEX,
            "inner_name": base.INNER_NAME,
            "inner_type": base.INNER_TYPE,
            "outer_entry_index": base.OUTER_INDEX,
            "outer_entry_pack_offset": base.OUTER_OFFSET,
            "routes": routes,
        },
    }


def publish(
    source_0a: Path,
    output_0a: Path,
    receipt_path: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    source_path = Path(source_0a)
    output_path = Path(output_0a)
    receipt = (
        Path(receipt_path)
        if receipt_path is not None
        else output_path.with_name(output_path.name + RECEIPT_SUFFIX)
    )
    source_meta = base._regular_source(source_path)
    if output_path.name != base.VOLUME_NAME or not output_path.parent.is_dir():
        raise base.PatchError("output must be a new file named 0A in an existing directory")
    if not receipt.parent.is_dir():
        raise base.PatchError("receipt parent directory does not exist")
    for path, label in ((output_path, "output 0A"), (receipt, "receipt")):
        if path.exists() or path.is_symlink():
            raise base.PatchError(f"refusing to overwrite {label}: {path}")
    if source_path.resolve(strict=True) == output_path.resolve(strict=False):
        raise base.PatchError("source and output 0A paths alias")

    built = build_patch(source_path)
    read_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    write_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    source_fd = os.open(source_path, read_flags)
    output_fd: int | None = None
    keep = False
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            source_meta.st_dev,
            source_meta.st_ino,
            source_meta.st_size,
        ):
            raise base.PatchError("source 0A changed before publication")
        if base.sha256_bytes(os.pread(source_fd, base.OUTER_SIZE, base.OUTER_OFFSET)) != base.SOURCE_OUTER_SHA256:
            raise base.PatchError("source outer 1310 changed before publication")
        output_fd = os.open(output_path, write_flags, stat.S_IMODE(source_meta.st_mode))
        copy_method = base._copy_fd(source_fd, output_fd, base.VOLUME_SIZE)
        if os.fstat(output_fd).st_size != base.VOLUME_SIZE:
            raise base.PatchError("copied output 0A has the wrong size")
        if base.platform_compat.pwrite(output_fd, built.rebuilt_entry, base.OUTER_OFFSET) != base.OUTER_SIZE:
            raise base.PatchError("short write while installing rebuilt outer 1310")
        os.fsync(output_fd)
        if os.pread(output_fd, base.OUTER_SIZE, base.OUTER_OFFSET) != built.rebuilt_entry:
            raise base.PatchError("published outer 1310 failed exact reread")

        source_prefix = base._hash_fd_range(source_fd, 0, base.OUTER_OFFSET)
        output_prefix = base._hash_fd_range(output_fd, 0, base.OUTER_OFFSET)
        suffix_offset = base.OUTER_OFFSET + base.OUTER_SIZE
        suffix_size = base.VOLUME_SIZE - suffix_offset
        source_suffix = base._hash_fd_range(source_fd, suffix_offset, suffix_size)
        output_suffix = base._hash_fd_range(output_fd, suffix_offset, suffix_size)
        if source_prefix != output_prefix or source_suffix != output_suffix:
            raise base.PatchError("output changed bytes outside outer 1310")
        source_sha = base._hash_fd(source_fd)
        output_sha = base._hash_fd(output_fd)
        document = _receipt_document(
            built,
            source_volume_sha256=source_sha,
            output_volume_sha256=output_sha,
            prefix_sha256=source_prefix,
            suffix_sha256=source_suffix,
            copy_method=copy_method,
            output_name=output_path.name,
        )
        base._write_json_new(receipt, document)
        keep = True
        return output_path, receipt, document
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(source_fd)
        if not keep:
            receipt.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="read-only source 0A")
    parser.add_argument("--output", required=True, type=Path, help="new output file named 0A")
    parser.add_argument("--receipt", type=Path, help="new JSON receipt path")
    args = parser.parse_args(argv)
    try:
        output, receipt, document = publish(args.source, args.output, args.receipt)
    except (OSError, base.PatchError) as exc:
        parser.exit(2, f"dual-LOD helmet shell material route failed: {exc}\n")
    print(
        json.dumps(
            {
                "output": str(output),
                "output_sha256": document["result"]["output_volume_sha256"],
                "outer_entry_sha256": document["result"]["outer_entry_sha256"],
                "receipt": str(receipt),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
