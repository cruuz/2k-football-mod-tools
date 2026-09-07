"""EXPERIMENTAL / UNWITNESSED fixed-channel glTF import and output-copy transport.

primary.gltf contains only pre-mirror, pre-derived rotation channels at native
sample times, including samples past controller duration. animation.gltf remains
an inspection bake. No external buffers, resampling, retiming or new identities.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from bisect import bisect_right
import json
import hashlib
import math
import os
from pathlib import Path
import shutil
import struct
import tempfile

from . import nfl2k5_animation as A, nfl2k5_animation_math as Q, platform_compat as io

require = A.require
MAX_FILE = 64 * 1024 * 1024


def primary_files(clip):
    require(clip.kind in ('SMCD', 'XBE_ROOT') and len(clip.roots) == 1, 'Only single roots accept import')
    r = clip.roots[0]
    require(r.frames * r.channels <= 262144, 'Clip exceeds the native authoring budget')
    times = [Q.f32(i / (r.rate * r.multiplier)) for i in range(r.frames)]
    require(all(a < b for a, b in zip(times, times[1:])), 'Native times are not distinct float32 values')
    binary = bytearray(struct.pack(f'<{len(times)}f', *times))
    doc = {'asset': {'version': '2.0', 'generator': '2K5 native primary channels'},
           'scene': 0, 'scenes': [{'nodes': list(range(r.channels))}],
           'nodes': [{'name': f'primary_{i}', 'extras': {'packed_channel': i}} for i in range(r.channels)],
           'buffers': [], 'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary)}],
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': r.frames, 'type': 'SCALAR',
                          'min': [times[0]], 'max': [times[-1]]}],
           'animations': [{'name': clip.name, 'channels': [], 'samplers': []}],
           'extras': {'schema': 'nfl2k5_primary_gltf/v1', 'identity': clip.identity,
                      'source_sha256': A.sha256(clip.original), 'native_sidecar': 'animation.native.json',
                      'duration_seconds': r.duration, 'map_id': clip.map_id,
                      'space': 'primary packed channels before mirroring and derived joints'}}
    keys = A.native_rotations(clip)
    for channel in range(r.channels):
        offset = len(binary)
        for frame in keys:
            w, x, y, z = Q.unit(frame[channel])
            binary.extend(struct.pack('<4f', x, y, z, w))
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': r.frames * 16})
        doc['accessors'].append({'bufferView': channel + 1, 'componentType': 5126,
                                 'count': r.frames, 'type': 'VEC4'})
        doc['animations'][0]['samplers'].append({'input': 0, 'output': channel + 1, 'interpolation': 'LINEAR'})
        doc['animations'][0]['channels'].append({'sampler': channel, 'target': {'node': channel, 'path': 'rotation'}})
    doc['buffers'] = [{'uri': 'primary.bin', 'byteLength': len(binary)}]
    return {'primary.gltf': A._json(doc), 'primary.bin': bytes(binary)}


def _read(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_FILE + 1)
    require(len(data) <= MAX_FILE, 'Import file exceeds 64 MiB')
    return data


def _document(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f'Duplicate JSON field: {key}')
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(A.AnimationError('Nonfinite JSON number')))
    except (ValueError, UnicodeError) as exc:
        raise A.AnimationError(f'Invalid import JSON: {exc}') from exc


def _angle(a, b):
    a, b = Q.unit(a), Q.unit(b)
    return math.degrees(2 * math.acos(min(1., abs(sum(x * y for x, y in zip(a, b))))))


def _slerp(a, b, t):
    a, b = Q.unit(a), Q.unit(b)
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-v for v in b), -dot
    if dot > .9995:
        return Q.unit(tuple(x * (1-t) + y*t for x, y in zip(a, b)))
    angle = math.acos(min(1., dot))
    return tuple((x * math.sin((1-t)*angle) + y * math.sin(t*angle)) / math.sin(angle) for x, y in zip(a, b))


def _requested_pose(clip, keys, seconds, flags, *, standard=False):
    r = clip.roots[0]
    seconds = Q.f32(seconds)
    if flags & 1:
        while seconds >= r.duration:
            seconds = Q.f32(seconds-r.duration)
    coordinate = Q.f32(Q.f32(r.rate*seconds)*r.multiplier)
    left = min(int(coordinate), r.frames-1)
    right = min(left+1, r.frames-1)
    factor = Q.f32(coordinate-left) if left != right else 0.
    if standard:
        times = [Q.f32(i/(r.rate*r.multiplier)) for i in range(r.frames)]
        left = max(0, min(bisect_right(times, seconds)-1, r.frames-1))
        right = min(left+1, r.frames-1)
        factor = max(0., (seconds-times[left])/(times[right]-times[left])) if left != right else 0.
    mapping = {'referee': Q.REF_MAP, 'player': Q.PLAYER_MAP}.get(clip.family)
    output = []
    for joint in range(25 if mapping else r.channels):
        channel = mapping[2*joint + bool(flags & 4)] if mapping else joint
        if channel < 0:
            output.append((1., 0., 0., 0.))
            continue
        a, b = keys[left][channel], keys[right][channel]
        q = a if left == right else (_slerp(a, b, factor) if standard else Q.interpolate(a, b, factor))
        if flags & 4:
            q = (q[0], q[1], -q[2], -q[3])
        output.append(q)
    return Q.complete_pose(output, clip.family) if mapping else tuple(output)


def pose_preflight(clip, replacement, keys):
    """Bounded sampled comparison, never a continuous or gameplay guarantee."""
    r = clip.roots[0]
    body = replacement.after if clip.kind == 'XBE_ROOT' else replacement.after[32:]
    edited = replace(clip, original=replacement.after, body=body)
    times = {i / (4*r.rate*r.multiplier) for i in range(4*r.frames-3)}
    times.update((0., max(0., r.duration-1e-6), r.duration, r.duration+1e-6,
                  r.duration*2+.001, r.duration*3))
    maximum = standard_max = comparisons = 0
    for mode in (0, 1, 4, 5):
        flags = (r.flags & ~5) | mode
        variant = replace(edited, roots=(replace(r, flags=flags),))
        for t in sorted(times):
            actual = A.sample_pose(variant, t)
            expected = _requested_pose(clip, keys, t, flags)
            standard = _requested_pose(clip, keys, t, flags, standard=True)
            for a, b, c in zip(actual, expected, standard):
                maximum = max(maximum, _angle(a, b))
                standard_max = max(standard_max, _angle(a, c))
                comparisons += 1
    require(maximum <= .75, f'Decoded pose error {maximum:.6f} degrees exceeds 0.75')
    require(standard_max <= 1., f'glTF/native sampled pose error {standard_max:.6f} degrees exceeds 1.0')
    return {'passed': True, 'joint_comparisons': comparisons, 'maximum_native_degrees': maximum,
            'maximum_gltf_degrees': standard_max, 'native_limit_degrees': .75, 'gltf_limit_degrees': 1.,
            'samples': 'native frames, quarter/half/three-quarter intervals, mirror/loop/end and repeated loops',
            'mapped_skeleton': clip.family if clip.map_id else None, 'continuous_error_bound': None}


@dataclass(frozen=True)
class ImportPlan:
    clip: A.Clip
    replacement: A.Replacement
    receipt: dict
    bundle_hashes: dict


def compile_import(clip, gltf_path, skeleton=None):
    path = Path(gltf_path).resolve()
    require(path.name == 'primary.gltf', 'Choose primary.gltf from a native export bundle')
    require(clip.kind != 'MMCD', 'Paired and multi-root animation import is disabled')
    raw = {name: _read(path.parent/name) for name in ('primary.gltf', 'primary.bin', 'animation.native.json')}
    doc, sidecar = _document(raw['primary.gltf']), _document(raw['animation.native.json'])
    A.verify_sidecar(sidecar, clip)
    require(sidecar.get('skeleton') == skeleton, 'Source skeleton differs from the native sidecar')
    expected = primary_files(clip)
    require(doc == _document(expected['primary.gltf']), 'Fixed glTF structure, identity, channels or timing changed')
    hashes = sidecar.get('export_hashes', {})
    require(all(hashes.get(name) == A.sha256(data) for name, data in expected.items()),
            'Native sidecar authoring hashes differ from a fresh source export')
    data = raw['primary.bin']
    require(len(data) == len(expected['primary.bin']), 'Native frame/channel buffer length changed')
    r = clip.roots[0]
    require(data[:r.frames*4] == expected['primary.bin'][:r.frames*4], 'Native frame times changed')
    keys = A.native_rotations(clip)
    for channel in range(r.channels):
        for frame in range(r.frames):
            x, y, z, w = struct.unpack_from('<4f', data, 4*r.frames+16*(channel*r.frames+frame))
            q = (w, x, y, z)
            require(all(math.isfinite(v) for v in q) and abs(sum(v*v for v in q)-1.) <= 2e-4,
                    f'Frame {frame+1}, channel {channel}: glTF rotation must be finite and unit length')
            # Retain decoded float32 values when sign-equivalent, for native identity and interpolation.
            if _angle(keys[frame][channel], q) > .00003:
                keys[frame][channel] = Q.unit(q)
    replacement = A.compile_replacement(clip, keys)
    comparison = pose_preflight(clip, replacement, keys)
    receipt = {**replacement.receipt, 'schema': 'nfl2k5_animation_import/v1', 'pose_preflight': comparison,
               'preflight_passed': True, 'native_sidecar_required': True, 'experimental': True, 'witnessed': False}
    return ImportPlan(clip, replacement, receipt, {name: A.sha256(data) for name, data in raw.items()})


def author_referee_variant(clip):
    """A new modest arm gesture in the existing delay-of-game identity and budget."""
    require(clip.identity == 'archive:3107/27' and clip.family == 'referee', 'The first gesture requires the referee seed')
    keys = A.native_rotations(clip)
    r = clip.roots[0]
    for frame in range(1, r.frames-1):
        angle = math.radians(8.) * math.sin(math.pi*frame/(r.frames-1)) ** 2
        delta = (math.cos(angle/2), 0., 0., math.sin(angle/2))
        keys[frame][14] = Q.unit(Q.multiply(keys[frame][14], delta))
    replacement = A.compile_replacement(clip, keys)
    pose = pose_preflight(clip, replacement, keys)
    receipt = {**replacement.receipt, 'schema': 'nfl2k5_animation_import/v1', 'preflight_passed': True,
               'pose_preflight': pose, 'variant': 'referee_left_arm_eight_degrees',
               'new_identity': False, 'growth_bytes': 0,
               'payload_budget_bytes': 4*r.channels*r.frames+r.stride*r.frames+4*(len(r.events)+1)+52+(12*r.frames if r.auxiliary else 0)}
    return ImportPlan(clip, replacement, receipt, {})


@dataclass(frozen=True)
class SpanEdit:
    identity: str
    before: bytes
    after: bytes
    # (file/image offset, offset inside resource, length); all bytes are covered exactly once.
    spans: tuple


def validate_spans(edits, size):
    occupied = []
    require(bool(edits), 'No edits selected')
    for edit in edits:
        require(len(edit.before) == len(edit.after) and len(edit.before) <= MAX_FILE, 'Invalid fixed-span edit')
        cursor = 0
        for off, inner, length in edit.spans:
            require(all(type(v) is int for v in (off, inner, length)) and inner == cursor and length > 0 and
                    0 <= off <= size-length, 'Invalid or incomplete output span mapping')
            occupied.append((off, off+length))
            cursor += length
        require(cursor == len(edit.before), 'Resource span mapping is incomplete')
    occupied.sort()
    require(all(a[1] <= b[0] for a, b in zip(occupied, occupied[1:])), 'Output resource reservations overlap')


def _read_span(fd, edit):
    return b''.join(io.pread(fd, n, off) for off, _, n in edit.spans)


def _states(fd, edits):
    states = [A.Replacement(e.identity, e.before, e.after, {}).status(_read_span(fd, e)) for e in edits]
    require(not ('original' in states and 'applied' in states), 'Mixed original/applied resources in one coordinated edit')
    return states


def preflight_file(source, edits):
    fd = os.open(Path(source), os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    try:
        validate_spans(edits, os.fstat(fd).st_size)
        return _states(fd, edits)
    finally:
        os.close(fd)


def write_copy(source, destination, edits, *, receipt=None, progress=None):
    """Stage, verify, close every handle, then publish one new output file.

    Only differing byte runs are written. The entire source is copied through a
    bounded buffer. No existing destination is replaced, including hardlinks.
    """
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    require(source != destination and not destination.exists(), 'Choose a new output file distinct from the source')
    receipt_path = destination.with_name(destination.name+'.animation-receipt.json')
    require(not receipt_path.exists(), 'Output receipt already exists')
    progress = progress or (lambda *_: None)
    edits = tuple(edits)
    preflight_file(source, edits)
    size = source.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(destination.parent).free >= size + 1024*1024, 'Not enough space for the output copy')
    # Real acceptance builds have a stricter, documented disk floor.
    if size > 1024**3:
        require(shutil.disk_usage(destination.parent).free >= 100*1024**3 + size,
                'The output copy would leave less than 100 GiB free')
    actual = []
    with tempfile.TemporaryDirectory(prefix='.animation-copy-', dir=destination.parent) as folder:
        stage = (Path(folder)/'output').resolve()
        with source.open('rb') as reader, stage.open('xb') as writer:
            source_hash = hashlib.sha256()
            original_stat = os.fstat(reader.fileno())
            validate_spans(edits, original_stat.st_size)
            _states(reader.fileno(), edits)
            copied = 0
            while block := reader.read(1024*1024):
                writer.write(block)
                source_hash.update(block)
                copied += len(block)
                progress('Copying game data', copied, size)
            require(copied == size, 'Source size changed while copying')
            writer.flush()
            os.fsync(writer.fileno())
            now = os.fstat(reader.fileno())
            require((now.st_size, now.st_mtime_ns, now.st_ctime_ns) ==
                    (original_stat.st_size, original_stat.st_mtime_ns, original_stat.st_ctime_ns),
                    'Source changed while copying')
        path_stat = source.stat()
        # Windows reports st_dev/st_ino/st_ctime differently between a handle and a path;
        # size and mtime carry the identity there, and the streamed hash decides content.
        def _identity(stat):
            posix = () if os.name == 'nt' else (stat.st_dev, stat.st_ino, stat.st_ctime_ns)
            return (stat.st_size, stat.st_mtime_ns) + posix
        require(_identity(path_stat) == _identity(original_stat), 'Source path changed while copying')
        # Some filesystems coalesce timestamps. Content, not timestamps alone,
        # must catch an input modification during the copy.
        recheck = hashlib.sha256()
        with source.open('rb') as reader:
            for block in iter(lambda: reader.read(1024*1024), b''):
                recheck.update(block)
        require(recheck.digest() == source_hash.digest(), 'Source changed while copying')
        fd = os.open(stage, os.O_RDWR | getattr(os, 'O_BINARY', 0))
        try:
            states = _states(fd, edits)  # all resources validated before the first write
            for edit, state in zip(edits, states):
                current = edit.after if state == 'applied' else edit.before
                for run in A._diff_spans(current, edit.after):
                    for off, inner, n in edit.spans:
                        lo, hi = max(inner, run['offset']), min(inner+n, run['offset']+run['length'])
                        if lo >= hi:
                            continue
                        at, data = off+lo-inner, edit.after[lo:hi]
                        require(io.pwrite(fd, data, at) == len(data), 'Short write into output copy')
                        actual.append({'identity': edit.identity, 'offset': at, 'length': len(data),
                                       'before_hex': current[lo:hi].hex(), 'after_hex': data.hex()})
            os.fsync(fd)
            require(all(_read_span(fd, e) == e.after for e in edits), 'Output read-back differs')
        finally:
            os.close(fd)
        output_hash = hashlib.sha256()
        with stage.open('rb') as reader:
            for block in iter(lambda: reader.read(1024*1024), b''):
                output_hash.update(block)
        result = {**(receipt or {}), 'source': str(source), 'output': str(destination), 'write_spans': actual,
                  'changed_bytes': sum(r['length'] for r in actual), 'resource_states': states,
                  'source_sha256': source_hash.hexdigest(), 'output_sha256': output_hash.hexdigest(),
                  'game_files_written': True, 'experimental': True, 'witnessed': False, 'receipt_path': str(receipt_path)}
        staged_receipt = Path(folder)/'receipt.json'
        staged_receipt.write_bytes(A._json(result))
        require(not destination.exists(), 'Output appeared during the build')
        # Reserve the filename exclusively before replacement, so a competing output is refused.
        reservation = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
        os.close(reservation)
        reserved_receipt = False
        try:
            reservation = os.open(receipt_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_BINARY', 0), 0o600)
            os.close(reservation)
            reserved_receipt = True
            os.replace(stage, destination)
            os.replace(staged_receipt, receipt_path)
        except BaseException:
            destination.unlink()
            if reserved_receipt:
                receipt_path.unlink()
            raise
    return result


def archive_guard(fd, packs, resources):
    """Pin the actual archive directory, including identity and split-pack geometry."""
    outer = A._tool('nfl_outer')
    index = packs.get('0')
    require(index is not None, 'Disc archive index is missing')
    header = io.pread(fd, outer.HEADER_SIZE, index.byte_offset)
    require(len(header) == outer.HEADER_SIZE, 'Truncated archive header')
    count, reserved, populated = struct.unpack_from('<3I', header)
    require(0 < count <= outer.MAX_ENTRIES and reserved == 0 and 0 < populated <= outer.PACK_SLOT_COUNT,
            'Invalid archive directory header')
    blocks = struct.unpack_from('<36I', header, 12)
    starts, cursor = {}, 0
    for name, n in zip(outer.PACK_NAMES[:populated], blocks):
        require(name in packs and packs[name].size == n*outer.ALIGNMENT, 'Archive pack sizes differ from the file table')
        starts[name] = cursor
        cursor += n*outer.ALIGNMENT
    size = outer.HEADER_SIZE+count*12
    require(size <= index.size, 'Archive directory exceeds index pack')
    directory = io.pread(fd, size, index.byte_offset)
    require(len(directory) == size, 'Truncated archive directory')
    for source, length in resources:
        i = source['outer_index']
        require(type(i) is int and 0 <= i < count, 'Resource outer identity is absent')
        ident, n, block = struct.unpack_from('<3I', directory, outer.HEADER_SIZE+i*12)
        require(ident == int(source['outer_id'], 0) and n == source['outer_size'] and
                0 <= source['chunk_offset'] <= n-length, 'Resource directory identity or size changed')
        cursor = block*outer.ALIGNMENT+source['chunk_offset']
        total = 0
        for segment in source['segments']:
            require(segment['pack'] in starts and starts[segment['pack']]+segment['offset'] == cursor,
                    'Resource location differs from the archive directory')
            cursor += segment['length']
            total += segment['length']
        require(total == length, 'Resource segments are incomplete')
    return SpanEdit('archive_directory', directory, directory, ((index.byte_offset, 0, size),))


def image_edits(image, plans):
    """Map pinned archive resources through the existing XDVDFS extent parser."""
    from . import nfl2k5_models as models
    fd = os.open(image, os.O_RDONLY | getattr(os, 'O_BINARY', 0))
    try:
        size = os.fstat(fd).st_size
        packs = {name.upper(): entry for name, entry in models._xdvdfs_pack_entries(fd, size).items()}
        result = []
        for plan in plans:
            clip, replacement = plan.clip, plan.replacement
            require(clip.kind == 'SMCD', 'Embedded roots require the executable transport')
            spans, cursor = [], 0
            for segment in clip.source.get('segments', []):
                entry = packs.get(str(segment['pack']))
                require(entry is not None and 0 <= segment['offset'] <= entry.size-segment['length'],
                        'Animation pack segment is absent or outside the output disc')
                spans.append((entry.byte_offset+segment['offset'], cursor, segment['length']))
                cursor += segment['length']
            result.append(SpanEdit(clip.identity, replacement.before, replacement.after, tuple(spans)))
        result.append(archive_guard(fd, packs, [(p.clip.source, len(p.replacement.before)) for p in plans]))
        validate_spans(result, size)
        _states(fd, result)
        return tuple(result)
    finally:
        os.close(fd)


def write_import_copy(plan, image, destination):
    require(plan.receipt.get('preflight_passed') is True, 'Animation preflight is missing')
    return write_copy(image, destination, image_edits(image, (plan,)), receipt=plan.receipt)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--xbe', type=Path)
    actions = parser.add_subparsers(dest='action', required=True)
    for name in ('check', 'import', 'variant'):
        p = actions.add_parser(name)
        p.add_argument('identity')
        if name != 'variant':
            p.add_argument('--gltf', type=Path, required=True)
        p.add_argument('--source', type=Path, required=True, help='Source disc image, or XBE for an embedded root')
        p.add_argument('--output', type=Path, required=True, help='New receipt JSON (check) or new game copy (import/variant)')
    for name in ('limb-check', 'limb-import'):
        p = actions.add_parser(name)
        p.add_argument('--scale', type=float, default=1.01)
        p.add_argument('--source', type=Path, required=True)
        p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action.startswith('limb-'):
        from . import nfl2k5_animation_bones as bones, nfl2k5_models as models
        plan = bones.compile_limb(models.ModelSource(args.index, args.inventory), args.scale)
        edits = bones.image_edits(plan, args.source)
        result = plan.receipt if args.action == 'limb-check' else write_copy(args.source, args.output, edits, receipt=plan.receipt)
    else:
        source = A.AnimationSource(args.index, args.inventory, args.xbe)
        clip = source.load(args.identity)
        plan = author_referee_variant(clip) if args.action == 'variant' else compile_import(clip, args.gltf, source.skeleton(clip))
        if clip.kind == 'XBE_ROOT':
            from . import nfl2k5_animation_xbe as xbe
            xbe.apply(_read(args.source), plan.replacement)
            result = plan.receipt if args.action == 'check' else xbe.write_import_copy(plan, args.source, args.output)
        else:
            require(clip.map_id is not None, 'Import needs a proved skeleton family')
            edits = image_edits(args.source, (plan,))
            result = plan.receipt if args.action == 'check' else write_copy(args.source, args.output, edits, receipt=plan.receipt)
    if args.action in ('check', 'limb-check'):
        with args.output.open('xb') as stream:
            stream.write(A._json(result))
    print(json.dumps({'action': args.action, 'output': str(args.output), 'experimental': True, 'witnessed': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
