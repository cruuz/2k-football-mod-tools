#!/usr/bin/env python3
"""Independent numeric oracle for the portable NFL 2K5 0x00092140 graph.

The oracle intentionally does not import or parse the C implementation.  It
loads the pinned title tables directly from default.xbe, executes a separate
Python description of the recovered ordered graph, and compares all 62x16
output lanes with a shared library built from the portable C source.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import json
import math
from pathlib import Path
import random
import struct

from nfl_rest_orientation import xbe_reader


LOW = 25
HIGH = 62
LOCAL_BASE = 0x004EF8E0
TITLE_MAP = [
    0, 1, 2, 3, 4, 13, 14, 15, 16, 26, 27, 28, 29,
    30, 31, 32, 0xFF, 37, 44, 45, 46, 0xFF, 51, 58, 59,
]
EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"


class Tables(ctypes.Structure):
    _fields_ = [
        ("low_to_high", ctypes.c_uint8 * LOW),
        ("angle_lut", ctypes.c_float * 512),
        ("angle_coefficients", ctypes.c_float * 6),
        ("projection_lower_clamp", ctypes.c_float),
        ("angle_scale", ctypes.c_float),
        ("blend_scale", ctypes.c_float),
        ("local_constants", ctypes.c_float * 351),
    ]


Matrix = ctypes.c_float * 16
Vector = ctypes.c_float * 4


class Matrices(ctypes.Structure):
    _fields_ = [("low", Matrix * LOW), ("high", Matrix * HIGH)]


Skeleton = Vector * LOW
TraceCallback = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32
)


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def add(left: float, right: float) -> float:
    return f32(f32(left) + f32(right))


def sub(left: float, right: float) -> float:
    return f32(f32(left) - f32(right))


def mul(left: float, right: float) -> float:
    return f32(f32(left) * f32(right))


def dot4(left: list[float], right: list[float]) -> float:
    value = add(mul(left[0], right[0]), mul(left[1], right[1]))
    value = add(value, mul(left[2], right[2]))
    return add(value, mul(left[3], right[3]))


def length4(value: list[float]) -> float:
    return f32(math.sqrt(max(0.0, dot4(value, value))))


def normalize4(value: list[float]) -> list[float]:
    squared = dot4(value, value)
    if squared == 0.0:
        return [0.0, 0.0, 0.0, 0.0]
    inverse = f32(1.0 / f32(math.sqrt(squared)))
    return [mul(lane, inverse) for lane in value]


def cross4(left: list[float], right: list[float]) -> list[float]:
    return [
        sub(mul(left[1], right[2]), mul(left[2], right[1])),
        sub(mul(left[2], right[0]), mul(left[0], right[2])),
        sub(mul(left[0], right[1]), mul(left[1], right[0])),
        0.0,
    ]


def matmul(left: list[float], right: list[float]) -> list[float]:
    output = [0.0] * 16
    for row in range(4):
        for column in range(4):
            value = add(
                mul(left[row * 4], right[column]),
                mul(left[row * 4 + 1], right[4 + column]),
            )
            value = add(value, mul(left[row * 4 + 2], right[8 + column]))
            output[row * 4 + column] = add(
                value, mul(left[row * 4 + 3], right[12 + column])
            )
    return output


def transform_xyz(matrix: list[float], vector: list[float]) -> list[float]:
    x, y, z = vector[:3]
    return [
        add(add(mul(matrix[8], z), mul(x, matrix[0])), mul(matrix[4], y)),
        add(add(mul(matrix[9], z), mul(matrix[1], x)), mul(matrix[5], y)),
        add(add(mul(matrix[10], z), mul(matrix[2], x)), mul(matrix[6], y)),
        add(add(mul(matrix[11], z), mul(matrix[3], x)), mul(matrix[7], y)),
    ]


def axis_rotation(axis: list[float], sine: float, cosine: float) -> list[float]:
    delta = sub(1.0, cosine)
    x, y, z = axis[:3]
    result = [0.0] * 16
    result[0] = add(mul(mul(x, x), delta), cosine)
    result[1] = add(mul(sine, z), mul(mul(y, x), delta))
    result[2] = sub(mul(mul(z, x), delta), mul(sine, y))
    result[4] = sub(mul(mul(y, x), delta), mul(sine, z))
    result[5] = add(mul(mul(y, y), delta), cosine)
    result[6] = add(mul(sine, x), mul(mul(z, y), delta))
    result[8] = add(mul(sine, y), mul(mul(z, x), delta))
    result[9] = sub(mul(mul(z, y), delta), mul(sine, x))
    result[10] = add(mul(mul(z, z), delta), cosine)
    result[15] = 1.0
    return result


def axis_scale(axis: list[float], scale: float) -> list[float]:
    delta = sub(scale, 1.0)
    x, y, z = axis[:3]
    result = [0.0] * 16
    result[0] = add(mul(mul(x, x), delta), 1.0)
    result[1] = mul(mul(y, x), delta)
    result[2] = mul(mul(z, x), delta)
    result[4] = mul(mul(y, x), delta)
    result[5] = add(mul(mul(y, y), delta), 1.0)
    result[6] = mul(mul(y, z), delta)
    result[8] = mul(mul(z, x), delta)
    result[9] = mul(mul(y, z), delta)
    result[10] = add(mul(mul(z, z), delta), 1.0)
    result[15] = 1.0
    return result


def axis_two_scale(
    axis: list[float], parallel: float, perpendicular: float
) -> list[float]:
    delta = sub(parallel, perpendicular)
    x, y, z = axis[:3]
    result = [0.0] * 16
    result[0] = add(mul(mul(x, x), delta), perpendicular)
    result[1] = mul(mul(y, x), delta)
    result[2] = mul(mul(x, z), delta)
    result[4] = mul(mul(y, x), delta)
    result[5] = add(mul(mul(y, y), delta), perpendicular)
    result[6] = mul(mul(y, z), delta)
    result[8] = mul(mul(x, z), delta)
    result[9] = mul(mul(y, z), delta)
    result[10] = add(mul(mul(z, z), delta), perpendicular)
    result[15] = 1.0
    return result


def scale_columns(matrix: list[float], x: float, y: float, z: float) -> None:
    for row in range(4):
        matrix[row * 4] = mul(matrix[row * 4], x)
        matrix[row * 4 + 1] = mul(matrix[row * 4 + 1], y)
        matrix[row * 4 + 2] = mul(matrix[row * 4 + 2], z)


def basis_a(second: list[float], primary: list[float]) -> list[float]:
    cross = normalize4(cross4(primary, second))
    result = [0.0] * 16
    result[0:3] = cross[:3]
    result[4:7] = primary[:3]
    result[8] = sub(mul(cross[1], primary[2]), mul(cross[2], primary[1]))
    result[9] = sub(mul(cross[2], primary[0]), mul(cross[0], primary[2]))
    result[10] = sub(mul(cross[0], primary[1]), mul(cross[1], primary[0]))
    result[15] = 1.0
    return result


def basis_b(second: list[float], primary: list[float]) -> list[float]:
    cross = normalize4(cross4(primary, second))
    result = [0.0] * 16
    result[0] = cross[0]
    result[1] = primary[0]
    result[2] = sub(mul(cross[1], primary[2]), mul(cross[2], primary[1]))
    result[4] = cross[1]
    result[5] = primary[1]
    result[6] = sub(mul(cross[2], primary[0]), mul(cross[0], primary[2]))
    result[8] = cross[2]
    result[9] = primary[2]
    result[10] = sub(mul(cross[0], primary[1]), mul(cross[1], primary[0]))
    result[15] = 1.0
    return result


def align_ratio(value: list[float], seed: list[float], other: list[float]) -> list[float]:
    seed_length = length4(seed)
    value_length = length4(value)
    seed_normalized = [f32(lane / seed_length) for lane in seed]
    value_normalized = [f32(lane / value_length) for lane in value]
    destination = basis_b(other, seed_normalized)
    scale_columns(destination, 1.0, f32(value_length / seed_length), 1.0)
    return matmul(destination, basis_a(other, value_normalized))


def align_vectors(seed: list[float], target: list[float]) -> list[float]:
    seed_length = length4(seed)
    target_length = length4(target)
    seed_normalized = [f32(lane / seed_length) for lane in seed]
    target_normalized = [f32(lane / target_length) for lane in target]
    destination = axis_scale(seed_normalized, f32(target_length / seed_length))
    cosine = dot4(target_normalized, seed_normalized)
    cross = cross4(seed_normalized, target_normalized)
    sine = length4(cross)
    axis = [f32(lane / sine) for lane in cross]
    return matmul(destination, axis_rotation(axis, sine, cosine))


def compose_nonuniform(
    value: list[float], seed: list[float], other: list[float],
    x_scale: float, y_scale: float, z_scale: float,
) -> list[float]:
    seed_length = length4(seed)
    value_length = length4(value)
    seed_normalized = [f32(lane / seed_length) for lane in seed]
    value_normalized = [f32(lane / value_length) for lane in value]
    destination = basis_b(other, seed_normalized)
    scale_columns(destination, x_scale, y_scale, z_scale)
    return matmul(destination, basis_a(other, value_normalized))


def add4(value: list[float], addend: list[float]) -> list[float]:
    return [add(a, b) for a, b in zip(value, addend, strict=True)]


def sub4(value: list[float], subtrahend: list[float]) -> list[float]:
    return [sub(a, b) for a, b in zip(value, subtrahend, strict=True)]


def truncate_i32(value: float) -> int:
    if not math.isfinite(value) or value >= 2147483648.0 or value < -2147483648.0:
        return -(1 << 31)
    return math.trunc(value)


def angle_units(tables: dict[str, object], first: float, second: float) -> int:
    sign = -1
    quadrant = 0x4000
    if second < 0.0:
        second = f32(-second)
        sign = 0
    if first < 0.0:
        first = f32(-first)
        sign = ~sign
        quadrant = -0x4000
    if second > first:
        ratio = f32(first / second)
        quadrant += (sign ^ 0x4000) - sign
        sign = ~sign
    else:
        if first == 0.0:
            return 0
        ratio = f32(second / first)
    coeff = tables["coeff"]
    assert isinstance(coeff, list)
    numerator = add(mul(add(mul(coeff[5], ratio), coeff[4]), ratio), coeff[3])
    denominator = add(
        mul(add(mul(add(mul(ratio, coeff[2]), coeff[1]), ratio), coeff[0]), ratio),
        1.0,
    )
    result = truncate_i32(add(f32(numerator / denominator), 0.5))
    return ((result ^ sign) - sign) + quadrant


def lut_rotation(
    tables: dict[str, object], axis: list[float], angle: int
) -> list[float]:
    lut = tables["lut"]
    assert isinstance(lut, list)
    angle16 = angle & 0xFFFF
    cosine_angle = (angle16 + 0x4000) & 0xFFFF
    sine_index = (angle16 >> 8) * 2
    cosine_index = (cosine_angle >> 8) * 2
    sine = add(mul(float(angle16), lut[sine_index + 1]), lut[sine_index])
    cosine = add(
        mul(float(cosine_angle), lut[cosine_index + 1]), lut[cosine_index]
    )
    return axis_rotation(axis, sine, cosine)


def project_sine_cosine(
    matrix: list[float], axis: list[float], tables: dict[str, object]
) -> tuple[float, float]:
    perpendicular = [f32(-axis[1]), axis[0], 0.0, 0.0]
    transformed = transform_xyz(matrix, perpendicular)
    projected = [sub(value, mul(dot4(transformed, axis), lane)) for value, lane in zip(transformed, axis, strict=True)]
    inverse_a = f32(1.0 / math.sqrt(add(mul(perpendicular[0], perpendicular[0]), mul(perpendicular[1], perpendicular[1]))))
    inverse_b = f32(1.0 / math.sqrt(dot4(projected, projected)))
    cosine = mul(
        mul(
            add(
                mul(projected[0], perpendicular[0]),
                mul(projected[1], perpendicular[1]),
            ),
            inverse_a,
        ),
        inverse_b,
    )
    if cosine > 1.0:
        cosine = 1.0
    elif cosine <= float(tables["clamp"]):
        cosine = -1.0
    sine = f32(math.sqrt(max(0.0, sub(1.0, mul(cosine, cosine)))))
    orientation = add(
        add(
            mul(
                sub(
                    mul(projected[1], perpendicular[0]),
                    mul(perpendicular[1], projected[0]),
                ),
                axis[2],
            ),
            mul(
                sub(
                    mul(projected[2], perpendicular[1]),
                    mul(projected[1], 0.0),
                ),
                axis[0],
            ),
        ),
        mul(
            sub(
                mul(projected[0], 0.0),
                mul(projected[2], perpendicular[0]),
            ),
            axis[1],
        ),
    )
    if orientation < 0.0:
        sine = f32(-sine)
    return sine, cosine


def oracle(
    skeleton: list[list[float]], tables: dict[str, object],
    low: list[list[float]], initial_high: list[list[float]],
) -> list[list[float]]:
    high = [row[:] for row in initial_high]
    constants = tables["local"]
    assert isinstance(constants, list)

    def c(address: int) -> float:
        return constants[(address - LOCAL_BASE) // 4]

    def v(address: int) -> list[float]:
        start = (address - LOCAL_BASE) // 4
        return constants[start : start + 4]

    for low_index, high_index in enumerate(TITLE_MAP):
        if high_index != 0xFF:
            high[high_index] = low[low_index][:]
    high[37] = matmul(high[37], low[16])
    high[51] = matmul(high[51], low[21])

    sine, cosine = project_sine_cosine(high[3], v(0x004EFDE0), tables)
    angle = f32(angle_units(tables, sine, cosine))
    high[6] = axis_two_scale(
        skeleton[2], sub(1.0, mul(angle, c(0x004EFE4C))),
        add(1.0, mul(angle, c(0x004EFE50))),
    )
    sine, cosine = project_sine_cosine(high[15], v(0x004EFDD0), tables)
    angle = f32(angle_units(tables, sine, cosine))
    high[18] = axis_two_scale(
        skeleton[6], sub(1.0, mul(angle, c(0x004EFE4C))),
        add(1.0, mul(angle, c(0x004EFE50))),
    )

    axis = normalize4(cross4(skeleton[1], skeleton[2]))
    sine, cosine = project_sine_cosine(high[2], axis, tables)
    left_leg = f32(angle_units(tables, sine, cosine))
    high[5] = lut_rotation(tables, axis, truncate_i32(mul(left_leg, c(0x004EFE48))))
    high[5] = matmul(
        axis_scale(v(0x004EFDC0), sub(1.0, mul(left_leg, c(0x004EFE44)))), high[5]
    )
    high[7] = lut_rotation(tables, axis, truncate_i32(mul(left_leg, float(tables["angle_scale"]))))
    high[7] = matmul(
        axis_scale(v(0x004EFDB0), add(1.0, mul(left_leg, c(0x004EFE50)))), high[7]
    )

    axis = normalize4(cross4(skeleton[5], skeleton[6]))
    sine, cosine = project_sine_cosine(high[14], axis, tables)
    right_leg = f32(angle_units(tables, sine, cosine))
    high[17] = lut_rotation(tables, axis, truncate_i32(mul(right_leg, c(0x004EFE48))))
    high[17] = matmul(
        axis_scale(v(0x004EFDA0), sub(1.0, mul(right_leg, c(0x004EFE44)))), high[17]
    )
    high[19] = lut_rotation(tables, axis, truncate_i32(mul(right_leg, float(tables["angle_scale"]))))
    high[19] = matmul(
        axis_scale(v(0x004EFD90), add(1.0, mul(right_leg, c(0x004EFE50)))), high[19]
    )

    sine, cosine = project_sine_cosine(high[1], skeleton[1], tables)
    high[9] = matmul(axis_rotation(skeleton[1], f32(-sine), cosine), high[1])
    half_sine = f32(math.sqrt(max(0.0, mul(sub(1.0, cosine), 0.5))))
    if sine < 0.0:
        half_sine = f32(-half_sine)
    half_cosine = f32(math.sqrt(max(0.0, add(mul(cosine, 0.5), 0.5))))
    high[10] = axis_rotation(skeleton[1], half_sine, half_cosine)

    sine, cosine = project_sine_cosine(high[13], skeleton[5], tables)
    high[21] = matmul(axis_rotation(skeleton[5], f32(-sine), cosine), high[13])
    half_sine = f32(math.sqrt(max(0.0, mul(sub(1.0, cosine), 0.5))))
    if sine < 0.0:
        half_sine = f32(-half_sine)
    half_cosine = f32(math.sqrt(max(0.0, add(mul(cosine, 0.5), 0.5))))
    high[22] = axis_rotation(skeleton[5], half_sine, half_cosine)

    value = add4(transform_xyz(high[10], v(0x004EFD80)), v(0x004EFD70))
    value = add4(transform_xyz(high[9], value), v(0x004EFD60))
    high[8] = align_ratio(value, v(0x004EFD50), v(0x004EFD40))
    value = add4(transform_xyz(high[7], v(0x004EFD30)), v(0x004EFD20))
    value = add4(transform_xyz(high[1], value), v(0x004EFD10))
    high[12] = align_vectors(v(0x004EFD00), value)
    value = add4(transform_xyz(high[22], v(0x004EFCF0)), v(0x004EFCE0))
    value = add4(transform_xyz(high[21], value), v(0x004EFCD0))
    high[20] = align_ratio(value, v(0x004EFCC0), v(0x004EFCB0))
    value = add4(transform_xyz(high[19], v(0x004EFCA0)), v(0x004EFC90))
    value = add4(transform_xyz(high[13], value), v(0x004EFC80))
    high[24] = align_vectors(v(0x004EFC70), value)

    left_value = add4(transform_xyz(high[1], v(0x004EFC60)), v(0x004EFC50))
    right_value = add4(transform_xyz(high[13], v(0x004EFC40)), v(0x004EFC30))
    for destination, source, scale_axis, scale_a, scale_b, angle_a, angle_b, rotate_axis in (
        (11, left_value, 0x004EFC20, 0x004EFE40, 0x004EFE3C, 0x004EFE38, 0x004EFE34, 0x004EFC10),
        (61, left_value, 0x004EFC00, 0x004EFE30, 0x004EFE2C, 0x004EFE28, 0x004EFE24, 0x004EFBF0),
        (23, right_value, 0x004EFBE0, 0x004EFE40, 0x004EFE3C, 0x004EFE38, 0x004EFE34, 0x004EFBD0),
        (60, right_value, 0x004EFBC0, 0x004EFE30, 0x004EFE2C, 0x004EFE28, 0x004EFE24, 0x004EFBB0),
    ):
        high[destination] = axis_scale(
            v(scale_axis), sub(1.0, add(mul(source[1], c(scale_a)), c(scale_b)))
        )
        rotation = lut_rotation(
            tables, v(rotate_axis), truncate_i32(add(mul(source[1], c(angle_a)), c(angle_b)))
        )
        high[destination] = matmul(high[destination], rotation)

    high[25] = basis_b(v(0x004EFB90), v(0x004EFBA0))
    scale_columns(
        high[25], 1.0,
        sub(1.0, mul(add(add(left_value[1], c(0x004EFE20)), right_value[1]), c(0x004EFE40))),
        1.0,
    )
    summed = normalize4([add(a, b) for a, b in zip(left_value, right_value, strict=True)])
    high[25] = matmul(high[25], basis_a(v(0x004EFB80), summed))

    sine, cosine = project_sine_cosine(high[37], skeleton[15], tables)
    cosine = f32(math.sqrt(max(0.0, add(mul(cosine, 0.5), 0.5))))
    sine = mul(f32(math.sqrt(max(0.0, mul(sub(1.0, cosine), 0.5)))), -1.0 if sine < 0.0 else 1.0)
    cosine = f32(math.sqrt(max(0.0, add(mul(cosine, 0.5), 0.5))))
    left_forearm = f32(angle_units(tables, sine, cosine))
    high[33] = axis_rotation(skeleton[15], sine, cosine)
    for destination in (34, 35, 36):
        high[destination] = high[33][:]

    sine, cosine = project_sine_cosine(high[51], skeleton[20], tables)
    cosine = f32(math.sqrt(max(0.0, add(mul(cosine, 0.5), 0.5))))
    sine = mul(f32(math.sqrt(max(0.0, mul(sub(1.0, cosine), 0.5)))), -1.0 if sine < 0.0 else 1.0)
    cosine = f32(math.sqrt(max(0.0, add(mul(cosine, 0.5), 0.5))))
    right_forearm = f32(angle_units(tables, sine, cosine))
    high[47] = axis_rotation(skeleton[20], sine, cosine)
    for destination in (48, 49, 50):
        high[destination] = high[47][:]

    for destination, twist, parent, first, first_add, second_add, seed in (
        (42, 33, 32, 0x004EFB70, 0x004EFB60, 0x004EFB50, 0x004EFB40),
        (40, 33, 32, 0x004EFB30, 0x004EFB20, 0x004EFB10, 0x004EFB00),
        (55, 47, 46, 0x004EFAF0, 0x004EFAE0, 0x004EFAD0, 0x004EFAC0),
        (54, 47, 46, 0x004EFAB0, 0x004EFAA0, 0x004EFA90, 0x004EFA80),
    ):
        value = add4(transform_xyz(high[twist], v(first)), v(first_add))
        value = add4(transform_xyz(high[parent], value), v(second_add))
        high[destination] = align_vectors(v(seed), value)

    value = add4(transform_xyz(high[32], v(0x004EFA70)), v(0x004EFA60))
    value = sub4(value, v(0x004EFA50))
    high[41] = axis_scale(v(0x004EFA30), mul(dot4(value, v(0x004EFA40)), c(0x004EFE1C)))
    value = add4(transform_xyz(high[46], v(0x004EFA20)), v(0x004EFA10))
    value = sub4(value, v(0x004EFA00))
    high[53] = axis_scale(v(0x004EF9E0), mul(dot4(value, v(0x004EF9F0)), c(0x004EFE18)))

    axis = normalize4(cross4(skeleton[14], skeleton[15]))
    sine, cosine = project_sine_cosine(high[32], axis, tables)
    upper_left = f32(angle_units(tables, sine, cosine))
    high[38] = lut_rotation(
        tables, v(0x004EF9D0),
        truncate_i32(add(mul(upper_left, c(0x004EFE14)), mul(left_forearm, float(tables["blend_scale"])))),
    )
    high[39] = axis_scale(v(0x004EF9C0), sub(1.0, mul(upper_left, c(0x004EFE10))))
    high[39] = matmul(
        high[39], lut_rotation(
            tables, v(0x004EF9B0),
            truncate_i32(add(mul(upper_left, c(0x004EFE08)), mul(left_forearm, c(0x004EFE0C)))),
        )
    )
    value = add4(transform_xyz(high[38], v(0x004EF9A0)), v(0x004EF990))
    value = sub4(value, v(0x004EF980))
    blend = add(mul(upper_left, c(0x004EFE00)), mul(left_forearm, c(0x004EFE04)))
    high[43] = compose_nonuniform(
        value, v(0x004EF970), v(0x004EF960),
        add(mul(blend, float(tables["blend_scale"])), 1.0),
        sub(1.0, mul(blend, 0.5)), add(blend, 1.0),
    )

    axis = normalize4(cross4(skeleton[19], skeleton[20]))
    sine, cosine = project_sine_cosine(high[46], axis, tables)
    upper_right = f32(angle_units(tables, sine, cosine))
    high[56] = lut_rotation(
        tables, v(0x004EF950),
        truncate_i32(add(mul(upper_right, c(0x004EFE14)), mul(right_forearm, float(tables["blend_scale"])))),
    )
    high[57] = axis_scale(v(0x004EF940), sub(1.0, mul(upper_right, c(0x004EFE10))))
    high[57] = matmul(
        high[57], lut_rotation(
            tables, v(0x004EF930),
            truncate_i32(add(mul(upper_right, c(0x004EFE08)), mul(right_forearm, c(0x004EFE0C)))),
        )
    )
    value = add4(transform_xyz(high[56], v(0x004EF920)), v(0x004EF910))
    value = sub4(value, v(0x004EF900))
    blend = add(mul(upper_right, c(0x004EFE44)), mul(right_forearm, c(0x004EFE04)))
    high[52] = compose_nonuniform(
        value, v(0x004EF8F0), v(0x004EF8E0),
        add(mul(blend, float(tables["blend_scale"])), 1.0),
        sub(1.0, mul(blend, 0.5)), add(blend, 1.0),
    )
    return high


def title_data(xbe_path: Path, header_path: Path, report_path: Path) -> tuple[Tables, dict[str, object], list[list[float]]]:
    xbe = xbe_path.read_bytes()
    if hashlib.md5(xbe).hexdigest() != EXPECTED_XBE_MD5:
        raise ValueError("unexpected default.xbe MD5")
    read = xbe_reader(xbe, json.loads(header_path.read_text(encoding="utf-8")))

    def floats(address: int, count: int) -> list[float]:
        return list(struct.unpack("<" + "f" * count, read(address, count * 4)))

    table_object = Tables()
    for index, value in enumerate(TITLE_MAP):
        table_object.low_to_high[index] = value
    lut = floats(0x004E53E8, 512)
    coeff = floats(0x004E5C4C, 6)
    local = floats(LOCAL_BASE, 351)
    for index, value in enumerate(lut):
        table_object.angle_lut[index] = value
    for index, value in enumerate(coeff):
        table_object.angle_coefficients[index] = value
    table_object.projection_lower_clamp = floats(0x004E5C7C, 1)[0]
    table_object.angle_scale = floats(0x004E696C, 1)[0]
    table_object.blend_scale = floats(0x004E6D5C, 1)[0]
    for index, value in enumerate(local):
        table_object.local_constants[index] = value
    tables: dict[str, object] = {
        "lut": [f32(value) for value in lut],
        "coeff": [f32(value) for value in coeff],
        "clamp": f32(table_object.projection_lower_clamp),
        "angle_scale": f32(table_object.angle_scale),
        "blend_scale": f32(table_object.blend_scale),
        "local": [f32(value) for value in local],
    }
    report = json.loads(report_path.read_text(encoding="utf-8"))
    skeleton = [
        [f32(value) for value in record["values"]]
        for record in report["function_0x00093850"]["skel_vectors"]
    ]
    if len(skeleton) != LOW:
        raise ValueError("wrong SKEL vector count")
    return table_object, tables, skeleton


def input_case(case: int) -> list[list[float]]:
    rng = random.Random(0x92140 + case * 7919)
    result: list[list[float]] = []
    for index in range(LOW):
        if case == 0:
            matrix = [0.0] * 16
            matrix[0] = matrix[5] = matrix[10] = matrix[15] = 1.0
        else:
            axis = normalize4([
                rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0),
                rng.uniform(-1.0, 1.0), 0.0,
            ])
            theta = rng.uniform(-0.55, 0.55)
            matrix = axis_rotation(axis, f32(math.sin(theta)), f32(math.cos(theta)))
        matrix[12] = f32((index - 12) * 0.07 + rng.uniform(-0.02, 0.02))
        matrix[13] = f32((index % 5) * 0.11 + rng.uniform(-0.02, 0.02))
        matrix[14] = f32((index % 7 - 3) * 0.05 + rng.uniform(-0.02, 0.02))
        result.append(matrix)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--xbe", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    parser.add_argument("--xbe-header", type=Path, default=Path("reports/headers/nfl2k5_xbe_header.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/assets/nfl_player_postprocess.json"))
    parser.add_argument("--calls", type=Path, default=Path("reports/assets/nfl_player_postprocess_calls.tsv"))
    args = parser.parse_args()

    table_object, tables, skeleton = title_data(args.xbe, args.xbe_header, args.report)
    skeleton_object = Skeleton()
    for index, vector in enumerate(skeleton):
        for lane, value in enumerate(vector):
            skeleton_object[index][lane] = value

    with args.calls.open(encoding="utf-8", newline="") as stream:
        calls = [
            int(row["callsite"], 16)
            for row in csv.DictReader(stream, delimiter="\t")
            if row["owner"] == "0x00092140"
        ]
    if len(calls) != 127 or calls != sorted(calls):
        raise ValueError("canonical 0x00092140 call ledger is not 127 ordered rows")

    library = ctypes.CDLL(str(args.library.resolve()))
    function = library.vc_nfl_player_local_postprocess_92140
    function.argtypes = [
        ctypes.POINTER(Skeleton), ctypes.POINTER(Tables), ctypes.POINTER(Matrices),
        TraceCallback, ctypes.c_void_p,
    ]
    function.restype = ctypes.c_int

    maximum = 0.0
    compared = 0
    for case in range(8):
        low = input_case(case)
        # Poison every high lane.  A missing persistent writer in either the
        # oracle or native graph therefore fails the finite-output check.
        initial_high = [[math.nan for _lane in range(16)] for _index in range(HIGH)]
        expected = oracle(skeleton, tables, low, initial_high)
        matrices = Matrices()
        for index in range(LOW):
            for lane in range(16):
                matrices.low[index][lane] = low[index][lane]
        for index in range(HIGH):
            for lane in range(16):
                matrices.high[index][lane] = initial_high[index][lane]

        observed_trace: list[tuple[int, int]] = []

        @TraceCallback
        def callback(_user: int, sequence: int, address: int) -> None:
            observed_trace.append((sequence, address))

        status = function(
            ctypes.byref(skeleton_object), ctypes.byref(table_object),
            ctypes.byref(matrices), callback, None,
        )
        if status != 0:
            raise ValueError(f"portable function failed case {case}: {status}")
        if observed_trace != list(enumerate(calls, 1)):
            raise ValueError(f"127-operation trace differs in case {case}")
        for index in range(LOW):
            for lane in range(16):
                if float(matrices.low[index][lane]) != low[index][lane]:
                    raise ValueError(
                        f"low input mutated case={case} low={index} lane={lane}"
                    )
        for index in range(HIGH):
            for lane in range(16):
                actual = float(matrices.high[index][lane])
                wanted = expected[index][lane]
                if not math.isfinite(actual) or not math.isfinite(wanted):
                    raise ValueError(f"non-finite output case={case} high={index} lane={lane}")
                difference = abs(actual - wanted)
                maximum = max(maximum, difference)
                tolerance = 2.5e-4 + abs(wanted) * 2.5e-5
                if difference > tolerance:
                    raise ValueError(
                        f"oracle mismatch case={case} high={index} lane={lane} "
                        f"actual={actual:.9g} expected={wanted:.9g} diff={difference:.9g} "
                        f"tolerance={tolerance:.9g}"
                    )
                compared += 1

    print(
        "NFL_PLAYER_92140_NATIVE_ORACLE_PASS "
        f"cases=8 calls_per_case=127 compared_lanes={compared} "
        f"max_abs_difference={maximum:.9g}"
    )


if __name__ == "__main__":
    main()
