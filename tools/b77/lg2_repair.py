#!/usr/bin/env python3
"""Hash-pinned lg2 repair: XBE offline proof, disc plan, fixed-span disc write and full scope compare.

xbe INPUT OUTPUT --receipt JSON
prepare --disc INPUT --plan JSON --receipt JSON   (read only, no disc copy)
disc --disc COPY --plan JSON --receipt JSON       (in place, only declared spans)
scope --before INPUT --after COPY --plan JSON --receipt JSON

A prepare receipt is a virtual overlay proof, explicitly not a physical disc write.
The disc writer accepts only the full input/output hashes pinned by prepare.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_letter_grades as lg
from mod_editor.core import nfl2k5_letter_grades_attributes as attributes
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

BASE_DISC = '520429148f57c29a23f56b5f43c5fe04be39728d01a101210aad8336b60581a4'
FIXED_DISC = 'bc0425f148661de31c18b04acad8adbdb7f6ffd0eb730978f947f7950455ce32'
BASE_XBE = '1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f'
# Derived from the pinned v0.6.1 executable by the Studio owner, checked in tests.
FIXED_XBE = 'e7d96e0ea6eea3a7efed370ab2c8416add80eb52a5b91ee500ab5c335b346e3f'
BLOCK = 8 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError('lg2 repair refused: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def read_at(fd, offset, size):
    os.lseek(fd, offset, os.SEEK_SET)
    data = bytearray()
    while len(data) < size:
        part = os.read(fd, size - len(data))
        require(bool(part), 'short read')
        data.extend(part)
    return bytes(data)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def scopes(payload):
    rows = [(rdata.offset_of(payload, va), len(old), label)
            for label, va, old, _ in attributes.sites(payload)]
    rows += [(space.SCALE_DIRECTORY, space.PAGE, 'allocator directory'),
             (space.DIRECTORY, space.LIB_COPY - space.DIRECTORY, 'allocator header seal')]
    rows += [(s.header + 36, 20, s.name + ' SHA-1') for s in XbeImage(payload).sections]
    rows.sort()
    require(all(a + n <= b for (a, n, _), (b, _, _) in zip(rows, rows[1:])), 'overlapping scopes')
    return rows


def compare_xbe(before, after):
    require(len(before) == len(after), 'XBE length changed')
    restored = bytearray(after)
    for start, size, _ in scopes(before):
        restored[start:start + size] = before[start:start + size]
    require(restored == before, 'XBE bytes outside declared spans changed')
    return dict(changed_bytes=sum(a != b for a, b in zip(before, after)),
                outside_scope_changed_bytes=0, file_size=len(after),
                before_sha256=sha(before), after_sha256=sha(after),
                allocations_identical=space.layout(before)['allocations'] == space.layout(after)['allocations'])


def repair_xbe(before):
    require(sha(before) in (BASE_XBE, FIXED_XBE), 'unknown XBE hash ' + sha(before))
    after, _ = attributes.apply(before)
    require(sha(after) == FIXED_XBE, 'unexpected fixed XBE hash')
    studio, _ = lg.apply(before)
    require(studio == after, 'Studio/native mismatch')
    again, replay = attributes.apply(after)
    require(again == after and replay['changed_bytes'] == 0, 'replay changed bytes')
    return after, dict(compare_xbe(before, after), studio_output_identical=True, replay_changed_bytes=0)


def patch_rows(before, after, base=0):
    return [dict(offset=base + start, size=size, label=label,
                 before=before[start:start + size].hex(), after=after[start:start + size].hex())
            for start, size, label in scopes(before)
            if before[start:start + size] != after[start:start + size]]


def overlay(block, offset, rows):
    result = bytearray(block)
    for row in rows:
        a, b = max(offset, row['offset']), min(offset + len(block), row['offset'] + row['size'])
        if a < b:
            old, new = bytes.fromhex(row['before']), bytes.fromhex(row['after'])
            start, length = a - row['offset'], b - a
            require(block[a-offset:b-offset] == old[start:start+length], 'plan/input span mismatch')
            result[a-offset:b-offset] = new[start:start+length]
    return bytes(result)


def stream_compare(before, rows, after=None):
    """Read every byte. With no after file, compare against a virtual fixed-span overlay."""
    hb, ha = hashlib.sha256(), hashlib.sha256()
    changed, total = 0, 0
    out = Path(after).open('rb') if after is not None else None
    try:
        with Path(before).open('rb') as f:
            for block in iter(lambda: f.read(BLOCK), b''):
                expected = overlay(block, total, rows)
                actual = out.read(len(block)) if out else expected
                require(actual == expected, 'disc bytes differ from declared overlay')
                hb.update(block); ha.update(actual)
                if block != actual:
                    changed += sum(a != b for a, b in zip(block, actual))
                total += len(block)
        require(out is None or not out.read(1), 'disc size changed')
    finally:
        if out:
            out.close()
    return dict(before_sha256=hb.hexdigest(), after_sha256=ha.hexdigest(),
                compared_bytes=total, changed_bytes=changed, outside_scope_changed_bytes=0,
                physical_disc_compare=after is not None)


def validate_plan(plan):
    require(plan.get('schema') == 'b773.lg2.disc-plan.v1', 'foreign plan')
    require(plan['before_sha256'] == BASE_DISC and plan['after_sha256'] == FIXED_DISC
            and plan['xbe_before_sha256'] == BASE_XBE
            and plan['xbe_after_sha256'] == FIXED_XBE, 'unknown plan source/result')
    rows = plan['spans']
    require(rows == sorted(rows, key=lambda r:r['offset']), 'unsorted plan')
    require(all(r['size'] == len(bytes.fromhex(r['before'])) == len(bytes.fromhex(r['after']))
                and 0 <= r['offset'] < r['offset'] + r['size'] <= plan['disc_size'] for r in rows), 'invalid spans')
    require(all(a['offset'] + a['size'] <= b['offset'] for a,b in zip(rows,rows[1:])), 'overlapping plan spans')


def write_spans(path, rows, expected_before, expected_after):
    require(not Path(path).is_symlink(), 'symlink target')
    fd = os.open(path, os.O_RDWR | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    try:
        before = file_hash(path)
        require(before in (expected_before, expected_after), 'unknown target hash ' + before)
        if before == expected_after:
            return dict(write_bytes=0, changed_bytes=0, after_sha256=before, replay=True)
        for r in rows:
            require(read_at(fd, r['offset'], r['size']) == bytes.fromhex(r['before']), 'prewrite span mismatch')
        for r in rows:
            os.lseek(fd, r['offset'], os.SEEK_SET)
            data = memoryview(bytes.fromhex(r['after']))
            while data:
                n = os.write(fd, data)
                require(n > 0, 'short write')
                data = data[n:]
        os.fsync(fd)
        after = file_hash(path)
        require(after == expected_after, 'postwrite hash mismatch')
        return dict(write_bytes=sum(r['size'] for r in rows),
                    changed_bytes=sum(sum(a != b for a,b in zip(bytes.fromhex(r['before']),bytes.fromhex(r['after']))) for r in rows),
                    before_sha256=before, after_sha256=after, replay=False)
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    x = sub.add_parser('xbe'); x.add_argument('source', type=Path); x.add_argument('output', type=Path)
    q = sub.add_parser('prepare'); q.add_argument('--disc', type=Path, required=True); q.add_argument('--plan', type=Path, required=True)
    d = sub.add_parser('disc'); d.add_argument('--disc', type=Path, required=True); d.add_argument('--plan', type=Path, required=True)
    s = sub.add_parser('scope'); s.add_argument('--before', type=Path, required=True); s.add_argument('--after', type=Path, required=True); s.add_argument('--plan', type=Path, required=True)
    for sp in (x,q,d,s): sp.add_argument('--receipt', type=Path, required=True)
    args = p.parse_args()
    require(not args.receipt.exists(), 'receipt exists')
    if args.command == 'xbe':
        require(not args.output.exists() and not args.output.is_symlink(), 'output exists')
        before = args.source.read_bytes(); after, receipt = repair_xbe(before)
        rows = patch_rows(before, after)
        with args.output.open('xb') as out: out.write(before)
        receipt['write'] = write_spans(args.output, rows, sha(before), sha(after))
        receipt['replay'] = write_spans(args.output, rows, sha(before), sha(after))
        receipt['scope'] = compare_xbe(before, args.output.read_bytes())
    elif args.command == 'prepare':
        require(not args.plan.exists(), 'plan exists')
        from mod_editor.core.nfl2k5_throw_tuning import image_xbe_extent
        fd = os.open(args.disc, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
        try:
            size = os.fstat(fd).st_size
            offset, length = image_xbe_extent(fd, size)
            before = read_at(fd, offset, length)
        finally: os.close(fd)
        after, xreceipt = repair_xbe(before)
        rows = patch_rows(before, after, offset)
        receipt = stream_compare(args.disc, rows)
        require(receipt['before_sha256'] == BASE_DISC, 'unknown base disc hash')
        plan = dict(schema='b773.lg2.disc-plan.v1', disc_size=size, xbe_offset=offset,
                    xbe_before_sha256=sha(before), xbe_after_sha256=sha(after), spans=rows,
                    before_sha256=receipt['before_sha256'], after_sha256=receipt['after_sha256'])
        validate_plan(plan); write_json(args.plan, plan)
        receipt.update(xbe_proof=xreceipt, physical_disc_write=False)
    else:
        plan = json.loads(args.plan.read_text(encoding='utf-8')); validate_plan(plan)
        if args.command == 'disc':
            # Regenerate the expected spans from the pinned XBE so an edited plan cannot add writes.
            fd = os.open(args.disc, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
            try:
                from mod_editor.core.nfl2k5_throw_tuning import image_xbe_extent
                offset, length = image_xbe_extent(fd, os.fstat(fd).st_size)
                require(offset == plan['xbe_offset'], 'plan/default.xbe extent mismatch')
                current = read_at(fd, offset, length)
            finally: os.close(fd)
            if sha(current) == FIXED_XBE:
                original = bytearray(current)
                for row in plan['spans']:
                    at = row['offset'] - plan['xbe_offset']
                    require(0 <= at and at + row['size'] <= len(original), 'span outside executable')
                    original[at:at+row['size']] = bytes.fromhex(row['before'])
                current = bytes(original)
            fixed, _ = repair_xbe(current)
            require(plan['spans'] == patch_rows(current, fixed, plan['xbe_offset']), 'plan differs from Studio spans')
            receipt = write_spans(args.disc, plan['spans'], plan['before_sha256'], plan['after_sha256'])
            receipt['replay'] = write_spans(args.disc, plan['spans'], plan['before_sha256'], plan['after_sha256'])
        else:
            receipt = stream_compare(args.before, plan['spans'], args.after)
            require(receipt['before_sha256'] == plan['before_sha256'] and receipt['after_sha256'] == plan['after_sha256'], 'scope hash mismatch')
    write_json(args.receipt, receipt)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
