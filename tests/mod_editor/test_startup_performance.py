"""Lazy page entry points, metadata caches and quiet worker progress."""
from __future__ import annotations
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from mod_editor.gui import studio_qt as shell
from mod_editor.gui.build_panel_qt import _Task
from mod_editor.core import metadata_cache
from mod_editor.core.nfl2k5_extended_visual_catalog import ExtendedVisualAsset, VisualWriterRoute, Nfl2k5ExtendedVisualCatalog, VisualReportPaths


def assets(count):
    return tuple(ExtendedVisualAsset(f'id:{i}', f'Texture {i}', 'Equipment', 'p8_texture',
                 f'target:{i}',64,64,VisualWriterRoute.UNIFIED_VISUAL,'test') for i in range(count))


class StartupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self, **kwargs):
        window = shell.StudioMainWindow(**kwargs)
        window._start_automatic_update_check = lambda: None
        self.addCleanup(window.deleteLater)
        return window

    def test_default_constructor_does_not_load_catalogs_or_build_options(self):
        with mock.patch.object(shell,'load_nfl2k5_uniform_catalog',side_effect=AssertionError('eager uniforms')), \
             mock.patch.object(shell,'load_nfl2k5_extended_visual_catalog',side_effect=AssertionError('eager visuals')), \
             mock.patch.object(shell.mod_build,'availability',side_effect=AssertionError('eager CSVs')):
            window = self.make_window()
            window.show()
            self.app.processEvents()
        self.assertEqual(window.pages.count(),window.navigation.count())
        self.assertIsNone(window._build_panel)
        self.assertIsNone(window._scorebar_panel)
        self.assertFalse(window._visual_browsers)

    def test_explicit_open_constructs_one_page_once_and_keeps_row_numbers(self):
        rows=assets(80)
        catalog=Nfl2k5ExtendedVisualCatalog(rows,VisualReportPaths())
        window=self.make_window(extended_visual_catalog=catalog)
        page=window.open_workspace('textures')
        self.assertIs(page,window.open_workspace('textures'))
        self.assertEqual(window.pages.count(),window.navigation.count())
        self.assertEqual(window._navigation_key(window.navigation.currentRow()),'textures')
        browser=window._visual_browsers[shell.ProductCategory.TEXTURES]
        self.assertEqual(browser.asset_list.count(),80)
        browser.asset_list.setCurrentRow(60)
        self.assertEqual(browser.selected_asset_id,'id:60')
        browser.search.setText('Texture 60')
        self.assertEqual(browser.asset_list.count(),1)
        self.assertEqual(browser.asset_list.currentItem().data(Qt.UserRole),'id:60')

    def test_visual_list_does_not_create_an_icon_per_row(self):
        window=self.make_window()
        view=shell._VisualList(window)
        self.addCleanup(view.deleteLater)
        with mock.patch.object(window,'_visual_icon',wraps=window._visual_icon) as icons:
            view.set_rows(assets(40000),())
            self.assertEqual(view.count(),40000)
            self.assertEqual(icons.call_count,0)
            first=view.rows_model.index(0)
            view.rows_model.data(first,Qt.DecorationRole)
            self.assertEqual(icons.call_count,1)
        # IDs with the same abbreviation and old color seed share exact icons.
        rows=assets(100)
        for row in rows:
            window._visual_icon(row)
        self.assertLessEqual(len(window._monogram_icons),5)

    def test_navigation_can_pump_events_while_metadata_loads(self):
        gate=threading.Event();entered=threading.Event()
        catalog=Nfl2k5ExtendedVisualCatalog(assets(10),VisualReportPaths())
        def load():
            entered.set()
            gate.wait(5)
            return catalog
        window=self.make_window()
        try:
            with mock.patch.object(shell,'load_nfl2k5_extended_visual_catalog',load):
                window.navigation.setCurrentRow(12)
                self.assertTrue(entered.wait(1))
                self.app.processEvents()
                self.assertEqual(window.pages.currentIndex(),12)
                self.assertIn(12,window._page_loads)
                gate.set()
                deadline=time.monotonic()+5
                while window._workers and time.monotonic()<deadline:
                    self.app.processEvents()
                    time.sleep(.005)
            self.assertFalse(window._workers)
            self.assertEqual(window._visual_browsers[shell.ProductCategory.TEXTURES].asset_list.count(),10)
        finally:
            gate.set()
            window.thread_pool.waitForDone(5000)
            self.app.processEvents()

    def test_first_roster_navigation_prepares_build_options_without_switching_page(self):
        window = self.make_window()
        row = next(i for i in range(window.navigation.count())
                   if window._navigation_key(i) == 'rosters')
        with mock.patch.object(window, '_show_workspace') as prepare:
            window._refresh_entered_page(row)
        prepare.assert_called_once_with(window.navigation.count() - 1, select=False)
        self.assertIsNone(window._build_panel)

    def test_saving_before_build_page_keeps_existing_gameplay_choices(self):
        window = self.make_window()
        from types import SimpleNamespace
        stored = []
        window.facade = SimpleNamespace(source_ready=True,
            project_build_settings=lambda: {'catch_slider': True, 'throw': True, 'max_deep_yards': 80},
            set_project_build_settings=stored.append)
        saved = window._capture_music_build_settings()
        self.assertTrue(saved['catch_slider'])
        self.assertEqual(saved['max_deep_yards'], 80)
        self.assertEqual(stored, [saved])
        self.assertIsNone(window._build_panel)

    def test_progress_preserves_large_byte_counts_and_coalesces_storms(self):
        received=[]
        worker=shell._BackgroundTask(lambda progress: progress('Copying',5_000_000_000,6_300_000_000))
        worker.signals.progress.connect(lambda *args:received.append(args))
        worker.run()
        self.assertEqual(received,[('Copying',5_000_000_000,6_300_000_000)])
        task=_Task(lambda progress:[progress('Copying',i,10000) for i in range(10000)])
        messages=[]
        task.signals.progress.connect(messages.append)
        task.run()
        self.assertLess(len(messages),10)
        self.assertIn('100%',task.latest_progress)


class MetadataCacheTests(unittest.TestCase):
    def test_content_hash_invalidates_even_when_size_and_mtime_are_restored(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.json';cache=Path(folder)/'cache.json'
            source.write_bytes(b'first');stamp=source.stat()
            key=metadata_cache.source_key([source],'v1')
            metadata_cache.write(cache,key,[[1,'metadata only']])
            self.assertEqual(metadata_cache.read(cache,key),[[1,'metadata only']])
            source.write_bytes(b'other');os.utime(source,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            newer=metadata_cache.source_key([source],'v1')
            self.assertNotEqual(key,newer)
            self.assertIsNone(metadata_cache.read(cache,newer))
            cache.write_bytes(b'partial JSON')
            self.assertIsNone(metadata_cache.read(cache,key))


if __name__=='__main__':
    unittest.main()
