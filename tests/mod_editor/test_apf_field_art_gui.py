"""Headless product tests for the bounded APF Field Art workspace."""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.catalog import ApfCatalog  # noqa: E402
from mod_editor.apf_studio.field_art import (  # noqa: E402
    FieldArtKind,
)
from mod_editor.apf_studio.gui import FieldArtStudioPage  # noqa: E402
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfAsset,
    ApfCategory,
    ApfStatus,
)


def _asset(
    outer_index: int,
    inner_index: int,
    name: str,
    type_name: str,
    asset_class: str,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{outer_index}:inner:{inner_index}",
        outer_index=outer_index,
        inner_index=inner_index,
        name=name,
        type_name=type_name,
        asset_class=asset_class,
        category=ApfCategory.FIELD_ART,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=1,
        outer_size=1,
        part_count=1,
    )


def _synthetic_catalog() -> ApfCatalog:
    assets: list[ApfAsset] = []
    for outer_index in range(118):
        assets.append(_asset(outer_index, 0, "endzone_l0", "TXTR", "texture"))
        if outer_index < 117:
            assets.append(
                _asset(outer_index, 1, "endzone_l1", "TXTR", "texture")
            )

    for ordinal, outer_index in enumerate(range(200, 204)):
        assets.extend(
            (
                _asset(outer_index, 0, "field", "SCNE", "scene_model_package"),
                _asset(outer_index, 1, "field_radiance", "TXTR", "texture"),
            )
        )
        if ordinal < 3:
            assets.append(_asset(outer_index, 2, "divots", "TXTR", "texture"))

    for inner_index, name in enumerate(
        (
            "divot_GrassRain",
            "divot_GrassSnow",
            "divot_GrassDry",
            "pc_field_goal",
            "Field_Pass_text",
            "Stride_number_field",
        )
    ):
        assets.append(_asset(300, inner_index, name, "TXTR", "texture"))
    for inner_index, name in enumerate(("divotb1", "field_pass01", "divota1"), 6):
        assets.append(
            _asset(300, inner_index, name, "SCNE", "scene_model_package")
        )
    assets.append(_asset(301, 0, "tc2_footballField", "SCNE", "scene_model_package"))
    assets.extend(
        (
            _asset(
                302,
                0,
                "there_is_a_penalty_onthe_field",
                "CurveAnim",
                "animation_curve",
            ),
            _asset(
                302,
                1,
                "penalty_onthe_field",
                "CurveAnim",
                "animation_curve",
            ),
        )
    )
    if len(assets) != 258:
        raise AssertionError("Synthetic Field Art inventory changed")
    return ApfCatalog(
        source_sha256="f" * 64,
        outer_count=1543,
        iff_count=1473,
        non_iff_count=70,
        inner_count=10_394,
        assets=tuple(assets),
        uniform_assets=(),
        capabilities=(),
        audio_selection_manifest=Path("synthetic-inner-selection.json"),
    )


class _Facade:
    def __init__(self, catalog: ApfCatalog, *, ready: bool = True):
        self.catalog = catalog
        self.source_ready = ready
        self.modified_asset_ids: frozenset[str] = frozenset()

    def require_catalog(self) -> ApfCatalog:
        return self.catalog

    def browse_assets(self, **kwargs: object) -> tuple[ApfAsset, ...]:
        return self.catalog.browse(**kwargs)  # type: ignore[arg-type]

    @staticmethod
    def capability_cards(_category: ApfCategory) -> tuple[object, ...]:
        return ()


def _do_not_run_tasks(*_args: object, **_kwargs: object) -> None:
    return None


class ApfFieldArtGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def _page(
        self, catalog: ApfCatalog | None = None, *, ready: bool = True
    ) -> FieldArtStudioPage:
        page = FieldArtStudioPage(
            _Facade(catalog or _synthetic_catalog(), ready=ready),  # type: ignore[arg-type]
            _do_not_run_tasks,  # type: ignore[arg-type]
        )
        page.set_context()
        self.application.processEvents()
        return page

    def test_semantic_map_and_exact_catalog_browser_ship_together(self) -> None:
        page = self._page()
        try:
            self.assertEqual(page.group_table.rowCount(), 7)
            self.assertEqual(page.group_filter.count(), 8)
            self.assertEqual(
                page.summary_label.text(),
                "258 resources  •  7 families  •  125 packages",
            )
            self.assertEqual(
                tuple(
                    page.group_table.item(row, 1).text()
                    for row in range(page.group_table.rowCount())
                ),
                ("235", "4", "4", "6", "3", "4", "2"),
            )
            self.assertIn("co-location only", page.package_note.text())
            self.assertIn("Exact asset IDs", page.package_note.text())
            self.assertEqual(len(page.browser._matches), 258)
            self.assertEqual(page.browser.result_count.text(), "258 assets")
            self.assertIn("ID: apf:outer:", page.browser.detail_metadata.text())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_family_filter_uses_reviewed_asset_ids_not_name_guessing(self) -> None:
        page = self._page()
        try:
            index = page.group_filter.findData(FieldArtKind.FIELD_SCENE.value)
            self.assertGreater(index, 0)
            page.group_filter.setCurrentIndex(index)
            self.application.processEvents()

            self.assertEqual(len(page.browser._matches), 4)
            self.assertEqual(
                {asset.name for asset in page.browser._matches}, {"field"}
            )
            self.assertEqual(
                {asset.type_name for asset in page.browser._matches}, {"SCNE"}
            )
            self.assertEqual(page.browser.result_count.text(), "4 assets")
            self.assertIn("4 records across 4 archive packages", page.group_note.text())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_replace_and_revert_are_visible_but_explicitly_locked(self) -> None:
        page = self._page()
        try:
            self.assertFalse(page.browser.replace_button.isHidden())
            self.assertFalse(page.browser.revert_button.isHidden())
            self.assertFalse(page.browser.replace_button.isEnabled())
            self.assertFalse(page.browser.revert_button.isEnabled())
            self.assertEqual(page.browser.replace_button.text(), "Replace locked")
            self.assertEqual(page.browser.revert_button.text(), "Revert locked")
            self.assertIn("runtime field material", page.browser.detail_notes.text())
            self.assertIn("no bounded Field Art writer", page.browser.replace_button.toolTip())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_semantic_contract_drift_fails_closed_but_raw_rows_stay_visible(self) -> None:
        catalog = _synthetic_catalog()
        drifted = replace(catalog, assets=catalog.assets[:-1])
        page = self._page(drifted)
        try:
            self.assertIsNone(page.inventory)
            self.assertEqual(page.group_table.rowCount(), 0)
            self.assertIn("Semantic map needs review", page.summary_label.text())
            self.assertEqual(len(page.browser._matches), 257)
            self.assertFalse(page.browser.replace_button.isEnabled())
            self.assertFalse(page.browser.revert_button.isEnabled())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_unloaded_state_preserves_the_action_lock(self) -> None:
        page = self._page(ready=False)
        try:
            self.assertEqual(page.summary_label.text(), "Load a game to map Field Art")
            self.assertEqual(page.browser.table.rowCount(), 0)
            self.assertFalse(page.browser.replace_button.isEnabled())
            self.assertFalse(page.browser.revert_button.isEnabled())
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
