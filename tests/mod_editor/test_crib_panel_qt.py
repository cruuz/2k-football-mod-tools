"""Headless, retail-free tests for the isolated PyQt5 Crib panel contract."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_crib import (
    CribAssetStatus,
    load_nfl2k5_crib_catalog,
)
from mod_editor.gui.crib_panel_qt import (
    CRIB_FINDINGS_PLAIN_TEXT,
    CallbackCribPanelHost,
    CribPanel,
    CribPanelCallbacks,
    CribPanelHost,
    PYQT5_AVAILABLE,
    VALID_STATUS_FILTERS,
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
        cls.object = cls.catalog.objects[0]
        cls.export_only_object = replace(
            cls.object, status=CribAssetStatus.EXPORT_ONLY
        )

    def test_all_498_assets_are_photo_first_and_status_filterable(self) -> None:
        result = filter_crib_assets(self.catalog.assets)
        self.assertEqual(result.catalog_total, 498)
        self.assertEqual(result.match_total, 498)
        self.assertEqual(result.editable_total, 498)
        self.assertEqual(result.export_only_total, 0)
        self.assertTrue(all(asset.editable for asset in result.assets))

        editable = filter_crib_assets(self.catalog.assets, status="editable")
        modified = filter_crib_assets(
            self.catalog.assets,
            status="modified",
            modified_asset_ids=(self.photo.asset_id,),
        )
        self.assertEqual(editable.match_total, 498)
        self.assertEqual(modified.assets, (self.photo,))
        self.assertNotIn("export_only", VALID_STATUS_FILTERS)
        with self.assertRaisesRegex(ValidationError, "Crib status filter"):
            filter_crib_assets(self.catalog.assets, status="export_only")
        with self.assertRaisesRegex(ValidationError, "Crib status filter"):
            filter_crib_assets(self.catalog.assets, status="unsafe")

    def test_panel_has_no_dead_export_only_filter_or_zero_count(self) -> None:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        host = CallbackCribPanelHost(CribPanelCallbacks(
            list_assets=lambda: self.catalog.assets,
            is_source_ready=lambda: False,
            modified_ids=lambda: (),
            preview=lambda _asset_id, _sink: Path("preview.png"),
            export=lambda _asset_id, destination, _sink: destination,
            replace=lambda _asset_id, _supplied, _sink: None,
            revert=lambda _asset_id, _sink: None,
        ))
        panel = CribPanel(host)
        labels = tuple(
            panel.status_filter.itemText(index)
            for index in range(panel.status_filter.count())
        )
        self.assertEqual(labels, ("All statuses", "Editable assets", "Modified"))
        self.assertEqual(panel.count_label.text(), "498 assets  ·  498 editable")
        self.assertNotIn("Export-only", panel.count_label.text())
        panel.close()
        app.processEvents()

    def test_search_groups_and_findings_expose_the_honest_boundary(self) -> None:
        result = filter_crib_assets(self.catalog.assets, search="bar monitor")
        self.assertEqual(result.assets, (self.screen,))
        photos = filter_crib_assets(self.catalog.assets, group="Team Photos")
        self.assertEqual(photos.match_total, 128)
        self.assertEqual(crib_group_options(self.catalog.assets)[0], "Team Photos")

        findings = CRIB_FINDINGS_PLAIN_TEXT.casefold()
        for phrase in ("498", "reflection", "ticker_src", "position-only",
                       "not supported"):
            self.assertIn(phrase, findings)

    def test_replace_and_revert_are_gated_to_proved_editable_assets(self) -> None:
        photo_clean = crib_action_state(
            self.photo, source_ready=True, busy=False, modified=False
        )
        photo_changed = crib_action_state(
            self.photo, source_ready=True, busy=False, modified=True
        )
        object_state = crib_action_state(
            self.export_only_object,
            source_ready=True,
            busy=False,
            modified=True,
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
            list_models=lambda: ({
                "scene_id": "nfl2k5.crib.o4248.c0105.scene4218",
                "scene_name": "phone",
                "shape_names": ("phone",),
                "target_count": 1,
            },),
            modified_model_ids=lambda: (
                "nfl2k5.crib.o4248.c0105.scene4218",
            ),
            export_model=lambda scene_id, destination, sink: (
                calls.append(("export_model", scene_id, destination)),
                (destination, destination.with_suffix(".bin")),
            )[-1],
            import_model=lambda scene_id, source, sink: calls.append(
                ("import_model", scene_id, source)
            ),
            revert_model=lambda scene_id, sink: calls.append(
                ("revert_model", scene_id)
            ),
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
        model = host.list_crib_model_scenes()[0]
        scene_id = str(model["scene_id"])
        self.assertEqual(host.modified_crib_model_scene_ids, (scene_id,))
        host.export_crib_model(scene_id, Path("phone.gltf"), progress)
        host.import_crib_model(scene_id, Path("edited.gltf"), progress)
        host.revert_crib_model(scene_id, progress)
        self.assertIn(("preview", self.photo.asset_id), calls)
        self.assertIn(("export", self.object.asset_id, destination), calls)
        self.assertIn(("replace", self.photo.asset_id, Path("mine.png")), calls)
        self.assertIn(("revert", self.photo.asset_id), calls)
        self.assertIn(("export_model", scene_id, Path("phone.gltf")), calls)
        self.assertIn(("import_model", scene_id, Path("edited.gltf")), calls)
        self.assertIn(("revert_model", scene_id), calls)

    def test_panel_uses_existing_pyqt5_without_starting_an_application(self) -> None:
        from PyQt5.QtWidgets import QWidget

        self.assertTrue(PYQT5_AVAILABLE)
        self.assertTrue(issubclass(CribPanel, QWidget))


if __name__ == "__main__":
    unittest.main()
