"""Bound Crib collection rows by the existing widget-label block.

PROVED in bounded native execution; in-game behavior remains UNWITNESSED.
Disc collections start at label 49 and have four rows; HDD collections start
at label 22 and have thirteen. Retail incorrectly uses thirteen for both.
This in-place loop repair owns no cave, table, or runtime state.
"""
from __future__ import annotations

import hashlib
import struct

from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = 'nfl2k5_jukebox_list'
CAVES = ()
RUNTIME_GLOBALS = ()
FUNCTION_VA, FUNCTION_SIZE = 0x32A0F0, 435
FUNCTION_SHA256 = '36a66f2a35336c845fc2713630d397947c8d96b9365bdf68860d5583dff22a80'
# Keep the pointer initialization at +0x62. Reuse only the alignment NOP
# immediately before the live loop, then retarget its one backward branch.
SITES = (
    (0x32A159, bytes.fromhex('8da4240000000083ff0d0f8dec000000'),
     bytes.fromhex('81fe1c62ae000f83f000000090909090')),
    (0x32A24F, bytes.fromhex('0f840bffffff'), bytes.fromhex('0f8404ffffff')),
)


def status(payload):
    try:
        image = XbeImage(payload)
        normalized = bytearray(image.read(FUNCTION_VA, FUNCTION_SIZE))
        states = set()
        for va, before, after in SITES:
            actual = image.read(va, len(before))
            states.add('retail' if actual == before else 'applied' if actual == after else 'foreign')
            normalized[va-FUNCTION_VA:va-FUNCTION_VA+len(before)] = before
        if hashlib.sha256(normalized).hexdigest() != FUNCTION_SHA256:
            return 'foreign'
        return states.pop() if len(states) == 1 else 'foreign'
    except (ValueError, IndexError, struct.error):
        return 'foreign'


def apply(payload):
    state = status(payload)
    if state == 'foreign':
        raise ValueError('Foreign or mixed Crib collection list builder; rebuild from base')
    if state == 'applied':
        return payload, dict(status='already_applied', changed_bytes=0, runtime_witnessed=False)
    image, result = XbeImage(payload), bytearray(payload)
    for va, before, after in SITES:
        at = image.offset(va, len(before))
        result[at:at+len(after)] = after
    for section in _sections(result):
        result[section.header_offset+36:section.header_offset+56] = section_digest(result, section)
    result = bytes(result)
    if status(result) != 'applied':
        raise ValueError('Crib collection list postcondition failed')
    return result, dict(status='applied', runtime_witnessed=False,
        changed_bytes=sum(a != b for a, b in zip(payload, result)),
        disc_visible_rows=4, hdd_visible_rows=13,
        edits=[dict(va=hex(va), size=len(before)) for va, before, _ in SITES])


def reservations(payload):
    if status(payload) != 'applied':
        raise ValueError('Collection reservations require verified installed bytes')
    return [dict(owner=OWNER, start=hex(va), end=hex(va+len(before)), size=len(before),
                 basis='pinned live loop: Crib collection widget bound')
            for va, before, _ in SITES]
