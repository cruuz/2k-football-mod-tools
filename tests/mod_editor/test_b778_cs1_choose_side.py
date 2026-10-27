"""PB20: a mid-game Choose Side controller change must not arm a fresh
automatic VIP context whose native playcall cursor (VIP +0xE2C) is still null.

Native 17D330/17D5F0/17D670 dereference that cursor as soon as +0x38 says
playback; on the released disc the Choose Side VIP prompt leads to a kernel
bugcheck 0x1E (null read at 0xc, and at 0x38 through F7660). The guard keeps
the newly human-to-CPU side on the ordinary native caller for that game.
"""
from pathlib import Path
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_coach_ai as ai
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES


class AutomaticRebind(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get("NFL2K5_COACH_AI_XBE")
        image = os.environ.get("NFL2K5_COACH_AI_IMAGE")
        if not source or not image:
            raise unittest.SkipTest("Set NFL2K5_COACH_AI_XBE and NFL2K5_COACH_AI_IMAGE for native execution")
        with OuterImage(image) as archive:
            raw = archive.read_entry(BOOK_ENTRIES["SEA"])
            roster = rr.RosterDocument(archive.read_entry(5)[32:])
        cls.xbe = ai.apply(Path(source).read_bytes())[0]
        cls.book, cls.receipt = ai.build_profile(
            raw, json.loads((ROOT / "data/vip/coaches/SEA.json").read_text(encoding="utf-8")))
        at = roster.teams[cls.receipt["book_index"]].coach_offset
        cls.coach = roster.body[at:at + 0xA8]

    def world(self):
        from tools.b77.vp2_native import bind_automatic
        w, context = bind_automatic(self.xbe, self.book, self.receipt, self.coach, 4)
        w.put(0xE60280, 0xE5FC60)
        w.put(0xE60284, 0xE5FC20)
        w.configure()
        self.assertNotEqual(context, 0)
        self.assertNotEqual(w.get(context + 0xE2C), 0,
                            "the game-start fixture must carry a native playcall cursor")
        return w, context

    def test_mid_game_controller_change_does_not_arm_a_fresh_context(self):
        w, _ = self.world()
        w.put(0xE53800, 1)                 # the first play has started
        w.put(0xE602B8, 0xE)               # pre-snap VIP phase
        w.change_controllers((False, True))  # side 0 (human) becomes the CPU side
        # The exact native consumer from the bugcheck must not fault.
        w.put(0xE602B8, 0xE)
        try:
            w.call(0x17D5F0, ecx=0xE5FC20, args=(0,))
        except Exception as exc:
            self.fail(f"native VIP selector dereferenced a null playcall cursor: {exc}")
        self.assertEqual(w.get(0xBA04B0), 0,
                         "a fresh VIP context was armed without its native playcall cursor")
        self.assertEqual(w.get(0xE5FC20 + 0x38), 0)

    def test_idle_controller_change_still_arms_the_automatic_profile(self):
        w, _ = self.world()
        w.put(0xE53800, 0)
        w.put(0xE602B8, 0)
        w.change_controllers((False, True))
        context = w.get(0xBA04B0)
        self.assertNotEqual(context, 0, "an idle rebind must keep the automatic profile")
        self.assertEqual(w.get(context + 0x38), 2)

    def test_playing_cpu_context_is_rebound_across_the_other_side_change(self):
        w, context = self.world()
        w.put(0xE53800, 1)
        w.put(0xE602B8, 0xE)
        w.change_controllers((True, False))  # side 0 becomes human; side 1 stays CPU
        self.assertEqual(w.get(0xBA04B0), 0)
        self.assertEqual(w.get(0xBA04B4), context,
                         "a CPU context that already has a playcall cursor must rebind")
        self.assertEqual(w.get(context + 0xE2C) != 0, True)


if __name__ == "__main__":
    unittest.main()
