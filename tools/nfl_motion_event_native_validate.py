#!/usr/bin/env python3
"""Compare native NFL 2K5 event decoding with every shipped event stream."""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

import nfl_outer


WRAPPER_SIZE = 0x20
EXPECTED_STREAMS = 6_068
EXPECTED_NONEMPTY_STREAMS = 1_995
EXPECTED_EVENTS = 9_024
EXPECTED_EVENT_IDS = 59


class NativeEvent(ctypes.Structure):
    _fields_ = [
        ("raw_word", ctypes.c_uint32),
        ("tick", ctypes.c_uint32),
        ("event_id", ctypes.c_uint8),
        ("seconds", ctypes.c_float),
    ]


def f32(raw: int) -> float:
    return struct.unpack("<f", struct.pack("<I", raw))[0]


def validate(index_path: Path, inventory_path: Path, library_path: Path) -> dict[str, object]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "nfl2k5_motion_inventory/v1":
        raise ValueError("unsupported motion inventory schema")
    archive = nfl_outer.parse_archive(index_path)
    library = ctypes.CDLL(str(library_path))
    decoder = library.vc_nfl_motion_event_decode_le
    decoder.argtypes = [
        ctypes.POINTER(ctypes.c_uint8), ctypes.c_float,
        ctypes.POINTER(NativeEvent),
    ]
    decoder.restype = ctypes.c_int

    stream_count = 0
    nonempty_stream_count = 0
    event_count = 0
    event_ids: Counter[int] = Counter()
    maximum_seconds_error = 0.0

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
            time_scale = f32(words[4])
            region = regions[(root_index, 0x2C)]
            encoded = body[int(region["offset"]) : int(region["end"])]
            if not encoded or len(encoded) % 4:
                raise ValueError("event stream is not a nonempty dword sequence")
            raw_words = [item[0] for item in struct.iter_unpack("<I", encoded)]
            if raw_words[-1] != 0xFFFFFFFF or 0xFFFFFFFF in raw_words[:-1]:
                raise ValueError("event stream terminator differs")
            ticks: list[int] = []
            for offset, word in enumerate(raw_words):
                raw = (ctypes.c_uint8 * 4).from_buffer_copy(
                    encoded[offset * 4 : offset * 4 + 4]
                )
                native = NativeEvent(raw_word=7)
                status = decoder(raw, time_scale, ctypes.byref(native))
                if word == 0xFFFFFFFF:
                    if status != 1 or native.raw_word != 7:
                        raise ValueError("native terminator handling differs")
                    continue
                if status != 0:
                    raise ValueError(f"native decoder rejected event status={status}")
                tick = word >> 8
                event_id = word & 0xFF
                if (
                    native.raw_word != word or native.tick != tick
                    or native.event_id != event_id
                ):
                    raise ValueError("native event word split differs")
                seconds = tick * (1.0 / 65536.0) / time_scale
                maximum_seconds_error = max(
                    maximum_seconds_error,
                    abs(float(native.seconds) - seconds),
                )
                if not math.isfinite(float(native.seconds)):
                    raise ValueError("native event time is non-finite")
                ticks.append(tick)
                event_ids[event_id] += 1
                event_count += 1
            if ticks != sorted(ticks):
                raise ValueError("event ticks are not monotonic")
            stream_count += 1
            nonempty_stream_count += bool(ticks)

    if stream_count != EXPECTED_STREAMS:
        raise ValueError(f"event stream count differs: {stream_count}")
    if nonempty_stream_count != EXPECTED_NONEMPTY_STREAMS:
        raise ValueError("nonempty event stream count differs")
    if event_count != EXPECTED_EVENTS:
        raise ValueError(f"event count differs: {event_count}")
    if len(event_ids) != EXPECTED_EVENT_IDS:
        raise ValueError("event ID domain differs")
    if maximum_seconds_error >= 2e-6:
        raise ValueError(
            f"native event time error {maximum_seconds_error} exceeds tolerance"
        )
    return {
        "streams": stream_count,
        "nonempty_streams": nonempty_stream_count,
        "events": event_count,
        "event_ids": len(event_ids),
        "maximum_seconds_error": maximum_seconds_error,
    }


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
        print(f"nfl_motion_event_native_validate: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_MOTION_EVENT_NATIVE_FULL_CORPUS_PASS "
        f"streams={result['streams']} events={result['events']} "
        f"ids={result['event_ids']} "
        f"max_seconds_error={result['maximum_seconds_error']:.9g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
