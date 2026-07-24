from __future__ import annotations

import csv
import json
from pathlib import Path
import stat
import tempfile
import unittest

from mod_editor.core import platform_compat
from mod_editor.apf_studio.backend import ensure_tools_importable
from mod_editor.apf_studio import player_ratings
from mod_editor.apf_studio.player_ratings import (
    DEFAULT_SCHEMA_PATH,
    PlayerRatingsError,
    load_player_rating_schema,
)
from mod_editor.apf_studio.inspectors import (
    InspectorError,
    PagedModel,
    _row,
    export_player_rating_sheet,
)


ensure_tools_importable()
import apf_roster  # type: ignore  # noqa: E402


class PlayerRatingSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_player_rating_schema()

    def test_exact_28_field_contract_and_excluded_neighbors(self) -> None:
        self.assertEqual(len(self.schema.fields), 28)
        self.assertEqual(sum(field.named for field in self.schema.fields), 27)
        self.assertEqual(
            (self.schema.native_minimum, self.schema.native_maximum), (0, 100)
        )
        self.assertEqual(
            (
                self.schema.stock_observed_minimum,
                self.schema.stock_observed_maximum,
            ),
            (0, 99),
        )
        self.assertEqual(
            [field.display_order for field in self.schema.fields], list(range(28))
        )
        self.assertEqual(
            {field.formula_modifier_index for field in self.schema.fields},
            set(range(28)),
        )
        unknown = next(
            field
            for field in self.schema.fields
            if field.field_id == "unknown_rating_24"
        )
        self.assertEqual(
            (unknown.label, unknown.relative_offset_hex, unknown.label_status),
            ("Unknown Rating 24", "0xD4", "neutral_unresolved"),
        )
        self.assertEqual(
            [item.relative_offset_hex for item in self.schema.excluded_neighbor_bytes],
            ["0xBD", "0xC5", "0xD2", "0xD9"],
        )
        self.assertEqual(
            self.schema.excluded_neighbor_bytes[-1].status,
            "height_in_inches_consumer_proved",
        )
        self.assertEqual(
            [item.status for item in self.schema.excluded_neighbor_bytes[:3]],
            ["unknown_unassigned"] * 3,
        )

    def test_record_decode_preserves_zero_99_and_native_100(self) -> None:
        record = bytearray(self.schema.record_stride)
        offsets = {field.field_id: field.relative_offset for field in self.schema.fields}
        record[offsets["speed"]] = 0
        record[offsets["catch"]] = 99
        record[offsets["unknown_rating_24"]] = 100
        values = self.schema.decode_record(record)
        self.assertEqual(values["speed"], 0)
        self.assertEqual(values["catch"], 99)
        self.assertEqual(values["unknown_rating_24"], 100)
        rows = self.schema.field_rows(values)
        self.assertEqual(len(rows), 28)
        self.assertEqual(rows[17]["label"], "Catch")
        self.assertEqual(rows[17]["value"], 99)
        self.assertEqual(rows[25]["relative_offset_hex"], "0xD4")

    def test_record_decode_rejects_101_and_wrong_length(self) -> None:
        with self.assertRaisesRegex(PlayerRatingsError, "expected exactly 332"):
            self.schema.decode_record(bytes(331))
        record = bytearray(self.schema.record_stride)
        record[self.schema.fields[0].relative_offset] = 101
        with self.assertRaisesRegex(PlayerRatingsError, "exceed the native 0..100"):
            self.schema.decode_record(record)

    def _complete_rating_model(self, count: int = 2_254) -> PagedModel:
        values = {
            field.field_id: (99 if field.field_id == "speed" else 50)
            for field in self.schema.fields
        }
        values["unknown_rating_24"] = 100
        ratings = self.schema.field_rows(values)
        return PagedModel(
            tuple(
                _row(
                    f"apf:roster:player:{index}",
                    "player",
                    f"PLAYER {index}",
                    f"#{index:04d} · QB",
                    {
                        "player_index": index,
                        "first_name": "PLAYER",
                        "last_name": str(index),
                        "position_code": 0,
                        "position_abbreviation": "QB",
                        "position_name": "Quarterback",
                        "team_names": ("Americans",) if index < 42 else (),
                        "base_ratings": ratings,
                    },
                )
                for index in range(count)
            ),
            (),
        )

    def test_private_complete_rating_sheet_is_wide_atomic_and_exact(self) -> None:
        model = self._complete_rating_model()
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "ratings.csv"
            result = export_player_rating_sheet(
                model, destination, source_sha256="a" * 64
            )
            self.assertEqual(result, destination)
            # POSIX privacy is the mode bits and stays exactly 0o600 here.
            # Windows implements none of them, so the same private sheet reports
            # 0o666 and its confidentiality comes from the per-user profile
            # root's inherited ACL instead (platform_compat.privacy_guarantee).
            expected_mode = 0o666 if platform_compat.IS_WINDOWS else 0o600
            self.assertEqual(platform_compat.private_file_mode(), expected_mode)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), expected_mode)
            with destination.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2_254)
            self.assertEqual(
                rows[0]["schema"], "apf2k8_private_player_rating_sheet/v2"
            )
            self.assertEqual(rows[0]["source_sha256"], "a" * 64)
            self.assertEqual(rows[0]["player_index"], "0")
            self.assertEqual(rows[-1]["player_index"], "2253")
            self.assertEqual(rows[0]["team_names"], "'Americans")
            self.assertEqual(rows[0]["native_rating_maximum"], "100")
            self.assertEqual(rows[0]["stock_observed_maximum"], "99")
            self.assertEqual(rows[0]["rating.speed"], "99")
            self.assertEqual(rows[0]["rating.unknown_rating_24"], "100")
            self.assertEqual(
                len([name for name in rows[0] if name.startswith("rating.")]),
                28,
            )
            with self.assertRaisesRegex(InspectorError, "already exists"):
                export_player_rating_sheet(
                    model, destination, source_sha256="a" * 64
                )

    def test_private_rating_sheet_refuses_incomplete_inventory_without_output(self) -> None:
        model = self._complete_rating_model(2_253)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "ratings.csv"
            with self.assertRaisesRegex(InspectorError, "2,253 players"):
                export_player_rating_sheet(
                    model, destination, source_sha256="a" * 64
                )
            self.assertFalse(destination.exists())

    def test_loader_rejects_relabeling_and_expansion(self) -> None:
        original = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ratings.json"
            relabeled = json.loads(json.dumps(original))
            relabeled["fields"][0]["label"] = "Velocity"
            path.write_text(json.dumps(relabeled), encoding="utf-8")
            with self.assertRaisesRegex(PlayerRatingsError, "dictionary changed"):
                load_player_rating_schema(path)

            expanded = json.loads(json.dumps(original))
            expanded["fields"].append(dict(expanded["fields"][0]))
            expanded["field_count"] = 29
            path.write_text(json.dumps(expanded), encoding="utf-8")
            with self.assertRaisesRegex(PlayerRatingsError, "dictionary changed"):
                load_player_rating_schema(path)

    def test_public_dictionary_is_metadata_only_and_module_has_no_writer(self) -> None:
        document = json.loads(DEFAULT_SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIs(document["public_distribution"]["contains_retail_bytes"], False)
        self.assertIs(document["public_distribution"]["contains_player_values"], False)
        self.assertNotIn("payload", document["public_distribution"])
        for name in (
            "write_player_rating",
            "replace_player_rating",
            "patch_player_rating",
        ):
            self.assertFalse(hasattr(player_ratings, name))

    def test_player_tsv_exports_every_exact_rating_column(self) -> None:
        values = {field.field_id: index for index, field in enumerate(self.schema.fields)}
        player = {
            "player_index": 7,
            "record_offset": "0x000714",
            "first_name": "Fixture",
            "last_name": "Player",
            "position_code": 0,
            "position_abbreviation": "QB",
            "position_name": "Quarterback",
            "base_ratings": values,
            "hall_of_fame_induction_year_at_0x112": 0,
            "championship_count_at_0x114": 0,
            "championship_game_appearance_count_at_0x115": 0,
            "all_pro_game_count_at_0x116": 0,
            "strings": {
                label: ""
                for _offset, label in apf_roster.PLAYER_STRING_FIELDS.items()
                if label not in ("first_name", "last_name")
            },
            "team_memberships": [],
            "raw_record_sha256": "fixture",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "players.tsv"
            apf_roster.write_players_tsv(path, [player])
            with path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rating_speed"], "0")
        self.assertEqual(rows[0]["rating_catch"], "17")
        self.assertEqual(rows[0]["rating_unknown_rating_24"], "25")
        self.assertEqual(rows[0]["rating_scramble"], "27")


if __name__ == "__main__":
    unittest.main()
