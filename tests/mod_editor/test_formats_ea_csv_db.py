"""Tests for the EA CSV table package.  Synthetic tables only."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games._formats import ea_csv_db  # noqa: E402
from mod_editor.games.contract import Refusal  # noqa: E402


COLUMNS = ("first_name", "last_name", "jersey", "bats")
ROWS = (("0aaa0001", ("Alpha", "First", "7", "0")),
        ("0aaa0002", ("Beta", "Second", "12", "1")),
        ("0aaa0003", ("Gamma", "Third", "44", "0")))


class IndexedGrammarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = ea_csv_db.build_indexed_table(COLUMNS, ROWS)
        self.table = ea_csv_db.parse_table(self.payload, name="t.dat")

    def test_the_header_and_rows_are_read_without_the_numbers(self) -> None:
        self.assertTrue(self.table.indexed)
        self.assertEqual(self.table.columns(), list(COLUMNS))
        self.assertEqual(self.table.row_count(), 3)
        lines = self.table.data_line_numbers()
        self.assertEqual(self.table.row_id(lines[1]), "0aaa0002")
        self.assertEqual(self.table.values(lines[1]), ["Beta", "Second", "12", "1"])
        self.assertEqual(self.table.cell(lines[2], 2), "44")

    def test_an_unedited_table_renders_byte_for_byte(self) -> None:
        self.assertEqual(self.table.render(), self.payload)

    def test_a_cell_edit_changes_only_its_own_line(self) -> None:
        lines = self.table.data_line_numbers()
        self.table.set_cell(lines[1], 0, "Delta")
        out = self.table.render()
        before = self.payload.split(b"\r\n")
        after = out.split(b"\r\n")
        self.assertEqual(len(before), len(after))
        for number, (old, new) in enumerate(zip(before, after)):
            if number == lines[1]:
                self.assertIn(b",0 Delta,", new)
                self.assertTrue(new.startswith(b"0aaa0002,"))
                self.assertTrue(new.endswith(b",;"))
            else:
                self.assertEqual(old, new)

    def test_values_that_would_change_the_grammar_are_refused(self) -> None:
        lines = self.table.data_line_numbers()
        for bad, word in (("a,b", "comma"), ("a\nb", "line break"), ("☃", "Latin-1")):
            with self.assertRaises(Refusal) as caught:
                self.table.set_cell(lines[0], 0, bad)
            self.assertIn(word, str(caught.exception))
        with self.assertRaises(Refusal) as caught:
            self.table.set_cell(lines[0], 9, "x")
        self.assertIn("no column 9", str(caught.exception))
        with self.assertRaises(Refusal):
            self.table.set_cell(99, 0, "x")

    def test_summary_carries_shape_only(self) -> None:
        summary = self.table.summary()
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["columns"], 4)
        self.assertEqual(summary["terminators"], ["\r\n"])
        self.assertNotIn("Alpha", repr(summary))


class PlainGrammarTests(unittest.TestCase):
    def test_a_plain_table_is_read_edited_and_rendered_exactly(self) -> None:
        payload = ea_csv_db.build_plain_table([("Age", "Level", "Low"), ("18", "1", "100"),
                                               ("", "", ""), ("19", "2", "110")])
        table = ea_csv_db.parse_table(payload, name="p.csv")
        self.assertFalse(table.indexed)
        self.assertEqual(table.columns(), ["Age", "Level", "Low"])
        # The blank line is not a row; the two numeric lines are.
        self.assertEqual(table.row_count(), 2)
        self.assertEqual(table.render(), payload)
        table.set_cell(3, 2, "111")
        self.assertEqual(table.render(), payload.replace(b"19,2,110", b"19,2,111"))

    def test_mixed_terminators_are_kept_per_line(self) -> None:
        payload = b"a,b\r\nc,d\ne,f"
        table = ea_csv_db.parse_table(payload)
        self.assertEqual(table.render(), payload)
        table.set_cell(1, 1, "D")
        self.assertEqual(table.render(), b"a,b\r\nc,D\ne,f")

    def test_a_line_that_only_looks_indexed_is_not(self) -> None:
        payload = b"0 a,1 b\r\n"          # no trailer: plain
        self.assertFalse(ea_csv_db.parse_table(payload).indexed)
        payload = b"x,0 a,2 b,;\r\n"      # numbers out of order: plain
        self.assertFalse(ea_csv_db.parse_table(payload).indexed)


if __name__ == "__main__":
    unittest.main()
