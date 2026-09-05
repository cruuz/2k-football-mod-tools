"""Offscreen defense wizard/designer and ordinary project persistence."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from test_nfl2k5_defense_play import retail_resources
from mod_editor.core import nfl2k5_playbook_inspector as insp, nfl2k5_playbook_pack as pk
from mod_editor.core import nfl2k5_play_library as lib, nfl2k5_formation_play_writer as writer


class DefenseQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest('PyQt5 missing; offscreen Qt required')
        cls.resources = retail_resources()
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.resource = self.resources['ATL']
        self.book = insp.parse_playbook_resource(self.resource, asset_id='book:ATL')
        testcase = self
        class Host:
            installed = None
            def playbook_raw_body(self, _asset):
                return testcase.resource[32:]
            def staged_replace_targets(self, _asset):
                return (), ()
            def install_playbook_pack(self, pack, teams, progress):
                self.installed = pack
                return pk.apply_pack_to_resource(testcase.resource, pack)
        self.host = Host()

    def wizard(self):
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard
        w = CreatePlayWizard(self.host)
        self.addCleanup(w.close)
        w.load_book(self.book)
        w.page_team.family.setCurrentIndex(1)
        w.page_formation.initializePage()
        w.page_formation.validatePage()
        w.page_type.initializePage()
        w.page_type.coverages.setCurrentText('Cover 3')
        w.page_assign.initializePage()
        return w

    def test_full_defense_wizard_stages_spy_and_restores_project(self):
        w = self.wizard()
        self.assertTrue(w.is_defense)
        f = w.page_formation
        self.assertEqual(f._issues, [])
        self.assertTrue(all(lib.formation_record(w.body, f.stock.itemData(n)).type_code >= 4 for n in range(f.stock.count())))
        self.assertIn('MLB', f.personnel.text())
        self.assertIn('FS', f.personnel.text())
        self.assertEqual(w.page_assign.jobs.count(), 11)
        a = w.page_assign
        a.defense_design.set_assignment(self.book, w.body, 5, 'spy', depth_yd=4)
        a._refresh()
        self.assertIn(lib.SPY_NOTICE, a.status.text())
        self.assertTrue(any(getattr(item, 'text', lambda: '')() == 'S: shallow zone' for item in a.scene.art_items))
        a.name_edit.setText('SD Spy Test')
        a._commit()
        final = w.page_finalize
        final.initializePage()
        self.assertTrue(final.apply.isEnabled(), final.status.text())
        self.assertIn('pool 176 bytes', final.status.text())
        self.assertEqual(final._groups[1][1].currentData(), 3)
        final._apply_defense()
        pack = self.host.installed
        self.assertIsNotNone(pack)
        self.assertEqual(pack.plays[0].spy_slots, (5,))
        frows, prows, links = pk.pack_requests(pack, self.book.asset_id, self.book)
        from mod_editor.studio.project_archive import save_project_archive, load_project_archive
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            path = save_project_archive(catalog=None, asset_io=None, edits=(), destination=root / 'spy.2k5mod',
                formation_creates=frows, play_creates=prows, formation_links=links)
            import json
            import zipfile
            with zipfile.ZipFile(path) as archive:
                saved = json.loads(archive.read('project.json'))
            # The model and .2k5mod persist intent. The existing create-only
            # project loader bug is isolated below and documented in WIRING.md.
            requests = [writer.play_request_from_mapping(row) for row in saved['playbook_creates'] if row['kind'] == 'play_create']
            self.assertEqual(requests[0].spy_slots, (5,))
            compiled = writer.compile_formation_play_creations(self.resource, frows, requests, links)
            self.assertEqual(compiled.report['spy_intent']['records'][0]['slot'], 5)

    @unittest.expectedFailure
    def test_create_only_project_reload_pending_project_archive_wiring(self):
        # project_archive.py is outside this job's owned files. WIRING.md gives
        # the two missing predicates; leave a live regression for integration.
        from mod_editor.studio.project_archive import save_project_archive, load_project_archive
        w = self.wizard()
        w.page_assign._commit()
        w.page_finalize.initializePage()
        pack = w.page_finalize._defense_pack()
        frows, prows, links = pk.pack_requests(pack, self.book.asset_id, self.book)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            path = save_project_archive(catalog=None, asset_io=None, edits=(), destination=root / 'defense.2k5mod',
                formation_creates=frows, play_creates=prows, formation_links=links)
            loaded = load_project_archive(source=path, catalog=None, asset_io=None, private_root=root / 'private')
            self.assertEqual(len(loaded.play_creates), 1)

    def test_designer_presets_eleven_choices_spy_and_capacity(self):
        from PyQt5.QtWidgets import QMessageBox
        from mod_editor.gui.play_designer_qt import PlayDesignerDialog, DEFENSE_ASSIGNMENT_CHOICES
        dialog = PlayDesignerDialog(self.book, self.resource[32:], 23, 8)
        self.addCleanup(dialog.close)
        self.assertIn(('Spy', 'spy'), DEFENSE_ASSIGNMENT_CHOICES)
        dialog._defense_preset('Cover 4 Quarters (spot)')
        self.assertIsNone(dialog._error)
        design = dialog._defense_design()
        self.assertEqual(len(lib.defense_counts(design.effective())['deep']), 4)
        design.set_assignment(self.book, self.resource[32:], 5, 'spy', depth_yd=4)
        dialog._take_defense_design(design)
        dialog.name_edit.setText('Spy Designer')
        dialog._accept()
        self.assertEqual(dialog.result_payload['spy_intent']['slots'], [5])
        self.assertEqual(dialog.slot_list.count(), 11)
        from dataclasses import replace
        dialog.book = replace(dialog.book, node_count=3490)
        self.assertIn('remaining node pool', dialog._validate())

    def test_double_a_and_exchange_show_experimental_and_keep_pairs(self):
        w = self.wizard()
        w.page_formation._double_a()
        self.assertEqual(w.page_formation.positions[4:6], [[-76, 91], [76, 91]])
        self.assertIn('EXPERIMENTAL', w.page_formation.name_edit.text())
        d = lib.make_defense_design(self.book, w.body, 23, 'Stock Exchange')
        partners = [(s, int(v[5])) for s, chain in enumerate(d.chains) for op, v in chain if op == 0x0E and v[6]]
        self.assertTrue(partners)
        for s, t in partners:
            self.assertIn((t, s), partners)
        self.assertIn('Tampa 2 Drop EXPERIMENTAL', [w.page_type.coverages.itemText(n) for n in range(w.page_type.coverages.count())])


if __name__ == '__main__':
    unittest.main()
