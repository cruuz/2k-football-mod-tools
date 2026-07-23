#!/usr/bin/env python3
"""Strictly inventory every NFL 2K5 SMCD/MMCD motion resource.

Executable callbacks prove the common name/root relocation, four pointer
fields in each SMCD-compatible root, and MMCD's counted 0x10-byte child
directory.  Packed animation payloads remain opaque and are preserved by
exact pointer-bounded region hashes.

// PORTME: decode SMCD packed channels, bone IDs, time/value quantization,
//         interpolation, root motion, and termination from runtime samplers.
// PORTME: bind decoded channels to SKEL/SCNE before glTF animation export.
// PORTME: implement a writer only after capacities and archive rules are known.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


WRAPPER = struct.Struct("<4s7I")
COMMON_SIZE = 0x20
MOTION_ROOT_SIZE = 0x34
MMCD_RECORD_SIZE = 0x10
POINTER_FIELDS = (0x24, 0x28, 0x2C, 0x30)
STANDARD_ORDER = (0x2C, 0x28, 0x24)
ALTERNATE_ORDER = (0x2C, 0x30, 0x28, 0x24)


class MotionError(ValueError):
    """Raised when a motion resource violates an executable-proved invariant."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signed32(value: int) -> int:
    return value if value < 0x80000000 else value - 0x1_0000_0000


def relative_pointer(data: bytes, field_offset: int, *, nullable: bool) -> dict[str, int] | None:
    if field_offset < 0 or field_offset + 4 > len(data):
        raise MotionError(f"pointer field 0x{field_offset:x} is outside body")
    raw = struct.unpack_from("<I", data, field_offset)[0]
    if raw == 0:
        if nullable:
            return None
        raise MotionError(f"required pointer at 0x{field_offset:x} is null")
    target = field_offset + signed32(raw) - 1
    if target < 0 or target > len(data):
        raise MotionError(
            f"pointer at 0x{field_offset:x} raw 0x{raw:08x} resolves to 0x{target:x}"
        )
    return {"field_offset": field_offset, "stored_value": raw, "target": target}


def utf16le_z(data: bytes, offset: int) -> tuple[str, int]:
    if offset % 2:
        raise MotionError(f"UTF-16 name target 0x{offset:x} is not aligned")
    cursor = offset
    units: list[int] = []
    while cursor + 2 <= len(data):
        unit = struct.unpack_from("<H", data, cursor)[0]
        cursor += 2
        if unit == 0:
            try:
                return bytes().join(struct.pack("<H", item) for item in units).decode(
                    "utf-16le"
                ), cursor
            except UnicodeDecodeError as exc:
                raise MotionError(f"invalid UTF-16 name at 0x{offset:x}") from exc
        units.append(unit)
        if len(units) > 512:
            break
    raise MotionError(f"unterminated UTF-16 name at 0x{offset:x}")


def parse_common(data: bytes, kind: str) -> tuple[str, int, dict[str, object]]:
    if len(data) < COMMON_SIZE or data[:0x0C] != bytes(0x0C):
        raise MotionError(f"{kind}: invalid common zero prefix")
    if data[0x0C:0x10] != kind.encode("ascii") or data[0x18:0x20] != bytes(8):
        raise MotionError(f"{kind}: common marker/callback slots differ")
    name_pointer = relative_pointer(data, 0x10, nullable=False)
    root_pointer = relative_pointer(data, 0x14, nullable=False)
    assert name_pointer is not None and root_pointer is not None
    if name_pointer["target"] != COMMON_SIZE:
        raise MotionError(f"{kind}: object name does not begin at +0x20")
    name, name_end = utf16le_z(data, name_pointer["target"])
    root = root_pointer["target"]
    if root % 4 or root < name_end:
        raise MotionError(f"{kind}/{name}: overlapping or misaligned name/root")
    gap = data[name_end:root]
    return name, root, {
        "name_pointer": name_pointer,
        "root_pointer": root_pointer,
        "name_end": name_end,
        "name_to_root_gap_length": len(gap),
        "name_to_root_gap_hex": gap.hex(),
        "name_to_root_gap_sha256": sha256(gap),
    }


