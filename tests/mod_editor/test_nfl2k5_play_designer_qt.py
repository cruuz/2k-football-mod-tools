"""Offscreen smoke tests for the Formation / Play Designer dialogs (private cache required)."""
import os
import pathlib
import struct
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

INDEX = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0")
INVENTORY = pathlib.Path("/home/noah/.cache/2k5-mod-studio/7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9/indexes/nfl2k5_resource_chunks_v2.json")
ATL = "nfl2k5.resource.o0308.c0000.k504c4159"


def _has_cache() -> bool:
    return INDEX.exists() and INVENTORY.exists()


def _load_atl():
    import sys
    from mod_editor.core.nfl2k5_universal_asset_index import Nfl2k5UniversalAssetIndex
    from mod_editor.core import nfl2k5_playbook_inspector as insp
    sys.path.insert(0, "tools")
    from nfl_outer import read_entry_range
    index = Nfl2k5UniversalAssetIndex(INVENTORY, INDEX, INVENTORY.parent / "universal-assets-v1.sqlite3")
    record = index.get(ATL)
    raw = read_entry_range(index.archive, index.archive.entries[record.outer_index], record.chunk_offset, record.raw_size)
    return insp.parse_playbook_resource(raw, asset_id=ATL), raw[0x20:]


@unittest.skipUnless(_has_cache(), "private 2K5 cache missing")
class DesignerDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.book, cls.body = _load_atl()

    def test_formation_designer_pistol_is_legal_and_stages(self):
        from mod_editor.gui.play_designer_qt import PRESETS, FormationDesignerDialog
        dialog = FormationDesignerDialog(self.book, self.body, 10)
        dialog._apply_preset(PRESETS["Pistol (QB 4 yd, HB 7 yd behind)"])
        self.assertEqual(dialog._issues, [])
        dialog.name_edit.setText("Pistol Ace")
        dialog._accept()
        payload = dialog.result_payload
        self.assertEqual(payload["custom_name"], "Pistol Ace")
        self.assertEqual(payload["slot_positions"][0], [0, -366])
        self.assertEqual(payload["slot_positions"][10], [0, -640])

    def test_formation_designer_flags_illegal_alignment(self):
        from mod_editor.gui.play_designer_qt import FormationDesignerDialog
        dialog = FormationDesignerDialog(self.book, self.body, 10)
        dialog.positions[6] = [-457.0, -200.0]  # pull a lineman-side WR off the line: only 6 on the LOS
        dialog._refresh_legality()
        self.assertTrue(any("line of scrimmage" in issue for issue in dialog._issues))

    def test_play_designer_routes_validate_and_stage(self):
        from mod_editor.gui.play_designer_qt import ROUTE_RECIPES, PlayDesignerDialog
        dialog = PlayDesignerDialog(self.book, self.body, 10, 141)
        dialog.slot_list.setCurrentRow(6)
        dialog._apply_recipe(ROUTE_RECIPES[1], 8)
        self.assertIsNone(dialog._validate())
        dialog.name_edit.setText("Test Slant")
        dialog._accept()
        payload = dialog.result_payload
        self.assertEqual([i for i, a in enumerate(payload["assignments"]) if a], [6])
        self.assertEqual(payload["assignments"][6][0][0], 0x01)
        self.assertEqual(payload["assignments"][6][1][0], 0x12)

    def test_play_designer_rejects_unmatched_handoff(self):
        from mod_editor.core import nfl2k5_play_codec as codec
        from mod_editor.gui.play_designer_qt import PlayDesignerDialog
        dialog = PlayDesignerDialog(self.book, self.body, 10, 141)
        dialog.slot_list.setCurrentRow(0)
        dialog.chains[0] = [codec.Node(0x01, 0, [1, 4, 0, 0, 0, 0]), codec.Node(0x03, 0, [0]), codec.Node(0x13, 0, [10, 0])]
        dialog.changed[0] = True
        self.assertIn("Handoff To", dialog._validate() or "")


if __name__ == "__main__":
    unittest.main()
