"""Tests for the Midway ``SEC `` section container.  Synthetic containers only."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import midway_sec as sec  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


SECTIONS = [(2, "first", b"\x00\x40\x00\x00" + bytes(300)), (4, "model.rws", b"\x10\x00\x00\x00" + bytes(1000)), (2, "third", b"x")]


class SecTests(unittest.TestCase):
    def test_sections_are_named_located_contiguous_and_128_aligned(self) -> None:
        blob = sec.build_sec(SECTIONS)
        c = sec.parse(blob)
        self.assertTrue(sec.looks_like_sec(blob))
        self.assertEqual([s.name for s in c.sections], ["first", "model.rws", "third"])
        self.assertEqual([s.kind for s in c.sections], [2, 4, 2])
        self.assertEqual([s.size for s in c.sections], [384, 1024, 128])
        self.assertEqual(c.first_section_offset, 128)
        self.assertEqual(c.section_bytes(c.sections[1])[:4], b"\x10\x00\x00\x00")
        self.assertEqual(c.identities(), {"sections": 3, "contiguous": True, "last_ends_at_total": True,
                                          "sizes_are_128_multiples": True, "first_section_follows_padded_names": True, "kinds": [2, 4]})
        self.assertEqual(c.total, len(blob))
        self.assertEqual(c.fill, 0xCDCDCDCD)

    def test_the_empty_form_is_128_bytes_of_pad(self) -> None:
        blob = sec.build_sec()
        self.assertEqual(len(blob), 128)
        c = sec.parse(blob)
        self.assertTrue(c.is_empty)
        self.assertIsNone(c.first_section_offset)
        self.assertTrue(c.identities()["last_ends_at_total"])

    def test_refusals(self) -> None:
        blob = bytearray(sec.build_sec(SECTIONS))
        with self.assertRaises(Refusal) as caught:
            sec.parse(b"SEC " + bytes(60))
        self.assertEqual(str(caught.exception), "the section container does not begin with 'SEC ' as a little-endian word")
        struct.pack_into("<I", blob, 24, len(blob) + 1)
        with self.assertRaises(Refusal) as caught:
            sec.parse(bytes(blob), "s.sec")
        self.assertEqual(str(caught.exception), "s.sec declares %d bytes for a %d-byte file" % (len(blob) + 1, len(blob)))
        struct.pack_into("<I", blob, 24, len(blob))
        struct.pack_into("<I", blob, 28 + 16 + 4, 4096)      # second section's offset breaks the chain
        with self.assertRaises(Refusal) as caught:
            sec.parse(bytes(blob), "s.sec")
        self.assertIn("starts at 4096, not where the previous ended", str(caught.exception))
        struct.pack_into("<I", blob, 28 + 16 + 4, 512)
        struct.pack_into("<I", blob, 28 + 16 + 12, 2)        # second section's name offset is mid-string
        with self.assertRaises(Refusal) as caught:
            sec.parse(bytes(blob), "s.sec")
        self.assertIn("not a string start", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
