"""Synthetic file-format, input routing and export checks; no retail bytes."""
from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_xex as x
from mod_editor.core import apf2k8_playcall_patch as p
from mod_editor.core import xex_codec as codec
from mod_editor.core.errors import ValidationError


class BitWriter:
    def __init__(self):
        self.bits = ""

    def put(self, value, width):
        self.bits += f"{value:0{width}b}" if width else ""

    def align(self, force=False):
        self.bits += "0" * ((-len(self.bits) % 16) or (16 if force else 0))

    def payload(self):
        self.align()
        return b"".join(int(self.bits[i:i + 16], 2).to_bytes(2, "little")
                        for i in range(0, len(self.bits), 16))


def raw_lzx(data):
    bits = BitWriter()
    bits.put(0, 1)
    bits.put(3, 3)
    bits.put(len(data), 24)
    bits.align(force=True)
    return bits.payload() + struct.pack("<3I", 1, 1, 1) + data + bytes(len(data) % 2)


def synthetic_xex(image=b"MZsynthetic-test", *, encrypted=False, window=32768):
    header = bytearray(0x400)
    struct.pack_into(">6I", header, 0, 0x58455832, 1, len(header), 0, 0x80, 1)
    struct.pack_into(">II", header, 24, 0x3FF, 0x300)
    struct.pack_into(">I", header, 0x84, len(image))
    lzx = raw_lzx(image)
    block = bytes(24) + len(lzx).to_bytes(2, "big") + lzx + bytes(2)
    block += bytes(-len(block) % 16)
    struct.pack_into(">IHHII", header, 0x300, 36, int(encrypted), 2, window, len(block))
    header[0x310:0x324] = hashlib.sha1(block).digest()
    if encrypted:
        assert image == b"MZsynthetic-test"
        # Fixed ciphertext of the authored raw LZX block, generated once with
        # independent AES. No optional crypto package is needed by these tests.
        header[0x1D0:0x1E0] = bytes.fromhex("3130ccb1cedcc803f9eda9a68713230d")
        block = bytes.fromhex(
            "c6a13b37878f5b826f4f8162a1c8d879f0b6d8eac1126c76aef3cb06dbe2887d7"
            "62e891f97afc0e9090e29703ec327c58c63a1af746f0e8ea1f97a465d895a5e")
    return bytes(header) + block


def codes(lengths):
    result, value, previous = {}, 0, 0
    for length, symbol in sorted((n, s) for s, n in enumerate(lengths) if n):
        value <<= length - previous
        result[symbol] = value, length
        value += 1
        previous = length
    return result


def write_lengths(writer, lengths):
    pre = [4] * 12 + [5] * 8
    for n in pre:
        writer.put(n, 4)
    symbols = codes(pre)
    pos = 0
    while pos < len(lengths):
        n = lengths[pos]
        count = 1
        while pos + count < len(lengths) and lengths[pos + count] == n:
            count += 1
        if n == 0 and count >= 20:
            count = min(51, count)
            writer.put(*symbols[18]); writer.put(count - 20, 5)
        elif n == 0 and count >= 4:
            count = min(19, count)
            writer.put(*symbols[17]); writer.put(count - 4, 4)
        elif n != 0 and count >= 4:
            count = min(5, count)
            writer.put(*symbols[19]); writer.put(count - 4, 1)
            writer.put(*symbols[(17 - n) % 17])
        else:
            count = 1
            writer.put(*symbols[(17 - n) % 17])
        pos += count


def compressed_lzx(aligned=False, reference=False):
    # Four main codes: literals M/Z/A, and a 5-byte match. Main tree zero
    # runs exercise both long and short pretree runs, with an empty length tree.
    slot = 8 if aligned else 0
    symbol = 256 + slot * 8 + 3
    lengths = [0] * 496
    for literal in (65, 77, 90, symbol):
        lengths[literal] = 2
    writer = BitWriter()
    writer.put(0, 1); writer.put(2 if aligned else 1, 3)
    writer.put(5 if reference else 8, 24)
    if aligned:
        for _ in range(8):
            writer.put(3, 3)
    write_lengths(writer, lengths[:256]); write_lengths(writer, lengths[256:])
    write_lengths(writer, [0] * 249)
    main = codes(lengths)
    if not reference:
        for literal in b"MZA":
            writer.put(*main[literal])
    writer.put(*main[symbol])
    if aligned:
        writer.put(1, 3)  # distance=15, reaches into the supplied reference
    return writer.payload()


