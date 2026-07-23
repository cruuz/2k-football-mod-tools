#!/usr/bin/env python3
"""Compare the native NFL 2K5 quaternion decoder with every shipped record."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


WRAPPER_SIZE = 0x20
EXPECTED_MAIN = 14_073_985
EXPECTED_AUXILIARY = 17_311
EXPECTED_MAXIMUM_SQUARE_SUM = 382_874


class NativePose(ctypes.Structure):
    _fields_ = [
        ("lanes", ctypes.c_float * 4),
        ("packed_components", ctypes.c_int16 * 3),
        ("ideal_radicand", ctypes.c_float),
        ("omitted_component", ctypes.c_uint8),
    ]


def f32(raw: int) -> float:
    return struct.unpack("<f", struct.pack("<I", raw))[0]


def region_bytes(
    body: bytes, regions: dict[tuple[int, int], dict[str, object]],
    root_index: int, pointer_relative: int,
) -> bytes:
    region = regions[(root_index, pointer_relative)]
    return body[int(region["offset"]) : int(region["end"])]


class Comparator:
    def __init__(self, library_path: Path) -> None:
        library = ctypes.CDLL(str(library_path))
        self.decode_many = library.vc_nfl_packed_pose_decode_many_le_portable
        self.decode_many.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t,
            ctypes.POINTER(NativePose), ctypes.POINTER(ctypes.c_size_t),
        ]
        self.decode_many.restype = ctypes.c_int
        self.scale = f32(0x3AB55FA3)
        self.main_count = 0
        self.auxiliary_count = 0
        self.maximum_lane_error = 0.0
        self.maximum_radicand_error = 0.0
        self.maximum_square_sum = 0
        self.omitted_components: set[int] = set()

    def compare(self, encoded: bytes, *, auxiliary: bool) -> None:
        if len(encoded) % 4:
            raise ValueError("packed quaternion region is not dword aligned")
        count = len(encoded) // 4
        if count == 0:
            return
        source = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        poses = (NativePose * count)()
        failed = ctypes.c_size_t(count)
        status = self.decode_many(source, count, poses, ctypes.byref(failed))
        if status != 0:
            raise ValueError(
                f"native decoder rejected corpus record {int(failed.value)} "
                f"with status {status}"
            )

        for index, (word,) in enumerate(struct.iter_unpack("<I", encoded)):
            packed = (
                ((word >> 20) & 0x3FF) - 0x200,
                ((word >> 10) & 0x3FF) - 0x200,
                (word & 0x3FF) - 0x200,
            )
            omitted = word >> 30
            native = poses[index]
            if tuple(native.packed_components) != packed:
                raise ValueError("native signed-10 extraction differs")
            if native.omitted_component != omitted:
                raise ValueError("native omitted-component selector differs")

            stored = [value * self.scale for value in packed]
            radicand = 1.0 - sum(value * value for value in stored)
            if radicand < 0.0:
                raise ValueError("reference decoder found a negative radicand")
            lanes = list(stored)
            lanes.insert(omitted, math.sqrt(radicand))
            lane_error = max(
                abs(float(native.lanes[lane]) - lanes[lane])
                for lane in range(4)
            )
            self.maximum_lane_error = max(self.maximum_lane_error, lane_error)
            self.maximum_radicand_error = max(
                self.maximum_radicand_error,
                abs(float(native.ideal_radicand) - radicand),
            )
            if not all(math.isfinite(float(value)) for value in native.lanes):
                raise ValueError("native decoder emitted a non-finite lane")
            square_sum = sum(value * value for value in packed)
            self.maximum_square_sum = max(self.maximum_square_sum, square_sum)
            self.omitted_components.add(omitted)

        if auxiliary:
            self.auxiliary_count += count
        else:
            self.main_count += count


def validate(index_path: Path, inventory_path: Path, library_path: Path) -> Comparator:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "nfl2k5_motion_inventory/v1":
        raise ValueError("unsupported motion inventory schema")
    archive = nfl_outer.parse_archive(index_path)
    comparator = Comparator(library_path)

    for resource in inventory["resources"]:
        entry = archive.entries[int(resource["outer_index"])]
        body = nfl_outer.read_entry_range(
            archive, entry,
            int(resource["chunk_offset"]) + WRAPPER_SIZE,
            int(resource["stored_size"]),
        )
        regions = {
            (int(region["owner_root_index"]),
             int(region["owner_pointer_field_relative"])): region
            for region in resource["packed_regions"]
        }
        for root_index, root in enumerate(resource["roots"]):
            words = tuple(int(value, 16) for value in root["header_words"])
            main_count = (words[0] & 0xFF) * (words[0] >> 16)
            main = region_bytes(body, regions, root_index, 0x24)
            comparator.compare(main[:main_count * 4], auxiliary=False)

            if (root_index, 0x30) in regions:
                auxiliary = region_bytes(body, regions, root_index, 0x30)
                packed = bytearray()
                for offset in range(0, len(auxiliary), 12):
                    packed.extend(auxiliary[offset : offset + 4])
                comparator.compare(bytes(packed), auxiliary=True)

    if comparator.main_count != EXPECTED_MAIN:
        raise ValueError(f"main count differs: {comparator.main_count}")
    if comparator.auxiliary_count != EXPECTED_AUXILIARY:
        raise ValueError(f"auxiliary count differs: {comparator.auxiliary_count}")
    if comparator.maximum_square_sum != EXPECTED_MAXIMUM_SQUARE_SUM:
        raise ValueError("maximum quantized square sum differs")
    if comparator.omitted_components != {0, 1, 2, 3}:
        raise ValueError("not all omitted-component selectors were exercised")
    if comparator.maximum_lane_error >= 2e-7:
        raise ValueError(
            f"native lane error {comparator.maximum_lane_error} exceeds tolerance"
        )
    if comparator.maximum_radicand_error >= 2e-7:
        raise ValueError(
            "native radicand error "
            f"{comparator.maximum_radicand_error} exceeds tolerance"
        )
    return comparator


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--index", type=Path, required=True)
    result.add_argument("--inventory", type=Path, required=True)
    result.add_argument("--library", type=Path, required=True)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = validate(args.index, args.inventory, args.library)
    except (OSError, ValueError, KeyError, struct.error, nfl_outer.OuterError) as exc:
        print(f"nfl_packed_pose_native_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PACKED_POSE_NATIVE_FULL_CORPUS_PASS "
        f"main={result.main_count} auxiliary={result.auxiliary_count} "
        f"max_lane_error={result.maximum_lane_error:.9g} "
        f"max_radicand_error={result.maximum_radicand_error:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
