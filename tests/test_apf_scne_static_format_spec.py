#!/usr/bin/env python3
"""Independent refusal and inverse-rule tests for the APF SCNE spec."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_scne_static_format_spec as spec  # noqa: E402


EXPECTED_SPEC_SIZE = 75_274
EXPECTED_SPEC_SHA256 = "e7eeaf35d897d188d6a0c2faa5e0300a741d751204bc4fae1222460bc980802b"


class ApfScneStaticFormatSpecTest(unittest.TestCase):
    def test_canonical_spec_validates_with_exact_identity(self) -> None:
        result = spec.validate()
        self.assertEqual(result["scne_resources"], 1_303)
        self.assertEqual(result["mesh_nodes"], 13_006)
        self.assertEqual(result["position_formats"], 3)
        self.assertEqual(result["write_profiles"], 2)
        self.assertFalse(result["retail_geometry"])
        self.assertFalse(result["writer_implemented"])
        self.assertTrue(result["pinned_writer_implemented"])
        self.assertEqual(result["catalog_targets"], 77)
        self.assertTrue(result["catalog_dispatcher_implemented"])
        self.assertTrue(result["node3_writer_implemented"])
        self.assertTrue(result["node3_rebuild_fit"])
        self.assertTrue(result["topology_writer_implemented"])
        self.assertEqual(result["topology_changed_decoded_bytes"], 2)
        self.assertEqual(result["topology_allocation_slack_after"], 1_403)
        self.assertFalse(result["runtime_proved"])
        self.assertEqual(spec.DEFAULT_SPEC.stat().st_size, EXPECTED_SPEC_SIZE)
        self.assertEqual(hashlib.sha256(spec.DEFAULT_SPEC.read_bytes()).hexdigest(), EXPECTED_SPEC_SHA256)

    def test_generator_is_byte_identical_to_checked_in_spec(self) -> None:
        self.assertEqual(spec.render_spec(), spec.DEFAULT_SPEC.read_bytes())

    def test_normative_magic_and_format_integers_match_hex(self) -> None:
        document = json.loads(spec.DEFAULT_SPEC.read_bytes())
        iff = document["container_ownership"]["iff"]
        h7a = document["container_ownership"]["h7a"]
        footer = iff["name_footer"]
        self.assertEqual(iff["magic_u32be"], int(iff["magic_hex"], 16))
        self.assertEqual(h7a["magic_u32be"], int(h7a["magic_hex"], 16))
        self.assertEqual(footer["magic_u32be"], int(footer["magic_hex"], 16))
        for item in document["scne"]["position0_formats"]:
            self.assertEqual(item["format_code"], int(item["format_code_hex"], 16))
        draw = document["scne"]["draw_record"]
        self.assertEqual(draw["size_bytes"], 0x30)
        self.assertEqual(
            [field["name"] for field in draw["fields"]],
            [
                "draw_primitive_code",
                "first_element",
                "element_count",
                "primitive_capacity",
                "base_vertex",
                "minimum_vertex",
                "vertex_range",
                "optional_draw_state",
                "material_slot",
                "reserved_24",
                "reserved_28",
                "render_flags_2c",
            ],
        )
        topology = document["write_profiles"]["outer14_inner8_node17_four_be16_strip/v1"]
        self.assertEqual(topology["implemented_target"]["index_allocation_bytes"], 8)
        self.assertEqual(topology["runtime_status"], "unproved")

    def test_float32_inverse_is_big_endian_and_refuses_nonfinite(self) -> None:
        encoded = spec.encode_position_float32x3((1.25, -2.5, 0.0))
        self.assertEqual(encoded, struct.pack(">3f", 1.25, -2.5, 0.0))
        with self.assertRaisesRegex(spec.SpecError, "finite"):
            spec.encode_position_float32x3((math.inf, 0.0, 0.0))

    def test_snorm16_inverse_preserves_w_and_negative_minimum(self) -> None:
        source = b"\xaa\xbb\xcc\xdd\xee\xff\x12\x34"
        encoded = spec.encode_position_snorm16_xyz((-1.0, 0.0, 1.0), source)
        self.assertEqual(struct.unpack(">3h", encoded[:6]), (-32_767, 0, 32_767))
        self.assertEqual(encoded[6:], source[6:])
        self.assertEqual(spec.decode_snorm(0x8000, 16), -1.0)
        with self.assertRaisesRegex(spec.SpecError, "inside"):
            spec.encode_position_snorm16_xyz((1.0001, 0.0, 0.0), source)

    def test_snorm10_inverse_preserves_high_bits_and_lane_order(self) -> None:
        encoded = spec.encode_position_snorm10_xyz((-1.0, 0.0, 1.0), b"\xc0\x00\x00\x00")
        word = struct.unpack(">I", encoded)[0]
        self.assertEqual(word & 0xC0000000, 0xC0000000)
        self.assertEqual(word & 0x3FF, (-511) & 0x3FF)
        self.assertEqual((word >> 10) & 0x3FF, 0)
        self.assertEqual((word >> 20) & 0x3FF, 511)
        self.assertEqual(spec.decode_snorm(0x200, 10), -1.0)

    def test_mutated_write_boundary_is_rejected(self) -> None:
        document = json.loads(spec.DEFAULT_SPEC.read_bytes())
        mutated = copy.deepcopy(document)
        mutated["write_profiles"]["same_count_position_only/v1"]["forbidden_changes"].remove(
            "index width, index count, index payload, restart placement, primitive type, or topology"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(mutated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(spec.SpecError, "canonical"):
                spec.validate(path)

    def test_mutated_runtime_claim_is_rejected(self) -> None:
        document = json.loads(spec.DEFAULT_SPEC.read_bytes())
        document["claim_flags"]["emulator_runtime_visibility_proved"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated.json"
            path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(spec.SpecError, "canonical"):
                spec.validate(path)

    def test_spec_excludes_retail_geometry_and_freezes_part_ownership(self) -> None:
        document = json.loads(spec.DEFAULT_SPEC.read_bytes())
        self.assertEqual(
            document["data_policy"],
            {
                "allowed_evidence": "format constants, aggregate counts, hashes, field offsets, algorithms, and claim boundaries only",
                "contains_retail_archive_bytes": False,
                "contains_retail_geometry": False,
                "contains_retail_index_values": False,
                "contains_retail_stream_payloads": False,
                "contains_retail_vertex_values": False,
            },
        )
        proof = document["corpus_proof"]
        self.assertEqual((proof["dram_only_scne"], proof["dram_vram_scne"], proof["scne_sram_part_count"]), (504, 799, 0))
        claims = document["claim_flags"]
        self.assertTrue(claims["no_op_whole_entry_byte_identity_required"])
        self.assertTrue(claims["fixed_allocation_required_by_current_profile"])
        self.assertTrue(claims["changed_topology_writer_proved"])
        self.assertTrue(claims["pinned_outer14_node17_same_footprint_topology_writer_implemented"])
        self.assertTrue(claims["pinned_outer14_node17_same_footprint_topology_offline_roundtrip_proved"])
        self.assertFalse(claims["general_scne_topology_dispatcher_implemented"])
        self.assertFalse(claims["production_mesh_importer_proved"])
        self.assertTrue(claims["pinned_outer14_node17_same_count_position_writer_implemented"])
        self.assertTrue(claims["outer14_additional_static_target_catalog_proved"])
        self.assertTrue(claims["outer14_catalog_all_77_targets_structurally_authorized"])
        self.assertTrue(claims["outer14_catalog_same_count_position_dispatcher_implemented"])
        self.assertTrue(claims["pinned_outer14_node3_representative_h7a_rebuild_fit_proved"])
        self.assertTrue(claims["pinned_outer14_node3_writer_implemented"])
        self.assertTrue(claims["pinned_outer14_node3_offline_structural_writeback_proved"])
        self.assertFalse(claims["general_scne_same_count_position_dispatcher_implemented"])
        self.assertFalse(claims["same_count_position_writer_implemented"])


if __name__ == "__main__":
    unittest.main()
