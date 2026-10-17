"""Historical coaches selected by physical Anniversary row, isolated from modern teams.

At 20CBE7 both historic teams have loaded into temporary slots. Clone their coach
records into two private RW records and redirect only these teams. Names follow
all 51 real games. Fifteen confirmed USA retail likenesses use separate c60..c89
archives derived from the user's retail disc. Missing likenesses retain their
placeholder body and are explicitly listed in the catalog for later art work.
No original model, texture or coach record is distributed here.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct

from . import nfl2k5_xbe_space as space
from .nfl2k5_bump_strength import _sections, section_digest
from .nfl2k5_cave_oracle import XbeImage
from .nfl2k5_draft_ai import _Asm

OWNER = 'nfl2k5_moment_coaches'
CODE_SIZE, DATA_SIZE = 512, 512
MAGIC = b'MCO1'
SIDE_SIZE = 84
NAME_BYTES = 80
REQUESTS = ((OWNER, 'code', CODE_SIZE, 16), (OWNER, 'data', DATA_SIZE, 16))
SITE = 0x20CBE7
BEFORE = bytes.fromhex('8bcde8f2aee6ff')
CATALOG = Path(__file__).resolve().parents[2] / 'data/nfl2k5_moment_coaches.json'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def rows():
    doc = json.loads(CATALOG.read_text(encoding='utf-8'))
    require(doc['schema'] == 'nfl2k5_moment_coaches/v1', 'foreign coach catalog')
    result = doc['moments']
    require([r['row'] for r in result] == list(range(1, 52)), 'coach catalog must cover physical rows 1..51')
    for row in result:
        for side in ('away', 'home'):
            person = row[side]
            require(isinstance(person['coach'], str) and person['coach'].isascii()
                    and '\0' not in person['coach'] and len(person['coach'].split()) >= 2, 'invalid coach name')
            require(person['retail_model'] is None or type(person['retail_model']) is int
                    and 0 <= person['retail_model'] <= 37, 'invalid retail coach model')
    return result


def metadata(row):
    out = bytearray(MAGIC)
    for side in ('away', 'home'):
        person = row[side]
        first, last = person['coach'].split(' ', 1)
        require(len(first) < 16 and len(last) < 24, 'coach name capacity')
        model = person['retail_model']
        out.extend(struct.pack('<HH', 0xFFFF if model is None else model+60, 0))
        out.extend((first+'\0').encode('utf-16le').ljust(32, b'\0'))
        out.extend((last+'\0').encode('utf-16le').ljust(48, b'\0'))
    return bytes(out)


def situation(raw, stats=None):
    """Rebuild SITU string pointers, putting versioned coach data after each goal's NUL.

    Retail text consumers stop at the same NUL. Only our selection hook reads the
    extension while SITU is alive. It copies names before the collection unloads.
    Scalars, visible text and sibling chunks are preserved exactly.

    b775 mo2: the moment context's stats block ("MST1") follows the coach block. ``stats`` ({physical row: block})
    replaces every row's block; without it an existing block is kept byte for byte, so this rebuild stays idempotent.
    """
    from . import nfl2k5_moment_context as moment_context
    from . import nfl2k5_espn25_scenarios as sc
    require(raw[:4] == b'SITU' and struct.unpack_from('<I', raw, 8)[0] == 51, 'expected 51 moments')
    end = 32 + struct.unpack_from('<I', raw, 4)[0]
    src = raw[32:end]
    out = bytearray(src[:sc.RECORDS + 51*sc.STRIDE])
    for i, row in enumerate(rows()):
        at = sc.RECORDS + i*sc.STRIDE
        require(sc.utf16(src, sc.rel(src, at)) == row['title']
                and sc.utf16(src, sc.rel(src, at+12)) == row['date'],
                'coach catalog does not match this physical moment')
        for field in sc.POINTERS:
            site = sc.RECORDS + i*sc.STRIDE + field
            text = sc.utf16(src, sc.rel(src, site))
            struct.pack_into('<i', out, site, len(out)-site+1)
            out.extend((text+'\0').encode('utf-16le'))
            if field == 8:
                out.extend(metadata(row))
                if stats is not None:
                    out.extend(stats.get(row['row'], b''))
                else:
                    tail = sc.rel(src, site) + 2 * len(text) + 2
                    out.extend(moment_context.trailer_after_coaches(src[tail:]))
    out.extend(bytes(-len(out)%16))
    header = bytearray(raw[:32]);struct.pack_into('<I', header, 4, len(out))
    return bytes(header+out)+raw[end:]


def code_for(va, state):
    a = _Asm(va)
    a.b('9c60' '833d80ffe50008'); a.j32('0f85', 'done')
    a.b('a15818bf00' '83f833'); a.j32('0f83', 'done')
    # ESI is the live selected SITU record. Its pointers have been relocated by
    # the retail resource loader. Scan its objective to the terminating UTF16 NUL.
    a.b('8b5608' '85d2'); a.j32('0f84', 'done')
    a.b('b900020000')  # bounded scan: never walk an arbitrary foreign string
    a.label('scan'); a.b('66833a00'); a.j8('74', 'found')
    a.b('83c20249'); a.j8('75', 'scan'); a.j32('e9', 'done')
    a.label('found'); a.b('83c202813a' + MAGIC.hex()); a.j32('0f85', 'done')
    a.b('83c204')
    # Metadata: away then home. Clone records and names into two 256-byte slots.
    for side, team_reg, dst in ((1, '89eb', state+256), (0, '89fb', state)):
        a.b('60' + team_reg + '85db'); a.j32('0f84', f'skip{side}')
        a.b('8bb34c010000' '85f6'); a.j32('0f84', f'skip{side}')
        a.b('bf' + struct.pack('<I', dst).hex() + 'b92a000000fcf3a5')
        a.b('c7834c010000' + struct.pack('<I', dst).hex())
        if side: a.b('83c254')
        a.b('0fb7026683f8ff'); a.j8('74', f'nomodel{side}')
        a.b('66a3' + struct.pack('<I', dst+0x18).hex())
        a.label(f'nomodel{side}')
        a.b('8d7204b914000000f3a5')  # EDI now dst+168; copy 80 UTF16 name bytes
        for field, target in ((0, dst+168), (4, dst+200)):
            a.b('c705' + struct.pack('<II', dst+field, target).hex())
        a.label(f'skip{side}'); a.b('61')
    a.label('done'); a.b('619d8bcd'); a.call(0x77AE0); a.jmp_abs(SITE+len(BEFORE))
    code = a.assemble()
    require(len(code) <= CODE_SIZE, 'coach code budget exceeded')
    return code.ljust(CODE_SIZE, b'\xcc')


def allocations(payload):
    found = [r for r in space.layout(payload)['allocations'] if r['owner'] == OWNER]
    if not found:
        return None
    require(len(found) == 2 and {(r['kind'], r['size']) for r in found} ==
            {('code', CODE_SIZE), ('data', DATA_SIZE)}, 'foreign coach allocation')
    return {r['kind']: r for r in found}


def hook(va):
    return (b'\xe9' + struct.pack('<i', va - SITE - 5)).ljust(len(BEFORE), b'\x90')


def status(payload):
    try:
        owned, image = allocations(payload), XbeImage(payload)
        if owned:
            c, d = owned['code']['va'], owned['data']['va']
            if image.read(SITE, len(BEFORE)) == hook(c):
                require(image.read(c, CODE_SIZE) == code_for(c, d), 'foreign coach code')
                return 'applied'
            require(image.read(c, CODE_SIZE) == b'\xcc' * CODE_SIZE, 'foreign coach padding')
        require(image.read(SITE, len(BEFORE)) == BEFORE, 'foreign coach hook')
        return 'retail'
    except (ValueError, KeyError, struct.error):
        return 'foreign'


def seal(buf):
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


def underlying(payload):
    """Recognized view for the moment owner's selection-handler guard."""
    require(status(payload) != 'foreign', 'foreign moment coaches')
    if status(payload) == 'retail':
        return payload
    out = bytearray(payload); off = XbeImage(payload).offset(SITE, len(BEFORE))
    out[off:off + len(BEFORE)] = BEFORE
    return seal(out)


