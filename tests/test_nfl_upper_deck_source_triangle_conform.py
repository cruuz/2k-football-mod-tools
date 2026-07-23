from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_upper_deck_subset_patch as downstream  # noqa: E402
import nfl_upper_deck_source_triangle_conform as conformer  # noqa: E402


SAMPLE4 = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
    "stadium_upper_deck_nonidentity4_source_triangle_mesh.v1.json"
)
SAMPLE8 = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
    "stadium_upper_deck_prefix8_source_triangle_mesh.v1.json"
)
RECIPE4 = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
    "stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json"
)
RECIPE8 = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
    "stadium_upper_deck_prefix8_source_subset_recipe.v1.json"
)


class NflUpperDeckSourceTriangleConformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.authorities = conformer.load_authorities()
        cls.sample4, cls.sample4_payload = conformer.load_source_mesh(SAMPLE4)
        cls.sample8, cls.sample8_payload = conformer.load_source_mesh(SAMPLE8)

    def test_authorities_pin_offline_writer_without_widening_claims(self) -> None:
        closure = self.authorities["closure"]
        claims = closure["claim_flags"]
        self.assertTrue(claims["changed_count_source_subset_writer_implemented"])
        self.assertTrue(claims["independent_changed_count_verifier_implemented"])
        self.assertTrue(claims["nonidentity_synchronized_whole_record_remap_proved"])
        self.assertFalse(claims["arbitrary_external_vertex_authoring_proved"])
        self.assertFalse(claims["edited_gltf_import_proved"])
        self.assertFalse(claims["bounds_or_culling_serializer_proved"])
        self.assertFalse(claims["runtime_visibility_proved"])
        self.assertEqual(
            conformer.DEFAULT_INPUT_SCHEMA.stat().st_size,
            conformer.INPUT_SCHEMA_SIZE,
        )
        self.assertEqual(
            conformer.sha256(conformer.DEFAULT_INPUT_SCHEMA.read_bytes()),
            conformer.INPUT_SCHEMA_SHA256,
        )

    def test_four_triangle_mesh_conforms_byte_exactly_to_checked_recipe(self) -> None:
        recipe, facts = conformer.conform_mesh(self.sample4)
        self.assertEqual(
            conformer.canonical_json(recipe),
            RECIPE4.read_bytes(),
        )
        self.assertEqual(recipe["source_vertex_ids"], [8, 9, 10, 11])
        self.assertEqual(facts["native_quad_count"], 1)
        self.assertTrue(facts["oriented_triangle_multiset_preserved"])
        self.assertFalse(facts["external_vertex_or_attribute_values_admitted"])

    def test_eight_triangle_mesh_conforms_byte_exactly_to_checked_recipe(self) -> None:
        recipe, facts = conformer.conform_mesh(self.sample8)
        self.assertEqual(
            conformer.canonical_json(recipe),
            RECIPE8.read_bytes(),
        )
        self.assertEqual(recipe["source_vertex_ids"], list(range(8)))
        self.assertEqual(facts["native_quad_count"], 2)
        self.assertEqual(facts["distinct_source_vertex_count"], 8)

    def test_triangle_cycles_pair_order_and_quad_order_canonicalize(self) -> None:
        changed = copy.deepcopy(self.sample8)
        changed["triangles"] = [
            [6, 4, 5],
            [2, 3, 0],
            [6, 7, 4],
            [2, 0, 1],
        ]
        recipe, _ = conformer.conform_mesh(changed)
        self.assertEqual(recipe["source_vertex_ids"], list(range(8)))
        self.assertEqual(
            conformer._triangle_multiset(changed["triangles"]),
            conformer._triangle_multiset(
                conformer.expand_native_quads(recipe["source_vertex_ids"])
            ),
        )

    def test_reversed_input_winding_is_preserved_not_silently_flipped(self) -> None:
        changed = copy.deepcopy(self.sample4)
        changed["triangles"] = [[8, 10, 9], [8, 11, 10]]
        recipe, facts = conformer.conform_mesh(changed)
        self.assertNotEqual(recipe["source_vertex_ids"], [8, 9, 10, 11])
        self.assertEqual(
            conformer._triangle_multiset(changed["triangles"]),
            conformer._triangle_multiset(
                conformer.expand_native_quads(recipe["source_vertex_ids"])
            ),
        )
        self.assertFalse(facts["winding_reversal_admitted"])

    def test_structurally_invalid_topologies_are_rejected(self) -> None:
        bad_values = (
            [[[0, 1, 2]]],
            [[0, 1, 2], [0, 2, 3], [4, 5, 6]],
            [[0, 0, 1], [0, 1, 2]],
            [[0, 1, 2], [1, 2, 0]],
            [[0, 1, 2], [0, 1, 3]],
            [[0, 1, 2], [0, 2, 3], [3, 4, 5], [3, 5, 6]],
        )
        for triangles in bad_values:
            with self.subTest(triangles=triangles):
                with self.assertRaises(conformer.SourceTriangleConformanceError):
                    conformer.conform_source_indexed_quads(triangles)

    def test_boolean_out_of_range_and_non_array_ids_are_rejected(self) -> None:
        bad_values = (
            [[0, 1, True], [0, True, 3]],
            [[0, 1, 12], [0, 12, 3]],
            [[0, 1, "2"], [0, "2", 3]],
            "not-an-array",
        )
        for triangles in bad_values:
            with self.subTest(triangles=triangles):
                with self.assertRaises(conformer.SourceTriangleConformanceError):
                    conformer.conform_source_indexed_quads(triangles)

    def test_source_mesh_identity_policy_and_extra_fields_are_rejected(self) -> None:
        mutations = (
            lambda value: value.__setitem__("schema", "future/v2"),
            lambda value: value.__setitem__("target_id", "other"),
            lambda value: value.__setitem__("source_decoded_sha256", "0" * 64),
            lambda value: value.__setitem__("primitive", "QUADS"),
            lambda value: value.__setitem__("attribute_policy", "invent_values"),
            lambda value: value.__setitem__("positions", [[0.0, 0.0, 0.0]]),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, mutate in enumerate(mutations):
                value = copy.deepcopy(self.sample4)
                mutate(value)
                path = root / f"bad-{index}.json"
                path.write_bytes(conformer.canonical_json(value))
                with self.subTest(index=index):
                    with self.assertRaises(conformer.SourceTriangleConformanceError):
                        conformer.load_source_mesh(path)

    def test_noncanonical_duplicate_key_and_symlink_input_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            noncanonical = root / "noncanonical.json"
            noncanonical.write_text(
                json.dumps(self.sample4, separators=(",", ":")),
                encoding="utf-8",
            )
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"schema":"a","schema":"b"}\n',
                encoding="utf-8",
            )
            link = root / "link.json"
            link.symlink_to(SAMPLE4)
            for path in (noncanonical, duplicate, link):
                with self.subTest(path=path.name):
                    with self.assertRaises(conformer.SourceTriangleConformanceError):
                        conformer.load_source_mesh(path)

    def test_authority_claim_or_native_primitive_drift_is_rejected(self) -> None:
        mutations = (
            lambda value: value["claim_flags"].__setitem__(
                "runtime_visibility_proved", True
            ),
            lambda value: value["claim_flags"].__setitem__(
                "changed_count_source_subset_writer_implemented", False
            ),
            lambda value: value["format_contract"]["shape"].__setitem__(
                "native_primitive", "TRIANGLES"
            ),
            lambda value: value["implementation_contract"]["changed_modes"].__setitem__(
                "external_positions_or_attributes_admitted", True
            ),
        )
        for mutate in mutations:
            changed = copy.deepcopy(self.authorities["closure"])
            mutate(changed)
            with self.assertRaises(conformer.SourceTriangleConformanceError):
                conformer._validate_closure(changed)

    def test_generated_recipes_are_accepted_by_proved_downstream_loader(self) -> None:
        downstream_authorities = downstream.load_authorities()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, sample, expected_mode in (
                ("four.json", self.sample4, "source_subset_remap"),
                ("eight.json", self.sample8, "count_only_prefix"),
            ):
                recipe, _ = conformer.conform_mesh(sample)
                path = root / name
                path.write_bytes(conformer.canonical_json(recipe))
                request = downstream.load_request(path, False, downstream_authorities)
                self.assertEqual(request["new_count"], recipe["new_vertex_count"])
                self.assertEqual(request["source_ids"], recipe["source_vertex_ids"])
                self.assertEqual(request["mode"], expected_mode)

    def test_exclusive_output_refuses_existing_file_and_symlink_parent(self) -> None:
        recipe, _ = conformer.conform_mesh(self.sample4)
        payload = conformer.canonical_json(recipe)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "recipe.json"
            self.assertEqual(conformer._write_exclusive(output, payload), output)
            self.assertEqual(output.read_bytes(), payload)
            with self.assertRaises(conformer.SourceTriangleConformanceError):
                conformer._write_exclusive(output, payload)
            linked_parent = root / "linked"
            actual_parent = root / "actual"
            actual_parent.mkdir()
            linked_parent.symlink_to(actual_parent, target_is_directory=True)
            with self.assertRaises(conformer.SourceTriangleConformanceError):
                conformer._write_exclusive(linked_parent / "recipe.json", payload)


if __name__ == "__main__":
    unittest.main()
