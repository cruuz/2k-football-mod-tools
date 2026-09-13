"""Retail-backed bounded native wait evidence. Never claims a played scene load."""
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests', ROOT / 'tools'):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_espn25_rosters as e
from mod_editor.core import nfl2k5_practice_squad as ps
from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL
try:
    from nfl2k5_espn25_in_game import CompletionCPU, evidence, XBE_SHA256
    from unicorn import x86_const as regs
    NATIVE_ERROR = None
except ImportError as exc:
    NATIVE_ERROR = str(exc)


class LoadingWaitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NATIVE_ERROR:
            raise unittest.SkipTest('Unicorn unavailable: ' + NATIVE_ERROR)
        for path in (RETAIL / 'default.xbe', RETAIL / 'vc_53450030/0'):
            if not path.is_file():
                raise unittest.SkipTest('user-owned USA evidence absent: ' + str(path))
        cls.payload = e.read_xbe(RETAIL)
        if e.sha(cls.payload) != XBE_SHA256:
            raise unittest.SkipTest('USA XBE evidence pin differs')
        cls.resources, cls.context, cls.ids = evidence(RETAIL)
        manifest, _ = e.dataset()
        originals = {r['outer']: cls.resources[r['outer']] for r in manifest['resources']}
        compiled, _ = e._compile_resources(originals)
        cls.resources.update(compiled)
        cls.fixed = e.apply_xbe(cls.payload)[0]
        cls.practice = ps.apply(cls.fixed)[0]

    def cpu(self, payload):
        return CompletionCPU(payload, self.resources, self.context, self.ids)

    def receipt(self, name, data):
        folder = os.environ.get('ESPN25_WAIT_RECEIPTS')
        if folder:
            path = Path(folder)
            path.mkdir(parents=True, exist_ok=True)
            (path / (name + '.json')).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')

    def test_wide_right_withheld_completion_stops_at_exact_branch_then_resumes(self):
        for label, payload in (('retail_repaired', self.fixed), ('practice_repaired', self.practice)):
            with self.subTest(stack=label):
                cpu = self.cpu(payload)
                cpu.select(0)
                cpu.match()
                imports_before = len(cpu.imports)
                cpu.hold_completion = True
                with self.assertRaisesRegex(AssertionError, '432ec'):
                    cpu.select(14)
                self.assertEqual(cpu.reg('eip'), 0x432EC)
                self.assertEqual(cpu.r(0xB09584), 1)
                self.assertEqual(cpu.wait_callers[-1], 0x2D1833)
                self.assertEqual(len(cpu.imports), imports_before)  # stalled before C1030, not inside import
                stack = cpu.reg('esp')
                cpu.hold_completion = False
                cpu.uc.emu_start(cpu.reg('eip'), cpu.STOP, count=cpu.instruction_budget)
                self.assertEqual(cpu.reg('eip'), cpu.STOP)
                self.assertEqual(cpu.r(0xB09584), 0)
                cpu.run(0x20C5C0, ecx=0x2310000)
                match = cpu.match()
                self.assertEqual([i['result'] for i in cpu.imports], [1, 1, 1, 1])
                self.assertEqual([match['sides'][s]['quarterback']['last'] for s in ('home', 'away')],
                                 ['Hostetler', 'Kelly'])
                self.receipt(label + '_withheld', {'wait_pc': hex(0x432EC), 'branch': 'je 0x432e0',
                    'caller_return': hex(0x2D1833), 'busy_address': hex(0xB09584), 'busy_when_held': 1,
                    'suspended_esp': hex(stack), 'imports_before_resume': imports_before,
                    'imports_after_resume': cpu.imports, 'match': match,
                    'boundary': 'modeled OS delivery at 38F50 tail-calls native 42FC0 with ECX=0',
                    'observed_game_freeze_reproduced': False, 'in_game': 'UNWITNESSED'})

    def test_all_25_moments_and_reentry_with_native_wait_and_supplied_completions(self):
        for label, payload in (('retail_repaired', self.fixed), ('practice_repaired', self.practice)):
            with self.subTest(stack=label):
                cpu = self.cpu(payload)
                results = []
                for index in (*range(25), 0, 14, 0):
                    cpu.select(index)
                    match = cpu.match()
                    self.assertEqual([i['result'] for i in cpu.imports[-2:]], [1, 1])
                    self.assertEqual(match['export_players'], 106)
                    self.assertNotEqual(match['sides']['home']['team'], match['sides']['away']['team'])
                    self.assertTrue(all(s['kit_exists'] for s in match['sides'].values()))
                    self.assertEqual(cpu.r(0xB09584), 0)
                    results.append({'moment': index, **match})
                self.assertEqual(cpu.deliveries, 56)
                self.assertEqual(len(cpu.wait_callers), 56)
                self.assertEqual(set(cpu.wait_callers), {0x2D1833})
                self.assertTrue(all(r['pointers_after'] == 0 for r in cpu.releases))
                self.receipt(label + '_all_moments', {'results': results, 'imports': cpu.imports,
                    'releases': cpu.releases, 'native_waits': len(cpu.wait_callers),
                    'supplied_completions': cpu.deliveries, 'in_game': 'UNWITNESSED',
                    'complete_scene_load_executed': False})


if __name__ == '__main__':
    unittest.main()
