"""Immutable jukebox song records with pinned collection pointer ownership.

EXPERIMENTAL / UNWITNESSED. No profile purchases or playback policies change.
The first 59 logical indices keep their retail collection/song identities.
Additional songs own new named collections, with at most 256 songs per list.
The collection-entry freeze remains UNWITNESSED and belongs to job D2.
"""
from __future__ import annotations

import hashlib
import json
import struct

from . import nfl2k5_music_storage as storage
from . import nfl2k5_jukebox_list as jukebox_list
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
LEGACY_MAGIC = b'MSONGS1\0'
MAGIC = b'MSONGS2\0'
from . import nfl2k5_music_collections as collections


def _offset(payload, va, size):
    section = XbeImage(payload).section(va)
    space._require(section is not None and va+size <= section.start+section.raw_size, 'unmapped music field')
    return section.raw + va-section.start


def _legacy_identities(count):
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


def _legacy_build(songs):
    songs = _document(songs)
    doc = json.dumps(songs, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
    data = bytearray(LEGACY_MAGIC + struct.pack('<I', len(doc)) + doc)
    data.extend(bytes((-len(data)) % 16))
    records = len(data)
    data.extend(bytes(16 * len(songs)))
    base = storage.VA + storage.PREFIX
    groups = [[] for _ in range(18)]
    for index, (song, (collection, _)) in enumerate(zip(songs, _legacy_identities(len(songs)))):
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


def identities(count):
    space._require(type(count) is int and 1 <= count <= 400, 'jukebox library must contain 1..400 songs')
    retail = [(c, s) for c, (n, _) in enumerate(RETAIL) for s in range(n)]
    return retail[:count] + [(18 + i // 256, i % 256) for i in range(max(0, count - 59))]


def collection_label(value):
    space._require(isinstance(value, str) and 1 <= len(value.strip()) <= 120
                   and all(ord(c) >= 32 for c in value), 'collection name needs 1..120 characters on one line')
    return value.strip()


def build(songs, collection_name='My songs', *, headers=None):
    songs = _document(songs)
    collection_name = collection_label(collection_name)
    document = dict(songs=songs, collection_name=collection_name)
    doc = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('ascii')
    data = bytearray(MAGIC + struct.pack('<I', len(doc)) + doc)
    base = storage.VA + storage.PREFIX
    groups = [[] for _ in range(max(18, 18 + (max(0, len(songs)-59)+255)//256))]
    for index, (song, (collection, _)) in enumerate(zip(songs, identities(len(songs)))):
        pointers = []
        seconds = song['frames'] // 22050
        for value in (song['title'], song['artist'], f'{seconds//60}:{seconds%60:02d}'):
            pointers.append(base + len(data))
            data.extend(value.encode('utf-16le') + b'\0\0')
        groups[collection].append(struct.pack('<4I', index, *pointers))
    fields = []
    for records in groups:
        data.extend(bytes((-len(data)) % 16))
        fields.append((len(records), base + len(data)))
        data.extend(b''.join(records))
    names = []
    for index in range(18, len(groups)):
        names.append(base + len(data))
        label = collection_name if index == 18 else f'{collection_name} (2)'
        data.extend(label.encode('utf-16le') + b'\0\0')
    data.extend(bytes((-len(data)) % 16))
    if headers is None:
        headers = [bytes(24)] * 18  # sizing-only public build(); install supplies pinned source headers
    space._require(len(headers) == 18 and all(len(h) == 24 for h in headers), 'invalid collection headers')
    for index, values in enumerate(fields):
        # +4 is the artwork resource identifier, not a second display label.
        # Reuse the existing collection_17 artwork; inventing a resource name
        # would send the UI to an asset that does not exist on the disc.
        header = headers[index] if index < 18 else struct.pack('<6I', names[index-18], 0xE92D1C, 0xE92A34, 0xE92A48, 1, 0)
        data.extend(header + struct.pack('<2I', *values))
    space._require(len(data) <= storage.CAPACITY-storage.PREFIX, 'jukebox metadata exceeds read-only budget')
    return bytes(data), fields


def _headers(payload):
    image = XbeImage(payload)
    return [image.read(COLLECTIONS+i*32, 24) for i in range(18)]


def _contents(payload):
    _, data = storage.unwrap(payload)
    space._require(data[:8] in (MAGIC, LEGACY_MAGIC), 'foreign song records')
    length = struct.unpack_from('<I', data, 8)[0]
    space._require(0 < length <= len(data)-12, 'foreign song document length')
    document = json.loads(data[12:12+length])
    if data[:8] == LEGACY_MAGIC:
        expected, fields = _legacy_build(document)
        table = COLLECTIONS
        label = None
        result = document
    else:
        space._require(isinstance(document, dict) and set(document) == {'songs', 'collection_name'}, 'foreign song document')
        result, label = document['songs'], document['collection_name']
        expected, fields = build(result, label, headers=_headers(payload))
        table = storage.VA + storage.PREFIX + len(data) - len(fields)*32
    space._require(data == expected, 'foreign song metadata bytes')
    return result, label, fields, table


def songs(payload):
    return _contents(payload)[0]


def collection_table(payload):
    """Reparse the native table and validate every count/record pointer and title."""
    result, label, fields, table = _contents(payload)
    image = XbeImage(payload)
    rows = []
    for index, expected in enumerate(fields):
        values = struct.unpack('<8I', image.read(table + index*32, 32))
        space._require(values[6:] == expected, 'collection table read-back differs')
        rows.append(dict(index=index, count=values[6], records_va=values[7],
                         name_va=values[0], source='retail' if index < 18 else 'library',
                         name=None if index < 18 else label if index == 18 else f'{label} (2)'))
    return rows


def refresh_policy(payload):
    """Mirror verified retail purchase fields after the existing policy writer.

    No playback or purchase policy is invented: the copied first 18 headers
    follow exactly the original table, while added collections remain free.
    """
    if not space.has_music(payload):
        return payload
    base, data = storage.unwrap(payload)
    if data[:8] == LEGACY_MAGIC:
        return payload
    length = struct.unpack_from('<I', data, 8)[0]
    document = json.loads(data[12:12+length])
    updated, _ = build(document['songs'], document['collection_name'], headers=_headers(payload))
    result, _ = storage.install(base, updated)
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
        if not space.has_music(payload):
            return ('retail' if _fields(payload) == list(RETAIL) and collections.matches(payload) else 'foreign')
        space._require(jukebox_list.status(payload) == 'applied', 'unbounded collection list builder')
        _, _, fields, table = _contents(payload)
        collection_table(payload)
        return ('applied' if _fields(payload) == fields[:18]
                and collections.matches(payload, table, len(fields)) else 'foreign')
    except (ValueError, TypeError, KeyError, IndexError, struct.error, UnicodeError):
        return 'foreign'


def apply(payload, song_records, collection_name='My songs'):
    state = status(payload)
    space._require(state != 'foreign', 'mixed/foreign jukebox metadata; rebuild from base')
    data, fields = build(song_records, collection_name, headers=_headers(payload))
    if state == 'applied':
        old_songs, old_name, _, _ = _contents(payload)
        space._require(old_songs == _document(song_records) and old_name in (None, collection_label(collection_name)),
                       'different jukebox recipe; rebuild from base')
        return payload, dict(status='already_applied', changed_bytes=0)
    grown, allocation = space.apply(payload)
    grown, list_fix = jukebox_list.apply(grown)
    grown, ro = storage.install(grown, data)
    table = storage.VA + storage.PREFIX + len(data) - len(fields)*32
    grown, edits = collections.apply(grown, table, len(fields))
    buf = bytearray(grown)
    for i, values in enumerate(fields[:18]):
        va = COLLECTIONS+i*32+24
        at = _offset(buf, va, 8)
        struct.pack_into('<2I', buf, at, *values)
        edits.append(dict(label='collection_count_and_records', va=hex(va), size=8))
    for section in _sections(buf):
        buf[section.header_offset+36:section.header_offset+56] = section_digest(buf, section)
    result = bytes(buf)
    space._require(status(result) == 'applied', 'jukebox metadata postcondition failed')
    return result, dict(status='applied', experimental=True, runtime_witnessed=False,
                        count=len(song_records), collection_name=collection_name,
                        collections=collection_table(result), table_va=hex(table),
                        collection_list=list_fix,
                        collection_entry_freeze='collection-list builder bounded by nfl2k5_jukebox_list (D2); entering the collection in game is UNWITNESSED',
                        edits=edits, allocation=allocation, read_only=ro,
                        changed_bytes=sum(a != b for a,b in zip(payload,result))+len(result)-len(payload),
                        file_growth=len(result)-len(payload), identities=identities(len(song_records)))
