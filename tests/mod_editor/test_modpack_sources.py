"""Frozen source portability without game data or running a Studio build."""
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import modpack_sources as s, modpack as m, modpack_files as f
from tests.mod_editor.pack_path_test_support import directory_symlink


class SourcesTests(unittest.TestCase):
    def test_long_unicode_roundtrip_without_resolve(self):
        from mod_editor.core import nfl2k5_official_marks  # Load dependencies before injecting the failure.
        with tempfile.TemporaryDirectory() as td:
            root = f._path(Path(td) / ("données " + "a" * 75) / ("sources " + "b" * 75) / ("été " + "c" * 75))
            root.mkdir(parents=True)
            png = f._path(root / "original é.png")
            png.write_bytes(b"editable art")
            tree = f._path(root / "art tree")
            tree.mkdir()
            f._path(tree / "é.png").write_bytes(b"tree art")
            project = f._path(root / "project.json")
            project.write_text(json.dumps(dict(edits=[dict(png=str(png))])), encoding="utf-8")
            recipe = f._path(root / "recipe.json")
            recipe.write_text(json.dumps(dict(preset="softdrink_experimental", overrides=dict(art_folder=str(tree)),
                                             freeze=dict(project=dict(path=str(project))))), encoding="utf-8")
            originals = recipe.read_bytes(), project.read_bytes(), png.read_bytes()
            with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                portable, assets = s.prepare(recipe, root / "stage")
                bundle = root / "sources.2k5sources"
                identity = s.write_bundle(bundle, portable, assets)
                out = f._path(root / "user sources é")
                extracted = s.extract_bundle(bundle, out, identity)
                local = s.materialize(extracted, out)
                user_project = json.loads(Path(local["project"]).read_text(encoding="utf-8"))
                art = Path(user_project["edits"][0]["png"])
                self.assertTrue(m.platform_compat.path_is_within(art, out))
                self.assertEqual(art.read_bytes(), originals[2])
                self.assertEqual(Path(local["original_recipe"]).read_bytes(), originals[0])
                self.assertEqual(Path(local["original_project"]).read_bytes(), originals[1])
                self.assertEqual(f._path(Path(local["overrides"]["art_folder"]) / "é.png").read_bytes(), b"tree art")
                with self.assertRaises(m.ModpackError):
                    s.materialize(extracted, out)
            self.assertEqual((recipe.read_bytes(), project.read_bytes(), png.read_bytes()), originals)

    def test_capture_staging_cannot_overwrite_original_project(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "league-project.json"
            project.write_bytes(b'{"edits": []}')
            recipe = root / "recipe.json"
            recipe.write_text(json.dumps(dict(preset="softdrink_experimental", overrides={},
                                             freeze=dict(project=dict(path=str(project))))))
            with self.assertRaisesRegex(m.ModpackError, "different file"):
                s.prepare(recipe, root)
            self.assertEqual(project.read_bytes(), b'{"edits": []}')

    def test_case_colliding_source_members_are_refused_before_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            art = root / "art.png"
            art.write_bytes(b"art")
            bundle = root / "sources.2k5sources"
            identity = s.write_bundle(bundle, {}, {"assets/Art.png": art, "assets/art.png": art})
            out = root / "out"
            with self.assertRaisesRegex(m.ModpackError, "Duplicate source asset"):
                s.extract_bundle(bundle, out, identity)
            self.assertFalse(out.exists())

    def test_capture_extract_resolve_preserves_originals(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            png = root / "source.png"
            png.write_bytes(b"synthetic editable art")
            roster = root / "roster.json"
            roster.write_text('{"edits": []}')
            project = root / "project.json"
            project.write_text(json.dumps(dict(schema="nfl2k5_visual_mod_project/v1", edits=[dict(png=str(png))])))
            recipe = root / "recipe.json"
            recipe.write_text(json.dumps(dict(preset="softdrink_experimental", overrides=dict(roster_edits=str(roster)),
                                             freeze=dict(project=dict(path=str(project), sha256=hashlib.sha256(project.read_bytes()).hexdigest())))))
            portable, assets = s.prepare(recipe, root / "staging")
            bundle = root / "sources.2k5sources"
            identity = s.write_bundle(bundle, portable, assets)
            out = root / "user sources é"
            extracted = s.extract_bundle(bundle, out, identity)
            local = s.materialize(extracted, out)
            self.assertEqual(Path(local["original_recipe"]).read_bytes(), recipe.read_bytes())
            self.assertEqual(Path(local["original_project"]).read_bytes(), project.read_bytes())
            user_project = json.loads(Path(local["project"]).read_text())
            self.assertEqual(Path(user_project["edits"][0]["png"]).read_bytes(), png.read_bytes())
            self.assertIn(out, Path(user_project["edits"][0]["png"]).parents)
            self.assertEqual(Path(local["overrides"]["roster_edits"]).read_bytes(), roster.read_bytes())
            with self.assertRaises(m.ModpackError): s.materialize(extracted, out)
            with self.assertRaises(m.ModpackError): s.extract_bundle(bundle, root / "wrong", dict(identity, sha256="0" * 64))

    def test_relocation_cannot_escape(self):
        with tempfile.TemporaryDirectory() as td:
            for value in ("@pack/assets/../escape", "@pack/assets/C:/bad", "@pack/assets/missing"):
                with self.assertRaises(m.ModpackError): s.resolve(value, td)

    def test_portable_names_refuse_windows_devices_and_trailing_characters(self):
        for name in ("CON.png", "AUX", "COM1.txt", "LPT9", "COM¹.png", "lpt².dat", "CONIN$", "NUL .txt",
                     "name.", "name ", "a:b", "a\x01b", "../escape", "folder./file"):
            with self.subTest(name=name), self.assertRaises(m.ModpackError):
                f._asset_name("assets/" + name)
        f._asset_name("assets/user sources é/été.png")

    def test_source_links_cannot_escape_even_when_resolve_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            out, external = root / "sources", root / "external"
            out.mkdir()
            external.mkdir()
            (external / "art.png").write_bytes(b"preserve")
            directory_symlink(self, out / "assets", external)
            with mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                with self.assertRaisesRegex(m.ModpackError, "symbolic link"):
                    s.resolve("@pack/assets/art.png", out)
                payload = root / "payload.png"
                payload.write_bytes(b"replacement")
                bundle = root / "sources.2k5sources"
                identity = s.write_bundle(bundle, {}, {"assets/art.png": payload})
                with self.assertRaisesRegex(m.ModpackError, "symbolic link"):
                    s.extract_bundle(bundle, out, identity)
            self.assertEqual((external / "art.png").read_bytes(), b"preserve")

    def test_source_link_metadata_is_refused_without_resolve(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "assets").mkdir()
            payload = root / "payload.png"
            payload.write_bytes(b"replacement")
            bundle = root / "sources.2k5sources"
            identity = s.write_bundle(bundle, {}, {"assets/art.png": payload})
            original = Path.lstat
            def link_stat(path, *args, **kwargs):
                return info if path.name == "assets" else original(path, *args, **kwargs)
            for mode, tag, message in ((stat.S_IFLNK | 0o777, 0, "symbolic link"),
                                       (stat.S_IFDIR | 0o755, 0xA0000003, "reparse point")):
                info = type("Link", (), {"st_mode": mode, "st_reparse_tag": tag})()
                with self.subTest(message=message), mock.patch.object(Path, "lstat", link_stat), \
                     mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
                    with self.assertRaisesRegex(m.ModpackError, message):
                        s.resolve("@pack/assets/art.png", root)
                    with self.assertRaisesRegex(m.ModpackError, message):
                        s.extract_bundle(bundle, root, identity)
            self.assertFalse((root / "assets" / "art.png").exists())

    def test_source_export_refuses_incomplete_official_marks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "project.json"
            project.write_text('{"edits": []}')
            recipe = root / "recipe.json"
            recipe.write_text(json.dumps(dict(preset="softdrink_experimental", overrides=dict(espn_marks_2026=True),
                                             freeze=dict(project=dict(path=str(project))))))
            with self.assertRaisesRegex(m.ModpackError, "complete official marks"):
                s.prepare(recipe, root / "stage")
            marks = root / "marks"
            marks.mkdir()
            (marks / "manifest.json").write_text('{"schema":"nfl2k5_official_marks/v1","marks":{}}')
            with self.assertRaisesRegex(m.ModpackError, "incomplete official marks"):
                s.prepare(recipe, root / "stage", marks_pack=marks)


if __name__ == "__main__":
    unittest.main()
