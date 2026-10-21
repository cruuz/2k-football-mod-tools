#!/usr/bin/env python3
"""cr1: native crowd-proportion repair for the v0.6.1 disc (fixed-span stadium SCNE writes; no positions move).

The Studio fix (mod_editor/core/nfl2k5_metlife_model.py crowd_u / crowd_band_v, used by the SoFi-derived venues'
_crowd and MetLife's _crowd) changes only the crowd billboards' UVs. This tool carries exactly that into the bundles
of a built disc, the s1b way:

* the fifteen SoFi-derived venues (135 bundles, crowd in v0.4's crowd-only ``*_crowd_fix`` shapes): tools/b765/
  s1b_repair.py's pinned transport, which writes only the crowd NORMSHORT2 UV lanes and those shapes' UV decode
  constants (+0x30..+0x3F), proved equal to the Studio's own compile by native vertex ID;
* MetLife s18/s19 (18 bundles, crowd inside the Studio-built bowl shapes): the Studio's own compile of the pinned
  stadium + intro-cameras stretch (the disc stretch must equal the old compile's pin), with a decoded proof that only
  UV lanes and UV decode constants of crowd-bearing shapes differ.

    check-before  (run from a tree of the pre-fix source) input crowd UVs equal the old Studio compile
    prepare       --input-dir FILES --pins PINS --out PLAN_DIR [--workers N]
    apply         --input-dir FILES --retail-dir RETAIL --plan PLAN_DIR/plan.json --output-dir OUT --receipt JSON
    disc          --disc ISO --files OUT --pins PINS --receipt JSON     write the repaired bundles in place
    scope         --before ISO --after ISO --receipt JSON --repair-receipt JSON   every differing byte is owned

Every step refuses on a pin mismatch, verifies the whole batch in memory before writing, reads back, and replays to
an identical output (idempotence).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SOFI_CODES = ['s00', 's01', 's03', 's07', 's10', 's11', 's12', 's14', 's15', 's16', 's23', 's24', 's25', 's40']
TRANSPLANT_CODES = ['s20']                     # b77 alg: Allegiant ships the Studio's own full-mesh compile
METLIFE_CODES = ['s18', 's19']
VARIANT_SUFFIXES = [t + w for t in 'dan' for w in 'drs']
UV_LANE = slice(4, 8)


def sha(data):
    return hashlib.sha256(bytes(data)).hexdigest()


def require(ok, message):
    if not ok:
        raise SystemExit(f"cr1_repair: REFUSED: {message}")


def names(codes):
    return [c + s + '.iff' for c in codes for s in VARIANT_SUFFIXES]


def load_pins(path):
    doc = json.loads(Path(path).read_text())
    require(doc.get('schema') == 'b77_cr1_pins/v1', 'unexpected pins schema')
    return doc


def check_inputs(input_dir, pins, wanted):
    rows = {r['name']: r for r in pins['bundles']}
    for name in wanted:
        require(name in rows, f'{name}: not pinned')
        data = (Path(input_dir) / name).read_bytes()
        require(sha(data) in (rows[name]['input_sha256'], rows[name].get('output_sha256')),
                f'{name}: bundle is neither the pinned v0.6.1 input nor the pinned cr1 output')
        require(len(data) == rows[name]['size'], f'{name}: input bundle size differs')
    return rows


# --- MetLife ----------------------------------------------------------------------------------------------------

def _decoded_layout(buf):
    """[(record offset, stream-1 offset, stride, vertex count)] for every shape of a decoded static scene."""
    from mod_editor.core import nfl2k5_scne_builder as sb
    desc = sb._rel(buf, 0x14)
    count = struct.unpack_from('<I', buf, desc + 0x2C)[0]
    at0 = sb._rel(buf, desc + 0x30)
    out = []
    for i in range(count):
        at = at0 + i * 0x100
        n = struct.unpack_from('<H', buf, at + 0x4C)[0]
        stride = struct.unpack_from('<H', buf, at + 0xC4 + 2)[0]
        p1 = sb._rel(buf, at + sb.SHAPE_STREAMS[1])
        out.append((at, p1, stride, n))
    return out


def uv_only_scope(before, after, system_bytes):
    """Proof that two decoded stadium scenes differ only in UV lanes and UV decode constants, with the counts."""
    import numpy as np
    from mod_editor.core import nfl2k5_scne_builder as sb
    require(len(before) == len(after), 'decoded stadium size changed')
    layout_b, layout_a = _decoded_layout(before), _decoded_layout(after)
    require(layout_b == layout_a, 'decoded shape layout changed')
    mask = np.zeros(len(before), dtype=bool)
    for at, p1, stride, n in layout_b:
        mask[at + 0x30:at + 0x40] = True
        if p1 is None or stride != 10:
            continue
        lanes = (p1 + 10 * np.arange(n))[:, None] + np.arange(4, 8)[None, :]
        mask[lanes.ravel()] = True
    b = np.frombuffer(before, dtype=np.uint8)
    a = np.frombuffer(after, dtype=np.uint8)
    diff = b != a
    require(not (diff & ~mask).any(), 'a decoded byte outside the UV lanes and UV constants changed')
    sc_b, sc_a = sb.parse(before, system_bytes), sb.parse(after, system_bytes)
    shapes = []
    for i, (sb_, sa_) in enumerate(zip(sc_b.shapes, sc_a.shapes)):
        if sb_.streams[1] == sa_.streams[1] and sb_.record == sa_.record:
            continue
        crowd_ids, other_ids = set(), set()
        for sub in sa_.submeshes:
            ids = {i_ for _m, ix in sb.decode_words(sub.words) for i_ in ix}
            (crowd_ids if sc_a.materials[sub.material].name == 'crowd' else other_ids).update(ids)
        require(crowd_ids, f'{sa_.name}: UV changed in a shape without crowd')
        lb = np.frombuffer(sb_.streams[1], dtype=np.dtype([('c', 'u1', 4), ('uv', '<i2', 2), ('s', '<i2')]))
        la = np.frombuffer(sa_.streams[1], dtype=lb.dtype)
        cb = np.array(struct.unpack_from('<4f', sb_.record, 0x30))
        ca = np.array(struct.unpack_from('<4f', sa_.record, 0x30))
        dec_b = lb['uv'] / 32767.0 * cb[:2] + cb[2:]
        dec_a = la['uv'] / 32767.0 * ca[:2] + ca[2:]
        others = sorted(other_ids - crowd_ids)
        changed = np.flatnonzero((lb['uv'] != la['uv']).any(axis=1))
        shapes.append(dict(shape=i, name=sa_.name, vertices=int(len(la)), crowd_vertices=len(crowd_ids),
                           packed_uv_changed=int(len(changed)),
                           non_crowd_packed_uv_changed=int(len(set(changed.tolist()) & set(others))),
                           non_crowd_max_decoded_uv_delta=float(np.abs(dec_a[others] - dec_b[others]).max()) if others else 0.0,
                           uv_constant_before=cb.tolist(), uv_constant_after=ca.tolist()))
    return dict(changed_decoded_bytes=int(diff.sum()), all_changes_in_uv_lanes_or_constants=True, shapes=shapes)


def metlife_bundle(name, data, retail, retail_dry, pin):
    from mod_editor.core import nfl2k5_metlife_model as mm
    from mod_editor.core import nfl2k5_modern_metlife as ml
    skin = mm.skin_bundle(retail, name, retail_dry)
    model, info = mm.model_bundle(skin, name)
    off, span = mm.stadium_span(data)
    cam, _ = mm._cameras_chunk(data)
    end = cam.offset + 32 + cam.stored_size
    require((off, end - off) == (pin['offset'], pin['length']), f'{name}: MetLife stretch moved')
    before = bytes(data[off:end])
    after = bytes(model[off:end])
    require(sha(before) in (pin['before_sha256'], sha(after)), f'{name}: MetLife stretch is neither its pin nor this repair')
    require(len(after) == len(before), f'{name}: stretch size changed')
    out = bytes(data[:off]) + after + bytes(data[end:])
    require(len(out) == len(data) and out[:off] == data[:off] and out[end:] == data[end:], f'{name}: outside-stretch bytes')
    tx = ml._tools()[0]
    cb, ca = ml.bundle_scenes(data)['stadium'], ml.bundle_scenes(out)['stadium']
    dec_b, _ = tx.decode_chunk(data, cb)
    dec_a, _ = tx.decode_chunk(out, ca)
    cam_b = data[cam.offset:end]
    cam_a = out[cam.offset:end]
    require(cam_a == cam_b, f'{name}: intro cameras chunk changed')
    scope = uv_only_scope(dec_b, dec_a, cb.system_bytes) if dec_b != dec_a else dict(changed_decoded_bytes=0, shapes=[])
    return out, dict(name=name, offset=off, length=end - off, before_stretch_sha256=sha(before),
                     after_stretch_sha256=sha(after), decoded_before_sha256=sha(dec_b), decoded_after_sha256=sha(dec_a),
                     already_applied=before == after, studio_compile='nfl2k5_metlife_model.model_bundle(skin_bundle(retail))',
                     intro_cameras_identical=True, outside_stretch_identical=True, decoded_scope=scope,
                     system=info['system'], video=info['video'], scratch=info['scratch'])


def allegiant_bundle(name, data, retail_dir, pin):
    """b77 alg ships Allegiant as the Studio's own compile of the stretch (cityscape to intro cameras) with v0.5's
    three fan banners carried across: the same pipeline at this tree (tools/b77/alg_repair.py compile and carry)."""
    from mod_editor.core import nfl2k5_allegiant_model as lv
    from mod_editor.core import nfl2k5_modern_metlife as ml
    from tools.b77 import alg_repair as alg
    start, end = lv.stretch(data)
    require((start, end - start) == (pin['offset'], pin['length']), f'{name}: Allegiant stretch moved')
    before = bytes(data[start:end])
    retail = (Path(retail_dir) / name).read_bytes()
    dry = (Path(retail_dir) / lv.dry_of(name)).read_bytes()
    _n, model, info = lv._compile((name, retail, dry))
    painted, detail = alg.carry_fan_art(model, alg.fan_payloads(data))
    after = bytes(painted[start:end])
    require(len(after) == len(before), f'{name}: stretch size changed')
    require(sha(before) in (pin['before_sha256'], sha(after)), f'{name}: Allegiant stretch is neither its pin nor this repair')
    out = bytes(data[:start]) + after + bytes(data[end:])
    tx = ml._tools()[0]
    chunks_b = {c.index: c for c in tx.parse_chunks(data, allow_trailing=True)}
    chunks_a = {c.index: c for c in tx.parse_chunks(out, allow_trailing=True)}
    require([(c.kind, c.offset, c.stored_size) for c in chunks_b.values()] ==
            [(c.kind, c.offset, c.stored_size) for c in chunks_a.values()], f'{name}: chunk layout changed')
    stad = ml.bundle_scenes(data)['stadium']
    for i, c in chunks_b.items():
        if i == stad.index:
            continue
        require(data[c.offset:c.offset + 32 + c.stored_size] == out[c.offset:c.offset + 32 + c.stored_size],
                f'{name}: chunk {i} ({c.kind}) changed outside the stadium scene')
    dec_b, _ = tx.decode_chunk(data, stad)
    dec_a, _ = tx.decode_chunk(out, chunks_a[stad.index])
    scope = uv_only_scope(dec_b, dec_a, stad.system_bytes) if dec_b != dec_a else dict(changed_decoded_bytes=0, shapes=[])
    return out, dict(name=name, offset=start, length=end - start, before_stretch_sha256=sha(before),
                     after_stretch_sha256=sha(after), decoded_before_sha256=sha(dec_b), decoded_after_sha256=sha(dec_a),
                     already_applied=before == after,
                     studio_compile='nfl2k5_allegiant_model._compile(retail) + alg_repair.carry_fan_art(v0.6.1 banners)',
                     other_chunks_identical=True, outside_stretch_identical=out[:start] == data[:start] and out[end:] == data[end:],
                     decoded_scope=scope, fan_banners=detail.get('textures'))


def _allegiant_job(job):
    name, input_dir, retail_dir, pin = job
    data = (Path(input_dir) / name).read_bytes()
    out, receipt = allegiant_bundle(name, data, retail_dir, pin)
    return name, out, receipt


def _metlife_job(job):
    name, input_dir, retail_dir, pin = job
    from mod_editor.core import nfl2k5_modern_metlife as ml
    data = (Path(input_dir) / name).read_bytes()
    retail = (Path(retail_dir) / name).read_bytes()
    dry = (Path(retail_dir) / ml.dry_name(name)).read_bytes()
    out, receipt = metlife_bundle(name, data, retail, dry, pin)
    return name, out, receipt


# --- commands ---------------------------------------------------------------------------------------------------

def cmd_pins(a):
    """Author time: pin the input bundles (hashes, sizes, MetLife stretches) from an extract manifest."""
    from mod_editor.core import nfl2k5_metlife_model as mm
    src = json.loads(Path(a.manifest).read_text())
    rows = {r['name']: r for r in src['entries']}
    bundles = []
    for name in names(SOFI_CODES + TRANSPLANT_CODES + METLIFE_CODES):
        r = rows[name]
        row = dict(name=name, outer_index=r['outer_index'], name_id=r['name_id'], size=r['size'],
                   input_sha256=r['sha256'])
        if name[:3] in TRANSPLANT_CODES:
            from mod_editor.core import nfl2k5_allegiant_model as lv
            data = (Path(a.input_dir) / name).read_bytes()
            require(sha(data) == r['sha256'], f'{name}: manifest hash differs')
            start, end = lv.stretch(data)
            row['allegiant_stretch'] = dict(offset=start, length=end - start, before_sha256=sha(data[start:end]))
        if name[:3] in METLIFE_CODES:
            data = (Path(a.input_dir) / name).read_bytes()
            require(sha(data) == r['sha256'], f'{name}: manifest hash differs')
            off, _span = mm.stadium_span(data)
            cam, _ = mm._cameras_chunk(data)
            end = cam.offset + 32 + cam.stored_size
            row['metlife_stretch'] = dict(offset=off, length=end - off, before_sha256=sha(data[off:end]))
        bundles.append(row)
    doc = dict(schema='b77_cr1_pins/v1', disc=a.disc_name, disc_sha256=a.disc_sha256, bundles=bundles)
    Path(a.out).write_text(json.dumps(doc, indent=1) + '\n', newline='\n')
    print('PINS', len(bundles))


def cmd_pin_outputs(a):
    """Author time, after a verified apply: pin each repaired bundle's whole-file SHA-256 next to its input pin, so a
    replay accepts exactly the input or exactly this output."""
    doc = load_pins(a.pins)
    out = {p.name: sha(p.read_bytes()) for p in Path(a.files).glob('s??[dan][drs].iff')}
    for row in doc['bundles']:
        require(row['name'] in out, f"{row['name']}: no repaired bundle")
        row['output_sha256'] = out[row['name']]
    Path(a.pins).write_text(json.dumps(doc, indent=1) + '\n', newline='\n')
    print('OUTPUT PINS', len(doc['bundles']))


def _verify_disc_job(job):
    """One code: bundles read back from the disc image against the Studio at this tree."""
    disc, code, retail_dir = job
    import importlib
    from mod_editor.core import nfl2k5_modern_metlife as ml
    from mod_editor.core import nfl2k5_scne_builder as sb
    rows = []
    with ml._outer_image()(str(disc)) as archive:
        byid = {e.name_id: e for e in archive.entries}
        bundles = {n: archive.read(byid[ml.name_id(n)].virtual_offset, byid[ml.name_id(n)].size) for n in names([code])}
    if code in SOFI_CODES:
        from tools.b765 import s1b_repair as s1b
        model = importlib.import_module('mod_editor.core.nfl2k5_' + s1b.MODULES[code] + '_model').build(code)
        cache = {}
        for n, data in bundles.items():
            rec = s1b.verify(data, code, model, compiled_meshes=cache)
            rows.append(dict(name=n, method='s1b.verify: packed crowd UVs and UV constants equal the Studio compile by native ID',
                             shapes=len(rec), vertices=sum(r['vertices'] for r in rec)))
    elif code in METLIFE_CODES:
        from mod_editor.core import nfl2k5_metlife_model as mm
        pins = {p['name']: p for p in mm.model_pins()['bundles']}
        for n, data in bundles.items():
            p = pins[n]
            require(sha(data[p['offset']:p['offset'] + p['length']]) == p['model_sha256'], f'{n}: disc stretch is not the Studio pin')
            rows.append(dict(name=n, method='stadium+cameras stretch equals data/nfl2k5_metlife_model/pins.json model_sha256',
                             model_sha256=p['model_sha256']))
    else:
        from mod_editor.core import nfl2k5_allegiant_model as lv
        tx = ml._tools()[0]
        for n, data in bundles.items():
            retail = (Path(retail_dir) / n).read_bytes()
            dry = (Path(retail_dir) / lv.dry_of(n)).read_bytes()
            _n, model, _info = lv._compile((n, retail, dry))
            c_d, c_m = ml.bundle_scenes(data)['stadium'], ml.bundle_scenes(model)['stadium']
            dd, _ = tx.decode_chunk(data, c_d)
            dm, _ = tx.decode_chunk(model, c_m)
            sd, sm_ = sb.parse(dd, c_d.system_bytes), sb.parse(dm, c_m.system_bytes)
            require(len(sd.shapes) == len(sm_.shapes), f'{n}: shape count differs')
            for x, y in zip(sd.shapes, sm_.shapes):
                require(x.name == y.name and x.streams == y.streams and bytes(x.record) == bytes(y.record),
                        f'{n}: {x.name} differs from the Studio compile')
            rows.append(dict(name=n, method='every stadium shape record and vertex stream equals the Studio compile '
                             '(textures differ only by the carried fan banners)', shapes=len(sd.shapes)))
    return rows


def cmd_verify_disc(a):
    jobs = [(a.disc, code, a.retail_dir) for code in SOFI_CODES + TRANSPLANT_CODES + METLIFE_CODES]
    out = []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        for rows in pool.map(_verify_disc_job, jobs):
            out += rows
            print(rows[0]['name'][:3], 'Studio equality', len(rows), 'bundles', flush=True)
    Path(a.receipt).write_text(json.dumps(dict(schema='b77_cr1_disc_studio_equality/v1', disc=str(a.disc),
                                               bundles=out), indent=1) + '\n', newline='\n')
    print('VERIFIED', len(out))


def cmd_check_before(a):
    """Pre-fix source only: the input crowd UVs equal the old Studio compile (s1b verify) and MetLife stretches equal
    the old model pins."""
    import importlib
    from tools.b765 import s1b_repair as s1b
    from mod_editor.core import nfl2k5_metlife_model as mm
    pins = load_pins(a.pins)
    rows = check_inputs(a.input_dir, pins, names(SOFI_CODES + TRANSPLANT_CODES + METLIFE_CODES))
    out = dict(schema='b77_cr1_check_before/v1', source_root=str(ROOT), venues={})
    for code in a.codes or SOFI_CODES:
        model = importlib.import_module('mod_editor.core.nfl2k5_' + s1b.MODULES[code] + '_model').build(code)
        cache = {}
        for name in names([code]):
            receipts = s1b.verify((Path(a.input_dir) / name).read_bytes(), code, model, compiled_meshes=cache)
            out['venues'][name] = dict(shapes=len(receipts), vertices=sum(r['vertices'] for r in receipts),
                                       crowd_uvs_equal_old_studio=True)
            print(name, 'old-Studio crowd UV equality', len(receipts), 'shapes', flush=True)
    alg_doc = json.loads((ROOT / 'tools' / 'b77' / 'alg_repair_manifest.json').read_text())
    for name in names(TRANSPLANT_CODES):
        data = (Path(a.input_dir) / name).read_bytes()
        st = rows[name]['allegiant_stretch']
        want = alg_doc['bundles'][name]
        require((want['offset'], want['length']) == (st['offset'], st['length']), f'{name}: alg stretch differs')
        require(sha(data[st['offset']:st['offset'] + st['length']]) == want['after_stretch_sha256'],
                f'{name}: not the b77 alg Studio compile')
        out['venues'][name] = dict(allegiant_stretch_equals_alg_output_pin=want['after_stretch_sha256'])
        print(name, 'alg output pin equal', flush=True)
    model_pins = {p['name']: p for p in mm.model_pins()['bundles']}
    for name in names(METLIFE_CODES):
        data = (Path(a.input_dir) / name).read_bytes()
        p = model_pins[name]
        st = rows[name]['metlife_stretch']
        require((p['offset'], p['length']) == (st['offset'], st['length']), f'{name}: old pin stretch differs')
        require(sha(data[p['offset']:p['offset'] + p['length']]) == p['model_sha256'], f'{name}: not the old MetLife compile')
        out['venues'][name] = dict(metlife_stretch_equals_old_studio_pin=p['model_sha256'])
        print(name, 'old MetLife pin equal', flush=True)
    Path(a.receipt).write_text(json.dumps(out, indent=1) + '\n', newline='\n')


def cmd_prepare(a):
    from tools.b765 import s1b_repair as s1b
    pins = load_pins(a.pins)
    rows = check_inputs(a.input_dir, pins, names(a.codes))
    require(not Path(a.out).exists(), 'prepare needs a new plan folder')
    Path(a.out).mkdir(parents=True)
    s1b_pins = {n: dict(sha256=r['input_sha256'], outer_index=r['outer_index']) for n, r in rows.items()}
    jobs = [(code, Path(a.input_dir), Path(a.out), s1b_pins) for code in a.codes]
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        entries = [e for group in pool.map(s1b.prepare_venue, jobs) for e in group]
    from tools.b765 import s1_geometry as g
    g.write_atomic(Path(a.out) / 'plan.json', g.json_bytes(dict(schema='b765_s1_repair_plan/v1', entries=entries)))
    print(json.dumps(dict(plan=str(Path(a.out) / 'plan.json'), resources=len(entries))))


def cmd_apply(a):
    from tools.b765 import s1b_repair as s1b
    from tools.b765 import s1_geometry as g
    pins = load_pins(a.pins)
    out_dir = Path(a.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    receipt = dict(schema='b77_cr1_native_repair/v1', pins_sha256=sha(Path(a.pins).read_bytes()))
    if a.plan:
        plan_doc = json.loads(Path(a.plan).read_text())
        check_inputs(a.input_dir, pins, [e['name'] for e in plan_doc['entries']])
        sofi_receipt = out_dir.parent / (out_dir.name + '.sofi_receipt.json')
        s1b.apply(Path(a.input_dir), out_dir, Path(a.plan), sofi_receipt, workers=a.workers)
        receipt['sofi_derived'] = dict(receipt=str(sofi_receipt), receipt_sha256=sha(sofi_receipt.read_bytes()),
                                       resources=len(plan_doc['entries']))
    if a.metlife:
        rows = check_inputs(a.input_dir, pins, names(METLIFE_CODES))
        jobs = [(n, a.input_dir, a.retail_dir, rows[n]['metlife_stretch']) for n in names(METLIFE_CODES)]
        outputs, ml_receipts = {}, []
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            for name, out, rec in pool.map(_metlife_job, jobs):
                outputs[name] = out
                ml_receipts.append(dict(rec, before_sha256=sha((Path(a.input_dir) / name).read_bytes()), after_sha256=sha(out)))
        # whole batch verified in memory above; only now write
        for name, out in outputs.items():
            g.write_atomic(out_dir / name, out)
            require((out_dir / name).read_bytes() == out, f'{name}: written file read-back differs')
        receipt['metlife'] = ml_receipts
    if a.allegiant:
        rows = check_inputs(a.input_dir, pins, names(TRANSPLANT_CODES))
        jobs = [(n, a.input_dir, a.retail_dir, rows[n]['allegiant_stretch']) for n in names(TRANSPLANT_CODES)]
        outputs, al_receipts = {}, []
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            for name, out, rec in pool.map(_allegiant_job, jobs):
                outputs[name] = out
                al_receipts.append(dict(rec, before_sha256=sha((Path(a.input_dir) / name).read_bytes()), after_sha256=sha(out)))
        for name, out in outputs.items():
            g.write_atomic(out_dir / name, out)
            require((out_dir / name).read_bytes() == out, f'{name}: written file read-back differs')
        receipt['allegiant'] = al_receipts
    Path(a.receipt).write_text(json.dumps(receipt, indent=1) + '\n', newline='\n')
    print('APPLIED', len(receipt.get('metlife', [])), 'metlife;', receipt.get('sofi_derived', {}).get('resources', 0), 'sofi-derived')


def owned_stretch(name, bundle):
    """(start, end) inside a bundle that this repair owns: the stadium SCNE chunk, plus MetLife's intro cameras."""
    from mod_editor.core import nfl2k5_modern_metlife as ml
    c = ml.bundle_scenes(bundle)['stadium']
    end = c.offset + 32 + c.stored_size
    if name[:3] in METLIFE_CODES:
        from mod_editor.core import nfl2k5_metlife_model as mm
        cam, _ = mm._cameras_chunk(bundle)
        require(cam.offset == end, f'{name}: intro cameras do not follow the stadium chunk')
        end = cam.offset + 32 + cam.stored_size
    return c.offset, end


