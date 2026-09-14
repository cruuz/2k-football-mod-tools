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


if __name__ == '__main__':
    unittest.main()
