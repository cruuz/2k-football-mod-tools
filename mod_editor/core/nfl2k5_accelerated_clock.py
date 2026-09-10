"""Madden-style accelerated clock; bounded native proof, gameplay UNWITNESSED.

Build-time only, default Off / 20 seconds. Reserve REQUESTS with the complete
selected owner union before installing. Runtime instructions, latch and option
words use separate owned RX, RW and RO allocations. Retail timers retain their
native start/stop, warning, snap and delay-of-game rules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from . import nfl2k5_accelerated_clock_code as assembly
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_accelerated_clock"
CODE_SIZE, DATA_SIZE, OPTIONS_SIZE = 1024, 4, 8
MINIMUM_SECONDS = (25, 20, 15, 10, 5)
DEFAULT_ENABLED, DEFAULT_MINIMUM = False, 20
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 4),
            (OWNER, "read_only", OPTIONS_SIZE, 4))
BUILD_CAPTION = "Accelerated clock (Madden style)"
HELP_TEXT = (
    "After a huddled play call, jump the play clock to your chosen minimum and "
    "run off the same time from a running game clock. Applies to both offenses. "
    "No acceleration in the final two minutes of a half or overtime, during "
    "no-huddle, or on the first snap of a quarter and kickoffs. Build-time option; "
    "native execution proved with synthetic clocks, in-game play UNWITNESSED."
)
HOOKS = {
    "complete": (0xB86E0, bytes.fromhex("e8eb95feff")),
    "stop_clock": (0xB6EB0, bytes.fromhex("8b0d9402e600")),
    "period_reset": (0xB6DC0, bytes.fromhex("a1b002e600")),
    "no_huddle": (0xA24B0, bytes.fromhex("538b1d8402e600")),
}
# Complete native routines, with only the four exactly checked hooks normalized.
# The snap's five-byte call is pinned separately: QB-spy owns an earlier snap
# store. Neither this writer nor its guards claim that owner's live instruction.
GUARDS = (
    (0xB8650, 305, "23c802a83e18450d26a601ea23d8a95a59b96695818e3aed5addba7084347d36"),
    (0xB6EB0, 11, "ffac5c041b2531fac0b331b847ae872af5b950a5ad0d6528806dbc6791801b86"),
    (0xB6DC0, 29, "2eaaa21efe71bdf7e1d7e3d58d5af99d9b95ee00fe07635d8138e2513f05e037"),
    (0xA24B0, 134, "76bf2e07ad8917db3baa6e6cfcc1d28636d41f1eb7057d3a91c3ebdec0b4e3e4"),
    (0xB7200, 41, "5ea6f0ed815b4053d22b1577a0eb1fef121c05876bdbddc8276aeafee5b5ebb1"),
    (0xAF490, 84, "23796fb1055859f25dd6321b856a1d3d6a5eef161b3db88b549d7df145cd92cb"),
    (0xAF4F0, 55, "9c2dddc2ff1b56bd0623353ac1728acb8b1046126965ee598e18fa67c0f7c647"),
    (0x205F80, 85, "f13f49dd43be5f9600a610544ea03a4a8871df044aed2e2e23754c05804e6365"),
    (0xB2580, 70, "42cb54f8e439279f166952a5cd84487430cb57620f4aa985ec457aa09a62650d"),
    (0x158C90, 70, "c5292381f46e50089ec53925e82e367329e2b3d9130fb1295c309aa77bc60348"),
    (0x1580F0, 31, "6f511172f091b532c7c69c7bbe703cfc1b2a555ed3cec1571286d4be61e1a310"),
    (0xFBB10, 90, "c16ab07016e0db66b19d8b1a90bd24199f3aaa1886accc80accf801f7d3e2bec"),
)


def _settings(enabled, minimum_seconds):
    space._require(type(enabled) is bool, "Accelerated clock must be Off or On")
    space._require(type(minimum_seconds) is int and minimum_seconds in MINIMUM_SECONDS,
                   "Minimum play clock must be 25, 20, 15, 10 or 5 seconds")
    return dict(enabled=enabled, minimum_seconds=minimum_seconds)


def encode_options(*, enabled=DEFAULT_ENABLED, minimum_seconds=DEFAULT_MINIMUM):
    _settings(enabled, minimum_seconds)
    return struct.pack("<II", enabled, minimum_seconds)


def code_for(code_va, data_va, options_va):
    symbols = dict(code=code_va, latch=data_va, options=options_va,
                   native_restart=0xA1CD0, stop_tail=0xB6EB6,
                   period_tail=0xB6DC5, no_huddle_tail=0xA24B7)
    content = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", content, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", content, offset, target & 0xFFFFFFFF)
    space._require(len(content) <= CODE_SIZE, "Accelerated clock code exceeds its reservation")
    return bytes(content).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    return [(name, va, before,
             (b"\xe8" if name == "complete" else b"\xe9") +
             struct.pack("<i", code_va + assembly.LABELS[name] - va - 5) +
             b"\x90" * (len(before)-5))
            for name, (va, before) in HOOKS.items()]


def allocations(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    found = {a["kind"]: a for a in rows}
    space._require(len(rows) == 3 and set(found) == {"code", "data", "read_only"},
                   "Reserve the complete accelerated-clock owner union on a clean base")
    for _, kind, size, align in REQUESTS:
        space._require((found[kind]["size"], found[kind]["align"]) == (size, align),
                       "Foreign accelerated-clock allocation geometry")
    return found


def _inspect(payload):
    space._require(isinstance(payload, bytes) and len(payload) <= space.SCALE_FILE_SIZE,
                   "Expected bounded default.xbe bytes")
    layout = space.layout(payload)  # verifies allocator seals and section digests
    image = XbeImage(payload)
    settings, code_va = None, 0
    if any(a["owner"] == OWNER for a in layout["allocations"]):
        places = allocations(payload)
        code_va = places["code"]["va"]
        content = image.read(code_va, CODE_SIZE)
        options = image.read(places["read_only"]["va"], OPTIONS_SIZE)
        space._require(image.read(places["data"]["va"], DATA_SIZE) == bytes(DATA_SIZE),
                       "Offline accelerated-clock latch must be zero")
        if content == b"\xcc" * CODE_SIZE:
            space._require(options == bytes(OPTIONS_SIZE), "Mixed accelerated-clock options/code")
        else:
            enabled, minimum = struct.unpack("<II", options)
            space._require(enabled in (0, 1), "Foreign accelerated-clock enable word")
            settings = _settings(bool(enabled), minimum)
            space._require(content == code_for(code_va, places["data"]["va"], places["read_only"]["va"]),
                           "Foreign accelerated-clock code, relocation or padding")
    for name, va, before, after in sites(code_va):
        space._require(image.read(va, len(before)) == (after if settings is not None else before),
                       f"Mixed/foreign accelerated-clock {name} hook")
    normalize = sites(code_va)
    # Kick rules owns the later PAT re-spot call in this same no-huddle routine.
    # Accept only its completely verified cave, tables and live hooks, never
    # an arbitrary call target or a relaxed hash over the rest of this routine.
    from . import nfl2k5_kick_rules as kicks
    if image.read(kicks.PAT_AUDIBLE_SITE_VA, 5) != kicks.RETAIL_CALL_AUDIBLE:
        space._require(kicks.status(payload) == "applied", "Foreign kick-rules no-huddle neighbor")
    normalize.append(("kick_rules", kicks.PAT_AUDIBLE_SITE_VA, kicks.RETAIL_CALL_AUDIBLE, b""))
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for _, hook, before, _ in normalize:
            if va <= hook and hook + len(before) <= va + size:
                blob[hook-va:hook-va+len(before)] = before
        space._require(hashlib.sha256(blob).hexdigest() == digest,
                       f"Foreign accelerated-clock prerequisite at {va:#x}")
    for va, expected in ((0xB7010, bytes.fromhex("e89bfeffff")),
                         (0xA1CD0, bytes.fromhex("e92b550100"))):
        space._require(image.read(va, len(expected)) == expected,
                       f"Foreign accelerated-clock native dispatch at {va:#x}")
    return settings


def status(payload):
    try:
        return "applied" if _inspect(payload) is not None else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError):
        return "foreign"


def verify(payload, *, enabled=None, minimum_seconds=None):
    """Reparse all written bytes, native pins, options, padding and allocator seals.

    Optional expected settings turn this into a build postcondition. A pristine
    image reports retail/Off; asking it to verify an installed setting refuses.
    """
    settings = _inspect(payload)
    if enabled is not None or minimum_seconds is not None:
        space._require(settings is not None, "Accelerated clock is not installed")
        expected = _settings(settings["enabled"] if enabled is None else enabled,
                             settings["minimum_seconds"] if minimum_seconds is None else minimum_seconds)
        space._require(expected == settings, "Accelerated-clock options differ from requested build")
    return dict(status="applied" if settings is not None else "retail",
                **(settings or _settings(DEFAULT_ENABLED, DEFAULT_MINIMUM)),
                option_source="build_time", runtime_witnessed=False)


def describe(payload):
    settings = verify(payload)
    choice = f"On, {settings['minimum_seconds']} s minimum" if settings["enabled"] else "Off (native clocks)"
    return f"Accelerated clock: {choice}. Build-time setting; in-game play UNWITNESSED."


def reservations(payload):
    code_va = allocations(payload)["code"]["va"]
    return [r for r in space.reservations(payload) if r["owner"] == OWNER] + [
        dict(owner=OWNER, start=hex(va), end=hex(va+len(before)), size=len(before),
             basis=f"pinned live accelerated-clock {name} hook; not a cave")
        for name, va, before, _ in sites(code_va)]


def apply(payload, *, enabled=None, minimum_seconds=None):
    """Install Off/20 by default; omitted settings preserve a verified installation.

    The Studio skips this writer when Off for byte-identical native output. An
    explicit disabled installation is supported and exercises the native-only
    wrappers. Changing an installed choice requires a rebuild from the clean base.
    """
    previous = _inspect(payload)
    settings = _settings(
        (previous["enabled"] if previous else DEFAULT_ENABLED) if enabled is None else enabled,
        (previous["minimum_seconds"] if previous else DEFAULT_MINIMUM) if minimum_seconds is None else minimum_seconds)
    if previous is not None:
        space._require(settings == previous, "Different accelerated-clock options; rebuild from base")
        return payload, {**verify(payload), "status": "already_applied", "owner": OWNER,
                         "changed_bytes": 0, "edits": []}
    allocated, receipt = (space.apply(payload, REQUESTS, scaleout=True)
                          if space.status(payload) == "retail" else (payload, {}))
    places = allocations(allocated)
    code, data, options = (places[k] for k in ("code", "data", "read_only"))
    installed, _ = space.install_code(allocated, OWNER, code_for(code["va"], data["va"], options["va"]))
    installed, _ = space.install_read_only(installed, OWNER, encode_options(**settings))
    result, patch = rdata.apply(installed, sites(code["va"]), OWNER)
    verified = verify(result, **settings)
    edits = [dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
             for name, va, before, after in sites(code["va"])]
    edits += [dict(label="owned_accelerated_clock_" + k, va=hex(places[k]["va"]), size=places[k]["size"])
              for k in ("code", "read_only")]
    return result, dict(**verified, owner=OWNER, allocation=receipt, edits=edits,
                        sections_repinned=patch["sections_repinned"], reservations=reservations(result),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload),
                        file_growth=len(result)-len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "apply"))
    parser.add_argument("xbe", type=Path)
    parser.add_argument("--output", type=Path, help="new file only")
    parser.add_argument("--enabled", choices=("off", "on"))
    parser.add_argument("--minimum-seconds", type=int, choices=MINIMUM_SECONDS)
    args = parser.parse_args(argv)
    if (args.action == "apply") != (args.output is not None):
        parser.error("apply requires --output; status accepts no output")
    if args.action == "status" and (args.enabled is not None or args.minimum_seconds is not None):
        parser.error("status accepts only the XBE")
    try:
        with args.xbe.open("rb") as stream:
            payload = stream.read(space.SCALE_FILE_SIZE + 1)
        if args.action == "status":
            receipt = verify(payload)
        else:
            result, receipt = apply(payload, enabled=None if args.enabled is None else args.enabled == "on",
                                    minimum_seconds=args.minimum_seconds)
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
        print(f"Accelerated clock refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
