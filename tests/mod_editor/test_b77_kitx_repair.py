"""Combined repair ordering, exclusion, hash gates, derivation and scope."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools/b77'), str(ROOT / 'tools')]
import kitx_repair as k

DISC = Path('/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso')


class CombinedTests(unittest.TestCase):
    def test_output_space_guard_reserves_root_on_root_destination(self):
        with patch.object(k.os, 'stat', return_value=SimpleNamespace(st_dev=1)), \
                patch.object(k.Path, 'exists', return_value=True), \
                patch.object(k.shutil, 'disk_usage', return_value=SimpleNamespace(free=52 * 1024**3)):
            with self.assertRaisesRegex(ValueError, 'root disk floor'):
                k.require_output_room(Path('/tmp/new/0'), 3 * 1024**3)

    def test_output_space_guard_allows_bounded_tmpfs_without_50_gib_tmpfs(self):
        def stat(path):
            return SimpleNamespace(st_dev=1 if str(path) == '/' else 2)
        def usage(path):
            return SimpleNamespace(free=(51 if str(path) == '/' else 4) * 1024**3)
        with patch.object(k.os, 'stat', side_effect=stat), \
                patch.object(k.Path, 'exists', return_value=True), \
                patch.object(k.shutil, 'disk_usage', side_effect=usage):
            k.require_output_room(Path('/dev/shm/new/0'), 3 * 1024**3)
            with self.assertRaisesRegex(ValueError, 'output filesystem'):
                k.require_output_room(Path('/dev/shm/new/0'), 4 * 1024**3)

    def test_output_space_guard_still_requires_root_reserve_for_tmpfs(self):
        with patch.object(k.os, 'stat', side_effect=lambda p: SimpleNamespace(st_dev=1 if str(p) == '/' else 2)), \
                patch.object(k.Path, 'exists', return_value=True), \
                patch.object(k.shutil, 'disk_usage', return_value=SimpleNamespace(free=49 * 1024**3)):
            with self.assertRaisesRegex(ValueError, 'root disk floor'):
                k.require_output_room(Path('/dev/shm/new/0'), 1)

    def test_order_requires_all_jobs_and_u3r_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'plan.json'
            doc = dict(jobs=[dict(job=j) for j in k.ORDER], baseline_sha256=k.BASELINE_SHA256)
            k.write_json(p, doc)
            self.assertEqual(k.load_plan(p), doc)
            doc['jobs'][-1], doc['jobs'][-2] = doc['jobs'][-2], doc['jobs'][-1]
            k.write_json(p, doc)
            with self.assertRaisesRegex(ValueError, 'u3r LAST'):
                k.load_plan(p)

    def test_jax5_excluded_jax6_retained(self):
        self.assertEqual(k.selected_keys(['JAX:5', 'JAX:6', 'LV:4']), ['JAX:6', 'LV:4'])

    def test_u3c_keys_reject_jax5_and_missing_bold_city(self):
        self.assertEqual(k.u3c_keys(','.join(k.U3C_KEYS)), list(k.U3C_KEYS))
        for keys in [','.join(k.U3C_KEYS + ('JAX:5',)), ','.join(k.U3C_KEYS[1:])]:
            with self.assertRaisesRegex(ValueError, 'exclude JAX:5'):
                k.u3c_keys(keys)

    def test_jax6_label_is_alternate_one_after_exclusion(self):
        self.assertEqual(k.label_for('JAX:6', {'label':[2026,2]}), (2026,1))
        self.assertEqual(k.uniforms.us.style_label(6, *k.label_for('JAX:6', {'label':[2026,2]})), '2026  Alternate 1')

    def test_uniform_order_last_writer_wins(self):
        calls = []
        def apply(data, patches):
            calls.append(patches[0]['data'])
            return patches[0]['data'], {}
        groups = [('u3a', {1: [dict(offset=0, length=1, data=b'a')]}),
                  ('u3r', {1: [dict(offset=0, length=1, data=b'r')]})]
        with patch.object(k.uniforms, 'apply_patches', apply), patch.object(k.last, 'apply_patches', apply):
            result, _, _ = k.apply_uniforms(b'x', 1, groups)
        self.assertEqual(calls, [b'a', b'r'])
        self.assertEqual(result, b'r')

    def test_second_run_noop_and_unexpected_hash_refused(self):
        self.assertFalse(k.validate_input(b'original', b'original', b'fixed'))
        self.assertTrue(k.validate_input(b'fixed', b'original', b'fixed'))
        with self.assertRaisesRegex(ValueError, 'unexpected input hash'):
            k.validate_input(b'foreign', b'original', b'fixed')

    def test_scope_merges_overlaps_and_detects_unowned_change(self):
        self.assertEqual(k.merge_ranges([(3, 6), (1, 4), (9, 10)]), [(1, 6), (9, 10)])
        self.assertEqual(k.outside_hash(b'abcdef', [(1, 3)]), k.outside_hash(b'aXXdef', [(1, 3)]))
        self.assertNotEqual(k.outside_hash(b'abcdef', [(1, 3)]), k.outside_hash(b'aXXdeZ', [(1, 3)]))

    @unittest.skipUnless(DISC.is_file(), 'shipped disc unavailable')
    def test_three_untouched_spans_match_w1_pins_and_are_idempotent(self):
        rows = json.loads(k.w1.KIT_MANIFEST.read_text())['spans']
        # Rams shipped alternates are outside all u1/u2 primary spans.
        rows = [r for r in rows if r['selector'] == '23H10']
        self.assertEqual(len(rows), 3)
        with k.bump._Image.open(DISC, writable=False) as image:
            index = k.bump._parsed_index(image)
            for row in rows:
                entry = k.w1._entry_for(index, k.bump, row['selector'])
                self.assertEqual(index.sub_extents(entry, row['resource_offset'], row['length']),
                                 ((row['pack'], row['pack_offset'], row['length']),))
                span = image.read_pack(row['pack'], row['pack_offset'], row['length'])
                fixed, _ = k.w1.rewrite_chunk(span)
                self.assertEqual(k.sha(fixed), row['after_sha256'])
                self.assertEqual(k.w1.rewrite_chunk(fixed)[0], fixed)
                self.assertGreater(k.check_mud(span, fixed), 0)

    @unittest.skipUnless(DISC.is_file(), 'shipped disc unavailable')
    def test_studio_wrapper_drops_stale_scratch_floor_without_changing_stream(self):
        with k.bump._Image.open(DISC, writable=False) as image:
            span = image.read_pack(k.PACK_NAMES.index('A'), 136338560, 12416)
        fields = list(k.HEADER.unpack_from(span))
        fields[5] += 4096
        inflated = k.HEADER.pack(*fields) + span[k.HEADER.size:]
        fixed = k.studio_wrapper_span(span, inflated)
        self.assertEqual(fixed[k.HEADER.size:], span[k.HEADER.size:])
        self.assertEqual(k.decode_chunk(fixed, k.parse_chunks(fixed)[0])[0],
                         k.decode_chunk(span, k.parse_chunks(span)[0])[0])
        self.assertLess(k.HEADER.unpack_from(fixed)[5], fields[5])
        self.assertEqual(k.studio_wrapper_span(span, fixed), fixed)


if __name__ == '__main__':
    unittest.main()
