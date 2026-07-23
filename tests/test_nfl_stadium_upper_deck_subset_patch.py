from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_upper_deck_subset_patch as writer  # noqa: E402


CATALOG = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
BOUNDARY = ROOT / "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json"
RECIPE_SCHEMA = ROOT / "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json"
PREFIX8 = ROOT / "reports/asset_samples/nfl_scne/stadium_upper_deck_prefix8_source_subset_recipe.v1.json"
NONIDENTITY4 = ROOT / "reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json"


class UpperDeckSubsetPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.authorities = writer.load_authorities(CATALOG, BOUNDARY, RECIPE_SCHEMA)
        cls.prefix8 = json.loads(PREFIX8.read_text(encoding="utf-8"))
        cls.nonidentity4 = json.loads(NONIDENTITY4.read_text(encoding="utf-8"))

    def write_json(
        self, directory: Path, value: object, *, canonical: bool = True,
        name: str = "recipe.json",
    ) -> Path:
        path = directory / name
        payload = writer.canonical_json(value) if canonical else json.dumps(value).encode("utf-8")
        path.write_bytes(payload)
        return path

    def test_pinned_authorities_and_checked_recipes_load(self) -> None:
        authority = self.authorities["authority"]
        self.assertEqual(authority["catalog"], {
            "schema": writer.base.CATALOG_SCHEMA,
            "size": writer.CATALOG_SIZE,
            "sha256": writer.CATALOG_SHA256,
            "authorized_target_count": 75,
        })
        self.assertEqual(authority["changed_count_boundary"], {
            "schema": writer.BOUNDARY_SCHEMA,
            "size": writer.BOUNDARY_SIZE,
            "sha256": writer.BOUNDARY_SHA256,
        })
        self.assertEqual(authority["recipe_schema"], {
            "schema": writer.RECIPE_SCHEMA,
            "size": writer.RECIPE_SCHEMA_SIZE,
            "sha256": writer.RECIPE_SCHEMA_SHA256,
        })

        prefix = writer.load_request(PREFIX8, False, self.authorities)
        self.assertEqual(prefix["mode"], "count_only_prefix")
        self.assertEqual(prefix["new_count"], 8)
        self.assertEqual(prefix["source_ids"], list(range(8)))
        self.assertEqual(
            prefix["summary"]["sha256"],
            "6ab4313098939202f528820cc25862cc8a289907562d61c1d5431b57a9c511e6",
        )

        remap = writer.load_request(NONIDENTITY4, False, self.authorities)
        self.assertEqual(remap["mode"], "source_subset_remap")
        self.assertEqual(remap["new_count"], 4)
        self.assertEqual(remap["source_ids"], [8, 9, 10, 11])
        self.assertEqual(
            remap["summary"]["sha256"],
            "546700178dfd2bf116beaa9bcd534c4be38a0b2f2d450590c809d605b428b311",
        )
        self.assertNotIn("source_vertex_ids", remap["summary"])
        self.assertEqual(
            remap["summary"]["source_vertex_ids_sha256"],
            hashlib.sha256(writer.canonical_json([8, 9, 10, 11])).hexdigest(),
        )

    def test_identity_request_is_flag_only_and_hashes_order_without_publishing_it(self) -> None:
        request = writer.load_request(None, True, self.authorities)
        self.assertEqual(request["mode"], "identity_noop")
        self.assertEqual(request["new_count"], 12)
        self.assertEqual(request["source_ids"], list(range(12)))
        self.assertEqual(request["summary"]["kind"], "identity_noop_flag")
        self.assertEqual(request["summary"]["schema"], writer.IDENTITY_REQUEST_SCHEMA)
        self.assertNotIn("source_vertex_ids", request["summary"])
        with self.assertRaises(writer.UpperDeckSubsetPatchError):
            writer.load_request(PREFIX8, True, self.authorities)
        with self.assertRaises(writer.UpperDeckSubsetPatchError):
            writer.load_request(None, False, self.authorities)

    def test_recipe_contract_rejects_every_count_and_source_id_escape(self) -> None:
        variants: list[object] = []
        for count in (0, 12, True):
            value = copy.deepcopy(self.prefix8)
            value["new_vertex_count"] = count
            variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["source_vertex_ids"] = list(range(7))
        variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["source_vertex_ids"] = [0, 1, 2, 3, 4, 5, 6, 6]
        variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["source_vertex_ids"][-1] = 12
        variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["source_vertex_ids"][-1] = True
        variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["source_decoded_sha256"] = "0" * 64
        variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["target_id"] = "nfl2k5/stadium/o3280/c5/s2"
        variants.append(value)
        value = copy.deepcopy(self.prefix8)
        value["positions"] = []
        variants.append(value)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, value in enumerate(variants):
                with self.subTest(index=index):
                    path = self.write_json(root, value, name=f"bad-{index}.json")
                    with self.assertRaises(writer.UpperDeckSubsetPatchError):
                        writer.load_request(path, False, self.authorities)

    def test_noncanonical_and_duplicate_json_keys_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.write_json(root, self.prefix8, canonical=False)
            with self.assertRaises(writer.UpperDeckSubsetPatchError):
                writer.load_request(path, False, self.authorities)
            path.write_text(
                '{"new_vertex_count":8,"new_vertex_count":4}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(writer.UpperDeckSubsetPatchError, "duplicate JSON key"):
                writer.load_request(path, False, self.authorities)

    def test_authority_hash_pin_rejects_even_canonical_semantic_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            changed = json.loads(BOUNDARY.read_text(encoding="utf-8"))
            changed["claim_flags"]["runtime_visibility_proved"] = True
            path = self.write_json(root, changed, name="boundary.json")
            with self.assertRaisesRegex(writer.UpperDeckSubsetPatchError, "pinned authority"):
                writer.load_authorities(CATALOG, path, RECIPE_SCHEMA)

    def test_whole_record_remap_preserves_physical_tails(self) -> None:
        for stride in (12, 10):
            with self.subTest(stride=stride):
                source = b"".join(bytes([record]) * stride for record in range(12))
                result = writer.remap_stream_prefix(source, stride, 12, [8, 9, 10, 11])
                self.assertEqual(
                    result[:4 * stride],
                    b"".join(bytes([record]) * stride for record in (8, 9, 10, 11)),
                )
                self.assertEqual(result[4 * stride:], source[4 * stride:])
                self.assertEqual(source, b"".join(bytes([record]) * stride for record in range(12)))

    def test_remap_helper_rejects_partial_duplicate_boolean_and_bad_extent(self) -> None:
        source = bytes(range(36))
        invalid = (
            [0, 1, 2],
            [0, 1, 1, 2],
            [0, 1, 2, True],
            [0, 1, 2, 12],
        )
        for source_ids in invalid:
            with self.subTest(source_ids=source_ids):
                with self.assertRaises(writer.UpperDeckSubsetPatchError):
                    writer.remap_stream_prefix(source, 3, 12, source_ids)
        with self.assertRaises(writer.UpperDeckSubsetPatchError):
            writer.remap_stream_prefix(source[:-1], 3, 12, [0, 1, 2, 3])

    def test_identity_build_returns_validated_source_span_without_compression(self) -> None:
        decoded = bytes(writer.base.DECODED_SIZE)
        retail_stream = bytes(writer.base.RETAIL_CONSUMED)
        tail = bytes(writer.base.OPAQUE_TAIL_SIZE)
        source_span = bytes(writer.base.CHUNK_SPAN_SIZE - len(tail)) + tail
        source = {
            "decoded": decoded,
            "retail_stream": retail_stream,
            "tail": tail,
            "span": source_span,
        }
        request = writer.load_request(None, True, self.authorities)
        with (
            mock.patch.object(writer, "_validate_source_decoded"),
            mock.patch.object(writer, "compress_vc_lz",
                              side_effect=AssertionError("identity must not recompress")),
            mock.patch.object(writer, "minimum_vc_lz_overlap_scratch", return_value=0),
            mock.patch.object(writer.base, "RETAIL_STREAM_SHA256", writer.sha256(retail_stream)),
            mock.patch.object(writer.base, "OPAQUE_TAIL_SHA256", writer.sha256(tail)),
        ):
            rebuilt, build = writer.build_span(source, request, self.authorities)
        self.assertEqual(rebuilt, source_span)
        self.assertEqual(build["mode"], "identity_noop")
        self.assertEqual(build["decoded_changed_byte_count"], 0)
        self.assertEqual(build["count_control_changed_byte_count"], 0)
        self.assertEqual(build["stream_changed_byte_counts"], [0, 0])

    @unittest.skipUnless(
        (ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0").is_file(),
        "pinned user-owned NFL 2K5 extraction is unavailable",
    )
    def test_pinned_retail_in_memory_identity_prefix8_and_nonidentity4(self) -> None:
        index = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
        source = writer.base._validate_source(
            index, self.authorities["catalog"], self.authorities["row"]
        )
        cases = (
            (
                writer.load_request(None, True, self.authorities),
                {
                    "mode": "identity_noop",
                    "span_sha256": writer.base.CHUNK_SPAN_SHA256,
                    "decoded_sha256": writer.base.DECODED_SHA256,
                    "changed": 0,
                    "count_changed": 0,
                    "streams_changed": [0, 0],
                    "encoded_bytes": 908_864,
                    "encoded_sha256": writer.base.RETAIL_STREAM_SHA256,
                    "scratch": 16,
                },
            ),
            (
                writer.load_request(PREFIX8, False, self.authorities),
                {
                    "mode": "count_only_prefix",
                    "span_sha256": "68c60f2055c8b4d343dad8a16610fdecf45fb060893201ee98902a3d931dc829",
                    "decoded_sha256": "dffa0cc9aa4599c94fe436ec8599c8b9597eacb0d377865c6454a733cf56f272",
                    "changed": 2,
                    "count_changed": 2,
                    "streams_changed": [0, 0],
                    "encoded_bytes": 908_863,
                    "encoded_sha256": "09a02cccb40f017445289d9b3db2067df75f6fa9f1e8e22099b5a5f789c1ae5a",
                    "scratch": 32,
                },
            ),
            (
                writer.load_request(NONIDENTITY4, False, self.authorities),
                {
                    "mode": "source_subset_remap",
                    "span_sha256": "a06178f73e72ee40a25af3f28857d12056945e362f17152fb7c8e8b32e5b7974",
                    "decoded_sha256": "5503271598c6f55edb0f4d19b5232cadd55a9869029bf343287cb2157c4b9f93",
                    "changed": 64,
                    "count_changed": 2,
                    "streams_changed": [34, 28],
                    "encoded_bytes": 908_822,
                    "encoded_sha256": "6372ef3baee483d4bd6b3b6e9c045c509a31b9b82357a09a2d7baa8b5f33e1b0",
                    "scratch": 64,
                },
            ),
        )
        for request, expected in cases:
            with self.subTest(mode=expected["mode"]):
                span, build = writer.build_span(source, request, self.authorities)
                self.assertEqual(build["mode"], expected["mode"])
                self.assertEqual(writer.sha256(span), expected["span_sha256"])
                self.assertEqual(build["decoded_after_sha256"], expected["decoded_sha256"])
                self.assertEqual(build["decoded_changed_byte_count"], expected["changed"])
                self.assertEqual(
                    build["count_control_changed_byte_count"], expected["count_changed"]
                )
                self.assertEqual(
                    build["stream_changed_byte_counts"], expected["streams_changed"]
                )
                self.assertEqual(build["encoded_bytes"], expected["encoded_bytes"])
                self.assertEqual(build["encoded_sha256"], expected["encoded_sha256"])
                self.assertEqual(build["scratch_after"], expected["scratch"])
                self.assertTrue(all(row["bit_exact"] for row in build["physical_tails"]))
                self.assertEqual(
                    build["complement_before_sha256"], build["complement_after_sha256"]
                )

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

                def fileno(self) -> int:
                    return self.stream.fileno()

                def read(self, size: int = -1) -> bytes:
                    if not self.raced:
                        self.raced = True
                        staged.unlink()
                        staged.symlink_to(victim)
                    return self.stream.read(size)

            class RacingSource:
                def open(self, mode: str) -> RacingReader:
                    if mode != "rb":
                        raise AssertionError(mode)
                    return RacingReader()

            with (
                mock.patch.object(writer.base, "PACK_SIZE", 8),
                mock.patch.object(writer.base, "CHUNK_PACK_OFFSET", 2),
                mock.patch.object(writer.base, "CHUNK_SPAN_SIZE", 2),
            ):
                with self.assertRaisesRegex(
                    writer.UpperDeckSubsetPatchError, "pathname changed during copy/patch"
                ):
                    writer._copy_and_patch_owned_volume(
                        RacingSource(), staged, b"XY"  # type: ignore[arg-type]
                    )
            self.assertEqual(victim.read_bytes(), b"DO-NOT-CHANGE")
            self.assertTrue(staged.is_symlink())

    def test_writer_never_imports_an_independent_verifier(self) -> None:
        source = (ROOT / "tools/nfl_stadium_upper_deck_subset_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("nfl_stadium_upper_deck_subset_verify", source)
        self.assertNotIn("import verifier", source)


if __name__ == "__main__":
    unittest.main()
