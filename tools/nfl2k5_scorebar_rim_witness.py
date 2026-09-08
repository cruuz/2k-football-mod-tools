#!/usr/bin/env python3
"""Bounded native CPU forecasts and pinned v3 comparator, never a game witness."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import importlib.util
from pathlib import Path
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebar_v3 as colors
from nfl2k5_scorebug_exact import Build, write_json
import nfl2k5_scorebug_exact as comparator
import nfl2k5_scorebar_v3_witness as v3

BASELINES = {
    'nfl2k5_scorebug_exact_v3.py': '92dc368a99018159a3c2e84147138c81fe2424ec984c539f239d6f7bd9aa1772',
    'nfl2k5_scorebar_callbacks_v3.py': '768d1307511cc6965ea7746649515f2ffe1e4cd2a12a32bb788f276a326345da',
}


@contextmanager
def previous_v3():
    modules = []
    for name, digest in BASELINES.items():
        path = ROOT / 'tests/fixtures' / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('foreign witnessed-v3 compiler fixture: ' + name)
        spec = importlib.util.spec_from_file_location('mod_editor.core._rim_' + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    exact, callbacks = modules
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(colors, 'xbe_specs', callbacks.xbe_specs))
        stack.enter_context(mock.patch.object(scene, 'exact', exact))
        yield exact


def cases():
    return {
        'bal_at_jax': dict(v3.CASES['bal_jax_pre_snap']),
        'min_at_nyj': dict(v3.CASES['min_nyj_pre_snap']),
        'lv_at_hou': {**v3.CASES['bal_jax_pre_snap'], 'identity': dict(away='LV', home='HOU')},
        'live_min_at_nyj': dict(v3.CASES['min_nyj_live']),
        'atl_at_gb': {**v3.CASES['bal_jax_pre_snap'], 'identity': dict(away='ATL', home='GB')},
        'lv_mirror_secondary_silver': {**v3.CASES['bal_jax_pre_snap'], 'identity': dict(away='LV', home='LV')},
        'missing_codes_silver': {**v3.CASES['bal_jax_pre_snap'],
            'identity': dict(away='BAL', home='JAX', away_code='missing', home_code='missing')},
    }


def region_differences(before, after, geometry):
    """V3-to-rim RGB MAE using the existing five-region comparator rectangles."""
    import numpy as np
    a, b = np.asarray(before.convert('RGB')).astype(float), np.asarray(after.convert('RGB')).astype(float)
    result = {}
    for name, rect in scene.exact.SOURCE_REGIONS.items():
        x0, y0, x1, y1 = map(round, scene.exact.hud_box(rect))
        delta = abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1])
        mask = np.ones(delta.shape[:2], dtype=bool)
        if name == 'frame_rim':
            mask[2:-2, 2:-2] = False
        result[name] = float(delta[mask].mean())
    return result


def color_evidence(build):
    import struct
    import unicorn
    cap = {}
    decoded = scene.serialize(scene.exact.mesh(build.retail_scene))
    atlas = scene.apply(build.spans['score_buga'],'score_buga')[0]
    v3.projection.native_geometry(build.payload, decoded, fonts=build.fonts,
        texture_span=atlas, capture=cap, visible_elements=(), visibility_state='pre_snap')
    m = cap['machine']; rows = []
    try:
        table = m.get(m.get(0xa95528)+0x20); dest = m.alloc(128)
        for away,home in (('BAL','JAX'),('MIN','NYJ'),('LV','HOU'),('ATL','GB')):
            m.identity(away=away,home=home)
            for side,team,context,callback in (('away',away,0xb30a58,0xfc030),('home',home,0xb30864,0xfc010)):
                reads = []
                hook = m.uc.hook_add(unicorn.UC_HOOK_MEM_READ,
                    lambda _u,_a,at,n,_v,_d: reads.append((at,n)),begin=0x4e7fe0,end=0x4e889f)
                try:
                    m.run(0x68d70,ecx=context); primary=m.uc.reg_read(m.x.UC_X86_REG_EAX)
                    m.run(0x68dc0,ecx=context); secondary=m.uc.reg_read(m.x.UC_X86_REG_EAX)
                    m.run(callback,ecx=dest)
                finally:
                    m.uc.hook_del(hook)
                word_reads=sorted({hex(at) for at,n in reads if n==4 and (at-0x4e7fe0)%28 in (8,12)})
                target=table+128*colors.RIM_INDICES[side]
                rows.append(dict(team=team,side=side,primary=hex(primary),secondary=hex(secondary),
                    panel=hex(m.get(table+128*colors.MATERIAL_INDICES[side]+24)),rim=hex(m.get(target+24)),
                    native_colour_word_reads=word_reads,
                    submission=v3.material_submission(m,build.payload,target)))
        start=scene.layout.sbpos.va_to_off(build.payload,0x4e7fe0)
        raw=build.payload[start:start+2240]
        words=[struct.unpack_from('<I',raw,i*28+offset)[0] for i in range(80) for offset in (8,12)]
        assert all(word>>24==255 for word in words)
        assert 0xff0065e6 not in words[::2]
        return dict(rows=rows,table_sha256=scene.digest(raw),rows_in_table=80,
            all_primary_and_secondary_words_present_and_opaque=True,
            unknown_primary_default_not_in_table=True,
            missing_colour_scope='Missing retail palette/code has neither word. No pinned row has a missing primary with a present secondary.')
    finally:
        m.close()


def build_evidence(extraction, output):
    from PIL import Image, ImageDraw
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build = Build(extraction / 'vc_53450030/0', extraction / 'default.xbe')
    rows, sheet_rows = {}, []
    try:
        write_json(output/'colors.json', color_evidence(build))
        _, photograph = comparator.reference()
        for name, case in cases().items():
            variants = {}
            for label in ('v3', 'rim'):
                path = output / f'{name}_{label}.png'
                with ExitStack() as stack:
                    compiler = stack.enter_context(previous_v3()) if label == 'v3' else scene.exact
                    # HUD-resolution output makes the unchanged comparator's
                    # rectangles usable without fitting a new viewport.
                    g = v3.render(build, path, case, compiler=compiler, calibrated=False)
                    xbe = scene.apply_xbe(build.payload)[0]
                variants[label] = dict(geometry=g, xbe_sha256=scene.digest(xbe), png_sha256=scene.digest(path.read_bytes()))
            with Image.open(output/f'{name}_v3.png') as before, Image.open(output/f'{name}_rim.png') as after:
                differences = region_differences(before, after, variants['rim']['geometry'])
                # Existing v3 comparator against the same LV/HOU photograph.
                # Other pairs intentionally do not have that photograph's colours.
                for label, im in (('v3', before), ('rim', after)):
                    variants[label]['broadcast_comparator'] = comparator.compare(photograph, im, variants[label]['geometry'], {})
                tile = Image.new('RGB', (980, 155), '#202020')
                d = ImageDraw.Draw(tile)
                d.text((8, 4), name + ' | old v3 (left) | rim forecast (right) | UNWITNESSED', fill='white')
                for x, im in ((8, before), (496, after)):
                    tile.paste(im.crop((140, 398, 500, 458)).resize((480, 80), Image.Resampling.NEAREST), (x, 30))
                d.text((8, 120), 'Native CPU inputs; software raster. Live clock values are fixture inputs.', fill='white')
                sheet_rows.append(tile)
            old_draws = variants['v3']['geometry']['draws']
            new_draws = variants['rim']['geometry']['draws']
            text_equal = old_draws == new_draws
            rows[name] = dict(inputs=case, variants=variants, v3_region_rgb_mae=differences,
                              text_submissions_identical=text_equal)
            if not text_equal:
                raise AssertionError('rim edit changed native text submission: ' + name)
        sheet = Image.new('RGB', (980, 155*len(sheet_rows)))
        for i, tile in enumerate(sheet_rows):
            sheet.paste(tile, (0, i*155))
        sheet.save(output/'comparison.png')
        write_json(output/'forecasts.json', dict(schema='nfl2k5_scorebar_rim_forecast/v1',
            experimental=True, witnessed=False, cases=rows, baseline_compilers=BASELINES,
            limits='Native CPU evidence, not GPU execution or gameplay. Broadcast metrics keep the original LV/HOU reference; exact match is not claimed.'))
    finally:
        build.close()
    return rows


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extraction', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'docs/scorebug_ingame/rim')
    args = parser.parse_args(argv)
    rows = build_evidence(args.extraction, args.output)
    for name, row in rows.items():
        print(name, row['v3_region_rgb_mae'], 'identical text:', row['text_submissions_identical'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
