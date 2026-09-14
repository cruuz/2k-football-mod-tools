"""Fast generated-data gates for byte-stable crest acceleration and cancellation."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(Path(__file__).parent)]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PIL import Image
import apf_logo_patch as writer
import apf_field_art_patch as field
import apf_inner as inner
from mod_editor.apf_studio import ps3_texture_codec as codec
from mod_editor.apf_studio import ps3_texture_bundle as bundle
from test_apf_ps3_texture_bundle import dds


def process_identity(value):
    return value, os.getpid(), writer._CREST_CHILD


def process_timeout(value):
    raise TimeoutError('crest source timed out')


class EncoderTests(unittest.TestCase):
    def test_native_greedy_preserves_candidate_limits_ties_and_all_shifts(self):
        binary = field._optimal_binary()
        if binary is None:
            self.skipTest('reviewed Linux x86-64 helper absent; portable tests still run')
        rng = random.Random(69)
        samples = (bytes(512), b'abcabcabcdefabc' * 42,
                   bytes(rng.randrange(16) for _ in range(2048)))
        for shift in range(1, 16):
            for limit in (1, 64, 128):
                for data in samples:
                    expected = writer._compress_h7a_python(data, shift, candidate_limit=limit)
                    native = subprocess.run([str(binary), str(shift), '--greedy', str(limit)],
                        input=data, capture_output=True, check=True, timeout=10).stdout
                    self.assertEqual(native, expected, (shift, limit))
                    writer.verify_h7a_stream(native, data, shift)

    def test_portable_optimal_has_identical_trials_and_hash_collision_rules(self):
        binary = field._optimal_binary()
        rng = random.Random(690)
        for shift in (2, 8, 9, 15):
            for data in (b'abcabcabc', bytes(180), bytes(rng.randrange(16) for _ in range(900))):
                expected = writer._compress_h7a_optimal_python(data, shift)
                writer.verify_h7a_stream(expected, data, shift)
                if binary is not None:
                    native = subprocess.run([str(binary), str(shift)], input=data,
                        capture_output=True, check=True, timeout=10).stdout
                    self.assertEqual(native, expected)
                greedy = writer._compress_h7a_python(data, shift)
                with patch.object(field, '_optimal_binary', return_value=None):
                    # Without the reviewed helper the ladder keeps beta 68's greedy bytes ...
                    self.assertEqual(writer.compress_h7a_best(data, shift, greedy=greedy), greedy)
                    # ... unless the portable optimal parse is asked for explicitly (parity checks).
                    with patch.dict(os.environ, {'APF_H7A_PYTHON_OPTIMAL': '1'}):
                        self.assertEqual(writer.compress_h7a_best(data, shift, greedy=greedy),
                                         expected if len(expected) < len(greedy) else greedy)

    def test_missing_failed_and_unsafe_helpers_use_identical_python_greedy(self):
        data = b'abc' * 2000
        expected = writer._compress_h7a_python(data, 8)
        with patch.object(field, '_optimal_binary', return_value=None):
            self.assertEqual(writer.compress_h7a(data, 8), expected)
        for failure in (OSError('no executable'), subprocess.TimeoutExpired('encoder', 180)):
            with patch.object(field, '_optimal_binary', return_value=Path('not-executed')), \
                 patch.object(writer.subprocess, 'run', side_effect=failure):
                self.assertEqual(writer.compress_h7a(data, 8), expected)
        unsafe = subprocess.CompletedProcess([], 0, b'\x08abc\x03\x03')
        with patch.object(field, '_optimal_binary', return_value=Path('not-executed')), \
             patch.object(writer.subprocess, 'run', return_value=unsafe):
            self.assertEqual(writer.compress_h7a(data, 8), expected)

    def test_helper_drift_is_never_executed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'helper'
            path.write_bytes(b'wrong helper')
            path.chmod(0o755)
            with patch.object(field, '_OPTIMAL_BINARY', path):
                self.assertIsNone(field._optimal_binary())

    def test_optimal_timeout_and_bad_output_keep_portable_bytes(self):
        data = bytes(random.Random(69).choices(range(4), k=512))
        greedy = writer._compress_h7a_python(data, 8)
        optimal = writer._compress_h7a_optimal_python(data, 8)
        expected = optimal if len(optimal) < len(greedy) else greedy
        for failure in (subprocess.TimeoutExpired('encoder', 180), OSError('cannot execute')):
            with patch.object(field, '_optimal_binary', return_value=Path('not-executed')), \
                 patch.object(writer.subprocess, 'run', side_effect=failure):
                self.assertEqual(writer.compress_h7a_best(data, 8, greedy=greedy), greedy)
                with patch.dict(os.environ, {'APF_H7A_PYTHON_OPTIMAL': '1'}):
                    self.assertEqual(writer.compress_h7a_best(data, 8, greedy=greedy), expected)
        with patch.object(field, '_optimal_binary', return_value=Path('not-executed')), \
             patch.object(writer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'bad')), \
             patch.dict(os.environ, {'APF_H7A_PYTHON_OPTIMAL': '1'}):
            self.assertEqual(writer.compress_h7a_best(data, 8, greedy=greedy), expected)


class CacheAndWorkerTests(unittest.TestCase):
    def test_worker_timeout_is_propagated_without_polling_forever(self):
        with patch.object(writer, 'crest_worker_count', return_value=2):
            with self.assertRaisesRegex(TimeoutError, 'crest source timed out'):
                list(writer.ordered_crest_map(process_timeout, (1, 2)))

    def test_pixel_transport_matches_independent_untile_with_all_endian_modes(self):
        from test_apf_crest_fit import synthetic_package
        metadata = dict(synthetic_package()[-1][0].metadata)
        pixels = random.Random(6910).randbytes(512 * 512 * 4)
        expected = bytes(((v * 15 + 127) // 255) * 17 for v in pixels)
        for mode in (0, 1, 2, 3):
            metadata['endianness'] = mode
            encoded = writer.encode_4444_base(metadata, pixels)
            self.assertEqual(writer.decode_4444_base(metadata, encoded), expected)
        metadata['endianness'] = 1
        encoded = writer.encode_4444_base(metadata, pixels)
        linear = inner._endian_swap(inner._untile_2d(encoded, 512, 512, 512, 1, 1, 2), 1)
        import struct
        oracle = b''.join(bytes(inner._swizzle_pixel(tuple(((word[0] >> (4 * c)) & 15) * 17
            for c in range(4)), metadata['swizzle_components'])) for word in struct.iter_unpack('<H', linear))
        self.assertEqual(writer.decode_4444_base(metadata, encoded), oracle)

    def test_cancelled_staging_rolls_back_its_completed_crest(self):
        from test_apf_crest_budget_import import inputs
        from types import SimpleNamespace
        source, slots, measurements = inputs()
        plan = bundle.build_plan(source, slots, measurements=measurements)
        event, edits, undone = threading.Event(), [], []
        def stage(*_, **__):
            edits.append('crest')
            event.set()
            return 'crest'
        def undo():
            undone.append(edits.pop())
        session = SimpleNamespace(source=SimpleNamespace(index_0a=Path('synthetic')),
            modifications=(), replace_helmet_crest_design=stage, undo=undo)
        with patch.object(bundle, 'destination_slots', return_value=slots), \
             patch.object(bundle, 'measure_bundle_logos', return_value=measurements):
            with self.assertRaisesRegex(bundle.BundleError, 'cancelled'):
                bundle.stage_plan(session, plan, cancelled=event.is_set)
        self.assertEqual(edits, [])
        self.assertEqual(undone, ['crest'])

    def test_decoded_sources_are_content_keyed_and_never_share_mutable_images(self):
        codec._DECODED_SOURCES.clear()
        data = dds((17, 34, 51, 68), (4, 4))
        first = codec.decode_source(data, 'dds')
        first.putpixel((0, 0), (255, 0, 0, 0))
        with patch.object(codec, 'decode_dds', side_effect=AssertionError('decode repeated')):
            second = codec.decode_source(data, 'dds')
        self.assertEqual(second.getpixel((0, 0)), (17, 34, 51, 68))
        self.assertNotEqual(codec.decode_source(dds((0, 0, 0, 0), (4, 4)), 'dds').tobytes(), second.tobytes())

    def test_processes_return_in_input_order_and_do_not_nest(self):
        with patch.object(writer, 'crest_worker_count', return_value=2):
            rows = list(writer.ordered_crest_map(process_identity, (9, 2, 7)))
        self.assertEqual([row[0] for row in rows], [9, 2, 7])
        self.assertTrue(all(pid != os.getpid() and child for _, pid, child in rows))

    def test_cancel_before_and_between_crests_has_no_later_result(self):
        with self.assertRaisesRegex(writer.PatchError, 'cancelled'):
            list(writer.ordered_crest_map(process_identity, (1, 2), cancelled=lambda: True))
        event, calls = threading.Event(), []
        def one(value):
            calls.append(value)
            return value
        def progress(*_):
            event.set()
        with patch.object(writer, 'crest_worker_count', return_value=1):
            with self.assertRaisesRegex(writer.PatchError, 'cancelled'):
                list(writer.ordered_crest_map(one, (1, 2, 3), progress=progress, cancelled=event.is_set))
        self.assertEqual(calls, [1])

    def test_single_crest_mips_can_use_the_shared_pool_without_changing_bytes(self):
        from test_apf_crest_fit import synthetic_package
        layer = synthetic_package()[-1][0]
        pixels = Image.new('RGBA', (512, 512), (17, 34, 51, 136)).tobytes()
        expected = writer.rebuild_mip_tail(layer.metadata, pixels, layer.mip_tail)
        writer._PIXEL_CACHE.clear()
        with patch.object(writer, 'crest_worker_count', return_value=2), writer.crest_pool(2):
            actual = writer.rebuild_mip_tail(layer.metadata, pixels, layer.mip_tail)
        self.assertEqual(actual, expected)


class GuiWorkerTests(unittest.TestCase):
    def test_qt_timer_runs_during_worker_and_cancel_reaches_safe_boundary(self):
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QApplication, QWidget, QProgressDialog
        from mod_editor.apf_studio.gui import _BackgroundTask
        from mod_editor.apf_studio.ps3_texture_bundle_qt import run_crest_task
        from PyQt5.QtCore import QThreadPool
        app = QApplication.instance() or QApplication([])
        parent = QWidget()
        pool = QThreadPool()
        tasks, completed, ticks, threads = [], [], [], []
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        def runner(label, operation, success, blocking):
            task = _BackgroundTask(operation)
            tasks.append(task)
            task.signals.succeeded.connect(success)
            pool.start(task)
            return True
        def work(progress):
            threads.append(threading.get_ident())
            while not progress.cancelled():
                time.sleep(0.005)
            raise bundle.BundleError('cancelled')
        timer.start()
        run_crest_task(parent, runner, 'Testing crest worker', work, completed.append)
        deadline = time.monotonic() + 3
        while len(ticks) < 4 and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.001)
        dialogs = parent.findChildren(QProgressDialog)
        self.assertEqual(len(dialogs), 1)
        dialogs[0].canceled.emit()
        while pool.activeThreadCount() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.001)
        app.processEvents()
        timer.stop()
        parent.close()
        self.assertGreaterEqual(len(ticks), 4)
        self.assertNotEqual(threads, [threading.get_ident()])
        self.assertEqual(completed, [])
        self.assertEqual(pool.activeThreadCount(), 0)


if __name__ == '__main__':
    unittest.main()
