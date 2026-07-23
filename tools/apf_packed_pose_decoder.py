#!/usr/bin/env python3
"""Validate the instruction-proved APF 2K8 packed-pose mode-0 decoder.

The report intentionally stops at logical output lanes.  It does not assign
bone names, coordinate axes, or emit glTF because none of those bindings are
proved by the focused executable trace.

// PORTME at 0x846384A8: emulate Xenon vrsqrtefp for bit-exact floats.
// PORTME at 0x8463A4F0: recover packed-map mode 2 and its 0x84639938 call.
// PORTME at 0x8463A52C: recover packed-map mode 1.
// PORTME at 0x8463A4B0: bind logical map records to proved skeleton bones.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from typing import Iterable


SCHEMA = "apf_packed_pose_decoder/v1"
APF_SCHEMA = "apf_mocap_inventory/v1"
EXPECTED_APF_INVENTORY_SHA256 = (
    "e477214f818be01891253683d731551c98a06bf3da0b396dc9de968b031dfb69"
)
EXPECTED_APF_CORPUS_SHA256 = (
    "ba6ddcddd018f579e4ddbe385d63b31b45cca3c2aaf450850cf0fce20344d15f"
)
EXPECTED_XEX_MD5 = "217eea6084c3d03f0f1143802b1f5636"
EXPECTED_LANGUAGE = "PowerPC:BE:64:A2ALT-32addr"
EXPECTED_INSTRUCTION_COUNT = 976
UNIT_SIZE = 8
COMPONENT_BITS = 20
SCALE = Fraction(23, 1 << 24)


class DecoderError(ValueError):
    """Raised when canonical evidence no longer matches the proved decoder."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def float_text(value: float) -> str:
    return format(value, ".17g")


def signed20(value: int) -> int:
    value &= (1 << COMPONENT_BITS) - 1
    if value & (1 << (COMPONENT_BITS - 1)):
        value -= 1 << COMPONENT_BITS
    return value


def int_distribution(values: Counter[int]) -> dict[str, int]:
    return {str(key): values[key] for key in sorted(values)}


def region_by_role(resource: dict[str, object], role: str) -> dict[str, object]:
    matches = [item for item in resource["regions"] if item["role"] == role]
    if len(matches) != 1:
        raise DecoderError(f"{resource['name']}: expected one {role!r} region")
    return matches[0]


def checked_region(body: bytes, region: dict[str, object]) -> bytes:
    start = int(region["offset"])
    end = int(region["end"])
    result = body[start:end]
    if len(result) != int(region["length"]) or sha256(result) != region["sha256"]:
        raise DecoderError("canonical packed region hash changed")
    return result


CONSTANT_RE = re.compile(
    r"^CONST_FLOAT (0x[0-9A-F]{8}) raw=(0x[0-9A-F]{8}) "
    r"float=(\S+) hex=(\S+) label=(\S+)$"
)
MAP_RE = re.compile(r"^MAP (\d+) (\d+) (\d+) (\d+)$")


EXPECTED_CONSTANTS = {
    0x82000BF0: (0xBAA57A2C, "acos_x7"),
    0x82000BF4: (0x3BDA90C5, "acos_x6"),
    0x82000BF8: (0xBC8BFC66, "acos_x5"),
    0x82000BFC: (0x3CFD10F8, "acos_x4"),
    0x82000C00: (0xBD4D8392, "acos_x3"),
    0x82000C04: (0x3DB63A9E, "acos_x2"),
    0x82000C08: (0xBE5BBFCA, "acos_x1"),
    0x82000C0C: (0x3FC90FDA, "acos_x0"),
    0x82000C10: (0xB94C8C6E, "sin_x7"),
    0x82000C14: (0x3C088342, "sin_x5"),
    0x82000C18: (0xBE2AAAA1, "sin_x3"),
    0x82000C1C: (0x3FC90FDB, "half_pi"),
    0x82000C20: (0xBAB24993, "cos_x6"),
    0x82000C24: (0x3D2AA036, "cos_x4"),
    0x82000C28: (0xBEFFFFDF, "cos_x2"),
    0x82000C2C: (0x3F7FF2E5, "linear_threshold"),
    0x820009A0: (0x00000000, "clamped_frame_fraction"),
}


