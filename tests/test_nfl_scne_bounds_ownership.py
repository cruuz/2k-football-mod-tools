from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_scne_bounds_ownership as bounds  # noqa: E402
import nfl_stadium_static_target_catalog as catalog  # noqa: E402


INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
SCAN = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
XBE = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
XBE_HEADER = ROOT / "reports/headers/nfl2k5_xbe_header.json"
REPORT = ROOT / "reports/assets/nfl_scne_bounds_ownership.json"


class ScneBoundsOwnershipTests(unittest.TestCase):
    def test_authorities_are_hash_pinned_and_exclude_external_values(self) -> None:
        evidence = bounds.authority_evidence()
        self.assertEqual(evidence["admitted_changed_counts"], [4, 8])
        self.assertEqual(evidence["admitted_source_vertex_ids"], "distinct IDs in [0,11]")
        self.assertFalse(evidence["external_vertex_values_admitted"])
        self.assertEqual(len(evidence["files"]), 7)

    def test_executable_dataflow_is_exact(self) -> None:
        evidence = bounds.executable_evidence(XBE, XBE_HEADER)
        self.assertEqual(evidence["md5"], bounds.EXPECTED_XBE_MD5)
        self.assertEqual(evidence["sha256"], bounds.EXPECTED_XBE_SHA256)
        self.assertEqual(
            {item["name"]: item["sha256"] for item in evidence["function_ranges"]},
            {
                "frustum_sphere_test": "72444b6c5a4236cf5a8b720a5b91c00571e657e7e1bfb6423f607c418ff913c3",
                "node_relocator": "fbe34058fa5197b0c584c31b23672668eadbd84710d577d84f61aacbb4f41bc8",
                "node_sphere_visibility_dispatch": "3004525d4f27a344c5ce145503f99093a59e57d9d92d775427394a948ed02bda",
                "render_node": "4b51b577a3dedc1b8aebb5d89bc1983c054d913728acefd5514edf291c9c2566",
                "shape_center_getter": "58367ffa2a0179375018fa0f5c26da24391e42ebe0ed8fdda35a21fc7bdc396f",
                "shape_radius_getter": "a3c5b6dafc3d14f6903185a68e16b068ced67b6eb9cb8cdca6aeac1a387cf380",
                "shape_relocator": "c537a5b259fe034d0c8dfa8362a71830c2a7d18f4b2064b0868880a775796751",
                "transform_bound_center": "1c2d288c9e44c8dea32cca64bb1673bcb6d9e08d05d961eef1f4bbe541fd3d1a",
            },
        )
        flow = evidence["proved_dataflow"]
        self.assertIn("shape +0x48", flow["serialized_radius"])
        self.assertEqual(flow["consumer"], "0x0002adc0 camera/frustum sphere test")

    def test_float_and_normshort_position_decode(self) -> None:
        raw_float = struct.pack("<3f", 1.25, -2.5, 3.75)
        self.assertEqual(
            bounds.decode_position(raw_float, 0, "FLOAT3", 99.0, (9.0, 9.0, 9.0)),
            (1.25, -2.5, 3.75),
        )
        raw_short = struct.pack("<3h", 32767, -32768, 0)
        self.assertEqual(
            bounds.decode_position(raw_short, 0, "NORMSHORT3", 2.0, (1.0, 1.0, 1.0)),
            (3.0, -1.0, 1.0),
        )
        with self.assertRaisesRegex(bounds.BoundsError, "unsupported"):
            bounds.decode_position(bytes(12), 0, "FLOAT4", 1.0, (0.0, 0.0, 0.0))

    def test_sphere_measurement_and_upward_binary32_step(self) -> None:
        result = bounds.sphere_measurement(
            (0.0, 0.0, 0.0), 5.0,
            [(3.0, 4.0, 0.0), (0.0, 0.0, -1.0)],
        )
        self.assertTrue(result["contains_all_vertices"])
        self.assertEqual(result["maximum_vertex_distance"], 5.0)
        self.assertEqual(result["signed_slack"], 0.0)
        next_one = bounds.next_f32_up(1.0)
        self.assertEqual(struct.pack("<f", next_one).hex(), "0100803f")
        self.assertGreater(next_one, 1.0)

    def test_upper_deck_retail_sphere_contains_every_admitted_subset(self) -> None:
        source = catalog._load_source(INDEX, SCAN)
        decoded = source["decoded"]
        shape = source["scene"]["shapes"][bounds.TARGET_SHAPE]
        self.assertEqual(shape["name"], bounds.TARGET_NAME)
        self.assertEqual(shape["vertex_count"], bounds.TARGET_VERTEX_COUNT)
        record = int(shape["record_offset"])
        center = struct.unpack_from("<3f", decoded, record)
        radius = struct.unpack_from("<f", decoded, record + 0x48)[0]
        self.assertEqual(
            hashlib.sha256(decoded[record:record + 16]).hexdigest(),
            "48cd3215dc317e3e0012f75632bbfb4907c631571eb8d8e10600c29b52bade31",
        )
        self.assertEqual(
            hashlib.sha256(decoded[record + 0x48:record + 0x4C]).hexdigest(),
            "596656595223c44edca411796cac204d92f9430058a442b4a78d4f64adf5efe7",
        )
        positions = [
            struct.unpack_from("<3f", decoded, bounds.TARGET_POSITION_OFFSET + index * 12)
            for index in range(bounds.TARGET_VERTEX_COUNT)
        ]
        full = bounds.sphere_measurement(center, radius, positions)
        self.assertTrue(full["contains_all_vertices"])
        self.assertTrue(math.isclose(full["signed_slack"], 0.00004071272405781201))
        for count in (4, 8):
            for selected in itertools.combinations(range(bounds.TARGET_VERTEX_COUNT), count):
                measured = bounds.sphere_measurement(
                    center, radius, [positions[index] for index in selected]
                )
                self.assertTrue(measured["contains_all_vertices"])

    def test_checked_report_keeps_general_authoring_closed(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], bounds.SCHEMA)
        claims = report["claim_flags"]
        self.assertTrue(claims["serialized_sphere_owner_proved"])
        self.assertTrue(claims["frustum_culling_consumer_proved"])
        self.assertFalse(claims["upper_deck_source_subset_needs_bounds_rewrite"])
        self.assertFalse(claims["bounds_serializer_implemented"])
        self.assertFalse(claims["arbitrary_external_positions_proved"])
        self.assertFalse(claims["runtime_visibility_proved"])
        corpus = report["corpus"]
        self.assertEqual(corpus["counts"]["shape_count"], 54_966)
        self.assertEqual(corpus["counts"]["vertex_count"], 13_731_388)
        self.assertEqual(corpus["register_zero_format_counts"], {
            "FLOAT3": 46_192, "NORMSHORT3": 8_774,
        })
        containment = corpus["sphere_containment"]
        self.assertEqual(containment["within_one_upward_radius_ulp_by_format"]["FLOAT3"], 46_192)
        self.assertEqual(containment["more_than_one_upward_radius_ulp_outside_count"], 5_772)
        self.assertTrue(corpus["upper_deck"]["all_admissible_4_or_8_source_subsets_contained"])


if __name__ == "__main__":
    unittest.main()
