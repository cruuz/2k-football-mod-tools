"""Ordinary tap bursts independent of the current role's move attribute.

Retail scales the initial 4% burst by state+190. For a return carrier that
cache is effective Break Tackle (getter 1DDE20), so a fast DB with a low
offensive rating gets almost no initial burst. Keep condition, animation,
duration and repeated-tap arithmetic; omit that extra scale for the ordinary
0.25-second burst only. The charged 1.5-second branch remains bit-identical.
This fixed .text span needs no new allocation, hook or runtime dependency.
"""
from __future__ import annotations

import hashlib

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

START, END = 0x30EDF1, 0x30EE25
BEFORE = bytes.fromhex(
    "d9442410d8259c414e008bcfdec9d8059c414e00d95c2410"
    "d98690010000d9442410d8259c414e00dec9d8059c414e00d95c2410")
# ST0 is the native condition curve on entry. Round its result through the
# same float32 slot as retail before the role scaling. The duration was set
# above to exactly 0.25 (ordinary) or 1.5 (charged); neither is rewritten.
# FLD1 / FSUBP and FLD1 / FADDP compute the same x87 operations as the retail
# memory-constant forms, leaving enough room for the ordinary-only branch.
# Save EFLAGS for the new branch; the one extra stack word is accounted for
# in every local-slot displacement. GPRs and deeper x87 values are preserved.
AFTER = bytes.fromhex(
    "9c d9442414 d9e8 dee9 dec9 d9e8 dec1 d95c2414 d9442414"
    "807c24233e 740e d9e8 dee9 d88e90010000 d9e8 dec1"
    "d95c2414 8bcf 9d90")
assert len(BEFORE) == len(AFTER) == END - START
GUARDS = (
    (0x30EDAC, 69, "1813995af72cb7937ddbfd86f1b199372de21fa0762b381521a6dc05f70a4303"),
    (END, 306, "ef84345248d7e184cf5045e6f2aa4ce71d71d833d15fe1bd0081cc4dd3848257"),
    (0x237C70, 22, "cdeccafa56c472dc0902d17cd6c5ad0ed617f0365c5f9114ccb005d2189e515d"),
    (0x4E419C, 4, "e00e5eb9444182f352323374ef4e08ebcb784725fdd4fd612d7730540b3e0c8c"),
)


def status(payload):
    try:
        space.layout(payload)
        image = XbeImage(payload)
        for va, size, digest in GUARDS:
            data = image.read(va, size)
            if va == END and hashlib.sha256(data).hexdigest() != digest:
                from . import nfl2k5_human_tap_burst as human
                data = human.normalize_sp1_guard(payload, va, data)
            space._require(hashlib.sha256(data).hexdigest() == digest,
                           f"foreign tap-burst dependency at {va:#x}")
        current = image.read(START, len(BEFORE))
        return "retail" if current == BEFORE else "applied" if current == AFTER else "foreign"
    except (ValueError, KeyError, IndexError, TypeError):
        return "foreign"


def apply(payload):
    state = status(payload)
    space._require(state != "foreign", "foreign tap-burst initializer or prerequisite")
    if state == "applied":
        return payload, {"status": "already_applied", "changed_bytes": 0, "edits": []}
    image = XbeImage(payload)
    offset = image.offset(START, len(BEFORE))
    buf = bytearray(payload)
    buf[offset:offset + len(AFTER)] = AFTER
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    result = bytes(buf)
    space._require(status(result) == "applied", "tap-burst postcondition failed")
    return result, {"status": "applied", "changed_bytes": space.count_differing_bytes(payload, result),
                    "file_growth": 0, "charged_arithmetic_unchanged": True,
                    "edits": [{"label": "ordinary_tap_burst", "va": hex(START),
                               "file_offset": hex(offset), "size": len(AFTER),
                               "before": BEFORE.hex(), "after": AFTER.hex()}]}
