"""Native shoulder identity, lossless donor transport, refusals and disc proof."""
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_nyg_numbers as numbers
from tools.b77 import ny1_repair as repair
import nfl_txtr as tx
from nfl_live_numbers_nameplate_png_import import decode_levels


def fixture(name, colour=(255, 255, 255), size=64):
    system = bytearray(128)
    system[12:16] = b"TXTR"
    struct.pack_into("<II", system, 16, 32 - 15, 64 - 19)
    encoded = (name + "\0").encode("utf-16le")
    system[32:32 + len(encoded)] = encoded
    count = sum((size >> level)**2 for level in range(4))
    power = size.bit_length() - 1
    struct.pack_into("<5I", system, 68, 0, count,
                     (power << 24) | (power << 20) | (4 << 16) | (11 << 8) | (2 << 4), 0, 0)
    palette = bytearray(1024)
    palette[4:8] = bytes((*colour[::-1], 255))
    palette[8:12] = bytes((*colour[::-1], 90))
    # Each mip has its own asymmetric landmark and partial-alpha edge. A
    # compiler that copies only mip0 or regenerates lower mips must fail.
    video = b""
    for level in range(4):
        width = size >> level
        pixels = bytearray(width**2)
        pixels[width + level + 1] = 1
        pixels[2 * width + level + 1] = 2
        video += tx.swizzle_2d(bytes(pixels), width, width, 1)
    decoded = bytes(system) + video + bytes(palette)
    stream, _ = tx.compress_vc_lz(decoded, stream_tag=1, offset_bits=12)
    stored = (len(stream) + 31) & ~15
    return tx.HEADER.pack(b"TXTR", stored, 128, count + 1024, tx.COMPRESSED_SENTINEL, 32, 0, 0) + stream + bytes(stored-len(stream))


def levels(span):
    chunk = tx.parse_chunks(span)[0]
    decoded, _ = tx.decode_chunk(span, chunk)
    return decode_levels(decoded, chunk, tx.parse_texture(decoded, chunk))


