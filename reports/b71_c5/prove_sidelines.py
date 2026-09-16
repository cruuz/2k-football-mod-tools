"""Rebuild/decode retail spans in memory; export numbers and hashes, never retail bytes."""
from pathlib import Path
from collections import Counter
import argparse
from functools import lru_cache
import colorsys
import json
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_color as mc
BASE = '5eac51c7'
SOURCE = ROOT / 'extracted/ESPN NFL 2K5 (USA)'


def baseline():
    old = types.ModuleType('mod_editor.core._c4_baseline')
    old.__file__ = mc.__file__
    old.__package__ = 'mod_editor.core'
    code = subprocess.check_output(['git', 'show', BASE+':mod_editor/core/nfl2k5_modern_color.py'], cwd=ROOT)
    exec(compile(code, old.__file__, 'exec'), old.__dict__)
    old._PINS = json.loads(subprocess.check_output(['git', 'show', BASE+':data/nfl2k5_modern_color_pins.json'], cwd=ROOT))
    return old


def hsv(rgb):
    h, s, v = colorsys.rgb_to_hsv(*(c/255 for c in rgb))
    return dict(hue=h*360, saturation=s, value=v)


@lru_cache(maxsize=4096)
def green_rgb(rgb, hue_max=150):
    h, s, v = colorsys.rgb_to_hsv(*(c/255 for c in rgb))
    return 45 <= h*360 <= hue_max and s > .15 and v > .10


def decoded(blob, mask_blob=None, *, raw_override=None):
    tx, inv, R, H = mc._tools()
    rec, out, record = mc._scene(blob, mc._chunks(blob)[0])
    old_out = mc._scene(mask_blob, mc._chunks(mask_blob)[0])[1] if mask_blob is not None else out
    if raw_override is not None:
        out = raw_override
    rgb, spans = {}, []
    for name in (mc.COLOR_MAP_MATERIAL, mc.OUTSIDE_MATERIAL):
        texture = next((t for t in rec['embedded_textures'] if name in t.get('mapped_material_names', [])), None)
        if texture:
            info = inv.texture_info(out, texture['descriptor_offset'], rec['name'], texture['index'])
            pixels = tx.texture_to_rgba(out, record.as_chunk(), info)
            masks = tx.texture_to_rgba(old_out, record.as_chunk(), info)
            # Independent decoder, source green mask. No use of writer mean helper.
            used = [i for i in range(0, len(pixels), 4)
                    if green_rgb(bytes(masks[i:i+3]), 180)]
            rgb[name] = tuple(sum(pixels[i+c] for i in used)/len(used) for c in range(3)) if used else None
            if name == mc.OUTSIDE_MATERIAL:
                spans.extend(range(rec['system_bytes']+texture['palette_offset'], rec['system_bytes']+texture['palette_offset']+1024))
        else:
            mat = next((m for m in rec['materials'] if m['name'] == name), None)
            if mat:
                at = mat['record_offset'] + 0x18
                rgb[name] = tuple(out[at+c] for c in (2, 1, 0))
    tints = Counter()
    for shape in rec['shapes']:
        if shape['name'] != 'Outside_grass':
            continue
        colour = next((a for a in shape['attribute_descriptors'] if a['format_name'] == 'D3DCOLOR'), None)
        if colour:
            stream = shape['vertex_streams'][colour['stream_index']]
            for i in range(shape['vertex_count']):
                at = stream['offset'] + i*stream['stride'] + colour['byte_offset']
                tints[tuple(out[at+c] for c in (2, 1, 0))] += 1
                spans.extend(range(at, at+3))  # alpha is never changed
    materials = {m['name']: tuple(out[m['record_offset']+o:m['record_offset']+o+4].hex() for o in (0x14, 0x18))
                 for m in rec['materials'] if m['name'] in (mc.COLOR_MAP_MATERIAL, mc.OUTSIDE_MATERIAL)}
    return dict(rgb=rgb, tints=[dict(rgb=t, count=c) for t,c in tints.items()], materials=materials), out, set(spans)


