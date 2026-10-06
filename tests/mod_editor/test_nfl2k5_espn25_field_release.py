"""Pinned Anniversary art can ship without admitting foreign or retail PNGs."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "anniversary_release_check", ROOT / "packaging/check_2k5_mod_studio_release.py"
)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class AnniversaryFieldReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "stage"
        self.catalog = json.loads((ROOT / release.ANNIVERSARY_FIELD_PNG_CATALOG).read_text())
        self.files = [release.ANNIVERSARY_FIELD_PNG_CATALOG, *self.catalog["files"]]
        for relative in self.files:
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self.allowlist = Path(self.temporary.name) / "allowlist.txt"
        self.allow()

    def allow(self):
        self.allowlist.write_text("\n".join(self.files) + "\n", encoding="utf-8")

    def test_all_283_reviewed_pngs_pass_and_match_existing_provider_pins(self):
        result = release.audit_release(self.root, self.allowlist)
        self.assertEqual(result["reviewed_anniversary_field_png_count"], 283)
        self.assertFalse(result["retail_payloads_included"])
        self.assertEqual(result["reviewed_scorebug_template_png_count"], 0)
        module = ast.parse((ROOT / "mod_editor/core/providers.py").read_text())
        provider = next(node for node in module.body if isinstance(node, ast.ClassDef)
                        and node.name == "Nfl2k5UnifiedVisualProvider")
        pins = ast.literal_eval(next(node.value for node in provider.body
                                    if isinstance(node, ast.AnnAssign)
                                    and isinstance(node.target, ast.Name)
                                    and node.target.id == "data_pins"))
        actual = {path.relative_to(ROOT).as_posix()
                  for path in (ROOT / "data/nfl2k5_espn25_fields").rglob("*.png")}
        self.assertEqual(set(self.catalog["files"]), actual)
        for relative, contract in self.catalog["files"].items():
            self.assertEqual(contract["sha256"], pins[relative])

    def test_changed_bytes_at_reviewed_path_are_refused_without_size_change(self):
        path = self.root / "data/nfl2k5_espn25_fields/source/den_1968_1996.png"
        data = bytearray(path.read_bytes())
        data[-8] ^= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(release.ReleaseCheckError, "Anniversary PNG identity changed"):
            release.audit_release(self.root, self.allowlist)

    def test_changed_size_at_reviewed_path_is_refused(self):
        path = self.root / "data/nfl2k5_espn25_fields/row51/center_logo.png"
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(release.ReleaseCheckError, "Anniversary PNG size changed"):
            release.audit_release(self.root, self.allowlist)

    def test_reviewed_bytes_at_foreign_paths_remain_forbidden(self):
        for relative in ("data/nfl2k5_espn25_fields/row51/extra.png",
                         "data/nfl2k5_espn25_fields/source/foreign.png"):
            with self.subTest(relative=relative):
                path = self.root / relative
                shutil.copyfile(ROOT / "data/nfl2k5_espn25_fields/row51/center_logo.png", path)
                self.files.append(relative)
                self.allow()
                with self.assertRaisesRegex(release.ReleaseCheckError, "suffix is forbidden"):
                    release.audit_release(self.root, self.allowlist)
                path.unlink()
                self.files.remove(relative)
                self.allow()

    def test_modified_or_missing_catalog_cannot_grant_an_exception(self):
        path = self.root / release.ANNIVERSARY_FIELD_PNG_CATALOG
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(release.ReleaseCheckError, "Anniversary PNG catalog hash changed"):
            release.audit_release(self.root, self.allowlist)
        path.unlink()
        with self.assertRaisesRegex(release.ReleaseCheckError, "suffix is forbidden"):
            release.audit_release(self.root, self.allowlist)

    def test_private_byte_boundary_precedes_the_reviewed_png_exception(self):
        relative = "data/nfl2k5_espn25_fields/row51/center_logo.png"
        digest = hashlib.sha256((self.root / relative).read_bytes()).hexdigest()
        with mock.patch.object(release, "_private_boundary", return_value=(set(), {digest})):
            with self.assertRaisesRegex(release.ReleaseCheckError, "private marks/evidence bytes are forbidden"):
                release.audit_release(self.root, self.allowlist)


if __name__ == "__main__":
    unittest.main()