def cmd_disc(a):
    """Write repaired bundles into a disc image in place (the image must be the pinned input or already repaired)."""
    from mod_editor.core import nfl2k5_modern_metlife as ml
    pins = load_pins(a.pins)
    rows = {r['name']: r for r in pins['bundles']}
    files = sorted(p for p in Path(a.files).glob('s??[dan][drs].iff'))
    require(files, 'no repaired bundles')
    plan = []
    with ml._outer_image()(str(a.disc)) as archive:
        byid = {e.name_id: e for e in archive.entries}
        for path in files:
            r = rows[path.name]
            e = byid[ml.name_id(path.name)]
            require(e.index == r['outer_index'] and e.size == r['size'], f'{path.name}: archive entry differs')
            new = path.read_bytes()
            require(len(new) == e.size, f'{path.name}: size differs')
            have = archive.read(e.virtual_offset, e.size)
            require(sha(have) in (r['input_sha256'], sha(new)), f'{path.name}: disc bundle is neither the pinned input nor the repair')
            plan.append((path.name, e, new, sha(have)))
    receipts = []
    with ml._outer_image()(str(a.disc), writable=True) as archive:
        for name, e, new, before in plan:
            if before != sha(new):
                archive.write(e.virtual_offset, new)
            back = archive.read(e.virtual_offset, e.size)
            require(back == new, f'{name}: disc read-back differs')
            off, end = owned_stretch(name, new)
            image = [(pack.image_offset + o, pack.image_offset + o + n)
                     for pack, o, n in archive._segments(e.virtual_offset + off, end - off)]
            receipts.append(dict(name=name, outer_index=e.index, virtual_offset=e.virtual_offset, size=e.size,
                                 before_sha256=before, after_sha256=sha(new), already_applied=before == sha(new),
                                 owned_stretch=[off, end], owned_image_ranges=image))
    Path(a.receipt).write_text(json.dumps(dict(schema='b77_cr1_disc_write/v1', disc=str(a.disc), bundles=receipts),
                                          indent=1) + '\n', newline='\n')
    print('DISC', len(receipts), 'bundles,', sum(not r['already_applied'] for r in receipts), 'written')


