#!/usr/bin/env python3
"""Reproduce Noah's r64 captures with bounded native submissions, then compare.

The affine viewport and tone curve are measured from the old bar, not fitted
per glyph. They model this capture chain, not an independently proved NV2A
renderer. This tool never opens a disc for writing or launches an emulator.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_scorebug_ingame as scene
from mod_editor.core import nfl2k5_scorebug_exact as exact
from nfl2k5_scorebug_exact import Build, write_json
import nfl2k5_scorebug_projection as projection

FIXTURE = ROOT / 'tests/fixtures/nfl2k5_scorebug_exact_v1.py'
FIXTURE_SHA = '6489bdd9a06112180219bb6382bf9c570f2850ee7c7d847fcc38f2f653e0074c'
V2_FIXTURE_SHA = '7626ade9cf27019e86e13ee8bf5c69b74851620846edfcab0b5461c1d0d6faba'
WITNESSES = {
    'pre_snap': dict(file='ksnip_20260907-140247.png', size=[1128, 665],
        sha256='5624a4f2c460869ab16ae267976b0fe21ee9f8eb900abac00f2e9498d32ab63c', offset=[85, -25]),
    'after_play': dict(file='ksnip_20260907-140233.png', size=[1131, 671],
        sha256='a4f02b53fa3dd633819f3759b80ac262093ed485eed3cd904e044fecb0681745', offset=[87, -25]),
    'demo': dict(file='ksnip_20260907-135348.png', size=[1130, 667],
        sha256='e607b24b1f70705cc1046387286450e4367a8f0fe48542694c662708fae894f1', offset=[86, -26]),
}


@contextmanager
def historical(version='v1'):
    """Hash-pinned historical compiler, independent of Git history or scratch."""
    fixture = FIXTURE if version == 'v1' else ROOT/'tests/fixtures/nfl2k5_scorebug_exact_v2.py'
    if version not in ('v1', 'v2'):
        raise ValueError('unknown historical scorebar')
    wanted = FIXTURE_SHA if version == 'v1' else V2_FIXTURE_SHA
    source = fixture.read_bytes()
    if hashlib.sha256(source).hexdigest() != wanted:
        raise ValueError('foreign '+version+' negative-control compiler')
    spec = importlib.util.spec_from_file_location('mod_editor.core._scorebug_'+version+'_control', fixture)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    with ExitStack() as stack:
        for name, value in (('exact', old), ('ANCHORS', old.ANCHORS), ('VERSION', old.VERSION)):
            stack.enter_context(mock.patch.object(scene, name, value))
        yield old


def calibration(name):
    row = WITNESSES[name]
    return dict(size=row['size'], affine=[1.5, 1.5, *row['offset']], gain=1.082, bias=-21.1,
        evidence='Frame rails and independent score/down glyphs; frame 37->19 and light cell 247->246.',
        limits='Empirical capture transform. The video-range/GPU/host-filter source is not isolated.')


def ink_box(image, box, *, bright=True):
    """Ignore ROI-edge background/rim components; never substitute reference ink."""
    import numpy as np
    a, b, c, d = map(int, box)
    rgb = np.asarray(image.convert('RGB'))[b:d, a:c]
    hit = rgb.min(axis=2) > 200 if bright else rgb.max(axis=2) < 85
    visited = np.zeros(hit.shape, dtype=bool)
    ink = []
    for y, x in np.argwhere(hit):
        if visited[y, x]:
            continue
        queue, component = [(int(y), int(x))], []
        visited[y, x] = True
        while queue:
            yy, xx = queue.pop(); component.append((yy, xx))
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = yy+dy, xx+dx
                if 0 <= ny < hit.shape[0] and 0 <= nx < hit.shape[1] and hit[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True; queue.append((ny, nx))
        if len(component) >= 3 and not any(y in (0, hit.shape[0]-1) or x in (0, hit.shape[1]-1) for y, x in component):
            ink.extend(component)
    if not ink:
        return None
    ys, xs = zip(*ink)
    return [a+min(xs), b+min(ys), a+max(xs)+1, b+max(ys)+1]


def render(build, output, *, compiler=exact, state='pre_snap', calibrated=None, **kwargs):
    """Compile actual fixed-span inputs and run native setup, frame and text."""
    mesh = compiler.mesh(build.retail_scene)
    span, _ = scene.layout.refit(build.spans['score_bug'], scene.serialize(mesh))
    decoded = scene.decode(span)[1]
    atlas, _ = scene.encode_atlas(build.spans['score_buga'], compiler.atlas())
    if compiler.VERSION.endswith('v1'):
        if scene.digest(span) != 'f6c7cdef8533ada1dd7ace770f93fd88807da8c1d8833c8bcd82ada6aab3c472':
            raise ValueError('v1 scene reconstruction changed')
        if scene.digest(atlas) != '031104a3c1d0d6b2fde3bcd988415f0187cc1f44d333df58298f33b76899cef8':
            raise ValueError('v1 atlas reconstruction changed')
    capture = {}
    geometry = projection.native_geometry(build.payload, decoded, fonts=build.fonts, texture_span=atlas,
        capture=capture, visible_elements=(), visibility_state='live' if state == 'demo' else state,
        identity=dict(home='NYG', away='WAS'), possession='away', game_seconds=300, play_seconds=22,
        ball_yards=35, **kwargs)
    try:
        geometry.update(projection.native_text_draw(capture))
        geometry.update(projection.render_native(decoded, atlas, build.fonts, geometry, output,
                                                  calibration=calibrated))
    finally:
        capture['machine'].close()
    geometry['resource_pins'] = dict(scene=scene.digest(span), atlas=scene.digest(atlas))
    return geometry


def measure(witness, before, name):
    # The same ROIs are used for measured and independently rendered ink.
    dx, dy = (v-u for u, v in zip(WITNESSES['pre_snap']['offset'], WITNESSES[name]['offset']))
    rois = {'away_score': [430, 590, 490, 637], 'home_score': [645, 590, 700, 635]}
    if name == 'pre_snap':
        rois.update(down=[509, 585, 617, 614], lower_row=[506, 617, 625, 649])
    elif name == 'after_play':
        # The defect physically joins the right score to the ball-on text.
        # Measure that connected cluster, not a falsely isolated score ROI.
        rois.pop('home_score')
        rois['overlap_cluster'] = [500, 585, 700, 638]
    rows = {}
    for label, box in rois.items():
        box = [box[0]+dx, box[1]+dy, box[2]+dx, box[3]+dy]
        want = ink_box(witness, box, bright=label != 'lower_row')
        got = ink_box(before, box, bright=label != 'lower_row')
        rows[label] = dict(roi=box, witness_ink_box=want, projected_ink_box=got,
            maximum_edge_error_px=None if want is None or got is None else max(abs(a-b) for a, b in zip(want, got)))
    return rows


def build_evidence(pack, xbe, output, *, disc=None):
    from PIL import Image, ImageDraw
    output.mkdir(parents=True, exist_ok=True)
    build = Build(pack, xbe)
    rows = {}
    crops = []
    try:
        for state, record in WITNESSES.items():
            source = ROOT / 'docs/scorebug_ingame/fix/witness' / record['file']
            if hashlib.sha256(source.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError('foreign gameplay witness: '+record['file'])
            with Image.open(source) as original:
                witness = original.convert('RGB')
            if list(witness.size) != record['size']:
                raise ValueError('gameplay capture dimensions changed')
            with historical() as old:
                before = render(build, output / (state+'_before.png'), compiler=old, state=state, calibrated=calibration(state))
            after = render(build, output / (state+'_after.png'), state=state, calibrated=calibration(state))
            with Image.open(output / (state+'_before.png')) as image:
                before_image = image.convert('RGB')
            with Image.open(output / (state+'_after.png')) as image:
                after_image = image.convert('RGB')
            measurements = measure(witness, before_image, state)
            rows[state] = dict(witness=record, calibration=calibration(state), ink=measurements,
                               before=before, after=after)
            x, y = record['offset']
            box = (x+207, y+604, x+750, y+684)
            crops.append([image.crop(box) for image in (witness, before_image, after_image)])
        sheet = Image.new('RGB', (3*553, 3*118+28), (28, 28, 28))
        draw = ImageDraw.Draw(sheet)
        for i, label in enumerate(('Noah gameplay witness', 'v1 calibrated native raster', 'v2 forecast: EXPERIMENTAL / UNWITNESSED')):
            draw.text((i*553+5, 7), label, fill='white')
        for j, (state, pictures) in enumerate(zip(WITNESSES, crops)):
            for i, picture in enumerate(pictures):
                draw.text((i*553+5, j*118+30), state.replace('_', ' '), fill='white')
                sheet.paste(picture, (i*553+5, j*118+47))
        sheet.save(output/'comparison.png')
        write_json(output/'calibration.json', dict(schema='nfl2k5_scorebug_witness/v1',
            experimental=True, fix_witnessed=False, baseline_fixture_sha256=FIXTURE_SHA,
            measurement_policy='One 1.5x viewport mapping per capture, no per-glyph placement or shape fit.',
            cases=rows))
        placements = []
        for runtime in (False, True):
            for wide in (False, True):
                for mode in (0, 1):
                    name = ('runtime' if runtime else 'static') + ('_wide' if wide else '_4x3') + f'_mode{mode}'
                    geometry = build.render(output/(name+'.png'), runtime=runtime, widescreen=wide, mode=mode)
                    failures = projection.containment_failures(geometry, geometry['frame'], .02)
                    if failures:
                        raise ValueError('native containment failed: '+name+' '+str(failures))
                    placements.append(dict(name=name, geometry=geometry))
        write_json(output/'placements.json', placements)
        receipts = projection.static_receipts(build.payload, build.spans)
        receipts['root_free_bytes'] = shutil.disk_usage(ROOT.anchor).free
        if disc is not None:
            with Path(disc).open('rb') as stream:
                jobs, receipt = scene.image_plan(stream.fileno(), os.fstat(stream.fileno()).st_size)
            receipts['retail_disc_preflight'] = dict(receipt=receipt, planned_writes=[
                dict(offset=offset, length=len(before), before_sha256=scene.digest(before),
                     after_sha256=scene.digest(after)) for offset, before, after in jobs])
        write_json(output/'receipts.json', receipts)
    finally:
        build.close()
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--extraction', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--disc', type=Path, help='Optional read-only disc preflight; never creates an image.')
    args = ap.parse_args()
    rows = build_evidence(args.extraction/'vc_53450030/0', args.extraction/'default.xbe',
                          args.output.resolve(), disc=args.disc)
    print(json.dumps({name: row['ink'] for name, row in rows.items()}, indent=2))


if __name__ == '__main__':
    main()
