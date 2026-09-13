"""One existing dry-weather haze coefficient. EXPERIMENTAL / UNWITNESSED.

Data-only XBE edit, no caves, hooks or runtime allocations. The native reader
still decides eligibility. This does not force fog, introduce a sky set, or
change time of day during a game.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = "nfl2k5_weather_haze"
REQUESTS = CAVES = RUNTIME_GLOBALS = ()
DEFAULT_ENABLED = False
BUILD_CAPTION = "Existing dry-weather haze response (experimental)"
HELP_TEXT = (
    "EXPERIMENTAL / UNWITNESSED. Changes one existing renderer coefficient from "
    "0.8 to 1.0 when retail selects dry outdoor haze. Clear weather with zero haze, "
    "rain, snow and indoor settings keep their native parameters. Does not force "
    "fog or add sky artwork. Appearance is unwitnessed. Off in every preset."
)
SITE_VA = 0xA867F4
TABLE_VA, TABLE_SIZE = 0xA867F0, 60
TABLE_SHA256 = "311636b9459867b8fb1fb57be66e6bee17660119754995f678f8f9e1f6642520"
BEFORE, AFTER = struct.pack("<f", 0.8), struct.pack("<f", 1.0)
GUARDS = (
    (0x85EF0, 160, "9a6c2b318862584e4831c20c289a3686cf206dc63df001a3cc57bf0758944777"),
    (0x86190, 35, "a2dd6d42a842bb0da56a1acb2da8b76580acd0dd73b4769bb5a0fa15922374ae"),
    (0x77BB0, 95, "5c18644f31c7c71ac8aa3c5b389788ce29be30d9487932e3a6fa8f4528da9e5f"),
)


def _inspect(payload):
    image = XbeImage(payload)
    for va, size, digest in GUARDS:
        if hashlib.sha256(image.read(va, size)).hexdigest() != digest:
            raise ValueError(f"Weather haze reader changed at {va:#x}; rebuild from a supported base")
    table = bytearray(image.read(TABLE_VA, TABLE_SIZE))
    value = bytes(table[4:8])
    if value not in (BEFORE, AFTER):
        raise ValueError("Foreign weather haze coefficient; rebuild from a supported base")
    table[4:8] = BEFORE
    if hashlib.sha256(table).hexdigest() != TABLE_SHA256:
        raise ValueError("Weather haze table changed outside the owned coefficient")
    if image.section(SITE_VA).name != ".data":
        raise ValueError("Weather haze coefficient is not in the expected data section")
    return value == AFTER


def status(payload):
    try:
        return "applied" if _inspect(payload) else "retail"
    except (ValueError, TypeError, IndexError, struct.error):
        return "foreign"


def verify(payload, *, enabled=True):
    if type(enabled) is not bool or _inspect(payload) != enabled:
        raise ValueError("Weather haze coefficient does not match the requested option")
    return dict(state="applied" if enabled else "retail", enabled=enabled,
                coefficient=struct.unpack("<f", XbeImage(payload).read(SITE_VA, 4))[0],
                label="EXPERIMENTAL / UNWITNESSED", runtime_witnessed=False)


def apply(payload, *, enabled=True):
    if type(enabled) is not bool:
        raise ValueError("Weather haze must be Off or On")
    _inspect(payload)
    result = bytearray(payload)
    at = XbeImage(payload).offset(SITE_VA, 4)
    result[at:at+4] = AFTER if enabled else BEFORE
    # Only this section changed; preserve the other owners' digests verbatim.
    for section in _sections(result):
        if section.header_offset == XbeImage(payload).section(SITE_VA).header:
            result[section.header_offset+36:section.header_offset+56] = section_digest(result, section)
    result = bytes(result)
    return result, dict(verify(result, enabled=enabled),
                        changed_bytes=sum(a != b for a, b in zip(payload, result)),
                        edits=[dict(va=hex(SITE_VA), size=4)])


def reservations(payload):
    verify(payload)
    return [dict(owner=OWNER, start=hex(SITE_VA), end=hex(SITE_VA+4), size=4,
                 basis="one pinned existing dry-weather renderer coefficient; no runtime space")]
