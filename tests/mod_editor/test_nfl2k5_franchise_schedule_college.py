"""beta-63.1 hotfix: a franchise schedule edit is not refused over a player record the roster codec cannot read.

The report (BigTimeEmpire, #2k5-bugs 2026-09-08 19:16): Franchise -> Schedule, postseason, "Apply to this game"
on a kickoff-time change answered twice with

    Refused: no supported ROST: unsupported ROST version 593952; player college is not a college record

Three defects sit behind that line, and each has a test here:

1. ``nfl2k5_save_rost.decode`` treated the 0x20-byte outer wrapper's own ``ROST`` magic as an inner header
   candidate, so the wrapper's declared length (0x91020 = 593,952 on every 720,044-byte save) was reported as
   an "unsupported ROST version".  593,952 is not a version; the pinned layout was intact.
2. The strict codec refused the whole ROST when one player's college pointer did not land on one of the
   college records, although it stayed inside the arena.  The game never checks that pointer (it dereferences
   it for the COLLEGE line and maps an unknown target to college 0 on team export, ``FUN_00242190``), the
   studio's own roster parser already reads such a player as "no college", and the codec copies the bytes
   verbatim.  It is now recorded (``SaveRost.unresolved_colleges``), not refused, and every refusal the codec
   still raises names the player record it could not read.
3. Every franchise edit, including a schedule cell that lives in the season block, was gated on the roster
   ownership validation (``validate_save``).  A schedule / year / cap / control edit leaves the roster arena
   and the injured-reserve table untouched, so ``validate_save_edit`` skips the codec for it; arena edits are
   validated exactly as before.

Synthetic saves only (the core tests' generator); the real fixtures, when present, prove the wrapper word.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_franchise_save as fs  # noqa: E402
from mod_editor.core import nfl2k5_practice_squad as ps  # noqa: E402
from mod_editor.core import nfl2k5_save_rost as codec  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from test_nfl2k5_franchise_save import F0, F1, FRANCHISE1, synthetic_franchise  # noqa: E402
from test_roster_editor_panel_franchise import write_container  # noqa: E402

REPORTED = "player college is not a college record"
WRAPPER_LENGTH = 0x91020          # the word at 0x2E4 of every 720,044-byte franchise save: 593,952


def _rel(buffer: bytearray, field: int, target: int) -> None:
    struct.pack_into("<i", buffer, field, target - field + 1)


def franchise_with_unresolved_college(player: int = 0) -> tuple[bytes, int]:
    """The synthetic franchise save with one player's college pointer inside the arena but off the table."""

    payload = bytearray(synthetic_franchise())
    document = codec.decode(bytes(payload))
    colleges = document.tables["colleges"]
    assert colleges.offset is not None
    target = colleges.offset + colleges.count * colleges.stride + 4       # 4 bytes past the last record
    _rel(payload, document.players[player].offset, target)
    return bytes(payload), target


def franchise_with_broken_history(player: int = 0) -> bytes:
    """A save the codec still refuses: one player's history stream pointer points at its own field."""

    payload = bytearray(synthetic_franchise())
    document = codec.decode(bytes(payload))
    struct.pack_into("<i", payload, document.players[player].offset + 0x2C, 1)
    return bytes(payload)


