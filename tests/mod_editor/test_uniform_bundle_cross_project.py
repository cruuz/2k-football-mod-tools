"""Team Kit merge regressions using real PNGs and bounded private sessions."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]

from test_team_kit_bundle import _PngAssetIO, _png
from PIL import Image
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet, SHEET_LAYOUTS
from mod_editor.core.nfl2k5_uniform_catalog import DEFAULT_REPORT, load_nfl2k5_uniform_catalog
from mod_editor.studio.session import StudioSession
from mod_editor.studio.uniform_bundle import TEAM_KIT_MANIFEST, TeamKitBundleService


class CrossProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DEFAULT_REPORT.is_file():
            raise unittest.SkipTest(f"Private Team Select catalog evidence absent: {DEFAULT_REPORT}")
        cls.catalog = load_nfl2k5_uniform_catalog()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="team-kit-cross-project-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.cache = SimpleNamespace(source=SimpleNamespace(sha256="a" * 64),
                                     root=self.root / "cache")
        self.a = self.session("a")
        self.b = self.session("b")
        self.service_a = TeamKitBundleService(self.catalog, self.a)
        self.service_b = TeamKitBundleService(self.catalog, self.b)
        self.torso = self.catalog.get_asset("nfl2k5.uniform.02h3.torso")

    def session(self, name):
        with mock.patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
            session = StudioSession(self.cache, self.catalog, root=self.root / "sessions",
                                    session_id=name)
        session.visual_catalog = self.catalog
        return session

    def edit(self, session, asset, color):
        path = self.root / "edit.png"
        path.write_bytes(_png(asset, color))
        session.replace(asset, path)

    def edit_bundle(self, bundle, asset, color):
        rows = json.loads((bundle / TEAM_KIT_MANIFEST).read_text())["assets"]
        path = bundle / next(row["path"] for row in rows if row["asset_id"] == asset.asset_id)
        path.write_bytes(_png(asset, color))
        return path

    def test_fresh_bundle_imports_into_project_with_earlier_torso_edit(self):
        bundle = self.root / "ravens"
        self.service_a.export(("02H3", "02A3"), bundle)
        incoming = self.edit_bundle(bundle, self.torso, (200, 10, 20, 255)).read_bytes()
        self.edit(self.b, self.torso, (5, 6, 7, 255))
        result = self.service_b.import_edited(bundle)
        self.assertEqual(result.changed_count, 1)
        self.assertEqual(result.unchanged_count, 77)
        self.assertEqual(self.b.current_path(self.torso).read_bytes(), incoming)

    def sheet(self, session, name, color=(40, 80, 120, 255)):
        """Follow Studio's existing fresh-kit bridge and unchanged splitter."""
        source = self.root / f"{name}.png"
        with Image.new("RGBA", (640, 64), color) as image:
            image.save(source)
        targets = tuple(asset for asset in self.catalog.assets_for_set("02H3")
                        if asset.family == "jersey" and asset.digit is not None)
        outputs = split_digit_sheet(source, targets, orientation=SHEET_LAYOUTS[0][1])
        service = TeamKitBundleService(self.catalog, session)
        kit = self.root / name
        service.export(("02H3",), kit)
        rows = json.loads((kit / TEAM_KIT_MANIFEST).read_text())["assets"]
        paths = {row["asset_id"]: kit / row["path"] for row in rows}
        for output in outputs:
            paths[output.asset_id].write_bytes(output.png)
        result = service.import_edited(kit, expected_set_selectors=("02H3",))
        return result, targets

    def test_cross_project_saved_destination_sheet_first_and_repeat_receipt(self):
        bundle = self.root / "both-sides"
        self.service_a.export(("02H3", "02A3"), bundle)
        away = self.catalog.get_asset("nfl2k5.uniform.02a3.torso")
        for torso in (self.torso, away):
            self.edit_bundle(bundle, torso, (90, 60, 10, 255))
            self.edit(self.b, torso, (10, 20, 30, 255))
        _, digits = self.sheet(self.b, "sheet-first")
        project = self.b.save_shareable_project(self.root / "main.2k5mod")
        destination = self.session("loaded-main")
        self.assertEqual(destination.load_shareable_project(project), 12)
        service = TeamKitBundleService(self.catalog, destination)
        digit_bytes = {a.asset_id: destination.current_path(a).read_bytes() for a in digits}
        revision = destination.mutation_revision
        result = service.import_edited(bundle, expected_set_selectors=("02H3", "02A3"))
        self.assertGreater(destination.mutation_revision, revision)
        self.assertEqual((result.changed_count, result.imported_count,
                          result.skipped_unchanged_count, result.overwritten_count), (2, 2, 76, 2))
        overwritten = [row for row in result.components if row.overwritten]
        self.assertEqual({row.asset_id for row in overwritten}, {self.torso.asset_id, away.asset_id})
        self.assertEqual({row.replaced for row in overwritten}, {"your earlier edit"})
        self.assertIn("02H3: Live Uniform / Torso / Jersey", result.details)
        self.assertIn("02A3: Live Uniform / Torso / Jersey", result.details)
        self.assertEqual(digit_bytes, {a.asset_id: destination.current_path(a).read_bytes() for a in digits})
        revision = destination.mutation_revision
        state = (destination.root / "session.json").read_bytes()
        # A new service models the facade creating one for every import.
        repeat = TeamKitBundleService(self.catalog, destination).import_edited(bundle)
        self.assertEqual(repeat.changed_count, 0)
        self.assertEqual(repeat.components, result.components)
        self.assertEqual(repeat.summary, result.summary)
        self.assertEqual(repeat.details, result.details)
        self.assertEqual(destination.mutation_revision, revision)
        self.assertEqual((destination.root / "session.json").read_bytes(), state)
        self.assertEqual(destination.undo(), "Import Team Kit 02H3, 02A3")
        self.assertEqual(destination.current_path(self.torso).read_bytes(), _png(self.torso, (10, 20, 30, 255)))
        self.assertEqual(digit_bytes, {a.asset_id: destination.current_path(a).read_bytes() for a in digits})

    def test_number_sheet_then_kit_and_kit_then_sheet_attribute_earlier_edits(self):
        kit = self.root / "digit-kit"
        self.service_a.export(("02H3",), kit)
        digit = self.catalog.get_asset("nfl2k5.uniform.02h3.digit.jersey.0")
        self.edit_bundle(kit, digit, (110, 130, 150, 255))
        self.edit_bundle(kit, self.torso, (70, 80, 90, 255))
        self.sheet(self.b, "first-sheet")
        result = self.service_b.import_edited(kit)
        row = next(row for row in result.components if row.asset_id == digit.asset_id)
        self.assertTrue(row.overwritten)
        self.assertEqual(row.replaced, "your earlier edit")
        self.assertEqual(result.changed_count, 2)
        torso = self.b.current_path(self.torso).read_bytes()
        result, _ = self.sheet(self.b, "second-sheet", (1, 2, 3, 255))
        self.assertEqual(result.changed_count, 10)
        self.assertEqual(result.overwritten_count, 10)
        row = next(row for row in result.components if row.asset_id == digit.asset_id)
        self.assertEqual(row.replaced, "your earlier edit")
        self.assertEqual(self.b.current_path(self.torso).read_bytes(), torso)
        _, rgba = self.b.asset_io.validate_replacement(digit, self.b.current_path(digit))
        self.assertEqual(rgba, bytes((1, 2, 3, 255)) * digit.width * digit.height)

    def test_main_project_baseline_and_source_overwrite_and_replay(self):
        self.edit(self.a, self.torso, (10, 20, 30, 255))
        kit = self.root / "main-export"
        self.service_a.export(("02H3",), kit)
        self.edit_bundle(kit, self.torso, (200, 50, 70, 255))
        result = self.service_a.import_edited(kit)
        self.assertEqual((result.imported_count, result.overwritten_count), (1, 1))
        self.assertEqual(next(r.replaced for r in result.components if r.overwritten), "your earlier edit")
        result = self.service_b.import_edited(kit)
        self.assertEqual(next(r.replaced for r in result.components if r.overwritten), "source")
        again = self.service_b.import_edited(kit)
        self.assertEqual(again.changed_count, 0)
        self.assertEqual(again.details, result.details)
        # Undo invalidates the attribution cache even though the file is unchanged.
        self.b.undo()
        self.edit(self.b, self.torso, (3, 4, 5, 255))
        after_undo = self.service_b.import_edited(kit)
        self.assertEqual(next(r.replaced for r in after_undo.components if r.overwritten), "your earlier edit")

    def test_unchanged_rgba_skips_despite_reencoding_origin_and_current_change(self):
        self.edit(self.a, self.torso, (1, 2, 3, 255))
        kit = self.root / "unchanged"
        self.service_a.export(("02H3",), kit)
        path = self.edit_bundle(kit, self.torso, (1, 2, 3, 255))
        old_bytes = path.read_bytes()
        with Image.open(path) as opened:
            image = opened.copy()
        with image:
            image.save(path, compress_level=0)
        self.assertNotEqual(path.read_bytes(), old_bytes)
        self.edit(self.b, self.torso, (4, 5, 6, 255))
        state = (self.b.root / "session.json").read_bytes()
        with mock.patch.object(self.b, "current_path", side_effect=AssertionError("untouched read")):
            result = self.service_b.import_edited(kit)
        self.assertEqual((result.changed_count, result.imported_count, result.unchanged_count), (0, 0, 39))
        self.assertEqual((self.b.root / "session.json").read_bytes(), state)

    def test_selection_and_manifest_refusals_are_atomic(self):
        kit = self.root / "invalid"
        self.service_a.export(("02H3",), kit)
        self.edit_bundle(kit, self.torso, (40, 50, 60, 255))
        manifest = kit / TEAM_KIT_MANIFEST
        original = manifest.read_bytes()
        for selectors in (("02A3",), ("02H0",), ("18H0",), ("02H3", "02A3")):
            with self.subTest(selection=selectors), self.assertRaisesRegex(ValidationError, "selected team"):
                self.service_b.import_edited(kit, expected_set_selectors=selectors)
        def mutate(field):
            doc = json.loads(original)
            if field == "schema": doc["schema"] = "unknown"
            elif field == "identity": doc["source"]["sha256"] = "b" * 64
            elif field == "order": doc["assets"][:2] = reversed(doc["assets"][:2])
            elif field == "duplicate": doc["assets"][1] = doc["assets"][0]
            elif field == "metadata": doc["assets"][0]["label"] = "Other target"
            return (json.dumps(doc, sort_keys=True, indent=2) + "\n").encode()
        for field in ("schema", "identity", "order", "duplicate", "metadata"):
            with self.subTest(field=field):
                manifest.write_bytes(mutate(field))
                with self.assertRaises(ValidationError): self.service_b.import_edited(kit)
                self.assertEqual(self.b.modified_count, 0)
                self.assertFalse(self.b.can_undo)
        manifest.write_bytes(original)
        rows = json.loads(original)["assets"]
        last = kit / rows[-1]["path"]
        original_png = last.read_bytes()
        for invalid in (None, b"not PNG", _png(self.torso, (0, 1, 2, 255))):
            with self.subTest(invalid=type(invalid).__name__):
                if invalid is None: last.unlink()
                else: last.write_bytes(invalid)
                with self.assertRaises(ValidationError): self.service_b.import_edited(kit)
                self.assertEqual(self.b.modified_count, 0)
                self.assertFalse(self.b.can_undo)
                last.write_bytes(original_png)

    def test_zip_cross_project_and_edited_input_snapshot(self):
        kit = self.root / "zip-input"
        self.service_a.export(("02H3",), kit)
        supplied = self.edit_bundle(kit, self.torso, (60, 70, 80, 255))
        expected = supplied.read_bytes()
        self.edit(self.b, self.torso, (1, 2, 3, 255))
        archive = self.root / "edited.zip"
        with zipfile.ZipFile(archive, "w") as output:
            for path in kit.rglob("*"):
                if path.is_file(): output.write(path, path.relative_to(kit).as_posix())
        result = self.service_b.import_edited(archive)
        self.assertEqual(result.overwritten_count, 1)
        self.assertEqual(self.b.current_path(self.torso).read_bytes(), expected)
        def progress(stage, *_):
            if stage.startswith("Staging changed"):
                supplied.write_bytes(_png(self.torso, (200, 210, 220, 255)))
        self.service_a.import_edited(kit, progress=progress)
        self.assertEqual(self.a.current_path(self.torso).read_bytes(), expected)

    def test_foreign_staged_edit_is_still_refused_before_mutation(self):
        kit = self.root / "foreign"
        self.service_a.export(("02H3",), kit)
        self.edit_bundle(kit, self.torso, (2, 3, 4, 255))
        self.edit(self.b, self.torso, (30, 40, 50, 255))
        self.b.current_path(self.torso).write_bytes(_png(self.torso, (60, 70, 80, 255)))
        revision = self.b.mutation_revision
        with self.assertRaisesRegex(ValidationError, "outside Mod Studio"):
            self.service_b.import_edited(kit)
        self.assertEqual(self.b.mutation_revision, revision)


if __name__ == "__main__":
    unittest.main()
