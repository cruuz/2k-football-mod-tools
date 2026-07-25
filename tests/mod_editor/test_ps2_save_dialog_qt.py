"""Model and service tests for the PS2 save editor dialog.

The dialog keeps its view model above the PyQt5 import so the gating and
capacity rules can be proved without a display.  The service tests run the
whole edit-and-verify path against a synthesized save, so no game data and no
memory card are required.
"""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.core.errors import ValidationError
from mod_editor.core.ps2_save_service import Ps2SaveService
from mod_editor.gui.ps2_save_dialog_qt import (
    PYQT5_AVAILABLE,
    PlayerNameRow,
    Ps2SaveEditorDialog,
    Ps2SaveEditorHost,
    STATUS_ALL,
    STATUS_EDITED,
    STATUS_UNCHANGED,
    filter_player_rows,
    name_capacity,
    ps2_save_action_state,
    suggested_psu_name,
)

import nfl2k5_ps2_save as save_lib


def _row(index: int = 0, first: str = "Duane", last: str = "Starks",
         original_first: str | None = None, original_last: str | None = None
         ) -> PlayerNameRow:
    return PlayerNameRow(
        index=index,
        first=first,
        last=last,
        first_capacity=5,
        last_capacity=6,
        original_first=first if original_first is None else original_first,
        original_last=last if original_last is None else original_last,
    )


class NameCapacityTests(unittest.TestCase):
    def test_a_name_that_exactly_fills_the_slot_is_accepted(self) -> None:
        capacity = name_capacity(_row(), "last", "Starks")
        self.assertTrue(capacity.valid)
        self.assertEqual((capacity.used, capacity.capacity), (6, 6))

    def test_one_character_too_many_is_refused_with_both_numbers(self) -> None:
        capacity = name_capacity(_row(), "last", "Starksx")
        self.assertFalse(capacity.valid)
        self.assertIn("7 characters", capacity.message)
        self.assertIn("holds 6", capacity.message)

    def test_an_empty_name_is_allowed(self) -> None:
        self.assertTrue(name_capacity(_row(), "first", "").valid)

    def test_an_unknown_field_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "first.*last"):
            name_capacity(_row(), "middle", "X")


class FilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = (
            _row(0, "Duane", "Starks"),
            _row(1, "Renaldo", "Hill", original_last="Hilt"),
        )

    def test_search_matches_number_and_name(self) -> None:
        self.assertEqual(filter_player_rows(self.rows, search="renaldo").match_total, 1)
        self.assertEqual(filter_player_rows(self.rows, search="0").match_total, 1)

    def test_status_filters_split_edited_from_unchanged(self) -> None:
        edited = filter_player_rows(self.rows, status=STATUS_EDITED)
        unchanged = filter_player_rows(self.rows, status=STATUS_UNCHANGED)
        self.assertEqual(edited.match_total, 1)
        self.assertEqual(unchanged.match_total, 1)
        self.assertEqual(edited.player_total, 2)
        self.assertEqual(edited.edited_total, 1)

    def test_an_unknown_status_is_refused(self) -> None:
        with self.assertRaisesRegex(ValidationError, "all, edited, or unchanged"):
            filter_player_rows(self.rows, status="whatever")

    def test_everything_is_returned_by_default(self) -> None:
        self.assertEqual(
            filter_player_rows(self.rows, status=STATUS_ALL).match_total, 2
        )


class ActionStateTests(unittest.TestCase):
    def test_nothing_is_offered_before_a_save_is_open(self) -> None:
        state = ps2_save_action_state(
            None, capacity=None, save_loaded=False, busy=False,
            edit_count=0, changed=False,
        )
        self.assertFalse(state.can_apply)
        self.assertFalse(state.can_write)
        self.assertFalse(state.can_revert_all)

    def test_apply_needs_a_changed_and_valid_name(self) -> None:
        row = _row()
        valid = name_capacity(row, "last", "Carey")
        invalid = name_capacity(row, "last", "Carey Junior")
        common = dict(save_loaded=True, busy=False, edit_count=0)
        self.assertTrue(
            ps2_save_action_state(row, capacity=valid, changed=True, **common).can_apply
        )
        self.assertFalse(
            ps2_save_action_state(row, capacity=valid, changed=False, **common).can_apply
        )
        self.assertFalse(
            ps2_save_action_state(row, capacity=invalid, changed=True, **common).can_apply
        )

    def test_writing_needs_at_least_one_staged_edit(self) -> None:
        common = dict(save_loaded=True, busy=False, changed=False, capacity=None)
        self.assertFalse(ps2_save_action_state(None, edit_count=0, **common).can_write)
        self.assertTrue(ps2_save_action_state(None, edit_count=1, **common).can_write)

    def test_a_busy_dialog_offers_nothing(self) -> None:
        row = _row()
        state = ps2_save_action_state(
            row, capacity=name_capacity(row, "last", "Carey"),
            save_loaded=True, busy=True, edit_count=1, changed=True,
        )
        self.assertFalse(state.can_apply)
        self.assertFalse(state.can_write)


