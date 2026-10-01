"""External-pack boundary: absent, changed, confined, pinned and clean public release."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(Path(__file__).parent)]
from mod_editor.core import nfl2k5_official_marks as official
from mod_editor.core import nfl2k5_espn_marks as marks, nfl2k5_espn_wipes_boards as wipes
from mod_editor.core import mod_build, nfl2k5_build_settings as settings
from official_marks_fixture import synthetic_pack


class PackBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = mock.patch.dict(os.environ, {official.ENVIRONMENT: ""})
        env.start()
        self.addCleanup(env.stop)

    def test_absent_pack_metadata_still_loads_and_write_refuses_before_open(self):
        for module in (marks, wipes):
            self.assertTrue(module._pins())
            self.assertFalse(module.available())
            self.assertIn("Official marks pack missing", module.availability_reason())
            target = self.root / "untouched.iso"
            target.write_bytes(b"unchanged")
            with mock.patch.object(module, "_outer_image", side_effect=AssertionError("must not open")):
                with self.assertRaisesRegex(ValueError, "Official marks pack missing"):
                    module.apply_to_image(target)
            self.assertEqual(target.read_bytes(), b"unchanged")

    def test_selected_build_refuses_missing_pack_before_copy(self):
        from test_mod_build_performance import synthetic_disc
        source = self.root / "source.iso"
        synthetic_disc(source)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        for key in ("espn_marks_2026", "espn_wipes_boards_2026"):
            target = self.root / (key + ".iso")
            with mock.patch("mod_editor.core.build_io.copy_image", side_effect=AssertionError("must not copy")):
                with self.assertRaisesRegex(ValueError, "Official marks pack missing"):
                    mod_build.build(mod_build.BuildPlan(str(source), str(target), **{key: True}))
            self.assertFalse(target.exists())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)

    def test_recipe_preserves_pack_path_and_validates_type(self):
        values = settings.build_settings({"official_marks_pack": str(self.root), "espn_marks_2026": True})
        plan = settings.to_plan(values, "source", "target")
        self.assertEqual(plan.to_recipe()["official_marks_pack"], str(self.root))
        with self.assertRaisesRegex(ValueError, "official_marks_pack must be text"):
            settings.build_settings({"official_marks_pack": 7})
        self.assertTrue(mod_build.validate_plan(mod_build.BuildPlan("s", "t", official_marks_pack=7)))

    def test_manifest_and_bytes_are_both_pinned_and_rechecked(self):
        pins = synthetic_pack(self.root)
        name = "nfl_chiclet.png"
        with mock.patch.dict(official.ASSETS, pins, clear=True):
            self.assertEqual(official.asset_path(name, self.root), self.root / name)
            path = self.root / name
            path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "PNG differs"):
                official.asset_path(name, self.root)
            document = json.loads((self.root / "manifest.json").read_text())
            document["marks"][name]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (self.root / "manifest.json").write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "manifest differs"):
                official.asset_path(name, self.root)

    def test_long_unicode_marks_folder_without_resolve(self):
        root = official.platform_compat.io_path(
            self.root / ("données " + "a" * 75) / ("sources " + "b" * 75) / ("marks é " + "c" * 75))
        root.mkdir(parents=True)
        pins = synthetic_pack(root)
        with mock.patch.dict(official.ASSETS, pins, clear=True), \
             mock.patch.object(Path, "resolve", side_effect=OSError(234, "More data available")):
            for name in pins:
                path = official.asset_path(name, root)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), pins[name])

    def test_explicit_root_overrides_environment_and_paths_stay_inside_pack(self):
        pins = synthetic_pack(self.root)
        name = "nfl_chiclet.png"
        with mock.patch.dict(official.ASSETS, pins, clear=True), mock.patch.dict(os.environ, {official.ENVIRONMENT: "missing"}):
            self.assertTrue(official.asset_path(name, self.root).is_file())
            manifest = self.root / "manifest.json"
            doc = json.loads(manifest.read_text())
            # A Windows root-relative path (/absolute.png) has no drive and
            # reaches the later containment check. Exercise both checks with
            # the appropriate exact diagnostic, including fully absolute paths.
            bad_paths = [("../escape.png", "path escapes"),
                         (str(self.root / "absolute.png"), "path escapes"),
                         ("/absolute.png", "path must stay" if os.name == "nt" else "path escapes")]
            for bad, reason in bad_paths:
                doc["marks"][name]["file"] = bad
                manifest.write_text(json.dumps(doc))
                with self.assertRaisesRegex(ValueError, reason):
                    official.asset_path(name, self.root)
            doc["marks"][name]["file"] = "alias.png"
            manifest.write_text(json.dumps(doc))
            try:
                (self.root / "alias.png").symlink_to(self.root / name)
            except OSError:
                return  # Windows without symlink permission still ran the traversal checks.
            with self.assertRaisesRegex(ValueError, "path must stay"):
                official.asset_path(name, self.root)

    def test_malformed_and_incomplete_manifests_refuse_cleanly(self):
        for doc in ("{", "[]", json.dumps({"schema": official.SCHEMA, "marks": {}})):
            (self.root / "manifest.json").write_text(doc)
            with self.assertRaisesRegex(ValueError, "Official marks pack invalid"):
                official.asset_path("nfl_chiclet.png", self.root)

    def test_public_tree_and_release_catalog_exclude_five_pngs(self):
        allow = (ROOT / "packaging/release-allowlist.txt").read_text().splitlines()
        catalog = json.loads((ROOT / "packaging/nfl2k5_scorebug_template_pngs.json").read_text())["files"]
        for relative in official.CATALOG:
            self.assertFalse((ROOT / relative).exists())
            self.assertNotIn(relative, allow)
            self.assertNotIn(relative, catalog)
        self.assertIn("mod_editor/core/nfl2k5_official_marks.py", allow)


if __name__ == "__main__":
    unittest.main()