def cmd_scope(a):
    """Byte comparison of two disc images: every differing byte must fall inside an owned stadium stretch."""
    import numpy as np
    disc_rec = json.loads(Path(a.disc_receipt).read_text())
    owned = sorted((s, e, b['name']) for b in disc_rec['bundles'] for s, e in b['owned_image_ranges'])
    size_b, size_a = os.path.getsize(a.before), os.path.getsize(a.after)
    require(size_b == size_a, 'disc sizes differ')
    diffs = []
    block = 1 << 24
    with open(a.before, 'rb') as fb, open(a.after, 'rb') as fa:
        pos = 0
        while True:
            x, y = fb.read(block), fa.read(block)
            if not x:
                break
            if x != y:
                d = np.flatnonzero(np.frombuffer(x, np.uint8) != np.frombuffer(y, np.uint8))
                start = prev = int(d[0])
                for k in d[1:].tolist():
                    if k != prev + 1:
                        diffs.append((pos + start, pos + prev + 1))
                        start = k
                    prev = k
                diffs.append((pos + start, pos + prev + 1))
            pos += len(x)
    starts = [s for s, _e, _n in owned]
    outside, per_bundle = [], {}
    import bisect
    for s, e in diffs:
        i = bisect.bisect_right(starts, s) - 1
        if i < 0 or not (owned[i][0] <= s and e <= owned[i][1]):
            outside.append((s, e))
        else:
            per_bundle[owned[i][2]] = per_bundle.get(owned[i][2], 0) + (e - s)
    doc = dict(schema='b77_cr1_disc_scope/v1', before=str(a.before), after=str(a.after),
               before_sha256=a.before_sha256, after_sha256=a.after_sha256, image_size=size_a,
               differing_runs=len(diffs), differing_bytes=sum(e - s for s, e in diffs),
               owned_stretches=len(owned), owned_bytes=sum(e - s for s, e, _n in owned),
               bytes_outside_owned_stretches=sum(e - s for s, e in outside), outside_runs=outside[:50],
               changed_bytes_per_bundle=per_bundle)
    Path(a.receipt).write_text(json.dumps(doc, indent=1) + '\n', newline='\n')
    print('DIFF runs', len(diffs), 'bytes', doc['differing_bytes'], 'outside owned', doc['bytes_outside_owned_stretches'])
    require(not outside, 'bytes changed outside the owned stadium stretches')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('pins'); s.add_argument('--manifest', required=True); s.add_argument('--input-dir', required=True)
    s.add_argument('--out', required=True); s.add_argument('--disc-name', required=True); s.add_argument('--disc-sha256', required=True)
    s = sub.add_parser('pin-outputs'); s.add_argument('--files', required=True); s.add_argument('--pins', required=True)
    s = sub.add_parser('verify-disc'); s.add_argument('--disc', required=True); s.add_argument('--retail-dir', required=True)
    s.add_argument('--receipt', required=True); s.add_argument('--workers', type=int, default=4)
    s = sub.add_parser('check-before'); s.add_argument('--input-dir', required=True); s.add_argument('--pins', required=True)
    s.add_argument('--receipt', required=True); s.add_argument('--codes', nargs='*')
    s = sub.add_parser('prepare'); s.add_argument('--input-dir', required=True); s.add_argument('--pins', required=True)
    s.add_argument('--out', required=True); s.add_argument('--codes', nargs='+', default=SOFI_CODES); s.add_argument('--workers', type=int, default=4)
    s = sub.add_parser('apply'); s.add_argument('--input-dir', required=True); s.add_argument('--pins', required=True)
    s.add_argument('--output-dir', required=True); s.add_argument('--receipt', required=True); s.add_argument('--plan')
    s.add_argument('--metlife', action='store_true'); s.add_argument('--allegiant', action='store_true'); s.add_argument('--retail-dir'); s.add_argument('--workers', type=int, default=4)
    s = sub.add_parser('disc'); s.add_argument('--disc', required=True); s.add_argument('--files', required=True)
    s.add_argument('--pins', required=True); s.add_argument('--receipt', required=True)
    s = sub.add_parser('scope'); s.add_argument('--before', required=True); s.add_argument('--after', required=True)
    s.add_argument('--disc-receipt', required=True); s.add_argument('--receipt', required=True)
    s.add_argument('--before-sha256', default=''); s.add_argument('--after-sha256', default='')
    a = p.parse_args(argv)
    return dict(pins=cmd_pins, prepare=cmd_prepare, **{'pin-outputs': cmd_pin_outputs, 'verify-disc': cmd_verify_disc}, apply=cmd_apply, disc=cmd_disc, scope=cmd_scope,
                **{'check-before': cmd_check_before})[a.cmd](a) or 0


if __name__ == '__main__':
    raise SystemExit(main())
