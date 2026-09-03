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

import nfl_stadium_upper_deck_subset_xiso_patch as writer  # noqa: E402
import nfl_stadium_upper_deck_subset_xiso_verify as verifier  # noqa: E402


MANIFEST = (
    ROOT / "build/nfl2k5-stadium-upper-deck-subset-xiso-20260716/xiso-workflow.json"
)


def independent_ledger(before: bytes, after: bytes) -> dict[str, object]:
    offsets = [index for index, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
    runs: list[tuple[int, int]] = []
    for offset in offsets:
        if not runs or runs[-1][1] != offset:
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


class UpperDeckSubsetXisoTests(unittest.TestCase):
    def test_writer_and_verifier_ledgers_match_third_derivation(self) -> None:
        before = bytes(range(48))
        after = bytearray(before)
        for offset, value in ((0, 90), (1, 91), (7, 92), (19, 93), (47, 94)):
            after[offset] = value
        expected = independent_ledger(before, bytes(after))
        with (
            mock.patch.object(writer, "SPAN_SIZE", len(before)),
            mock.patch.object(verifier, "SPAN_SIZE", len(before)),
        ):
            self.assertEqual(writer._ledger(before, bytes(after)), expected)
            self.assertEqual(verifier.ledger(before, bytes(after)), expected)
        self.assertEqual(expected["changed_byte_count"], 5)
        self.assertEqual(expected["changed_run_count"], 4)

    def test_both_ledgers_reject_wrong_spans(self) -> None:
        with (
            mock.patch.object(writer, "SPAN_SIZE", 8),
            mock.patch.object(verifier, "SPAN_SIZE", 8),
        ):
            with self.assertRaisesRegex(writer.UpperDeckSubsetXisoError, "span ledger size"):
                writer._ledger(b"1234567", b"1234567")
            with self.assertRaisesRegex(verifier.UpperDeckSubsetXisoVerifyError, "ledger span size"):
                verifier.ledger(b"12345678", b"1234567X9")

    def test_writer_full_compare_is_confined_to_authorized_span(self) -> None:
        source = bytes(range(64))
        output = bytearray(source)
        for offset in (16, 18, 23):
            output[offset] ^= 0xFF
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
                    expected = writer._ledger(source[16:24], bytes(output[16:24]))
                    hashes = writer._compare_complete_xisos(left, right, 64, 16, expected)
            finally:
                os.close(left)
                os.close(right)
        self.assertEqual(hashes, (
            hashlib.sha256(source).hexdigest(), hashlib.sha256(output).hexdigest()
        ))

    def test_writer_and_verifier_reject_outside_differences(self) -> None:
        source = bytes(range(64))
        output = bytearray(source)
        output[16] ^= 0xFF
        output[4] ^= 0xFF
        expected = independent_ledger(source[16:24], bytes(output[16:24]))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left_path = root / "source"
            right_path = root / "output"
            left_path.write_bytes(source)
            right_path.write_bytes(output)
            left = os.open(left_path, os.O_RDONLY)
            right = os.open(right_path, os.O_RDONLY)
            try:
                with mock.patch.object(writer, "SPAN_SIZE", 8):
                    with self.assertRaisesRegex(writer.UpperDeckSubsetXisoError, "outside"):
                        writer._compare_complete_xisos(left, right, 64, 16, expected)
                with (
                    mock.patch.object(verifier, "SPAN_SIZE", 8),
                    mock.patch.object(verifier, "BLOCK", 7),
                ):
                    with self.assertRaisesRegex(verifier.UpperDeckSubsetXisoVerifyError,
                                                "unauthorized"):
                        verifier.compare_full(left, right, 64, 16)
            finally:
                os.close(left)
                os.close(right)

    def test_both_paths_reject_symlink_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_bytes(b"x")
            link = root / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(writer.UpperDeckSubsetXisoError, "non-symlink regular"):
                writer.regular(link, "test")
            with self.assertRaisesRegex(verifier.UpperDeckSubsetXisoVerifyError,
                                        "non-symlink regular"):
                verifier.regular(link, "test")

    def test_checked_manifest_is_canonical_and_keeps_runtime_claims_false(self) -> None:
        raw = MANIFEST.read_bytes()
        value = json.loads(raw)
        self.assertEqual(raw, verifier.canonical_json(value))
        self.assertEqual(value["schema"], verifier.MANIFEST_SCHEMA)
        self.assertEqual(value["native_subset_proof"]["source_vertex_count"], 12)
        self.assertEqual(value["native_subset_proof"]["output_vertex_count"], 4)
        self.assertEqual(value["claims"], {
            "changed_vertex_count_transport_proved": True,
            "layout_identical_copy_only_xiso": True,
            "offline_native_subset_transport_proved": True,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
            "xemu_boot_proved": False,
            "xemu_changed_count_visibility_proved": False,
        })

    def test_independent_verifier_does_not_import_transport_writer(self) -> None:
        source = (ROOT / "tools/nfl_stadium_upper_deck_subset_xiso_verify.py").read_text()
        self.assertNotIn("import nfl_stadium_upper_deck_subset_xiso_patch", source)
        self.assertNotIn("from nfl_stadium_upper_deck_subset_xiso_patch", source)


if __name__ == "__main__":
    unittest.main()