class CodecTests(unittest.TestCase):
    def test_an_off_table_college_pointer_is_recorded_not_refused(self) -> None:
        payload, target = franchise_with_unresolved_college()
        document = codec.decode(payload)
        self.assertEqual(document.unresolved_colleges, {("primary", 0): target})
        self.assertEqual(document.to_bytes(), payload)                      # the bytes travel verbatim
        self.assertEqual(document.summary()["unresolved_colleges"], 1)
        self.assertEqual(codec.decode(synthetic_franchise()).unresolved_colleges, {})
        # the ownership validation the franchise page runs is what the tester's edit hit
        ps.validate_save(payload)

    def test_a_college_pointer_outside_the_arena_loads_with_a_repair_warning(self) -> None:
        payload = bytearray(synthetic_franchise())
        document = codec.decode(bytes(payload))
        _rel(payload, document.players[1].offset, document.layout.end + 0x100)
        loaded = codec.decode(bytes(payload))
        self.assertEqual(loaded.to_bytes(), bytes(payload))
        self.assertIn(("primary", 1), loaded.unresolved_colleges)
        self.assertIn("1 players have a missing/invalid college", loaded.college_warning)

    def test_the_wrapper_length_is_not_reported_as_a_version(self) -> None:
        payload = bytearray(synthetic_franchise())
        self.assertEqual(struct.unpack_from("<I", payload, fs.ARENA_WRAPPER + 4)[0], WRAPPER_LENGTH)
        struct.pack_into("<I", payload, fs.ARENA_ROOT + 0x18, 0)             # no teams: the real header fails
        with self.assertRaises(codec.SaveRostError) as caught:
            codec.decode(bytes(payload))
        message = str(caught.exception)
        self.assertNotIn(str(WRAPPER_LENGTH), message)
        self.assertNotIn("unsupported ROST version", message)
        self.assertIn("primary players and teams are required", message)
        # a real version mismatch still says so
        wrong = bytearray(synthetic_franchise())
        struct.pack_into("<I", wrong, fs.ARENA_PREAMBLE + 0x10, 5)
        with self.assertRaisesRegex(codec.SaveRostError, "unsupported ROST version 5"):
            codec.decode(bytes(wrong))

    def test_a_refusal_names_the_player_it_could_not_read(self) -> None:
        with self.assertRaises(codec.SaveRostError) as caught:
            codec.decode(franchise_with_broken_history(player=1))
        message = str(caught.exception)
        self.assertIn("primary player 1", message)
        self.assertIn("history stream", message)

    def test_validate_save_edit_consults_the_codec_only_for_roster_state(self) -> None:
        before = franchise_with_broken_history()
        save = fs.FranchiseSave(before)
        save.set_game(0, 1, hour=8, minute=30)
        after = save.to_bytes()
        self.assertNotEqual(after, before)
        self.assertIsNone(ps.validate_save_edit(before, after))             # season block only: skipped
        with self.assertRaises(codec.SaveRostError):
            ps.validate_save_edit(before, before[:0x1000] + bytes([before[0x1000] ^ 1]) + before[0x1001:])
        with self.assertRaises(codec.SaveRostError):
            ps.validate_save(after)
        clean = synthetic_franchise()
        self.assertIsInstance(ps.validate_save_edit(clean, clean[:0x1000] + bytes([clean[0x1000] ^ 1]) + clean[0x1001:]), dict)
        # the injured-reserve table is roster state too
        ir_at = fs.FRONT_OFFICE_BLOCK + fs.F_INJURED_RESERVE
        with self.assertRaises(codec.SaveRostError):
            ps.validate_save_edit(before, before[:ir_at] + struct.pack("<H", 0) + before[ir_at + 2:])

    def test_real_saves_carry_the_wrapper_word_and_no_unresolved_college(self) -> None:
        present = [path for path in (F0, F1, FRANCHISE1) if path.is_file()]
        if not present:
            self.skipTest(f"private franchise fixtures missing under {F0.parents[3]}; set NFL2K5_SAVE_FIXTURES")
        for path in present:
            with self.subTest(fixture=path.parents[3].name):
                data = path.read_bytes()
                self.assertEqual(struct.unpack_from("<I", data, fs.ARENA_WRAPPER + 4)[0], WRAPPER_LENGTH)
                document = codec.decode(data)
                self.assertEqual(document.unresolved_colleges, {})
                self.assertEqual(document.to_bytes(), data)