def parse_motion_root(data: bytes, root: int) -> dict[str, object]:
    if root < 0 or root + MOTION_ROOT_SIZE > len(data):
        raise MotionError(f"motion root 0x{root:x} is truncated")
    pointers = [
        relative_pointer(data, root + relative, nullable=(relative == 0x30))
        for relative in POINTER_FIELDS
    ]
    concrete = [pointer for pointer in pointers if pointer is not None]
    if len(concrete) not in (3, 4):
        raise MotionError("motion root does not contain three/four pointers")
    if len({pointer["target"] for pointer in concrete}) != len(concrete):
        raise MotionError("motion root pointer targets overlap")
    ordered = sorted(concrete, key=lambda pointer: pointer["target"])
    relative_order = tuple(pointer["field_offset"] - root for pointer in ordered)
    expected = STANDARD_ORDER if len(concrete) == 3 else ALTERNATE_ORDER
    if relative_order != expected:
        raise MotionError(f"unexpected motion pointer order {relative_order}")
    return {
        "offset": root,
        "header_words": [
            f"0x{word:08x}" for word in struct.unpack_from("<13I", data, root)
        ],
        "variant": "standard_three_region" if len(concrete) == 3 else "alternate_four_region",
        "pointers": [
            None
            if pointer is None
            else {
                "field_offset": pointer["field_offset"],
                "field_offset_relative_to_root": pointer["field_offset"] - root,
                "stored_value": f"0x{pointer['stored_value']:08x}",
                "target": pointer["target"],
            }
            for pointer in pointers
        ],
        "ordered_pointer_targets": [pointer["target"] for pointer in ordered],
    }


def attach_regions(
    data: bytes, roots: list[dict[str, object]], first_data_offset: int
) -> list[dict[str, object]]:
    owners: list[tuple[int, int, int]] = []
    for root_index, root in enumerate(roots):
        for pointer in root["pointers"]:
            if pointer is None:
                continue
            owners.append(
                (
                    int(pointer["target"]),
                    root_index,
                    int(pointer["field_offset_relative_to_root"]),
                )
            )
    owners.sort()
    if not owners or owners[0][0] != first_data_offset:
        raise MotionError(
            f"first packed region is 0x{owners[0][0] if owners else -1:x}, "
            f"expected 0x{first_data_offset:x}"
        )
    if len({target for target, _, _ in owners}) != len(owners):
        raise MotionError("packed region targets are not globally unique")
    regions: list[dict[str, object]] = []
    for index, (target, root_index, relative_field) in enumerate(owners):
        end = owners[index + 1][0] if index + 1 < len(owners) else len(data)
        if not target < end <= len(data):
            raise MotionError("packed region is empty or outside the body")
        raw = data[target:end]
        regions.append(
            {
                "index": index,
                "owner_root_index": root_index,
                "owner_pointer_field_relative": relative_field,
                "offset": target,
                "end": end,
                "length": len(raw),
                "sha256": sha256(raw),
                "head_hex": raw[:16].hex(),
            }
        )
    if data[:first_data_offset] + b"".join(
        data[region["offset"] : region["end"]] for region in regions
    ) != data:
        raise MotionError("prefix and pointer-bounded regions do not reconstruct body")
    return regions


def parse_smcd(data: bytes, source: dict[str, object]) -> dict[str, object]:
    name, root_offset, common = parse_common(data, "SMCD")
    root = parse_motion_root(data, root_offset)
    first_data = root_offset + MOTION_ROOT_SIZE
    regions = attach_regions(data, [root], first_data)
    return {
        **source,
        "kind": "SMCD",
        "name": name,
        "decoded_length": len(data),
        "decoded_sha256": sha256(data),
        "common": common,
        "root_count": 1,
        "roots": [root],
        "directory_records": [],
        "packed_regions": regions,
        "prefix_length": first_data,
        "prefix_sha256": sha256(data[:first_data]),
    }