def apply(payload):
    initial = status(payload)
    require(initial != 'foreign', 'foreign moment coach installation')
    if initial == 'applied':
        return payload, dict(status='already_applied', changed_bytes=0)
    before = payload
    if allocations(payload) is None:
        payload, _ = space.extend_scaleout(payload, REQUESTS)
    owned = allocations(payload)
    c, d = owned['code']['va'], owned['data']['va']
    payload, _ = space.install_code(payload, OWNER, code_for(c, d))
    out = bytearray(payload); off = XbeImage(payload).offset(SITE, len(BEFORE))
    out[off:off + len(BEFORE)] = hook(c)
    result = seal(out)
    require(status(result) == 'applied' and space.status(result) == 'applied', 'coach installation readback')
    require(len(result) == len(before), 'coach XBE grew')
    return result, dict(status='applied', changed_bytes=sum(a != b for a, b in zip(before, result)),
                        code_va=c, data_va=d, moments=51, names=102)


def retail_resources(source):
    """Pin original archives using the modern-coach compiler's existing retail pins."""
    from . import nfl2k5_roster_records as rr, nfl2k5_modern_coaches as modern
    from .nfl2k5_espn25_more_moments import name_id
    pins = json.loads(modern.PINS_PATH.read_text(encoding='utf-8'))['teams']
    by_archive = {p['archive']: p for p in pins}
    models = sorted({r[s]['retail_model'] for r in rows() for s in ('away', 'home')} - {None})
    out = {}
    with rr._outer_image()(source) as archive:
        entries = {e.name_id: e for e in archive.entries}
        for model in models:
            name = f'c{model:02d}.iff'; p = by_archive[name]
            entry = entries[name_id(name)]; raw = archive.read(entry.virtual_offset, entry.size)
            span = raw[p['span_offset']:p['span_offset'] + p['span_size']]
            require(hashlib.sha256(span).hexdigest() == p['retail_sha256'],
                    name + ': historical likeness requires the original retail disc')
            out[f'c{model + 60:02d}.iff'] = raw
    return out


