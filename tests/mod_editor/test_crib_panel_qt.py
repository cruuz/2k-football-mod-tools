"""Headless, retail-free tests for the isolated PyQt5 Crib panel contract."""

from __future__ import annotations

from pathlib import Path
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_crib import load_nfl2k5_crib_catalog
from mod_editor.gui.crib_panel_qt import (
    CRIB_FINDINGS_PLAIN_TEXT,
    CallbackCribPanelHost,
    CribPanel,
    CribPanelCallbacks,
    CribPanelHost,
    PYQT5_AVAILABLE,
    crib_action_state,
    crib_group_options,
    filter_crib_assets,
)


class CribPanelViewModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_nfl2k5_crib_catalog()
        cls.photo = cls.catalog.photos[0]
        cls.screen = cls.catalog.by_selector("crib_scene_texture:room:22")
        cls.object = next(asset for asset in cls.catalog.objects if not asset.editable)

    def test_all_498_assets_are_photo_first_and_status_filterable(self) -> None:
        result = filter_crib_assets(self.catalog.assets)
        self.assertEqual(result.catalog_total, 498)
        self.assertEqual(result.match_total, 498)
        self.assertEqual(result.editable_total, 129)
        self.assertEqual(result.export_only_total, 369)
        self.assertTrue(all(asset.editable for asset in result.assets[:129]))
        self.assertTrue(all(not asset.editable for asset in result.assets[129:]))

        editable = filter_crib_assets(self.catalog.assets, status="editable")
        export_only = filter_crib_assets(self.catalog.assets, status="export_only")
        modified = filter_crib_assets(
            self.catalog.assets,
            status="modified",
            modified_asset_ids=(self.photo.asset_id,),
        )
        self.assertEqual(editable.match_total, 129)
        self.assertEqual(export_only.match_total, 369)
        self.assertEqual(modified.assets, (self.photo,))
        with self.assertRaisesRegex(ValidationError, "Crib status filter"):
            filter_crib_assets(self.catalog.assets, status="unsafe")

    def test_search_groups_and_findings_expose_the_honest_boundary(self) -> None:
        result = filter_crib_assets(self.catalog.assets, search="bar monitor")
        self.assertEqual(result.assets, (self.screen,))
        photos = filter_crib_assets(self.catalog.assets, group="Team Photos")
        self.assertEqual(photos.match_total, 128)
        self.assertEqual(crib_group_options(self.catalog.assets)[0], "Team Photos")

        findings = CRIB_FINDINGS_PLAIN_TEXT.casefold()
        for phrase in ("bar_monitor", "screen_crib", "ps5", "coming soon", "silhouette"):
            self.assertIn(phrase, findings)

    def test_replace_and_revert_are_gated_to_proved_editable_assets(self) -> None:
        photo_clean = crib_action_state(
            self.photo, source_ready=True, busy=False, modified=False
        )
        photo_changed = crib_action_state(
            self.photo, source_ready=True, busy=False, modified=True
        )
        object_state = crib_action_state(
            self.object, source_ready=True, busy=False, modified=True
        )
        screen_state = crib_action_state(
            self.screen, source_ready=True, busy=False, modified=True
        )
        waiting = crib_action_state(
            self.photo, source_ready=False, busy=False, modified=True
        )
        self.assertTrue(photo_clean.can_preview)
        self.assertTrue(photo_clean.can_export)
        self.assertTrue(photo_clean.can_replace)
        self.assertFalse(photo_clean.can_revert)
        self.assertTrue(photo_changed.can_revert)
        self.assertTrue(object_state.can_preview)
        self.assertTrue(object_state.can_export)
        self.assertFalse(object_state.can_replace)
        self.assertFalse(object_state.can_revert)
        self.assertTrue(screen_state.can_replace)
        self.assertTrue(screen_state.can_revert)
        self.assertEqual(
            waiting,
            type(waiting)(False, False, False, False, False),
        )

    def test_callback_adapter_is_the_complete_small_host_protocol(self) -> None:
        calls: list[tuple[object, ...]] = []

        def progress(stage: str, completed: int, total: int) -> None:
            calls.append(("progress", stage, completed, total))

        callbacks = CribPanelCallbacks(
            list_assets=lambda: (self.photo, self.object),
            is_source_ready=lambda: True,
            modified_ids=lambda: (self.photo.asset_id,),
            preview=lambda asset_id, sink: (
                sink("preview", 1, 1), calls.append(("preview", asset_id)),
                Path("preview.png"),
            )[-1],
            export=lambda asset_id, destination, sink: (
                sink("export", 1, 1),
                calls.append(("export", asset_id, destination)),
                destination,
            )[-1],
            replace=lambda asset_id, supplied, sink: calls.append(
                ("replace", asset_id, supplied)
            ),
            revert=lambda asset_id, sink: calls.append(("revert", asset_id)),
        )
        host = CallbackCribPanelHost(callbacks)
        self.assertIsInstance(host, CribPanelHost)
        self.assertTrue(host.source_ready)
        self.assertEqual(host.modified_crib_asset_ids, (self.photo.asset_id,))
        self.assertEqual(host.list_crib_assets(), (self.photo, self.object))
        self.assertEqual(
            host.preview_crib_asset(self.photo.asset_id, progress),
            Path("preview.png"),
        )
        destination = Path("export.png")
        self.assertEqual(
            host.export_crib_asset(self.object.asset_id, destination, progress),
            destination,
        )
        host.replace_crib_photo(self.photo.asset_id, Path("mine.png"), progress)
        host.revert_crib_photo(self.photo.asset_id, progress)
        self.assertIn(("preview", self.photo.asset_id), calls)
        self.assertIn(("export", self.object.asset_id, destination), calls)
        self.assertIn(("replace", self.photo.asset_id, Path("mine.png")), calls)
        self.assertIn(("revert", self.photo.asset_id), calls)

    def test_panel_uses_existing_pyqt5_without_starting_an_application(self) -> None:
        from PyQt5.QtWidgets import QWidget

        self.assertTrue(PYQT5_AVAILABLE)
        self.assertTrue(issubclass(CribPanel, QWidget))


if __name__ == "__main__":
    unittest.main()
