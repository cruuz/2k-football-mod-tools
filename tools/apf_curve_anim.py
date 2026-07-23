#!/usr/bin/env python3
"""Inventory every APF 2K8 CurveAnim body without guessing its bit codec.

The XEX load callback proves four one-based, field-local relative pointers at
root offsets 0x0c, 0x10, 0x14, and 0x18.  This tool applies only that proved
relocation contract and preserves each resulting byte region by length/hash.

// PORTME: recover the four region element codecs from their runtime samplers.
// PORTME: map facial channels to SCNE morph targets and emit glTF animation.
// PORTME: implement serialization only after bit widths, interpolation,
//         allocation, H7A recompression, and archive integrity are proved.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

import apf_inner
import apf_outer


TYPE_NAME = "CurveAnim"
ROOT_SIZE = 0x1C
FIRST_REGION_OFFSET = 0x20
FIXED_SECOND_REGION_OFFSET = 0xD4
CONSTANT_WORD_04 = 0x2AAAAAA9
EXPECTED = (
    {
        "outer_table_index": 101,
        "outer_name_id": 0x10EF4DCC,
        "outer_name": "face_speech.iff",
        "resource_count": 2302,
        "decoded_length": 2_626_944,
        "decoded_sha256": "fd5e95c9fa99c1157ea83d66819f06a31eefe6bde4b28f5660904dbe917b7941",
    },
    {
        "outer_table_index": 598,
        "outer_name_id": 0x633DC3E4,
        "outer_name": "face_ambient.iff",
        "resource_count": 23,
        "decoded_length": 30_120,
        "decoded_sha256": "4df057a6dc9b6681b5c56e18d41be726428171dfbe1dc63e00d77464eb68783b",
    },
)


class CurveAnimError(ValueError):
    """Raised when a supplied CurveAnim corpus violates a proved invariant."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hex32(value: int) -> str:
    return f"0x{value:08x}"


def signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x1_0000_0000


def resolve_pointer(data: bytes, field_offset: int) -> tuple[int, int] | None:
    raw = struct.unpack_from(">I", data, field_offset)[0]
    if raw == 0:
        return None
    target = field_offset + signed32(raw) - 1
    if target < FIRST_REGION_OFFSET or target > len(data):
        raise CurveAnimError(
            f"pointer at 0x{field_offset:02x} resolves outside body: 0x{target:x}"
        )
    return raw, target


def parse_body(
    outer_index: int, inner_index: int, name: str, data: bytes
) -> dict[str, object]:
    identity = f"outer {outer_index} inner {inner_index} {name!r}"
    if len(data) < FIRST_REGION_OFFSET or len(data) % 8:
        raise CurveAnimError(f"{identity}: length {len(data)} is not aligned/minimal")
    words = struct.unpack_from(">7I", data, 0)
    pointers = [resolve_pointer(data, offset) for offset in (0x0C, 0x10, 0x14, 0x18)]

    if all(pointer is None for pointer in pointers):
        if not (
            name == "null"
            and len(data) == 0x20
            and words == (0, 0, 0x003C000F, 0, 0, 0, 0)
            and data[0x1C:0x20] == b"ircl"
        ):
            raise CurveAnimError(f"{identity}: unrecognized all-null root")
        return {
            "outer_table_index": outer_index,
            "inner_index": inner_index,
            "name": name,
            "length": len(data),
            "sha256": sha256(data),
            "kind": "null_sentinel",
            "root_words": [hex32(word) for word in words],
            "packed_word_08_high16": words[2] >> 16,
            "packed_word_08_low16": words[2] & 0xFFFF,
            "inline_word_1c": data[0x1C:0x20].hex(),
            "pointers": [],
            "regions": [],
        }

    if any(pointer is None for pointer in pointers):
        raise CurveAnimError(f"{identity}: partially null four-pointer root")
    if words[0] != 0 or words[1] != CONSTANT_WORD_04:
        raise CurveAnimError(f"{identity}: root constants differ")
    if (words[2] & 0xFFFF) != 0x000F:
        raise CurveAnimError(f"{identity}: packed word +0x08 low half differs")

    concrete = [pointer for pointer in pointers if pointer is not None]
    targets = [pointer[1] for pointer in concrete]
    if targets[0] != FIRST_REGION_OFFSET or targets[1] != FIXED_SECOND_REGION_OFFSET:
        raise CurveAnimError(
            f"{identity}: fixed targets are {targets[0]:#x}/{targets[1]:#x}"
        )
    if targets != sorted(targets) or targets[-1] > len(data):
        raise CurveAnimError(f"{identity}: pointer targets are not ordered/bounded")

    ends = [targets[1], targets[2], targets[3], len(data)]
    regions: list[dict[str, object]] = []
    for index, (start, end) in enumerate(zip(targets, ends)):
        region = data[start:end]
        regions.append(
            {
                "index": index,
                "offset": start,
                "end": end,
                "length": len(region),
                "sha256": sha256(region),
            }
        )
    if data[:FIRST_REGION_OFFSET] + b"".join(
        data[item["offset"] : item["end"]] for item in regions
    ) != data:
        raise CurveAnimError(f"{identity}: root/region segmentation does not rebuild")

    return {
        "outer_table_index": outer_index,
        "inner_index": inner_index,
        "name": name,
        "length": len(data),
        "sha256": sha256(data),
        "kind": "curve",
        "root_words": [hex32(word) for word in words],
        "packed_word_08_high16": words[2] >> 16,
        "packed_word_08_low16": words[2] & 0xFFFF,
        "inline_word_1c": data[0x1C:0x20].hex(),
        "pointers": [
            {
                "field_offset": offset,
                "stored_value": hex32(pointer[0]),
                "target": pointer[1],
            }
            for offset, pointer in zip((0x0C, 0x10, 0x14, 0x18), concrete)
        ],
        "regions": regions,
    }


