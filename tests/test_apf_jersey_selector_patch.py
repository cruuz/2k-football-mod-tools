from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_inner  # noqa: E402
import apf_jersey_selector_patch as patch  # noqa: E402


SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"
RECIPES = ROOT / "reports/asset_samples/apf_roster"


class APFJerseySelectorPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = patch._validate_source(SOURCE)

    def build(self, recipe: str) -> patch.BuildResult:
        with mock.patch.object(patch, "_validate_source", return_value=self.source):
            return patch.build_patch(SOURCE, RECIPES / recipe)

    def test_source_layout_and_two_bank_derivation(self) -> None:
        _, entry, record, outer, stored, decoded, layout = self.source
        self.assertEqual(entry.table_index, 1126)
        self.assertEqual(len(outer), 436_224)
        self.assertEqual(record.file_length, 435_329)
        self.assertEqual(len(stored), 435_245)
        self.assertEqual(patch.sha256_bytes(decoded), patch.DECODED_SHA256)
        self.assertEqual(layout.offsets[22], (0x1E02B8, 0x1E0248))
        self.assertEqual(layout.record_indices[22], (18, 4))
        self.assertEqual(tuple(decoded[offset] for offset in layout.offsets[22]), (4, 4))

    def test_identity_is_outer_span_bit_exact(self) -> None:
        result = self.build("jersey_wasps_identity.v1.json")
        self.assertEqual(result.entry, self.source[3])
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.manifest["preservation"]["decoded_changed_byte_count"], 0)
        self.assertEqual(result.manifest["compression"]["payload_size_after"], 435_225)
        self.assertTrue(result.manifest["compression"]["identity_noop_returned_source_span_verbatim"])
        self.assertFalse(result.manifest["compression"]["changed_path_recompressed"])

    def test_wasps_targeted_changes_exactly_two_byte_zero_values(self) -> None:
        result = self.build("jersey_wasps_4_to_21_targeted.v1.json")
        decoded = apf_inner.decompress_h7a(
            result.entry[104 : result.manifest["result"]["file_length_after"]],
            patch.DECODED_SIZE,
            patch.H7A_SHIFT,
        )
        source = self.source[5]
        differences = [index for index, pair in enumerate(zip(source, decoded)) if pair[0] != pair[1]]
        self.assertEqual(differences, [0x1E0248, 0x1E02B8])
        self.assertEqual([decoded[index] for index in differences], [21, 21])
        for offset in self.source[6].offsets[22]:
            self.assertEqual(decoded[offset + 1 : offset + 8], source[offset + 1 : offset + 8])
        self.assertEqual(result.manifest["compression"]["payload_size_after"], 435_231)
        self.assertEqual(result.manifest["compression"]["headroom_bytes_after"], 793)
        self.assertEqual(
            result.manifest["compression"]["payload_sha256_after"],
            "8ac85217c64dc5a212ad43b20d02f473e9c1128859c34d2cb2f36f78be64131b",
        )

    def test_full_plan_changes_thirty_bytes_and_is_unique(self) -> None:
        result = self.build("jersey_all_24_built_in_unique.v1.json")
        file_length = result.manifest["result"]["file_length_after"]
        decoded = apf_inner.decompress_h7a(
            result.entry[104:file_length], patch.DECODED_SIZE, patch.H7A_SHIFT
        )
        source = self.source[5]
        differences = [index for index, pair in enumerate(zip(source, decoded)) if pair[0] != pair[1]]
        self.assertEqual(len(differences), 30)
        self.assertEqual(set(differences), {
            offset
            for team in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19, 20, 21, 22, 23)
            for offset in self.source[6].offsets[team]
        })
        assets = [decoded[self.source[6].offsets[team][0]] for team in range(24)]
        self.assertEqual(sorted(assets), list(range(24)))
        self.assertEqual(result.manifest["compression"]["payload_size_after"], 435_262)
        self.assertEqual(result.manifest["compression"]["headroom_bytes_after"], 762)
        self.assertEqual(
            result.manifest["compression"]["payload_sha256_after"],
            "3d9d90f139e96803a1ff3d80a2d3f76c45ce20d174e722c91285ed1a45cc12fa",
        )
        self.assertEqual(
            result.manifest["preservation"]["decoded_output_sha256"],
            "13997341f21a8ead74fc7526c28d7f2dfe8ff886abc64acd243ff96448db0cd2",
        )
        self.assertEqual(result.manifest["compression"]["output_token_count"], 284_047)
        self.assertEqual(result.manifest["compression"]["retail_tokens_split_or_replaced"], 20)

    def _recipe_document(self, name: str) -> dict[str, object]:
        return json.loads((RECIPES / name).read_text(encoding="utf-8"))

    def _write_recipe(self, document: dict[str, object], *, canonical: bool = True) -> Path:
        temporary = tempfile.NamedTemporaryFile("wb", delete=False)
        raw = patch.canonical_json_bytes(document) if canonical else json.dumps(document).encode("utf-8")
        temporary.write(raw)
        temporary.close()
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_recipe_rejects_wrong_expected_retail_asset(self) -> None:
        document = self._recipe_document("jersey_wasps_4_to_21_targeted.v1.json")
        document["assignments"][0]["expected_retail_asset_index"] = 23
        with self.assertRaisesRegex(patch.PatchError, "expected retail asset"):
            patch.load_recipe(self._write_recipe(document))

    def test_recipe_rejects_duplicate_or_unsorted_teams(self) -> None:
        document = self._recipe_document("jersey_wasps_4_to_21_targeted.v1.json")
        document["assignments"] = [copy.deepcopy(document["assignments"][0])] * 2
        with self.assertRaisesRegex(patch.PatchError, "strictly increasing"):
            patch.load_recipe(self._write_recipe(document))

    def test_full_mode_rejects_duplicate_asset_allocation(self) -> None:
        document = self._recipe_document("jersey_all_24_built_in_unique.v1.json")
        document["assignments"][23]["replacement_asset_index"] = 21
        with self.assertRaisesRegex(patch.PatchError, "permutation"):
            patch.load_recipe(self._write_recipe(document))

    def test_recipe_rejects_noncanonical_json(self) -> None:
        document = self._recipe_document("jersey_wasps_identity.v1.json")
        with self.assertRaisesRegex(patch.PatchError, "canonical"):
            patch.load_recipe(self._write_recipe(document, canonical=False))

    def test_encoder_rejects_wrong_retail_decode(self) -> None:
        retail = self.source[4][20:]
        wrong = bytes([self.source[5][0] ^ 1]) + self.source[5][1:]
        with self.assertRaisesRegex(patch.PatchError, "does not decode"):
            patch.encode_preserving_h7a(retail, wrong, self.source[5], patch.H7A_SHIFT)

    def test_changed_build_rejects_h7a_allocation_overflow(self) -> None:
        with mock.patch.object(patch, "_validate_source", return_value=self.source):
            with mock.patch.object(
                patch,
                "encode_preserving_h7a",
                return_value=(bytes(patch.MAX_H7A_PAYLOAD_SIZE + 1), {}),
            ):
                with self.assertRaisesRegex(
                    patch.PatchError, "H7A payload exceeds fixed allocation"
                ):
                    patch.build_patch(
                        SOURCE,
                        RECIPES / "jersey_wasps_4_to_21_targeted.v1.json",
                    )

    def test_output_paths_reject_aliases_symlink_parents_and_existing_files(self) -> None:
        recipe = RECIPES / "jersey_wasps_identity.v1.json"
        errors = (patch.PatchError, patch.transport.PatchError)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            alias = root / "same-output"
            with self.assertRaisesRegex(errors, "colliding output paths"):
                patch.write_output(SOURCE, recipe, alias, alias)
            self.assertFalse(alias.exists())

            existing_output = root / "existing-output"
            existing_output.write_bytes(b"sentinel output")
            absent_manifest = root / "absent-manifest"
            with self.assertRaisesRegex(errors, "existing output volume"):
                patch.write_output(
                    SOURCE, recipe, existing_output, absent_manifest
                )
            self.assertEqual(existing_output.read_bytes(), b"sentinel output")
            self.assertFalse(absent_manifest.exists())

            absent_output = root / "absent-output"
            existing_manifest = root / "existing-manifest"
            existing_manifest.write_bytes(b"sentinel manifest")
            with self.assertRaisesRegex(errors, "existing manifest"):
                patch.write_output(
                    SOURCE, recipe, absent_output, existing_manifest
                )
            self.assertFalse(absent_output.exists())
            self.assertEqual(existing_manifest.read_bytes(), b"sentinel manifest")

            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(errors, "parent is not a real directory"):
                patch.write_output(
                    SOURCE,
                    recipe,
                    linked_parent / "output",
                    real_parent / "manifest",
                )

    def test_write_failure_removes_only_owned_output_and_manifest(self) -> None:
        recipe = RECIPES / "jersey_wasps_identity.v1.json"
        result = self.build("jersey_wasps_identity.v1.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "output-0A"
            manifest = root / "manifest.json"

            def fake_source(_path: Path) -> patch.BoundSourceVolume:
                descriptor = os.open(SOURCE, os.O_RDONLY)
                metadata = os.fstat(descriptor)
                return patch.BoundSourceVolume(
                    path=SOURCE.resolve(),
                    descriptor=descriptor,
                    identity=(metadata.st_dev, metadata.st_ino),
                    size=metadata.st_size,
                    times=(metadata.st_mtime_ns, metadata.st_ctime_ns),
                    metadata=metadata,
                    sha256=patch.SOURCE_VOLUME_SHA256,
                )

            copied = {
                "volume_size": patch.SOURCE_VOLUME_SIZE,
                "source_volume_sha256_before": patch.SOURCE_VOLUME_SHA256,
                "source_volume_sha256_after": patch.SOURCE_VOLUME_SHA256,
                "outside_replacement": {
                    "prefix_sha256": "0" * 64,
                    "suffix_sha256": patch.SOURCE_SUFFIX_SHA256,
                },
                "output_volume_sha256": patch.SOURCE_VOLUME_SHA256,
            }

            with mock.patch.object(patch, "build_patch", return_value=result):
                with mock.patch.object(
                    patch, "_bind_source_volume", side_effect=fake_source
                ):
                    with mock.patch.object(
                        patch,
                        "_write_bound_copied_volume",
                        return_value=(copied, (0, 0)),
                    ):
                        with self.assertRaisesRegex(
                            patch.PatchError, "copied 0A complement differs"
                        ):
                            patch.write_output(SOURCE, recipe, output, manifest)
            self.assertFalse(output.exists())
            self.assertFalse(manifest.exists())

    def test_wrong_source_is_refused_before_parse(self) -> None:
        with tempfile.NamedTemporaryFile() as temporary:
            with self.assertRaisesRegex(patch.PatchError, "pinned regular"):
                patch._validate_source(Path(temporary.name))


if __name__ == "__main__":
    unittest.main()
