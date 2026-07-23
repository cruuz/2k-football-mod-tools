#!/usr/bin/env python3
"""Small-fixture tests for the independent APF typed-provider verifier."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_jersey_family_patch as family_patch  # noqa: E402
import apf_jersey_family_verify as verifier  # noqa: E402
import apf_texture_patch  # noqa: E402
import apf_xenos_mip_layout as xenos_mips  # noqa: E402


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def recipe(path: Path, png: Path, asset_index: int = 6) -> Path:
    path.write_bytes(canonical({
        "schema": verifier.RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": str(png),
    }))
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class IndependentVerifierTests(unittest.TestCase):
    def test_recipe_and_png_gates_are_canonical_bounded_and_non_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            png = root / "jersey.png"
            Image.new("RGBA", (1024, 1024), (1, 2, 3, 255)).save(png)
            path = recipe(root / "recipe.json", png, 23)
            loaded = verifier.load_recipe(path)
            self.assertEqual(loaded["asset_index"], 23)
            self.assertEqual(loaded["png_report"]["width"], 1024)
            self.assertEqual(loaded["png_report"]["mode"], "RGBA")

            value = json.loads(path.read_text(encoding="utf-8"))
            value["raw_offset"] = "0x1234"
            path.write_bytes(canonical(value))
            with self.assertRaises(verifier.VerifyError):
                verifier.load_recipe(path)

            value.pop("raw_offset")
            value["asset_index"] = 24
            path.write_bytes(canonical(value))
            with self.assertRaises(verifier.VerifyError):
                verifier.load_recipe(path)

            value["asset_index"] = 6
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(verifier.VerifyError):
                verifier.load_recipe(path)

            link = root / "linked.png"
            link.symlink_to(png)
            recipe(path, link)
            with self.assertRaisesRegex(verifier.VerifyError, "non-symlink"):
                verifier.load_recipe(path)

            wrong = root / "wrong.png"
            Image.new("RGBA", (256, 256), (1, 2, 3, 255)).save(wrong)
            recipe(path, wrong)
            with self.assertRaisesRegex(verifier.VerifyError, "1024x1024"):
                verifier.load_recipe(path)

    def test_small_copy_fixture_proves_only_selected_span_changed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            output = root / "output.bin"
            original = bytes(range(256)) * 8
            offset = 311
            size = 173
            changed = bytearray(original)
            changed[offset:offset + size] = b"X" * size
            source.write_bytes(original)
            output.write_bytes(changed)
            result = verifier.compare_copy_outside_span(
                source,
                output,
                offset,
                size,
                hashlib.sha256(original).hexdigest(),
            )
            self.assertTrue(result["outside_span_identical"])
            self.assertEqual(result["source_span_sha256"], hashlib.sha256(original[offset:offset + size]).hexdigest())
            self.assertEqual(result["output_span_sha256"], hashlib.sha256(b"X" * size).hexdigest())

            broken = bytearray(changed)
            broken[10] ^= 0xFF
            output.write_bytes(broken)
            with self.assertRaisesRegex(verifier.VerifyError, "outside"):
                verifier.compare_copy_outside_span(
                    source,
                    output,
                    offset,
                    size,
                    hashlib.sha256(original).hexdigest(),
                )

    def test_nine_level_png_decode_back_recomputes_manifest_without_volume_copy(self) -> None:
        catalog = verifier.load_catalog()
        metadata = catalog["jerseys"][6]["txtr_descriptor"]
        locations = xenos_mips.derive_layout(metadata)
        base = Image.new("RGBA", (1024, 1024), (40, 90, 160, 255)).tobytes()
        wanted = verifier.wanted_levels(base, locations)
        texture = bytes(
            int(metadata["vc_base_data_length"]) + int(metadata["vc_mip_data_length"])
        )
        rows = []
        for location, desired in zip(locations, wanted):
            pixels = [tuple(desired[:4])] * 16
            block = apf_texture_patch.encode_bc3_block(pixels)
            linear = block * location.logical_block_count
            texture = xenos_mips.insert_linear_bc3(texture, location, linear)
            decoded = verifier.decode_linear_bc3(linear, location)
            rows.append({
                "level": location.level,
                "linear_bc3_sha256_after": hashlib.sha256(linear).hexdigest(),
                "decoded_rgba_sha256_after": hashlib.sha256(decoded).hexdigest(),
                "wanted_rgba_sha256": hashlib.sha256(desired).hexdigest(),
                "decode_back_metrics": verifier.rgba_metrics(desired, decoded),
            })
        manifest = {"mode": "patched", "levels": rows}
        result = verifier.verify_decoded_levels(base, texture, locations, manifest)
        self.assertEqual(len(result), 9)
        self.assertEqual([row["level"] for row in result], list(range(9)))
        manifest["levels"][4]["decoded_rgba_sha256_after"] = "0" * 64
        with self.assertRaisesRegex(verifier.VerifyError, "mip 4"):
            verifier.verify_decoded_levels(base, texture, locations, manifest)

    def test_retail_entry_decodes_in_memory_without_copying_0a(self) -> None:
        source = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
        png = WORKSPACE / "reports/assets/apf_uniform_samples/team00_bank0_jersey_06_jersey_color.png"
        before = sha256_file(source)
        self.assertEqual(before, verifier.EXPECTED_VOLUME_SHA256)
        result = family_patch.build_patch(source, png, 6)
        row = verifier.load_catalog()["jerseys"][6]
        decoded = verifier.decode_entry_bytes(result.entry_bytes, row)
        self.assertEqual(hashlib.sha256(decoded["texture"]).hexdigest(), row["inner_file"]["texture_sha256"])
        levels = verifier.verify_decoded_levels(
            Image.open(png).convert("RGBA").tobytes(),
            decoded["texture"],
            decoded["locations"],
            result.manifest,
        )
        self.assertEqual(len(levels), 9)
        self.assertEqual(sha256_file(source), before)


if __name__ == "__main__":
    unittest.main()
