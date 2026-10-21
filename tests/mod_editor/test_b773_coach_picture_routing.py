"""League coach pictures survive the last Studio pass; plain builds never retain rejected renders."""
from pathlib import Path
import os
import sys
import unittest
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_modern_coaches as mc
from tools.b77 import pr2_repair as repair

BASE = Path(os.environ.get('NFL2K5_PR2_BASE', 'missing-pr2-input'))
CO3 = Path(os.environ.get('NFL2K5_PR2_CO3', 'missing-co3-input'))


class Rules(unittest.TestCase):
    def test_repair_inputs_are_explicit_and_scope_detects_escape(self):
        self.assertEqual(len(repair.INPUTS), 2)
        self.assertEqual(repair.outside_count([(9, 13), (19, 22)], [(10, 20, 'portrait')]), 3)
        self.assertEqual(repair.outside_count([(10, 12)], [(10, 20, 'portrait')]), 0)
        with self.assertRaisesRegex(ValueError, 'REFUSED'):
            repair.require(False, 'unknown hash')

    def test_unknown_original_hash_refused_before_compilation_or_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original, image = root / 'original', root / 'copy'
            original.write_bytes(b'bad')
            image.write_bytes(b'bad')
            args = ['--image', str(image), '--original', str(original), '--index', str(root / '0'),
                    '--project', str(root / 'project.json'), '--receipts', str(root / 'receipts')]
            with mock.patch.object(repair, 'INPUT_SIZE', 3), mock.patch.object(repair, 'compile_project') as compile_:
                with self.assertRaisesRegex(ValueError, 'unknown original hash'):
                    repair.main(args)
                compile_.assert_not_called()
            self.assertEqual(image.read_bytes(), b'bad')

    def test_pin_generator_preserves_rejected_render_ids_without_png_inputs(self):
        import contextlib
        import io
        from tools.b77 import co2_record_pins as generator
        captured = {}
        def record(_retail, _teams, portraits, _superseded):
            captured['portraits'] = portraits
            return {'teams': []}
        with mock.patch.object(mc, 'record_pins', side_effect=record), contextlib.redirect_stdout(io.StringIO()):
            generator.main(['--retail', 'unused.iso'])
        for generated, pinned in zip(captured['portraits'], mc.pins()['portraits']):
            self.assertNotIn('png', generated)
            self.assertEqual(generated['rejected_sha256'], pinned['rejected_sha256'])

    def test_slot_contract_has_no_photo_or_render_asset(self):
        self.assertTrue(mc.available())
        for row in mc.pins()['portraits']:
            self.assertFalse({'png', 'png_sha256'} & row.keys())
            self.assertNotIn(row['applied_sha256'], row['rejected_sha256'])

    @unittest.skipUnless(BASE.is_file(), 'set NFL2K5_PR2_BASE')
    def test_existing_real_headshots_survive_final_studio_pass(self):
        plan, rows = mc.plan_image(BASE)
        self.assertFalse(plan)
        portraits = [r for r in rows if r['kind'] == 'portrait']
        self.assertEqual(len(portraits), 2)
        self.assertEqual({r['state_before'] for r in portraits}, {'kept'})
        self.assertEqual(mc.image_status(BASE), 'applied')
        from mod_editor.core import nfl2k5_coach_ai as ai
        gate = ai.roster_readiness(BASE)
        self.assertTrue(gate['ready'])
        self.assertEqual(gate['checked'], 32)

    @unittest.skipUnless(BASE.is_file(), 'set NFL2K5_PR2_BASE')
    def test_coach_sync_uses_real_disc_names_and_reserved_ids(self):
        import struct
        from tests.mod_editor.test_franchise_upgrade import fixture, with_coaches
        from mod_editor.core import nfl2k5_franchise_upgrade as up
        saved = with_coaches(fixture()[0], [('Dan', 'Quinn', 29, 7029),
                                          ('Brian', 'Schottenheimer', 7, 7007)])
        with mc._outer_image()(BASE) as arc:
            _base, document = mc._roster(arc)
        result, receipt = up.sync_coaches(saved, bytes(document.body))
        self.assertEqual(struct.unpack_from('<H', result, 0x84040)[0], 7034)
        self.assertEqual(struct.unpack_from('<H', result, 0x84000 + 0xA8 + 0x40)[0], 7031)
        self.assertEqual({r['coach'] for r in receipt['matched']}, {'Dan Quinn', 'Brian Schottenheimer'})
        self.assertFalse(up.sync_coaches(result, bytes(document.body))[1]['changes'])

    @unittest.skipUnless(CO3.is_file(), 'set NFL2K5_PR2_CO3')
    def test_plain_studio_removes_both_rejected_renders(self):
        plan, rows = mc.plan_image(CO3)
        written = [r for r in rows if r['written']]
        self.assertEqual([(r['kind'], r['team']) for r in written], [('portrait', 'DAL'), ('portrait', 'WAS')])
        self.assertEqual(len(plan), 2)
        for (_at, before, after), row in zip(plan, mc.pins()['portraits']):
            self.assertIn(mc.sha(before), row['rejected_sha256'])
            self.assertEqual(mc.sha(after), row['applied_sha256'])
            self.assertEqual(before[:160], after[:160])


if __name__ == '__main__':
    unittest.main()
