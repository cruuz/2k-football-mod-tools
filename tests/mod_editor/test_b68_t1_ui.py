"""Fresh equipment navigation and one-PNG kit import using synthetic catalogs."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")
from PyQt5.QtWidgets import QApplication
from mod_editor.gui import studio_qt as shell
from mod_editor.core.nfl2k5_extended_visual_catalog import ExtendedVisualAsset, VisualWriterRoute
from mod_editor.core.product_catalog import ProductCategory, PRODUCT_CATEGORY_ORDER
from mod_editor.studio.session import StudioSession
from mod_editor.studio.uniform_bundle import TeamKitBundleService, TEAM_KIT_MANIFEST
from test_b661_kit_build import synthetic_catalog
from test_team_kit_bundle import _PngAssetIO, _png


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_equipment_button_builds_browser_from_fresh_window(self):
        catalog = synthetic_catalog()
        assets = tuple(ExtendedVisualAsset(f"tset:1:8:{n}:shoe", f"Equipment {n}", "Equipment",
            "uniform_equipment_texture", "18H0", 32, 32, VisualWriterRoute.UNIFIED_VISUAL,
            "nfl2k5.uniform_equipment", search_terms=("18H0", "equipment")) for n in range(45))
        extended = SimpleNamespace(assets=assets, get_asset=lambda asset_id: next(a for a in assets if a.asset_id == asset_id))
        with patch.object(shell, "load_nfl2k5_extended_visual_catalog", return_value=extended):
            window = shell.StudioMainWindow(uniform_catalog=catalog, offer_recovery=False)
            errors = []
            window._show_error = errors.append
            try:
                self.assertNotIn(ProductCategory.TEXTURES, window._visual_browsers)
                window._selected_set = catalog.uniform_sets[0]
                window._browse_selected_uniform_equipment()
                state = window._visual_browsers[ProductCategory.TEXTURES]
                self.assertEqual(state.asset_list.count(), 45)
                self.assertEqual(state.search.text(), "18H0 equipment")
                self.assertEqual(window.navigation.currentRow(), PRODUCT_CATEGORY_ORDER.index(ProductCategory.TEXTURES) + 1)
                window._browse_selected_uniform_equipment()
                self.assertIs(window._visual_browsers[ProductCategory.TEXTURES], state)
                self.assertFalse(errors)
            finally:
                window.deleteLater()
                self.app.processEvents()

    def test_one_edited_png_and_staged_baseline_are_compared_to_project(self):
        catalog = synthetic_catalog()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cache = SimpleNamespace(root=root / "cache", source=SimpleNamespace(sha256="a" * 64))
            with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
                session = StudioSession(cache, catalog, root=root / "sessions")
            service = TeamKitBundleService(catalog, session)
            asset = catalog.assets[0]
            staged = root / "staged.png"
            staged.write_bytes(_png(asset, (11, 22, 33, 255)))
            session.replace(asset, staged)
            bundle = root / "kit"
            service.export(("18H0", "18A0"), bundle)
            row = next(r for r in json.loads((bundle / TEAM_KIT_MANIFEST).read_bytes())["assets"] if r["asset_id"] == asset.asset_id)
            self.assertEqual(row["content_origin"], "user_replacement")
            png = bundle / row["path"]
            png.write_bytes(_png(asset, (44, 55, 66, 255)))
            result = service.import_edited(bundle)
            self.assertEqual((result.imported_count, result.changed_count, result.unchanged_count), (1, 1, 77))
            self.assertIn(row["path"], result.details)
            self.assertIn("Identical to the current project", result.details)
            self.assertEqual(session.current_path(asset).read_bytes(), png.read_bytes())
            repeat = service.import_edited(bundle)
            self.assertEqual((repeat.imported_count, repeat.changed_count, repeat.unchanged_count), (0, 0, 78))
            # Untouched export must preserve a later destination change.
            untouched = root / "untouched"
            service.export(("18H0",), untouched)
            session.replace(asset, staged)
            result = service.import_edited(untouched)
            self.assertEqual(result.imported_count, 0)
            self.assertEqual(next(r.decision for r in result.components if r.asset_id == asset.asset_id), "skipped_baseline")
            self.assertEqual(session.current_path(asset).read_bytes(), staged.read_bytes())


if __name__ == "__main__":
    unittest.main()
