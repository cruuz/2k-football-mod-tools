"""Allocator-owned, preloaded read-only music records, outside retail mappings.

The existing allocator relocates all 196 bytes at 0x840..0x904. Its first two
descriptors consume 112 of those retired bytes. A third consumes another 56;
the remaining 28 hold its name and separate page counters. No retail cave or
unknown padding is allocated. The existing code and writable pages stay put.
"""
from __future__ import annotations

import hashlib
import struct

from . import nfl2k5_xbe_space as space

OWNER = 'nfl2k5_music_metadata'
VA = space.DATA_VA + space.PAGE
RAW = space.FILE_SIZE
CAPACITY = 0x10000
FILE_SIZE = RAW + CAPACITY
HEADER = space.META_START + 112
NAME = HEADER + 56
REFS = NAME + 8
PREFIX = 128
MAGIC = b'MUSICRO1'


def _slots(extended):
    return ((space.META_START + 168, space.MUSIC2_NAME, space.MUSIC2_REFS)
            if extended else (HEADER, NAME, REFS))


def _descriptor(data, extended=False):
    _header, name, refs = _slots(extended)
    return struct.pack('<9I20s', 0x3A, VA, CAPACITY, RAW, CAPACITY,
                       0x10000 + name, 0, 0x10000 + refs, 0x10000 + refs + 2,
                       space._digest(data))


def unwrap(payload):
    """Validate the complete allocation and project the original 24 sections."""
    extended = len(payload) == space.EXT_FILE_SIZE
    space._require(len(payload) in (FILE_SIZE, space.EXT_FILE_SIZE), 'foreign music allocation extent')
    header, name, refs = _slots(extended)
    block = payload[RAW:RAW + CAPACITY]
    space._require(block[:8] == MAGIC, 'foreign music allocation magic')
    size = struct.unpack_from('<I', block, 8)[0]
    space._require(0 < size <= CAPACITY-PREFIX, 'foreign music allocation size')
    data = block[PREFIX:PREFIX+size]
    space._require(block[12:44] == hashlib.sha256(data).digest()
                   and not any(block[44:PREFIX]) and not any(block[PREFIX+size:]),
                   'foreign music allocation seal/padding')
    space._require(payload[header:header+56] == _descriptor(block, extended)
                   and payload[name:refs+4] == b'.ASTRAr\0' + bytes(4),
                   'foreign read-only music section')
    expected_image = space.EXT_IMAGE_SIZE if extended else VA+CAPACITY-0x10000
    space._require(struct.unpack_from('<I', payload, 0x10C)[0] == expected_image,
                   'foreign music image size')
    base = bytearray(payload if extended else payload[:RAW])
    if extended:
        base[RAW:RAW + CAPACITY] = bytes(CAPACITY)
        # Restore the exact extended allocator tail, including code-page name.
        tail = space._extra_header_tail()
        expected = bytearray(tail)
        offset = header - (space.META_START + 168)
        expected[offset:offset+56] = _descriptor(block, True)
        offset = name - (space.META_START + 168)
        expected[offset:offset+12] = b'.ASTRAr\0' + bytes(4)
        space._require(payload[space.META_START+168:space.LIB_END] == expected,
                       'foreign extended music header suffix')
        base[space.META_START+168:space.LIB_END] = tail
    else:
        space._require(payload[REFS+4:space.META_END] ==
                       payload[space.META_COPY+REFS+4-space.META_START:space.NAMES],
                       'foreign retired music header suffix')
        base[HEADER:space.META_END] = payload[space.META_COPY+112:space.NAMES]
    struct.pack_into('<I', base, 0x11C, 25 if extended else 24)
    struct.pack_into('<I', base, 0x10C, space.EXT_IMAGE_SIZE if extended else space.IMAGE_SIZE)
    return bytes(base), data


