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

    def test_records_the_completed_static_ownership_join(self) -> None:
        self.assertEqual(
            self.document["schema"],
            "apf2k8_mod_studio_stadium_material_findings/v1",
        )
        self.assertEqual(
            self.document["outcome"], "embedded_texture_ownership_proved"
        )
        experiment = self.document["experiment"]
        self.assertEqual(experiment["scene_surface_nodes"], 89)
        self.assertEqual(experiment["serialized_material_records"], 84)
        self.assertEqual(experiment["shader_family_records"], 20)
        self.assertEqual(experiment["embedded_texture_descriptors"], 78)
        self.assertEqual(experiment["material_slots_referenced"], 84)
        self.assertEqual(experiment["orphaned_material_slots"], 0)
        self.assertEqual(experiment["orphaned_embedded_textures"], 0)
        self.assertEqual(experiment["editable_texture_descriptors"], 78)
        self.assertEqual(experiment["retail_format_classes"], 8)

    def test_exposes_bounded_texture_actions_and_keeps_runtime_honest(self) -> None:
        proof = self.document["proved"]
        self.assertTrue(proof["draw_to_serialized_material_slot"])
        self.assertTrue(proof["material_slot_to_embedded_texture"])
        self.assertTrue(proof["all_embedded_textures_have_material_owners"])
        self.assertTrue(proof["full_declared_mip_transport_for_every_texture"])
        self.assertTrue(proof["fixed_allocation_copy_only_writer"])
        self.assertTrue(proof["texture_writer_safe_to_expose"])
        self.assertFalse(proof["runtime_visibility_proved"])
        runtime_capture = self.document["runtime_capture"]
        self.assertEqual(runtime_capture["outcome"], "offline_writer_proved")
        self.assertFalse(runtime_capture["emulator_used"])
        self.assertTrue(runtime_capture["source_opened_read_only"])
        self.assertTrue(runtime_capture["copied_output_reopened"])
        self.assertEqual(len(self.document["missing_runtime_fields"]), 3)
        next_experiment = self.document["best_next_experiment"]
        for required in ("Xbox 360 hardware", "additional stadium scene"):
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
        self.assertEqual(findings.outcome, "embedded_texture_ownership_proved")
        self.assertEqual(findings.experiment["embedded_texture_descriptors"], 78)
        self.assertTrue(findings.proof["material_slot_to_embedded_texture"])
        self.assertTrue(findings.proof["texture_writer_safe_to_expose"])
        self.assertFalse(findings.proof["runtime_visibility_proved"])
        self.assertEqual(findings.runtime_capture["outcome"], "offline_writer_proved")
        self.assertEqual(len(findings.missing_runtime_fields), 3)
        self.assertIn("89 exact scene surfaces", findings.author_summary)
        self.assertIn("all 78 embedded textures", findings.author_summary)
        self.assertIn("Replace, Revert", findings.author_summary)
        self.assertIn("Runtime visibility", findings.author_summary)
        self.assertIn("Xbox 360 hardware", findings.best_next_experiment)
        with self.assertRaises(TypeError):
            findings.experiment["scene_surface_nodes"] = 0  # type: ignore[index]

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
            changed_count["experiment"]["scene_surface_nodes"] = 90
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "counts"):
                load_stadium_material_findings(
                    self._write(root, "count.json", changed_count)
                )

            changed_proof = json.loads(json.dumps(self.document))
            changed_proof["proved"]["runtime_visibility_proved"] = True
            with self.assertRaisesRegex(StadiumMaterialFindingsError, "booleans"):
                load_stadium_material_findings(
                    self._write(root, "proof.json", changed_proof)
                )

            changed_runtime = json.loads(json.dumps(self.document))
            changed_runtime["runtime_capture"]["emulator_used"] = True
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
