from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_catalog_position_patch as writer  # noqa: E402
import nfl_stadium_catalog_position_verify as verifier  # noqa: E402


CATALOG_PATH = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
ZERO_RECIPE = ROOT / "reports/asset_samples/nfl_scne/stadium_upper_deck_nonretail_zero_recipe.v2.json"


class CatalogPositionPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog_left = writer.load_catalog(CATALOG_PATH)
        cls.catalog_right = verifier.load_catalog(CATALOG_PATH)
        cls.base = json.loads(ZERO_RECIPE.read_text())

    def write(self, root: Path, value: object, *, canonical: bool = True) -> Path:
        path = root / "recipe.json"
        path.write_bytes(writer.canonical_json(value) if canonical else json.dumps(value).encode())
        return path

    def rejected_by_both(self, path: Path) -> None:
        with self.assertRaises(writer.CatalogPositionPatchError):
            writer.load_recipe(path, self.catalog_left)
        with self.assertRaises(verifier.CatalogPositionVerifyError):
            verifier.load_recipe(path, self.catalog_right)

    def test_pinned_catalog_and_nonretail_witness_are_agreed(self) -> None:
        left = writer.load_recipe(ZERO_RECIPE, self.catalog_left)
        right = verifier.load_recipe(ZERO_RECIPE, self.catalog_right)
        self.assertEqual(left["target_id"], "nfl2k5/stadium/o3280/c5/s1")
        self.assertEqual(left["contract"]["vertex_count"], 12)
        self.assertEqual(left["packed"], bytes(144))
        self.assertEqual(left["packed"], right["packed"])
        self.assertEqual(left["sha256"], right["sha256"])
        self.assertEqual(len(self.catalog_left["targets"]), 75)

    def test_schema_exposes_procedural_exact_count_boundary(self) -> None:
        schema = json.loads((ROOT / "reports/specs/nfl2k5_catalog_static_position_recipe.v2.schema.json").read_text())
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["catalog"]["properties"]["sha256"]["const"], writer.CATALOG_SHA256)
        self.assertEqual(schema["properties"]["positions"]["maxItems"], 1877)
        self.assertIn("procedural loader", schema["description"])

    def test_wrong_target_count_hash_and_extra_field_are_rejected(self) -> None:
        variants = []
        unknown = copy.deepcopy(self.base); unknown["target_id"] = "nfl2k5/stadium/o3280/c5/s999"; variants.append(unknown)
        count = copy.deepcopy(self.base); count["positions"].pop(); variants.append(count)
        catalog = copy.deepcopy(self.base); catalog["catalog"]["sha256"] = "0" * 64; variants.append(catalog)
        extra = copy.deepcopy(self.base); extra["topology"] = []; variants.append(extra)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, value in enumerate(variants):
                path = root / f"bad-{index}.json"; path.write_bytes(writer.canonical_json(value))
                self.rejected_by_both(path)

    def test_noncanonical_duplicate_boolean_and_nonexact_f32_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.rejected_by_both(self.write(root, self.base, canonical=False))
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"catalog":{},"positions":[],"schema":"x","schema":"y","target_id":"x"}')
            self.rejected_by_both(duplicate)
            for index, bad in enumerate((True, 1.1, 1e100, 10 ** 1000)):
                value = copy.deepcopy(self.base); value["positions"][0][0] = bad
                path = root / f"number-{index}.json"; path.write_bytes(writer.canonical_json(value))
                self.rejected_by_both(path)

    def test_independent_verifier_does_not_import_writer_or_project_modules(self) -> None:
        text = (ROOT / "tools/nfl_stadium_catalog_position_verify.py").read_text()
        self.assertNotIn("nfl_stadium_catalog_position_patch", text)
        self.assertNotIn("from nfl_", text)
        self.assertNotIn("import nfl_", text)

    def test_independent_decoder_and_alias_math(self) -> None:
        stream = struct.pack("<IIB", 6, 1, 12) + bytes((0x08,)) + b"ABC" + struct.pack("<H", 3)
        decoded, info = verifier.decompress_vc_lz(stream, 6)
        self.assertEqual(decoded, b"ABCABC")
        self.assertEqual(info["consumed"], len(stream))
        self.assertGreaterEqual(verifier.minimum_overlap_scratch(stream, len(stream), 6), 0)

    def test_symlinked_output_parent_is_refused_before_source_access(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); real = root / "real"; real.mkdir()
            linked = root / "linked"; linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(writer.CatalogPositionPatchError, "non-symlink"):
                writer.patch(root / "missing-index", CATALOG_PATH, ZERO_RECIPE, linked / "out")

    def test_publication_refuses_raced_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / "out"; output.mkdir()
            staging = output / ".staging"; staging.mkdir()
            (staging / "9").write_bytes(b"ours"); (staging / "manifest.json").write_bytes(b"manifest")
            known = {name: writer._inode(staging / name) for name in ("9", "manifest.json")}
            (output / "9").write_bytes(b"attacker")
            with self.assertRaisesRegex(writer.CatalogPositionPatchError, "raced artifact"):
                writer._publish_staged_no_replace(output, writer._inode(output), staging,
                                                   writer._inode(staging), known)
            self.assertEqual((output / "9").read_bytes(), b"attacker")

    def test_copy_patch_descriptor_cannot_be_redirected_by_symlink_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "source"; source.write_bytes(b"abcdefgh")
            staged = root / "staged"; victim = root / "victim"; victim.write_bytes(b"DO-NOT-CHANGE")

            class RacingReader:
                def __init__(self) -> None:
                    self.stream = source.open("rb"); self.raced = False
                def __enter__(self) -> "RacingReader": return self
                def __exit__(self, *args: object) -> None: self.stream.close()
                def read(self, size: int = -1) -> bytes:
                    if not self.raced:
                        self.raced = True; staged.unlink(); staged.symlink_to(victim)
                    return self.stream.read(size)

            class RacingSource:
                def open(self, mode: str) -> RacingReader:
                    self.assert_mode = mode
                    if mode != "rb": raise AssertionError(mode)
                    return RacingReader()

            with mock.patch.object(writer, "PACK_SIZE", 8), \
                    mock.patch.object(writer, "CHUNK_PACK_OFFSET", 2), \
                    mock.patch.object(writer, "CHUNK_SPAN_SIZE", 2):
                with self.assertRaisesRegex(writer.CatalogPositionPatchError,
                                            "pathname changed during copy/patch"):
                    writer._copy_and_patch_owned_volume(RacingSource(), staged, b"XY")  # type: ignore[arg-type]
            self.assertEqual(victim.read_bytes(), b"DO-NOT-CHANGE")
            self.assertTrue(staged.is_symlink())

    def test_independent_verifier_rejects_hardlink_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / "source"; source.write_bytes(b"retail")
            alias = root / "alias"; os.link(source, alias)
            with self.assertRaisesRegex(verifier.CatalogPositionVerifyError, "inode aliases"):
                verifier.require_distinct_files(source, alias)


if __name__ == "__main__":
    unittest.main()
