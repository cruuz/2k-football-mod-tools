from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import tempfile
import unittest

from mod_editor.apf_studio.inspectors import export_semantic_rows
from mod_editor.apf_studio.product_findings import (
    PRODUCT_FINDINGS,
    ProductFindingsError,
    gameplay_snapshot,
    load_product_findings,
    presentation_snapshot,
)
from mod_editor.core.gameplay_inspection import (
    inspect_draft_priority,
    inspect_gameplay_sliders,
)
from mod_editor.core.presentation_inspection import (
    inspect_apf_scorebug_presentation,
)


RAW_ADDRESS = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)


class ProductFindingsParityTests(unittest.TestCase):
    def test_packaged_projection_matches_the_sanitized_core_contract(self) -> None:
        document = load_product_findings()
        gameplay = document["gameplay"]
        assert isinstance(gameplay, dict)
        sliders = inspect_gameplay_sliders("apf2k8")
        draft = inspect_draft_priority("apf2k8")
        presentation = inspect_apf_scorebug_presentation()

        self.assertEqual(
            gameplay["sliders"],
            [row["name"] for row in sliders["sliders"]],
        )
        self.assertEqual(gameplay["stock_ui_range"], sliders["stock_ui_range"])
        self.assertEqual(gameplay["platform_proof"], sliders["platform_proof"])
        for field in (
            "current_values_available",
            "observed_fixture_values_available",
            "save_or_profile_writer_available",
            "executable_writer_available",
            "out_of_range_runtime_safety_proved",
        ):
            self.assertEqual(gameplay[field], sliders[field])

        lineage = gameplay["draft_lineage"]
        assert isinstance(lineage, dict)
        self.assertEqual(lineage["position_weights"], draft["position_weights"])
        self.assertEqual(lineage["proof_status"], draft["proof_status"])
        self.assertEqual(
            lineage["safe_writer_available"], draft["safe_writer_available"]
        )
        self.assertEqual(
            lineage["runtime_patch_performed"], draft["runtime_patch_performed"]
        )

        product_presentation = document["presentation"]
        assert isinstance(product_presentation, dict)
        field = product_presentation["field_scorebug"]
        assert isinstance(field, dict)
        self.assertEqual(
            field["components"], presentation["field_scorebug"]["components"]
        )
        self.assertEqual(
            field["geometry_writer_available"],
            presentation["field_scorebug"]["geometry_writer_available"],
        )
        self.assertEqual(
            field["runtime_behavior_writer_available"],
            presentation["field_scorebug"]["runtime_behavior_writer_available"],
        )
        self.assertEqual(
            product_presentation["digital_font"], presentation["digital_font"]
        )
        self.assertEqual(
            product_presentation["safe_writer_count"],
            presentation["safe_writer_count"],
        )

    def test_projection_is_small_retail_free_and_has_no_research_provenance(self) -> None:
        payload = PRODUCT_FINDINGS.read_text(encoding="utf-8")
        lowered = payload.casefold()
        self.assertLess(PRODUCT_FINDINGS.stat().st_size, 20_000)
        self.assertIsNone(RAW_ADDRESS.search(payload))
        for forbidden in (
            "source_report",
            "source_reports",
            "sha256",
            "retail_file",
            "outer_index",
            "inner_index",
            "offset",
        ):
            self.assertNotIn(forbidden, lowered)

    def test_loader_rejects_wrong_schema_raw_addresses_and_changed_counts(self) -> None:
        document = json.loads(PRODUCT_FINDINGS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrong_schema = root / "wrong-schema.json"
            wrong_schema.write_text(
                json.dumps({**document, "schema": "wrong"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ProductFindingsError, "unsupported schema"):
                load_product_findings(wrong_schema)

            address = root / "address.json"
            address.write_text(
                json.dumps({**document, "note": "0x1234"}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ProductFindingsError, "raw address"):
                load_product_findings(address)

            changed = json.loads(json.dumps(document))
            changed["gameplay"]["sliders"].pop()
            with self.assertRaisesRegex(ProductFindingsError, "exactly 21"):
                gameplay_snapshot(changed)


class ProductFindingsModelTests(unittest.TestCase):
    def test_gameplay_model_is_38_read_only_searchable_rows(self) -> None:
        snapshot = gameplay_snapshot()
        self.assertEqual(
            snapshot.summary,
            {"sliders": 21, "draft_lineage_weights": 17, "editable_controls": 0},
        )
        self.assertEqual(len(snapshot.model.rows), 38)
        self.assertEqual(
            snapshot.model.kind_counts,
            {"draft_lineage_weight": 17, "gameplay_slider": 21},
        )
        catching = snapshot.model.get("apf:gameplay:slider:03")
        self.assertEqual(catching.title, "Human Catching")
        self.assertFalse(catching.fields["current_profile_value_available"])
        self.assertFalse(catching.fields["save_or_profile_writer_available"])
        self.assertFalse(catching.fields["out_of_range_runtime_safety_proved"])
        quarterback = snapshot.model.get("apf:gameplay:draft-lineage:qb")
        self.assertEqual(quarterback.fields["retained_weight"], 2.0)
        proof = quarterback.fields["proof_status"]
        assert isinstance(proof, dict)
        self.assertFalse(proof["cpu_selector_owner_proved"])
        self.assertEqual(len(snapshot.model.filtered_rows(search="catching")), 2)
        self.assertIn("not a live APF AI control", quarterback.subtitle)

    def test_presentation_model_is_seven_scenes_plus_font_boundary(self) -> None:
        snapshot = presentation_snapshot()
        self.assertEqual(
            snapshot.summary,
            {
                "scorebug_scene_components": 7,
                "bounded_texture_writers": 1,
                "semantic_rows": 8,
            },
        )
        self.assertEqual(len(snapshot.model.rows), 8)
        self.assertEqual(
            snapshot.model.kind_counts,
            {
                "digital_font_writer_boundary": 1,
                "scorebug_scene_component": 7,
            },
        )
        bottom = snapshot.model.get(
            "apf:presentation:component:scorebug_bottombar"
        )
        self.assertEqual(bottom.fields["mesh_count"], 46)
        self.assertEqual(bottom.fields["triangle_count"], 221)
        self.assertFalse(bottom.fields["geometry_writer_available"])
        font = snapshot.model.get("apf:presentation:digital_font")
        self.assertEqual(font.fields["dimensions"], [128, 128])
        self.assertTrue(font.fields["copy_only_writer_proved"])
        self.assertFalse(font.fields["runtime_visibility_proved"])

    def test_existing_json_and_csv_export_path_preserves_product_boundaries(self) -> None:
        gameplay = gameplay_snapshot()
        presentation = presentation_snapshot()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gameplay_json = export_semantic_rows(
                gameplay.model,
                root / "gameplay.json",
                kinds="gameplay_slider",
            )
            document = json.loads(gameplay_json.read_text(encoding="utf-8"))
            self.assertEqual(document["record_count"], 21)
            self.assertEqual(
                {row["kind"] for row in document["records"]},
                {"gameplay_slider"},
            )
            self.assertIsNone(RAW_ADDRESS.search(json.dumps(document)))

            presentation_csv = export_semantic_rows(
                presentation.model,
                root / "presentation.csv",
            )
            with presentation_csv.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 8)
            self.assertEqual(
                {row["kind"] for row in rows},
                {"scorebug_scene_component", "digital_font_writer_boundary"},
            )
            self.assertNotIn("outer_index", presentation_csv.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
