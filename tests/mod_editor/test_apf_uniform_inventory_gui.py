from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.catalog import ApfCatalog  # noqa: E402
from mod_editor.apf_studio.gui import UniformStudioPage  # noqa: E402
from mod_editor.apf_studio.models import (  # noqa: E402
    ApfAsset,
    ApfCategory,
    ApfStatus,
    UniformAsset,
)


FAMILY_INNER_NAMES = {
    "jersey": "jersey_color",
    "pants": "pants_color",
    "helmet": "helmet_color",
    "shoulder": "shoulder_color",
}


def _catalog_asset(
    ordinal: int,
    *,
    name: str,
    type_name: str,
    category: ApfCategory = ApfCategory.UNIFORMS,
) -> ApfAsset:
    return ApfAsset(
        asset_id=f"apf:outer:{ordinal}:inner:0",
        outer_index=ordinal,
        inner_index=0,
        name=name,
        type_name=type_name,
        asset_class={
            "TXTR": "texture",
            "NumberFont": "font",
            "NameFont": "font",
            "SCNE": "scene_model_package",
            "AUDO": "audio",
        }[type_name],
        category=category,
        status=ApfStatus.EXPORT_ONLY,
        decoded_size=1_024 + ordinal,
        outer_size=2_048 + ordinal,
        part_count=1 if type_name in {"NumberFont", "NameFont"} else 2,
    )


def _uniform_fixture() -> tuple[tuple[UniformAsset, ...], tuple[ApfAsset, ...]]:
    typed: list[UniformAsset] = []
    catalog_rows: list[ApfAsset] = []
    dimensions = {
        "jersey": (1024, 1024),
        "pants": (512, 512),
        "helmet": (256, 1024),
        "shoulder": (1024, 1024),
    }
    ordinal = 100
    for family in ("jersey", "pants", "helmet", "shoulder"):
        width, height = dimensions[family]
        for asset_index in range(24):
            typed.append(
                UniformAsset(
                    family=family,
                    asset_index=asset_index,
                    asset_id=f"apf:uniform:{family}:{asset_index:02d}",
                    title=f"{family.title()} {asset_index:02d}",
                    width=width,
                    height=height,
                    png_contract=f"Synthetic {family} PNG contract.",
                    status=ApfStatus.EDITABLE,
                    outer_index=ordinal,
                    inner_index=0,
                    affected_teams=(f"Linked Team {asset_index:02d}",),
                    notes=("Synthetic metadata only.",),
                )
            )
            catalog_rows.append(
                _catalog_asset(
                    ordinal,
                    name=FAMILY_INNER_NAMES[family],
                    type_name="TXTR",
                )
            )
            ordinal += 1
    return tuple(typed), tuple(catalog_rows)


def _additional_fixture(start: int = 1_000) -> tuple[ApfAsset, ...]:
    rows: list[ApfAsset] = []
    for index in range(275):
        # Repeated names exercise identity-based selection and exclusion.
        name = "helmet_normal" if index < 24 else f"additional_texture_{index:03d}"
        rows.append(_catalog_asset(start + len(rows), name=name, type_name="TXTR"))
    for _index in range(24):
        rows.append(
            _catalog_asset(start + len(rows), name="uniform", type_name="NumberFont")
        )
    for _index in range(11):
        rows.append(
            _catalog_asset(start + len(rows), name="font_metric", type_name="NameFont")
        )
    rows.append(_catalog_asset(start + len(rows), name="bighelmet", type_name="SCNE"))
    rows.append(_catalog_asset(start + len(rows), name="helmet_00", type_name="SCNE"))
    if len(rows) != 312:
        raise AssertionError("synthetic additional uniform inventory changed")
    return tuple(rows)


