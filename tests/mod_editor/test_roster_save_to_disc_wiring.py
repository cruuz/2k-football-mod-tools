"""Run the exact protected Rosters patch in memory, or shipped source after wiring."""
from __future__ import annotations

import os
import hashlib
from pathlib import Path
import re
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests/mod_editor'), str(ROOT / 'tools')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_save_to_disc as importer
from tests.mod_editor.test_roster_save_to_disc import signed, save_files, image_fixture, league_body


def proposed_source():
    path = 'mod_editor/gui/roster_editor_panel_qt.py'
    text = (ROOT / path).read_text(encoding="utf-8")
    if '    def save_roster_to_disc(' in text:
        return text
    source = text.splitlines(True)
    lines = (ROOT / 'tests/fixtures/roster_save_to_disc_wiring.patch').read_text(encoding="utf-8").splitlines(True)
    assert lines[:2] == [f'--- a/{path}\n', f'+++ b/{path}\n']
    output, cursor, i = [], 0, 2
    while i < len(lines):
        start = int(re.match(r'@@ -(\d+)', lines[i])[1]) - 1
        assert start >= cursor
        output.extend(source[cursor:start])
        cursor = start
        i += 1
        while i < len(lines) and not lines[i].startswith('@@'):
            line = lines[i]
            if line == '\n': line = ' \n'
            if line[0] in ' -':
                assert source[cursor] == line[1:], (cursor, line)
                cursor += 1
            if line[0] in ' +': output.append(line[1:])
            i += 1
    return ''.join(output + source[cursor:])


