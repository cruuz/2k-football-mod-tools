from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_scne_static_format_spec as spec_tool  # noqa: E402


class NflScneStaticFormatSpecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads(spec_tool.DEFAULT_SPEC.read_text(encoding="utf-8"))

    def assert_exact_coverage(self, fields: list[dict[str, object]], size: int) -> None:
        cursor = 0
        for item in sorted(fields, key=lambda row: int(row["offset"])):
            self.assertEqual(int(item["offset"]), cursor, item["name"])
            self.assertGreater(int(item["size"]), 0, item["name"])
            cursor += int(item["size"])
        self.assertEqual(cursor, size)

    def test_checked_in_spec_is_canonical_and_contains_no_retail_geometry(self) -> None:
        self.assertEqual(self.spec, spec_tool.canonical_spec())
        self.assertFalse(self.spec["contains_retail_geometry_or_pixel_bytes"])
        self.assertFalse(
            self.spec["binary_evidence"]["raw_executable_or_geometry_bytes_embedded"]
        )
        self.assertEqual(len(self.spec["scene_descriptor"]["top_level_tables"]), 8)
        self.assertEqual(self.spec["scope"]["not_a_writer"], True)

    def test_all_fixed_records_have_gapless_nonoverlapping_field_maps(self) -> None:
        self.assert_exact_coverage(self.spec["outer_archive"]["header_fields"], 0x9C)
        self.assert_exact_coverage(
            self.spec["outer_archive"]["entry_record"]["fields"], 0x0C
        )
        self.assert_exact_coverage(self.spec["resource_chunk"]["fields"], 0x20)
        self.assert_exact_coverage(self.spec["scne_object"]["fields"], 0x18)
        self.assert_exact_coverage(
            self.spec["scene_descriptor"]["fields"],
            self.spec["scene_descriptor"]["size"],
        )
        self.assert_exact_coverage(
            self.spec["shape_record"]["fields"], self.spec["shape_record"]["stride"]
        )
        self.assert_exact_coverage(
            self.spec["submesh_record"]["fields"],
            self.spec["submesh_record"]["stride"],
        )

    def test_position_write_boundary_is_narrow_and_fail_closed(self) -> None:
        boundary = self.spec["same_count_position_write_boundary_v1"]
        self.assertEqual(
            boundary["status"],
            "implemented for pinned group36 plus a 75-target stadium FLOAT3 catalog; general 51,679-shape eligibility-profile dispatch not implemented",
        )
        self.assertIn("vertex_count is nonzero and unchanged", boundary["eligibility"])
        self.assertIn("transform_count is exactly one, conservatively excluding multi-transform shapes", boundary["eligibility"])
        self.assertIn("changed vertex count or ordering", boundary["mandatory_rejections"])
        self.assertIn("topology generation", boundary["excluded_extensions"])
        self.assertEqual(boundary["eligibility_corpus_count"], 51679)
        formats = self.spec["vertex_declaration"]["static_position"]["accepted_formats"]
        self.assertEqual([item["name"] for item in formats], ["FLOAT3", "NORMSHORT3"])
        self.assertIn("preserve scale and bias", formats[1]["same_count_encode_v1"])
        self.assertFalse(self.spec["claim_flags"]["same_count_position_writer_implemented"])
        self.assertTrue(
            self.spec["claim_flags"]["pinned_group36_float3_same_count_writer_implemented"]
        )
        self.assertFalse(
            self.spec["claim_flags"]["general_eligibility_profile_writer_dispatch_implemented"]
        )
        self.assertTrue(
            self.spec["claim_flags"]["stadium_catalog_75_float3_dispatch_implemented"]
        )
        witness = boundary["implemented_group36_witness"]
        self.assertEqual(
            (witness["outer_index"], witness["chunk_index"], witness["shape_index"]),
            (3280, 5, 4),
        )
        self.assertTrue(witness["no_op_whole_volume_bit_exact"])
        self.assertTrue(witness["independent_verifier"])
        self.assertFalse(witness["runtime_proved"])
        catalog = boundary["implemented_stadium_catalog_v2"]
        self.assertEqual(catalog["authorized_target_count"], 75)
        self.assertEqual(catalog["second_target_name"], "upper_deck")
        self.assertTrue(catalog["second_target_no_op_whole_volume_bit_exact"])
        self.assertTrue(catalog["independent_verifier"])
        self.assertFalse(catalog["runtime_proved"])
        self.assertFalse(self.spec["claim_flags"]["topology_write_proved"])

    def test_roundtrip_contract_requires_complete_byte_identity_and_independent_decode(self) -> None:
        contract = self.spec["roundtrip_contract"]
        self.assertTrue(any("byte-identical complete" in item for item in contract["no_op"]))
        self.assertTrue(any("SHA-256" in item for item in contract["no_op"]))
        self.assertTrue(
            any("independently decode the complete rebuilt fixed span" in item
                for item in contract["changed_position"])
        )
        self.assertTrue(contract["runtime_witness_required_for_runtime_claim"])

    def test_mutated_claim_or_layout_is_rejected(self) -> None:
        for mutate in (
            lambda data: data["claim_flags"].__setitem__("runtime_proved", True),
            lambda data: data["shape_record"].__setitem__("stride", 0x104),
            lambda data: data["relative_pointer"].__setitem__(
                "target_formula", "pointer_field_offset + s32le(pointer_field)"
            ),
            lambda data: data["scene_descriptor"]["top_level_tables"][4].__setitem__(
                "record_stride", 0x104
            ),
        ):
            changed = copy.deepcopy(self.spec)
            mutate(changed)
            with mock.patch.object(spec_tool, "validate_sources"), \
                    mock.patch.object(spec_tool, "validate_parser_constants"), \
                    mock.patch.object(spec_tool, "validate_reports"):
                with self.assertRaises(spec_tool.SpecError):
                    spec_tool.validate_spec(changed)


if __name__ == "__main__":
    unittest.main()
