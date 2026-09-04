"""The 7-on-7 book composes with the one-pool position recode, which the Build tab runs first.

recode(7on7(retail)) must equal 7on7(recode(retail)) byte for byte, and the writer must recognise the
recoded practice book as a source it can build on. Uses the loose retail extraction (read-only)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mod_editor.core import nfl2k5_seven_on_seven_book as book  # noqa: E402

LOOSE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "vc_53450030"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless((LOOSE / "0").is_file(), "retail extraction not present")
class RecodeCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import nfl2k5_playbook_position_recode as recode
        cls.recode = recode
        with recode.OuterImage(LOOSE) as archive:
            (cls.practice,) = recode.load_books(archive, ["PRACTICE"])
            cls.entry = archive.entries[book.PRACTICE_OUTER_INDEX]
            cls.retail = archive.read(cls.entry.virtual_offset, cls.entry.size)
        cls.table_at = recode.RESOURCE_HEADER_SIZE + recode.CATEGORY_BASE

    def _splice(self, resource: bytes, table: bytes) -> bytes:
        return resource[: self.table_at] + table + resource[self.table_at + len(table):]

    def _recoded(self, resource: bytes) -> bytes:
        parsed = self.recode.parse_book("PRACTICE", self.entry, resource)
        table, _changes = self.recode.recoded_table(parsed)
        return self._splice(resource, table)

    def test_the_retail_and_recoded_pins_match_the_tools(self) -> None:
        self.assertEqual(_sha(self.retail), book.RETAIL_RESOURCE_SHA256)
        recoded = self._recoded(self.retail)
        self.assertEqual(_sha(recoded), book.RECODED_RESOURCE_SHA256)
        self.assertEqual(book.resource_status(self.retail), "retail")
        self.assertEqual(book.resource_status(recoded), "recoded")

    def test_recode_then_seven_on_seven_equals_seven_on_seven_then_recode(self) -> None:
        recoded_first, _report = book.build_replacement(self._recoded(self.retail))
        seven_first, _report = book.build_replacement(self.retail)
        self.assertNotEqual(recoded_first, seven_first, "the recode must change the personnel groups")
        self.assertEqual(recoded_first, self._recoded(seven_first))
        self.assertEqual(book.resource_status(recoded_first), "applied")
        book.verify(recoded_first)

    def test_the_writer_refuses_any_other_source(self) -> None:
        tampered = bytearray(self.retail)
        tampered[self.table_at + 5] ^= 0x01
        self.assertEqual(book.resource_status(bytes(tampered)), "foreign")
        with self.assertRaises(book.SevenOnSevenBookError):
            book.build_replacement(bytes(tampered))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless((LOOSE / "0").is_file(), "retail extraction not present")
class MenuLinkShapeTests(unittest.TestCase):
    """Formation menu links must look exactly like retail's: bit 15 set, group in bits 9-10, index in 0-8."""

    def test_every_new_link_word_has_the_retail_shape(self) -> None:
        import struct
        import nfl2k5_playbook_position_recode as recode
        with recode.OuterImage(LOOSE) as archive:
            entry = archive.entries[book.PRACTICE_OUTER_INDEX]
            retail = archive.read(entry.virtual_offset, entry.size)
        built, _report = book.build_replacement(retail)
        body = built[book.RESOURCE_HEADER_SIZE:]
        seen = 0
        for index in range(23, 28):
            aux = book.FORMATION_AUX_BASE + index * book.FORMATION_AUX_SIZE
            for word in struct.unpack_from(f"<{book.FORMATION_PLAY_LINKS}H", body, aux):
                if word == book.EMPTY_LINK:
                    continue
                seen += 1
                self.assertTrue(word & book.LINK_PRESENT, hex(word))
                self.assertEqual((word >> 9) & 0x3F, book.LINK_GROUP, hex(word))
                self.assertGreaterEqual(word & 0x1FF, 27, hex(word))
                self.assertLess(word & 0x1FF, 42, hex(word))
        self.assertEqual(seen, 3 * 3 + 2 * 6)

    def test_retail_links_all_carry_bit_15(self) -> None:
        import struct
        import nfl2k5_playbook_position_recode as recode
        with recode.OuterImage(LOOSE) as archive:
            entry = archive.entries[book.PRACTICE_OUTER_INDEX]
            body = archive.read(entry.virtual_offset, entry.size)[book.RESOURCE_HEADER_SIZE:]
        words = [w for f in range(23) for w in struct.unpack_from(f"<{book.FORMATION_PLAY_LINKS}H", body, book.FORMATION_AUX_BASE + f * book.FORMATION_AUX_SIZE)]
        real = [w for w in words if w not in (0, book.EMPTY_LINK)]
        self.assertTrue(real)
        self.assertTrue(all(w & book.LINK_PRESENT for w in real))
