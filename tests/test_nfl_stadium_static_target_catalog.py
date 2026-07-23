from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_static_target_catalog as catalog_tool  # noqa: E402
from nfl_outer import parse_archive, read_entry_range  # noqa: E402
from nfl_scene_probe import decode_resource, parse_inventory  # noqa: E402
from nfl_scne_inventory import parse_scene  # noqa: E402


CATALOG = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
SCAN = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"


class NflStadiumStaticTargetCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    def test_catalog_is_narrow_complete_for_selected_resource_and_geometry_free(self) -> None:
        catalog_tool.validate_catalog(self.catalog)
        self.assertEqual(self.catalog["scope"]["additional_catalog_target_count"], 75)
        self.assertTrue(self.catalog["scope"]["exhaustive_for_selected_resource"])
        self.assertFalse(self.catalog["scope"]["exhaustive_for_all_477_stadium_scenes"])
        self.assertFalse(self.catalog["data_policy"]["contains_retail_geometry_values"])
        self.assertFalse(self.catalog["claim_flags"]["general_position_writer_implemented"])
        self.assertFalse(self.catalog["claim_flags"]["changed_topology_writer_implemented"])
        self.assertFalse(self.catalog["claim_flags"]["runtime_visibility_proved"])
        self.assertEqual(
            [row["shape"]["index"] for row in self.catalog["targets"]],
            [value for value in range(76) if value != 4],
        )
        encoded = CATALOG.read_text(encoding="utf-8")
        for forbidden in ('"positions"', '"position_values"', '"indices"', '"vertices"'):
            self.assertNotIn(forbidden, encoded)

    def test_every_row_pins_full_mechanical_and_allocation_boundary(self) -> None:
        contract_hash = self.catalog["resource_contract_sha256"]
        for row in self.catalog["targets"]:
            self.assertEqual(row["source_identity"]["resource_contract_sha256"], contract_hash)
            self.assertEqual(row["position"]["declaration"]["format_name"], "FLOAT3")
            self.assertEqual(row["position"]["stream_stride"], 12)
            self.assertEqual(row["position"]["lane_size"], 12)
            self.assertEqual(
                row["position"]["contiguous_decoded_span"]["size"],
                row["shape"]["vertex_count"] * 12,
            )
            self.assertEqual(row["transform"]["base_count"], 1)
            self.assertEqual(row["transform"]["blended_palette_entry_count"], 0)
            self.assertTrue(row["transform"]["one_zero_root_parent_minus_one"])
            self.assertEqual(row["morph"]["count"], 0)
            self.assertTrue(row["selectors"]["all_select_sole_transform"])
            self.assertEqual(
                row["selectors"]["lane_element_count"], row["shape"]["vertex_count"]
            )
            topology = row["topology_and_materials"]
            self.assertTrue(topology["all_vertex_references_in_bounds"])
            self.assertFalse(topology["unknown_push_methods"])
            self.assertEqual(topology["submesh_count"], len(topology["push_streams"]))
            self.assertEqual(topology["submesh_count"], len(topology["materials"]))
            allocation = row["fixed_allocation"]
            self.assertEqual(allocation["changed_stream_cap_bytes"], 908_864)
            self.assertEqual(allocation["fixed_final_tail_bytes"], 16)
            self.assertTrue(allocation["scratch_must_be_rederived_per_edit"])
            self.assertFalse(allocation["runtime_acceptance_of_changed_scratch_proved"])
            self.assertFalse(row["eligibility"]["same_count_position_writer_implemented_for_this_target"])

    def test_upper_deck_second_target_and_all_zero_probe_are_exact(self) -> None:
        row = next(item for item in self.catalog["targets"] if item["shape"]["index"] == 1)
        self.assertEqual(row["shape"]["name"], "upper_deck")
        self.assertEqual(row["shape"]["vertex_count"], 12)
        self.assertEqual(
            row["position"]["contiguous_decoded_span"],
            {
                "offset": 0x11120,
                "end_offset": 0x111B0,
                "size": 144,
                "sha256": "95164ce59e125ac1775003846a1eb780c63f001c65f2b3da8d2aebd20fbe67f7",
            },
        )
        self.assertEqual(
            row["transform"]["table"]["sha256"],
            "9f93b547f55db606521ae4c19373fd857aba2b6009daecc1ceb6c724d3ca4658",
        )
        self.assertEqual(
            row["selectors"]["lane_sha256"],
            "9d908ecfb6b256def8b49a7c504e6c889c4b0e41fe6ce3e01863dd7b61a20aa0",
        )
        topology = row["topology_and_materials"]
        self.assertEqual(topology["primitive_mode_counts"], {"END": 1, "QUADS": 1})
        self.assertEqual(topology["materials"][0]["material_name"], "sign01")
        self.assertEqual(topology["push_streams"][0]["method_counts"], {"0x17fc": 2, "0x1810": 1})
        self.assertEqual(
            topology["push_streams"][0]["commands"]["sha256"],
            "6811dd478e03b4be22628c3f07c27d2dcb7791b98e0f409086e3c4267bfce1b0",
        )
        probe = self.catalog["selected_second_target"]
        self.assertEqual(probe["target_id"], row["target_id"])
        self.assertEqual(
            probe["authored_probe"]["position_after_sha256"],
            hashlib.sha256(bytes(144)).hexdigest(),
        )
        self.assertEqual(probe["authored_probe"]["decoded_changed_byte_count"], 144)
        self.assertEqual(probe["compression"]["rebuilt_consumed_bytes"], 908_799)
        self.assertEqual(probe["compression"]["zero_gap_bytes"], 65)
        self.assertEqual(probe["compression"]["minimum_alias_scratch_bytes"], 66)
        self.assertEqual(probe["compression"]["aligned_scratch_bytes"], 0x60)
        self.assertEqual(probe["compression"]["scratch_0x60_has_retail_scne_precedent_count"], 165)
        self.assertTrue(probe["claim_boundary"]["offline_fixed_allocation_fit_proved"])
        self.assertFalse(probe["claim_boundary"]["pack_write_implemented"])
        self.assertFalse(probe["claim_boundary"]["runtime_visibility_proved"])

    @unittest.skipUnless(INDEX.is_file() and SCAN.is_file(), "pinned retail source unavailable")
    def test_upper_deck_row_independently_rederives_from_source(self) -> None:
        _, resources = parse_inventory(SCAN)
        resource = next(
            item for item in resources
            if item.kind == "SCNE" and item.outer_index == 3280 and item.chunk_index == 5
        )
        archive = parse_archive(INDEX)
        span = read_entry_range(
            archive, archive.entries[3280], resource.chunk_offset, 0x20 + resource.stored_size
        )
        decoded, detail = decode_resource(span, resource)
        scene = parse_scene(2648, resource, decoded, {})[0]
        shape = scene["shapes"][1]
        row = next(item for item in self.catalog["targets"] if item["shape"]["index"] == 1)
        self.assertEqual(shape["name"], "upper_deck")
        self.assertEqual(shape["vertex_count"], 12)
        position = next(item for item in shape["attribute_descriptors"] if item["register"] == 0)
        stream = next(item for item in shape["vertex_streams"] if item["stream_index"] == 0)
        self.assertEqual(position["format_name"], "FLOAT3")
        self.assertEqual((stream["stride"], stream["offset"], stream["end_offset"]), (12, 0x11120, 0x111B0))
        self.assertEqual(
            hashlib.sha256(decoded[stream["offset"]:stream["end_offset"]]).hexdigest(),
            row["position"]["contiguous_decoded_span"]["sha256"],
        )
        transform = shape["transform_offset"]
        self.assertEqual(struct.unpack_from("<4f", decoded, transform + 0x40), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(struct.unpack_from("<4f", decoded, transform + 0x50), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(struct.unpack_from("<i", decoded, transform + 0x64)[0], -1)
        self.assertEqual(detail["lz"]["consumed_bytes"], 908_864)
        self.assertEqual(hashlib.sha256(span[-16:]).hexdigest(), row["fixed_allocation"]["fixed_final_tail_sha256"])

    def test_promoted_writer_or_runtime_claim_is_rejected(self) -> None:
        for path in ("writer", "runtime"):
            changed = copy.deepcopy(self.catalog)
            if path == "writer":
                changed["claim_flags"]["general_position_writer_implemented"] = True
            else:
                changed["selected_second_target"]["claim_boundary"]["runtime_visibility_proved"] = True
            with self.assertRaises(catalog_tool.CatalogError):
                catalog_tool.validate_catalog(changed)


if __name__ == "__main__":
    unittest.main()
