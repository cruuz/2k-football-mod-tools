"""The Beta 76 boundary uses neutral fixtures, including across process workers."""
import hashlib
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from mod_editor.core import nfl2k5_official_marks as official, mod_build
from official_marks_fixture import synthetic_pack

MODULES = {
    'modern_metlife': 'modern_metlife',
    'modern_metlife_model': 'metlife_model',
    'modern_sofi': 'sofi_model',
    'modern_highmark': 'highmark_model',
    'modern_mercedes_benz': 'mercedes_benz_model',
    'modern_usbank': 'usbank_model',
    'modern_lucas_oil': 'lucas_oil_model',
    'modern_state_farm': 'state_farm_model',
}


def worker_root(_job):
    return official.selected_root()


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.configured_pack = os.environ.get(official.ENVIRONMENT, "")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {official.ENVIRONMENT: ''})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_every_new_consumer_refuses_before_opening_source_or_target(self):
        target = self.root / 'unchanged.iso'
        target.write_bytes(b'unchanged')
        for feature, name in MODULES.items():
            module = importlib.import_module('mod_editor.core.nfl2k5_' + name)
            with self.subTest(feature=feature):
                with self.assertRaisesRegex(ValueError, 'Official marks pack missing'):
                    module.apply_to_image(target, retail_source='never-opened')
                with self.assertRaisesRegex(ValueError, 'Official marks pack missing'):
                    mod_build.preflight_plan(mod_build.BuildPlan('never-opened', str(target), **{feature: True}))
        self.assertEqual(target.read_bytes(), b'unchanged')

    def test_all_paths_use_pins_even_if_a_public_copy_reappears(self):
        pins = synthetic_pack(self.root)
        with mock.patch.dict(official.ASSETS, pins, clear=True), official.using_pack(self.root):
            for relative, row in official.CATALOG.items():
                with self.subTest(path=relative):
                    resolved = official.resolve_path(ROOT / relative)
                    self.assertEqual(resolved, self.root / row['name'])
                    self.assertEqual(hashlib.sha256(resolved.read_bytes()).hexdigest(), pins[row['name']])
            for feature in MODULES:
                official.validate_feature(feature)
        with self.assertRaisesRegex(ValueError, 'Official marks pack missing'):
            official.resolve_path(ROOT / next(iter(official.CATALOG)))

    def test_metlife_cached_pixels_cannot_hide_a_changed_or_missing_pack(self):
        from mod_editor.core import nfl2k5_modern_metlife as mm
        relative = 'art/s18/stadium/banner01.png'
        row = official.CATALOG[(mm.DATA_DIR / relative).relative_to(ROOT).as_posix()]
        pins = synthetic_pack(self.root)
        with mock.patch.dict(official.ASSETS, pins, clear=True), official.using_pack(self.root):
            self.assertEqual(mm.art_rgba(relative, 64, 64).shape, (64, 64, 4))
            (self.root / row['name']).write_bytes(b'changed after first read')
            with self.assertRaisesRegex(ValueError, 'PNG differs'):
                mm.art_rgba(relative, 64, 64)
        with self.assertRaisesRegex(ValueError, 'Official marks pack missing'):
            mm.art_rgba(relative, 64, 64)

    def test_explicit_recipe_scope_reaches_spawn_workers_and_resets(self):
        with mock.patch.dict(os.environ, {official.ENVIRONMENT: 'environment-pack'}):
            with official.using_pack('recipe-pack'):
                with multiprocessing.get_context('spawn').Pool(1) as pool:
                    actual = pool.apply(official.run_with_pack, (worker_root, None, official.selected_root()))
                self.assertEqual(actual, 'recipe-pack')
            self.assertEqual(official.selected_root(), 'environment-pack')

    def test_lossless_split_uses_public_pixels_and_only_the_private_rectangle(self):
        from PIL import Image
        import numpy as np
        name = "neutral.png"
        base = self.root / "public.png"
        original = Image.new("RGBA", (8, 4), (20, 40, 60, 255))
        original.save(base)
        original.paste((180, 100, 10, 255), (4, 0, 8, 2))
        original.save(self.root / name)
        sha = hashlib.sha256((self.root / name).read_bytes()).hexdigest()
        (self.root / "manifest.json").write_text(json.dumps({"schema": official.SCHEMA,
            "marks": {name: {"file": name, "sha256": sha}}}))
        row = dict(name=name, public_base=str(base), private_rects=[[4, 0, 8, 2]],
                   public_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),
                   rgba_sha256=hashlib.sha256(original.tobytes()).hexdigest())
        relative = "data/neutral-split.png"
        with mock.patch.dict(official.CATALOG, {relative: row}, clear=True), \
                mock.patch.dict(official.ASSETS, {name: sha}, clear=True):
            result = official.rgba(ROOT / relative, self.root)
            self.assertTrue(np.array_equal(result, np.asarray(original)))
            row["private_rects"] = [[4, 0, 7, 2]]
            with self.assertRaisesRegex(ValueError, "does not reconstruct"):
                official.rgba(ROOT / relative, self.root)
            base.write_bytes(b"modified public base")
            with self.assertRaisesRegex(ValueError, "public split differs"):
                official.rgba(ROOT / relative, self.root)

    def test_rams_split_reconstructs_every_original_pixel(self):
        if not self.configured_pack:
            self.skipTest("official marks pack absent")
        import numpy as np
        from PIL import Image
        relative = "data/nfl2k5_sofi_model/art/field/s23_endzone_R.png"
        row = official.CATALOG[relative]
        with Image.open(official.resolve_path(ROOT / relative, self.configured_pack)) as image:
            original = np.asarray(image.convert("RGBA"))
        self.assertTrue(np.array_equal(official.rgba(ROOT / relative, self.configured_pack), original))
        with Image.open(ROOT / row["public_base"]) as image:
            public = np.asarray(image.convert("RGBA"))
        self.assertTrue((public[0:64, 112:200] == (0, 53, 148, 255)).all())
        original = original.copy()
        original[0:64, 112:200] = (0, 53, 148, 255)
        self.assertTrue(np.array_equal(public, original))

    def test_entire_boundary_is_absent_from_public_files_and_release_catalog(self):
        doc = json.loads((ROOT / 'packaging/b76_private_paths.json').read_text())
        catalog = json.loads((ROOT / 'packaging/nfl2k5_scorebug_template_pngs.json').read_text())['files']
        allow = set((ROOT / 'packaging/release-allowlist.txt').read_text().splitlines())
        for relative in doc['paths']:
            with self.subTest(path=relative):
                # The handoff report may be left untracked for main to read.
                if relative != 'MK2_REPORT.md':
                    self.assertFalse((ROOT / relative).exists())
                self.assertNotIn(relative, catalog)
                self.assertNotIn(relative, allow)
        self.assertEqual(len(official.CATALOG), 42)
        self.assertFalse(doc['released_blob_exceptions'])


if __name__ == '__main__':
    unittest.main()
