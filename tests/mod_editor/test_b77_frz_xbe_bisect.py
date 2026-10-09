"""Scope and disc-copy regression tests for the diagnostic XBE bisector."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import frz_xbe_bisect as b


class ScopeTests(unittest.TestCase):
    def test_dependency_closure(self):
        self.assertEqual(b.expand(["f4"]), ["f4", "f4b"])
        self.assertEqual(b.expand(["a4pd", "f5b"]), ["a4", "f5"])
        self.assertEqual(b.expand(["p9"]), ["p9"])
        with self.assertRaises(ValueError):
            b.expand(["misspelled"])

    def test_reject_wrong_source_before_mutation(self):
        with self.assertRaisesRegex(ValueError, "exact shipped"):
            b.build(b"wrong", b"input", ["p9"])

    def test_outside_scope_byte_is_rejected(self):
        before = bytes(range(40))
        after = bytearray(before)
        after[7:9] = b"xx"
        spans = [dict(file_offset=7, size=2)]
        self.assertEqual(b.verify_scope(before, after, spans), b.sha(before))
        after[30] ^= 1
        with self.assertRaisesRegex(ValueError, "outside declared"):
            b.verify_scope(before, after, spans)

    def test_exact_changed_runs_include_tail(self):
        self.assertEqual(b.changed_ranges(b"abcdef", b"aXXdXY"), [[1, 2], [4, 2]])

    def test_root_reserve(self):
        with mock.patch.object(b.shutil, "disk_usage") as usage:
            usage.return_value.free = 50 * 1024**3 + 99
            with self.assertRaisesRegex(ValueError, "50 GiB"):
                b.check_room(ROOT, 100)


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.source = self.directory / "source.iso"
        self.output = self.directory / "variant.iso"
        self.raw = bytes(range(256)) * 8
        self.source.write_bytes(self.raw)

    def test_copy_across_chunk_boundary_and_complete_readback(self):
        replacement = b"Y" * 200
        with mock.patch.object(b, "CHUNK", 128):
            receipt = b.copy_with_xbe(self.source, self.output, replacement, 117, self.raw[117:317])
        expected = self.raw[:117] + replacement + self.raw[317:]
        self.assertEqual(self.output.read_bytes(), expected)
        self.assertEqual(self.source.read_bytes(), self.raw)
        self.assertEqual(receipt["sha256"], b.sha(expected))
        self.assertEqual(receipt["source_sha256"], b.sha(self.raw))
        self.assertEqual(receipt["outside_xbe_sha256"], b.sha(self.raw[:117] + self.raw[317:]))
        self.assertTrue(receipt["full_readback_verified"])

    def test_existing_output_is_never_overwritten(self):
        self.output.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "existing output"):
            b.copy_with_xbe(self.source, self.output, b"xxxx", 0, self.raw[:4])
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_wrong_original_and_size_mismatch_leave_no_copy(self):
        for replacement, original in ((b"abcd", b"nope"), (b"abc", self.raw[:4])):
            with self.assertRaises(ValueError):
                b.copy_with_xbe(self.source, self.output, replacement, 0, original)
            self.assertFalse(self.output.exists())

    def test_short_source_read_removes_only_own_partial_copy(self):
        pread = os.pread
        def short(fd, size, offset):
            raw = pread(fd, size, offset)
            return raw[:-1] if size == len(self.raw) else raw
        with mock.patch.object(b.os, "pread", side_effect=short):
            with self.assertRaisesRegex(ValueError, "short source read"):
                b.copy_with_xbe(self.source, self.output, b"yyyy", 0, self.raw[:4])
        self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(), self.raw)

    def test_readback_corruption_is_rejected(self):
        pread = os.pread
        def corrupt(fd, size, offset):
            raw = pread(fd, size, offset)
            return b"!" + raw[1:] if raw.startswith(b"yyyy") else raw
        with mock.patch.object(b.os, "pread", side_effect=corrupt):
            with self.assertRaisesRegex(ValueError, "read-back"):
                b.copy_with_xbe(self.source, self.output, b"yyyy", 0, self.raw[:4])
        self.assertFalse(self.output.exists())


@unittest.skipUnless(os.environ.get("FRZ_XBE_FIXTURES"), "set FRZ_XBE_FIXTURES to the extracted audit scratch")
class PreparedArtifactsTests(unittest.TestCase):
    def test_disc_command_with_real_xdvdfs_and_prepared_xbe(self):
        import struct
        root = Path(os.environ["FRZ_XBE_FIXTURES"])
        final = (root / "v06/default.xbe").read_bytes()
        offset = 34 * 2048
        image = bytearray(offset + len(final) + 2048)
        header = memoryview(image)[0x10000:0x10800]
        header[:20] = b.xiso.XDVDFS_MAGIC
        header[-20:] = b.xiso.XDVDFS_MAGIC
        struct.pack_into("<II", header, 20, 33, 32)
        struct.pack_into("<HHIIBB", image, 33 * 2048, 0, 0, 34, len(final), 0x20, 11)
        image[33 * 2048 + 14:33 * 2048 + 25] = b"default.xbe"
        image[offset:offset + len(final)] = final
        with tempfile.TemporaryDirectory() as temp:
            source, output = Path(temp) / "source.iso", Path(temp) / "output.iso"
            source.write_bytes(image)
            xbe = root / "variants/X0.default.xbe"
            receipt = b.disc(source, xbe, output)
            got = output.read_bytes()
            self.assertEqual(got[:offset], image[:offset])
            self.assertEqual(got[offset:offset + len(final)], xbe.read_bytes())
            self.assertEqual(got[offset + len(final):], image[offset + len(final):])
            self.assertEqual(receipt["sha256"], b.sha(got))
            self.assertTrue(output.with_suffix(".iso.receipt.json").is_file())

    def test_all_four_outputs_match_pinned_bases_and_exact_receipts(self):
        root = Path(os.environ["FRZ_XBE_FIXTURES"])
        old = (root / "v05/default.xbe").read_bytes()
        final = (root / "v06/default.xbe").read_bytes()
        self.assertEqual(b.sha(old), b.V05_HASH)
        self.assertEqual(b.sha(final), b.V06_HASH)
        for name in b.VARIANTS:
            with self.subTest(variant=name):
                path = root / "variants" / (name + ".default.xbe")
                raw = path.read_bytes()
                receipt = json.loads(path.with_suffix(".xbe.receipt.json").read_text())
                self.assertEqual(receipt["selected"], b.expand(b.VARIANTS[name]))
                self.assertEqual(receipt["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(receipt["changed_ranges"], b.changed_ranges(final, raw))
                self.assertEqual(b.verify_scope(final, raw, receipt["ranges"]), b.V06_HASH)
                for span in receipt["ranges"]:
                    if span["kind"] == "v05_restore":
                        at, size = span["file_offset"], span["size"]
                        self.assertEqual(raw[at:at + size], old[at:at + size])
                self.assertTrue(b.digests_ok(raw))
                self.assertEqual(b.space.status(raw), "applied")
                self.assertEqual(b.space._read_scale_directory(raw), b.space._read_scale_directory(final))


if __name__ == "__main__":
    unittest.main()
