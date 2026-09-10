"""Composition, project and actual Build dispatcher regressions for APF wave 1."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import build, coverage_service, play_design_service, scheme_service
from mod_editor.apf_studio.models import ApfSource, Modification
from mod_editor.apf_studio.session import ApfSession, SessionError
from mod_editor.apf_studio.project import load_project, ProjectError, _validated_metadata
from mod_editor.core import apf2k8_coverage_tuning as coverage
from mod_editor.core import apf2k8_scheme_presets as presets
from mod_editor.core import apf2k8_audibles as audibles
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError

ROOT = Path(__file__).resolve().parents[2]
INDEX = Path(os.environ.get("APF_RETAIL_INDEX", "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"))


class ProviderBoundaryTests(unittest.TestCase):
    def test_final_book_identity_failure_cleans_staging_without_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            (game / "0A").write_bytes(b"synthetic pack")
            (game / "default.xex").write_bytes(b"synthetic executable")
            tree = {p.name: (p.stat().st_size, hashlib.sha256(p.read_bytes()).hexdigest()) for p in game.iterdir()}
            digest = tree["0A"][1]
            source = ApfSource(game, game, game / "0A", digest, tree["0A"][0], tree["default.xex"][1], "Synthetic")
            def refuse(index):
                self.assertNotEqual(index, source.index_0a)
                self.assertEqual(index.read_bytes(), b"synthetic pack")
                raise ValidationError("Final ROST identity is invalid")
            with patch.object(build, "EXPECTED_TREE", tree), patch.object(build, "EXPECTED_0A_SHA256", digest), \
                    patch.object(build.apf_outer, "parse_archive", return_value=SimpleNamespace(entries=())), \
                    patch.object(build.ApfBuildService, "_verify_composed", return_value=digest), \
                    patch.object(build, "disc_book_identity_report", side_effect=refuse) as identity:
                with self.assertRaisesRegex(build.BuildError, "Book Identity reparse failed"):
                    build.ApfBuildService(source).build((), root / "output")
            identity.assert_called_once()
            self.assertFalse((root / "output").exists())
            self.assertFalse(list(root.glob(".output.building-*")))
            self.assertEqual(hashlib.sha256(source.index_0a.read_bytes()).hexdigest(), digest)

    def test_every_conflict_names_both_features_before_build_compiles_or_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / "game"
            game.mkdir()
            source = ApfSource(game, game, game / "0A", build.EXPECTED_0A_SHA256, 0, "b" * 64, "Synthetic")
            design = Modification("design", "apf_play_design", root / "absent.json", "a" * 64, {})
            for kind in ("formation_package_map", "play_assignment_route", "formation_alignment",
                         "splb_book_membership", "coverage_geometry", "apf_scheme_presets"):
                with self.subTest(kind=kind), patch.object(build, "sha256_file", return_value=build.EXPECTED_0A_SHA256), \
                        patch.object(build, "_require_build_space"), patch.object(build, "_copy_regular") as copy, \
                        patch.object(play_design_service, "compile_modification") as compile_design:
                    other = Modification("other", kind, root / "absent2.json", "c" * 64, {})
                    with self.assertRaisesRegex(build.BuildError, "apf_play_design.*" + kind):
                        build.ApfBuildService(source).build((design, other), root / "output")
                    self.assertFalse((root / "output").exists())
                    self.assertFalse(list(root.glob(".output.building-*")))
                    copy.assert_not_called()
                    compile_design.assert_not_called()

    def test_profile_identity_and_duplicate_recipe_keys_fail_closed(self):
        for kind, selector, schema in ((coverage.PROVIDER_KIND, coverage.PROFILE_ASSET_ID, coverage.PROFILE_SCHEMA),
                                       (scheme_service.PROVIDER_KIND, scheme_service.SELECTOR, scheme_service.SCHEMA)):
            with self.subTest(kind=kind), self.assertRaises(ProjectError):
                _validated_metadata(selector, kind, {"schema": schema, "unchecked_values": []})
        with self.assertRaisesRegex(ValidationError, "Duplicate"):
            scheme_service.validate_payload(b'{"schema":1,"schema":2}', scheme_service.SELECTOR,
                                            {"schema": scheme_service.SCHEMA})


@unittest.skipUnless(INDEX.is_file(), "Set APF_RETAIL_INDEX to the user-owned retail 0A")
class RetailIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="apf-wave-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = ApfSource(INDEX.parent, INDEX.parent, INDEX, build.EXPECTED_0A_SHA256,
                                INDEX.stat().st_size, "b" * 64, "APF retail")
        self.session = ApfSession(self.source, SimpleNamespace(), cache_root=self.root / "cache")

    def test_coverage_roundtrip_undo_revert_and_composed_preview(self):
        from mod_editor.core.apf2k8_playbook_route_writer import RouteCloneRequest
        self.session.apply_coverage_geometry((coverage.ZoneEdit(3223, lateral_extent_yards=8),))
        defaults, rows, edits, report = self.session.coverage_context()
        self.assertEqual(next(r for r in defaults if r["node_index"] == 3223)["lateral_extent_yards"], 6)
        self.assertEqual(next(r for r in rows if r["node_index"] == 3223)["lateral_extent_yards"], 8)
        path = self.root / "coverage.apf2k8mod"
        self.session.save_project(path)
        self.session.load_project(path)
        self.assertEqual(self.session.coverage_context()[2], edits)
        modification = self.session.modifications[0]
        outer, entry, row = build.ApfBuildService(self.source)._compile_master_play_edits(coverage_profiles=(modification,))
        self.assertEqual(outer, 180)
        self.assertEqual(len(entry), 57344)
        self.assertEqual(row["coverage"]["replacement_sha256"], report["replacement_sha256"])
        # Shared-use count changes after a stock assignment clone while all tuned
        # nodes survive. Find a safe stock request without inventing a new chain.
        request = RouteCloneRequest(278, 9, 279, 9)
        self.session.apply_play_assignment_route_batch((request,))
        _, final_rows, _, combined = self.session.coverage_context()
        self.assertTrue(combined["composition"]["tuned_node_pool_preserved"])
        self.assertEqual(combined["composition"]["order"], ["coverage", "package_maps", "route_clones"])
        self.assertEqual(len(final_rows), 368)
        self.assertTrue(self.session.revert(coverage.PROFILE_ASSET_ID))
        self.assertFalse(self.session.coverage_context()[2])
        self.assertTrue(self.session.undo())
        self.assertEqual(self.session.coverage_context()[2], edits)
        self.session.apply_coverage_geometry(())
        self.assertFalse(self.session.coverage_context()[2])

    def test_rejected_coverage_does_not_record_undo_or_store_payload(self):
        before = set(self.session.replacements_root.glob("*"))
        with self.assertRaises(SessionError):
            self.session.apply_coverage_geometry((coverage.ZoneEdit(3223, lateral_extent_yards=16),))
        self.assertEqual(set(self.session.replacements_root.glob("*")), before)
        self.assertFalse(self.session.undo())
        self.assertEqual(self.session.modified_count, 0)

    def test_crest_detail_survives_project_import_directory_cleanup(self):
        from PIL import Image
        from mod_editor.apf_studio.helmet_crest_design import RETAIL_CREST_PROFILE
        from mod_editor.apf_studio.backend import ensure_tools_importable
        ensure_tools_importable()
        import apf_team_crests
        slot = apf_team_crests.crest_slots(INDEX)[0]
        paths = (self.root / "l0.png", self.root / "l1.png")
        for path, color in zip(paths, ((255, 0, 0, 255), (0, 255, 0, 255))):
            Image.new("RGBA", (512, 512), color).save(path)
        modification = self.session.replace_helmet_crest_design(
            paths[0], detail_png=paths[1], profile=RETAIL_CREST_PROFILE,
            crest_asset_index=slot.asset_index, crest_outer_entry_index=slot.outer_entry_index)
        project = self.root / "paired.apf2k8mod"
        self.session.save_project(project)
        # Use a fresh session, so the original cached detail cannot mask a bug.
        restored = ApfSession(self.source, SimpleNamespace(), cache_root=self.root / "restored")
        restored.load_project(project)
        result = restored.modifications[0]
        detail = build.ApfBuildService._crest_detail_path(result)
        self.assertTrue(detail.is_relative_to(restored.replacements_root))
        self.assertEqual(hashlib.sha256(detail.read_bytes()).hexdigest(), modification.metadata["detail_sha256"])
        self.assertFalse(list(restored.working_root.glob("import-*")))
        self.assertNotEqual(detail.read_bytes(), result.replacement_path.read_bytes())

    def test_presets_compose_after_audibles_and_roundtrip(self):
        outer = next(i for i in audibles.CPU_OFFENSE_BOOKS if splb.STOCK_BOOKS[i] == "O-ZoneBlock")
        plan = audibles.plan_audibles(splb.read_book(INDEX, outer), audibles.play_catalog(self.session._master_play_body()))
        self.session.apply_splb_membership_batch(plan.changes, replace_outer=outer)
        before = self.session.staged_splb_changes()
        reports = self.session.apply_scheme_presets(("wide-zone",))
        self.assertEqual(reports[0]["composition"]["prior_selectors"], [c.selector for c in before])
        self.assertEqual(reports[0]["composition"]["order"], ["fine_tune_and_audible_selectors", "scheme_preset"])
        self.assertEqual(len(reports[0]["personnel_availability"]["after"]["categories"]), 28)
        path = self.root / "schemes.apf2k8mod"
        self.session.save_project(path)
        self.session.load_project(path)
        self.assertEqual(self.session.staged_splb_changes(), before)
        self.assertTrue(self.session.revert(scheme_service.SELECTOR))
        self.assertEqual(self.session.staged_splb_changes(), before)

    def test_designer_example_uses_actual_build_dispatcher_and_three_entries(self):
        plan = json.loads((ROOT / "docs/research/apf_play_design_example.json").read_text())
        self.session.apply_play_design(plan)
        modification = self.session.modifications[0]
        # Execute the real dispatcher, stop exactly at the publication boundary.
        # The separate integration replay builds and hashes full retail copies.
        with patch.object(build.ApfBuildService, "_normalize_compiled_spans", side_effect=StopBeforeCopy) as boundary, \
                patch.object(build, "_copy_regular") as copying:
            with self.assertRaises(StopBeforeCopy):
                build.ApfBuildService(self.source).build((modification,), self.root / "output")
        spans = boundary.call_args.args[0]
        self.assertEqual({s.outer_index for s in spans}, {180, 259, 618})
        self.assertTrue(all(s.kind == "apf_play_design" and s.reparse_owner for s in spans))
        copying.assert_not_called()
        self.assertFalse((self.root / "output").exists())


class StopBeforeCopy(Exception):
    pass


if __name__ == "__main__":
    unittest.main()