class SuggestedNameTests(unittest.TestCase):
    def test_the_suggestion_is_derived_from_the_save_directory(self) -> None:
        self.assertEqual(
            suggested_psu_name("BASLUS-209192K5Roster"),
            "BASLUS-209192K5Roster-edited.psu",
        )

    def test_a_blank_directory_still_yields_a_usable_name(self) -> None:
        self.assertTrue(suggested_psu_name("").endswith(".psu"))


class ServiceTests(unittest.TestCase):
    """Drive the real service the dialog binds to, on a synthesized save."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory(prefix="ps2-save-service-")
        self.root = Path(self._temp.name)
        source = save_lib._synthetic_save()
        self.source_path = self.root / "source.psu"
        save_lib.write_psu(source, self.source_path)
        self.service = Ps2SaveService()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def test_opening_reports_the_save_and_its_players(self) -> None:
        summary = self.service.open(self.source_path)
        self.assertTrue(summary.checksum_valid)
        self.assertEqual(summary.player_count, 2)
        self.assertIn("checksum OK", summary.headline)
        self.assertEqual([row.first for row in self.service.players()],
                         ["Alpha", "Bravo"])

    def test_capacity_is_reported_in_characters(self) -> None:
        self.service.open(self.source_path)
        row = self.service.players()[0]
        self.assertEqual(row.first_capacity, len("Alpha"))

    def test_an_oversized_name_is_refused_before_anything_is_written(self) -> None:
        self.service.open(self.source_path)
        self.assertIsNotNone(self.service.validate_name(0, "first", "Wayovertheline"))
        with self.assertRaises(ValidationError):
            self.service.set_name(0, "first", "Wayovertheline")
        self.assertFalse(self.service.dirty)

    def test_writing_reseals_and_independently_verifies(self) -> None:
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Delta")
        self.assertTrue(self.service.dirty)
        output = self.root / "edited.psu"
        result = self.service.write(output)
        self.assertTrue(result.verified, result.detail)
        self.assertEqual(result.edits, 1)
        self.assertTrue(output.is_file())
        # The written save re-opens cleanly with the edit in place.
        reopened = Ps2SaveService()
        reopened.open(output)
        self.assertEqual(reopened.players()[0].first, "Delta")
        self.assertTrue(reopened.summary().checksum_valid)

    def test_writing_without_changes_is_refused(self) -> None:
        self.service.open(self.source_path)
        with self.assertRaises(ValidationError):
            self.service.write(self.root / "unchanged.psu")

    def test_revert_restores_the_file_on_disk(self) -> None:
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Delta")
        self.service.revert()
        self.assertFalse(self.service.dirty)
        self.assertEqual(self.service.players()[0].first, "Alpha")

    def test_the_source_file_is_never_modified(self) -> None:
        before = self.source_path.read_bytes()
        self.service.open(self.source_path)
        self.service.set_name(0, "first", "Delta")
        self.service.write(self.root / "elsewhere.psu")
        self.assertEqual(self.source_path.read_bytes(), before)

    def test_the_service_satisfies_the_dialog_host_protocol(self) -> None:
        self.assertIsInstance(self.service, Ps2SaveEditorHost)


class DialogContractTests(unittest.TestCase):
    def test_the_dialog_is_a_qt_dialog_without_starting_an_application(self) -> None:
        from PyQt5.QtWidgets import QDialog

        self.assertTrue(PYQT5_AVAILABLE)
        self.assertTrue(issubclass(Ps2SaveEditorDialog, QDialog))


if __name__ == "__main__":
    unittest.main()