def load_corpus(index_path: Path) -> tuple[list[dict[str, object]], list[bytes]]:
    archive = apf_outer.parse_archive(index_path)
    resources: list[dict[str, object]] = []
    decoded_blocks: list[bytes] = []
    with apf_inner.ArchiveReader(archive) as reader:
        for expected in EXPECTED:
            outer_index = expected["outer_table_index"]
            entry = archive.entries[outer_index]
            if entry.table_index != outer_index or entry.name_id != expected["outer_name_id"]:
                raise CurveAnimError(f"outer entry {outer_index} identity differs")
            record = apf_inner.parse_iff(reader, entry)
            if record.warnings or len(record.blocks) != 1:
                raise CurveAnimError(f"outer entry {outer_index} is not one clean block")
            if len(record.files) != expected["resource_count"]:
                raise CurveAnimError(f"outer entry {outer_index} file count differs")
            block = apf_inner.decode_block(reader, record, 0, 16 * 1024 * 1024)
            if len(block) != expected["decoded_length"] or sha256(block) != expected["decoded_sha256"]:
                raise CurveAnimError(f"outer entry {outer_index} decoded anchor differs")

            ranges: list[tuple[int, int]] = []
            first_resource = len(resources)
            for item in record.files:
                if item.type_name != TYPE_NAME or item.name is None:
                    raise CurveAnimError(f"outer {outer_index} contains a non-CurveAnim file")
                if len(item.parts) != 1 or item.parts[0].block_index != 0:
                    raise CurveAnimError(f"outer {outer_index} inner {item.index} has variant parts")
                part = item.parts[0]
                body = block[part.offset : part.offset + part.length]
                if len(body) != part.length:
                    raise CurveAnimError(f"outer {outer_index} inner {item.index} is truncated")
                ranges.append((part.offset, part.offset + part.length))
                resources.append(parse_body(outer_index, item.index, item.name, body))

            cursor = 0
            for start, end in sorted(ranges):
                if start != cursor:
                    raise CurveAnimError(
                        f"outer {outer_index} CurveAnim bodies do not tile block at 0x{cursor:x}"
                    )
                cursor = end
            if cursor != len(block):
                raise CurveAnimError(f"outer {outer_index} block has an unowned tail")
            decoded_blocks.append(block)
            for item in resources[first_resource:]:
                item["outer_name"] = expected["outer_name"]
    return resources, decoded_blocks


def distribution(values: Iterable[int]) -> dict[str, object]:
    sequence = list(values)
    return {
        "minimum": min(sequence),
        "maximum": max(sequence),
        "unique_count": len(set(sequence)),
    }


