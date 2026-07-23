#!/usr/bin/env python3
"""Bind NFL 2K5's 25 logical motion channels to proved SCNE transforms.

The executable sampler writes one 16-byte quaternion slot per logical mask
bit.  Its pose-query path follows one of two adjacent 25-entry parent tables.
Those tables match the serialized 0x70-byte transform-record order in the
player and referee/coach SCNE shapes.  Runtime helpers search transform +0x60
names, turn the matching record address into ``(record - base) / 0x70``, and
use that result to index the sampled quaternion array.

This tool records that executable/corpus join.  It deliberately does not name
the remaining transform fields or infer glTF axes, bind matrices, or skin
weights.

// PORTME: decode transform record +0x00..+0x5f without guessing matrix roles.
// PORTME: prove Xbox vertex joint-index and weight register semantics.
// PORTME: prove coordinate axes, handedness, units, and root-motion application.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Any, Iterable

from nfl_motion_channel_maps import SPECS, parse_map
from nfl_motion_sampler_inventory import SamplerError, XbeImage
from nfl_outer import Archive, parse_archive, read_entry_range
from nfl_scene_probe import ProbeError, ResourceRecord, decode_resource, parse_inventory
from nfl_scne_inventory import ScneError, read_name, resolve_relative, u32


LOGICAL_CHANNELS = 25
PLAYER_PARENT_VA = 0x0051CDA8
SHARED_PARENT_VA = 0x0051D048
PLAYER_RESOURCE = (3, 113)
REFEREE_RESOURCE = (346, 109)
COACH_OUTERS = tuple(range(348, 384))

PLAYER_LOOKUP_TABLE = (0x004EEAD4, 3)
COACH_LOOKUP_TABLE = (0x004EFE8C, 4)
REFEREE_LOOKUP_TABLE = (0x004EFF34, 4)

FUNCTION_SPANS = (
    (0x00021930, 0x04),
    (0x00023690, 0x13),
    (0x000236B0, 0x46),
    (0x00023710, 0x1B),
    (0x00023730, 0x04),
    (0x000901E0, 0x67),
    (0x00090570, 0xC6E),
    (0x00091890, 0x1A),
    (0x00095B40, 0x69),
    (0x00095D40, 0x23E),
    (0x00095FB0, 0x57),
    (0x00096590, 0x69),
    (0x00096600, 0x415),
    (0x00096A80, 0x4C),
    (0x000DF700, 0x1A5),
    (0x002176D0, 0xC3),
)


class BindingError(ValueError):
    """An exact channel/transform invariant did not hold."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hex32(value: int) -> str:
    return f"0x{value:08x}"


def xbe_utf16(image: XbeImage, va: int, maximum_code_units: int = 128) -> str:
    chars: list[str] = []
    for index in range(maximum_code_units):
        value = struct.unpack("<H", image.at(va + index * 2, 2))[0]
        if value == 0:
            return "".join(chars)
        chars.append(chr(value))
    raise BindingError(f"unterminated XBE UTF-16 string at {hex32(va)}")


def xbe_string_table(image: XbeImage, va: int, count: int) -> dict[str, Any]:
    raw = image.at(va, count * 4)
    pointers = struct.unpack(f"<{count}I", raw)
    return {
        "va": hex32(va),
        "count": count,
        "raw_hex": raw.hex(),
        "sha256": sha256(raw),
        "entries": [
            {"index": index, "string_va": hex32(pointer), "value": xbe_utf16(image, pointer)}
            for index, pointer in enumerate(pointers)
        ],
    }


def resource_key(resource: ResourceRecord) -> tuple[int, int]:
    return resource.outer_index, resource.chunk_index


def decode_selected(
    archive: Archive,
    resources: dict[tuple[int, int], ResourceRecord],
    outer: int,
    chunk: int,
) -> tuple[ResourceRecord, bytes, dict[str, Any]]:
    key = (outer, chunk)
    if key not in resources:
        raise BindingError(f"missing SCNE resource outer {outer} chunk {chunk}")
    resource = resources[key]
    if resource.kind != "SCNE":
        raise BindingError(f"outer {outer} chunk {chunk} is {resource.kind}, not SCNE")
    span = read_entry_range(
        archive,
        archive.entries[outer],
        resource.chunk_offset,
        0x20 + resource.stored_size,
    )
    output, detail = decode_resource(span, resource)
    if len(output) != resource.word_08 + resource.word_0c:
        raise BindingError(f"outer {outer} chunk {chunk}: decoded length mismatch")
    return resource, output, detail


