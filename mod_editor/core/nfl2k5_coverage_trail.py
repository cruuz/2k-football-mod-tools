"""Close pursuit recovery, EXPERIMENTAL / UNWITNESSED and opt-in.

Bounded native replays reproduce full-throttle pursuit orbiting a nearby
target. The single detour authorizes the native shortest turn when an ordinary
CPU defender's man/pursuit target is within three yards and the requested
heading is at least 90 degrees behind. The retail integrator updates the body
and animation orientation. At the native arrival distance, a stationary
opponent behind the defender also clears this tick's movement request.
Headings, RNG, lapse commands and special animations retain their rules.

b780 cv1: the optional moving arrival brake (``moving_arrival_brake``, Build
option ``coverage_hitch_brake``, from the unmerged ai2-hitch work of 10/11)
fixes the repeated pivots this owner causes on moving man targets: inside the
same 0.35-yard arrival distance a man defender (callbacks 0x1A4830, 0x1A4CF0,
0x1A4DD0) whose moving receiver is behind him clears this tick's throttle
instead of pivoting past him again. The next native planning tick moves him
again. Pursuit and zone callbacks keep the pivot. Both byte templates fit the
same 640-byte reservation; the default template stays the historical 520 bytes.
Replays of the released v0.8 bytes: 8 stem pivots plus 1 to 31 more after the
break without the brake, none (one turn back after a curl) with it.

Reserve REQUESTS with the complete allocator union before composing owners.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

from . import nfl2k5_coverage_trail_code as assembly
from . import nfl2k5_coverage_hitch_code as hitch_assembly
from . import nfl2k5_gameplay_lever as lever
from . import nfl2k5_xbe_space as space

OWNER = "nfl2k5_coverage_trail"
CODE_SIZE = 640
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK_VA = 0x2FC9F0
RETAIL_HOOK = bytes.fromhex("8b510cd94210")
BUILD_CAPTION = "Close pursuit recovery (experimental)"
RETAIL_CAPTION = "Keep the retail coverage pursuit"
HITCH_CAPTION = "Stop man-coverage spins and run-ins (experimental)"
HITCH_HELP = (
    "EXPERIMENTAL / UNWITNESSED. Needs Close pursuit recovery. Retail: a CPU man defender circles a receiver "
    "who stops on a hitch. Close pursuit recovery alone stops that circle, but a defender who catches up to a "
    "moving receiver can then run past him and snap around again and again: the spins, sudden jags and "
    "run-ins on curls, comebacks, slants and go routes. Patch: once he is within "
    "about a third of a yard of the receiver he covers and would have to turn around, he holds for that "
    "moment instead of running past, and moves again right after. He turns once after a curl instead of "
    "spinning, and he still stops on a hitch instead of circling it. He can give up a few tenths of a yard "
    "at the break. Chasing the ball carrier, zone coverage and special animations keep their rules. On in "
    "Advanced and Experimental, off in Basic."
)
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


def code_for(va, *, moving_arrival_brake=False):
    if type(moving_arrival_brake) is not bool:
        raise ValueError("moving_arrival_brake must be boolean")
    template = hitch_assembly if moving_arrival_brake else assembly
    symbols = {"code": va, "native_tail": HOOK_VA + len(RETAIL_HOOK)}
    code = bytearray(template.CODE)
    for offset, kind, symbol, value in template.RELOCATIONS:
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
            # b780 cv1: the optional brake shares this owner's hook, reservation and gates.
            "moving_arrival_brake": {"build_option": "coverage_hitch_brake", "arrival_yards": .35,
                                     "man_callbacks": ["0x1a4830", "0x1a4cf0", "0x1a4dd0"],
                                     "presets": {"basic": False, "advanced": True, "experimental": True},
                                     "template_bytes": len(hitch_assembly.CODE)},
            "runtime_state_bytes": 0}


def _variant(enabled):
    return SimpleNamespace(OWNER=OWNER, CODE_SIZE=CODE_SIZE, GUARDS=GUARDS, REQUESTS=REQUESTS, mapping=mapping,
                           sites=sites, code_for=lambda va: code_for(va, moving_arrival_brake=enabled))


def read_settings(payload):
    """Recognize complete, sealed default or opt-in bytes, never just a flag."""
    for enabled in (False, True):
        state = lever.status(payload, _variant(enabled))
        if state != "foreign":
            return {"status": state, "moving_arrival_brake": enabled if state == "applied" else False}
    return {"status": "foreign"}


def status(payload):
    return read_settings(payload)["status"]


def _reconfigure(payload, place, enabled):
    """Replace only a completely recognized owner, then reuse allocator seals."""
    from .nfl2k5_bump_strength import _sections, section_digest

    requests = space._validate(payload)[2]
    before = payload[place["raw"]:place["raw"] + CODE_SIZE]
    space._require(before in (code_for(place["va"]), code_for(place["va"], moving_arrival_brake=True)),
                   "Foreign coverage recovery code")
    buf = bytearray(payload)
    buf[place["raw"]:place["raw"] + CODE_SIZE] = code_for(place["va"], moving_arrival_brake=enabled)
    if space.is_scaleout(payload):
        space._seal_scaleout(buf, requests)
    else:
        buf[space.DIRECTORY:space._directory_end(requests)] = space._directory(requests, space._code_bytes(buf, requests))
        section = next(s for s in _sections(buf) if s.raw_offset <= place["raw"] < s.raw_offset + s.raw_size)
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    space._require(space.status(result) == "applied", "Coverage recovery allocator seal failed")
    return result, {"va": hex(place["va"]), "file_offset": hex(place["raw"]), "size": CODE_SIZE}


def apply(payload, *, moving_arrival_brake=False):
    """The default keeps the released v0.6 to v0.8 bytes; the brake reuses this owner's reservation."""
    if type(moving_arrival_brake) is not bool:
        raise ValueError("moving_arrival_brake must be boolean")
    settings = read_settings(payload)
    space._require(settings["status"] != "foreign", f"{OWNER}: foreign/mixed bytes; refusing")
    # Retail installs the default template; an installed owner (either template) replays as already applied.
    result, receipt = lever.apply(payload, _variant(settings["moving_arrival_brake"]))
    if settings["moving_arrival_brake"] != moving_arrival_brake:
        place = lever.allocation(result, OWNER, CODE_SIZE)
        result, installation = _reconfigure(result, place, moving_arrival_brake)
        receipt = {**receipt, "already_applied": False, "option_installation": installation,
                   "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload),
                   "before_sha256": hashlib.sha256(payload).hexdigest(),
                   "after_sha256": hashlib.sha256(result).hexdigest()}
    space._require(read_settings(result) == {"status": "applied", "moving_arrival_brake": moving_arrival_brake},
                   "Coverage hitch option postcondition failed")
    return result, {**receipt, "moving_arrival_brake": moving_arrival_brake}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", required=True, type=Path)
    parser.add_argument("--apply", action="store_true", help="write the owner to a new XBE")
    parser.add_argument("--output", type=Path, help="new file only; never overwrite an existing path")
    parser.add_argument("--moving-arrival-brake", action="store_true", help=HITCH_HELP)
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
            result, receipt = apply(payload, moving_arrival_brake=args.moving_arrival_brake)
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
    print(json.dumps({**read_settings(payload), "experimental": True, "runtime_witnessed": False,
                      "requests": REQUESTS, **mapping()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
