"""Momentum model 1: EXPERIMENTAL / UNWITNESSED USA executable experiment.

The global ordinary turn curve keeps its low-command points and Agility/history
math. High-command ordinates and the floor (including retail's inline copy)
decrease with level. Braking temporarily substitutes throttle/neutral heading
across the ordinary dispatcher AND its animation tail call. Native acceleration
and the legacy rating envelope are untouched. Optional contact adds at most
.08 * level/100 to the two carrier Break Tackle reads in one resolution.

Runtime history is 32 distinct 64-byte slots in a named grown RW allocation.
The simulation tick at B71D10 is incremented by AF2C0 before 1E08D0; no history
advance occurs twice in a tick. Identity includes entity/state/roster, state
age, eligibility and consecutive tick continuity. No controller-index test is
used. Unknown/special states and exhausted slots fall back to retail.

Use space.apply(base, REQUESTS + other_owners.REQUESTS) before either owner
when composing grown patches. Adding requests after growth requires a rebuild.
Zero adds no hooks or allocation. Reconfiguration requires a supported base.
This module does not claim a gameplay, loader, or complete collision witness.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_momentum_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_momentum"
MODEL_VERSION = 1
CODE_SIZE = (len(assembly.CODE) + 15) & -16
DATA_SIZE = 16 + 32 * 64
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
REFERENCE_SPEED = 640.0800170898438 + 274.32000732421875 * .99
RUNUP_FRAMES = 21
CURVE_VA = 0x50A588
RETAIL_CURVE = bytes.fromhex(
    "05000000cdcccc3d0000c03f0000003f9a99993f3333333f0000803f"
    "6666663fcdcccc3e0000803fcdcc4c3d"
)
FLOOR_VA = 0x513E38
FLOOR_INLINE_VA = 0x237D20
RETAIL_FLOOR = struct.pack("<f", 19114)
RETAIL_INLINE = bytes.fromhex("c744240400549546")
HOOKS = {
    "dispatch": (0x1CD5D7, bytes.fromhex("8b77108b481c")),
    "contact_first": (0x1D9D62, bytes.fromhex("e8a912faff")),
    "contact_later": (0x1DA39F, bytes.fromhex("e86c0cfaff")),
}
# Proof dependencies, not edited spans. Pin the real clock and ordinary state.
PINS = {
    0xAF2D0: bytes.fromhex("a1101db7004089350c1db700a3101db700"),
    0x1CE280: bytes.fromhex("a100fce50085c0740c8b0085c0740683781c01740233c0c3"),
    0x50F4EC: bytes.fromhex("01000001a032210010332100f0322100"),
    0xAD67F0: struct.pack("<I", 0x50F4EC),
}


class MomentumError(ValueError):
    """Foreign, mixed, unreserved, or differently configured executable."""


def _require(ok, message):
    if not ok:
        raise MomentumError(message)


def _settings(momentum, momentum_contact):
    _require(type(momentum) is int and 0 <= momentum <= 100, "momentum must be an integer 0..100")
    _require(type(momentum_contact) is bool, "momentum_contact must be Boolean")
    _require(momentum > 0 or not momentum_contact, "contact requires a nonzero momentum level")
    return {"momentum": momentum, "momentum_contact": momentum_contact}


def code_for(momentum, momentum_contact, code_va, data_va):
    """Relocate assembler-declared operands, then encode immutable settings."""
    _settings(momentum, momentum_contact)
    _require(momentum > 0, "zero has no Momentum code")
    blob = bytearray(assembly.CODE)
    symbols = {"code": code_va, "state_data": data_va,
               "retail_dispatch": 0x1CD5DD, "retail_attribute": 0x17B010}
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        addend = struct.unpack_from("<I", blob, offset)[0]
        target = symbols[symbol] + value + addend
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", blob, offset, target & 0xFFFFFFFF)
    m = momentum / 100
    struct.pack_into("<I6f", blob, assembly.LABELS["config"],
                     momentum | (int(momentum_contact) << 8), .4 * m, .12 * m,
                     (.55 * REFERENCE_SPEED) ** 2, .55 * REFERENCE_SPEED,
                     1 / (.45 * REFERENCE_SPEED), .08 * m / RUNUP_FRAMES)
    blob.extend(b"\xcc" * (CODE_SIZE - len(blob)))
    return bytes(blob), {key: code_va + off for key, off in assembly.LABELS.items()}


def _table(momentum):
    result = bytearray(RETAIL_CURVE)
    for i, reduction in ((2, .15), (3, .35), (4, .5)):
        off = 8 + i * 8
        original = struct.unpack_from("<f", result, off)[0]
        struct.pack_into("<f", result, off, original * (1 - reduction * momentum / 100))
    return bytes(result)


def _edits(settings, labels):
    level = settings["momentum"]
    floor = struct.pack("<f", 19114 * (1 - .4 * level / 100))
    out = [("turn_curve", CURVE_VA, RETAIL_CURVE, _table(level)),
           ("turn_floor", FLOOR_VA, RETAIL_FLOOR, floor),
           ("inline_turn_floor", FLOOR_INLINE_VA, RETAIL_INLINE, RETAIL_INLINE[:4] + floor)]
    for name, (va, retail) in HOOKS.items():
        enabled = name == "dispatch" or settings["momentum_contact"]
        opcode = b"\xe9" if name == "dispatch" else b"\xe8"
        replacement = opcode + struct.pack("<i", labels[name] - va - 5) + b"\x90" * (len(retail) - 5)
        out.append((name, va, retail, replacement if enabled else retail))
    return out


def _sites(payload):
    sites = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    _require(set(sites) == {"code", "data"}, "Momentum allocations missing; rebuild with combined requests")
    for _, kind, size, align in REQUESTS:
        _require((sites[kind]["size"], sites[kind]["align"]) == (size, align), "foreign Momentum allocation")
    return sites["code"], sites["data"]


def _inspect(payload):
    _require(space.status(payload) != "foreign", "foreign XBE layout or stale digest")
    image = XbeImage(payload)
    for va, expected in PINS.items():
        _require(image.read(va, len(expected)) == expected, f"foreign Momentum dependency at {va:#x}")
    owners = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    installed = False
    settings = {"momentum": 50, "momentum_contact": False}
    labels = {key: 0 for key in HOOKS}
    if owners:
        code, data = _sites(payload)
        content = payload[code["raw"]:code["raw"] + code["size"]]
        if content != b"\xcc" * code["size"]:
            config = struct.unpack_from("<I", content, assembly.LABELS["config"])[0]
            _require(config & ~0x17F == 0, "foreign Momentum config bits")
            settings = _settings(config & 0x7F, bool(config & 0x100))
            expected, labels = code_for(**settings, code_va=code["va"], data_va=data["va"])
            _require(content == expected, "foreign Momentum code or configuration")
            installed = True
    for name, va, retail, applied in _edits(settings, labels):
        expected = applied if installed else retail
        _require(image.read(va, len(expected)) == expected, f"mixed/foreign Momentum {name}")
    return "applied" if installed else "retail", settings if installed else {}


def status(payload: bytes) -> str:
    """Return retail/applied/foreign, validating every span before mutation."""
    try:
        return _inspect(payload)[0]
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def read_settings(payload: bytes) -> dict:
    try:
        state, settings = _inspect(payload)
        return {"status": state, **settings, "model_version": MODEL_VERSION,
                "experimental": True, "runtime_witnessed": False}
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return {"status": "foreign", "experimental": True, "runtime_witnessed": False}


def reservations(payload: bytes) -> list[dict]:
    """Explicit edited retail spans and named children for the manifest builder."""
    settings = read_settings(payload)
    _require(settings["status"] == "applied", "reservations require installed Momentum")
    code, data = _sites(payload)
    _, labels = code_for(settings["momentum"], settings["momentum_contact"], code["va"], data["va"])
    out = [r for r in space.reservations(payload) if r["owner"] == OWNER]
    for name, va, before, after in _edits(settings, labels):
        if before != after:
            out.append(dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
                            basis="pinned live " + name + "; not a cave"))
    return out


def apply(payload: bytes, *, momentum: int | None = None,
          momentum_contact: bool | None = None) -> tuple[bytes, dict]:
    """Default new experiment is 50/off; omitted replay options retain settings.

    An explicit zero/off on retail is byte-identical, including length/digests.
    Existing legacy acceleration is retained and reported, never transplanted.
    UI normalization should choose legacy acceleration off for parity witnesses.
    """
    state, previous = _inspect(payload)
    wanted = _settings(previous.get("momentum", 50) if momentum is None else momentum,
                       previous.get("momentum_contact", False) if momentum_contact is None else momentum_contact)
    from . import nfl2k5_accel_ramp as legacy
    legacy_state = legacy.status(payload)
    _require(legacy_state != "foreign", "foreign/mixed legacy acceleration owner")
    receipt = dict(wanted, experimental=True, runtime_witnessed=False, model_version=MODEL_VERSION,
                   legacy_accel_ramp=legacy_state, changed_bytes=0,
                   legacy_policy="independent rating envelope retained; no new acceleration law")
    if state == "applied":
        _require(wanted == previous, "different Momentum settings; rebuild from supported base")
        return payload, {**receipt, "status": "already_applied"}
    if wanted["momentum"] == 0:
        return payload, {**receipt, "status": "retail"}
    allocated, allocation_receipt = (space.apply(payload, REQUESTS) if space.status(payload) == "retail"
                                     else (payload, {}))
    code, data = _sites(allocated)
    content, labels = code_for(**wanted, code_va=code["va"], data_va=data["va"])
    installed, _ = space.install_code(allocated, OWNER, content)
    image = XbeImage(installed)
    buf = bytearray(installed)
    edits = []
    for name, va, before, after in _edits(wanted, labels):
        if before == after:
            continue
        off = image.offset(va, len(before))
        buf[off:off + len(after)] = after
        edits.append(dict(label=name, va=hex(va), file_offset=hex(off), size=len(after),
                          before=before.hex(), after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    _require(status(result) == "applied", "Momentum postcondition failed")
    return result, {**receipt, "status": "applied", "edits": edits, "allocation": allocation_receipt,
                    "code_va": hex(code["va"]), "data_va": hex(data["va"]),
                    "code_bytes": CODE_SIZE, "data_bytes": DATA_SIZE,
                    "runup_frames": RUNUP_FRAMES,
                    "max_break_tackle_bonus": .08 * wanted["momentum"] / 100 if wanted["momentum_contact"] else 0,
                    "reservations": reservations(result),
                    "source_sha256": hashlib.sha256(payload).hexdigest(),
                    "result_sha256": hashlib.sha256(result).hexdigest(),
                    "changed_bytes": sum(a != b for a, b in zip(payload, result)) + len(result) - len(payload)}


def main() -> None:
    """Inspect an XBE, or write an explicitly requested new experiment copy."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Momentum model 1: EXPERIMENTAL / UNWITNESSED")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, help="write a new XBE; existing files are never overwritten")
    parser.add_argument("--level", type=int, default=0, help="0=Retail, 25=Light, 50=Medium, 100=Heavy")
    parser.add_argument("--contact", action="store_true", help="enable the separate running-start contact experiment")
    args = parser.parse_args()
    payload = args.source.resolve(strict=True).read_bytes()
    if args.output is None:
        if args.level or args.contact:
            parser.error("--level/--contact need --output")
        result = read_settings(payload)
    else:
        content, result = apply(payload, momentum=args.level, momentum_contact=args.contact)
        with args.output.resolve().open("xb") as output:
            output.write(content)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