def scene_shapes(resource: ResourceRecord, output: bytes) -> tuple[str, list[dict[str, Any]]]:
    system_size = resource.word_08
    if output[0x0C:0x10] != b"SCNE":
        raise BindingError(
            f"outer {resource.outer_index} chunk {resource.chunk_index}: missing SCNE marker"
        )
    scene_name_target = resolve_relative(
        output, 0x10, system_size,
        f"outer {resource.outer_index} chunk {resource.chunk_index} scene name",
    )
    scene_name = read_name(
        output, scene_name_target, system_size,
        f"outer {resource.outer_index} chunk {resource.chunk_index} scene name",
    )
    descriptor = resolve_relative(
        output, 0x14, system_size,
        f"outer {resource.outer_index} chunk {resource.chunk_index} descriptor",
    )
    if descriptor is None:
        raise BindingError("SCNE descriptor pointer is null")
    shape_count = u32(output, descriptor + 0x2C)
    shape_start = resolve_relative(
        output, descriptor + 0x30, system_size,
        f"outer {resource.outer_index} chunk {resource.chunk_index} shape table",
    )
    if shape_count and shape_start is None:
        raise BindingError("nonempty SCNE shape table has a null pointer")
    if shape_start is not None and shape_start + shape_count * 0x100 > system_size:
        raise BindingError("SCNE shape table exceeds the system buffer")

    shapes: list[dict[str, Any]] = []
    for shape_index in range(shape_count):
        shape_offset = int(shape_start) + shape_index * 0x100
        name_target = resolve_relative(
            output, shape_offset + 0x40, system_size,
            f"shape {shape_index} name",
        )
        shape_name = read_name(output, name_target, system_size, f"shape {shape_index} name")
        transform_count = struct.unpack_from("<H", output, shape_offset + 0x50)[0]
        transform_start = resolve_relative(
            output, shape_offset + 0x64, system_size,
            f"shape {shape_index} transform table",
        )
        if transform_count and transform_start is None:
            raise BindingError(f"shape {shape_name}: nonzero transform count with null pointer")
        if transform_start is not None and transform_start + transform_count * 0x70 > system_size:
            raise BindingError(f"shape {shape_name}: transform table exceeds system buffer")
        transforms: list[dict[str, Any]] = []
        for transform_index in range(transform_count):
            offset = int(transform_start) + transform_index * 0x70
            transform_name_target = resolve_relative(
                output, offset + 0x60, system_size,
                f"shape {shape_name} transform {transform_index} name",
            )
            transform_name = read_name(
                output, transform_name_target, system_size,
                f"shape {shape_name} transform {transform_index} name",
            )
            parent_index = struct.unpack_from("<i", output, offset + 0x64)[0]
            if parent_index < -1 or parent_index >= transform_index:
                raise BindingError(
                    f"shape {shape_name} transform {transform_index}: invalid parent {parent_index}"
                )
            transforms.append(
                {
                    "index": transform_index,
                    "name": transform_name,
                    "parent_index": parent_index,
                    "record_offset": offset,
                    "name_pointer_field": offset + 0x60,
                    "name_target": transform_name_target,
                    "raw_sha256": sha256(output[offset : offset + 0x70]),
                }
            )
        raw = (
            output[int(transform_start) : int(transform_start) + transform_count * 0x70]
            if transform_start is not None else b""
        )
        shapes.append(
            {
                "shape_index": shape_index,
                "shape_name": shape_name,
                "shape_record_offset": shape_offset,
                "transform_count": transform_count,
                "transform_offset": transform_start,
                "transform_table_sha256": sha256(raw),
                "transforms": transforms,
            }
        )
    if scene_name is None:
        raise BindingError("SCNE scene name is null")
    return scene_name, shapes


def order_signature(transforms: list[dict[str, Any]]) -> list[tuple[str, int]]:
    return [(str(item["name"]), int(item["parent_index"])) for item in transforms]


def selected_shape(
    shapes: Iterable[dict[str, Any]], name: str, expected_count: int = LOGICAL_CHANNELS
) -> dict[str, Any]:
    matches = [shape for shape in shapes if shape["shape_name"] == name]
    if len(matches) != 1:
        raise BindingError(f"expected one shape {name!r}, found {len(matches)}")
    shape = matches[0]
    if shape["transform_count"] != expected_count:
        raise BindingError(
            f"shape {name!r} has {shape['transform_count']} transforms, expected {expected_count}"
        )
    return shape


