"""Speed separation: a faster receiver pulls away from a slower CPU man defender on a straight deep route.

Retail barely lets Speed matter: the top speed curve is 7 + 3 x Speed yards a second, so a 10-point Speed gap is only
0.3 yards a second (about 3 percent). This optional late owner shaves a little more off a slower CPU defender's straight
running speed while he covers a faster receiver man to man. The strength is a whole number from 0 to 100. 0 changes
nothing (Studio installs no code at 0). At 100 the defender's ordinary running speed is multiplied by
1 - min(receiver Speed - defender Speed, 25) / 100, and at strength S that reduction is scaled by S / 100. The effect
ramps in from eight to twelve yards beyond the line of scrimmage. Only a CPU defender in the established man task whose
target is a faster opponent, with both players running straight downfield, qualifies. The cave writes only a local speed
result: ratings, steering, tasks and the receiver are untouched, and native consumers respond to the changed speed.

Hook: the 7-byte epilogue of the speed mapper (0x2381B1) in one 1,024-byte code reservation, no RW state. Ported from the
unmerged job/ai1-speed prototype (e88b60246) onto the beta-79 executable (b780-cv5).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from . import nfl2k5_rdata_sites as rdata
from . import nfl2k5_speed_threshold_code as assembly
from . import nfl2k5_xbe_space as space
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_speed_threshold"
CODE_SIZE, SETTING_OFFSET = 1024, 1020
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
HOOK_VA = 0x2381B1
RETAIL_HOOK = bytes.fromhex("d944240083c414")
DEFAULT = 0
SOFTDRINK = 35  # the strength the SOFTDRINK 2K28 recipe uses (Noah's coordinator default, b780-cv5)
BUILD_CAPTION = "Speed separation on deep routes (experimental)"
HELP_TEXT = (
    "In the stock game Speed barely matters on a straight run: a 10-point Speed gap is only 0.3 yards a second. "
    "This makes a faster receiver pull away from a slower CPU corner when both run straight downfield, such as a go "
    "route in man coverage. 0 keeps the stock feel and installs nothing. Higher numbers slow the corner a little more "
    "per point of Speed he gives up: 35 is the SOFTDRINK setting and 100 is strong. The effect starts eight yards "
    "downfield and is full strength by twelve. Turns, cuts, zone coverage, human defenders, equal or faster corners "
    "and the receiver are unchanged. EXPERIMENTAL / UNWITNESSED in a played game. Changing the number later needs a "
    "rebuild from the source disc."
)
# Complete ordinary speed mapper, including every constant it reads. Hook is
# normalized only after exact hook/cave recognition. Addresses and disassembly:
# reports/ai1_speed/native.txt and tools/nfl2k5_speed_threshold_research.py.
GUARDS = (
    (0x238020, 411, "be6e4950b42988a7368653d4e3abf11526d4a183fda3dd1aaa5243dc4459da2f"),
    (0x4e4180, 4, "df3f619804a92fdb4057192dc43dd748ea778adc52bc498ce80524c014b81119"),
    (0x4f0f6c, 8, "8e9d9f6415f8050c835e4e7f3f216275bd232ae0717faaa2d09eaae757e9b7ad"),
    (0x4f6bd4, 4, "4f9666bffd029360e6e44ae8be3ab0690dd7a2032737723fa16e3d757b4d4a6c"),
    (0x4edd28, 4, "49f300df7b25775c5f74fe898b1f86b0d96646ead4d9661ecdba6ff7029b3ca7"),
    (0x4f0f50, 4, "4c89a6e13f8f61f8858595b9c833c3dddd2071a10a4aef82e890e5ed718213dd"),
    (0x513e28, 8, "5421c95f6f6dc005dfb59e3db10b4f049de7af890da2250c49d03712fba15cdf"),
    (0x513e50, 12, "73743a4e812a65ce3711e342c3a8c524693d5fb8b6e6105dd859a471c57349ce"),
    (0x4e6d10, 4, "0b9d79ff0fc4d0a77ef398763bbe45c445501e826219f2b6a1aa709411ab631d"),
    (0x503c08, 4, "648028189e1b9cf504049057e9f15b079bca9b2370e5f9cff34c80f5f04f21eb"),
)


def validate(value):
    space._require(type(value) is int and 0 <= value <= 100,
                   "Speed threshold must be an integer from 0 to 100")
    return value


def code_for(va, value=DEFAULT):
    validate(value)
    symbols = dict(code=va, setting=va + SETTING_OFFSET,
                   native_tail=HOOK_VA + len(RETAIL_HOOK))
    content = bytearray(assembly.CODE)
    for offset, kind, symbol, addend in assembly.RELOCATIONS:
        target = symbols[symbol] + addend + struct.unpack_from("<I", content, offset)[0]
        if kind == 2:
            target -= va + offset
        struct.pack_into("<I", content, offset, target & 0xFFFFFFFF)
    space._require(len(content) <= SETTING_OFFSET, "Speed threshold exceeds its code reservation")
    return bytes(content).ljust(SETTING_OFFSET, b"\xcc") + bytes([value]) + b"\xcc" * 3


def sites(va):
    return [("vertical_man_speed", HOOK_VA, RETAIL_HOOK,
             b"\xe9" + struct.pack("<i", va - HOOK_VA - 5) + b"\x90\x90")]


def allocation(payload):
    rows = [a for a in space.layout(payload)["allocations"] if a["owner"] == OWNER]
    space._require(len(rows) == 1 and (rows[0]["kind"], rows[0]["size"], rows[0]["align"])
                   == REQUESTS[0][1:], "Missing or foreign speed-threshold allocation")
    return rows[0]


def _inspect(payload):
    space._require(isinstance(payload, bytes) and 0x178 <= len(payload) <= space.SCALE_FILE_SIZE,
                   "Expected bounded default.xbe bytes")
    try:
        layout = space.layout(payload)
    except zlib.error as exc:
        raise ValueError("Foreign speed-threshold allocation directory") from exc
    image = XbeImage(payload)
    value, va = None, 0
    if any(a["owner"] == OWNER for a in layout["allocations"]):
        va = allocation(payload)["va"]
        code = image.read(va, CODE_SIZE)
        if code != b"\xcc" * CODE_SIZE:
            value = validate(code[SETTING_OFFSET])
            space._require(code == code_for(va, value), "Foreign speed-threshold code or padding")
    for _, hook, before, after in sites(va):
        space._require(image.read(hook, len(before)) == (before if value is None else after),
                       "Foreign or mixed speed-threshold hook")
    for start, size, digest in GUARDS:
        blob = bytearray(image.read(start, size))
        if start <= HOOK_VA and HOOK_VA + len(RETAIL_HOOK) <= start + size:
            blob[HOOK_VA-start:HOOK_VA-start+len(RETAIL_HOOK)] = RETAIL_HOOK
        space._require(hashlib.sha256(blob).hexdigest() == digest,
                       f"Foreign speed-threshold prerequisite at {start:#x}")
    return value


def status(payload):
    try:
        return "retail" if _inspect(payload) is None else "applied"
    except (ValueError, TypeError, KeyError, IndexError, struct.error, OverflowError):
        return "foreign"


def verify(payload, *, value=None):
    installed = _inspect(payload)
    if value is not None:
        space._require(installed == validate(value), "Speed threshold differs; rebuild from source")
    return dict(status="retail" if installed is None else "applied",
                value=DEFAULT if installed is None else installed, runtime_witnessed=False)


def reservations(payload):
    return [r for r in space.reservations(payload) if r["owner"] == OWNER] + [
        dict(owner=OWNER, start=hex(HOOK_VA), end=hex(HOOK_VA+len(RETAIL_HOOK)),
             size=len(RETAIL_HOOK), basis="pinned ordinary speed epilogue; not a cave")]


def apply(payload, *, value=None):
    """Explicit installation can carry 0; Studio skips the writer at default 0.

    Omitted value preserves an existing verified installation. A changed value
    refuses. On a sealed v3 image the allocator may append this late owner only
    if every existing allocation stays fixed and the new span is padding.
    """
    previous = _inspect(payload)
    chosen = validate((DEFAULT if previous is None else previous) if value is None else value)
    if previous is not None:
        space._require(previous == chosen, "Speed threshold differs; rebuild from source")
        return payload, dict(owner=OWNER, status="already_applied", value=chosen, changed_bytes=0)
    allocated, receipt = payload, {}
    if space.status(payload) == "retail":
        allocated, receipt = space.apply(payload, REQUESTS, scaleout=True)
    elif not any(a["owner"] == OWNER for a in space.layout(payload)["allocations"]):
        allocated, receipt = space.extend_scaleout(payload, REQUESTS)
    row = allocation(allocated)
    installed, _ = space.install_code(allocated, OWNER, code_for(row["va"], chosen))
    result, patch = rdata.apply(installed, sites(row["va"]), OWNER)
    return result, dict(**verify(result, value=chosen), owner=OWNER, allocation=receipt,
                        reservations=reservations(result), sections_repinned=patch["sections_repinned"],
                        edits=[dict(label="vertical_man_speed", va=HOOK_VA, size=len(RETAIL_HOOK))],
                        changed_bytes=space.count_differing_bytes(payload, result) + len(result)-len(payload),
                        file_growth=len(result)-len(payload),
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xbe", type=Path)
    parser.add_argument("--value", type=int)
    parser.add_argument("--output", type=Path, help="new file only; omit to inspect")
    args = parser.parse_args(argv)
    if args.value is not None and args.output is None:
        parser.error("--value requires --output")
    try:
        with args.xbe.open("rb") as stream:
            payload = stream.read(space.SCALE_FILE_SIZE + 1)
        if args.output is None:
            receipt = verify(payload)
        else:
            result, receipt = apply(payload, value=args.value)
            with args.output.open("xb") as stream:
                stream.write(result)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
