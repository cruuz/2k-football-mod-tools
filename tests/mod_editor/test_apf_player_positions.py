from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from mod_editor.apf_studio import player_positions
from mod_editor.apf_studio.player_positions import (
    DEFAULT_SCHEMA_PATH,
    PlayerPositionsError,
    load_player_position_schema,
)


class PlayerPositionSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_player_position_schema()

    def test_exact_17_code_semantic_and_source_mirror_contract(self) -> None:
        self.assertEqual(
            (
                self.schema.player_count,
                self.schema.record_stride,
                self.schema.semantic_relative_offset,
                self.schema.mirror_relative_offset,
            ),
            (2_254, 0x14C, 0x34, 0x35),
        )
        self.assertEqual(
            [(row.code, row.abbreviation, row.name) for row in self.schema.positions],
            [
                (0, "QB", "Quarterback"),
                (1, "K", "Kicker"),
                (2, "P", "Punter"),
                (3, "WR", "Wide Receiver"),
                (4, "CB", "Cornerback"),
                (5, "FS", "Free Safety"),
                (6, "SS", "Strong Safety"),
                (7, "HB", "Halfback"),
                (8, "FB", "Fullback"),
                (9, "TE", "Tight End"),
                (10, "OLB", "Outside Linebacker"),
                (11, "ILB", "Inside Linebacker"),
                (12, "C", "Center"),
                (13, "G", "Guard"),
                (14, "T", "Tackle"),
                (15, "DT", "Defensive Tackle"),
                (16, "DE", "Defensive End"),
            ],
        )
        self.assertEqual(
            self.schema.runtime_status,
            "offline_writer_proved_runtime_spot_check_pending",
        )

    def test_record_decode_requires_exact_code_and_equal_mirror(self) -> None:
        record = bytearray(self.schema.record_stride)
        record[0x34] = record[0x35] = 16
        self.assertEqual(self.schema.decode_record(record).abbreviation, "DE")
        record[0x35] = 15
        with self.assertRaisesRegex(PlayerPositionsError, "mirror"):
            self.schema.decode_record(record)
        record[0x34] = record[0x35] = 17
        with self.assertRaisesRegex(PlayerPositionsError, "0 to 16"):
            self.schema.decode_record(record)
        with self.assertRaisesRegex(PlayerPositionsError, "expected exactly 332"):
            self.schema.decode_record(bytes(331))

    def test_bool_float_and_out_of_range_codes_fail_closed(self) -> None:
        for value in (-1, 17, True, 3.0, "3"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(PlayerPositionsError, "integer from 0 to 16"):
                    self.schema.position_for(value)

    def test_loader_rejects_relabeling_or_offset_widening(self) -> None:
        original = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "positions.json"
            relabeled = json.loads(json.dumps(original))
            relabeled["positions"][7]["abbreviation"] = "RB"
            path.write_text(json.dumps(relabeled), encoding="utf-8")
            with self.assertRaisesRegex(PlayerPositionsError, "dictionary changed"):
                load_player_position_schema(path)
            widened = json.loads(json.dumps(original))
            widened["source_contract"]["mirror_relative_offset"] = 0x36
            path.write_text(json.dumps(widened), encoding="utf-8")
            with self.assertRaisesRegex(PlayerPositionsError, "record contract"):
                load_player_position_schema(path)

    def test_packaged_dictionary_contains_only_retail_free_metadata(self) -> None:
        document = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIs(document["public_distribution"]["contains_retail_bytes"], False)
        self.assertIs(document["public_distribution"]["contains_player_values"], False)
        self.assertFalse(hasattr(player_positions, "replace_player_position"))


if __name__ == "__main__":
    unittest.main()
