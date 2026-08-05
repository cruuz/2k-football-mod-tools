#!/usr/bin/env python3
"""Focused checks for the positive-visibility ``upper_deck`` board candidate."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_stadium_upper_deck_subset_verify as native  # noqa: E402


INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
SOURCE_VOLUME = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/9"
BUILD = ROOT / "build/nfl2k5-stadium-upper-deck-wide-overlay8-20260716"
OUTPUT_VOLUME = BUILD / "native/9"
RECIPE = (
    ROOT
    / "reports/asset_samples/nfl_scne/"
      "stadium_upper_deck_wide_overlay8_source_subset_recipe.v1.json"
)
S42_BUILD = ROOT / "build/nfl2k5-stadium-group36-geometry-xiso-20260713"
RUNTIME_QUEUE = (
    ROOT / "reports/specs/nfl2k5_upper_deck_wide_overlay8_runtime_queue.v1.json"
)

EXPECTED_RECIPE_SHA256 = (
    "df3a552a9387cb351d3918fddf6cea106418ae1f908fce5d9b6c8f3f7c762056"
)
EXPECTED_VOLUME_SHA256 = (
    "5e983c0727d903aef298df7320bffe7cf5ae4bcf91720438cb9bcd26edff54fc"
)
EXPECTED_CHANGED_OFFSETS = [
    30540,
    69887,
    69968,
    69969,
    69970,
    69971,
    69972,
    69973,
    69976,
    69977,
    69980,
    69981,
    69982,
    69983,
    69984,
    69985,
    69988,
    69989,
    70120,
    70121,
    70122,
    70124,
    70125,
    70126,
    70127,
    70130,
    70131,
    70132,
    70134,
    70135,
    70136,
    70137,
]
EXPECTED_S42_FROM_RETAIL_OFFSETS = [
    *range(2_397_076, 2_397_096),
    *range(2_397_804, 2_397_824),
    2_735_201,
    13_457_596,
    13_457_597,
    1_635_418_436,
    1_635_418_438,
]


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def load_canonical(path: Path) -> dict[str, object]:
    payload = path.read_bytes()
    value = json.loads(payload)
    if payload != canonical_json(value):
        raise AssertionError(f"not canonical JSON: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(16 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def decoded_resource(volume: Path) -> bytes:
    mapping = native.parse_index(INDEX)
    with volume.open("rb") as stream:
        stream.seek(mapping["pack_offset"] + 0x5EA40)
        chunk = stream.read(native.CHUNK_SPAN)
    if len(chunk) != native.CHUNK_SPAN:
        raise AssertionError("short upper_deck resource read")
    decoded, metadata = native.decompress_vc_lz(
        chunk[32:32 + native.CHUNK_STORED], native.DECODED_SIZE
    )
    if metadata["consumed"] > native.RETAIL_CONSUMED:
        raise AssertionError("upper_deck resource exceeds retail consumed cap")
    return decoded


def positions(decoded: bytes, ids: list[int]) -> list[tuple[float, float, float]]:
    return [
        struct.unpack_from(
            "<3f", decoded, native.STREAM0_OFFSET + source_id * native.STREAM0_STRIDE
        )
        for source_id in ids
    ]


def cross(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    ab = tuple(b[index] - a[index] for index in range(3))
    ac = tuple(c[index] - a[index] for index in range(3))
    return (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )


def quad_area(points: list[tuple[float, float, float]]) -> float:
    vectors = (cross(points[0], points[1], points[2]),
               cross(points[0], points[2], points[3]))
    return sum(math.sqrt(sum(component * component for component in value)) / 2
               for value in vectors)


@unittest.skipUnless(
    OUTPUT_VOLUME.is_file(),
    # ``build/`` is gitignored, and this volume is a large generated output from
    # one dated build. On any checkout that does not happen to still hold it,
    # the class used to raise FileNotFoundError out of setUpClass -- an error
    # that looks like a real regression, and one that masks real regressions by
    # sitting permanently red. It is a missing input, so it skips. When the
    # build IS present the assertions below run exactly as before.
    "build/nfl2k5-stadium-upper-deck-wide-overlay8-20260716/native/9 not built",
)
class UpperDeckWideOverlay8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = decoded_resource(SOURCE_VOLUME)
        cls.output = decoded_resource(OUTPUT_VOLUME)

    def test_recipe_is_exact_source_only_contract(self) -> None:
        recipe = load_canonical(RECIPE)
        self.assertEqual(sha256(RECIPE), EXPECTED_RECIPE_SHA256)
        self.assertEqual(recipe, {
            "new_vertex_count": 8,
            "schema": "nfl2k5_upper_deck_source_subset_recipe/v1",
            "source_decoded_sha256": native.SOURCE_DECODED_SHA256,
            "source_vertex_ids": [0, 1, 2, 3, 8, 9, 6, 7],
            "target_id": "nfl2k5/stadium/o3280/c5/s1",
        })

    def test_three_retail_quads_map_base_and_two_inset_overlays(self) -> None:
        base = positions(self.source, [0, 1, 2, 3])
        right = positions(self.source, [4, 5, 6, 7])
        left = positions(self.source, [8, 9, 10, 11])

        for quad in (base, right, left):
            normals = (cross(quad[0], quad[1], quad[2]),
                       cross(quad[0], quad[2], quad[3]))
            self.assertTrue(all(normal[2] < 0 for normal in normals))
            self.assertTrue(all(math.sqrt(sum(v * v for v in normal)) > 0
                                for normal in normals))

        base_x = (min(point[0] for point in base), max(point[0] for point in base))
        base_y = (min(point[1] for point in base), max(point[1] for point in base))
        for overlay in (left, right):
            self.assertGreater(min(point[0] for point in overlay), base_x[0])
            self.assertLess(max(point[0] for point in overlay), base_x[1])
            self.assertGreater(min(point[1] for point in overlay), base_y[0])
            self.assertLess(max(point[1] for point in overlay), base_y[1])
        self.assertLess(max(point[0] for point in left),
                        min(point[0] for point in right))
        self.assertEqual(len({point[2] for point in base}), 1)
        self.assertEqual(len({point[2] for point in left}), 1)
        self.assertEqual(len({point[2] for point in right}), 1)
        self.assertNotEqual(base[0][2], left[0][2])
        self.assertNotEqual(base[0][2], right[0][2])

    def test_candidate_keeps_base_and_forms_one_large_positive_overlay(self) -> None:
        selected = [0, 1, 2, 3, 8, 9, 6, 7]
        base = positions(self.source, selected[:4])
        wide = positions(self.source, selected[4:])
        left = positions(self.source, [8, 9, 10, 11])
        right = positions(self.source, [4, 5, 6, 7])

        normals = (cross(wide[0], wide[1], wide[2]),
                   cross(wide[0], wide[2], wide[3]))
        self.assertTrue(all(normal[2] < 0 for normal in normals))
        self.assertAlmostEqual(normals[0][0], normals[1][0], delta=0.01)
        self.assertAlmostEqual(normals[0][2], normals[1][2], delta=5.0)
        self.assertEqual(min(point[0] for point in wide),
                         min(point[0] for point in left))
        self.assertEqual(max(point[0] for point in wide),
                         max(point[0] for point in right))
        self.assertGreater(quad_area(wide), 2 * (quad_area(left) + quad_area(right)))
        self.assertLess(quad_area(wide), quad_area(base))

    def test_native_output_copies_exact_complete_records(self) -> None:
        selected = [0, 1, 2, 3, 8, 9, 6, 7]
        for destination, source_id in enumerate(selected):
            for offset, stride in (
                (native.STREAM0_OFFSET, native.STREAM0_STRIDE),
                (native.STREAM1_OFFSET, native.STREAM1_STRIDE),
            ):
                self.assertEqual(
                    self.output[offset + destination * stride:offset + (destination + 1) * stride],
                    self.source[offset + source_id * stride:offset + (source_id + 1) * stride],
                )
        self.assertEqual(
            self.output[native.STREAM0_OFFSET + 8 * native.STREAM0_STRIDE:native.STREAM0_END],
            self.source[native.STREAM0_OFFSET + 8 * native.STREAM0_STRIDE:native.STREAM0_END],
        )
        self.assertEqual(
            self.output[native.STREAM1_OFFSET + 8 * native.STREAM1_STRIDE:native.STREAM1_END],
            self.source[native.STREAM1_OFFSET + 8 * native.STREAM1_STRIDE:native.STREAM1_END],
        )
        changed = [index for index, values in enumerate(zip(self.source, self.output))
                   if values[0] != values[1]]
        self.assertEqual(changed, EXPECTED_CHANGED_OFFSETS)
        self.assertEqual(native.inspect_target(self.output, 8)["degenerate_triangle_count"], 0)
        self.assertEqual(sha256(OUTPUT_VOLUME), EXPECTED_VOLUME_SHA256)

    def test_s42_control_is_a_45_byte_route_layer_not_board_geometry(self) -> None:
        dispatch = load_canonical(S42_BUILD / "s42-dispatch-control-workflow.json")
        visible = load_canonical(S42_BUILD / "s42-visible-control-workflow.json")
        night = load_canonical(S42_BUILD / "s42-visible-night-control-workflow.json")
        layers = [dispatch, visible, night]
        changed = [set(layer["patch"]["actual_changed_byte_offsets"]) for layer in layers]
        self.assertTrue(all(left.isdisjoint(right) for index, left in enumerate(changed)
                            for right in changed[index + 1:]))
        self.assertEqual(sorted(set().union(*changed)), EXPECTED_S42_FROM_RETAIL_OFFSETS)
        self.assertEqual(sum(len(offsets) for offsets in changed), 45)
        self.assertEqual(dispatch["xdvdfs"]["source_profile_volume9_sha256"],
                         native.PACK_SHA256)
        self.assertEqual(visible["xdvdfs"]["pack9_sha256"], native.PACK_SHA256)
        self.assertEqual(night["xdvdfs"]["pack9_sha256"], native.PACK_SHA256)

    def test_candidate_disc_manifests_pin_one_identical_geometry_layer(self) -> None:
        retail = load_canonical(BUILD / "retail-xiso-workflow.json")
        s42 = load_canonical(BUILD / "s42-xiso-workflow.json")
        retail_verify = load_canonical(BUILD / "retail-xiso-verification.json")
        s42_verify = load_canonical(BUILD / "s42-xiso-verification.json")
        for manifest in (retail, s42):
            self.assertEqual(manifest["native_subset_proof"]["recipe_sha256"],
                             EXPECTED_RECIPE_SHA256)
            self.assertEqual(manifest["native_subset_proof"]["changed_volume_sha256"],
                             EXPECTED_VOLUME_SHA256)
            self.assertEqual(manifest["native_subset_proof"]["decoded_changed_byte_count"], 32)
            self.assertEqual(manifest["patch"]["changed_byte_count"], 856_572)
            self.assertEqual(manifest["patch"]["changed_run_count"], 38_041)
            self.assertTrue(manifest["patch"]["all_xiso_bytes_outside_span_bit_exact"])
        self.assertEqual(retail_verify["output_xiso_sha256"],
                         "c24c543e4518862b4de4886a1432a99c5a7651291653457927c9a9f3165f6ddc")
        self.assertEqual(s42_verify["output_xiso_sha256"],
                         "7effd276abea02aa41573ae30a8cba537ced4520b0f807809789872d864bbc60")
        self.assertTrue(retail_verify["default_xbe_exact"])
        self.assertTrue(s42_verify["default_xbe_exact"])
        self.assertTrue(retail_verify["xdvdfs_tree_exact"])
        self.assertTrue(s42_verify["xdvdfs_tree_exact"])

    def test_runtime_queue_is_complete_and_does_not_invent_gui_evidence(self) -> None:
        queue = load_canonical(RUNTIME_QUEUE)
        self.assertEqual(
            queue["schema"], "nfl2k5_upper_deck_wide_overlay8_runtime_queue/v1"
        )
        self.assertEqual(
            queue["status"], "offline_runtime_lane_fully_prepared_spark_mcp_unavailable"
        )
        self.assertTrue(queue["claims"]["controller_lane_released"])
        self.assertTrue(queue["claims"]["runtime_launch_prepared"])
        self.assertFalse(queue["claims"]["emulator_launched_for_this_queue"])
        self.assertFalse(queue["claims"]["matched_runtime_pair_captured"])
        self.assertFalse(queue["claims"]["direct_upper_deck_visibility_proved"])
        self.assertEqual(
            queue["spark_handoff"]["required_tools"],
            ["spark_desktop_task", "spark_look"],
        )
        self.assertIn(
            "never read, modify, or launch anything in a Backbreaker path",
            queue["spark_handoff"]["desktop_task_goal"],
        )
        self.assertEqual(len(queue["expected_evidence"]["screenshots"]), 5)
        for run in queue["prepared_runs"].values():
            config = ROOT / run["config"]["path"]
            hdd = ROOT / run["hdd"]["path"]
            xiso = ROOT / run["xiso"]["path"]
            self.assertEqual(config.stat().st_size, run["config"]["size"])
            self.assertEqual(hdd.stat().st_size, run["hdd"]["size"])
            self.assertEqual(xiso.stat().st_size, run["xiso"]["size"])
            self.assertEqual(sha256(config), run["config"]["sha256"])
            self.assertEqual(sha256(hdd), run["hdd"]["sha256"])
            parsed = tomllib.loads(config.read_text())
            self.assertEqual(Path(parsed["sys"]["files"]["hdd_path"]), hdd)
            self.assertEqual(Path(parsed["sys"]["files"]["dvd_path"]), xiso)


if __name__ == "__main__":
    unittest.main()
