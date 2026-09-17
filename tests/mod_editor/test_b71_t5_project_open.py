"""No-encode open, durable saves, bounded fit and cancellable build regressions."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from b71_t5_project_probe import Corpus
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core import nfl2k5_equipment_lz as lz
from mod_editor.core import equipment_staging as staging
from mod_editor.core.nfl2k5_project_fit import BuildCancelled, progress_text
from mod_editor.studio import project_archive as archive
from mod_editor.core.errors import ValidationError


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_600_open_under_ten_seconds_without_encoders(self):
        corpus = Corpus(self.root)
        before = corpus.project.read_bytes()
        session = corpus.session()
        events = []
        with (corpus.context(), patch.object(writer, '_compile_group', side_effect=AssertionError('open encoded')),
              patch.object(lz, 'compress_equipment_optimal', side_effect=AssertionError('open optimal'))):
            start = time.monotonic()
            self.assertEqual(session.load_shareable_project(corpus.project, progress=lambda *args: events.append(args)), 600)
            elapsed = time.monotonic() - start
        print(f'600 replacement open: {elapsed:.6f} seconds', flush=True)
        # The regression this guards is the old open, which encoded every group: 407.8 s at beta 69,
        # 431.6 at beta 70 and 429.3 at beta 71 for this same corpus. It measures 0.65 s here and
        # 25 s on the slowest hosted Windows runner, so the ceiling is set where a slow shared
        # machine still passes and a return to encoding on open cannot. The patched encoders above
        # are what actually prove no encoding happened; this is the wall-clock backstop.
        self.assertLess(elapsed, 120)
        self.assertEqual(corpus.project.read_bytes(), before)
        self.assertEqual(events[-1][1:], (600, 600))
        self.assertTrue(all(r['fit_status'] == 'fit pending' for r in staging.cached_equipment_fit_rows(session)))

    def test_receipts_survive_save_reload_and_bind_siblings_span_and_source(self):
        corpus = Corpus(self.root, 3)
        session = corpus.session()
        with corpus.context():
            session.load_shareable_project(corpus.project)
            rows = [dict(asset_id=row.asset_id, set_selector=row.set_selector, fit_status='fits',
                         encoded_dimensions=[32,32], used_palette_entries=16, encoded_bytes=800) for row in corpus.rows]
            staging._remember_fit(session, rows)
            saved = self.root/'receipts.2k5mod'
            session.save_shareable_project(saved)
            another = corpus.session(name='again')
            with patch.object(writer, '_compile_group', side_effect=AssertionError('receipt encoded')):
                another.load_shareable_project(saved)
            self.assertEqual(staging.cached_equipment_fit_rows(another), tuple(rows))
            corpus.cache.source.sha256 = 'b'*64
            different = corpus.session(name='different-source')
            different.load_shareable_project(saved)
            self.assertTrue(all(r['fit_status'] == 'fit pending' for r in staging.cached_equipment_fit_rows(different)))
            corpus.cache.source.sha256 = 'a'*64
            span = bytearray(corpus.fixture.span)
            span[-1] ^= 1
            corpus.fixture.span = bytes(span)
            changed_span = corpus.session(name='different-span')
            changed_span.load_shareable_project(saved)
            self.assertTrue(all(r['fit_status'] == 'fit pending' for r in staging.cached_equipment_fit_rows(changed_span)))

    def test_atomic_save_order_and_failed_replace_preserves_old_archive(self):
        corpus = Corpus(self.root, 3)
        before = corpus.project.read_bytes()
        calls = []
        fsync, publish = archive.os.fsync, archive._publish_archive
        def sync(fd):
            calls.append('fsync')
            return fsync(fd)
        def fail(temporary, destination, **kwargs):
            self.assertEqual(temporary.parent, destination.parent)
            self.assertIn('fsync', calls)
            self.assertEqual(destination.read_bytes(), before)
            raise OSError('injected interruption before atomic rename')
        with patch.object(archive.os,'fsync',side_effect=sync), patch.object(archive,'_publish_archive',side_effect=fail):
            with self.assertRaisesRegex(ValidationError,'interruption'):
                archive.save_project_archive(catalog=corpus.catalog,asset_io=corpus.io(),edits=corpus.edits,
                                             destination=corpus.project,replace=True)
        self.assertEqual(corpus.project.read_bytes(),before)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_process_death_before_publish_keeps_original(self):
        corpus = Corpus(self.root, 3)
        before = corpus.project.read_bytes()
        script = """import os,sys
from pathlib import Path
from unittest.mock import patch
from mod_editor.studio import project_archive as a
with patch.object(a, '_publish_archive', side_effect=lambda *a,**k: os._exit(23)):
 a.save_project_archive(catalog=None,asset_io=None,edits=(),destination=Path(sys.argv[1]),replace=True,allow_empty=True)
