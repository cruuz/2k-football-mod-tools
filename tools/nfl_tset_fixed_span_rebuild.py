#!/usr/bin/env python3
"""Build the pinned Lions jersey TSET identity span with deterministic VC-LZ.

The tool reads retail outer 3685/chunk 1, recompresses its decoded bytes, and
O_EXCL-writes a same-size span whose unused stored tail is zero padded.  It
also performs an in-memory one-byte palette mutation to quantify non-identity
headroom.  No archive or disc image is modified.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from nfl_outer import parse_archive
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    decode_chunk,
    rebuild_compressed_chunk_fixed_span,
)
from nfl_uniform_inventory import (
    logical_name_candidates,
    parse_tset,
    read_and_validate_span,
)


SCHEMA = "nfl2k5_tset_fixed_span_rebuild/v1"
TARGET_OUTER = 3685
TARGET_CHUNK = 1
TARGET_ID = 0x9A4832D6
TARGET_NAME = "09H0.IFF"
TARGET_PACK = "A"
TARGET_PACK_OFFSET = 0x055CA800
TARGET_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
TARGET_DECODED_SHA256 = "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e"
RETAIL_STREAM_SHA256 = "f83c0b59a59a744fdbd1f8b91172ec882203b70a5bc76e2b888b239f3b724706"
REBUILT_SPAN_SHA256 = "a802389334ad0e895557a9047f24381eb0f3ed9eefc77a7572a87ac64f56c9a9"
MUTATION_SPAN_SHA256 = "1a1ae6f6612563e0cf7736186cb5a10619c01e70eea405dab374e9d1e842a97a"
OUTPUT_ARTIFACT_NAME = "nfl2k5_lions_09H0_tset1_identity_zero_pad.bin"
INVENTORY_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"


class RebuildError(ValueError):
    """Raised when the pinned target or output ownership fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RebuildError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_new_path(path: Path) -> Path:
    require(path.name not in {"", ".", ".."}, "invalid output filename")
    parent = path.parent.resolve(strict=True)
    require(parent.is_dir(), f"output parent is not a directory: {parent}")
    return parent / path.name


def write_exclusive(path: Path, value: bytes) -> tuple[int, int]:
    target = canonical_new_path(path)
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        position = 0
        while position < len(value):
            written = os.write(descriptor, value[position:])
            require(written > 0, f"short output write at 0x{position:x}")
            position += written
        os.fsync(descriptor)
        require(os.fstat(descriptor).st_size == len(value), "output size mismatch")
        current = target.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino) == identity,
                "output pathname identity changed")
        success = True
        return identity
    finally:
        os.close(descriptor)
        if not success:
            owned_unlink(target, identity)


