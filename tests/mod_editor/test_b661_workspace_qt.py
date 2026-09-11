"""First-page completion and bounded UI delivery with a real StudioMainWindow."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")
from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt5.QtCore import QEvent, QTimer
from mod_editor.gui import studio_qt as shell
from mod_editor.gui.stall_watchdog import StallWatchdog, install_stall_watchdog
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.session import StudioSession
from mod_editor.core import studio_inspection
from test_b661_kit_build import synthetic_catalog
from tests.mod_editor.test_team_kit_bundle import _PngAssetIO
from mod_editor.studio.uniform_bundle import TEAM_KIT_MANIFEST
from nfl_txtr import encode_rgba_png
import b661_wiring

b661_wiring.install(shell)


class SyntheticSourceFacade(Nfl2k5StudioFacade):
    """Tiny source stand-in; the session, facade getters and previews stay real."""
    def __init__(self, root, catalog):
        super().__init__(uniform_catalog=catalog, xemu_command=())
        self.test_root = root

    @property
    def models_source_paths(self):
        return None

    def load_source(self, path, progress):
        cache = SimpleNamespace(source=SimpleNamespace(selected_path=path, sha256="a"*64),
                                root=self.test_root / "cache")
        with patch("mod_editor.studio.session.Nfl2k5ProductVisualIO", _PngAssetIO):
            session = StudioSession(cache, self.uniform_catalog, root=self.test_root / "sessions")
        session.attach_visual_catalog(self.uniform_catalog)
        with self._lock:
            self._cache, self._session = cache, session
            self._source_name = path.name
        return SimpleNamespace(message="Synthetic disc opened")

    def uniform_colors(self, selector, progress):
        return "FF000000", "FF000000", False


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def pump_until(self, predicate, timeout=5):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.002)
        self.assertTrue(predicate(), "Qt result did not arrive")

    def test_uniforms_first_cold_and_cached_without_navigation_and_no_stall(self):
        for cached in (False, True):
            with self.subTest(cached=cached), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / "synthetic.iso"
                source.write_bytes(b"synthetic source, no retail assets")
                catalog = synthetic_catalog()
                facade = SyntheticSourceFacade(root, catalog)
                window = shell.StudioMainWindow(facade=facade, offer_recovery=False,
                                               uniform_catalog=catalog if cached else None)
                errors = []
                window._show_error = errors.append
                window.show()
                self.app.processEvents()
                watch = StallWatchdog(window)
                entered, release = threading.Event(), threading.Event()
                def prepare():
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("test did not release catalog preparation")
                    return catalog
                try:
                    with patch.object(QMessageBox, "warning", return_value=QMessageBox.Ok), \
                         patch.object(studio_inspection, "inspect_source", return_value={}), \
                         patch.object(shell, "load_nfl2k5_uniform_catalog", prepare):
                        window._load_source_path(source)
                        self.pump_until(lambda: not window._blocking)
                        self.assertTrue(facade.source_ready, errors)
                        row = 1
                        placeholder = window.pages.widget(row)
                        window.navigation.setCurrentRow(row)
                        if not cached:
                            self.pump_until(entered.is_set)
                            placeholder.findChild(QTimer).setInterval(20)
                            # A slow preparation must leave event delivery alive.
                            deadline = time.monotonic()+.3
                            while time.monotonic() < deadline:
                                self.app.processEvents()
                                time.sleep(.002)
                            self.assertIs(window.pages.widget(row), placeholder)
                            from PyQt5.QtWidgets import QLabel
                            self.assertIn(" s", placeholder.findChild(QLabel).text())
                        release.set()
                        self.pump_until(lambda: window.pages.widget(row) is not placeholder)
                        self.pump_until(lambda: not window._workers)
                        watch.beat()
                        self.assertEqual(window.navigation.currentRow(), row)
                        self.assertEqual(window.pages.currentIndex(), row)
                        self.assertGreater(window.uniform_list.count(), 0)
                        self.assertIsNotNone(window.preview._pixmap)
                        self.assertFalse(errors, errors)
                        self.assertLess(watch.max_gap, .25, list(watch.stalls))
                        print(f"uniforms_first cached={cached} max_ui_gap={watch.max_gap:.3f}s")
                finally:
                    release.set()
                    watch.stop()
                    window.thread_pool.waitForDone(5000)
                    window.deleteLater()
                    self.app.sendPostedEvents(None, QEvent.DeferredDelete)
                    self.app.processEvents()

    def test_cold_preview_does_not_hold_the_ui_state_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            facade = SyntheticSourceFacade(root, synthetic_catalog())
            facade.load_source(root / "disc.iso", lambda *a: None)
            asset = facade.uniform_catalog.assets[0]
            entered, release = threading.Event(), threading.Event()
            original = facade._session.asset_io.ensure_original
            def decode(row):
                entered.set()
                release.wait(3)
                return original(row)
            with patch.object(facade._session.asset_io, "ensure_original", decode):
                thread = threading.Thread(target=lambda: facade.preview_asset(asset, lambda *a: None))
                thread.start()
                try:
                    self.assertTrue(entered.wait(1))
                    # Another thread releases the decoder if a regression deadlocks
                    # this getter, so failure is bounded and preserves its evidence.
                    timer = threading.Timer(.5, release.set)
                    timer.start()
                    start = time.monotonic()
                    self.assertTrue(facade.source_ready)
                    self.assertEqual(facade.modified_count, 0)
                    self.assertLess(time.monotonic()-start, .1)
                    timer.cancel()
                finally:
                    release.set()
                    thread.join(3)

    def test_failed_preparation_replaces_loading_text_and_can_retry(self):
        from PyQt5.QtWidgets import QLabel, QPushButton
        window = shell.StudioMainWindow(offer_recovery=False)
        try:
            with patch.object(shell, "load_nfl2k5_uniform_catalog", side_effect=ValueError("synthetic failure")):
                window.navigation.setCurrentRow(1)
                self.pump_until(lambda: not window._workers)
            placeholder = window.pages.widget(1)
            self.assertIn("synthetic failure", placeholder.findChild(QLabel).text())
            retry = placeholder.findChild(QPushButton)
            self.assertIsNotNone(retry)
            with patch.object(shell, "load_nfl2k5_uniform_catalog", return_value=synthetic_catalog()):
                retry.click()
                self.pump_until(lambda: not window._workers)
            self.assertIsNot(window.pages.widget(1), placeholder)
            self.assertEqual(window.pages.currentIndex(), 1)
        finally:
            window.thread_pool.waitForDone(5000)
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_preparation_finishes_while_another_page_stays_selected(self):
        entered, release = threading.Event(), threading.Event()
        window = shell.StudioMainWindow(offer_recovery=False)
        def prepare():
            entered.set()
            if not release.wait(3):
                raise RuntimeError("test did not release preparation")
            return synthetic_catalog()
        try:
            with patch.object(shell, "load_nfl2k5_uniform_catalog", prepare):
                placeholder = window.pages.widget(1)
                window.navigation.setCurrentRow(1)
                self.pump_until(entered.is_set)
                window.navigation.setCurrentRow(0)
                release.set()
                self.pump_until(lambda: not window._workers)
            self.assertIsNot(window.pages.widget(1), placeholder)
            self.assertEqual(window.pages.currentIndex(), 0)
            window.navigation.setCurrentRow(1)
            self.assertGreater(window.uniform_list.count(), 0)
        finally:
            release.set()
            window.thread_pool.waitForDone(5000)
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_colour_preparation_does_not_hold_the_ui_state_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            facade = SyntheticSourceFacade(Path(folder), synthetic_catalog())
            facade.load_source(Path(folder) / "disc.iso", lambda *a: None)
            entered, release = threading.Event(), threading.Event()
            def read(_selector):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("test did not release colour reading")
                return "FF000000", "FF000000", False
            with patch.object(facade._session, "uniform_colors", read):
                thread = threading.Thread(target=lambda: Nfl2k5StudioFacade.uniform_colors(
                    facade, "18H0", lambda *a: None))
                thread.start()
                try:
                    self.assertTrue(entered.wait(1))
                    timer = threading.Timer(.5, release.set)
                    timer.start()
                    start = time.monotonic()
                    self.assertTrue(facade.source_ready)
                    self.assertLess(time.monotonic() - start, .1)
                    timer.cancel()
                finally:
                    release.set()
                    thread.join(3)

    def test_import_button_refreshes_the_selected_component_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            catalog = synthetic_catalog()
            facade = SyntheticSourceFacade(root, catalog)
            facade.load_source(root / "disc.iso", lambda *a: None)
            window = shell.StudioMainWindow(facade=facade, uniform_catalog=catalog, offer_recovery=False)
            # This test starts with an open synthetic session; disc inspection
            # and bump-map browsing are covered by the source-open test above.
            window._sync_constructed_page = lambda: None
            try:
                window.navigation.setCurrentRow(1)
                self.pump_until(lambda: not window._workers)
                asset = window._selected_asset
                self.assertEqual(asset.kind, "torso")
                old = window.preview._pixmap.toImage().pixelColor(0, 0).getRgb()
                bundle = root / "kit"
                facade.export_team_kit_sets(("18H0",), bundle, container="folder", progress=lambda *a: None)
                manifest = json.loads((bundle / TEAM_KIT_MANIFEST).read_bytes())
                row = next(row for row in manifest["assets"] if row["asset_id"] == asset.asset_id)
                color = (202, 17, 68, 255)
                (bundle / row["path"]).write_bytes(encode_rgba_png(asset.width, asset.height,
                                                                 bytes(color)*(asset.width*asset.height)))
                window.team_kit_scope.setCurrentIndex(window.team_kit_scope.findData("HOME"))
                imported = []
                window.team_kit_imported.connect(imported.append)
                with patch.object(QFileDialog, "getExistingDirectory", return_value=str(bundle)), \
                     patch.object(QMessageBox, "exec_", return_value=QMessageBox.Ok):
                    window._choose_team_kit_import()
                    self.pump_until(lambda: bool(imported) and not window._workers)
                self.assertEqual(imported, [1])
                self.assertNotEqual(old, color)
                self.assertEqual(window.preview._pixmap.toImage().pixelColor(0,0).getRgb(), color)
                self.assertIn("Build Modded XISO", window.team_kit_receipt_summary.text())
            finally:
                window.thread_pool.waitForDone(5000)
                window.deleteLater()
                self.app.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_opt_in_watchdog_logs_a_real_block_and_python_stack(self):
        with tempfile.TemporaryDirectory() as folder:
            from PyQt5.QtWidgets import QWidget
            owner = QWidget()
            with patch.dict(os.environ, {"MOD_STUDIO_STALL_LOG": "0"}):
                self.assertIsNone(install_stall_watchdog(owner))
            path = Path(folder) / "stalls.jsonl"
            with patch.dict(os.environ, {"MOD_STUDIO_STALL_LOG": "1"}), \
                 patch("mod_editor.gui.stall_watchdog.log_directory", return_value=Path(folder)):
                watch = install_stall_watchdog(owner)
            try:
                timer = QTimer(owner)
                timer.setObjectName("synthetic-preparation")
                timer.setInterval(20)
                fired = []
                timer.timeout.connect(lambda: fired.append(True))
                timer.start()
                watch.inventory(owner)
                self.pump_until(lambda: bool(fired))
                def blocked_ui_handler():
                    time.sleep(.32)
                blocked_ui_handler()
                self.app.processEvents()
            finally:
                watch.stop()
                owner.deleteLater()
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            stalls = [row for row in rows if row["event"] == "stall"]
            self.assertEqual(len(stalls), 1)
            self.assertIn("blocked_ui_handler", stalls[0]["stack"])
            self.assertTrue(any(row["event"] == "timer-fired"
                                and row["name"] == "synthetic-preparation" for row in rows))


if __name__ == "__main__":
    unittest.main()
