"""H3: retire empty personnel supply, while preserving bounded lookup safety."""
from pathlib import Path
import os
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_splb_writer as w
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_splb_formation_personnel import forged_book

INDEX = Path(os.environ.get('APF_RETAIL_0A', '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'))
IMAGE = Path(os.environ.get('APF_BOOK_FLAT_PE', '/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe'))


class LadderTests(unittest.TestCase):
    def test_every_queens_swap_retires_its_advertisement_and_receipts_it(self):
        before = forged_book(130, ((9, 0), (20, 3), (120, 6), (78, 6)))
        changes = [w.TrailerReplace(130, i, 69, 6) for i in (2, 3)]
        compiled = w.compile_book(before, changes)
        after = w.parse_book(compiled.replacement, 130)
        self.assertNotIn(6, w.book_category_rows(after.body))
        self.assertIn(8, w.book_category_rows(after.body))
        self.assertEqual(compiled.report['personnel_ladder']['messages'],
                         ["Queens retired from this book's ladder"])
        self.assertNotIn(6, w.personnel_availability(after)['normalization_restores_category_indices'])
        w.verify_book(before.body, after.body, changes)
        forged = bytearray(after.body)
        struct.pack_into('>I', forged, w.BOOK_CATEGORY_MASK_OFFSET,
                         int.from_bytes(forged[w.BOOK_CATEGORY_MASK_OFFSET:w.BOOK_CATEGORY_MASK_OFFSET+4], 'big') | (1 << 6))
        with self.assertRaises(ValidationError):
            w.verify_book(before.body, bytes(forged), changes)

    def test_remove_last_record_of_category_carries_mask_too(self):
        before = forged_book(130, ((9, 0), (20, 3), (69, 8), (120, 6)))
        change = w.MembershipChange(130, 3, 3, False)
        compiled = w.compile_book(before, [change])
        self.assertNotIn(6, w.book_category_rows(compiled.replacement))
        w.verify_book(before.body, compiled.replacement, [change])

    def test_removing_middle_record_remains_refused_because_lookup_stops(self):
        before = forged_book(130, ((9, 0), (120, 6), (20, 3), (69, 8)))
        with self.assertRaisesRegex(ValidationError, 'hidden|first empty record'):
            w.compile_book(before, [w.MembershipChange(130, 1, 1, False)])

    def test_hidden_duplicate_cannot_reintroduce_retired_category(self):
        before = forged_book(130, ((9, 0), (20, 3), (120, 6), (69, 8), (69, 6)))
        with self.assertRaisesRegex(ValidationError, 'game can restore its ladder bit'):
            w.compile_book(before, [w.TrailerReplace(130, 2, 69, 8)])

    @unittest.skipUnless(INDEX.is_file(), f'Retail APF 0A absent: {INDEX}')
    def test_retail_bulk_swap_h7a_and_native_picker(self):
        before = w.read_book(INDEX, 130)
        changes = [w.TrailerReplace(130, r.record_index, 69, 8)
                   for r in before.records if r.populated and r.category_index == 6]
        self.assertEqual(len(changes), 3)
        compiled = w.build_book_patch(INDEX, changes)
        after = w.parse_book(compiled.replacement, 130)
        self.assertNotIn(6, w.book_category_rows(after.body))
        self.assertIn("Queens retired from this book's ladder", compiled.report['personnel_ladder']['messages'])
        if not IMAGE.is_file():
            self.skipTest(f'Pinned BASE flat PE absent: {IMAGE}')
        try:
            from tools.apf_personnel_native_probe import witness
            import unicorn
        except ImportError:
            self.skipTest('Unicorn is required for bounded native PPC execution')
        from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
        proof = witness(IMAGE, read_master_play_body(INDEX), before, after)
        self.assertEqual(proof['new_null_record_paths'], 0)
        self.assertTrue(all(row['category'] != 6 for row in proof['after']))
        self.assertTrue(proof['after'][7]['records'])
        self.assertEqual(compiled.report['h7a_transport']['overlapping_matches'], 0)
        # Negative control: the beta-66 stale advertisement selects empty Queens.
        stale = bytearray(after.body)
        stale[w.BOOK_CATEGORY_MASK_OFFSET:w.BOOK_CATEGORY_MASK_OFFSET+4] = before.body[w.BOOK_CATEGORY_MASK_OFFSET:w.BOOK_CATEGORY_MASK_OFFSET+4]
        from tools.apf_personnel_native_probe import PersonnelMachine
        machine = PersonnelMachine(IMAGE, read_master_play_body(INDEX))
        bad = w.parse_book(bytes(stale), 130)
        machine.install(bad)
        self.assertEqual(machine.picker(7), 6)
        self.assertEqual(machine.reachable(bad, 6), [])


if __name__ == '__main__': unittest.main()