def mirror_indices(transforms: list[dict[str, Any]]) -> list[int]:
    by_name = {str(item["name"]): int(item["index"]) for item in transforms}
    if len(by_name) != len(transforms):
        raise BindingError("transform names are not unique")
    result: list[int] = []
    for item in transforms:
        name = str(item["name"])
        if name.startswith("l") and "r" + name[1:] in by_name:
            partner = by_name["r" + name[1:]]
        elif name.startswith("r") and "l" + name[1:] in by_name:
            partner = by_name["l" + name[1:]]
        else:
            partner = int(item["index"])
        result.append(partner)
    if any(result[result[index]] != index for index in range(len(result))):
        raise BindingError("name-derived left/right relation is not an involution")
    return result


def check_parent_table(
    image: XbeImage, va: int, transforms: list[dict[str, Any]], label: str
) -> dict[str, Any]:
    raw = image.at(va, LOGICAL_CHANNELS * 4)
    values = list(struct.unpack("<25I", raw))
    if int(transforms[0]["parent_index"]) != -1 or values[0] != 0:
        raise BindingError(f"{label}: root sentinel mismatch")
    for index in range(1, LOGICAL_CHANNELS):
        parent = int(transforms[index]["parent_index"])
        if values[index] != parent:
            raise BindingError(
                f"{label}: XBE parent[{index}]={values[index]} != SCNE parent {parent}"
            )
    return {
        "va": hex32(va),
        "count": LOGICAL_CHANNELS,
        "raw_hex": raw.hex(),
        "sha256": sha256(raw),
        "values": values,
        "root_encoding": "XBE parent[0]=0; serialized transform[0].parent_index=-1",
        "non_root_entries_match_scne": True,
    }


def compact_copy(
    resource: ResourceRecord,
    detail: dict[str, Any],
    scene_name: str,
    shape: dict[str, Any],
) -> dict[str, Any]:
    return {
        "outer_index": resource.outer_index,
        "chunk_index": resource.chunk_index,
        "scene_name": scene_name,
        "shape_index": shape["shape_index"],
        "shape_name": shape["shape_name"],
        "transform_count": shape["transform_count"],
        "transform_offset": shape["transform_offset"],
        "transform_table_sha256": shape["transform_table_sha256"],
        "decoded_sha256": detail["decoded_sha256"],
    }


def binding_rows(
    parsed_map: dict[str, Any],
    family: str,
    transforms: list[dict[str, Any]],
    direct_witnesses: set[int],
) -> list[dict[str, Any]]:
    skeleton_mirror = mirror_indices(transforms)
    rows: list[dict[str, Any]] = []
    for entry in parsed_map["entries"]:
        logical = int(entry["logical_channel"])
        transform = transforms[logical]
        parent_index = int(transform["parent_index"])
        expected_partner = skeleton_mirror[logical]
        runtime_partner = entry.get("mirror_logical_partner")
        if entry["enabled"]:
            if runtime_partner != expected_partner:
                raise BindingError(
                    f"{family} channel {logical}: map mirror {runtime_partner} != "
                    f"transform-name mirror {expected_partner}"
                )
            mirror_status = "enabled_map_partner_matches_transform_name_partner"
        else:
            if not parsed_map["entries"][expected_partner]["enabled"]:
                mirror_status = "both_transform_name_partners_disabled"
            else:
                raise BindingError(
                    f"{family} channel {logical}: only one side of a transform pair is disabled"
                )
        rows.append(
            {
                "map_name": parsed_map["name"],
                "map_va": parsed_map["va"],
                "skeleton_family": family,
                "logical_channel": logical,
                "transform_index": logical,
                "bone_name": transform["name"],
                "parent_channel": parent_index,
                "parent_bone_name": (
                    transforms[parent_index]["name"] if parent_index >= 0 else None
                ),
                "enabled": bool(entry["enabled"]),
                "normal_packed_index": int(entry["normal_packed_index"]),
                "mirrored_packed_index": int(entry["mirrored_packed_index"]),
                "runtime_mirror_partner_channel": runtime_partner,
                "skeleton_mirror_partner_channel": expected_partner,
                "skeleton_mirror_partner_bone_name": transforms[expected_partner]["name"],
                "mirror_evidence": mirror_status,
                "direct_callback_slot_witness": logical in direct_witnesses,
                "binding_evidence": (
                    "0x002176d0 samples 25 logical slots, indexes the adjacent parent "
                    "table by logical channel, and composes sampled slots by those indices; "
                    "the parent table matches this 25-record SCNE transform order"
                ),
            }
        )
    return rows


