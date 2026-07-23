#!/usr/bin/env python3
"""Pin NFL 2K5 axes, physical units, and root-motion composition.

The report deliberately separates direct instruction proof from corpus
corroboration and anatomical/content inference.  It does not flatten the
engine's caller-supplied external root into an assumed universal world node.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Callable, Iterable

import nfl_outer


SCHEMA = "nfl2k5_axis_root_motion/v1"
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
EXPECTED_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
WRAPPER_SIZE = 0x20
TRAJECTORY_SCALE_VA = 0x004F24E4
SINE_TABLE_VA = 0x004E53E8
SINE_TABLE_SIZE = 0x800
PLAYER_ROOT_BASELINE_VA = 0x004E5CAC
UNITS_PER_YARD = 91.44
METERS_PER_UNIT = 0.01

# End addresses are exclusive.  Disjoint Ghidra bodies are conservatively
# pinned through their highest byte; padding in those few gaps is evidence too.
FUNCTION_RANGES = (
    ("immediate_position_writer", 0x0002CA70, 0x0002CB46),
    ("position3_wrapper", 0x0002CB50, 0x0002CB85),
    ("field_rectangle_rasterizer", 0x0009B080, 0x0009B34F),
    ("field_boundary_builder", 0x0009BE70, 0x0009BFCE),
    ("field_scene_setup", 0x0009C160, 0x0009CA8D),
    ("trajectory_sampler", 0x000DEE30, 0x000DF030),
    ("trajectory_turn_accessor", 0x000DF220, 0x000DF2E5),
    ("trajectory_vertical_accessor", 0x000DF2F0, 0x000DF3CB),
    ("trajectory_interval", 0x000DF3D0, 0x000DF445),
    ("fixed_turn_sine_cosine", 0x002171C0, 0x00217221),
    ("sample_bone_plus_trajectory", 0x00218150, 0x002181F0),
    ("sample_local_motion", 0x00304B50, 0x00304BE5),
    ("compose_external_parent", 0x00304BF0, 0x00304C97),
    ("player_hierarchy_builder", 0x00093800, 0x00093849),
    ("player_motion_matrix_witness", 0x0035B520, 0x0035B651),
    ("quaternion_multiply", 0x003CA150, 0x003CA1DC),
    ("quaternion_rotate_vector", 0x003CA1E0, 0x003CA26E),
    ("quaternion_to_matrix", 0x003CA3D0, 0x003CA4D2),
)

FIELD_RECTS = (
    ("negative_lateral_boundary", (-27.125, -26.375, -60.0, 60.0)),
    ("positive_lateral_boundary", (26.375, 27.125, -60.0, 60.0)),
    ("positive_longitudinal_boundary", (-26.75, 26.75, 59.625, 60.375)),
    ("negative_longitudinal_boundary", (-26.75, 26.75, -60.375, -59.625)),
)

FIELD_RECT_PUSHES = (
    (0x0009BE90, 0x0009BE95, 0x0009BE9A, 0x0009BE9F),
    (0x0009BEA9, 0x0009BEAE, 0x0009BEB3, 0x0009BEB8),
    (0x0009BEC2, 0x0009BEC7, 0x0009BECC, 0x0009BED1),
    (0x0009BEDB, 0x0009BEE0, 0x0009BEE5, 0x0009BEEA),
)

PORTMES = [
    "// PORTME at 0x000DF3D0: preserve its asymmetric interval contract: X/Z/turn are differences, Y is the absolute end sample.",
    "// PORTME at 0x00304BF0: classify every caller's external parent as model, attachment, camera, or world space before flattening nodes.",
    "// PORTME at 0x00093800: retain caller-supplied external-root ownership; it is not universally world space.",
    "// PORTME: prove scene-node ownership and loop-boundary accumulation before emitting complete glTF root tracks.",
]


class EvidenceError(ValueError):
    """Raised when pinned executable or corpus evidence differs."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def float_text(value: float) -> str:
    return format(value, ".9g")


def xbe_reader(xbe: bytes, header: dict[str, object]) -> Callable[[int, int], bytes]:
    def read(va: int, size: int) -> bytes:
        for section in header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return xbe[offset:offset + size]
        raise EvidenceError(f"XBE VA 0x{va:08x}+0x{size:x} is not raw-backed")
    return read


