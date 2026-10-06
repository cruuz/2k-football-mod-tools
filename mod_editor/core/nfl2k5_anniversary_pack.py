"""Bounded Anniversary archive updates; existing game files survive byte for byte.

The two touched archive files are pack 0 (directory/SITU) and pack F (appended
Anniversary resources). Directory growth follows the existing virtual sector
model. This does not change the main roster, modern stadiums, or other packs.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct

from . import nfl2k5_espn25_more_moments as mm
from . import nfl2k5_resource_growth as growth
from . import nfl2k5_music_archive as archive

HEADER = 156
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def entries(pack0):
    count = struct.unpack_from('<I', pack0)[0]
    mm.require(0 < count < 100000 and HEADER + count * 12 <= len(pack0), 'foreign archive directory')
    return [struct.unpack_from('<III', pack0, HEADER + i * 12) for i in range(count)]


def extend_situation(original, data, main):
    """Append the 51st physical row, preserving all previous scalar values/texts."""
    count = struct.unpack_from('<I', original, 8)[0]
    mm.require(count == 50 and len(data.moments) == 26, 'expected v0.4 fifty-row collection')
    first_end = 32 + struct.unpack_from('<I', original, 4)[0]
    source = original[32:first_end]
    body = bytearray(source[:mm.sc.RECORDS + count * mm.sc.STRIDE])
    rows = [{p: mm.sc.utf16(source, mm.sc.rel(source, mm.sc.RECORDS + i * mm.sc.STRIDE + p))
             for p in mm.sc.POINTERS} for i in range(count)]
    record, texts = mm.compile_records(data, main)[-1]
    body.extend(record)
    rows.append(texts)
    struct.pack_into('<I', body, 64, 51)
    for i, row in enumerate(rows):
        for p in mm.sc.POINTERS:
            at = mm.sc.RECORDS + i * mm.sc.STRIDE + p
            struct.pack_into('<i', body, at, len(body) - at + 1)
            body.extend(mm.sc.text_bytes(row[p]))
    body.extend(bytes(-len(body) % 16))
    wrapper = bytearray(original[:32])
    struct.pack_into('<II', wrapper, 4, len(body), 51)
    return bytes(wrapper + body) + original[first_end:]


def update_packs(pack0, pack_f, additions, *, situation=None):
    """Pure file-set transform, preserving unrelated payloads across relocations.

    Existing additions must match exactly. A missing or mixed addition set is
    refused. Receipts describe exact outside-scope copy ranges and hashes.
    """
    before0, before_f = bytes(pack0), bytes(pack_f)
    rows = entries(pack0)
    sizes = list(struct.unpack_from('<16I', pack0, 12))
    mm.require(sizes[0] * 2048 == len(pack0) and sizes[15] * 2048 == len(pack_f), 'pack size mismatch')
    ids = {r[0]: i for i, r in enumerate(rows)}
    desired = [(name, bytes(raw), mm.name_id(name)) for name, raw in additions.items()]
    mm.require(len({r[2] for r in desired}) == len(desired), 'duplicate new resource hash')
    present = [identity in ids for _, _, identity in desired]
    if any(present):
        mm.require(all(present), 'mixed Anniversary append state')
        f_start = sum(sizes[:15]) * 2048
        for name, raw, identity in desired:
            _, size, sector = rows[ids[identity]]
            at = sector * 2048 - f_start
            mm.require(0 <= at <= len(pack_f) - size and pack_f[at:at + size] == raw,
                       'foreign existing Anniversary resource: ' + name)
        if situation is not None:
            _, size, sector = rows[mm.SITU_OUTER]
            mm.require(pack0[sector * 2048:sector * 2048 + size] == situation, 'foreign installed SITU')
        return before0, before_f, {'status': 'already_applied', 'changed_bytes': 0}

    # Add directory sectors only when the known slack cannot hold the new rows.
    first = rows[0][2] * 2048
    required = HEADER + 12 * (len(rows) + len(desired))
    directory_growth = max(0, (required - first + 2047) // 2048) * 2048
    source0 = bytearray(pack0)
    if directory_growth:
        source0[first:first] = bytes(directory_growth)
        sizes[0] += directory_growth // 2048
        struct.pack_into('<I', source0, 12, sizes[0])
        rows = [(identity, size, sector + directory_growth // 2048) for identity, size, sector in rows]
        for i, row in enumerate(rows):
            struct.pack_into('<III', source0, HEADER + 12 * i, *row)
    copied = []
    situ_scope = None
    if situation is not None:
        plan = growth.plan_pack0(lambda n, at: bytes(source0[at:at+n]), len(source0),
                                mm.SITU_OUTER, mm.SITU_ID, situation, padding_bytes=(0, 0x9f))
        rebuilt = (plan.table + bytes(source0[len(plan.table):plan.start]) + plan.replacement
                   + bytes([plan.padding_byte]) * (archive.align_up(len(plan.replacement)) - len(plan.replacement))
                   + bytes(source0[plan.old_end:]))
        situ_scope = [plan.start, archive.align_up(plan.start + len(situation))]
        pack0 = bytearray(rebuilt)
        rows = entries(pack0)
        sizes[0] = len(pack0) // 2048
    else:
        pack0 = source0
    new_f = bytearray(pack_f)
    f_start = sum(sizes[:15]) * 2048
    appended = []
    for name, raw, identity in desired:
        mm.require(identity not in ids, 'duplicate Anniversary identity')
        at = archive.align_up(len(new_f))
        new_f.extend(bytes(at-len(new_f)))
        new_f.extend(raw)
        rows.append((identity, len(raw), (f_start + at)//2048))
        appended.append({'name': name, 'pack_f_offset': at, 'size': len(raw), 'sha256': sha(raw)})
    mm.require(len(new_f) % 2048 == 0, 'final appended resource must be sector padded')
    struct.pack_into('<I', pack0, 0, len(rows))
    struct.pack_into('<I', pack0, 12 + 15 * 4, len(new_f)//2048)
    for i, row in enumerate(rows):
        struct.pack_into('<III', pack0, HEADER + 12 * i, *row)
    # Check continuous byte spans, including unreferenced padding. Only the
    # directory and the sector allocation of SITU may differ in pack 0.
    old_table_end = HEADER + 12 * len(old_rows := entries(before0))
    new_table_end = HEADER + 12 * len(rows)
    mm.require(pack0[4:12] == before0[4:12] and pack0[16:72] == before0[16:72]
               and pack0[76:HEADER] == before0[76:HEADER], 'unowned archive header changed')
    gap_start = max(old_table_end, new_table_end)
    if not directory_growth and gap_start < first:
        copied.append({'before': [gap_start, first], 'after': [gap_start, first]})
    old_situ = old_rows[mm.SITU_OUTER]
    old_start = old_situ[2] * 2048
    old_end = archive.align_up(old_start + old_situ[1])
    if situation is not None:
        copied.extend([{'before': [first, old_start], 'after': [first + directory_growth, old_start + directory_growth]},
                       {'before': [old_end, len(before0)], 'after': [situ_scope[1], len(pack0)]}])
    else:
        copied.append({'before': [first, len(before0)], 'after': [first + directory_growth, len(pack0)]})
    for span in copied:
        lo, hi = span['before']; after_lo, after_hi = span['after']
        mm.require(before0[lo:hi] == pack0[after_lo:after_hi], 'outside-scope pack 0 bytes changed')
        span['sha256'] = sha(before0[lo:hi])
    # Check every pre-existing resource other than the owned SITU against its source.
    for i, (identity, size, sector) in enumerate(old_rows):
        after_id, after_size, after_sector = rows[i]
        mm.require(identity == after_id and (i == mm.SITU_OUTER or size == after_size), 'existing outer identity changed')
        if sector*2048 + size <= len(before0) and i != mm.SITU_OUTER:
            mm.require(before0[sector*2048:sector*2048+size] == pack0[after_sector*2048:after_sector*2048+size],
                       'unrelated pack-0 payload changed')
    mm.require(new_f[:len(before_f)] == before_f, 'existing pack F changed')
    return bytes(pack0), bytes(new_f), dict(status='applied', directory_growth=directory_growth,
        scope='pack-0 directory, SITU collection and alignment; append-only pack F',
        pack0_before_sha256=sha(before0), pack0_after_sha256=sha(pack0),
        pack_f_before_sha256=sha(before_f), pack_f_after_sha256=sha(new_f),
        old_pack_f_preserved_bytes=len(before_f), pack0_copy_ranges=copied,
        pack0_owned_after_ranges=[[0, 4], [12, 16], [72, 76], [HEADER, new_table_end]]
                                 + ([situ_scope] if situ_scope else []),
        untouched_pack0_resources_verified=sum(r[2]*2048+r[1] <= len(before0) for i,r in enumerate(old_rows) if i != mm.SITU_OUTER),
        appended=appended, count_before=len(old_rows), count_after=len(rows))


def append_to_image(path, resources, *, situation=None):
    """Append prepared assets to the builder's output image, with rollback."""
    from . import platform_compat as io
    with archive.Disc(Path(path), descriptors=()) as disc:
        p0, pf = disc.pack_extents['0'], disc.pack_extents['F']
        raw0, raw_f = disc.read(p0.size, p0.byte_offset), disc.read(pf.size, pf.byte_offset)
        resources = dict(resources)
        # A private transport member gives the directory a sector-aligned last entry without altering a bundle.
        marker = b"Anniversary resource alignment; generated by 2K5 Mod Studio.\n"
        resources['a1_archive_alignment.bin'] = (marker * (2048//len(marker)+1))[:2048]
        out0, out_f, receipt = update_packs(raw0, raw_f, resources, situation=situation)
        if receipt['status'] == 'already_applied':
            return receipt
        old_size = disc.image_size
        at0 = archive.align_up(old_size)
        at_f = archive.align_up(at0 + len(out0))
        nodes = [(disc.nodes['0'][0], struct.pack('<II', p0.sector, p0.size)),
                 (disc.nodes['F'][0], struct.pack('<II', pf.sector, pf.size))]
        with Path(path).open('r+b') as f:
            fd = f.fileno()
            try:
                for at, raw in ((at0, out0), (at_f, out_f)):
                    archive.write_all(fd, raw, at)
                    mm.require(io.pread(fd, len(raw), at) == raw, 'Anniversary pack readback')
                archive.write_all(fd, struct.pack('<II', (at0-disc.partition)//2048, len(out0)), nodes[0][0])
                archive.write_all(fd, struct.pack('<II', (at_f-disc.partition)//2048, len(out_f)), nodes[1][0])
                os.fsync(fd)
            except BaseException:
                for at, raw in nodes:
                    archive.write_all(fd, raw, at)
                os.ftruncate(fd, old_size)
                os.fsync(fd)
                raise
    receipt['image_growth'] = at_f + len(out_f) - old_size
    return receipt


def apply_fields_to_image(path, retail_source, *, progress=None):
    """Compile period aliases from the completed build and append them to it."""
    from . import nfl2k5_espn25_fields as fields
    from . import nfl2k5_historic_styles as styles
    with styles.Source(path) as built, styles.Source(retail_source) as retail:
        situ, situ_receipt = fields.repair_situ(built.get(identity=mm.SITU_ID))
        resources, art_receipt = fields.compile_assets(built.get, retail.get, situ, progress=progress)
    receipt = append_to_image(path, resources, situation=situ)
    receipt.update(fields=art_receipt, situation=situ_receipt, situation_after_sha256=sha(situ))
    return receipt


def verify_fields_on_image(path, receipt):
    """Check every installed alias and SITU after the builder's final relocation."""
    from . import nfl2k5_historic_styles as styles
    assets = receipt['fields']['assets']
    mm.require(len(assets) == 51 and len({row['alias'] for row in assets}) == 51,
               'incomplete Anniversary field receipt')
    with styles.Source(path) as built:
        mm.require(sha(built.get(identity=mm.SITU_ID)) == receipt['situation_after_sha256'],
                   'Anniversary SITU changed after field compilation')
        for row in assets:
            raw = built.get(row['alias'])
            mm.require(len(raw) == row['size'] and sha(raw) == row['after'],
                       'Anniversary field changed after compilation: ' + row['alias'])
    return dict(status='applied', assets_verified=51, situation_verified=True)
