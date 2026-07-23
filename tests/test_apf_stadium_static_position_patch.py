#!/usr/bin/env python3
"""Synthetic and refusal tests for APF same-count POSITION0 write-back."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import apf_stadium_static_position_patch as writer  # noqa: E402
import apf_stadium_static_position_verify as verifier  # noqa: E402


SAMPLE_RECIPE = ROOT / "reports/asset_samples/apf_scene/stadium_polySurface19930_nonretail_zero_recipe.json"
GAME_DIR = ROOT / "extracted/All-Pro Football 2K8 (USA)"


class ApfStadiumStaticPositionPatchTest(unittest.TestCase):
    def _recipe(self) -> dict[str, object]:
        return json.loads(SAMPLE_RECIPE.read_bytes())

    def _write_recipe(self, directory: Path, value: dict[str, object], name: str = "recipe.json") -> Path:
        path = directory / name
        path.write_bytes(writer.canonical_json_bytes(value))
        return path

    def test_canonical_const_pinned_nonretail_sample_encodes_exact_float32(self) -> None:
        sample, sample_raw, sample_positions = writer.load_recipe(SAMPLE_RECIPE)
        self.assertEqual(len(sample_positions), 48)
        self.assertEqual(sample_positions, bytes(48))
        self.assertEqual(sample_raw, writer.canonical_json_bytes(sample))
        self.assertEqual(verifier._load_recipe(SAMPLE_RECIPE)[2], sample_positions)

    def test_recipe_refuses_extra_key_wrong_count_rounding_bool_and_noncanonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            cases: list[tuple[str, dict[str, object]]] = []
            extra = self._recipe()
            extra["unexpected"] = 1
            cases.append(("extra", extra))
            wrong_count = self._recipe()
            wrong_count["positions"] = wrong_count["positions"][:3]  # type: ignore[index]
            cases.append(("count", wrong_count))
            rounded = self._recipe()
            rounded["positions"][0][0] = 0.1  # type: ignore[index]
            cases.append(("round", rounded))
            boolean = self._recipe()
            boolean["positions"][0][0] = True  # type: ignore[index]
            cases.append(("bool", boolean))
            for name, value in cases:
                path = self._write_recipe(directory, value, f"{name}.json")
                with self.assertRaises((writer.PatchError, verifier.VerifyError), msg=name):
                    writer.load_recipe(path)
                with self.assertRaises((writer.PatchError, verifier.VerifyError), msg=name):
                    verifier._load_recipe(path)
            noncanonical = directory / "noncanonical.json"
            noncanonical.write_text(json.dumps(self._recipe()), encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "canonical"):
                writer.load_recipe(noncanonical)

    def test_recipe_refuses_duplicate_keys_and_nan(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            duplicate = directory / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}\n', encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "duplicate"):
                writer.load_recipe(duplicate)
            with self.assertRaisesRegex(verifier.VerifyError, "duplicate"):
                verifier._load_recipe(duplicate)
            nan = directory / "nan.json"
            nan.write_text('{"positions":[[NaN,0,0],[0,0,0],[0,0,0],[0,0,0]]}\n', encoding="utf-8")
            with self.assertRaisesRegex(writer.PatchError, "non-JSON"):
                writer.load_recipe(nan)
            with self.assertRaisesRegex(verifier.VerifyError, "non-JSON"):
                verifier._load_recipe(nan)

    def test_interleaved_patch_changes_only_four_position_lanes(self) -> None:
        source = bytes(range(96))
        positions = b"".join(struct.pack(">3f", float(i), float(i + 1), float(i + 2)) for i in range(4))
        output = writer.patch_interleaved_stream(source, positions)
        self.assertEqual(writer._position_payload(output), positions)
        changed = {index for index, pair in enumerate(zip(source, output)) if pair[0] != pair[1]}
        allowed = {vertex * 24 + byte for vertex in range(4) for byte in range(12)}
        self.assertTrue(changed <= allowed)
        for vertex in range(4):
            self.assertEqual(output[vertex * 24 + 12 : vertex * 24 + 24], source[vertex * 24 + 12 : vertex * 24 + 24])

    def test_independent_h7a_literal_decode_and_refusal(self) -> None:
        data = b"ABCDEFGH"
        payload = b"\x00" + data
        stored = struct.pack(">5I", 0x0E4837C3, len(data), 20 + len(payload), 7, 12) + payload
        self.assertEqual(verifier._decompress_h7a(stored, len(data), 12), data)
        bad_payload = b"\x01\x00\x01"
        bad = struct.pack(">5I", 0x0E4837C3, 3, 20 + len(bad_payload), 7, 12) + bad_payload
        with self.assertRaisesRegex(verifier.VerifyError, "match"):
            verifier._decompress_h7a(bad, 3, 12)

    def test_independent_header_complement_allows_only_three_fields(self) -> None:
        source = bytes(292)
        allowed = bytearray(source)
        allowed[0x08] = 1
        allowed[0x38] = 2
        allowed[0x54] = 3
        verifier.validate_iff_header_preservation(source, bytes(allowed))
        forbidden = bytearray(source)
        forbidden[0x34] = 1  # block0 codec/opaque metadata, not a mechanical field
        with self.assertRaisesRegex(verifier.VerifyError, "header"):
            verifier.validate_iff_header_preservation(source, bytes(forbidden))
        descriptor = bytearray(source)
        descriptor[0x88] = 1  # packed file descriptor region
        with self.assertRaisesRegex(verifier.VerifyError, "header"):
            verifier.validate_iff_header_preservation(source, bytes(descriptor))

    def test_writer_refuses_symlink_game_recipe_parent_and_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory_name:
            directory = Path(directory_name)
            game_link = directory / "game_link"
            game_link.symlink_to(GAME_DIR, target_is_directory=True)
            with self.assertRaisesRegex(writer.PatchError, "game directory"):
                writer.write_output(game_link, SAMPLE_RECIPE, directory / "out1")
            ancestor_link = directory / "ancestor_link"
            ancestor_link.symlink_to(GAME_DIR.parent, target_is_directory=True)
            with self.assertRaisesRegex(writer.PatchError, "contains a symlink"):
                writer.write_output(ancestor_link / GAME_DIR.name, SAMPLE_RECIPE, directory / "out_ancestor")
            recipe_link = directory / "recipe_link.json"
            recipe_link.symlink_to(SAMPLE_RECIPE)
            with self.assertRaisesRegex(writer.PatchError, "recipe"):
                writer.write_output(GAME_DIR, recipe_link, directory / "out2")
            parent_link = directory / "parent_link"
            real_parent = directory / "real_parent"
            real_parent.mkdir()
            parent_link.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(writer.PatchError, "parent"):
                writer.write_output(GAME_DIR, SAMPLE_RECIPE, parent_link / "out3")
            existing = directory / "existing"
            existing.mkdir()
            with self.assertRaisesRegex(writer.PatchError, "existing"):
                writer.write_output(GAME_DIR, SAMPLE_RECIPE, existing)

    @unittest.skipUnless((GAME_DIR / "1A").is_file(), "retail APF fixture unavailable")
    def test_independent_verifier_rejects_output_source_hardlink_alias_before_hashing(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory_name:
            output = Path(directory_name) / "output"
            output.mkdir()
            os.link(GAME_DIR / "1A", output / "1A")
            (output / writer.MANIFEST_NAME).write_bytes(writer.canonical_json_bytes({"schema": "dummy"}))
            with self.assertRaisesRegex(verifier.VerifyError, "hardlink"):
                verifier.verify(GAME_DIR, SAMPLE_RECIPE, output)

    def test_verification_artifact_refuses_output_directory_and_existing_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            directory = Path(directory_name)
            output = directory / "output"
            output.mkdir()
            inside = output / "verify.json"
            with self.assertRaisesRegex(verifier.VerifyError, "outside"):
                verifier._write_artifact(inside, {"schema": "test"}, output)
            existing = directory / "existing.json"
            existing.write_text("owned", encoding="utf-8")
            with self.assertRaisesRegex(verifier.VerifyError, "existing"):
                verifier._write_artifact(existing, {"schema": "test"}, output)

    def test_directory_ownership_helper_detects_rename_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as directory_name:
            root = Path(directory_name)
            target = root / "target"
            target.mkdir()
            metadata = os.lstat(target)
            identity = (metadata.st_dev, metadata.st_ino)
            self.assertTrue(writer._directory_path_matches(target, identity))
            target.rename(root / "moved")
            target.mkdir()
            self.assertFalse(writer._directory_path_matches(target, identity))


if __name__ == "__main__":
    unittest.main()
