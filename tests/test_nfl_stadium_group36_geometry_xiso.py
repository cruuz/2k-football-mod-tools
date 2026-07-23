from __future__ import annotations

import hashlib
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

import nfl_stadium_group36_geometry_xiso_patch as writer  # noqa: E402
import nfl_stadium_group36_geometry_xiso_verify as verifier  # noqa: E402


MANIFEST = (
    ROOT
    / "build/nfl2k5-stadium-group36-geometry-xiso-20260713/workflow-v2.json"
)


def expected_ledger(before: bytes, after: bytes) -> dict[str, object]:
    offsets = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        if not runs or offset != runs[-1][1]:
            runs.append((offset, offset + 1))
        else:
            runs[-1] = (runs[-1][0], offset + 1)
    return {
        "changed_byte_count": len(offsets),
        "changed_offset_u32le_sha256": hashlib.sha256(
            b"".join(struct.pack("<I", offset) for offset in offsets)
        ).hexdigest(),
        "changed_before_bytes_sha256": hashlib.sha256(
            bytes(before[offset] for offset in offsets)
        ).hexdigest(),
        "changed_after_bytes_sha256": hashlib.sha256(
            bytes(after[offset] for offset in offsets)
        ).hexdigest(),
        "changed_run_count": len(runs),
        "changed_run_pairs_u32le_sha256": hashlib.sha256(
            b"".join(struct.pack("<II", start, end) for start, end in runs)
        ).hexdigest(),
    }


