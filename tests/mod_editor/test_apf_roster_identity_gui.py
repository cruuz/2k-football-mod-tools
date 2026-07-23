from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication, QDialog, QPlainTextEdit  # noqa: E402

from mod_editor.apf_studio.gui import (  # noqa: E402
    InspectorBrowser,
    RatingSheetImportPreviewDialog,
)
from mod_editor.apf_studio.inspectors import PagedModel, _row  # noqa: E402
from mod_editor.apf_studio.player_ratings import (  # noqa: E402
    load_player_rating_schema,
)
from mod_editor.apf_studio.player_positions import (  # noqa: E402
    load_player_position_schema,
)


PLAYER_RATING_SCHEMA = load_player_rating_schema()
PLAYER_POSITION_SCHEMA = load_player_position_schema()


def _base_rating_rows() -> tuple[dict[str, object], ...]:
    values = {
        field.field_id: (
            99
            if field.field_id == "speed"
            else 100
            if field.field_id == "unknown_rating_24"
            else 50
        )
        for field in PLAYER_RATING_SCHEMA.fields
    }
    return PLAYER_RATING_SCHEMA.field_rows(values)


def _identity_metadata(
    asset_id: str,
    limit: int,
    owners: tuple[SimpleNamespace, ...],
    note: str,
    *,
    runtime_edit_scope: str | None = None,
) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "maximum_characters": limit,
        "editable": True,
        "runtime_editable": runtime_edit_scope is not None,
        "runtime_edit_scope": runtime_edit_scope,
        "known_alias_count": len(owners),
        "known_alias_owners": tuple(
            {
                "entity_kind": owner.entity_kind,
                "entity_index": owner.entity_index,
                "field": owner.field,
                "label": owner.label,
            }
            for owner in owners
        ),
        "note": note,
    }


def _identity_owner(
    entity_kind: str, entity_index: int, field: str
) -> SimpleNamespace:
    label = (
        f"{entity_kind.title()} {entity_index} · "
        f"{field.replace('_', ' ')}"
    )
    return SimpleNamespace(
        entity_kind=entity_kind,
        entity_index=entity_index,
        field=field,
        owner_id=f"{entity_kind}:{entity_index}:{field}",
        label=label,
    )


FIRST_NAME_OWNERS = (_identity_owner("player", 7, "first_name"),)
LAST_NAME_OWNERS = (
    _identity_owner("player", 7, "last_name"),
    _identity_owner("player", 8, "last_name"),
    _identity_owner("player", 9, "first_name"),
)
TEAM_NAME_OWNERS = (_identity_owner("team", 0, "display_name"),)
TEAM_ABBREVIATION_OWNERS = (
    _identity_owner("team", 0, "abbreviation"),
    _identity_owner("team", 1, "abbreviation"),
)
TEAM_SECONDARY_OWNERS = (_identity_owner("team", 0, "secondary_abbreviation"),)


