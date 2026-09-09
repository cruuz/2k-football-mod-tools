"""Deep-zone corner facing and press bail, EXPERIMENTAL / UNWITNESSED.

Both tiers are opt-in. Reserve REQUESTS in the selected owner union first.
The native wrappers leave QB-spy callbacks, the initial-drop cap
and coverage-trail turn integrator under their existing owners. Bail's optional
pre-snap PLAY alignment is authored by nfl2k5_deep_zone_bail; runtime eligibility
uses actual starting depth and all native deep assignments, never play names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

from . import nfl2k5_deep_zone_code as assembly
from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_xbe_space as space
from . import nfl2k5_zone_drop as drop
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_deep_zone"
CODE_SIZE, DATA_SIZE = 2048, 256
RECORD_SIZE, RECORD_COUNT = 21, 11
FLAGS_OFFSET = 20
REQUESTS = ((OWNER, "code", CODE_SIZE, 16), (OWNER, "data", DATA_SIZE, 16))
HOOKS = {
    "planner": (0x1A4170, bytes.fromhex("558bec83e4f0")),
    "init": (0x1A66D5, bytes.fromhex("e8e6410900")),
    "tick": (0x2FCADD, bytes.fromhex("e88e8d0000")),
}
BUILD_CAPTIONS = ("Deep-zone QB facing (experimental)", "Press corner bail (experimental)")
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Retail: deep-zone corners can turn to run. "
    "Patch: try keeping CPU corners oriented toward the QB with a slower directional "
    "drop until a pass, a run, or their selected receiver gets a yard beyond "
    "them. Press bail applies only to three-deep calls and corners starting "
    "within two yards; by itself it ends at seven yards. Native target "
    "selection and player control retain their rules. Off in every preset."
)
GUARDS = (
    (0x20b20, 9, 'ae4a39f1f86ea5a10dc0f01ad19c2ede2c9ddf1aed58b048c690bc9f8fdebf83'),
    (0x3ca150, 140, '76343d475ba9c89963bf42f9a1951e8b20183759dd8e05e72ab4b288ec06f945'),
    (0x3ca1e0, 142, '082823e17edd283a9b7e5e8de394ef095643489f498205e5c14686b510f9c2da'),
    (0x35ad60, 477, 'aa44796e450100ea03ab3c9c8f56f471246ecb0a60efb41337c07213d613eb97'),
    (0x50f4ec, 40, '8213d178656ba8a5583beca7b8ffa9e2e576671289498d864bb89f27eff9baeb'),
    (0x23a8c0, 9, '089c461fd7498f1f8827819c0f7a448ec64e7da4c9ed8bb50ea82510dea76aa7'),
    (0x1b8960, 181, 'fae1a48a8f061382017cab3287952f08af80f4546f513b09270175634b10d1b5'),
    (0x183f60, 325, 'a2bc0091e5a1dbd4e92f9b496b47194117e89f5fa52ec02289f0a383ae812a7f'),

    (1720688, 406, '10f9e12e191bac116a46afef1416edd352c2ff33296c4edc73ed6377024ab5e2'),
    (0x1a6220, 1217, "e4083f8cf81c27f826670aafa1acc9d69b3f1b54f96fdb3df90543ac167b97e5"),
    (0x2fcac0, 679, "5fb44b7e44b9d474eda21e938d7ffe5e0032d61a6aa1ae5a389e5e1c70406b56"),
    (0x305870, 167, "ebae5073632faea655ea78e4a6c061795f9cda6b737359deb26c8f3653325037"),
    (0x305850, 20, "a3e7a8327e662000f07944706b88d3f802a054bc73788bf7f866f2ca00eda209"),
    (0x305920, 179, "3b3cb244734ef1fab81a1b59a0e254ee80b75ddbca53dbe66df863cf1e62864e"),
    (0x511070, 40, "2f41674d415b3ba2f2eae8eae89fa0a71e0e91536289c65f7e1c2af29800b1ea"),
    (0x510e88, 360, "f9f57f77256af28f2f320fbc9682ed63ec0de8e8a5162592a6dcdd3199f7fc60"),
    (0x1a8890, 46, "92a33a7ae15890e63572679bac9fd09cd22e70e0b3fe35ab9056fc351745baf2"),
    (0x217ae0, 24, "d27adf50607c6c2430191a95caf26879b44e238e499907c559db076cf77451a9"),
    (0x217ab0, 44, "4d3c3bdcb144bf55dc294d97a10c45d4c9cadbbc31d014cac5e1ee104bf339d5"),
    (0x210b0, 215, "992f601ec2f53fa33bbb4b5f0bad2c0e16b1efd5be83a5693710bdbf17990734"),
    (0x35af40, 42, "28887f8a5aaa02aedc4d9f0fd4253e9a3e5387843f16138bd6eabe7b1285f980"),
    (0xa0b90, 141, "18901eb1904e1f1945b94a5bd4f84422725265dc2cb731891e8c44909021b839"),
    (0xb7430, 32, "984484fe97cda4a5ffaf51a500143fb3f01e5525c12e9b3be9eb0c3b7e3d1377"),
)


def _settings(facing, bail):
    space._require(type(facing) is bool and type(bail) is bool and (facing or bail),
                   "Select at least one deep-zone tier with boolean settings")
    return dict(facing=facing, bail=bail)


def code_for(code_va, data_va, *, facing=True, bail=True):
    _settings(facing, bail)
    symbols = dict(code=code_va, state_data=data_va, native_init_tail=0x23A8C0,
                   native_rows=0x305870, bearing=0x210B0, effective_facing=0x217AE0, native_planner_tail=0x1A4176)
    content = bytearray(assembly.CODE)
    for offset, kind, symbol, value in assembly.RELOCATIONS:
        target = symbols[symbol] + value + struct.unpack_from("<I", content, offset)[0]
        if kind == 2:
            target -= code_va + offset
        struct.pack_into("<I", content, offset, target & 0xFFFFFFFF)
    struct.pack_into("<II", content, assembly.LABELS["config"], facing, bail)
    space._require(len(content) <= CODE_SIZE, "Deep-zone code exceeds its allocation")
    return bytes(content).ljust(CODE_SIZE, b"\xcc")


def sites(code_va):
    return [(name, va, old, (b"\xe9" if name == "planner" else b"\xe8") + struct.pack("<i", code_va + assembly.LABELS[name] - va - 5) + b"\x90" * (len(old)-5))
            for name, (va, old) in HOOKS.items()]


def allocations(payload):
    found = {a["kind"]: a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER}
    space._require(set(found) == {"code", "data"}, "Reserve the complete deep-zone owner union on a clean base")
    for _, kind, size, align in REQUESTS:
        space._require((found[kind]["size"], found[kind]["align"]) == (size, align),
                       "Foreign deep-zone allocation geometry")
    return found


def _inspect(payload):
    space._require(isinstance(payload, bytes) and len(payload) <= space.SCALE_FILE_SIZE,
                   "Expected bounded default.xbe bytes")
    layout = space.layout(payload)
    image = XbeImage(payload)
    settings, code_va = None, 0
    if any(a["owner"] == OWNER for a in layout["allocations"]):
        places = allocations(payload)
        code_va = places["code"]["va"]
        content = image.read(code_va, CODE_SIZE)
        space._require(image.read(places["data"]["va"], DATA_SIZE) == bytes(DATA_SIZE),
                       "Deep-zone offline writable state must be zero")
        if content != b"\xcc" * CODE_SIZE:
            f, b = struct.unpack_from("<II", content, assembly.LABELS["config"])
            space._require(f in (0, 1) and b in (0, 1), "Foreign deep-zone settings")
            settings = _settings(bool(f), bool(b))
            space._require(content == code_for(code_va, places["data"]["va"], **settings),
                           "Foreign deep-zone code/constants/padding")
    for name, va, before, after in sites(code_va):
        space._require(image.read(va, len(before)) == (after if settings else before),
                       f"Mixed/foreign deep-zone {name} call")
    # The old cap's five bytes are normalized only after its own complete seal,
    # hook, settings and dependency checks. No mutual/recursive normalization.
    space._require(drop.status(payload) in ("retail", "applied"), "Foreign initial-drop neighbor")
    normalize = sites(code_va) + [("drop", drop.HOOK_VA, drop.RETAIL_HOOK, b"")]
    # The shared legal presnap helper also hosts kickoff's lineup exception.
    # Normalize its prologue only after the actual legacy/relocated owner seal.
    from . import nfl2k5_dynamic_kickoff as kickoff
    va, old = kickoff.HOOKS["lineup"]
    if image.read(va, len(old)) != old:
        space._require(kickoff.status(payload) == "applied", "Foreign kickoff lineup neighbor")
    normalize.append(("kickoff_lineup", va, old, b""))
    for va, size, digest in GUARDS:
        blob = bytearray(image.read(va, size))
        for _, hook, before, _ in normalize:
            if va <= hook and hook + len(before) <= va + size:
                blob[hook-va:hook-va+len(before)] = before
        space._require(hashlib.sha256(blob).hexdigest() == digest,
                       f"Foreign deep-zone prerequisite at {va:#x}")
    # Complete callback, target-selection and fast-planner dependencies belong
    # to Spy. Our own owner/code/hooks and normalized planner body are already
    # proved above, so validate its remaining context without a recursive call
    # back into this owner. Public Spy status always checks this neighbor.
    from . import nfl2k5_qb_spy_runtime as spy
    spy._inspect(payload, check_deep_zone=False)
    return settings


def status(payload):
    try:
        return "applied" if _inspect(payload) is not None else "retail"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError, UnicodeError):
        return "foreign"


def read_settings(payload):
    settings = _inspect(payload)
    return {"status": "applied" if settings else "retail", **(settings or {}),
            "experimental": True, "runtime_witnessed": False}


def reservations(payload):
    place = allocations(payload)["code"]
    return [r for r in space.reservations(payload) if r["owner"] == OWNER] + [
        dict(owner=OWNER, start=hex(va), end=hex(va + len(before)), size=len(before),
             basis=f"pinned live deep-zone {name} call; not a cave")
        for name, va, before, _ in sites(place["va"])]


def apply(payload, *, facing=None, bail=None):
    """Install or replay; omitted settings preserve an installed configuration."""
    previous = _inspect(payload)  # every byte/geometry/neighbor preflight first
    settings = _settings(previous["facing"] if facing is None and previous else True if facing is None else facing,
                         previous["bail"] if bail is None and previous else True if bail is None else bail)
    common = dict(owner=OWNER, experimental=True, runtime_witnessed=False, **settings,
                  code_bytes=CODE_SIZE, instruction_bytes=assembly.LABELS["config"],
                  data_bytes=DATA_SIZE, presets={k: False for k in ("basic", "advanced", "experimental")})
    if previous is not None:
        space._require(settings == previous, "Different deep-zone tiers; rebuild from base")
        return payload, dict(status="already_applied", changed_bytes=0, edits=[], **common)
    allocated, receipt = (space.apply(payload, REQUESTS, scaleout=True)
                          if space.status(payload) == "retail" else (payload, {}))
    places = allocations(allocated)
    code, data = places["code"], places["data"]
    installed, _ = space.install_code(allocated, OWNER, code_for(code["va"], data["va"], **settings))
    result, patch = rdata.apply(installed, sites(code["va"]), OWNER)
    space._require(status(result) == "applied", "Deep-zone postcondition failed")
    edits = [dict(label=name, va=hex(va), size=len(before), before=before.hex(), after=after.hex())
             for name, va, before, after in sites(code["va"])]
    edits.append(dict(label="owned_deep_zone_code", va=hex(code["va"]), size=CODE_SIZE))
    return result, dict(status="applied", **common, allocation=receipt, edits=edits,
                        sections_repinned=patch["sections_repinned"], reservations=reservations(result),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)) + len(result)-len(payload),
                        file_growth=len(result)-len(payload), before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


def read_xbe(path):
    with Path(path).open("rb") as stream:
        payload = stream.read(space.SCALE_FILE_SIZE + 1)
    space._require(len(payload) <= space.SCALE_FILE_SIZE, "Expected a bounded XBE, not a disc or archive")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "apply"))
    parser.add_argument("xbe", type=Path)
    parser.add_argument("--output", type=Path, help="new file only")
    parser.add_argument("--tier", choices=("facing", "bail", "both"))
    args = parser.parse_args(argv)
    if (args.action == "apply") != (args.output is not None) or (args.action == "status" and args.tier):
        parser.error("apply requires --output; status accepts only the XBE")
    try:
        payload = read_xbe(args.xbe)
        if args.action == "status":
            receipt = read_settings(payload)
        else:
            options = {} if args.tier is None else dict(facing=args.tier != "bail", bail=args.tier != "facing")
            result, receipt = apply(payload, **options)
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
        print(f"Deep-zone patch refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
