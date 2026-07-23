#!/usr/bin/env python3
"""Audit NFL 2K5 jersey TSET chunk 1 across all 634 uniform packages."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

from nfl_outer import Archive, Entry, parse_archive
from nfl_scene_probe import read_entry_range
from nfl_txtr import HEADER
from nfl_uniform_inventory import (
    logical_name_candidates,
    read_and_validate_span,
    relative_pointer,
    utf16z,
)
import nfl_uniform_color_xiso_direct_patch as xiso


SCHEMA = "nfl2k5_jersey_tset_compatibility/v1"
INDEX_SHA256 = "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
INVENTORY_SHA256 = "af881421c10fa01288556fec12a24ad0d8e36d6f58db8134fd956db686b0bcac"
UNIFORM_INVENTORY_SHA256 = "b9799b6f67b023f51b56695443fe2d5ff9e5ee3abc08a2c567f4c3c6cd5d04b8"
PACK_SHA256 = {
    "9": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    "A": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    "B": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
    "C": "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090",
}
FIRST_OUTER = 3613
LAST_OUTER = 4246
PACKAGE_COUNT = LAST_OUTER - FIRST_OUTER + 1
CHUNK_INDEX = 1
EXPECTED_LAYOUT = {
    "kind": "TSET",
    "chunk_index": 1,
    "chunk_offset": 112,
    "system_bytes": 256,
    "video_bytes": 176768,
    "decoded_bytes": 177024,
    "compression_magic": "0xfeedbeef",
    "reserved_words": [0, 0],
    "tset_version": 13,
    "reference_count": 2,
    "names": ["jersey00", "jersey00_mud"],
    "record_offsets": [24, 60],
    "name_offsets": [84, 102],
    "descriptor_offsets": [128, 160],
    "root_offsets": [0, 0],
    "unknown0": [0, 0],
    "pixel_offsets": [0, 0],
    "palette_offsets": [174720, 175744],
    "packed_formats": ["0x08960b29", "0x08960b29"],
    "packed_sizes": [0, 0],
    "descriptor_flags": ["0x80000000", "0x80000000"],
    "dimensions": [2, 2],
    "format_codes": [11, 11],
    "format_names": ["P8", "P8"],
    "mip_levels": [6, 6],
    "widths": [512, 512],
    "heights": [256, 256],
    "depths": [1, 1],
    "shared_index_chain_bytes": 174720,
    "palette_bytes_each": 1024,
}


class CompatibilityError(ValueError):
    """Raised when the pinned corpus or output contract is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CompatibilityError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    return sha256_bytes(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode("utf-8"))


def exclusive_write(path: Path, payload: bytes) -> tuple[int, int]:
    parent = path.parent.resolve(strict=True)
    target = parent / path.name
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    success = False
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, f"short output write at {offset}")
            offset += amount
        os.fsync(descriptor)
        info = target.stat(follow_symlinks=False)
        require((info.st_dev, info.st_ino) == identity and info.st_size == len(payload),
                "output pathname/size changed")
        success = True
        return identity
    finally:
        os.close(descriptor)
        if not success:
            try:
                info = target.stat(follow_symlinks=False)
                if (info.st_dev, info.st_ino) == identity:
                    target.unlink()
            except FileNotFoundError:
                pass


def locate_range(entry: Entry, offset: int, length: int) -> list[dict[str, int | str]]:
    require(0 <= offset and 0 <= length and offset + length <= entry.size,
            "entry range exceeds package")
    remaining_offset = offset
    remaining_length = length
    pieces: list[dict[str, int | str]] = []
    entry_cursor = 0
    for segment in entry.segments:
        if remaining_offset >= segment.size:
            remaining_offset -= segment.size
            entry_cursor += segment.size
            continue
        take = min(remaining_length, segment.size - remaining_offset)
        pieces.append({
            "pack_ordinal": segment.pack_ordinal,
            "pack_name": segment.pack_name,
            "pack_offset": segment.pack_offset + remaining_offset,
            "entry_offset": entry_cursor + remaining_offset,
            "size": take,
        })
        remaining_length -= take
        remaining_offset = 0
        entry_cursor += segment.size
        if remaining_length == 0:
            break
    require(remaining_length == 0, "entry range mapping is incomplete")
    return pieces


