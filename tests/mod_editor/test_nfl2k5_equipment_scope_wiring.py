"""Exercise the exact protected-dialog handoff without editing the protected file."""

import json
import os
from pathlib import Path
import re
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt5.QtWidgets import QApplication, QLabel
except ImportError:
    QApplication = None


# Integration: the WIRING.md handoff has been applied to the protected GUI file and the
# capability registry, so these now exercise the shipped dialog and the shipped row instead
# of the proposal document. WIRING.md itself was renamed to WIRING_B68_T2.md on merge.
@unittest.skipUnless(QApplication is not None, "offscreen PyQt5 is absent")
class ScopeWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from mod_editor.gui.equipment_texture_import_dialog import EquipmentTextureImportDialog

        cls.dialog_type = EquipmentTextureImportDialog

    def test_global_shoes_offer_only_all_teams_and_the_refusal_sentence(self):
        from mod_editor.core.nfl2k5_equipment_import import GLOBAL_RULE

        for asset_id in ("tset:3850:8:0:shoes01", "tset:3850:8:1:shoes01_mud",
                         "tset:3850:9:0:shoes02", "tset:3850:6:0:glove01"):
            dialog = self.dialog_type(SimpleNamespace(asset_id=asset_id, label="Equipment", width=256, height=256))
            try:
                self.assertEqual(dialog.import_scope.count(), 1)
                self.assertEqual(dialog.import_scope.currentText(), "All teams")
                self.assertEqual(dialog.scope, "all-teams")
                self.assertEqual(dialog.findChild(QLabel, "equipmentScopeExplanation").text(), GLOBAL_RULE)
            finally:
                dialog.close()

    def test_local_shoes_and_socks_offer_selected_package_and_full_size_art(self):
        for asset_id in ("tset:3850:8:4:shoes09", "tset:3850:9:4:shoes10", "tset:3850:4:0:socks00"):
            dialog = self.dialog_type(SimpleNamespace(asset_id=asset_id, label="Equipment", width=64, height=64))
            try:
                self.assertEqual(dialog.import_scope.count(), 1)
                self.assertEqual(dialog.scope, "selected-package")
                self.assertTrue(dialog.independent)
                self.assertEqual(dialog.scale, 1)
            finally:
                dialog.close()

    def test_integrated_capability_matches_the_registry_row_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is absent")
        registry = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json").read_text())
        rows = [row for row in registry["capabilities"] if row["id"] == "nfl2k5.uniforms.bump_textures"]
        self.assertEqual(len(rows), 1, "the integrated bump/shoe-relief capability row is absent")
        schema = json.loads((ROOT / "mod_editor/capabilities/registry.schema.json").read_text())
        Draft202012Validator({"$ref": "#/$defs/capability", "$defs": schema["$defs"]}).validate(rows[0])


if __name__ == "__main__":
    unittest.main()
