"""Native snap/frame/dead-ball series for the decided clock and its clock neighbor.

No physical-play or rendered witness. Inherits the declared beta-68 scene,
device, animation-ready and snap/completed-play input boundaries.
"""
from pathlib import Path
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_b69_rules_native import uc
from mod_editor.core import nfl2k5_decided_clock as decided
from mod_editor.core import nfl2k5_accelerated_clock as accelerated
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_xbe_space as space


@unittest.skipUnless(uc is not None, 'Unicorn required for native series')
class SeriesTests(unittest.TestCase):
    def test_decided_undecided_trailing_and_ot_through_native_dead_ball(self):
        from tests.nfl2k5_b68_series import Machine, ready_input, snap_input
        payload = space.apply(retail_xbe(), mode.REQUESTS+decided.REQUESTS+accelerated.REQUESTS,
                              scaleout=True)[0]
        for owner, options in ((mode, {}), (decided, {}), (accelerated, dict(enabled=True))):
            payload = owner.apply(payload, **options)[0]
        rows = []
        with Machine(payload) as m:
            m.series_scene()
            m.presentation_services()
            ready_input(m)
            snap_input(m)
            initial = m.checkpoint()
            for name, period, margin, zero in (('decided', 4, 17, True), ('undecided', 4, 16, False),
                    ('trailing_possession', 4, -17, False), ('overtime', 5, 17, False)):
                with self.subTest(situation=name):
                    m.restore(initial)
                    offense, defense = m.get(0xE60280), m.get(0xE60284)
                    timer = m.get(0xE6028C)
                    # Scenario time/score inputs while the native play is live.
                    m.put(0xE602C4, period)
                    m.put(m.get(offense+8), 30+margin)
                    m.put(m.get(defense+8), 30)
                    m.f32(timer+16, 60)
                    self.assertEqual(m.get(0xE602B8), 14)
                    m.presented_frame()
                    live = m.f32(timer+16)
                    self.assertGreater(live, 59)
                    self.assertEqual(m.get(0xE602B8), 14)
                    m.call(0xA0390, budget=3000000)
                    final = m.f32(timer+16)
                    self.assertEqual(m.get(0xE602B8), 18)
                    self.assertEqual(m.get(0xE60280), offense)
                    self.assertEqual(final, 0 if zero else live)
                    rows.append(dict(situation=name, period=period, margin=margin,
                                     live_state=14, live_seconds=live, dead_ball_state=18,
                                     dead_ball_seconds=final, offense_retained=True))
        destination = os.environ.get('NFL2K5_B69_RULES_SERIES_TRACE')
        if destination:
            Path(destination).write_bytes((json.dumps(dict(runtime_witnessed=False,
                accelerated_clock='On/20', cases=rows,
                boundary='native selected scene and frame; readiness, snap and dead-ball commands supplied'),
                indent=2)+'\n').encode())


if __name__ == '__main__':
    unittest.main()