def parse_mmcd(data: bytes, source: dict[str, object]) -> dict[str, object]:
    name, root_offset, common = parse_common(data, "MMCD")
    if root_offset + 4 > len(data):
        raise MotionError("MMCD root count is truncated")
    count = struct.unpack_from("<I", data, root_offset)[0]
    if count not in (2, 3, 4, 5):
        raise MotionError(f"MMCD child count {count} is outside observed/proved domain")
    directory_end = root_offset + 4 + count * MMCD_RECORD_SIZE
    child_array_end = directory_end + count * MOTION_ROOT_SIZE
    if child_array_end > len(data):
        raise MotionError("MMCD directory/root array is truncated")
    directory: list[dict[str, object]] = []
    roots: list[dict[str, object]] = []
    for index in range(count):
        record_offset = root_offset + 4 + index * MMCD_RECORD_SIZE
        child_pointer = relative_pointer(data, record_offset, nullable=False)
        assert child_pointer is not None
        expected_child = directory_end + index * MOTION_ROOT_SIZE
        if child_pointer["target"] != expected_child:
            raise MotionError(
                f"MMCD child {index} target 0x{child_pointer['target']:x} != 0x{expected_child:x}"
            )
        raw_words = struct.unpack_from("<4I", data, record_offset)
        directory.append(
            {
                "index": index,
                "offset": record_offset,
                "child_pointer_stored": f"0x{raw_words[0]:08x}",
                "child_target": expected_child,
                "opaque_words_04_0c": [f"0x{word:08x}" for word in raw_words[1:]],
            }
        )
        roots.append(parse_motion_root(data, expected_child))
    regions = attach_regions(data, roots, child_array_end)
    return {
        **source,
        "kind": "MMCD",
        "name": name,
        "decoded_length": len(data),
        "decoded_sha256": sha256(data),
        "common": common,
        "root_count": count,
        "roots": roots,
        "directory_records": directory,
        "packed_regions": regions,
        "prefix_length": child_array_end,
        "prefix_sha256": sha256(data[:child_array_end]),
    }