def parse_descriptors(decoded: bytes, system_bytes: int) -> dict[str, object]:
    require(len(decoded) >= system_bytes, "decoded system area exceeds buffer")
    version, count = struct.unpack_from("<II", decoded, 0)
    refs: list[dict[str, object]] = []
    require(0 <= count <= 32, "unreasonable TSET reference count")
    for index in range(count):
        base = 0x18 + index * 0x24
        require(base + 0x18 <= system_bytes, "reference record exceeds system area")
        require(decoded[base:base + 4] == b"TXTR", "embedded TXTR marker absent")
        name_offset = relative_pointer(decoded, base + 4, "jersey name")
        descriptor_offset = relative_pointer(decoded, base + 8, "jersey descriptor")
        root_offset = relative_pointer(decoded, base + 0x14, "jersey root")
        name = utf16z(decoded, name_offset, system_bytes, "jersey name")
        require(descriptor_offset is not None and descriptor_offset + 24 <= system_bytes,
                "jersey descriptor exceeds system area")
        assert descriptor_offset is not None
        unknown0, pixel_offset, palette_offset, packed_format, packed_size, flags = \
            struct.unpack_from("<6I", decoded, descriptor_offset)
        dimensions = (packed_format >> 4) & 0xF
        format_code = (packed_format >> 8) & 0xFF
        mip_levels = (packed_format >> 16) & 0xF
        width = packed_size & 0xFFFF if packed_size else 1 << ((packed_format >> 20) & 0xF)
        height = packed_size >> 16 if packed_size else 1 << ((packed_format >> 24) & 0xF)
        depth = 1 << ((packed_format >> 28) & 0xF)
        refs.append({
            "reference_index": index,
            "record_offset": base,
            "name": name,
            "name_offset": name_offset,
            "descriptor_offset": descriptor_offset,
            "root_offset": root_offset,
            "unknown0": unknown0,
            "pixel_offset": pixel_offset,
            "palette_offset": palette_offset,
            "packed_format": f"0x{packed_format:08x}",
            "packed_size": packed_size,
            "descriptor_flags": f"0x{flags:08x}",
            "dimensions": dimensions,
            "format_code": format_code,
            "format_name": "P8" if format_code == 11 else f"UNKNOWN_0x{format_code:02x}",
            "mip_levels": mip_levels,
            "width": width,
            "height": height,
            "depth": depth,
        })
    projection = {
        "tset_version": version,
        "reference_count": count,
        "names": [row["name"] for row in refs],
        "record_offsets": [row["record_offset"] for row in refs],
        "name_offsets": [row["name_offset"] for row in refs],
        "descriptor_offsets": [row["descriptor_offset"] for row in refs],
        "root_offsets": [row["root_offset"] for row in refs],
        "unknown0": [row["unknown0"] for row in refs],
        "pixel_offsets": [row["pixel_offset"] for row in refs],
        "palette_offsets": [row["palette_offset"] for row in refs],
        "packed_formats": [row["packed_format"] for row in refs],
        "packed_sizes": [row["packed_size"] for row in refs],
        "descriptor_flags": [row["descriptor_flags"] for row in refs],
        "dimensions": [row["dimensions"] for row in refs],
        "format_codes": [row["format_code"] for row in refs],
        "format_names": [row["format_name"] for row in refs],
        "mip_levels": [row["mip_levels"] for row in refs],
        "widths": [row["width"] for row in refs],
        "heights": [row["height"] for row in refs],
        "depths": [row["depth"] for row in refs],
    }
    return {"projection": projection, "references": refs}


