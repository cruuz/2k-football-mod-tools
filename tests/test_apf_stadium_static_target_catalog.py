import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/apf_stadium_static_target_catalog.py"
REPORT_PATH = ROOT / "mod_editor/data/apf2k8_stadium_static_position_target_catalog.v1.json"


def _module():
    spec = importlib.util.spec_from_file_location("apf_stadium_static_target_catalog", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _report():
    return json.loads(REPORT_PATH.read_bytes())


class CatalogTests(unittest.TestCase):
    def test_catalog_contract_and_second_handoff(self):
        module = _module()
        report = _report()
        module.validate_document(report)
        self.assertEqual(
            report["summary"],
            {
                "additional_priority_tier_counts": {
                    "mesh_like_multi_hierarchy_attachment_unknown": 3,
                    "mesh_like_single_hierarchy": 63,
                    "position_only_effect_or_variant": 11,
                },
                "additional_target_count": 77,
                "eligible_including_first_proved_node": 78,
                "first_proved_node_excluded_from_additional_catalog": 17,
                "selected_second_target_node": 3,
            },
        )
        handoff = report["selected_second_target_handoff"]
        self.assertEqual(handoff["candidate_id"], "outer14.inner8.node3")
        self.assertEqual(
            handoff["new_structural_coverage"],
            {"draw_record_count": 3, "vertex_count": 24},
        )
        # 1967, not 1367. The generator used to re-encode this block with the
        # greedy encoder, which is 2,599 bytes WORSE than retail on it even
        # before the edit -- so regenerating the catalog overflowed a slot
        # retail itself fits, and this witness could not be reproduced at all.
        # It now preserves retail's own H7A tokens (pure Python, so the bytes
        # are identical on all three OS), which drops the representative edit's
        # growth from 659 bytes to 59 and raises the slack accordingly. The
        # safety property strengthened; it did not move.
        self.assertEqual(
            handoff["representative_local_only_fit_witness"]["allocation_slack_after_bytes"],
            1967,
        )
        self.assertEqual(
            handoff["representative_local_only_fit_witness"]["stored_block0_growth_bytes"],
            59,
        )

    def test_every_target_is_hash_pinned_bounded_float32_and_never_runtime_rigid(self):
        report = _report()
        for target in report["additional_targets"]:
            self.assertEqual(target["classification"], "structural_static_same_count_position_candidate")
            self.assertIs(target["runtime_rigid_attachment_proved"], False)
            self.assertIs(target["runtime_visibility_proved"], False)
            self.assertIs(target["declarations"]["has_blendindices_or_blendweight"], False)
            self.assertEqual(target["position0"]["format_name"], "float32x3")
            self.assertEqual(
                target["position0"]["authorized_lane_bytes"],
                target["position0"]["vertex_count"] * 12,
            )
            stream = target["streams"][target["position0"]["stream_index"]]["payload"]
            self.assertLessEqual(target["position0"]["last_lane_end"], stream["offset"] + stream["length"])
            self.assertEqual(len(target["node"]["record"]["sha256"]), 64)
            for key in (
                "matrix_slot_by_serialized_node_ordinal",
                "hierarchy",
                "draw_records",
                "index_topology",
                "declarations",
                "mesh_descriptor_and_stream_records",
            ):
                self.assertEqual(len(target[key]["sha256"]), 64)

    def test_catalog_contains_no_vertex_values_or_json_floats(self):
        report = _report()
        forbidden_keys = {
            "positions", "position", "minimum", "maximum", "center", "scale",
            "vector_10", "vector_20", "vector_30",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            else:
                self.assertNotIsInstance(value, float)

        walk(report)

    def test_validation_rejects_runtime_overclaim_and_fit_drift(self):
        module = _module()
        report = _report()
        overclaim = copy.deepcopy(report)
        overclaim["additional_targets"][0]["runtime_rigid_attachment_proved"] = True
        with self.assertRaises(module.CatalogError):
            module.validate_document(overclaim)
        overflow = copy.deepcopy(report)
        overflow["selected_second_target_handoff"]["representative_local_only_fit_witness"]["stored_block0_length_after"] = 9_999_999
        with self.assertRaises(module.CatalogError):
            module.validate_document(overflow)


if __name__ == "__main__":
    unittest.main()
