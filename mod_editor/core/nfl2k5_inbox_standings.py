"""Repair the retail last-undefeated inbox story's missing table setup.

Story 23 (generator 0x27EB80) stores the fallen club in its first argument.
Its body callback 0x3603D0 resolves that club into the standings row pointer,
but its setup callback is null, leaving the shared row count at zero (or at
the previous story's count). Reuse 0x3616A0, the existing single-team setup.
The body then replaces its initial user-team pointer with the fallen club.

Only one existing descriptor pointer changes. No new code, cave, save field
or roster data is needed. Native execution is tested offline; rendered proof
must be obtained in xemu when the host permits its sockets.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_inbox_standings"
BUILD_CAPTION = "Inbox standings: last-undefeated story"
HELP_TEXT = ("Restores the missing single-team standings setup for the last-undefeated inbox story, so its "
             "table opens with the fallen club instead of an empty or stale list. One existing descriptor "
             "pointer is repaired; no new code or save field.")
REQUESTS = ()
STORY = 23
DESCRIPTOR = 0xAED1AC
SETUP_SITE = DESCRIPTOR + 0x10
SINGLE_TEAM_SETUP = 0x3616A0
PINS = (
    (DESCRIPTOR, 0x34, "d1bdac383f89918c65c9ae582f11e22e5b4831c7b1c1cff38bb563d225e1ffa8"),
)
# Kept separately from the editable descriptor; a foreign callback refuses
# even if the target pointer happens to have a supported value.
CALLBACK_PINS = (
    (0x3616A0, 0x15, "4922846d2ea5035ff8d1a5f85c1b84ca832986b8c1bcea849c874a35732a8558"),
    (0x3603D0, 0x9D, "05a3f655f364c8107f9f8320f7e60d41f870bbf2595809ab4f66e24280ee0014"),
    (0x361E90, 7, "bbd28817bf5b86633bbde018e1f46586f0d5ac42df91e53f599fd3babfd1aa53"),
    (0x361E80, 8, "7ea28b6942379913196ae9043d4d030e0f59b26baeabad869d1fcc3b45beaab3"),
    (0x27EB80, 0x92, "b71c30b0f770b7cd1b073104e0cc7c26bfb71649e0a6f88bd762b0b756b4df5b"),
    (0x361830, 0x19, "d27affa425d8cff8cc8c55214b37d6a8a02054bc4236573f94a0dab01466b517"),
)


class InboxStandingsError(ValueError):
    """The story descriptor or a reused retail routine is unsupported."""


def status(payload: bytes) -> str:
    try:
        image = XbeImage(payload)
        pointer = struct.unpack("<I", image.read(SETUP_SITE, 4))[0]
        if pointer not in (0, SINGLE_TEAM_SETUP):
            return "foreign"
        descriptor = bytearray(image.read(DESCRIPTOR, 0x34))
        descriptor[0x10:0x14] = bytes(4)
        if hashlib.sha256(descriptor).hexdigest() != PINS[0][2]:
            return "foreign"
        for address, size, digest in CALLBACK_PINS:
            if hashlib.sha256(image.read(address, size)).hexdigest() != digest:
                return "foreign"
        return "applied" if pointer else "retail"
    except (ValueError, struct.error, IndexError):
        return "foreign"


def apply(payload: bytes) -> tuple[bytes, dict]:
    state = status(payload)
    if state == "foreign":
        raise InboxStandingsError("unsupported last-undefeated story descriptor or callback")
    if state == "applied":
        return payload, {"already_applied": True, "changed_bytes": 0}
    image = XbeImage(payload)
    out = bytearray(payload)
    offset = image.offset(SETUP_SITE, 4)
    struct.pack_into("<I", out, offset, SINGLE_TEAM_SETUP)
    section = next(s for s in image.sections if s.raw <= offset < s.raw + s.raw_size)
    touched = (section.header - (struct.unpack_from("<I", payload, 0x120)[0] - image.base)) // 56
    at = section.header + 36
    out[at:at + 20] = hashlib.sha1(struct.pack("<I", section.raw_size) +
                                  out[section.raw:section.raw + section.raw_size]).digest()
    result = bytes(out)
    if status(result) != "applied":
        raise InboxStandingsError("inbox standings read-back failed")
    return result, {"story": STORY, "site_va": hex(SETUP_SITE),
                    "setup_va": hex(SINGLE_TEAM_SETUP), "pointer_bytes": 4,
                    "edits": [{"label": "last_undefeated_table_setup", "va": hex(SETUP_SITE), "bytes": 4}],
                    "code_bytes": 0, "writable_bytes": 0, "readonly_bytes": 0,
                    "sections_repinned": [touched],
                    "changed_bytes": sum(a != b for a, b in zip(payload, result))}
