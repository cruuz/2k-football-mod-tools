#!/usr/bin/env python3
"""Synthetic, source-backed no-op, and refusal tests for APF node17 topology."""

from __future__ import annotations

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

import apf_scne_draw_topology_spec as spec_tool  # noqa: E402
import apf_stadium_node17_topology_patch as writer  # noqa: E402
import apf_stadium_node17_topology_verify as verifier  # noqa: E402


SAMPLE = ROOT / "reports/asset_samples/apf_scene/stadium_node17_nonretail_permuted_strip_recipe.json"
CORPUS = ROOT / "reports/assets/apf_scne_draw_topology_corpus.v1.json"
SPEC = ROOT / "reports/specs/apf2k8_scne_draw_topology.v1.json"
GAME_DIR = ROOT / "extracted/All-Pro Football 2K8 (USA)"


class ApfNode17TopologyPatchTests(unittest.TestCase):
    def recipe(self) -> dict[str, object]:
        return json.loads(SAMPLE.read_bytes())

    def write_recipe(self, directory: Path, value: dict[str, object], name: str) -> Path:
        path = directory / name
        path.write_bytes(writer.canonical_json_bytes(value))
        return path

    def test_public_recipe_is_canonical_nonretail_and_both_parsers_agree(self) -> None:
        recipe, raw, packed = writer.load_recipe(SAMPLE)
        independent, independent_raw, independent_packed = verifier._load_recipe(SAMPLE)
        self.assertEqual(recipe, independent)
        self.assertEqual(raw, independent_raw)
        self.assertEqual(packed, independent_packed)
        self.assertEqual(packed, bytes.fromhex("0000000200010003"))
        self.assertEqual(writer.expand_strip(recipe["indices"]), [0, 2, 1, 1, 2, 3])
        self.assertEqual(verifier.expand_strip(recipe["indices"]), [0, 2, 1, 1, 2, 3])

    def test_recipe_refuses_duplicate_restart_wrong_count_bool_extra_and_noncanonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            cases: list[tuple[str, dict[str, object]]] = []
            for name, indices in (
                ("duplicate", [0, 1, 1, 3]),
                ("restart", [0, 1, 2, 65535]),
                ("count", [0, 1, 2]),
                ("bool", [0, 1, 2, True]),
            ):
                value = self.recipe()
                value["indices"] = indices
                cases.append((name, value))
            extra = self.recipe()
            extra["unexpected"] = 1
            cases.append(("extra", extra))
            for name, value in cases:
                path = self.write_recipe(directory, value, f"{name}.json")
                with self.assertRaises((writer.PatchError, verifier.VerifyError), msg=name):
                    writer.load_recipe(path)
                with self.assertRaises((writer.PatchError, verifier.VerifyError), msg=name):
                    verifier._load_recipe(path)
            noncanonical = directory / "noncanonical.json"
            noncanonical.write_text(json.dumps(self.recipe()), encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "canonical"):
                writer.load_recipe(noncanonical)
            with self.assertRaisesRegex(verifier.VerifyError, "canonical"):
                verifier._load_recipe(noncanonical)

    def test_recipe_refuses_duplicate_json_keys_and_nan(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            duplicate = directory / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "duplicate"):
                writer.load_recipe(duplicate)
            with self.assertRaisesRegex(verifier.VerifyError, "duplicate"):
                verifier._load_recipe(duplicate)
            nan = directory / "nan.json"
            nan.write_text('{"indices":[0,1,2,NaN]}\n', encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "non-JSON"):
                writer.load_recipe(nan)
            with self.assertRaisesRegex(verifier.VerifyError, "non-JSON"):
                verifier._load_recipe(nan)

    def test_draw_record_semantics_are_exact_and_mutation_is_refused(self) -> None:
        system = bytearray(writer.DRAW_OFFSET + writer.DRAW_SIZE)
        struct.pack_into(">12I", system, writer.DRAW_OFFSET, 6, 0, 4, 2, 0, 0, 4, 0, 12, 0, 0, 1)
        self.assertEqual(
            writer.sha256_bytes(system[writer.DRAW_OFFSET : writer.DRAW_OFFSET + 48]),
            writer.DRAW_SHA256,
        )
        self.assertEqual(writer._draw_semantics(bytes(system))["vertex_range"], 4)
        struct.pack_into(">I", system, writer.DRAW_OFFSET + 0x18, 3)
        with self.assertRaisesRegex(writer.PatchError, "draw"):
            writer._draw_semantics(bytes(system))

    def test_corpus_and_normative_spec_are_canonical_and_complete(self) -> None:
        corpus = json.loads(CORPUS.read_bytes())
        spec = json.loads(SPEC.read_bytes())
        self.assertEqual(CORPUS.read_bytes(), spec_tool.canonical(corpus))
        self.assertEqual(SPEC.read_bytes(), spec_tool.canonical(spec))
        rebuilt = spec_tool.build_spec(corpus, spec_tool.DEFAULT_TRACE)
        self.assertEqual(spec, rebuilt)
        self.assertEqual(corpus["coverage"]["draw_records"], 47_112)
        self.assertEqual(corpus["coverage"]["serialized_indices"], 24_519_417)
        self.assertEqual(corpus["coverage"]["partitioned_nodes"], 13_006)
        self.assertTrue(all(corpus["proved_invariants"].values()))
        fields = {item["name"]: item for item in spec["draw_record"]["fields"]}
        self.assertEqual(fields["first_element"]["offset_bytes"], 4)
        self.assertEqual(fields["element_count"]["offset_bytes"], 8)
        self.assertEqual(fields["minimum_vertex"]["offset_bytes"], 0x14)
        self.assertEqual(fields["vertex_range"]["offset_bytes"], 0x18)
        self.assertFalse(spec["claim_flags"]["runtime_proved"])
        self.assertFalse(spec["claim_flags"]["hardware_proved"])

    def test_independent_verifier_imports_no_writer_parser_or_compressor(self) -> None:
        source = (ROOT / "tools/apf_stadium_node17_topology_verify.py").read_text(encoding="utf-8")
        for forbidden in (
            "import apf_stadium_node17_topology_patch",
            "import apf_scene",
            "import apf_inner",
            "compress_h7a",
        ):
            self.assertNotIn(forbidden, source)

    @unittest.skipUnless((GAME_DIR / "1A").is_file(), "retail APF fixture unavailable")
    def test_source_backed_noop_bypasses_rebuild_and_is_exact(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            value = copy.deepcopy(writer.RECIPE_CONSTANTS)
            value["indices"] = [0, 1, 2, 3]
            recipe = self.write_recipe(directory, value, "noop.json")
            original = writer.container._rebuild_entry
            writer.container._rebuild_entry = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no-op recompressed"))
            try:
                entry, manifest = writer.build_patch(GAME_DIR, recipe)
            finally:
                writer.container._rebuild_entry = original
            self.assertEqual(manifest["mode"], "no_op")
            self.assertFalse(manifest["result"]["h7a_block0_recompressed"])
            self.assertEqual(writer.sha256_bytes(entry), writer.container.OUTER_SHA256)

    def test_writer_refuses_symlink_inputs_and_existing_output_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory_name:
            directory = Path(directory_name)
            game_link = directory / "game"
            game_link.symlink_to(GAME_DIR, target_is_directory=True)
            with self.assertRaisesRegex(writer.PatchError, "game directory"):
                writer.write_output(game_link, SAMPLE, directory / "out1")
            recipe_link = directory / "recipe.json"
            recipe_link.symlink_to(SAMPLE)
            with self.assertRaisesRegex(writer.PatchError, "recipe"):
                writer.write_output(GAME_DIR, recipe_link, directory / "out2")
            existing = directory / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(writer.PatchError, "existing"):
                writer.write_output(GAME_DIR, SAMPLE, existing)

    def test_verification_artifact_refuses_inside_output_and_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            output = directory / "output"
            output.mkdir()
            with self.assertRaisesRegex(verifier.VerifyError, "outside"):
                verifier._write_artifact(output / "verify.json", {"schema": "test"}, output)
            existing = directory / "existing.json"
            existing.write_text("owned", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                verifier._write_artifact(existing, {"schema": "test"}, output)


if __name__ == "__main__":
    unittest.main()
