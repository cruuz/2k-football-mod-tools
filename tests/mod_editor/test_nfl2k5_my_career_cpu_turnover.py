"""Native snap/event/turnover boundaries with declared animation inputs.

This does not prove automatic snap animation or the CPU's fourth-down choice.
No play, possession, clock, turnover, stat or lineup callee is substituted.
"""
from pathlib import Path
import hashlib
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC
from tests.nfl2k5_my_career_cpu_fixture import retail_playbook
from tests.nfl2k5_my_career_cpu_boundary import Machine
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "pinned USA XBE, ROST, PLAY and Unicorn required")
class TurnoverTests(unittest.TestCase):
    def test_snap_live_clock_turnover_on_downs_log_and_next_cpu_choice(self):
        self.turnover(benched=True)

    def test_starting_qb_returns_to_human_calling_after_native_turnover(self):
        self.turnover(benched=False)

    def test_punt_return_event_and_next_drive_restore_starting_qb_calling(self):
        self.turnover(benched=False, punt_return=True)

    def turnover(self, *, benched, punt_return=False):
        if XBE.stat().st_size > 16 * 1024**2:
            self.skipTest("retail XBE exceeds 16 MiB")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE pin differs")
        roster, resource = retail_roster(), retail_playbook()
        with Machine(mode.apply(retail)[0]) as m:
            m.create(roster, preseason=False)
            m.child_services()
            m.cpu_scene(resource, benched=benched)
            # The newly human play-call route resets two absent HUD scenes.
            # Only their null scene-clock setters are a presentation seam;
            # menu eligibility, possession, lineup and play choice stay live.
            m.replace_stub(0x2F010, lambda: m.ret(pop=4) if not m.reg('ECX') else None)
            original_offense, original_defense = m.offense, m.defense
            m.put(0xE602C4, 1)
            timer, play = m.get(0xE6028C), m.get(0xE602EC)
            m.f32(timer + 16, 300)
            m.put(play + 4, 1)
            m.put(0xE60288, m.offense)
            m.f32(play + 0x28, 914.4)
            m.call(0xCD560, ecx=m.defense, budget=2000000)
            if punt_return:
                # Backing word for the native punt camera-mode setter, not
                # a substitute for its decision or for an actor/role script.
                m.put(m.get(0xE5FC00)+0x1C, m.BODIES+0x18200)
                m.put(0xE602B4, 1)  # native punt phase, with a fourth-down input
                m.put(play+4, 4)
            m.cpu_choice()
            lineup = {m.uc.mem_read(m.get(body + 0x3C) + 0x35, 1)[0]: body
                      for body in m.actors if m.get(body + 0x38) == m.offense}
            if punt_return:
                qb = lineup[2]  # actual native punter selection
                # Animation inputs only: a snapper from the native punt unit
                # and a completed catch by its opponent's CB. No punt flight
                # or physical long-snap animation is claimed by this fixture.
                center = next(b for b in m.actors if m.get(b+0x38)==m.offense and b!=qb)
                self.assertEqual(m.call('mode_unit_present'), 0)
            else:
                qb, center = lineup[0], lineup[12]
            for body in m.actors:
                m.call(0x186160, ecx=body, budget=2000000)
                desc = m.get(body + 16)
                # A completed ready animation using the embedded retail clip.
                m.put(desc + 4, 0x50F1E4)
                m.put(desc + 0xD4, 0x63C8C0)
                m.put(desc + 0x110, 0)
            # Declare a fourth-down play boundary after native play selection.
            # Native A8680/1B9E70 capture its replay/lineup snapshot. This is
            # not evidence that the CPU selected a go-for-it fourth-down play.
            m.put(play + 4, 4)
            m.call(0xA8680, budget=2000000)
            m.call(0x1B9E70, ecx=m.offense, budget=2000000)
            m.call(0x18C1F0, budget=2000000)
            m.call(0xE9210, args=(0x3C888889,), budget=2000000)
            self.assertEqual(m.get(0xE602B8), 13)
            calls = m.observe((0x9FE50, 0xB6F30, 0xB91A0, 0xA09B0,
                               0x1BB690, 0xB7330, 0xB9670, 0xCDEF0,
                               0x189080, 0x18AD10))
            # The native snap-animation and possession events are supplied.
            m.call(0x9FF80, edx=center, args=(qb,), budget=2000000)
            self.assertEqual(m.get(0xE602B8), 14)
            self.assertEqual(m.get(play + 0x1A0), center)
            self.assertEqual(m.get(play + 0x1A4), qb)
            m.call(0xB9B50, ecx=qb, budget=2000000)
            if punt_return:
                returner = next(b for b in m.actors if m.get(b+0x38)==m.defense and
                                m.uc.mem_read(m.get(b+0x3C)+0x35,1)[0]==4)
                m.call(0xB9B50, ecx=returner, budget=2000000)
            for _ in range(30):
                m.control_frame()
                self.assertEqual(m.get(0xE602B8), 14)
                self.assertEqual(m.call("mode_unit_present"), 0)
            self.assertAlmostEqual(m.f32(timer + 16), 299.5, places=3)
            # A dead-ball event at the supplied spot goes through the complete
            # native post-play rules and event/stat writer, with no score edits.
            m.call(0xA0390, budget=2000000)
            self.assertEqual(m.get(0xE602B8), 18)
            self.assertEqual(m.get(play + 4), 1)
            self.assertEqual(m.get(0xE60280), original_defense)
            self.assertEqual(m.get(0xE60284), original_offense)
            self.assertEqual(m.get(0xE53804), 1)
            self.assertTrue(any(m.uc.mem_read(0xE53874, 20)))
            for va in (0x9FE50, 0xB6F30, 0xB91A0, 0xA09B0, 0x1BB690,
                       0xB7330, 0xB9670, 0xCDEF0, 0x189080):
                self.assertIn(va, calls)
            result = m.next_choice()
            self.assertEqual(result["phase"], 12 if benched else 11)
            if benched:
                self.assertTrue(all(flags & 8 for flags in result["chosen_flags"]))
                self.assertEqual((result["unit_present"], result["offense_human"],
                                  result["defense_human"]), (0, 0, 0))
            else:
                self.assertNotEqual(result["unit_present"], 0)
                self.assertEqual((result["offense_human"], result["defense_human"]), (1, 0))
                self.assertEqual(result["chosen_flags"][0] & 8, 0)
                self.assertEqual(m.call(0x189D10, ecx=m.offense, budget=1000000), 0)
            self.assertEqual(calls.count(0x18AD10), 4)
            self.assertEqual(m.get(m.state + 2564), m.match_player)
            if benched:
                self.assertEqual(m.get(m.state + 2572), 0)
            else:
                self.assertEqual(m.get(m.state + 2572), m.call('fixture_key'))
            self.assertEqual(m.get(m.state + 64), 0)


if __name__ == "__main__":
    unittest.main()
