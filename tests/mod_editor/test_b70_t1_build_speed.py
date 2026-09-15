"""Beta-69 byte goldens, helper-disabled budgets, safe pruning and staged reuse."""
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
import cProfile
from dataclasses import replace
import hashlib
import json
import random
import subprocess
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from b70_equipment_fixture import CASES, SizedFixture, stage_case, writer, lz
import test_nfl2k5_equipment_import as session_tests
from test_nfl2k5_equipment_texture_chain import digest, artwork
from nfl_txtr import HEADER, compress_vc_lz, parse_chunks, decode_chunk

# Captured from the writer after T2's quantizer and stripe floor landed (beta 70 stack, 5ce880d9): T1's search
# bounds and caching must not change these bytes. (Before T2 the noise cases were 409e6651.., fed500b1.. and 666.)
# Complete compressed span, including wrapper, scratch-preserving fill and pad.
BETA69_SPANS = {
    'sock256_stripes': '1cd108128cc224f2bd92fdf26b76e3e79ab220bbd500df25825fd547e6bc9aeb',
    'shoe64_stripes': 'fd090c83614b221547b3f2dad47eb2a2002c82aeb3c2460edad6070410e8b9bf',
    'shoe64_diagonal': '473086c049a1585b29e19528e9d997b13d3b40c964637d9cbe57b97046802afd',
    'shoe32_tight': '290ac5c940eb438468b1be42ed313b54693f1970e773f8a54e64c4e0beb2fc67',
    'shoe32_noise_half': 'd7929c8fed8c3863e91d5a6cde5c81c80fcd3bf72a7012e7f336e5896aa9814c',
    'shoe32_noise_quarter': '80f42a2ea0df9452234af4080df2666f60ce7fad316bc50ee1f5d6cd3f672c19',
}
IMPORT_BUDGET_SECONDS = 30.0  # Generous for CI; measurements are printed, not hidden.


def clear():
    writer._STAGED_CACHE.clear()
    writer._PARSE_CACHE.clear()


