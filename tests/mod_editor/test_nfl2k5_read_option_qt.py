"""Offscreen option authoring, branch display and staging. No facade cache writes."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / 'tools'):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from tests.mod_editor.test_nfl2k5_read_option import retail_resources
from mod_editor.core import nfl2k5_play_codec as codec, nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_pack as pk, nfl2k5_playbook_inspector as insp


class OptionQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest('PyQt5 missing; option widget tests require offscreen Qt')
        cls.app = QApplication.instance() or QApplication([])
        cls.resource = retail_resources()['MIN']
        cls.book = insp.parse_playbook_resource(cls.resource, asset_id='book:MIN')
        cls.fi = next(f.index for f in cls.book.formations if f.name == 'I Jokers')

    def wizard(self):
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard, DesignedFormation
        testcase = self
        class Host:
            installed = None
            used = ()
            def playbook_raw_body(self, _asset): return testcase.resource[32:]
            def staged_replace_targets(self, _asset): return (), self.used
            def install_playbook_pack(self, pack, teams, progress):
                self.installed = pack
                self.teams = teams
                self.compiled = pk.apply_pack_to_resource(testcase.resource, pack)
        host = Host()
        w = CreatePlayWizard(host); w.load_book(self.book)
        self.addCleanup(w.close)
        rec = lib.formation_record(w.body, self.fi)
        codes = lib.category_positions(w.body, lib.formation_category(w.body, self.fi))
        w.current = DesignedFormation(self.book.formations[self.fi].name,
            lib.formation_category(w.body, self.fi), self.fi, [(s.x[0], s.z[0]) for s in rec.slots],
            [c & 31 for c in codes], [codec.position_label(c) for c in codes], codes=codes)
        w.designed = [w.current]
        w.page_type.initializePage()
        w.page_type.radios['option'].setChecked(True)
        return w, host

    def test_presets_are_experimental_fixed_opponent_slots_and_limits_visible(self):
        from PyQt5.QtWidgets import QLabel
        w, _ = self.wizard(); p = w.page_type
        self.assertFalse(p.option_box.isHidden())
        self.assertEqual([p.option_preset.itemText(i) for i in range(3)], list(lib.OPTION_PRESETS))
        self.assertEqual([p.option_back.itemData(i) for i in range(p.option_back.count())], [9, 10])
        text = ' '.join(label.text() for label in p.option_box.findChildren(QLabel))
        self.assertIn('EXPERIMENTAL / UNWITNESSED', text)
        self.assertIn('position/velocity based', text)
        self.assertIn('later runtime tier', text)
        self.assertIn('not guaranteed to remain unblocked', text)
        self.assertNotIn('—', text)
        for preset in lib.OPTION_PRESETS:
            p.option_preset.setCurrentText(preset)
            self.assertTrue(p.isComplete(), p.option_problem.text())
            d = p.option_design()
            if preset != lib.OPTION_PRESETS[0]:
                self.assertEqual(d.chains[0][2][1][5], 1)
                self.assertEqual(d.chains[0][2][1][7], 0)
        w.current.positions[0] = (1, -100)
        self.assertFalse(p.isComplete())
        self.assertIn('Restore', p.option_problem.text())

    def test_node_budget_enforced_cumulatively_and_all_presets_stage(self):
        from PyQt5.QtWidgets import QMessageBox
        for preset in lib.OPTION_PRESETS:
            with self.subTest(preset=preset):
                w, host = self.wizard(); w.page_type.option_preset.setCurrentText(preset)
                w.page_assign.initializePage(); a = w.page_assign
                self.assertIsNone(a._error)
                cost = sum(map(len, a.option_design.chains))
                self.assertIn(f'{cost} nodes ({cost * 8} bytes)', a.status.text())
                self.assertIn('alternate 1-7', a.status.text())
                normal = w.book; w.book = replace(normal, node_count=3500 - cost + 1)
                a._refresh(); self.assertFalse(a.isComplete())
                w.book = normal; a._refresh(); self.assertTrue(a.validatePage())
                # A committed option locks this batch to options.
                w.page_type.initializePage()
                self.assertFalse(w.page_type.radios['pass'].isEnabled())
                w.book = replace(normal, node_count=3500 - cost)
                a._refresh(); self.assertFalse(a.isComplete())
                w.book = normal
                final = w.page_finalize; final.initializePage()
                for obj, combo in final._choices:
                    self.assertTrue(all(combo.itemData(i)[1] is not None for i in range(combo.count())))
                with patch.object(QMessageBox, 'warning') as warning:
                    final._apply()
                warning.assert_not_called()
                self.assertIsNotNone(host.installed)
                self.assertEqual(host.teams, ('MIN',))
                self.assertEqual(host.installed.plays[0].option_intent['preset'], preset)
                self.assertEqual(len(host.compiled.report['option_intent']['records']), 1)
                self.assertTrue(final.build.isEnabled())

    def test_no_unused_play_replacement_disables_staging(self):
        w, host = self.wizard(); w.page_assign.initializePage(); w.page_assign.validatePage()
        host.used = tuple(p.index for p in self.book.plays)
        w.page_finalize.initializePage()
        self.assertFalse(w.page_finalize.apply.isEnabled())
        self.assertIn('No unused replacement', w.page_finalize.table.item(1, 3).text())

    def test_saved_project_manifest_preserves_branch_bytes_and_fixture(self):
        import json
        import tempfile
        import zipfile
        from mod_editor.studio.project_archive import save_project_archive
        from mod_editor.core import nfl2k5_formation_play_writer as writer
        w, _ = self.wizard()
        w.page_type.option_preset.setCurrentText(lib.OPTION_PRESETS[2])
        w.page_assign.initializePage(); w.page_assign.validatePage()
        w.page_finalize.initializePage(); pack = w.page_finalize._option_pack()
        forms, plays, links = pk.pack_requests(pack, self.book.asset_id, self.book)
        with tempfile.TemporaryDirectory() as td:
            path = save_project_archive(catalog=None, asset_io=None, edits=(),
                destination=Path(td).resolve() / 'option.2k5mod',
                formation_creates=forms, play_creates=plays, formation_links=links)
            with zipfile.ZipFile(path) as archive:
                saved = json.loads(archive.read('project.json'))
            requests = [writer.play_request_from_mapping(row) for row in saved['playbook_creates']
                        if row['kind'] == 'play_create']
            self.assertEqual(requests[0].option_intent, pack.plays[0].option_intent)
            self.assertEqual([n[2] for n in requests[0].assignments[0]], [0x10, 0x10, 0x14, 2, 0x13])
            compiled = writer.compile_formation_play_creations(self.resource, forms, requests, links)
            self.assertEqual(compiled.replacement, pk.apply_pack_to_resource(self.resource, pack).replacement)

    def test_real_facade_staging_emits_no_duplicate_menu_links(self):
        from threading import RLock
        from types import SimpleNamespace
        from mod_editor.studio.facade import Nfl2k5StudioFacade
        pack = pk.load_pack(ROOT / 'data/playbooks/softdrink_option.2k5book')
        rows, links = [], []
        session = SimpleNamespace(attach_playbook_inspector=lambda _i: None,
                                  create_play=lambda request: rows.append(request) or True,
                                  create_formation_link=lambda request: links.append(request) or True)
        host = SimpleNamespace(_lock=RLock(), _require_playbook_inspector=lambda: object(),
                               _require_session=lambda: session)
        count = Nfl2k5StudioFacade._stage_pack(host, pack, self.book.asset_id, self.book)
        self.assertEqual((count, len(rows), links), (8, 8, []))
        self.assertEqual([r.option_intent for r in rows], [p.option_intent for p in pack.plays])

    def test_designer_branch_details_marker_and_flags_survive_edit(self):
        from mod_editor.gui.play_designer_qt import PlayDesignerDialog
        d = PlayDesignerDialog(self.book, self.resource[32:], self.fi, 24)
        self.addCleanup(d.close)
        d.slot_list.setCurrentRow(0); d.node_list.setCurrentRow(3)
        detail = d.node_list.item(3).text()
        self.assertIn('Position / velocity', detail)
        self.assertIn('alternate=4', detail)
        self.assertIn('opponent=Friendly', detail)
        self.assertIn('human=Yes', detail)
        self.assertIn('terminal', detail)
        self.assertTrue(any('alternate node 4' in item.toolTip() for item in d.scene.art_items))
        d._operand_changed(1, -13 * lib.YD)
        self.assertIsNone(d._error)
        d._accept()
        authored = d.result_payload['assignments'][0]
        self.assertEqual([n[2] for n in authored], [0x10, 0x10, 0x14, 0x12, 0x13])
        self.assertEqual(authored[3][1][1], -13 * lib.YD)

    def test_designer_refuses_broken_cache_reference_and_keeps_read_order_flags(self):
        from mod_editor.gui.play_designer_qt import PlayDesignerDialog
        from mod_editor.gui.create_play_wizard_qt import with_read_order
        d = PlayDesignerDialog(self.book, self.resource[32:], self.fi, 24)
        self.addCleanup(d.close)
        d.slot_list.setCurrentRow(10); d.node_list.setCurrentRow(1)
        d._operand_changed(6, 2)
        self.assertIn('condition node', d._error)
        chain = [(6, [0, 2, 0, 0, 0, .3], 2)]
        self.assertEqual(with_read_order(chain, (3, 0, 0, 0), allow_zero=True), [(6, [0, 3, 0, 0, 0, .3], 2)])


if __name__ == '__main__':
    unittest.main()