class _PanelCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    def load(self, payload: bytes) -> None:
        self.assertTrue(self.panel.load_save(write_container(self.root / "fr", payload)))
        self.application.processEvents()
        self.assertTrue(self.panel.franchise_panel.active)


class SchedulePanelTests(_PanelCase):
    def test_apply_to_this_game_works_on_a_save_with_an_unresolved_college(self) -> None:
        """The report: a kickoff-time change on a save whose college pointer the codec could not resolve."""

        payload, target = franchise_with_unresolved_college()
        self.load(payload)
        page = self.panel.franchise_panel
        game = page.save.game(0, 1)
        self.assertEqual((game.hour, game.minute), (4, 15))
        self.assertTrue(page.edit_game(0, 1, hour=8, minute=30), page.status_label.text())
        for status in (page.status_label.text(), self.panel.status_label.text()):
            self.assertNotIn("Refused", status)
            self.assertNotIn(REPORTED, status)
        # Beta 66: the Franchise status keeps the college warning on a second line until it is repaired.
        self.assertTrue(page.status_label.text().startswith("Week 1 game 2: hour 4 → 8, minute 15 → 30"), page.status_label.text())
        self.assertIn("missing/invalid college; use Check my rosters to repair", page.status_label.text())
        self.assertEqual((page.save.game(0, 1).hour, page.save.game(0, 1).minute), (8, 30))
        self.assertTrue(page.swap_home_away(0, 1), page.status_label.text())
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        written = next((self.root / "copy").rglob("SAVEGAME.DAT")).read_bytes()
        changed = [i for i, (a, b) in enumerate(zip(payload, written)) if a != b]
        cell = fs.FranchiseSave(payload).game(0, 1).offset
        self.assertTrue(changed and all(cell <= i < cell + 8 for i in changed), changed[:8])
        self.assertEqual(written[fs.ARENA_WRAPPER:fs.ARENA_END], payload[fs.ARENA_WRAPPER:fs.ARENA_END])
        # the unresolved pointer left the studio exactly as it came in
        document = codec.decode(written)
        self.assertEqual(document.unresolved_colleges, {("primary", 0): target})

    def test_a_schedule_edit_does_not_depend_on_the_roster_codec_but_an_ir_move_still_does(self) -> None:
        self.load(franchise_with_broken_history())
        page = self.panel.franchise_panel
        self.assertTrue(page.edit_game(0, 1, hour=1), page.status_label.text())
        self.assertEqual(page.save.game(0, 1).hour, 1)
        self.assertTrue(page.set_salary_cap(90_000), page.status_label.text())
        self.assertTrue(page.set_user_control(1, True), page.status_label.text())
        team = self.panel.document.club_of(self.panel.document.players[0])
        self.assertIsNotNone(team)
        self.assertFalse(page.place_on_ir(team, 0))
        for status in (page.status_label.text(), self.panel.status_label.text()):
            self.assertIn("Refused", status)
            self.assertIn("primary player 0", status)
            self.assertIn("history stream", status)
            self.assertNotIn("unsupported ROST version", status)
        self.assertEqual(page.edit_labels(), ["Week 1 game 2: hour 4 → 1",
                                              "Salary cap $80.5M (80,500) → $90.0M (90,000)",
                                              "ATL: CPU → user-controlled"])
        # the copy is written too: roster state is exactly what the game wrote, so the codec is not asked
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        written = next((self.root / "copy").rglob("SAVEGAME.DAT")).read_bytes()
        source = franchise_with_broken_history()
        self.assertEqual(written[fs.ARENA_WRAPPER:fs.ARENA_END], source[fs.ARENA_WRAPPER:fs.ARENA_END])
        self.assertEqual(fs.FranchiseSave(written).game(0, 1).hour, 1)
        self.assertEqual(fs.FranchiseSave(written).salary_cap, 90_000)
        self.assertIn(1, fs.FranchiseSave(written).user_teams())


if __name__ == "__main__":
    unittest.main()
