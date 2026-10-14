"""Period field art must survive the game's later team-texture replacement."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_historic_styles as historic
from mod_editor.core import nfl2k5_espn25_rosters as rosters
from mod_editor.core import nfl2k5_modern_metlife as metlife
from test_nfl2k5_team_logo_swap import _field_scene_run, LOADED
from b77 import mo2_repair as repair

DISC = os.environ.get('MO2_DISC')


class Contract(unittest.TestCase):
    def test_names_do_not_match_native_swap_even_case_insensitively(self):
        original = {key.casefold() for key in fields.PERIOD_MATERIALS}
        self.assertEqual(len(original), 7)
        self.assertFalse(original & {key.casefold() for key in fields.PERIOD_MATERIALS.values()})
        for old, new in fields.PERIOD_MATERIALS.items():
            self.assertEqual(len(old), len(new))
        self.assertEqual(fields.PRESERVED_RETAIL_ROWS, (24, 25, 34))


class RepairContract(unittest.TestCase):
    """Exercise actual writes on tiny synthetic files, never an image copy."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.original = self.folder / 'original.bin'
        self.copy = self.folder / 'copy.bin'
        before, after = b'0123456789abcdef', b'0123XYZ789abcdef'
        self.original.write_bytes(before)
        self.copy.write_bytes(before)
        (self.folder / '00.span').write_bytes(b'XYZ')
        self.pins = dict(input_sha256=fields.sha(before), output_sha256=fields.sha(after),
                         size=len(before), spans=[dict(offset=4, length=3, file='00.span',
                         before_sha256=fields.sha(b'456'), after_sha256=fields.sha(b'XYZ'))])
        repair.write_json(self.folder / 'pins.json', self.pins)
        self.addCleanup(patch.stopall)
        patch.object(repair, 'PINS', self.folder / 'pins.json').start()
        patch.object(repair, 'BASE_SHA', fields.sha(before)).start()
        self.receipt = self.folder / 'receipt.json'

    def test_fixed_span_write_replay_and_full_scope(self):
        with contextlib.redirect_stdout(io.StringIO()):
            repair.apply(self.copy, self.folder, self.receipt)
            self.assertEqual(json.loads(self.receipt.read_text())['written_bytes'], 3)
            repair.apply(self.copy, self.folder, self.receipt)
            self.assertEqual(json.loads(self.receipt.read_text())['written_bytes'], 0)
            repair.scope(self.original, self.copy, self.receipt)
        self.assertEqual(self.copy.read_bytes(), b'0123XYZ789abcdef')
        self.assertEqual(json.loads(self.receipt.read_text())['changed_outside_spans'], 0)

    def test_unknown_input_refused_before_write(self):
        unknown = b'unknown candidate'
        self.copy.write_bytes(unknown)
        with self.assertRaisesRegex(ValueError, 'unknown input disc'):
            repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.copy.read_bytes(), unknown)
        self.assertFalse(self.receipt.exists())

    def test_tampered_payload_refused_before_write(self):
        (self.folder / '00.span').write_bytes(b'BAD')
        with self.assertRaisesRegex(ValueError, 'payload hash mismatch'):
            repair.apply(self.copy, self.folder, self.receipt)
        self.assertEqual(self.copy.read_bytes(), self.original.read_bytes())

    def test_scope_rejects_change_outside_spans(self):
        self.copy.write_bytes(b'0123XYZ789abcde!')
        self.pins['output_sha256'] = fields.sha(self.copy.read_bytes())
        repair.write_json(self.folder / 'pins.json', self.pins)
        with self.assertRaisesRegex(ValueError, 'out-of-scope change'):
            repair.scope(self.original, self.copy, self.receipt)

    def test_studio_comparison_records_mismatch_and_refuses_success(self):
        source = MagicMock()
        source.__enter__.return_value = source
        source.get.return_value = b'original bundle'
        with patch.object(historic, 'Source', return_value=source), \
             patch.object(fields, 'catalog', return_value=[dict(row=45)]), \
             patch.object(fields, 'repair_situ', return_value=(b'', {})), \
             patch.object(fields, 'variant', return_value='nd'), \
             patch.object(fields, 'protect_period_field', return_value=(b'repaired bundle', {})), \
             patch.object(fields, '_field_chunk', return_value=(None, None, None)), \
             patch.object(metlife, 'scene_span', side_effect=lambda bundle, chunk: bundle), \
             patch.object(fields, 'compile_assets', return_value=({'a44nd.iff': b'wrong bundle'}, {})):
            with self.assertRaisesRegex(ValueError, 'Studio field output differs'):
                repair.studio(self.original, self.original, self.receipt)
        result = json.loads(self.receipt.read_text())
        self.assertEqual(result['byte_equal'], 0)
        self.assertFalse(result['physical_disc_written'])

    def test_studio_reports_non_field_drift_separately(self):
        source = MagicMock()
        source.__enter__.return_value = source
        source.get.return_value = b'original bundle'
        with patch.object(historic, 'Source', return_value=source), \
             patch.object(fields, 'catalog', return_value=[dict(row=45)]), \
             patch.object(fields, 'repair_situ', return_value=(b'', {})), \
             patch.object(fields, 'variant', return_value='nd'), \
             patch.object(fields, 'protect_period_field', return_value=(b'field|original wall', {})), \
             patch.object(fields, '_field_chunk', return_value=(None, None, None)), \
             patch.object(metlife, 'scene_span', side_effect=lambda bundle, chunk: bundle.split(b'|')[0]), \
             patch.object(fields, 'compile_assets', return_value=({'a44nd.iff': b'field|current wall'}, {})), \
             contextlib.redirect_stdout(io.StringIO()):
            repair.studio(self.original, self.original, self.receipt)
        result = json.loads(self.receipt.read_text())
        self.assertEqual(result['equal_field_spans'], 1)
        self.assertEqual(result['byte_equal'], 0)