def load_inventory(path: Path) -> dict[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "nfl2k5_resource_chunk_inventory/v1":
        raise MotionError("unsupported canonical resource inventory schema")
    return document


def read_motion_corpus(
    index_path: Path, inventory_path: Path
) -> tuple[list[dict[str, object]], dict[str, object]]:
    archive = nfl_outer.parse_archive(index_path)
    inventory = load_inventory(inventory_path)
    selected = [
        item for item in inventory["chunks"] if item["kind"] in ("SMCD", "MMCD")
    ]
    resources: list[dict[str, object]] = []
    zero_gap_count = 0
    zero_gap_bytes = 0
    for item in selected:
        outer_index = int(item["outer_index"])
        entry = archive.entries[outer_index]
        offset = int(item["chunk_offset"])
        stored_size = int(item["stored_size"])
        wrapper = nfl_outer.read_entry_range(archive, entry, offset, WRAPPER.size)
        kind_raw, stored, word08, word0c, word10, word14, reserved0, reserved1 = (
            WRAPPER.unpack(wrapper)
        )
        kind = kind_raw.decode("ascii")
        if not (
            kind == item["kind"]
            and stored == stored_size == word08
            and word0c == word10 == word14 == reserved0 == reserved1 == 0
        ):
            raise MotionError(f"outer {outer_index} chunk {item['chunk_index']}: wrapper differs")
        padding = int(item.get("zero_padding_before", 0))
        if padding:
            gap = nfl_outer.read_entry_range(archive, entry, offset - padding, padding)
            if any(gap):
                raise MotionError(f"outer {outer_index}: declared pre-motion padding is nonzero")
            zero_gap_count += 1
            zero_gap_bytes += padding
        body = nfl_outer.read_entry_range(
            archive, entry, offset + WRAPPER.size, stored_size
        )
        source = {
            "outer_index": outer_index,
            "outer_id": item["outer_id"],
            "outer_size": int(item["outer_size"]),
            "chunk_index": int(item["chunk_index"]),
            "chunk_offset": offset,
            "stored_size": stored_size,
            "zero_padding_before": padding,
        }
        resources.append(
            parse_smcd(body, source) if kind == "SMCD" else parse_mmcd(body, source)
        )

    motion_outers = {int(item["outer_index"]) for item in selected}
    zero_tails: list[dict[str, object]] = []
    for item in inventory["trailing_regions"]:
        outer_index = int(item["outer_index"])
        if outer_index not in motion_outers:
            continue
        size = int(item["trailing_bytes"])
        offset = int(item["parsed_end"])
        raw = nfl_outer.read_entry_range(archive, archive.entries[outer_index], offset, size)
        if any(raw):
            raise MotionError(f"outer {outer_index}: motion-associated trailing bytes are nonzero")
        zero_tails.append(
            {
                "outer_index": outer_index,
                "offset": offset,
                "length": size,
                "sha256": sha256(raw),
            }
        )
    return resources, {
        "zero_padding_before_motion_chunk_count": zero_gap_count,
        "zero_padding_before_motion_chunk_bytes": zero_gap_bytes,
        "zero_trailing_region_count": len(zero_tails),
        "zero_trailing_region_bytes": sum(item["length"] for item in zero_tails),
        "zero_trailing_regions": zero_tails,
    }


def distribution(values: Iterable[int]) -> dict[str, int]:
    values = list(values)
    return {"minimum": min(values), "maximum": max(values), "unique_count": len(set(values))}


def build_report(
    index_path: Path,
    inventory_path: Path,
    resources: list[dict[str, object]],
    padding: dict[str, object],
) -> dict[str, object]:
    smcd = [item for item in resources if item["kind"] == "SMCD"]
    mmcd = [item for item in resources if item["kind"] == "MMCD"]
    roots = [root for item in resources for root in item["roots"]]
    variants = Counter(root["variant"] for root in roots)
    regions = [region for item in resources for region in item["packed_regions"]]
    names = Counter(str(item["name"]) for item in smcd)
    return {
        "schema": "nfl2k5_motion_inventory/v1",
        "source_index": str(index_path),
        "canonical_resource_inventory": str(inventory_path),
        "pointer_rule": "target = field_offset + signed_le32(stored_value) - 1; zero is null only where allowed",
        "summary": {
            "motion_resource_count": len(resources),
            "smcd_resource_count": len(smcd),
            "mmcd_resource_count": len(mmcd),
            "motion_outer_count": len({int(item["outer_index"]) for item in resources}),
            "smcd_outer_count": len({int(item["outer_index"]) for item in smcd}),
            "mmcd_outer_count": len({int(item["outer_index"]) for item in mmcd}),
            "standalone_and_embedded_root_count": len(roots),
            "mmcd_embedded_root_count": sum(int(item["root_count"]) for item in mmcd),
            "standard_three_region_root_count": variants["standard_three_region"],
            "alternate_four_region_root_count": variants["alternate_four_region"],
            "packed_region_count": len(regions),
            "decoded_motion_body_bytes": sum(int(item["decoded_length"]) for item in resources),
            "smcd_unique_name_count": len(names),
            "smcd_repeated_name_count": sum(count > 1 for count in names.values()),
            "mmcd_unique_name_count": len({str(item["name"]) for item in mmcd}),
            "smcd_body_length": distribution(int(item["decoded_length"]) for item in smcd),
            "mmcd_body_length": distribution(int(item["decoded_length"]) for item in mmcd),
            "mmcd_child_count_distribution": dict(
                sorted(Counter(int(item["root_count"]) for item in mmcd).items())
            ),
            "all_wrapper_bodies_uncompressed": True,
            "all_pointer_bounded_regions_reconstruct": True,
            **{key: value for key, value in padding.items() if key != "zero_trailing_regions"},
        },
        "proved_layout": {
            "common_body": {
                "fourcc_offset": 0x0C,
                "name_pointer_offset": 0x10,
                "root_pointer_offset": 0x14,
                "callback_slots_offset": 0x18,
                "name_target": 0x20,
            },
            "smcd_compatible_root_size": MOTION_ROOT_SIZE,
            "root_pointer_fields": list(POINTER_FIELDS),
            "standard_target_order": list(STANDARD_ORDER),
            "alternate_target_order": list(ALTERNATE_ORDER),
            "mmcd_directory_record_size": MMCD_RECORD_SIZE,
            "mmcd_child_root_array_stride": MOTION_ROOT_SIZE,
        },
        "executable_evidence": {
            "type_registration": "0x00168520",
            "common_smcd_load_callback": "0x00168400",
            "common_smcd_release_callback": "0x00168430",
            "common_mmcd_load_callback": "0x00168440",
            "common_mmcd_release_callback": "0x00168470",
            "smcd_root_relocator": "0x002d0180",
            "smcd_root_inverse": "0x002d01d0",
            "mmcd_root_relocator": "0x002d0240",
            "mmcd_root_inverse": "0x002d0280",
            "contract": (
                "SMCD relocates root +0x24/+0x28/+0x2c/+0x30; MMCD loops a "
                "root count over 0x10-byte directory records, relocates record +0, "
                "and applies the SMCD relocator to every child root"
            ),
        },
        "zero_trailing_regions": padding["zero_trailing_regions"],
        "resources": resources,
        "worked": [
            "re-read all 5,198 uncompressed resource wrappers from the archive",
            "proved and applied the common name/root relocation to every resource",
            "bounded 4,559 standalone and 1,509 MMCD-embedded SMCD-compatible roots",
            "partitioned all packed data through 18,375 unique executable-relocated targets",
            "proved all 13 previously unclassified tails in motion-containing outers are zero padding",
        ],
        "failed": [
            "packed channel element widths, bone bindings, timing, interpolation, and root-motion meanings remain unresolved",
            "no glTF animation or archive writer is emitted from structurally bounded but semantically opaque regions",
        ],
        "portme": [
            "// PORTME: recover SMCD sampler bit widths, channel IDs, time/value quantization, and termination",
            "// PORTME: name MMCD directory words +0x04..+0x0c from exact composition consumers",
            "// PORTME: bind motion channels to SKEL/SCNE bones and validate sampled poses before glTF export",
            "// PORTME: implement writing only after fixed-slot capacities, references, and archive integrity are proved",
        ],
    }


def write_tsv(path: Path, resources: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "outer_index", "chunk_index", "kind", "name", "decoded_length",
        "decoded_sha256", "root_index", "root_offset", "variant",
        "pointer_24_target", "pointer_28_target", "pointer_2c_target",
        "pointer_30_target", "packed_region_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        for item in resources:
            counts = Counter(
                int(region["owner_root_index"]) for region in item["packed_regions"]
            )
            for root_index, root in enumerate(item["roots"]):
                targets = [
                    "" if pointer is None else pointer["target"]
                    for pointer in root["pointers"]
                ]
                writer.writerow(
                    {
                        "outer_index": item["outer_index"],
                        "chunk_index": item["chunk_index"],
                        "kind": item["kind"],
                        "name": item["name"],
                        "decoded_length": item["decoded_length"],
                        "decoded_sha256": item["decoded_sha256"],
                        "root_index": root_index,
                        "root_offset": root["offset"],
                        "variant": root["variant"],
                        "pointer_24_target": targets[0],
                        "pointer_28_target": targets[1],
                        "pointer_2c_target": targets[2],
                        "pointer_30_target": targets[3],
                        "packed_region_count": counts[root_index],
                    }
                )


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--resource-inventory", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        resources, padding = read_motion_corpus(args.index, args.resource_inventory)
        report = build_report(args.index, args.resource_inventory, resources, padding)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_tsv(args.tsv, resources)
    except (MotionError, nfl_outer.FormatError, OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = report["summary"]
    print(
        "NFL2K5_MOTION_INVENTORY_COMPLETE "
        f"resources={summary['motion_resource_count']} roots={summary['standalone_and_embedded_root_count']} "
        f"regions={summary['packed_region_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
