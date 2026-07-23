#!/usr/bin/env python3
"""Inventory NFL 2K5's fixed-angle quaternion interpolation implementation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any, Iterable


EXPECTED_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
SINE_TABLE_VA = 0x004E53E8
SINE_TABLE_SIZE = 0x800
THRESHOLD_VA = 0x004F24E8

FUNCTIONS = (
    ("cvttss2si_runtime", 0x00020B20, 0x09),
    ("sqrtss_runtime", 0x00020BC0, 0x19),
    ("fixed_asin_approximation", 0x00020C00, 0x9B),
    ("float_to_acos_turn_units", 0x00021390, 0x77),
    ("cvttss2si_engine_leaf", 0x003C9D10, 0x09),
    ("unreferenced_fixed_sine_evaluator", 0x003C9D80, 0x24),
    ("quaternion_interpolate", 0x003CA270, 0x15F),
)

CALL_SITES = (
    (0x0005CD16, 0x0005CC20),
    (0x000DF569, 0x000DF450),
    (0x000DF6DF, 0x000DF6A0),
    (0x000DF80F, 0x000DF700),
    (0x000DF887, 0x000DF700),
    (0x001C73F0, 0x001C71D0),
    (0x001CD315, 0x001CCFA0),
    (0x001DF680, 0x001DF430),
)

ANGLE_CONSTANT_VAS = (
    ("denominator_constant_0", 0x004E5BE8),
    ("denominator_constant_1", 0x004E5BEC),
    ("denominator_constant_2", 0x004E5BF0),
    ("numerator_constant_0", 0x004E5BF4),
    ("numerator_constant_1", 0x004E5BF8),
    ("numerator_constant_2", 0x004E5BFC),
    ("zero", 0x004E4180),
    ("half", 0x004E4184),
    ("one", 0x004E419C),
    ("quarter_turn_units", 0x004E5C78),
    ("minus_one", 0x004E5C7C),
    ("half_turn_units", 0x004E5C80),
    ("linear_threshold", THRESHOLD_VA),
)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def f32_raw(value: float) -> int:
    return struct.unpack("<I", struct.pack("<f", value))[0]


def format_float(value: float) -> str:
    return format(value, ".17g")


class XbeImage:
    def __init__(self, xbe_path: Path, header_path: Path) -> None:
        self.path = xbe_path
        self.data = xbe_path.read_bytes()
        self.header = json.loads(header_path.read_text(encoding="utf-8"))
        digest = hashlib.md5(self.data).hexdigest()
        if digest != EXPECTED_MD5:
            raise ValueError(f"unexpected NFL 2K5 XBE MD5 {digest}")
        self.md5 = digest

    def at(self, va: int, size: int) -> bytes:
        for section in self.header["sections"]:
            start = int(section["virtual_address"])
            raw_size = int(section["raw_size"])
            if start <= va and va + size <= start + raw_size:
                offset = int(section["raw_address"]) + va - start
                return self.data[offset : offset + size]
        raise ValueError(f"VA range is not file-backed: {va:#010x}+{size:#x}")

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.at(va, 4))[0]

    def float(self, va: int) -> float:
        return struct.unpack("<f", self.at(va, 4))[0]


def table_rows(image: XbeImage) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(256):
        va = SINE_TABLE_VA + index * 8
        base_raw, slope_raw = struct.unpack("<II", image.at(va, 8))
        rows.append(
            {
                "index": index,
                "va": va,
                "base_raw": base_raw,
                "base": struct.unpack("<f", struct.pack("<I", base_raw))[0],
                "slope_raw": slope_raw,
                "slope": struct.unpack("<f", struct.pack("<I", slope_raw))[0],
            }
        )
    return rows


def fixed_sine(angle: int, table: list[dict[str, Any]]) -> float:
    angle &= 0xFFFF
    entry = table[angle >> 8]
    return float(entry["base"]) + float(entry["slope"]) * angle


def fixed_angle_units(value: float, constants: dict[int, float]) -> int:
    """Binary64 semantic model of 0x21390; not an x87 bit-identity claim."""
    value = f32(value)
    if value < -1.0:
        return 0x8000
    if value > 1.0:
        return 0
    negative = value < 0.0
    work = -value if negative else value
    transformed = work > 0.5
    if transformed:
        work = f32(math.sqrt(f32((1.0 - work) * 0.5)))
    numerator = (
        (constants[0x004E5BFC] * work + constants[0x004E5BF8]) * work
        + constants[0x004E5BF4]
    )
    denominator = (
        (
            (work * constants[0x004E5BF0] - constants[0x004E5BEC]) * work
            - constants[0x004E5BE8]
        )
        * work
        + 1.0
    )
    approximation = numerator / denominator
    angle = 2.0 * approximation if transformed else 16384.0 - approximation
    if negative:
        angle = 32768.0 - angle
    return math.trunc(f32(angle + 0.5))


def cvtt_round_product(angle: int, t: float) -> int:
    product = float(angle) * f32(t)
    adjusted = product + 0.5 if product >= 0.0 else product - 0.5
    stored = f32(adjusted)
    if not math.isfinite(stored) or stored >= 2147483648.0 or stored < -2147483648.0:
        return -2147483648
    return math.trunc(stored)


def interpolate_reference(
    q0: Iterable[float],
    q1: Iterable[float],
    t: float,
    threshold: float,
    constants: dict[int, float],
    table: list[dict[str, Any]],
) -> dict[str, Any]:
    left = tuple(f32(value) for value in q0)
    right = tuple(f32(value) for value in q1)
    t = f32(t)
    dot = float(left[0]) * float(right[0])
    dot += float(left[1]) * float(right[1])
    dot += float(left[2]) * float(right[2])
    dot += float(left[3]) * float(right[3])
    negative = dot < 0.0
    absolute = -dot if negative else dot
    absolute_stored = f32(absolute)

    theta = -1
    step = -1
    if not math.isfinite(absolute) or absolute > threshold:
        branch = "linear"
        weight0 = 1.0 - t
        weight1 = float(t)
    else:
        branch = "fixed_slerp"
        theta = fixed_angle_units(absolute_stored, constants)
        step = cvtt_round_product(theta, t)
        denominator = fixed_sine(theta, table)
        inverse = 1.0 / denominator
        weight0 = fixed_sine((theta - step) & 0xFFFF, table) * inverse
        weight1 = fixed_sine(step & 0xFFFF, table) * inverse
    if negative:
        weight1 = -weight1
    output = tuple(
        f32(weight1 * float(right[lane]) + weight0 * float(left[lane]))
        for lane in range(4)
    )
    return {
        "dot": dot,
        "absolute_dot_stored": absolute_stored,
        "shortest_path_negated": negative,
        "branch": branch,
        "theta_units": theta,
        "step_units": step,
        "weight0": weight0,
        "weight1": weight1,
        "output": output,
    }


def vector_inputs(threshold: float) -> list[tuple[str, tuple[float, ...], tuple[float, ...], float]]:
    threshold_above = struct.unpack(
        "<f", struct.pack("<I", f32_raw(threshold) + 1)
    )[0]
    threshold_y = f32(math.sqrt(f32(1.0 - threshold * threshold)))
    threshold_above_y = f32(
        math.sqrt(f32(1.0 - threshold_above * threshold_above))
    )
    return [
        ("identity", (1, 0, 0, 0), (1, 0, 0, 0), 0.37),
        ("antipodal", (1, 0, 0, 0), (-1, 0, 0, 0), 0.37),
        ("orthogonal_half", (1, 0, 0, 0), (0, 1, 0, 0), 0.5),
        ("negative_dot", (1, 0, 0, 0), (-0.5, math.sqrt(0.75), 0, 0), 0.25),
        ("threshold_equal", (1, 0, 0, 0), (threshold, threshold_y, 0, 0), 0.5),
        (
            "threshold_above",
            (1, 0, 0, 0),
            (threshold_above, threshold_above_y, 0, 0),
            0.5,
        ),
        ("balanced_nontrivial", (0.5, 0.5, 0.5, 0.5), (0.5, -0.5, 0.5, -0.5), 0.3),
        ("extrapolate_negative", (1, 0, 0, 0), (0, 1, 0, 0), -0.25),
        ("extrapolate_high", (1, 0, 0, 0), (0, 1, 0, 0), 1.25),
    ]


def write_table_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, dialect="excel-tab", lineterminator="\n")
        writer.writerow(("index", "va", "base_raw", "base", "slope_raw", "slope"))
        for row in rows:
            writer.writerow(
                (
                    row["index"],
                    f"0x{row['va']:08x}",
                    f"0x{row['base_raw']:08x}",
                    format_float(row["base"]),
                    f"0x{row['slope_raw']:08x}",
                    format_float(row["slope"]),
                )
            )


def write_vectors_tsv(path: Path, vectors: list[dict[str, Any]]) -> None:
    fields = [
        "id", "q0_lane0", "q0_lane1", "q0_lane2", "q0_lane3",
        "q1_lane0", "q1_lane1", "q1_lane2", "q1_lane3",
        "t", "dot", "absolute_dot_stored", "shortest_path_negated", "branch",
        "theta_units", "step_units", "weight0", "weight1",
        "out_lane0", "out_lane1", "out_lane2", "out_lane3",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, dialect="excel-tab", lineterminator="\n")
        writer.writeheader()
        for vector in vectors:
            q0 = vector["q0"]
            q1 = vector["q1"]
            result = vector["result"]
            row: dict[str, Any] = {
                "id": vector["id"],
                "t": format_float(vector["t"]),
                "dot": format_float(result["dot"]),
                "absolute_dot_stored": format_float(result["absolute_dot_stored"]),
                "shortest_path_negated": int(result["shortest_path_negated"]),
                "branch": result["branch"],
                "theta_units": result["theta_units"],
                "step_units": result["step_units"],
                "weight0": format_float(result["weight0"]),
                "weight1": format_float(result["weight1"]),
            }
            for lane, suffix in enumerate(("lane0", "lane1", "lane2", "lane3")):
                row[f"q0_{suffix}"] = format_float(q0[lane])
                row[f"q1_{suffix}"] = format_float(q1[lane])
                row[f"out_{suffix}"] = format_float(result["output"][lane])
            writer.writerow(row)


def write_native_table(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "/* Generated from NFL 2K5 default.xbe:0x004E53E8 by",
        "   tools/nfl_quaternion_interpolation.py. */",
    ]
    for row in rows:
        lines.append(
            "    {UINT32_C(0x%08X), UINT32_C(0x%08X)}, /* %3d */"
            % (row["base_raw"], row["slope_raw"], row["index"])
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--table-tsv", type=Path, required=True)
    parser.add_argument("--vectors-tsv", type=Path, required=True)
    parser.add_argument("--native-table-inc", type=Path)
    args = parser.parse_args()

    image = XbeImage(args.xbe, args.xbe_header)
    table = table_rows(image)
    constants = {va: image.float(va) for _, va in ANGLE_CONSTANT_VAS}
    threshold = constants[THRESHOLD_VA]

    function_rows = []
    for name, va, size in FUNCTIONS:
        body = image.at(va, size)
        function_rows.append(
            {
                "name": name,
                "va": f"0x{va:08x}",
                "size": size,
                "sha256": hashlib.sha256(body).hexdigest(),
            }
        )

    caller_rows = []
    for call_va, owner_va in CALL_SITES:
        encoded = image.at(call_va, 5)
        if encoded[0] != 0xE8:
            raise ValueError(f"expected CALL rel32 at {call_va:#x}")
        displacement = struct.unpack_from("<i", encoded, 1)[0]
        target = call_va + 5 + displacement
        if target != 0x003CA270:
            raise ValueError(f"call at {call_va:#x} targets {target:#x}")
        caller_rows.append(
            {
                "call_va": f"0x{call_va:08x}",
                "owner_va": f"0x{owner_va:08x}",
                "target_va": "0x003ca270",
                "bytes": encoded.hex(),
            }
        )

    max_sine_error = (-1.0, -1, 0.0, 0.0)
    sine_squared_error = 0.0
    for angle in range(65536):
        actual = fixed_sine(angle, table)
        ideal = math.sin(math.tau * angle / 65536.0)
        error = abs(actual - ideal)
        sine_squared_error += error * error
        if error > max_sine_error[0]:
            max_sine_error = (error, angle, actual, ideal)

    angle_mismatches = 0
    maximum_angle_unit_error = 0
    maximum_angle_radian_error = (-1.0, -1.0)
    for index in range(65537):
        value = f32(index / 65536.0)
        actual = fixed_angle_units(value, constants)
        ideal = math.floor(math.acos(value) * 32768.0 / math.pi + 0.5)
        difference = abs(actual - ideal)
        if difference:
            angle_mismatches += 1
        maximum_angle_unit_error = max(maximum_angle_unit_error, difference)
        radians_error = abs(actual * math.pi / 32768.0 - math.acos(value))
        if radians_error > maximum_angle_radian_error[0]:
            maximum_angle_radian_error = (radians_error, value)

    vectors: list[dict[str, Any]] = []
    for vector_id, q0_source, q1_source, t_source in vector_inputs(threshold):
        q0 = tuple(f32(value) for value in q0_source)
        q1 = tuple(f32(value) for value in q1_source)
        t = f32(t_source)
        vectors.append(
            {
                "id": vector_id,
                "q0": q0,
                "q1": q1,
                "t": t,
                "result": interpolate_reference(q0, q1, t, threshold, constants, table),
            }
        )

    raw_table = image.at(SINE_TABLE_VA, SINE_TABLE_SIZE)
    report = {
        "schema": "nfl2k5_quaternion_interpolation/v1",
        "source": {
            "path": str(args.xbe),
            "md5": image.md5,
        },
        "function": {
            "entry_va": "0x003ca270",
            "abi": {
                "destination": "ECX: float[4]",
                "left": "EDX: const float[4]",
                "right": "stack+0x04: const float[4]",
                "t": "stack+0x08: float",
                "callee_stack_pop_bytes": 8,
                "return": "void",
            },
            "functions": function_rows,
            "call_site_count": len(caller_rows),
            "caller_function_count": len({row[1] for row in CALL_SITES}),
            "call_sites": caller_rows,
        },
        "constants": {
            label: {
                "va": f"0x{va:08x}",
                "raw": f"0x{image.u32(va):08x}",
                "value": format_float(image.float(va)),
            }
            for label, va in ANGLE_CONSTANT_VAS
        },
        "sine_table": {
            "va": "0x004e53e8",
            "size": SINE_TABLE_SIZE,
            "entry_count": 256,
            "entry_layout": "float32 base; float32 slope",
            "evaluation": "base[angle>>8] + uint16(angle) * slope[angle>>8]",
            "sha256": hashlib.sha256(raw_table).hexdigest(),
            "exhaustive_angle_count": 65536,
            "maximum_absolute_error_vs_sin": format_float(max_sine_error[0]),
            "maximum_error_angle_units": max_sine_error[1],
            "maximum_error_actual": format_float(max_sine_error[2]),
            "maximum_error_ideal": format_float(max_sine_error[3]),
            "rms_error_vs_sin": format_float(math.sqrt(sine_squared_error / 65536.0)),
        },
        "angle_helper": {
            "input_domain_used_here": "absolute float32 dot product",
            "output_domain": "0x0000..0x4000 for input 1..0",
            "full_turn_units": 65536,
            "threshold_angle_units": fixed_angle_units(threshold, constants),
            "sample_count": 65537,
            "binary64_model_mismatch_count_vs_ideal_rounded_acos": angle_mismatches,
            "maximum_unit_error_vs_ideal_rounded_acos": maximum_angle_unit_error,
            "maximum_radian_error_vs_ideal_acos": format_float(maximum_angle_radian_error[0]),
            "maximum_radian_error_input": format_float(maximum_angle_radian_error[1]),
            "model_fidelity": "instruction-equivalent topology; binary64 is not x87 bit identity",
        },
        "proved_semantics": {
            "component_convention": "adjacent Hamilton product 0x003ca150 proves lane 0 is scalar and lanes 1..3 are the vector; vector-to-world-axis names remain unproved",
            "dot_accumulation": "four float32 products accumulated on x87 in lane order 0..3",
            "shortest_path": "if dot<0, abs(dot) selects weights and only the right weight is negated",
            "branch": "linear iff abs(x87 dot)>float32(0x3f7ff2e5); equality uses fixed slerp",
            "linear_weights": "left=1-t; right=t; result is not normalized",
            "fixed_weights": "left=sin16(theta-round(theta*t))/sin16(theta); right=sin16(round(theta*t))/sin16(theta)",
            "fixed_rounding": "add +0.5 for nonnegative or -0.5 for negative, store float32, CVTTSS2SI",
            "angle_wrap": "sine operands use low uint16; table index is bits 15..8",
            "output": "four x87 weighted sums independently stored as float32; no normalization",
        },
        "reference_vectors": [
            {
                "id": vector["id"],
                "branch": vector["result"]["branch"],
                "shortest_path_negated": vector["result"]["shortest_path_negated"],
                "theta_units": vector["result"]["theta_units"],
                "step_units": vector["result"]["step_units"],
                "output": [format_float(value) for value in vector["result"]["output"]],
            }
            for vector in vectors
        ],
        "portme": [
            "PORTME at 0x003CA275..0x003CA3C8: reproduce x87 80-bit register lifetime and store rounding for bit-exact original-Xbox replay.",
            "PORTME at 0x00020C00 and 0x00021390: verify the host compiler's x87/SSE and floating-point-control-word behavior before claiming bit identity.",
            "PORTME at 0x003CA328..0x003CA377: retain the original 2 KiB sine table and x87 evaluation order when exact historical bits matter; libm slerp is only numerically equivalent.",
            "PORTME: caller ownership and vector-lane world-axis names remain unresolved; adjacent 0x003CA150 proves scalar lane 0 but not the engine's axis convention for lanes 1..3.",
        ],
    }

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_table_tsv(args.table_tsv, table)
    write_vectors_tsv(args.vectors_tsv, vectors)
    if args.native_table_inc is not None:
        write_native_table(args.native_table_inc, table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