def predictions(info, rig):
    field = mc.predicted_on_screen(info['rgb'][mc.COLOR_MAP_MATERIAL], rig, rounded=False)
    outside = mc.predicted_on_screen(info['rgb'][mc.OUTSIDE_MATERIAL], rig, surface='outside', rounded=False)
    tinted = [mc.predicted_on_screen(info['rgb'][mc.OUTSIDE_MATERIAL], rig, surface='outside', tint=t['rgb'], rounded=False)
              for t in info['tints']]
    return dict(field=field, outside=outside, field_hsv=hsv(field), outside_hsv=hsv(outside),
                tinted_value_ratios=[max(t)/max(field) for t in tinted],
                tinted_saturations=[hsv(t)['saturation'] for t in tinted])


def check_model(info):
    checks = {}
    for rig in mc.MODERN_RIGS:
        p = predictions(info, rig)
        ratio = max(p['outside'])/max(p['field'])
        assert .92 <= ratio <= 1, (rig, 'value', ratio, p)
        assert p['outside_hsv']['saturation'] <= p['field_hsv']['saturation'], (rig, 'saturation', p)
        assert all(.92 <= r <= 1 for r in p['tinted_value_ratios']), (rig, 'tints', p)
        assert all(s <= p['field_hsv']['saturation'] for s in p['tinted_saturations']), (rig, 'tint saturation', p)
        for tint in [(255, 255, 255)] + [t['rgb'] for t in info['tints']]:
            f = mc.predicted_on_screen(info['rgb'][mc.COLOR_MAP_MATERIAL], rig)
            o = mc.predicted_on_screen(info['rgb'][mc.OUTSIDE_MATERIAL], rig, surface='outside', tint=tint)
            assert .92 <= max(o)/max(f) <= 1, (rig, 'rounded value', f, o)
            assert hsv(o)['saturation'] <= hsv(f)['saturation'], (rig, 'rounded saturation', f, o)
        checks[rig] = p
    return checks


