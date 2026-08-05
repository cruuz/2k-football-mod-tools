"""Headless facade and offscreen Qt integration for complete Team Kit bundles."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402
from PIL import Image  # noqa: E402

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_uniform_catalog import (  # noqa: E402
    load_nfl2k5_uniform_catalog,
)
from mod_editor.core.product_catalog import (  # noqa: E402
    PRODUCT_CATEGORY_ORDER,
    ProductCategory,
)
from mod_editor.gui.studio_qt import (  # noqa: E402
    BrowseOnlyFacade,
    StudioMainWindow,
)
from mod_editor.studio.facade import Nfl2k5StudioFacade  # noqa: E402
from mod_editor.studio.uniform_bundle import TEAM_KIT_MANIFEST  # noqa: E402


class _LockCheckingTeamKitService:
    def __init__(self, lock: object, calls: list[tuple[object, ...]]) -> None:
        self.lock = lock
        self.calls = calls

    def _assert_locked(self) -> None:
        checker = getattr(self.lock, "_is_owned", None)
        if callable(checker):
            if not checker():
                raise AssertionError("Team Kit service escaped the facade source lock")

    def export(
        self, selectors: object, destination: Path, *, container: str, progress: object
    ) -> object:
        self._assert_locked()
        progress("explicit sets", 1, 2)
        self.calls.append(("sets", tuple(selectors), destination, container))
        return SimpleNamespace(
            path=destination,
            asset_count=39,
            set_selectors=tuple(selectors),
            message="Explicit Team Kit exported",
        )

    def export_team(self, **values: object) -> object:
        self._assert_locked()
        progress = values.pop("progress")
        progress("paired team", 2, 2)
        self.calls.append(("team", values.copy()))
        return SimpleNamespace(
            path=values["destination"],
            asset_count=78,
            set_selectors=("18H0", "18A0"),
            message="Paired Team Kit exported",
        )

    def import_edited(self, source: Path, *, progress: object) -> object:
        self._assert_locked()
        progress("transaction", 3, 3)
        self.calls.append(("import", source))
        return SimpleNamespace(
            path=source,
            asset_count=78,
            changed_count=2,
            set_selectors=("18H0", "18A0"),
            message="Imported 2 components as one Undo action",
        )


class TeamKitFacadeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_uniform_catalog()

    def test_all_team_kit_routes_hold_the_active_source_session_lock(self) -> None:
        facade = Nfl2k5StudioFacade(
            uniform_catalog=self.catalog,
            xemu_command=(),
        )
        # These bounded routes need only an active source-bound session; the
        # injected service proves the lock and exact argument forwarding.
        facade._session = object()  # type: ignore[assignment]
        calls: list[tuple[object, ...]] = []
        facade._team_kit_service_factory = (  # type: ignore[assignment]
            lambda _catalog, _session: _LockCheckingTeamKitService(
                facade._lock, calls
            )
        )
        events: list[tuple[str, int, int]] = []
        progress = lambda stage, done, total: events.append((stage, done, total))

        explicit = facade.export_team_kit_sets(
            ("18H0",), Path("/private/18H0"),
            container="folder", progress=progress,
        )
        paired = facade.export_team_kit(
            asset_code="18", variant=0, sides="BOTH",
            destination=Path("/private/giants.zip"), container="zip",
            progress=progress,
        )
        imported = facade.import_team_kit(Path("/private/edited"), progress)

        self.assertEqual(explicit.asset_count, 39)
        self.assertEqual(paired.asset_count, 78)
        self.assertEqual(imported.changed_count, 2)
        self.assertEqual(calls[0], (
            "sets", ("18H0",), Path("/private/18H0"), "folder",
        ))
        self.assertEqual(calls[1][0], "team")
        self.assertEqual(calls[1][1]["asset_code"], "18")
        self.assertEqual(calls[1][1]["sides"], "BOTH")
        self.assertEqual(calls[2], ("import", Path("/private/edited")))
        self.assertEqual(events, [
            ("explicit sets", 1, 2),
            ("paired team", 2, 2),
            ("transaction", 3, 3),
        ])


class _WindowTeamKitFacade(BrowseOnlyFacade):
    def __init__(self) -> None:
        self.source_ready = False
        self.source_display_name = "Synthetic NFL 2K5"
        self.source_path = Path("/private/NFL2K5.iso")
        self.source_sha256 = "a" * 64
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.modified_count = 0
        self.can_undo = False
        self.can_launch_xemu = False
        self.calls: list[tuple[object, ...]] = []
        self.import_changed = 2
        self.import_error: Exception | None = None

    def export_team_kit_sets(
        self, selectors: object, destination: Path, *, container: str,
        progress: object,
    ) -> object:
        progress("Exporting set", 40, 40)
        selected = tuple(selectors)
        self.calls.append(("sets", selected, destination, container))
        return SimpleNamespace(
            path=destination,
            asset_count=39 * len(selected),
            set_selectors=selected,
            message="Complete selected physical set exported privately.",
        )

    def export_team_kit(self, **values: object) -> object:
        progress = values.pop("progress")
        progress("Exporting paired kit", 79, 79)
        self.calls.append(("team", values.copy()))
        return SimpleNamespace(
            path=values["destination"],
            asset_count=78,
            set_selectors=("18H0", "18A0"),
            message="Complete paired Team Kit exported privately.",
        )

    def import_team_kit(self, source: Path, progress: object) -> object:
        if self.import_error is not None:
            raise self.import_error
        progress("Validating all kit PNGs", 79, 79)
        self.calls.append(("import", source))
        if self.import_changed:
            self.modified_asset_ids = frozenset({
                "nfl2k5.uniform.18h0.torso",
                "nfl2k5.uniform.18a0.torso",
            })
            self.modified_count = self.import_changed
            self.can_undo = True
        return SimpleNamespace(
            path=source,
            asset_count=78,
            changed_count=self.import_changed,
            set_selectors=("18H0", "18A0"),
            message=(
                "Imported 2 changed components as one Undo action."
                if self.import_changed else
                "All decoded pixels matched; nothing was staged."
            ),
        )


class TeamKitOffscreenGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="team-kit-gui-")
        self.root = Path(self.temporary.name)
        self.facade = _WindowTeamKitFacade()
        self.window = StudioMainWindow(facade=self.facade)
        self.errors: list[str] = []
        self.window._show_error = self.errors.append  # type: ignore[method-assign]
        self.window._save_recovery_snapshot = lambda: None  # type: ignore[method-assign]
        self.window._load_preview = lambda _asset: None  # type: ignore[method-assign]
        self.window._preview_selected_asset = lambda: None  # type: ignore[method-assign]

        def immediate(operation: object, success: object, **_kwargs: object) -> None:
            try:
                value = operation(lambda *_args: None)
            except Exception as exc:
                self.window._set_status(f"Could not finish: {exc}")
                self.window._show_error(str(exc))
            else:
                success(value)

        self.window._start_task = immediate  # type: ignore[method-assign]
        for index in range(self.window.uniform_list.count()):
            item = self.window.uniform_list.item(index)
            if item.data(Qt.UserRole) == "18H0":
                self.window.uniform_list.setCurrentItem(item)
                break

    def tearDown(self) -> None:
        self.window._allow_close = True
        self.window.close()
        self.temporary.cleanup()

    def _ready(self) -> None:
        self.facade.source_ready = True
        self.window._refresh_action_states()

    def test_controls_explain_private_scope_format_and_source_gating(self) -> None:
        self.assertFalse(self.window.export_team_kit_button.isEnabled())
        self.assertFalse(self.window.import_team_kit_button.isEnabled())
        self.assertIn("retail artwork", self.window.team_kit_warning.text())
        self.assertIn("do not share", self.window.team_kit_warning.text())
        self.assertEqual(self.window.team_kit_scope.count(), 4)
        self.assertEqual(self.window.team_kit_scope.currentData(), "BOTH")
        self.assertIn("18H0 + 18A0", self.window.team_kit_scope.currentText())
        self.assertEqual(
            [self.window.team_kit_container.itemData(index) for index in range(2)],
            ["folder", "zip"],
        )
        self._ready()
        self.assertTrue(self.window.export_team_kit_button.isEnabled())
        self.assertTrue(self.window.import_team_kit_button.isEnabled())
        self.assertTrue(self.window.import_digit_sheet_button.isEnabled())

    def test_selected_set_opens_one_searchable_canonical_equipment_list(self) -> None:
        # Catalog discovery is available before a source is loaded; mutation
        # actions in the destination browser retain their existing source gate.
        self.assertTrue(self.window.browse_uniform_equipment_button.isEnabled())
        self.window.browse_uniform_equipment_button.click()
        self.application.processEvents()

        texture_row = PRODUCT_CATEGORY_ORDER.index(ProductCategory.TEXTURES) + 1
        self.assertEqual(self.window.navigation.currentRow(), texture_row)
        state = self.window._visual_browsers[ProductCategory.TEXTURES]
        self.assertEqual(state.search.text(), "18H0 equipment")
        visible_ids = tuple(
            str(state.asset_list.item(index).data(Qt.UserRole))
            for index in range(state.asset_list.count())
        )
        self.assertEqual(len(visible_ids), 45)
        self.assertEqual(len(set(visible_ids)), 45)

        expected = tuple(
            asset.asset_id
            for asset in self.window.extended_visual_catalog.assets_for_kind(
                "uniform_equipment_texture"
            )
            if "18H0" in asset.search_terms
        )
        self.assertEqual(set(visible_ids), set(expected))
        selected = self.window.extended_visual_catalog.get_asset(visible_ids[0])
        self.assertEqual(selected.provider_edit("replacement.png"), {
            "asset_id": selected.asset_id,
            "kind": "uniform_equipment_texture",
            "png": "replacement.png",
        })
        self.assertFalse(state.export_button.isEnabled())
        self.assertFalse(state.replace_button.isEnabled())

        state.search.setText("18H0 equipment socks")
        self.application.processEvents()
        self.assertEqual(state.asset_list.count(), 2)
        self.assertTrue(all(
            "Socks" in state.asset_list.item(index).text()
            for index in range(state.asset_list.count())
        ))

    def test_digit_sheet_import_resizes_every_arm_digit_and_stages_one_batch(self) -> None:
        self._ready()
        sheet = self.root / "arm-digits-4x.png"
        image = Image.new("RGBA", (1280, 128), (0, 0, 0, 0))
        for digit in range(10):
            image.paste(
                (digit * 20, 255 - digit * 20, digit, 255),
                (digit * 128, 0, (digit + 1) * 128, 128),
            )
        image.save(sheet)
        imported_sizes: dict[int, tuple[int, int]] = {}

        def export_private(
            selectors: object,
            destination: Path,
            *,
            container: str,
            progress: object,
        ) -> object:
            self.assertEqual(tuple(selectors), ("18H0",))
            self.assertEqual(container, "folder")
            rows = []
            for asset in self.window.uniform_catalog.assets_for_set("18H0"):
                if asset.family != "arm" or asset.digit is None:
                    continue
                relative = f"digits/arm_{asset.digit}.png"
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGBA", (asset.width, asset.height)).save(target)
                rows.append({"asset_id": asset.asset_id, "path": relative})
            (destination / TEAM_KIT_MANIFEST).write_text(
                json.dumps({"assets": rows}), encoding="utf-8"
            )
            return SimpleNamespace(path=destination)

        def import_private(source: Path, progress: object) -> object:
            manifest = json.loads(
                (source / TEAM_KIT_MANIFEST).read_text(encoding="utf-8")
            )
            for row in manifest["assets"]:
                digit = int(Path(row["path"]).stem.rsplit("_", 1)[1])
                with Image.open(source / row["path"]) as written:
                    imported_sizes[digit] = written.size
                    self.assertEqual(
                        written.getpixel((written.width // 2, written.height // 2))[0],
                        digit * 20,
                    )
            return SimpleNamespace(changed_count=10)

        self.facade.export_team_kit_sets = export_private  # type: ignore[method-assign]
        self.facade.import_team_kit = import_private  # type: ignore[method-assign]
        receipts: list[str] = []
        with (
            mock.patch(
                "mod_editor.gui.studio_qt.QInputDialog.getItem",
                return_value=("Arm / shoulder numbers", True),
            ),
            mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getOpenFileName",
                return_value=(str(sheet), "Images"),
            ),
            mock.patch(
                "mod_editor.gui.studio_qt.QMessageBox.information",
                side_effect=lambda _parent, _title, text: receipts.append(text),
            ),
        ):
            self.window._choose_digit_sheet_import()

        expected = {
            int(asset.digit): (asset.width, asset.height)
            for asset in self.window.uniform_catalog.assets_for_set("18H0")
            if asset.family == "arm" and asset.digit is not None
        }
        self.assertEqual(imported_sizes, expected)
        self.assertTrue(self.window._workspace_dirty)
        self.assertIn("ten exact game slots", receipts[-1])

    def test_export_selected_set_and_paired_zip_use_clear_dialog_contracts(self) -> None:
        self._ready()
        info: list[str] = []
        self.window.team_kit_scope.setCurrentIndex(
            self.window.team_kit_scope.findData("SELECTED")
        )
        for index in range(self.window.uniform_list.count()):
            item = self.window.uniform_list.item(index)
            if item.data(Qt.UserRole) == "18A0":
                item.setSelected(True)
                break
        self.assertIn("+ 1 more", self.window.team_kit_scope.currentText())
        selected_folder = self.root / "selected-kit"
        with (
            mock.patch(
                "mod_editor.gui.studio_qt.QMessageBox.warning",
                return_value=QMessageBox.Ok,
            ),
            mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getSaveFileName",
                return_value=(str(selected_folder), "Team Kit folder name (*)"),
            ),
            mock.patch(
                "mod_editor.gui.studio_qt.QMessageBox.information",
                side_effect=lambda _parent, _title, text: info.append(text),
            ),
        ):
            self.window._choose_team_kit_export()
        self.assertEqual(
            self.facade.calls[-1],
            ("sets", ("18H0", "18A0"), selected_folder, "folder"),
        )
        self.assertIn("replacement-only .2k5mod", info[-1])

        self.window.team_kit_scope.setCurrentIndex(
            self.window.team_kit_scope.findData("BOTH")
        )
        self.window.team_kit_container.setCurrentIndex(
            self.window.team_kit_container.findData("zip")
        )
        paired_without_suffix = self.root / "paired-kit"
        with (
            mock.patch(
                "mod_editor.gui.studio_qt.QMessageBox.warning",
                return_value=QMessageBox.Ok,
            ),
            mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getSaveFileName",
                return_value=(str(paired_without_suffix), "Team Kit ZIP (*.zip)"),
            ),
            mock.patch("mod_editor.gui.studio_qt.QMessageBox.information"),
        ):
            self.window._choose_team_kit_export()
        call = self.facade.calls[-1]
        self.assertEqual(call[0], "team")
        self.assertEqual(call[1]["asset_code"], "18")
        self.assertEqual(call[1]["variant"], 0)
        self.assertEqual(call[1]["sides"], "BOTH")
        self.assertEqual(call[1]["container"], "zip")
        self.assertEqual(call[1]["destination"], paired_without_suffix.with_suffix(".zip"))

    def test_folder_import_marks_modified_once_emits_receipt_and_enables_undo(self) -> None:
        self._ready()
        imported: list[int] = []
        receipts: list[str] = []
        self.window.team_kit_imported.connect(imported.append)
        edited = self.root / "edited-folder"
        with (
            mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getExistingDirectory",
                return_value=str(edited),
            ),
            mock.patch(
                "mod_editor.gui.studio_qt.QMessageBox.information",
                side_effect=lambda _parent, _title, text: receipts.append(text),
            ),
        ):
            self.window._choose_team_kit_import()
        self.assertEqual(self.facade.calls[-1], ("import", edited))
        self.assertEqual(imported, [2])
        self.assertTrue(self.window._workspace_dirty)
        self.assertTrue(self.window.undo_button.isEnabled())
        self.assertIn("one Undo action", receipts[-1])
        self.assertIn("source XISO was not changed", receipts[-1])
        self.assertIn("2 pending edits", self.window.edit_count.text())

    def test_unchanged_or_invalid_import_does_not_dirty_the_project(self) -> None:
        self._ready()
        edited = self.root / "unchanged-folder"
        self.facade.import_changed = 0
        emitted: list[int] = []
        self.window.team_kit_imported.connect(emitted.append)
        with (
            mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getExistingDirectory",
                return_value=str(edited),
            ),
            mock.patch("mod_editor.gui.studio_qt.QMessageBox.information"),
        ):
            self.window._choose_team_kit_import()
        self.assertEqual(emitted, [0])
        self.assertFalse(self.window._workspace_dirty)
        self.assertFalse(self.window.undo_button.isEnabled())

        self.facade.import_error = ValidationError(
            "Sleeves need an exact 128×128 RGBA PNG; no components were staged."
        )
        with mock.patch(
            "mod_editor.gui.studio_qt.QFileDialog.getExistingDirectory",
            return_value=str(edited),
        ):
            self.window._choose_team_kit_import()
        self.assertIn("no components were staged", self.errors[-1])
        self.assertFalse(self.window._workspace_dirty)
        self.assertFalse(self.window.undo_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
