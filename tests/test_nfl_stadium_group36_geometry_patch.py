from __future__ import annotations

import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_group36_geometry_patch as writer  # noqa: E402
import nfl_stadium_group36_geometry_verify as verifier  # noqa: E402


SAMPLE = ROOT / "reports/asset_samples/nfl_scne/stadium_group36_zero_positions_permuted_quad_recipe.json"


class GeometryPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recipe = json.loads(SAMPLE.read_bytes())

    def write_recipe(self, directory: Path, value: object, canonical: bool = True) -> Path:
        path = directory / "recipe.json"
        raw = writer._canonical_json(value) if canonical else json.dumps(value).encode()
        path.write_bytes(raw)
        return path

    def test_checked_nonretail_recipe_is_canonical_and_valid(self) -> None:
        parsed = writer.load_recipe(SAMPLE)
        self.assertEqual(parsed["indices"], [0, 2, 1, 3])
        self.assertEqual(parsed["packed_positions"], bytes(48))

    def test_duplicate_indices_are_mechanically_admitted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            value = copy.deepcopy(self.recipe)
            value["indices"] = [0, 0, 1, 2]
            parsed = writer.load_recipe(self.write_recipe(Path(temporary), value))
            self.assertEqual(parsed["indices"], [0, 0, 1, 2])

    def test_index_escape_and_boolean_fail_closed(self) -> None:
        for invalid in ([0, 1, 2, 4], [0, 1, 2, True]):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                value = copy.deepcopy(self.recipe)
                value["indices"] = invalid
                with self.assertRaises(writer.GeometryPatchError):
                    writer.load_recipe(self.write_recipe(Path(temporary), value))

    def test_huge_json_integer_is_a_domain_refusal_in_both_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            value = copy.deepcopy(self.recipe)
            value["positions"][0][0] = 10 ** 400
            path = self.write_recipe(Path(temporary), value)
            with self.assertRaisesRegex(writer.GeometryPatchError, "binary32 range"):
                writer.load_recipe(path)
            with self.assertRaisesRegex(verifier.GeometryVerifyError, "binary32 range"):
                verifier.load_recipe(path)

    def test_noop_returns_source_span_without_recompression(self) -> None:
        decoded = bytearray(writer.base.DECODED_SIZE)
        struct.pack_into(
            "<7I", decoded, writer.base.PUSH_OFFSET,
            0x000417FC, 8, 0x40081800, 0x00010000,
            0x00030002, 0x000417FC, 0,
        )
        source_span = bytes(writer.base.CHUNK_SPAN_SIZE)
        source = {
            "decoded": bytes(decoded),
            "retail_stream": bytes(writer.base.RETAIL_CONSUMED),
            "span": source_span,
            "tail": bytes(writer.base.OPAQUE_TAIL_SIZE),
        }
        with (
            mock.patch.object(
                writer, "compress_vc_lz",
                side_effect=AssertionError("no-op must not invoke the compressor"),
            ),
            mock.patch.object(writer, "minimum_vc_lz_overlap_scratch", return_value=0),
        ):
            rebuilt, result = writer.build_span(
                source, bytes(writer.base.POSITION_SIZE), [0, 1, 2, 3]
            )
        self.assertEqual(rebuilt, source_span)
        self.assertEqual(result["mode"], "no_op")
        self.assertEqual(result["decoded_changed_byte_count"], 0)

    def test_noncanonical_and_duplicate_json_key_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "recipe.json"
            path.write_text(json.dumps(self.recipe))
            with self.assertRaises(writer.GeometryPatchError):
                writer.load_recipe(path)
            path.write_text('{"schema":"a","schema":"b"}\n')
            with self.assertRaises(writer.GeometryPatchError):
                writer.load_recipe(path)

    def test_push_parser_reports_permutation_and_degeneracy(self) -> None:
        decoded = bytearray(writer.base.DECODED_SIZE)
        struct.pack_into("<7I", decoded, writer.base.PUSH_OFFSET,
                         0x000417FC, 8, 0x40081800, 0x00020000,
                         0x00030001, 0x000417FC, 0)
        result = verifier.parse_quad_push(bytes(decoded))
        self.assertEqual(result["indices"], [0, 2, 1, 3])
        self.assertTrue(result["indices_are_permutation"])
        self.assertEqual(result["nondegenerate_triangle_count"], 2)
        struct.pack_into("<4H", decoded, writer.INDEX_PARAMETER_OFFSET, 0, 0, 1, 2)
        result = verifier.parse_quad_push(bytes(decoded))
        self.assertFalse(result["indices_are_permutation"])
        self.assertGreater(result["degenerate_triangle_count"], 0)

    def test_independent_verifier_does_not_import_geometry_writer(self) -> None:
        source = (ROOT / "tools/nfl_stadium_group36_geometry_verify.py").read_text()
        self.assertNotIn("import nfl_stadium_group36_geometry_patch", source)
        self.assertNotIn("from nfl_stadium_group36_geometry_patch", source)

    def test_copy_patch_descriptor_cannot_be_redirected_by_symlink_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"abcdefgh")
            staged = root / "staged"
            victim = root / "victim"
            victim.write_bytes(b"DO-NOT-CHANGE")

            class RacingReader:
                def __init__(self) -> None:
                    self.stream = source.open("rb")
                    self.raced = False

                def __enter__(self) -> "RacingReader":
                    return self

                def __exit__(self, *args: object) -> None:
                    self.stream.close()

                def read(self, size: int = -1) -> bytes:
                    if not self.raced:
                        self.raced = True
                        staged.unlink()
                        staged.symlink_to(victim)
                    return self.stream.read(size)

            class RacingSource:
                def open(self, mode: str) -> RacingReader:
                    self_mode = mode
                    if self_mode != "rb":
                        raise AssertionError(self_mode)
                    return RacingReader()

            with self.assertRaisesRegex(
                writer.GeometryPatchError, "pathname changed during copy/patch"
            ):
                writer._copy_and_patch_owned_volume(
                    RacingSource(),  # type: ignore[arg-type]
                    staged,
                    b"XY",
                    patch_offset=2,
                    expected_size=8,
                )
            self.assertEqual(victim.read_bytes(), b"DO-NOT-CHANGE")
            self.assertTrue(staged.is_symlink())

    def test_machine_schema_matches_runtime_recipe_boundary(self) -> None:
        schema = json.loads((
            ROOT / "reports/specs/nfl2k5_group36_same_footprint_geometry_recipe.schema.json"
        ).read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["target"]["const"], writer.TARGET)
        self.assertEqual(schema["properties"]["profile_contract"]["const"], writer.PROFILE_CONTRACT)
        indices = schema["properties"]["indices"]
        self.assertEqual((indices["minItems"], indices["maxItems"]), (4, 4))
        self.assertEqual((indices["items"]["minimum"], indices["items"]["maximum"]), (0, 3))


if __name__ == "__main__":
    unittest.main()
