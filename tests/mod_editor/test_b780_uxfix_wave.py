"""b780 fix wave, UX-FIX items: Q19 (MyCareer page and grown saves), Q35 (coach Super Bowls), Q58 (BOM), Q59 (dotted names).

Q56 (Cancel on the Build tab) is pinned in test_b791_h3_build_failure_qt.py next to the failure dialog it replaced.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_my_career as career  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.core import nfl2k5_staff_ui as staff_ui  # noqa: E402

#: HUNT4's evidence: the v0.9 game's own draft-stage franchise save (987,836 bytes, capacity arena and footers).
GROWN_DRAFT_SAVE = Path(os.environ.get(
    "NFL2K5_B780_GROWN_DRAFT_SAVE", "/home/noah/2k-worktrees/.b77-scratch/b780/hunt4/evidence/rc_franchise_y01_draft.dat"))
TOKEN = "12345678-1234-5678-1234-567812345678"


class Q58ByteOrderMarkTests(unittest.TestCase):
    """Windows Notepad saves UTF-8 with a byte-order mark; both files failed with "Unexpected UTF-8 BOM"."""

    def test_a_roster_edits_file_saved_by_notepad_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "roster-edits.json"
            document = {"schema": rr.EDITS_SCHEMA, "edits": []}
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps(document).encode("utf-8"))
            self.assertEqual(rr.read_edits(path)["schema"], rr.EDITS_SCHEMA)
            path.write_text(json.dumps(document), encoding="utf-8")        # without the mark, exactly as before
            self.assertEqual(rr.read_edits(path)["edits"], [])

    def test_a_staff_file_saved_by_notepad_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "staff.json"
            staff = {"schema": staff_ui.SCHEMA, "head_coaches": {}}
            path.write_bytes(b"\xef\xbb\xbf" + json.dumps(staff).encode("utf-8"))
            self.assertEqual(staff_ui.read_file(path), staff)


class Q59UpgradedFolderNameTests(unittest.TestCase):
    def test_a_dotted_save_folder_keeps_its_whole_name(self):
        from mod_editor.gui.franchise_upgrade_dialog_qt import upgraded_folder_name
        with tempfile.TemporaryDirectory() as folder:
            dotted = Path(folder) / "Franchise 2.0"
            dotted.mkdir()
            self.assertEqual(upgraded_folder_name(dotted), "Franchise 2.0-upgraded")     # Path.stem gave "Franchise 2"
            plain = Path(folder) / "source"
            plain.mkdir()
            self.assertEqual(upgraded_folder_name(plain), "source-upgraded")
            archive = Path(folder) / "My.Save.zip"
            archive.write_bytes(b"PK")
            self.assertEqual(upgraded_folder_name(archive), "My.Save-upgraded")      # only .zip itself is dropped


class Q35CoachSuperBowlsTests(unittest.TestCase):
    def test_the_field_says_it_is_the_roster_count(self):
        from mod_editor.gui import franchise_panel_qt as panel
        captions = dict(panel.COACH_STATS)
        self.assertEqual(captions["super_bowls"], "Super Bowls (roster)")
        tip = panel.COACH_STAT_TIPS["super_bowls"]
        for needle in ("roster", "Super Bowl wins", "Super Bowl losses", "winning season"):
            self.assertIn(needle, tip)
        self.assertNotIn("—", tip)


class ProgressTextTests(unittest.TestCase):
    def test_a_disc_read_counts_in_gb_and_a_count_stays_a_count(self):
        # power-user review U2: "Checking your XISO • 591396864 of 6300499968"
        import time
        from mod_editor.core.nfl2k5_project_fit import progress_text
        text = progress_text("Checking your game file", 591396864, 6300499968, time.monotonic() - 3)
        self.assertIn("0.6 of 5.9 GB", text)
        self.assertNotIn("6300499968", text)
        self.assertIn("9999 of 10000", progress_text("Copying", 9999, 10000, time.monotonic() - 3))


class Q19GrownSaveTests(unittest.TestCase):
    """The Studio MyCareer page refused every SOFTDRINK franchise save (retail size and season block offset)."""

    def test_a_native_save_keeps_the_retail_layout(self):
        payload = bytes(career.SAVE_SIZE)
        self.assertEqual(career.season_block(payload), fs.SEASON_BLOCK)
        self.assertEqual(career.arena_limit(payload), 0x91000)
        from mod_editor.core import nfl2k5_roster_arena as arena
        self.assertEqual(career.arena_limit(), arena.CAPACITY_ARENA_SIZE)  # a state alone: the largest arena

    def test_a_short_or_broken_save_is_still_refused(self):
        with self.assertRaisesRegex(career.MyCareerError, "complete Franchise save"):
            career.save_key(bytes(1000))
        broken = bytearray(career.SAVE_SIZE + 0x1000)
        broken[0x2E0:0x2E4] = b"ROST"
        with self.assertRaisesRegex(career.MyCareerError, "complete Franchise save"):
            career.save_key(bytes(broken))

    def test_name_offsets_follow_the_real_arena(self):
        from tests.nfl2k5_my_career_fixture import prepared
        result, setup, _receipt = prepared()
        state = bytearray(career.read_setup(setup))
        for value, payload in ((0x91000, result), (0xCA000, None)):
            bad = bytearray(state)
            for identity, recipe in ((84, 96), (88, 112), (92, 116)):
                struct.pack_into("<I", bad, identity, value)
                struct.pack_into("<I", bad, recipe, value)
            with self.assertRaisesRegex(career.MyCareerError, "escape the roster arena"):
                career.validate_state(career.seal_state(bad), payload)

    @unittest.skipUnless(GROWN_DRAFT_SAVE.is_file(), "needs a grown SOFTDRINK draft-stage franchise save")
    def test_the_v09_games_own_draft_save_prepares_myplayer(self):
        payload = GROWN_DRAFT_SAVE.read_bytes()
        self.assertNotEqual(len(payload), career.SAVE_SIZE)
        season = career.season_block(payload)
        self.assertGreater(season, fs.SEASON_BLOCK)                             # the arena grew, the block moved
        self.assertEqual(payload[season + fs.S_STAGE], 5)                       # NFL Draft stage, read where it is
        result, setup, receipt = career.prepare(payload, first="Sam", last="Rookie", position=0, template=0, token=TOKEN)
        self.assertEqual(len(result), len(payload))
        self.assertEqual(receipt["myplayer"], "Sam Rookie")
        control = season + fs.S_USER_CONTROL
        self.assertEqual(result[control:control + 136], bytes(136))           # the draft AI owns every club
        self.assertEqual(result[fs.SEASON_BLOCK + fs.S_USER_CONTROL:fs.SEASON_BLOCK + fs.S_USER_CONTROL + 136],
                         payload[fs.SEASON_BLOCK + fs.S_USER_CONTROL:fs.SEASON_BLOCK + fs.S_USER_CONTROL + 136])
        career.validate_state(career.read_setup(setup), result)
        from mod_editor.core import nfl2k5_my_career_advisory as advisory
        document = rr.RosterDocument(result, base=rr.find_block_base(result))
        fingerprint = advisory.class_fingerprint(document, "retail")
        rows = advisory.estimate(result, player_index=receipt["index"], expected_class=fingerprint)
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
