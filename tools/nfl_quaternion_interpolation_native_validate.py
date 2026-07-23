#!/usr/bin/env python3
"""Compare the portable NFL quaternion helper to the recovered semantic model."""

from __future__ import annotations

import argparse
import ctypes
import math
from pathlib import Path

from nfl_quaternion_interpolation import (
    ANGLE_CONSTANT_VAS,
    THRESHOLD_VA,
    XbeImage,
    f32,
    interpolate_reference,
    table_rows,
    vector_inputs,
)


class NativeInfo(ctypes.Structure):
    _fields_ = [
        ("branch", ctypes.c_int),
        ("shortest_path_negated", ctypes.c_bool),
        ("theta_units", ctypes.c_int32),
        ("step_units", ctypes.c_int32),
        ("left_weight", ctypes.c_float),
        ("right_weight", ctypes.c_float),
    ]


Float4 = ctypes.c_float * 4


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--xbe-header", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    args = parser.parse_args()

    image = XbeImage(args.xbe, args.xbe_header)
    table = table_rows(image)
    constants = {va: image.float(va) for _, va in ANGLE_CONSTANT_VAS}
    threshold = constants[THRESHOLD_VA]

    library = ctypes.CDLL(str(args.library.resolve()))
    interpolate = library.vc_nfl_quaternion_interpolate_portable
    interpolate.argtypes = [
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_float,
        ctypes.POINTER(NativeInfo),
    ]
    interpolate.restype = ctypes.c_int

    maximum_lane_error = 0.0
    maximum_weight_error = 0.0
    checked = 0

    def check(q0_source: tuple[float, ...], q1_source: tuple[float, ...], t_source: float) -> None:
        nonlocal maximum_lane_error, maximum_weight_error, checked
        q0 = tuple(f32(value) for value in q0_source)
        q1 = tuple(f32(value) for value in q1_source)
        t = f32(t_source)
        expected = interpolate_reference(q0, q1, t, threshold, constants, table)
        native_q0 = Float4(*q0)
        native_q1 = Float4(*q1)
        output = Float4()
        info = NativeInfo()
        status = interpolate(output, native_q0, native_q1, t, ctypes.byref(info))
        assert status == 0
        expected_branch = 0 if expected["branch"] == "linear" else 1
        assert info.branch == expected_branch
        assert bool(info.shortest_path_negated) == expected["shortest_path_negated"]
        assert info.theta_units == expected["theta_units"]
        assert info.step_units == expected["step_units"]
        for actual, wanted in zip(output, expected["output"], strict=True):
            difference = abs(float(actual) - float(wanted))
            maximum_lane_error = max(maximum_lane_error, difference)
            assert difference <= 2.0e-6
        for actual, wanted in (
            (info.left_weight, expected["weight0"]),
            (info.right_weight, expected["weight1"]),
        ):
            difference = abs(float(actual) - float(wanted))
            maximum_weight_error = max(maximum_weight_error, difference)
            assert difference <= 2.0e-6
        checked += 1

    t_values = (0.0, 0.125, 0.5, 0.875, 1.0, -0.25, 1.25)
    for index in range(65537):
        absolute = f32(index / 65536.0)
        signed = -absolute if index & 1 else absolute
        remainder = f32(math.sqrt(max(0.0, f32(1.0 - absolute * absolute))))
        check((1.0, 0.0, 0.0, 0.0), (signed, remainder, 0.0, 0.0),
              t_values[index % len(t_values)])

    for _, q0, q1, t in vector_inputs(threshold):
        check(q0, q1, t)

    print(
        "NFL_QUATERNION_INTERPOLATION_NATIVE_GRID_PASS "
        f"vectors={checked} max_lane_error={maximum_lane_error:.9g} "
        f"max_weight_error={maximum_weight_error:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