@unittest.skipUnless(DISC, 'set MO2_DISC to the read-only candidate disc')
class Candidate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = rosters.read_xbe(Path(DISC))
        with historic.Source(Path(DISC)) as source:
            cls.bundle = source.get('a44nd.iff')
        cls.fixed, cls.receipt = fields.protect_period_field(cls.bundle)

    def test_only_material_strings_change_after_decompression(self):
        _, before, raw = fields._field_chunk(self.bundle)
        _, after, fixed = fields._field_chunk(self.fixed)
        restored = bytearray(fixed)
        for row in self.receipt['name_ranges']:
            at, size = row['offset'], row['size']
            restored[at:at + size] = raw[at:at + size]
        self.assertEqual(restored, raw)
        self.assertEqual(self.receipt['decoded_changed_bytes'], 37)
        self.assertEqual(before['system_bytes'], after['system_bytes'])
        end = self.receipt['field_offset'] + self.receipt['field_size']
        self.assertEqual(self.bundle[end:], self.fixed[end:])
        self.assertEqual(len(self.bundle), len(self.fixed))

    def test_replay_and_incomplete_name_refusal(self):
        replay, receipt = fields.protect_period_field(self.fixed)
        self.assertEqual(replay, self.fixed)
        self.assertEqual(receipt['decoded_changed_bytes'], 0)
        chunk, rec, decoded = fields._field_chunk(self.bundle)
        rec['materials'][1]['name'] = 'foreign'
        with patch.object(fields, '_field_chunk', return_value=(chunk, rec, decoded)):
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                fields.protect_period_field(self.bundle)

    @unittest.skipUnless(importlib.util.find_spec('unicorn'), 'Unicorn required')
    def test_real_candidate_swap_overwrites_old_names_but_preserves_new(self):
        before = [m['name'] for m in fields._field_chunk(self.bundle)[1]['materials']]
        after = [m['name'] for m in fields._field_chunk(self.fixed)[1]['materials']]
        overwritten, _ = _field_scene_run(self.xbe, before, LOADED)
        retained, _ = _field_scene_run(self.xbe, after, LOADED)
        self.assertEqual(sum(value is not None for value in overwritten.values()), 7)
        self.assertTrue(all(value is None for value in retained.values()))
        # Regular fields still go through the unmodified native swap.
        self.assertEqual(_field_scene_run(self.xbe, before, LOADED)[0], overwritten)

    def test_build_calls_the_same_transform_after_paint_compilation(self):
        row = fields.catalog()[44]
        situ = bytearray(32 + 0x44 + 51 * 0x6c)
        import struct
        struct.pack_into('<I', situ, 32 + 0x40, 51)
        with patch.object(fields, 'catalog', return_value=[row]), \
             patch.object(fields, '_wordmark', return_value=None), \
             patch.object(fields, '_field', return_value=(self.bundle[:self.receipt['field_size']], {})):
            resources, receipt = fields.compile_assets(lambda _: self.bundle, lambda _: self.bundle, bytes(situ))
        self.assertEqual(resources['a44dd.iff'], self.fixed)
        self.assertTrue(receipt['assets'][0]['detail']['period_material_protection']['textures_and_geometry_identical'])


if __name__ == '__main__':
    unittest.main()
