#!/usr/bin/env python3
"""Offline, generated APFe/VC-IFF benchmark. Never copies a retail volume.

Run with PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen. The fixture uses 32
independent crest pairs (28 recognized team folders and four alternatives).
Stage costs are exclusive, summed worker seconds; phase costs are wall time.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
import functools
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import random
import shutil
import struct
import sys
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from PIL import Image
import apf_inner as inner
import apf_outer as outer
import apf_logo_patch as writer
import apf_field_art_patch as field
import apf_logocache_patch as cache
from mod_editor.apf_studio import ps3_texture_bundle as bundle_api
from mod_editor.apf_studio.build import (ApfBuildService, _CompiledBuildSpan,
    HELMET_CREST_DESIGN_KIND, HELMET_CREST_COMPOSITE_SCHEMA)
from test_apf_crest_fit import synthetic_package

STATS = defaultdict(float)
CALLS = defaultdict(int)
STACK = []
_ORIGINAL_MAP = getattr(writer, 'ordered_crest_map', None)
_INSTRUMENTED = False
QT_REFERENCE = None
REPEAT_INPUTS = None


def timed(name, fn):
    @functools.wraps(fn)
    def call(*args, **kwargs):
        frame = [time.perf_counter(), 0.0]
        STACK.append(frame)
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - frame[0]
            STACK.pop()
            STATS[name] += elapsed - frame[1]
            CALLS[name] += 1
            if STACK:
                STACK[-1][1] += elapsed
    return call


def instrument():
    global _INSTRUMENTED
    if _INSTRUMENTED:
        return
    _INSTRUMENTED = True
    for name, funcs in {
        'region_masks': ('encode_4444_base', 'simplify_regions'),
        'mips': ('rebuild_mip_tail',),
        'greedy_h7a': ('compress_h7a',),
        'optimal_h7a': ('compress_h7a_best',),
        'verification': ('verify_h7a_stream', '_recompress_rebuild_reparse', '_extract_layer'),
        'ladder_overhead': ('measure_logo_pair', '_fit_rebuild'),
    }.items():
        for fn in funcs:
            setattr(writer, fn, timed(name, getattr(writer, fn)))
    inner.decode_block = timed('source_decode', inner.decode_block)
    bundle_api.read_bundle = timed('ps3_decode', bundle_api.read_bundle)
    for name in ('encode_4444_base', 'rebuild_mip_tail', 'compress_h7a'):
        setattr(cache, name, getattr(writer, name))
    cache._extract_target = timed('verification', cache._extract_target)
    cache._decompress_part = timed('source_decode', cache._decompress_part)


def profile_job(job):
    function, argument = job
    if writer._CREST_CHILD:
        instrument()
        STATS.clear()
        CALLS.clear()
        result = function(argument)
        return result, dict(STATS), dict(CALLS)
    return function(argument), {}, {}


def profiled_map(function, jobs, **kwargs):
    for result, stats, calls in _ORIGINAL_MAP(profile_job, tuple((function, job) for job in jobs), **kwargs):
        for name, value in stats.items():
            STATS[name] += value
        for name, value in calls.items():
            CALLS[name] += value
        yield result


def fixture(root, count):
    source = synthetic_package(budget=300000)
    raw = source[2]
    header_size = 40 + count * 12
    header = bytearray(header_size)
    struct.pack_into('>6I', header, 0, outer.MAGIC, 1, 1, 0, count, 0)
    struct.pack_into('>II8s', header, 24, header_size + len(raw) * count, 0,
                     '0A'.encode('utf-16be').ljust(8, b'\0'))
    for i in range(count):
        struct.pack_into('>III', header, 40 + i * 12,
                         zlib.crc32(f'UNIFORM_LOGO_{i:02d}.IFF'.encode()),
                         header_size + i * len(raw), len(raw))
    index = root / '0A'
    index.write_bytes(bytes(header) + raw * count)
    zipped = root / 'synthetic.zip'
    with zipfile.ZipFile(zipped, 'w', zipfile.ZIP_DEFLATED) as archive:
        for i in range(count):
            rng = random.Random(661 + (i % REPEAT_INPUTS if REPEAT_INPUTS else i))
            image = Image.new('RGBA', (128, 128))
            image.putdata([tuple((4 + rng.randrange(8)) * 17 for _ in range(3)) + (255,)
                           for _ in range(128 * 128)])
            image = image.resize((512, 512), Image.Resampling.NEAREST)
            team = bundle_api.NFL_TEAMS[i % len(bundle_api.NFL_TEAMS)]
            variant = f'/Alternative-{i}' if i >= len(bundle_api.NFL_TEAMS) else ''
            for layer in range(2):
                art = image if layer == 0 else image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                rgba = art.tobytes()
                # APFe's 16-bit ARGB4444 DDS header and base pixels.
                buffer = io.BytesIO()
                art.save(buffer, 'DDS')
                dds = bytearray(buffer.getvalue()[:128])
                struct.pack_into('<I', dds, 20, 1024)
                struct.pack_into('<5I', dds, 88, 16, 0xF00, 0xF0, 0xF, 0xF000)
                words = [((rgba[p + 3] // 17) << 12) | ((rgba[p] // 17) << 8)
                         | ((rgba[p + 1] // 17) << 4) | (rgba[p + 2] // 17)
                         for p in range(0, len(rgba), 4)]
                name = f'1_logo_l{layer}.dds'
                folder = f'{team}{variant}/selected_subfile_{layer}'
                archive.writestr(f'{folder}/{name}', bytes(dds) + struct.pack('<262144H', *words))
                archive.writestr(f'{folder}/manifest.json', json.dumps({'row': {
                    'entryIndex': i, 'entryHash': zlib.crc32(f'UNIFORM_LOGO_{i:02d}.IFF'.encode()),
                    'subfileName': f'logo_l{layer}', 'type': 'TXTR', 'byteLength': 524416}, 'files': [name]}))
    return index, zipped


def cache_fixture():
    """Author all 118 x 2 cache descriptors and payloads; no retail bytes.

    Unused DRAM prefix bytes are generated until its legal H7A stream has the
    cache format's fixed 113-byte length. All texture descriptors stay intact.
    """
    source = synthetic_package(budget=300000)
    layers, blocks = source[-1], source[3]
    parts = []
    for layer_index in range(2):
        dram = bytearray(blocks[0][layer_index * 224:(layer_index + 1) * 224])
        found = False
        for seed in range(20):
            rng = random.Random(seed)
            noise = rng.randbytes(80)
            for count in range(80):
                candidate = bytearray(dram)
                candidate[:count] = noise[:count]
                stream = writer.compress_h7a(bytes(candidate), 8)
                if len(stream) == 93:
                    writer.verify_h7a_stream(stream, bytes(candidate), 8)
                    writer._strict_descriptor(inner.parse_txtr_metadata(candidate))
                    found = True
                    break
            if found:
                break
        assert found, 'could not author fixed-size synthetic DRAM stream'
        part_a = struct.pack('>5I', inner.H7A_MAGIC, 224, 113, 0, 8) + stream
        vram = blocks[1][layer_index * writer.PAYLOAD_LEN:(layer_index + 1) * writer.PAYLOAD_LEN]
        stream = writer.compress_h7a(vram, 8)
        part_b = struct.pack('>5I', inner.H7A_MAGIC, len(vram), 20 + len(stream), 0, 8) + stream
        parts.append((part_a, part_b))
    raw = bytearray(cache.DIR_HEADER_SIZE)
    struct.pack_into('>10I', raw, 0, cache.DIR_MAGIC, cache.DIR_HEADER_SIZE,
        cache.DIR_HEADER_SIZE, 0, 2, 0x28 - 0x14 + 1, 236, 0x68 - 0x1c + 1,
        0x1688 - 0x20 + 1, 0x28f8 - 0x24 + 1)
    for i, (kind, stride) in enumerate(((0xbb05a9c1, 224), (0x411536d5, writer.PAYLOAD_LEN))):
        struct.pack_into('>8I', raw, 0x28 + i * 32, 0, kind, 0, stride, 0, 0, 0, 0)
    names, payload = [], bytearray()
    for i in range(236):
        name = f'{i // 2:02d}_logo_l{i % 2}'
        names.append(name)
        descriptor, pointer = 0x68 + 236 * 4 + i * 20, 0x68 + i * 4
        struct.pack_into('>I', raw, pointer, descriptor - pointer + 1)
        struct.pack_into('>5I', raw, descriptor, zlib.crc32(name.encode()), cache.TXTR_TYPE_HASH,
                         2, i * 224, i * writer.PAYLOAD_LEN)
        auxiliary, pointer = 0x1688 + 236 * 4 + i * 16, 0x1688 + i * 4
        struct.pack_into('>I', raw, pointer, auxiliary - pointer + 1)
        a, b = parts[i % 2]
        struct.pack_into('>4I', raw, auxiliary, len(payload), len(a), len(payload) + len(a), len(b))
        payload.extend(a + b)
    raw[0x28f8:] = cache.DIR_INTERNAL_NAME.encode('utf-16be') + b'\0\0'
    footer = bytearray(8 + 236 * 12)
    struct.pack_into('<II', footer, 0, 236, 5)
    for i, name in enumerate(names):
        descriptor, pointer = 8 + 236 * 4 + i * 8, 8 + i * 4
        struct.pack_into('<I', footer, pointer, descriptor - pointer + 1)
        name_at = len(footer)
        footer.extend(name.encode('utf-16le') + b'\0\0')
        type_at = len(footer)
        footer.extend('TXTR'.encode('utf-16le') + b'\0\0')
        struct.pack_into('<II', footer, descriptor, name_at - descriptor + 1, type_at - descriptor - 4 + 1)
    raw.extend(struct.pack('>I', inner.NAME_FOOTER_MAGIC) + struct.pack('<I', len(footer)) + footer)
    raw.extend(bytes(cache.DIR_SIZE - len(raw)))
    payload.extend(bytes(cache.PAYLOAD_SIZE - len(payload)))
    cache.parse_cache_directory(bytes(raw))
    return bytes(raw), bytes(payload)


def run(count, root, parallel=False, include_cache=False):
    index, zipped = fixture(root, count)
    cache_source = cache_fixture() if include_cache else None
    writer._STREAM_CACHE.clear()
    writer._MEASUREMENT_CACHE.clear()
    for name in ('_PIXEL_CACHE', '_PACKAGE_CACHE', '_FITTED_STREAMS'):
        if hasattr(writer, name):
            getattr(writer, name).clear()
    if hasattr(bundle_api, '_BUNDLE_MEASUREMENTS'):
        bundle_api._BUNDLE_MEASUREMENTS.clear()
        from mod_editor.apf_studio import ps3_texture_codec
        ps3_texture_codec._DECODED_SOURCES.clear()
        writer._tile_halfword_order.cache_clear()
        cache._COMPILED_LAYERS.clear()
    STATS.clear()
    CALLS.clear()
    phases = {}
    def phase(name, fn):
        start = time.perf_counter()
        value = fn()
        phases[name] = time.perf_counter() - start
        print(f'{count} {name}: {phases[name]:.3f}s', flush=True)
        return value
    started = time.perf_counter()
    bundle = phase('read_bundle', lambda: bundle_api.read_bundle(zipped))
    slots = phase('destination_slots', lambda: bundle_api.destination_slots(index))
    measurements = phase('measure', lambda: bundle_api.measure_bundle_logos(bundle, slots, index,
        lambda msg, done, total: print(msg, done, total, flush=True) if msg.startswith('Measured') else None))
    plan = phase('plan', lambda: bundle_api.build_plan(bundle, slots, measurements=measurements))
    # Exercise stage revalidation and PNG round-trip; session mutation is a
    # sink because the archive here deliberately has no executable/catalog.
    session = SimpleNamespace(source=SimpleNamespace(index_0a=index), modifications=(),
        replace_helmet_crest_design=lambda *a, **kw: None, undo=lambda: None)
    phase('stage', lambda: bundle_api.stage_plan(session, plan))
    def compile_packages():
        if parallel:
            return writer.build_crest_packages(index, tuple((slot.outer_index,
                *(layer.image.tobytes() for layer in pair.layers), True) for pair, slot in plan.assignments))
        results = {}
        for pair, slot in plan.assignments:
            results[slot.outer_index] = writer.build_patch_rgba(index,
                *(layer.image.tobytes() for layer in pair.layers), entry_index=slot.outer_index,
                allow_simplification=True)
        return results
    results = phase('compile', compile_packages)
    cache_hashes = None
    if include_cache:
        specs = []
        for pair, slot in plan.assignments:
            shades = results[slot.outer_index].manifest['fit']['shades_per_region']
            paths = []
            for i, layer in enumerate(pair.layers):
                pixels = layer.image.tobytes()
                if shades < 16:
                    pixels = writer.simplify_regions(pixels, shades)
                path = root / f'cache-{slot.outer_index}-{i}.png'
                Image.frombytes('RGBA', (512, 512), pixels).save(path)
                paths.append(path)
            specs.append(cache.CacheLayerSpec(slot.crest_asset_index, *paths))
        with patch.object(cache, '_read_pair', return_value=(None, None, None, *cache_source)):
            linked = phase('linked_cache', lambda: cache.build_cache_patch_many(index, specs))
        cache_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in
                       (('directory', linked.directory_bytes), ('payload', linked.payload_bytes))}
    archive = outer.parse_archive(index)
    output = root / 'output'
    output.mkdir()
    spans = tuple(_CompiledBuildSpan('0A', archive.entries[i].segments[0].pack_offset,
        result.entry_bytes, i, (f'crest:{i}',), 'helmet_crest_design', writer.SCHEMA, True)
        for i, result in results.items())
    def apply():
        shutil.copyfile(index, output / '0A')
        ApfBuildService._apply_compiled_spans(output, spans)
        reparsed = outer.parse_archive(output / '0A')
        with inner.ArchiveReader(reparsed) as reader:
            for i, result in results.items():
                entry = reparsed.entries[i]
                assert reader.read(entry, 0, entry.size) == result.entry_bytes
                inner.parse_iff(reader, entry)
        if include_cache:
            # Exercise the same package-span writer without a 1.1 GiB disc copy.
            cache_output = output / 'cache-spans'
            cache_output.mkdir()
            cache_path = cache_output / '0A'
            cache_path.write_bytes(bytes(cache.DIR_SIZE + cache.PAYLOAD_SIZE))
            cache_spans = tuple(_CompiledBuildSpan('0A', offset, data, owner,
                (f'cache:{owner}',), HELMET_CREST_DESIGN_KIND, HELMET_CREST_COMPOSITE_SCHEMA, True)
                for offset, data, owner in ((0, linked.directory_bytes, 171),
                    (cache.DIR_SIZE, linked.payload_bytes, 213)))
            ApfBuildService._apply_compiled_spans(cache_output, cache_spans)
            assert cache_path.read_bytes() == linked.directory_bytes + linked.payload_bytes
    phase('apply_and_readback', apply)
    total = time.perf_counter() - started
    from PyQt5.QtWidgets import QApplication
    from mod_editor.apf_studio.ps3_texture_bundle_qt import Ps3BundleMappingDialog
    if QT_REFERENCE is not None:
        Ps3BundleMappingDialog = QT_REFERENCE.Ps3BundleMappingDialog
    app = QApplication.instance() or QApplication([])
    start = time.perf_counter()
    dialog = Ps3BundleMappingDialog(bundle, slots, measurements=measurements)
    app.processEvents()
    gui_seconds = time.perf_counter() - start
    dialog.close()
    return {'count': count, 'wall_seconds': total, 'phases': phases,
        'stages_exclusive_seconds': dict(STATS), 'calls': dict(CALLS), 'gui_dialog_seconds': gui_seconds,
        'packages': {str(i): {'sha256': hashlib.sha256(r.entry_bytes).hexdigest(),
            'fit': r.manifest.get('fit')} for i, r in results.items()},
        'output_pack_sha256': hashlib.sha256((output / '0A').read_bytes()).hexdigest(),
        'linked_cache_sha256': cache_hashes}


def main():
    global writer, cache, bundle_api, QT_REFERENCE, REPEAT_INPUTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--counts', type=int, nargs='+', default=[1, 32])
    parser.add_argument('--freeze-helper', action='store_true')
    parser.add_argument('--parallel', action='store_true')
    parser.add_argument('--include-cache', action='store_true')
    parser.add_argument('--reference-dir', type=Path)
    parser.add_argument('--disable-helper', action='store_true', help='Force portable encoding, including spawned workers')
    parser.add_argument('--repeat-inputs', type=int, help='Cycle this many distinct six-mask inputs across destinations')
    args = parser.parse_args()
    if args.repeat_inputs is not None and args.repeat_inputs < 1:
        parser.error('--repeat-inputs must be positive')
    REPEAT_INPUTS = args.repeat_inputs
    if args.disable_helper:
        os.environ['APF_H7A_DISABLE_NATIVE'] = '1'
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if args.reference_dir:
        def load(name, filename):
            spec = importlib.util.spec_from_file_location(name, args.reference_dir / filename)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module
        writer = load('apf_logo_patch', 'writer.py')
        cache = load('apf_logocache_patch', 'cache.py')
        bundle_api = load('mod_editor.apf_studio.ps3_texture_bundle_reference', 'bundle.py')
        QT_REFERENCE = load('mod_editor.apf_studio.ps3_texture_bundle_qt_reference', 'bundle_qt.py')
        field._OPTIMAL_BINARY = args.reference_dir / 'helper'
        field._OPTIMAL_BINARY_SIZE = field._OPTIMAL_BINARY.stat().st_size
        field._OPTIMAL_BINARY_SHA256 = hashlib.sha256(field._OPTIMAL_BINARY.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='apf-ps3-benchmark-') as directory:
        root = Path(directory)
        if args.freeze_helper:
            helper = root / 'apf_h7a_optimal'
            shutil.copy2(field._OPTIMAL_BINARY, helper)
            field._OPTIMAL_BINARY = helper
        instrument()
        if args.parallel:
            writer.ordered_crest_map = profiled_map
            cache.ordered_crest_map = profiled_map
        report = {'python': sys.version, 'cpu_count': os.cpu_count(),
                  'native_disabled': os.environ.get('APF_H7A_DISABLE_NATIVE') == '1',
                  'portable_optimal': os.environ.get('APF_H7A_PYTHON_OPTIMAL') == '1',
                  'repeat_inputs': REPEAT_INPUTS, 'runs': []}
        for count in args.counts:
            folder = root / str(count)
            folder.mkdir()
            report['runs'].append(run(count, folder, args.parallel, args.include_cache))
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
