"""Repair reversed tens/ones on v0.4 stadium end-wall play clocks.

This edits supplied IFF resource bytes, never a disc. The manifest pins the
original/fixed resource and every end-wall clock quad. Composed resources require
an explicit opt-in and must still match the exact original/fixed clock hash.
The decoded edit changes only the clock X coordinates; compression retains the
original stored span. All other decoded bytes and outer bytes are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_metlife as ml
from mod_editor.core import nfl2k5_scne_builder as sb

MANIFEST = Path(__file__).with_name('d2_clock_manifest.json')
VENUES = ('s00', 's01', 's03', 's07', 's10', 's11', 's12', 's14', 's15',
          's16', 's18', 's19', 's20', 's23', 's24', 's25', 's40')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def geometry(decoded, system):
    """Return pinned clock bytes, exact coordinate offsets, and current order."""
    scene = sb.parse(decoded, system)
    shapes = [shape for shape in scene.shapes if any(scene.materials[sub.material].name == 'digit_playclock_L'
                                                    for sub in shape.submeshes)]
    if len(shapes) != 1:
        raise ValueError('no unique stadium digit shape')
    shape = shapes[0]
    desc = sb._rel(decoded, 0x14)
    table = sb._rel(decoded, desc + 0x30)
    shape_index = scene.shapes.index(shape)
    record_at = table + shape_index * 0x100
    stream_at = sb._rel(decoded, record_at + sb.SHAPE_STREAMS[0])
    if shape.stride(0) != 12 or shape.stride(1) != 10:
        raise ValueError('unexpected digit vertex format')
    fingerprint = bytearray()
    offsets, states, labels = [], [], []
    for sub in shape.submeshes:
        name = scene.materials[sub.material].name
        if name not in ('digit_playclock_L', 'digit_playclock_R'):
            continue
        ids = sorted({i for _, ix in sb.decode_words(sub.words) for i in ix})
        if len(ids) % 4:
            raise ValueError('play-clock vertices are not complete quads')
        for start in range(0, len(ids), 4):
            quad = ids[start:start + 4]
            points = [struct.unpack_from('<3f', shape.streams[0], i * 12) for i in quad]
            x, y, z = [sum(p[k] for p in points) / 4 for k in range(3)]
            # MetLife also has correct clocks high on its boards.
            if y > 500:
                continue
            if (y not in (260., 270.) or abs(z) < 5000 or abs(x) != 90.
                    or max(p[0] for p in points) - min(p[0] for p in points) != 150.
                    or max(p[1] for p in points) - min(p[1] for p in points) != 220.
                    or any(p[2] != z for p in points)):
                raise ValueError('unexpected end-wall play-clock geometry')
            zs = 1 if z > 0 else -1
            side = -1 if name.endswith('_L') else 1
            states.append('original' if x == side * 90 * zs else 'fixed')
            labels.append((name, zs))
            fingerprint.extend(name.encode('ascii') + b'\0')
            for i in quad:
                fingerprint.extend(shape.streams[0][i * 12:(i + 1) * 12])
                fingerprint.extend(shape.streams[1][i * 10:(i + 1) * 10])
                offsets.append((stream_at + i * 12, x))
    # Some retail donors contain three or four clock pairs. The model retains
    # those copies at the two end walls; preserve their topology and fix each.
    if (len(offsets) not in (16, 24, 32) or len(set(states)) != 1 or
            set(labels) != {(name, zs) for name in ('digit_playclock_L', 'digit_playclock_R') for zs in (-1, 1)}):
        raise ValueError('missing, repeated, or mixed-state play-clock quads')
    if any(labels.count(('digit_playclock_L', zs)) != labels.count(('digit_playclock_R', zs)) for zs in (-1, 1)):
        raise ValueError('unpaired play-clock quads')
    return sha(fingerprint), offsets, states[0]


def repair_resource(data: bytes, name: str, *, allow_composed=False):
    """Return fixed resource and scope receipt; refuse unrecognized inputs."""
    manifest = json.loads(MANIFEST.read_text())['resources']
    if name not in manifest:
        raise ValueError('resource is outside the clock repair manifest')
    expected = manifest[name]
    input_hash = sha(data)
    if not allow_composed and input_hash not in (expected['original_sha256'], expected['fixed_sha256']):
        raise ValueError('unexpected resource hash; compose only with explicit scoped verification')
    chunk = ml.bundle_scenes(data)['stadium']
    # The chunk encoder owns these words and writes zero. A composed resource
    # with unknown wrapper metadata must not lose it during recompression.
    if struct.unpack_from('<2I', data, chunk.offset + 0x18) != (0, 0):
        raise ValueError('unexpected reserved SCNE wrapper words')
    if not allow_composed and (chunk.offset != expected['chunk_offset'] or
                               32 + chunk.stored_size != expected['chunk_size']):
        raise ValueError('stadium chunk bounds differ from manifest')
    _, decoded = ml._scene(data, chunk)
    fingerprint, offsets, state = geometry(decoded, chunk.system_bytes)
    if fingerprint != expected[state + '_geometry_sha256']:
        raise ValueError('unexpected play-clock geometry hash')
    if not allow_composed and [at for at, _ in offsets] != expected['decoded_scope']:
        raise ValueError('decoded clock scope differs from manifest')
    if not allow_composed and input_hash != expected[state + '_sha256']:
        raise ValueError('unexpected resource hash; compose only with explicit scoped verification')
    if state == 'fixed':
        return data, dict(name=name, status='already_fixed', before_sha256=input_hash,
                          after_sha256=input_hash, changed_ranges=[])
    out = bytearray(decoded)
    ranges = []
    for at, centre_x in offsets:
        value = struct.unpack_from('<f', decoded, at)[0]
        replacement = struct.pack('<f', value - 2 * centre_x)
        out[at:at + 4] = replacement
        ranges.append(dict(offset=at, size=4, before=decoded[at:at + 4].hex(), after=replacement.hex()))
    outside_before, outside_after = bytearray(decoded), bytearray(out)
    for row in ranges:
        at = row['offset']
        outside_before[at:at + 4] = outside_after[at:at + 4] = bytes(4)
    if outside_before != outside_after:
        raise AssertionError('decoded bytes escaped the clock coordinate scope')
    after_fingerprint, _, after_state = geometry(bytes(out), chunk.system_bytes)
    if after_state != 'fixed' or after_fingerprint != expected['fixed_geometry_sha256']:
        raise ValueError('fixed geometry differs from manifest')
    span = data[chunk.offset:chunk.offset + 32 + chunk.stored_size]
    fixed, compression = sb.fixed_span_chunk('SCNE', bytes(out), chunk.system_bytes,
                                              chunk.video_bytes, span)
    result = data[:chunk.offset] + fixed + data[chunk.offset + len(span):]
    if len(result) != len(data):
        raise AssertionError('resource span grew')
    check_chunk = ml.bundle_scenes(result)['stadium']
    _, back = ml._scene(result, check_chunk)
    if back != out:
        raise AssertionError('native scene decode roundtrip failed')
    output_hash = sha(result)
    if not allow_composed and output_hash != expected['fixed_sha256']:
        raise ValueError('fixed resource hash differs from manifest')
    return result, dict(name=name, status='fixed', before_sha256=input_hash, after_sha256=output_hash,
                        chunk_offset=chunk.offset, chunk_size=len(span),
                        chunk_before_sha256=sha(span), chunk_after_sha256=sha(fixed),
                        decoded_before_sha256=sha(decoded), decoded_after_sha256=sha(back),
                        decoded_outside_scope_sha256=sha(outside_before),
                        original_geometry_sha256=fingerprint, fixed_geometry_sha256=after_fingerprint,
                        decoded_changed_ranges=ranges, compression=compression,
                        outside_chunk_identical=(result[:chunk.offset] == data[:chunk.offset] and
                                                 result[chunk.offset + len(span):] == data[chunk.offset + len(span):]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--name', required=True)
    parser.add_argument('--allow-composed', action='store_true')
    parser.add_argument('--expected-input-sha256', help='required whole-resource pin for composed input')
    args = parser.parse_args()
    receipt_path = args.output.with_suffix(args.output.suffix + '.receipt.json')
    if args.input.is_symlink() or not args.input.is_file():
        parser.error('input must be a regular file, not a symlink')
    if (args.input.resolve() == args.output.resolve() or
            any(path.exists() or path.is_symlink() for path in (args.output, receipt_path))):
        parser.error('output and receipt must be new paths distinct from input')
    flags = getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(args.input, os.O_RDONLY | flags)
    with os.fdopen(fd, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            parser.error('input must be a regular file')
        data = source.read()
    if args.allow_composed and not args.expected_input_sha256:
        parser.error('--allow-composed requires --expected-input-sha256')
    if args.expected_input_sha256 and sha(data) != args.expected_input_sha256:
        parser.error('input SHA-256 differs from explicit pin')
    fixed, receipt = repair_resource(data, args.name, allow_composed=args.allow_composed)
    # Reserve both new paths before writing either; O_EXCL also refuses dangling
    # symlinks and races after the friendly preflight checks above.
    created, descriptors = [], []
    try:
        for path in (args.output, receipt_path):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | flags, 0o600)
            created.append(path)
            descriptors.append(descriptor)
        for descriptor, content in zip(descriptors, (fixed, (json.dumps(receipt, indent=2) + '\n').encode())):
            view = memoryview(content)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError('short output write')
                view = view[written:]
        for descriptor in descriptors:
            os.close(descriptor)
        descriptors.clear()
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        for path in created:
            path.unlink()
        raise


if __name__ == '__main__':
    main()