def read_utf16le_z(read: Callable[[int, int], bytes], va: int, limit: int = 256) -> str:
    units: list[int] = []
    for index in range(limit):
        unit = struct.unpack("<H", read(va + index * 2, 2))[0]
        if unit == 0:
            return b"".join(struct.pack("<H", value) for value in units).decode("utf-16le")
        units.append(unit)
    raise EvidenceError(f"unterminated UTF-16LE string at 0x{va:08x}")


def executable_evidence(xbe_path: Path, header_path: Path) -> tuple[dict[str, object], Callable[[int, int], bytes]]:
    xbe = xbe_path.read_bytes()
    header = json.loads(header_path.read_text(encoding="utf-8"))
    md5 = hashlib.md5(xbe).hexdigest()
    digest = sha256(xbe)
    if md5 != EXPECTED_XBE_MD5 or digest != EXPECTED_XBE_SHA256:
        raise EvidenceError(f"unexpected NFL 2K5 executable {md5}/{digest}")
    if header.get("md5") != md5 or header.get("sha256") != digest:
        raise EvidenceError("XBE header report does not pin the supplied executable")
    read = xbe_reader(xbe, header)

    function_ranges = []
    for name, start, end in FUNCTION_RANGES:
        body = read(start, end - start)
        function_ranges.append({
            "name": name,
            "start": f"0x{start:08x}",
            "end_exclusive": f"0x{end:08x}",
            "size": len(body),
            "sha256": sha256(body),
        })

    scale_raw = struct.unpack("<I", read(TRAJECTORY_SCALE_VA, 4))[0]
    baseline_raw = struct.unpack("<I", read(PLAYER_ROOT_BASELINE_VA, 4))[0]
    if scale_raw != 0x3E000000 or baseline_raw != 0x42C80000:
        raise EvidenceError("trajectory scale or player-root baseline differs")

    sine_raw = read(SINE_TABLE_VA, SINE_TABLE_SIZE)
    sine_pairs = list(struct.iter_unpack("<ff", sine_raw))
    if len(sine_pairs) != 256:
        raise EvidenceError("fixed sine table does not have 256 intercept/slope pairs")

    def sine(angle: int) -> float:
        turn = angle & 0xFFFF
        intercept, slope = sine_pairs[turn >> 8]
        return intercept + slope * turn

    cardinals = []
    for angle in (0x0000, 0x4000, 0x8000, 0xC000):
        cardinals.append({
            "turn_units": angle,
            "fraction_of_turn": float_text(angle / 65536.0),
            "sine_table_value": float_text(sine(angle)),
            "cosine_table_value": float_text(sine(angle + 0x4000)),
        })
    maximum_sine_error = max(
        abs(sine(angle) - math.sin(angle * math.tau / 65536.0))
        for angle in range(65536)
    )

    strings = {
        f"0x{va:08x}": read_utf16le_z(read, va)
        for va in (0x00E66380, 0x00E664F0, 0x00E66534, 0x00E66540)
    }
    if strings != {
        "0x00e66380": "endzone_north_left",
        "0x00e664f0": "field",
        "0x00e66534": "ticks",
        "0x00e66540": "marks",
    }:
        raise EvidenceError(f"field strings differ: {strings}")

    rectangles = []
    for (name, yards), pushes in zip(FIELD_RECTS, FIELD_RECT_PUSHES):
        # x86 pushes the last C argument first.  Each instruction is PUSH imm32
        # (0x68), so reverse zMax,zMin,xMax,xMin into xMin,xMax,zMin,zMax.
        immediate_bits = []
        for va in pushes:
            encoded = read(va, 5)
            if encoded[0] != 0x68:
                raise EvidenceError(f"field argument at 0x{va:08x} is not PUSH imm32")
            immediate_bits.append(struct.unpack_from("<I", encoded, 1)[0])
        actual_bits = tuple(reversed(immediate_bits))
        units = tuple(struct.unpack("<f", struct.pack("<I", value))[0] for value in actual_bits)
        expected_units = tuple(f32(value * UNITS_PER_YARD) for value in yards)
        if tuple(struct.pack("<f", value) for value in units) != tuple(
            struct.pack("<f", value) for value in expected_units
        ):
            raise EvidenceError(f"field rectangle {name} immediates differ")
        recovered_yards = tuple(value / UNITS_PER_YARD for value in units)
        error = max(abs(a - b) for a, b in zip(yards, recovered_yards))
        if error > 2.0e-6:
            raise EvidenceError(f"field rectangle {name} no longer matches yard dimensions")
        rectangles.append({
            "name": name,
            "push_instruction_vas": [f"0x{value:08x}" for value in pushes],
            "immediate_bits_argument_order": [f"0x{value:08x}" for value in actual_bits],
            "x_min_units": float_text(units[0]),
            "x_max_units": float_text(units[1]),
            "z_min_units": float_text(units[2]),
            "z_max_units": float_text(units[3]),
            "x_min_yards": float_text(yards[0]),
            "x_max_yards": float_text(yards[1]),
            "z_min_yards": float_text(yards[2]),
            "z_max_yards": float_text(yards[3]),
            "yard_roundtrip_error": float_text(error),
        })

    return ({
        "md5": md5,
        "sha256": digest,
        "header_sha256": sha256_file(header_path),
        "function_ranges": function_ranges,
        "trajectory_scale": {
            "va": f"0x{TRAJECTORY_SCALE_VA:08x}",
            "bits": f"0x{scale_raw:08x}",
            "value": 0.125,
        },
        "player_root_baseline": {
            "va": f"0x{PLAYER_ROOT_BASELINE_VA:08x}",
            "bits": f"0x{baseline_raw:08x}",
            "value": 100.0,
            "consumer_instruction": "0x0035B5E1 FSUB [0x004E5CAC] before matrix m13",
        },
        "fixed_sine_table": {
            "va": f"0x{SINE_TABLE_VA:08x}",
            "size": len(sine_raw),
            "sha256": sha256(sine_raw),
            "pair_count": len(sine_pairs),
            "maximum_error_against_binary64_sine": float_text(maximum_sine_error),
            "cardinals": cardinals,
        },
        "field_strings": strings,
        "field_rectangles": rectangles,
    }, read)


