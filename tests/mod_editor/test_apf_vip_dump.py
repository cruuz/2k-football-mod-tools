"""Retail-free tests for the read-only APF VIP save inspector."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import apf_vip_dump as subject  # noqa: E402

PRIVATE_BASE_PE = Path(os.environ.get(
    "APF_VIP_BASE_PE", "/home/noah/2k-worktrees/.b765-scratch/d3/charge_base.pe"))
BASE_PE_SHA256 = "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"


def payload() -> bytes:
    data = bytearray(subject.USR_SIZE)
    struct.pack_into(">I", data, 0, 123456)
    name = "Synthetic".encode("utf-16-be") + b"\0\0"
    data[4:4 + len(name)] = name
    # Preserve stale name storage after the first terminator.
    data[0x20:0x24] = b"\0X\0Y"
    struct.pack_into(">IIIII", data, 0x3F00, 0x7FC00001, 0x7F800000,
                     0xFFFF0000, 0xFF800000, 0x80000000)
    data[-5:] = b"\xFF\xFE\xFD\xFC\xFB"
    return bytes(data)


def metadata(name: str = "Main.USR") -> bytes:
    data = bytearray(subject.XENIA_HEADER_SIZE)
    struct.pack_into(">II", data, 0, 1, 1)
    data[8:8 + len("Synthetic".encode("utf-16-be"))] = "Synthetic".encode("utf-16-be")
    data[0x108:0x108 + len(name)] = name.encode("ascii")
    data[0x134:0x13C] = b"opaque!!"
    struct.pack_into(">I", data, 0x140, subject.APF_TITLE_ID)
    data[0x144:0x148] = b".USR"
    return bytes(data)


def stfs_package(data: bytes, name: str = "Main.USR") -> bytes:
    """Small independent one-table CON fixture, deliberately unsigned."""
    count = (len(data) + 0xFFF) // 0x1000
    package = bytearray(0xA000 + (count + 2) * 0x1000)
    package[:4] = b"CON "
    struct.pack_into(">I", package, 0x340, 0xA000)
    struct.pack_into(">I", package, 0x344, 1)
    struct.pack_into(">I", package, 0x360, subject.APF_TITLE_ID)
    package[0x379] = 0x24
    package[0x37B] = 1
    struct.pack_into("<H", package, 0x37C, 1)
    struct.pack_into(">I", package, 0x395, count + 1)
    directory = 0xB000
    package[directory:directory + len(name)] = name.encode("ascii")
    package[directory + 0x28] = 0x40 | len(name)
    package[directory + 0x29:directory + 0x2C] = count.to_bytes(3, "little")
    package[directory + 0x2C:directory + 0x2F] = count.to_bytes(3, "little")
    package[directory + 0x2F:directory + 0x32] = (1).to_bytes(3, "little")
    package[directory + 0x32:directory + 0x34] = b"\xFF\xFF"
    struct.pack_into(">I", package, directory + 0x34, len(data))
    package[0xC000:0xC000 + len(data)] = data
    for block in range(count + 1):
        entry = 0xA000 + block * 0x18
        start = 0xB000 + block * 0x1000
        package[entry:entry + 0x14] = hashlib.sha1(package[start:start + 0x1000]).digest()
        package[entry + 0x14] = 0x80
        package[entry + 0x15:entry + 0x18] = (
            block + 1 if block != 0 and block < count else 0xFFFFFF).to_bytes(3, "big")
    package[0x381:0x395] = hashlib.sha1(package[0xA000:0xB000]).digest()
    package[0x32C:0x340] = hashlib.sha1(package[0x344:0xA000]).digest()
    return bytes(package)


class VipParseTests(unittest.TestCase):
    def test_payload_preserves_every_byte_and_native_allocation(self) -> None:
        data = payload()
        parsed = subject.parse_usr(data)
        self.assertEqual(bytes.fromhex(parsed["lossless"]["data"]), data)
        self.assertEqual(parsed["profile_id"]["u32be"], 123456)
        self.assertEqual(parsed["name"]["text"], "Synthetic")
        self.assertEqual(parsed["name"]["capacity_utf16_units"], 16)
        self.assertEqual(parsed["regions"][1]["offset"], 0x1410)
        self.assertEqual(sum(row["length"] for row in parsed["regions"]), len(data))
        self.assertEqual(len(parsed["word_views"]["words"]), len(data) // 4)
        self.assertFalse(parsed["integrity"]["writer_available"])

    def test_unknown_statistics_are_never_given_behavior_names(self) -> None:
        parsed = subject.parse_usr(payload())
        self.assertIn("UNKNOWN", parsed["word_views"]["status"])
        self.assertIn("HYPOTHESIS", parsed["opaque_record_view"]["status"])
        self.assertEqual(len(parsed["opaque_record_view"]["records"]), 128)
        self.assertEqual(parsed["opaque_record_view"]["records"][0]["offset"], 0x3F00)

    def test_native_named_run_pass_and_ratio_fields_decode_stored_values(self) -> None:
        data = bytearray(payload())
        struct.pack_into(">II", data, 0x1114, 17, 23)
        struct.pack_into(">f", data, 0x109C, 0.75)
        named = {field["name"]: field
                 for field in subject.parse_usr(bytes(data))["display_statistics"]["fields"]}
        self.assertEqual(named["Running Plays"]["value"], 17)
        self.assertEqual(named["Pass Plays"]["value"], 23)
        self.assertEqual(named["Completion %"]["value"], 0.75)
        self.assertEqual(named["Completion %"]["native_type"], "float32be")
        self.assertEqual(named["Running Plays"]["evidence"]["formatter"], "0x847670D0")
        self.assertIn("PROVED", named["Running Plays"]["status"])
        self.assertNotIn("Total Yards", named)  # computed formatter remains unmapped

    def test_motion_ui_reproduces_native_integer_truncation_and_display_percent(self) -> None:
        data = bytearray(payload())
        for numerator, denominator, expected in (
            (20.0, 168.0, 11), (5.9, 10.9, 50), (1.0, 3.0, 33),
            (5.0, 0.5, 0), (5.0, -2.0, 0), (-5.9, 10.9, -50),
        ):
            with self.subTest(numerator=numerator, denominator=denominator):
                struct.pack_into(">f", data, 0x3A28, numerator)
                struct.pack_into(">f", data, 0x39AC, denominator)
                motion = subject.parse_usr(bytes(data))["motion_ui_display"]
                self.assertEqual(motion["derived"]["displayed_integer_percent"], expected)
                self.assertIn("CPU_EFFECT_UNKNOWN", motion["status"])
                self.assertIn("EVENT_UNIT_UNKNOWN", motion["numerator"]["status"])
                self.assertEqual(motion["denominator"]["offset"], 0x39AC)

    def test_motion_ui_unsupported_conversion_retains_raw_bytes(self) -> None:
        data = bytearray(payload())
        struct.pack_into(">f", data, 0x3A28, 20.0)
        for denominator in (float("nan"), float("inf"), float(1 << 31)):
            with self.subTest(denominator=denominator):
                struct.pack_into(">f", data, 0x39AC, denominator)
                parsed = subject.parse_usr(bytes(data))
                self.assertEqual(parsed["motion_ui_display"]["derived"]["status"],
                                 "UNSUPPORTED_INPUT")
                self.assertEqual(bytes.fromhex(parsed["lossless"]["data"]), bytes(data))
                json.dumps(parsed, allow_nan=False)
        # Native <=0 denominator branch never converts the numerator.
        struct.pack_into(">f", data, 0x3A28, float("nan"))
        struct.pack_into(">f", data, 0x39AC, 0.0)
        derived = subject.parse_usr(bytes(data))["motion_ui_display"]["derived"]
        self.assertEqual(derived["displayed_integer_percent"], 0)

    def test_other_ui_ratios_add_float_components_before_integer_truncation(self) -> None:
        data = bytearray(payload())
        for offset, value in ((0x2740, 2.0), (0x2748, 0.6), (0x2764, 10.0),
                              (0x276C, 0.6), (0x2770, 3.9), (0x2774, 0.4),
                              (0x2778, 0.4), (0x277C, 0.4)):
            struct.pack_into(">f", data, offset, value)
        parsed = subject.parse_usr(bytes(data))
        displays = {row["name"]: row for row in parsed["other_ui_displays"]}
        self.assertEqual(displays["Audible"]["derived"]["displayed_integer_percent"], 8)
        self.assertEqual(displays["Formation Shifts"]["derived"]["displayed_integer_percent"], 30)
        self.assertEqual(displays["O-Line Adjustments"]["derived"]["displayed_integer_percent"], 10)
        for row in displays.values():
            self.assertIn("CPU_EFFECT_UNKNOWN", row["status"])
            for field in row["numerator_components"] + row["denominator_components"]:
                self.assertIn("EVENT_UNIT_UNKNOWN", field["status"])
        self.assertEqual(bytes.fromhex(parsed["lossless"]["data"]), bytes(data))

    def test_ui_float32_sum_overflow_and_nonfinite_inputs_are_lossless_strict_json(self) -> None:
        data = bytearray(payload())
        maximum = struct.unpack(">f", bytes.fromhex("7f7fffff"))[0]
        struct.pack_into(">f", data, 0x2764, 10.0)
        for value in (maximum, float("nan"), float("inf")):
            with self.subTest(value=value):
                for offset in (0x2748, 0x276C, 0x2774, 0x2778, 0x277C):
                    struct.pack_into(">f", data, offset, value)
                parsed = subject.parse_usr(bytes(data))
                displays = {row["name"]: row for row in parsed["other_ui_displays"]}
                for name in ("Audible", "O-Line Adjustments"):
                    self.assertEqual(displays[name]["derived"]["status"], "UNSUPPORTED_INPUT")
                self.assertEqual(bytes.fromhex(parsed["lossless"]["data"]), bytes(data))
                json.dumps(parsed, allow_nan=False)

    def test_nonfinite_floats_produce_strict_json_and_keep_exact_bits(self) -> None:
        parsed = subject.parse_usr(payload())
        json.loads(json.dumps(parsed, allow_nan=False))
        words = parsed["word_views"]["words"]
        self.assertEqual(words[0x3F00 // 4]["float32be_interpretation"], "NaN")
        self.assertEqual(words[0x3F04 // 4]["float32be_interpretation"], "Infinity")
        self.assertEqual(words[0x3F0C // 4]["float32be_interpretation"], "-Infinity")
        self.assertEqual(words[0x3F10 // 4]["raw_hex"], "80000000")

    def test_name_stops_at_first_nul_and_retains_stale_units(self) -> None:
        parsed = subject.parse_usr(payload())
        self.assertEqual(parsed["name"]["text"], "Synthetic")
        self.assertTrue(parsed["name"]["raw_hex"].endswith("00580059"))

    def test_invalid_utf16_is_lossless_with_explicit_error(self) -> None:
        data = bytearray(payload())
        data[4:8] = b"\xD8\x00\0\0"
        name = subject.parse_usr(bytes(data))["name"]
        self.assertIsNone(name["text"])
        self.assertIsNotNone(name["decode_error"])
        self.assertTrue(name["raw_hex"].startswith("d8000000"))

    def test_wrong_length_and_mutable_input_refused(self) -> None:
        for data in (b"", payload()[:-1], payload() + b"\0", bytearray(payload())):
            with self.subTest(size=len(data)):
                with self.assertRaises(subject.VipError):
                    subject.parse_usr(data)

    def test_metadata_maps_title_and_retains_uninitialized_padding(self) -> None:
        data = metadata()
        parsed = subject.parse_xenia_header(data)
        self.assertEqual(parsed["display_name"]["text"], "Synthetic")
        self.assertEqual(parsed["file_name"]["text"], "Main.USR")
        self.assertEqual(parsed["title_id"]["u32be"], subject.APF_TITLE_ID)
        self.assertEqual(parsed["tail_padding_144_hex"], "2e555352")
        self.assertIn("UNKNOWN", parsed["opaque_134"]["status"])
        self.assertEqual(bytes.fromhex(parsed["lossless_hex"]), data)
        with self.assertRaises(subject.VipError):
            subject.parse_xenia_header(data[:-1])

    @unittest.skipUnless(PRIVATE_BASE_PE.is_file(), "optional pinned APF BASE research PE absent")
    def test_all_named_cells_match_native_label_table_and_typed_record_load(self) -> None:
        data = PRIVATE_BASE_PE.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), BASE_PE_SHA256)
        base = 0x82000000
        for offset, name, native_type, table, label, formatter, load in subject.PRIMARY_STAT_FIELDS:
            with self.subTest(name=name, offset=hex(offset)):
                self.assertEqual(struct.unpack_from(">II", data, table - base), (label, formatter))
                label_bytes = data[label - base:label - base + len(name.encode("utf-16-be")) + 2]
                self.assertEqual(label_bytes, name.encode("utf-16-be") + b"\0\0")
                instruction = struct.unpack_from(">I", data, load - base)[0]
                self.assertEqual((instruction >> 16) & 31, 3)  # primary record base r3
                self.assertEqual(instruction & 0xFFFF, offset)
                self.assertEqual(instruction >> 26, 32 if native_type == "u32be" else 48)
        for instruction_va, context_delta in (
            (0x84A6C5D8, 0x1374), (0x84A6C5F4, 0x13F0),
            (0x84A6C6B8, 0x12C), (0x84A6C6BC, 0x108),
            (0x84A6C6DC, 0x110), (0x84A6C6E0, 0x134),
            (0x84A6C730, 0x12C), (0x84A6C74C, 0x138),
            (0x84A6C798, 0x12C), (0x84A6C7B4, 0x13C),
            (0x84A6C7B8, 0x140), (0x84A6C7C4, 0x144),
        ):
            instruction = struct.unpack_from(">I", data, instruction_va - base)[0]
            self.assertEqual(instruction >> 26, 48)  # lfs
            self.assertEqual((instruction >> 16) & 31, 3)
            self.assertEqual(instruction & 0xFFFF, context_delta)
        self.assertEqual(struct.unpack_from(">f", data, 0x820009B8 - base)[0], 100.0)


class VipFileTests(unittest.TestCase):
    def test_xenia_tree_dump_is_read_only_and_header_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            usr = root / "00000001/Main.USR/Main.USR"
            hdr = root / "Headers/00000001/Main.USR.header"
            usr.parent.mkdir(parents=True)
            hdr.parent.mkdir(parents=True)
            usr.write_bytes(payload())
            hdr.write_bytes(metadata())
            before = {path: path.read_bytes() for path in (usr, hdr)}
            parsed = subject.dump_path(root)
            self.assertEqual(parsed["container"]["kind"], "raw_usr")
            self.assertEqual(parsed["xenia_header"]["source_path"], str(hdr))
            self.assertEqual(before, {path: path.read_bytes() for path in (usr, hdr)})

    def test_ambiguous_tree_and_header_mismatch_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            usr = root / "Main.USR"
            hdr = root / "Main.USR.header"
            usr.write_bytes(payload())
            hdr.write_bytes(metadata("Other.USR"))
            with self.assertRaisesRegex(subject.VipError, "filename"):
                subject.dump_path(root)
            hdr.unlink()
            (root / "Other.USR").write_bytes(payload())
            with self.assertRaisesRegex(subject.VipError, "individual"):
                subject.dump_path(root)

    def test_new_json_cannot_overwrite_source_or_existing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Main.USR"
            source.write_bytes(payload())
            with self.assertRaises(FileExistsError):
                subject.write_json({"x": 1}, source)
            self.assertEqual(source.read_bytes(), payload())
            output = Path(tmp) / "dump.json"
            subject.write_json({"x": 1}, output)
            self.assertEqual(json.loads(output.read_text()), {"x": 1})
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                subject.write_json({"x": 2}, output)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_input_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            usr = root / "Main.USR"
            usr.write_bytes(payload())
            link = root / "link.USR"
            try:
                link.symlink_to(usr)
            except OSError:
                self.skipTest("platform does not allow symlink creation")
            with self.assertRaisesRegex(subject.VipError, "symlink"):
                subject.dump_path(link)

    def test_signed_stfs_member_extracts_but_never_authenticates_rsa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vip.con"
            source.write_bytes(stfs_package(payload()))
            parsed = subject.dump_path(source, member="Main.USR")
            self.assertEqual(parsed["container"]["kind"], "CON")
            self.assertTrue(parsed["container"]["metadata_hash_verified"])
            self.assertTrue(parsed["container"]["active_hash_tree_verified"])
            self.assertFalse(parsed["container"]["rsa_signature_verified"])
            self.assertEqual(bytes.fromhex(parsed["vip"]["lossless"]["data"]), payload())

    def test_corrupt_stfs_block_and_wrong_member_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vip.con"
            valid = stfs_package(payload())
            source.write_bytes(valid)
            with self.assertRaisesRegex(subject.VipError, "exactly one"):
                subject.dump_path(source, member="Other.USR")
            damaged = bytearray(valid)
            damaged[0xC000] ^= 1
            source.write_bytes(damaged)
            with self.assertRaisesRegex(subject.VipError, "SHA-1"):
                subject.dump_path(source)

    def test_wrong_title_metadata_and_raw_member_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "Main.USR"
            header = root / "Main.USR.header"
            source.write_bytes(payload())
            data = bytearray(metadata())
            struct.pack_into(">I", data, 0x140, 0x12345678)
            header.write_bytes(data)
            with self.assertRaisesRegex(subject.VipError, "another title"):
                subject.dump_path(source, header=header)
            with self.assertRaisesRegex(subject.VipError, "only to STFS"):
                subject.dump_path(source, member="Main.USR")


if __name__ == "__main__":
    unittest.main()