class CodecTests(unittest.TestCase):
    def test_aes_standard_vector_and_cbc_chaining(self):
        key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        block = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        self.assertEqual(codec.aes_cbc_decrypt(key, block * 2),
                         plain + bytes(a ^ b for a, b in zip(plain, block)))
        with self.assertRaisesRegex(ValidationError, "block-aligned"):
            codec.aes_cbc_decrypt(key, block[:-1])

    def test_synthetic_retail_encrypted_container(self):
        decoded, receipt = x.decode_xex(synthetic_xex(encrypted=True))
        self.assertEqual(decoded, b"MZsynthetic-test")
        self.assertEqual(receipt["window_bits"], 15)
        self.assertEqual(receipt["compressed_blocks_sha1_verified"], 1)
        self.assertEqual(receipt["image_sha256"], hashlib.sha256(decoded).hexdigest())

    def test_unencrypted_normal_block_odd_length(self):
        self.assertEqual(x.decode_xex(synthetic_xex(b"MZ-odd!"))[0], b"MZ-odd!")

    def test_raw_lzx_spans_frames(self):
        raw = bytes(range(256)) * 260
        self.assertEqual(codec.lzx_decompress(raw_lzx(raw), len(raw), 15), raw)

    def test_verbatim_huffman_and_overlapping_match(self):
        self.assertEqual(codec.lzx_decompress(compressed_lzx(), 8, 15), b"MZAAAAAA")

    def test_aligned_match_with_reference_window(self):
        reference = bytes(32768 - 16) + b"0123456789ABCDEF"
        self.assertEqual(codec.lzx_decompress(compressed_lzx(True, True), 5, 15,
                                             reference=reference), b"12345")
        with self.assertRaisesRegex(ValidationError, "history"):
            codec.lzx_decompress(compressed_lzx(True, True), 5, 15)

    def test_malformed_xex_and_compressed_blocks_refused(self):
        original = synthetic_xex()
        cases = []
        for offset, word in ((8, 0xFFFFFFF0), (16, 0xFFFFFFF0), (20, 0x10000000),
                             (0x84, 0xFFFFFFF0), (0x308, 123), (0x30C, 0xFFFFFFF0)):
            data = bytearray(original); struct.pack_into(">I", data, offset, word)
            cases.append(bytes(data))
        damaged = bytearray(original); damaged[-1] ^= 1; cases.append(bytes(damaged))
        cases.extend(original[:n] for n in (1, 12, 25, 0x401, len(original) - 1))
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValidationError):
                x.decode_xex(data)

    def test_malformed_huffman_and_truncated_stream(self):
        for lengths in ([0] * 8, [1] * 3, [2] * 3, [17, 17]):
            with self.assertRaises(ValidationError):
                codec._Huffman(lengths)
        for stream in (b"", compressed_lzx()[:-4], raw_lzx(b"hello")[:-3]):
            with self.assertRaises(ValidationError):
                codec.lzx_decompress(stream, 8, 15)

    def test_delta_copy_zero_and_lzx(self):
        target = bytearray(b"MZ" + b"123456" * 4)
        compressed = raw_lzx(b"abcde")
        records = (struct.pack(">IIHH", 2, 10, 5, 1)
                   + struct.pack(">IIHH", 0, 20, 3, 0)
                   + struct.pack(">IIHH", 2, 3, 5, len(compressed)) + compressed)
        self.assertEqual(x._apply_delta(records, target), 3)
        self.assertEqual(target[10:15], b"12345")
        self.assertEqual(target[20:23], bytes(3))
        self.assertEqual(target[3:8], b"abcde")
        for records in (b"bad", struct.pack(">IIHH", 25, 0, 5, 1)):
            with self.assertRaises(ValidationError):
                x._apply_delta(records, target)


