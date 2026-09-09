"""Offscreen Rules, Info, existing pack dialog and project persistence tests."""
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

from tests.mod_editor.test_nfl2k5_match_coverage import resources, SEED
from mod_editor.core import nfl2k5_playbook_pack as pk
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_match_coverage as match
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_formation_play_writer as writer


class MatchQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest('PyQt5 is absent; offscreen match UI acceptance requires it')
        cls.app = QApplication.instance() or QApplication([])
        cls.resources = resources()
        cls.books = {t: insp.parse_playbook_resource(r, asset_id='book:' + t) for t, r in cls.resources.items()}

    def test_info_search_documents_native_census_and_missing_modern_keys(self):
        from mod_editor.gui.play_info_panel_qt import PlayInfoPanel
        panel = PlayInfoPanel()
        self.addCleanup(panel.close)
        panel.search.setText('Palms')
        index = next(i for i in range(panel.topics.count()) if
                     panel.topics.item(i).text().startswith('Match coverage:'))
        panel.topics.setCurrentRow(index)
        text = panel.reader.toPlainText()
        for word in ('59', '105', '15 yards', '#2-out', 'UNWITNESSED', 'slot 0'):
            self.assertIn(word, text)
        self.assertTrue(panel.reader.isReadOnly())

    def test_named_ravens_bundle_uses_existing_library_apply_action(self):
        from PyQt5.QtCore import Qt
        from mod_editor.gui.play_rules_panel_qt import PlayRulesPanel
        bundles = []
        panel = PlayRulesPanel(apply_bundle=bundles.append)
        self.addCleanup(panel.close)
        panel.set_book(self.books['BAL'], self.resources['BAL'][32:])
        index = next(i for i in range(panel.presets.count()) if panel.presets.itemData(i) and
                     panel.presets.itemData(i)['preset'] == 'match_vertical' and panel.presets.itemData(i)['play'] == 14)
        panel.presets.setCurrentIndex(index)
        self.assertIn('15 yards', panel.status.text())
        panel.positions.item(0, 7).setCheckState(Qt.Unchecked)
        panel.apply.click()
        self.assertFalse(bundles)
        self.assertIn('linked', panel.status.text())
        panel.positions.item(0, 7).setCheckState(Qt.Checked)
        panel.apply.click()
        self.assertEqual(len(bundles), 1)
        self.assertTrue({7, 8, 9, 10} <= set(bundles[0].slots))

    def test_existing_pack_dialog_retargets_installs_and_saves_real_compiler_rows(self):
        from PyQt5.QtWidgets import QDialogButtonBox
        from mod_editor.gui.playbook_pack_dialog_qt import PlaybookPackInstallDialog
        from mod_editor.studio.project_archive import save_project_archive, load_project_archive
        owner = self
        class Host:
            installed = None
            compiled = None
            def load_playbook_pack(self, path):
                return pk.load_pack(path)
            def playbook_teams(self):
                return ('BAL', 'OAK')
            def preview_playbook_pack(self, pack, team, _progress):
                raw = owner.resources[team]
                return pk.preview_pack(pack, team, owner.books[team], raw[32:], resource=raw)
            def install_playbook_pack(self, pack, teams, _progress):
                team = teams[0]
                preview = self.preview_playbook_pack(pack, team, _progress)
                self.installed = preview.pack
                self.compiled = pk.apply_pack_to_resource(owner.resources[team], preview.pack)
                return self.compiled
        host = Host()
        dialog = PlaybookPackInstallDialog(host, SEED)
        self.addCleanup(dialog.close)
        self.assertIn('#2-out', dialog.summary.text())
        dialog.team_combo.setCurrentIndex(dialog.team_combo.findData('OAK'))
        button = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertTrue(button.isEnabled(), dialog.status.text())
        self.assertEqual(dialog.table.rowCount(), 5)
        button.click()
        self.assertEqual(dialog.installed_teams, ('OAK',))
        self.assertEqual(len(host.installed.plays), 5)
        self.assertEqual(host.installed.plays[0].defense_formation, '4-3')
        frows, prows, links = pk.pack_requests(host.installed, 'book:OAK', self.books['OAK'])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            path = save_project_archive(catalog=None, asset_io=None, edits=(),
                destination=root / 'match.2k5mod', formation_creates=frows,
                play_creates=prows, formation_links=links)
            restored = load_project_archive(source=path, catalog=None, asset_io=None, private_root=root / 'private')
            rebuilt = writer.compile_formation_play_creations(self.resources['OAK'],
                restored.formation_creates, restored.play_creates, restored.formation_links)
            # Project archives canonically sort replacement rows. Pool/name
            # allocation order may differ; all native descriptors, chains,
            # names and menus must retain the same meaning after recompiling.
            self.assertEqual(rebuilt.parsed_replacement.formations, host.compiled.parsed_replacement.formations)
            for p in rebuilt.parsed_replacement.plays:
                self.assertEqual(p.name, host.compiled.parsed_replacement.plays[p.index].name)
                self.assertEqual(lib.play_chains(rebuilt.replacement[32:], p.index),
                                 lib.play_chains(host.compiled.replacement[32:], p.index))

    def test_offscreen_export_has_no_window_and_preserves_resource(self):
        from tools.nfl2k5_match_coverage import render_play
        from PyQt5.QtGui import QImage
        raw = self.resources['BAL']
        with tempfile.TemporaryDirectory() as td:
            out = Path(td).resolve() / 'play.png'
            receipt = render_play(self.books['BAL'], raw[32:], 14, 25, out, team='BAL')
            image = QImage(str(out))
            self.assertFalse(image.isNull())
            self.assertEqual((image.width(), image.height()), (1280, 940))
            self.assertEqual(receipt['front'], 43)
            self.assertNotEqual(image.pixel(50, 150), image.pixel(1250, 930))
        self.assertEqual(raw, self.resources['BAL'])
        self.assertFalse(any(w.isVisible() for w in self.app.topLevelWidgets()))


if __name__ == '__main__':
    unittest.main()
