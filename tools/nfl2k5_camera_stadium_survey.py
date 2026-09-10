"""Offline Broadcast eye survey over Stadium Studio's private raw-coordinate exports.

Development-only dependency of nfl2k5_camera_broadcast_proof --survey-cache.
Geometry stays in memory; output contains measurements and source hashes only.
The baseline's winding, pixel centres, wall rectangle and 2% rule are retained.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from numba import njit

GRID_X = tuple(range(-2400, 2401, 300))
GRID_Z = tuple(range(-5400, 5401, 900))
VALUES = {
    'v5.2': ((400., 0., 250.), 80., (5250., 1650., 200.)),
    'v5.3': ((400., 0., 250.), 68., (4500., 1400., 200.)),
    'v5.4': ((400., 0., 250.), 68., (4500., 1400., 200.)),
}
IGNORE = set('yardfront yardside pylon CAMERA_DOLLY_CAMERA_DOLLY telex_lambert9 Bench_warm Bench_cold '
             'towels garbage drinks Ice_bags fence lambert4 lambert7 lambert8 lambert9 lambert2 Heater Fan '
             'kickingnet_lambert3 pushcart_lambert2 water_lambert2 table4_lambert4 gatorade_cups_lambert8 '
             'gatorade_jug_lambert7 trunk1_lambert2 towel_flat_lambert2 replayarea_lambert2 '
             'communications_lambert4 oxygen_tank_lambert9 foldingchair_lambert3 sideline_telex '
             'sideline_communications sideline_replay sideline_kicknet sideline_cameradolly sideline_gatorjug '
             'sideline_rail sideline_hamper4 sideline_gatorcooler sidelinePropsA2_lambert9'.split())


def eye_target(bx, bz, direction, revision):
    target, _, offset = VALUES[revision]
    look = np.array((bx + target[0], target[1], bz + direction * target[2]))
    eye = look + np.array((offset[0], offset[1], direction * offset[2]))
    if revision == 'v5.4':
        eye[0] = min(eye[0], 5600.)
        eye[2] = np.clip(eye[2], -5500., 5500.)
    return eye, look


def basis_and_fov(eye, target, lens):
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, (0., 1., 0.))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    # Native 16:9 lens-80 projection, measured by the pinned CPU projector.
    tx = math.tan(math.radians(33.39848846798724) / 2) * 80 / lens
    ty = math.tan(math.radians(21.887248901135568) / 2) * 80 / lens
    return forward, right, up, tx, ty


def load_triangles(path):
    raw = path.read_bytes()
    doc = json.loads(raw)
    if not doc.get('extras', {}).get('raw_coordinates'):
        raise ValueError(f'{path.name}: expected raw Xbox coordinates')
    buffers = []
    hashes = {path.name: hashlib.sha256(raw).hexdigest()}
    for spec in doc['buffers']:
        source = (path.parent / spec['uri']).resolve()
        if source.parent != path.parent.resolve():
            raise ValueError('survey buffer must be a sibling of its glTF')
        data = source.read_bytes()
        buffers.append(data)
        hashes[source.name] = hashlib.sha256(data).hexdigest()

    def accessor(index):
        a = doc['accessors'][index]
        v = doc['bufferViews'][a['bufferView']]
        dt = np.dtype({5121: '<u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[a['componentType']])
        count = {'SCALAR': 1, 'VEC3': 3}[a['type']]
        return np.ndarray((a['count'], count), dtype=dt, buffer=buffers[v['buffer']],
                          offset=v.get('byteOffset', 0) + a.get('byteOffset', 0),
                          strides=(v.get('byteStride', dt.itemsize * count), dt.itemsize))

    triangles, labels = [], []
    for node in doc['nodes']:
        if any(key in node for key in ('matrix', 'translation', 'rotation', 'scale', 'children')):
            raise ValueError('raw-coordinate survey cannot assume node transforms')
        if 'mesh' not in node:
            continue
        for p in doc['meshes'][node['mesh']]['primitives']:
            pos = accessor(p['attributes']['POSITION']).astype(np.float64)
            idx = accessor(p['indices'])[:, 0].astype(np.int64) if 'indices' in p else np.arange(len(pos))
            mode = p.get('mode', 4)
            if mode == 4:
                faces = idx.reshape(-1, 3)
            elif mode == 5:
                faces = np.column_stack((idx[:-2], idx[1:-1], idx[2:]))
                faces[1::2, :2] = faces[1::2, 1::-1]
            elif mode == 6:
                faces = np.column_stack((np.full(len(idx)-2, idx[0]), idx[1:-1], idx[2:]))
            else:
                continue
            tri = pos[faces]
            normals = np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0])
            tri = tri[(np.linalg.norm(normals, axis=1) > 1e-6) & (np.abs(tri[:, :, 1]).max(1) > 1.)]
            material = p['extras']['source_material_name']
            triangles.append(tri)
            labels.extend([material not in IGNORE] * len(tri))
    return np.concatenate(triangles), np.array(labels, dtype=np.bool_), hashes


def bvh(tri, labels):
    """Median-split acceleration only; intersection/winding stay exact."""
    low, high, nodes, order = [], [], [], []
    lo, hi = tri.min(1), tri.max(1)
    centres = (lo + hi) / 2

    def split(ids):
        n = len(nodes)
        low.append(lo[ids].min(0)); high.append(hi[ids].max(0)); nodes.append(None)
        if len(ids) <= 12:
            nodes[n] = (-1, -1, len(order), len(ids))
            order.extend(ids)
        else:
            axis = np.ptp(centres[ids], axis=0).argmax()
            ids = ids[np.argsort(centres[ids, axis], kind='stable')]
            middle = len(ids) // 2
            nodes[n] = (split(ids[:middle]), split(ids[middle:]), 0, 0)
        return n

    split(np.arange(len(tri)))
    return (np.ascontiguousarray(tri[order]), np.ascontiguousarray(labels[order]),
            np.array(low), np.array(high), np.array(nodes, dtype=np.int64))


@njit(cache=True)
def cast(eye, rays, depths, tri, labels, lo, hi, nodes):
    hits = np.zeros(len(rays), dtype=np.bool_)
    for k in range(len(rays)):
        direction = rays[k]
        best, label = depths[k] - 1., False
        stack = np.empty(64, dtype=np.int64)
        stack[0], count = 0, 1
        while count:
            count -= 1
            n = stack[count]
            near, far = 0., best
            for axis in range(3):
                if abs(direction[axis]) < 1e-15:
                    if eye[axis] < lo[n, axis] or eye[axis] > hi[n, axis]:
                        far = -1.
                        break
                else:
                    a = (lo[n, axis] - eye[axis]) / direction[axis]
                    b = (hi[n, axis] - eye[axis]) / direction[axis]
                    near, far = max(near, min(a, b)), min(far, max(a, b))
            if near > far:
                continue
            left, right, start, size = nodes[n]
            if left >= 0:
                stack[count], stack[count + 1] = left, right
                count += 2
                continue
            for j in range(start, start + size):
                ax, ay, az = tri[j, 0]
                e1x, e1y, e1z = tri[j, 1] - tri[j, 0]
                e2x, e2y, e2z = tri[j, 2] - tri[j, 0]
                dx, dy, dz = direction
                px, py, pz = dy*e2z-dz*e2y, dz*e2x-dx*e2z, dx*e2y-dy*e2x
                det = e1x*px + e1y*py + e1z*pz
                # Same det < 0 side as the prior raw-Xbox stadium survey.
                # det = -dot(ray, cross(e1, e2)); do not reverse exported winding.
                if det >= -1e-9:
                    continue
                tx, ty, tz = eye[0]-ax, eye[1]-ay, eye[2]-az
                u = (tx*px + ty*py + tz*pz) / det
                if u < 0. or u > 1.:
                    continue
                qx, qy, qz = ty*e1z-tz*e1y, tz*e1x-tx*e1z, tx*e1y-ty*e1x
                v = (dx*qx + dy*qy + dz*qz) / det
                if v < 0. or u + v > 1.:
                    continue
                distance = (e2x*qx + e2y*qy + e2z*qz) / det
                if 1e-3 < distance < best:
                    best, label = distance, labels[j]
        hits[k] = label
    return hits


def frame(tree, eye, target, lens):
    f, r, u, tx, ty = basis_and_fov(eye, target, lens)
    gx, gy = np.meshgrid((np.arange(96)+.5)/96*640, (np.arange(72)+.5)/72*480)
    rays = (f + ((gx.ravel()-320)/320*tx)[:, None]*r
            + ((240-gy.ravel())/240*ty)[:, None]*u)
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    with np.errstate(divide='ignore', invalid='ignore'):
        depth = np.where(rays[:, 1] < 0, -eye[1]/rays[:, 1], np.inf)
    hit = eye + rays * np.where(np.isfinite(depth), depth, 0)[:, None]
    onfield = np.isfinite(depth) & (np.abs(hit[:, 0]) <= 2810.) & (np.abs(hit[:, 2]) <= 5900.)
    count = int(onfield.sum())
    occluded = int(cast(eye, np.ascontiguousarray(rays[onfield]), depth[onfield], *tree).sum())
    return count, occluded


def summarize(rows):
    result = {}
    for name, limit in (('whole_grid', 2400), ('between_numbers', 1350), ('between_hashes', 600)):
        subset = [r for r in rows if abs(r['bx']) <= limit]
        dirty = sum(r['occluded_pixels'] > .02*r['field_pixels'] for r in subset)
        result[name] = dict(frames=len(subset), dirty_frames=dirty, dirty_percent=100*dirty/len(subset))
    return result


def survey_model(path):
    tri, labels, hashes = load_triangles(Path(path))
    tree = bvh(tri, labels)
    cases = {}
    for revision, values in VALUES.items():
        rows = []
        for direction in (1, -1):
            for bz in GRID_Z:
                for bx in GRID_X:
                    eye, target = eye_target(bx, bz, direction, revision)
                    field, occluded = frame(tree, eye, target, values[1])
                    rows.append(dict(direction=direction, bx=bx, bz=bz,
                                     field_pixels=field, occluded_pixels=occluded))
        cases[revision] = summarize(rows)
    return dict(scene=Path(path).stem, triangles=len(tri), source_sha256=hashes, revisions=cases)


def survey(cache, *, workers=4):
    models = []
    for outer in range(3136, 3189):
        choices = sorted((Path(cache)/'models').glob(f'{outer}_*_stadium.gltf'))
        if len(choices) != 1:
            raise ValueError(f'expected one model for scene {outer}, found {len(choices)}')
        models.append(choices[0])
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(survey_model, models):
            rows.append(row)
            print(f"survey {len(rows)}/53 {row['scene']}: "
                  f"v5.4 {row['revisions']['v5.4']['between_numbers']['dirty_percent']:.2f}% between numbers", flush=True)
    totals = {}
    for revision in VALUES:
        totals[revision] = {}
        for band in rows[0]['revisions'][revision]:
            frames = sum(r['revisions'][revision][band]['frames'] for r in rows)
            dirty = sum(r['revisions'][revision][band]['dirty_frames'] for r in rows)
            totals[revision][band] = dict(frames=frames, dirty_frames=dirty, dirty_percent=100*dirty/frames)
    return dict(schema='nfl2k5_camera_stadium_survey/v1', runtime_witnessed=False,
                method='96x72 pixel centres; nearest det<0 raw-Xbox triangle; >2% of wall-rectangle ground pixels',
                limitations='Static opaque geometry; no GPU, texture alpha, near-plane clipping or moving-camera guarantee. '
                            'Counts every ignored prop material, without the historical top-six reporting truncation.',
                grid_x=GRID_X, grid_z=GRID_Z, directions=[1, -1], wall_rectangle_cm=[2810, 5900],
                band_limits_cm=dict(whole_grid=2400, between_numbers=1350, between_hashes=600),
                eye_clamp_cm=dict(max_x=5600, min_z=-5500, max_z=5500),
                ignored_materials=sorted(IGNORE), totals=totals, models=rows)
