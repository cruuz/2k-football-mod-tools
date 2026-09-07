"""EXPERIMENTAL / UNWITNESSED coordinated left-forearm axial length adjustment.

Counts, parents, names, weights and runtime rotations remain fixed. Both LODs
move together, including the high forearm twist pivots. Axial scaling preserves
the existing SKEL axes; those 400 bytes are pinned and retained, not guessed
from bone endpoints (they are not that table). Head and equipment need a played
witness. Each compressed member must fit its original span and scratch budget.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
from pathlib import Path
import struct

from . import nfl2k5_animation as A, nfl2k5_animation_math as Q, nfl2k5_models as M
from .nfl2k5_animation_import import SpanEdit, validate_spans, archive_guard, write_copy

BODY_PINS = {
    'o3c113': (25, 5065, 0x6f00, '2a89df4b2e83dee4c7937194e5cd885c4b3662720bf976d8440ab5c3fb423e56'),
    'o3c114': (62, 7396, 0x6a00, '43c95e150c72805b419e05db3cff6cacc69c56791c349caa2f0456782775893b'),
}
SKEL_SHA256 = 'c0892cd00a6819031c5cc6e7e4392548cc72e665e27f7dc14c928fc860feed3d'


@dataclass(frozen=True)
class BoneMember:
    key: str
    before: bytes
    after: bytes
    segments: tuple
    receipt: dict
    source: dict


@dataclass(frozen=True)
class BonePlan:
    members: tuple
    receipt: dict

    def status(self, payloads):
        A.require(set(payloads) == {m.key for m in self.members}, 'Coordinated limb members are incomplete')
        states = [A.Replacement(m.key, m.before, m.after, {}).status(payloads[m.key]) for m in self.members]
        changed = {s for s in states if s != 'unchanged'}
        A.require(not ('original' in changed and 'applied' in changed), 'Mixed low/high limb edit')
        return 'applied' if 'applied' in changed else 'original' if 'original' in changed else 'unchanged'

    def apply(self, payloads):
        state = self.status(payloads)
        return {m.key: m.after for m in self.members}, {**self.receipt, 'input_status': state}


def _bounds(points):
    return [[min(p[a] for p in points), max(p[a] for p in points)] for a in range(3)]


def _source_record(source, resource):
    return {'outer_index': resource.outer_index, 'outer_id': resource.outer_id, 'outer_size': resource.outer_size,
            'chunk_offset': resource.chunk_offset,
            'segments': [{'pack': s.pack_name, 'offset': s.pack_offset, 'length': s.size}
                         for s in source.archive_segments(resource)]}


def _body(source, key, scale):
    count, vertices, start, digest = BODY_PINS[key]
    resource, body, scene = source.parse(key)
    before = source.span(resource)
    A.require(A.sha256(body) == digest, f'{key}: body is not the pinned retail skeleton/geometry')
    A.require(len(scene['shapes']) == 1, 'Unexpected body shape count')
    shape = scene['shapes'][0]
    lanes = M._shape_lanes(scene, shape, body)
    A.require(lanes.transform_count == count and lanes.vertex_count == vertices and lanes.position_format == 'NORMSHORT3',
              'Body bone/vertex layout differs')
    actual_start = A._tool('nfl_scne_inventory').resolve_relative(body, lanes.record_offset+0x64, len(body), 'bind array')
    A.require(actual_start == start, 'Body bind array moved')
    skin = M.decode_skin(body, shape, lanes, scene['submeshes'])
    A.require(skin is not None and not skin.notes, 'Body skin has unresolved vertex ownership')
    positions = M.read_positions(body, shape, lanes)
    transforms = skin.transforms
    names = {t['name']: t['index'] for t in transforms}
    elbow, hand = names['lelbow'], names['lhand']
    pivot = transforms[elbow]['absolute']
    vector = tuple(b-a for a, b in zip(pivot, transforms[hand]['absolute']))
    length = math.sqrt(sum(v*v for v in vector))
    axis = tuple(v/length for v in vector)
    left = {t['index'] for t in transforms if t['name'] in ('lcollar', 'lhumerus', 'lelbow', 'lwrist', 'lhand')
            or t['name'].startswith(('l_forearm_', 'l_arm_', 'l_ulna_', 'l_radius_', 'l_triceps_', 'l_biceps_'))}
    output = bytearray(body)

    def distance(point):
        return sum((a-b)*c for a, b, c in zip(point, pivot, axis))

    def deform(point, weight=1.):
        along = max(0., min(length, distance(point)))
        return tuple(a+weight*(scale-1.)*along*b for a, b in zip(point, axis))

    absolutes, joints = [], []
    for t in transforms:
        # Scale each distal bind offset from the elbow. This preserves the
        # individual wrist/hand/twist directions, including their small retail
        # deviations from the overall elbow-to-hand axis.
        distal = t['name'] in ('lwrist','lhand') or t['name'].startswith('l_forearm_twist_')
        new = tuple(Q.f32(a+(b-a)*scale) for a,b in zip(pivot,t['absolute'])) if distal else t['absolute']
        absolutes.append(new)
    # Add the delta to the stored local offset, retaining the retail rounding residual.
    for t, absolute in zip(transforms, absolutes):
        i, parent = t['index'], t['parent']
        delta = tuple(a-b for a, b in zip(absolute, t['absolute']))
        parent_delta = tuple(a-b for a, b in zip(absolutes[parent], transforms[parent]['absolute'])) if parent >= 0 else (0.,)*3
        local = tuple(Q.f32(v+d-p) for v, d, p in zip(t['local'], delta, parent_delta))
        if absolute != t['absolute'] or local != t['local']:
            struct.pack_into('<3f', output, start+i*112+0x40, *absolute)
            struct.pack_into('<3f', output, start+i*112+0x50, *local)
            joints.append({'index': i, 'name': t['name'], 'absolute_before': t['absolute'], 'absolute_after': absolute,
                           'local_before': t['local'], 'local_after': local})
        expected = tuple(v+(absolutes[parent][a] if parent >= 0 else 0.) for a, v in enumerate(local))
        A.require(math.dist(expected, absolute) <= 1e-5, 'Local and absolute bind positions disagree')

    changed_vertices = changed_normals = 0
    base = M._stream_base(scene, shape, lanes.position_stream)
    for i, (point, influences) in enumerate(zip(positions, skin.influences)):
        A.require(all(0 <= w <= 1 for _, w in influences) and abs(sum(w for _, w in influences)-1) < 1e-5,
                  'Unsupported skin weights')
        weight = sum(w for j, w in influences if j in left)
        new = deform(point, weight)
        if new == point:
            continue
        encoded = tuple((v-o)/lanes.scale for v, o in zip(new, lanes.offset))
        A.require(all(-1 <= v <= 1 for v in encoded), 'Limb geometry exceeds the original native position bounds')
        at = base+i*lanes.position_stride+lanes.position_offset
        raw = struct.pack('<3h', *(M.encode_normshort(v) for v in encoded))
        if raw != body[at:at+6]:
            output[at:at+6] = raw
            changed_vertices += 1
        # Inverse transpose of the per-vertex axial deformation; skin weights stay authored.
        if lanes.normal and 0 < distance(point) < length and weight:
            at = lanes.stream_offsets[lanes.normal[0]]+i*lanes.normal[2]+lanes.normal[1]
            word = struct.unpack_from('<I', body, at)[0]
            normal = M._normalise(M.decode_normpacked3(word))
            dot = sum(v*a for v, a in zip(normal, axis))
            inverse_delta = 1/(1+weight*(scale-1))-1
            normal = M._normalise(tuple(v+inverse_delta*dot*a for v, a in zip(normal, axis)))
            edited = M.encode_normpacked3(*normal)
            if edited != word:
                struct.pack_into('<I', output, at, edited)
                changed_normals += 1
    # Range fields are conservative bounds as well as the vertex decoder. Verify
    # the deformed positions fit them; do not tighten/requantize unrelated vertices.
    after_positions = M.read_positions(bytes(output), shape, M._shape_lanes(scene, shape, output))
    if output == body:
        rebuilt, fit = before, {'unchanged': True, 'wrapper_identical': True}
    else:
        rebuilt, info = A._tool('nfl_vc_lz_fill').rebuild_fixed_span_filled(before, bytes(output), encoder='auto')
        fit = asdict(info)
    A.require(len(rebuilt) == len(before) and rebuilt[:32] == before[:32], 'Body span/scratch wrapper changed')
    A.require(source.decode_span(rebuilt, resource) == bytes(output), 'Body refit does not decode to the authored bytes')
    after_skin = M.decode_skin(bytes(output), shape, lanes, scene['submeshes'])
    A.require(after_skin.influences == skin.influences, 'Body weights changed')
    A.require([(t['name'], t['parent']) for t in after_skin.transforms] == [(t['name'], t['parent']) for t in transforms],
              'Body hierarchy changed')
    # At rest, T(-bind)*current(bind) is identity for every newly rebound joint.
    current = []
    for t in after_skin.transforms:
        parent = t['parent']
        current.append(tuple(v+(current[parent][a] if parent >= 0 else 0.) for a,v in enumerate(t['local'])))
    rest_error = max(math.dist(tuple(sum((p[a]-after_skin.transforms[j]['absolute'][a]+current[j][a])*w
                                         for j,w in inf) for a in range(3)), p)
                     for p, inf in zip(after_positions, after_skin.influences))
    A.require(rest_error <= 1e-4, 'Rest skin is inconsistent with the rebound geometry')
    receipt = {'key': key, 'bind_array_bytes': count*112, 'joints': joints,
               'vertices_changed': changed_vertices, 'normals_changed': changed_normals,
               'decoded_before_sha256': A.sha256(body), 'decoded_after_sha256': A.sha256(output),
               'decoded_write_spans': A._diff_spans(body, output), 'write_spans': A._diff_spans(before, rebuilt),
               'bounds_before_cm': _bounds(positions), 'bounds_after_cm': _bounds(after_positions),
               'native_position_bounds_retained': True, 'maximum_rest_skin_error_cm': rest_error,
               'forearm_length_before_cm': length, 'forearm_length_after_cm': math.dist(absolutes[elbow], absolutes[hand]),
               'fit': fit, 'morph_records_retained': True}
    return BoneMember(key, before, rebuilt, tuple(source.archive_segments(resource)), receipt, _source_record(source, resource))


def compile_limb(source, scale=1.01):
    A.require(type(scale) in (float, int) and math.isfinite(scale) and .98 <= scale <= 1.02,
              'Left forearm scale must be between 0.98 and 1.02')
    members = [_body(source, key, scale) for key in BODY_PINS]
    # The SKEL axes are independently authored normalized vectors, not low local offsets.
    _, resources = A._tool('nfl_scene_probe').parse_inventory(source.inventory_path)
    skel = next((r for r in resources if (r.outer_index, r.chunk_index) == (3, 116)), None)
    A.require(skel is not None, 'Coordinated limb requires SKEL 3/116')
    raw = source.span(skel)
    A.require(A.sha256(raw) == SKEL_SHA256, 'SKEL is not the pinned 25-vector resource')
    vectors = [struct.unpack_from('<4f', raw, 32+0x50+i*16) for i in range(25)]
    A.require(all(v[3] == 0 and abs(sum(x*x for x in v[:3])-1) < 1e-5 for v in vectors), 'SKEL axes differ')
    members.append(BoneMember('o3c116', raw, raw, tuple(source.archive_segments(skel)),
                              {'key': 'o3c116', 'axis_array_bytes': 400, 'write_spans': [],
                               'reason': 'Axial length adjustment retains the normalized SKEL direction data'}, _source_record(source, skel)))
    low, high = members[:2]
    A.require(abs(low.receipt['forearm_length_after_cm']-high.receipt['forearm_length_after_cm']) < 1e-5,
              'Low and high forearm endpoints disagree')
    receipt = {'schema': 'nfl2k5_animation_limb/v1', 'limb': 'left_forearm', 'scale': scale,
               'members': [m.receipt for m in members], 'preflight_passed': True,
               'experimental': True, 'witnessed': False, 'growth_bytes': 0,
               'retained': ['counts', 'parents', 'names', 'weights', 'SKEL axes', 'head', 'morph records'],
               'limits': ['No captured live body profiles or contact behavior',
                          'High derived rotations use the existing runtime; translated twist pivots are coordinated',
                          'Body morph displacements are retained; varied-profile appearance needs a witness']}
    return BonePlan(tuple(members), receipt)


def image_edits(plan, source_image):
    from . import platform_compat as io
    import os
    fd = os.open(source_image, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    try:
        size = os.fstat(fd).st_size
        packs = {name.upper(): entry for name, entry in M._xdvdfs_pack_entries(fd, size).items()}
        edits, current = [], {}
        for member in plan.members:
            spans, inner = [], 0
            for segment in member.segments:
                entry = packs.get(str(segment.pack_name))
                A.require(entry is not None and 0 <= segment.pack_offset <= entry.size-segment.size,
                          'Body member pack is absent or truncated')
                spans.append((entry.byte_offset+segment.pack_offset, inner, segment.size))
                inner += segment.size
            edit = SpanEdit(member.key, member.before, member.after, tuple(spans))
            edits.append(edit)
            current[member.key] = b''.join(io.pread(fd, n, off) for off, _, n in spans)
        edits.append(archive_guard(fd, packs, [(m.source, len(m.before)) for m in plan.members]))
        validate_spans(edits, size)
        plan.status(current)
        return tuple(edits)
    finally:
        os.close(fd)


def write_limb_copy(plan, source_image, destination):
    return write_copy(source_image, destination, image_edits(plan, source_image), receipt=plan.receipt)
