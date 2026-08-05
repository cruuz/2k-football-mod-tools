#!/usr/bin/env python3
"""Independently verify the fixed APF high-LOD helmet material-route copy.

This verifier imports neither the writer nor any writer-owned helper.  It
independently reads standalone 0A volumes, parses both IFFs/H7A streams and the
SCNE ownership path, checks the receipt, and hashes the complete prefix and
suffix outside outer 1310.
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
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_scene  # noqa: E402


PATCH_SCHEMA = "apf2k8_helmet_shell_material_route_patch/v1"
VERIFY_SCHEMA = "apf2k8_helmet_shell_material_route_verify/v1"
OPERATION = "route_helmet_hi_draw_1_material_slot_1_to_2"
VOLUME_SIZE = 1_140_850_688
DIRECTORY_SIZE = 18_604
DIRECTORY_SHA256 = "2463120a5fd4aacec49e50585eb23a4fc3ee27759f7bd11b407d35a2ab809942"
OUTER_INDEX = 1310
OUTER_NAME_ID = 0xDB5E3E48
OUTER_OFFSET = 0x01570800
OUTER_SIZE = 0x017DE800
SOURCE_OUTER_SHA256 = "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d"
OUTPUT_OUTER_SHA256 = "e7dfc4ca5015b7900196e0369be4b1159dc4cfd905c2721a5439c9659149287d"
INNER_INDEX = 128
INNER_FILE_ID = 0x4A3503FC
INNER_NAME = "helmet_00"
SYSTEM_PART_OFFSET = 0x00173680
SYSTEM_LENGTH = 0x000D5680
SOURCE_SYSTEM_SHA256 = "5c121fcf01b96f2e087e9238584a511868b09ad60476658d023eb186f33dc1bb"
OUTPUT_SYSTEM_SHA256 = "35539dc5087982c6f0d63b05024351fd7e36b36d59ed96fed0ed2c9c5e8df715"
MATERIAL_FIELD_OFFSET = 0x00009A10
CHANGED_BYTE_OFFSET = 0x00009A13
DRAW_RECORD_START = 0x000099C0
DRAW_RECORD_SIZE = 0x30
DRAW_RECORD_INDEX = 1
MAX_DECOMPRESSED = 128 * 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024


class VerifyError(ValueError):
    """The copied candidate or its receipt failed independent verification."""


class BytesReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds allocation")
        return self.payload[offset : offset + size]


@dataclass(frozen=True)
class ParsedEntry:
    raw: bytes
    record: apf_inner.IFFRecord
    stored: tuple[bytes, ...]
    blocks: tuple[bytes, ...]
    system: bytes


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


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
            apf_outer.Segment(0, "0A", OUTER_OFFSET, OUTER_SIZE),
        ),
    )


def _regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VerifyError(f"could not inspect {label}: {exc}") from exc
    require(
        stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode),
        f"{label} must be a regular non-symlink file",
    )
    return metadata


def _read_exact(stream: BinaryIO, offset: int, size: int, label: str) -> bytes:
    stream.seek(offset)
    payload = stream.read(size)
    require(len(payload) == size, f"short read for {label}")
    return payload


def _read_volume(path: Path, label: str) -> tuple[os.stat_result, bytes, bytes]:
    metadata = _regular(path, label)
    require(path.name == "0A" and metadata.st_size == VOLUME_SIZE, f"{label} shape differs")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        require(
            (opened.st_dev, opened.st_ino, opened.st_size)
            == (metadata.st_dev, metadata.st_ino, metadata.st_size),
            f"{label} changed while opening",
        )
        directory = _read_exact(stream, 0, DIRECTORY_SIZE, f"{label} directory")
        entry = _read_exact(stream, OUTER_OFFSET, OUTER_SIZE, f"{label} outer 1310")
    require(sha256_bytes(directory) == DIRECTORY_SHA256, f"{label} directory identity differs")
    table = directory[88 + OUTER_INDEX * 12 : 88 + (OUTER_INDEX + 1) * 12]
    require(
        table == struct.pack(">3I", OUTER_NAME_ID, OUTER_OFFSET // 2048, OUTER_SIZE // 2048),
        f"{label} outer 1310 routing differs",
    )
    return metadata, directory, entry


def _parse_entry(raw: bytes, expected_sha: str, label: str) -> ParsedEntry:
    require(len(raw) == OUTER_SIZE and sha256_bytes(raw) == expected_sha, f"{label} outer hash differs")
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
        raise VerifyError(f"{label} IFF/H7A parse failed: {exc}") from exc
    require(not record.warnings and record.block_count == 3, f"{label} block inventory differs")
    require(len(record.files) > INNER_INDEX, f"{label} inner 128 is missing")
    item = record.files[INNER_INDEX]
    require(
        item.file_id == INNER_FILE_ID
        and item.name == INNER_NAME
        and item.type_name == "SCNE"
        and len(item.parts) == 1
        and item.parts[0].block_index == 0
        and item.parts[0].offset == SYSTEM_PART_OFFSET
        and item.parts[0].length == SYSTEM_LENGTH,
        f"{label} helmet_00 ownership differs",
    )
    part = item.parts[0]
    system = blocks[0][part.offset : part.offset + part.length]
    return ParsedEntry(raw, record, stored, blocks, system)


def _semantic_material_slot(system: bytes, label: str) -> int:
    try:
        scene = apf_scene.parse_scene_system_part(
            system, outer_index=OUTER_INDEX, inner_index=INNER_INDEX, capture_geometry=False
        )
    except apf_scene.SceneError as exc:
        raise VerifyError(f"{label} SCNE semantic parse failed: {exc}") from exc
    nodes = scene.get("nodes")
    require(isinstance(nodes, list) and bool(nodes), f"{label} helmet_hi node missing")
    node = nodes[0]
    derived = int(node.get("draw_record_offset", -1)) + DRAW_RECORD_INDEX * DRAW_RECORD_SIZE + 0x20
    require(
        scene.get("root_name") == INNER_NAME
        and node.get("name") == "helmet_hi"
        and node.get("draw_record_offset") == DRAW_RECORD_START
        and derived == MATERIAL_FIELD_OFFSET,
        f"{label} helmet_hi draw-1 field route differs",
    )
    return struct.unpack_from(">I", system, derived)[0]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while payload := stream.read(16 * 1024 * 1024):
            digest.update(payload)
    return digest.hexdigest()


def _hash_range(path: Path, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        stream.seek(offset)
        remaining = size
        while remaining:
            payload = stream.read(min(16 * 1024 * 1024, remaining))
            require(bool(payload), "short read while hashing range")
            digest.update(payload)
            remaining -= len(payload)
    return digest.hexdigest()


def _strict_receipt(path: Path) -> dict[str, Any]:
    metadata = _regular(path, "writer receipt")
    require(0 < metadata.st_size <= MAX_RECEIPT_BYTES, "writer receipt size is unbounded")
    raw = path.read_bytes()

    def reject_constant(value: str) -> None:
        raise VerifyError(f"writer receipt has non-JSON number {value!r}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"writer receipt duplicate key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(raw, parse_constant=reject_constant, object_pairs_hook=unique)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"writer receipt JSON is invalid: {exc}") from exc
    require(isinstance(value, dict), "writer receipt top level is not an object")
    require(raw == canonical_json_bytes(value), "writer receipt is not canonical JSON")
    return value


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
        and source.get("outer_entry_sha256") == SOURCE_OUTER_SHA256
        and source.get("source_scne_sha256") == SOURCE_SYSTEM_SHA256,
        "writer receipt source hashes differ",
    )
    require(
        result.get("output_volume_sha256") == output_sha
        and result.get("outer_entry_sha256") == OUTPUT_OUTER_SHA256
        and result.get("output_scne_sha256") == OUTPUT_SYSTEM_SHA256
        and result.get("outer_entry_size_bytes") == OUTER_SIZE,
        "writer receipt output hashes/size differ",
    )
    require(
        target.get("outer_entry_index") == OUTER_INDEX
        and target.get("inner_file_index") == INNER_INDEX
        and target.get("node_name") == "helmet_hi"
        and target.get("draw_record_index") == DRAW_RECORD_INDEX
        and target.get("material_field_byte_offset") == "0x00009a10"
        and target.get("old_material_slot") == 1
        and target.get("new_material_slot") == 2,
        "writer receipt target differs",
    )
    require(
        preservation.get("decoded_scne_changed_offsets") == ["0x00009a13"]
        and preservation.get("decoded_scne_changed_byte_count") == 1
        and preservation.get("fixed_outer_allocation_exact") is True
        and preservation.get("sibling_blocks_decoded_exact") is True
        and preservation.get("sibling_blocks_stored_exact") is True
        and preservation.get("whole_volume_outside_outer_1310_exact") is True
        and preservation.get("outside_outer_1310_prefix_sha256") == prefix_sha
        and preservation.get("outside_outer_1310_suffix_sha256") == suffix_sha,
        "writer receipt preservation proof differs",
    )
    require(
        claims.get("material_route_semantics_proved") is True
        and claims.get("visual_eagles_match_proved") is False
        and claims.get("emulator_runtime_visibility_proved") is False,
        "writer receipt claim boundary differs",
    )


def verify(source_path: Path, output_path: Path, receipt_path: Path) -> dict[str, Any]:
    source_meta, source_directory, source_raw = _read_volume(source_path, "source 0A")
    output_meta, output_directory, output_raw = _read_volume(output_path, "output 0A")
    receipt_meta = _regular(receipt_path, "writer receipt")
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
    source = _parse_entry(source_raw, SOURCE_OUTER_SHA256, "source")
    output = _parse_entry(output_raw, OUTPUT_OUTER_SHA256, "output")
    require(sha256_bytes(source.system) == SOURCE_SYSTEM_SHA256, "source SCNE hash differs")
    require(sha256_bytes(output.system) == OUTPUT_SYSTEM_SHA256, "output SCNE hash differs")
    changed = [index for index, pair in enumerate(zip(source.system, output.system)) if pair[0] != pair[1]]
    require(len(source.system) == len(output.system) and changed == [CHANGED_BYTE_OFFSET], "decoded SCNE diff is not exactly byte 0x9a13")
    require(_semantic_material_slot(source.system, "source") == 1, "source material slot is not 1")
    require(_semantic_material_slot(output.system, "output") == 2, "output material slot is not 2")
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
    require(len(output.raw) == OUTER_SIZE, "fixed outer allocation differs")

    prefix_source = _hash_range(source_path, 0, OUTER_OFFSET)
    prefix_output = _hash_range(output_path, 0, OUTER_OFFSET)
    suffix_offset = OUTER_OFFSET + OUTER_SIZE
    suffix_size = VOLUME_SIZE - suffix_offset
    suffix_source = _hash_range(source_path, suffix_offset, suffix_size)
    suffix_output = _hash_range(output_path, suffix_offset, suffix_size)
    require(prefix_source == prefix_output and suffix_source == suffix_output, "whole volume outside outer 1310 differs")
    source_sha = _hash_file(source_path)
    output_sha = _hash_file(output_path)
    receipt = _strict_receipt(receipt_path)
    _validate_receipt(receipt, source_sha, output_sha, prefix_source, suffix_source)
    return {
        "output": {
            "outer_entry_sha256": OUTPUT_OUTER_SHA256,
            "scne_sha256": OUTPUT_SYSTEM_SHA256,
            "volume_sha256": output_sha,
            "volume_size_bytes": VOLUME_SIZE,
        },
        "proof": {
            "decoded_scne_changed_offsets": ["0x00009a13"],
            "fixed_outer_allocation_exact": True,
            "material_slot_route": "helmet_hi draw 1: 1 -> 2",
            "sibling_blocks_decoded_and_stored_exact": True,
            "whole_volume_outside_outer_1310_exact": True,
        },
        "schema": VERIFY_SCHEMA,
        "source": {
            "outer_entry_sha256": SOURCE_OUTER_SHA256,
            "scne_sha256": SOURCE_SYSTEM_SHA256,
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
        payload = canonical_json_bytes(document)
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
        parser.exit(2, f"helmet shell material route verification failed: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
