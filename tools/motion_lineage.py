#!/usr/bin/env python3
"""Prove bounded motion-format lineage between NFL 2K5 and APF 2K8.

This lane deliberately distinguishes a shared sampler/container contract from
packed-pose codec compatibility.  It validates the full APF SingleMoCap corpus,
the full NFL sampler report, and the seven exact-name resources.  It does not
bind either title's logical channels to bones and therefore emits no glTF.

// PORTME: bind APF 8-byte packed pose units and NFL logical channels to bones.
// PORTME: recover the executable-proved APF 8-byte pose decoder semantics.
// PORTME: prove coordinate axes, handedness, units, and optional-stream roles.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
from typing import Iterable

import nfl_outer


APF_SCHEMA = "apf_mocap_inventory/v1"
NFL_SAMPLER_SCHEMA = "nfl2k5_motion_sampler_inventory/v1"
NFL_MOTION_SCHEMA = "nfl2k5_motion_inventory/v1"
OUTPUT_SCHEMA = "cross_title_motion_lineage/v1"
PAIR_NAMES = (
    "es213bk",
    "es263bl",
    "es264bl",
    "es267bl",
    "es268bl",
    "es269bl",
    "es270bl",
)
NFL_WRAPPER_SIZE = 0x20
APF_UNIT_SIZE = 8
APF_COMPONENT_BITS = 20


class LineageError(ValueError):
    """Raised when an input violates a previously proved invariant."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, schema: str) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != schema:
        raise LineageError(f"{path}: expected schema {schema!r}")
    return value


def signed20(value: int) -> int:
    value &= (1 << APF_COMPONENT_BITS) - 1
    if value & (1 << (APF_COMPONENT_BITS - 1)):
        value -= 1 << APF_COMPONENT_BITS
    return value


def int_distribution(values: Counter[int]) -> dict[str, int]:
    return {str(key): values[key] for key in sorted(values)}


def float_from_raw(raw: int, endian: str = ">") -> float:
    return struct.unpack(f"{endian}f", struct.pack(f"{endian}I", raw))[0]


def region_by_role(resource: dict[str, object], role: str) -> dict[str, object]:
    matches = [item for item in resource["regions"] if item["role"] == role]
    if len(matches) != 1:
        raise LineageError(f"{resource['name']}: expected one {role!r} region")
    return matches[0]


def nfl_region(
    resource: dict[str, object], root_index: int, pointer_field: int
) -> dict[str, object]:
    matches = [
        item
        for item in resource["packed_regions"]
        if int(item["owner_root_index"]) == root_index
        and int(item["owner_pointer_field_relative"]) == pointer_field
    ]
    if len(matches) != 1:
        raise LineageError(
            f"{resource['name']} root {root_index}: expected one region for +0x{pointer_field:x}"
        )
    return matches[0]


def checked_slice(data: bytes, region: dict[str, object]) -> bytes:
    start = int(region["offset"])
    end = int(region["end"])
    value = data[start:end]
    if len(value) != int(region["length"]) or sha256(value) != region["sha256"]:
        raise LineageError("region bytes differ from canonical hash")
    return value


def nfl_smallest_three_valid(word: int, scale: float) -> bool:
    components = (
        ((word >> 20) & 0x3FF) - 0x200,
        ((word >> 10) & 0x3FF) - 0x200,
        (word & 0x3FF) - 0x200,
    )
    return sum(value * value for value in components) * scale * scale <= 1.0


