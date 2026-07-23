#!/usr/bin/env python3
"""Compare native NFL 2K5 trajectory decoding with all shipped records."""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


WRAPPER_SIZE = 0x20
EXPECTED_RECORDS = 567_075
EXPECTED_RECORDS_BY_STRIDE = {6: 451_676, 8: 115_399}
EXPECTED_ROOTS_BY_STRIDE = {6: 4_263, 8: 1_805}
EXPECTED_MINIMUM = [-11_599, -29, -8_900, -11_991]
EXPECTED_MAXIMUM = [7_985, 3_530, 12_287, 10_545]


class NativeSample(ctypes.Structure):
    _fields_ = [
        ("lanes", ctypes.c_float * 3),
        ("packed_lanes", ctypes.c_int16 * 4),
        ("yaw_like", ctypes.c_int32),
        ("has_yaw_like", ctypes.c_bool),
    ]


class Comparator:
    def __init__(self, library_path: Path) -> None:
        library = ctypes.CDLL(str(library_path))
        self.decode_many = library.vc_nfl_trajectory_decode_many_le
        self.decode_many.argtypes = [
            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t, ctypes.c_size_t,
            ctypes.POINTER(NativeSample), ctypes.POINTER(ctypes.c_size_t),
        ]
        self.decode_many.restype = ctypes.c_int
        self.record_counts: Counter[int] = Counter()
        self.root_counts: Counter[int] = Counter()
        self.minimum = [32_767, 32_767, 32_767, 32_767]
        self.maximum = [-32_768, -32_768, -32_768, -32_768]

    def compare(self, encoded: bytes, stride: int) -> None:
        if len(encoded) % stride:
            raise ValueError("trajectory payload does not tile by its stride")
        count = len(encoded) // stride
        source = (ctypes.c_uint8 * len(encoded)).from_buffer_copy(encoded)
        samples = (NativeSample * count)()
        failed = ctypes.c_size_t(count)
        status = self.decode_many(source, stride, count, samples,
                                  ctypes.byref(failed))
        if status != 0:
            raise ValueError(
                f"native decoder rejected record {int(failed.value)} "
                f"with status {status}"
            )
        format_string = "<hhh" if stride == 6 else "<hhhh"
        for index, values in enumerate(struct.iter_unpack(format_string, encoded)):
            native = samples[index]
            expected_packed = tuple(values) + ((0,) if stride == 6 else ())
            if tuple(native.packed_lanes) != expected_packed:
                raise ValueError("native signed-short decode differs")
            if native.has_yaw_like != (stride == 8):
                raise ValueError("native fourth-lane presence differs")
            expected_yaw = values[3] * 8 if stride == 8 else 0
            if native.yaw_like != expected_yaw:
                raise ValueError("native fourth-lane shift differs")
            for lane in range(3):
                expected = values[lane] * 0.125
                if float(native.lanes[lane]) != expected:
                    raise ValueError("native one-eighth float scale differs")
            for lane, value in enumerate(values):
                self.minimum[lane] = min(self.minimum[lane], value)
                self.maximum[lane] = max(self.maximum[lane], value)
        self.record_counts[stride] += count
        self.root_counts[stride] += 1


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
        if hashlib.sha256(body).hexdigest() != resource["decoded_sha256"]:
            raise ValueError("motion body differs from canonical inventory")
        regions = {
            (int(region["owner_root_index"]),
             int(region["owner_pointer_field_relative"])): region
            for region in resource["packed_regions"]
        }
        for root_index, root in enumerate(resource["roots"]):
            words = tuple(int(value, 16) for value in root["header_words"])
            frame_count = words[0] >> 16
            stride = 6 if (words[1] & 8) else 8
            region = regions[(root_index, 0x28)]
            start = int(region["offset"])
            encoded = body[start : start + frame_count * stride]
            comparator.compare(encoded, stride)

    if sum(comparator.record_counts.values()) != EXPECTED_RECORDS:
        raise ValueError("trajectory record count differs")
    if dict(comparator.record_counts) != EXPECTED_RECORDS_BY_STRIDE:
        raise ValueError("trajectory record stride distribution differs")
    if dict(comparator.root_counts) != EXPECTED_ROOTS_BY_STRIDE:
        raise ValueError("trajectory root stride distribution differs")
    if comparator.minimum != EXPECTED_MINIMUM:
        raise ValueError(f"trajectory minima differ: {comparator.minimum}")
    if comparator.maximum != EXPECTED_MAXIMUM:
        raise ValueError(f"trajectory maxima differ: {comparator.maximum}")
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
        print(f"nfl_trajectory_native_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_TRAJECTORY_NATIVE_FULL_CORPUS_PASS "
        f"records={sum(result.record_counts.values())} "
        f"stride6={result.record_counts[6]} stride8={result.record_counts[8]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
