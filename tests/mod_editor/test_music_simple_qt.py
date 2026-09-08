"""Offscreen Songs UI; every playback process is stubbed and never launched."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
try:
    from PyQt5.QtCore import QMimeData, QUrl, Qt, QPointF, QPoint
    from PyQt5.QtGui import QDropEvent, QDragEnterEvent
    from PyQt5.QtWidgets import QApplication, QLabel
    from mod_editor.gui.music_panel_qt import MusicPanel
except ImportError:
    QApplication = None
from tests.mod_editor.music_fixtures import MusicDisc, music_session, wav_bytes
from tests.mod_editor.test_music_simple import tone, mp3


@unittest.skipUnless(QApplication is not None, 'PyQt5 absent; offscreen Add songs tests unavailable')
class SongsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.disc = MusicDisc(self.root)
        self.service, _ = music_session(self.root, self.disc)
        self.panel = MusicPanel(self.service)
        self.panel.resize(1060, 700)
        self.panel.show()
        self.wav = tone(self.root/'Friday Night.wav', frames=1025)
        self.events = []
        self.panel.library_changed.connect(self.events.append)

    def tearDown(self):
        self.panel.close()
        self.drain()
        self.panel.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def drain(self):
        deadline = time.monotonic()+30
        while self.panel.operation_in_progress and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()
        self.assertFalse(self.panel.operation_in_progress, 'Song worker did not finish')

    def add(self, paths=None):
        self.panel.add_songs(paths or [self.wav])
        self.drain()
        self.assertTrue(self.service.library_songs(), self.panel.status.text())

    def test_default_plain_page_add_button_multi_select_and_build_signal(self):
        self.assertEqual(self.panel.pages.tabText(self.panel.pages.currentIndex()), 'Songs')
        self.assertFalse(self.panel.pages.isTabVisible(1))
        self.assertEqual(self.panel.songs_table.rowCount(), 66)
        with patch('mod_editor.gui.music_panel_qt.QFileDialog.getOpenFileNames', return_value=([str(self.wav)]*2, '')) as choose:
            self.panel.add_songs_button.click()
            self.drain()
        self.assertIn('*.m4a', choose.call_args.args[3])
        self.assertEqual(self.panel.songs_table.rowCount(), 68)
        self.assertEqual(self.panel.songs_table.item(66, 2).text(), 'yours')
        self.assertEqual(self.panel.songs_table.item(66, 0).text(), 'Friday Night')
        self.assertEqual(self.panel.songs_summary.text(), '2 of your songs will be added; the game keeps its 66.')
        recipe = json.loads(Path(self.events[-1]).read_text())
        self.assertEqual(len(recipe['tracks']), 61)
        for word in ('WAV', '22,050', 'mono', 'stereo', 'slots', 'twins', 'recipes', 'banks'):
            visible = ' '.join(w.text() for w in self.panel.findChildren(QLabel) if w.isVisible())
            self.assertNotIn(word, visible)
        self.assertEqual(self.panel.player.state(), 0)

    def test_page_drop_encoded_play_stub_edit_remove_reorder_and_playlist_identity(self):
        mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(self.wav))]*2)
        event = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        enter = QDragEnterEvent(QPoint(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        self.app.sendEvent(self.panel.songs_table.viewport(), enter)
        self.app.sendEvent(self.panel.songs_table.viewport(), event); self.drain()
        self.assertTrue(event.isAccepted())
        songs = self.service.library_songs()
        page = self.panel.playlist_page
        self.assertEqual(page.list.item(66).checkState(), Qt.Checked)
        self.assertEqual(page.list.item(67).checkState(), Qt.Checked)
        page.list.item(66).setCheckState(Qt.Unchecked)
        self.panel.songs_table.selectRow(67)
        self.panel.songs_table.item(67, 0).setText('Second song')
        self.panel.songs_table.item(67, 1).setText('My artist')
        self.panel.song_buttons['Move up'].click()
        self.assertEqual(self.service.library_songs()[0]['title'], 'Second song')
        self.assertEqual(page.list.item(66).checkState(), Qt.Checked)
        self.assertEqual(page.list.item(67).checkState(), Qt.Unchecked)
        preview = self.service.song_playback_path(songs[1]['id'])
        with patch('mod_editor.gui.audio_panel_qt.audio_player_command', return_value=('never-play', ('preview',))) as command, \
                patch.object(self.panel.player, 'start') as start:
            self.panel.songs_table.cellWidget(66, 4).click(); self.drain()
            self.assertEqual(command.call_args.args[0], preview)
            self.assertNotEqual(command.call_args.args[0], self.wav)
            start.assert_called_once()
        self.panel.songs_table.selectRow(66)
        self.panel.song_buttons['Remove'].click()
        self.assertEqual(self.panel.songs_table.rowCount(), 67)
        self.assertEqual(page.list.item(66).checkState(), Qt.Unchecked)
        self.panel.songs_table.selectRow(0)
        self.assertFalse(self.panel.song_buttons['Remove'].isEnabled())

    def test_warning_nonblocking_limits_errors_and_busy_pages(self):
        quiet = tone(self.root/'Quiet.wav', amplitude=100)
        self.panel.add_songs([quiet])
        self.assertFalse(self.panel.songs_page.isEnabled())
        self.assertFalse(self.panel.playlist_page.isEnabled())
        self.drain()
        self.assertIn('very quiet', self.panel.song_note.text())
        self.assertEqual(self.panel.songs_table.rowCount(), 67)
        self.panel.add_songs([self.wav]*134); self.drain()
        self.assertIn('200 songs', self.panel.status.text())
        self.assertEqual(self.panel.songs_table.rowCount(), 67)
        self.assertTrue(self.panel.songs_page.isEnabled())

    def test_stop_or_navigation_cancels_a_preview_that_is_still_preparing(self):
        import threading
        self.add()
        key = self.service.library_songs()[0]['id']
        for stop in (self.panel.stop_preview, lambda: self.panel.pages.setCurrentWidget(self.panel.playlist_page)):
            self.panel.pages.setCurrentWidget(self.panel.songs_page)
            entered, release = threading.Event(), threading.Event()
            def prepare(*args, **kwargs):
                entered.set()
                if not release.wait(3):
                    raise ValueError('test preview release timed out')
                return self.wav
            with patch.object(self.service, 'song_playback_path', side_effect=prepare), \
                    patch.object(self.panel.player, 'start') as start:
                self.panel.play_song(key)
                self.assertTrue(entered.wait(2))
                stop(); release.set(); self.drain()
                start.assert_not_called()

    def test_source_detach_clears_the_automatic_build_path(self):
        self.add()
        self.assertIsNotNone(self.events[-1])
        self.panel.set_service(None)
        self.assertIsNone(self.events[-1])
        self.assertIsNone(self.panel.library_recipe_path())
        self.assertEqual(self.panel.songs_table.rowCount(), 0)

    def test_cancel_source_change_no_delivery_or_autoplay(self):
        import threading
        entered = threading.Event()
        def prepare(paths, cancelled, progress):
            entered.set()
            while not cancelled():
                time.sleep(.005)
            raise ValueError('cancelled')
        with patch.object(self.service, 'prepare_songs', side_effect=prepare):
            self.panel.add_songs([self.wav])
            self.assertTrue(entered.wait(2))
            self.panel.set_service(None)
            self.drain()
        self.assertEqual(self.events, [])
        self.assertEqual(self.service.library_songs(), [])
        self.assertEqual(self.panel.player.state(), 0)

    def test_playlist_capacity_keeps_new_songs_checked_and_all_library_songs(self):
        tiny = self.root/'Tiny.wav'; tiny.write_bytes(wav_bytes())
        self.add([tiny]*35)
        page = self.panel.playlist_page
        self.assertEqual(self.panel.songs_table.rowCount(), 101)
        self.assertEqual(len(page.selected().records), 100)
        self.assertTrue(all(page.list.item(i).checkState() == Qt.Checked for i in range(66, 101)))
        self.assertIn('newest songs', page.summary.text())
        self.assertEqual(len(self.service.library_songs()), 35)

    def test_music_project_ui_roundtrip_includes_playlist_and_owned_audio(self):
        self.add()
        self.panel.playlist_page.enabled.setChecked(True)
        self.panel.playlist_page.list.item(0).setCheckState(Qt.Unchecked)
        chosen = self.panel.playlist_options()
        destination = self.root/'saved.2k5music'
        with patch('mod_editor.gui.music_panel_qt.QFileDialog.getSaveFileName', return_value=(str(destination), '')):
            self.panel.save_project(); self.drain()
        self.panel.songs_table.selectRow(66)
        self.panel.song_buttons['Remove'].click()
        with patch('mod_editor.gui.music_panel_qt.QFileDialog.getOpenFileName', return_value=(str(destination), '')):
            self.panel.load_project(); self.drain()
        self.assertEqual(self.panel.songs_table.rowCount(), 67)
        self.assertEqual(self.panel.playlist_options(), chosen)
        self.assertEqual(len(json.loads(Path(self.events[-1]).read_text())['tracks']), 60)

    def test_wav_and_mp3_add_to_synthetic_library_and_build_receives_recipe(self):
        encoded_source = mp3(self.wav, self.root/'Second song.mp3')
        # The same handoff used by Studio fills the unchanged Build controls.
        from mod_editor.gui.build_panel_qt import BuildPanel
        target = BuildPanel()
        self.addCleanup(target.deleteLater)
        def receive(path):
            target.music_library_field.setText(path or '')
            target.music_library_check.setChecked(bool(path))
        self.panel.library_changed.connect(receive)
        self.add([self.wav, encoded_source])
        received = json.loads(Path(target.music_library_field.text()).read_text())
        self.assertTrue(target.music_library_check.isChecked())
        self.assertEqual(received['tracks'][:59], [{'source_index': i} for i in range(59)])
        self.assertEqual([r['title'] for r in received['tracks'][59:]], ['Friday Night', 'Second song'])
        for track in received['tracks'][59:]:
            import wave
            with wave.open(track['wav']) as wav:
                self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate()), (2, 2, 22050))
        self.assertEqual([self.panel.playlist_page.list.item(i).checkState() for i in (66, 67)], [Qt.Checked]*2)


if __name__ == '__main__':
    unittest.main()
