"""Project content/metadata races and concise, truthful build completion text."""
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).parent)]
import copy
import hashlib
import os
import threading
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from mod_editor.core.errors import ValidationError
from mod_editor.core.nfl2k5_build_service import BuildResult
from mod_editor.studio.facade import Nfl2k5StudioFacade, _project_open_hash
from mod_editor.studio.project_archive import project_target_identity
from test_studio_facade import _Session


class DiagnosticsTests(unittest.TestCase):
    def test_open_detects_content_size_mtime_and_deleted_path_and_keeps_active_session(self):
        for mode in ('content', 'size', 'mtime', 'deleted'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as folder:
                path = Path(folder).resolve() / 'named.2k5mod'
                path.write_bytes(b'original')
                before = project_target_identity(path)
                before_hash = hashlib.sha256(b'original').hexdigest()
                facade = object.__new__(Nfl2k5StudioFacade)
                facade._lock = threading.RLock()
                facade._cache = object()
                active = object()
                facade._session = active
                facade._text_catalog = facade._audio_service = None
                facade._crib_catalog = facade._crib_io = None
                facade._stadium_cache_result = None
                facade._uniform_catalog = SimpleNamespace()
                facade._attach_visual_catalog = lambda candidate: None
                candidate = _Session(facade._cache, None)
                def load(source):
                    if mode == 'content':
                        source.write_bytes(b'altered!')
                        os.utime(source, ns=(before.modified_ns, before.modified_ns))
                    elif mode == 'size':
                        source.write_bytes(b'larger replacement')
                    elif mode == 'mtime':
                        os.utime(source, ns=(before.modified_ns, before.modified_ns+10000000))
                    else:
                        source.unlink()
                    return 1
                candidate.load_shareable_project = load
                facade.session_factory = lambda cache, catalog: candidate
                with self.assertRaises(ValidationError) as caught:
                    facade.load_project(path, lambda *args: None)
                message = str(caught.exception)
                for value in (str(path), before_hash, 'size 8', f'mtime_ns {before.modified_ns}',
                              'Before:', 'After:', 'Finish saving or syncing'):
                    self.assertIn(value, message)
                if mode != 'deleted':
                    after = project_target_identity(path)
                    self.assertIn(f'size {after.size}', message)
                    self.assertIn(f'mtime_ns {after.modified_ns}', message)
                    self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), message)
                else:
                    self.assertIn('SHA-256 unavailable', message)
                self.assertIs(facade._session, active)
                self.assertTrue(candidate.discarded)
                print('B70 OPEN REFUSAL', mode, message, flush=True)

    def test_protected_completion_snippets_use_the_shared_summary(self):
        import inspect
        import textwrap
        from mod_editor.gui import studio_qt
        from mod_editor.core import build_feedback
        root = Path(__file__).resolve().parents[2]
        wiring = (root / 'WIRING_B70_T1.md').read_text(encoding='utf-8')  # the archived T1 wiring; WIRING.md belongs to the current job
        snippet = wiring.split('<!-- B70_GUI_COMPLETION -->',1)[1].split('```python\n',1)[1].split('```',1)[0]
        source = inspect.getsource(studio_qt.StudioMainWindow._choose_build_output)
        start = source.index('            kept = tuple(getattr(result, "kept_retail"')
        end = source.index('            QMessageBox.information(',start)
        namespace = dict(vars(studio_qt))
        exec(textwrap.dedent(source[:start] + snippet + source[end:]), namespace)
        rows = (dict(kind='live_number_nameplate',selector='arm:1',family='arm',digit=1,
                     asset_code='26',side='A',variant=0,shortfall_bytes=42,
                     suggestion=dict(width=32,height=32,colours=16),message='old wall '*20),)
        result = BuildResult(Path('out.iso'),100,'a'*64,1,20,kept_retail=rows)
        fake = SimpleNamespace(_build_panel=None, _refuse_while_audio_busy=lambda *args:False,
                              _set_status=lambda *args:None, _refresh_edit_state=lambda:None)
        fake._start_task = lambda operation, success, **kwargs: success(result)
        with patch.object(studio_qt.QFileDialog, 'getSaveFileName', return_value=('out.iso','')), \
             patch.object(studio_qt.QMessageBox, 'information') as dialog:
            namespace['_choose_build_output'](fake)
        body = dialog.call_args.args[2]
        self.assertIn('42 bytes over; 32 x 32 at 16 colours fits',body)
        self.assertNotIn('old wall',body)
        snippet = wiring.split('<!-- B70_BUILD_COMPLETION -->',1)[1].split('```python\n',1)[1].split('```',1)[0]
        namespace = dict(vars(build_feedback))
        exec(snippet,namespace)
        receipt = dict(outcome=dict(status='changed',message='Measured changed bytes.'),
                       steps=[dict(kept_retail=list(rows))])
        saved = copy.deepcopy(receipt)
        title,body = namespace['completion'](receipt)
        self.assertEqual(title,'Disc ready')
        self.assertIn('42 bytes over; 32 x 32 at 16 colours fits',body)
        self.assertNotIn('old wall',body)
        self.assertEqual(receipt,saved)

    def test_project_hash_opens_in_binary_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bytes.2k5mod'
            payload = b'\r\n\x1a' * 123
            path.write_bytes(payload)
            original = os.open
            flags_seen = []
            binary = 0x80000000
            def checked(path, flags, *args, **kwargs):
                flags_seen.append(flags)
                return original(path, flags & ~binary, *args, **kwargs)
            with patch.object(os, 'O_BINARY', binary, create=True), patch.object(os, 'open', checked):
                self.assertEqual(_project_open_hash(path), hashlib.sha256(payload).hexdigest())
            self.assertTrue(all(flags & binary for flags in flags_seen))

    def test_nine_digit_rows_are_one_line_each_and_detail_receipt_stays_exact(self):
        rows = []
        for family, digits in [('arm',range(1,6)),('jersey',range(1,5))]:
            for digit in digits:
                rows.append(dict(kind='live_number_nameplate', selector=f'{family}:{digit}',
                    family=f'{family} digit {digit}', asset_code='26', side='A', variant=0,
                    outcome='kept_retail', shortfall_bytes=27+digit, suggestion=dict(width=32,height=32,colours=16),
                    message='the authored digit could not fit after cleanup ' * 8,
                    fit_attempts=[dict(result='vc_lz_overflow', maximum_palette_entries=16)]))
        original = copy.deepcopy(rows)
        # Repeated diagnostics for the same asset collapse; separate digits do not.
        result = BuildResult(Path('out.iso'),100,'a'*64,9,20,
                             kept_retail=tuple(rows+[rows[0]]))
        summary = result.message
        self.assertEqual(summary.count('kept retail;'),9)
        self.assertEqual(summary.count('Edit the named asset'),1)
        self.assertNotIn('after cleanup',summary)
        for family,digits in [('arm',range(1,6)),('jersey',range(1,5))]:
            for digit in digits:
                self.assertIn(f'Uniforms / {family} digit {digit} / 26A0 / texture {family}:{digit}:',summary)
                self.assertIn(f'{27+digit} bytes over; 32 x 32 at 16 colours fits.',summary)
        self.assertEqual(rows,original)
        print('B70 BUILD SUMMARY\n'+summary,flush=True)

    def test_equipment_suggestion_and_historical_unmeasured_digits_are_not_conflated(self):
        from mod_editor.core.nfl2k5_uniform_equipment_writer import EquipmentFitError
        failure = EquipmentFitError(464,666,(),dict(asset_id='sock',width=16,height=16,colours=2))
        rows=(dict(kind='uniform_equipment_texture',asset_id='sock',set_selector='26A0',family='Socks',
                   shortfall_bytes=failure.required-failure.budget,suggestion=failure.suggestion),
              dict(kind='live_number_nameplate',selector='digit:1',family='Arm',asset_code='26',side='A',variant=0))
        result=BuildResult(Path('out.iso'),100,'a'*64,2,20,kept_retail=rows)
        self.assertIn('202 bytes over; 16 x 16 at 2 colours fits',result.message)
        self.assertIn('byte shortfall unmeasured; no checked size/colour retry',result.message)


if __name__ == '__main__': unittest.main()
