#!/usr/bin/env python3
"""Execute original default.xbe 0x00092140 and compare portable C output.

This optional high-strength gate uses Unicorn's 32-bit x86 CPU emulator.  It
maps the pinned XBE sections, patches only the runtime SKEL pointer and the
already-proved 25-byte LO->HI map, invokes the original function with its
recovered EAX/ECX/stack ABI, and compares all 62 matrices with native C.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_PROT_ALL
from unicorn.x86_const import (
    UC_X86_REG_EAX,
    UC_X86_REG_ECX,
    UC_X86_REG_EFLAGS,
    UC_X86_REG_EIP,
    UC_X86_REG_ESP,
    UC_X86_REG_MXCSR,
)

from nfl_player_92140_native_validate import (
    HIGH,
    LOW,
    Matrices,
    Skeleton,
    Tables,
    TITLE_MAP,
    TraceCallback,
    input_case,
    title_data,
)


EXPECTED_XBE_MD5 = "444064a9ec984dd29d2c05a43f5c96e8"
FUNCTION = 0x00092140
GLOBAL_SKEL_POINTER = 0x00B65B78
GLOBAL_LOW_TO_HIGH = 0x00B65BFC
MATRIX_BASE = 0x02000000
SKEL_OBJECT = 0x02100000
STACK_BASE = 0x02200000
SENTINEL = 0x02300000


def page_ceil(value: int) -> int:
    return (value + 0xFFF) & ~0xFFF


def emulate(
    xbe: bytes, header: dict[str, object], skeleton: list[list[float]],
    low: list[list[float]],
) -> list[list[float]]:
    emulator = Uc(UC_ARCH_X86, UC_MODE_32)
    image = header["header"]
    assert isinstance(image, dict)
    image_base = int(image["image_base"])
    image_size = page_ceil(int(image["image_size"]))
    emulator.mem_map(image_base, image_size, UC_PROT_ALL)
    emulator.mem_write(image_base, xbe[: int(image["headers_size"])])
    sections = header["sections"]
    assert isinstance(sections, list)
    for section in sections:
        assert isinstance(section, dict)
        raw_address = int(section["raw_address"])
        raw_size = int(section["raw_size"])
        emulator.mem_write(
            int(section["virtual_address"]),
            xbe[raw_address : raw_address + raw_size],
        )

    emulator.mem_map(MATRIX_BASE, 0x4000, UC_PROT_ALL)
    emulator.mem_map(SKEL_OBJECT, 0x2000, UC_PROT_ALL)
    emulator.mem_map(STACK_BASE, 0x20000, UC_PROT_ALL)
    emulator.mem_map(SENTINEL, 0x1000, UC_PROT_ALL)
    emulator.mem_write(
        SKEL_OBJECT + 0x10,
        b"".join(struct.pack("<4f", *vector) for vector in skeleton),
    )
    emulator.mem_write(GLOBAL_SKEL_POINTER, struct.pack("<I", SKEL_OBJECT))
    emulator.mem_write(GLOBAL_LOW_TO_HIGH, bytes(TITLE_MAP))
    low_bytes = b"".join(struct.pack("<16f", *matrix) for matrix in low)
    emulator.mem_write(MATRIX_BASE, low_bytes)
    poison = struct.pack("<I", 0x7FC00000) * (HIGH * 16)
    emulator.mem_write(MATRIX_BASE + LOW * 0x40, poison)

    stack = STACK_BASE + 0x1FFF0
    emulator.mem_write(stack, struct.pack("<II", SENTINEL, 0))
    emulator.reg_write(UC_X86_REG_ESP, stack)
    emulator.reg_write(UC_X86_REG_EAX, MATRIX_BASE + LOW * 0x40)
    emulator.reg_write(UC_X86_REG_ECX, MATRIX_BASE)
    emulator.reg_write(UC_X86_REG_EFLAGS, 2)
    emulator.reg_write(UC_X86_REG_MXCSR, 0x1F80)
    emulator.emu_start(FUNCTION, SENTINEL, count=10_000_000)
    if emulator.reg_read(UC_X86_REG_EIP) != SENTINEL:
        raise ValueError("original function did not return to the sentinel")
    if emulator.reg_read(UC_X86_REG_ESP) != stack + 8:
        raise ValueError("original RET 4 stack cleanup differs")
    if bytes(emulator.mem_read(MATRIX_BASE, LOW * 0x40)) != low_bytes:
        raise ValueError("original function unexpectedly changed low matrices")
    raw = emulator.mem_read(MATRIX_BASE + LOW * 0x40, HIGH * 0x40)
    values = struct.unpack("<" + "f" * (HIGH * 16), raw)
    return [list(values[index * 16 : (index + 1) * 16]) for index in range(HIGH)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument(
        "--xbe", type=Path,
        default=Path("extracted/ESPN NFL 2K5 (USA)/default.xbe"),
    )
    parser.add_argument(
        "--xbe-header", type=Path,
        default=Path("reports/headers/nfl2k5_xbe_header.json"),
    )
    parser.add_argument(
        "--report", type=Path,
        default=Path("reports/assets/nfl_player_postprocess.json"),
    )
    parser.add_argument("--cases", type=int, default=8)
    args = parser.parse_args()
    if args.cases < 1:
        raise ValueError("--cases must be positive")

    xbe = args.xbe.read_bytes()
    if hashlib.md5(xbe).hexdigest() != EXPECTED_XBE_MD5:
        raise ValueError("unexpected default.xbe MD5")
    header = json.loads(args.xbe_header.read_text(encoding="utf-8"))
    table_object, _tables, skeleton = title_data(
        args.xbe, args.xbe_header, args.report
    )
    skeleton_object = Skeleton()
    for index, vector in enumerate(skeleton):
        for lane, value in enumerate(vector):
            skeleton_object[index][lane] = value

    library = ctypes.CDLL(str(args.library.resolve()))
    function = library.vc_nfl_player_local_postprocess_92140
    function.argtypes = [
        ctypes.POINTER(Skeleton), ctypes.POINTER(Tables),
        ctypes.POINTER(Matrices), TraceCallback, ctypes.c_void_p,
    ]
    function.restype = ctypes.c_int

    maximum = 0.0
    compared = 0
    worst: tuple[int, int, int, float, float] | None = None
    for case in range(args.cases):
        low = input_case(case)
        original = emulate(xbe, header, skeleton, low)
        matrices = Matrices()
        for index in range(LOW):
            for lane in range(16):
                matrices.low[index][lane] = low[index][lane]
        for index in range(HIGH):
            for lane in range(16):
                matrices.high[index][lane] = math.nan

        @TraceCallback
        def callback(_user: int, _sequence: int, _address: int) -> None:
            return

        status = function(
            ctypes.byref(skeleton_object), ctypes.byref(table_object),
            ctypes.byref(matrices), callback, None,
        )
        if status != 0:
            raise ValueError(f"native function failed case {case}: {status}")
        for index in range(LOW):
            for lane in range(16):
                if float(matrices.low[index][lane]) != low[index][lane]:
                    raise ValueError(
                        f"native low input mutated case={case} "
                        f"low={index} lane={lane}"
                    )
        for index in range(HIGH):
            for lane in range(16):
                actual = float(matrices.high[index][lane])
                expected = original[index][lane]
                if not math.isfinite(actual) or not math.isfinite(expected):
                    raise ValueError(
                        f"non-finite lane case={case} high={index} lane={lane}"
                    )
                difference = abs(actual - expected)
                if difference > maximum:
                    maximum = difference
                    worst = (case, index, lane, actual, expected)
                # This is deliberately value-level.  Xbox rsqrt seed and x87
                # evaluation/store boundaries are not reproduced by native C.
                tolerance = 0.0003 + abs(expected) * 0.00002
                if difference > tolerance:
                    raise ValueError(
                        f"XBE mismatch case={case} high={index} lane={lane} "
                        f"native={actual:.9g} xbe={expected:.9g} "
                        f"difference={difference:.9g} tolerance={tolerance:.9g}"
                    )
                compared += 1

    if worst is None:
        raise ValueError("no lanes compared")
    print(
        "NFL_PLAYER_92140_XBE_ORACLE_PASS "
        f"cases={args.cases} compared_lanes={compared} "
        f"max_abs_difference={maximum:.9g} "
        f"worst_case={worst[0]} worst_high={worst[1]} worst_lane={worst[2]}"
    )


if __name__ == "__main__":
    main()
