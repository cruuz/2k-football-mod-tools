"""Beta 72.1: a Team Kit exported from an edited project imports into a fresh one.

Coach Edwards exported the kits of the teams he had finished, started fresh
projects when older ones would not open, and every import reported "Imported:
0. Skipped unchanged: 78." The export was right (it carried his edits); the
import's merge rule treated "equal to the export" as "untouched, keep the
destination", which is only true when the destination has its own edit.
"""
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
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).resolve().parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")

import b661_build_fixture as build_fixture
from test_b661_kit_build import synthetic_catalog
from test_team_kit_bundle import _PngAssetIO, _png, _rgba
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.session import StudioSession
from mod_editor.studio.uniform_bundle import TEAM_KIT_MANIFEST
from nfl_tset_png_import import decode_tset_levels
from nfl_txtr import decode_chunk, parse_chunks

EDITS = {
    "nfl2k5.uniform.18h0.torso": (200, 16, 40, 255),
    "nfl2k5.uniform.18h0.sleeve": (16, 200, 40, 255),
    "nfl2k5.uniform.18h0.digit.jersey.3": (250, 250, 250, 255),
    "nfl2k5.uniform.18a0.pants": (30, 30, 30, 255),
}


class FreshProjectKitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="b721-kit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.equipment, _ = build_fixture.create(self.root)
        self.catalog = synthetic_catalog()
        self.cache = SimpleNamespace(
            source=SimpleNamespace(sha256=build_fixture.sha((self.root / "source.iso").read_bytes())),
            root=self.root / "cache")

    def studio(self, name):
        with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
            session = StudioSession(self.cache, self.catalog, root=self.root / "sessions", session_id=name)
        session.attach_visual_catalog(self.catalog)
        facade = Nfl2k5StudioFacade(uniform_catalog=self.catalog, xemu_command=())
        facade._session, facade._cache = session, self.cache
        return facade, session

    def build(self, session):
        project_path = self.root / "fresh.json"
        session.write_canonical_project(project_path)
        project = json.loads(project_path.read_bytes())
        # The synthetic disc carries the one real torso target; equipment
        # (shoes, socks) is not a Team Kit part and travels in the project.
        project["edits"] = [row for row in project["edits"] if row["kind"] == "torso"]
        shoe_rgba = bytes((20, 150, 80, 255)) * (32 * 32)
        shoe_id, shoe_png = self.equipment.png(independent=False, rgba=shoe_rgba)
        project["edits"].append(dict(kind="uniform_equipment_texture", asset_id=shoe_id, png=str(shoe_png)))
        project_path.write_bytes((json.dumps(project, indent=2, sort_keys=True) + "\n").encode())
        command = [sys.executable, str(Path(build_fixture.__file__)), str(self.root), "build",
                   "--project", str(project_path), "--source-xiso", str(self.root / "source.iso"),
                   "--output-xiso", str(self.root / "built.iso"), "--manifest", str(self.root / "receipt.json"),
                   "--artifact-dir", str(self.root / "artifacts"), "--index", str(self.root / "0"),
                   "--inventory", str(self.root / "inventory.json")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=ROOT)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return json.loads((self.root / "receipt.json").read_bytes()), shoe_rgba

    def test_edited_project_kit_imports_into_fresh_project_and_builds(self):
        facade_a, a = self.studio("edited")
        for asset_id, color in EDITS.items():
            asset = self.catalog.get_asset(asset_id)
            path = self.root / f"{asset.kind}.png"
            path.write_bytes(_png(asset, color))
            a.replace(asset, path)
        kit = self.root / "ravens-kit"
        exported = facade_a.export_team_kit_sets(("18H0", "18A0"), kit, progress=lambda *args: None,
                                                 container="folder")
        self.assertEqual(exported.asset_count, 78)
        rows = {row["asset_id"]: row for row in json.loads((kit / TEAM_KIT_MANIFEST).read_bytes())["assets"]}
        # The export was never the bug: it carries each edit as user work.
        for asset_id in EDITS:
            self.assertEqual(rows[asset_id]["content_origin"], "user_replacement")
        self.assertFalse(any("shoe" in key or "sock" in key for key in rows))

        facade_b, b = self.studio("fresh")
        result = facade_b.import_team_kit(kit, lambda *args: None)
        imported = {row.asset_id: row for row in result.components if row.decision == "imported"}
        self.assertEqual(set(imported), set(EDITS))
        self.assertEqual((result.imported_count, result.changed_count, result.overwritten_count), (4, 4, 0))
        self.assertTrue(result.summary.startswith("Imported: 4. Skipped unchanged: 74. Overwritten: 0."))
        self.assertEqual({row.replaced for row in imported.values()}, {"source"})
        for asset_id, color in EDITS.items():
            asset = self.catalog.get_asset(asset_id)
            self.assertEqual(b.asset_io.validate_replacement(asset, b.current_path(asset))[1], _rgba(asset, color))
        self.assertEqual(b.undo(), "Import Team Kit 18H0, 18A0")
        self.assertEqual(b.modified_count, 0)
        self.assertEqual(facade_b.import_team_kit(kit, lambda *args: None).imported_count, 4)
        self.assertEqual(b.modified_count, 4)

        # Compiled bytes differ from retail: the imported torso and a project
        # shoe reach a real disc build.
        receipt, shoe_rgba = self.build(b)
        source = (self.root / "source.iso").read_bytes()
        built = (self.root / "built.iso").read_bytes()
        torso = self.catalog.get_asset("nfl2k5.uniform.18h0.torso")
        kinds = set()
        for row in receipt["edits"]:
            kinds.add(row["kind"])
            start, size = row["target"]["absolute_span_offset"], row["replacement"]["span_size"]
            self.assertNotEqual(built[start:start + size], source[start:start + size])
            span = built[start:start + size]
            chunk = parse_chunks(span)[0]
            decoded, _ = decode_chunk(span, chunk)
            if row["kind"] == "torso":
                self.assertEqual(decode_tset_levels(decoded)[0][0].rgba, _rgba(torso, EDITS[torso.asset_id]))
        self.assertEqual(kinds, {"torso", "uniform_equipment_texture"})

        # Back into the project it came from: identical content is skipped.
        revision = a.mutation_revision
        again = facade_a.import_team_kit(kit, lambda *args: None)
        self.assertEqual((again.imported_count, again.changed_count), (0, 0))
        self.assertEqual({row.decision for row in again.components}, {"skipped_unchanged"})
        self.assertEqual(a.mutation_revision, revision)

    def test_destination_edit_is_still_preserved_from_an_untouched_kit(self):
        facade_a, a = self.studio("source")
        torso = self.catalog.get_asset("nfl2k5.uniform.18h0.torso")
        path = self.root / "a.png"
        path.write_bytes(_png(torso, (1, 2, 3, 255)))
        a.replace(torso, path)
        kit = self.root / "kit"
        facade_a.export_team_kit_sets(("18H0",), kit, progress=lambda *args: None, container="folder")
        # The same project changes the torso again after the export.
        path.write_bytes(_png(torso, (9, 9, 9, 255)))
        a.replace(torso, path)
        result = facade_a.import_team_kit(kit, lambda *args: None)
        row = next(row for row in result.components if row.asset_id == torso.asset_id)
        self.assertEqual(row.decision, "skipped_baseline")
        self.assertEqual(a.asset_io.validate_replacement(torso, a.current_path(torso))[1],
                         _rgba(torso, (9, 9, 9, 255)))


if __name__ == "__main__":
    unittest.main()
