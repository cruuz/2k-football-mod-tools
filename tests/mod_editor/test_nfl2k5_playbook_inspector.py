from __future__ import annotations

import struct
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_playbook_inspector import (
    BODY_SIZE,
    CATEGORY_BASE,
    FORMATION_AUX_BASE,
    FORMATION_BASE,
    NODE_BASE,
    PLAY_BASE,
    STRING_BASE,
    corpus_counts,
    parse_playbook_resource,
)


def _relative(body: bytearray, field: int, target: int) -> None:
    struct.pack_into("<i", body, field, target - field + 1)


def _fixture() -> bytes:
    body = bytearray(BODY_SIZE)
    body[0x0C:0x10] = b"PLAY"
    body[0x20:0x28] = b"p\0l\0b\0\0\0"
    struct.pack_into("<IIII", body, 0x34, 1, 2, 1, 4)
    for field, target in (
        (0x44, FORMATION_BASE),
        (0x48, FORMATION_AUX_BASE),
        (0x60, PLAY_BASE),
        (0x64, CATEGORY_BASE),
        (0x68, NODE_BASE),
    ):
        _relative(body, field, target)

    names: dict[str, int] = {}
    cursor = STRING_BASE
    for value in ("TEST", "I Pro", "Quick Out", "Cover 3", "Ace"):
        names[value] = cursor
        payload = value.encode("utf-16le") + b"\0\0"
        body[cursor:cursor + len(payload)] = payload
        cursor += len(payload)
    _relative(body, 0x30, names["TEST"])
    _relative(body, FORMATION_BASE, names["I Pro"])
    _relative(body, PLAY_BASE, names["Quick Out"])
    _relative(body, PLAY_BASE + 0x60, names["Cover 3"])
    _relative(body, CATEGORY_BASE, names["Ace"])

    # Offense (family 0) and defense (family 1).
    struct.pack_into("<I", body, PLAY_BASE + 4, 0)
    struct.pack_into("<I", body, PLAY_BASE + 0x60 + 4, 1 << 6)
    for play_index, start in ((0, 0), (1, 2)):
        play = PLAY_BASE + play_index * 0x60
        for slot in range(11):
            struct.pack_into("<I", body, play + 8 + slot * 8, 0x1000 + slot)
            _relative(body, play + 0x0C + slot * 8, NODE_BASE + start * 8)

    # Four nodes partition into two exact two-node chains.  Start low flag bits
    # are zero and each chain's final node has terminal bit 1 set.
    body[NODE_BASE:NODE_BASE + 32] = bytes((
        0x01, 0x00, 1, 2, 3, 4, 5, 6,
        0x04, 0x02, 7, 8, 9, 10, 11, 12,
        0x1A, 0x00, 13, 14, 15, 16, 17, 18,
        0x05, 0x02, 19, 20, 21, 22, 23, 24,
    ))

    # One formation links to both plays, then has 34 empty entries.
    for index in range(36):
        struct.pack_into("<H", body, FORMATION_AUX_BASE + index * 2, 0x01FF)
    struct.pack_into("<H", body, FORMATION_AUX_BASE, 0)
    struct.pack_into("<H", body, FORMATION_AUX_BASE + 2, (2 << 9) | 1)

    wrapper = bytearray(0x20)
    wrapper[:4] = b"PLAY"
    struct.pack_into("<I", wrapper, 4, BODY_SIZE)
    return bytes(wrapper + body)


class Nfl2k5PlaybookInspectorTests(unittest.TestCase):
    def test_structured_fixture_is_fully_partitioned(self) -> None:
        book = parse_playbook_resource(
            _fixture(), asset_id="nfl2k5.resource.test.PLAY", outer_index=307
        )
        self.assertEqual(book.book_name, "TEST")
        self.assertEqual(book.outer_index, 307)
        self.assertEqual([row.name for row in book.formations], ["I Pro"])
        self.assertEqual([row.name for row in book.plays], ["Quick Out", "Cover 3"])
        self.assertEqual([row.family_label for row in book.plays], ["Offense", "Defense"])
        self.assertEqual([row.name for row in book.categories], ["Ace"])
        self.assertEqual([(row.start_index, row.end_index) for row in book.chains],
                         [(0, 2), (2, 4)])
        self.assertEqual(book.chain(2).nodes[-1].raw_hex, "0502131415161718")
        self.assertTrue(book.chain(2).nodes[-1].ends_chain)
        self.assertEqual(
            [(row.play_index, row.group) for row in book.formations[0].play_links],
            [(0, 0), (1, 2)],
        )
        self.assertEqual(
            [row.name for row in book.plays_for_formation(0)],
            ["Quick Out", "Cover 3"],
        )
        self.assertEqual(corpus_counts((book,)), {
            "books": 1,
            "formations": 1,
            "plays": 2,
            "categories": 1,
            "chains": 2,
            "nodes": 4,
            "slot_references": 22,
        })

    def test_invalid_assignment_pointer_is_rejected(self) -> None:
        raw = bytearray(_fixture())
        body_offset = 0x20
        pointer = body_offset + PLAY_BASE + 0x0C
        struct.pack_into("<i", raw, pointer, 1)
        with self.assertRaisesRegex(ValidationError, "outside its declared node"):
            parse_playbook_resource(bytes(raw))

    def test_chain_without_terminal_marker_is_rejected(self) -> None:
        raw = bytearray(_fixture())
        raw[0x20 + NODE_BASE + 8 + 1] = 0
        with self.assertRaisesRegex(ValidationError, "terminal marker"):
            parse_playbook_resource(bytes(raw))

    def test_wrong_resource_size_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "bytes"):
            parse_playbook_resource(_fixture()[:-1])


if __name__ == "__main__":
    unittest.main()
