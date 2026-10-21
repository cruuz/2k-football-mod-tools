#!/usr/bin/env python3
"""Fixed-span native yard-number repair, using the Studio's own scene writer.

prepare makes a virtual overlay, proves every changed field with the retail
XBE, and records full-stream scope, replay, and Studio byte equality. apply
refuses unknown full-disc hashes and writes only the frozen field spans.
Historical fields and turf bytes are outside the decoded edit scope.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_modern_metlife as mm
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b77.fa1_repair import bundle_payloads, sheet
from tools.b77.fd1_repair import BASE_SHA, file_sha, input_state, overlay_hash, require, save, sha

SCHEMA = 'b773_fn1_repair/v1'
PINS = Path(__file__).with_name('fn1_pins.json')
PREFIXES = ('s06', 's11', 's15', 's28')


def resource_names():
    return [p + t + w + '.iff' for p in PREFIXES for t in 'dan' for w in 'drs']


def studio_numbers(bundle, name):
    """The exact Studio scene span with a numbers-only plan, preserving all other decoded bytes."""
    chunk, rec, decoded, payloads = bundle_payloads(bundle, ('numbers',))
    index = mv.rows_by_material(rec)['numbers']
    item, = mv.default_numbers(name[:3])
    item = dict(item, dd=dict(scene='field', index=index))
    plan = dict(items=[item])
    base = {('field', index): mv.read_texture(decoded, rec, mv.p8_rows(rec)[index])}
    span, detail = mv.modern_scene_span(bundle, chunk, name[:3], name[3:5], plan, base)
    after = bundle[:chunk.offset] + span + bundle[chunk.end_offset:]
    _c, _r, back, actual = bundle_payloads(after, ('numbers',))
    lo, hi, _old_payload, _size = payloads['numbers']
    require(back[:lo] == decoded[:lo] and back[hi:] == decoded[hi:],
            'Studio changed decoded bytes outside numbers')
    require(span[:32] == bundle[chunk.offset:chunk.body_offset], 'field wrapper changed')
    require(len(after) == len(bundle), 'bundle allocation changed')
    return after, dict(scope_offset=chunk.offset, scope_size=len(span),
                       decoded_range=[lo, hi], studio_palette_cap=detail['palette_cap'],
                       decoded_numbers_only=True, studio_span_exact=True,
                       numbers_payload_sha256=sha(actual['numbers'][2]))


def prepare(base, retail, output):
    from mod_editor.core import nfl2k5_espn25_rosters as rosters
    from tools.b765.s2_native_decoder import prove_chunk
    require(file_sha(base) == BASE_SHA, 'unrecognized base disc hash')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sheets').mkdir(exist_ok=True)
    xbe = output / 'retail_decoder.xbe'
    xbe.write_bytes(rosters.read_xbe(retail))
    spans, receipts = [], []
    try:
        with mm._outer_image()(base) as archive:
            byid = {e.name_id: e for e in archive.entries}
            for name in resource_names():
                entry = byid[mv.name_id(name)]
                before = archive.read(entry.virtual_offset, entry.size)
                after, detail = studio_numbers(before, name)
                offset, size = detail['scope_offset'], detail['scope_size']
                require(before[:offset] == after[:offset] and before[offset+size:] == after[offset+size:],
                        'bytes outside field span changed')
                chunk = mm.bundle_scenes(after)['field']
                native = prove_chunk(after, chunk, xbe, instruction_limit=40_000_000)
                replay, _ = studio_numbers(after, name)
                # Fitting an identical decoded scene is deterministic, including candidate guard order.
                require(replay == after, 'Studio replay changes bytes')
                at = archive.image_offset(entry.virtual_offset + offset)
                require(archive.image_offset(entry.virtual_offset + offset + size - 1) == at+size-1,
                        'field span crosses pack seam')
                payload = after[offset:offset+size]
                filename = name + '.field'
                (output / filename).write_bytes(payload)
                spans.append(dict(name=name, file=filename, offset=at, size=size,
                                  before_sha256=sha(before[offset:offset+size]), after_sha256=sha(payload)))
                changed = sum(a != b for a, b in zip(before, after))
                receipts.append(dict(name=name, changed_bytes=changed, replay_changed_bytes=0,
                                     native_decoder=native, **detail))
                if name[3:5] == 'dd':
                    sheet(output/'sheets'/f'{name}.png', name+' | native numbers atlas', before, after, ('numbers',))
                print(json.dumps(dict(name=name, changed_bytes=changed, native_decoder_exact=True,
                                      studio_span_exact=True, decoded_numbers_only=True)), flush=True)
        spans.sort(key=lambda r: r['offset'])
        payloads = [(output / r['file']).read_bytes() for r in spans]
        proof = overlay_hash(base, spans, payloads)
        doc = dict(schema=SCHEMA, before_sha256=BASE_SHA, after_sha256=proof['after_sha256'],
                   disc_size=base.stat().st_size, spans=spans)
        if PINS.exists():
            require(doc == json.loads(PINS.read_text()), 'prepared output differs from frozen fn1 pins')
        require(input_state(proof['after_sha256'], doc) == 'already_applied', 'virtual replay state differs')
        save(output/'plan.json', doc)
        save(output/'prepare_receipt.json', dict(bundles=receipts, scope=proof,
             write=dict(mode='virtual overlay only; no disc copy made', spans=len(spans), bytes=sum(r['size'] for r in spans)),
             replay=dict(mode='virtual overlay; production input-state check', state='already_applied', bytes_written=0)))
        print(json.dumps(dict(prepared=len(spans), **proof)), flush=True)
    finally:
        xbe.unlink(missing_ok=True)


def load_plan(path):
    doc = json.loads(path.read_text())
    require(PINS.is_file() and doc == json.loads(PINS.read_text()), 'plan differs from frozen fn1 pins')
    require(doc['schema'] == SCHEMA and doc['before_sha256'] == BASE_SHA, 'foreign plan')
    require({r['name'] for r in doc['spans']} == set(resource_names()), 'foreign resource set')
    payloads = []; end = 0
    for span in doc['spans']:
        require(span['offset'] >= end and span['size'] > 0, 'overlapping spans')
        end = span['offset'] + span['size']; require(end <= doc['disc_size'], 'span outside disc')
        p = (path.parent / span['file']).resolve(); require(p.is_relative_to(path.parent.resolve()), 'payload path escapes plan')
        payload = p.read_bytes()
        require(len(payload) == span['size'] and sha(payload) == span['after_sha256'], 'payload pin mismatch')
        payloads.append(payload)
    return doc, payloads


def apply(disc, plan, receipt):
    doc, payloads = load_plan(plan); digest = file_sha(disc)
    require(disc.stat().st_size == doc['disc_size'], 'disc size differs')
    if input_state(digest, doc) == 'already_applied':
        save(receipt, dict(already_applied=True, bytes_written=0, sha256=digest)); return
    proof = overlay_hash(disc, doc['spans'], payloads)
    require(proof['after_sha256'] == doc['after_sha256'], 'plan output hash differs')
    fd = os.open(disc, os.O_RDWR | getattr(os, 'O_BINARY', 0)); written = 0
    try:
        for span, payload in zip(doc['spans'], payloads):
            os.lseek(fd, span['offset'], os.SEEK_SET)
            count = os.write(fd, payload); require(count == len(payload), 'short write'); written += count
        os.fsync(fd)
    finally:
        os.close(fd)
    require(file_sha(disc) == doc['after_sha256'], 'disc read-back hash differs')
    save(receipt, dict(bytes_written=written, sha256=doc['after_sha256'], readback_exact=True, scope=proof))


def scope(before, after, plan, receipt):
    import numpy as np
    doc, _payloads = load_plan(plan)
    require(file_sha(before) == doc['before_sha256'] and file_sha(after) == doc['after_sha256'], 'foreign compare hashes')
    require(before.stat().st_size == after.stat().st_size == doc['disc_size'], 'scope size differs')
    changed = outside = 0; at = 0
    with open(before, 'rb') as b, open(after, 'rb') as a:
        while x := b.read(4 * 1024 * 1024):
            y = a.read(len(x)); require(len(y) == len(x), 'short scope read')
            if x != y:
                mask = np.frombuffer(x, dtype='uint8') != np.frombuffer(y, dtype='uint8')
                changed += int(mask.sum())
                for span in doc['spans']:
                    lo = max(0, span['offset'] - at); hi = min(len(x), span['offset'] + span['size'] - at)
                    if hi > lo:
                        mask[lo:hi] = False
                outside += int(mask.sum())
            at += len(x)
    require(outside == 0, 'bytes changed outside owned spans')
    save(receipt, dict(compared_bytes=at, changed_bytes=changed, changed_bytes_outside_spans=outside))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0]); sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('prepare'); s.add_argument('--base', type=Path, required=True)
    s.add_argument('--retail', type=Path, required=True); s.add_argument('--output', type=Path, required=True)
    s = sub.add_parser('apply'); s.add_argument('--disc', type=Path, required=True)
    s.add_argument('--plan', type=Path, required=True); s.add_argument('--receipt', type=Path, required=True)
    s = sub.add_parser('scope'); s.add_argument('--before', type=Path, required=True); s.add_argument('--after', type=Path, required=True)
    s.add_argument('--plan', type=Path, required=True); s.add_argument('--receipt', type=Path, required=True)
    a = vars(p.parse_args()); command = a.pop('command'); globals()[command](**a)
