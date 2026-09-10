"""Synthetic stream/bounds tests; no game files needed."""
from __future__ import annotations

import io
import json
import random
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio.ps3_roster_probe import compare_rosters, read_input
from mod_editor.apf_studio.ps3_texture_probe import NestedPs3Archive, ProbeError, texture_kind
from tests.mod_editor.test_apf_save_roster_players import roster_save


def nested_package(path, *, stored=True, overlap=False):
    # One IFF-sized synthetic entry spans two tiny virtual packs. Actual bytes
    # need not form an IFF to exercise the stream directory and range adapter.
    header = bytearray(128)
    struct.pack_into(">6I", header, 0, 0xAA00B3BF, 16, 2, 0, 1, 0)
    struct.pack_into(">II8s", header, 24, 8, 0, "0A".encode("utf-16-be") + b"\0" * 4)
    struct.pack_into(">II8s", header, 40, 8, 0, "0B".encode("utf-16-be") + b"\0" * 4)
    struct.pack_into(">3I", header, 56, 0x12345678, 1 if overlap else 7, 2)
    header[112:] = b"A" * 16
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("game/USRDIR/0A", bytes(header))
        z.writestr("game/USRDIR/0B", b"B" * 128)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED) as z:
        z.writestr("Modify APF game File.zip", inner.getvalue())


class TextureStreamTests(unittest.TestCase):
    def test_inline_ps3_texture_uses_relative_pixel_pointer(self):
        from mod_editor.apf_studio.ps3_texture_probe import _ps3_image
        header = bytearray(256)
        struct.pack_into(">4BI3H2B2I", header, 0x58, 0xA5, 1, 2, 0, 0xAAE4, 4, 2, 1, 0, 0, 16, 0)
        struct.pack_into(">i", header, 0xA4, 0x5D)
        image, _ = _ps3_image([bytes(header) + bytes.fromhex("ff112233") * 8])
        self.assertEqual(image.getpixel((3, 1)), (17, 34, 51, 255))
        struct.pack_into(">i", header, 0xA4, 0)
        with self.assertRaisesRegex(ProbeError, "pixel pointer"):
            _ps3_image([bytes(header) + b"\0" * 32])

    def test_accelerated_decoder_matches_existing_decoder(self):
        from mod_editor.apf_studio.ps3_texture_probe_fast import decode_xbox_base
        import apf_inner
        rng = random.Random(715)
        for fmt in (2, 3, 4, 6, 10, 15, 18, 19, 20):
            for tiled in (False, True):
                for endian in range(4):
                    with self.subTest(format=fmt, tiled=tiled, endian=endian):
                        metadata = dict(width=64, height=32, pitch_pixels=128, format=fmt, format_name=str(fmt),
                                        tiled=tiled, dimension=1, stacked=False, endianness=endian,
                                        swizzle_components=((2, 1, 5, 0), (4, 1, 0, 3), (2, 0, 1, 3), (0, 1, 2, 3))[endian])
                        data = rng.randbytes(128 * 128 * 16)
                        self.assertEqual(decode_xbox_base(metadata, data), apf_inner.decode_txtr_base_rgba(metadata, data))

    def test_nested_compressed_volumes_cross_pack_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "package.zip"
            nested_package(path)
            with NestedPs3Archive(path) as archive:
                self.assertEqual(archive.entries[0].name_id, 0x12345678)
                self.assertEqual(archive.read_entry(archive.entries[0]), b"A" * 16 + b"B" * 16)
                with self.assertRaisesRegex(ProbeError, "Backward"):
                    archive.read_entry(archive.entries[0])
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()), ["package.zip"])

    def test_compressed_outer_and_overlapping_directory_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "package.zip"
            for options in ({"stored": False}, {"overlap": True}):
                nested_package(path, **options)
                with self.assertRaises(ProbeError):
                    with NestedPs3Archive(path):
                        pass

    def test_prefix_then_remainder_stays_forward_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "package.zip"
            nested_package(path)
            with NestedPs3Archive(path) as archive:
                entry = archive.entries[0]
                self.assertEqual(archive.read_entry_range(entry, 0, 4), b"AAAA")
                self.assertEqual(archive.read_entry_range(entry, 4, 28), b"A" * 12 + b"B" * 16)
                with self.assertRaisesRegex(ProbeError, "outside"):
                    archive.read_entry_range(entry, 30, 3)

    def test_candidate_kinds(self):
        for name, kind in (("logo_l0", "logos"), ("endzone_l1", "endzones"), ("helmet_color", "helmets"),
                           ("jersey_color", "uniforms"), ("number_03", "numbers"), ("stad_banner", "banners")):
            self.assertEqual(texture_kind(name), kind)


class RosterProbeTests(unittest.TestCase):
    def test_identical_synthetic_payload_has_zero_differences(self):
        raw = roster_save()
        report = compare_rosters(raw, raw)
        self.assertTrue(report["byte_identical"])
        self.assertTrue(report["ps3"]["players_valid"])
        self.assertEqual(report["different_bytes"], 0)
        self.assertNotIn("Alpha", json.dumps(report))

    def test_odd_nickname_pointer_is_reported_without_normalization(self):
        xbox = roster_save()
        ps3 = bytearray(xbox)
        field = 0x150 + 0x118
        pointer = struct.unpack_from(">I", ps3, field)[0]
        struct.pack_into(">I", ps3, field, pointer + 1)
        report = compare_rosters(bytes(ps3), xbox)
        self.assertFalse(report["ps3"]["players_valid"])
        self.assertIn("nickname", report["ps3"]["players_error"])
        self.assertEqual(report["ps3"]["name_pointer_audit"]["nickname"]["odd_target_count"], 1)
        self.assertFalse(report["converter_writer_authorized_by_evidence"])
        self.assertGreater(report["different_bytes"], 0)
        self.assertEqual(xbox, roster_save())

    def test_truncated_inputs_and_missing_zip_member(self):
        with self.assertRaises(ValueError):
            compare_rosters(b"raw", b"raw")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "roster.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("USERDATA", b"synthetic")
            self.assertEqual(read_input(path, "USERDATA"), b"synthetic")
            with self.assertRaises(ValueError):
                read_input(path, "missing")


if __name__ == "__main__":
    unittest.main()
