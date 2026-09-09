from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.apf_coverage_tu_extract import extract, BLOCK, FANOUT
from tools.apf_coverage_function_diff import Image, Function, compare


def live_fixture(blocks=172):
    header, allocated = 0xB000, blocks + 1
    def backing(n):
        return n + n // FANOUT + 1 + int(n >= FANOUT)
    out = bytearray(header + (backing(allocated - 1) + 1) * BLOCK)
    out[:4] = b"LIVE"
    struct.pack_into(">I", out, 0x340, 0xAD00)
    out[0x379], out[0x37B] = 0x24, 1
    struct.pack_into("<H", out, 0x37C, 1)
    struct.pack_into(">I", out, 0x395, allocated)
    directory = bytearray(BLOCK)
    directory[:12] = b"default.xexp"
    directory[0x28] = 0x40 | 12
    directory[0x29:0x2C] = blocks.to_bytes(3, "little")
    directory[0x2C:0x2F] = blocks.to_bytes(3, "little")
    directory[0x2F:0x32] = (1).to_bytes(3, "little")
    struct.pack_into(">H", directory, 0x32, 0xFFFF)
    struct.pack_into(">I", directory, 0x34, blocks * BLOCK - 23)
    payload = bytes((n * 7 + 11) % 251 for n in range(BLOCK))
    tables = [bytearray(BLOCK) for _ in range((allocated + FANOUT - 1) // FANOUT)]
    for n in range(allocated):
        data = bytes(directory) if n == 0 else payload
        address = header + backing(n) * BLOCK
        out[address:address + BLOCK] = data
        table, o = tables[n // FANOUT], n % FANOUT * 24
        table[o:o + 20] = hashlib.sha1(data).digest()
        table[o + 20] = 0x80
        table[o + 21:o + 24] = b"\xff\xff\xff"
    if allocated > FANOUT:
        top = bytearray(BLOCK)
        for i, table in enumerate(tables):
            top[i * 24:i * 24 + 20] = hashlib.sha1(table).digest()
            address = header + (i * (FANOUT + 1) + int(i > 0)) * BLOCK
            out[address:address + BLOCK] = table
        address = header + (FANOUT + 1) * BLOCK
        out[address:address + BLOCK] = top
    else:
        top = tables[0]
        out[header:header + BLOCK] = top
    out[0x381:0x395] = hashlib.sha1(top).digest()
    out[0x32C:0x340] = hashlib.sha1(out[0x344:header]).digest()
    return bytes(out), (payload * blocks)[:-23]


def pe_fixture(starts=(0x400, 0x420), value=7, relocated=False):
    out = bytearray(0x1000)
    out[:2] = b"MZ"
    struct.pack_into("<I", out, 0x3C, 0x80)
    out[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", out, 0x86, 2)
    struct.pack_into("<H", out, 0x94, 0xE0)
    struct.pack_into("<I", out, 0xB4, 0x82000000)
    for i, (name, size, rva) in enumerate(((b".text", 0x300, 0x400), (b".pdata", len(starts)*8, 0x800))):
        o = 0x178 + i * 40
        out[o:o + len(name)] = name
        # Deliberately wrong raw-file offsets: only VA mapping is valid here.
        struct.pack_into("<IIII", out, o + 8, size, rva, size, rva + 0x100)
    for i, start in enumerate(starts):
        struct.pack_into(">II", out, 0x800 + i * 8, 0x82000000 + start, 4 << 8)
        target = 0x82000900 + int(relocated) * 0x10
        instructions = (0x7D8802A6, 0x3D608200, 0x396B0000 | (target & 65535), 0x4E800020)
        if i == len(starts)-1:
            instructions = (0x7D8802A6, 0x38600000 | value, 0x38800003, 0x4E800020)
        struct.pack_into(">4I", out, start, *instructions)
    return bytes(out)


class StfsTests(unittest.TestCase):
    def test_zero_parent_status_two_levels_and_partial_final_block(self):
        raw, expected = live_fixture()
        payload, receipt = extract(raw)
        self.assertEqual(payload, expected)
        self.assertEqual(receipt["verified_data_blocks_including_directory"], 173)
        self.assertEqual(receipt["verified_level_zero_tables"], 2)
        self.assertFalse(receipt["rsa_verified"])

    def test_one_level(self):
        raw, expected = live_fixture(2)
        self.assertEqual(extract(raw)[0], expected)

    def test_integrity_at_each_level_and_bounds(self):
        raw, _ = live_fixture()
        for offset, message in ((0x390, "metadata"), (0xB000 + 171*4096, "top-table"),
                                (0xB000, "level-zero"), (0xD000, "data-block")):
            bad = bytearray(raw)
            bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, message):
                extract(bytes(bad))
        with self.assertRaises(ValueError):
            extract(raw[:-4096])

    def test_reject_other_layout_before_any_payload(self):
        raw, _ = live_fixture(2)
        b = bytearray(raw)
        b[0x37B] = 0
        b[0x32C:0x340] = hashlib.sha1(b[0x344:0xB000]).digest()
        with self.assertRaisesRegex(ValueError, "single-table"):
            extract(bytes(b))


class DiffTests(unittest.TestCase):
    def test_flat_mapping_bounds_and_prologues(self):
        im = Image(pe_fixture())
        self.assertEqual(im.word(0x82000400), 0x7D8802A6)
        self.assertEqual(len(im.functions()), 2)
        self.assertEqual(im.prologues(), [0x82000400, 0x82000420])
        with self.assertRaises(ValueError):
            im.read(0x81FFFFFF, 4)
        b = bytearray(pe_fixture())
        struct.pack_into(">I", b, 0x800, 0x82000900)
        with self.assertRaises(ValueError):
            Image(bytes(b)).functions()

    def test_address_relocation_does_not_hide_nonaddress_immediate(self):
        b = Image(pe_fixture())
        t = Image(pe_fixture((0x440, 0x460), value=8, relocated=True))
        report = compare(b, t)
        self.assertEqual(report["functions"][0]["comparison"], "normalized_equal")
        self.assertEqual(report["functions"][1]["comparison"], "normalized_different")
        self.assertEqual(report["functions"][1]["tu_va"], "0x82000460")

    def test_extra_function_is_unmatched(self):
        b = Image(pe_fixture())
        t = Image(pe_fixture((0x400, 0x420, 0x440)))
        report = compare(b, t)
        self.assertEqual(len(report["unmatched_tu"]), 1)
        self.assertEqual(len(report["functions"]), 2)


if __name__ == "__main__":
    unittest.main()