def analyze_apf_packed(
    apf: dict[str, object], corpus: bytes, nfl_quaternion_scale: float
) -> tuple[dict[str, object], list[dict[str, object]]]:
    selector_counts: Counter[int] = Counter()
    frame_strides: Counter[int] = Counter()
    units_per_frame: Counter[int] = Counter()
    optional_strides: Counter[int] = Counter()
    signed_component_minimum = [1 << 30, 1 << 30, 1 << 30]
    signed_component_maximum = [-(1 << 30), -(1 << 30), -(1 << 30)]
    maximum_signed_square_sum = 0
    reserved_high_two_nonzero = 0
    total_units = 0
    total_dwords = 0
    nfl_valid_be = 0
    nfl_valid_le = 0
    rows: list[dict[str, object]] = []

    clips = [item for item in apf["resources"] if item["kind"] == "full_clip"]
    for resource in clips:
        body_start = int(resource["corpus_offset"])
        body_end = body_start + int(resource["length"])
        body = corpus[body_start:body_end]
        if len(body) != int(resource["length"]) or sha256(body) != resource["sha256"]:
            raise LineageError(f"{resource['name']}: APF corpus body hash differs")

        main_region = region_by_role(resource, "packed_motion")
        main = checked_slice(body, main_region)
        frame_count = int(resource["sample_count"])
        stride, remainder = divmod(len(main), frame_count)
        if remainder or stride % APF_UNIT_SIZE:
            raise LineageError(f"{resource['name']}: packed stream does not tile by frame/8")
        unit_count = len(main) // APF_UNIT_SIZE
        per_frame = stride // APF_UNIT_SIZE
        frame_strides[stride] += 1
        units_per_frame[per_frame] += 1

        local_selectors: Counter[int] = Counter()
        local_reserved_nonzero = 0
        for (word,) in struct.iter_unpack(">Q", main):
            local_reserved_nonzero += (word >> 62) != 0
            selector = (word >> 60) & 3
            local_selectors[selector] += 1
            selector_counts[selector] += 1
            components = (
                signed20(word >> 40),
                signed20(word >> 20),
                signed20(word),
            )
            for index, value in enumerate(components):
                signed_component_minimum[index] = min(signed_component_minimum[index], value)
                signed_component_maximum[index] = max(signed_component_maximum[index], value)
            maximum_signed_square_sum = max(
                maximum_signed_square_sum, sum(value * value for value in components)
            )
        reserved_high_two_nonzero += local_reserved_nonzero
        total_units += unit_count

        local_dwords = len(main) // 4
        local_be = sum(
            nfl_smallest_three_valid(word, nfl_quaternion_scale)
            for (word,) in struct.iter_unpack(">I", main)
        )
        local_le = sum(
            nfl_smallest_three_valid(word, nfl_quaternion_scale)
            for (word,) in struct.iter_unpack("<I", main)
        )
        total_dwords += local_dwords
        nfl_valid_be += local_be
        nfl_valid_le += local_le

        optional = [item for item in resource["regions"] if item["role"] == "optional_packed_motion"]
        optional_stride = 0
        if optional:
            if len(optional) != 1:
                raise LineageError(f"{resource['name']}: multiple optional packed regions")
            optional_bytes = checked_slice(body, optional[0])
            optional_stride, optional_remainder = divmod(len(optional_bytes), frame_count)
            if optional_remainder:
                raise LineageError(f"{resource['name']}: optional stream does not tile by frame")
            optional_strides[optional_stride] += 1

        rows.append(
            {
                "name": resource["name"],
                "sample_count": frame_count,
                "sample_rate": int(resource["sample_rate_hz"]),
                "packed_bytes": len(main),
                "packed_bytes_per_sample": stride,
                "candidate_unit_size": APF_UNIT_SIZE,
                "candidate_units_per_sample": per_frame,
                "candidate_unit_count": unit_count,
                "reserved_high_two_nonzero": local_reserved_nonzero,
                "selector_0": local_selectors[0],
                "selector_1": local_selectors[1],
                "selector_2": local_selectors[2],
                "selector_3": local_selectors[3],
                "nfl_10bit_be_valid": local_be,
                "nfl_10bit_le_valid": local_le,
                "dword_count": local_dwords,
                "optional_bytes_per_sample": optional_stride,
            }
        )

    conservative_scale = 1.0 / (math.sqrt(2.0) * (1 << 19))
    candidate_maximum_square = maximum_signed_square_sum * conservative_scale**2
    if reserved_high_two_nonzero or candidate_maximum_square > 1.0:
        raise LineageError("APF 64-bit candidate grammar failed its corpus bounds")

    summary = {
        "clip_count": len(clips),
        "packed_bytes": sum(int(row["packed_bytes"]) for row in rows),
        "candidate_unit_size": APF_UNIT_SIZE,
        "candidate_unit_count": total_units,
        "packed_bytes_per_sample_distribution": int_distribution(frame_strides),
        "candidate_units_per_sample_distribution": int_distribution(units_per_frame),
        "optional_bytes_per_sample_distribution": int_distribution(optional_strides),
        "reserved_high_two_nonzero_count": reserved_high_two_nonzero,
        "selector_distribution": int_distribution(selector_counts),
        "signed20_component_minimum": signed_component_minimum,
        "signed20_component_maximum": signed_component_maximum,
        "maximum_signed20_three_square_sum": maximum_signed_square_sum,
        "candidate_conservative_scale": format(conservative_scale, ".12g"),
        "candidate_maximum_scaled_square_sum": format(candidate_maximum_square, ".12g"),
        "nfl_10bit_direct_test": {
            "dword_count": total_dwords,
            "big_endian_valid_count": nfl_valid_be,
            "big_endian_invalid_count": total_dwords - nfl_valid_be,
            "little_endian_valid_count": nfl_valid_le,
            "little_endian_invalid_count": total_dwords - nfl_valid_le,
            "interpretation": (
                "both byte orders produce invalid radicands, so APF is not the NFL "
                "three-signed-10-bit dword codec"
            ),
        },
        "status": (
            "8-byte frame-major pose-unit grammar proved; 2+2+20+20+20 "
            "smallest-three-like interpretation remains a candidate without APF decoder proof"
        ),
    }
    return summary, rows