class _RosterFacade:
    def __init__(self) -> None:
        definitions = (
            (
                "apf:roster-name:10",
                "JOHN",
                4,
                FIRST_NAME_OWNERS,
                "One mapped player field.",
            ),
            (
                "apf:roster-name:11",
                "SOURCE",
                6,
                LAST_NAME_OWNERS,
                "Shared by 3 mapped roster fields; all change together.",
            ),
            (
                "apf:roster-name:20",
                "SOURCE TEAM",
                12,
                TEAM_NAME_OWNERS,
                "One mapped team field.",
            ),
            (
                "apf:roster-name:21",
                "SRC",
                3,
                TEAM_ABBREVIATION_OWNERS,
                "Shared by 2 mapped team fields.",
            ),
            (
                "apf:roster-name:22",
                "ST",
                2,
                TEAM_SECONDARY_OWNERS,
                "One mapped team field.",
            ),
        )
        self.allocations = tuple(
            SimpleNamespace(
                asset_id=asset_id,
                text=value,
                maximum_utf16_units=limit,
                known_owners=owners,
                known_owner_count=len(owners),
                editable=True,
                note=note,
            )
            for asset_id, value, limit, owners, note in definitions
        )
        self.originals = {
            asset_id: value
            for asset_id, value, _limit, _owners, _note in definitions
        }
        self.identity_scopes = {
            "apf:roster-name:10": "player_name",
            "apf:roster-name:11": "player_name",
            "apf:roster-name:20": "team_display_name",
            "apf:roster-name:21": None,
            "apf:roster-name:22": None,
        }
        self.values = dict(self.originals)
        self.rating_originals = {
            str(row["id"]): int(row["value"])
            for row in _base_rating_rows()
        }
        self.rating_values = dict(self.rating_originals)
        self.position_original = 0
        self.position_value = self.position_original
        self._modified: set[str] = set()
        self.replace_calls: list[tuple[str, str]] = []
        self.revert_calls: list[str] = []
        self.rating_sheet_calls: list[tuple[object, Path]] = []
        self.rating_sheet_preview_calls: list[Path] = []
        self.rating_sheet_apply_calls: list[tuple[object, bool]] = []
        self.rating_replace_calls: list[tuple[int, str, int]] = []
        self.position_replace_calls: list[tuple[int, int]] = []
        self.rating_sheet_preview = SimpleNamespace(
            row_count=2_254,
            cell_count=63_112,
            changed_count=2,
            replacement_count=1,
            revert_count=1,
            unchanged_count=63_110,
            conflict_count=0,
            source_conflict_count=0,
            project_conflict_count=0,
            error_count=0,
            conflicts=(),
            errors=(),
            private_data=True,
        )

    @property
    def modified_asset_ids(self) -> frozenset[str]:
        return frozenset(self._modified)

    def roster_identity_allocations(self) -> tuple[object, ...]:
        return self.allocations

    def roster_identity_value(self, asset_id: str) -> str:
        return self.values[asset_id]

    def roster_identity_edit_scope(self, asset_id: str) -> str | None:
        return self.identity_scopes[asset_id]

    def roster_identity_is_product_editable(self, asset_id: str) -> bool:
        return self.roster_identity_edit_scope(asset_id) is not None

    def replace_roster_identity_text(
        self, asset_id: str, replacement: str, _progress: object
    ) -> object:
        self.replace_calls.append((asset_id, replacement))
        self.values[asset_id] = replacement
        self._modified.add(asset_id)
        return SimpleNamespace(asset_id=asset_id)

    def player_base_rating_value(self, player_index: int, field_id: str) -> int:
        if player_index != 7:
            raise KeyError(player_index)
        return self.rating_values[field_id]

    def replace_player_base_rating(
        self,
        player_index: int,
        field_id: str,
        value: int,
        _progress: object,
    ) -> object:
        self.rating_replace_calls.append((player_index, field_id, value))
        self.rating_values[field_id] = value
        asset_id = f"apf:player-rating:{player_index}:{field_id}"
        self._modified.add(asset_id)
        return SimpleNamespace(asset_id=asset_id)

    def player_position_value(self, player_index: int) -> int:
        if player_index != 7:
            raise KeyError(player_index)
        return self.position_value

    def replace_player_position(
        self,
        player_index: int,
        value: int,
        _progress: object,
    ) -> object:
        self.position_replace_calls.append((player_index, value))
        self.position_value = value
        asset_id = f"apf:player-position:{player_index}"
        self._modified.add(asset_id)
        return SimpleNamespace(asset_id=asset_id)

    def revert(self, asset_id: str, _progress: object) -> bool:
        self.revert_calls.append(asset_id)
        if asset_id.startswith("apf:player-rating:7:"):
            field_id = asset_id.rsplit(":", 1)[1]
            self.rating_values[field_id] = self.rating_originals[field_id]
            self._modified.discard(asset_id)
            return True
        if asset_id == "apf:player-position:7":
            self.position_value = self.position_original
            self._modified.discard(asset_id)
            return True
        self.values[asset_id] = self.originals[asset_id]
        self._modified.discard(asset_id)
        return True

    def export_player_rating_sheet(
        self,
        model: object,
        destination: Path,
        *,
        progress: object,
    ) -> Path:
        self.rating_sheet_calls.append((model, destination))
        progress("Exporting complete APF player ratings sheet", 2_254, 2_254)  # type: ignore[operator]
        return destination

    def preview_player_rating_sheet(
        self,
        source: Path,
        progress: object,
    ) -> object:
        self.rating_sheet_preview_calls.append(source)
        progress("Checking private APF ratings sheet", 63_112, 63_112)  # type: ignore[operator]
        return self.rating_sheet_preview

    def apply_player_rating_sheet(
        self,
        preview: object,
        *,
        allow_conflicts: bool,
        progress: object,
    ) -> object:
        self.rating_sheet_apply_calls.append((preview, allow_conflicts))
        self.rating_values["speed"] = 97
        self._modified.add("apf:player-rating:7:speed")
        progress("Applying reviewed APF ratings sheet", 2, 2)  # type: ignore[operator]
        return SimpleNamespace(
            row_count=2_254,
            changed_count=2,
            applied_count=2,
            replacement_count=1,
            revert_count=1,
            conflict_count=0,
            undo_action_count=1,
            private_data=True,
        )


def _roster_model() -> PagedModel:
    first = _identity_metadata(
        "apf:roster-name:10",
        4,
        FIRST_NAME_OWNERS,
        "One mapped player field.",
        runtime_edit_scope="player_name",
    )
    last = _identity_metadata(
        "apf:roster-name:11",
        6,
        LAST_NAME_OWNERS,
        "Shared by 3 mapped roster fields; all change together.",
        runtime_edit_scope="player_name",
    )
    display = _identity_metadata(
        "apf:roster-name:20",
        12,
        TEAM_NAME_OWNERS,
        "One mapped team field.",
        runtime_edit_scope="team_display_name",
    )
    abbreviation = _identity_metadata(
        "apf:roster-name:21",
        3,
        TEAM_ABBREVIATION_OWNERS,
        "Shared by 2 mapped team fields.",
    )
    secondary = _identity_metadata(
        "apf:roster-name:22",
        2,
        TEAM_SECONDARY_OWNERS,
        "One mapped team field.",
    )
    return PagedModel(
        (
            _row(
                "apf:roster:player:7",
                "player",
                "JOHN SOURCE",
                "#0007 · QB",
                {
                    "player_index": 7,
                    "first_name": "JOHN",
                    "last_name": "SOURCE",
                    "position_abbreviation": "QB",
                    "position_editor": {
                        "asset_id": "apf:player-position:7",
                        "editable": True,
                        "backend_editable": True,
                        "gui_status": "semantic_dropdown_enabled",
                        "semantic_relative_offset": 0x34,
                        "mirror_relative_offset": 0x35,
                        "source_mirror_required": True,
                        "runtime_status": (
                            "offline_writer_proved_runtime_spot_check_pending"
                        ),
                        "runtime_reason": "Fixture runtime proof remains pending.",
                        "choices": tuple(
                            {
                                "code": item.code,
                                "abbreviation": item.abbreviation,
                                "name": item.name,
                            }
                            for item in PLAYER_POSITION_SCHEMA.positions
                        ),
                    },
                    "base_ratings": _base_rating_rows(),
                    "base_rating_scale": {
                        "native_minimum": 0,
                        "native_maximum": 100,
                        "stock_observed_minimum": 0,
                        "stock_observed_maximum": 99,
                        "runtime_status": "preview_read_only_transport_locked",
                    },
                    "identity_editor": {
                        "first_name": first,
                        "last_name": last,
                    },
                    "jersey_number_edit_status": {
                        "status": "read_only_unmapped",
                        "result": (
                            "No consumer-backed jersey-number field has been identified; "
                            "no jersey-number writer is exposed."
                        ),
                        "best_next_experiment": "Correlate controlled save pairs.",
                    },
                },
            ),
            _row(
                "apf:roster:team:0",
                "team",
                "SOURCE TEAM",
                "SRC · stock",
                {
                    "team_index": 0,
                    "display_name": "SOURCE TEAM",
                    "abbreviation": "SRC",
                    "secondary_abbreviation": "ST",
                    "slot_kind": "stock",
                    "identity_editor": {
                        "display_name": display,
                        "abbreviation": abbreviation,
                        "secondary_abbreviation": secondary,
                    },
                },
            ),
            _row(
                "apf:roster:stadium:0",
                "stadium",
                "Source Stadium",
                "Capacity 50,000",
                {"stadium_index": 0},
            ),
            _row(
                "apf:roster:membership:0:0",
                "membership",
                "JOHN SOURCE",
                "SOURCE TEAM · roster slot 0",
                {"team_index": 0, "player_index": 7},
            ),
        ),
        (
            "Editable player/team names use fixed allocations.",
            "Jersey numbers remain read-only.",
        ),
    )


class ApfRosterIdentityGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def _browser(
        self,
        *,
        writes_enabled: bool = True,
    ) -> tuple[InspectorBrowser, _RosterFacade, list[tuple[str, bool]]]:
        facade = _RosterFacade()
        tasks: list[tuple[str, bool]] = []

        def run_task(
            title: str,
            operation: object,
            complete: object,
            blocking: bool,
        ) -> None:
            tasks.append((title, blocking))
            result = operation(lambda *_progress: None)  # type: ignore[operator]
            complete(result)  # type: ignore[operator]

        browser = InspectorBrowser(
            "Live roster model",
            facade,  # type: ignore[arg-type]
            run_task,
            roster_mode=True,
            roster_writes_enabled=writes_enabled,
        )
        browser.set_model(_roster_model(), "fixture")
        self.application.processEvents()
        return browser, facade, tasks

    def test_disabled_product_mode_is_read_only_but_keeps_limits_visible(self) -> None:
        browser, facade, tasks = self._browser(writes_enabled=False)
        try:
            self.assertIsNotNone(browser.detail_scroll)
            assert browser.detail_scroll is not None
            self.assertEqual(browser.detail_scroll.objectName(), "rosterDetailScroll")
            self.assertEqual(browser.detail_scroll.widget().minimumHeight(), 600)
            self.assertIsNotNone(browser.roster_detail_tabs)
            assert browser.roster_detail_tabs is not None
            self.assertEqual(
                [
                    browser.roster_detail_tabs.tabText(index)
                    for index in range(browser.roster_detail_tabs.count())
                ],
                ["Identity & Names", "Base Ratings (28)", "Position (17)"],
            )
            self.assertEqual(browser.roster_detail_tabs.currentIndex(), 0)
            self.assertTrue(browser.roster_detail_tabs.isTabEnabled(1))
            self.assertTrue(browser.roster_detail_tabs.isTabEnabled(2))
            status = browser.table.item(0, 3).text()
            self.assertIn("28 base ratings editable", status)
            self.assertIn("Player names locked", status)
            self.assertTrue(browser.export_ratings_sheet_button.isVisibleTo(browser))
            self.assertTrue(browser.export_ratings_sheet_button.isEnabled())
            self.assertIn("2,254", browser.export_ratings_sheet_button.toolTip())
            self.assertIn("28", browser.export_ratings_sheet_button.toolTip())
            self.assertIn("private", browser.export_ratings_sheet_button.toolTip())
            self.assertTrue(browser.roster_name_editor.isEnabled())
            self.assertTrue(browser.roster_name_editor.isReadOnly())
            self.assertEqual(browser.roster_name_editor.text(), "JOHN")
            self.assertIn("Maximum: 4", browser.roster_allocation_note.text())
            self.assertIn("runtime-locked", browser.roster_allocation_note.text())
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            self.assertIn("Team abbreviations", browser.apply_roster_name_button.toolTip())
            self.assertIn("runtime-locked", browser.roster_boundary_note.text())
            browser.roster_name_editor.setText("MOD")
            browser._apply_roster_identity()
            self.assertEqual(facade.replace_calls, [])
            self.assertEqual(tasks, [])

            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertTrue(browser.roster_boundary_note.isVisibleTo(browser))
            self.assertIn("runtime-locked", browser.roster_boundary_note.text())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_complete_ratings_sheet_action_is_private_and_blocking(self) -> None:
        browser, facade, tasks = self._browser(writes_enabled=False)
        try:
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "ratings.csv"
                with patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                    return_value=(str(destination), "Spreadsheet CSV (*.csv)"),
                ), patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information"
                ) as information:
                    browser._export_player_rating_sheet()
                self.assertEqual(
                    tasks[-1],
                    ("Exporting complete APF player ratings sheet", True),
                )
                self.assertEqual(len(facade.rating_sheet_calls), 1)
                self.assertIs(facade.rating_sheet_calls[0][0], browser.model)
                self.assertEqual(facade.rating_sheet_calls[0][1], destination)
                message = information.call_args.args[2]
                self.assertIn("2,254 players × 28", message)
                self.assertIn("Keep it private", message)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_ratings_sheet_import_previews_before_one_explicit_batch_apply(self) -> None:
        browser, facade, tasks = self._browser(writes_enabled=False)
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("changed"))
        try:
            self.assertTrue(browser.import_ratings_sheet_button.isVisibleTo(browser))
            self.assertTrue(browser.import_ratings_sheet_button.isEnabled())
            self.assertEqual(
                browser.import_ratings_sheet_button.shortcut().toString(),
                "Ctrl+Shift+I",
            )
            tooltip = browser.import_ratings_sheet_button.toolTip()
            self.assertIn("validate every row without changing", tooltip)
            self.assertIn("explicit Apply", tooltip)
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "private-ratings.csv"
                source.write_text("private fixture", encoding="utf-8")
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getOpenFileName",
                        return_value=(
                            str(source),
                            "APF Player Ratings Sheet (*.csv)",
                        ),
                    ),
                    patch.object(
                        RatingSheetImportPreviewDialog,
                        "exec_",
                        return_value=QDialog.Accepted,
                    ),
                    patch(
                        "mod_editor.apf_studio.gui.QMessageBox.information"
                    ) as information,
                ):
                    browser._import_player_rating_sheet()
                    # The chooser and validation never mutate. Apply is queued
                    # only after the explicit preview acceptance returns.
                    self.assertEqual(facade.rating_sheet_preview_calls, [source])
                    self.assertEqual(facade.rating_sheet_apply_calls, [])
                    self.assertEqual(modified_events, [])
                    self.application.processEvents()

                self.assertEqual(
                    facade.rating_sheet_apply_calls,
                    [(facade.rating_sheet_preview, False)],
                )
                self.assertEqual(
                    tasks[-2:],
                    [
                        ("Checking private APF ratings sheet", True),
                        ("Applying reviewed APF ratings sheet", True),
                    ],
                )
                self.assertEqual(modified_events, ["changed"])
                self.assertIn("Modified ratings (1)", browser.table.item(0, 3).text())
                message = information.call_args.args[2]
                self.assertIn("One Undo restores", message)
                self.assertIn("private CSV was not added", message)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_ratings_sheet_preview_explains_counts_and_requires_conflict_acknowledgment(self) -> None:
        conflict = SimpleNamespace(
            player_index=7,
            player_name="JOHN SOURCE",
            field_id="speed",
            field_label="Speed",
            source_value=99,
            current_value=92,
            desired_value=97,
            action="replace",
            message="Sheet value disagrees with the active project edit.",
        )
        preview = SimpleNamespace(
            replacement_count=3,
            revert_count=2,
            unchanged_count=63_106,
            conflict_count=1,
            source_conflict_count=0,
            project_conflict_count=1,
            error_count=0,
            conflicts=(conflict,),
            errors=(),
            private_data=True,
        )
        dialog = RatingSheetImportPreviewDialog(
            Path("/private/apf-ratings.csv"), preview
        )
        try:
            self.assertEqual(dialog.count_labels["New replacements"].text(), "3")
            self.assertEqual(dialog.count_labels["Reverts to source"].text(), "2")
            self.assertEqual(dialog.count_labels["Already matches"].text(), "63,106")
            self.assertEqual(dialog.count_labels["Source conflicts"].text(), "0")
            self.assertEqual(dialog.count_labels["Project conflicts"].text(), "1")
            self.assertFalse(dialog.apply_button.isEnabled())
            self.assertTrue(dialog.conflict_confirmation.isVisibleTo(dialog))
            self.assertIn("Player 7", dialog.sample_view.toPlainText())
            self.assertIn("JOHN SOURCE", dialog.sample_view.toPlainText())
            self.assertIn("Speed", dialog.sample_view.toPlainText())
            self.assertIn("92 → 97", dialog.sample_view.toPlainText())
            self.assertIn("Keep it private", dialog.private_warning.text())
            self.assertIn("source/revert-only", dialog.private_warning.text())
            self.assertIn("stay untouched", dialog.state_note.text())
            self.assertIn("#eef4ff", dialog.styleSheet())
            self.assertIn("#25354b", dialog.styleSheet())
            self.assertEqual(
                dialog.cancel_button.accessibleName(),
                "Cancel APF ratings-sheet import",
            )

            dialog.conflict_confirmation.setChecked(True)
            self.assertTrue(dialog.apply_button.isEnabled())
            self.assertTrue(dialog.allow_conflicts)
            self.assertEqual(dialog.apply_button.text(), "Apply 5 rating changes")
            self.assertIn("One Undo restores", dialog.state_note.text())
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_ratings_sheet_preview_errors_cannot_be_overridden(self) -> None:
        issue = SimpleNamespace(
            player_index=7,
            player_name="JOHN SOURCE",
            field_id="catch",
            field_label="Catch",
            current_value=50,
            desired_value=100,
            message="A newly authored rating must be 0..99.",
        )
        preview = SimpleNamespace(
            replacement_count=1,
            revert_count=0,
            unchanged_count=63_110,
            conflict_count=1,
            source_conflict_count=0,
            project_conflict_count=1,
            error_count=1,
            conflicts=(),
            errors=(issue,),
            private_data=True,
        )
        dialog = RatingSheetImportPreviewDialog(Path("ratings.csv"), preview)
        try:
            self.assertFalse(dialog.apply_button.isEnabled())
            self.assertFalse(dialog.conflict_confirmation.isEnabled())
            self.assertIn("Fix the CSV errors", dialog.state_note.text())
            self.assertIn("Catch", dialog.sample_view.toPlainText())
            self.assertIn("50 → 100", dialog.sample_view.toPlainText())
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_ratings_sheet_source_conflicts_are_never_overrideable(self) -> None:
        source_issue = SimpleNamespace(
            row_number=2,
            player_index=7,
            field_id=None,
            message=(
                "Source fingerprint does not match the exact loaded game; export "
                "a fresh sheet before importing."
            ),
        )
        conflict = SimpleNamespace(
            player_index=7,
            player_name="JOHN SOURCE",
            field_id="speed",
            field_label="Speed",
            source_value=99,
            current_value=99,
            desired_value=97,
            action="source_conflict",
            message="Source-owned player identity does not match this game.",
        )
        preview = SimpleNamespace(
            replacement_count=1,
            revert_count=0,
            unchanged_count=63_110,
            conflict_count=2,
            source_conflict_count=1,
            project_conflict_count=1,
            error_count=0,
            conflicts=(conflict,),
            source_conflicts=(source_issue,),
            errors=(),
            private_data=True,
        )
        dialog = RatingSheetImportPreviewDialog(Path("wrong-source.csv"), preview)
        try:
            self.assertEqual(dialog.count_labels["Source conflicts"].text(), "1")
            self.assertEqual(dialog.count_labels["Project conflicts"].text(), "1")
            self.assertFalse(dialog.apply_button.isEnabled())
            self.assertTrue(dialog.conflict_confirmation.isHidden())
            self.assertFalse(dialog.allow_conflicts)

            # Even an artificial programmatic check cannot turn a source
            # mismatch into the narrower active-project override route.
            dialog.conflict_confirmation.setChecked(True)
            self.assertFalse(dialog.apply_button.isEnabled())
            self.assertFalse(dialog.allow_conflicts)
            self.assertIn("exact loaded game source", dialog.state_note.text())
            self.assertIn("cannot be overridden", dialog.state_note.text())
            self.assertIn("Export a fresh ratings sheet", dialog.state_note.text())
            self.assertIn("Source fingerprint", dialog.sample_view.toPlainText())
            self.assertIn("exact loaded game", dialog.sample_view.toPlainText())
        finally:
            dialog.deleteLater()
            self.application.processEvents()

    def test_player_base_ratings_are_exact_searchable_editable_and_hide_for_nonplayers(self) -> None:
        browser, _facade, _tasks = self._browser(writes_enabled=False)
        try:
            panel = browser.base_ratings_panel
            self.assertIsNotNone(browser.roster_detail_tabs)
            assert browser.roster_detail_tabs is not None
            self.assertEqual(browser.roster_detail_tabs.currentIndex(), 0)
            self.assertTrue(browser.roster_detail_tabs.isTabEnabled(1))
            browser.roster_detail_tabs.setCurrentIndex(1)
            self.application.processEvents()
            self.assertTrue(panel.isVisibleTo(browser))
            self.assertEqual(panel.table.rowCount(), 28)
            self.assertEqual(panel.table.editTriggers(), panel.table.NoEditTriggers)
            self.assertEqual(panel.table.columnCount(), 4)
            self.assertEqual(panel.table.item(0, 0).text(), "Speed")
            self.assertEqual(panel.table.item(0, 1).text(), "99")
            self.assertEqual(panel.table.item(0, 2).text(), "0xBA")
            self.assertEqual(panel.table.item(0, 3).text(), "Original")
            self.assertEqual(panel.table.item(25, 0).text(), "Unknown Rating 24")
            self.assertEqual(panel.table.item(25, 1).text(), "100")
            self.assertIn("0–99", panel.note.text())
            self.assertIn("native 100", panel.note.text())
            self.assertIn("Overall", panel.note.text())
            self.assertIn("abilities", panel.note.text())
            self.assertIn("tier", panel.note.text())
            self.assertIn("Dan Marino", panel.note.text())
            self.assertIn("no on-screen numeric", panel.note.text())
            self.assertIn("28 / 28", panel.status.text())
            self.assertIn("EDITABLE", panel.status.text())
            self.assertTrue(panel.value_editor.isEnabled())
            self.assertEqual(panel.value_editor.value(), 99)
            self.assertFalse(panel.apply_button.isEnabled())

            panel.search.setText("catch")
            self.application.processEvents()
            self.assertEqual(panel.table.rowCount(), 1)
            self.assertEqual(panel.table.item(0, 0).text(), "Catch")
            self.assertEqual(panel.table.item(0, 1).text(), "50")

            panel.search.clear()
            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertTrue(panel.isHidden())
            self.assertEqual(panel.table.rowCount(), 0)
            self.assertEqual(browser.roster_detail_tabs.currentIndex(), 0)
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(1))
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(2))

            browser.table.selectRow(2)
            self.application.processEvents()
            self.assertTrue(panel.isHidden())
            self.assertEqual(browser.roster_detail_tabs.currentIndex(), 0)
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(1))
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(2))
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_player_position_dropdown_applies_reverts_and_marks_the_player(self) -> None:
        browser, facade, tasks = self._browser(writes_enabled=False)
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("changed"))
        try:
            panel = browser.player_position_panel
            self.assertIsNotNone(browser.roster_detail_tabs)
            assert browser.roster_detail_tabs is not None
            self.assertTrue(browser.roster_detail_tabs.isTabEnabled(2))
            browser.roster_detail_tabs.setCurrentIndex(2)
            self.application.processEvents()

            self.assertTrue(panel.isVisibleTo(browser))
            self.assertEqual(panel.position.count(), 17)
            self.assertEqual(panel.position.itemData(0), 0)
            self.assertEqual(panel.position.itemText(0), "QB — Quarterback")
            self.assertEqual(panel.position.itemData(16), 16)
            self.assertEqual(panel.position.itemText(16), "DE — Defensive End")
            self.assertEqual(panel.position.currentData(), 0)
            self.assertFalse(panel.apply_button.isEnabled())
            self.assertFalse(panel.revert_button.isEnabled())
            self.assertIn("code 0", panel.current_state.text())
            self.assertIn("team", panel.note.text())
            self.assertIn("depth-chart", panel.note.text())
            self.assertIn("Overall", panel.note.text())
            self.assertIn("+0x34", panel.note.text())
            self.assertIn("+0x35", panel.note.text())
            self.assertIn("spot check is still pending", panel.note.text())

            panel.position.setCurrentIndex(panel.position.findData(3))
            self.assertTrue(panel.apply_button.isEnabled())
            self.assertIn("code 3", panel.apply_button.toolTip())
            panel._apply_position()

            self.assertEqual(facade.position_replace_calls, [(7, 3)])
            self.assertEqual(
                tasks[-1], ("Applying exact APF player position", True)
            )
            self.assertEqual(panel.position.currentData(), 3)
            self.assertIn("WR — Wide Receiver", panel.current_state.text())
            self.assertIn("MODIFIED", panel.status.text())
            self.assertTrue(panel.revert_button.isEnabled())
            self.assertIn("Modified position", browser.table.item(0, 3).text())
            self.assertEqual(browser.table.item(0, 2).text(), "#0007 · WR")

            panel._revert_position()
            self.assertEqual(
                facade.revert_calls[-1], "apf:player-position:7"
            )
            self.assertEqual(
                tasks[-1], ("Reverting exact APF player position", True)
            )
            self.assertEqual(panel.position.currentData(), 0)
            self.assertIn("ORIGINAL", panel.status.text())
            self.assertFalse(panel.revert_button.isEnabled())
            self.assertNotIn("Modified position", browser.table.item(0, 3).text())
            self.assertEqual(modified_events, ["changed", "changed"])

            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertTrue(panel.isHidden())
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(2))
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_rating_apply_and_individual_revert_refresh_badges_and_project_state(self) -> None:
        browser, facade, tasks = self._browser(writes_enabled=False)
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("changed"))
        try:
            panel = browser.base_ratings_panel
            self.assertEqual(panel.table.item(0, 0).text(), "Speed")
            panel.value_editor.setValue(97)
            self.assertTrue(panel.apply_button.isEnabled())
            self.assertIn("exact native value 97", panel.apply_button.toolTip())
            panel._apply_rating()

            self.assertEqual(facade.rating_replace_calls, [(7, "speed", 97)])
            self.assertEqual(tasks[-1], ("Applying exact APF base rating", True))
            self.assertEqual(panel.table.item(0, 1).text(), "97")
            self.assertEqual(panel.table.item(0, 3).text(), "● Modified")
            self.assertIn("1 MODIFIED", panel.status.text())
            self.assertIn("Modified ratings (1)", browser.table.item(0, 3).text())
            self.assertTrue(panel.revert_button.isEnabled())

            panel._revert_rating()
            self.assertEqual(
                facade.revert_calls[-1], "apf:player-rating:7:speed"
            )
            self.assertEqual(tasks[-1], ("Reverting exact APF base rating", True))
            self.assertEqual(panel.table.item(0, 1).text(), "99")
            self.assertEqual(panel.table.item(0, 3).text(), "Original")
            self.assertFalse(panel.revert_button.isEnabled())
            self.assertEqual(modified_events, ["changed", "changed"])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_native_100_is_shown_exactly_and_never_silently_clamped(self) -> None:
        browser, facade, tasks = self._browser(writes_enabled=False)
        try:
            panel = browser.base_ratings_panel
            panel.table.selectRow(25)
            self.application.processEvents()
            self.assertEqual(panel.table.item(25, 1).text(), "100")
            self.assertEqual(panel.value_editor.maximum(), 100)
            self.assertEqual(panel.value_editor.value(), 100)
            self.assertFalse(panel.apply_button.isEnabled())
            self.assertIn("source/revert-only", panel.apply_button.toolTip())

            panel.value_editor.setValue(99)
            self.assertTrue(panel.apply_button.isEnabled())
            panel._apply_rating()
            self.assertEqual(
                facade.rating_replace_calls,
                [(7, "unknown_rating_24", 99)],
            )
            self.assertEqual(panel.value_editor.maximum(), 99)
            self.assertEqual(panel.value_editor.value(), 99)

            panel._revert_rating()
            self.assertEqual(tasks[-1], ("Reverting exact APF base rating", True))
            self.assertEqual(panel.table.item(25, 1).text(), "100")
            self.assertEqual(panel.value_editor.maximum(), 100)
            self.assertEqual(panel.value_editor.value(), 100)
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_player_names_replace_revert_and_disclose_every_alias_owner(self) -> None:
        browser, facade, tasks = self._browser()
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("changed"))
        try:
            self.assertEqual(browser.table.columnCount(), 4)
            self.assertTrue(browser.detail_fields.isHidden())
            self.assertEqual(
                browser.table.horizontalHeaderItem(3).text(), "Roster status"
            )
            self.assertIn("28 base ratings editable", browser.table.item(0, 3).text())
            self.assertIn("Player names editable", browser.table.item(0, 3).text())
            self.assertEqual(browser.roster_field_combo.count(), 2)
            self.assertEqual(browser.roster_field_combo.itemData(0), "first_name")
            self.assertEqual(browser.roster_field_combo.itemData(1), "last_name")
            self.assertIn("Editable", browser.roster_field_combo.itemText(0))
            self.assertEqual(browser.roster_name_editor.text(), "JOHN")
            self.assertFalse(browser.roster_name_editor.isReadOnly())
            self.assertEqual(
                browser.apply_roster_name_button.text(), "Replace Player Name"
            )
            self.assertEqual(
                browser.revert_roster_name_button.text(), "Revert Player Name"
            )
            self.assertIsNotNone(browser.roster_detail_tabs)
            assert browser.roster_detail_tabs is not None
            self.assertEqual(browser.roster_detail_tabs.currentIndex(), 0)
            self.assertEqual(browser.roster_detail_tabs.tabText(0), "Identity & Names")
            self.assertEqual(browser.roster_detail_tabs.tabText(1), "Base Ratings (28)")
            self.assertEqual(browser.roster_detail_tabs.tabText(2), "Position (17)")
            self.assertTrue(browser.roster_detail_tabs.isTabEnabled(1))
            self.assertTrue(browser.roster_detail_tabs.isTabEnabled(2))
            self.assertIn("Maximum: 4", browser.roster_allocation_note.text())
            self.assertIn(
                "Known affected fields: 1",
                browser.roster_allocation_note.text(),
            )
            self.assertEqual(
                browser.roster_aliases_button.text(), "View 1 affected field…"
            )
            self.assertIn("Player 7 · first name", browser.roster_aliases_button.toolTip())
            self.assertTrue(browser.roster_boundary_note.isVisibleTo(browser))
            self.assertIn("separate tabs", browser.roster_boundary_note.text())
            self.assertIn("Jersey number remains read-only", browser.roster_boundary_note.text())
            self.assertIn("Dan CODEX", browser.roster_boundary_note.toolTip())
            self.assertIn(
                "No consumer-backed", browser.roster_boundary_note.toolTip()
            )
            browser.roster_field_combo.setCurrentIndex(1)
            self.assertEqual(browser.roster_name_editor.text(), "SOURCE")
            self.assertIn(
                "Known affected fields: 3",
                browser.roster_allocation_note.text(),
            )
            self.assertIn("all change together", browser.roster_allocation_note.text())
            self.assertEqual(
                browser.roster_aliases_button.text(), "View 3 affected fields…"
            )
            dialog = browser._build_roster_alias_dialog()
            owners_view = dialog.findChild(QPlainTextEdit, "rosterAliasOwners")
            self.assertIsNotNone(owners_view)
            assert owners_view is not None
            for owner in (
                "Player 7 · last name",
                "Player 8 · last name",
                "Player 9 · first name",
            ):
                self.assertIn(owner, owners_view.toPlainText())
                self.assertNotIn(owner, browser.roster_allocation_note.text())
            self.assertEqual(len(owners_view.toPlainText().splitlines()), 3)
            dialog.deleteLater()
            with patch.object(QDialog, "exec_", return_value=QDialog.Accepted) as execute:
                browser.roster_aliases_button.click()
            execute.assert_called_once_with()
            self.assertIn(
                "Shared-allocation warning", browser.roster_allocation_note.text()
            )
            browser.roster_name_editor.setText("TOO-LONG")
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            self.assertIn(
                "allocation limit is 6",
                browser.apply_roster_name_button.toolTip(),
            )
            browser.roster_name_editor.setText("MOD")
            self.assertTrue(browser.apply_roster_name_button.isEnabled())
            browser._apply_roster_identity()
            self.assertEqual(
                facade.replace_calls, [("apf:roster-name:11", "MOD")]
            )
            self.assertEqual(tasks, [("Replacing APF player name", True)])
            self.assertEqual(browser.table.item(0, 0).text(), "JOHN MOD")
            self.assertIn(
                "Modified name allocation (1)", browser.table.item(0, 3).text()
            )
            self.assertTrue(browser.revert_roster_name_button.isEnabled())
            self.assertEqual(
                browser.revert_roster_name_button.text(), "Revert Player Name"
            )

            browser._revert_roster_identity()
            self.assertEqual(facade.revert_calls, ["apf:roster-name:11"])
            self.assertEqual(tasks[-1], ("Reverting APF player name", True))
            self.assertEqual(browser.table.item(0, 0).text(), "JOHN SOURCE")
            self.assertEqual(modified_events, ["changed", "changed"])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_large_shared_name_allocation_discloses_all_23_fields_in_dialog(self) -> None:
        browser, _facade, _tasks = self._browser()
        try:
            owners = tuple(
                _identity_owner("player", index, "last_name")
                for index in range(23)
            )
            row = browser._selected_row()
            self.assertIsNotNone(row)
            assert row is not None
            editors = row.fields["identity_editor"]
            assert isinstance(editors, dict)
            first = editors["first_name"]
            assert isinstance(first, dict)
            first["known_alias_count"] = len(owners)
            first["known_alias_owners"] = tuple(
                {
                    "entity_kind": owner.entity_kind,
                    "entity_index": owner.entity_index,
                    "field": owner.field,
                    "label": owner.label,
                }
                for owner in owners
            )
            browser._roster_allocations["apf:roster-name:10"] = SimpleNamespace(
                asset_id="apf:roster-name:10",
                text="JOHN",
                maximum_utf16_units=4,
                known_owners=owners,
                known_owner_count=len(owners),
                editable=True,
                note="Shared by 23 mapped roster fields.",
            )
            browser._roster_field_changed()

            self.assertEqual(
                browser.roster_aliases_button.text(), "View 23 affected fields…"
            )
            self.assertNotIn("Player 22", browser.roster_allocation_note.text())
            dialog = browser._build_roster_alias_dialog()
            owners_view = dialog.findChild(QPlainTextEdit, "rosterAliasOwners")
            self.assertIsNotNone(owners_view)
            assert owners_view is not None
            lines = owners_view.toPlainText().splitlines()
            self.assertEqual(len(lines), 23)
            self.assertEqual(lines[0], "Player 0 · last name")
            self.assertEqual(lines[-1], "Player 22 · last name")
            self.assertTrue(owners_view.isReadOnly())
            self.assertGreaterEqual(dialog.width(), 620)
            self.assertGreaterEqual(dialog.height(), 520)
            self.assertGreaterEqual(owners_view.minimumHeight(), 360)
            dialog.deleteLater()
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_team_display_name_replace_and_revert_refresh_the_row(self) -> None:
        browser, facade, tasks = self._browser()
        modified_events: list[str] = []
        browser.modifiedChanged.connect(lambda: modified_events.append("changed"))
        try:
            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertIn("Team name editable", browser.table.item(1, 3).text())
            self.assertEqual(browser.roster_field_combo.currentData(), "display_name")
            self.assertIn("Editable", browser.roster_field_combo.itemText(0))
            self.assertFalse(browser.roster_name_editor.isReadOnly())
            browser.roster_name_editor.setText("MOD TEAM")
            self.assertTrue(browser.apply_roster_name_button.isEnabled())
            browser._apply_roster_identity()

            self.assertEqual(
                facade.replace_calls, [("apf:roster-name:20", "MOD TEAM")]
            )
            self.assertEqual(tasks, [("Replacing APF team name", True)])
            self.assertEqual(browser.table.item(1, 0).text(), "MOD TEAM")
            self.assertIn(
                "Modified team-name allocation", browser.table.item(1, 3).text()
            )
            self.assertEqual(browser.detail_title.text(), "MOD TEAM")
            self.assertEqual(browser.roster_field_combo.currentData(), "display_name")
            self.assertTrue(browser.revert_roster_name_button.isEnabled())

            browser._revert_roster_identity()
            self.assertEqual(facade.revert_calls, ["apf:roster-name:20"])
            self.assertEqual(tasks[-1], ("Reverting APF team name", True))
            self.assertEqual(browser.table.item(1, 0).text(), "SOURCE TEAM")
            self.assertFalse(browser.revert_roster_name_button.isEnabled())
            self.assertEqual(modified_events, ["changed", "changed"])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_zero_capacity_player_name_is_explicitly_read_only(self) -> None:
        browser, facade, tasks = self._browser()
        try:
            asset_id = "apf:roster-name:10"
            facade.values[asset_id] = ""
            facade.identity_scopes[asset_id] = None
            browser._roster_allocations[asset_id] = SimpleNamespace(
                asset_id=asset_id,
                text="",
                maximum_utf16_units=0,
                known_owners=FIRST_NAME_OWNERS,
                known_owner_count=1,
                editable=False,
                note="Source allocation has no payload capacity.",
            )
            browser._roster_field_changed()

            self.assertFalse(browser.roster_name_editor.isEnabled())
            self.assertTrue(browser.roster_name_editor.isReadOnly())
            self.assertEqual(browser.apply_roster_name_button.text(), "Replace (Locked)")
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            note = browser.roster_allocation_note.text()
            self.assertIn("Maximum: 0 UTF-16 characters", note)
            self.assertIn("zero writable characters", note)
            self.assertIn("Known affected fields: 1", note)
            self.assertEqual(
                browser.roster_aliases_button.text(), "View 1 affected field…"
            )
            self.assertIn(
                "zero writable characters",
                browser.apply_roster_name_button.toolTip(),
            )
            browser._apply_roster_identity()
            self.assertEqual(facade.replace_calls, [])
            self.assertEqual(tasks, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_shared_modified_allocation_is_counted_once_per_row(self) -> None:
        browser, facade, _tasks = self._browser()
        try:
            row = browser._selected_row()
            self.assertIsNotNone(row)
            assert row is not None
            editors = row.fields["identity_editor"]
            assert isinstance(editors, dict)
            first = editors["first_name"]
            assert isinstance(first, dict)
            first["asset_id"] = "apf:roster-name:11"
            facade._modified.add("apf:roster-name:11")

            self.assertEqual(browser._roster_modified_count(row), 1)
            self.assertEqual(
                browser._roster_modified_identity_asset_ids(row),
                frozenset({"apf:roster-name:11"}),
            )
            browser.refresh(row.row_id)
            self.assertIn(
                "Modified name allocation (1)", browser.table.item(0, 3).text()
            )
            self.assertNotIn("(2)", browser.table.item(0, 3).text())
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_team_fields_and_read_only_row_boundaries_are_explicit(self) -> None:
        browser, _facade, _tasks = self._browser()
        try:
            browser.table.selectRow(1)
            self.application.processEvents()
            self.assertEqual(browser.roster_field_combo.count(), 3)
            self.assertEqual(
                [
                    browser.roster_field_combo.itemData(index)
                    for index in range(browser.roster_field_combo.count())
                ],
                ["display_name", "abbreviation", "secondary_abbreviation"],
            )
            self.assertEqual(browser.roster_name_editor.text(), "SOURCE TEAM")
            self.assertTrue(browser.roster_boundary_note.isVisibleTo(browser))
            self.assertIn("Team display name · Editable", browser.roster_boundary_note.text())

            browser.roster_field_combo.setCurrentIndex(1)
            self.assertEqual(browser.roster_name_editor.text(), "SRC")
            self.assertTrue(browser.roster_name_editor.isReadOnly())
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            self.assertIn("Locked", browser.roster_field_combo.itemText(1))
            self.assertIn("Maximum: 3", browser.roster_allocation_note.text())
            self.assertIn(
                "Known affected fields: 2",
                browser.roster_allocation_note.text(),
            )
            self.assertIn("Team 0 · abbreviation", browser.roster_aliases_button.toolTip())
            self.assertIn("Team 1 · abbreviation", browser.roster_aliases_button.toolTip())
            self.assertNotIn("Team 0 · abbreviation", browser.roster_allocation_note.text())
            self.assertIn("Shared-allocation warning", browser.roster_allocation_note.text())
            self.assertIn("remain locked", browser.roster_allocation_note.text())

            browser.table.selectRow(2)
            self.application.processEvents()
            self.assertFalse(browser.roster_field_combo.isEnabled())
            self.assertFalse(browser.roster_name_editor.isEnabled())
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            self.assertFalse(browser.revert_roster_name_button.isEnabled())
            self.assertFalse(browser.roster_aliases_button.isEnabled())
            assert browser.roster_detail_tabs is not None
            self.assertEqual(browser.roster_detail_tabs.currentIndex(), 0)
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(1))
            self.assertFalse(browser.roster_detail_tabs.isTabEnabled(2))
            self.assertIn("Stadium rows are read-only", browser.roster_boundary_note.text())

            browser.table.selectRow(3)
            self.application.processEvents()
            self.assertFalse(browser.roster_field_combo.isEnabled())
            self.assertIn(
                "Roster-membership rows are read-only",
                browser.roster_boundary_note.text(),
            )
        finally:
            browser.deleteLater()
            self.application.processEvents()

    def test_over_limit_and_nul_names_fail_before_dispatch_with_plain_errors(self) -> None:
        browser, facade, tasks = self._browser()
        try:
            browser.table.selectRow(1)
            self.application.processEvents()
            browser.roster_name_editor.setText("THIS TEAM NAME IS TOO LONG")
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            self.assertIn("allocation limit is 12", browser.apply_roster_name_button.toolTip())
            browser._apply_roster_identity()
            self.assertEqual(facade.replace_calls, [])
            self.assertEqual(tasks, [])

            browser.roster_name_editor.setText("A\0B")
            self.assertFalse(browser.apply_roster_name_button.isEnabled())
            self.assertIn("cannot contain a NUL", browser.apply_roster_name_button.toolTip())
            browser._apply_roster_identity()
            self.assertEqual(facade.replace_calls, [])
        finally:
            browser.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
