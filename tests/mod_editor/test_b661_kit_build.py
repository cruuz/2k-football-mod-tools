"""Export/edit/import/preview/CLI build with synthetic art and real encoders."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")
import b661_build_fixture as fixture
from mod_editor.core import nfl2k5_uniform_catalog as catalog_module
from mod_editor.studio.session import StudioSession
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.uniform_bundle import TeamKitBundleService, TEAM_KIT_MANIFEST
from tests.mod_editor.test_team_kit_bundle import _PngAssetIO
from nfl_txtr import encode_rgba_png, parse_chunks, decode_chunk
from nfl_tset_png_import import decode_rgba_png, decode_tset_levels


def synthetic_catalog():
    # Real 39 component contracts, one synthetic physical set. No shipped reports.
    sets, all_assets = [], []
    for side, name in (("H", "HOME"), ("A", "AWAY")):
        selector = f"18{side}0"
        with patch.object(catalog_module, "_authored_digit_dimensions", return_value={}):
            assets = catalog_module._assets_for_seed("18", side, name, 0, selector)
        sets.append(catalog_module.UniformSet(selector, f"Synthetic {name}", ("Synthetic",), ("SYN",), (),
            "18", side, name, 0, name, selector+".IFF", tuple(a.asset_id for a in assets), assets[0].asset_id))
        all_assets.extend(assets)
    with patch.object(catalog_module, "EXPECTED_SET_COUNT", 2):
        return catalog_module.Nfl2k5UniformCatalog(sets, all_assets, Path("synthetic.json"))


class KitBuildTests(unittest.TestCase):
    def test_alpha_and_indexed_palette_changes_are_not_skipped(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = synthetic_catalog()
            cache = SimpleNamespace(source=SimpleNamespace(sha256="a"*64), root=root / "cache")
            with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
                session = StudioSession(cache, catalog, root=root / "sessions")
            service = TeamKitBundleService(catalog, session)
            bundle = root / "kit"
            service.export(("18H0",), bundle, container="folder")
            manifest = json.loads((bundle / TEAM_KIT_MANIFEST).read_bytes())
            first, second = catalog.assets[:2]
            for asset, mode in ((first, "alpha"), (second, "palette")):
                row = next(r for r in manifest["assets"] if r["asset_id"] == asset.asset_id)
                path = bundle / row["path"]
                base = _PngAssetIO._color(asset)
                if mode == "alpha":
                    edited = (*base[:3], 99)
                    path.write_bytes(encode_rgba_png(asset.width, asset.height,
                                                    bytes(edited)*(asset.width*asset.height)))
                else:
                    edited = ((base[0]+31)%256, base[1], base[2], 255)
                    image = Image.new("P", (asset.width, asset.height), 0)
                    image.putpalette(list(edited[:3]) + [0]*765)
                    image.save(path)
            result = service.import_edited(bundle)
            self.assertEqual(result.changed_count, 2)
            self.assertEqual(session.modified_asset_ids, {first.asset_id, second.asset_id})
            alpha = decode_rgba_png(session.current_path(first).read_bytes(), first.dimensions)[2]
            self.assertEqual(set(alpha[3::4]), {99})
            pixels = decode_rgba_png(session.current_path(second).read_bytes(), second.dimensions)[2]
            self.assertEqual(pixels, bytes(edited)*(second.width*second.height))

    def test_kit_pixels_reach_preview_and_actual_cli_package(self):
        from PyQt5.QtWidgets import QApplication
        from mod_editor.gui.studio_qt import _PngDropPreview
        self.app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            equipment, target = fixture.create(root)
            catalog = synthetic_catalog()
            cache = SimpleNamespace(source=SimpleNamespace(sha256=fixture.sha((root / "source.iso").read_bytes())),
                                    root=root / "cache")
            with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
                session = StudioSession(cache, catalog, root=root / "sessions")
            session.attach_visual_catalog(catalog)
            facade = Nfl2k5StudioFacade(uniform_catalog=catalog, xemu_command=())
            facade._session, facade._cache = session, cache
            bundle = root / "kit"
            exported = facade.export_team_kit_sets(("18H0",), bundle, progress=lambda *a: None, container="folder")
            self.assertEqual(exported.asset_count, 39)
            manifest = json.loads((bundle / TEAM_KIT_MANIFEST).read_bytes())
            asset = catalog.assets[0]
            selected = next(row for row in manifest["assets"] if row["asset_id"] == asset.asset_id)
            rgba = bytes((30, 190, 220, 255))*(512*256)
            (bundle / selected["path"]).write_bytes(encode_rgba_png(512, 256, rgba))
            result = facade.import_team_kit(bundle, lambda *a: None)
            self.assertEqual(result.changed_count, 1)
            self.assertEqual(result.unchanged_count, 38)
            self.assertEqual(session.modified_asset_ids, {asset.asset_id})
            self.assertIn(asset.label, result.summary)
            self.assertIn("Build Modded XISO", result.summary)
            preview = facade.preview_asset(asset, lambda *a: None)
            self.assertEqual(decode_rgba_png(preview.read_bytes(), (512,256))[2], rgba)
            widget = _PngDropPreview()
            self.assertTrue(widget.set_png(preview))
            # Inspect the actual rendered source pixmap, including all new pixels.
            self.assertEqual(widget._pixmap.toImage().pixelColor(0, 0).getRgb(), (30,190,220,255))
            widget.deleteLater()
            project_path = root / "project.json"
            session.write_canonical_project(project_path)
            project = json.loads(project_path.read_bytes())
            equipment_rgba = bytes((20, 150, 80, 255))*(32*32)
            equipment_id, png = equipment.png(independent=False, rgba=equipment_rgba)
            project["edits"].append(dict(kind="uniform_equipment_texture", asset_id=equipment_id, png=str(png)))
            project_path.write_bytes((json.dumps(project, indent=2, sort_keys=True)+"\n").encode())
            command = [sys.executable, str(Path(fixture.__file__)), str(root), "build",
                "--project", str(project_path), "--source-xiso", str(root / "source.iso"),
                "--output-xiso", str(root / "built.iso"), "--manifest", str(root / "receipt.json"),
                "--artifact-dir", str(root / "artifacts"), "--index", str(root / "0"),
                "--inventory", str(root / "inventory.json")]
            before = (root / "source.iso").read_bytes()
            completed = subprocess.run(command, capture_output=True, text=True, timeout=40, cwd=ROOT)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("NFL2K5_VISUAL_MOD_BUILD_PASS edits=2", completed.stdout)
            receipt = json.loads((root / "receipt.json").read_bytes())
            self.assertEqual({row["kind"] for row in receipt["edits"]}, {"torso", "uniform_equipment_texture"})
            built = (root / "built.iso").read_bytes()
            self.assertEqual((root / "source.iso").read_bytes(), before)
            for row in receipt["edits"]:
                start = row["target"]["absolute_span_offset"]
                span = built[start:start+row["replacement"]["span_size"]]
                chunk = parse_chunks(span)[0]
                decoded, _ = decode_chunk(span, chunk)
                if row["kind"] == "torso":
                    self.assertEqual(decode_tset_levels(decoded)[0][0].rgba, rgba)
                    self.assertEqual(row["project_edit"]["kind"], "torso")
                else:
                    from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
                    textures, _ = writer._validate_layout(equipment.decoded, equipment.chunk, equipment.rows)
                    self.assertEqual(writer.decode_equipment_levels(decoded, chunk, textures[0])[0], equipment_rgba)
            print(completed.stdout.strip())


if __name__ == "__main__":
    unittest.main()
