"""Offscreen standalone tests for the Rules library and searchable Info tab."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tools'):
    sys.path.insert(0, str(path))

from mod_editor.core import nfl2k5_play_rules as rules, nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_pack as pk, nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_formation_play_writer as writer
from tests.mod_editor.test_nfl2k5_defense_play import retail_resources


def qt_app():
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        raise unittest.SkipTest('PyQt5 missing; the Rules UI tests require offscreen Qt')
    return QApplication.instance() or QApplication([])


class InfoQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()

    def test_info_search_is_read_only_and_opcodes_have_parameters(self):
        from mod_editor.gui.play_info_panel_qt import PlayInfoPanel
        panel = PlayInfoPanel()
        self.addCleanup(panel.close)
        total = panel.topics.count()
        self.assertGreaterEqual(total, 40)
        panel.search.setText('0x11')
        self.assertGreater(panel.topics.count(), 0)
        index = next(i for i in range(panel.topics.count()) if panel.topics.item(i).text().startswith('0x11:'))
        panel.topics.setCurrentRow(index)
        self.assertIn('Leg type', panel.reader.toPlainText())
        self.assertTrue(panel.reader.isReadOnly())
        panel.search.setText('31 records')
        self.assertIn('31 records', panel.reader.toPlainText())
        panel.search.setText('a_unique_missing_topic_123')
        self.assertEqual(panel.topics.count(), 0)
        self.assertIn('No reference topics', panel.reader.toPlainText())
        panel.search.clear()
        self.assertEqual(panel.topics.count(), total)

    def test_report_links_open_locally_and_refuse_external_or_parent_paths(self):
        from PyQt5.QtCore import QUrl
        from mod_editor.gui.play_info_panel_qt import PlayInfoPanel
        panel = PlayInfoPanel()
        self.addCleanup(panel.close)
        panel._open_report(QUrl('ASTRA_DEFENSE_PLAY_REPORT.md'))
        self.assertIn('defense play report', panel.reader.toPlainText())
        for bad in ('https://example.com', '../../outside.md', 'file:///etc/passwd'):
            panel._open_report(QUrl(bad))
            self.assertIn('Only local', panel.status.text())
        panel._open_report(QUrl('docs/mod_editor/play_rules.md'))
        panel._open_report(QUrl('../../ASTRA_PLAY_RULES_REPORT.md'))
        self.assertIn('Rule vocabulary', panel.reader.toPlainText())


class RetailRulesQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt_app()
        cls.resources = retail_resources()

    def wizard(self, team='ATL', defense=True):
        from mod_editor.gui.create_play_wizard_qt import CreatePlayWizard
        raw = self.resources[team]
        book = insp.parse_playbook_resource(raw, asset_id='book:' + team)
        class Host:
            installed = None
            compiled = None
            def playbook_raw_body(self, _asset):
                return raw[32:]
            def staged_replace_targets(self, _asset):
                return (), ()
            def install_playbook_pack(self, pack, _teams, _progress):
                self.installed = pk.loads_pack(pack.dumps())
                self.compiled = pk.apply_pack_to_resource(raw, self.installed)
                return self.compiled
        w = CreatePlayWizard(Host())
        self.addCleanup(w.close)
        w.page_team.family.setCurrentIndex(1 if defense else 0)
        w.load_book(book)
        w.page_formation.initializePage()
        w.page_formation.validatePage()
        w.page_type.initializePage()
        if defense:
            w.page_type.coverages.setCurrentText('Cover 3')
        w.page_assign.initializePage()
        return w

    def test_combo_apply_via_buttons_stages_v3_pack_and_project_roundtrip(self):
        from PyQt5.QtCore import Qt
        w = self.wizard()
        a = w.page_assign
        panel = a.rules_panel
        self.assertEqual([a.tabs.tabText(i) for i in range(a.tabs.count())],
                         ['Assignments', 'Rules library', 'Info'])
        index = next(i for i in range(panel.presets.count()) if panel.presets.itemData(i) and
                     panel.presets.itemData(i)['preset'] == 'combo_inside' and
                     panel.presets.itemData(i)['formation'] == 23)
        panel.presets.setCurrentIndex(index)
        panel.positions.item(0, 9).setCheckState(Qt.Unchecked)
        panel.apply.click()
        self.assertIn('linked players', panel.status.text())
        self.assertIsNone(a.rule_application)
        panel.positions.item(0, 9).setCheckState(Qt.Checked)
        panel.apply.click()
        self.assertIsNotNone(a.rule_application, panel.status.text())
        self.assertTrue(a.isComplete(), a.status.text())
        self.assertFalse(a._can_draw(4))
        a._commit()
        final = w.page_finalize
        final.initializePage()
        self.assertTrue(final.apply.isEnabled(), final.status.text())
        final._apply_defense()
        self.assertIsNotNone(w.host.installed)
        self.assertEqual(w.host.installed.schema, pk.OPTION_SCHEMA)
        self.assertEqual(w.host.compiled.report['new_play_count'], len(w.book.plays))
        frows, prows, links = pk.pack_requests(w.host.installed, w.book.asset_id, w.book)
        from mod_editor.studio.project_archive import save_project_archive, load_project_archive
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            path = save_project_archive(catalog=None, asset_io=None, edits=(),
                destination=root / 'rules.2k5mod', formation_creates=frows,
                play_creates=prows, formation_links=links)
            restored = load_project_archive(source=path, catalog=None, asset_io=None,
                                             private_root=root / 'private')
            self.assertEqual(len(restored.play_creates), len(prows))
            compiled = writer.compile_formation_play_creations(self.resources['ATL'],
                restored.formation_creates, restored.play_creates, restored.formation_links)
            self.assertEqual(compiled.replacement, w.host.compiled.replacement)

    def test_complete_retail_pass_keeps_zero_read_values_at_finalize(self):
        w = self.wizard(defense=False)
        # This native screen has zero read-order values that must not become one.
        w.page_formation._use_stock(w.page_formation.stock.findData(5))
        w.page_formation.validatePage()
        w.page_type.initializePage()
        w.page_assign.initializePage()
        bundle = rules.extract_bundle(w.book, w.body, 5, 178)
        w.page_assign._apply_retail_rules(bundle)
        w.page_assign._commit()
        saved = w.current.plays[-1]
        expected = lib.play_chains(w.body, 178)[1][0][1]
        self.assertIn(0, saved.chains[0][-1][1][1:5])
        w.page_finalize.initializePage()
        self.assertEqual(w.page_finalize._read_orders, {})
        self.assertEqual([n.to_bytes() for n in lib.codec.encode_chain(saved.chains[0])], expected)

    def test_viewer_search_and_reset_leave_source_unchanged(self):
        w = self.wizard()
        panel = w.page_assign.rules_panel
        source = w.body
        panel.search.setText('Combo Inside Zone')
        self.assertEqual(panel.plays.count(), 1)
        self.assertEqual(panel.nodes.rowCount(), 26)
        self.assertTrue(all(panel.nodes.item(row, 4).text() for row in range(panel.nodes.rowCount())))
        panel.scope.setCurrentIndex(panel.scope.findData('active'))
        panel.apply.click()
        self.assertIsNotNone(w.page_assign.rule_application, panel.status.text())
        panel.reset.click()
        self.assertIsNone(w.page_assign.rule_application)
        self.assertEqual(w.body, source)
        panel.search.setText('no such retail play')
        self.assertFalse(panel.apply.isEnabled())
        self.assertEqual(panel.nodes.rowCount(), 0)

    def test_multiple_partial_copies_do_not_restore_overwritten_spy_intent(self):
        w = self.wizard()
        a = w.page_assign
        a.defense_design.set_assignment(w.book, w.body, 5, 'spy', depth_yd=4)
        self.assertEqual(a.defense_design.spy_slots, {5})
        a._apply_retail_rules(rules.extract_bundle(w.book, w.body, 23, 25, slots=(5,)))
        a._apply_retail_rules(rules.extract_bundle(w.book, w.body, 23, 25, slots=(7,)))
        a._commit()
        self.assertEqual(w.current.plays[-1].spy_slots, ())
        a._reset_rules()
        self.assertEqual(a._rule_replaced_slots, set())
        self.assertEqual(a.defense_design.spy_slots, {5})


if __name__ == '__main__':
    unittest.main()
