"""Tests for the Midway ``.dbs`` / ``.dbd`` reader.  Synthetic pairs only."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import midway_db as db  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


def _packed(bits: int, shift: int) -> int:
    return bits | (shift << 8)


SCHEMA_TABLES = [
    ("T", "version", [("I", "version", 0)]),
    ("T", "people", [("b", "id", 0), ("s", "first", 8), ("S", "last", 12), ("w", "jersey", 0),
                     ("i", "playid", _packed(16, 0)), ("i", "form_type", _packed(15, 16)), ("i", "sprite", _packed(1, 31)),
                     ("f", "weight", 0), ("r", "city", 3), ("q", "note", 3),
                     ("b", "low", _packed(7, 0)), ("b", "flag", _packed(1, 7))]),
    ("T", "unused", [("w", "a", 0)]),
    ("t", "strings", [("s", "string", 50)]),
]


class SchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = db.parse_schema(db.build_schema("people_db", SCHEMA_TABLES))

    def test_tables_fields_widths_and_offsets(self) -> None:
        s = self.schema
        self.assertEqual(s.database, "people_db")
        self.assertEqual([t.name for t in s.tables], ["version", "people", "unused", "strings"])
        people = s.table("people")
        self.assertEqual(people.row_width, 1 + 8 + 12 + 2 + 4 + 4 + 4 + 2 + 1)
        self.assertEqual(people.offsets(), [0, 1, 9, 21, 23, 23, 23, 27, 31, 35, 37, 37])
        self.assertTrue(s.table("strings").is_pool)
        self.assertEqual(s.index_of("strings"), 3)
        self.assertTrue(people.fields[2].is_key)
        self.assertEqual((people.fields[5].bits, people.fields[5].shift), (15, 16))

    def test_an_unknown_field_type_is_refused_by_name(self) -> None:
        with self.assertRaises(Refusal) as caught:
            db.parse_schema(db.build_schema("x", [("T", "t", [("z", "odd", 0)])]))
        self.assertEqual(str(caught.exception), "field odd has type 'z', which this reader does not know")
        with self.assertRaises(Refusal):
            db.parse_schema(db.build_schema("x", [("t", "pool", [("i", "notastring", 0)])]))


class DataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = db.parse_schema(db.build_schema("people_db", SCHEMA_TABLES))
        pool, offsets = db.build_pool(["Springfield", "left-handed"])
        people = self.schema.table("people")
        rows = [db.pack_row(people, {"id": 1, "first": "Ann", "last": "Example", "jersey": 12, "playid": 0x1F2, "form_type": 0x4F,
                                     "sprite": 1, "weight": 210.5, "city": offsets["Springfield"], "note": offsets["left-handed"],
                                     "low": 77, "flag": 1}),
                db.pack_row(people, {"id": 2, "first": "Bob", "last": "Sample", "jersey": 7, "playid": 500, "form_type": 3,
                                     "sprite": 0, "weight": 190.0, "city": 0, "note": 0, "low": 5, "flag": 0})]
        self.data = db.build_data("people_db", [("version", struct.pack("<I", 1)), ("people", b"".join(rows)),
                                                ("unused", b""), ("strings", pool)])
        self.database = db.parse_data(self.data, self.schema)

    def test_the_walk_counts_rows_and_reads_the_trailer(self) -> None:
        d = self.database
        self.assertEqual(d.name, "people_db")
        self.assertEqual([t.name for t in d.tables], ["version", "people", "unused", "strings"])
        self.assertEqual(d.table("people").row_count, 2)
        self.assertEqual(d.table("unused").row_count, 0)
        self.assertEqual(d.table("version").row_count, 1)
        self.assertEqual(d.trailer, 0)
        self.assertEqual(d.table("strings").strings(), ["", "Springfield", "left-handed"])
        self.assertEqual(db.database_name(self.data), "people_db")

    def test_rows_decode_bit_fields_strings_floats_and_references(self) -> None:
        row = self.database.row("people", 0)
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["first"], "Ann")
        self.assertEqual(row["last"], "Example")
        self.assertEqual(row["jersey"], 12)
        self.assertEqual((row["playid"], row["form_type"], row["sprite"]), (0x1F2, 0x4F, 1))
        self.assertAlmostEqual(row["weight"], 210.5)
        self.assertEqual(row["city"], "Springfield")
        self.assertEqual(row["note"], "left-handed")
        self.assertEqual((row["low"], row["flag"]), (77, 1))
        raw = self.database.row("people", 1, resolve=False)
        self.assertEqual((raw["city"], raw["note"], raw["sprite"], raw["flag"]), (0, 0, 0, 0))
        self.assertEqual(len(list(self.database.rows("people"))), 2)
        self.assertEqual(self.database.check_references(), {"fields": 2, "values": 4, "on_string_start": 4, "param_not_a_pool": 0})

    def test_a_data_file_may_omit_trailing_tables(self) -> None:
        short = db.build_data("people_db", [("version", struct.pack("<I", 1))])
        d = db.parse_data(short, self.schema)
        self.assertEqual([t.name for t in d.tables], ["version"])
        self.assertFalse(d.has_table("people"))

    def test_refusals_name_the_condition(self) -> None:
        with self.assertRaises(Refusal) as caught:
            db.parse_data(db.build_data("other_db", [("version", struct.pack("<I", 1))]), self.schema, "x.dbd")
        self.assertEqual(str(caught.exception), "x.dbd belongs to database other_db; the schema is for people_db")
        with self.assertRaises(Refusal) as caught:
            db.parse_data(db.build_data("people_db", [("ghost", b"")]), self.schema, "x.dbd")
        self.assertEqual(str(caught.exception), "x.dbd: table ghost is not in the schema for people_db")
        with self.assertRaises(Refusal) as caught:
            db.parse_data(db.build_data("people_db", [("people", bytes(39))]), self.schema, "x.dbd")
        self.assertEqual(str(caught.exception), "x.dbd: table people holds 39 bytes, not a multiple of its 38-byte row")
        with self.assertRaises(Refusal) as caught:
            db.parse_data(db.build_data("people_db", [("strings", b"abc")]), self.schema, "x.dbd")
        self.assertEqual(str(caught.exception), "x.dbd: pool strings does not end with a NUL")
        with self.assertRaises(Refusal) as caught:
            db.parse_data(self.data[:-1], self.schema, "x.dbd")
        self.assertIn("where the 4-byte trailer belongs", str(caught.exception))
        with self.assertRaises(Refusal) as caught:
            self.database.table("strings").string_at(3)
        self.assertEqual(str(caught.exception), "offset 3 is not a string start in pool strings")
        with self.assertRaises(Refusal):
            self.database.row("people", 2)
        with self.assertRaises(Refusal):
            self.database.row("strings", 0)


if __name__ == "__main__":
    unittest.main()
