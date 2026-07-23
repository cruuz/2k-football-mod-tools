#!/usr/bin/env python3
"""Recover NFL 2K5 motion-controller pool allocation/configuration evidence.

The report separates exact executable facts from semantic inferences.  It
proves the 11+11, seven-entry, and two-team-affiliated actor pools that install
the already recovered 23/21-channel maps.  It does not turn count/position
evidence into unproved model or bone names.

// PORTME: prove the seven-entry pool's exact model/class name from its loader.
// PORTME: prove the two-entry team-affiliated pool's exact model/class name.
// PORTME: bind logical channels to exact SCNE/SKEL bones.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from nfl_motion_sampler_inventory import SamplerError, XbeImage


CONFIG_TABLE_VA = 0x004F9E98
CONFIG_COUNT = 5
CONFIG_WORDS = 5
CONFIG_RECORD_SIZE = CONFIG_WORDS * 4


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_u32(image: XbeImage, va: int, count: int) -> tuple[int, ...]:
    return struct.unpack(f"<{count}I", image.at(va, count * 4))


def function_hashes(image: XbeImage) -> dict[str, dict[str, object]]:
    specs = (
        (0x0011A540, 0x1CB),
        (0x00074D40, 0x78),
        (0x00075B30, 0x98),
        (0x000DD6A0, 0x75),
        (0x000DDAD0, 0x60),
        (0x001D2B00, 0x40),
        (0x00217E10, 0x9A),
        (0x00217EB0, 0x6F),
        (0x00217F20, 0x6F),
    )
    return {
        f"0x{va:08x}": {"size": size, "sha256": sha256(image.at(va, size))}
        for va, size in specs
    }


def configuration_rows(image: XbeImage) -> tuple[list[dict[str, object]], bytes]:
    raw = image.at(CONFIG_TABLE_VA, CONFIG_COUNT * CONFIG_RECORD_SIZE)
    rows: list[dict[str, object]] = []
    for index in range(CONFIG_COUNT):
        words = struct.unpack_from("<5I", raw, index * CONFIG_RECORD_SIZE)
        rows.append(
            {
                "configuration_index": index,
                "side_a_actor_count": words[0],
                "side_b_actor_count": words[1],
                "seven_actor_pool_count": words[2],
                "separate_singleton_pool_count": words[3],
                "team_affiliated_actor_pool_count": words[4],
                "combined_side_actor_count": words[0] + words[1],
                "raw_words": list(words),
            }
        )
    expected = (
        (1, 1, 0, 1, 0),
        (11, 11, 0, 1, 2),
        (11, 0, 0, 1, 1),
        (11, 11, 0, 1, 2),
        (11, 11, 7, 1, 2),
    )
    if tuple(tuple(row["raw_words"]) for row in rows) != expected:
        raise SamplerError("unexpected motion actor allocation table")
    return rows, raw


def actor_records(
    image: XbeImage, va: int, count: int, name: str
) -> tuple[list[dict[str, object]], bytes]:
    raw = image.at(va, count * 0x1C)
    records: list[dict[str, object]] = []
    for index in range(count):
        offset = index * 0x1C
        words = struct.unpack_from("<7I", raw, offset)
        coordinates = struct.unpack_from("<3f", raw, offset)
        if words[3] != 21 or words[4] != index or words[5:] != (0, 0):
            raise SamplerError(f"unexpected {name} record {index}")
        records.append(
            {
                "index": index,
                "coordinate_float_bits": [f"0x{word:08x}" for word in words[:3]],
                "coordinates": [format(value, ".9g") for value in coordinates],
                "packed_quaternion_dwords_per_frame": words[3],
                "actor_or_owner_index": words[4],
                "trailing_zero_words": list(words[5:]),
            }
        )
    return records, raw


def build_report(image: XbeImage) -> dict[str, object]:
    rows, config_raw = configuration_rows(image)
    seven, seven_raw = actor_records(image, 0x0050DF00, 7, "seven-actor")
    team, team_raw = actor_records(image, 0x0050DFC4, 2, "team-affiliated")
    if [record["coordinates"] for record in team] != [
        ["0", "0", "0"], ["0", "0", "0"]
    ]:
        raise SamplerError("team-affiliated actor coordinates are not both zero")

    return {
        "schema": "nfl2k5_motion_object_pools/v1",
        "executable_md5": hashlib.md5(image.data).hexdigest(),
        "summary": {
            "configuration_count": len(rows),
            "maximum_combined_side_actor_count": max(
                int(row["combined_side_actor_count"]) for row in rows
            ),
            "maximum_seven_actor_pool_count": max(
                int(row["seven_actor_pool_count"]) for row in rows
            ),
            "maximum_team_affiliated_actor_pool_count": max(
                int(row["team_affiliated_actor_pool_count"]) for row in rows
            ),
            "all_actor_configuration_records_use_21_packed_dwords": True,
            "all_actor_configuration_indices_dense": True,
        },
        "allocation_table": {
            "va": f"0x{CONFIG_TABLE_VA:08x}",
            "record_size": CONFIG_RECORD_SIZE,
            "sha256": sha256(config_raw),
            "rows": rows,
            "consumer": {
                "function": "0x0011a540",
                "configuration_index_source": "DAT_00e5ff80 capped to 4",
                "side_pool_call": (
                    "ECX = row[0] + row[1]; call 0x00075b30"
                ),
                "seven_pool_call": "ECX = row[2]; call 0x00074d40",
                "singleton_pool_call": "ECX = row[3]; call 0x000ddad0",
                "team_affiliated_pool_call": "ECX = row[4]; call 0x000dd6a0",
            },
        },
        "motion_mapped_pools": [
            {
                "structural_name": "two_side_actor_pool",
                "head_global_va": "0x00e60268",
                "allocator": "0x00075b30",
                "allocation_count_columns": [0, 1],
                "allocation_count_rule": "side_a_actor_count + side_b_actor_count",
                "maximum_count": 22,
                "linked_record_stride": 0x50,
                "backing_record_stride": 0x15C0,
                "allocator_type_value": 1,
                "next_pointer_offset": 0x30,
                "controller_initializer": "0x00217e10",
                "channel_map_va": "0x0051cd70",
                "enabled_channel_count": 23,
                "exact_facts": (
                    "three configuration rows allocate 11+11 actors; one allocates "
                    "11+0 and one allocates 1+1"
                ),
                "semantic_inference": (
                    "on-field player pool; supported by the two 11-actor sides and "
                    "existing player/game consumers, but no source symbol survives"
                ),
                "semantic_confidence": "strong_inference_not_source_symbol",
            },
            {
                "structural_name": "seven_actor_pool",
                "head_global_va": "0x00e60274",
                "allocator": "0x00074d40",
                "allocation_count_columns": [2],
                "allocation_count_rule": "seven_actor_pool_count",
                "maximum_count": 7,
                "linked_record_stride": 0x38,
                "backing_record_stride": 0x640,
                "allocator_type_value": 2,
                "next_pointer_offset": 0x30,
                "controller_initializer": "0x00217eb0",
                "channel_map_va": "0x0051d010",
                "enabled_channel_count": 21,
                "configuration_record_table": {
                    "va": "0x0050df00",
                    "record_size": 0x1C,
                    "record_count": len(seven),
                    "sha256": sha256(seven_raw),
                    "records": seven,
                },
                "exact_facts": (
                    "only configuration index 4 allocates this pool, with seven "
                    "indexed actors and seven fixed coordinate triplets"
                ),
                "semantic_inference": (
                    "seven-official crew is consistent with count and field-position "
                    "evidence; exact model/class naming is not yet proved"
                ),
                "semantic_confidence": "plausible_inference_explicitly_unproved",
            },
            {
                "structural_name": "team_affiliated_actor_pool",
                "head_global_va": "0x00e537f4",
                "allocator": "0x000dd6a0",
                "allocation_count_columns": [4],
                "allocation_count_rule": "team_affiliated_actor_pool_count",
                "maximum_count": 2,
                "linked_record_stride": 0x3C,
                "backing_record_stride": 0x640,
                "allocator_type_value": 3,
                "next_pointer_offset": 0x38,
                "controller_initializer": "0x00217f20",
                "channel_map_va": "0x0051d010",
                "enabled_channel_count": 21,
                "configuration_record_table": {
                    "va": "0x0050dfc4",
                    "record_size": 0x1C,
                    "record_count": len(team),
                    "sha256": sha256(team_raw),
                    "records": team,
                },
                "team_binding": {
                    "function": "0x001d2b00",
                    "owner_index_source": "record +0x10 / word 4",
                    "owner_indices": [0, 1],
                    "owner_globals": ["0x00e5fc20", "0x00e5fc60"],
                },
                "exact_facts": (
                    "normal two-side configurations allocate two actors; owner indices "
                    "0 and 1 select the two team globals"
                ),
                "semantic_inference": (
                    "coach-like/team-representative actors are consistent with one per "
                    "team; the exact class/model name is not yet proved"
                ),
                "semantic_confidence": "team_affiliation_proved_role_name_unproved",
            },
        ],
        "separate_unmapped_pool": {
            "head_global_va": "0x00e537f0",
            "allocator": "0x000ddad0",
            "allocation_count_column": 3,
            "count_in_all_configurations": 1,
            "installed_by_motion_channel_initializer": False,
            "meaning": "retained separately; this pool is not assigned either recovered map",
        },
        "function_hashes": function_hashes(image),
        "worked": [
            "recovered all five exact allocation rows and their call-site column mapping",
            "proved two-side 11+11, seven-entry, and two-team-affiliated pool cardinalities",
            "proved linked/backing record strides and allocator type values",
            "joined all three actor pools to their exact 23/21-channel controller maps",
            "proved the two-entry pool selects owner globals by dense team indices 0 and 1",
        ],
        "failed": [
            "no surviving symbol proves the human-facing name of any actor pool",
            "the seven-entry pool has no loader-proved official model name yet",
            "the two-entry team-affiliated pool has no loader-proved coach model name yet",
            "logical channels remain unbound to exact skeleton bone names",
        ],
        "portme": [
            "// PORTME: trace the seven-entry pool loader to an exact model/class name",
            "// PORTME: trace the two-entry team-affiliated pool loader to an exact model/class name",
            "// PORTME: bind each 23/21 logical channel to an exact SCNE/SKEL bone",
        ],
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        image = XbeImage(args.xbe, args.xbe_header)
        report = build_report(image)
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError, SamplerError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("NFL_MOTION_OBJECT_POOLS_COMPLETE configurations=5 maxima=22/7/2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
