"""Native passing regression: accuracy, true laterals, Challenges and d2 composition."""
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765 import d2b_passing_probe as probe
from tools.b765 import d2_repair
from mod_editor.core import nfl2k5_throw_tuning as tuning

V04 = Path(os.environ.get('B765_D2_V04_XBE', '/nonexistent-b765-d2-evidence'))


@unittest.skipUnless(V04.is_file(), 'Set B765_D2_V04_XBE to exact extracted v0.4 XBE')
class NativePassingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = V04.read_bytes()
        if d2_repair.sha(cls.pack) != probe.V04_SHA256:
            raise ValueError('Unexpected v0.4 fixture')
        cls.retail = probe.read_retail(probe.DEFAULT_XBE)

    def test_accuracy_launch_and_true_lateral_sign(self):
        machines = [probe.ThrowMachine(data) for data in (self.retail, self.pack)]
        for direction in (-1, 1):
            for depth in (-600., -401., -399., -137.16, 182.88):
                args = dict(receiver=(800., depth), release=-400., kind=7,
                            direction=direction, challenges=0, seed=29)
                old, new = [m.throw(**args) for m in machines]
                old.pop('accuracy_instructions')
                new.pop('accuracy_instructions')
                self.assertEqual(old, new)
                if depth < 91.44:
                    self.assertEqual(new['accuracy_point'], new['target']['point'])
                self.assertEqual(new['kind'], 3 if new['downfield_velocity'] < 0 else 4)

    def test_challenges_changes_ruling_without_reversing_flight(self):
        m = probe.ThrowMachine(self.pack)
        for direction in (-1, 1):
            off = m.throw(receiver=(300., -399.), direction=direction, challenges=0)
            on = m.throw(receiver=(300., -399.), direction=direction, challenges=1)
            self.assertGreater(off['downfield_velocity'], 0)
            self.assertEqual(off['launch_velocity'], on['launch_velocity'])
            self.assertEqual(off['kind'], 4)
            self.assertEqual(on['kind'], 3)

    def test_d2_repairs_preserve_short_throw_and_actual_backward_ruling(self):
        fixed, _ = d2_repair.repair_xbe(self.pack)
        machines = [probe.ThrowMachine(data) for data in (self.pack, fixed)]
        for kind in (1, 7, 9):
            for role in (1, 2, 3, 4):
                for depth in (-600., -137.16, 200.):
                    args = dict(receiver=(800., depth), kind=kind, role=role, seed=17)
                    old, new = [m.throw(**args) for m in machines]
                    self.assertEqual(old, new)
                    if new['downfield_velocity'] < 0:
                        self.assertEqual(new['kind'], 3)

    def test_foreign_pack_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Expected exact'):
            probe.compare(self.retail, self.pack[:-1])

    def test_forward_ruling_repair_preserves_laterals_and_flight(self):
        repaired, receipt = tuning.apply_forward_pass_ruling(self.pack)
        self.assertEqual(tuning.forward_pass_ruling_status(repaired), 'applied')
        self.assertTrue(receipt['outside_scope_identical'])
        self.assertEqual(tuning.apply_forward_pass_ruling(repaired)[0], repaired)
        machines = [probe.ThrowMachine(data) for data in (self.pack, repaired)]
        for direction in (-1, 1):
            for challenges in (0, 1):
                for referee in (-.99, 0., .99):
                    for delta in (-200., -1., 0., 1., 200.):
                        args = dict(receiver=(300., -400. + delta), direction=direction,
                                    challenges=challenges, referee_random=referee)
                        old, new = [m.throw(**args) for m in machines]
                        self.assertEqual(old['launch_velocity'], new['launch_velocity'])
                        self.assertEqual(old['endpoint'], new['endpoint'])
                        self.assertEqual(new['kind'], 3 if new['downfield_velocity'] < 0 else 4)
                        if delta < 0:
                            self.assertEqual(old['kind'], 3)
                            self.assertEqual(old['classifier_flags'], new['classifier_flags'])

    def test_forward_ruling_repair_scope_guards_and_d2_composition(self):
        repaired, receipt = tuning.apply_forward_pass_ruling(self.pack)
        allowed = set()
        for row in receipt['edits']:
            start = int(row['file_offset'], 16)
            allowed.update(range(start, start + row['size']))
        self.assertFalse({i for i, (a, b) in enumerate(zip(self.pack, repaired)) if a != b} - allowed)
        for at in (0x2268DF, 0x226810, 0xA7450, 0x394):
            broken = bytearray(self.pack)
            broken[at] ^= 1
            with self.subTest(offset=hex(at)), self.assertRaises(ValueError):
                tuning.apply_forward_pass_ruling(bytes(broken))
        d2_first = d2_repair.repair_xbe(self.pack)[0]
        self.assertEqual(tuning.apply_forward_pass_ruling(d2_first)[0], d2_repair.repair_xbe(repaired)[0])

    def test_explicit_gameplay_repair_pipeline_includes_ruling_repair(self):
        curves = tuning.curves_for(tuning.TuningSettings(80))
        result, receipt = tuning._apply_all(self.retail, curves, False, forward_pass_ruling=True)
        self.assertEqual(tuning.forward_pass_ruling_status(result), 'applied')
        self.assertIn('forward_pass_ruling_patch', receipt)
        curves_only, _ = tuning._apply_all(self.retail, curves, False)
        self.assertEqual(tuning.forward_pass_ruling_status(curves_only), 'retail')
        plain, _ = tuning._apply_all(self.retail, None, False)
        self.assertEqual(plain, self.retail)

    def test_native_xbe_writer_accepts_ruling_only_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = [Path(folder) / name for name in ('source.xbe', 'fixed.xbe')]
            source.write_bytes(self.retail)
            receipt = tuning.write_xbe_copy(source, target, forward_pass_ruling=True)
            self.assertEqual(source.read_bytes(), self.retail)
            self.assertEqual(target.read_bytes(), tuning.apply_forward_pass_ruling(self.retail)[0])
            self.assertIn('forward_pass_ruling_patch', receipt)


class RepairCliRefusalTests(unittest.TestCase):
    def test_unknown_hash_and_symlink_refused_before_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source, alias, output, receipt = [base / name for name in ('unknown.xbe', 'alias.xbe', 'fixed.xbe', 'receipt.json')]
            source.write_bytes(b'foreign executable')
            alias.symlink_to(source)
            for candidate in (source, alias):
                result = subprocess.run([sys.executable, str(ROOT / 'tools/b765/d2b_repair.py'),
                                         str(candidate), str(output), '--receipt', str(receipt)],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
                self.assertFalse(receipt.exists())
            self.assertEqual(source.read_bytes(), b'foreign executable')


if __name__ == '__main__':
    unittest.main()
