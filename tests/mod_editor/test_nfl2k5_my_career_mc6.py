"""mc6 (b778): MyCareer with a custom MyPlayer name, drafted path.

Reports (v0.6.1, 10/21): MyCareer works with the default name "First Last"; with any other name the drafted path
stops on the draft screen with only Save and Quit, and the saved file does not load. The undrafted path works.

Cause: Create Player's Last Name handler (0x346540) gives a surname no real player has the play-by-play cue
9000 + jersey (record +4). "First Last" keeps the default cue 0. MyCareer took +4 as part of MyPlayer's identity
when it placed him in the draft class, and the native jersey assigner 0x2BD260 rewrites every cue 9000..9099
when it gives him a number at his draft pick. The identity check failed (lost career, S24 = 6), the draft tick
stopped, and the save kept the lost state and a stale cue. The undrafted path takes its identity after signing.

These tests run the game's own name handlers, draft, save and load (Unicorn, pinned retail XBE and ROST, the
signed f0 franchise at the Combine as in test_nfl2k5_my_career_draft). EXPERIMENTAL / UNWITNESSED in game here.
"""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as ai  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC  # noqa: E402

CUSTOM = ("Swear", "Xqzvbn")          # a surname no player in the retail roster has


def cue(m, p):
    return struct.unpack('<H', m.uc.mem_read(p + 4, 2))[0]


def jersey(m, p):
    return (m.get(p + 0x20) >> 3) & 0x7F


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, ROST, signed f0 and Unicorn required')
class CustomNameDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, signed_save
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        signed_save()  # precise private-evidence skip comes from the fixture
        cls.payload = mode.apply(ai.apply(retail_bytes())[0])[0]
        cls.roster = retail_roster()

    def machine(self):
        from tests.nfl2k5_my_career_draft_fixture import Machine
        return Machine(self.payload)

    def until_drafted(self, m, frames=40):
        """Continue to the draft and run native draft frames until MyPlayer's own pick is signed."""
        m.select(0, budget=200000000)
        for _ in range(frames):
            if m.native_signings:
                return
            m.frame(budget=6000000000)
        self.fail('MyPlayer was not picked')

    def reload(self, saved):
        from tests.nfl2k5_my_career_draft_fixture import Machine
        cold = Machine(self.payload)
        cold.cold(self.roster, saved)
        return cold

    def test_native_last_name_rule_gives_the_jersey_cue(self):
        with self.machine() as m:
            p = m.prepare_draft(self.roster, complete=False)
            self.assertEqual(cue(m, p), 0)                     # CAP default "First Last"
            m.type_name("First", "Last")
            self.assertEqual(cue(m, p), 9000 + jersey(m, p))   # "Last" is no real surname either
            m.type_name(None, "Smith")                         # a real surname takes that player's recorded cue
            self.assertLess(cue(m, p), 9000)
            m.type_name(*CUSTOM)
            self.assertEqual(cue(m, p), 9000 + jersey(m, p))

    def test_custom_name_is_drafted_and_the_apartment_save_loads(self):
        with self.machine() as m:
            p = m.prepare_draft(self.roster, name=CUSTOM)
            self.assertEqual(cue(m, p), 9000)
            captured = m.get(m.state + 100)
            club = m.draft()
            self.assertEqual(m.call('primary'), p)
            self.assertEqual(m.get(m.state + 24), 3)
            self.assertLess(club, 32)
            self.assertEqual(m.top(), m.labels['apartment'])
            self.assertTrue(any(e[0] == 'notice' and e[1].startswith('You were drafted by') for e in m.events
                                if isinstance(e, tuple)))
            # Negative control for the old check: the native jersey assigner moved the cue, so the whole +4
            # word no longer equals the captured one; only the portrait half does.
            self.assertEqual(cue(m, p), 9000 + jersey(m, p))
            self.assertNotEqual(m.get(p + 4), captured)
            self.assertEqual(m.get(p + 4) >> 16, captured >> 16)
            saved = m.native_save(budget=500000000)
            self.assertEqual(saved[-128 + 36], 3)
        with self.reload(saved) as cold:
            self.assertNotIn(('notice', 'Career load failed.'), cold.events)
            self.assertEqual(cold.top(), m.labels['apartment'])
            self.assertEqual(cold.call('primary'), p)
            self.assertEqual(cold.get(cold.state + 56), club)

    def test_a_career_saved_lost_mid_draft_loads_and_finishes_the_draft(self):
        """The players' existing files: saved on the draft screen after the old check marked the career lost (6),
        with the cue captured before the pick."""
        with self.machine() as m:
            p = m.prepare_draft(self.roster, name=CUSTOM)
            stale = m.get(m.state + 100)
            self.until_drafted(m)
            self.assertNotEqual(m.get(p + 4), stale)
            m.put(m.state + 24, 6)                            # what the old identity check stored
            m.put(m.state + 2576, 1)
            saved = m.native_save(budget=500000000)
            self.assertEqual(saved[-128 + 36], 6)
            self.assertEqual(struct.unpack_from('<I', saved, len(saved) - 128 + 56)[0], stale)
        with self.reload(saved) as cold:
            self.assertNotIn(('notice', 'Career load failed.'), cold.events)
            self.assertEqual(cold.call('primary'), p)
            self.assertEqual(cold.get(cold.state + 24), 3)
            self.assertEqual(cold.top(), m.labels['m3_draft_menu'])
            for _ in range(260):
                if cold.get(0xE576A4) != 5:
                    break
                cold.frame(budget=6000000000)
            self.assertEqual(cold.top(), m.labels['apartment'])
            self.assertEqual(cold.call('primary'), p)

    def test_a_real_identity_loss_still_does_not_load(self):
        with self.machine() as m:
            p = m.prepare_draft(self.roster, name=CUSTOM)
            self.until_drafted(m)
            m.uc.mem_write(p + 6, struct.pack('<H', (struct.unpack('<H', m.uc.mem_read(p + 6, 2))[0] + 1) & 0xFFFF))
            self.assertEqual(m.call('primary'), 0)              # a different portrait is a different player
            self.assertEqual(m.get(m.state + 24), 6)
            saved = m.native_save(budget=500000000)
        with self.reload(saved) as cold:
            self.assertEqual(cold.call('primary'), 0)
            self.assertEqual(cold.get(cold.state + 2576), 7)


if __name__ == '__main__':
    unittest.main()