class InputTests(unittest.TestCase):
    def test_refusal_names_observed_and_both_accepted_shas(self):
        image = b"MZwrong"
        with self.assertRaises(ValidationError) as caught:
            p.check_image(image)
        for token in (hashlib.sha256(image).hexdigest(), "retail BASE", "Title Update 1.1",
                      *(profile.sha256 for profile in p.PROFILES)):
            self.assertIn(token, str(caught.exception))

    def test_folder_and_flat_share_identity_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "default.xex").write_bytes(synthetic_xex(encrypted=True))
            flat = folder / "test.pe"; flat.write_bytes(b"MZsynthetic-test")
            for source in (folder, flat):
                with self.assertRaisesRegex(ValidationError, "Executable SHA-256 mismatch") as caught:
                    x.derive_image(source)
                self.assertIn(hashlib.sha256(b"MZsynthetic-test").hexdigest(), str(caught.exception))
            (folder / "default.xex").unlink()
            with self.assertRaisesRegex(ValidationError, "No default.xex"):
                x.derive_image(folder)

    def test_discovers_xenia_and_xbox_content_layouts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); game = root / "game"; game.mkdir()
            installed = root / "content" / "54540807" / "000B0000" / "TU_test"
            installed.parent.mkdir(parents=True); installed.write_bytes(b"synthetic")
            self.assertEqual(x.discover_title_update(game), installed.resolve())
            self.assertEqual(x.discover_title_update(game, configured=installed.parent.parent.parent), installed.resolve())
            xbox = root / "elsewhere" / "0000000000000000" / "54540807" / "000B0000" / "TU_same"
            xbox.parent.mkdir(parents=True); xbox.write_bytes(b"synthetic")
            self.assertIn(x.discover_title_update(game, content_roots=(root / "elsewhere",)), (installed.resolve(), xbox.resolve()))
            xbox.write_bytes(b"different")
            with self.assertRaisesRegex(ValidationError, "Several different"):
                x.discover_title_update(game, content_roots=(root / "elsewhere",))
            self.assertEqual(x.discover_title_update(game, configured=xbox), xbox)

    def test_missing_configured_update_and_wrong_package_never_fall_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValidationError, "missing"):
                x.discover_title_update(tmp, configured=Path(tmp) / "missing")
            self.assertIsNone(x.discover_title_update(tmp))
        with self.assertRaisesRegex(ValidationError, "package SHA-256 mismatch"):
            x._extract_update(b"LIVE-unrecognized")

    def test_xenia_config_custom_content_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "xenia-canary.config.toml").write_text('[Storage]\nstorage_root = "data"\ncontent_root = "updates"\n')
            self.assertIn(root / "data" / "updates", x.xenia_content_roots(root / "xenia.exe"))

    def test_no_codec_subprocess_native_or_research_dependency(self):
        import ast
        for module in (codec, x):
            tree = ast.parse(Path(module.__file__).read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(n.name for n in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add(node.module or "")
            self.assertFalse(imported & {"subprocess", "ctypes", "cryptography", "Crypto", "tools.apf_playcall_audit"})


class ExportTests(unittest.TestCase):
    def test_folder_derivation_export_receipt_and_source_preservation(self):
        # A zero/synthetic image reaching the real hook/cave geometry; basic
        # compression avoids storing a 54 MiB fixture or slow synthetic LZX.
        header = bytearray(synthetic_xex()[:0x400])
        hook = p.PROFILES[0].hook - p.IMAGE_BASE
        struct.pack_into(">I", header, 0x84, p.IMAGE_SIZE)
        struct.pack_into(">IHH6I", header, 0x300, 32, 0, 1,
                         2, hook - 2, 4, p.IMAGE_SIZE - hook - 4, 0, 0)
        container = bytes(header) + b"MZ" + struct.pack(">I", 0x3D608506)
        image, _ = x.decode_xex(container)
        test_profile = replace(p.PROFILES[0], sha256=hashlib.sha256(image).hexdigest(),
                               fetch_sha256=hashlib.sha256(image[hook - 0x148:hook + 0x30]).hexdigest())
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, "PROFILES", (test_profile,)):
            root = Path(tmp); game = root / "game"; game.mkdir()
            source = game / "default.xex"; source.write_bytes(container)
            output = root / "test.patch.toml"
            receipt = p.write_patch(game, output)
            self.assertEqual(receipt["image_sha256"], test_profile.sha256)
            self.assertEqual(receipt["source"]["source_kind"], "game_folder")
            self.assertEqual(receipt["source"]["source_sha256"], hashlib.sha256(container).hexdigest())
            self.assertTrue(receipt["toml_reparsed"])
            self.assertEqual(receipt["status"], "unwitnessed")
            self.assertEqual(receipt["output_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            mtime = output.stat().st_mtime_ns
            self.assertEqual(p.write_patch(game, output), receipt)
            self.assertEqual(output.stat().st_mtime_ns, mtime)
            self.assertEqual(source.read_bytes(), container)
            self.assertEqual(sorted(q.name for q in game.iterdir()), ["default.xex"])
            with self.assertRaisesRegex(ValidationError, "separate .patch.toml"):
                p.write_patch(game, source)
            bad = game / "TU_unknown"; bad.write_bytes(b"LIVEbad")
            with self.assertRaisesRegex(ValidationError, "package SHA-256 mismatch"):
                p.write_patch(game, output)
            self.assertEqual(output.stat().st_mtime_ns, mtime)


if __name__ == "__main__":
    unittest.main()