def region_map(resource: dict[str, object]) -> dict[tuple[int, int], dict[str, object]]:
    result: dict[tuple[int, int], dict[str, object]] = {}
    for region in resource["packed_regions"]:
        key = (int(region["owner_root_index"]), int(region["owner_pointer_field_relative"]))
        if key in result:
            raise EvidenceError(f"duplicate packed region owner {key}")
        result[key] = region
    return result


def analyze_trajectories(index_path: Path, inventory_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    canonical = json.loads(inventory_path.read_text(encoding="utf-8"))
    if canonical.get("schema") != "nfl2k5_motion_inventory/v1":
        raise EvidenceError("unsupported motion inventory schema")
    if len(canonical.get("resources", [])) != 5198:
        raise EvidenceError("motion inventory is incomplete")
    archive = nfl_outer.parse_archive(index_path)

    minimum = [32767, 32767, 32767, 32767]
    maximum = [-32768, -32768, -32768, -32768]
    zero_counts = [0, 0, 0, 0]
    record_counts = [0, 0, 0, 0]
    stride_counts: Counter[int] = Counter()
    flag_counts: Counter[int] = Counter()
    final_minimum = [math.inf, math.inf, math.inf]
    final_maximum = [-math.inf, -math.inf, -math.inf]
    y_exact_100 = 0
    roots: list[dict[str, object]] = []
    groups: dict[tuple[str, int, int], list[dict[str, object]]] = defaultdict(list)
    body_count = 0
    total_records = 0

    for resource in canonical["resources"]:
        outer_index = int(resource["outer_index"])
        entry = archive.entries[outer_index]
        body = nfl_outer.read_entry_range(
            archive,
            entry,
            int(resource["chunk_offset"]) + WRAPPER_SIZE,
            int(resource["stored_size"]),
        )
        if sha256(body) != resource["decoded_sha256"]:
            raise EvidenceError(f"{resource['name']}: decoded body differs")
        body_count += 1
        regions = region_map(resource)
        for root_index, root in enumerate(resource["roots"]):
            root_offset = int(root["offset"])
            words = struct.unpack_from("<13I", body, root_offset)
            expected_words = tuple(int(value, 16) for value in root["header_words"])
            if words != expected_words:
                raise EvidenceError(f"{resource['name']} root {root_index}: header differs")
            frame_count = words[0] >> 16
            flags = words[1] & 0xFF
            stride = 6 if flags & 8 else 8
            region = regions[(root_index, 0x28)]
            start = int(region["offset"])
            payload_size = frame_count * stride
            payload = body[start:start + payload_size]
            if len(payload) != payload_size:
                raise EvidenceError(f"{resource['name']} root {root_index}: short trajectory")
            if sha256(body[start:int(region["end"])]) != region["sha256"]:
                raise EvidenceError(f"{resource['name']} root {root_index}: region hash differs")

            unpack = "<hhh" if stride == 6 else "<hhhh"
            first: tuple[int, ...] | None = None
            final: tuple[int, ...] | None = None
            for offset in range(0, payload_size, stride):
                values = struct.unpack_from(unpack, payload, offset)
                if first is None:
                    first = values
                final = values
                for lane, value in enumerate(values):
                    minimum[lane] = min(minimum[lane], value)
                    maximum[lane] = max(maximum[lane], value)
                    zero_counts[lane] += value == 0
                    record_counts[lane] += 1
            assert first is not None and final is not None
            total_records += frame_count
            stride_counts[stride] += 1
            flag_counts[flags] += 1
            decoded_final = [final[lane] * 0.125 for lane in range(3)]
            if flags & 4:
                decoded_final[0] = -decoded_final[0]
            for lane in range(3):
                final_minimum[lane] = min(final_minimum[lane], decoded_final[lane])
                final_maximum[lane] = max(final_maximum[lane], decoded_final[lane])
            y_exact_100 += final[1] == 800
            raw_turn = final[3] << 3 if stride == 8 else 0
            decoded_turn = -raw_turn if flags & 4 else raw_turn
            payload_hash = sha256(payload)
            item = {
                "outer_index": outer_index,
                "chunk_index": int(resource["chunk_index"]),
                "name": str(resource["name"]),
                "root_index": root_index,
                "frame_count": frame_count,
                "flags": flags,
                "stride": stride,
                "payload_sha256": payload_hash,
                "first_raw": list(first),
                "final_raw": list(final),
                "decoded_final": [float_text(value) for value in decoded_final],
                "decoded_final_turn_units": decoded_turn,
                "decoded_final_turn_degrees_modulo": float_text(
                    ((decoded_turn & 0xFFFF) * 360.0) / 65536.0
                ),
            }
            roots.append(item)
            groups[(payload_hash, frame_count, flags & ~4)].append(item)

    if body_count != 5198 or len(roots) != 6068 or total_records != 567075:
        raise EvidenceError(
            f"trajectory corpus differs: {body_count}/{len(roots)}/{total_records}"
        )

    paired_groups = [
        values for values in groups.values()
        if {bool(item["flags"] & 4) for item in values} == {False, True}
    ]
    paired_occurrences = sum(len(values) for values in paired_groups)
    paired_cross_products = sum(
        sum(not bool(item["flags"] & 4) for item in values)
        * sum(bool(item["flags"] & 4) for item in values)
        for values in paired_groups
    )

    witness_groups = sorted(
        paired_groups,
        key=lambda values: tuple(sorted(str(item["name"]) for item in values)),
    )
    mirror_witnesses: list[dict[str, object]] = []
    for values in witness_groups:
        names = " ".join(str(item["name"]) for item in values).upper()
        if "_L_" not in names or "_R_" not in names:
            continue
        normal = next(item for item in values if not item["flags"] & 4)
        mirrored = next(item for item in values if item["flags"] & 4)
        if normal["final_raw"] != mirrored["final_raw"]:
            raise EvidenceError("identical mirror-pair payloads decoded from different raw values")
        normal_final = [float(value) for value in normal["decoded_final"]]
        mirrored_final = [float(value) for value in mirrored["decoded_final"]]
        if not (
            mirrored_final[0] == -normal_final[0]
            and mirrored_final[1:] == normal_final[1:]
            and mirrored["decoded_final_turn_units"] == -normal["decoded_final_turn_units"]
        ):
            raise EvidenceError("mirror-pair decoded contract differs")
        mirror_witnesses.append({
            "normal_name": normal["name"],
            "mirrored_name": mirrored["name"],
            "payload_sha256": normal["payload_sha256"],
            "raw_final": normal["final_raw"],
            "normal_final": normal["decoded_final"],
            "mirrored_final": mirrored["decoded_final"],
            "normal_turn_units": normal["decoded_final_turn_units"],
            "mirrored_turn_units": mirrored["decoded_final_turn_units"],
        })
        if len(mirror_witnesses) == 12:
            break

    return ({
        "motion_inventory_sha256": sha256_file(inventory_path),
        "archive_index_sha256": sha256_file(index_path),
        "resource_count": body_count,
        "root_count": len(roots),
        "record_count": total_records,
        "stride_root_counts": {str(key): stride_counts[key] for key in sorted(stride_counts)},
        "flag_counts": {f"0x{key:02x}": flag_counts[key] for key in sorted(flag_counts)},
        "raw_lane_minimum": minimum,
        "raw_lane_maximum": maximum,
        "raw_lane_zero_count": zero_counts,
        "raw_lane_record_count": record_counts,
        "scaled_position_lane_minimum": [float_text(value * 0.125) for value in minimum[:3]],
        "scaled_position_lane_maximum": [float_text(value * 0.125) for value in maximum[:3]],
        "decoded_final_position_minimum": [float_text(value) for value in final_minimum],
        "decoded_final_position_maximum": [float_text(value) for value in final_maximum],
        "final_y_exact_100_count": y_exact_100,
        "turn_root_count": stride_counts[8],
        "turn_raw_short_unit_turn_units": 8,
        "turn_units_per_revolution": 65536,
        "turn_raw_short_unit_degrees": float_text(360.0 / 8192.0),
        "unique_payload_flagless_groups": len(groups),
        "identical_payload_mirror_pair_group_count": len(paired_groups),
        "identical_payload_mirror_pair_occurrence_count": paired_occurrences,
        "identical_payload_mirror_cross_product_count": paired_cross_products,
        "named_mirror_witnesses": mirror_witnesses,
    }, roots)


def analyze_bone_axes(hierarchy_path: Path) -> dict[str, object]:
    with hierarchy_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    if len(rows) != 125:
        raise EvidenceError(f"canonical hierarchy witness count differs: {len(rows)}")
    by_sample: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        by_sample[row["sample"]][row["transform_name"]] = row
    if len(by_sample) != 5:
        raise EvidenceError("canonical hierarchy sample count differs")

    pair_count = 0
    positive_left_count = 0
    maximum_pair_y_delta = 0.0
    maximum_pair_z_delta = 0.0
    vertical_spans: list[float] = []
    witnesses: list[dict[str, object]] = []
    for sample in sorted(by_sample):
        transforms = by_sample[sample]
        for name, left in sorted(transforms.items()):
            if not name.startswith("l") or "r" + name[1:] not in transforms:
                continue
            right = transforms["r" + name[1:]]
            left_x = float(left["absolute_x"])
            right_x = float(right["absolute_x"])
            pair_count += 1
            positive_left_count += left_x > right_x
            maximum_pair_y_delta = max(
                maximum_pair_y_delta,
                abs(float(left["absolute_y"]) - float(right["absolute_y"])),
            )
            maximum_pair_z_delta = max(
                maximum_pair_z_delta,
                abs(float(left["absolute_z"]) - float(right["absolute_z"])),
            )
        head = transforms["head"]
        left_foot = transforms["lfoot"]
        right_foot = transforms["rfoot"]
        head_y = float(head["absolute_y"])
        foot_y = min(float(left_foot["absolute_y"]), float(right_foot["absolute_y"]))
        if head_y <= foot_y:
            raise EvidenceError(f"{sample}: named head is not above named feet in lane Y")
        vertical_spans.append(head_y - foot_y)
        witnesses.append({
            "sample": sample,
            "left_femur_x": float_text(float(transforms["lfemur"]["absolute_x"])),
            "right_femur_x": float_text(float(transforms["rfemur"]["absolute_x"])),
            "head_y": float_text(head_y),
            "lowest_foot_y": float_text(foot_y),
            "head_to_foot_span": float_text(head_y - foot_y),
            "left_toes_local_z": float_text(float(transforms["ltoes"]["local_z"])),
            "right_toes_local_z": float_text(float(transforms["rtoes"]["local_z"])),
        })
    if positive_left_count != pair_count:
        raise EvidenceError("a canonical named left/right pair does not order left at greater X")

    return {
        "hierarchy_sha256": sha256_file(hierarchy_path),
        "sample_count": len(by_sample),
        "row_count": len(rows),
        "named_left_right_pair_count": pair_count,
        "left_x_greater_than_right_x_count": positive_left_count,
        "maximum_left_right_y_delta": float_text(maximum_pair_y_delta),
        "maximum_left_right_z_delta": float_text(maximum_pair_z_delta),
        "head_to_foot_span_minimum": float_text(min(vertical_spans)),
        "head_to_foot_span_maximum": float_text(max(vertical_spans)),
        "witnesses": witnesses,
    }


def build_report(
    index_path: Path,
    inventory_path: Path,
    xbe_path: Path,
    header_path: Path,
    hierarchy_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    executable, _read = executable_evidence(xbe_path, header_path)
    trajectories, roots = analyze_trajectories(index_path, inventory_path)
    bones = analyze_bone_axes(hierarchy_path)

    report: dict[str, object] = {
        "schema": SCHEMA,
        "sources": {
            "archive_index": str(index_path),
            "motion_inventory": str(inventory_path),
            "xbe": str(xbe_path),
            "xbe_header": str(header_path),
            "hierarchy_witnesses": str(hierarchy_path),
        },
        "executable": executable,
        "trajectory_corpus": trajectories,
        "bone_corpus": bones,
        "proved_contract": {
            "coordinate_axes": {
                "X": "field lateral; positive X is character-left in all canonical named skeleton witnesses",
                "Y": "vertical; positive Y points from named feet toward named head",
                "Z": "field longitudinal; positive/negative end signs are not assigned north/south by this trace",
            },
            "handedness": (
                "right-handed: 0x003CA150 is Hamilton multiplication, 0x003CA1E0 evaluates "
                "q*[0,v]*conjugate(q), and positive +Y fixed-turn rotation maps +Z to +X"
            ),
            "position_units": "centimeters; 1 engine position unit = 0.01 meter",
            "trajectory_position_quantum": "0.125 centimeter per serialized signed-short unit",
            "turn_units": (
                "65536 modulo units per revolution; serialized fourth short is shifted left by 3, "
                "so one raw unit is 8/65536 turn = 0.0439453125 degrees"
            ),
            "sample": "P(t) = [X(t),Y(t),Z(t),turn(t)]",
            "interval_0x000df3d0": (
                "D(t0,t1) = [X1-X0, Y1, Z1-Z0, t1-t0, turn1-turn0]; "
                "mirror negates X and turn only"
            ),
            "bone_plus_root_0x00218150": (
                "x = bone_x*cos(turn)+bone_z*sin(turn)+delta_x; "
                "y = bone_y+absolute_end_y; "
                "z = bone_z*cos(turn)-bone_x*sin(turn)+delta_z"
            ),
            "external_parent_0x00304bf0": (
                "scale local XYZ/W, rotate local quaternion and XZ by external +0x50 fixed turn, "
                "then add external matrix translation +0x30/+0x34/+0x38"
            ),
            "player_current_root_0x0035b520": (
                "sample pose and trajectory from 0 to current time, apply turn to the root quaternion, "
                "build its matrix, add trajectory X/(Y-100)/Z to m12/m13/m14 when enabled, "
                "then pass that matrix as the external root to 0x00093800"
            ),
            "gltf_basis": (
                "game and glTF are both right-handed and Y-up; retain XYZ/quaternion lanes and "
                "multiply all position translations by 0.01 for meters"
            ),
        },
        "proof_tiers": {
            "instruction_proof": [
                "0x0009BE70 sends football-field lateral/longitudinal constants to 0x0009B080; 0x0009B880 writes vertices as (first,0,second)",
                "0x000DEE30 scales trajectory lanes X/Y/Z by 1/8 and produces a fixed-turn integer from the optional fourth short",
                "0x000DF2F0 returns trajectory lane Y; 0x000DF220 returns turn; 0x000DF3D0 constructs the asymmetric interval result",
                "0x002171C0/0x00304700 return sine(angle) and sine(angle+quarter-turn)=cosine(angle)",
                "0x00218150 composes animated bone XYZ with root turn and trajectory XYZ",
                "0x00304B50 composes a local motion result; 0x00304BF0 scales/rotates/translates it into an external parent frame",
                "0x0035B520 writes trajectory X/(Y-100)/Z into matrix m12/m13/m14 before 0x00093800 expands player current matrices",
                "Hamilton multiplication/vector rotation prove a right-handed mathematical basis",
            ],
            "corpus_corroboration": [
                "all 567075 trajectory records in all 6068 roots obey the recovered layouts and domains",
                "692 identical-payload groups occur with both normal and mirror flag variants, covering 1392 occurrences",
                "all canonical named left/right bones place left at greater X; named heads are greater Y than named feet",
                "football-field constants are exact binary32 encodings of eighth-yard boundaries at 91.44 units per yard",
                "trajectory Y and the player matrix witness use a 100-unit root-height baseline consistent with centimeter-scale skeletons",
            ],
            "inference_only": [
                "named toes extend primarily toward positive Z in canonical rest witnesses, corroborating character-forward +Z; anatomy is not instruction proof",
                "the positive and negative longitudinal field ends are not assigned a universal north/south gameplay sign",
                "an external parent supplied to 0x00304BF0 or 0x00093800 may be model, attachment, camera, or world space depending on caller",
            ],
        },
        "portme": PORTMES,
    }
    return report, roots


def witness_rows(report: dict[str, object], roots: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rectangle in report["executable"]["field_rectangles"]:
        rows.append({
            "kind": "instruction_field_rectangle",
            "name": rectangle["name"],
            "a": rectangle["x_min_units"],
            "b": rectangle["x_max_units"],
            "c": rectangle["z_min_units"],
            "d": rectangle["z_max_units"],
            "detail": "X min/max then Z min/max; field vertex Y is exactly 0",
        })
    for item in report["bone_corpus"]["witnesses"]:
        rows.append({
            "kind": "corpus_named_skeleton",
            "name": item["sample"],
            "a": item["left_femur_x"],
            "b": item["right_femur_x"],
            "c": item["head_y"],
            "d": item["lowest_foot_y"],
            "detail": "left femur X, right femur X, head Y, lowest foot Y",
        })
    for item in report["trajectory_corpus"]["named_mirror_witnesses"]:
        rows.append({
            "kind": "corpus_identical_payload_mirror",
            "name": f"{item['normal_name']} | {item['mirrored_name']}",
            "a": item["normal_final"][0],
            "b": item["mirrored_final"][0],
            "c": item["normal_turn_units"],
            "d": item["mirrored_turn_units"],
            "detail": item["payload_sha256"],
        })
    # Preserve deterministic extreme endpoint witnesses without implying that
    # an asset name alone proves direction semantics.
    ranked = sorted(
        roots,
        key=lambda item: (
            -(abs(float(item["decoded_final"][0])) + abs(float(item["decoded_final"][2]))),
            str(item["name"]),
            int(item["outer_index"]),
            int(item["root_index"]),
        ),
    )[:12]
    for item in ranked:
        rows.append({
            "kind": "corpus_trajectory_endpoint",
            "name": item["name"],
            "a": item["decoded_final"][0],
            "b": item["decoded_final"][1],
            "c": item["decoded_final"][2],
            "d": item["decoded_final_turn_units"],
            "detail": f"outer={item['outer_index']} root={item['root_index']} flags=0x{item['flags']:02x}",
        })
    return rows


def write_json(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_tsv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("kind", "name", "a", "b", "c", "d", "detail"),
            dialect="excel-tab",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--motion-inventory", required=True, type=Path)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--xbe-header", required=True, type=Path)
    parser.add_argument("--hierarchy-tsv", required=True, type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--witnesses-tsv", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report, roots = build_report(
        args.index,
        args.motion_inventory,
        args.xbe,
        args.xbe_header,
        args.hierarchy_tsv,
    )
    write_json(args.json, report)
    write_tsv(args.witnesses_tsv, witness_rows(report, roots))
    print(
        "NFL_AXIS_ROOT_MOTION_REPORT_PASS "
        f"roots={report['trajectory_corpus']['root_count']} "
        f"records={report['trajectory_corpus']['record_count']} "
        f"mirror_groups={report['trajectory_corpus']['identical_payload_mirror_pair_group_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
