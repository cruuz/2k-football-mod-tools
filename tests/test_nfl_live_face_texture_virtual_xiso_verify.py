from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_live_face_texture_xiso_verify as verify  # noqa: E402
import nfl_live_face_texture_compatibility as compatibility  # noqa: E402
import nfl_uniform_color_xiso_direct_patch as xdvdfs  # noqa: E402


class LiveFaceVirtualXisoTests(unittest.TestCase):
    def test_compatibility_pin_uses_release_safe_logical_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfl-face-pin-") as temp:
            private = Path(temp) / "private-source.bin"
            private.write_bytes(b"pinned")
            record = compatibility.pin(private, "user-source/source.bin")
        self.assertEqual(record, {
            "path": "user-source/source.bin",
            "size": 6,
            "sha256": hashlib.sha256(b"pinned").hexdigest(),
        })

    def test_virtual_scan_hashes_multiple_spans_without_output(self) -> None:
        source = bytes(range(96))
        first_source = source[7:15]
        second_source = source[61:70]
        first = bytes(value ^ 0xFF for value in first_source)
        second = b"ninebytes"
        overlays = [(7, first_source, first), (61, second_source, second)]
        expected = bytearray(source)
        expected[7:15] = first
        expected[61:70] = second
        allowed = {
            index for index, (before, after) in enumerate(zip(source, expected))
            if before != after
        }
        with tempfile.TemporaryDirectory(prefix="nfl-face-virtual-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(source)
            descriptor = os.open(path, os.O_RDONLY)
            try:
                source_sha, output_sha, differences = verify.scan_virtual_output(
                    descriptor, len(source), overlays, allowed, chunk_size=13
                )
                self.assertEqual(
                    verify.virtual_read(descriptor, 4, 70, overlays),
                    bytes(expected[4:74]),
                )
            finally:
                os.close(descriptor)
            self.assertFalse((Path(temp) / "output.bin").exists())
        self.assertEqual(source_sha, hashlib.sha256(source).hexdigest())
        self.assertEqual(output_sha, hashlib.sha256(expected).hexdigest())
        self.assertEqual(differences, sorted(allowed))

    def test_virtual_scan_refuses_wrong_source_noop_and_difference_ledger(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfl-face-hostile-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(b"abcdefgh")
            descriptor = os.open(path, os.O_RDONLY)
            try:
                with self.assertRaisesRegex(verify.VerificationError, "retail bytes"):
                    verify.scan_virtual_output(
                        descriptor, 8, [(2, b"XX", b"YZ")], {2, 3}, chunk_size=3
                    )
                with self.assertRaisesRegex(verify.VerificationError, "ledger"):
                    verify.scan_virtual_output(
                        descriptor, 8, [(2, b"cd", b"XY")], {2}, chunk_size=3
                    )
                with self.assertRaisesRegex(verify.VerificationError, "does not change"):
                    verify.scan_virtual_output(
                        descriptor, 8, [(2, b"cd", b"cd")], set(), chunk_size=3
                    )
            finally:
                os.close(descriptor)

    def test_virtual_output_must_remain_absent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="nfl-face-absent-") as temp:
            root = Path(temp)
            absent = root / "historical.xiso.iso"
            self.assertEqual(verify.absent_output_path(absent), absent.resolve())
            present = root / "present.xiso.iso"
            present.write_bytes(b"x")
            with self.assertRaisesRegex(verify.VerificationError, "must be absent"):
                verify.absent_output_path(present)
            dangling = root / "dangling.xiso.iso"
            dangling.symlink_to(root / "missing-target")
            with self.assertRaisesRegex(verify.VerificationError, "must be absent"):
                verify.absent_output_path(dangling)
            directory = root / "directory.xiso.iso"
            directory.mkdir()
            with self.assertRaisesRegex(verify.VerificationError, "must be absent"):
                verify.absent_output_path(directory)

    def test_virtual_xdvdfs_proof_rejects_metadata_overlays(self) -> None:
        image = bytes(0x12000)
        directory = {
            "root_sector": 2,
            "root_size": 64,
            "directory_extents": 2,
            "directory_nodes": 1,
        }
        entries = {
            "folder": xdvdfs.XdvdfsEntry("folder", 3, 32, 0x10),
            "file": xdvdfs.XdvdfsEntry("file", 4, 16, 0x20),
        }
        with tempfile.TemporaryDirectory(prefix="nfl-face-xdvdfs-") as temp:
            path = Path(temp) / "source.bin"
            path.write_bytes(image)
            descriptor = os.open(path, os.O_RDONLY)
            try:
                verify.verify_virtual_xdvdfs_metadata(
                    descriptor, entries, directory, [(100, b"\0", b"x")]
                )
                for offset in (
                    xdvdfs.XDVDFS_HEADER_OFFSET,
                    2 * xdvdfs.SECTOR_SIZE,
                    3 * xdvdfs.SECTOR_SIZE,
                ):
                    with self.subTest(offset=offset):
                        with self.assertRaisesRegex(
                            verify.VerificationError, "changes XDVDFS"
                        ):
                            verify.verify_virtual_xdvdfs_metadata(
                                descriptor, entries, directory,
                                [(offset, b"\0", b"x")],
                            )
            finally:
                os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
