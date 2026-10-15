#!/usr/bin/env python3
"""Fixed-span fa1 field-art repair, compiled by the Studio writers.

prepare reads the recognized base disc and the user's retail source and emits
bounded resource-prefix payloads plus an auditable plan for:

* the Anniversary period fields of fd1 (rows 7, 8, 10, 13, 37, 49) and the
  Raiders rows 2 and 5, with their end zones compiled by
  ``nfl2k5_espn25_fields._field`` (row 10 and the Raiders rows now carry the
  authored period lettering);
* the nine MetLife field variants, whose midfield helmet is painted by
  ``nfl2k5_modern_metlife.paint_scene`` at the base build's palette cap.

Only the owned textures' decoded pixels, mips and palettes change; each field
is refit into its own allocation (or a lossless loan from a later scene, as in
fd1). apply writes those fixed spans to an authorized copy; it refuses foreign
full-disc hashes and replays with zero writes. scope compares every byte of a
before/after disc pair. prepare also verifies the complete virtual output
stream without creating a disc copy.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_modern_metlife as mm
from mod_editor.core import nfl2k5_modern_venues_2026 as mv
from tools.b77.fd1_repair import BASE_SHA, file_sha, input_state, overlay_hash, require, save, sha

ROWS = (2, 5, 7, 8, 10, 13, 37, 49)
METLIFE = tuple(f's18{t}{w}.iff' for t in 'dan' for w in 'drs')
#: Every base MetLife field holds the helmet exactly as paint_scene wrote it at this cap.
METLIFE_CAP = 128
ENDZONES = tuple(f'endzone_{end}_{part}' for end in 'NS' for part in 'LMR')
SCHEMA = 'b773_fa1_repair/v1'
PINS = Path(__file__).with_name('fa1_pins.json')


def row_name(number):
    return f"a{number - 1:02d}{fields.catalog()[number - 1]['variant']}.iff"


def resource_names():
    return [row_name(n) for n in ROWS] + list(METLIFE)


def texture_payloads(rec, decoded, keys):
    rows = mv.p8_rows(rec); materials = mv.rows_by_material(rec); result = {}
    for key in keys:
        r = rows[materials[key]]
        lo = rec['system_bytes'] + r['pixel_offset']; hi = rec['system_bytes'] + r['palette_offset'] + 1024
        result[key] = (lo, hi, bytes(decoded[lo:hi]), (r['width'], r['height'], r['mip_levels']))
    return result


def bundle_payloads(bundle, keys):
    chunk, rec, decoded = fields._field_chunk(bundle)
    return chunk, rec, decoded, texture_payloads(rec, decoded, keys)


def fit(original, chunk, edited):
    """(after bundle, scope, fit, loan): ``edited`` refit into the field's allocation, losslessly."""
    import nfl_vc_lz_fill as fill
    tx = mm._tools()[0]; oldspan = original[chunk.offset:chunk.end_offset]
    _declared, tag = struct.unpack_from('<II', oldspan, 32)
    modes = [('greedy', bits) for bits in dict.fromkeys((oldspan[40], 10, 9, 8, 11))]
    last_greedy = modes[-1][1]; candidates = []; attempts = []
    for encoder, bits in modes:
        try:
            if encoder == 'greedy':
                encoded, _ = tx.compress_vc_lz(bytes(edited), stream_tag=tag, offset_bits=bits)
            else:
                encoded = fill.compress_optimal(bytes(edited), stream_tag=tag, offset_bits=bits)
            candidates.append((encoded, encoder, bits))
            if encoder == 'greedy' and bits == last_greedy:
                best_bits = min(candidates, key=lambda x: len(x[0]))[2]
                modes.extend(('optimal', width) for width in dict.fromkeys((best_bits, 10)))
            if len(encoded) > chunk.stored_size:
                continue
            filled = fill.fill_stream(encoded, bytes(edited), chunk.stored_size, slack=0)[0]
            alias = tx.minimum_vc_lz_overlap_scratch(filled, chunk.stored_size, len(edited))
            if len(filled) != chunk.stored_size or alias > chunk.overlap_scratch_bytes:
                continue
            if chunk.overlap_scratch_bytes == 0 and len(fill.parse_tokens(filled)[3]) % 8 == 0:
                continue
            span = oldspan[:32] + filled
            require(span[:32] == oldspan[:32], 'chunk wrapper changed')
            return (original[:chunk.offset] + span + original[chunk.end_offset:], chunk.end_offset,
                    dict(encoder=encoder, offset_bits=bits, stored_size=chunk.stored_size, encoded_size=len(encoded),
                         alias_scratch=alias, scratch_bytes=chunk.overlap_scratch_bytes), None)
        except ValueError as exc:
            attempts.append(str(exc))
    # The field needs a little more compressed storage: losslessly repack the
    # largest later scene. Decoded neighbours and scratch allocations stay identical.
    neighbours = tx.parse_chunks(original, allow_trailing=True)
    donor = max((c for c in neighbours if c.offset > chunk.offset and c.compressed and c.kind == 'SCNE'),
                key=lambda c: c.stored_size)
    donor_decoded, _ = tx.decode_chunk(original, donor)
    donor_old = original[donor.offset:donor.end_offset]
    donor_tag = struct.unpack_from('<I', donor_old, 36)[0]
    donor_enc = fill.compress_optimal(donor_decoded, stream_tag=donor_tag, offset_bits=donor_old[40])
    encoded, encoder, bits = min(candidates, key=lambda x: len(x[0]))
    minimum = ((max(16, len(encoded) - chunk.stored_size) + 15) // 16) * 16
    for amount in range(minimum, donor.stored_size - len(donor_enc) + 1, 16):
        field_size = chunk.stored_size + amount; donor_size = donor.stored_size - amount
        try:
            field_body = fill.fill_stream(encoded, bytes(edited), field_size, slack=0)[0]
            donor_body = fill.fill_stream(donor_enc, donor_decoded, donor_size, slack=0)[0]
            alias = tx.minimum_vc_lz_overlap_scratch(field_body, field_size, len(edited))
            donor_alias = tx.minimum_vc_lz_overlap_scratch(donor_body, donor_size, len(donor_decoded))
            if alias > chunk.overlap_scratch_bytes or donor_alias > donor.overlap_scratch_bytes:
                continue
            if chunk.overlap_scratch_bytes == 0 and len(fill.parse_tokens(field_body)[3]) % 8 == 0:
                continue
            fh = bytearray(oldspan[:32]); dh = bytearray(donor_old[:32])
            struct.pack_into('<I', fh, 4, field_size); struct.pack_into('<I', dh, 4, donor_size)
            after = (original[:chunk.offset] + fh + field_body + original[chunk.end_offset:donor.offset]
                     + dh + donor_body + original[donor.end_offset:])
        except ValueError:
            continue
        new_chunks = tx.parse_chunks(after, allow_trailing=True)
        require(len(new_chunks) == len(neighbours), 'chunk count changed')
        for old, new in zip(neighbours, new_chunks):
            if old.index != chunk.index:
                require(tx.decode_chunk(original, old)[0] == tx.decode_chunk(after, new)[0],
                        'non-field decoded chunk changed')
        loan = dict(bytes=amount, donor_chunk_index=donor.index, donor_decoded_identical=True,
                    donor_encoded_size=len(donor_enc), donor_stored_size=donor_size,
                    donor_alias_scratch=donor_alias, donor_scratch_bytes=donor.overlap_scratch_bytes)
        return after, donor.end_offset, dict(encoder=encoder, offset_bits=bits, stored_size=field_size,
                                             encoded_size=len(encoded), alias_scratch=alias,
                                             scratch_bytes=chunk.overlap_scratch_bytes), loan
    raise ValueError('No lossless fixed prefix encoding fits: ' + str(dict(
        candidates=[(mode, width, len(data)) for data, mode, width in candidates],
        field_stored=chunk.stored_size, donor_saved=donor.stored_size - len(donor_enc), errors=attempts)))


def repair_bundle(original, expected):
    """Transplant the Studio's texture payloads ``{key: (data, (w, h, mips))}`` into ``original`` and refit."""
    chunk, rec, decoded, current = bundle_payloads(original, tuple(expected))
    edited = bytearray(decoded); ranges = []
    for key, (lo, hi, _old, size) in current.items():
        data, newsize = expected[key]
        require(size == newsize and hi - lo == len(data), 'texture allocation differs: ' + key)
        edited[lo:hi] = data; ranges.append((lo, hi))
    protected = bytearray(edited)
    for lo, hi in ranges:
        protected[lo:hi] = decoded[lo:hi]
    require(protected == decoded, 'decoded bytes outside the owned textures changed')
    if edited == decoded:
        return original, dict(scope_size=0, changed_bytes=0)
    after, scope, fitted, loan = fit(original, chunk, edited)
    require(len(after) == len(original) and after[scope:] == original[scope:], 'outside fixed prefix changed')
    _c, _r, back, actual = bundle_payloads(after, tuple(expected))
    require(back == edited, 'decoded field differs after fitting')
    require(all(actual[k][2] == expected[k][0] for k in expected), 'Studio texture bytes differ')
    return after, dict(scope_size=scope, changed_bytes=sum(a != b for a, b in zip(original, after)),
                       decoded_owned_textures_only=True, studio_native_payload_exact=True, fit=fitted,
                       allocation_loan=loan, decoded_ranges=ranges,
                       texture_payload_sha256={k: sha(v[2]) for k, v in actual.items()},
                       outside_prefix_identical=True)


def anniversary_payloads(source, number):
    row = fields.catalog()[number - 1]
    words = {e['team']: fields._wordmark(source.get(fields.WORDMARKS[e['team']] + 'dd.iff'), e['team'])
             for e in row['endzones']}
    compiled, _ = fields._field(source.get('s25' + row['variant'] + '.iff'), row, words)
    _c, _r, _d, payloads = bundle_payloads(compiled, ENDZONES)
    return {k: (v[2], v[3]) for k, v in payloads.items()}, ENDZONES


def metlife_payloads(source, name):
    venue, _tod, weather = mm.variant_parts(name)
    retail = source.get(name); dry = mm.dry_reference(source.get(mm.dry_name(name)))
    _c, rec, decoded = fields._field_chunk(retail)
    edited, receipt = mm.paint_scene(decoded, rec, venue, weather, dry.get('field'), palette_cap=METLIFE_CAP)
    require(any(p['material'] == 'center_logo' for p in receipt['patches'] + receipt['overlays']),
            'the MetLife painter did not write the midfield helmet')
    payloads = texture_payloads(rec, edited, ('center_logo',))
    return {k: (v[2], v[3]) for k, v in payloads.items()}, ('center_logo',)


def sheet(path, title, before, after, keys):
    """Before (top) and after (bottom) of the owned textures, as decoded from the two bundles."""
    from PIL import Image, ImageDraw
    import numpy as np

    def strip(bundle):
        _c, r, d = fields._field_chunk(bundle); rows = mv.p8_rows(r); materials = mv.rows_by_material(r)
        if keys == ENDZONES:
            return [np.concatenate([mv.read_texture(d, r, rows[materials[f'endzone_{end}_{p}']]) for p in 'LMR'], 1)
                    for end in 'NS']
        return [mv.read_texture(d, r, rows[materials[k]]) for k in keys]

    images = [[Image.fromarray(a).convert('RGBA') for a in strip(b)] for b in (before, after)]
    pad = 24; w = sum(im.width for im in images[0]) + pad * (len(images[0]) + 1)
    h = max(im.height for im in images[0]); out = Image.new('RGBA', (w, 2 * h + 4 * pad), (34, 68, 48, 255))
    d = ImageDraw.Draw(out)
    for row, (label, ims) in enumerate(zip(('before', 'after'), images)):
        y = pad + row * (h + 2 * pad); d.text((pad, y - 18), f'{title} | {label}', fill=(255, 255, 255, 255))
        x = pad
        for im in ims:
            out.alpha_composite(im, (x, y)); x += im.width + pad
    out.convert('RGB').save(path)


def prepare(base, retail, output):
    require(file_sha(base) == BASE_SHA, 'unrecognized base disc hash')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sheets').mkdir(exist_ok=True)
    spans = []; receipts = []; tx = mm._tools()[0]
    from mod_editor.core.nfl2k5_historic_styles import Source
    from mod_editor.core import nfl2k5_espn25_rosters as rosters
    from tools.b765.s2_native_decoder import prove_chunk
    xbe = output / 'retail_decoder.xbe'; xbe.write_bytes(rosters.read_xbe(retail))
    try:
        with mm._outer_image()(base) as archive, Source(retail) as source:
            byid = {e.name_id: e for e in archive.entries}
            for number in ROWS + METLIFE:
                name = row_name(number) if isinstance(number, int) else number
                entry = byid[mv.name_id(name)]; original = archive.read(entry.virtual_offset, entry.size)
                print('Compiling ' + name, flush=True)
                expected, keys = (anniversary_payloads(source, number) if isinstance(number, int)
                                  else metlife_payloads(source, name))
                after, receipt = repair_bundle(original, expected)
                require(receipt['scope_size'] > 0, 'expected repair is a no-op: ' + name)
                replay_bytes, replay = repair_bundle(after, expected)
                require(replay_bytes == after and replay['changed_bytes'] == 0, 'native payload replay changed bytes')
                receipt['replay_changed_bytes'] = 0
                size = receipt['scope_size']; at = archive.image_offset(entry.virtual_offset)
                require(archive.image_offset(entry.virtual_offset + size - 1) == at + size - 1, 'prefix crosses pack seam')
                payload = after[:size]; filename = name + '.prefix'; (output / filename).write_bytes(payload)
                spans.append(dict(name=name, file=filename, offset=at, size=size,
                                  before_sha256=sha(original[:size]), after_sha256=sha(payload)))
                native = []
                for c in tx.parse_chunks(after, allow_trailing=True):
                    if c.end_offset <= size and c.compressed:
                        # The 1.58 MB Washington stadium exceeds the helper's default 20M instruction cap.
                        native.append(dict(kind=c.kind, offset=c.offset,
                                           **prove_chunk(after, c, xbe, instruction_limit=40_000_000)))
                sheet(output / 'sheets' / f'{name}.png', name, original, after, keys)
                receipts.append(dict(name=name, textures=list(keys), native_decoder=native, **receipt))
                print(json.dumps(dict(name=name, scope_size=size, changed_bytes=receipt['changed_bytes'],
                                      loan=receipt['allocation_loan'] is not None,
                                      native_decoder_exact=True, studio_equal=True)), flush=True)
        spans.sort(key=lambda r: r['offset'])
        payloads = [(output / r['file']).read_bytes() for r in spans]
        scope = overlay_hash(base, spans, payloads)
        doc = dict(schema=SCHEMA, before_sha256=BASE_SHA, after_sha256=scope['after_sha256'],
                   disc_size=base.stat().st_size, spans=spans)
        if PINS.exists():
            require(doc == json.loads(PINS.read_text()), 'prepared output differs from frozen pins')
        require(input_state(scope['after_sha256'], doc) == 'already_applied', 'virtual replay did not skip writes')
        save(output / 'plan.json', doc)
        save(output / 'prepare_receipt.json', dict(
            bundles=receipts, scope=scope,
            write=dict(mode='virtual overlay only; no disc copy made', spans=len(spans),
                       bytes=sum(r['size'] for r in spans)),
            replay=dict(mode='virtual overlay; production input-state check',
                        state=input_state(scope['after_sha256'], doc), bytes_written=0)))
        print(json.dumps(dict(prepared=len(spans), **scope)), flush=True)
    finally:
        xbe.unlink(missing_ok=True)


def load_plan(path):
    doc = json.loads(path.read_text())
    require(PINS.is_file() and doc == json.loads(PINS.read_text()), 'plan differs from frozen fa1 pins')
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
