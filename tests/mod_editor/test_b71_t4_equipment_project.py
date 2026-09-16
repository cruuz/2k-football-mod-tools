"""Project recovery and refit through real session, facade and offscreen UI paths."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import test_nfl2k5_equipment_import as equipment_fixture
from test_b69_j1_fit import tight_fixture
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core import equipment_staging as staging
from mod_editor.core import nfl2k5_equipment_lz as lz
from mod_editor.core.equipment_reporting import project_fit_labels
from mod_editor.core.errors import ValidationError
from mod_editor.studio.facade import Nfl2k5StudioFacade
from nfl_txtr import encode_rgba_png, decompress_vc_lz, compress_vc_lz


class ProjectRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.h = equipment_fixture.EquipmentSessionTests()
        def factory(root):
            f, self.rgba = tight_fixture(root, family=4,
                names=('socks00', 'socks00_mud', 'untouched'))
            return f
        with patch('test_nfl2k5_equipment_import.Fixture', factory):
            self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.f = self.h.f
        self.normal, self.mud = self.f.rows[:2]
        _, self.png = self.f.png(rgba=self.rgba)
        _, mud_png = self.f.png(1, independent=False, rgba=bytes((90, 20, 10, 255)) * 1024)
        self.h.a.replace_batch(((self.h.assets[self.normal.asset_id], self.png),
                               (self.h.assets[self.mud.asset_id], mud_png)))
        self.originals = {e.asset_id: e.replacement_path.read_bytes() for e in self.h.a.iter_edits()}
        self.project = self.h.root / 'older.2k5mod'
        self.h.a.save_shareable_project(self.project)

    def reopen(self, name='loaded'):
        session = self.h.session(name)
        with self.f.context():
            self.assertEqual(session.load_shareable_project(self.project), 2)
        return session

    def test_loader_keeps_every_edit_and_build_names_only_failing_variant(self):
        session = self.reopen()
        self.assertEqual({e.asset_id: e.replacement_path.read_bytes() for e in session.iter_edits()}, self.originals)
        labels = project_fit_labels(session)
        self.assertIn('needs refit: Equipment art cannot fit', labels[self.normal.asset_id])
        self.assertIn('fitted at', labels[self.mud.asset_id])
        with self.f.context(), self.assertRaises(ValidationError) as caught:
            staging.require_equipment_fit(session)
        self.assertIn(self.normal.asset_id, str(caught.exception))
        self.assertNotIn(self.mud.asset_id, str(caught.exception))
        saved = self.h.root / 'retained.2k5mod'
        session.save_shareable_project(saved)
        again = self.h.session('again')
        with self.f.context():
            again.load_shareable_project(saved)
        self.assertEqual({e.asset_id: e.replacement_path.read_bytes() for e in again.iter_edits()}, self.originals)

    def test_exact_one_byte_message_is_retained_on_load(self):
        error = writer.EquipmentFitError(6784, 6785, (), required_is_lower_bound=True)
        actual = writer.build_unified_uniform_equipment_imports
        def fail_normal(index, edits, **kwargs):
            if any(key == self.normal.asset_id for key, _ in edits):
                raise error
            return actual(index, edits, **kwargs)
        with patch.object(writer, 'build_unified_uniform_equipment_imports', side_effect=fail_normal):
            session = self.reopen()
        row = next(r for r in staging.cached_equipment_fit_rows(session) if r['asset_id'] == self.normal.asset_id)
        self.assertEqual(row['fit_error'], str(error))
        self.assertIn('6,785 bytes required', row['fit_error'])
        self.assertEqual(session.modified_count, 2)

    def test_facade_adopts_loaded_project_and_reports_refit_inline(self):
        from mod_editor.studio.facade import _project_open_hash
        from mod_editor.studio.project_archive import project_target_identity
        candidate = self.h.session('facade-loaded')
        facade = Nfl2k5StudioFacade.__new__(Nfl2k5StudioFacade)
        facade._lock, facade._session, facade._cache = threading.RLock(), self.h.a, self.h.cache
        facade._require_playbook_inspector = lambda: None
        identity = project_target_identity(self.project)
        with self.f.context():
            result = facade._load_project_candidate(source=self.project, progress=lambda *args: None,
                opened_identity=identity, opened_sha256=_project_open_hash(self.project),
                cache=self.h.cache, text_catalog=None, audio_service=None, crib_catalog=None,
                crib_io=None, stadium_result=None, active_session=self.h.a, candidate=candidate)
        self.assertIs(facade._session, candidate)
        self.assertIn('Loaded 2 replacements', result.message)
        self.assertIn('needs refit', result.message)
        self.assertIn(self.normal.asset_id, result.message)
        self.assertEqual(candidate.modified_count, 2)

    def test_one_click_refit_via_facade_reports_fit_survives_save_and_undo(self):
        session = self.reopen()
        facade = Nfl2k5StudioFacade.__new__(Nfl2k5StudioFacade)
        facade._lock, facade._session = threading.RLock(), session
        attempts = []
        actual = writer.build_unified_uniform_equipment_imports
        def record(index, edits, **kwargs):
            from mod_editor.core.nfl2k5_equipment_import_intent import import_settings
            for key, path in edits:
                if Path(path).name == 'refit.png':
                    payload, rgba = session.asset_io.validate_replacement(self.h.assets[key], path)
                    attempts.append((import_settings(payload, key, rgba)[1],
                                     len({rgba[i:i+4] for i in range(0, len(rgba), 4)})))
            return actual(index, edits, **kwargs)
        with self.f.context(), patch.object(writer, 'build_unified_uniform_equipment_imports', side_effect=record):
            result = facade.refit_equipment(self.normal.asset_id, lambda *args: None)
            staging.require_equipment_fit(session)
        first_smaller = next(i for i, (scale, colours) in enumerate(attempts) if scale > 1)
        self.assertEqual(attempts[first_smaller - 1], (1, 2))
        self.assertIn('fitted at', result.message)
        self.assertIn('bytes encoded', result.message)
        self.assertEqual(result.changed_asset_ids, (self.normal.asset_id,))
        self.assertEqual(session.current_path(self.h.assets[self.mud.asset_id]).read_bytes(), self.originals[self.mud.asset_id])
        session.save_shareable_project(self.project, replace=True)
        again = self.reopen('refitted')
        self.assertNotIn('needs refit', project_fit_labels(again)[self.normal.asset_id])
        session.undo()
        self.assertEqual(session.current_path(self.h.assets[self.normal.asset_id]).read_bytes(), self.originals[self.normal.asset_id])
        self.assertIn('needs refit', project_fit_labels(session)[self.normal.asset_id])

    def test_import_fitting_mud_does_not_lose_unfitting_normal(self):
        session = self.reopen()
        _, png = self.f.png(1, independent=False, rgba=bytes((10, 60, 90, 255)) * 1024)
        with self.f.context():
            result = staging.stage_equipment_import(session, self.h.assets[self.mud.asset_id], png,
                                                     independent=False)
        self.assertEqual(result.changed_asset_ids, (self.mud.asset_id,))
        self.assertEqual(session.current_path(self.h.assets[self.normal.asset_id]).read_bytes(), self.originals[self.normal.asset_id])
        self.assertIn('needs refit', project_fit_labels(session)[self.normal.asset_id])

    def test_failed_refit_preserves_all_pixels_and_undo(self):
        session = self.reopen()
        before = session._manifest_document()
        undo = len(session._undo)
        with self.f.context(), patch.object(writer, 'build_unified_uniform_equipment_imports',
                side_effect=writer.EquipmentFitError(6784, 6785, ())), self.assertRaises(ValidationError):
            staging.refit_equipment(session, self.normal.asset_id)
        self.assertEqual(session._manifest_document(), before)
        self.assertEqual(len(session._undo), undo)
        self.assertEqual({e.asset_id: e.replacement_path.read_bytes() for e in session.iter_edits()}, self.originals)

    def test_corrupt_png_still_refuses_before_session_mutation(self):
        self.png.write_bytes(b'not a PNG')
        with self.f.context(), self.assertRaises(ValueError):
            writer.preflight_project_equipment(self.f.pack, [(None, self.normal.asset_id, self.png)])

    def test_quality_fit_error_is_also_recoverable(self):
        with patch.object(writer, 'build_unified_uniform_equipment_imports',
                          side_effect=writer.EquipmentRefitError('Cannot retain edge coverage')):
            session = self.reopen()
        self.assertTrue(all(r['fit_status'] == 'needs refit' for r in staging.cached_equipment_fit_rows(session)))

    def test_studio_button_uses_selected_item_and_worker(self):
        from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPlainTextEdit
        from mod_editor.gui.studio_qt import StudioMainWindow
        app = QApplication.instance() or QApplication([])
        session = self.reopen()
        panel = QWidget()
        layout = QVBoxLayout(panel)
        panel.project_includes_list = QPlainTextEdit(panel)
        layout.addWidget(panel.project_includes_list)
        calls = []
        owner = SimpleNamespace(facade=SimpleNamespace(_session=session,
            refit_equipment=lambda asset, progress: calls.append(asset)), _build_panel=panel,
            _blocking=False, _embedded_operation_is_busy=lambda: False)
        owner._refit_project_equipment = lambda: StudioMainWindow._refit_project_equipment(owner)
        owner._start_task = lambda worker, success, **kw: worker(lambda *args: None)
        with patch.object(writer, 'build_unified_uniform_equipment_imports',
                          side_effect=AssertionError('GUI rendering must not compile')):
            StudioMainWindow._refresh_build_includes(owner)
        self.assertIn('needs refit', panel.project_includes_list.toPlainText())
        self.assertEqual(panel.equipment_refit_choice.currentData(), self.normal.asset_id)
        panel.equipment_refit_button.click()
        self.assertEqual(calls, [self.normal.asset_id])
        panel.close()
        app.processEvents()


class OptimalPathTests(unittest.TestCase):
    def test_even_greedy_cutoff_runs_optimal_and_checks_actual_bytes(self):
        raw = b'abcabcabcd' * 80
        writer._PARSE_CACHE.clear()
        with patch.object(writer, 'compress_vc_lz', side_effect=writer.TxtrError(
                'VC-LZ stream needs more than the 100-byte bound')), \
             patch.object(lz, 'compress_equipment_optimal', wraps=lz.compress_equipment_optimal) as optimal:
            encoded, strategy = writer._cached_parse(raw, 1, 10, 100)
        self.assertEqual(strategy, 'optimal_token_parse')
        self.assertEqual(optimal.call_count, 1)
        self.assertEqual(decompress_vc_lz(encoded, len(raw))[0], raw)
        self.assertLessEqual(len(encoded), 100)

    @unittest.skipUnless(sys.platform.startswith('linux') and lz.platform.machine().lower() in ('x86_64', 'amd64'),
                         'Reviewed helper is Linux x86-64; other platforms use the bounded Python encoder')
    def test_worktree_optimal_helper_is_executable_and_executed(self):
        helper = lz._optimal_helper()
        self.assertIsNotNone(helper)
        self.assertTrue(os.access(helper, os.X_OK))
        with patch.object(lz.subprocess, 'run', wraps=lz.subprocess.run) as run:
            raw = b'abcd' * 400
            encoded = lz.compress_equipment_optimal(raw, stream_tag=1, offset_bits=10, max_encoded_size=1000)
        self.assertEqual(Path(run.call_args.args[0][0]), helper)
        self.assertEqual(decompress_vc_lz(encoded, len(raw))[0], raw)


class RetailBoundaryTests(unittest.TestCase):
    def test_22h2_greedy_6785_optimal_6764_and_beta69_beta70_project(self):
        from tools.b71_t4_equipment_probe import run
        index = ROOT / 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
        if not index.is_file():
            self.skipTest('Private NFL 2K5 retail index is absent; exact 22H2 span requires it')
        with tempfile.TemporaryDirectory(prefix='b71-t4-boundary-') as directory:
            result = run(index, Path(directory))
            self.assertEqual((result['budget'], result['greedy_bytes'], result['optimal_bytes']), (6784, 6785, 6764))
            self.assertEqual(result['beta69_palette_limit'], 2)
            self.assertIn('error', result['beta70'])
            self.assertEqual(result['beta70_without_stripe_floor']['palette_limit'], 2)
            self.assertTrue((Path(directory) / 'one-byte.2k5mod').is_file())
            self.assertTrue(result['wrapper_14_preserved'])


if __name__ == '__main__':
    unittest.main()
