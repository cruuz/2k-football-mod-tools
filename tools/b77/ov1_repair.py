#!/usr/bin/env python3
"""ov1: pinned, fixed-span Tampa Bay duplicate-shield cleanup.

--pin --audit --disc BASE --receipts DIR compiles the recipe and pins its two native
spans. --audit runs the Studio writer on a small extracted pack fixture and
streams the complete read-only base with the planned replacements. It never
copies or writes the disc. Without --audit/--pin, --disc must be a disposable
copy: the exact base or the exact pinned output. Unknown inputs are refused
before a writable descriptor is opened. No retail or logo pixels are shipped.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import numpy as np
from mod_editor.core import nfl2k5_bump_texture_writer as bump
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes
from tools.b77 import uf3_repair as transport

BASE_SHA256 = transport.BASE_SHA256
DISC_SIZE = transport.DISC_SIZE
BOXES = {"27H0": [155, 82, 169, 89], "27A0": [157, 82, 168, 89]}


def require(ok, message):
    if not ok:
        raise ValueError("ov1: " + message)


def write_json(path, document):
    transport.write_json(path, document)


def pin(disc):
    require(disc.stat().st_size == DISC_SIZE, "unexpected disc size")
    require(transport.file_sha(disc) == BASE_SHA256, "pin requires the exact base disc")
    rows = []
    with bump._Image.open(disc, writable=False) as im:
        ix = bump._parsed_index(im)
        by = {bump.logical_name_for(e.name_id): e for e in ix.entries}
        for sel, box in sorted(BOXES.items()):
            e = by[sel + ".IFF"]
            raw = im.read_segments(ix.sub_extents(e, 0, e.size))
            c = fixes._chunk_for(raw, 1)
            span = raw[c.offset:c.end_offset]
            cloth = "#B21C35" if sel == "27H0" else "#FFFFFF"
            x0, y0, x1, y1 = box
            row = dict(selector=sel, chunk=1, texture="jersey00", kind="tset", size=[512, 256, 6],
                       resource_size=len(raw), offset=c.offset, length=len(span),
                       defects=["ov1-TB-duplicate-shield"],
                       note="Exclude the old shield fragment embedded in the chest wordmark; preserve the collar shield and letters.",
                       ops=[dict(op="poly", color=cloth, points=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]])])
            out, _ = fixes.compile_texture(span, row)
            row.update(before_sha256=fixes.sha(span), after_sha256=fixes.sha(out))
            rows.append(row)
    doc = dict(schema=fixes.SCHEMA, source="ov1: TB wordmark raster carries an old shield fragment below the separately placed collar shield",
               method="Atlas exclusion of the duplicate fragment, flat source cloth restored; no new art, fixed spans and mud twins",
               base_disc_sha256=BASE_SHA256, textures=rows)
    write_json(fixes.DATA_OV1, doc)
    return doc


def compact_fixture(directory, raws):
    """Two real kit packages in a tiny native extracted pack set, not a disc copy."""
    payload = bytearray()
    entries = []
    for sel, raw in sorted(raws.items()):
        entries.append((transport.native.name_id(sel + ".IFF"), len(raw), 1 + len(payload)//2048))
        payload.extend(raw)
        payload.extend(bytes((-len(payload)) % 2048))
    table = bytearray(2048)
    struct.pack_into("<III", table, 0, len(entries), 0, 2)
    struct.pack_into("<II", table, 12, 1, len(payload)//2048)
    for i, entry in enumerate(entries):
        struct.pack_into("<III", table, bump.INDEX_HEADER_SIZE + i*12, *entry)
    (directory / "0").write_bytes(table)
    (directory / "1").write_bytes(payload)


def compile_plans(raws, doc):
    out, receipts = {}, []
    for sel, raw in sorted(raws.items()):
        parts, receipt = fixes.compile_resource(sel, raw, document=doc)
        buf = bytearray(raw)
        for at, data in parts:
            buf[at:at+len(data)] = data
        out[sel] = bytes(buf)
        receipts.append(receipt)
    return out, receipts


def full_scope(disc, ranges, before, after, *, virtual):
    """Stream all bytes; count differences outside owned spans and hash the
    reconstructed base. In audit mode the after stream is an explicit overlay.
    In apply mode every after byte comes from the written disc."""
    h_before, h_after = hashlib.sha256(), hashlib.sha256()
    changed, outside, total = 0, 0, 0
    pieces, pos = [], 0
    for row in ranges:
        n = row['end'] - row['start']
        pieces.append((row['start'], row['end'], before[pos:pos+n], after[pos:pos+n]))
        pos += n
    with os.fdopen(transport.binary(disc, os.O_RDONLY), 'rb') as stream:
        while block := stream.read(4*1024*1024):
            old, new = bytearray(block), bytearray(block)
            owned = np.zeros(len(block), bool)
            end = total + len(block)
            for start, stop, b, a in pieces:
                lo, hi = max(total, start), min(end, stop)
                if lo >= hi:
                    continue
                owned[lo-total:hi-total] = True
                old[lo-total:hi-total] = b[lo-start:hi-start]
                if virtual:
                    new[lo-total:hi-total] = a[lo-start:hi-start]
            diff = np.frombuffer(old, np.uint8) != np.frombuffer(new, np.uint8)
            changed += int(diff.sum())
            outside += int((diff & ~owned).sum())
            h_before.update(old);h_after.update(new);total = end
    require(total == DISC_SIZE and h_before.hexdigest() == BASE_SHA256, "full-scope reconstructed base differs")
    require(outside == 0, "bytes changed outside owned spans")
    return dict(mode="virtual_after_stream" if virtual else "written_disc", compared_bytes=total,
                changed_bytes=changed, changed_bytes_outside_spans=outside,
                reconstructed_base_sha256=h_before.hexdigest(), output_sha256=h_after.hexdigest())


def run(disc, receipts, audit=False, pin_recipe=False):
    require(not disc.is_symlink(), "disc is a symlink")
    require(disc.stat().st_size == DISC_SIZE, "unexpected disc size")
    if pin_recipe:
        doc = pin(disc)
    else:
        doc = fixes.overlaps()
    digest = transport.file_sha(disc)
    require(digest in {BASE_SHA256, doc.get("output_disc_sha256")}, "unknown whole-disc hash")
    require(not audit or digest == BASE_SHA256, "audit requires the base disc")
    donors = {}
    raws, ranges, extents = transport.read_resources(disc, doc, donors)
    require(not transport.alias_check(ranges, extents), "another archive entry aliases an owned span")
    require(not any(r['selector'].startswith('26') or r['chunk'] != 1 for r in ranges), "unexpected ownership")
    compiled, plans = compile_plans(raws, doc)
    before = b''.join(raws[r['selector']][r['resource_offset']:r['resource_offset']+r['end']-r['start']] for r in ranges)
    after = b''.join(compiled[r['selector']][r['resource_offset']:r['resource_offset']+r['end']-r['start']] for r in ranges)
    receipts.mkdir(parents=True, exist_ok=True)
    # Execute the actual Studio image writer against real native kit bytes.
    with tempfile.TemporaryDirectory(prefix='ov1-packs-', dir=receipts) as tmp:
        fixture = Path(tmp)
        compact_fixture(fixture, raws)
        original = (fixture/'1').read_bytes()
        wrote = fixes.apply_overlaps(fixture, strict=True)
        fixed = (fixture/'1').read_bytes()
        replay = fixes.apply_overlaps(fixture, strict=True)
        require(replay['written_bytes'] == replay['changed_bytes'] == 0, "fixture replay changed bytes")
        equal = []
        with bump._Image.open(fixture, writable=False) as im:
            ix = bump._parsed_index(im)
            for e in ix.entries:
                sel = bump.logical_name_for(e.name_id)[:-4]
                actual = im.read_segments(ix.sub_extents(e,0,e.size))
                require(actual == compiled[sel], "Studio writer differs from native compile")
                equal.append(sel)
        # Scope every byte of the compact archive, including package padding.
        owned = np.zeros(len(original), bool)
        at = 0
        for sel, raw in sorted(raws.items()):
            for row in doc['textures']:
                if row['selector'] == sel:
                    owned[at+row['offset']:at+row['offset']+row['length']] = True
            at += (len(raw)+2047)//2048*2048
        diff = np.frombuffer(original,np.uint8) != np.frombuffer(fixed,np.uint8)
        require(not (diff & ~owned).any(), "compact fixture changed bytes outside spans")
        fixture_scope = dict(compared_bytes=len(original), changed_bytes=int(diff.sum()), changed_bytes_outside_spans=int((diff&~owned).sum()))
    write_json(receipts/'studio_write.json', wrote)
    write_json(receipts/'studio_replay.json', replay)
    write_json(receipts/'studio_scope.json', fixture_scope)
    write_json(receipts/'studio_equality.json', dict(equal=True, selectors=equal, compiler='nfl2k5_kit_fixes_2026.compile_resource', writer='apply_overlaps(strict=True)'))
    disc_written_bytes = 0
    if not audit and before != after:
        # Whole-disc identity and every plan were checked before this open.
        with os.fdopen(transport.binary(disc, os.O_RDWR), 'r+b') as stream:
            pos = 0
            for r in ranges:
                n = r['end']-r['start']
                if before[pos:pos+n] != after[pos:pos+n]:
                    stream.seek(r['start'])
                    stream.write(after[pos:pos+n])
                    disc_written_bytes += n
                pos += n
            stream.flush();os.fsync(stream.fileno())
        require(transport.read_spans(disc,ranges) == after, "disc read-back differs")
    # Replay on an already fixed disc needs the original spans to reconstruct
    # the base; normal repeat proves exact pinned output and a no-op instead.
    if digest != BASE_SHA256:
        require(before == after, "pinned output was not a no-op")
        scope = dict(mode='pinned_output_replay', compared_bytes=DISC_SIZE, output_sha256=digest, changed_bytes=0)
    else:
        scope = full_scope(disc,ranges,before,after,virtual=audit)
    if pin_recipe:
        doc['output_disc_sha256'] = scope['output_sha256']
        write_json(fixes.DATA_OV1,doc)
    else:
        require(scope['output_sha256'] == doc['output_disc_sha256'], "whole-disc output differs from its pin")
    write_json(receipts/'disc_scope.json',scope)
    write_json(receipts/'ranges.json',ranges)
    summary = dict(mode='audit_no_disc_write' if audit else 'disc_write', disc_written=bool(disc_written_bytes),
                   disc_written_bytes=disc_written_bytes,
                   fixture_written_bytes=wrote['written_bytes'], fixture_changed_bytes=wrote['changed_bytes'],
                   fixture_replay_bytes=replay['written_bytes'], studio_equal=True,
                   disc_stream_compared_bytes=scope['compared_bytes'],
                   planned_changed_bytes=sum(p['changed_bytes'] for p in plans),
                   alias_count=0, seattle_spans=0, pants_spans=0)
    write_json(receipts/'summary.json',summary)
    print(json.dumps(summary,sort_keys=True))
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disc',type=Path,required=True);p.add_argument('--receipts',type=Path,required=True)
    p.add_argument('--audit',action='store_true');p.add_argument('--pin',action='store_true')
    a = p.parse_args()
    try:
        require(not a.pin or a.audit, '--pin requires --audit')
        run(a.disc,a.receipts,a.audit,a.pin)
    except (ValueError,OSError) as exc:
        p.exit(2,str(exc)+'\n')


if __name__ == '__main__':
    main()
