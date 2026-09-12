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


@unittest.skipUnless(QApplication is not None and (ROOT / "WIRING.md").is_file(),
                     "Protected-dialog handoff or offscreen PyQt5 is absent")
class ScopeWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.document = (ROOT / "WIRING.md").read_text()
        code = re.search(r"```python\n(.*?)\n```", cls.document, re.S).group(1)
        namespace = {"__name__": "equipment_scope_handoff"}
        exec(compile(code, "WIRING.md:equipment-dialog", "exec"), namespace)
        cls.dialog_type = namespace["EquipmentTextureImportDialog"]

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

    def test_proposed_capability_matches_the_registry_row_schema(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema is absent")
        row = json.loads(re.search(r"```json\n(.*?)\n```", self.document, re.S).group(1))
        schema = json.loads((ROOT / "mod_editor/capabilities/registry.schema.json").read_text())
        Draft202012Validator({"$ref": "#/$defs/capability", "$defs": schema["$defs"]}).validate(row)


if __name__ == "__main__":
    unittest.main()