def main(field_cache=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    old = baseline()
    pins = mc._pins()
    assert pins['light_tables'] == old._pins()['light_tables'], 'C5 may not change any rig'
    data = (SOURCE/'default.xbe').read_bytes()
    assert mc.apply(data)[0] == old.apply(data)[0], 'complete applied XBE must stay C4 exact'
    assert mc.apply(mc.apply(data)[0])[0] == mc.apply(data)[0]
    representatives = {'s08dd.iff':'day','s13dd.iff':'day','s13ad.iff':'afternoon',
                       's13nd.iff':'night_indoor','s11dd.iff':'night_indoor','s09dd.iff':'night_indoor','s48dd.iff':'day'}
    cache, old_cache, rows = field_cache or {}, {}, []
    raw_c4_cache = {}
    class CapturedScene(Exception):
        def __init__(self, raw): self.raw = raw
    def capture_raw(span, raw):
        raise CapturedScene(raw)
    def c4_raw(span, outer):
        key = mc.sha(span)
        if key not in raw_c4_cache:
            fit = old.fit_fixed_span
            old.fit_fixed_span = capture_raw
            try:
                old.modern_field_scene(span, outer_index=outer)
            except CapturedScene as captured:
                raw_c4_cache[key] = captured.raw
            finally:
                old.fit_fixed_span = fit
        return raw_c4_cache[key]

    if args.all and field_cache is None:
        spans = {}
        with mc._outer_image()(SOURCE/'vc_53450030') as archive:
            for pin in pins['bundles']:
                e = archive.entries[pin['outer']]
                data = archive.read(e.virtual_offset, e.size)
                for kind, at, size in mc.bundle_plan(data):
                    if kind != 'tint':
                        span = data[at:at+size]
                        spans.setdefault((kind, mc.sha(span)), (kind, pin['outer'], span))
        cache = mc._refit_fields(spans, workers=8, progress=lambda message, done, total: print(message, flush=True) if done % 50 == 0 else None)
    pairs = {p['name']:p for p in old._pins()['bundles']}
    with mc._outer_image()(SOURCE/'vc_53450030') as archive:
        for n, pin in enumerate(pins['bundles']):
            if not args.all and pin['name'] not in representatives:
                continue
            e = archive.entries[pin['outer']]
            retail = archive.read(e.virtual_offset, e.size)
            after, edits = mc.modern_bundle(retail, outer_index=pin['outer'], field_cache=cache)
            assert mc.sha(retail) == pin['retail_sha256']
            assert mc.sha(after) == pin['applied_sha256'], pin['name']
            assert not any(e.get('unfit') for e in edits if e['kind'] == 'field'), pin['name']
            info, raw, allowed = decoded(after, retail)
            assert info['rgb'][mc.COLOR_MAP_MATERIAL] is not None, pin['name']
            prior_raw = c4_raw(mc.field_span(retail), pin['outer'])
            changed = {i for i,(a,b) in enumerate(zip(prior_raw,raw)) if a != b}
            assert changed <= allowed, (pin['name'], 'C5 escaped outside palette/vertex RGB')
            assert info['materials'][mc.OUTSIDE_MATERIAL] == ('ffffffff', 'ffffffff'), (pin['name'], 'nonneutral outside material')
            try:
                checks = check_model(info) if info['rgb'][mc.OUTSIDE_MATERIAL] is not None else {}
                if not checks:
                    assert not changed, (pin['name'], 'non-green outside must stay C4 exact')
            except AssertionError:
                print('MODEL FAILED', pin['name'], info, flush=True)
                raise
            prior = pairs[pin['name']]
            for site, c4 in zip(pin['sites'], prior['sites']):
                assert all(site[k] == c4[k] for k in ('kind','offset','size','retail'))
                if site['kind'] != 'field':
                    assert site == c4, (pin['name'], site['kind'])
            for edit in edits:
                if edit['kind'] == 'tint':
                    continue
                at, size = edit['offset'], edit['size']
                assert after[at:at+32] == retail[at:at+32]
                tx = mc._tools()[0]
                before_raw = tx.decode_chunk(retail[at:at+size], mc._chunks(retail[at:at+size])[0])[0]
                after_raw = tx.decode_chunk(after[at:at+size], mc._chunks(after[at:at+size])[0])[0]
                assert len(before_raw) == len(after_raw)
            row = dict(name=pin['name'], applied_sha256=mc.sha(after), decoded=info, conditions=checks, changed_decoded_bytes=len(changed), c4_outside_only=True)
            if pin['name'] in representatives:
                before, _ = old.modern_bundle(retail, outer_index=pin['outer'], field_cache=old_cache)
                assert old.sha(before) == prior['applied_sha256']
                bi, br, _ = decoded(before, retail)
                if pin['name'] == 's08dd.iff':
                    assert tuple(bi['rgb'][mc.OUTSIDE_MATERIAL]) == mc.OUTSIDE_REFERENCE_MAP
                assert info['rgb'][mc.COLOR_MAP_MATERIAL] == bi['rgb'][mc.COLOR_MAP_MATERIAL]
                assert info['materials'] == bi['materials'], 'separate material colours stay neutral/exact'
                changes = {i for i,(x,y) in enumerate(zip(br,raw)) if x != y}
                assert changes <= allowed, 'only outside palettes and vertex RGB may differ from C4'
                row.update(before=bi, representative_rig=representatives[pin['name']],
                           prediction_before=predictions(bi,representatives[pin['name']]),
                           prediction_after=checks[representatives[pin['name']]], changed_decoded_bytes=len(changes))
            rows.append(row)
            print('PASS', pin['name'], 'seven conditions and every outside tint' if checks else 'non-green outside stays C4 exact', flush=True)
    result = dict(baseline=BASE, scope='MODEL, not rendered proof. Outside response calibrated from day s08dd strip; other conditions/classes extrapolated.',
                  outside_response=mc.OUTSIDE_RESPONSE, outside_calibration=dict(map=mc.OUTSIDE_REFERENCE_MAP, screen=mc.OUTSIDE_REFERENCE_SCREEN),
                  rigs_unchanged=True, complete_xbe_unchanged=True, rows=rows)
    target = ROOT/'reports/b71_c5'/('all-decoder-proof.json' if args.all else 'sideline-proof.json')
    target.write_text(json.dumps(result, indent=2)+'\n')
    print('PASS', len(rows), 'decoded bundles; seven identical C4 rigs; exact complete applied XBE')


if __name__ == '__main__':
    main()