def parse_trace(path: Path) -> tuple[list[list[int]], list[dict[str, object]]]:
    text = path.read_text(encoding="utf-8")
    if f"Program MD5: {EXPECTED_XEX_MD5}" not in text:
        raise DecoderError("focused trace has the wrong XEX MD5")
    if f"Program language: {EXPECTED_LANGUAGE}" not in text:
        raise DecoderError("focused trace has the wrong processor language")

    channel_map: list[list[int]] = []
    constants: dict[int, dict[str, object]] = {}
    for line in text.splitlines():
        if match := MAP_RE.fullmatch(line):
            index, mode, normal, mirrored = map(int, match.groups())
            if index != len(channel_map):
                raise DecoderError("default channel map is not contiguous")
            channel_map.append([mode, normal, mirrored])
        elif match := CONSTANT_RE.fullmatch(line):
            address = int(match.group(1), 16)
            raw = int(match.group(2), 16)
            constants[address] = {
                "address": f"0x{address:08X}",
                "raw": f"0x{raw:08X}",
                "float": match.group(3),
                "hex_float": match.group(4),
                "label": match.group(5),
            }

    expected_map = [[0, index, index] for index in range(32)]
    if channel_map != expected_map:
        raise DecoderError("default 0x82000B30 channel map changed")
    for address, (raw, label) in EXPECTED_CONSTANTS.items():
        item = constants.get(address)
        if item is None or item["raw"] != f"0x{raw:08X}" or item["label"] != label:
            raise DecoderError(f"constant evidence changed at 0x{address:08X}")
    return channel_map, [constants[address] for address in sorted(constants)]


# Address -> exact vendored-disassembler mnemonic and operands.  These anchors
# cover record loading, bit conversion, reconstruction, selection, SLERP,
# frame addressing, map lookup, mirroring, and inverse pack symmetry.
INSTRUCTION_ANCHORS = {
    0x84638464: ("lwz", "r9,0(r3)"),
    0x84638468: ("rlwinm", "r9,r9,6,26,29"),
    0x8463846C: ("lvrx", "v11,r3,r11"),
    0x84638470: ("lvlx", "v10,r3,r10"),
    0x8463847C: ("vaddsws", "v10,v12,v0"),
    0x84638480: ("vcfsx", "v12,v13,1"),
    0x84638484: ("lvsl", "v7,r0,r9"),
    0x84638488: ("vupkd3d128", "v11,v11,24"),
    0x8463848C: ("vcfsx", "v13,v10,5"),
    0x84638490: ("vslw", "v0,v11,v0"),
    0x84638494: ("vcfsx", "v0,v0,31"),
    0x84638498: ("vmulfp128", "v0,v13,v0"),
    0x846384A0: ("vmsum3fp128", "v0,v0,v0"),
    0x846384A4: ("vsubfp", "v13,v9,v0"),
    0x846384A8: ("vrsqrtefp", "v0,v13"),
    0x846384B4: ("vnmsubfp", "v12,v10,v9,v12"),
    0x846384B8: ("vmaddfp", "v0,v0,v12,v0"),
    0x846384BC: ("vmulfp128", "v0,v0,v13"),
    0x846384C0: ("vrlimi128", "v11,v0,1,0"),
    0x846384C8: ("vperm", "v1,v0,v0,v7"),
    0x846385A8: ("vmsum4fp128", "v9,v1,v2"),
    0x846385F0: ("vandc", "v31,v9,v8"),
    0x846385F8: ("vxor", "v2,v2,v31"),
    0x84638610: ("vrsqrtefp", "v9,v8"),
    0x84638674: ("vsel", "v13,v10,v7,v13"),
    0x846386C4: ("vcmpgefp", "v7,v10,v13"),
    0x846386CC: ("vcmpgefp", "v0,v0,v11"),
    0x84638708: ("vsel", "v12,v12,v3,v0"),
    0x8463870C: ("vsel", "v0,v13,v8,v0"),
    0x84638710: ("vmulfp128", "v13,v12,v2"),
    0x84638714: ("vmaddfp", "v1,v0,v1,v13"),
    0x84639778: ("vpkd3d128", "v13,v0,6,2,2"),
    0x8463981C: ("bl", "0x84638450"),
    0x8463A374: ("lfs", "f0,12(r25)"),
    0x8463A378: ("lwz", "r11,0(r25)"),
    0x8463A380: ("lhz", "r10,4(r25)"),
    0x8463A388: ("rlwinm", "r6,r11,23,24,31"),
    0x8463A38C: ("lwz", "r9,32(r25)"),
    0x8463A394: ("rlwinm", "r8,r11,10,27,31"),
    0x8463A39C: ("rlwinm", "r7,r11,5,27,31"),
    0x8463A3AC: ("add", "r23,r8,r7"),
    0x8463A3D4: ("mullw", "r10,r10,r23"),
    0x8463A3D8: ("rlwinm", "r10,r10,3,0,28"),
    0x8463A3F4: ("fctiwz", "f13,f0"),
    0x8463A420: ("add", "r28,r8,r30"),
    0x8463A428: ("fsubs", "f0,f0,f13"),
    0x8463A448: ("rlwinm", "r24,r11,26,31,31"),
    0x8463A49C: ("rlwinm", "r11,r27,1,0,30"),
    0x8463A4B0: ("lbz", "r11,1(r11)"),
    0x8463A4B4: ("extsb", "r11,r11"),
    0x8463A4D8: ("lbzx", "r10,r10,r26"),
    0x8463A680: ("bl", "0x846385a8"),
    0x8463A684: ("vxor128", "v0,v1,v125"),
    0x8463A688: ("stvx", "v0,r0,r31"),
    0x8463A68C: ("rlwinm", "r22,r22,31,1,31"),
    0x8463A690: ("addi", "r27,r27,1"),
    0x8463A694: ("addi", "r31,r31,16"),
    0x8463A7A8: ("rlwinm", "r11,r11,3,0,28"),
    0x8463A830: ("lfs", "f0,8(r6)"),
    0x8463A834: ("lfs", "f13,12(r6)"),
    0x8463A840: ("stfs", "f0,8(r6)"),
    0x8463A844: ("stfs", "f13,12(r6)"),
    0x847C1478: ("bl", "0x8463a320"),
    0x847C14AC: ("bl", "0x846394d0"),
    0x84AD12EC: ("bl", "0x84639790"),
}