"""
        result = subprocess.run([sys.executable,'-c',script,str(corpus.project)],cwd=ROOT)
        self.assertEqual(result.returncode,23)
        self.assertEqual(corpus.project.read_bytes(),before)

    def test_open_failure_never_changes_archive(self):
        corpus = Corpus(self.root, 3)
        before = corpus.project.read_bytes()
        with corpus.context(), patch.object(corpus.io, 'validate_replacement', side_effect=ValueError('PNG invalid')):
            with self.assertRaisesRegex(ValueError,'PNG invalid'):
                corpus.session().load_shareable_project(corpus.project)
        self.assertEqual(corpus.project.read_bytes(),before)

    def test_cancel_midway_through_open_preserves_saved_and_active_project(self):
        corpus = Corpus(self.root)
        before = corpus.project.read_bytes()
        session = corpus.session()
        def cancel(stage, done, total):
            if done == 300:
                raise ValidationError('Project check cancelled')
        with corpus.context(), self.assertRaisesRegex(ValidationError, 'cancelled'):
            session.load_shareable_project(corpus.project, progress=cancel)
        self.assertEqual(corpus.project.read_bytes(), before)
        self.assertEqual(list(session.iter_edits()), [])


class BuildTests(unittest.TestCase):
    def test_completed_fit_enables_explicit_save_without_saving_in_background(self):
        from mod_editor.gui.studio_qt import StudioMainWindow
        session = SimpleNamespace(_project_fit_receipts={})
        changed = []
        owner = SimpleNamespace(facade=SimpleNamespace(_session=session),
            _embedded_operation_state_changed=lambda *args:None,
            _mark_workspace_changed=lambda:changed.append(True))
        StudioMainWindow._build_operation_state_changed(owner, True)
        session._project_fit_receipts = {'a'*64: [dict(asset_id='sock',fit_status='fits')]}
        StudioMainWindow._build_operation_state_changed(owner, False)
        self.assertEqual(changed, [True])
        StudioMainWindow._build_operation_state_changed(owner, True)
        StudioMainWindow._build_operation_state_changed(owner, False)
        self.assertEqual(changed, [True])

    def test_build_receipts_for_uniform_art_bind_source_span_and_siblings(self):
        from mod_editor.core.nfl2k5_project_fit import remember_art, restore_art, art_fit_labels
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            pack=root/'pack';pack.write_bytes(b'synthetic source span')
            edits=[]
            for name in ('jersey','mud'):
                path=root/(name+'.png');path.write_bytes(name.encode())
                edits.append(SimpleNamespace(asset_id=name,replacement_path=path,
                    replacement_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            session=SimpleNamespace(cache=SimpleNamespace(pack0=root/'0',source=SimpleNamespace(sha256='a'*64)),
                                    iter_project_png_edits=lambda:iter(edits))
            archive_view=SimpleNamespace(packs=[SimpleNamespace(name='pack',path=pack,size=pack.stat().st_size)])
            record=dict(paths=[str(e.replacement_path) for e in edits],targets=[dict(pack='pack',offset=0,
                size=pack.stat().st_size,sha256=hashlib.sha256(pack.read_bytes()).hexdigest())])
            with patch.object(writer,'parse_archive',return_value=archive_view):
                remember_art(session,[record])
                saved=archive._fit_receipts(session._project_fit_receipts)
                restore_art(session,saved)
                self.assertTrue(all('checked' in v for v in art_fit_labels(session).values()))
                edits[1].replacement_sha256='b'*64
                restore_art(session,saved)
                self.assertTrue(all('pending' in v for v in art_fit_labels(session).values()))
                edits[1].replacement_sha256=hashlib.sha256(edits[1].replacement_path.read_bytes()).hexdigest()
                pack.write_bytes(b'changed source bytes')
                restore_art(session,saved)
                self.assertTrue(all('pending' in v for v in art_fit_labels(session).values()))

    def test_close_during_open_requests_cancel_without_blocking_dialog(self):
        from mod_editor.gui.studio_qt import StudioMainWindow
        owner=SimpleNamespace(_project_open_worker=SimpleNamespace(cancelled=threading.Event()),
                              _set_status=lambda message:None)
        event=SimpleNamespace(ignore=lambda:None)
        StudioMainWindow.closeEvent(owner,event)
        self.assertTrue(owner._project_open_worker.cancelled.is_set())
        self.assertTrue(owner._close_after_project_check)

    def test_qt_large_disc_progress_does_not_overflow(self):
        from PyQt5.QtCore import QCoreApplication
        from mod_editor.gui.build_panel_qt import _Task
        app=QCoreApplication.instance() or QCoreApplication([])
        task=_Task(lambda progress:progress('Copying disc image',4*1024**3,6*1024**3))
        counts=[];errors=[]
        task.signals.counts.connect(lambda *args:counts.append(args))
        task.signals.failed.connect(errors.append)
        task.run();app.processEvents()
        self.assertFalse(errors)
        self.assertEqual(counts,[(667,1000)])

    def test_cancel_stops_subprocess_and_leaves_project_unchanged(self):
        from mod_editor.core.nfl2k5_build_service import SubprocessBuildCommandRunner
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project=root/'saved.2k5mod'; project.write_bytes(b'unchanged project')
            ready=root/'ready'; late=root/'late'
            script="import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); time.sleep(30); pathlib.Path(sys.argv[2]).touch()"
            started=time.monotonic()
            def cancel():
                if ready.exists():
                    raise BuildCancelled('Build cancelled; no output was published')
            with self.assertRaises(BuildCancelled):
                SubprocessBuildCommandRunner().run([sys.executable,'-c',script,str(ready),str(late)],ROOT,poll=cancel)
            self.assertLess(time.monotonic()-started,5)
            self.assertFalse(late.exists())
            self.assertEqual(project.read_bytes(),b'unchanged project')

    def test_progress_cancel_is_not_swallowed(self):
        from mod_editor.core.nfl2k5_build_service import _emit, BuildStage
        def cancelled(event):
            raise BuildCancelled('cancelled')
        with self.assertRaises(BuildCancelled):
            _emit(cancelled,BuildStage.BUILDING,1,600,'socks00')

    def test_qt_progress_has_item_counts_and_cancel(self):
        from PyQt5.QtCore import QCoreApplication
        from mod_editor.gui.build_panel_qt import _Task
        app=QCoreApplication.instance() or QCoreApplication([])
        seen=[]
        def operation(progress):
            progress('Fitting 22H2 / socks00',2,600)
            task.cancelled.set()
            progress('Fitting 22H2 / socks00_mud',3,600)
        task=_Task(operation)
        task.signals.progress.connect(seen.append)
        errors=[]; task.signals.failed.connect(errors.append)
        task.run();app.processEvents()
        self.assertIn('socks00',seen[0]);self.assertIn('2 of 600',seen[0])
        self.assertIn('remaining',seen[0]);self.assertIn('cancelled',errors[0])

    def test_one_optimal_attempt_per_physical_item_and_cached_miss(self):
        from test_nfl2k5_equipment_import import EquipmentSessionTests
        h=EquipmentSessionTests();h.setUp()
        try:
            _, png=h.f.png(independent=True)
            writer._PARSE_CACHE.clear()
            with h.f.context(), patch.object(lz,'compress_equipment_optimal',wraps=lz.compress_equipment_optimal) as optimal:
                try:
                    writer.build_unified_uniform_equipment_imports(h.cache.pack0,[(h.asset.asset_id,png)],preflight_only=True)
                except writer.EquipmentRefitError:
                    pass
                first=optimal.call_count
                self.assertLessEqual(first,1)
                try:
                    writer.build_unified_uniform_equipment_imports(h.cache.pack0,[(h.asset.asset_id,png)],preflight_only=True)
                except writer.EquipmentRefitError:
                    pass
                self.assertEqual(optimal.call_count,first)
        finally:h.doCleanups()

    def test_optimal_timeout_python_and_helper(self):
        data=bytes(range(256))*1024
        with patch.object(lz,'_optimal_helper',return_value=None):
            start=time.monotonic()
            with self.assertRaises(lz.EquipmentSearchTimeout):
                lz.compress_equipment_optimal(data,stream_tag=1,offset_bits=12,max_encoded_size=1024*1024,timeout=.001)
            self.assertLess(time.monotonic()-start,.1)
        with (patch.object(lz,'_optimal_helper',return_value=Path('fake-helper')),
              patch.object(lz.subprocess,'run',side_effect=subprocess.TimeoutExpired('helper',.001)) as helper):
            with self.assertRaises(lz.EquipmentSearchTimeout):
                lz.compress_equipment_optimal(data,stream_tag=1,offset_bits=12,max_encoded_size=1024*1024,timeout=.001)
            self.assertEqual(helper.call_count,1)

    def test_failed_fit_survives_memory_cache_clear_without_another_optimal(self):
        from test_b69_j1_fit import tight_fixture
        with tempfile.TemporaryDirectory() as folder:
            fixture, rgba = tight_fixture(Path(folder))
            edit = fixture.png(rgba=rgba)
            with self.assertRaises(writer.EquipmentFitError) as first:
                fixture.build([edit])
            writer._STAGED_CACHE.clear()
            writer._PARSE_CACHE.clear()
            with patch.object(writer, '_compile_group', side_effect=AssertionError('failed fit recompressed')):
                with self.assertRaises(writer.EquipmentFitError) as second:
                    fixture.build([edit])
            self.assertEqual(str(second.exception), str(first.exception))


if __name__ == '__main__':
    unittest.main()
