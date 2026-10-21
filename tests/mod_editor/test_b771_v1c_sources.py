"""v0.6 source composition and selection regression, with public-pack fixtures."""
from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import modpack_sources as sources
from tools import nfl2k5_visual_mod_project as compiler
from tools.nfl_live_numbers_nameplate_targets import normalize_selector

PACK = Path(os.environ.get("B771_V06_PACK", "/home/noah/2k-worktrees/.b77-scratch/g2p/release/SOFTDRINK-2K28-v0.6.2k5patch"))


def target(edit):
    return normalize_selector(edit["asset_code"], edit["side"], edit["variant"], edit["family"], edit["digit"])


def document(edits):
    return dict(schema=compiler.SCHEMA, purpose="V1C selection regression", edits=edits)


class CompositionTests(unittest.TestCase):
    def test_export_and_legacy_materialization_keep_only_the_winning_target(self):
        from mod_editor.core import modpack_files as files
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            art = root / "art.png"
            art.write_bytes(b"author art, not native disc data")
            edit = dict(kind="live_number_nameplate", asset_code="16", side="H", variant=0,
                        family="jersey", digit=0, png=str(art))
            original = document([edit, dict(edit, family="jersey_digit")])
            project = root / "original.json"
            project.write_bytes(compiler.canonical_json(original))
            recipe = root / "recipe.json"
            recipe.write_text(json.dumps(dict(preset="softdrink_experimental", overrides={},
                freeze=dict(project=dict(path=str(project))))) + "\n", newline="\n")
            portable, assets = sources.prepare(recipe, root / "stage")
            self.assertEqual(len(json.loads(assets["assets/documents/league-project.json"].read_text())["edits"]), 1)
            bundle = root / "sources.2k5sources"
            identity = sources.write_bundle(bundle, portable, assets)
            local_root = root / "local"
            extracted = sources.extract_bundle(bundle, local_root, identity)
            # Simulate an already shipped archive: its portable project still
            # contains the legacy aliases when materialize opens it.
            legacy = json.loads(assets["assets/documents/league-project.json"].read_text())
            legacy["edits"].append(dict(legacy["edits"][0], family="jersey_digit"))
            (local_root / "assets/documents/league-project.json").write_text(json.dumps(legacy) + "\n", newline="\n")
            materialized = sources.materialize(extracted, local_root)
            fixed = compiler.read_project(Path(materialized["project"]))
            self.assertEqual(len(fixed.value["edits"]), 1)
            self.assertEqual(project.read_bytes(), compiler.canonical_json(original))
            self.assertEqual(Path(materialized["original_project"]).read_bytes(), project.read_bytes())

    def test_aliases_last_complete_layer_wins_and_input_is_unchanged(self):
        old = dict(kind="live_number_nameplate", asset_code="16", side="H", variant=0,
                   family="jersey", digit=0, png="old.png")
        new = dict(old, family="jersey_digit", png="new.png")
        original = document([old, dict(old, digit=1), new])
        before = json.dumps(original)
        fixed = sources.compose_project(original)
        self.assertEqual([e["png"] for e in fixed["edits"]], ["old.png", "new.png"])
        self.assertEqual([e["digit"] for e in fixed["edits"]], [1, 0])
        self.assertEqual(json.dumps(original), before)
        self.assertEqual(sources.compose_project(fixed), fixed)

    def test_importer_alias_contract_and_invalid_selectors(self):
        for short, aliases in (("jersey", ("plain", "jersey_digit")),
                               ("arm", ("shoulder", "arm_digit")),
                               ("helmet", ("helmet_digit",))):
            for alias in aliases:
                edits = [dict(kind="live_number_nameplate", asset_code="16", side=side, variant=0,
                              family=family, digit=2, png=family + ".png")
                         for side, family in (("H", short), ("home", alias))]
                fixed = sources.compose_project(document(edits))["edits"]
                self.assertEqual(len(fixed), 1)
                self.assertEqual(fixed[0]["family"], short)
                self.assertEqual(fixed[0]["side"], "H")
        bad = dict(edits[0], digit=10)
        with self.assertRaises(ValueError):
            sources.compose_project(document([bad]))

    def test_duplicate_aliases_fail_during_preflight(self):
        edit = dict(kind="live_number_nameplate", asset_code="16", side="H", variant=0,
                    family="jersey", digit=0, png="art.png")
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "project.json"
            project.write_bytes(compiler.canonical_json(document([edit, dict(edit, family="jersey_digit")])))
            with self.assertRaisesRegex(ValueError, "including family aliases"):
                compiler.read_project(project)

    def test_existing_source_selection_dialog_composes_before_checkboxes(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        try:
            from PyQt5.QtWidgets import QApplication
            from mod_editor.gui.modpack_sources_qt import SourceSelection
        except ImportError:
            self.skipTest("PyQt5 required for offscreen source selection")
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy.json"
            edit = dict(kind="live_number_nameplate", asset_code="16", side="H", variant=0,
                        family="jersey", digit=0, png="old.png")
            path.write_bytes(compiler.canonical_json(document([edit, dict(edit, family="jersey_digit", png="new.png")])))
            dialog = SourceSelection(path)
            self.assertEqual(len(dialog.items), 1)
            out = Path(td) / "selection.json"
            self.assertEqual(dialog.save(out), 1)
            self.assertEqual(compiler.read_project(out).value["edits"][0]["png"], "new.png")
            dialog.close()


@unittest.skipUnless(PACK.is_file(), "public v0.6 pack fixture required (B771_V06_PACK)")
class RealPackSelections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with zipfile.ZipFile(PACK) as archive:
            cls.original = json.loads(archive.read("assets/documents/league-project.json"))
        cls.fixed = sources.compose_project(cls.original)

    def test_real_collision_count_and_last_layer_provenance(self):
        self.assertEqual(len(self.original["edits"]), 11540)
        self.assertEqual(len(self.fixed["edits"]), 11200)
        before = [e for e in self.original["edits"] if e["kind"] == "live_number_nameplate"]
        self.assertEqual(len(before) - len({target(e) for e in before}), 340)
        winners = {target(e): e["png"] for e in before}
        after = [e for e in self.fixed["edits"] if e["kind"] == "live_number_nameplate"]
        self.assertEqual({target(e): e["png"] for e in after}, winners)
        self.assertEqual(sources.compose_project(self.fixed), self.fixed)

    def test_every_partial_selection_has_unique_native_digit_targets(self):
        # This proves the collision property for all 2**11200 subsets without
        # pretending to enumerate them: each target has exactly one writer in
        # the full set. Deleting any edits cannot introduce a second writer.
        seen = set()
        for index, edit in enumerate(self.fixed["edits"]):
            compiler.validate_edit_shape(edit, index)
            if edit["kind"] == "live_number_nameplate":
                key = target(edit)
                self.assertNotIn(key, seen)
                seen.add(key)
        self.assertEqual(len(seen), len([e for e in self.fixed["edits"] if e["kind"] == "live_number_nameplate"]))

    def test_partial_selections_use_the_actual_project_compiler_preflight(self):
        # Enumerate all combinations of the digit family checkboxes, plus the
        # reported NE target alone, all digits, and a few unchecked art items.
        digits = [e for e in self.fixed["edits"] if e["kind"] == "live_number_nameplate"]
        families = sorted({e["family"] for e in digits})
        selections = [[e for e in digits if e["family"] in chosen]
                      for n in range(1, len(families) + 1) for chosen in itertools.combinations(families, n)]
        selections += [[e for e in digits if target(e) == ("16", "H", 0, "jersey_digit", 0)],
                       self.fixed["edits"][7:], self.fixed["edits"]]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "project.json"
            for selected in selections:
                path.write_bytes(compiler.canonical_json(document(selected)))
                compiled = compiler.read_project(path)
                self.assertEqual(len(compiled.value["edits"]), len(selected))
                self.assertEqual(compiler.compile_dependency_groups(compiled.value["edits"]),
                                 compiler.compile_dependency_groups(selected))

    def test_each_real_colliding_target_compiles_its_winning_art(self):
        index = Path(os.environ.get("B771_RETAIL_INDEX", "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
        report = compiler.REPORTS["live_number_nameplate"]
        if not index.is_file() or not report.is_file():
            self.skipTest("private retail index and hydrated target report required")
        counts = {}
        for edit in self.original["edits"]:
            if edit["kind"] == "live_number_nameplate":
                key = target(edit)
                counts[key] = counts.get(key, 0) + 1
        colliding = {key for key, count in counts.items() if count > 1}
        rows = []
        from tools import nfl_live_numbers_nameplate_png_import as importer
        with zipfile.ZipFile(PACK) as archive, tempfile.TemporaryDirectory() as td:
            path = Path(td) / "art.png"
            for edit in self.fixed["edits"]:
                if edit["kind"] != "live_number_nameplate" or target(edit) not in colliding:
                    continue
                path.write_bytes(archive.read(edit["png"].removeprefix("@pack/")))
                try:
                    span, _preview, receipt = importer.build_import(index, report, edit["family"],
                        edit["asset_code"], edit["side"], edit["variant"], edit["digit"], path)
                    self.assertTrue(span)
                    rows.append(dict(target=target(edit), status="compiled", size=len(span)))
                except compiler.QualityBudgetError:
                    # The product explicitly keeps retail for this quality
                    # budget case. All other importer errors remain failures.
                    self.assertIn(edit["family"], compiler._KEPT_RETAIL_DIGIT_FAMILIES)
                    rows.append(dict(target=target(edit), status="kept_retail"))
        self.assertEqual(len(rows), 340)
        evidence = os.environ.get("B771_EVIDENCE")
        if evidence:
            (Path(evidence) / "real-digit-compilation.json").write_text(json.dumps(rows, indent=2) + "\n", newline="\n")


if __name__ == "__main__":
    unittest.main()