class SearchTests(unittest.TestCase):
    def setUp(self):
        clear()
        self.addCleanup(clear)

    def test_beta69_complete_span_bytes_and_helper_disabled_import_budget(self):
        for case in CASES:
            with self.subTest(case=case[0]):
                clear()
                row = stage_case(case, repeat=True)
                print('B70 IMPORT', case[0], json.dumps(row), flush=True)
                self.assertLess(row['seconds'], IMPORT_BUDGET_SECONDS)
                if case[0] in BETA69_SPANS:
                    self.assertEqual(row['outcome'], 'fit')
                    self.assertEqual(row['span_sha256'], BETA69_SPANS[case[0]])
                else:
                    self.assertEqual(row['outcome'], 'refused')
                    self.assertEqual(row['required'], 664)
                    self.assertEqual(row['suggestion']['scale'], 2)

    def test_python_parser_golden_bytes_and_timing(self):
        golden = json.loads((Path(__file__).resolve().parents[2] / 'reports/b70_t1/beta69-codec.json').read_text())
        with patch.object(lz, '_optimal_helper', return_value=None):
            for name, source in [('flat', bytes(65536)), ('repeated', b'abcdefghijklmno1234567890'*4000),
                                 ('palette', bytes((i*i+i//7)%256 for i in range(65536)))]:
                start = time.perf_counter()
                result = lz.compress_equipment_optimal(source, stream_tag=1, offset_bits=10, max_encoded_size=1000000)
                elapsed = time.perf_counter() - start
                print(f'B70 CODEC {name}: {elapsed:.6f} s', flush=True)
                self.assertLess(elapsed, 10)
                self.assertEqual(digest(result), golden[name]['sha256'])

    def test_greedy_margin_is_a_proved_bound_and_fits_keep_old_selection(self):
        rng = random.Random(70)
        with patch.object(lz, '_optimal_helper', return_value=None):
            for bits in range(10, 14):
                for n in range(1, 30):
                    source = bytes(rng.randrange(n % 9 + 1) for _ in range(n * 37))
                    optimal = lz.compress_equipment_optimal(source, stream_tag=1, offset_bits=bits, max_encoded_size=10000)
                    greedy, _ = compress_vc_lz(source, stream_tag=1, offset_bits=bits)
                    self.assertLessEqual(len(greedy), writer._greedy_ceiling(len(optimal)))
                    encoded, _ = writer._cached_parse(source, 1, bits, len(optimal))
                    self.assertEqual(encoded, greedy if len(greedy) <= len(optimal) else optimal)
                    self.assertLessEqual(lz.minimum_equipment_size(len(source), bits), len(optimal))

    def test_small_bound_aborts_reverse_search_and_misses_are_cached(self):
        rng = random.Random(701)
        source = bytes(rng.randrange(256) for _ in range(65536))
        profile = cProfile.Profile()
        with patch.object(lz, '_optimal_helper', return_value=None):
            with self.assertRaises(lz.EquipmentSizeOverflow) as caught:
                profile.runcall(lz.compress_equipment_optimal, source, stream_tag=1,
                                offset_bits=10, max_encoded_size=3000)
        calls = sum(entry.callcount for entry in profile.getstats() if 'rfind' in str(entry.code))
        self.assertLess(calls, len(source)//8)
        self.assertFalse(caught.exception.exact)
        print(f'B70 EARLY EXIT: searched {calls} / {len(source)} positions', flush=True)
        with patch.object(lz, 'compress_equipment_optimal', wraps=lz.compress_equipment_optimal) as optimal:
            with self.assertRaises(lz.EquipmentSizeOverflow):
                writer._cached_parse(source, 1, 10, 3000)
            optimal.assert_called_once()  # a greedy cutoff still checks the optimal parse
        with patch.object(writer, 'compress_vc_lz', side_effect=AssertionError('repeated greedy')):
            with self.assertRaises(lz.EquipmentSizeOverflow):
                writer._cached_parse(source, 1, 10, 3000)

    def test_suggestion_checks_one_ladder_and_reuses_every_parse(self):
        from test_b69_j1_fit import tight_fixture
        with tempfile.TemporaryDirectory() as folder:
            f, rgba = tight_fixture(Path(folder))
            _, png = f.png(rgba=rgba)
            payload, rgba, levels = writer._read_png(png, f.rows[0])
            _, info = decode_chunk(f.span, parse_chunks(f.span)[0])
            def run():
                with self.assertRaises(writer.EquipmentFitError):
                    writer._compile_group(f.span, f.chunk, f.decoded, info, f.rows,
                        {0: (f.rows[0], payload, rgba, levels)}, {0})
            with patch.object(lz, '_optimal_helper', return_value=None), \
                 patch.object(writer, '_compile_group', wraps=writer._compile_group) as compile:
                run()
                self.assertEqual(compile.call_count, 2)  # requested + one suggestion
            with patch.object(writer, 'compress_vc_lz', side_effect=AssertionError('greedy repeated')), \
                 patch.object(lz, 'compress_equipment_optimal', side_effect=AssertionError('optimal repeated')):
                run()

    def test_near_miss_uses_budget_plus_512_and_does_not_repeat_optimal(self):
        source = b'abcde' * 600
        optimal_bytes = lz.compress_equipment_optimal(source, stream_tag=1, offset_bits=10, max_encoded_size=10000)
        budget = len(optimal_bytes) - 1
        with patch.object(lz, '_optimal_helper', return_value=None), \
             patch.object(lz, 'compress_equipment_optimal', wraps=lz.compress_equipment_optimal) as optimal:
            for _ in range(2):
                with self.assertRaises(lz.EquipmentSizeOverflow):
                    writer._cached_parse(source, 1, 10, budget)
            self.assertEqual(optimal.call_count, 1)
            self.assertEqual(optimal.call_args.kwargs['max_encoded_size'], budget + 512)

    def test_palette_invariant_floor_stops_all_remaining_rungs(self):
        with tempfile.TemporaryDirectory() as folder:
            f = SizedFixture(Path(folder), width=256, family=4, margin=1000,
                             names=('socks00', 'socks00_mud', 'untouched'))
            with patch.object(lz, '_optimal_helper', return_value=None):
                encoded = lz.compress_equipment_optimal(f.decoded, stream_tag=1, offset_bits=10, max_encoded_size=100000)
            stored = len(encoded) + 16
            span = HEADER.pack(b'TSET', stored, f.chunk.system_bytes, f.chunk.video_bytes,
                               0xFEEDBEEF, stored, 0, 0) + encoded + bytes(16)
            chunk = replace(parse_chunks(span)[0], index=4)
            _, info = decode_chunk(span, parse_chunks(span)[0])
            _, png = f.png()
            payload, rgba, levels = writer._read_png(png, f.rows[0])
            with patch.object(writer, '_rebuild_fixed_span', side_effect=AssertionError('impossible rung parsed')):
                with self.assertRaises(writer.EquipmentFitError) as caught:
                    writer._compile_group(span, chunk, f.decoded, info, f.rows,
                        {r.reference_index: (r, payload, rgba, levels) for r in f.rows}, {0,1,2}, suggest_fit=False)
            self.assertEqual(caught.exception.attempts[0]['proof'], 'palette_invariant_token_bound')
            self.assertTrue(caught.exception.required_is_lower_bound)


class ReopenTests(unittest.TestCase):
    def setUp(self):
        clear()
        self.h = session_tests.EquipmentSessionTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.addCleanup(clear)

    def test_real_import_reopen_memory_disk_art_and_target_invalidation(self):
        h = self.h
        with h.f.context(), patch.object(lz, '_optimal_helper', return_value=None):
            h.stage()
            project = h.root / 'checked.2k5mod'
            h.a.save_shareable_project(project)
            for name, cold in [('warm', False), ('fresh-process-cache', True)]:
                if cold: clear()
                with patch.object(writer, '_compile_group', side_effect=AssertionError('open repeated fit search')):
                    b = h.session(name)
                    start = time.perf_counter()
                    b.load_shareable_project(project)
                    print(f'B70 OPEN {name}: {time.perf_counter()-start:.6f} s', flush=True)
                    self.assertEqual(b.current_path(h.asset).read_bytes(), h.a.current_path(h.asset).read_bytes())
            # A new interpreter must also reuse the checked disk result.
            script = """
from pathlib import Path
import sys
from unittest.mock import patch
from test_nfl2k5_equipment_texture_chain import Fixture, writer
root = Path(sys.argv[1]); f = Fixture(root)
with f.context(), patch.object(writer, '_compile_group', side_effect=AssertionError('cold open recompiled')):
    writer.preflight_project_equipment(root / '0', [(None, f.rows[0].asset_id, Path(sys.argv[2]))])
print('B70 OPEN new interpreter: no fit search')
"""
            environment = dict(os.environ, PYTHONPATH=os.pathsep.join((str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent))))
            child = subprocess.run([sys.executable, '-c', script, str(h.root), str(h.a.current_path(h.asset))],
                env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(child.returncode, 0, child.stderr)
            print(child.stdout.strip(), flush=True)
            # Same path and dimensions, new source pixels: must compile again.
            png = h.f.png(rgba=bytes((200,40,70,255))*1024)[1]
            with patch.object(writer, '_compile_group', wraps=writer._compile_group) as compile:
                writer.preflight_project_equipment(h.cache.pack0, [(None,h.asset.asset_id,png)])
                self.assertEqual(compile.call_count, 1)
            # A different target descriptor/catalog signature invalidates reuse.
            altered = tuple(replace(row, descriptor_flags=row.descriptor_flags ^ 1) for row in h.f.rows)
            with patch.object(writer, 'load_targets', return_value=({r.asset_id:r for r in altered},{(0,8):altered})), \
                 patch.object(writer, '_compile_group', side_effect=ValueError('target invalidated')):
                with self.assertRaisesRegex(ValueError, 'not the reviewed swizzled P8 descriptor'):
                    writer.preflight_project_equipment(h.cache.pack0, [(None,h.asset.asset_id,png)])

    def test_unavailable_cache_fingerprint_still_compiles_valid_import(self):
        h = self.h
        with patch.object(writer, '_stage_disk_cache', side_effect=OSError('source files not available')):
            result = h.stage()
        self.assertTrue(result.modified)

    def test_corrupt_staged_cache_recompiles(self):
        h = self.h
        h.stage()
        clear()
        files = list((h.cache.pack0.parent / '.nfl2k5-equipment-stage-cache').glob('*.json'))
        self.assertTrue(files)
        for path in files: path.write_bytes(b'corrupt')
        with h.f.context(), patch.object(writer, '_compile_group', wraps=writer._compile_group) as compile:
            writer.preflight_project_equipment(h.cache.pack0,
                [(None,h.asset.asset_id,h.a.current_path(h.asset))])
            self.assertEqual(compile.call_count, 1)


if __name__ == '__main__':
    unittest.main()
