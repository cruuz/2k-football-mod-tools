#!/usr/bin/env python3
"""Create the fixed APF high-LOD helmet-shell material-route witness.

The only supported operation is the source-bound ``helmet_hi`` draw-record 1
material word change from slot 1 to slot 2 in ``global.iff`` outer 1310,
``helmet_00`` inner 128.  The source 0A is never opened writable.  Publication
is an exclusive copy to a new 0A plus a hash-only JSON receipt.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_scene  # noqa: E402
from mod_editor.core import platform_compat  # noqa: E402


SCHEMA = "apf2k8_helmet_shell_material_route_patch/v1"
OPERATION = "route_helmet_hi_draw_1_material_slot_1_to_2"
RECEIPT_SUFFIX = ".apf-helmet-shell-material-route.json"

VOLUME_NAME = "0A"
VOLUME_SIZE = 1_140_850_688
OUTER_DIRECTORY_SIZE = 18_604
OUTER_DIRECTORY_SHA256 = (
    "2463120a5fd4aacec49e50585eb23a4fc3ee27759f7bd11b407d35a2ab809942"
)
OUTER_INDEX = 1310
OUTER_NAME_ID = 0xDB5E3E48
OUTER_OFFSET = 0x01570800
OUTER_SIZE = 0x017DE800
SOURCE_OUTER_SHA256 = (
    "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d"
)
INNER_INDEX = 128
INNER_FILE_ID = 0x4A3503FC
INNER_NAME = "helmet_00"
INNER_TYPE = "SCNE"
BLOCK_COUNT = 3
SYSTEM_BLOCK_INDEX = 0
SYSTEM_PART_OFFSET = 0x00173680
SYSTEM_LENGTH = 0x000D5680
SOURCE_SYSTEM_SHA256 = (
    "5c121fcf01b96f2e087e9238584a511868b09ad60476658d023eb186f33dc1bb"
)
HELMET_NODE_INDEX = 0
HELMET_NODE_NAME = "helmet_hi"
DRAW_RECORD_SIZE = 0x30
DRAW_RECORD_INDEX = 1
DRAW_RECORD_START = 0x000099C0
MATERIAL_FIELD_OFFSET = 0x00009A10
CHANGED_BYTE_OFFSET = 0x00009A13
SOURCE_MATERIAL_SLOT = 1
OUTPUT_MATERIAL_SLOT = 2
MAX_DECOMPRESSED = 128 * 1024 * 1024


class PatchError(ValueError):
    """The source, fixed route, or copy-only publication failed closed."""


class BytesReader:
    """Bounded entry-relative reader accepted by the foundational IFF parser."""

    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds outer allocation")
        return self.payload[offset : offset + size]


@dataclass(frozen=True)
class SourceEntry:
    entry: apf_outer.Entry
    raw: bytes
    record: apf_inner.IFFRecord
    stored: tuple[bytes, ...]
    blocks: tuple[bytes, ...]
    system: bytes


@dataclass(frozen=True)
class BuiltPatch:
    source: SourceEntry
    rebuilt_entry: bytes
    output_system: bytes
    file_length_after: int
    h7a_metrics: dict[str, int]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def difference_offsets(before: bytes, after: bytes) -> list[int]:
    if len(before) != len(after):
        raise PatchError("difference inputs have unequal lengths")
    return [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]


def replace_material_word(
    system: bytes,
    *,
    field_offset: int = MATERIAL_FIELD_OFFSET,
    expected: int = SOURCE_MATERIAL_SLOT,
    replacement: int = OUTPUT_MATERIAL_SLOT,
) -> bytes:
    """Replace one guarded big-endian material word and no other byte."""

    if field_offset < 0 or field_offset + 4 > len(system):
        raise PatchError("material field is outside the SCNE system part")
    actual = struct.unpack_from(">I", system, field_offset)[0]
    if actual != expected:
        raise PatchError(
            f"helmet shell material source drift: expected {expected}, found {actual}"
        )
    output = bytearray(system)
    struct.pack_into(">I", output, field_offset, replacement)
    changed = difference_offsets(system, output)
    wanted = [field_offset + 3]
    if changed != wanted:
        raise PatchError(f"material route changed {changed!r}, expected {wanted!r}")
    return bytes(output)


def _fixed_entry() -> apf_outer.Entry:
    return apf_outer.Entry(
        table_index=OUTER_INDEX,
        name_id=OUTER_NAME_ID,
        offset_blocks=OUTER_OFFSET // 2048,
        size_blocks=OUTER_SIZE // 2048,
        virtual_offset=OUTER_OFFSET,
        size=OUTER_SIZE,
        head_hex="ff3bef94",
        segments=(
            apf_outer.Segment(
                pack_ordinal=0,
                pack_name=VOLUME_NAME,
                pack_offset=OUTER_OFFSET,
                size=OUTER_SIZE,
            ),
        ),
    )


def _regular_source(path: Path) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PatchError(f"could not inspect source 0A: {exc}") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise PatchError("source 0A must be a regular non-symlink file")
    if path.name != VOLUME_NAME or metadata.st_size != VOLUME_SIZE:
        raise PatchError("source must be the fixed-size APF volume named 0A")
    return metadata


def _read_exact_at(stream: BinaryIO, offset: int, size: int, what: str) -> bytes:
    stream.seek(offset)
    payload = stream.read(size)
    if len(payload) != size:
        raise PatchError(f"short read while reading {what}")
    return payload


def read_source_entry(path: Path) -> SourceEntry:
    """Read the target from a standalone 0A; sibling packs are not required."""

    metadata = _regular_source(path)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise PatchError("source 0A changed while opening")
        directory = _read_exact_at(
            stream, 0, OUTER_DIRECTORY_SIZE, "outer directory"
        )
        raw = _read_exact_at(stream, OUTER_OFFSET, OUTER_SIZE, "outer 1310")
    if sha256_bytes(directory) != OUTER_DIRECTORY_SHA256:
        raise PatchError("APF outer directory identity drift")
    table_record = directory[88 + OUTER_INDEX * 12 : 88 + (OUTER_INDEX + 1) * 12]
    if table_record != struct.pack(">3I", OUTER_NAME_ID, OUTER_OFFSET // 2048, OUTER_SIZE // 2048):
        raise PatchError("outer 1310 directory route drift")
    if sha256_bytes(raw) != SOURCE_OUTER_SHA256:
        raise PatchError("global.iff outer 1310 is not the pinned source allocation")

    entry = _fixed_entry()
    reader = BytesReader(raw)
    try:
        record = apf_inner.parse_iff(reader, entry)
        stored = tuple(
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        )
        blocks = tuple(
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        )
    except apf_inner.FormatError as exc:
        raise PatchError(f"could not parse pinned global.iff: {exc}") from exc
    if record.warnings or record.block_count != BLOCK_COUNT:
        raise PatchError("global.iff block inventory drift")
    try:
        item = record.files[INNER_INDEX]
    except IndexError as exc:
        raise PatchError("helmet_00 inner index is missing") from exc
    if (
        item.file_id != INNER_FILE_ID
        or item.name != INNER_NAME
        or item.type_name != INNER_TYPE
        or len(item.parts) != 1
        or item.parts[0].block_index != SYSTEM_BLOCK_INDEX
        or item.parts[0].offset != SYSTEM_PART_OFFSET
        or item.parts[0].length != SYSTEM_LENGTH
    ):
        raise PatchError("helmet_00 SCNE ownership drift")
    part = item.parts[0]
    system = blocks[part.block_index][part.offset : part.offset + part.length]
    if len(system) != SYSTEM_LENGTH or sha256_bytes(system) != SOURCE_SYSTEM_SHA256:
        raise PatchError("helmet_00 SCNE identity drift")
    _validate_semantic_route(system, SOURCE_MATERIAL_SLOT)
    return SourceEntry(entry, raw, record, stored, blocks, system)


def _validate_semantic_route(system: bytes, wanted_slot: int) -> None:
    try:
        scene = apf_scene.parse_scene_system_part(
            system,
            outer_index=OUTER_INDEX,
            inner_index=INNER_INDEX,
            capture_geometry=False,
        )
    except apf_scene.SceneError as exc:
        raise PatchError(f"helmet_00 SCNE semantic parse failed: {exc}") from exc
    nodes = scene.get("nodes")
    if not isinstance(nodes, list) or len(nodes) <= HELMET_NODE_INDEX:
        raise PatchError("helmet_hi node is missing")
    node = nodes[HELMET_NODE_INDEX]
    derived = int(node.get("draw_record_offset", -1)) + (
        DRAW_RECORD_INDEX * DRAW_RECORD_SIZE
    ) + 0x20
    if (
        scene.get("root_name") != INNER_NAME
        or node.get("name") != HELMET_NODE_NAME
        or node.get("draw_record_offset") != DRAW_RECORD_START
        or derived != MATERIAL_FIELD_OFFSET
        or struct.unpack_from(">I", system, derived)[0] != wanted_slot
    ):
        raise PatchError("helmet_hi draw-1 material route drift")


def _rebuild_entry(source: SourceEntry, new_block0: bytes) -> tuple[bytes, dict[str, int], int]:
    descriptor = source.record.blocks[0]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise PatchError("helmet DRAM block lost its H7A wrapper")
    try:
        encoded, metrics = apf_inner.encode_h7a_preserving_tokens(
            source.stored[0][apf_inner.H7A_HEADER_SIZE :],
            source.blocks[0],
            new_block0,
            descriptor.wrapper.shift,
        )
    except apf_inner.FormatError as exc:
        raise PatchError(f"could not preservation-encode helmet DRAM: {exc}") from exc
    changed_stored = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        len(new_block0),
        apf_inner.H7A_HEADER_SIZE + len(encoded),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + encoded
    stored = (changed_stored, *source.stored[1:])
    header = bytearray(source.raw[: source.record.header_size])
    body = bytearray()
    cursor = source.record.header_size
    for index, (old, payload) in enumerate(zip(source.record.blocks, stored)):
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            old.name_hash,
            old.type_hash,
            old.unknown_08,
            old.uncompressed_length,
            old.unknown_10,
            cursor,
            len(payload),
            old.indexed,
        )
        body.extend(payload)
        cursor += len(payload)
    struct.pack_into(">I", header, 0x08, cursor)
    if source.record.footer is None:
        raise PatchError("global.iff name footer is missing")
    footer_size = 8 + source.record.footer.payload_size
    footer = source.raw[
        source.record.file_length : source.record.file_length + footer_size
    ]
    tail = source.raw[source.record.file_length + footer_size :]
    if len(footer) != footer_size or any(tail):
        raise PatchError("global.iff footer or zero-allocation tail drift")
    active = bytes(header) + bytes(body) + footer
    if len(active) > OUTER_SIZE:
        raise PatchError(
            f"rebuilt global.iff exceeds its fixed allocation by {len(active) - OUTER_SIZE} bytes"
        )
    return active + bytes(OUTER_SIZE - len(active)), metrics, cursor


def build_patch(source_0a: Path) -> BuiltPatch:
    source = read_source_entry(Path(source_0a))
    output_system = replace_material_word(source.system)
    new_block0 = bytearray(source.blocks[0])
    new_block0[SYSTEM_PART_OFFSET : SYSTEM_PART_OFFSET + SYSTEM_LENGTH] = output_system
    rebuilt, metrics, file_length = _rebuild_entry(source, bytes(new_block0))

    reader = BytesReader(rebuilt)
    try:
        record = apf_inner.parse_iff(reader, source.entry)
        output_blocks = tuple(
            apf_inner.decode_block(reader, record, index, MAX_DECOMPRESSED)
            for index in range(record.block_count)
        )
    except apf_inner.FormatError as exc:
        raise PatchError(f"rebuilt global.iff failed reopen: {exc}") from exc
    item = record.files[INNER_INDEX]
    part = item.parts[0]
    reopened_system = output_blocks[part.block_index][
        part.offset : part.offset + part.length
    ]
    if reopened_system != output_system:
        raise PatchError("reopened helmet_00 SCNE differs")
    if difference_offsets(source.system, reopened_system) != [CHANGED_BYTE_OFFSET]:
        raise PatchError("reopened SCNE changed outside byte 0x9a13")
    _validate_semantic_route(reopened_system, OUTPUT_MATERIAL_SLOT)
    if output_blocks[1:] != source.blocks[1:]:
        raise PatchError("decoded sibling blocks changed")
    output_stored = tuple(
        reader.read(source.entry, block.start_offset, block.stored_length)
        for block in record.blocks
    )
    if output_stored[1:] != source.stored[1:]:
        raise PatchError("stored sibling blocks changed")
    if len(rebuilt) != OUTER_SIZE:
        raise PatchError("rebuilt outer allocation length changed")
    return BuiltPatch(source, rebuilt, output_system, file_length, metrics)


def _hash_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    size = os.fstat(descriptor).st_size
    cursor = 0
    while cursor < size:
        payload = os.pread(descriptor, min(16 * 1024 * 1024, size - cursor), cursor)
        if not payload:
            raise PatchError("short read while hashing volume")
        digest.update(payload)
        cursor += len(payload)
    return digest.hexdigest()


def _hash_fd_range(descriptor: int, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    cursor = offset
    remaining = size
    while remaining:
        payload = os.pread(descriptor, min(16 * 1024 * 1024, remaining), cursor)
        if not payload:
            raise PatchError("short read while hashing volume range")
        digest.update(payload)
        cursor += len(payload)
        remaining -= len(payload)
    return digest.hexdigest()


def _copy_fd(source_fd: int, output_fd: int, size: int) -> str:
    if platform_compat.try_reflink(output_fd, source_fd):
        return "reflink"
    os.ftruncate(output_fd, 0)
    copied = 0
    while copied < size:
        count = min(16 * 1024 * 1024, size - copied)
        payload = os.pread(source_fd, count, copied)
        if not payload:
            raise PatchError("short read while copying source 0A")
        written = platform_compat.pwrite(output_fd, payload, copied)
        if written != len(payload):
            raise PatchError("short write while copying source 0A")
        copied += written
    return "bounded-copy"


def _write_json_new(path: Path, document: dict[str, Any]) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        payload = canonical_json_bytes(document)
        if os.write(descriptor, payload) != len(payload):
            raise PatchError("short write while publishing receipt")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _receipt_document(
    built: BuiltPatch,
    *,
    source_volume_sha256: str,
    output_volume_sha256: str,
    prefix_sha256: str,
    suffix_sha256: str,
    copy_method: str,
    output_name: str,
) -> dict[str, Any]:
    output_entry_sha = sha256_bytes(built.rebuilt_entry)
    output_system_sha = sha256_bytes(built.output_system)
    sibling_stored = {
        str(index): sha256_bytes(payload)
        for index, payload in enumerate(built.source.stored[1:], start=1)
    }
    return {
        "claim_flags": {
            "editor_gui_integrated": False,
            "emulator_runtime_visibility_proved": False,
            "material_route_semantics_proved": True,
            "original_xbox_360_hardware_proved": False,
            "visual_eagles_match_proved": False,
        },
        "compression": dict(sorted(built.h7a_metrics.items())),
        "operation": OPERATION,
        "preservation": {
            "authorized_scne_field_range": ["0x00009a10", "0x00009a13"],
            "decoded_scne_changed_byte_count": 1,
            "decoded_scne_changed_offsets": ["0x00009a13"],
            "fixed_outer_allocation_bytes": OUTER_SIZE,
            "fixed_outer_allocation_exact": True,
            "sibling_blocks_decoded_exact": True,
            "sibling_blocks_stored_exact": True,
            "sibling_stored_sha256": sibling_stored,
            "whole_volume_outside_outer_1310_exact": True,
            "outside_outer_1310_prefix_sha256": prefix_sha256,
            "outside_outer_1310_suffix_sha256": suffix_sha256,
        },
        "result": {
            "copy_method": copy_method,
            "file_length_after": built.file_length_after,
            "outer_allocation_tail_bytes": (
                OUTER_SIZE
                - built.file_length_after
                - (8 + built.source.record.footer.payload_size)  # type: ignore[union-attr]
            ),
            "outer_entry_sha256": output_entry_sha,
            "outer_entry_size_bytes": len(built.rebuilt_entry),
            "output_name": output_name,
            "output_scne_sha256": output_system_sha,
            "output_volume_sha256": output_volume_sha256,
            "output_volume_size_bytes": VOLUME_SIZE,
        },
        "schema": SCHEMA,
        "source": {
            "outer_directory_sha256": OUTER_DIRECTORY_SHA256,
            "outer_entry_sha256": SOURCE_OUTER_SHA256,
            "source_scne_sha256": SOURCE_SYSTEM_SHA256,
            "source_volume_name": VOLUME_NAME,
            "source_volume_sha256": source_volume_sha256,
            "source_volume_size_bytes": VOLUME_SIZE,
        },
        "target": {
            "draw_record_index": DRAW_RECORD_INDEX,
            "inner_file_index": INNER_INDEX,
            "inner_name": INNER_NAME,
            "inner_type": INNER_TYPE,
            "material_field_byte_offset": "0x00009a10",
            "new_material_slot": OUTPUT_MATERIAL_SLOT,
            "node_index": HELMET_NODE_INDEX,
            "node_name": HELMET_NODE_NAME,
            "old_material_slot": SOURCE_MATERIAL_SLOT,
            "outer_entry_index": OUTER_INDEX,
            "outer_entry_pack_offset": OUTER_OFFSET,
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
    source_meta = _regular_source(source_path)
    if output_path.name != VOLUME_NAME or not output_path.parent.is_dir():
        raise PatchError("output must be a new file named 0A in an existing directory")
    if not receipt.parent.is_dir():
        raise PatchError("receipt parent directory does not exist")
    for path, label in ((output_path, "output 0A"), (receipt, "receipt")):
        if path.exists() or path.is_symlink():
            raise PatchError(f"refusing to overwrite {label}: {path}")
    if source_path.resolve(strict=True) == output_path.resolve(strict=False):
        raise PatchError("source and output 0A paths alias")

    built = build_patch(source_path)
    read_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    write_flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
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
            raise PatchError("source 0A changed before publication")
        if sha256_bytes(os.pread(source_fd, OUTER_SIZE, OUTER_OFFSET)) != SOURCE_OUTER_SHA256:
            raise PatchError("source outer 1310 changed before publication")
        output_fd = os.open(output_path, write_flags, stat.S_IMODE(source_meta.st_mode))
        copy_method = _copy_fd(source_fd, output_fd, VOLUME_SIZE)
        if os.fstat(output_fd).st_size != VOLUME_SIZE:
            raise PatchError("copied output 0A has the wrong size")
        if platform_compat.pwrite(output_fd, built.rebuilt_entry, OUTER_OFFSET) != OUTER_SIZE:
            raise PatchError("short write while installing rebuilt outer 1310")
        os.fsync(output_fd)
        if os.pread(output_fd, OUTER_SIZE, OUTER_OFFSET) != built.rebuilt_entry:
            raise PatchError("published outer 1310 failed exact reread")

        source_prefix = _hash_fd_range(source_fd, 0, OUTER_OFFSET)
        output_prefix = _hash_fd_range(output_fd, 0, OUTER_OFFSET)
        suffix_offset = OUTER_OFFSET + OUTER_SIZE
        suffix_size = VOLUME_SIZE - suffix_offset
        source_suffix = _hash_fd_range(source_fd, suffix_offset, suffix_size)
        output_suffix = _hash_fd_range(output_fd, suffix_offset, suffix_size)
        if source_prefix != output_prefix or source_suffix != output_suffix:
            raise PatchError("output changed bytes outside outer 1310")
        source_sha = _hash_fd(source_fd)
        output_sha = _hash_fd(output_fd)
        document = _receipt_document(
            built,
            source_volume_sha256=source_sha,
            output_volume_sha256=output_sha,
            prefix_sha256=source_prefix,
            suffix_sha256=source_suffix,
            copy_method=copy_method,
            output_name=output_path.name,
        )
        _write_json_new(receipt, document)
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
    except (OSError, PatchError) as exc:
        parser.exit(2, f"helmet shell material route failed: {exc}\n")
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
