"""Synthetic-only STFS writer contract and optional pinned Xenia source audit."""
from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_apf_save_custom_team_appearance import synthetic_save, synthetic_stfs
import apf_stfs_roster_extract as reader
import apf_stfs_roster_rehash as subject


def xenia_chain_payload(data: bytes) -> bytes:
    """Independent translation of pinned BlockToOffset / ReadEntry traversal.

    No production reader geometry calls. This is a model, not emulator execution.
    """
    base = (int.from_bytes(data[0x340:0x344], "big") + 4095) & ~4095
    copies = 1 if data[0x37B] & 1 else 2
    active = (data[0x37B] >> 1) & 1
    total = int.from_bytes(data[0x395:0x399], "big")

    def offset(block):
        physical = block
        for level in (170, 28900, 4913000):
            physical += ((block + level) // level) * copies
            if block < level:
                break
        return base + physical * 4096

    directory = offset(int.from_bytes(data[0x37E:0x381], "little"))
    length = int.from_bytes(data[directory + 0x34:directory + 0x38], "big")
    block = int.from_bytes(data[directory + 0x2F:directory + 0x32], "little")
    result = bytearray()
    while len(result) < length:
        if block >= total:
            raise ValueError("Xenia chain ended early")
        result.extend(data[offset(block):offset(block) + min(4096, length - len(result))])
        group = block // 170
        table = base + (0 if group == 0 else group * (170 + copies) + copies) * 4096
        if copies == 2:
            leaf_active = active
            if total > 170:
                top_entry = base + (170 + copies + active) * 4096 + group * 24
                leaf_active = (data[top_entry + 20] >> 6) & 1
            table += leaf_active * 4096
        entry = table + (block % 170) * 24
        block = int.from_bytes(data[entry + 21:entry + 24], "big")
    return bytes(result)


class RehashTests(unittest.TestCase):
    def test_known_synthetic_roster_round_trip_all_copies_and_chains(self):
        raw = synthetic_save()
        for copies, active in ((1, 0), (2, 0), (2, 1)):
            for fragmented in (False, True):
                with self.subTest(copies=copies, active=active, fragmented=fragmented):
                    package = synthetic_stfs(raw, copies=copies, active=active, fragmented=fragmented)
                    self.assertEqual(xenia_chain_payload(package), raw)
                    replacement = bytearray(raw)
                    replacement[0x1DD04C + 64 * 48:0x1DD04C + 64 * 48 + 4] = b"\xff\x12\x34\x56"
                    output, receipt = subject.rehash_roster(package, bytes(replacement))
                    self.assertEqual(reader.extract_roster_payload(output).payload, replacement)
                    self.assertEqual(xenia_chain_payload(output), replacement)
                    self.assertEqual(output[4:0x32C], package[4:0x32C])
                    self.assertTrue(subject.verify_rehash(package, output, receipt)["verified"])
                    self.assertEqual(len(receipt["hash_table_addresses_rehashed"]), 2)
                    self.assertFalse(receipt["console_resigned"])
                    self.assertIn("real console will reject", receipt["label"])

    def test_one_level_and_all_magics(self):
        for magic in reader.STFS_MAGICS:
            package = synthetic_stfs(b"a" * 6000, magic)
            output, receipt = subject.rehash_roster(package, b"b" * 6000)
            self.assertEqual(xenia_chain_payload(output), b"b" * 6000)
            self.assertEqual(len(receipt["hash_table_addresses_rehashed"]), 1)
            self.assertEqual(receipt["data_blocks_rehashed"], [1, 2])

    def test_metadata_payload_and_receipt_tampering_are_rejected(self):
        source = synthetic_stfs(b"a" * 6000)
        output, receipt = subject.rehash_roster(source, b"b" * 6000)
        for offset in (0x344, 0xA000, 0xB000, 0xC000):
            tampered = bytearray(output)
            tampered[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(reader.StfsRosterError):
                subject.verify_rehash(source, bytes(tampered), receipt)
        tampered = bytearray(output)
        tampered[4] ^= 1  # RSA signature lies outside the hash tree, but must be preserved.
        with self.assertRaisesRegex(reader.StfsRosterError, "outside roster"):
            subject.verify_rehash(source, bytes(tampered), receipt)
        with self.assertRaisesRegex(reader.StfsRosterError, "data_blocks_rehashed"):
            subject.verify_rehash(source, output, dict(receipt, data_blocks_rehashed=[]))
        with self.assertRaisesRegex(reader.StfsRosterError, "length"):
            subject.rehash_roster(source, b"short")

    def test_chain_incompatibility_and_shared_directory_are_refused(self):
        source = bytearray(synthetic_stfs(b"a" * 6000))
        source[0xA000 + 24 + 21:0xA000 + 24 + 24] = b"\xff\xff\xff"
        source[0x381:0x395] = hashlib.sha1(source[0xA000:0xB000]).digest()
        source[0x32C:0x340] = hashlib.sha1(source[0x344:0xA000]).digest()
        with self.assertRaisesRegex(reader.StfsRosterError, "Xenia traversal"):
            subject.rehash_roster(bytes(source), b"b" * 6000)
        source = bytearray(synthetic_stfs(b"a" * 6000))
        source[0xB02F:0xB032] = b"\0\0\0"
        source[0xA000:0xA014] = hashlib.sha1(source[0xB000:0xC000]).digest()
        source[0x381:0x395] = hashlib.sha1(source[0xA000:0xB000]).digest()
        source[0x32C:0x340] = hashlib.sha1(source[0x344:0xA000]).digest()
        with self.assertRaisesRegex(reader.StfsRosterError, "share data blocks"):
            subject.rehash_roster(bytes(source), b"b" * 6000)

    def test_boundary_offsets_match_xenia_equation(self):
        # Exercise the original single-copy end-of-level bug and two-copy bug.
        for copies in (1, 2):
            r = object.__new__(reader._StfsReader)
            r.sex = copies - 1
            r.allocated_blocks = 28900
            for block in (0, 169, 170, 171, 28729, 28730, 28899):
                expected = block + (block // 170 + 1) * copies + (copies if block >= 170 else 0)
                self.assertEqual(r._data_backing_block(block), expected)


class LocalXeniaAuditTests(unittest.TestCase):
    def test_pinned_source_has_no_signature_verification(self):
        root = Path("/home/noah/.codex-tmp/xenia-slot43-build/src/xenia/vfs/devices")
        if not root.is_dir():
            self.skipTest("optional local Xenia source revision d09cae8d is unavailable")
        pins = {
            "xcontent_container_device.cc": "21ca059098c8c93fa7e0a26016ca24196d3ba3e45f29f97675887524ddde6c14",
            "xcontent_devices/stfs_container_device.cc": "0dad581748c15cc0db9d9b5c399077a1f49c6bb461729c01523579a0b6ff5202",
            "stfs_xbox.h": "47ed398b7267615542ea0f9036a6cf79fd6ed66db367caf39f4f64b6e0aeda4c",
        }
        for name, sha in pins.items():
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), sha)
        text = (root / "xcontent_container_device.cc").read_text()
        body = text[text.index("XContentContainerDevice::Result XContentContainerDevice::ReadHeaderAndVerify("):]
        self.assertIn("is_magic_valid()", body)
        self.assertNotIn("signature", body)
        self.assertNotIn("sha1", body)


if __name__ == "__main__":
    unittest.main()