class GeometryXisoTransportTests(unittest.TestCase):
    def test_independent_ledgers_match_a_third_derivation(self) -> None:
        before = bytes(range(32))
        changed = bytearray(before)
        for offset, value in ((0, 90), (1, 91), (4, 92), (15, 93), (31, 94)):
            changed[offset] = value
        after = bytes(changed)
        expected = expected_ledger(before, after)
        with (
            mock.patch.object(writer, "SPAN_SIZE", len(before)),
            mock.patch.object(verifier, "SPAN_SIZE", len(before)),
        ):
            self.assertEqual(writer._ledger(before, after), expected)
            self.assertEqual(verifier.ledger(before, after), expected)
        self.assertEqual(expected["changed_byte_count"], 5)
        self.assertEqual(expected["changed_run_count"], 4)

    def test_both_ledgers_refuse_wrong_span_lengths(self) -> None:
        with (
            mock.patch.object(writer, "SPAN_SIZE", 8),
            mock.patch.object(verifier, "SPAN_SIZE", 8),
        ):
            with self.assertRaisesRegex(writer.GeometryXisoError, "span ledger size"):
                writer._ledger(b"1234567", b"1234567")
            with self.assertRaisesRegex(verifier.GeometryXisoVerifyError, "ledger span size"):
                verifier.ledger(b"12345678", b"1234567X9")

    def test_writer_full_compare_accepts_only_the_authorized_span(self) -> None:
        source = bytes(range(64))
        output = bytearray(source)
        output[16] ^= 0xFF
        output[18] ^= 0xFF
        output[23] ^= 0xFF
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left_path = root / "source"
            right_path = root / "output"
            left_path.write_bytes(source)
            right_path.write_bytes(output)
            left = os.open(left_path, os.O_RDONLY)
            right = os.open(right_path, os.O_RDONLY)
            try:
                with (
                    mock.patch.object(writer, "SPAN_SIZE", 8),
                    mock.patch.object(writer, "LEDGER_CHUNK", 7),
                ):
                    ledger = writer._ledger(source[16:24], bytes(output[16:24]))
                    hashes = writer._compare_complete_xisos(left, right, 64, 16, ledger)
            finally:
                os.close(left)
                os.close(right)
        self.assertEqual(hashes, (hashlib.sha256(source).hexdigest(), hashlib.sha256(output).hexdigest()))

    def test_writer_full_compare_refuses_outside_changes_and_bad_count(self) -> None:
        source = bytes(range(64))
        output = bytearray(source)
        output[16] ^= 0xFF
        expected = expected_ledger(source[16:24], bytes(output[16:24]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left_path = root / "source"
            right_path = root / "output"
            left_path.write_bytes(source)
            output[4] ^= 0xFF
            right_path.write_bytes(output)
            left = os.open(left_path, os.O_RDONLY)
            right = os.open(right_path, os.O_RDONLY)
            try:
                with mock.patch.object(writer, "SPAN_SIZE", 8):
                    with self.assertRaisesRegex(writer.GeometryXisoError, "outside the authorized"):
                        writer._compare_complete_xisos(left, right, 64, 16, expected)
            finally:
                os.close(left)
                os.close(right)

            output[4] ^= 0xFF
            right_path.write_bytes(output)
            expected["changed_byte_count"] = 2
            left = os.open(left_path, os.O_RDONLY)
            right = os.open(right_path, os.O_RDONLY)
            try:
                with mock.patch.object(writer, "SPAN_SIZE", 8):
                    with self.assertRaisesRegex(writer.GeometryXisoError, "changed-byte count"):
                        writer._compare_complete_xisos(left, right, 64, 16, expected)
            finally:
                os.close(left)
                os.close(right)

    def test_independent_full_compare_refuses_outside_and_short_reads(self) -> None:
        source = bytes(range(64))
        output = bytearray(source)
        output[16] ^= 0xFF
        output[23] ^= 0xFF
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left_path = root / "source"
            right_path = root / "output"
            left_path.write_bytes(source)
            right_path.write_bytes(output)

            def compare(size: int = 64) -> int:
                left = os.open(left_path, os.O_RDONLY)
                right = os.open(right_path, os.O_RDONLY)
                try:
                    with (
                        mock.patch.object(verifier, "ABSOLUTE_SPAN", 16),
                        mock.patch.object(verifier, "SPAN_SIZE", 8),
                        mock.patch.object(verifier, "BLOCK", 7),
                    ):
                        return verifier.compare_full(left, right, size)
                finally:
                    os.close(left)
                    os.close(right)

            self.assertEqual(compare(), 2)
            output[24] ^= 0xFF
            right_path.write_bytes(output)
            with self.assertRaisesRegex(verifier.GeometryXisoVerifyError, "unauthorized"):
                compare()
            output[24] ^= 0xFF
            right_path.write_bytes(output[:63])
            with self.assertRaisesRegex(verifier.GeometryXisoVerifyError, "short full-disc"):
                compare()

    def test_both_paths_refuse_symlink_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_bytes(b"x")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(writer.GeometryXisoError, "non-symlink regular"):
                writer.regular(link, "test")
            with self.assertRaisesRegex(verifier.GeometryXisoVerifyError, "non-symlink regular"):
                verifier.regular(link, "test")

    def test_manifest_key_gate_rejects_canonical_extra_field_early(self) -> None:
        checked = json.loads(MANIFEST.read_bytes())
        checked["unexpected"] = True
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "output"
            geometry = root / "geometry"
            geometry.mkdir()
            changed = geometry / "9"
            manifest = root / "manifest.json"
            for path in (source, output, changed):
                path.write_bytes(b"x")
            manifest.write_bytes(verifier.canonical_json(checked))
            with (
                mock.patch.object(verifier.geometry_verify, "verify", return_value={"mode": "patched"}),
                self.assertRaisesRegex(verifier.GeometryXisoVerifyError, "root differs from v1"),
            ):
                verifier.verify(source, root / "unused-index", root / "unused-recipe", geometry, output, manifest)

    def test_checked_manifest_is_canonical_and_keeps_runtime_claims_false(self) -> None:
        raw = MANIFEST.read_bytes()
        value = json.loads(raw)
        self.assertEqual(raw, verifier.canonical_json(value))
        self.assertEqual(value["schema"], verifier.MANIFEST_SCHEMA)
        self.assertEqual(value["claims"], {
            "layout_identical_copy_only_xiso": True,
            "offline_native_geometry_transport_proved": True,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
            "xemu_boot_proved": False,
            "xemu_geometry_visibility_proved": False,
        })

    def test_independent_verifier_does_not_import_transport_writer(self) -> None:
        source = (ROOT / "tools/nfl_stadium_group36_geometry_xiso_verify.py").read_text()
        self.assertNotIn("import nfl_stadium_group36_geometry_xiso_patch", source)
        self.assertNotIn("from nfl_stadium_group36_geometry_xiso_patch", source)


if __name__ == "__main__":
    unittest.main()
