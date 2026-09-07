"""Small invented codec fixtures, never historically accurate player content."""
from pathlib import Path
import json
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_espn25_scenarios as e
from mod_editor.core import nfl2k5_roster_records as rr

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')


def fixtures():
    def pointer(body, at, target):
        struct.pack_into('<i', body, at, target - at + 1)
    def wrapper(kind, body, count=None):
        return kind + struct.pack('<II', len(body), len(body) if count is None else count) + bytes(20) + bytes(body)
    body = bytearray(8192)
    body[12:16] = b'ROST'
    struct.pack_into('<I', body, 16, 17)
    pointer(body, 20, 64)
    for pool, (count_at, table_at) in rr.POOL_FIELDS.items():
        struct.pack_into('<I', body, count_at, 53 if pool == 'primary' else 0)
        pointer(body, table_at, 972 if pool == 'primary' else 256)
    struct.pack_into('<I', body, rr.TEAM_COUNT_FIELD, 1)
    pointer(body, rr.TEAM_TABLE_FIELD, 472)
    body[472 + rr.TEAM_PLAYER_COUNT] = 53
    cursor = 5500
    for i in range(53):
        at = 972 + i * rr.PLAYER_SIZE
        pointer(body, 472 + i * 4, at)
        body[at + 0x36:at + 0x52] = bytes([50] * 28)
        for field, name in ((16, f'First{i:02}'), (20, f'Last{i:02}')):
            raw = name.encode('utf-16le') + b'\0\0'
            pointer(body, at + field, cursor)
            body[cursor:cursor + len(raw)] = raw
            cursor += len(raw)
    historic = wrapper(b'ROST', body)
    doc = rr.RosterDocument(body)
    resources, manifest, descriptors = {}, {'rosters': {}}, []
    main = bytearray(8192)
    main[12:16] = b'ROST'
    pointer(main, 20, 64)
    struct.pack_into('<I', main, 0x98, 75)
    pointer(main, 0x9c, 0x100)
    cursor = 0x600
    for i in range(75):
        selector, year, code, outer = f'team{i:02}', 1950 + i, f'{i:02}', 113 + i
        at = 0x100 + i * 16
        struct.pack_into('<H', main, at, year)
        main[at + 4:at + 8] = code.encode('utf-16le')
        pointer(main, at + 12, cursor)
        raw = selector.encode('utf-16le') + b'\0\0'
        main[cursor:cursor + len(raw)] = raw
        cursor += len(raw)
        filename = f'h-{code}-{year}-{selector}-0.iff'
        identity = zlib.crc32(filename.upper().encode('utf-16le')) & 0xffffffff
        descriptors.append(dict(index=i, selector=selector, year=year, kit=0, code=code, filename=filename, id=identity, outer=outer))
        resources[outer] = (identity, historic)
        pin = {'id': identity, 'size': len(historic), 'primary_table': doc.primary_table, 'names': [doc.names.start, doc.names.end]}
        pin['guard_sha256'] = e.masked_sha(historic, e.roster_mask(historic, pin))
        manifest['rosters'][str(outer)] = pin
    main = wrapper(b'ROST', main)
    resources[5] = (10, main)
    manifest['main'] = {'id': 10, 'size': len(main), 'header': main[:32].hex(), 'table': 0x100,
                        'descriptor_sha256': e.sha(json.dumps(descriptors, sort_keys=True).encode())}
    situ = bytearray(29104)
    situ[12:16] = b'SITU'
    pointer(situ, 20, 64)
    struct.pack_into('<I', situ, 64, 25)
    strings, cursor = [], 0xad0
    for i in range(25):
        at = e.RECORDS + i * e.STRIDE
        for offset in e.POINTERS:
            value = f'Test moment {i} field {offset}' if offset < 16 else 'team00'
            raw = value.encode('utf-16le') + b'\0\0'
            pointer(situ, at + offset, cursor)
            situ[cursor:cursor + len(raw)] = raw
            strings.append([cursor, 64])
            cursor += 64
        struct.pack_into('<II', situ, at + 28, 1950, 1950)
        struct.pack_into('<f', situ, at + 0x44, 10)
    situ = wrapper(b'SITU', situ, 25) + b'UNRELATED SIBLING RESOURCE'
    resources[22] = (20, situ)
    pin = {'id': 20, 'size': len(situ), 'strings': strings, 'conditions': [bytes(12).hex()]}
    pin['guard_sha256'] = e.masked_sha(situ, e.situ_mask(situ, pin))
    manifest['situ'] = pin
    return e.Catalog(resources, manifest)


def draft(catalog, append=5):
    source = catalog.moment(0)
    return {'schema': e.DRAFT_SCHEMA, 'append': [
        {'template': 0, 'text': {'title': f'Authored test {i}', 'description': 'Test description',
                                'objective': 'Test objective', 'date': 'Test date'},
         'teams': source['teams'], 'setup': source['setup']} for i in range(append)]}