class PatchTests(unittest.TestCase):
    def test_proposal_compiles_and_contains_exact_action(self):
        source = proposed_source()
        compile(source, '<Rosters proposal>', 'exec')
        self.assertIn("Use this save's roster on the disc...", source)


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PyQt5.QtWidgets import QApplication
            from mod_editor.gui import roster_editor_panel_qt
        except ImportError as exc:
            raise unittest.SkipTest(f'Offscreen Qt dependencies unavailable: {exc}')
        cls.app = QApplication.instance() or QApplication([])
        name = 'mod_editor.gui._roster_save_to_disc_proposal'
        cls.module = ModuleType(name)
        cls.module.__file__ = roster_editor_panel_qt.__file__
        cls.module.__package__ = 'mod_editor.gui'
        sys.modules[name] = cls.module
        cls.addClassCleanup(sys.modules.pop, name, None)
        exec(compile(proposed_source(), cls.module.__file__, 'exec'), cls.module.__dict__)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.disc = image_fixture(self.root, league_body()).path
        self.save = signed(league_body())
        self.save.players[0].record.set('speed', 99)
        self.path = save_files(self.root / 'save', self.save)
        self.panel = self.module.RosterEditorPanel(SimpleNamespace(source_path=self.disc))
        self.addCleanup(self.panel.deleteLater)
        # No unrelated executable/catalog background reads for a roster-only UI proof.
        self.panel._reload_espn25 = Mock()
        self.panel._load_templates = Mock()
        self.output = self.root / 'roster_edits.json'

    def load(self, kind='save'):
        self.panel.load_document(self.save if kind == 'save' else rr.load_image(self.disc),
                                 kind=kind, source=self.path if kind == 'save' else self.disc)

    def test_save_button_visibility_and_tools_file_picker_visibility(self):
        self.assertTrue(self.panel.save_roster_to_disc_button.isHidden())
        self.load('save')
        self.assertFalse(self.panel.save_roster_to_disc_button.isHidden())
        self.assertFalse(self.panel.save_roster_to_disc_action.isVisible())
        self.load('disc')
        self.assertTrue(self.panel.save_roster_to_disc_button.isHidden())
        self.assertTrue(self.panel.save_roster_to_disc_action.isVisible())

    def test_loaded_save_uses_current_disc_export_path_and_build_signal_without_losing_session(self):
        self.load()
        prior = self.panel.document.to_body()
        emitted = []
        self.panel.roster_edits_changed.connect(emitted.append)
        result = self.panel.save_roster_to_disc(self.output)
        self.assertEqual(emitted, [str(self.output)])
        self.assertEqual(self.output.read_text(encoding="utf-8"), importer.json_text(result.edits))
        self.assertEqual(self.output.with_suffix('.receipt.json').read_text(encoding="utf-8"), result.details)
        self.assertEqual(self.panel._edits_path, self.output)
        self.assertEqual(self.panel.document.to_body(), prior)
        self.assertEqual(self.panel._source_kind, 'save')
        self.assertEqual(rr.load_image(self.disc).players[0].record.get('speed'), 50)
        # The existing Build panel consumes the same signal's saved JSON.
        from mod_editor.gui.build_panel_qt import BuildPanel
        build = BuildPanel()
        self.addCleanup(build.deleteLater)
        build.set_roster_edits(str(self.output))
        self.assertEqual(build.plan().roster_edits, str(self.output))

    def test_replacement_roster_from_signed_file_reaches_build_writer(self):
        from tests.mod_editor.test_nfl2k5_roster_records import league_sample, synthetic_body
        from mod_editor.gui.build_panel_qt import BuildPanel
        rows = []
        for index, row in enumerate(league_sample()):
            row = list(row)
            row[:2] = [f"N{index:x}", f"New{index:x}"]
            rows.append(tuple(row))
        source = signed(synthetic_body(rows))
        for player in source.players:
            player.record.set('pbp_id', 0)
            player.record.set('speed', 99)
        source.swap(source.players[0], source.players[44])
        path = save_files(self.root / 'replacement', source)
        # Real save framing and HMAC, freshly opened, with no editor-session diffs.
        source = importer.load_save(path)
        self.assertFalse(rr.edits_document(source)['edits'])
        self.panel.load_document(source, kind='save', source=path)
        build = BuildPanel()
        self.addCleanup(build.deleteLater)
        self.addCleanup(build._hires_budget_timer.stop)
        self.panel.roster_edits_changed.connect(build.set_roster_edits)
        with patch.object(self.module.QFileDialog, 'getSaveFileName', return_value=(str(self.output), '')), \
             patch.object(self.module, 'QMessageBox', Mock()):
            self.panel.save_roster_to_disc_button.click()
        plan = build.plan()
        self.assertEqual(plan.roster_edits, str(self.output))
        # Only the bounded fixture's ROST writer runs, never a disc build.
        receipt = rr.apply(self.disc, plan.roster_edits)
        target = rr.load_image(self.disc)
        self.assertGreater(receipt['players_changed'], 0)
        for before, after in zip(source.players, target.players):
            self.assertEqual((after.first, after.last), (before.first, before.last))
            self.assertEqual(after.record.get('speed'), 99)
            self.assertEqual(after.teams, before.teams)

    def test_private_signed_save_replaces_all_2547_players_through_button(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        fixture_root = Path(os.environ.get('NFL2K5_SAVE_FIXTURES',
                            '/home/noah/Desktop/2K5-8 Editors/save_fixtures'))
        path = fixture_root / 'f0/UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
        retail = ROOT / 'extracted/ESPN NFL 2K5 (USA)'
        if not path.is_file() or not (retail / 'vc_53450030/0').is_file():
            self.skipTest(f'Private save/retail fixture missing: {path}, {retail}')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         '56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8')
        original = rr.load_image(retail).to_body()
        # Only a sub-megabyte generated archive containing the real roster is written.
        self.disc = image_fixture(self.root, original).path
        self.panel._facade.source_path = self.disc
        source = importer.load_save(path)
        self.assertEqual(len(source.players), 2547)
        self.assertFalse(rr.edits_document(source)['edits'])
        self.panel.load_document(source, kind='save', source=path)
        build = BuildPanel()
        self.addCleanup(build.deleteLater)
        self.addCleanup(build._hires_budget_timer.stop)
        self.panel.roster_edits_changed.connect(build.set_roster_edits)
        with patch.object(self.module.QFileDialog, 'getSaveFileName', return_value=(str(self.output), '')), \
             patch.object(self.module, 'QMessageBox', Mock()) as box:
            self.panel.save_roster_to_disc_button.click()
        box.warning.assert_not_called()
        self.assertEqual(build.plan().roster_edits, str(self.output))
        receipt = rr.apply(self.disc, build.plan().roster_edits)
        self.assertEqual(receipt['log'], [])
        target = rr.load_image(self.disc)
        # c2's final commentary pass repairs stale numbers and absent name cues.
        # Every other carried field, and every other player's ID, stays exact.
        canonical_pbp = {
            1700: 9033,  # Nathan Jones: 9027 -> 9033
            1715: 9048,  # Andre Sommersell: 9093 -> 9048
            1850: 9079,  # Christian Ferrara: 9099 -> 9079
            1862: 9637,  # Robert Tate: 971 -> 9637
            1867: 9056,  # Deon Humphrey: 3787 -> 9056
            1893: 9459,  # Leonard Stephens: 4906 -> 9459
            1898: 9048,  # Lenny Williams: 9024 -> 9048
            1904: 9598,  # Moran Norris: 0 -> 9598
            1906: 9057,  # Colby Bockwoldt: 9051 -> 9057
            2118: 9097,  # Martin Zdyrko: 9783 -> 9097
        }
        for src, dst in zip(source.players, target.players):
            self.assertEqual((src.first, src.last, src.college), (dst.first, dst.last, dst.college))
            for field in importer.CARRIED_FIELDS:
                expected = src.record.get(field)
                if field == 'pbp_id' and src.pool == 'primary':
                    expected = canonical_pbp.get(src.index, expected)
                self.assertEqual(expected, dst.record.get(field), (src.index, field))
        for src, dst in zip(source.teams, target.teams):
            self.assertEqual([source.by_offset[o].index for o in src.slots],
                             [target.by_offset[o].index for o in dst.slots])
        first = target.to_body()
        rr.apply(self.disc, build.plan().roster_edits)
        self.assertEqual(rr.load_image(self.disc).to_body(), first)
        self.assertEqual(rr.load_image(retail).to_body(), original)

    def test_tools_action_picks_file_and_result_dialog_contains_counts_and_skips(self):
        self.load('disc')
        box = Mock()
        with patch.object(self.module.QFileDialog, 'getOpenFileName', return_value=(str(self.path), '')) as choose, \
             patch.object(self.module.QFileDialog, 'getSaveFileName', return_value=(str(self.output), '')), \
             patch.object(self.module, 'QMessageBox', Mock(return_value=box)):
            self.panel.save_roster_to_disc_action.trigger()
        choose.assert_called_once()
        box.setText.assert_called_once()
        self.assertIn('Roster prepared:', box.setText.call_args.args[0])
        self.assertIn('"skipped":', box.setDetailedText.call_args.args[0])
        self.assertIn('"teams":', box.setDetailedText.call_args.args[0])
        self.assertEqual(self.panel._source_kind, 'disc')

    def test_cancellation_and_refusal_publish_no_build_signal(self):
        self.load('disc')
        emitted = []
        self.panel.roster_edits_changed.connect(emitted.append)
        with patch.object(self.module.QFileDialog, 'getOpenFileName', return_value=('', '')):
            self.panel._use_save_roster_on_disc()
        self.assertEqual(emitted, [])
        self.load('save')
        self.save.set_scheme('one_pool')
        with self.assertRaisesRegex(importer.SaveToDiscError, 'Position scheme mismatch'):
            self.panel.save_roster_to_disc(self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(emitted, [])
        with self.assertRaisesRegex(rr.RosterRecordError, '.json filename'):
            self.panel.save_roster_to_disc(self.path)

    def test_loaded_save_without_project_disc_prompts_for_disc_and_keeps_save(self):
        self.load('save')
        self.panel._facade = None
        with patch.object(self.module.QFileDialog, 'getOpenFileName', return_value=(str(self.disc), '')) as choose, \
             patch.object(self.module.QFileDialog, 'getSaveFileName', return_value=(str(self.output), '')), \
             patch.object(self.module, 'QMessageBox', Mock()):
            self.panel.save_roster_to_disc_button.click()
        choose.assert_called_once()
        self.assertIn('disc', choose.call_args.args[1])
        self.assertEqual(self.panel._source_kind, 'save')
        self.assertTrue(self.output.is_file())


if __name__ == '__main__':
    unittest.main()
