"""b772: the reviewed modern-art PNG catalog admits exactly the authored 2026 coach, fan and officials art."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "modern_art_release_check", ROOT / "packaging/check_2k5_mod_studio_release.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
TOOL_SPEC = importlib.util.spec_from_file_location("modern_art_catalog_tool", ROOT / "tools/b77/modern_art_png_catalog.py")
tool = importlib.util.module_from_spec(TOOL_SPEC)
TOOL_SPEC.loader.exec_module(tool)
FOLDERS = ("data/nfl2k5_modern_coaches", "data/nfl2k5_modern_fans", "data/nfl2k5_modern_officials",
           "data/nfl2k5_super_bowl_walls", "data/nfl2k5_era_ball")


class ModernArtReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "stage"
        self.catalog = json.loads((ROOT / release.MODERN_ART_PNG_CATALOG).read_text(encoding="utf-8"))
        self.files = [release.MODERN_ART_PNG_CATALOG, *self.catalog["files"]]
        for relative in self.files:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.allowlist = Path(self.temporary.name) / "allowlist.txt"
        self.allow()

    def allow(self):
        self.allowlist.write_text("\n".join(self.files) + "\n", encoding="utf-8")

    def test_catalog_digest_is_pinned_and_every_reviewed_png_passes(self):
        data = (ROOT / release.MODERN_ART_PNG_CATALOG).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), release.MODERN_ART_PNG_CATALOG_SHA256)
        result = release.audit_release(self.root, self.allowlist)
        self.assertEqual(result["reviewed_modern_art_png_count"], len(self.catalog["files"]))
        self.assertFalse(result["retail_payloads_included"])
        self.assertEqual(result["reviewed_anniversary_field_png_count"], 0)

    def test_the_tool_regenerates_the_committed_catalog_byte_for_byte(self):
        document, refused = tool.build(ROOT)
        self.assertEqual(tool.render(document), (ROOT / release.MODERN_ART_PNG_CATALOG).read_bytes())
        on_disk = {path.relative_to(ROOT).as_posix() for folder in FOLDERS for path in (ROOT / folder).rglob("*.png")}
        self.assertEqual(set(document["files"]) | set(refused), on_disk)
        self.assertFalse(set(document["files"]) & set(refused))

    def test_photo_portraits_and_retail_pixel_art_are_not_admitted(self):
        _document, refused = tool.build(ROOT)
        for relative in ("data/nfl2k5_modern_coaches/portraits/7031.png",
                         "data/nfl2k5_modern_coaches/portraits/7034.png",
                         "data/nfl2k5_modern_coaches/DAL/accessories.png"):
            with self.subTest(relative=relative):
                self.assertNotIn(relative, self.catalog["files"])
                self.assertIn(relative, refused)
                path = self.root / relative
                parent_existed = path.parent.exists()
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, path)
                self.files.append(relative)
                self.allow()
                with self.assertRaisesRegex(release.ReleaseCheckError, "suffix is forbidden"):
                    release.audit_release(self.root, self.allowlist)
                self.files.remove(relative)
                path.unlink()
                if not parent_existed:
                    path.parent.rmdir()
                self.allow()

    def test_catalog_matches_the_owning_modules_pins(self):
        coaches = json.loads((ROOT / "data/nfl2k5_modern_coaches/pins.json").read_text(encoding="utf-8"))
        pinned = {}
        for row in coaches["teams"]:
            for name, digest in row["art"].items():
                pinned[f"data/nfl2k5_modern_coaches/{row['team']}/{name}.png"] = digest
        for relative, contract in self.catalog["files"].items():
            if relative in pinned:
                self.assertEqual(contract["sha256"], pinned[relative], relative)
        for relative, contract in self.catalog["files"].items():
            data = (ROOT / relative).read_bytes()
            self.assertEqual(contract["size"], len(data))
            self.assertEqual(contract["sha256"], hashlib.sha256(data).hexdigest())

    def test_changed_bytes_at_a_reviewed_path_are_refused(self):
        relative = next(iter(sorted(self.catalog["files"])))
        path = self.root / relative
        data = bytearray(path.read_bytes())
        data[-8] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(release.ReleaseCheckError, "modern-art PNG identity changed"):
            release.audit_release(self.root, self.allowlist)

    def test_changed_size_at_a_reviewed_path_is_refused(self):
        relative = next(iter(sorted(self.catalog["files"])))
        path = self.root / relative
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(release.ReleaseCheckError, "modern-art PNG size changed"):
            release.audit_release(self.root, self.allowlist)

    def test_reviewed_bytes_at_a_foreign_path_remain_forbidden(self):
        relative = next(iter(sorted(self.catalog["files"])))
        foreign = relative.rsplit("/", 1)[0] + "/extra.png"
        shutil.copyfile(ROOT / relative, self.root / foreign)
        self.files.append(foreign)
        self.allow()
        with self.assertRaisesRegex(release.ReleaseCheckError, "suffix is forbidden"):
            release.audit_release(self.root, self.allowlist)

    def test_a_changed_catalog_is_refused(self):
        catalog = self.root / release.MODERN_ART_PNG_CATALOG
        catalog.write_bytes(catalog.read_bytes().replace(b'"schema"', b' "schema"', 1))
        with self.assertRaisesRegex(release.ReleaseCheckError, "modern-art PNG catalog hash changed"):
            release.audit_release(self.root, self.allowlist)


if __name__ == "__main__":
    unittest.main()
