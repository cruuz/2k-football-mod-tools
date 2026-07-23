"""Retail-free receipt for the bounded APF stadium material experiment."""

from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from mod_editor.apf_studio.stadium_material_findings import (
    StadiumMaterialFindingsError,
    load_stadium_material_findings,
)


FINDINGS = (
    Path(__file__).resolve().parents[2]
    / "mod_editor"
    / "data"
    / "apf2k8_stadium_material_findings.v1.json"
)


class ApfStadiumMaterialFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = FINDINGS.read_text(encoding="utf-8")
        self.document = json.loads(self.payload)

    def test_records_the_completed_negative_ownership_experiment(self) -> None:
        self.assertEqual(
            self.document["schema"],
            "apf2k8_mod_studio_stadium_material_findings/v1",
        )
        self.assertEqual(self.document["outcome"], "texture_owner_unresolved")
        experiment = self.document["experiment"]
        self.assertEqual(experiment["scene_mesh_nodes"], 116)
        self.assertEqual(experiment["draw_records"], 328)
        self.assertEqual(experiment["serialized_material_records"], 113)
        self.assertEqual(experiment["shader_family_records"], 13)
        self.assertEqual(
            (experiment["minimum_material_slot"], experiment["maximum_material_slot"]),
            (0, 112),
        )
        self.assertEqual(experiment["out_of_range_material_slots"], 0)
        self.assertEqual(experiment["known_named_texture_identities_checked"], 737)
        self.assertEqual(
            experiment["named_texture_identity_matches_in_scene_system_part"], 0
        )
        self.assertEqual(experiment["same_package_named_texture_candidates"], 3)
        self.assertEqual(
            experiment["same_package_identity_matches_in_scene_system_part"], 0
        )

    def test_withholds_texture_actions_and_names_the_runtime_join(self) -> None:
        proof = self.document["proved"]
        self.assertTrue(proof["draw_to_serialized_material_slot"])
        self.assertTrue(proof["material_slot_to_serialized_material_record"])
        self.assertTrue(proof["serialized_material_to_shader_family"])
        self.assertFalse(proof["mesh_to_named_texture_identity"])
        self.assertFalse(proof["texture_writer_safe_to_expose"])
        runtime_capture = self.document["runtime_capture"]
        self.assertEqual(
            runtime_capture["outcome"], "host_breakpoint_intercepted"
        )
        self.assertFalse(runtime_capture["game_frame_rendered"])
        self.assertFalse(runtime_capture["guest_registers_captured"])
        self.assertTrue(runtime_capture["configuration_restored"])
        self.assertEqual(len(self.document["missing_runtime_fields"]), 4)
        next_experiment = self.document["best_next_experiment"]
        for required in (
            "material-array base",
            "pixel-shader mapping",
            "texture-object pointer",
            "guest allocation",
        ):
            self.assertIn(required, next_experiment)

    def test_payload_contains_no_retail_bytes_or_research_provenance(self) -> None:
        lowered = self.payload.casefold()
        self.assertLess(FINDINGS.stat().st_size, 8_000)
        self.assertIsNone(re.search(r"0x[0-9a-f]+", self.payload, re.IGNORECASE))
        for forbidden in (
            "sha256",
            "source_report",
            "retail_file",
            "outer_index",
            "inner_index",
            "system_offset",
            "extracted/",
        ):
            self.assertNotIn(forbidden, lowered)


class ApfStadiumMaterialFindingsLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(FINDINGS.read_text(encoding="utf-8"))

    def _write(self, root: Path, name: str, document: object) -> Path:
        path = root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_loads_immutable_product_boundary_and_author_summary(self) -> None:
        findings = load_stadium_material_findings()
        self.assertEqual(findings.outcome, "texture_owner_unresolved")
        self.assertEqual(findings.experiment["draw_records"], 328)
        self.assertTrue(findings.proof["serialized_material_to_shader_family"])
        self.assertFalse(findings.proof["mesh_to_named_texture_identity"])
        self.assertFalse(findings.proof["texture_writer_safe_to_expose"])
        self.assertEqual(
            findings.runtime_capture["outcome"], "host_breakpoint_intercepted"
        )
        self.assertEqual(len(findings.missing_runtime_fields), 4)
        self.assertIn("116 scene meshes and 328 draws", findings.author_summary)
        self.assertIn("737 known named texture identities", findings.author_summary)
        self.assertIn("Replace/Revert stays disabled", findings.author_summary)
        self.assertIn("did not test ownership", findings.author_summary)
        self.assertIn("material-array base", findings.best_next_experiment)
        with self.assertRaises(TypeError):
            findings.experiment["draw_records"] = 0  # type: ignore[index]

    def test_rejects_schema_addresses_and_research_provenance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-stadium-findings-") as directory:
            root = Path(directory)
            wrong_schema = json.loads(json.dumps(self.document))
            wrong_schema["schema"] = "wrong"
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "schema"):
                load_stadium_material_findings(
                    self._write(root, "wrong-schema.json", wrong_schema)
                )

            address = json.loads(json.dumps(self.document))
            address["note"] = "inspect 0x1234"
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "raw address"):
                load_stadium_material_findings(
                    self._write(root, "address.json", address)
                )

            provenance = json.loads(json.dumps(self.document))
            provenance["source_report"] = "private"
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "provenance"):
                load_stadium_material_findings(
                    self._write(root, "provenance.json", provenance)
                )

    def test_rejects_changed_counts_proofs_and_incomplete_next_experiment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-stadium-findings-") as directory:
            root = Path(directory)
            changed_count = json.loads(json.dumps(self.document))
            changed_count["experiment"]["draw_records"] = 329
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "counts"):
                load_stadium_material_findings(
                    self._write(root, "count.json", changed_count)
                )

            changed_proof = json.loads(json.dumps(self.document))
            changed_proof["proved"]["mesh_to_named_texture_identity"] = True
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "booleans"):
                load_stadium_material_findings(
                    self._write(root, "proof.json", changed_proof)
                )

            changed_runtime = json.loads(json.dumps(self.document))
            changed_runtime["runtime_capture"]["guest_registers_captured"] = True
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "capture"):
                load_stadium_material_findings(
                    self._write(root, "runtime.json", changed_runtime)
                )

            missing_join = json.loads(json.dumps(self.document))
            missing_join["best_next_experiment"] = "Capture one runtime value."
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "incomplete"):
                load_stadium_material_findings(
                    self._write(root, "next.json", missing_join)
                )


if __name__ == "__main__":
    unittest.main()
