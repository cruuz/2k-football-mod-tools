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

import nfl_stadium_group36_position_patch as writer  # noqa: E402
import nfl_stadium_group36_position_verify as verifier  # noqa: E402


class Group36PositionPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = {
            "schema": writer.RECIPE_SCHEMA,
            "target": writer.TARGET,
            "encoding": writer.ENCODING,
            "positions": [[0, 0, 0] for _ in range(4)],
        }

    def write(self, directory: Path, value: object, *, canonical: bool = True) -> Path:
        path = directory / "recipe.json"
        payload = writer.canonical_json(value) if canonical else json.dumps(value).encode()
        path.write_bytes(payload)
        return path

    def assert_rejected_by_both(self, path: Path) -> None:
        with self.assertRaises(writer.PositionPatchError):
            writer.load_recipe(path)
        with self.assertRaises(verifier.VerifyError):
            verifier.load_recipe(path)

    def test_checked_zero_recipe_is_canonical_and_agreed(self) -> None:
        path = ROOT / "reports/asset_samples/nfl_scne/stadium_group36_zero_recipe.json"
        left = writer.load_recipe(path)
        right = verifier.load_recipe(path)
        self.assertEqual(left["packed"], bytes(48))
        self.assertEqual(left["packed"], right["packed"])
        self.assertEqual(left["sha256"], right["sha256"])

    def test_recipe_schema_and_encoding_are_const_pinned(self) -> None:
        schema = json.loads(
            (ROOT / "reports/specs/nfl2k5_static_position_recipe.schema.json").read_text()
        )
        self.assertEqual(schema["properties"]["target"]["const"], writer.TARGET)
        self.assertEqual(schema["properties"]["encoding"]["const"], writer.ENCODING)
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["positions"]["minItems"], 4)
        self.assertEqual(schema["properties"]["positions"]["maxItems"], 4)

    def test_extra_fields_wrong_constants_and_wrong_counts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            variants = []
            extra = copy.deepcopy(self.base)
            extra["topology"] = [0, 1, 2, 3]
            variants.append(extra)
            wrong_target = copy.deepcopy(self.base)
            wrong_target["target"]["shape_index"] = 5
            variants.append(wrong_target)
            wrong_encoding = copy.deepcopy(self.base)
            wrong_encoding["encoding"]["vertex_count"] = 5
            variants.append(wrong_encoding)
            wrong_count = copy.deepcopy(self.base)
            wrong_count["positions"] = [[0, 0, 0]] * 5
            variants.append(wrong_count)
            wrong_components = copy.deepcopy(self.base)
            wrong_components["positions"][0] = [0, 0]
            variants.append(wrong_components)
            for index, value in enumerate(variants):
                path = root / f"bad-{index}.json"
                path.write_bytes(writer.canonical_json(value))
                self.assert_rejected_by_both(path)

    def test_noncanonical_duplicate_boolean_and_nonexact_f32_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compact = self.write(root, self.base, canonical=False)
            self.assert_rejected_by_both(compact)

            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"encoding":{},"positions":[],"schema":"x","schema":"y","target":{}}',
                encoding="utf-8",
            )
            self.assert_rejected_by_both(duplicate)

            for index, bad in enumerate((True, 1.1, 1e100)):
                value = copy.deepcopy(self.base)
                value["positions"][0][0] = bad
                path = root / f"number-{index}.json"
                path.write_bytes(writer.canonical_json(value))
                self.assert_rejected_by_both(path)

            nan_path = root / "nan.json"
            text = writer.canonical_json(self.base).decode().replace("0,", "NaN,", 1)
            nan_path.write_text(text, encoding="utf-8")
            self.assert_rejected_by_both(nan_path)

    def test_independent_vc_lz_decoder_handles_literal_and_backward_match(self) -> None:
        # Tokens: literal A/B/C followed by a distance-3, length-3 match.
        stream = struct.pack("<IIB", 6, 1, 12) + bytes((0x08,)) + b"ABC" + struct.pack("<H", 3)
        decoded, info = verifier.decompress_vc_lz(stream, 6)
        self.assertEqual(decoded, b"ABCABC")
        self.assertEqual(info["consumed"], len(stream))
        self.assertEqual((info["literals"], info["matches"]), (3, 1))
        self.assertGreaterEqual(verifier.minimum_overlap_scratch(stream, len(stream), 6), 0)

    def test_writer_rejects_symlinked_output_parent_before_source_access(self) -> None:
        recipe = ROOT / "reports/asset_samples/nfl_scne/stadium_group36_zero_recipe.json"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir()
            linked = root / "linked"
            linked.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(
                writer.PositionPatchError, "non-symlink directory"
            ):
                writer.patch(root / "missing-index", recipe, linked / "output")

    def test_independent_manifest_key_gate_rejects_extras(self) -> None:
        with self.assertRaises(verifier.VerifyError):
            verifier.require_keys({"schema": "x", "extra": True}, {"schema"}, "test")

    def test_independent_verifier_rejects_hardlink_alias_inode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.write_bytes(b"retail")
            alias = root / "alias"
            alias.hardlink_to(source)
            with self.assertRaisesRegex(verifier.VerifyError, "inode aliases"):
                verifier.require_distinct_files(source, alias)

    def test_atomic_publication_never_replaces_race_created_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reservation = root / "output"
            reservation.mkdir()
            staging = reservation / ".staging-test"
            staging.mkdir()
            (staging / "9").write_bytes(b"ours-pack")
            (staging / "manifest.json").write_bytes(b"ours-manifest")
            raced = reservation / "9"
            raced.write_bytes(b"attacker")
            with self.assertRaisesRegex(
                writer.PositionPatchError, "unexpected raced artifact"
            ):
                writer._publish_staged_no_replace(  # type: ignore[attr-defined]
                    reservation, writer._inode(reservation), staging,  # type: ignore[attr-defined]
                    writer._inode(staging),  # type: ignore[attr-defined]
                    {
                        "9": writer._inode(staging / "9"),  # type: ignore[attr-defined]
                        "manifest.json": writer._inode(staging / "manifest.json"),  # type: ignore[attr-defined]
                    },
                )
            self.assertEqual(raced.read_bytes(), b"attacker")
            self.assertEqual((staging / "9").read_bytes(), b"ours-pack")

    def test_second_link_collision_cleanup_preserves_attacker_and_removes_owned_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reservation = root / "output"
            reservation.mkdir()
            reservation_inode = writer._inode(reservation)  # type: ignore[attr-defined]
            staging = reservation / ".staging-test"
            staging.mkdir()
            staging_inode = writer._inode(staging)  # type: ignore[attr-defined]
            staged_pack = staging / "9"
            staged_manifest = staging / "manifest.json"
            staged_pack.write_bytes(b"ours-pack")
            staged_manifest.write_bytes(b"ours-manifest")
            known = {
                "9": writer._inode(staged_pack),  # type: ignore[attr-defined]
                "manifest.json": writer._inode(staged_manifest),  # type: ignore[attr-defined]
            }
            real_link = writer.os.link
            calls = 0

            def raced_link(source: Path, destination: Path, **kwargs: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    real_link(source, destination, **kwargs)
                    (reservation / "manifest.json").write_bytes(b"attacker")
                    return
                real_link(source, destination, **kwargs)

            with mock.patch.object(writer.os, "link", side_effect=raced_link):
                with self.assertRaisesRegex(
                    writer.PositionPatchError, "created during publication"
                ):
                    writer._publish_staged_no_replace(  # type: ignore[attr-defined]
                        reservation, reservation_inode, staging, staging_inode, known
                    )
            # This is the same cleanup path used by patch(); it must not mask
            # the publication error or delete the raced inode.
            writer._safe_cleanup_owned_reservation(  # type: ignore[attr-defined]
                reservation, reservation_inode, staging, staging_inode, known
            )
            self.assertEqual((reservation / "manifest.json").read_bytes(), b"attacker")
            self.assertFalse((reservation / "9").exists())
            self.assertFalse(staging.exists())
            self.assertTrue(reservation.exists())

    def test_staged_replacement_before_unlink_is_preserved_and_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reservation = root / "output"
            reservation.mkdir()
            reservation_inode = writer._inode(reservation)  # type: ignore[attr-defined]
            staging = reservation / ".staging-test"
            staging.mkdir()
            staging_inode = writer._inode(staging)  # type: ignore[attr-defined]
            staged_pack = staging / "9"
            staged_manifest = staging / "manifest.json"
            staged_pack.write_bytes(b"ours-pack")
            staged_manifest.write_bytes(b"ours-manifest")
            known = {
                "9": writer._inode(staged_pack),  # type: ignore[attr-defined]
                "manifest.json": writer._inode(staged_manifest),  # type: ignore[attr-defined]
            }
            real_check = writer._is_regular_inode  # type: ignore[attr-defined]
            pack_checks = 0

            def replace_on_cleanup(path: Path, expected: tuple[int, int]) -> bool:
                nonlocal pack_checks
                if path == staged_pack:
                    pack_checks += 1
                    # First call is the prepublication gate; the second is the
                    # immediate owned-cleanup gate after both links.
                    if pack_checks == 2:
                        staged_pack.unlink()
                        staged_pack.write_bytes(b"attacker")
                return real_check(path, expected)

            with mock.patch.object(
                writer, "_is_regular_inode", side_effect=replace_on_cleanup
            ):
                with self.assertRaisesRegex(
                    writer.PositionPatchError, "staged volume inode changed"
                ):
                    writer._publish_staged_no_replace(  # type: ignore[attr-defined]
                        reservation, reservation_inode, staging, staging_inode, known
                    )
            writer._safe_cleanup_owned_reservation(  # type: ignore[attr-defined]
                reservation, reservation_inode, staging, staging_inode, known
            )
            self.assertEqual(staged_pack.read_bytes(), b"attacker")
            self.assertFalse((reservation / "9").exists())
            self.assertFalse(staged_manifest.exists())
            self.assertTrue(staging.exists())


if __name__ == "__main__":
    unittest.main()
