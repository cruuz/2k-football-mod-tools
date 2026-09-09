"""Close pursuit recovery, EXPERIMENTAL / UNWITNESSED and opt-in.

Bounded native replays reproduce full-throttle pursuit orbiting a nearby
target. The single detour authorizes the native shortest turn when an ordinary
CPU defender's man/pursuit target is within three yards and the requested
heading is at least 90 degrees behind. The retail integrator updates the body
and animation orientation. At the native arrival distance, a stationary
opponent behind the defender also clears this tick's movement request.
Headings, RNG, lapse commands and special animations retain their rules.

The reported man-coverage bug is not established by a live capture. Keep all
presets off until the witness list in ASTRA_DEFENDER_CIRCLING_REPORT.md passes.
Reserve REQUESTS with the complete allocator union before composing owners.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

from . import nfl2k5_coverage_trail_code as assembly
from . import nfl2k5_gameplay_lever as lever

OWNER = "nfl2k5_coverage_trail"
CODE_SIZE = 640
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK_VA = 0x2FC9F0
RETAIL_HOOK = bytes.fromhex("8b510cd94210")
BUILD_CAPTION = "Close pursuit recovery (experimental)"
RETAIL_CAPTION = "Keep the retail coverage pursuit"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: nearby pursuing defenders can keep "
    "running while their turn limit makes them circle. Patch: CPU defenders "
    "in ordinary man coverage or pursuit can turn back when their assigned "
    "opponent is within three yards and their requested direction is behind "
    "them. A defender who reaches a stopped opponent can stop instead of circling. "
    "Player control, mistakes and special animations retain their rules. "
    "Noah played it on 2026-09-08 and saw no circling on several pass plays; the reported man-coverage "
    "problem still needs a longer test. On in Advanced and Experimental, off in Basic."
)
GUARDS = (
    (0x2FC9F0, 193, "f5b5565ebbe5f916e7566b6e5c8ee93184cf87983ef48f6e37c368127a95b08f"),
    (0x2FC690, 9, "ae4a39f1f86ea5a10dc0f01ad19c2ede2c9ddf1aed58b048c690bc9f8fdebf83"),
    (0x2FC910, 218, "ddcf897fc91ef58e0706873ace96431e1fbe3e3f0999894d0b64e8c3dfe08cdf"),
    (0x50F4EC, 20, "a018a4b7faf534b64238ceb04fc72ba5e71d99b3611f77f57e462ab6345b5e49"),
)


def code_for(va):
    symbols = {"code": va, "native_tail": HOOK_VA + len(RETAIL_HOOK)}
    code = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", code, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", code, offset, target & 0xFFFFFFFF)
    if len(code) > CODE_SIZE:
        raise ValueError("Coverage trail exceeds its reserved code budget")
    return bytes(code).ljust(CODE_SIZE, b"\xcc")


def sites(va):
    return [("close_pursuit_turn", HOOK_VA, RETAIL_HOOK,
             b"\xe9" + struct.pack("<i", va - HOOK_VA - 5) + b"\x90")]


def mapping():
    return {"hook": hex(HOOK_VA), "radius_yards": 3, "minimum_turn_degrees": 90,
            "stationary_arrival_yards": .35,
            "cpu_only": True, "ordinary_locomotion_only": True,
            "presets": {"basic": False, "advanced": True, "experimental": True},
            "cause_status": "native pursuit mechanism proved; reported man bug unconfirmed",
            "runtime_state_bytes": 0}


def status(payload):
    return lever.status(payload, sys.modules[__name__])


def apply(payload):
    return lever.apply(payload, sys.modules[__name__])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write the owner to a new XBE")
    parser.add_argument("--output", type=Path, help="new file only; never overwrite an existing path")
    args = parser.parse_args(argv)
    if args.apply != (args.output is not None):
        parser.error("--apply and --output must be provided together")
    try:
        with args.xbe.open("rb") as stream:
            payload = stream.read(16 * 1024**2 + 1)
        if len(payload) > 16 * 1024**2:
            raise ValueError("Expected a supported executable, not a disc or archive")
        state = status(payload)
        if state == "foreign":
            raise ValueError("Foreign or mixed coverage pursuit bytes")
        if args.apply:
            result, receipt = apply(payload)
            created = False
            try:
                with args.output.open("xb") as stream:
                    created = True
                    stream.write(result)
            except BaseException:
                if created:
                    args.output.unlink(missing_ok=True)
                raise
            print(json.dumps(receipt, indent=2))
            return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps({"status": state, "experimental": True, "runtime_witnessed": False,
                      "requests": REQUESTS, **mapping()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
