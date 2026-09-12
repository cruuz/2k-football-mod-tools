"""Clone -> actual Fine-tune widget -> recipe -> copied multi-volume reparse."""
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio import book_content as content
from mod_editor.apf_studio.book_identity_qt import BookContentDialog, BookIdentityPanel
from mod_editor.core import apf2k8_book_clone as clone, apf2k8_book_identity as identity
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.errors import ValidationError
from tests.mod_editor.test_apf_book_unlock import archive_fixture


def inventory(_index):
    master = bytearray(0x2000)
    for i, row in enumerate(splb.PERSONNEL_ROWS):
        master[0x44+i*16+4] = row
    return {'plays': [{'index': i, 'name': f'Play {i}'} for i in range(586)],
            'formations': [{'index': i, 'name': f'Formation {i}'} for i in range(163)]}, bytes(master)


def runner(_title, operation, complete, _blocking):
    complete(operation(lambda *_args: None))


class ContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.source = archive_fixture(cls.root / 'source')
        plan = clone.compile_unlock(cls.source, [clone.CloneRequest(5, 3, 'O-ZoneBlock')])
        clone.build_new_folder(plan, cls.root / 'cloned')
        cls.index = cls.root / 'cloned/0A'

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def session(self):
        with patch.object(content, 'master_inventory', side_effect=inventory):
            return content.BookContentSession(self.index)

    def test_clone_edit_recipe_and_build_leave_original_shared_book_and_roster_intact(self):
        session = self.session()
        dialog = BookContentDialog(session, runner, selected_name='Label05')
        try:
            panel = dialog.panel
            self.assertEqual(panel._book.name, 'Label05')
            outer = panel._book.outer_index
            self.assertNotEqual(outer, 943)
            panel.stage_tag_move(0, 0, 4)
            panel.stage_membership(0, 5, False)
            panel.stage_trailer_replace(0, 69, 8)
            self.assertTrue(session.changes)
            recipe = self.root / 'edits.json'
            session.save_recipe(recipe)
            again = self.session()
            again.load_recipe(recipe)
            self.assertEqual(again.changes, session.changes)
            output = self.root / 'edited'
            with patch.object(content, "master_inventory", side_effect=inventory):
                receipt = again.build_to(output)
            after = splb.read_book(output / '0A', outer)
            self.assertEqual(after.records[0].formation_index, 69)
            self.assertEqual(next(e.y for e in after.records[0].entries if e.play_index == 4), 0)
            self.assertNotIn(5, {e.play_index for e in after.records[0].entries})
            donor_id = identity.filename_id('O-ZoneBlock')
            self.assertEqual(identity.read_resource(self.index, donor_id, 'spb', 'SPLB')[3],
                             identity.read_resource(output / '0A', donor_id, 'spb', 'SPLB')[3])
            self.assertEqual(identity.read_disc_roster(self.index), identity.read_disc_roster(output / '0A'))
            self.assertEqual((output / 'default.xex').read_bytes(), (self.index.parent / 'default.xex').read_bytes())
            self.assertGreater(receipt['untouched_pack_bytes_compared'], 0)
            self.assertEqual(receipt['runtime_status'], 'UNWITNESSED')
            self.assertTrue((output / 'book-content-receipt.json').is_file())
            with self.assertRaisesRegex(ValidationError, 'contents differ'):
                with patch.object(content, 'master_inventory', side_effect=inventory):
                    edited = content.BookContentSession(output / '0A')
                edited.load_recipe(recipe)
        finally:
            dialog.close()

    def test_identity_button_opens_a_real_fine_tune_panel_on_clone(self):
        panel = BookIdentityPanel(runner)
        panel._edit_index = self.index
        panel._edit_name = 'Label05'
        try:
            with patch.object(content, 'master_inventory', side_effect=inventory):
                panel.open_fine_tune()
            self.assertEqual(len(panel._content_dialogs), 1)
            dialog = panel._content_dialogs[0]
            self.assertEqual(dialog.panel._book.name, 'Label05')
            self.assertTrue(dialog.panel.book_picker.isEnabled())
            panel.set_busy(True)
            self.assertFalse(dialog.isEnabled())
            panel.set_busy(False)
            self.assertTrue(dialog.isEnabled())
            dialog.close()
        finally:
            panel.close()

    def test_late_stock_load_cannot_replace_the_selected_clone(self):
        pending = []
        def delayed(_title, work, done, _blocking):
            pending.append((work, done))
            return True
        dialog = BookContentDialog(self.session(), delayed, selected_name='Label05')
        try:
            self.assertGreaterEqual(len(pending), 2)
            self.assertIsNone(dialog.panel._book)
            for work, done in reversed(pending):
                done(work(lambda *_args: None))
            self.assertEqual(dialog.panel._book.name, 'Label05')
            self.assertEqual(dialog.panel._book.outer_index, dialog.panel.book_picker.currentData())
        finally:
            dialog.close()

    def test_recipe_content_clone_is_verified_and_idempotent_without_editing_donor(self):
        import playbook_inventory
        import zlib
        from mod_editor.core import apf2k8_scheme_presets as presets
        # Beta 67 applies the preset to the already-authored donor book instead of
        # recompiling it from the archive, so it now composes with MASTER directly.
        # This synthetic archive carries no MASTER resource; supply it here.
        master_id = zlib.crc32(b'PLAYBOOK_MASTER.IFF')
        fake_master = (None, SimpleNamespace(table_index=0, name_id=master_id), None, b'', None, b'')
        real_read = clone.read_resource
        def read(index, name_id, inner, type_name):
            if name_id == master_id:
                return fake_master
            return real_read(index, name_id, inner, type_name)
        def applied(book, recipe, _master):
            changed = splb.compile_book(book, [splb.MembershipChange(book.outer_index, 0, 5, False)])
            return changed.replacement, {}
        with patch.object(presets, 'apply_preset', side_effect=applied), \
             patch.object(clone, 'read_resource', side_effect=read), \
             patch.object(playbook_inventory, 'parse_apf_body', return_value={}):
            plan = clone.compile_unlock(self.source, [clone.CloneRequest(6, 4, 'O-ZoneBlock')],
                                        preset_ids=('wide-zone',))
            output = self.root / 'preset-copy'
            receipt = clone.build_new_folder(plan, output)
        self.assertTrue(receipt['verification']['idempotent_reapply'])
        copied = identity.read_resource(output / '0A', identity.filename_id('Label06'), 'spb', 'SPLB')
        donor = identity.read_resource(output / '0A', identity.filename_id('O-ZoneBlock'), 'spb', 'SPLB')
        self.assertNotIn(5, {e.play_index for e in splb.parse_book(copied[3], copied[1].table_index).records[0].entries})
        self.assertIn(5, {e.play_index for e in splb.parse_book(donor[3], donor[1].table_index).records[0].entries})

    def test_new_folder_required_and_tampered_name_refused(self):
        session = self.session()
        outer = next(i for i, b in session.books.items() if b.name == 'Label05')
        session.stage_splb_membership([splb.MembershipChange(outer, 0, 5, False)], replace_outer=outer)
        with self.assertRaisesRegex(ValidationError, 'separate new output'), patch.object(content, "master_inventory", side_effect=inventory):
            session.build_to(self.index.parent)
        with patch.object(splb, 'parse_book', return_value=type('Book', (), {'name': 'Another name'})()):
            with self.assertRaisesRegex(ValidationError, 'filename and decoded book name'):
                splb.read_book(self.index, outer)


if __name__ == '__main__': unittest.main()
