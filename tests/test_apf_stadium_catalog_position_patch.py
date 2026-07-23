#!/usr/bin/env python3
"""Unit and refusal tests for APF catalog-backed POSITION0 write-back."""

from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_stadium_catalog_position_patch as writer  # noqa: E402
import apf_stadium_catalog_position_verify as verifier  # noqa: E402


SAMPLE = ROOT / "reports/asset_samples/apf_scene/stadium_node3_nonretail_zero_recipe.json"
GAME_DIR = ROOT / "extracted/All-Pro Football 2K8 (USA)"


class CatalogPositionTests(unittest.TestCase):
    def _recipe(self):
        return json.loads(SAMPLE.read_bytes())

    def _write(self, directory: Path, value, name="recipe.json"):
        path = directory / name
        path.write_bytes(writer.canonical_json_bytes(value))
        return path

    def test_nonretail_node3_sample_is_canonical_exact_24_float3(self):
        recipe, raw, packed, target = writer.load_recipe(SAMPLE)
        self.assertEqual(raw, writer.canonical_json_bytes(recipe))
        self.assertEqual(target["candidate_id"], "outer14.inner8.node3")
        self.assertEqual(len(packed), 24 * 12)
        self.assertEqual(packed, bytes(24 * 12))
        self.assertEqual(verifier._load_recipe(SAMPLE)[2], packed)

    def test_catalog_dispatches_77_hash_only_targets_and_node3_layout(self):
        catalog, targets = writer.load_catalog()
        self.assertEqual(len(targets), 77)
        self.assertIs(catalog["contains_retail_vertex_values"], False)
        target = targets["outer14.inner8.node3"]
        self.assertEqual(writer._target_layout(target), (24, 348988, 24, 0))
        self.assertEqual(target["draw_records"]["count"], 3)

    def test_recipe_refuses_wrong_catalog_hash_target_count_round_bool_and_extra(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            cases = []
            wrong_hash = self._recipe()
            wrong_hash["catalog"]["sha256"] = "0" * 64
            cases.append(wrong_hash)
            wrong_target = self._recipe()
            wrong_target["target_id"] = "outer14.inner8.node17"
            cases.append(wrong_target)
            wrong_count = self._recipe()
            wrong_count["positions"] = wrong_count["positions"][:-1]
            cases.append(wrong_count)
            rounded = self._recipe()
            rounded["positions"][0][0] = 0.1
            cases.append(rounded)
            boolean = self._recipe()
            boolean["positions"][0][0] = True
            cases.append(boolean)
            extra = self._recipe()
            extra["unexpected"] = 1
            cases.append(extra)
            for index, value in enumerate(cases):
                path = self._write(directory, value, f"case{index}.json")
                with self.assertRaises((writer.PatchError, verifier.VerifyError)):
                    writer.load_recipe(path)
                with self.assertRaises((writer.PatchError, verifier.VerifyError)):
                    verifier._load_recipe(path)

    def test_recipe_refuses_duplicate_nan_and_noncanonical_json(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            duplicate = directory / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "duplicate"):
                writer.load_recipe(duplicate)
            with self.assertRaisesRegex(verifier.VerifyError, "duplicate"):
                verifier._load_recipe(duplicate)
            nan = directory / "nan.json"
            nan.write_text('{"positions":[[NaN,0,0]]}\n', encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "non-JSON"):
                writer.load_recipe(nan)
            noncanonical = directory / "noncanonical.json"
            noncanonical.write_text(json.dumps(self._recipe()), encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "canonical"):
                writer.load_recipe(noncanonical)

    def test_dynamic_lane_helpers_preserve_every_non_position_byte(self):
        target = {
            "position0": {"vertex_count": 3, "stream_start": 5, "stream_stride": 20, "byte_offset": 4}
        }
        source = bytes(range(80))
        changed = bytearray(source)
        for vertex in range(3):
            lane = 5 + vertex * 20 + 4
            changed[lane : lane + 12] = struct.pack(">3f", float(vertex), 2.0, 3.0)
        self.assertNotEqual(writer._position_payload(source, target), writer._position_payload(bytes(changed), target))
        self.assertEqual(writer._non_position_system_hash(source, target), writer._non_position_system_hash(bytes(changed), target))
        self.assertEqual(writer._stream_complement_hash(source, target), writer._stream_complement_hash(bytes(changed), target))

    def test_verifier_module_imports_no_writer(self):
        tree = ast.parse((ROOT / "tools/apf_stadium_catalog_position_verify.py").read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        self.assertNotIn("apf_stadium_catalog_position_patch", imported)
        self.assertNotIn("apf_stadium_static_position_patch", imported)

    def test_structural_span_set_covers_node_attachment_draw_topology_and_descriptor(self):
        target = writer.load_catalog()[1]["outer14.inner8.node3"]
        self.assertEqual(
            set(writer._structural_spans(target)),
            {"node_record", "matrix_slot", "hierarchy", "draw_records", "index_topology", "declarations", "mesh_descriptor_and_stream_records"},
        )

    def test_claims_stay_offline_same_count_and_nonproduction(self):
        claims = writer.copy_claims()
        self.assertIs(claims["catalog_backed_dispatcher_implemented"], True)
        self.assertIs(claims["same_count_position_only"], True)
        for key in ("changed_topology_proved", "rigid_attachment_proved", "emulator_runtime_visibility_proved", "xbox_360_hardware_proved", "production_mesh_importer_proved"):
            self.assertIs(claims[key], False)
        self.assertEqual(claims, verifier._claims())

    def test_h7a_capacity_refuses_one_byte_over_fixed_catalog_maximum(self):
        catalog = writer.load_catalog()[0]
        writer._validate_stored0_capacity(3_301_108, catalog)
        with self.assertRaisesRegex(writer.PatchError, "exceeds"):
            writer._validate_stored0_capacity(3_301_109, catalog)
        drift = copy.deepcopy(catalog)
        drift["container"]["h7a_rebuild_envelope"]["maximum_stored_block0_bytes"] += 1
        with self.assertRaisesRegex(writer.PatchError, "drift"):
            writer._validate_stored0_capacity(3_299_082, drift)

    def test_writer_refuses_symlink_inputs_parent_and_existing_output(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as name:
            directory = Path(name)
            game_link = directory / "game"
            game_link.symlink_to(GAME_DIR, target_is_directory=True)
            with self.assertRaisesRegex(writer.PatchError, "game directory"):
                writer.write_output(game_link, SAMPLE, directory / "out1")
            recipe_link = directory / "recipe.json"
            recipe_link.symlink_to(SAMPLE)
            with self.assertRaisesRegex(writer.PatchError, "recipe"):
                writer.write_output(GAME_DIR, recipe_link, directory / "out2")
            real_parent = directory / "real"
            real_parent.mkdir()
            parent_link = directory / "parent"
            parent_link.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(writer.PatchError, "parent"):
                writer.write_output(GAME_DIR, SAMPLE, parent_link / "out3")
            existing = directory / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(writer.PatchError, "existing"):
                writer.write_output(GAME_DIR, SAMPLE, existing)

    def test_verification_artifact_refuses_output_directory_and_existing_path(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            output = directory / "output"
            output.mkdir()
            with self.assertRaisesRegex(verifier.VerifyError, "outside"):
                verifier.archive._write_artifact(output / "verify.json", {"schema": "test"}, output)
            existing = directory / "existing.json"
            existing.write_text("owned", encoding="utf-8")
            with self.assertRaisesRegex(verifier.VerifyError, "existing"):
                verifier.archive._write_artifact(existing, {"schema": "test"}, output)

    def test_publication_ownership_helper_rejects_rename_replacement(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            target = directory / "target"
            target.mkdir()
            metadata = os.lstat(target)
            identity = (metadata.st_dev, metadata.st_ino)
            self.assertTrue(writer.container._directory_path_matches(target, identity))
            target.rename(directory / "moved")
            target.mkdir()
            self.assertFalse(writer.container._directory_path_matches(target, identity))

    @unittest.skipUnless((GAME_DIR / "1A").is_file(), "retail APF fixture unavailable")
    def test_independent_verifier_refuses_source_output_hardlink_alias(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as name:
            output = Path(name) / "output"
            output.mkdir()
            os.link(GAME_DIR / "1A", output / "1A")
            (output / writer.MANIFEST_NAME).write_bytes(writer.canonical_json_bytes({"schema": "dummy"}))
            with self.assertRaisesRegex(verifier.VerifyError, "hardlink"):
                verifier.verify(GAME_DIR, SAMPLE, output)

    @unittest.skipUnless((GAME_DIR / "1A").is_file(), "retail APF fixture unavailable")
    def test_independent_node3_parser_rederives_retail_catalog_target(self):
        import apf_inner
        import apf_outer

        target = writer.load_catalog()[1]["outer14.inner8.node3"]
        outer = apf_outer.parse_archive(GAME_DIR / "0A")
        with apf_inner.ArchiveReader(outer) as reader:
            record = apf_inner.parse_iff(reader, outer.entries[14])
            system = apf_inner.decode_block(reader, record, 0, 1 << 30)[:writer.SYSTEM_LENGTH]
        parsed = verifier._parse_target_scne(system, target, True)
        self.assertEqual(parsed["positions"], writer._position_payload(system, target))
        self.assertEqual(len(parsed["positions"]), 288)


if __name__ == "__main__":
    unittest.main()