def build_report(index_path: Path, resources: list[dict[str, object]]) -> dict[str, object]:
    curves = [item for item in resources if item["kind"] == "curve"]
    sentinels = [item for item in resources if item["kind"] == "null_sentinel"]
    by_hash: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in resources:
        by_hash[str(item["sha256"])].append(item)
    duplicate_groups = [
        {
            "sha256": digest,
            "resources": [
                {
                    "outer_table_index": item["outer_table_index"],
                    "inner_index": item["inner_index"],
                    "name": item["name"],
                }
                for item in items
            ],
        }
        for digest, items in sorted(by_hash.items())
        if len(items) > 1
    ]
    region_lengths = {
        f"region_{index}": distribution(
            int(item["regions"][index]["length"]) for item in curves
        )
        for index in range(4)
    }
    source = []
    for expected in EXPECTED:
        source.append(
            {
                **expected,
                "outer_name_id": hex32(expected["outer_name_id"]),
            }
        )
    return {
        "schema": "apf_curve_anim_inventory/v1",
        "source_index": str(index_path),
        "sources": source,
        "pointer_rule": "target = field_offset + signed_be32(stored_value) - 1; zero means null",
        "root_layout": {
            "serialized_root_size": ROOT_SIZE,
            "opaque_inline_word_offset": 0x1C,
            "pointer_fields": [0x0C, 0x10, 0x14, 0x18],
            "fixed_targets_in_every_nonnull_body": [
                FIRST_REGION_OFFSET,
                FIXED_SECOND_REGION_OFFSET,
            ],
            "executable_proof": (
                "registered callback 0x84668c00 calls 0x84668528, which relocates "
                "all four fields; inverse callback 0x84668c50 calls 0x846684b0"
            ),
        },
        "summary": {
            "resource_count": len(resources),
            "curve_count": len(curves),
            "null_sentinel_count": len(sentinels),
            "unique_name_count": len({str(item["name"]) for item in resources}),
            "unique_body_sha256_count": len(by_hash),
            "duplicate_body_group_count": len(duplicate_groups),
            "decoded_body_bytes": sum(int(item["length"]) for item in resources),
            "relocated_pointer_count": len(curves) * 4,
            "body_length": distribution(int(item["length"]) for item in resources),
            "packed_word_08_high16": distribution(
                int(item["packed_word_08_high16"]) for item in curves
            ),
            "region_lengths": region_lengths,
            "all_bodies_tile_their_decoded_blocks": True,
        },
        "executable_evidence": {
            "type_crc32": "0xf4257702",
            "registry_descriptor": "0x82003e10",
            "load_callback": "0x84668c00",
            "inverse_callback": "0x84668c50",
            "destructor_callback": "0x84668f40",
            "load_relocator_helper": "0x84668528",
            "inverse_relocator_helper": "0x846684b0",
            "typed_lookup": "0x849cd578",
            "typed_lookup_caller": "0x849cd710",
            "resource_retaining_caller": "0x84aaa310",
        },
        "duplicate_body_groups": duplicate_groups,
        "resources": resources,
        "worked": [
            "decoded both CurveAnim-only IFF blocks and proved their 2,325 bodies tile every decoded byte",
            "applied the executable-proved four-pointer root to all 2,324 nonnull bodies",
            "bounded four ordered opaque regions in every nonnull body and retained exact hashes",
            "identified the sole explicit null sentinel without treating it as a normal curve",
        ],
        "failed": [
            "the bit-packed region element widths, interpolation modes, channel identities, and value scales remain unnamed",
            "no glTF animation or writer is emitted because morph binding and serializer capacity are not proved",
        ],
        "portme": [
            "// PORTME: decompile/runtime-test CurveAnim sampling beyond pointer relocation",
            "// PORTME: recover bit widths, time/value quantization, interpolation, and termination for all four regions",
            "// PORTME: bind CurveAnim channels to proved SCNE facial morph targets before glTF export",
            "// PORTME: implement a writer only after allocation, H7A recompression, IFF directory, and archive integrity rules are proved",
        ],
    }


def write_tsv(path: Path, resources: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "outer_table_index", "outer_name", "inner_index", "name", "kind",
        "length", "sha256", "packed_word_08_high16", "packed_word_08_low16",
        "inline_word_1c", "pointer_0", "pointer_1", "pointer_2", "pointer_3",
        "region_0_length", "region_1_length", "region_2_length", "region_3_length",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        for item in resources:
            pointers = [entry["target"] for entry in item["pointers"]]
            regions = [entry["length"] for entry in item["regions"]]
            writer.writerow(
                {
                    **{field: item.get(field, "") for field in fields},
                    **{f"pointer_{index}": value for index, value in enumerate(pointers)},
                    **{
                        f"region_{index}_length": value
                        for index, value in enumerate(regions)
                    },
                }
            )


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    parser.add_argument("--face-speech-bin", type=Path)
    parser.add_argument("--face-ambient-bin", type=Path)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        resources, blocks = load_corpus(args.index)
        report = build_report(args.index, resources)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_tsv(args.tsv, resources)
        for path, block in zip((args.face_speech_bin, args.face_ambient_bin), blocks):
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(block)
    except (CurveAnimError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "APF_CURVE_ANIM_INVENTORY_COMPLETE "
        f"resources={summary['resource_count']} curves={summary['curve_count']} "
        f"pointers={summary['relocated_pointer_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