class DonorTransport(unittest.TestCase):
    def test_all_four_native_mips_and_alpha_are_copied_exactly(self):
        source, arm = fixture("48"), fixture("an48", (184, 26, 53))
        out, receipt = numbers.copy_digit_video(source, arm, 0)
        self.assertEqual(levels(out), levels(source))
        self.assertEqual(out[:32], arm[:32])
        chunk = tx.parse_chunks(out)[0]
        decoded, _ = tx.decode_chunk(out, chunk)
        old, _ = tx.decode_chunk(arm, tx.parse_chunks(arm)[0])
        self.assertEqual(decoded[:128], old[:128])
        self.assertEqual(tx.parse_texture(decoded, chunk).name, "an48")
        self.assertTrue(receipt["wrapper_identical"])
        self.assertLessEqual(receipt["fit"]["exact_minimum_scratch"], chunk.overlap_scratch_bytes)

    def test_replay_does_not_recompress(self):
        out, _ = numbers.copy_digit_video(fixture("48"), fixture("an48", (184, 26, 53)), 0)
        with mock.patch.object(numbers, "rebuild_fixed_span_filled", side_effect=AssertionError("recompressed")):
            repeat, receipt = numbers.copy_digit_video(fixture("48"), out, 0)
        self.assertEqual(out, repeat)
        self.assertFalse(receipt["changed"])

    def test_helmet_and_wrong_digit_are_refused(self):
        for name in ("hn48", "an49", "48"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "family/name"):
                numbers.copy_digit_video(fixture("48"), fixture(name), 0)

    def test_coloured_donor_and_wrong_slot_size_are_refused(self):
        with self.assertRaisesRegex(ValueError, "plain white"):
            numbers.copy_digit_video(fixture("48", (184, 26, 53)), fixture("an48"), 0)
        with self.assertRaisesRegex(ValueError, "storage"):
            numbers.copy_digit_video(fixture("48"), fixture("an48", size=32), 0)

    def test_family_resolution_follows_names_even_when_chunks_move(self):
        spans = [fixture(prefix + str(48 + i)) for prefix in ("an", "", "hn") for i in range(10)]
        resolved = numbers.digit_chunks(b"".join(spans))
        self.assertEqual(resolved["an48"].index, 0)
        self.assertEqual(resolved["48"].index, 10)
        self.assertEqual(resolved["hn48"].index, 20)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            numbers.digit_chunks(b"".join(spans + [spans[0]]))
        with self.assertRaisesRegex(ValueError, "missing"):
            numbers.digit_chunks(b"".join(spans[:-1]))

    def test_native_tool_refuses_wrong_disc_before_creating_output(self):
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "bad.iso"; source.write_bytes(b"not a disc")
            output = root / "out.iso"
            with self.assertRaisesRegex(ValueError, "unknown input"):
                repair.run(SimpleNamespace(input=source, output=output, receipts=root / "receipts"))
            self.assertFalse(output.exists())

    def test_unrelated_image_is_skipped_by_studio_but_refused_by_native_repair(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "other.img"; path.write_bytes(b"other game")
            receipt = numbers.apply_to_image(path)
            self.assertEqual(receipt["state"], "other_image")
            self.assertEqual(receipt["written_bytes"], 0)
            self.assertEqual(path.read_bytes(), b"other game")
            with self.assertRaises(ValueError):
                numbers.apply_to_image(path, strict=True)

    def test_uni_ownership_accepts_arm_names_and_rejects_helmet_names(self):
        from tools.b77 import uni_repair
        import tempfile
        spans = [fixture(prefix + str(48 + i)) for prefix in ("", "hn", "an") for i in range(10)]
        raw = b"".join(spans); chunks = numbers.digit_chunks(raw)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("an48", "hn48"):
                c = chunks[name]; span = raw[c.offset:c.end_offset]
                (root / "digit.span").write_bytes(span)
                patch = dict(offset=c.offset, length=len(span), label=f"digit_{c.index}",
                             replacement="digit.span", before_sha256=numbers.sha(span), after_sha256=numbers.sha(span))
                if name.startswith("an"):
                    uni_repair.validate_resource("18H0.IFF", raw, [patch], root)
                else:
                    with self.assertRaisesRegex(ValueError, "outside owned"):
                        uni_repair.validate_resource("18H0.IFF", raw, [patch], root)


BASE = os.environ.get("NFL2K5_NY1_BASE")


@unittest.skipUnless(BASE, "set NFL2K5_NY1_BASE to the pinned input disc for native integration")
class NativeDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.ranges = repair.read_resource(Path(BASE))
        cls.parts, cls.receipt = numbers.compile_resource(cls.raw)
        out = bytearray(cls.raw)
        for offset, data in cls.parts:
            out[offset:offset + len(data)] = data
        cls.fixed = bytes(out)

    def test_every_changed_byte_is_a_shoulder_and_all_mips_equal_chest(self):
        self.assertEqual(len(self.parts), 10)
        old, new = numbers.digit_chunks(self.raw), numbers.digit_chunks(self.fixed)
        owned = set()
        for i in range(10):
            a, j = new["an" + str(48 + i)], old[str(48 + i)]
            self.assertEqual(a.index, 33 + i)
            owned.update(range(a.offset, a.end_offset))
            self.assertEqual(levels(self.fixed[a.offset:a.end_offset]), levels(self.raw[j.offset:j.end_offset]))
        changed = {i for i, pair in enumerate(zip(self.raw, self.fixed)) if pair[0] != pair[1]}
        self.assertTrue(changed)
        self.assertFalse(changed - owned)

    def test_exact_replay_has_no_writes(self):
        parts, receipt = numbers.compile_resource(self.fixed)
        self.assertEqual(parts, [])
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_corrupted_arm_donor_and_partial_output_are_refused(self):
        spec = numbers.pins()["digits"]
        # Mutate compressed padding so parsing remains valid but the pin fails.
        for offset in (spec[0]["offset"] + spec[0]["length"] - 1,
                       spec[0]["donor_offset"] + spec[0]["donor_length"] - 1):
            bad = bytearray(self.raw);bad[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "input hashes"):
                numbers.compile_resource(bytes(bad))
        bad = bytearray(self.raw);at, data = self.parts[0];bad[at:at+len(data)] = data
        with self.assertRaisesRegex(ValueError, "partially repaired"):
            numbers.compile_resource(bytes(bad))

    def test_studio_preserves_a_separate_custom_recipe(self):
        # Fully unrelated shoulder pins are a user's separate kit, not ours.
        with mock.patch.object(numbers, "pins", return_value={**numbers.pins(), "digits": [
                {**p, "before_sha256": "0" * 64, "after_sha256": "1" * 64}
                for p in numbers.pins()["digits"]]}):
            parts, receipt = numbers.compile_resource(self.raw, strict=False)
        self.assertEqual(parts, [])
        self.assertEqual(receipt["state"], "other_uniform")


if __name__ == "__main__":
    unittest.main()
