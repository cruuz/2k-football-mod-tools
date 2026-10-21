#!/usr/bin/env python3
"""PROTOTYPE only: preview a raised pants color boundary without changing a disc.

Requires the existing authoring environment (numpy, Pillow, Blender). Supply
--disc, --sha256 and a NEW --out directory outside the repo and disc directory.
Example: python3 tools/b77/pt0_pants_preview.py --disc BASE.iso --sha256 HASH \
    --out SCRATCH/preview --fraction 0.46

Uses native hi/lo_body bind poses, averages their horizontal-cut UV contours,
and extends each kit's upper 1/8 sock texture over the lower pants. Matching
pants/sock cuff vertices register the circumference. This is mechanical test
imagery, not production art. No geometry, UV, bump, mip or game bytes are edited.
Raw exports and unlabeled intermediate images live only in a temporary folder.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from pt0_pants_probe import (models, Disc, chunks, digest, identity, triangles,
                             texture_records, logical_name_candidates, write_json, sha)

KITS = {'18H0': 'NYG home', '01A0': 'ATL away', '06H0': 'CIN home'}
VIEWS = [('front', 0), ('side', 90), ('back', 180)]


def geometry(source, key):
    _, decoded, scene = source.parse(key)
    shape = scene['shapes'][0]
    lanes = models._shape_lanes(scene, shape, decoded)
    pos = np.asarray(models.read_positions(decoded, shape, lanes))
    pairs = models.read_lane_2h(decoded, shape, lanes.texcoord, lanes.vertex_count)
    uv = np.asarray([models.uv_to_gltf(*p, lanes.uv_scale, lanes.uv_offset) for p in pairs])
    subs = [s for s in scene['submeshes'] if s['shape_index'] == shape['index']]
    skin = models.decode_skin(decoded, shape, lanes, subs)
    bones = {t['name']: t['absolute'] for t in skin.transforms}
    surfaces = {name: np.asarray([t for s in subs if s['material_name'] == name
                                 for t in triangles(decoded, s)], dtype=int)
                for name in ('UNIF_pants', 'SOCKS')}
    return dict(pos=pos, uv=uv, surfaces=surfaces, hip=bones['lfemur'][1],
                length=bones['lfemur'][1] - bones['lfoot'][1])


def cut_segments(pos, uv, tris, y):
    """Intersect triangles with native horizontal plane, returning UV segments."""
    segments = []
    for tri in tris:
        points = []
        for a, b in zip(tri, np.roll(tri, -1)):
            ya, yb = pos[a, 1], pos[b, 1]
            if (ya <= y < yb) or (yb <= y < ya):
                t = (y - ya) / (yb - ya)
                p = uv[a] + t * (uv[b] - uv[a])
                if not any(np.allclose(p, q, atol=1e-10, rtol=0) for q in points):
                    points.append(p)
        if len(points) == 2 and abs(points[1][0] - points[0][0]) > 1e-10:
            segments.append(points)
    if not segments:
        raise ValueError('Cut does not intersect the pants')
    return np.asarray(segments)


def common_contour(segment_sets):
    """Mean of both LOD curves over their shared U extent, retaining all knots."""
    lo = max(s[:, :, 0].min() for s in segment_sets)
    hi = min(s[:, :, 0].max() for s in segment_sets)
    knots = sorted({float(u) for s in segment_sets for u in s[:, :, 0].flat if lo <= u <= hi})
    result = []
    for u in knots:
        values = []
        for segments in segment_sets:
            vs = [a[1] + (u-a[0]) / (b[0]-a[0]) * (b[1]-a[1]) for a, b in segments
                  if min(a[0], b[0])-1e-9 <= u <= max(a[0], b[0])+1e-9]
            if not vs:
                raise ValueError('Gap in LOD contour')
            values.append(float(np.mean(vs)))
        result.append([u, float(np.mean(values))])
    if len(result) < 2:
        raise ValueError('No common LOD contour')
    return np.asarray(result)


def cuff_registration(g):
    """Find coincident pants/sock vertices; unwrap sock U across its seam."""
    pants = np.unique(g['surfaces']['UNIF_pants'])
    socks = np.unique(g['surfaces']['SOCKS'])
    socks = socks[g['uv'][socks, 1] < .02]
    if not len(socks):
        raise ValueError('No upper sock vertices')
    rows = []
    for i in pants:
        distances = np.linalg.norm(g['pos'][socks] - g['pos'][i], axis=1)
        j = int(np.argmin(distances))
        if distances[j] < .01:
            rows.append([*g['uv'][i], g['uv'][socks[j], 0]])
    rows = np.asarray(sorted(set(map(tuple, rows))))
    if len(rows) < 8:
        raise ValueError('Too few matching pants/sock cuff vertices')
    rows[:, 2] = np.unwrap(rows[:, 2] * 2*np.pi) / (2*np.pi)
    if np.any(np.diff(rows[:, 0]) <= 0):
        raise ValueError('Ambiguous cuff registration')
    return rows


def recolor(pants, socks, contour, registration):
    """Copy upper-sock RGB below contour; preserve alpha and every pixel above."""
    if pants.ndim != 3 or pants.shape[2] != 4 or socks.ndim != 3 or socks.shape[2] != 4:
        raise ValueError('RGBA images required')
    h, w = pants.shape[:2]
    sh, sw = socks.shape[:2]
    u = (np.arange(w) + .5) / w
    v = (np.arange(h) + .5)[:, None] / h
    hem = np.interp(u, contour[:, 0], contour[:, 1])
    cuff = np.interp(u, registration[:, 0], registration[:, 1])
    if np.any(cuff <= hem):
        raise ValueError('Target must be above the physical cuff on both legs')
    sock_u = np.interp(u, registration[:, 0], registration[:, 2]) % 1
    # The cuff joins sock row 0. The raised edge samples row 7 on a 64px sock.
    sy = (1 - np.clip((v - hem) / (cuff - hem), 0, 1)) * (max(1, sh//8) - 1)
    sx = sock_u * sw - .5
    x0 = np.floor(sx).astype(int)
    y0 = np.floor(sy).astype(int)
    fx, fy = (sx-x0)[None, :, None], (sy-y0)[:, :, None]
    top = socks[y0, x0 % sw, :3]*(1-fx) + socks[y0, (x0+1) % sw, :3]*fx
    bottom = socks[np.minimum(y0+1, sh-1), x0 % sw, :3]*(1-fx) + socks[np.minimum(y0+1, sh-1), (x0+1) % sw, :3]*fx
    rgb = np.rint(top*(1-fy) + bottom*fy).astype(np.uint8)
    mask = v >= hem
    result = pants.copy()
    result[:, :, :3][mask] = rgb[mask]
    return result, mask


def comparison(images, title, labels):
    """Every delivered image carries an inseparable PROTOTYPE banner."""
    width, height = sum(im.width for im in images), max(im.height for im in images)
    canvas = Image.new('RGB', (width, height+100), (38, 42, 47))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('DejaVuSans.ttf', 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text((12, 10), 'PROTOTYPE | not final art | Opus authors the real textures', font=font, fill='white')
    draw.text((12, 38), title, font=font, fill='white')
    x = 0
    for im, label in zip(images, labels):
        draw.text((x+12, 70), label, font=font, fill='white')
        canvas.paste(im, (x, 100), im if im.mode == 'RGBA' else None)
        x += im.width
    return canvas


def validate_output(out, disc):
    out, disc = out.resolve(), disc.resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError('Private previews must be outside the repository')
    if out == disc.parent or disc.parent in out.parents or out in disc.parents:
        raise ValueError('Output must be separate from the source disc directory')
    if out.exists():
        raise ValueError('Output directory must be new')
    return out


def run(args):
    if not np.isfinite(args.fraction) or not .35 <= args.fraction <= .49:
        raise ValueError('Prototype fraction must be between 0.35 and 0.49')
    out = validate_output(args.out, args.disc)
    blender = shutil.which(args.blender)
    if not blender:
        raise ValueError('Blender executable not found')
    before = identity(args.disc)
    report = dict(schema='pt0_pants_preview/v1', status='PROTOTYPE, not final art',
                  fraction=args.fraction, source=str(args.disc.resolve()), kits=[], images=[],
                  geometry_edits=0, disc_write_bytes=0, runtime_witnessed=False)
    with Disc(args.disc, descriptors=()) as disc:
        report['source_sha256_before'] = digest(disc.read, disc.image_size)
        if report['source_sha256_before'] != args.sha256.lower():
            raise ValueError('Source disc hash mismatch')
        print('source_sha256', report['source_sha256_before'], flush=True)
        entry = disc.archive_entries[3]
        raw = disc.read_entry_range(entry, 0, entry.size)
        spans = {f'o3c{i}': r for i, _, r in chunks(raw) if i in (113, 114)}
        source = models.ModelSpanSource(spans)
        geos = {lod: geometry(source, key) for lod, key in [('hi', 'o3c114'), ('lo', 'o3c113')]}
        contour = common_contour([cut_segments(g['pos'], g['uv'], g['surfaces']['UNIF_pants'],
                                                g['hip']-args.fraction*g['length']) for g in geos.values()])
        registration = cuff_registration(geos['hi'])
        report.update(common_contour_uv=contour.tolist(), cuff_registration=registration.tolist(),
                      source_model_span_sha256={k: sha(v) for k, v in spans.items()})
        out.mkdir(parents=True)
        with tempfile.TemporaryDirectory(prefix='.intermediate-', dir=out) as temp:
            tmp = Path(temp)
            textures = {}
            names = logical_name_candidates()
            for entry in disc.archive_entries:
                logical = names.get(entry.name_id)
                kit = logical.name.removesuffix('.IFF') if logical else None
                if kit not in KITS:
                    continue
                data = disc.read_entry_range(entry, 0, entry.size)
                pixels = {}
                for i, _, raw in chunks(data):
                    if i not in (2, 4):
                        continue
                    _, records = texture_records(raw, i, include_pixels=True)
                    for tex, rgba in records:
                        if tex['name'] in ('pants00', 'socks00'):
                            pixels[tex['name']] = np.frombuffer(rgba, dtype=np.uint8).reshape(tex['height'], tex['width'], 4)
                pants, socks = pixels['pants00'], pixels['socks00']
                after, mask = recolor(pants, socks, contour, registration)
                row = dict(kit=kit, name=KITS[kit], selected_pixels=int(mask.sum()),
                           changed_rgb_pixels=int(np.any(after[:, :, :3] != pants[:, :, :3], axis=2).sum()),
                           changed_pixels_above_contour=int(np.any(after[~mask] != pants[~mask], axis=1).sum()),
                           changed_alpha_pixels=int(np.count_nonzero(after[:, :, 3] != pants[:, :, 3])),
                           source_pants_rgba_sha256=sha(pants.tobytes()), source_sock_rgba_sha256=sha(socks.tobytes()),
                           prototype_pants_rgba_sha256=sha(after.tobytes()), upper_sock_rows=[0, max(1, socks.shape[0]//8)-1])
                report['kits'].append(row)
                textures[kit] = {}
                for name, array in [('before', pants), ('after', after), ('socks', socks)]:
                    p = tmp/f'{kit}_{name}.png'
                    Image.fromarray(array).save(p)
                    textures[kit][name] = str(p)
                p = out/f'{kit}_atlas_PROTOTYPE.png'
                comparison([Image.fromarray(pants), Image.fromarray(after)],
                           f'{KITS[kit]} ({kit}) | common f={args.fraction:.3f} | native 512 x 256 atlas',
                           ['Source pants', 'Mechanical upper-sock extension']).save(p)
                report['images'].append(p.name)
                print(kit, 'changed_rgb_pixels', row['changed_rgb_pixels'], 'above_contour', row['changed_pixels_above_contour'], 'alpha', row['changed_alpha_pixels'], flush=True)
            if set(textures) != set(KITS):
                raise ValueError('Missing requested kit')
            for lod, key in [('hi', 'o3c114'), ('lo', 'o3c113')]:
                body = tmp/f'{lod}.gltf'
                models.export_model(source, key, body)
                gltf = json.loads(body.read_text(encoding='utf-8'))
                hide = [m['name'] for m in gltf['materials'] if m['name'] not in ('UNIF_pants', 'SOCKS', 'SHOE_L', 'SHOE_R')]
                items = []
                for kit, paths in textures.items():
                    for version in ('before', 'after'):
                        views = [dict(yaw=yaw, pitch=0, dist=3.4, fov=23, target=[0, 0, -.5],
                                      size=[640, 800], parts='body', samples=24,
                                      out=str(tmp/f'{lod}_{kit}_{view}_{version}.png')) for view, yaw in VIEWS]
                        items.append(dict(tex={'UNIF_pants': paths[version], 'SOCKS': paths['socks']},
                                          hide=hide, shoe=[25, 25, 25], views=views))
                job = tmp/f'{lod}_job.json'
                write_json(job, dict(body=str(body), items=items))
                command = [blender, '-b', '-t', '4', '--python-exit-code', '1', '-P',
                           str(ROOT/'tools/b765/u1_blender.py'), '--', str(job)]
                with (out/f'{lod}_blender.log').open('w', encoding='utf-8', newline='\n') as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                for kit in KITS:
                    for view, _ in VIEWS:
                        images = [Image.open(tmp/f'{lod}_{kit}_{view}_{v}.png').convert('RGBA') for v in ('before', 'after')]
                        p = out/f'{kit}_{lod}_{view}_PROTOTYPE.png'
                        comparison(images, f'{KITS[kit]} ({kit}) | {lod}_body | {view} | common f={args.fraction:.3f}',
                                   ['Source texture', 'Mechanical prototype | same geometry']).save(p)
                        report['images'].append(p.name)
                print(lod+'_body', 'rendered 18 views; delivered 9 labeled comparisons', flush=True)
        report['source_sha256_after'] = digest(disc.read, disc.image_size)
    report['source_identity_unchanged'] = identity(args.disc) == before
    if not report['source_identity_unchanged'] or report['source_sha256_after'] != report['source_sha256_before']:
        raise RuntimeError('Source changed during preview')
    report['temporary_exports_removed'] = not any(out.glob('.intermediate-*'))
    write_json(out/'receipt.json', report)
    print('labeled_PNGs', len(report['images']), flush=True)
    print('source_sha256_unchanged True; disc_write_bytes 0; geometry_edits 0', flush=True)
    print('temporary_exports_removed', report['temporary_exports_removed'], flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--disc', required=True, type=Path)
    p.add_argument('--sha256', required=True)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--fraction', type=float, default=.46)
    p.add_argument('--blender', default='blender')
    run(p.parse_args())