def owned_unlink(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        current = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == identity:
        path.unlink()


def build(index: Path, inventory_path: Path) -> tuple[bytes, dict[str, object]]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    require(inventory.get("schema") == INVENTORY_SCHEMA, "inventory schema mismatch")
    item = next(
        (
            row for row in inventory["chunks"]
            if int(row["outer_index"]) == TARGET_OUTER and
            int(row["chunk_index"]) == TARGET_CHUNK
        ),
        None,
    )
    require(item is not None, "pinned Lions TSET inventory row is absent")
    assert item is not None
    archive = parse_archive(index)
    entry = archive.entries[TARGET_OUTER]
    require(entry.name_id == TARGET_ID and len(entry.segments) == 1,
            "pinned Lions outer identity/segmentation mismatch")
    segment = entry.segments[0]
    require(segment.pack_name == TARGET_PACK and
            segment.pack_offset == TARGET_PACK_OFFSET,
            "pinned Lions outer pack mapping mismatch")
    logical = logical_name_candidates().get(entry.name_id)
    require(logical is not None and logical.name == TARGET_NAME,
            "pinned Lions logical name mismatch")
    assert logical is not None

    record, span, decoded, decode_info = read_and_validate_span(archive, item)
    require(decode_info is not None, "pinned Lions TSET is not compressed")
    require(record.kind == "TSET" and record.chunk_offset == 0x70 and
            record.stored_size == 74688 and len(span) == 74720,
            "pinned Lions TSET wrapper/span mismatch")
    require(sha256_bytes(span) == TARGET_SPAN_SHA256 and
            sha256_bytes(decoded) == TARGET_DECODED_SHA256,
            "pinned Lions TSET source hash mismatch")
    summary, references, _ = parse_tset(decoded, record, logical, None)
    require([row["name"] for row in references] == ["jersey00", "jersey00_mud"],
            "pinned Lions TSET embedded names mismatch")

    stream_tag = int.from_bytes(span[HEADER.size + 4:HEADER.size + 8], "little")
    offset_bits = span[HEADER.size + 8]
    encoded, compression_info = compress_vc_lz(
        decoded,
        stream_tag=stream_tag,
        offset_bits=offset_bits,
        max_encoded_size=record.stored_size,
    )
    retail_stream = span[HEADER.size:HEADER.size + decode_info.consumed_bytes]
    require(encoded == retail_stream and sha256_bytes(encoded) == RETAIL_STREAM_SHA256,
            "deterministic encoder did not reproduce the retail stream")

    rebuilt, rebuild_info = rebuild_compressed_chunk_fixed_span(span, decoded)
    require(rebuild_info.rebuilt_span_sha256 == REBUILT_SPAN_SHA256,
            "identity rebuilt-span hash mismatch")
    require(rebuild_info.recompressed_bytes == 74674 and
            rebuild_info.zero_padding_bytes == 14 and
            rebuild_info.compressed_stream_matches_template,
            "identity rebuilt-span size/stream mismatch")
    require(rebuilt[74706:] == bytes(14), "identity rebuilt span is not zero padded")
    rebuilt_decoded, rebuilt_decode_info = decode_chunk(rebuilt, record.as_chunk())
    require(rebuilt_decode_info is not None and rebuilt_decoded == decoded and
            rebuilt_decode_info.consumed_bytes == 74674,
            "identity rebuilt span failed independent decode")
    differences = [
        index for index, (before, after) in enumerate(zip(span, rebuilt))
        if before != after
    ]
    require(differences == list(range(74706, 74720)),
            "identity rebuilt span differs outside old padding")

    palette_probe_offset = record.word_08 + int(references[0]["palette_offset"])
    palette_probe = bytearray(decoded)
    before_byte = palette_probe[palette_probe_offset]
    palette_probe[palette_probe_offset] ^= 0x55
    after_byte = palette_probe[palette_probe_offset]
    mutated_span, mutation_info = rebuild_compressed_chunk_fixed_span(
        span, bytes(palette_probe)
    )
    require(mutation_info.recompressed_bytes == 74675 and
            mutation_info.zero_padding_bytes == 13 and
            mutation_info.rebuilt_span_sha256 == MUTATION_SPAN_SHA256,
            "one-byte palette mutation fixed-span result mismatch")
    mutation_decoded, mutation_decode_info = decode_chunk(
        mutated_span, record.as_chunk()
    )
    require(mutation_decode_info is not None and
            mutation_decoded == bytes(palette_probe) and
            mutation_decode_info.consumed_bytes == 74675,
            "one-byte palette mutation failed independent decode")

    report: dict[str, object] = {
        "schema": SCHEMA,
        "source_index": str(index),
        "canonical_inventory": str(inventory_path),
        "target": {
            "logical_name": TARGET_NAME,
            "outer_index": TARGET_OUTER,
            "outer_id": f"0x{TARGET_ID:08x}",
            "pack": TARGET_PACK,
            "outer_pack_offset": TARGET_PACK_OFFSET,
            "chunk_index": TARGET_CHUNK,
            "chunk_offset": record.chunk_offset,
            "kind": record.kind,
            "stored_size": record.stored_size,
            "complete_span_size": len(span),
            "system_bytes": record.word_08,
            "video_bytes": record.word_0c,
            "compression_magic": "0xfeedbeef",
            "overlap_scratch_bytes": record.word_14,
            "embedded_names": [row["name"] for row in references],
            "source_span_sha256": sha256_bytes(span),
            "decoded_sha256": sha256_bytes(decoded),
        },
        "retail_stream": {
            "stream_tag": stream_tag,
            "offset_bits": offset_bits,
            "consumed_bytes": decode_info.consumed_bytes,
            "unused_bytes": record.stored_size - decode_info.consumed_bytes,
            "unused_tail_hex": span[
                HEADER.size + decode_info.consumed_bytes:
            ].hex(),
            "sha256": sha256_bytes(retail_stream),
        },
        "compression": asdict(compression_info),
        "identity_rebuild": {
            **asdict(rebuild_info),
            "artifact_name": OUTPUT_ARTIFACT_NAME,
            "complete_span_size_preserved": len(rebuilt) == len(span),
            "decoded_bytes_equal": rebuilt_decoded == decoded,
            "independent_decode_consumed_bytes": rebuilt_decode_info.consumed_bytes,
            "source_vs_rebuilt_changed_byte_count": len(differences),
            "source_vs_rebuilt_changed_range": [differences[0], differences[-1]],
            "only_original_padding_changed": True,
        },
        "one_byte_palette_probe": {
            "decoded_offset": palette_probe_offset,
            "texture": "jersey00",
            "palette_offset": references[0]["palette_offset"],
            "before_byte": before_byte,
            "after_byte": after_byte,
            "xor_mask": "0x55",
            "recompressed_bytes": mutation_info.recompressed_bytes,
            "zero_padding_bytes": mutation_info.zero_padding_bytes,
            "rebuilt_span_sha256": mutation_info.rebuilt_span_sha256,
            "decoded_sha256": mutation_info.decoded_sha256,
            "decoded_bytes_equal": mutation_decoded == bytes(palette_probe),
            "independent_decode_consumed_bytes": mutation_decode_info.consumed_bytes,
            "fits_original_stored_body": mutation_info.recompressed_bytes <= record.stored_size,
            "artifact_written": False,
        },
        "claims": {
            "retail_stream_reproduced_exactly": True,
            "identity_fixed_span_rebuild_proved": True,
            "zero_padding_proved": True,
            "nonidentity_fixed_span_rebuild_proved": True,
            "general_png_importer": False,
            "xiso_created": False,
            "title_executed": False,
            "portme": (
                "PORTME: add bounded PNG-to-P8 quantization, mip regeneration, and "
                "descriptor-aware palette/index replacement before claiming PNG import."
            ),
        },
    }
    return rebuilt, report


def run(index: Path, inventory: Path, output_span: Path, output_report: Path) -> dict[str, object]:
    span_path = canonical_new_path(output_span)
    report_path = canonical_new_path(output_report)
    require(span_path != report_path, "span and report paths must differ")
    require(span_path.name == OUTPUT_ARTIFACT_NAME,
            f"output span must be named {OUTPUT_ARTIFACT_NAME}")
    require(not span_path.exists() and not report_path.exists(),
            "output span/report already exists")
    rebuilt, report = build(index, inventory)
    span_identity: tuple[int, int] | None = None
    report_identity: tuple[int, int] | None = None
    success = False
    try:
        span_identity = write_exclusive(span_path, rebuilt)
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        report_identity = write_exclusive(report_path, payload)
        require(sha256_bytes(span_path.read_bytes()) == REBUILT_SPAN_SHA256,
                "written span readback hash mismatch")
        require(json.loads(report_path.read_bytes()) == report,
                "written report readback mismatch")
        success = True
        return report
    finally:
        if not success:
            owned_unlink(report_path, report_identity)
            owned_unlink(span_path, span_identity)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--output-span", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = run(args.index, args.inventory, args.output_span, args.output_report)
    except (OSError, TxtrError, RebuildError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_TSET_FIXED_SPAN_REBUILD_OK "
        f"target=09H0 chunk=1 encoded={result['compression']['encoded_bytes']}/74688 "
        "zero_pad=14 exact_stream=true palette_probe=74675/74688 xiso=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