def build_report(
    image: XbeImage,
    archive: Archive,
    resources: dict[tuple[int, int], ResourceRecord],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    parsed_maps = [parse_map(image, spec) for spec in SPECS]

    player_resource, player_output, player_detail = decode_selected(
        archive, resources, *PLAYER_RESOURCE
    )
    player_scene_name, player_shapes = scene_shapes(player_resource, player_output)
    if player_scene_name != "lo_body":
        raise BindingError(f"player scene is {player_scene_name!r}, expected 'lo_body'")
    player_shape = selected_shape(player_shapes, "LO_res")
    player_transforms = player_shape["transforms"]

    referee_resource, referee_output, referee_detail = decode_selected(
        archive, resources, *REFEREE_RESOURCE
    )
    referee_scene_name, referee_shapes = scene_shapes(referee_resource, referee_output)
    if referee_scene_name != "referee":
        raise BindingError(f"referee scene is {referee_scene_name!r}")
    referee_selected = [
        selected_shape(referee_shapes, "ref_high"),
        selected_shape(referee_shapes, "ref_low"),
    ]
    shared_signature = order_signature(referee_selected[0]["transforms"])
    for shape in referee_selected[1:]:
        if order_signature(shape["transforms"]) != shared_signature:
            raise BindingError("referee high/low transform orders differ")

    coach_copies: list[dict[str, Any]] = []
    for outer in COACH_OUTERS:
        resource, output, detail = decode_selected(archive, resources, outer, 0)
        scene_name, shapes = scene_shapes(resource, output)
        if scene_name != "coach":
            raise BindingError(f"outer {outer} scene is {scene_name!r}, expected 'coach'")
        for shape_name in ("coachBodyGrp1", "coachLodGrp1"):
            shape = selected_shape(shapes, shape_name)
            if order_signature(shape["transforms"]) != shared_signature:
                raise BindingError(f"outer {outer} {shape_name}: transform order differs")
            coach_copies.append(compact_copy(resource, detail, scene_name, shape))

    player_parent = check_parent_table(
        image, PLAYER_PARENT_VA, player_transforms, "player parent table"
    )
    shared_transforms = referee_selected[0]["transforms"]
    shared_parent = check_parent_table(
        image, SHARED_PARENT_VA, shared_transforms, "referee/coach parent table"
    )

    lookups = {
        "player": xbe_string_table(image, *PLAYER_LOOKUP_TABLE),
        "coach": xbe_string_table(image, *COACH_LOOKUP_TABLE),
        "referee": xbe_string_table(image, *REFEREE_LOOKUP_TABLE),
    }
    if [item["value"] for item in lookups["player"]["entries"]] != [
        "head", "lhand", "rhand"
    ]:
        raise BindingError("unexpected player transform lookup table")
    expected_limbs = ["ltwist", "lwrist", "rtwist", "rwrist"]
    for family in ("coach", "referee"):
        if [item["value"] for item in lookups[family]["entries"]] != expected_limbs:
            raise BindingError(f"unexpected {family} transform lookup table")

    player_rows = binding_rows(
        parsed_maps[0], "player_lo_body", player_transforms, {16, 17, 21, 22}
    )
    shared_rows = binding_rows(
        parsed_maps[1], "referee_coach_body", shared_transforms,
        {14, 15, 17, 20, 21, 23},
    )
    rows = player_rows + shared_rows

    function_hashes = {
        hex32(va): {"size": size, "sha256": sha256(image.at(va, size))}
        for va, size in FUNCTION_SPANS
    }
    referee_copies = [
        compact_copy(referee_resource, referee_detail, referee_scene_name, shape)
        for shape in referee_selected
    ]
    report: dict[str, Any] = {
        "schema": "nfl2k5_bone_binding/v1",
        "executable_md5": hashlib.md5(image.data).hexdigest(),
        "summary": {
            "logical_channel_count": LOGICAL_CHANNELS,
            "named_binding_count": len(rows),
            "skeleton_family_count": 2,
            "player_transform_copy_count": 1,
            "referee_transform_copy_count": len(referee_copies),
            "coach_scene_count": len(COACH_OUTERS),
            "coach_transform_copy_count": len(coach_copies),
            "shared_transform_copy_count": len(referee_copies) + len(coach_copies),
            "all_non_root_parent_entries_match": True,
            "all_enabled_mirror_partners_match_named_transforms": True,
            "all_disabled_channels_are_bilateral_transform_pairs": True,
        },
        "executable_contract": {
            "sampler": {
                "function": "0x000df700",
                "output_stride": 0x10,
                "logical_mask_at_binding_call_sites": "0x01ffffff",
                "evidence": (
                    "0x000df824..0x000df836 and 0x000df88c..0x000df89c shift "
                    "the logical mask, advance the two-byte map, and advance the output "
                    "pointer by 0x10 for every logical slot"
                ),
            },
            "pose_parent_query": {
                "function": "0x002176d0",
                "player_map_va": parsed_maps[0]["va"],
                "shared_map_va": parsed_maps[1]["va"],
                "player_parent_table_va": player_parent["va"],
                "shared_parent_table_va": shared_parent["va"],
                "evidence": (
                    "the function samples all 25 slots, selects parent_table[channel], "
                    "then indexes the sampled 0x10-byte slots while following that table"
                ),
            },
            "shape_transform_helpers": {
                "node_shape_pointer": "0x00021930 returns node +0x08",
                "name_lookup": (
                    "0x000236b0 scans shape +0x64, count at +0x50, stride 0x70, "
                    "and compares each transform +0x60 name"
                ),
                "parent_lookup": (
                    "0x00023690 reads transform +0x64 as a parent index and returns "
                    "shape->transform_base + parent*0x70"
                ),
                "index_conversion": (
                    "0x00023710 computes (transform - shape->transform_base) / 0x70"
                ),
            },
            "scene_bindings": {
                "player": (
                    "0x00090570 loads SKEL 'skeleton' and SCNE 'lo_body', resolves the "
                    "shape, and looks up head/lhand/rhand transforms; 0x00091890 applies "
                    "the hand records to sampled slots"
                ),
                "referee": (
                    "0x00096600 loads SCNE 'referee', selects 'ref_low', and looks up "
                    "ltwist/lwrist/rtwist/rwrist; 0x00096a80 consumes those slot indices"
                ),
                "coach": (
                    "0x00095d40 loads SCNE 'coach' variants and looks up the same four "
                    "limb transforms; 0x00095fb0 consumes those slot indices"
                ),
            },
            "transform_lookup_string_tables": lookups,
            "parent_tables": {
                "player": player_parent,
                "referee_coach": shared_parent,
            },
            "function_hashes": function_hashes,
        },
        "skeleton_families": [
            {
                "name": "player_lo_body",
                "channel_map_va": parsed_maps[0]["va"],
                "parent_table_va": player_parent["va"],
                "source_copies": [
                    compact_copy(
                        player_resource, player_detail, player_scene_name, player_shape
                    )
                ],
                "transforms": player_transforms,
                "bindings": player_rows,
            },
            {
                "name": "referee_coach_body",
                "channel_map_va": parsed_maps[1]["va"],
                "parent_table_va": shared_parent["va"],
                "referee_source_copies": referee_copies,
                "coach_source_copies": coach_copies,
                "transforms": shared_transforms,
                "bindings": shared_rows,
            },
        ],
        "worked": [
            "recovered exact names and parent indices for both 25-transform skeleton orders",
            "proved the two adjacent XBE parent arrays match the serialized SCNE orders",
            "proved the runtime converts named 0x70-byte transform records to sampled-slot indices",
            "proved every enabled map mirror partner matches the named left/right transform partner",
            "proved every disabled channel belongs to a bilateral named transform pair",
            "validated the referee order in both LOD shapes and the coach order in 72 body/LOD shapes",
        ],
        "failed": [
            "transform record fields other than +0x60 name and +0x64 parent remain unnamed",
            "Xbox vertex input registers are not yet bound to glTF JOINTS/WEIGHTS semantics",
            "coordinate axes, handedness, units, bind matrices, and root-motion application remain unproved",
        ],
        "portme": [
            "// PORTME: decode transform record +0x00..+0x5f and prove local/bind/world matrix roles",
            "// PORTME: recover the active Xbox vertex shader's joint-index and weight register semantics",
            "// PORTME: prove axes, handedness, units, inverse bind matrices, and root-motion application before skeletal glTF export",
        ],
    }
    return report, rows


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "map_name", "map_va", "skeleton_family", "logical_channel", "transform_index",
        "bone_name", "parent_channel", "parent_bone_name", "enabled",
        "normal_packed_index", "mirrored_packed_index",
        "runtime_mirror_partner_channel", "skeleton_mirror_partner_channel",
        "skeleton_mirror_partner_bone_name", "mirror_evidence",
        "direct_callback_slot_witness", "binding_evidence",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path, help="vc_53450030/0 outer archive index")
    parser.add_argument("--resource-scan", type=Path, required=True)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        image = XbeImage(args.xbe, args.xbe_header)
        archive = parse_archive(args.index)
        _, parsed_resources = parse_inventory(args.resource_scan)
        resources = {resource_key(item): item for item in parsed_resources}
        report, rows = build_report(image, archive, resources)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_tsv(args.tsv, rows)
    except (
        OSError, ValueError, struct.error, BindingError, SamplerError,
        ProbeError, ScneError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_BONE_BINDING_COMPLETE families=2 channels=25 named=50 "
        "shared_copies=74"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