def parse_vmx(path: Path) -> tuple[dict[int, dict[str, str]], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    if len(rows) != EXPECTED_INSTRUCTION_COUNT:
        raise DecoderError(
            f"expected {EXPECTED_INSTRUCTION_COUNT} focused instructions, got {len(rows)}"
        )
    by_address: dict[int, dict[str, str]] = {}
    for row in rows:
        address = int(row["address"], 16)
        if address in by_address:
            raise DecoderError(f"duplicate VMX trace address 0x{address:08X}")
        by_address[address] = row
    evidence: list[dict[str, str]] = []
    for address, expected in INSTRUCTION_ANCHORS.items():
        row = by_address.get(address)
        actual = None if row is None else (row["mnemonic"], row["operands"])
        if actual != expected:
            raise DecoderError(
                f"instruction anchor 0x{address:08X}: expected {expected}, got {actual}"
            )
        evidence.append(
            {
                "address": f"0x{address:08X}",
                "raw": row["raw"],
                "instruction": " ".join(part for part in expected if part),
            }
        )
    return by_address, evidence


def validate_pseudo(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    required = (
        "static ApfPose4 apf_decode_mode0_be",
        "float scale = 23.0f / 16777216.0f;",
        "static ApfPose4 apf_interpolate_mode0",
        "uint32_t units_per_frame = ((flags >> 22) & 31) + ((flags >> 27) & 31);",
        "if (mirror) *output = xor_float_sign_lanes_2_and_3(*output);",
        "PORTME at 0x846384A8",
        "PORTME at 0x8463A4F0",
        "PORTME at 0x8463A52C",
        "PORTME at 0x8463A46C",
        "PORTME: Ghidra truncated VMX128 function at 0x84638450",
        "PORTME: Ghidra truncated VMX128 function at 0x846385A8",
        "PORTME: Ghidra truncated VMX128 function at 0x8463A328",
    )
    for marker in required:
        if marker not in text:
            raise DecoderError(f"focused pseudo-C lacks {marker!r}")


def decode_reference(word: int) -> tuple[int, list[int], list[float], float]:
    selector = (word >> 60) & 0xF
    packed = [signed20(word), signed20(word >> 20), signed20(word >> 40)]
    scaled = [float(Fraction(value) * SCALE) for value in packed]
    radicand = 1.0 - sum(value * value for value in scaled)
    if radicand < 0:
        raise DecoderError("negative mode-0 radicand")
    stored = scaled + [math.sqrt(radicand)]
    rotate = selector & 3
    output = [stored[(lane + rotate) & 3] for lane in range(4)]
    return selector, packed, output, radicand


def analyze_corpus(
    inventory: dict[str, object], corpus: bytes
) -> tuple[dict[str, object], list[dict[str, object]]]:
    selector_counts: Counter[int] = Counter()
    missing_lane_counts: Counter[int] = Counter()
    flag_counts: Counter[int] = Counter()
    frame_group_counts: Counter[tuple[int, int, int]] = Counter()
    component_minimum = [1 << 30, 1 << 30, 1 << 30]
    component_maximum = [-(1 << 30), -(1 << 30), -(1 << 30)]
    maximum_square_sum = -1
    maximum_unit: dict[str, object] | None = None
    ideal_missing_minimum = math.inf
    ideal_missing_maximum = -math.inf
    total_units = 0
    optional_bytes = 0
    rows: list[dict[str, object]] = []

    for resource in inventory["resources"]:
        if resource["kind"] != "full_clip":
            continue
        start = int(resource["corpus_offset"])
        end = start + int(resource["length"])
        body = corpus[start:end]
        if len(body) != int(resource["length"]) or sha256(body) != resource["sha256"]:
            raise DecoderError(f"{resource['name']}: resource body hash changed")
        main = checked_region(body, region_by_role(resource, "packed_motion"))
        flags = int(resource["flags"], 16)
        count22 = (flags >> 22) & 31
        count27 = (flags >> 27) & 31
        units_per_frame = count22 + count27
        sample_count = int(resource["sample_count"])
        if int(resource["sample_rate_hz"]) != ((flags >> 9) & 0xFF):
            raise DecoderError(f"{resource['name']}: sample-rate flag mismatch")
        if len(main) != sample_count * units_per_frame * UNIT_SIZE:
            raise DecoderError(f"{resource['name']}: frame/unit tiling mismatch")

        local_selectors: Counter[int] = Counter()
        local_maximum_square = -1
        for unit_index, (word,) in enumerate(struct.iter_unpack(">Q", main)):
            selector, packed, output, radicand = decode_reference(word)
            selector_counts[selector] += 1
            local_selectors[selector] += 1
            missing_lane_counts[3 - (selector & 3)] += 1
            for index, value in enumerate(packed):
                component_minimum[index] = min(component_minimum[index], value)
                component_maximum[index] = max(component_maximum[index], value)
            square_sum = sum(value * value for value in packed)
            local_maximum_square = max(local_maximum_square, square_sum)
            if square_sum > maximum_square_sum:
                maximum_square_sum = square_sum
                maximum_unit = {
                    "resource": resource["name"],
                    "unit_index": unit_index,
                    "frame_index": unit_index // units_per_frame,
                    "packed_index": unit_index % units_per_frame,
                    "raw_be64": f"0x{word:016X}",
                    "selector4": selector,
                    "packed_components_low_to_high": packed,
                }
            ideal_missing = output[3 - (selector & 3)]
            ideal_missing_minimum = min(ideal_missing_minimum, ideal_missing)
            ideal_missing_maximum = max(ideal_missing_maximum, ideal_missing)
            total_units += 1

        local_scaled_square = Fraction(local_maximum_square * 23 * 23, 1 << 48)
        optional_length = sum(
            int(item["length"])
            for item in resource["regions"]
            if item["role"] == "optional_packed_motion"
        )
        optional_bytes += optional_length
        flag_counts[flags] += 1
        frame_group_counts[(count22, count27, units_per_frame)] += 1
        rows.append(
            {
                "name": resource["name"],
                "flags": f"0x{flags:08X}",
                "mirror": (flags >> 6) & 1,
                "sample_rate_hz": (flags >> 9) & 0xFF,
                "sample_count": sample_count,
                "count_bits_22_26": count22,
                "count_bits_27_31": count27,
                "units_per_frame": units_per_frame,
                "packed_bytes": len(main),
                "unit_count": len(main) // UNIT_SIZE,
                "selector_0": local_selectors[0],
                "selector_1": local_selectors[1],
                "selector_2": local_selectors[2],
                "selector_3": local_selectors[3],
                "maximum_scaled_three_square_sum": float_text(float(local_scaled_square)),
                "minimum_ideal_radicand": float_text(1.0 - float(local_scaled_square)),
                "optional_packed_bytes_not_claimed": optional_length,
            }
        )

    if maximum_unit is None:
        raise DecoderError("no packed units found")
    if any(selector > 3 for selector in selector_counts):
        raise DecoderError("shipped corpus now uses selector upper bits")
    maximum_scaled_square = Fraction(maximum_square_sum * 23 * 23, 1 << 48)
    minimum_radicand = Fraction(1) - maximum_scaled_square
    maximum_unit["maximum_signed_three_square_sum"] = maximum_square_sum
    maximum_unit["maximum_scaled_three_square_sum"] = float_text(
        float(maximum_scaled_square)
    )
    maximum_unit["minimum_ideal_radicand"] = float_text(float(minimum_radicand))

    component_domains = []
    for index, (minimum, maximum) in enumerate(zip(component_minimum, component_maximum)):
        component_domains.append(
            {
                "packed_component": index,
                "bit_range": [index * 20, index * 20 + 19],
                "signed_minimum": minimum,
                "signed_maximum": maximum,
                "scaled_minimum": float_text(float(Fraction(minimum) * SCALE)),
                "scaled_maximum": float_text(float(Fraction(maximum) * SCALE)),
            }
        )

    groups = [
        {
            "count_bits_22_26": key[0],
            "count_bits_27_31": key[1],
            "units_per_frame": key[2],
            "clip_count": count,
        }
        for key, count in sorted(frame_group_counts.items())
    ]
    summary = {
        "clip_count": len(rows),
        "unit_size": UNIT_SIZE,
        "unit_count": total_units,
        "packed_bytes": total_units * UNIT_SIZE,
        "selector4_distribution": int_distribution(selector_counts),
        "selector_upper_two_nonzero_count": sum(
            count for selector, count in selector_counts.items() if selector & 0xC
        ),
        "reconstructed_output_lane_distribution": int_distribution(missing_lane_counts),
        "packed_component_domains_low_to_high": component_domains,
        "maximum_unit": maximum_unit,
        "minimum_ideal_missing_component": float_text(ideal_missing_minimum),
        "maximum_ideal_missing_component": float_text(ideal_missing_maximum),
        "flag_distribution": {f"0x{key:08X}": flag_counts[key] for key in sorted(flag_counts)},
        "frame_group_distribution": groups,
        "optional_packed_bytes_excluded_from_decoder_claim": optional_bytes,
    }
    return summary, rows


def write_tsv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    rows = list(rows)
    if not rows:
        raise DecoderError("cannot write an empty clip table")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
            dialect="excel-tab",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def build_report(args: argparse.Namespace) -> tuple[dict[str, object], list[dict[str, object]]]:
    inventory_bytes = args.inventory.read_bytes()
    corpus = args.corpus.read_bytes()
    if sha256(inventory_bytes) != EXPECTED_APF_INVENTORY_SHA256:
        raise DecoderError("APF mocap inventory hash changed")
    if sha256(corpus) != EXPECTED_APF_CORPUS_SHA256:
        raise DecoderError("APF mocap corpus hash changed")
    inventory = json.loads(inventory_bytes)
    if inventory.get("schema") != APF_SCHEMA:
        raise DecoderError(f"expected {APF_SCHEMA!r}")
    if inventory["summary"]["packed_motion_bytes"] != 1_245_136:
        raise DecoderError("APF packed byte anchor changed")

    channel_map, constants = parse_trace(args.trace)
    _, instruction_evidence = parse_vmx(args.vmx)
    validate_pseudo(args.pseudo)
    corpus_summary, rows = analyze_corpus(inventory, corpus)

    selector_lane_map = {
        "0": ["packed_component_0", "packed_component_1", "packed_component_2", "reconstructed"],
        "1": ["packed_component_1", "packed_component_2", "reconstructed", "packed_component_0"],
        "2": ["packed_component_2", "reconstructed", "packed_component_0", "packed_component_1"],
        "3": ["reconstructed", "packed_component_0", "packed_component_1", "packed_component_2"],
    }
    report = {
        "schema": SCHEMA,
        "sources": {
            "apf_mocap_inventory": {
                "path": str(args.inventory),
                "sha256": sha256(inventory_bytes),
                "schema": APF_SCHEMA,
            },
            "apf_mocap_corpus": {
                "path": str(args.corpus),
                "sha256": sha256(corpus),
            },
            "focused_ghidra_trace": {
                "path": str(args.trace),
                "sha256": file_sha256(args.trace),
            },
            "focused_ghidra_pseudo_c": {
                "path": str(args.pseudo),
                "sha256": file_sha256(args.pseudo),
            },
            "vmx128_disassembly": {
                "path": str(args.vmx),
                "sha256": file_sha256(args.vmx),
                "instruction_count": EXPECTED_INSTRUCTION_COUNT,
                "decoder": "vendored XenonRecomp PowerPC/VMX128 opcode table",
            },
        },
        "executable": {
            "xex_md5": EXPECTED_XEX_MD5,
            "language": EXPECTED_LANGUAGE,
            "mode0_decoder": "0x84638450..0x846384CC",
            "quaternion_interpolator": "0x846385A8..0x84638718",
            "single_unit_dispatch_decoder": "0x84639790 (mode 0 calls 0x84638450 at 0x8463981C)",
            "aggregate_sampler": "0x8463A320 wrapper; 0x8463A328..0x8463A6BC body",
            "inverse_encoder": "0x84639670; mode 0 body 0x846396C0..0x8463978C",
            "concrete_callers": ["0x847C1438", "0x847C9428", "0x84AD12C0"],
            "instruction_evidence": instruction_evidence,
        },
        "proved_mode0_codec": {
            "record_size_bytes": 8,
            "byte_order": "big-endian uint64",
            "bit_layout_high_to_low": "selector4 | signed20 component2 | signed20 component1 | signed20 component0",
            "bit_ranges": {
                "packed_component_0": "19..0 signed",
                "packed_component_1": "39..20 signed",
                "packed_component_2": "59..40 signed",
                "selector4": "63..60 unsigned",
            },
            "scale": {
                "exact": "23/16777216",
                "decimal": float_text(float(SCALE)),
                "binary_float": "0x1.7000000000000p-20",
                "derivation": (
                    "vaddsws 11+12=23; vcfsx(...,5)=23/32; signed20 is shifted "
                    "12 then vcfsx(...,31), giving signed20/2^19"
                ),
            },
            "reconstruction": (
                "r=1-(c0*c0+c1*c1+c2*c2); missing=r*NR1(vrsqrtefp(r)), "
                "where NR1 is one Newton-Raphson refinement"
            ),
            "portable_numerical_equivalent": "missing=sqrt(r); not bit-exact to Xenon vrsqrtefp",
            "selector_operation": (
                "rlwinm extracts selector4*4; lvsl uses the low address nibble; "
                "vperm rotates the four 32-bit lanes left by selector4&3"
            ),
            "selector_to_output_lanes": selector_lane_map,
            "missing_output_lane_for_observed_selector": {
                "0": 3,
                "1": 2,
                "2": 1,
                "3": 0,
            },
            "corpus": corpus_summary,
        },
        "proved_interpolation": {
            "address": "0x846385A8..0x84638718",
            "classification": "shortest-path polynomial SLERP with a linear near-equality fallback",
            "sign_rule": (
                "dot4(left,right); if its sign bit is set, XOR that sign bit into all "
                "right lanes; then x=min(abs(dot),1)"
            ),
            "angle": (
                "theta=sqrt_NR1(1-x)*P7(x), using the eight 0x82000BF0..0x82000C0C "
                "coefficients and the exact VMX multiply-add order in the pseudo-C"
            ),
            "weights": (
                "left=sin_poly((1-t)*theta)/sin(theta); "
                "right=sin_poly(t*theta)/sin(theta); output=left*left_pose+right*right_pose"
            ),
            "linear_fallback": (
                "when x>=bitcast_float(0x3F7FF2E5), select weights (1-t,t); "
                "the vector implementation computes both paths then vsel chooses"
            ),
            "constants": constants,
            "bit_exact_limit": (
                "all coefficients and operation ordering are recovered; the initial Xenon "
                "vrsqrtefp estimate and platform floating exception/rounding behavior remain PORTME"
            ),
        },
        "proved_frame_and_output_mapping": {
            "root_fields": {
                "flags": "+0x00",
                "sample_count": "+0x04 big-endian u16 in serialized/runtime layout",
                "time_scale": "+0x0C float",
                "packed_pose_pointer": "+0x20",
            },
            "flag_fields": {
                "sample_rate_hz": "(flags>>9)&0xff",
                "packed_count_0": "(flags>>22)&0x1f",
                "packed_count_1": "(flags>>27)&0x1f",
                "units_per_frame": "packed_count_0+packed_count_1",
                "mirror": "(flags>>6)&1",
            },
            "frame_coordinate": "sample_rate_hz * (seconds * time_scale)",
            "frame_selection": (
                "at/after sample_count-1: use the final frame twice with t=0; otherwise "
                "frame0=fctiwz(coordinate), frame1=frame0+1, t=coordinate-frame0"
            ),
            "frame_address": "packed_pose + (frame*units_per_frame + signed_map_index)*8",
            "map_record": "three bytes [mode, normal_signed_index, mirrored_signed_index]",
            "map_selection": (
                "logical bit i selects map[i*3]; index=map[i*3+1+mirror]; a negative "
                "signed index skips decode; output advances 16 bytes for every logical bit position"
            ),
            "default_map_address": "0x82000B30",
            "default_map": channel_map,
            "default_map_interpretation": (
                "all 32 records are [mode0,i,i]; for active in-range logical outputs, "
                "logical i therefore reads packed unit i in each selected frame"
            ),
            "mode0_mirror": (
                "after interpolation XOR the float sign bit in output lanes 2 and 3; "
                "0x8463A830..0x8463A844 independently confirms those two lanes"
            ),
            "clip_table": "reports/assets/apf_packed_pose_decoder_clips.tsv",
        },
        "inverse_symmetry": {
            "proof": (
                "mode-0 inverse body 0x846396C0 selects/canonicalizes a lane then "
                "0x84639778 executes vpkd3d128 type 6 and stores exactly 8 bytes"
            ),
            "significance": (
                "type 6 is Xenon VPACK_NORMPACKED64 4_20_20_20 w_z_y_x, independently "
                "matching decoder vupkd3d128 type 6 at 0x84638488"
            ),
        },
        "worked": [
            "recovered the runtime mode-0 decoder from raw VMX128 words despite stock Ghidra truncation",
            "proved bit ranges, exact quantization scale, missing-lane reconstruction, and selector rotation",
            "proved shortest-path polynomial interpolation and its exact constant table",
            "proved frame stride and logical-map addressing for all 67 full clips and 155642 units",
            "proved mode-0 mirrored output flips logical lanes 2 and 3",
            "proved inverse type-6 pack symmetry and three concrete runtime caller paths",
        ],
        "failed": [
            "a bit-exact software model of the Xenon vrsqrtefp estimate was not recovered",
            "map modes 1 and 2 are outside this bounded mode-0 decoder proof",
            "the 11328 optional packed bytes are excluded because this sampler reads +0x20 only",
            "logical lanes and map indices are not yet bound to named skeleton bones or coordinate axes",
        ],
        "portme": [
            "// PORTME at 0x846384A8 and 0x84638610: emulate Xenon vrsqrtefp for bit-exact output.",
            "// PORTME at 0x846385A8: preserve VMX floating rounding, NaN, and exception behavior if exact replay is required.",
            "// PORTME at 0x8463A4F0 / 0x84639938: recover packed-map mode 2.",
            "// PORTME at 0x8463A52C: recover packed-map mode 1.",
            "// PORTME at 0x8463A4B0: bind each logical map record to a proved skeleton bone before glTF export.",
            "// PORTME at 0x8463A46C and 0x8463A684: name mirrored lanes 2 and 3 only after coordinate-axis proof.",
            "// PORTME at 0x8463A38C: this path reads root +0x20; locate the consumer of optional serialized +0x2C before decoding that stream.",
        ],
        "export_status": "no glTF emitted; bone names, axes, handedness, and skeleton binding remain unproved",
    }
    return report, rows


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--inventory", type=Path, required=True)
    result.add_argument("--corpus", type=Path, required=True)
    result.add_argument("--trace", type=Path, required=True)
    result.add_argument("--pseudo", type=Path, required=True)
    result.add_argument("--vmx", type=Path, required=True)
    result.add_argument("--json", type=Path, required=True)
    result.add_argument("--clips-tsv", type=Path, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    report, rows = build_report(args)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_tsv(args.clips_tsv, rows)
    print(
        "APF_PACKED_POSE_DECODER_COMPLETE "
        f"clips={report['proved_mode0_codec']['corpus']['clip_count']} "
        f"units={report['proved_mode0_codec']['corpus']['unit_count']}"
    )


if __name__ == "__main__":
    main()
