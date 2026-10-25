"""Third-down run preference for the native CPU play selector (b778 ai8). EXPERIMENTAL / UNWITNESSED.

The generated modern books carry run plays in every formation, and the retail play selector 0x2096A0 blends run and
pass scores with a single run weight at [EBP-0xC] (0.4 on a third-down call, or the game's 0xBF16F8 value on the other
path). It has no distance term: on third and long it still gives runs that weight, so the native lottery calls draws
and wildcat runs the NFL does not. Over 32 compiled books and 1,920 samples per distance bucket the native selector
called 19.9 percent runs on 3rd and 7-10 and 19.3 percent on 3rd and 11+; the automatic coach pools are worse (the
20-pool map puts 3rd and 3+ in the same pool as 1st/2nd and long, and the shipped late-leading pool 15 has a 33
percent pass target).

This owner hooks 0x2096DE (the call to the native 0x2045E0 book setup, after both run-weight paths have stored
[EBP-0xC]). On third down with at least 7 yards to go it lowers the run weight to 0.05, so run candidates keep 5
percent of their blended score and the selector chooses a pass. A third and 20+ in the fourth quarter, inside five
minutes, with the offense leading is left alone: running there is the measured NFL behavior (nflverse 2023-2025,
12 of 15 such calls). Third and 1-6, every other down, and every non-CPU path keep the retail value exactly.

The stub preserves every register, flag and the x87 stack, reserves the 128-byte red zone before pushing, re-executes
the displaced native call and jumps back to 0x2096E3. It needs no writable data and no runtime allocation. The 192-byte
code allocation is a late owner appended after every existing owner; the only image edit is the five-byte hook at
0x2096DE. The instruction is entered by the native caller 0x20B670 and by the automatic coach kernel's native fallback.
"""
from __future__ import annotations

import hashlib
import struct

OWNER = "nfl2k5_cpu_third_down"
CODE_SIZE = 192
REQUESTS = ((OWNER, "code", CODE_SIZE, 16),)
BUILD_CAPTION = "CPU third-down run preference (experimental)"
SITE_VA = 0x2096DE
SITE_BEFORE = bytes.fromhex("e8fdaeffff")
CALL_VA = 0x2045E0
BACK_VA = 0x2096E3
CODE = bytes.fromhex(
    "81ec800000009c608b1dec02e60085db7473837b0403756dd94328d86318d9e183ec04d91c248b042483c4043d1f0520"
    "4472523d9a99e4447244833dc402e60004753b8b0d8c02e60085c974318b491081f90000964377268b0d8002e60085c9"
    "741c8b510885d274158b028b0985c9740d8b490885c974062b017e02eb07c745f4cdcc4c3d619d81c480000000e8dc45"
    "2000e9df962000"
)
# (offset in CODE, kind, target VA). Kind 2 is a PC-relative rel32 from offset+4.
RELOCATIONS = ((0x8E, 2, CALL_VA), (0x93, 2, BACK_VA))


class ThirdDownError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise ThirdDownError(message)


def code_for(va):
    out = bytearray(CODE)
    for offset, kind, target in RELOCATIONS:
        if kind == 2:
            struct.pack_into("<i", out, offset, target - (va + offset + 4))
        else:
            struct.pack_into("<I", out, offset, target)
    require(len(out) <= CODE_SIZE, "third-down code exceeds its RX allocation")
    return bytes(out).ljust(CODE_SIZE, b"\xcc")


def sites(va):
    after = b"\xe9" + struct.pack("<i", va - (SITE_VA + 5))
    return (("third_down_blend", SITE_VA, SITE_BEFORE, after),)


def allocations(payload):
    from . import nfl2k5_xbe_space as space
    rows = [r for r in space.layout(payload)["allocations"] if r["owner"] == OWNER]
    require(len(rows) <= 1, "Duplicate CPU third-down allocation")
    if rows:
        row = rows[0]
        require((row["kind"], row["size"], row["align"]) == ("code", CODE_SIZE, 16),
                "Foreign CPU third-down allocation")
    return rows[0] if rows else None


def _site_state(payload, row):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    raw = image.read(SITE_VA, len(SITE_BEFORE))
    if raw == SITE_BEFORE:
        return "retail"
    if row is not None and raw == sites(row["va"])[0][3] and image.read(row["va"], CODE_SIZE) == code_for(row["va"]):
        return "applied"
    return "foreign"


def status(payload):
    try:
        return _site_state(payload, allocations(payload))
    except (ValueError, TypeError, KeyError, IndexError, struct.error):
        return "foreign"


def normalized_sites(payload):
    from .nfl2k5_cave_oracle import XbeImage
    image = XbeImage(payload)
    if image.read(SITE_VA, len(SITE_BEFORE)) == SITE_BEFORE:
        return []
    require(status(payload) == "applied", "Foreign CPU third-down hook")
    return sites(allocations(payload)["va"])


def apply(payload):
    from . import nfl2k5_xbe_space as space
    from .nfl2k5_bump_strength import _sections, section_digest
    from .nfl2k5_cave_oracle import XbeImage
    state = status(payload)
    if state == "applied":
        return payload, dict(owner=OWNER, status="already_applied", changed_bytes=0, edits=[])
    require(state == "retail", "Foreign CPU third-down hook")
    row = allocations(payload)
    if row is None:
        if space.status(payload) == "retail":
            payload, allocation = space.apply(payload, REQUESTS, scaleout=True)
        else:
            require(space.is_scaleout(payload), "CPU third-down owner needs the scale-out allocator")
            payload, allocation = space.extend_scaleout(payload, REQUESTS)
    else:
        allocation = dict(status="already_allocated", allocations=[row])
    row = allocations(payload)
    va = row["va"]
    payload, _ = space.install_code(payload, OWNER, code_for(va))
    image = XbeImage(payload)
    buf = bytearray(payload)
    edits = []
    for name, site, before, after in sites(va):
        off = image.offset(site, len(before))
        require(bytes(buf[off:off + len(before)]) == before, f"CPU third-down site {site:#x} is not retail")
        buf[off:off + len(before)] = after
        edits.append(dict(label=name, va=hex(site), before=before.hex(), after=after.hex()))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    require(status(result) == "applied", "CPU third-down postcondition failed")
    return result, dict(owner=OWNER, status="applied", changed_bytes=space.count_differing_bytes(payload, result),
                        file_growth=len(result) - len(payload), allocation=allocation, edits=edits,
                        before_sha256=hashlib.sha256(payload).hexdigest(),
                        after_sha256=hashlib.sha256(result).hexdigest())


__all__ = ["OWNER", "CODE_SIZE", "REQUESTS", "BUILD_CAPTION", "SITE_VA", "SITE_BEFORE", "CALL_VA", "BACK_VA",
           "CODE", "RELOCATIONS", "ThirdDownError", "code_for", "sites", "allocations", "status",
           "normalized_sites", "apply"]
