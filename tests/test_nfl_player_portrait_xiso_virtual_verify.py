#!/usr/bin/env python3
"""Hostile boundary tests for portrait absent-output verification."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "tools"))
import nfl_player_portrait_xiso_virtual_verify as virtual  # noqa: E402


class PortraitVirtualVerifyTests(unittest.TestCase):
    def record(self, path: Path) -> dict[str, object]:
        return {
            "copy_method": "copy_file_range",
            "device": 1,
            "exclusively_created": True,
            "inode": 2,
            "manifest_path": str(path.parent / "workflow.json"),
            "preview_directory": str(path.parent / "previews"),
            "preview_sha256": {"0000_portrait_0124.png": "0" * 64},
            "xiso_path": str(path),
            "xiso_sha256": virtual.OUTPUT_SHA256,
            "xiso_size": 6_300_499_968,
        }

    def test_exact_missing_path_is_the_only_accepted_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            expected = root / "proof.xiso.iso"
            self.assertEqual(
                virtual.validate_absent_output(self.record(expected), expected), expected,
            )
            with self.assertRaisesRegex(virtual.VirtualVerificationError, "exactly match"):
                virtual.validate_absent_output(self.record(expected), root / "other.xiso.iso")

    def test_existing_file_and_symlink_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            expected = root / "proof.xiso.iso"
            expected.write_bytes(b"not a proof")
            with self.assertRaisesRegex(virtual.VirtualVerificationError, "existing"):
                virtual.validate_absent_output(self.record(expected), expected)
            expected.unlink()
            expected.symlink_to(root / "missing-target")
            with self.assertRaisesRegex(virtual.VirtualVerificationError, "symlink"):
                virtual.validate_absent_output(self.record(expected), expected)

    def test_forged_hash_size_and_copy_boundary_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            expected = Path(temporary).resolve() / "proof.xiso.iso"
            for key, value in (
                ("xiso_sha256", "0" * 64),
                ("xiso_size", 1),
                ("copy_method", "virtual"),
                ("exclusively_created", False),
            ):
                record = self.record(expected)
                record[key] = value
                with self.assertRaisesRegex(
                    virtual.VirtualVerificationError, "receipt boundary",
                ):
                    virtual.validate_absent_output(record, expected)

    def test_virtual_verifier_has_no_output_or_emulator_path(self) -> None:
        source = (ROOT / "tools/nfl_player_portrait_xiso_virtual_verify.py").read_text()
        self.assertNotIn("O_WRONLY", source)
        self.assertNotIn("O_CREAT", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("flatpak run", source)

    def test_historical_provenance_receipt_reconstructs_exactly(self) -> None:
        payload = (
            ROOT / "reports/assets/nfl2k5_player_portrait_compatibility.json"
        ).read_bytes()
        self.assertEqual(
            virtual.reconstruct_historical_compatibility(
                payload,
                (ROOT / "ESPN NFL 2K5 (USA).xiso.iso").resolve(strict=True),
                (
                    ROOT
                    / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
                ).resolve(strict=True),
            ),
            virtual.HISTORICAL_COMPATIBILITY_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