def install(payload, data):
    """Immutable exact replay; reconfiguration needs a rebuild from base."""
    data = bytes(data)
    space._require(0 < len(data) <= CAPACITY-PREFIX, 'music read-only allocation exceeds 65408 bytes')
    count = struct.unpack_from('<I', payload, 0x11C)[0]
    if space.has_music(payload):
        base, old = unwrap(payload)
        space._require(space.status(base) == 'applied' and old == data, 'foreign/different music allocation')
        return payload, {'status': 'already_applied', 'changed_bytes': 0}
    space._require(count in (24, 25) and space.status(payload) == 'applied', 'music requires established XBE allocator')
    extended = count == 25
    header, name, refs = _slots(extended)
    block = bytearray(CAPACITY)
    block[:8] = MAGIC
    struct.pack_into('<I', block, 8, len(data))
    block[12:44] = hashlib.sha256(data).digest()
    block[PREFIX:PREFIX+len(data)] = data
    buf = bytearray(payload) if extended else bytearray(payload) + block
    buf[RAW:RAW + CAPACITY] = block
    buf[header:header+56] = _descriptor(block, extended)
    buf[name:refs+4] = b'.ASTRAr\0' + bytes(4)
    struct.pack_into('<I', buf, 0x11C, 26 if extended else 25)
    struct.pack_into('<I', buf, 0x10C, space.EXT_IMAGE_SIZE if extended else VA+CAPACITY-0x10000)
    result = bytes(buf)
    space._require(space.status(result) == 'applied', 'music allocation postcondition failed')
    return result, {'status': 'applied', 'file_growth': len(result) - len(payload), 'reservations': reservations()}


def reservations():
    return [dict(owner=OWNER, start=hex(VA), end=hex(VA+CAPACITY), size=CAPACITY,
                 basis='owned new read-only preload section; immutable music metadata and padding')]


def allocation_evidence(retail, manifest):
    from .nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
    image = XbeImage(retail)
    space._require(image.sha256 == RETAIL_SHA256 == manifest.document.get('retail_sha256'), 'music proof requires pinned retail')
    space._require(all(s.end <= VA for s in image.sections) and image.base+image.image_size <= VA,
                   'music allocation overlaps retail mapping')
    space._require(not manifest.overlaps(VA, VA+CAPACITY, exclude_owner=OWNER), 'music allocation overlaps owner')
    hits = []
    spans = [(image.base, retail[:image.headers_size], False)]
    spans += [(s.start, retail[s.raw:s.raw+s.raw_size], s.executable) for s in image.sections]
    for base, data, executable in spans:
        for at in range(len(data)):
            if at+4 <= len(data) and VA <= struct.unpack_from('<I', data, at)[0] < VA+CAPACITY:
                hits.append((base+at, 'absolute'))
            if not executable:
                continue
            op, prefix, width = data[at], 0, 0
            if op in (0xE8, 0xE9): prefix, width = 1, 4
            elif op == 15 and at+1 < len(data) and 0x80 <= data[at+1] <= 0x8F: prefix, width = 2, 4
            elif op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3: prefix, width = 1, 1
            if width and at+prefix+width <= len(data):
                delta = int.from_bytes(data[at+prefix:at+prefix+width], 'little', signed=True)
                if VA <= (base+at+prefix+width+delta) & 0xFFFFFFFF < VA+CAPACITY:
                    hits.append((base+at, 'relative'))
    # A byte-granular scan also treats compressed bitmaps, float tables and
    # instruction substrings as pointers. Unlike an overwritten retail cave,
    # this allocation adds a new mapping after the existing loader image.
    # Retain ALL candidates in the receipt; never report this range as a free
    # cave or claim the raw-reference scan was empty. Dynamic aliases remain
    # an explicit loader/gameplay witness boundary.
    return dict(start=hex(VA), end=hex(VA+CAPACITY), raw_encoding_candidates=hits,
                manifest_overlaps=[],retail_mapping_overlaps=[],
                allocation='new allocator-owned read-only loader section; no retail address overwritten',
                proof='pinned loader geometry and ownership; raw encodings are not a free-cave verdict')
