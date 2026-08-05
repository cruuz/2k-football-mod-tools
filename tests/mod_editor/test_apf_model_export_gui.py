"""Discoverable, accurately bounded APF helmet/player POSITION round trips."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio import model_export  # noqa: E402
from mod_editor.apf_studio.model_export_qt import (  # noqa: E402
    PlayerEquipmentModelExportPanel,
)


ROOT = Path(__file__).resolve().parents[2]
PRIVATE_INDEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


class ContractTests(unittest.TestCase):
    def test_release_allowlist_ships_both_model_export_modules(self) -> None:
        lines = {
            line.strip()
            for line in (ROOT / "packaging/apf2k8-release-allowlist.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue({
            "mod_editor/apf_studio/model_export.py",
            "mod_editor/apf_studio/model_export_qt.py",
            "mod_editor/apf_studio/model_import.py",
            "tools/apf_scene.py",
        } <= lines)

    def test_exact_stock_targets_are_named_with_bounded_position_import(self) -> None:
        helmet = model_export.target("helmet")
        player = model_export.target("player")
        self.assertEqual(
            (helmet.outer_index, helmet.inner_index, helmet.root_name, helmet.expected_mesh_count),
            (1310, 128, "helmet_00", 33),
        )
        self.assertEqual(
            (player.outer_index, player.inner_index, player.root_name, player.expected_mesh_count),
            (1310, 273, "player", 1),
        )
        self.assertIn("POSITION-only importer", model_export.MODEL_EXPORT_BOUNDARY)
        self.assertIn("topology changes cannot be authored", model_export.MODEL_EXPORT_BOUNDARY)

    @unittest.skipUnless(PRIVATE_INDEX.is_file(), "private APF archive is not present")
    def test_private_helmet_and_player_exports_match_the_pinned_inventory(self) -> None:
        expected = {
            "helmet": (33, 22_124, 34_874),
            "player": (1, 11_253, 16_646),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for key, counts in expected.items():
                with self.subTest(model=key):
                    receipt = model_export.export_model(
                        PRIVATE_INDEX, key, root / f"{key}.gltf"
                    )
                    self.assertEqual(
                        (receipt.mesh_count, receipt.vertex_count, receipt.triangle_count),
                        counts,
                    )
                    self.assertTrue(receipt.gltf.is_file())
                    self.assertTrue(receipt.binary.is_file())
                    document = json.loads(receipt.manifest.read_text(encoding="utf-8"))
                    self.assertTrue(document["model_import_available"])
                    self.assertEqual(
                        document["import_contract"]["operation"],
                        "same_topology_position_only",
                    )
                    self.assertEqual(document["claim_boundary"], model_export.MODEL_EXPORT_BOUNDARY)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    @staticmethod
    def _runner(*_args):
        return True

    def test_panel_is_discoverable_and_explicitly_position_only(self) -> None:
        class _Source:
            index_0a = Path("/private/game/0A")

        class _Facade:
            source_ready = True
            source = _Source()

        panel = PlayerEquipmentModelExportPanel(_Facade(), self._runner)
        try:
            self.assertEqual(set(panel.buttons), {"helmet", "player"})
            self.assertEqual(set(panel.import_buttons), {"helmet", "player"})
            self.assertTrue(all(button.isEnabled() for button in panel.buttons.values()))
            self.assertTrue(
                all(button.isEnabled() for button in panel.import_buttons.values())
            )
            self.assertIn("Same-topology POSITION-only import", panel.boundary_note.text())
            self.assertIn("topology changes cannot be authored", panel.boundary_note.text())
            self.assertIn("helmet", panel.buttons["helmet"].accessibleName().casefold())
            self.assertIn("player", panel.buttons["player"].accessibleName().casefold())
            self.assertIn(
                "position", panel.import_buttons["player"].accessibleName().casefold()
            )
        finally:
            panel.deleteLater()
            self.application.processEvents()

    def test_uniform_workspace_carries_the_model_export_tab(self) -> None:
        from mod_editor.apf_studio.gui import UniformStudioPage

        class _Facade:
            source_ready = False
            modified_asset_ids = frozenset()

        page = UniformStudioPage(_Facade(), self._runner)  # type: ignore[arg-type]
        try:
            labels = [page.tabs.tabText(index) for index in range(page.tabs.count())]
            self.assertIn("Model Round Trip", labels)
            self.assertIsInstance(page.model_export_panel, PlayerEquipmentModelExportPanel)
        finally:
            page.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