def run(index: Path, inventory_path: Path, uniform_inventory_path: Path,
        source_xiso: Path) -> dict[str, object]:
    require(sha256_file(index) == INDEX_SHA256, "pack/index 0 SHA-256 mismatch")
    require(sha256_file(inventory_path) == INVENTORY_SHA256,
            "chunk inventory SHA-256 mismatch")
    require(sha256_file(uniform_inventory_path) == UNIFORM_INVENTORY_SHA256,
            "uniform inventory SHA-256 mismatch")
    inventory = json.loads(inventory_path.read_bytes())
    uniform_inventory = json.loads(uniform_inventory_path.read_bytes())
    require(inventory.get("schema") == "nfl2k5_resource_chunk_inventory/v1",
            "chunk inventory schema mismatch")
    require(uniform_inventory.get("schema") == "nfl2k5_uniform_inventory/v1" and
            len(uniform_inventory.get("packages", [])) == PACKAGE_COUNT,
            "uniform inventory schema/package count mismatch")
    packages = {int(row["outer_index"]): row for row in uniform_inventory["packages"]}
    chunks = {
        int(row["outer_index"]): row for row in inventory["chunks"]
        if FIRST_OUTER <= int(row["outer_index"]) <= LAST_OUTER and
        int(row["chunk_index"]) == CHUNK_INDEX
    }
    require(len(packages) == len(chunks) == PACKAGE_COUNT,
            "jersey package/chunk coverage mismatch")

    archive = parse_archive(index)
    logical_by_id = logical_name_candidates()
    for name, expected in PACK_SHA256.items():
        pack = next(item for item in archive.packs if item.name == name)
        require(sha256_file(pack.path) == expected, f"extracted pack {name} hash mismatch")

    source_info = source_xiso.lstat()
    require(not stat.S_ISLNK(source_info.st_mode), "source XISO must not be a symlink")
    source = source_xiso.resolve(strict=True)
    descriptor = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        identity = xiso.fd_identity(descriptor)
        require(identity == (source_info.st_dev, source_info.st_ino) and
                xiso.path_identity(source) == identity,
                "source XISO pathname changed")
        require(os.fstat(descriptor).st_size == xiso.EXPECTED_XISO_SIZE and
                xiso.sha256_fd(descriptor) == xiso.EXPECTED_XISO_SHA256,
                "source XISO size/hash mismatch")
        entries, directory = xiso.parse_xdvdfs(descriptor, xiso.EXPECTED_XISO_SIZE)
        pack_extents: dict[str, dict[str, object]] = {}
        for name, expected_hash in PACK_SHA256.items():
            path = f"vc_53450030/{name}"
            entry = entries.get(path.casefold())
            require(entry is not None, f"XDVDFS pack {name} absent")
            assert entry is not None
            archive_pack = next(item for item in archive.packs if item.name == name)
            require(entry.size == archive_pack.size and
                    xiso.sha256_fd(descriptor, entry.byte_offset, entry.size) == expected_hash,
                    f"XDVDFS/extracted pack {name} mismatch")
            pack_extents[name] = {
                "path": path,
                "sector": entry.sector,
                "byte_offset": entry.byte_offset,
                "size": entry.size,
                "sha256": expected_hash,
            }

        expected_projection = {
            key: value for key, value in EXPECTED_LAYOUT.items()
            if key not in {
                "kind", "chunk_index", "chunk_offset", "system_bytes", "video_bytes",
                "decoded_bytes", "compression_magic", "reserved_words",
                "shared_index_chain_bytes", "palette_bytes_each",
            }
        }
        expected_layout_signature = canonical_digest(EXPECTED_LAYOUT)
        rows: list[dict[str, object]] = []
        layout_counts: Counter[str] = Counter()
        allocation_counts: Counter[tuple[int, int]] = Counter()
        pack_counts: Counter[str] = Counter()
        side_counts: Counter[str] = Counter()
        for outer_index in range(FIRST_OUTER, LAST_OUTER + 1):
            package = packages[outer_index]
            item = chunks[outer_index]
            entry = archive.entries[outer_index]
            logical = logical_by_id.get(entry.name_id)
            require(logical is not None and logical.name == package["logical_name"],
                    f"outer {outer_index} logical identity mismatch")
            assert logical is not None
            record, span, decoded, info = read_and_validate_span(archive, item)
            descriptor_evidence = parse_descriptors(decoded, record.word_08)
            projection = descriptor_evidence["projection"]
            actual_layout = {
                "kind": record.kind,
                "chunk_index": record.chunk_index,
                "chunk_offset": record.chunk_offset,
                "system_bytes": record.word_08,
                "video_bytes": record.word_0c,
                "decoded_bytes": len(decoded),
                "compression_magic": f"0x{record.word_10:08x}",
                "reserved_words": list(HEADER.unpack_from(span)[6:8]),
                **projection,
                "shared_index_chain_bytes": 174720,
                "palette_bytes_each": 1024,
            }
            signature = canonical_digest(actual_layout)
            layout_counts[signature] += 1
            reasons: list[str] = []
            if actual_layout != EXPECTED_LAYOUT:
                reasons.append("layout_projection_differs")
            video = decoded[record.word_08:]
            if len(video) != 176768:
                reasons.append("video_size_differs")
            if projection != expected_projection:
                reasons.append("descriptor_projection_differs")
            span_pieces = locate_range(entry, record.chunk_offset, len(span))
            if len(span_pieces) != 1:
                reasons.append("chunk_span_crosses_pack_boundary")
            xiso_absolute: int | None = None
            source_xiso_match = False
            if len(span_pieces) == 1:
                piece = span_pieces[0]
                pack_name = str(piece["pack_name"])
                extent = pack_extents[pack_name]
                xiso_absolute = int(extent["byte_offset"]) + int(piece["pack_offset"])
                source_xiso_match = xiso.read_exact(descriptor, xiso_absolute, len(span)) == span
                if not source_xiso_match:
                    reasons.append("source_xiso_span_differs")
                pack_counts[pack_name] += 1
            else:
                pack_name = "+".join(str(piece["pack_name"]) for piece in span_pieces)
                pack_counts[pack_name] += 1
            compatible = not reasons
            allocation_counts[(record.word_14, record.stored_size)] += 1
            side_counts[logical.side_code] += 1
            rows.append({
                "selector": {
                    "asset_code": logical.asset_code,
                    "side": logical.side_code,
                    "variant": logical.variant_id,
                    "logical_name": logical.name,
                },
                "outer_index": outer_index,
                "outer_id": f"0x{entry.name_id:08x}",
                "outer_size": entry.size,
                "chunk_index": record.chunk_index,
                "chunk_offset": record.chunk_offset,
                "stored_size": record.stored_size,
                "span_size": len(span),
                "system_bytes": record.word_08,
                "video_bytes": record.word_0c,
                "decoded_size": len(decoded),
                "compression_magic": f"0x{record.word_10:08x}",
                "overlap_scratch_bytes": record.word_14,
                "stream_tag": int.from_bytes(span[HEADER.size + 4:HEADER.size + 8], "little"),
                "offset_bits": span[HEADER.size + 8],
                "wrapper_sha256": sha256_bytes(span[:HEADER.size]),
                "span_sha256": sha256_bytes(span),
                "stored_sha256": sha256_bytes(span[HEADER.size:]),
                "decoded_sha256": sha256_bytes(decoded),
                "system_sha256": sha256_bytes(decoded[:record.word_08]),
                "video_sha256": sha256_bytes(video),
                "lz_consumed_bytes": info.consumed_bytes if info is not None else None,
                "lz_unused_bytes": record.stored_size - info.consumed_bytes
                    if info is not None else None,
                "references": descriptor_evidence["references"],
                "descriptor_projection_sha256": canonical_digest(projection),
                "layout_signature_sha256": signature,
                "archive_segments": [
                    {
                        "pack_ordinal": segment.pack_ordinal,
                        "pack_name": segment.pack_name,
                        "pack_offset": segment.pack_offset,
                        "size": segment.size,
                    }
                    for segment in entry.segments
                ],
                "span_segments": span_pieces,
                "xiso_pack": pack_name,
                "xiso_absolute_span_offset": xiso_absolute,
                "source_xiso_span_matches": source_xiso_match,
                "compatible_with_shared_p8_six_mip_importer": compatible,
                "incompatibility_reasons": reasons,
                "fixed_allocation_policy": (
                    "deterministic recompression must be <= this row's stored_size; "
                    "wrapper/span size and descriptors remain unchanged"
                ),
            })

        compatible_rows = [
            row for row in rows if row["compatible_with_shared_p8_six_mip_importer"]
        ]
        require(len(rows) == PACKAGE_COUNT and
                len({(row["selector"]["asset_code"], row["selector"]["side"],
                     row["selector"]["variant"]) for row in rows}) == PACKAGE_COUNT,
                "selector rows are incomplete or ambiguous")
        classes = [
            {
                "layout_signature_sha256": signature,
                "count": count,
                "compatible": signature == expected_layout_signature,
            }
            for signature, count in sorted(layout_counts.items())
        ]
        allocation_classes = [
            {
                "overlap_scratch_bytes": scratch,
                "stored_size": stored,
                "span_size": stored + HEADER.size,
                "package_count": count,
            }
            for (scratch, stored), count in sorted(allocation_counts.items())
        ]
        return {
            "schema": SCHEMA,
            "sources": {
                "index": {"path": str(index), "sha256": INDEX_SHA256},
                "chunk_inventory": {
                    "path": str(inventory_path), "sha256": INVENTORY_SHA256,
                },
                "uniform_inventory": {
                    "path": str(uniform_inventory_path),
                    "sha256": UNIFORM_INVENTORY_SHA256,
                },
                "retail_xiso": {
                    "path": str(source), "size": xiso.EXPECTED_XISO_SIZE,
                    "sha256": xiso.EXPECTED_XISO_SHA256,
                    "opened_read_only": True,
                },
                "packs": pack_extents,
                "xdvdfs": {**directory, "file_count": len([
                    item for item in entries.values() if not (item.attributes & 0x10)
                ])},
            },
            "expected_compatible_layout": {
                **EXPECTED_LAYOUT,
                "layout_signature_sha256": expected_layout_signature,
                "allocation_rule": (
                    "stored_size and overlap_scratch_bytes are target-specific; "
                    "the rebuilt VC-LZ stream must fit without relayout"
                ),
            },
            "summary": {
                "package_count": len(rows),
                "pair_count": len(rows) // 2,
                "home_count": side_counts["H"],
                "away_count": side_counts["A"],
                "layout_class_count": len(classes),
                "allocation_class_count": len(allocation_classes),
                "compatible_package_count": len(compatible_rows),
                "incompatible_package_count": len(rows) - len(compatible_rows),
                "compatible_home_count": sum(
                    row["selector"]["side"] == "H" for row in compatible_rows
                ),
                "compatible_away_count": sum(
                    row["selector"]["side"] == "A" for row in compatible_rows
                ),
                "pack_counts": dict(sorted(pack_counts.items())),
                "stored_size_minimum": min(int(row["stored_size"]) for row in rows),
                "stored_size_maximum": max(int(row["stored_size"]) for row in rows),
                "all_spans_single_pack_segment": all(
                    len(row["span_segments"]) == 1 for row in rows
                ),
                "all_source_xiso_spans_match": all(
                    row["source_xiso_span_matches"] for row in rows
                ),
            },
            "layout_classes": classes,
            "allocation_classes": allocation_classes,
            "packages": rows,
            "claims": {
                "all_634_chunk1_packages_audited": True,
                "selectors_derived_from_pinned_inventories": True,
                "compatible_means_static_layout_only": True,
                "fixed_allocation_fit_still_required_per_import": True,
                "models_or_other_texture_chunks_supported": False,
                "runtime_visibility_proved": False,
                "xemu_started": False,
                "title_executed": False,
                "portme": (
                    "PORTME: audit other TSET chunks independently; this report proves "
                    "only jersey chunk 1 in the 634 uniform packages."
                ),
            },
        }
    finally:
        os.close(descriptor)


