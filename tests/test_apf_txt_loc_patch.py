from __future__ import annotations

import struct
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import apf_txt_loc  # noqa: E402
import apf_txt_loc_patch as writer  # noqa: E402
import string_table_inventory  # noqa: E402


def _sample_table() -> dict[str, object]:
    # One ordinary record points to HOME. INVALID TEXT remains the required,
    # unreferenced fallback allocation at pool index zero.
    body = bytearray(struct.pack(">III", apf_txt_loc.EXPECTED_LANGUAGE_ID, 1, 5))
    body.extend(struct.pack(">II", 1, 31))
    body.extend("INVALID TEXT".encode("utf-16be") + b"\0\0")
    body.extend("HOME".encode("utf-16be") + b"\0\0")
    return apf_txt_loc.parse_body(
        bytes(body),
        outer_index=1127,
        inner_index=0,
        inner_name="English",
        inner_file_id=0xD34DB33F,
    )


def _sample_strg() -> string_table_inventory.ParsedTable:
    count = 4
    pool_offset = 8 + count * string_table_inventory.RECORD_SIZE
    strings = ("HOME", "", "PLAY")
    offsets: list[int] = []
    cursor = pool_offset
    for value in strings:
        offsets.append(cursor)
        cursor += len(value.encode("utf-16be")) + 2
    body = bytearray(struct.pack(">II", count, string_table_inventory.APF_VERSION))
    for index, pool_index in enumerate((0, 1, 2, 0)):
        record_offset = 8 + index * string_table_inventory.RECORD_SIZE
        relative = offsets[pool_index] - (record_offset + 7)
        body.extend(struct.pack(">IIi", index + 1, 0x100 + index, relative))
    for value in strings:
        body.extend(value.encode("utf-16be") + b"\0\0")
    body.extend(b"\0" * 8)
    return string_table_inventory.parse_apf_body(
        bytes(body),
        outer_index=810,
        inner_index=87,
        name="strings",
    )


class ApfLocalizationPatchTests(unittest.TestCase):
    def test_complete_archive_text_bank_pins_include_txt_and_strg(self) -> None:
        self.assertEqual(
            writer.TABLE_TARGETS,
            {
                185: (20, "artist_bio_english"),
                526: (0, "credits_English"),
                810: (87, "strings"),
                1127: (0, "English"),
            },
        )

    def test_stable_asset_id_parser(self) -> None:
        self.assertEqual(
            writer.parse_asset_id("apf:text-pool:1127:0:10"),
            (1127, 0, 10),
        )
        with self.assertRaisesRegex(writer.TextPatchError, "Unknown"):
            writer.parse_asset_id("apf:text:1127:0:10")
        with self.assertRaisesRegex(writer.TextPatchError, "Malformed"):
            writer.parse_asset_id("apf:text-pool:wat:0:10")

    def test_allocation_inventory_marks_fallback_read_only(self) -> None:
        rows = writer._allocations_for_table(_sample_table())
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0].editable)
        self.assertEqual(rows[0].maximum_utf16_units, 12)
        self.assertTrue(rows[1].editable)
        self.assertEqual(rows[1].maximum_utf16_units, 4)
        self.assertEqual(rows[1].reference_count, 1)

    def test_shorter_edit_rebuilds_pointers_and_round_trips(self) -> None:
        original = _sample_table()
        body, receipt = writer._edited_body(original, {1: "MOD"})
        self.assertEqual(len(body), int(original["body_size"]) - 2)
        rebuilt = apf_txt_loc.parse_body(
            body,
            outer_index=1127,
            inner_index=0,
            inner_name="English",
            inner_file_id=0xD34DB33F,
        )
        self.assertEqual(rebuilt["records"][0]["text"], "MOD")
        self.assertEqual(rebuilt["pool"][1]["text"], "MOD")
        self.assertEqual(apf_txt_loc.rebuild_table(rebuilt), body)
        self.assertEqual(receipt[0]["asset_id"], "apf:text-pool:1127:0:1")
        self.assertNotIn("MOD", str(receipt))

    def test_exact_fit_and_surrogate_pair_limits_use_utf16_units(self) -> None:
        table = _sample_table()
        body, _receipt = writer._edited_body(table, {1: "ABCD"})
        self.assertEqual(len(body), int(table["body_size"]))
        with self.assertRaisesRegex(writer.TextPatchError, "at most 4"):
            writer._edited_body(table, {1: "ABCDE"})
        # One non-BMP glyph occupies two UTF-16 units.
        writer._edited_body(table, {1: "A\U0001F3C8B"})
        with self.assertRaisesRegex(writer.TextPatchError, "needs 5"):
            writer._edited_body(table, {1: "A\U0001F3C8BC"})

    def test_special_fallback_and_nul_are_rejected(self) -> None:
        table = _sample_table()
        with self.assertRaisesRegex(writer.TextPatchError, "fallback sentinel"):
            writer._edited_body(table, {0: "BROKEN"})
        with self.assertRaisesRegex(writer.TextPatchError, "NUL"):
            writer._edited_body(table, {1: "A\0B"})

    def test_recipe_rows_are_hashes_only(self) -> None:
        _body, receipt = writer._edited_body(_sample_table(), {1: "MOD"})
        row = receipt[0]
        self.assertEqual(
            set(row),
            {
                "asset_id",
                "pool_index",
                "reference_count",
                "allocation_bytes",
                "maximum_utf16_units",
                "replacement_utf16_units",
                "original_text_sha256",
                "replacement_text_sha256",
            },
        )
        self.assertNotIn("original_text", row)
        self.assertNotIn("replacement_text", row)

    def test_strg_inventory_preserves_alias_and_zero_capacity_boundary(self) -> None:
        rows = writer._allocations_for_strg(_sample_strg())
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0].maximum_utf16_units, 4)
        self.assertEqual(rows[0].reference_count, 2)
        self.assertTrue(rows[0].editable)
        self.assertEqual(rows[1].maximum_utf16_units, 0)
        self.assertEqual(rows[1].reference_count, 1)
        self.assertFalse(rows[1].editable)
        self.assertIn("Zero-capacity", rows[1].note)

    def test_strg_shorter_edit_rebuilds_pointers_at_exact_body_size(self) -> None:
        original = _sample_strg()
        body, receipt = writer._edited_strg_body(original, {0: "MOD", 2: "PASS"})
        self.assertEqual(len(body), len(original.body))
        rebuilt = string_table_inventory.parse_apf_body(
            body,
            outer_index=810,
            inner_index=87,
            name="strings",
        )
        self.assertEqual(rebuilt.pool[0].text, "MOD")
        self.assertEqual(rebuilt.pool[2].text, "PASS")
        self.assertEqual(rebuilt.records[0].text, "MOD")
        self.assertEqual(rebuilt.records[3].text, "MOD")
        self.assertEqual(string_table_inventory.rebuild_table(rebuilt), body)
        self.assertEqual(original.pool[0].text, "HOME")
        self.assertEqual(receipt[0]["asset_id"], "apf:text-pool:810:87:0")
        self.assertNotIn("MOD", str(receipt))

    def test_strg_zero_capacity_and_per_allocation_limit_fail_closed(self) -> None:
        table = _sample_strg()
        with self.assertRaisesRegex(writer.TextPatchError, "Zero-capacity"):
            writer._edited_strg_body(table, {1: "X"})
        with self.assertRaisesRegex(writer.TextPatchError, "at most 4"):
            writer._edited_strg_body(table, {0: "TOO LONG"})


if __name__ == "__main__":
    unittest.main()
