#!/usr/bin/env python3
"""Unit coverage for the bounded NFL Main Menu literal writer."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_main_menu_label_patch as patch  # noqa: E402


class MainMenuLabelPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source_path = ROOT / "extracted/ESPN NFL 2K5 (USA)/default.xbe"
        cls.source = cls.source_path.read_bytes()

    def test_pinned_source_and_all_seven_maximum_slots(self) -> None:
        edits = {
            "quick_game": "ABCDEFGHIJK",
            "game_modes": "LMNOPQRSTUV",
            "the_crib": "ABCDEFGHIJKLM",
            "features": "ABCDEFGHI",
            "options": "ABCDEFG",
            "xbox_live": "ABCDEFGHI",
            "extras": "ABCDEFG",
        }
        output, report = patch.build_patch(self.source, edits)
        self.assertEqual(len(output), len(self.source))
        self.assertEqual([row["selector"] for row in report["rows"]],
                         list(edits))
        self.assertTrue(all(row["changed"] for row in report["rows"]))
        self.assertTrue(report["claims"]["same_row_count_and_pointers"])
        self.assertFalse(report["claims"]["retail_rsa_signature_valid_after_patch"])
        self.assertFalse(report["claims"]["runtime_visible_pixels_proved"])
        for slot in patch.SLOTS:
            expected = edits[slot.selector].encode("utf-16le") + b"\0\0"
            actual = output[slot.file_offset:slot.file_offset + slot.size]
            self.assertEqual(actual[:len(expected)], expected)
            self.assertFalse(any(actual[len(expected):]))
            self.assertEqual(
                output[slot.pointer_field_file_offset:
                       slot.pointer_field_file_offset + 4],
                self.source[slot.pointer_field_file_offset:
                            slot.pointer_field_file_offset + 4],
            )
        parsed = patch.parse_sections(output)
        for section in parsed:
            body = output[section.raw_offset:section.raw_offset + section.raw_size]
            self.assertEqual(section.stored_digest, patch.xbe_sha1(body))

    def test_partial_edit_preserves_other_slots_and_route(self) -> None:
        output, report = patch.build_patch(self.source, {"quick_game": "Play Now"})
        for slot in patch.SLOTS:
            before = self.source[slot.file_offset:slot.file_offset + slot.size]
            after = output[slot.file_offset:slot.file_offset + slot.size]
            self.assertEqual(before == after, slot.selector != "quick_game")
        row_start = patch.SLOTS[0].pointer_field_file_offset - 4
        row_end = patch.SLOTS[-1].pointer_field_file_offset - 4 + 0x34 + 4
        self.assertEqual(output[row_start:row_end], self.source[row_start:row_end])
        self.assertEqual(
            output[patch.RSA_SIGNATURE_OFFSET:
                   patch.RSA_SIGNATURE_OFFSET + patch.RSA_SIGNATURE_SIZE],
            self.source[patch.RSA_SIGNATURE_OFFSET:
                        patch.RSA_SIGNATURE_OFFSET + patch.RSA_SIGNATURE_SIZE],
        )
        self.assertEqual(
            [row["selector"] for row in report["rows"] if row["changed"]],
            ["quick_game"],
        )

    def _load(self, raw: str) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "edits.json"
            path.write_text(raw, encoding="utf-8")
            return patch.load_edits(path)

    def test_edit_document_rejects_unsafe_shapes(self) -> None:
        bad = [
            {"schema": patch.EDITS_SCHEMA, "labels": {"unknown": "Text"}},
            {"schema": patch.EDITS_SCHEMA, "labels": {"options": "Too Long"}},
            {"schema": patch.EDITS_SCHEMA, "labels": {"extras": "Café"}},
            {"schema": patch.EDITS_SCHEMA, "labels": {"extras": ""}},
            {"schema": patch.EDITS_SCHEMA, "labels": {"extras": "Extras"}},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(patch.LabelPatchError):
                self._load(json.dumps(value))
        with self.assertRaises(patch.LabelPatchError):
            self._load(
                '{"schema":"nfl2k5_main_menu_label_edits/v1",'
                '"labels":{"extras":"Bonus","extras":"Again"}}'
            )


if __name__ == "__main__":
    unittest.main()
