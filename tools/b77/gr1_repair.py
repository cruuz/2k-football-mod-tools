#!/usr/bin/env python3
"""Fixed-span grass-only repair, using the Studio's final palette writer.

prepare verifies the pinned base, all decoded scopes and the native decoder;
apply writes only the frozen scene spans and refuses unknown full-disc hashes;
scope compares every disc byte. Payloads contain the user's own game bytes and
are private build products, never shipped source.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_broadcast_greens as greens
from mod_editor.core import nfl2k5_modern_surfaces as ms
from mod_editor.core import nfl2k5_modern_metlife as ml
from tools.b77.fd1_repair import BASE_SHA, file_sha, overlay_hash, input_state, require, save, sha

SCHEMA = 'b773_gr1_repair/v1'
PINS = Path(__file__).with_name('gr1_pins.json')


def worker(job):
    name, family, original, xbe = job
    from tools.b765.s2_native_decoder import prove_chunk
    after, receipt = greens.bundle_transform(original, name, family)
    tx = ml._tools()[0]
    native = []
    for edit in receipt['edits']:
        old = next(c for c in tx.parse_chunks(original, allow_trailing=True) if c.offset == edit['offset'])
        new = next(c for c in tx.parse_chunks(after, allow_trailing=True) if c.offset == edit['offset'])
        before_dec = tx.decode_chunk(original, old)[0]
        after_dec = tx.decode_chunk(after, new)[0]
        restored = bytearray(after_dec)
        for lo, hi in edit['decoded_ranges']:
            restored[lo:hi] = before_dec[lo:hi]
        require(restored == before_dec, name + ': outside grass RGB changed')
        if new.compressed:
            native.append(dict(scene=edit['scene'], **prove_chunk(after, new, xbe, instruction_limit=40_000_000)))
    # The source builder uses exactly this function and final placement.
    receipt.update(studio_bundle_exact=True, native_decoder=native)
    payloads = [(e, after[e['offset']:e['offset'] + e['size']]) for e in receipt['edits']]
    return name, receipt, payloads


def prepare(base, retail, output, workers=4, sample=False):
    require(1 <= workers <= 4, 'workers must be 1..4')
    require(file_sha(base) == BASE_SHA, 'unrecognized base disc hash')
    output.mkdir(parents=True, exist_ok=True)
    cache = output / 'cache'; cache.mkdir(exist_ok=True)
    from mod_editor.core import nfl2k5_espn25_rosters as rosters
    xbe = output / 'decoder.xbe'; xbe.write_bytes(rosters.read_xbe(retail))
    spans, receipts = [], []
    priority = ['a06dd.iff', 's18nd.iff', 's26dd.iff', 's13dd.iff', 's18dr.iff', 's32dd.iff', 's18ad.iff', 's18ds.iff', 's02dd.iff']
    try:
        with ms._outer_image()(str(base)) as archive, ProcessPoolExecutor(max_workers=workers) as pool:
            entries = greens.entries(archive); families = greens.families(archive)
            names = priority if sample else priority + sorted(set(entries) - set(priority))
            futures = {}
            for name in names:
                e = entries[name]; original = archive.read(e.virtual_offset, e.size)
                record = cache / (name + '.json')
                if record.exists():
                    cached = json.loads(record.read_text())
                    require(cached['before'] == sha(original) and cached['revision'] == greens.REVISION
                            and cached['source_sha256'] == sha((ROOT / 'mod_editor/core/nfl2k5_broadcast_greens.py').read_bytes()),
                            'stale preparation cache: ' + name)
                    receipts.append(cached['receipt']); spans.extend(cached['spans'])
                    print('CACHED ' + name, flush=True); continue
                futures[pool.submit(worker, (name, families[name[:3]], original, str(xbe)))] = name
            for future in as_completed(futures):
                name, receipt, payloads = future.result(); e = entries[name]
                resource_spans = []
                for edit, payload in payloads:
                    virtual = e.virtual_offset + edit['offset']; at = archive.image_offset(virtual)
                    require(archive.image_offset(virtual + len(payload) - 1) == at + len(payload) - 1,
                            'scene crosses archive pack seam')
                    old = archive.read(virtual, len(payload)); filename = name + '.' + edit['scene'] + '.span'
                    (output / filename).write_bytes(payload)
                    resource_spans.append(dict(name=name, scene=edit['scene'], file=filename, offset=at,
                                               size=len(payload), before_sha256=sha(old), after_sha256=sha(payload)))
                save(cache / (name + '.json'), dict(before=receipt['before'], revision=greens.REVISION,
                     source_sha256=sha((ROOT / 'mod_editor/core/nfl2k5_broadcast_greens.py').read_bytes()),
                     receipt=receipt, spans=resource_spans))
                receipts.append(receipt); spans.extend(resource_spans)
                print(json.dumps(dict(name=name, scenes=len(payloads), non_grass_bytes_changed=0,
                                      native_decoder_exact=True, studio_equal=True)), flush=True)
        spans.sort(key=lambda r: r['offset']); payloads = [(output / r['file']).read_bytes() for r in spans]
        scope = overlay_hash(base, spans, payloads)
        plan = dict(schema=SCHEMA, before_sha256=BASE_SHA, after_sha256=scope['after_sha256'],
                    disc_size=base.stat().st_size, spans=spans, revision=greens.REVISION)
        if not sample and PINS.exists():
            require(plan == json.loads(PINS.read_text()), 'output differs from frozen gr1 pins')
        save(output / ('sample_plan.json' if sample else 'plan.json'), plan)
        save(output / ('sample_receipt.json' if sample else 'prepare_receipt.json'),
             dict(bundles=receipts, scope=scope, all_528_bundles=not sample,
                  non_grass_bytes_changed=0, studio_bundle_exact=True,
                  replay=dict(mode='virtual overlay full-hash input check', bytes_written=0,
                              state=input_state(scope['after_sha256'], plan))))
        print(json.dumps(dict(prepared_bundles=len(receipts), spans=len(spans), **scope)), flush=True)
    finally:
        xbe.unlink(missing_ok=True)


def load_plan(path):
    doc = json.loads(path.read_text())
    require(PINS.is_file() and doc == json.loads(PINS.read_text()), 'plan differs from frozen gr1 pins')
    require(doc['schema'] == SCHEMA and doc['before_sha256'] == BASE_SHA, 'foreign plan')
    payloads = []; end = 0
    for span in doc['spans']:
        require(span['offset'] >= end and span['size'] > 0, 'overlapping spans')
        end = span['offset'] + span['size']; require(end <= doc['disc_size'], 'span outside disc')
        p = (path.parent / span['file']).resolve()
        require(p.is_relative_to(path.parent.resolve()), 'payload path escapes plan')
        payload = p.read_bytes()
        require(len(payload) == span['size'] and sha(payload) == span['after_sha256'], 'payload pin mismatch')
        payloads.append(payload)
    return doc, payloads


def apply(disc, plan, receipt):
    doc, payloads = load_plan(plan); digest = file_sha(disc)
    require(disc.stat().st_size == doc['disc_size'], 'disc size differs')
    if input_state(digest, doc) == 'already_applied':
        save(receipt, dict(already_applied=True, bytes_written=0, sha256=digest))
        print('REPLAY bytes_written=0'); return
    proof = overlay_hash(disc, doc['spans'], payloads)
    require(proof['after_sha256'] == doc['after_sha256'], 'output hash differs')
    fd = os.open(disc, os.O_RDWR | getattr(os, 'O_BINARY', 0)); written = 0
    try:
        for span, payload in zip(doc['spans'], payloads):
            os.lseek(fd, span['offset'], os.SEEK_SET)
            count = os.write(fd, payload); require(count == len(payload), 'short write'); written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    require(file_sha(disc) == doc['after_sha256'], 'disc readback hash differs')
    save(receipt, dict(bytes_written=written, sha256=doc['after_sha256'], readback_exact=True, scope=proof))
    print('APPLIED spans=' + str(len(doc['spans'])) + ' bytes_written=' + str(written) + ' readback_exact=true')


def scope(before, after, plan, receipt):
    import numpy as np
    doc, _ = load_plan(plan)
    require(file_sha(before) == doc['before_sha256'] and file_sha(after) == doc['after_sha256'], 'foreign compare hashes')
    require(before.stat().st_size == after.stat().st_size == doc['disc_size'], 'scope size differs')
    changed = outside = at = 0
    with open(before, 'rb') as b, open(after, 'rb') as a:
        while x := b.read(4 * 1024 * 1024):
            y = a.read(len(x)); require(len(y) == len(x), 'short scope read')
            if x != y:
                mask = np.frombuffer(x, np.uint8) != np.frombuffer(y, np.uint8); changed += int(mask.sum())
                for span in doc['spans']:
                    lo = max(0, span['offset'] - at); hi = min(len(x), span['offset'] + span['size'] - at)
                    if hi > lo:
                        mask[lo:hi] = False
                outside += int(mask.sum())
            at += len(x)
    require(outside == 0, 'bytes changed outside owned scene spans')
    save(receipt, dict(compared_bytes=at, changed_bytes=changed, changed_bytes_outside_spans=outside))
    print('SCOPE compared_bytes=' + str(at) + ' changed_bytes=' + str(changed) + ' outside_spans=' + str(outside))


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('prepare'); s.add_argument('--base', type=Path, required=True)
    s.add_argument('--retail', type=Path, required=True); s.add_argument('--output', type=Path, required=True)
    s.add_argument('--workers', type=int, default=4); s.add_argument('--sample', action='store_true')
    s = sub.add_parser('apply'); s.add_argument('--disc', type=Path, required=True)
    s.add_argument('--plan', type=Path, required=True); s.add_argument('--receipt', type=Path, required=True)
    s = sub.add_parser('scope'); s.add_argument('--before', type=Path, required=True)
    s.add_argument('--after', type=Path, required=True); s.add_argument('--plan', type=Path, required=True)
    s.add_argument('--receipt', type=Path, required=True)
    a = vars(p.parse_args()); command = a.pop('command'); globals()[command](**a)


if __name__ == '__main__':
    main()
