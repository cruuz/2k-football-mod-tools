"""Native play-call policy, two hand-backs and persisted post-game settings."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_my_career_fixture import HAVE_UC, XBE
from mod_editor.core import nfl2k5_my_career_mode as mode


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA retail XBE/ROST and Unicorn required')
class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.payload = mode.apply(retail_bytes())[0]

    def test_every_position_policy_and_opposite_unit_eligibility(self):
        from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests
        from tests.nfl2k5_my_career_mode_fixture import Machine
        for position in range(17):
            for away in (False, True):
                with Machine(self.payload) as m:
                    body, side = ControlTests().load(m, position, away)
                    other = 0xE5FC20 if away else 0xE5FC60
                    offense = position in (0, 3, 7, 8, 9, 12, 13, 14)
                    m.put(0xE60280, side if offense else other)
                    m.put(0xE60284, other if offense else side)
                    m.put(0xE602B4, 4)
                    for policy in range(3):
                        m.put(m.state + 2736, policy)
                        # Zero preserves beta 68, including its lineman and
                        # special-team eligibility. The other values restrict it.
                        expected = position not in (1, 2, 12, 13, 14) and (
                            policy == 0 or policy == 1 and position in (0, 11))
                        self.assertEqual(bool(m.call('mode_human', ecx=side)), expected,
                                         (position, away, policy))
                        self.assertEqual(m.call('mode_human', ecx=other), 0)
                        self.assertEqual(m.call('mode_unit_present'), body)

    def test_two_handbacks_per_value_offensive_and_defensive_signal_callers(self):
        from tests.nfl2k5_b69_series import policy_probe
        for position in (0, 11):
            for policy in range(3):
                with self.subTest(position=position, policy=policy):
                    try:
                        result = policy_probe(self.payload, position, policy)
                    except Exception:
                        import traceback
                        traceback.print_exc()
                        sys.stderr.flush()
                        raise
                    self.assertEqual(len(result['handbacks']), 2)
                    self.assertEqual(result['postgame_policy'], policy)
                    print('\nB69_PLAYCALL_RECEIPT ' + json.dumps(result, sort_keys=True), flush=True)

    def test_by_position_coach_possession_for_hb(self):
        from tests.nfl2k5_b69_series import policy_probe
        for position in (7,):
            with self.subTest(position=position):
                result = policy_probe(self.payload, position, 1, drives=3)
                self.assertEqual(len(result['handbacks']), 1)
                self.assertFalse(result['handbacks'][0]['menu'])
                print('\nB69_PLAYCALL_RECEIPT ' + json.dumps(result, sort_keys=True), flush=True)

    def test_returning_call_retires_old_arrival_before_native_clip_prefetch(self):
        from tests.nfl2k5_supersim_scheduler import Machine
        # Supply a settled CPU formation. Only the menu renderer and the final
        # asynchronous resource request are boundaries. The installed handoff,
        # native arrival producer and native prefetch predicate all execute.
        for policy in (0, 2):
            with self.subTest(policy=policy), Machine(self.payload) as m:
                m.setup()
                m.put(m.state + 2736, policy)
                m.put(m.state + 2708, 1)
                offense, defense = 0xE5FC20, 0xE5FC60
                m.put(offense + 4, m.actors[0])
                for i, actor in enumerate(m.actors):
                    m.put(actor + 0x38, offense if i < 11 else defense)
                    m.put(actor + 0x34, m.actors[i + 1] if i < 10 else 0)
                    m.put(m.get(actor + 0x10) + 0x8C, 0x09008300)
                menus, prefetches = [], []
                m.replace_stub(0xACB90, lambda: m.ret())
                m.replace_stub(0x9FBE0, lambda: (menus.append(True), m.ret()))
                m.replace_stub(0x1FE930, lambda: (prefetches.append(True), m.ret()))
                self.assertEqual(m.call('mode_ff_ready', ecx=m.manager), 0)
                self.assertEqual(bool(menus), policy == 0)
                for i, actor in enumerate(m.actors):
                    expected = 0x08008300 if policy == 0 and i < 11 else 0x09008300
                    self.assertEqual(m.get(m.get(actor + 0x10) + 0x8C), expected)
                if policy != 0:
                    continue
                choice = m.get(offense + 12)
                m.put(choice + 36, m.get(choice + 36) | 2)
                m.put(0xBF0E88, 1)
                # Two actors arrive first while other streamed clips still run.
                # Old code retained their old arrival bits and evicted clips.
                for actor in m.actors[:2]:
                    m.call(0x1FEB20, eax=actor)
                m.call(0x1FF920)
                self.assertEqual(prefetches, [])
                for actor in m.actors[2:11]:
                    m.call(0x1FEB20, eax=actor)
                m.call(0x1FF920)
                self.assertEqual(prefetches, [True])


if __name__ == '__main__':
    unittest.main()
