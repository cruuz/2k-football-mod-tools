#!/usr/bin/env python3
"""Compare the pre-change writer with acceleration on read-only retail packages.

Reference Python files and the reviewed pre-change helper are supplied explicitly
from a saved checkout. Reports contain hashes/timings only, never game bytes.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import random
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from PIL import Image
import apf_logo_patch as writer
import apf_logocache_patch as cache
import apf_field_art_patch as field


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-writer', type=Path, required=True)
    parser.add_argument('--reference-cache', type=Path, required=True)
    parser.add_argument('--reference-helper', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--native-only', action='store_true')
    args = parser.parse_args()
    index = Path(os.environ.get('APF_RETAIL_0A', ROOT / 'extracted/All-Pro Football 2K8 (USA)/0A'))
    report = {'retail_index': str(index), 'reference_writer_sha256': hashlib.sha256(args.reference_writer.read_bytes()).hexdigest(), 'packages': []}
    if args.native_only:
        reference = load('apf_logo_reference', args.reference_writer)
        binary = field._optimal_binary()
        if binary is None:
            report['skip'] = 'reviewed Linux x86-64 helper absent; native comparison unavailable'
        else:
            rng = random.Random(69010)
            samples = (bytes(1024), b'abcabcabzabc' * 95, rng.randbytes(1024))
            greedy_cases = optimal_cases = 0
            for shift in range(1, 16):
                for data in samples:
                    old = subprocess.run([str(args.reference_helper), str(shift)], input=data,
                        capture_output=True, timeout=20, check=True).stdout
                    new = subprocess.run([str(binary), str(shift)], input=data,
                        capture_output=True, timeout=20, check=True).stdout
                    assert old == new
                    optimal_cases += 1
                    for limit in (1, 64, 128):
                        old = reference.compress_h7a(data, shift, candidate_limit=limit)
                        new = subprocess.run([str(binary), str(shift), '--greedy', str(limit)],
                            input=data, capture_output=True, timeout=20, check=True).stdout
                        assert old == new
                        writer.verify_h7a_stream(new, data, shift)
                        greedy_cases += 1
            report['native_equivalence'] = {'optimal_original_helper_cases': optimal_cases,
                'greedy_original_python_cases': greedy_cases, 'all_byte_identical': True,
                'helper_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                'reference_helper_sha256': hashlib.sha256(args.reference_helper.read_bytes()).hexdigest()}
            print(f'Native equivalence: {optimal_cases} optimal + {greedy_cases} greedy cases', flush=True)
    elif not index.is_file():
        report['skip'] = f'APF retail 0A absent at {index}'
    else:
        reference = load('apf_logo_reference', args.reference_writer)
        with patch.dict(sys.modules, {'apf_logo_patch': reference}):
            old_cache = load('apf_logocache_reference', args.reference_cache)
        pixels = tuple(Image.new('RGBA', (512, 512), color).tobytes()
                       for color in ((255, 0, 170, 255), (0, 255, 34, 136)))
        helper_hash = hashlib.sha256(args.reference_helper.read_bytes()).hexdigest()
        for entry in (36, 1133, 712):
            started = time.perf_counter()
            with patch.object(field, '_OPTIMAL_BINARY', args.reference_helper), \
                 patch.object(field, '_OPTIMAL_BINARY_SIZE', args.reference_helper.stat().st_size), \
                 patch.object(field, '_OPTIMAL_BINARY_SHA256', helper_hash):
                before = reference.build_patch_rgba(index, *pixels, entry_index=entry, allow_simplification=True)
            before_seconds = time.perf_counter() - started
            started = time.perf_counter()
            after = writer.build_crest_packages(index, ((entry, *pixels, True),))[entry]
            after_seconds = time.perf_counter() - started
            assert before.entry_bytes == after.entry_bytes
            writer._STREAM_CACHE.clear()
            started = time.perf_counter()
            with patch.object(field, '_optimal_binary', return_value=None), \
                 patch.object(writer, '_compress_h7a_python', wraps=writer._compress_h7a_python) as fallback:
                portable = writer.build_patch_rgba(index, *pixels, entry_index=entry, allow_simplification=True)
                assert fallback.call_count > 0
            assert portable.entry_bytes == before.entry_bytes
            report['packages'].append({'outer_index': entry, 'sha256': hashlib.sha256(after.entry_bytes).hexdigest(),
                'before_seconds': before_seconds, 'after_seconds': after_seconds,
                'python_fallback_seconds': time.perf_counter() - started, 'byte_identical': True,
                'source_sha256': after.manifest['source']['entry_sha256'], 'fit': after.manifest.get('fit')})
            print(f'Retail outer {entry}: original = native = forced Python', flush=True)
        with tempfile.TemporaryDirectory(prefix='apf-parity-') as tmp:
            paths = tuple(Path(tmp) / f'l{i}.png' for i in range(2))
            for path, rgba in zip(paths, pixels):
                Image.frombytes('RGBA', (512, 512), rgba).save(path)
            started = time.perf_counter()
            before = old_cache.build_cache_patch(index, 1, paths[0], paths[1])
            before_seconds = time.perf_counter() - started
            started = time.perf_counter()
            after = cache.build_cache_patch(index, 1, paths[0], paths[1])
            after_seconds = time.perf_counter() - started
            assert before.directory_bytes == after.directory_bytes
            assert before.payload_bytes == after.payload_bytes
            started = time.perf_counter()
            with patch.object(cache, '_compile_cache_art', side_effect=AssertionError('unchanged cache recompiled')):
                warm = cache.build_cache_patch(index, 1, paths[0], paths[1])
            assert warm.directory_bytes == after.directory_bytes and warm.payload_bytes == after.payload_bytes
            report['linked_cache'] = {'before_seconds': before_seconds, 'after_seconds': after_seconds,
                'warm_seconds': time.perf_counter() - started, 'byte_identical': True,
                'directory_sha256': hashlib.sha256(after.directory_bytes).hexdigest(),
                'payload_sha256': hashlib.sha256(after.payload_bytes).hexdigest()}
            print('Retail linked cache: original = native = warm', flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
