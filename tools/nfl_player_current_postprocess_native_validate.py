#!/usr/bin/env python3
"""Compare the portable 0x00093850 subset with an independent Python oracle."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
from pathlib import Path
import random
import struct

from nfl_rest_orientation import xbe_reader


LOW = 25
HIGH = 62
PROFILES = 4
PROFILE_VA = 0x004EF018
PROFILE_STRIDE = 0xD0
SCHEDULE_VA = 0x004EF898


class Profile(ctypes.Structure):
    _fields_ = [
        ("reference", ctypes.c_float),
        ("multiplier", ctypes.c_float),
        ("lower", ctypes.c_float * LOW),
        ("upper", ctypes.c_float * LOW),
    ]


class Tables(ctypes.Structure):
    _fields_ = [
        ("profiles", Profile * PROFILES),
        ("high_source", ctypes.c_uint8 * HIGH),
    ]


Matrix = ctypes.c_float * 16


class Matrices(ctypes.Structure):
    _fields_ = [("low", Matrix * LOW), ("high", Matrix * HIGH)]


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def add(a: float, b: float) -> float:
    return f32(f32(a) + f32(b))


def sub(a: float, b: float) -> float:
    return f32(f32(a) - f32(b))


def mul(a: float, b: float) -> float:
    return f32(f32(a) * f32(b))


def matrix_multiply(left: list[float], right: list[float]) -> list[float]:
    output = [0.0] * 16
    for row in range(4):
        for column in range(4):
            value = add(
                mul(left[row * 4], right[column]),
                mul(left[row * 4 + 1], right[4 + column]),
            )
            value = add(value, mul(left[row * 4 + 2], right[8 + column]))
            value = add(value, mul(left[row * 4 + 3], right[12 + column]))
            output[row * 4 + column] = value
    return output


def perpendicular(axis: list[float], scale: float) -> list[float]:
    delta = sub(1.0, scale)
    x, y, z = axis[:3]
    result = [0.0] * 16
    result[0] = add(mul(mul(x, x), delta), scale)
    result[1] = mul(mul(y, x), delta)
    result[2] = mul(mul(z, x), delta)
    result[4] = mul(mul(y, x), delta)
    result[5] = add(mul(mul(y, y), delta), scale)
    result[6] = mul(mul(y, z), delta)
    result[8] = mul(mul(z, x), delta)
    result[9] = mul(mul(y, z), delta)
    result[10] = add(mul(mul(z, z), delta), scale)
    result[15] = 1.0
    return result


def transform_xyz(matrix: list[float], vector: list[float]) -> list[float]:
    x, y, z = vector[:3]
    return [
        add(add(mul(matrix[8], z), mul(x, matrix[0])), mul(matrix[4], y)),
        add(add(mul(matrix[9], z), mul(matrix[1], x)), mul(matrix[5], y)),
        add(add(mul(matrix[10], z), mul(matrix[2], x)), mul(matrix[6], y)),
        add(add(mul(matrix[11], z), mul(matrix[3], x)), mul(matrix[7], y)),
    ]


def normalize4(vector: list[float]) -> list[float]:
    squared = add(
        add(mul(vector[3], vector[3]), mul(vector[2], vector[2])),
        add(mul(vector[1], vector[1]), mul(vector[0], vector[0])),
    )
    if squared == 0.0:
        return [0.0] * 4
    inverse = f32(1.0 / f32(math.sqrt(squared)))
    return [mul(value, inverse) for value in vector]


def pretranslate(matrix: list[float], x: float, y: float, z: float) -> None:
    matrix[12] = add(add(add(mul(matrix[8], z), mul(x, matrix[0])), mul(matrix[4], y)), matrix[12])
    matrix[13] = add(add(add(mul(matrix[9], z), mul(matrix[5], y)), mul(matrix[1], x)), matrix[13])
    matrix[14] = add(add(add(mul(matrix[10], z), mul(matrix[6], y)), mul(matrix[2], x)), matrix[14])


def profile_scale(profile: dict[str, object], channel: int, parameter: float) -> float:
    lower = float(profile["lower"][channel])
    upper = float(profile["upper"][channel])
    return add(mul(sub(upper, lower), parameter), lower)


def oracle(
    field18: int, field2a: int, mask: int, special: bool,
    vectors: list[list[float]], profiles: list[dict[str, object]],
    schedule: list[int], low: list[list[float]], high: list[list[float]],
) -> None:
    scalar = f32(field2a + 150)
    if 450.0 <= scalar:
        scalar = 450.0
    elif scalar <= 150.0:
        scalar = 150.0
    profile = profiles[(field18 >> 3) & 3]
    parameter = mul(sub(scalar, float(profile["reference"])), float(profile["multiplier"]))

    for index in range(LOW):
        if not mask & (1 << index):
            continue
        scale = profile_scale(profile, index, parameter)
        low[index] = matrix_multiply(perpendicular(vectors[index], scale), low[index])

    for index, source in enumerate(schedule):
        if not mask & (1 << source):
            continue
        scale = profile_scale(profile, source, parameter)
        axis = normalize4(transform_xyz(high[index], vectors[source]))
        pivot = perpendicular(axis, scale)
        x, y, z = high[index][12:15]
        pretranslate(pivot, -x, -y, -z)
        pivot[12] = add(pivot[12], x)
        pivot[13] = add(pivot[13], y)
        pivot[14] = add(pivot[14], z)
        high[index] = matrix_multiply(high[index], pivot)

    if special and mask & 0x1000:
        for lane in (0, 1, 2, 4, 5, 6, 8, 9, 10):
            low[12][lane] = mul(low[12][lane], f32(1.9))


def skeleton_vectors(path: Path) -> list[list[float]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    matches = [
        record["semantic"]
        for record in report["records"]
        if record.get("kind") == "SKEL" and
        record.get("semantic", {}).get("name") == "skeleton"
    ]
    if len(matches) != 1:
        raise ValueError("expected one named skeleton resource")
    records = matches[0]["records"]
    if len(records) != LOW:
        raise ValueError("wrong skeleton record count")
    return [[f32(value) for value in record["values"]] for record in records]


def load_tables(xbe_path: Path, header_path: Path) -> tuple[Tables, list[dict[str, object]], list[int]]:
    xbe = xbe_path.read_bytes()
    header = json.loads(header_path.read_text(encoding="utf-8"))
    read = xbe_reader(xbe, header)
    native = Tables()
    profiles: list[dict[str, object]] = []
    for profile_index in range(PROFILES):
        values = struct.unpack(
            "<52f", read(PROFILE_VA + profile_index * PROFILE_STRIDE, PROFILE_STRIDE)
        )
        profile = {
            "reference": f32(values[0]),
            "multiplier": f32(values[1]),
            "lower": [f32(values[2 + index * 2]) for index in range(LOW)],
            "upper": [f32(values[3 + index * 2]) for index in range(LOW)],
        }
        profiles.append(profile)
        native.profiles[profile_index].reference = float(profile["reference"])
        native.profiles[profile_index].multiplier = float(profile["multiplier"])
        for index in range(LOW):
            native.profiles[profile_index].lower[index] = profile["lower"][index]
            native.profiles[profile_index].upper[index] = profile["upper"][index]
    schedule = list(read(SCHEDULE_VA, HIGH))
    for index, source in enumerate(schedule):
        native.high_source[index] = source
    return native, profiles, schedule


def random_matrix(rng: random.Random) -> list[float]:
    # Affine, non-singular-enough witnesses. Exact orthonormality is not an
    # input requirement of 0x00093850 and would reduce numeric coverage.
    matrix = [0.0] * 16
    for row in range(3):
        for column in range(3):
            matrix[row * 4 + column] = f32(rng.uniform(-0.35, 0.35))
        matrix[row * 4 + row] = add(matrix[row * 4 + row], 1.0)
    matrix[12] = f32(rng.uniform(-40.0, 40.0))
    matrix[13] = f32(rng.uniform(-40.0, 40.0))
    matrix[14] = f32(rng.uniform(-40.0, 40.0))
    matrix[15] = 1.0
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--xbe", type=Path, default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"))
    parser.add_argument("--xbe-header", type=Path, default=Path("reports/headers/nfl2k5_xbe_header.json"))
    parser.add_argument("--scene-probe", type=Path, default=Path("reports/assets/nfl2k5_scene_audio_probe.json"))
    args = parser.parse_args()

    library = ctypes.CDLL(str(args.library.resolve()))
    function = library.vc_nfl_player_current_postprocess
    function.argtypes = [
        ctypes.c_uint32, ctypes.c_uint8, ctypes.c_uint32, ctypes.c_bool,
        ctypes.POINTER(ctypes.c_float), ctypes.POINTER(Tables), ctypes.POINTER(Matrices),
    ]
    function.restype = ctypes.c_int

    tables, profiles, schedule = load_tables(args.xbe, args.xbe_header)
    vectors = skeleton_vectors(args.scene_probe)
    flat_vectors = (ctypes.c_float * (LOW * 4))(
        *(value for vector in vectors for value in vector)
    )
    rng = random.Random(0x93850)
    masks = [0, 0x01FFFFFF, 0x00001800, 0x01FFE7FF]
    masks.extend(1 << index for index in range(LOW))
    scalar_bytes = (0, 30, 90, 255)
    cases = 0
    maximum_error = 0.0

    for profile_index in range(PROFILES):
        for case_index, mask in enumerate(masks):
            field18 = profile_index << 3
            field2a = scalar_bytes[(profile_index + case_index) % len(scalar_bytes)]
            special = (case_index & 1) != 0
            low = [random_matrix(rng) for _ in range(LOW)]
            high = [random_matrix(rng) for _ in range(HIGH)]
            expected_low = [row[:] for row in low]
            expected_high = [row[:] for row in high]
            oracle(
                field18, field2a, mask, special, vectors, profiles, schedule,
                expected_low, expected_high,
            )

            matrices = Matrices()
            for index, matrix in enumerate(low):
                for lane, value in enumerate(matrix):
                    matrices.low[index][lane] = value
            for index, matrix in enumerate(high):
                for lane, value in enumerate(matrix):
                    matrices.high[index][lane] = value
            status = function(
                field18, field2a, mask, special, flat_vectors,
                ctypes.byref(tables), ctypes.byref(matrices),
            )
            if status != 0:
                raise SystemExit(f"native status {status} in case {cases}")
            for actual_matrix, expected_matrix in zip(matrices.low, expected_low, strict=True):
                for actual, expected in zip(actual_matrix, expected_matrix, strict=True):
                    maximum_error = max(maximum_error, abs(float(actual) - expected))
            for actual_matrix, expected_matrix in zip(matrices.high, expected_high, strict=True):
                for actual, expected in zip(actual_matrix, expected_matrix, strict=True):
                    maximum_error = max(maximum_error, abs(float(actual) - expected))
            cases += 1

    # sqrtf/rsqrt replacement and compiler evaluation order can differ by a
    # few ulps. This limit is still narrow enough to catch matrix order,
    # schedule, mask, pivot, profile, and conditional-stage mistakes.
    if maximum_error > 5.0e-5:
        raise SystemExit(f"maximum native/oracle error {maximum_error} exceeds limit")
    print(
        "NFL_PLAYER_CURRENT_POSTPROCESS_NATIVE_PASS "
        f"cases={cases} masks={len(masks)} max_error={maximum_error:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
