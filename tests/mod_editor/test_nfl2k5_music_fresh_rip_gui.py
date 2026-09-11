"""Real-window Music-only replay of FRESH_RIP_GUI_REPLAY_2026-09-09.py.

Optional local retail witness: set NFL2K5_MUSIC_REPLAY_XISO to the pinned
retail image. It is read only; the altered rip, cache, sessions and recovery
state live in TemporaryDirectory and are removed. No audio or emulator runs.
"""
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["MOD_STUDIO_NO_UPDATE_CHECK"] = "1"


class MusicFreshRipGuiTests(unittest.TestCase):
    def test_real_window_music_and_all_stadium_slots(self):
        configured = os.environ.get("NFL2K5_MUSIC_REPLAY_XISO")
        if not configured:
            self.skipTest("Set NFL2K5_MUSIC_REPLAY_XISO to the local pinned retail XISO for the Music replay")
        retail = Path(configured).expanduser().resolve()
        if not retail.is_file():
            self.skipTest(f"Music replay retail XISO is absent: {retail}")
        try:
            from PyQt5.QtCore import Qt
            from PyQt5.QtWidgets import QApplication, QMessageBox, QTabWidget
        except ImportError:
            self.skipTest("PyQt5 is absent; real offscreen Music window requires PyQt5")
        from mod_editor.core.capabilities import CapabilityRegistryLoader
        from mod_editor.core.nfl2k5_extended_visual_catalog import load_nfl2k5_product_visual_catalog
        from mod_editor.core.nfl2k5_source_cache import Nfl2k5SourceCache, SOURCE_SHA256
        from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
        from mod_editor.core.product_catalog import build_nfl2k5_product_catalog
        from mod_editor.gui.studio_qt import StudioMainWindow
        from mod_editor.studio.facade import Nfl2k5StudioFacade
        from mod_editor.studio.session import StudioSession
        from mod_editor.studio.workspace_state import WorkspaceStateStore

        def say(message):
            print(time.strftime("%H:%M:%S"), message, flush=True)

        app = QApplication.instance() or QApplication([])
        captured = {"dialogs": [], "crashes": [], "errors": []}

        def dialog(kind):
            def record(*args, **kwargs):
                captured["dialogs"].append([kind, " | ".join(str(a) for a in args[1:3])])
                return QMessageBox.Ok
            return record

        def hook(exc_type, exc, tb):
            captured["crashes"].append("".join(traceback.format_exception(exc_type, exc, tb)))

        before = retail.stat()
        with tempfile.TemporaryDirectory(prefix="astra-music-replay-") as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            fresh = root / "fresh-rip.xiso.iso"
            say("Copying and hashing read-only retail input into a temporary fresh rip")
            digest = hashlib.sha256()
            with retail.open("rb") as source, fresh.open("xb") as destination:
                for block in iter(lambda: source.read(16 * 1024 * 1024), b""):
                    digest.update(block)
                    destination.write(block)
            self.assertEqual(digest.hexdigest(), SOURCE_SHA256, "Replay input must be the pinned retail image")
            with fresh.open("r+b") as stream:
                stream.seek(0x100)
                self.assertEqual(stream.read(16), bytes(16))
                stream.seek(0x100)
                stream.write(b"ASTRA-MUSIC-63!!")
            for kind in ("warning", "critical", "information", "question"):
                stack.enter_context(patch.object(QMessageBox, kind, side_effect=dialog(kind)))
            stack.enter_context(patch.object(
                QMessageBox, "exec_", lambda box: (
                    captured["dialogs"].append(["exec", box.windowTitle() + " | " + box.text()]),
                    QMessageBox.Ok,
                )[1],
            ))
            stack.enter_context(patch.object(sys, "excepthook", hook))
            registry = CapabilityRegistryLoader().load(allow_sample_fallback=False, check_files=False)
            uniforms = load_nfl2k5_uniform_catalog()
            visuals = load_nfl2k5_product_visual_catalog()
            facade = Nfl2k5StudioFacade(
                uniform_catalog=uniforms, visual_catalog=visuals,
                source_cache=Nfl2k5SourceCache(root / "cache"), xemu_command=(),
                session_factory=lambda cache, catalog: StudioSession(cache, catalog, root=root / "sessions"),
            )
            window = StudioMainWindow(
                facade, eager_pages=True, product_catalog=build_nfl2k5_product_catalog(registry),
                uniform_catalog=uniforms, extended_visual_catalog=visuals.extended,
                workspace_store=WorkspaceStateStore(root / "workspace-state"), offer_recovery=False,
            )
            window._show_error = captured["errors"].append

            def pump(label, timeout=900):
                started = time.monotonic()
                last_report = started
                while time.monotonic() - started < timeout:
                    app.processEvents()
                    if (not window._blocking and not window._post_blocking_continuations
                            and not window._workers):
                        for _ in range(10):
                            app.processEvents()
                            time.sleep(0.01)
                        if not window._blocking and not window._workers and not window._post_blocking_continuations:
                            say(f"{label}: settled in {time.monotonic() - started:.1f}s")
                            return
                    if time.monotonic() - last_report >= 30:
                        say(f"{label}: waiting ({time.monotonic() - started:.0f}s)")
                        last_report = time.monotonic()
                    time.sleep(0.02)
                self.fail(f"{label} did not drain its real window workers in {timeout}s")

            try:
                window.show()
                app.processEvents()
                window._load_source_path(fresh)
                pump("Open fresh rip")
                self.assertTrue(facade.source_ready, captured)
                cache = facade._cache
                self.assertNotEqual(cache.source.sha256, SOURCE_SHA256)
                self.assertEqual(cache.root.name, cache.source.sha256)
                self.assertFalse(facade.audio_editing_ready)
                say(f"Project digest: {SOURCE_SHA256}; opened/cache digest: {cache.source.sha256}")
                for row in range(window.navigation.count()):
                    if window.navigation.item(row).data(Qt.UserRole) in ("music", "audio"):
                        window.navigation.setCurrentRow(row)
                        break
                else:
                    self.fail("Music/Audio navigation row is missing")
                pump("Enter Music workspace")
                music, audio = window._music_panel, window._audio_panel
                self.assertIsNotNone(music.service, music.status.text())
                audio.error_raised.connect(captured["errors"].append)
                tabs = window.findChild(QTabWidget, "audioTabs")
                self.assertIsNotNone(tabs)
                tabs.setCurrentWidget(music)
                music.advanced.setChecked(True)
                music.pages.setCurrentWidget(music.controls)
                paired = 0
                for index, row_id in enumerate(music.visible_ids()):
                    row = music.service.catalog.get(row_id)
                    if row.twin is None:
                        continue
                    self.assertEqual((row.primary.bank.name, row.twin.bank.name), ("cribmusic", "crib22"))
                    self.assertEqual((row.primary.channels, row.twin.channels), (2, 1))
                    music.table.selectRow(index)
                    self.assertEqual(music.selected_id(), row_id)
                    for mono in (False, True):
                        music.mono.setChecked(mono)
                        # Real signal wiring to studio_qt._music_changed and
                        # AudioPanel.invalidate_audio_content/readiness.
                        music.changed.emit()
                        app.processEvents()
                    paired += 1
                self.assertEqual(paired, 59)
                pump("59 jukebox/stadium pairs and 118 Music changes")
                tabs.setCurrentWidget(audio)
                audio._show_soundtrack()
                visited = {"cribmusic": set(), "crib22": set()}
                while True:
                    for index, asset in enumerate(audio.page.assets):
                        bank = getattr(asset, "bank", None)
                        if bank is None or bank.name not in visited:
                            continue
                        audio.table.selectRow(index)
                        self.assertEqual(audio.selected_asset_id, asset.asset_id)
                        audio.invalidate_audio_content()
                        window._music_changed()
                        app.processEvents()
                        visited[bank.name].add(asset.range_index)
                    if audio.page.offset + len(audio.page.assets) >= audio.page.total:
                        break
                    audio.next_button.click()
                    app.processEvents()
                for bank, indices in visited.items():
                    self.assertEqual(indices, set(range(59)), bank)
                self.assertFalse(facade.audio_editing_ready)
                say("Selected all 59 mono stadium and 59 stereo jukebox Audio Cues ranges; readiness=False without raising")
                pump("Music refreshes")
                window._load_source_path(fresh)
                pump("Reopen fresh rip with Music instantiated")
                window._music_changed()
                pump("Music change after reopen")
                self.assertEqual(facade._cache.root, cache.root)
                self.assertFalse(facade.audio_editing_ready)
                self.assertEqual(music.player.state(), 0)
                self.assertEqual(captured, {"dialogs": [], "crashes": [], "errors": []})
            finally:
                # _music_changed marks recovery state dirty. Discard only this
                # temporary workspace at cleanup, without a save dialog.
                window._allow_close = True
                window.close()
                pump("Close replay")
                window.deleteLater()
                app.processEvents()
            self.assertEqual(captured, {"dialogs": [], "crashes": [], "errors": []})
        after = retail.stat()
        self.assertEqual((before.st_size, before.st_mtime_ns, before.st_ctime_ns),
                         (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
        say("GUI_FRESH_RIP_MUSIC_OK " + json.dumps(captured, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