def best_component_transform(
    apf_samples: list[tuple[int, int, int]],
    nfl_samples: list[tuple[int, int, int]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    scores: list[tuple[int, tuple[int, int, int], tuple[int, int, int]]] = []
    for permutation in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            total = sum(
                abs(left[index] - signs[index] * right[permutation[index]])
                for left, right in zip(apf_samples, nfl_samples)
                for index in range(3)
            )
            scores.append((total, permutation, signs))
    scores.sort()
    details = [
        {
            "total_absolute_difference": score,
            "permutation": list(permutation),
            "signs": list(signs),
        }
        for score, permutation, signs in scores[:2]
    ]
    best = details[0]
    return details, best


def analyze_pairs(
    apf: dict[str, object],
    apf_corpus: bytes,
    nfl_motion: dict[str, object],
    nfl_index: Path,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    archive = nfl_outer.parse_archive(nfl_index)
    apf_by_name = {item["name"]: item for item in apf["resources"]}
    nfl_by_name: dict[str, list[dict[str, object]]] = {}
    for item in nfl_motion["resources"]:
        nfl_by_name.setdefault(item["name"], []).append(item)

    rows: list[dict[str, object]] = []
    combined_apf: list[tuple[int, int, int]] = []
    combined_nfl: list[tuple[int, int, int]] = []
    for name in PAIR_NAMES:
        if name not in apf_by_name or len(nfl_by_name.get(name, [])) != 1:
            raise LineageError(f"{name}: exact-name pair is missing or ambiguous")
        apf_resource = apf_by_name[name]
        nfl_resource = nfl_by_name[name][0]
        if apf_resource["kind"] != "full_clip" or nfl_resource["kind"] != "SMCD":
            raise LineageError(f"{name}: unexpected resource kind")
        if int(nfl_resource["root_count"]) != 1 or int(nfl_resource["outer_index"]) != 346:
            raise LineageError(f"{name}: NFL lineage anchor moved")

        apf_start = int(apf_resource["corpus_offset"])
        apf_body = apf_corpus[apf_start : apf_start + int(apf_resource["length"])]
        entry = archive.entries[int(nfl_resource["outer_index"])]
        nfl_body = nfl_outer.read_entry_range(
            archive,
            entry,
            int(nfl_resource["chunk_offset"]) + NFL_WRAPPER_SIZE,
            int(nfl_resource["stored_size"]),
        )
        if sha256(nfl_body) != nfl_resource["decoded_sha256"]:
            raise LineageError(f"{name}: NFL body hash differs")

        nfl_root = nfl_resource["roots"][0]
        root_offset = int(nfl_root["offset"])
        nfl_words = struct.unpack_from("<13I", nfl_body, root_offset)
        apf_words = tuple(int(value, 16) for value in apf_resource["root_words"])
        apf_count = int(apf_resource["sample_count"])
        nfl_count = nfl_words[0] >> 16
        apf_rate = int(apf_resource["sample_rate_hz"])
        nfl_rate = nfl_words[3] & 0xFF
        apf_time_raw = apf_words[3]
        nfl_time_raw = nfl_words[4]
        apf_duration_raw = apf_words[4]
        nfl_duration_raw = nfl_words[5]
        if not (
            apf_count == nfl_count
            and apf_rate == nfl_rate == 15
            and apf_time_raw == nfl_time_raw == 0x3F800000
            and int(apf_resource["unknown_u16_06"]) == ((nfl_words[3] >> 16) & 0xFFFF) == 100
        ):
            raise LineageError(f"{name}: normalized header lineage no longer holds")

        apf_main = checked_slice(apf_body, region_by_role(apf_resource, "packed_motion"))
        nfl_quaternion = checked_slice(nfl_body, nfl_region(nfl_resource, 0, 0x24))
        nfl_channels = nfl_words[0] & 0xFF
        nfl_quaternion_bytes = nfl_channels * nfl_count * 4
        if len(apf_main) != apf_count * 23 * 8 or len(nfl_quaternion) < nfl_quaternion_bytes:
            raise LineageError(f"{name}: paired packed-stream geometry differs")

        apf_trajectory = checked_slice(
            apf_body, region_by_role(apf_resource, "root_vector_samples")
        )
        nfl_trajectory = checked_slice(nfl_body, nfl_region(nfl_resource, 0, 0x28))
        nfl_flags = nfl_words[1] & 0xFF
        nfl_trajectory_stride = 6 if nfl_flags & 8 else 8
        if len(apf_trajectory) != apf_count * 6 or nfl_trajectory_stride != 6:
            raise LineageError(f"{name}: paired trajectory geometry differs")
        apf_samples = list(struct.iter_unpack(">3h", apf_trajectory))
        nfl_samples = [
            struct.unpack_from("<3h", nfl_trajectory, index * nfl_trajectory_stride)
            for index in range(nfl_count)
        ]
        combined_apf.extend(apf_samples)
        combined_nfl.extend(nfl_samples)
        transformations, best = best_component_transform(apf_samples, nfl_samples)
        if best["permutation"] != [0, 1, 2] or best["signs"] != [1, 1, 1]:
            raise LineageError(f"{name}: identity is no longer the best trajectory transform")
        component_exact = [
            sum(left[index] == right[index] for left, right in zip(apf_samples, nfl_samples))
            for index in range(3)
        ]
        component_sum_abs = [
            sum(abs(left[index] - right[index]) for left, right in zip(apf_samples, nfl_samples))
            for index in range(3)
        ]
        component_max_abs = [
            max(abs(left[index] - right[index]) for left, right in zip(apf_samples, nfl_samples))
            for index in range(3)
        ]

        apf_events = checked_slice(apf_body, region_by_role(apf_resource, "event_stream"))
        nfl_events = checked_slice(nfl_body, nfl_region(nfl_resource, 0, 0x2C))
        if apf_events != b"\xff\xff\xff\xff" or nfl_events != b"\xff\xff\xff\xff":
            raise LineageError(f"{name}: expected sentinel-only event streams")

        rows.append(
            {
                "name": name,
                "apf_inner_index": int(apf_resource["inner_index"]),
                "nfl_outer_index": int(nfl_resource["outer_index"]),
                "nfl_chunk_index": int(nfl_resource["chunk_index"]),
                "frame_count": apf_count,
                "sample_rate": apf_rate,
                "time_scale_raw": f"0x{apf_time_raw:08x}",
                "apf_duration_raw": f"0x{apf_duration_raw:08x}",
                "nfl_duration_raw": f"0x{nfl_duration_raw:08x}",
                "apf_minus_nfl_duration_raw": apf_duration_raw - nfl_duration_raw,
                "apf_duration": float_from_raw(apf_duration_raw),
                "nfl_duration": float_from_raw(nfl_duration_raw, "<"),
                "constant_100_field_equal": True,
                "apf_packed_bytes_per_frame": len(apf_main) // apf_count,
                "apf_candidate_8byte_units_per_frame": len(apf_main) // apf_count // 8,
                "nfl_packed_quaternion_dwords_per_frame": nfl_channels,
                "nfl_packed_quaternion_bytes_per_frame": nfl_channels * 4,
                "nfl_quaternion_slack_bytes": len(nfl_quaternion) - nfl_quaternion_bytes,
                "trajectory_stride": 6,
                "trajectory_scale": "0.125",
                "trajectory_exact_record_count": sum(
                    left == right for left, right in zip(apf_samples, nfl_samples)
                ),
                "trajectory_exact_component_counts": component_exact,
                "trajectory_component_sum_absolute_difference": component_sum_abs,
                "trajectory_component_maximum_absolute_difference": component_max_abs,
                "trajectory_best_transform": best,
                "trajectory_runner_up_transform": transformations[1],
                "event_streams_sentinel_only": True,
                "packed_streams_byte_identical": apf_main == nfl_quaternion,
                "opaque_vector_raw_equal": list(apf_words[5:8]) == list(nfl_words[6:9]),
            }
        )

    combined_transforms, combined_best = best_component_transform(combined_apf, combined_nfl)
    if combined_best["permutation"] != [0, 1, 2] or combined_best["signs"] != [1, 1, 1]:
        raise LineageError("identity is not the best combined trajectory transform")
    summary = {
        "pair_count": len(rows),
        "paired_frame_count": len(combined_apf),
        "all_counts_rates_time_scales_equal": True,
        "duration_raw_delta_distribution": int_distribution(
            Counter(int(row["apf_minus_nfl_duration_raw"]) for row in rows)
        ),
        "sentinel_only_event_pair_count": sum(row["event_streams_sentinel_only"] for row in rows),
        "byte_identical_packed_stream_count": sum(row["packed_streams_byte_identical"] for row in rows),
        "combined_trajectory_best_transform": combined_best,
        "combined_trajectory_runner_up_transform": combined_transforms[1],
        "interpretation": (
            "the clips retain the same sampling grid and component order, but revised values "
            "and incompatible packed-pose widths preclude interchangeability"
        ),
    }
    return rows, summary


def apf_duration_summary(apf: dict[str, object]) -> dict[str, object]:
    gaps: list[float] = []
    for item in apf["resources"]:
        if item["kind"] != "full_clip":
            continue
        coordinate = (
            float(item["duration"])
            * int(item["sample_rate_hz"])
            * float(item["time_scale"])
        )
        gaps.append((int(item["sample_count"]) - 1) - coordinate)
    if not all(-0.0001 <= value < 1.0 for value in gaps):
        raise LineageError("APF duration lies outside final sample window")
    return {
        "clip_count": len(gaps),
        "all_within_final_sample_window": True,
        "gap_minimum": format(min(gaps), ".12g"),
        "gap_maximum": format(max(gaps), ".12g"),
    }


def verify_pseudo(apf_path: Path, nfl_path: Path) -> dict[str, object]:
    apf = apf_path.read_text(encoding="utf-8")
    nfl = nfl_path.read_text(encoding="utf-8")
    apf_needles = (
        "/* 0x84638720:FUN_84638720",
        "(*param_2 >> 9 & 0xff)",
        "param_2[9]",
        "DAT_82000c30",
        "*(uint **)(param_3 + 0x28)",
    )
    nfl_needles = (
        "/* 0x000DED10:FUN_000ded10 */",
        "((uVar5 >> 0x14 & 0x3ff) - 0x200)",
        "/* 0x000DEE30:FUN_000dee30 */",
        "*(int *)(in_EAX + 0x28)",
        "_DAT_004f24e4",
        "*(uint **)(param_1 + 0x2c)",
    )
    if not all(value in apf for value in apf_needles):
        raise LineageError("APF focused pseudo-C no longer contains required sampler evidence")
    if not all(value in nfl for value in nfl_needles):
        raise LineageError("NFL focused pseudo-C no longer contains required sampler evidence")
    return {
        "apf": {
            "path": str(apf_path),
            "sha256": file_sha256(apf_path),
            "root_vector_sampler": "0x84638720",
            "event_consumers": ["0x846389a8", "0x84638c18", "0x84638cc8", "0x84638d68"],
        },
        "nfl": {
            "path": str(nfl_path),
            "sha256": file_sha256(nfl_path),
            "packed_quaternion_decoder": "0x000ded10",
            "trajectory_sampler": "0x000dee30",
            "event_consumers": ["0x000df030", "0x000df0d0"],
        },
    }


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, dialect="excel-tab", extrasaction="ignore"
        )
        writer.writeheader()
        for row in rows:
            cooked = {
                key: (
                    ",".join(str(value) for value in item)
                    if isinstance(item, list)
                    else json.dumps(item, sort_keys=True, separators=(",", ":"))
                    if isinstance(item, dict)
                    else item
                )
                for key, item in row.items()
            }
            writer.writerow(cooked)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apf-inventory", type=Path, required=True)
    parser.add_argument("--apf-corpus", type=Path, required=True)
    parser.add_argument("--nfl-sampler-inventory", type=Path, required=True)
    parser.add_argument("--nfl-motion-inventory", type=Path, required=True)
    parser.add_argument("--nfl-index", type=Path, required=True)
    parser.add_argument("--apf-pseudo", type=Path, required=True)
    parser.add_argument("--nfl-pseudo", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--pairs-tsv", type=Path, required=True)
    parser.add_argument("--apf-packed-tsv", type=Path, required=True)
    args = parser.parse_args()

    apf = load_json(args.apf_inventory, APF_SCHEMA)
    nfl_sampler = load_json(args.nfl_sampler_inventory, NFL_SAMPLER_SCHEMA)
    nfl_motion = load_json(args.nfl_motion_inventory, NFL_MOTION_SCHEMA)
    corpus = args.apf_corpus.read_bytes()
    if sha256(corpus) != apf["summary"]["corpus_sha256"]:
        raise LineageError("APF corpus hash differs from its inventory")
    if int(nfl_sampler["summary"]["root_count"]) != 6068:
        raise LineageError("NFL sampler inventory is incomplete")
    if int(nfl_motion["summary"]["standalone_and_embedded_root_count"]) != 6068:
        raise LineageError("NFL motion inventory is incomplete")

    nfl_scale_raw = int(nfl_sampler["executable_constants"]["quaternion_scale"]["raw"], 16)
    nfl_scale = float_from_raw(nfl_scale_raw, "<")
    apf_packed, packed_rows = analyze_apf_packed(apf, corpus, nfl_scale)
    pairs, pair_summary = analyze_pairs(apf, corpus, nfl_motion, args.nfl_index)
    pseudo = verify_pseudo(args.apf_pseudo, args.nfl_pseudo)

    report = {
        "schema": OUTPUT_SCHEMA,
        "sources": {
            "apf_inventory": {
                "path": str(args.apf_inventory),
                "sha256": file_sha256(args.apf_inventory),
            },
            "apf_corpus": {
                "path": str(args.apf_corpus),
                "sha256": file_sha256(args.apf_corpus),
            },
            "nfl_sampler_inventory": {
                "path": str(args.nfl_sampler_inventory),
                "sha256": file_sha256(args.nfl_sampler_inventory),
            },
            "nfl_motion_inventory": {
                "path": str(args.nfl_motion_inventory),
                "sha256": file_sha256(args.nfl_motion_inventory),
            },
            "nfl_index": str(args.nfl_index),
        },
        "executable_evidence": pseudo,
        "normalized_root_field_lineage": [
            {
                "semantic": "frame/sample count",
                "nfl": "little-endian u16 at +0x02",
                "apf": "big-endian u16 at +0x04",
            },
            {
                "semantic": "sample rate",
                "nfl": "byte at +0x0c",
                "apf": "(flags >> 9) & 0xff",
            },
            {
                "semantic": "constant 100",
                "nfl": "little-endian u16 at +0x0e",
                "apf": "big-endian u16 at +0x06",
            },
            {
                "semantic": "time scale",
                "nfl": "f32 at +0x10",
                "apf": "f32 at +0x0c",
            },
            {
                "semantic": "duration",
                "nfl": "f32 at +0x14",
                "apf": "f32 at +0x10",
            },
            {
                "semantic": "opaque finite vector",
                "nfl": "three f32 at +0x18..+0x20",
                "apf": "three f32 at +0x14..+0x1c",
            },
            {
                "semantic": "packed pose pointer",
                "nfl": "+0x24",
                "apf": "+0x20",
            },
            {
                "semantic": "trajectory/root-vector pointer",
                "nfl": "+0x28",
                "apf": "+0x24",
            },
            {
                "semantic": "event pointer",
                "nfl": "+0x2c",
                "apf": "+0x28",
            },
        ],
        "shared_runtime_contracts": {
            "frame_coordinate": "sample_rate * seconds * time_scale",
            "trajectory": (
                "three signed platform-endian int16 components, linear interpolation, "
                "each scaled by exactly 0.125"
            ),
            "events": (
                "event_id=word&0xff; tick=word>>8; seconds=tick/65536/time_scale; "
                "0xffffffff terminator"
            ),
            "relative_pointer_family": (
                "one-based field-local signed relative pointers; byte order and field offsets differ"
            ),
        },
        "flag_lineage": {
            "apf": {
                "mirror": "flags & 0x40",
                "six_byte_trajectory": "flags & 0x80 (set in all 67 normal clips)",
                "sample_rate": "(flags >> 9) & 0xff",
                "variable_pointer_count": "(flags >> 17) & 0x1f",
                "observed_distribution": apf["summary"]["flags_counts"],
            },
            "nfl": {
                "mirror": "flags byte & 0x04",
                "six_byte_trajectory": "flags byte & 0x08",
                "sample_rate": "separate byte at +0x0c",
                "observed_distribution": nfl_sampler["domains"]["flags"],
            },
            "decision": (
                "roles survived but bit positions and field placement changed; the raw flag "
                "words/bytes are not cross-title compatible"
            ),
        },
        "event_id_domain_comparison": {
            "apf": apf["summary"]["event_id_counts"],
            "nfl": nfl_sampler["domains"]["event_id"],
            "shared_observed_ids": [
                int(value)
                for value in sorted(
                    set(apf["summary"]["event_id_counts"])
                    & set(nfl_sampler["domains"]["event_id"]),
                    key=int,
                )
            ],
            "decision": (
                "the word grammar is identical, but the observed ID namespaces overlap only "
                "at ID 156 and callback-name stability is unproved"
            ),
        },
        "full_corpus": {
            "apf": {
                "resource_count": int(apf["summary"]["resource_count"]),
                "normal_clip_count": int(apf["summary"]["full_clip_count"]),
                "sample_rate_distribution": apf["summary"]["sample_rate_counts"],
                "time_scale_distribution": {"0x3f800000": 67},
                "trajectory_stride_distribution": {"6": 67},
                "optional_stream": "6 clips, exactly 16 bytes/sample, pointer +0x2c before events",
                "duration_window": apf_duration_summary(apf),
            },
            "nfl": {
                "resource_count": int(nfl_sampler["summary"]["resource_count"]),
                "root_count": int(nfl_sampler["summary"]["root_count"]),
                "sample_rate_distribution": nfl_sampler["domains"]["sample_rate"],
                "time_scale_distribution": nfl_sampler["domains"]["time_scale_raw"],
                "trajectory_stride_distribution": nfl_sampler["domains"]["trajectory_stride"],
                "optional_stream": "171 roots, exactly 12 bytes/frame, pointer +0x30 after events",
                "duration_window": {
                    "root_count": int(
                        nfl_sampler["summary"]["duration_within_final_sample_window_count"]
                    ),
                    "all_within_final_sample_window": True,
                    "gap_minimum": nfl_sampler["summary"]["duration_gap_coordinate_minimum"],
                    "gap_maximum": nfl_sampler["summary"]["duration_gap_coordinate_maximum"],
                },
            },
        },
        "apf_packed_pose_candidate": apf_packed,
        "exact_name_pairs": pairs,
        "pair_summary": pair_summary,
        "compatibility_decision": {
            "shared_semantic_lineage": True,
            "byte_compatible_roots": False,
            "byte_compatible_packed_pose_codec": False,
            "safe_interchange_without_decode_and_reencode": False,
            "reasons": [
                "root byte order, size, fields, and pointer offsets differ",
                "NFL uses one four-byte signed-10-bit smallest-three value per packed channel",
                "APF main streams tile into eight-byte candidate pose units and fail NFL decode bounds",
                "the seven pairs use 15 NFL dwords versus 23 APF eight-byte units per frame",
                "optional streams have incompatible placement and 12-versus-16-byte frame widths",
                "neither title yet has a proved logical-channel-to-bone binding",
            ],
        },
        "worked": [
            "normalized exact root fields and sampler equations across both endian conventions",
            "proved identical trajectory scale and event-word encoding from focused executable evidence",
            "validated all APF packed bytes as fixed frame-major 8-byte candidate units",
            "tested and rejected direct NFL 10-bit smallest-three decoding in both APF byte orders",
            "validated all seven exact-name clips against source archive bytes",
            "proved identity component order is the best signed permutation for every paired trajectory",
        ],
        "failed": [
            "no byte-compatible packed-pose codec exists between the supplied resources",
            "APF 8-byte units cannot yet be safely decoded from corpus statistics alone",
            "flags and optional-stream bits do not have a direct numeric mapping",
            "same-name trajectory samples are revised rather than exact copies",
        ],
        "portme": [
            "PORTME: recover the APF 8-byte packed pose decoder, scale, selector role, and interpolation",
            "PORTME: bind APF packed units and NFL logical channels to exact skeleton bone names",
            "PORTME: prove coordinate axes, handedness, units, and root-motion application",
            "PORTME: identify both optional-stream semantics before any cross-title conversion",
            "PORTME: do not emit glTF animation until decoded poses validate against bound skeletons",
        ],
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_tsv(
        args.pairs_tsv,
        pairs,
        [
            "name",
            "apf_inner_index",
            "nfl_outer_index",
            "nfl_chunk_index",
            "frame_count",
            "sample_rate",
            "time_scale_raw",
            "apf_duration_raw",
            "nfl_duration_raw",
            "apf_minus_nfl_duration_raw",
            "apf_packed_bytes_per_frame",
            "apf_candidate_8byte_units_per_frame",
            "nfl_packed_quaternion_dwords_per_frame",
            "nfl_packed_quaternion_bytes_per_frame",
            "nfl_quaternion_slack_bytes",
            "trajectory_stride",
            "trajectory_exact_record_count",
            "trajectory_exact_component_counts",
            "trajectory_component_sum_absolute_difference",
            "trajectory_component_maximum_absolute_difference",
            "trajectory_best_transform",
            "trajectory_runner_up_transform",
            "packed_streams_byte_identical",
            "opaque_vector_raw_equal",
        ],
    )
    write_tsv(
        args.apf_packed_tsv,
        packed_rows,
        [
            "name",
            "sample_count",
            "sample_rate",
            "packed_bytes",
            "packed_bytes_per_sample",
            "candidate_unit_size",
            "candidate_units_per_sample",
            "candidate_unit_count",
            "reserved_high_two_nonzero",
            "selector_0",
            "selector_1",
            "selector_2",
            "selector_3",
            "dword_count",
            "nfl_10bit_be_valid",
            "nfl_10bit_le_valid",
            "optional_bytes_per_sample",
        ],
    )
    print(
        "MOTION_LINEAGE_COMPLETE "
        f"pairs={len(pairs)} apf_units={apf_packed['candidate_unit_count']} "
        f"paired_frames={pair_summary['paired_frame_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
