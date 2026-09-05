"""Retail-free model, facade, and offscreen wiring tests for product inspectors."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QLabel, QWidget

from mod_editor.core.errors import ValidationError
from mod_editor.core.product_catalog import ProductCategory
from mod_editor.gui.gameplay_panel_qt import (
    GameplayPanel,
    GameplayPanelHost,
    build_gameplay_inspection_model,
)
from mod_editor.gui.menus_panel_qt import (
    MenusPanel,
    MenusPanelHost,
    build_main_menu_inspection_model,
)
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
import mod_editor.studio.facade as facade_module
from mod_editor.studio.facade import (
    Nfl2k5StudioFacade,
    collect_nfl2k5_gameplay_inspection,
    collect_nfl2k5_main_menu_inspection,
)


class _InspectionHost:
    source_ready = False

    def __init__(self, root: Path) -> None:
        self.root = root
        self.gameplay_exports: list[tuple[Path, str]] = []
        self.menu_exports: list[tuple[Path, str]] = []

    def inspect_gameplay(self, progress: object) -> object:
        progress("Synthetic gameplay ready", 1, 1)
        return collect_nfl2k5_gameplay_inspection()

    def export_gameplay_inspection(
        self, destination: Path, export_format: str, progress: object
    ) -> Path:
        self.gameplay_exports.append((destination, export_format))
        destination.write_text("synthetic", encoding="utf-8")
        progress("Synthetic gameplay exported", 1, 1)
        return destination

    def inspect_main_menu(self, progress: object) -> object:
        progress("Synthetic menu ready", 1, 1)
        return collect_nfl2k5_main_menu_inspection()

    def export_main_menu_inspection(
        self, destination: Path, export_format: str, progress: object
    ) -> Path:
        self.menu_exports.append((destination, export_format))
        destination.write_text("synthetic", encoding="utf-8")
        progress("Synthetic menu exported", 1, 1)
        return destination


class ProductInspectionModelTests(unittest.TestCase):
    def test_gameplay_model_exposes_exact_rows_and_honest_boundaries(self) -> None:
        model = build_gameplay_inspection_model(
            collect_nfl2k5_gameplay_inspection()
        )
        self.assertEqual(len(model.sliders), 21)
        self.assertEqual(len(model.draft_weights), 17)
        self.assertEqual(len(model.save_containers), 8)
        self.assertEqual(len(model.franchise_findings), 5)
        self.assertIn("signed-executable", model.draft_warning)
        self.assertIn("safe writer: Not available", model.integrity_summary)

    def test_gameplay_model_rejects_a_partial_table_instead_of_overclaiming(self) -> None:
        snapshot = collect_nfl2k5_gameplay_inspection()
        sliders = dict(snapshot["sliders"])
        sliders["sliders"] = list(sliders["sliders"])[1:]
        snapshot["sliders"] = sliders
        with self.assertRaisesRegex(ValidationError, "Expected 21"):
            build_gameplay_inspection_model(snapshot)
        self.assertEqual(
            len(collect_nfl2k5_gameplay_inspection()["sliders"]["sliders"]), 21
        )

    def test_sanitized_snapshots_work_when_private_research_reports_do_not_ship(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inspection-snapshot-") as temporary:
            missing = Path(temporary)
            facade_module._verified_gameplay_snapshot.cache_clear()
            facade_module._verified_menu_snapshot.cache_clear()
            with patch.multiple(
                facade_module,
                DEFAULT_TUNING_REPORT=missing / "tuning.json",
                DEFAULT_FRANCHISE_REPORT=missing / "franchise.json",
                DEFAULT_NFL_SAVE_REPORT=missing / "saves.json",
                DEFAULT_PS2_FIXTURE_REPORT=missing / "ps2.json",
                DEFAULT_MENU_REPORT_DIR=missing / "menus",
            ):
                gameplay = collect_nfl2k5_gameplay_inspection()
                menu = collect_nfl2k5_main_menu_inspection()
            facade_module._verified_gameplay_snapshot.cache_clear()
            facade_module._verified_menu_snapshot.cache_clear()
        self.assertEqual(gameplay["sliders"]["slider_count"], 21)
        self.assertEqual(len(menu["state"]["rows"]), 7)

    def test_menu_model_exposes_named_transitions_layouts_and_blockers(self) -> None:
        model = build_main_menu_inspection_model(
            collect_nfl2k5_main_menu_inspection()
        )
        self.assertEqual(len(model.transitions), 7)
        self.assertEqual(model.initial_selection, "Quick Game")
        self.assertTrue(all(row.initially_drawable for row in model.transitions))
        self.assertEqual(len(model.layouts), 2)
        self.assertEqual(len(model.blockers), 3)
        self.assertEqual(model.cold_boot_reachability, "unproved")

    def test_facade_json_csv_exports_are_sanitized_and_non_overwriting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inspection-export-") as temporary:
            root = Path(temporary)
            facade = Nfl2k5StudioFacade(
                uniform_catalog=object(),  # type: ignore[arg-type]
                visual_catalog=object(),  # type: ignore[arg-type]
                xemu_command=(),
            )
            progress = lambda *_args: None
            gameplay_json = facade.export_gameplay_inspection(
                root / "gameplay.json", "json", progress
            )
            gameplay_value = json.loads(gameplay_json.read_text(encoding="utf-8"))
            self.assertTrue(gameplay_value["read_only"])
            self.assertEqual(gameplay_value["sliders"]["slider_count"], 21)
            self.assertEqual(
                gameplay_value["fantasy_draft"]["position_weight_count"], 17
            )
            gameplay_csv = facade.export_gameplay_inspection(
                root / "gameplay.csv", "csv", progress
            ).read_text(encoding="utf-8")
            self.assertIn("fantasy_draft_weight", gameplay_csv)
            self.assertIn("Fantasy Draft only", gameplay_csv)

            menu_json = facade.export_main_menu_inspection(
                root / "menu.json", "json", progress
            )
            self.assertEqual(
                len(json.loads(menu_json.read_text(encoding="utf-8"))["state"]["rows"]),
                7,
            )
            menu_csv = facade.export_main_menu_inspection(
                root / "menu.csv", "csv", progress
            ).read_text(encoding="utf-8")
            self.assertIn("main_menu_transition", menu_csv)
            self.assertIn("known_blocker", menu_csv)

            with self.assertRaisesRegex(ValidationError, "already exists"):
                facade.export_main_menu_inspection(
                    root / "menu.csv", "csv", progress
                )
            with self.assertRaisesRegex(ValidationError, "JSON or CSV"):
                facade.export_gameplay_inspection(
                    root / "bad.txt", "yaml", progress
                )


class ProductInspectionOffscreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_isolated_panels_populate_and_keep_limitations_visible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="inspection-panel-") as temporary:
            host = _InspectionHost(Path(temporary))
            self.assertIsInstance(host, GameplayPanelHost)
            self.assertIsInstance(host, MenusPanelHost)

            capability = QLabel("Capability limitation witness")
            gameplay = GameplayPanel(host, capability_page=capability)
            self.application.processEvents()
            self.assertEqual(gameplay.slider_table.rowCount(), 21)
            self.assertEqual(gameplay.draft_table.rowCount(), 17)
            self.assertEqual(gameplay.save_table.rowCount(), 8)
            self.assertEqual(gameplay.franchise_table.rowCount(), 5)
            # the three research tables sit under one Reference (read-only) tab; the
            # capability cards stay one click away as What's possible
            self.assertEqual(gameplay.tabs.count(), 2)
            self.assertEqual(gameplay.tabs.tabText(0), "Reference (read-only)")
            self.assertEqual(gameplay.tabs.tabText(1), "What's possible")
            self.assertEqual(gameplay.reference_tabs.count(), 3)
            self.assertEqual(gameplay.reference_tabs.tabText(2), "Saves && Franchise")
            self.assertIn(
                "not the separate Franchise rookie-draft scorer",
                gameplay.reference_tabs.widget(1).findChildren(QLabel)[1].text(),
            )
            even = gameplay.slider_table.item(0, 1)
            odd = gameplay.slider_table.item(1, 1)
            self.assertEqual(even.background().color().name(), "#101827")
            self.assertEqual(odd.background().color().name(), "#17243a")
            self.assertEqual(even.foreground().color().name(), "#e7edf7")
            self.assertEqual(even.toolTip(), even.text())
            self.assertEqual(odd.toolTip(), odd.text())
            table_style = gameplay.styleSheet()
            self.assertIn("alternate-background-color: #17243a", table_style)
            self.assertIn("QTableWidget::item:selected", table_style)
            self.assertIn("QHeaderView::section", table_style)

            raw = QLabel("Universal raw fallback")
            menu_capability = QLabel("Menu capability limitations")
            menus = MenusPanel(
                host, raw_fallback=raw, capability_page=menu_capability
            )
            self.application.processEvents()
            self.assertEqual(menus.transition_table.rowCount(), 7)
            self.assertEqual(menus.layout_table.rowCount(), 2)
            self.assertIs(menus.tabs.widget(1), raw)
            self.assertIs(menus.tabs.widget(2), menu_capability)
            self.assertEqual(menus.tabs.tabText(2), "What's possible")
            self.assertIn("cold-boot reachability: unproved", menus.state_summary.text())
            transition_even = menus.transition_table.item(0, 1)
            transition_odd = menus.transition_table.item(1, 1)
            layout_even = menus.layout_table.item(0, 0)
            layout_odd = menus.layout_table.item(1, 0)
            self.assertEqual(transition_even.background().color().name(), "#101827")
            self.assertEqual(transition_odd.background().color().name(), "#17243a")
            self.assertEqual(layout_even.background().color().name(), "#101827")
            self.assertEqual(layout_odd.background().color().name(), "#17243a")
            for item in (transition_even, transition_odd, layout_even, layout_odd):
                self.assertEqual(item.foreground().color().name(), "#e7edf7")
                self.assertEqual(item.toolTip(), item.text())
            menu_table_style = menus.styleSheet()
            self.assertIn("alternate-background-color: #17243a", menu_table_style)
            self.assertIn("gridline-color: #33445f", menu_table_style)
            self.assertIn("QTableWidget::item:selected", menu_table_style)
            self.assertIn("QHeaderView::section", menu_table_style)
            self.assertGreaterEqual(menus.status_label.minimumHeight(), 30)
            self.assertTrue(menus.status_label.wordWrap())
            self.assertEqual(menus.status_label.toolTip(), menus.status_label.text())
            self.assertIn("Named map ready", menus.status_label.text())

            gameplay.deleteLater()
            menus.deleteLater()
            self.application.processEvents()

    def test_flagship_mounts_both_inspectors_and_preserves_raw_fallback(self) -> None:
        window = StudioMainWindow(facade=BrowseOnlyFacade())
        self.application.processEvents()
        gameplay = window._category_pages[ProductCategory.SLIDERS_GAMEPLAY]
        menus = window._category_pages[ProductCategory.MENUS_UI]
        self.assertIsInstance(gameplay, GameplayPanel)
        self.assertIsInstance(menus, MenusPanel)
        self.assertEqual(gameplay.slider_table.rowCount(), 21)
        self.assertEqual(gameplay.draft_table.rowCount(), 17)
        self.assertEqual(menus.transition_table.rowCount(), 7)
        self.assertIsNotNone(window._universal_browser)
        self.assertIs(menus.tabs.widget(1), window._universal_browser.search.parentWidget().parentWidget())
        window.deleteLater()
        self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
