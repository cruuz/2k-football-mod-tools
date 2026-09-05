"""Immutable jukebox song records with pinned collection pointer ownership.

EXPERIMENTAL / UNWITNESSED. No profile purchases or playback policies change.
The first 59 logical indices keep their retail collection/song identities.
Additional songs fill the free collections, with at most 256 songs per list.
"""
from __future__ import annotations

import hashlib
import json
import struct

from . import nfl2k5_music_storage as storage
from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage

OWNER = storage.OWNER
COLLECTIONS = 0xAC9C80
RETAIL = ((4, 11312192), (4, 11312128), (4, 11312064), (4, 11312000),
          (4, 11311936), (4, 11311872), (4, 11311808), (4, 11311744),
          (3, 11311696), (3, 11311648), (3, 11311600), (2, 11311568),
          (3, 11311520), (2, 11311488), (2, 11311456), (2, 11311424),
          (3, 11311376), (4, 11311312))
RECORDS_SHA256 = '926b5827abef41bee3b9dd86333705b108710a7714136e6f5571fbbd26179593'
MAGIC = b'MSONGS1\0'


def _offset(payload, va, size):
    section = XbeImage(payload).section(va)
    space._require(section is not None and va+size <= section.start+section.raw_size, 'unmapped music field')
    return section.raw + va-section.start


def identities(count):
    space._require(type(count) is int and 1 <= count <= 400, 'jukebox library must contain 1..400 songs')
    result = [(c, s) for c, (n, _) in enumerate(RETAIL) for s in range(n)][:count]
    lengths = [sum(c == col for c, _ in result) for col in range(18)]
    for _ in range(len(result), count):
        col = next(c for c in (17, 16, 15, 14) if lengths[c] < 256)
        result.append((col, lengths[col]))
        lengths[col] += 1
    return result


def _document(songs):
    identities(len(songs))
    result = []
    for song in songs:
        space._require(set(song) == {'title', 'artist', 'frames'}, 'metadata needs title, artist, frames')
        for key in ('title', 'artist'):
            value = song[key]
            space._require(isinstance(value, str) and 1 <= len(value) <= 120
                           and all(ord(c) >= 32 for c in value), 'invalid song title/artist')
            value.encode('utf-16le')
        frames = song['frames']
        space._require(type(frames) is int and 0 < frames <= ((600*22050+63)//64)*64
                       and frames % 64 == 0, 'invalid song frames')
        result.append(dict(song))
    return result


def build(songs):
    songs = _document(songs)
    doc = json.dumps(songs, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
    data = bytearray(MAGIC + struct.pack('<I', len(doc)) + doc)
    data.extend(bytes((-len(data)) % 16))
    records = len(data)
    data.extend(bytes(16 * len(songs)))
    base = storage.VA + storage.PREFIX
    groups = [[] for _ in range(18)]
    for index, (song, (collection, _)) in enumerate(zip(songs, identities(len(songs)))):
        pointers = []
        seconds = song['frames'] // 22050
        for value in (song['title'], song['artist'], f'{seconds//60}:{seconds%60:02d}'):
            pointers.append(base + len(data))
            data.extend(value.encode('utf-16le') + b'\0\0')
        struct.pack_into('<4I', data, records + index*16, index, *pointers)
        groups[collection].append(index)
    # Keep each collection contiguous even after extending a free collection.
    fields = []
    for indices in groups:
        data.extend(bytes((-len(data)) % 16))
        pointer = base + len(data)
        for index in indices:
            data.extend(data[records+index*16:records+(index+1)*16])
        fields.append((len(indices), pointer))
    space._require(len(data) <= storage.CAPACITY-storage.PREFIX, 'jukebox metadata exceeds read-only budget')
    return bytes(data), fields


def songs(payload):
    _, data = storage.unwrap(payload)
    space._require(data[:8] == MAGIC, 'foreign song records')
    length = struct.unpack_from('<I', data, 8)[0]
    space._require(0 < length <= len(data)-12, 'foreign song document length')
    result = json.loads(data[12:12+length])
    expected, _ = build(result)
    space._require(data == expected, 'foreign song metadata bytes')
    return result


def _fields(payload):
    return [struct.unpack_from('<2I', payload, _offset(payload, COLLECTIONS+i*32+24, 8)) for i in range(18)]


def status(payload):
    try:
        space._require(space.status(payload) != 'foreign', 'foreign allocator')
        at = _offset(payload, 0xAC98D0, 59*16)
        space._require(hashlib.sha256(payload[at:at+59*16]).hexdigest() == RECORDS_SHA256, 'foreign retail song records')
        for i in range(18):
            at = _offset(payload,COLLECTIONS+i*32+8,12)
            space._require(struct.unpack_from('<3I',payload,at) == (15280692,15280712,1),
                           'foreign collection bank pointers/enabled word')
        if struct.unpack_from('<I', payload, 0x11C)[0] != 25:
            return 'retail' if _fields(payload) == list(RETAIL) else 'foreign'
        _, fields = build(songs(payload))
        return 'applied' if _fields(payload) == fields else 'foreign'
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError):
        return 'foreign'


def apply(payload, song_records):
    state = status(payload)
    space._require(state != 'foreign', 'mixed/foreign jukebox metadata; rebuild from base')
    data, fields = build(song_records)
    if state == 'applied':
        space._require(songs(payload) == _document(song_records), 'different jukebox recipe; rebuild from base')
        return payload, dict(status='already_applied', changed_bytes=0)
    grown, allocation = space.apply(payload)
    grown, ro = storage.install(grown, data)
    buf = bytearray(grown)
    edits = []
    for i, values in enumerate(fields):
        va = COLLECTIONS+i*32+24
        at = _offset(buf, va, 8)
        struct.pack_into('<2I', buf, at, *values)
        edits.append(dict(label='collection_count_and_records', va=hex(va), size=8))
    for section in _sections(buf):
        buf[section.header_offset+36:section.header_offset+56] = section_digest(buf, section)
    result = bytes(buf)
    space._require(status(result) == 'applied', 'jukebox metadata postcondition failed')
    return result, dict(status='applied', experimental=True, runtime_witnessed=False,
                        count=len(song_records), edits=edits, allocation=allocation, read_only=ro,
                        changed_bytes=sum(a != b for a,b in zip(payload,result))+len(result)-len(payload),
                        file_growth=len(result)-len(payload), identities=identities(len(song_records)))
