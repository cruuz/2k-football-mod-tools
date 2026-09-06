"""Screen timing hooks, second experiment after PLAY timing levels A-D.

EXPERIMENTAL / UNWITNESSED. All presets off. Stateless, 640 RX bytes, no
new RW or RO. Integer classification follows the loaded assignment grammar
and its explicit first-read receiver. No name-based or global pass tuning.
The .S file documents the narrow supported grammar and live boundary ABI.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_screen_hooks_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_screen_hooks"
CODE_SIZE = 640
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOKS = {
    "block": (0x23ECD2, bytes.fromhex("d94660d81d80414e00")),
    "qb": (0x19C7E9, bytes.fromhex("8b4c240c894e60")),
}
BUILD_CAPTION = "Screen pass timing hooks (second experiment)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: screen plays use their original line "
    "and QB timers. Patch: matched screens keep expired line holds until 0.8 "
    "seconds after the snap and use a 0.6-second default QB timer. Explicit "
    "QB delays stay unchanged. This is the second experiment after the timing "
    "levels A-D. It does not guarantee a throw or catch. All presets are off."
)


class ScreenHooksError(ValueError):
    """Unsupported executable, incomplete allocation or mixed/foreign owner."""


def _require(ok, message):
    if not ok:
        raise ScreenHooksError(message)


def code_for(code_va):
    symbols = dict(code=code_va, block_tail=0x23ECDB, block_wait=0x23ECF6, qb_tail=0x19C7F0)
    result = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", result, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", result, offset, target & 0xFFFFFFFF)
    _require(len(result) <= CODE_SIZE, "Screen hooks exceed the fixed owner budget")
    return bytes(result).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    return [(name, va, before,
             b"\xe9" + struct.pack("<i", code_va + assembly.LABELS[name] - va - 5)
             + b"\x90" * (len(before) - 5)) for name, (va, before) in HOOKS.items()]


def allocation(payload):
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    _require(len(rows) == 1, "Screen hooks allocation missing; rebuild with complete request union")
    row = rows[0]
    _require((row["kind"], row["size"], row["align"]) == REQUESTS[0][1:],
             "Foreign screen hooks allocation")
    return row


def _inspect(payload):
    _require(space.status(payload) != "foreign", "Foreign XBE geometry, owner seal or section digest")
    image = XbeImage(payload)
    owned = any(r["owner"] == OWNER for r in space.layout(payload)["allocations"])
    installed, code_va = False, 0
    if owned:
        code_va = allocation(payload)["va"]
        content = image.read(code_va, CODE_SIZE)
        if content != b"\xcc" * CODE_SIZE:
            _require(content == code_for(code_va), "Foreign screen hooks runtime")
            installed = True
    for name, va, before, after in sites(code_va):
        _require(image.read(va, len(before)) == (after if installed else before),
                 f"Mixed/foreign screen hooks {name}")
    for va, size, digest in GUARDS:
        content = bytearray(image.read(va, size))
        for _name, address, before, _after in sites(code_va):
            if va <= address and address + len(before) <= va + size:
                content[address-va:address-va+len(before)] = before
        _require(hashlib.sha256(content).hexdigest() == digest,
                 f"Foreign screen hooks dependency at {va:#x}")
    return "applied" if installed else "retail"


def status(payload):
    try:
        return _inspect(payload)
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def read_settings(payload):
    if status(payload) != "applied":
        return None
    return dict(model_version=1, line_hold_floor_seconds=0.8, default_qb_timer_seconds=0.6,
                explicit_qb_delays_preserved=True, data_bytes=0, experimental=True,
                runtime_witnessed=False, experiment_order=2)


def reservations(payload):
    return [r for r in space.reservations(payload) if r["owner"] == OWNER] + [
        dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
             basis="pinned live " + name + "; not a cave")
        for name, (va, before) in HOOKS.items()]


def apply(payload: bytes) -> tuple[bytes, dict]:
    """Preflight the entire owner before mutation; identical replay is a no-op."""
    state = _inspect(payload)
    receipt = dict(experimental=True, runtime_witnessed=False, experiment_order=2,
                   code_bytes=CODE_SIZE, instruction_bytes=len(assembly.CODE), data_bytes=0,
                   changed_bytes=0, edits=[])
    if state == "applied":
        return payload, {**receipt, "status": "already_applied", "settings": read_settings(payload)}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS, scaleout=True)
                                    if space.status(payload) == "retail" else (payload, {}))
    place = allocation(allocated)
    installed, code_receipt = space.install_code(allocated, OWNER, code_for(place["va"]))
    image = XbeImage(installed)
    result = bytearray(installed)
    edits = []
    for name, va, before, after in sites(place["va"]):
        off = image.offset(va, len(before))
        result[off:off + len(after)] = after
        edits.append(dict(label=name, va=hex(va), file_offset=hex(off), size=len(after),
                          before=before.hex(), after=after.hex()))
    for section in _sections(result):
        result[section.header_offset + 36:section.header_offset + 56] = section_digest(result, section)
    result = bytes(result)
    _require(status(result) == "applied", "Screen hooks postcondition failed")
    return result, {**receipt, "status": "applied", "allocation": allocation_receipt,
                    "code_install": code_receipt, "edits": edits, "reservations": reservations(result),
                    "settings": read_settings(result),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "result_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload)}


# Whole native dependencies, normalized only at the two hooks. Generated from
# pinned USA evidence; no dependency is called or modified by the classifier.
GUARDS = (
    (0x161e30, 497, "775282ba400cb00b05892157089d8c02855ea49eaf7d764bc4fe3e7cd6abfa3f"),
    (0x19c740, 275, "661ab0647ceb5ff1e2243adccfc36dba60829f8d04caede6d74c2db0f86dab72"),
    (0x1b84e0, 142, "0c2df9ec89384a307f207975ea43e6f9bdfa1d88e31eab028e99bb2cf9a5d4f4"),
    (0x1b8790, 74, "a4dd08a60a27e7151f71d9b4e41c2c9e8b146f70e653f533163691ad9bb4ad84"),
    (0x1b8a20, 179, "b0f8ec19748f768effb99d3d60e74c789a0267dc62fc1e6f03100bfd687e8bea"),
    (0x23be30, 37, "dad3f5232308edc29952164ea267f50288a1d160d4880d28f75e6eb93252e7a1"),
    (0x23e550, 1967, "5150449e6769da8c9ba07e71210999b2f4527181a1cf9a917dc2300911fc4491"),
    (0x2400b0, 522, "3a09134b2f5c7f72b3bfe2bddd11f94b83ad6b7123be75bd3af64d8ef5e1317d"),
    (0x4e4180, 4, "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"),
)


def main(argv=None):
    """Bounded development XBE CLI. Exclusive output, never reads a disc/pack."""
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=HELP_TEXT)
    parser.add_argument("operation", choices=("status", "apply"))
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        with args.source.open("rb") as stream:
            payload = stream.read(12_300_289)
        _require(len(payload) <= 12_300_288, "Expected a supported XBE, not a disc or archive pack")
        if args.operation == "status":
            state = status(payload)
            print(json.dumps(dict(status=state, settings=read_settings(payload)), sort_keys=True))
            return 0 if state != "foreign" else 2
        _require(args.output is not None, "Apply requires a new --output XBE path")
        result, receipt = apply(payload)
        with args.output.open("xb") as stream:
            stream.write(result)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
