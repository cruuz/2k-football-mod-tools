"""USER/global names, side-safe clones and actual Fine-tune round trips."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio import book_content as content
from mod_editor.apf_studio.book_identity_qt import BookContentDialog, BookIdentityPanel
from mod_editor.apf_studio.playbook_playcall_qt import ApfPlaycallPanel
from mod_editor.core import apf2k8_book_clone as clone, apf2k8_book_identity as identity
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_book_unlock import archive_fixture
from tests.mod_editor.test_apf_b661_book_content import inventory, runner


class BookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_fifteen_lists_and_user_fine_tune_reparse_after_archive_shift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = archive_fixture(root / 'source')
            with patch.object(content, 'master_inventory', side_effect=inventory):
                session = content.BookContentSession(index)
                dialog = BookContentDialog(session, runner, selected_name='USER-o')
            cpu = ApfPlaycallPanel(session, runner)
            identity_panel = BookIdentityPanel(runner)
            try:
                names = set(splb.STOCK_BOOKS.values())
                for picker in (dialog.panel.book_picker, cpu.book_picker, identity_panel.donor):
                    self.assertEqual({picker.itemText(i) for i in range(picker.count())}, names)
                outer = dialog.panel._book.outer_index
                self.assertNotEqual(outer, 1037)  # synthetic directory ordinals differ
                dialog.panel.stage_membership(0, 5, False)
                with patch.object(content, 'master_inventory', side_effect=inventory):
                    session.build_to(root / 'edited')
                new = identity.read_resource(root / 'edited/0A', identity.filename_id('USER-o'), 'spb', 'SPLB')
                self.assertNotIn(5, {e.play_index for e in splb.parse_book(new[3], new[1].table_index).records[0].entries})
                self.assertIn(5, {e.play_index for e in session.books[outer].records[0].entries})
            finally:
                dialog.close(); cpu.close(); identity_panel.close()

    def test_each_user_and_global_donor_clone_preserves_content_and_assigns_correct_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = archive_fixture(root / 'source')
            for i, donor in enumerate(('USER-o', 'global-o', 'USER-d', 'global-d')):
                side = splb.BOOK_SIDES[donor]
                label = 5 if side == 'offense' else 37
                request = clone.CloneRequest(label, 3, donor)
                plan = clone.compile_unlock(index, [request])
                output = root / str(i)
                clone.build_new_folder(plan, output)
                parsed = identity.parse_roster_identity(identity.read_disc_roster(output / '0A'))
                self.assertEqual(getattr(parsed.teams[3], side), label)
                before = identity.read_resource(index, identity.filename_id(donor), 'spb', 'SPLB')[3]
                after = identity.read_resource(output / '0A', identity.filename_id(f'Label{label:02}'), 'spb', 'SPLB')[3]
                self.assertTrue(clone.verify_clone_body(before, after, f'Label{label:02}')['identical_except_name'])
                with self.assertRaisesRegex(ValidationError, 'same side'):
                    clone.bind_roster(identity.read_disc_roster(index), [clone.CloneRequest(37 if side == 'offense' else 5, 3, donor)])

    def test_donor_side_filters_unused_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = archive_fixture(Path(tmp) / 'source')
            panel = BookIdentityPanel(runner)
            try:
                panel.load_path(index)
                panel.donor.setCurrentIndex(panel.donor.findData('USER-d'))
                self.assertTrue(panel.label.count())
                self.assertTrue(all(panel._identity.labels[panel.label.itemData(i)].side == 'defense' for i in range(panel.label.count())))
                panel.donor.setCurrentIndex(panel.donor.findData('USER-o'))
                self.assertTrue(all(panel._identity.labels[panel.label.itemData(i)].side == 'offense' for i in range(panel.label.count())))
            finally:
                panel.close()


if __name__ == '__main__':
    unittest.main()
