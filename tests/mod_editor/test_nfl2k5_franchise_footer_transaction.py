"""b780 j23 J2: the game's own save transaction writes the franchise footer, the load restores it, an old save clears it.

The pinned retail executable with the generic MyCareer owner, the Player Progress screen (hosted) and the franchise
footer host composed the way a build composes them. The fixture executes the retail save FUN_0016E3F0 with every
serializer to the signing boundary (FUN_0016C2F0) and the retail load FUN_0016E540 with the metadata admission and all
four deserializers; only storage/authentication completion, heap allocation and a few UI services are substituted
(tests/nfl2k5_my_career_mode_fixture.py). No emulator boot, no physical signed save.
"""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_franchise_extension as ext  # noqa: E402
from mod_editor.core import nfl2k5_franchise_footer as footer  # noqa: E402
from mod_editor.core import nfl2k5_my_career_mode as mode  # noqa: E402
from mod_editor.core import nfl2k5_my_career_save as career  # noqa: E402
from mod_editor.core import nfl2k5_player_progress_screen as progress  # noqa: E402
from mod_editor.core import nfl2k5_player_progression as record  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, draft_save  # noqa: E402


def _compose():
    retail = XBE.read_bytes()
    # the scale-out pool with MyCareer's requests; the late owners extend it (as a build appends them)
    payload = space.apply(retail, mode.REQUESTS, scaleout=True)[0]
    payload = mode.apply(payload)[0]
    payload = progress.apply(payload, hosted=True)[0]
    return footer.apply(payload, static_body=True)[0]


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn and the pinned USA retail XBE are required")
class TransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = _compose()
        assert footer.status(cls.payload) == "applied"
        assert progress.variant(cls.payload) == "hosted"
        assert mode.status(cls.payload) == "applied"
        found = footer.allocations(cls.payload)
        cls.state = found["data"]["va"]
        cls.static = cls.state + footer.STATE_SIZE
        cls.pp_footer = progress.hosted_addresses(cls.payload)[0]

    def machine(self):
        from tests.nfl2k5_my_career_mode_fixture import Machine
        m = Machine(self.payload)
        return m

    def ram_body(self, m):
        pointer = m.get(self.state + 4)
        return bytes(m.uc.mem_read(pointer, ext.BODY_SIZE)) if pointer else None

    def test_a_plain_save_gains_an_empty_footer_and_reloads_cold(self):
        source = draft_save()
        with self.machine() as m:
            m.native_load(source, requested=False)
            self.assertEqual(m.get(self.state + footer.STATE_FIELDS["load_result"]), 1)   # no body: fresh later
            output = m.native_save()
            self.assertIsNotNone(output)
            found = ext.layout(output)
            self.assertEqual((found.native_size, found.career_offset, found.body_offset, found.pp_offset),
                             (720044, None, 720044, 720044 + ext.BODY_SIZE))
            view = ext.read_body(ext.body_of(output))
            self.assertTrue(view["header_ok"])
            self.assertEqual(view["bad"], [])
            self.assertEqual(view["header"]["saves"], 1)
            self.assertTrue(view["header"]["pp_follows"])
            # write a season into the running body, save again: the save carries it, sealed
            lines = [ext.season_club_line(9, 8, 0, place=2, points_for=380, points_against=360) for _ in range(32)]
            seasons = ext.encode_seasons([ext.season_record(2026, lines, champion=1, runner_up=2)])
            pointer = m.get(self.state + 4)
            m.uc.mem_write(pointer + ext.BLOCK_BY_NAME["seasons"].offset, seasons)
            second = m.native_save()
            self.assertEqual(ext.block_of(ext.body_of(second), "seasons"), seasons)
            self.assertEqual(ext.read_body(ext.body_of(second))["header"]["saves"], 2)
        with self.machine() as cold:                     # a new CPU: the load restores it
            cold.native_load(second, requested=False)
            self.assertEqual(cold.get(self.state + footer.STATE_FIELDS["load_result"]), 2)
            self.assertEqual(ext.block_of(ext.seal(self.ram_body(cold)), "seasons"), seasons)
            again = cold.native_save()
            self.assertEqual(ext.block_of(ext.body_of(again), "seasons"), seasons)

    def test_v08_player_progress_save_keeps_its_footer_and_gains_the_body(self):
        source = draft_save()
        roster = [{"pbp_id": 10 + i, "position": 0, "jersey": i, "overall": 70,
                   "ratings": [55] * record.RATING_COUNT} for i in range(record.TEAM_SLOTS)]
        v08_progress = record.baseline(roster, year=2026, team=3)
        with self.machine() as m:
            m.native_load(source + v08_progress, requested=False)
            self.assertEqual(bytes(m.uc.mem_read(self.pp_footer, record.FOOTER_SIZE)), v08_progress)
            output = m.native_save()
            self.assertEqual(len(output), 720044 + ext.BODY_SIZE + ext.PP_SIZE)
            self.assertEqual(output[-ext.PP_SIZE:], v08_progress)
            self.assertTrue(ext.read_body(ext.body_of(output))["header_ok"])

    def test_a_career_save_keeps_its_block_between_the_native_save_and_the_footer(self):
        from tests.mod_editor.test_nfl2k5_my_career_inline import block_for
        source = draft_save()
        with_career = source + block_for(source)
        with self.machine() as m:
            m.native_load(with_career)
            self.assertEqual(m.get(m.state + 2580), 2)                     # MyCareer staged and decoded its block
            output = m.native_save()
            found = ext.layout(output)
            self.assertEqual((found.career_offset, found.body_offset), (720044, 720172))
            self.assertEqual(career.read(output)[16:32], with_career[-112:-96])
        with self.machine() as cold:
            cold.native_load(output)                                       # MyCareer's stage strips the footers
            self.assertEqual(cold.get(cold.state + 2580), 2)
            self.assertEqual(cold.get(self.state + footer.STATE_FIELDS["load_result"]), 2)

    def test_damaged_body_blocks_and_a_foreign_size(self):
        source = draft_save()
        with self.machine() as m:
            m.native_load(source, requested=False)
            output = bytearray(m.native_save())
        found = ext.layout(bytes(output))
        totals = found.body_offset + ext.BLOCK_BY_NAME["totals"].offset
        output[totals + 3] ^= 0x55                                         # one block damaged: rebuilt, others kept
        with self.machine() as m:
            m.native_load(bytes(output), requested=False)
            self.assertEqual(m.get(self.state + footer.STATE_FIELDS["load_result"]), 4)
            view = ext.read_body(self.ram_body(m))
            self.assertEqual(view["info"]["repaired_mask"], 1 << 1)
        with self.machine() as m:                                          # a size of no franchise family: refused
            m.native_load(bytes(output) + b"\0" * 16, requested=False)
            self.assertIn("native_bad_size", m.events)


if __name__ == "__main__":
    unittest.main()
