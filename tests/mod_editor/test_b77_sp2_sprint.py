"""N29: execute the pinned v0.6.1 sprint code with Dike's disc roster flags.

Set B773_SP2_BASE_XBE and NFL2K5_RETAIL_XBE to private extracted fixtures.
These bounded native replays do not simulate collisions or world displacement.
"""
from pathlib import Path
import hashlib
import itertools
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_tap_burst as burst
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
try:
    from tests.nfl2k5_sprint_machine import SprintMachine
except ImportError:
    SprintMachine = None

BASE = Path(os.environ.get("B773_SP2_BASE_XBE", "/nonexistent/base.xbe"))
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XBE", "/nonexistent/retail.xbe"))
BASE_SHA256 = "1b41ec19aac6377484b9b30ee7a5c5ab220fb93d61aa3c14bafdb70092a9504f"
# Primary roster 1531, Chimere Dike: Speed 93, Break Tackle 17.
# Footer 0x0014 contains depth-chart locks, with no star or ability permission.
DIKE_SPEED, DIKE_FLAGS = 93, 0x0014


@unittest.skipUnless(SprintMachine and BASE.is_file() and RETAIL.is_file(),
                     "Unicorn and the pinned base/retail fixtures required")
class DikeSprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = BASE.read_bytes()
        retail = RETAIL.read_bytes()
        assert hashlib.sha256(cls.base).hexdigest() == BASE_SHA256
        assert hashlib.sha256(retail).hexdigest() == RETAIL_SHA256
        settings = abilities.read_settings(cls.base)
        keys = ("lock_speedster", "lock_right_stick", "lock_special_moves",
                "right_stick_stars_only", "charge_stars_only",
                "button_moves_stars_only", "star_access")
        cls.source = abilities.apply_rating_rules(retail, **{k: settings[k] for k in keys})[0]

    def test_installed_rules_and_source_replay(self):
        self.assertEqual(abilities.revision(self.base), "universal-sprint")
        self.assertEqual(burst.status(self.base), "applied")
        settings = abilities.read_settings(self.base)
        for name in ("charge_stars_only", "right_stick_stars_only", "lock_speedster"):
            self.assertTrue(settings[name])
        self.assertEqual(abilities.apply_rating_rules(self.base)[0], self.base)

    def test_dike_taps_survive_all_layouts_and_role_scales(self):
        machines = [SprintMachine(raw) for raw in (self.base, self.source)]
        # Context 10 is possession after the kickoff catch. Pre-catch input
        # uses a different map and is outside this ball-carrier replay.
        for layout, condition, role in itertools.product(
                range(3), (1, .8), (0, .17, 1)):
            results = []
            for m in machines:
                m.setup(speed=DIKE_SPEED, abilities=DIKE_FLAGS, layout=layout)
                m.f32(m.COND + 4, condition)
                m.f32(m.S + 0x190, role)
                m.frame(True)
                m.frame(False)
                self.assertEqual(m.frame(True), (0x16, 0x16, 0))
                multiplier, duration = m.enter_burst()
                self.assertAlmostEqual(multiplier, 1 + .04 * condition, places=6)
                self.assertEqual(duration, .25)
                results.append((multiplier, duration, m.sprint_rate()))
            self.assertEqual(*results)

    def test_dike_hold_keeps_charge_empty_but_star_control_can_charge(self):
        for payload, star, carrier in itertools.product(
                (self.base, self.source), (False, True), (False, True)):
            m = SprintMachine(payload)
            m.setup(speed=DIKE_SPEED, abilities=DIKE_FLAGS | (0x100 if star else 0),
                    carrier=carrier)
            commands = [m.frame(True)[0] for _ in range(90)]
            self.assertEqual(commands, [0x16] + [0] * 89)
            self.assertEqual(m.number(m.S + 0x44), 1 if star else 0)

    def test_speedster_lock_does_not_reduce_dikes_speed_93(self):
        for raw in (self.base, self.source):
            m = SprintMachine(raw)
            for flags in (DIKE_FLAGS, DIKE_FLAGS | 0x20, DIKE_FLAGS | 0x100,
                          DIKE_FLAGS | 0x120):
                m.setup(speed=DIKE_SPEED, abilities=flags)
                self.assertAlmostEqual(m.rating, .93, places=6)
                m.setup(speed=127, abilities=flags)
                self.assertAlmostEqual(m.rating, 1.27 if flags & 0x120 == 0x120 else 1,
                                       places=6)


if __name__ == "__main__":
    unittest.main()
