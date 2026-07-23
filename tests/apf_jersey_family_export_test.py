#!/usr/bin/env python3
"""Focused synthetic/in-memory tests for the APF jersey exporter."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_jersey_family_export as exporter  # noqa: E402
import apf_jersey_family_verify as verifier  # noqa: E402
import apf_xenos_mip_layout as xenos_mips  # noqa: E402


def synthetic_previews() -> tuple[exporter.PreviewLevel, ...]:
    row = deepcopy(verifier.load_catalog()["jerseys"][6])
    metadata = row["txtr_descriptor"]
    locations = xenos_mips.derive_layout(metadata)
    texture = bytes(
        int(metadata["vc_base_data_length"]) + int(metadata["vc_mip_data_length"])
    )
    row["inner_file"]["texture_sha256"] = hashlib.sha256(texture).hexdigest()
    for location, expected in zip(locations, row["nine_level_layout"]):
        linear = xenos_mips.extract_linear_bc3(texture, location)
        expected["linear_bc3_sha256"] = hashlib.sha256(linear).hexdigest()
    return exporter._preview_levels(  # type: ignore[attr-defined]
        row,
        {"metadata": metadata, "texture": texture, "locations": locations},
    )


def plan_from(previews: tuple[exporter.PreviewLevel, ...]) -> exporter.ExportPlan:
    files = (
        exporter.OutputFile("jersey_base.png", previews[0].png),
        *(exporter.OutputFile(item.png_name, item.png) for item in previews),
    )
    document = {
        "schema": exporter.SCHEMA,
        "target": {"asset_index": 6},
        "mip_previews": [item.provenance() for item in previews],
    }
    return exporter.ExportPlan(document, files)


class JerseyFamilyExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.previews = synthetic_previews()
        cls.plan = plan_from(cls.previews)

    def test_synthetic_texture_decodes_all_exact_layout_levels_in_memory(self) -> None:
        self.assertEqual([row.level for row in self.previews], list(range(9)))
        self.assertEqual(
            [(row.width, row.height) for row in self.previews],
            [
                (1024, 1024), (512, 512), (256, 256),
                (128, 128), (64, 64), (32, 32),
                (16, 16), (8, 8), (4, 4),
            ],
        )
        self.assertEqual(
            [row.level for row in self.previews if row.packed_tail], [6, 7, 8]
        )
        for row in self.previews:
            self.assertEqual(hashlib.sha256(row.png).hexdigest(), row.png_sha256)
            with Image.open(__import__("io").BytesIO(row.png)) as image:
                image.load()
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.mode, "RGBA")
                self.assertEqual(image.size, (row.width, row.height))
                self.assertEqual(
                    hashlib.sha256(image.tobytes()).hexdigest(), row.rgba_sha256
                )

    def test_exact_descriptor_and_layout_drift_are_refused(self) -> None:
        row = deepcopy(verifier.load_catalog()["jerseys"][6])
        metadata = deepcopy(row["txtr_descriptor"])
        locations = xenos_mips.derive_layout(metadata)
        texture = bytes(
            int(metadata["vc_base_data_length"]) + int(metadata["vc_mip_data_length"])
        )
        row["inner_file"]["texture_sha256"] = hashlib.sha256(texture).hexdigest()
        for location, expected in zip(locations, row["nine_level_layout"]):
            expected["linear_bc3_sha256"] = hashlib.sha256(
                xenos_mips.extract_linear_bc3(texture, location)
            ).hexdigest()
        changed = deepcopy(metadata)
        changed["width"] = 512
        with self.assertRaisesRegex(exporter.ExportError, "descriptor"):
            exporter._preview_levels(  # type: ignore[attr-defined]
                row, {"metadata": changed, "texture": texture, "locations": locations}
            )
        row["nine_level_layout"][4]["origin_block_x"] = 9
        with self.assertRaisesRegex(exporter.ExportError, "mip 4 layout"):
            exporter._preview_levels(  # type: ignore[attr-defined]
                row, {"metadata": metadata, "texture": texture, "locations": locations}
            )

    def test_pinned_team_join_uses_only_bank_zero_one_labels(self) -> None:
        catalog = verifier.load_catalog()
        asset6 = exporter._affected_team_banks(6, catalog["jerseys"][6])  # type: ignore[attr-defined]
        self.assertEqual(
            asset6,
            (
                {
                    "team_index": 0,
                    "team_name": "Americans",
                    "abbreviation": "PHI",
                    "slot_kind": "built_in_team",
                    "bank": 0,
                    "bank_label": "bank 0",
                },
                {
                    "team_index": 0,
                    "team_name": "Americans",
                    "abbreviation": "PHI",
                    "slot_kind": "built_in_team",
                    "bank": 1,
                    "bank_label": "bank 1",
                },
            ),
        )
        asset23 = exporter._affected_team_banks(23, catalog["jerseys"][23])  # type: ignore[attr-defined]
        self.assertEqual(len(asset23), 26)
        self.assertEqual({row["bank_label"] for row in asset23}, {"bank 0", "bank 1"})
        self.assertNotIn("home", json.dumps(asset23).lower())
        self.assertNotIn("away", json.dumps(asset23).lower())

    def test_synthetic_plan_commits_new_directory_and_canonical_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "export"
            result = exporter.write_export_plan(output, self.plan)
            self.assertEqual(result.asset_index, 6)
            self.assertEqual(result.file_count, 11)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {file.name for file in self.plan.files} | {exporter.PROVENANCE_NAME},
            )
            payload = result.provenance.read_bytes()
            value = json.loads(payload)
            self.assertEqual(payload, exporter.canonical_json(value))
            self.assertEqual(value, self.plan.document)
            self.assertFalse(any(path.suffix in {".iff", ".bin"} for path in output.iterdir()))

    def test_existing_and_broken_symlink_outputs_are_refused_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / "existing"
            existing.mkdir()
            sentinel = existing / "sentinel"
            sentinel.write_bytes(b"keep")
            with self.assertRaisesRegex(exporter.ExportError, "already exists"):
                exporter.write_export_plan(existing, self.plan)
            self.assertEqual(sentinel.read_bytes(), b"keep")

            broken = root / "broken"
            broken.symlink_to(root / "missing", target_is_directory=True)
            with self.assertRaisesRegex(exporter.ExportError, "already exists"):
                exporter.write_export_plan(broken, self.plan)
            self.assertTrue(broken.is_symlink())

    def test_partial_output_directory_is_cleaned_after_exclusive_write_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "partial"

            def fail_after_prefix(descriptor: int, payload: bytes) -> None:
                os.write(descriptor, payload[:13])
                raise OSError("synthetic failure")

            with patch.object(exporter, "_write_payload", side_effect=fail_after_prefix):
                with self.assertRaisesRegex(exporter.ExportError, "synthetic failure"):
                    exporter.write_export_plan(output, self.plan)
            self.assertFalse(os.path.lexists(output))

    def test_invalid_asset_and_nonretail_or_symlink_source_fail_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = root / "missing-0A"
            for asset_index in (-1, 24, True):
                with self.subTest(asset_index=asset_index), self.assertRaisesRegex(
                    exporter.ExportError, "0..23"
                ):
                    exporter.build_export_plan(missing, asset_index)

            fake = root / "0A"
            fake.write_bytes(b"not retail")
            with self.assertRaisesRegex(exporter.ExportError, "size"):
                exporter.build_export_plan(fake, 6)
            linked = root / "linked-0A"
            linked.symlink_to(fake)
            with self.assertRaisesRegex(verifier.VerifyError, "non-symlink"):
                exporter.build_export_plan(linked, 6)


if __name__ == "__main__":
    unittest.main()