def resource_plan(target, source):
    """Append preserved retail models through the same archive writer as period fields."""
    from . import nfl2k5_anniversary_pack as pack
    from .nfl2k5_music_archive import Disc, align_up
    from .nfl2k5_espn25_more_moments import name_id
    resources = retail_resources(source)
    with Disc(target, descriptors=()) as disc:
        by_id = {e.name_id: e for e in disc.archive_entries}
        situ_entry = disc.archive_entries[22]
        old_situ = disc.read_entry_range(situ_entry, 0, situ_entry.size)
        # b775 mo2: the moment stats ride in the same SITU write; their roster slots come from this disc's team files.
        from . import nfl2k5_moment_context as moment_context
        stat_blocks, stat_receipts = moment_context.stat_blocks(disc)
        new_situ = situation(old_situ, stats=stat_blocks)
        present = [name_id(n) in by_id for n in resources]
        if any(present):
            require(new_situ == old_situ, 'foreign historical coach SITU extension')
            require(all(present), 'mixed historical coach resources')
            for name, raw in resources.items():
                e = by_id[name_id(name)]
                require(e.size == len(raw) and disc.read_entry_range(e, 0, e.size) == raw,
                        name + ': foreign historical coach resource')
            return [], dict(status='already_applied', resources=len(resources), bytes_written=0,
                            moment_stats=stat_receipts)
        p0, pf = disc.pack_extents['0'], disc.pack_extents['F']
        old0, oldf = disc.read(p0.size, p0.byte_offset), disc.read(pf.size, pf.byte_offset)
        # A distinct final alignment member keeps the outer archive's last-entry invariant.
        marker = b'Historical coach resources; generated by 2K5 Mod Studio.\n'
        resources['mo1_coach_alignment.bin'] = (marker * 40)[:2048].ljust(2048, b'\0')
        new0, newf, detail = pack.update_packs(old0, oldf, resources, situation=new_situ)
        at0 = align_up(disc.image_size); atf = align_up(at0 + len(new0))
        writes = [(at0, new0), (atf, newf)]
        for key, at, raw in (('0', at0, new0), ('F', atf, newf)):
            writes.append((disc.nodes[key][0], struct.pack('<II', (at-disc.partition)//2048, len(raw))))
        return writes, dict(status='applied', resources=len(resources)-1, moment_stats=stat_receipts,
                            image_growth=atf+len(newf)-disc.image_size, archive=detail)


def image_plan(target, source):
    from .nfl2k5_music_archive import Disc
    writes, receipt = resource_plan(target, source)
    with Disc(target, descriptors=()) as disc:
        e = disc.entries['default.xbe']
        before = disc.read(e.size, e.byte_offset)
        after, xbe = apply(before)
        # Only differing contiguous XBE runs are owned, not the whole file.
        i = 0
        while i < len(before):
            if before[i] == after[i]:
                i += 1; continue
            start = i
            while i < len(before) and before[i] != after[i]:
                i += 1
            writes.append((e.byte_offset + start, after[start:i]))
    receipt['xbe'] = xbe
    receipt['writes'] = [dict(offset=at, size=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                         for at,raw in writes]
    return sorted(writes), receipt


def apply_to_image(target, source):
    from .nfl2k5_music_archive import write_all
    from . import platform_compat as io
    writes, receipt = image_plan(target, source)
    oldsize = Path(target).stat().st_size
    with Path(target).open('r+b') as f:
        before = [(at, io.pread(f.fileno(), min(len(raw), max(0, oldsize-at)), at)) for at,raw in writes]
        try:
            for at, raw in writes:
                write_all(f.fileno(), raw, at)
                require(io.pread(f.fileno(), len(raw), at) == raw, 'coach image readback')
            os.fsync(f.fileno())
        except BaseException:
            for at, raw in before:
                if raw:
                    write_all(f.fileno(), raw, at)
            f.truncate(oldsize); os.fsync(f.fileno()); raise
    replay, _ = image_plan(target, source)
    require(not replay, 'coach image replay must be empty')
    receipt['bytes_written'] = sum(len(raw) for _,raw in writes)
    return receipt