def tsv_payload(report: dict[str, object]) -> bytes:
    columns = (
        "asset_code", "side", "variant", "logical_name", "outer_index", "outer_id",
        "chunk_offset", "stored_size", "span_size", "overlap_scratch_bytes",
        "stream_tag", "offset_bits", "xiso_pack", "xiso_absolute_span_offset",
        "span_sha256", "decoded_sha256", "layout_signature_sha256", "compatible",
        "incompatibility_reasons",
    )
    from io import StringIO
    stream = StringIO(newline="")
    writer_csv = csv.DictWriter(stream, fieldnames=columns, delimiter="\t",
                                lineterminator="\n")
    writer_csv.writeheader()
    for row in report["packages"]:
        selector = row["selector"]
        writer_csv.writerow({
            "asset_code": selector["asset_code"],
            "side": selector["side"],
            "variant": selector["variant"],
            "logical_name": selector["logical_name"],
            "outer_index": row["outer_index"],
            "outer_id": row["outer_id"],
            "chunk_offset": row["chunk_offset"],
            "stored_size": row["stored_size"],
            "span_size": row["span_size"],
            "overlap_scratch_bytes": row["overlap_scratch_bytes"],
            "stream_tag": row["stream_tag"],
            "offset_bits": row["offset_bits"],
            "xiso_pack": row["xiso_pack"],
            "xiso_absolute_span_offset": row["xiso_absolute_span_offset"],
            "span_sha256": row["span_sha256"],
            "decoded_sha256": row["decoded_sha256"],
            "layout_signature_sha256": row["layout_signature_sha256"],
            "compatible": str(row["compatible_with_shared_p8_six_mip_importer"]).lower(),
            "incompatibility_reasons": ";".join(row["incompatibility_reasons"]),
        })
    return stream.getvalue().encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--uniform-inventory", required=True, type=Path)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-tsv", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run(args.index, args.inventory, args.uniform_inventory, args.source_xiso)
        json_payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        table_payload = tsv_payload(report)
        require(args.output_json.resolve(strict=False) != args.output_tsv.resolve(strict=False),
                "JSON/TSV output paths collide")
        json_identity = exclusive_write(args.output_json, json_payload)
        try:
            exclusive_write(args.output_tsv, table_payload)
        except Exception:
            try:
                info = args.output_json.stat(follow_symlinks=False)
                if (info.st_dev, info.st_ino) == json_identity:
                    args.output_json.unlink()
            except FileNotFoundError:
                pass
            raise
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "NFL_JERSEY_TSET_COMPATIBILITY_OK "
        f"packages={summary['package_count']} pairs={summary['pair_count']} "
        f"layouts={summary['layout_class_count']} allocations={summary['allocation_class_count']} "
        f"compatible={summary['compatible_package_count']} "
        f"incompatible={summary['incompatible_package_count']} "
        f"stored={summary['stored_size_minimum']}..{summary['stored_size_maximum']} "
        "runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
