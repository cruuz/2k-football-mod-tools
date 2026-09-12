"""Retail census and every accepted formation move use destination personnel."""
from pathlib import Path
import os
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_splb_writer as w, apf2k8_play_codec as codec
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_splb_formation_personnel import forged_book

INDEX = Path(os.environ.get('APF_RETAIL_0A', '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'))


class FormationMoveTests(unittest.TestCase):
    def test_stale_primary_and_secondary_are_normalized_in_recipe_and_receipt(self):
        book = forged_book(130, ((9, 0), (21, 0)))
        change = w.TrailerReplace(130, 0, 69, 0)
        compiled = w.compile_book(book, [change])
        record = w.parse_book(compiled.replacement, 130).records[0]
        self.assertEqual((record.formation_index, record.category_index), (69, 8))
        self.assertEqual(int.from_bytes(record.trailer[4:], 'big'), 1 << 8)
        receipt = compiled.report['records_trailer_replaced'][0]
        self.assertEqual((receipt['category_requested'], receipt['category_after']), (0, 8))
        self.assertEqual((receipt['word_b_before'], receipt['word_b_after']), (1, 256))
        w.verify_book(book.body, compiled.replacement, [change])

    def test_unsafe_retirement_explains_the_bounded_fallback(self):
        book = forged_book(130, ((9, 0),))
        with self.assertRaisesRegex(ValidationError, 'bounded ladder would have no formation'):
            w.compile_book(book, [w.TrailerReplace(130, 0, 69, 0)])

    @unittest.skipUnless(INDEX.is_file(), f'Retail APF 0A absent: {INDEX}')
    def test_retail_census_and_moves_across_all_fifteen_books(self):
        master = codec.Book.from_bytes(read_master_play_body(INDEX))
        table = w.retail_formation_packages(INDEX)
        self.assertEqual({f for f, cats in table.items() if len(cats) > 1}, {72, 78, 120})
        for f, formation in enumerate(master.formations):
            self.assertEqual(w.FORMATION_PERSONNEL_CATEGORIES[f],
                             tuple(c for c, _ in table[f]) if f in table else (formation.category_index,))
        moved = refused = records = 0
        for outer in w.STOCK_BOOKS:
            book = w.read_book(INDEX, outer)
            for original in book.records:
                if not original.populated: continue
                records += 1
                destination = 69 if original.formation_index != 69 else 9
                change = w.TrailerReplace(outer, original.record_index, destination, original.category_index)
                try: compiled = w.compile_book(book, [change])
                except ValidationError as exc:
                    self.assertIn('bounded ladder would have no formation', str(exc)); refused += 1; continue
                after = w.parse_book(compiled.replacement, outer)
                for record in after.records:
                    if record.populated:
                        self.assertIn(record.category_index, w.FORMATION_PERSONNEL_CATEGORIES[record.formation_index])
                row = after.records[original.record_index]
                self.assertEqual(int.from_bytes(row.trailer[4:], 'big'), 1 << row.category_index)
                moved += 1
        self.assertEqual(records, 209)
        self.assertGreater(moved, 100)
        self.assertGreater(refused, 0)


if __name__ == '__main__': unittest.main()
