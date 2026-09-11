"""Berman/kickoff and SEGA bounded native regression matrix.

No movie, device, disc build or console acceptance is claimed. The fixture
declares asynchronous loading/arrival/contact inputs and bounds every run.
Run standalone; --record writes derived diagnostics, never retail assets.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_b661_transition import compose, plan_for, DISC
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes, HAVE_UC
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core import nfl2k5_xbe_space as space

RECORD = '--record' in sys.argv
if RECORD:
    sys.argv.remove('--record')
RESULTS = {}


def machine(payload):
    m = Machine(payload)
    image = XbeImage(payload)
    m.uc.mem_write(image.base, payload[:image.headers_size])
    m.uc.mem_protect(image.base, 4096, m.u.UC_PROT_READ | m.u.UC_PROT_EXEC)
    if space.status(payload) == 'applied':
        for region in space.layout(payload)['regions']:
            s = image.section(region['va'])
            flags = m.u.UC_PROT_READ | (m.u.UC_PROT_WRITE if s.writable else 0) | (m.u.UC_PROT_EXEC if s.executable else 0)
            m.uc.mem_protect(region['va'], region['size'], flags)
    return m


def boot_wait(payload, complete_after):
    """Actual final-SEGA load wait. 38F50 supplies asynchronous I/O completion.

    432C0 itself is native; its B09584 queue predicate and the backward JE at
    7423D are never stubbed. This does not execute an Xbox file/DVD driver.
    """
    m = machine(payload)
    m.put(m.ARENA, 0x7fffffff)  # next splash deadline
    m.put(m.ARENA + 4, 0)
    m.put(m.ARENA + 32, 1)  # segalogo, last still splash
    m.put(0xB09584, m.ARENA + 64)  # outstanding resource request
    polls = []
    def pump():
        polls.append(m.get(0xB09584))
        if complete_after is not None and len(polls) >= complete_after:
            m.put(0xB09584, 0)
        m.ret()
    m.leaf(0x73E40, lambda: (m.reg('EDX', 0), m.ret(1)), reason='hardware tick source')
    m.leaf(0x38F50, pump, reason='asynchronous I/O pump completion input')
    try:
        m.call(0x74180, edi=m.ARENA, args=(m.ARENA + 32,), budget=1000)
        outcome = 'returned'
        assert m.reg('ESP') == m.STACK + 8, 'boot RET 4 ABI'
    except AssertionError as exc:
        if 'instruction budget exhausted' not in str(exc):
            raise
        outcome = 'bounded_wait'
    return dict(outcome=outcome, polls=len(polls), pc=hex(m.reg('EIP')),
                queue=hex(m.get(0xB09584)), leaves=m.leaves)


class PlanTests(unittest.TestCase):
    def test_reference_options_and_unavailable_owners(self):
        from dataclasses import replace
        from mod_editor.core import mod_build as mb
        advanced, full = plan_for('advanced'), plan_for('everything')
        self.assertFalse(advanced.dynamic_kickoff)
        self.assertFalse(advanced.my_career)
        for key in ('dynamic_kickoff', 'accelerated_clock', 'music_shuffle', 'screen_hooks',
                    'playbook_pair', 'read_option_runtime', 'qb_spy', 'scorebug_runtime',
                    'guardian_overlay', 'abilities', 'deep_zone_bail', 'weekly_prep', 'my_career'):
            self.assertTrue(getattr(full, key), key)
        for key, message in (('franchise_2026_rules', 'native saved counters'),
                             ('senior_bowl', 'simulation is unavailable')):
            with self.assertRaisesRegex(ValueError, message):
                mb._validated_r62_plan_options(replace(full, **{key: True}))


@unittest.skipUnless(HAVE_UC and DISC.is_file(), 'Unicorn and private USA disc required for real Build-tab intent compilation')
class TransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.payloads = {'retail': cls.retail}
        for name in ('advanced', 'simwin66', 'everything', 'everything_no_career'):
            payload, receipt = compose(cls.retail, plan_for(name))
            cls.payloads[name] = payload
            RESULTS[name] = dict(xbe_sha256=hashlib.sha256(payload).hexdigest(), build=receipt)
        RESULTS['retail'] = dict(xbe_sha256=hashlib.sha256(cls.retail).hexdigest())

    def test_sega_loader_completes_or_reports_pending_queue_for_every_preset(self):
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                # No selected owner edits this wait loop or its queue predicate.
                before, after = XbeImage(self.retail), XbeImage(payload)
                for va, size in ((0x74180, 0xCC), (0x432C0, 14), (0x4E9720, 48)):
                    self.assertEqual(before.read(va, size), after.read(va, size))
                ready, pending = boot_wait(payload, 3), boot_wait(payload, None)
                self.assertEqual((ready['outcome'], ready['polls']), ('returned', 3))
                self.assertEqual(pending['outcome'], 'bounded_wait')
                self.assertNotEqual(pending['queue'], '0x0')
                RESULTS[name]['sega'] = dict(completed=ready, pending=pending)

    def test_all_27_frame_phases_and_header_code_execute(self):
        from tests.nfl2k5_kickoff_frame import FrameMachine, PHASES
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                m = FrameMachine(payload)
                for _ in range(8):
                    m.frame()
                counts = {hex(pc): m.visited[pc] for pc in PHASES}
                self.assertEqual(set(counts.values()), {8})
                RESULTS[name]['frame_phases'] = counts

    def test_native_completed_lineup_readiness_and_approach(self):
        from tests.mod_editor.test_nfl2k5_kickoff_v5 import NativeSetupMachine
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                m = NativeSetupMachine(payload)
                m.complete_lineup(m.players)
                states = []
                for frame in range(32):
                    m.setup_frame = frame
                    m.frame()
                    states.append(m.get(0xE602B8))
                    if states[-1] == 13:
                        break
                self.assertEqual(states[-1], 13, f'{name}: lineup wait {states}')
                m.approach()
                self.assertEqual(m.get(0xE602B8), 14)
                RESULTS[name]['readiness'] = dict(states=states, approach=14, state_writes=m.state_writes)

    def test_camera_row7_state7_and_first_play_selection_on_composed_presets(self):
        from tests.mod_editor.test_nfl2k5_presentation_v6 import CameraV6Tests
        for name, payload in self.payloads.items():
            if name == 'retail':
                continue
            with self.subTest(name=name):
                case = CameraV6Tests('test_kickoff_setup_and_actual_native_row7_lookup')
                case.patched = payload
                case.test_kickoff_setup_and_actual_native_row7_lookup()
                RESULTS[name]['camera'] = 'native state 7 -> row 7 -> selected kickoff state 8'

    def test_v6_catch_kneel_and_next_play_with_optional_owners(self):
        from tests.mod_editor.test_nfl2k5_kickoff_v6 import replay
        from mod_editor.core import nfl2k5_dynamic_kickoff as dk
        for name in ('simwin66', 'everything', 'everything_no_career'):
            with self.subTest(name=name):
                case, _ = replay(self, self.payloads[name], dk.FLAGS, 1, -6)
                self.assertIsNotNone(case['next_play'])
                RESULTS[name]['touchback'] = dict(frames=len(case['rows']), next_play=case['next_play'])


if __name__ == '__main__':
    result = unittest.main(exit=False).result
    if RECORD:
        (ROOT / 'docs/nfl2k5_b661_transition_receipts.json').write_text(
            json.dumps(dict(scope='bounded native execution; in-game UNWITNESSED',
                            cases=RESULTS, successful=result.wasSuccessful()), indent=2) + '\n', encoding='utf-8')
    sys.exit(not result.wasSuccessful())
