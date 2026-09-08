"""Equipment choice survives preflight, save/reopen, replacement and Undo."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_nfl2k5_equipment_texture_chain import Fixture, artwork
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_equipment_import import stage_equipment_import
from mod_editor.core.nfl2k5_equipment_import_intent import OWN_TEXTURE, PALETTE_ONLY, import_mode, with_import_mode
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.studio.session import StudioSession
from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import encode_rgba_png, texture_to_rgba


class EquipmentSessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="equipment-session-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.f = Fixture(self.root)
        self.cache = SimpleNamespace(root=self.root / "cache", pack0=self.root / "0",
                                     source=SimpleNamespace(sha256="a" * 64))
        self.assets = {}
        for row in self.f.rows:
            asset = SimpleNamespace(asset_id=row.asset_id, width=row.width, height=row.height,
                                    dimensions=(row.width, row.height), kind="uniform_equipment_texture",
                                    label=row.name, editable=True,
                                    provider_edit=lambda path, target=row.asset_id: {
                                        "kind": "uniform_equipment_texture", "asset_id": target, "png": str(path),
                                    })
            self.assets[asset.asset_id] = asset
        self.catalog = SimpleNamespace(get_asset=lambda asset_id: self.assets[asset_id])
        textures, _ = writer._validate_layout(self.f.decoded, self.f.chunk, self.f.rows)
        originals = {row.asset_id: texture_to_rgba(self.f.decoded, self.f.chunk, textures[row.reference_index])
                     for row in self.f.rows}
        original_dir = self.root / "originals"
        original_dir.mkdir()

        class AssetIO:
            def __init__(self, cache):
                pass

            def ensure_original(self, asset):
                path = original_dir / f"{asset.label}.png"
                if not path.exists():
                    path.write_bytes(encode_rgba_png(asset.width, asset.height, originals[asset.asset_id]))
                return path

            def validate_replacement(self, asset, path):
                payload = Path(path).read_bytes()
                _, _, rgba = decode_rgba_png(payload, asset.dimensions)
                import_mode(payload, asset.asset_id, rgba)
                return payload, rgba

        self.asset_io_type = AssetIO
        self.a = self.session("a")
        self.asset = self.assets[self.f.rows[0].asset_id]

    def session(self, name):
        with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", self.asset_io_type):
            result = StudioSession(self.cache, self.catalog, root=self.root / "sessions", session_id=name)
        result.attach_visual_catalog(self.catalog)
        return result

    def mode(self, session):
        payload, rgba = session.asset_io.validate_replacement(self.asset, session.current_path(self.asset))
        return import_mode(payload, self.asset.asset_id, rgba)

    def stage(self, independent=True, scale=1):
        _asset_id, path = self.f.png(independent=False)
        with self.f.context():
            return stage_equipment_import(self.a, self.asset, path, independent=independent, scale=scale)

    def test_stage_replay_save_reopen_and_undo_preserve_mode(self):
        first = self.stage()
        self.assertTrue(first.modified)
        self.assertEqual(self.mode(self.a), OWN_TEXTURE)
        before = self.a._manifest_document()
        undo = len(self.a._undo)
        again = self.stage()
        self.assertEqual(again.changed_asset_ids, ())
        self.assertEqual(before, self.a._manifest_document())
        self.assertEqual(undo, len(self.a._undo))
        path = self.root / "equipment.2k5mod"
        self.a.save_shareable_project(path)
        b = self.session("b")
        b.load_shareable_project(path)
        self.assertEqual(self.mode(b), OWN_TEXTURE)
        edit = b.canonical_document()["edits"][0]
        self.assertEqual(edit["asset_id"], self.asset.asset_id)
        self.assertEqual(Path(edit["png"]).read_bytes(), self.a.current_path(self.asset).read_bytes())
        self.a.undo()
        self.assertEqual(self.mode(self.a), PALETTE_ONLY)

    def test_same_pixels_switch_mode_and_undo_restores_previous_choice(self):
        self.stage(False)
        palette_png = self.a.current_path(self.asset).read_bytes()
        self.stage(True)
        self.assertEqual(self.mode(self.a), OWN_TEXTURE)
        self.a.undo()
        self.assertEqual(self.a.current_path(self.asset).read_bytes(), palette_png)
        self.assertEqual(self.mode(self.a), PALETTE_ONLY)

    def test_explicit_size_change_is_undoable_even_when_pixels_match(self):
        from mod_editor.core.nfl2k5_equipment_import_intent import import_settings

        self.stage(True)
        original = self.a.current_path(self.asset).read_bytes()
        result = self.stage(True, scale=2)
        self.assertEqual(result.changed_asset_ids, (self.asset.asset_id,))
        self.assertIn("16 x 16", result.message)
        payload, rgba = self.a.asset_io.validate_replacement(self.asset, self.a.current_path(self.asset))
        self.assertEqual(import_settings(payload, self.asset.asset_id, rgba), (OWN_TEXTURE, 2))
        self.a.undo()
        self.assertEqual(self.a.current_path(self.asset).read_bytes(), original)

    def test_importing_original_with_default_choice_reverts_without_compiling_a_noop(self):
        self.stage()
        with self.f.context():
            result = stage_equipment_import(self.a, self.asset, self.a.asset_io.ensure_original(self.asset))
        self.assertFalse(result.modified)
        self.assertEqual(tuple(self.a.iter_edits()), ())
        self.assertEqual(self.mode(self.a), PALETTE_ONLY)

    def test_source_pixels_with_explicit_chain_are_a_real_saved_edit(self):
        original = self.a.asset_io.ensure_original(self.asset)
        payload, rgba = self.a.asset_io.validate_replacement(self.asset, original)
        path = self.root / "same-base-new-mips.png"
        path.write_bytes(with_import_mode(payload, self.asset.asset_id, rgba, independent=True))
        self.a.replace_batch(((self.asset, path),))
        self.assertEqual(self.mode(self.a), OWN_TEXTURE)
        saved = self.root / "same-base.2k5mod"
        self.a.save_shareable_project(saved)
        b = self.session("same-base")
        b.load_shareable_project(saved)
        self.assertEqual(self.mode(b), OWN_TEXTURE)

    def test_revert_all_and_undo_keep_authored_mode_and_bytes(self):
        self.stage()
        before = self.a.current_path(self.asset).read_bytes()
        self.a.revert_all()
        self.assertEqual(self.mode(self.a), PALETTE_ONLY)
        self.a.undo()
        self.assertEqual(before, self.a.current_path(self.asset).read_bytes())
        self.assertEqual(self.mode(self.a), OWN_TEXTURE)

    def test_preflight_refusal_leaves_session_bytes_and_undo_unchanged(self):
        self.stage(False)
        before = self.a.current_path(self.asset).read_bytes()
        manifest = self.a._manifest_document()
        undo = len(self.a._undo)
        with self.f.context(), patch.object(writer, "_rebuild_grown_video", side_effect=writer.TxtrError(
            "VC-LZ stream needs more than the 1-byte bound")):
            with self.assertRaisesRegex(ValueError, "cannot fit"):
                stage_equipment_import(self.a, self.asset, self.f.png(independent=False)[1], independent=True)
        self.assertEqual(self.a.current_path(self.asset).read_bytes(), before)
        self.assertEqual(self.a._manifest_document(), manifest)
        self.assertEqual(len(self.a._undo), undo)
        self.assertFalse(any(self.a.replacements.glob("equipment-import-*")))

    def test_preflight_includes_existing_sibling_and_refuses_tampering(self):
        sibling = self.assets[self.f.rows[1].asset_id]
        self.a.replace_batch(((sibling, self.f.png(1, independent=False)[1]),))
        result = self.stage(True)
        self.assertEqual(len(result.receipt["edits"]), 2)
        self.a.current_path(sibling).write_bytes(b"foreign")
        with self.f.context(), self.assertRaisesRegex(ValidationError, "staged equipment PNG changed"):
            stage_equipment_import(self.a, self.asset, self.f.png(independent=False)[1], independent=True)

    def test_project_rejects_stale_intent_even_if_png_pixel_validation_passes(self):
        tagged = self.f.png()[1].read_bytes()
        other = self.assets[self.f.rows[1].asset_id]
        path = self.root / "wrong-variant.png"
        path.write_bytes(tagged)
        with self.assertRaisesRegex(ValidationError, "no longer matches"):
            self.a.replace_batch(((other, path),))
        self.assertEqual(tuple(self.a.iter_edits()), ())


try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.equipment_texture_import_dialog import EquipmentTextureImportDialog
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, "PyQt5 is absent; equipment dialog requires Qt")
class EquipmentDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_plain_choice_defaults_to_palette_only(self):
        asset = SimpleNamespace(asset_id="tset:0:8:0:shoes01", label="Shoe 01", width=256, height=256)
        dialog = EquipmentTextureImportDialog(asset)
        try:
            self.assertFalse(dialog.independent)
            self.assertEqual(dialog.own_texture.text(), "Give this glove or shoe its own texture")
            self.assertIn("Experimental / unwitnessed", dialog.own_texture.toolTip())
            dialog.own_texture.setChecked(True)
            self.assertTrue(dialog.independent)
            self.assertEqual(dialog.scale, 1)
            dialog.game_size.setCurrentIndex(2)
            self.assertEqual(dialog.scale, 4)
        finally:
            dialog.close()

    def test_unreviewed_equipment_cannot_enable_a_private_chain(self):
        asset = SimpleNamespace(asset_id="tset:0:4:0:socks00", label="Sock 00", width=64, height=64)
        dialog = EquipmentTextureImportDialog(asset)
        try:
            dialog.own_texture.setChecked(True)
            self.assertFalse(dialog.independent)
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
