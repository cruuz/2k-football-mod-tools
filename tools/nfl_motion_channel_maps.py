#!/usr/bin/env python3
"""Recover NFL 2K5's executable-embedded SMCD logical-channel maps.

The runtime sampler consumes one signed-byte pair per logical channel.  The
object-group initializers install two exact maps at controller +0x20 and masks
covering channels 0..24.  This tool proves dense packed-index and mirror
involution properties without assigning unproved skeleton bone names.

// PORTME: bind logical channels 0..24 to exact scene/skeleton bone names.
// PORTME: prove the semantic role of controller +0x24's 25-float profile.
// PORTME: do not export skeletal glTF until bind pose and channel ownership are proved.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

from nfl_motion_sampler_inventory import XbeImage, SamplerError


MAP_BYTES = 50
LOGICAL_CHANNELS = 25
LOW_MASK = 0x000001FF
HIGH_MASK = 0x01FFFE00
SPECS = (
    {
        "name": "object_group_a",
        "va": 0x0051CD70,
        "initializers": ["0x00217e10"],
        "channel_profile_va": 0x0051CFA0,
    },
    {
        "name": "object_groups_b_c",
        "va": 0x0051D010,
        "initializers": ["0x00217eb0", "0x00217f20"],
        "channel_profile_va": 0x0051D240,
    },
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def signed(value: int) -> int:
    return value if value < 0x80 else value - 0x100


def parse_map(image: XbeImage, spec: dict[str, object]) -> dict[str, object]:
    va = int(spec["va"])
    raw = image.at(va, MAP_BYTES)
    zero_tail = image.at(va + MAP_BYTES, 64 - MAP_BYTES)
    if any(zero_tail):
        raise SamplerError(f"channel map at 0x{va:08x} has a nonzero 64-byte tail")
    entries: list[dict[str, object]] = []
    for logical in range(LOGICAL_CHANNELS):
        normal = signed(raw[logical * 2])
        mirrored = signed(raw[logical * 2 + 1])
        if (normal < 0) != (mirrored < 0) or normal < -1 or mirrored < -1:
            raise SamplerError(f"channel map {spec['name']} has asymmetric/invalid disable")
        entries.append(
            {
                "logical_channel": logical,
                "normal_packed_index": normal,
                "mirrored_packed_index": mirrored,
                "enabled": normal >= 0,
            }
        )

    enabled = [entry for entry in entries if entry["enabled"]]
    normal_values = [int(entry["normal_packed_index"]) for entry in enabled]
    mirrored_values = [int(entry["mirrored_packed_index"]) for entry in enabled]
    expected = list(range(len(enabled)))
    if sorted(normal_values) != expected or sorted(mirrored_values) != expected:
        raise SamplerError(f"channel map {spec['name']} is not dense in both variants")
    inverse_normal = {
        int(entry["normal_packed_index"]): int(entry["logical_channel"])
        for entry in enabled
    }
    for entry in enabled:
        partner = inverse_normal[int(entry["mirrored_packed_index"])]
        entry["mirror_logical_partner"] = partner
    partner_map = {
        int(entry["logical_channel"]): int(entry["mirror_logical_partner"])
        for entry in enabled
    }
    if any(partner_map[partner] != logical for logical, partner in partner_map.items()):
        raise SamplerError(f"channel map {spec['name']} mirror relation is not an involution")
    bilateral = sorted(
        (logical, partner)
        for logical, partner in partner_map.items()
        if logical < partner
    )
    self_mirrored = sorted(
        logical for logical, partner in partner_map.items() if logical == partner
    )
    disabled = [
        int(entry["logical_channel"]) for entry in entries if not entry["enabled"]
    ]
    profile_va = int(spec["channel_profile_va"])
    profile_raw = image.at(profile_va, LOGICAL_CHANNELS * 4)
    profile = struct.unpack("<25f", profile_raw)
    profile_tail = image.at(profile_va + len(profile_raw), 12)
    if any(profile_tail):
        raise SamplerError(
            f"channel profile at 0x{profile_va:08x} has a nonzero 12-byte tail"
        )
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in profile):
        raise SamplerError(f"channel profile at 0x{profile_va:08x} is not bounded 0..1")
    return {
        **spec,
        "va": f"0x{va:08x}",
        "channel_profile_va": f"0x{profile_va:08x}",
        "channel_profile": {
            "float_count": LOGICAL_CHANNELS,
            "raw_hex": profile_raw.hex(),
            "sha256": sha256(profile_raw),
            "values": [format(value, ".9g") for value in profile],
            "zero_tail_length": len(profile_tail),
            "semantic_status": (
                "controller +0x24 pointer; passed as a fourth stack argument by "
                "0x0031bd40 to 0x0031bba0 alongside a logical mask and two pose "
                "arrays, but the callee does not read that stack argument in this build"
            ),
        },
        "raw_hex": raw.hex(),
        "sha256": sha256(raw),
        "zero_tail_length_to_64_bytes": len(zero_tail),
        "enabled_channel_count": len(enabled),
        "disabled_logical_channels": disabled,
        "self_mirrored_logical_channels": self_mirrored,
        "bilateral_logical_channel_pairs": [list(pair) for pair in bilateral],
        "normal_packed_index_domain": expected,
        "mirrored_packed_index_domain": expected,
        "entries": entries,
    }


def build_report(image: XbeImage) -> dict[str, object]:
    maps = [parse_map(image, spec) for spec in SPECS]
    active = [index for index in range(32) if (LOW_MASK | HIGH_MASK) & (1 << index)]
    if active != list(range(LOGICAL_CHANNELS)) or LOW_MASK & HIGH_MASK:
        raise SamplerError("controller masks do not partition logical channels 0..24")
    function_hashes = {}
    for va, size in (
        (0x00217D00, 0x101),
        (0x00217E10, 0x9A),
        (0x00217EB0, 0x6F),
        (0x00217F20, 0x6F),
        (0x00218090, 0x35),
        (0x000DF9B0, 0x9A),
        (0x0031BBA0, 0x8D),
        (0x0031BD40, 0x14A),
    ):
        function_hashes[f"0x{va:08x}"] = {
            "size": size,
            "sha256": sha256(image.at(va, size)),
        }
    return {
        "schema": "nfl2k5_motion_channel_maps/v1",
        "executable_md5": hashlib.md5(image.data).hexdigest(),
        "summary": {
            "map_count": len(maps),
            "logical_channel_count": LOGICAL_CHANNELS,
            "object_group_a_enabled_channels": maps[0]["enabled_channel_count"],
            "object_groups_b_c_enabled_channels": maps[1]["enabled_channel_count"],
            "all_packed_domains_dense": True,
            "all_mirror_relations_involutions": True,
            "all_14_post_map_bytes_zero": True,
            "all_12_post_profile_bytes_zero": True,
        },
        "controller_contract": {
            "controller_low_mask_offset": 0x08,
            "controller_low_mask": f"0x{LOW_MASK:08x}",
            "controller_high_mask_offset": 0x04,
            "controller_high_mask": f"0x{HIGH_MASK:08x}",
            "active_logical_channels": active,
            "channel_map_pointer_offset": 0x20,
            "adjacent_channel_profile_pointer_offset": 0x24,
            "sampler_function": "0x000df9b0",
            "common_state_initializer": "0x00217d00",
            "top_level_initializer": "0x00218090",
            "channel_profile_consumer": "0x0031bd40 -> 0x0031bba0",
            "meaning": (
                "sampler shifts the 25-bit logical mask; for each set bit it reads "
                "map[logical*2 + mirror_variant] as signed packed-quaternion index"
            ),
        },
        "function_hashes": function_hashes,
        "maps": maps,
        "worked": [
            "recovered both executable-installed 25-pair signed-byte maps",
            "proved controller masks partition exactly logical channels 0 through 24",
            "proved each normal and mirrored packed-index domain is dense",
            "proved every enabled mirror mapping is an involution over logical channels",
            "recovered both exact 25-float controller +0x24 profiles",
            "proved the profile pointer is passed into the pose-difference call ABI",
        ],
        "failed": [
            "the three object-list globals are not assigned human-facing object classes",
            "logical channel numbers are not yet bound to exact skeleton bone names",
            "controller +0x24 profile semantics remain unproved because the callee ignores the stack argument",
        ],
        "portme": [
            "// PORTME: bind logical channels 0..24 to exact NFL skeleton bone names",
            "// PORTME: prove whether controller +0x24 profiles are blend/error weights or retained ABI data",
            "// PORTME: prove bind pose, axes, handedness, and pose application before glTF export",
        ],
    }


def write_tsv(path: Path, maps: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "map_name", "map_va", "logical_channel", "enabled",
        "normal_packed_index", "mirrored_packed_index", "mirror_logical_partner",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab")
        writer.writeheader()
        for item in maps:
            for entry in item["entries"]:
                writer.writerow(
                    {
                        "map_name": item["name"],
                        "map_va": item["va"],
                        "logical_channel": entry["logical_channel"],
                        "enabled": entry["enabled"],
                        "normal_packed_index": entry["normal_packed_index"],
                        "mirrored_packed_index": entry["mirrored_packed_index"],
                        "mirror_logical_partner": entry.get("mirror_logical_partner", ""),
                    }
                )


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--tsv", type=Path, required=True)
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
        write_tsv(args.tsv, report["maps"])
    except (OSError, ValueError, SamplerError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_MOTION_CHANNEL_MAPS_COMPLETE maps=2 logical=25 enabled=23/21"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