class _UniformFacade:
    def __init__(self, *, ready: bool = True):
        typed, represented = _uniform_fixture()
        additional = _additional_fixture()
        unrelated = _catalog_asset(
            9_000,
            name="unrelated_audio",
            type_name="AUDO",
            category=ApfCategory.AUDIO,
        )
        self.catalog = ApfCatalog(
            source_sha256="d" * 64,
            outer_count=409,
            iff_count=409,
            non_iff_count=0,
            inner_count=409,
            assets=represented + additional + (unrelated,),
            uniform_assets=typed,
            capabilities=(),
            audio_selection_manifest=Path("synthetic-inner-selection.json"),
        )
        self.source_ready = ready
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.export_calls: list[tuple[str, Path]] = []

    def require_catalog(self) -> ApfCatalog:
        return self.catalog

    def uniform_assets(self, family: str | None = None) -> tuple[UniformAsset, ...]:
        values = self.catalog.uniform_assets
        return values if family is None else tuple(
            item for item in values if item.family == family
        )

    def capability_cards(self, _category: ApfCategory) -> tuple[object, ...]:
        return ()

    def browse_assets(self, **kwargs: object) -> tuple[ApfAsset, ...]:
        return self.catalog.browse(**kwargs)  # type: ignore[arg-type]

    def export_asset(
        self, asset_id: str, destination: Path, _progress: object
    ) -> Path:
        self.export_calls.append((asset_id, destination))
        destination.write_bytes(b"synthetic local export")
        return destination


def _do_not_run_tasks(*_args: object, **_kwargs: object) -> None:
    return None


def _run_task_now(
    _title: str,
    operation: object,
    complete: object,
    _blocking: bool,
) -> None:
    result = operation(lambda *_progress: None)  # type: ignore[operator]
    complete(result)  # type: ignore[operator]


class ApfUniformInventoryGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.application.quit()
        sip.delete(cls.application)
        cls.application = None

    def _page(self, *, ready: bool = True) -> tuple[_UniformFacade, UniformStudioPage]:
        facade = _UniformFacade(ready=ready)
        page = UniformStudioPage(
            facade,  # type: ignore[arg-type]
            _do_not_run_tasks,  # type: ignore[arg-type]
        )
        page.set_context()
        self.application.processEvents()
        return facade, page

    def test_page_partitions_all_408_records_without_duplicate_coordinates(self) -> None:
        facade, page = self._page()
        try:
            self.assertEqual(page.tabs.count(), 2)
            self.assertEqual(page.tabs.tabText(0), "Editable Materials (96)")
            self.assertEqual(page.tabs.tabText(1), "Additional Assets (312)")
            self.assertEqual(page.tabs.objectName(), "workspaceTabs")
            self.assertEqual(page.list.count(), 96)
            self.assertEqual(len(page.inventory_browser._matches), 312)
            self.assertEqual(page.inventory_browser.table.rowCount(), 100)
            self.assertEqual(page.inventory_browser.result_count.text(), "312 assets")
            self.assertEqual(page.inventory_browser.page_label.text(), "Page 1 of 4")
            self.assertIn("408 indexed", page.inventory_summary.text())
            self.assertIn("96 safely editable", page.inventory_summary.text())

            editable_coordinates = {
                (item.outer_index, item.inner_index)
                for item in facade.catalog.uniform_assets
            }
            additional_coordinates = {
                (item.outer_index, item.inner_index)
                for item in page.inventory_browser._matches
            }
            all_uniform_coordinates = {
                (item.outer_index, item.inner_index)
                for item in facade.catalog.browse(
                    category=ApfCategory.UNIFORMS,
                    limit=len(facade.catalog.assets) + 1,
                )
            }
            self.assertTrue(editable_coordinates.isdisjoint(additional_coordinates))
            self.assertEqual(
                editable_coordinates | additional_coordinates,
                all_uniform_coordinates,
            )
            self.assertEqual(len(all_uniform_coordinates), 408)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_additional_inventory_has_scoped_types_and_exact_paging(self) -> None:
        _facade, page = self._page()
        browser = page.inventory_browser
        try:
            available_types = {
                browser.type_filter.itemData(index)
                for index in range(1, browser.type_filter.count())
            }
            self.assertEqual(
                available_types,
                {"TXTR", "NumberFont", "NameFont", "SCNE"},
            )
            self.assertNotIn("AUDO", available_types)
            for type_name, expected in (
                ("TXTR", 275),
                ("NumberFont", 24),
                ("NameFont", 11),
                ("SCNE", 2),
            ):
                browser.type_filter.setCurrentIndex(
                    browser.type_filter.findData(type_name)
                )
                browser._filter_timer.stop()
                browser.refresh()
                self.assertEqual(len(browser._matches), expected)

            browser.type_filter.setCurrentIndex(0)
            browser._filter_timer.stop()
            browser.refresh()
            browser._change_page(1)
            browser._change_page(1)
            browser._change_page(1)
            self.assertEqual(browser.page_label.text(), "Page 4 of 4")
            self.assertEqual(browser.table.rowCount(), 12)
            self.assertTrue(browser.previous_button.isEnabled())
            self.assertFalse(browser.next_button.isEnabled())
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_duplicate_names_restore_the_selected_asset_by_exact_id(self) -> None:
        _facade, page = self._page()
        browser = page.inventory_browser
        try:
            browser.search.setText("helmet_normal")
            browser._filter_timer.stop()
            browser.refresh()
            self.assertEqual(browser.table.rowCount(), 24)
            browser.table.selectRow(10)
            selected = browser._selected_asset()
            self.assertIsNotNone(selected)
            assert selected is not None
            selected_id = selected.asset_id
            browser.refresh()
            restored = browser._selected_asset()
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(restored.asset_id, selected_id)
            self.assertEqual(restored.name, "helmet_normal")
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_specialist_filters_and_additional_browser_state_are_independent(self) -> None:
        _facade, page = self._page()
        browser = page.inventory_browser
        modified_events: list[str] = []
        page.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            page.tabs.setCurrentIndex(1)
            browser._change_page(1)
            self.assertEqual(browser._page, 1)
            page.tabs.setCurrentIndex(0)
            page.family_filter.setCurrentIndex(page.family_filter.findData("jersey"))
            self.assertEqual(page.list.count(), 24)
            page.search.setText("Jersey 03")
            self.assertEqual(page.list.count(), 1)
            self.assertEqual(browser._page, 1)
            self.assertEqual(modified_events, [])

            page._mutation_complete("apf:uniform:jersey:03")
            self.assertEqual(modified_events, ["modified"])
            self.assertEqual(browser._page, 1)
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_additional_export_is_nonmutating_and_never_unlocks_replace(self) -> None:
        facade, page = self._page()
        browser = page.inventory_browser
        modified_events: list[str] = []
        page.modifiedChanged.connect(lambda: modified_events.append("modified"))
        try:
            page.tabs.setCurrentIndex(1)
            browser.table.selectRow(0)
            self.application.processEvents()
            selected = browser._selected_asset()
            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected.type_name, "TXTR")
            self.assertTrue(browser.replace_button.isHidden())
            self.assertTrue(browser.revert_button.isHidden())
            browser.run_task = _run_task_now  # type: ignore[assignment]
            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "helmet-normal.png"
                with (
                    patch(
                        "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                        return_value=(str(destination), "PNG preview (*.png)"),
                    ),
                    patch(
                        "mod_editor.apf_studio.gui.QMessageBox.information",
                        return_value=0,
                    ),
                ):
                    browser._export_selected()
                self.assertEqual(facade.export_calls, [(selected.asset_id, destination)])
                self.assertEqual(destination.read_bytes(), b"synthetic local export")
            self.assertEqual(modified_events, [])
        finally:
            page.deleteLater()
            self.application.processEvents()

    def test_unloaded_page_keeps_both_workspaces_safe_and_empty(self) -> None:
        _facade, page = self._page(ready=False)
        try:
            self.assertEqual(page.tabs.count(), 2)
            self.assertEqual(page.tabs.tabText(0), "Editable Materials (96)")
            self.assertEqual(page.tabs.tabText(1), "Additional Assets")
            self.assertEqual(page.list.count(), 0)
            self.assertEqual(page.inventory_browser.table.rowCount(), 0)
            self.assertEqual(page.inventory_browser.page_label.text(), "Page 0 of 0")
            self.assertFalse(page.export_button.isEnabled())
            self.assertFalse(page.replace_button.isEnabled())
            self.assertFalse(page.revert_button.isEnabled())
            self.assertFalse(page.inventory_browser.export_button.isEnabled())
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
