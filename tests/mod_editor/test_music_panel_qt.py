"""Offscreen Music UI tests; playback processes are always mocked, never started."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
try:
    from PyQt5.QtCore import QMimeData,QUrl,Qt,QPoint,QPointF
    from PyQt5.QtGui import QDropEvent
    from PyQt5.QtWidgets import QApplication,QDialog
    from mod_editor.gui.music_panel_qt import MusicPanel,MusicTable,AssignmentReview,FitReview
except ImportError:
    QApplication=None
from tests.mod_editor.music_fixtures import MusicDisc,music_session,wav_bytes

@unittest.skipUnless(QApplication is not None,'PyQt5 is not installed; offscreen Music UI unavailable')
class MusicPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.disc=MusicDisc(self.root);self.service,_=music_session(self.root,self.disc)
        self.panel=MusicPanel(self.service)
        self.wav=self.root/'authored.wav';self.wav.write_bytes(wav_bytes(sample=3500))
        self.panel.match_volume.setChecked(False)
    def tearDown(self):
        self.panel.close();self.drain();self.temp.cleanup()
    def drain(self):
        deadline=time.monotonic()+15
        while self.panel._task is not None and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.005)
        self.app.processEvents()
        self.assertIsNone(self.panel._task,'Music worker failed to finish')

    def test_rows_honest_names_presentation_policy_defaults_and_no_autoplay(self):
        self.assertEqual(self.panel.table.rowCount(),66)
        self.assertEqual(self.panel.table.item(0,1).text(),'Menu 01')
        self.assertEqual(self.panel.menu_policy.currentData(),'retail')
        self.assertFalse(self.panel.unlock.isChecked())
        self.assertFalse(self.panel.userlist.isChecked())
        self.assertEqual(self.panel.player.state(),0)
        self.panel.presentation.setChecked(True)
        self.assertEqual(self.panel.table.rowCount(),86)
        self.panel.table.selectRow(27)
        self.assertIn('Spoken outtake',self.panel.detail.text())
        self.panel.menu_policy.setCurrentIndex(1)
        self.panel.unlock.setChecked(True)
        self.panel.userlist.setChecked(True)
        self.assertEqual(self.service.policy,dict(music_policy='jukebox_menus',music_unlock=True,music_userlist=True))
        self.panel.menu_policy.setCurrentIndex(0)
        self.assertFalse(self.panel.userlist.isChecked())

    def test_drop_mime_order_local_only_assignment_reordering_and_oversize(self):
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(self.wav)),QUrl.fromLocalFile(str(self.root/'z.ogg'))])
        self.assertEqual(MusicTable.paths(mime),(self.wav,self.root/'z.ogg'))
        mime.setUrls([QUrl('https://example.com/music.mp3')]);self.assertEqual(MusicTable.paths(mime),())
        drops=[]
        table=MusicTable();table.setRowCount(2)
        from PyQt5.QtWidgets import QTableWidgetItem
        for i,key in enumerate(('femusic:0','femusic:1')):
            item=QTableWidgetItem(key);item.setData(Qt.UserRole,key);table.setItem(i,0,item)
        table.files_dropped.connect(lambda files,start:drops.append((files,start)))
        mime.setUrls([QUrl.fromLocalFile(str(self.wav))])
        table.dropEvent(QDropEvent(QPointF(1,1),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))
        self.assertEqual(drops[-1],((self.wav,),'femusic:0'))
        table.selectRow(1)
        table.dropEvent(QDropEvent(QPointF(1,10000),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))
        self.assertEqual(drops[-1],((self.wav,),'femusic:1'))
        assignments=self.service.catalog.assignments([self.wav,self.root/'z.ogg'],self.panel.visible_ids(),'femusic:6')
        review=AssignmentReview(assignments,self.service.catalog)
        item=review.files.takeItem(1);review.files.insertItem(0,item)
        self.assertEqual(review.result_assignments()[0],('femusic:6',self.root/'z.ogg'))
        self.panel.drop_files([self.wav,self.wav],'cribmusic:58')
        self.assertIn('Too many',self.panel.status.text())
        self.assertFalse(self.service.session._audio_edits)

    def test_review_apply_stage_worker_restore_undo_redo(self):
        with patch.object(AssignmentReview,'exec_',return_value=QDialog.Accepted),patch.object(FitReview,'exec_',return_value=QDialog.Accepted):
            self.panel.drop_files([self.wav],'cribmusic:0')
            self.drain()
        self.assertEqual(self.service.row_state('cribmusic:0'),'Replaced')
        self.assertEqual(self.panel.player.state(),0)
        self.panel.table.selectRow(7)
        self.assertIn('Dropped file',self.panel.detail.text())
        self.panel.restore();self.drain();self.assertEqual(self.service.row_state('cribmusic:0'),'Original')
        self.panel.undo();self.drain();self.assertEqual(self.service.row_state('cribmusic:0'),'Replaced')
        self.panel.redo();self.drain();self.assertEqual(self.service.row_state('cribmusic:0'),'Original')

    def test_cancel_review_and_stale_source_completion_never_apply(self):
        with patch.object(AssignmentReview,'exec_',return_value=QDialog.Accepted),patch.object(FitReview,'exec_',return_value=QDialog.Rejected):
            self.panel.drop_files([self.wav],'cribmusic:0');self.drain()
        self.assertFalse(self.service.session._audio_edits)
        self.assertFalse(list(self.service.root.glob('import-*')))
        self.panel._run(lambda cancel,progress:self.service.prepare_batch([('cribmusic:0',self.wav)],cancelled=cancel))
        self.panel.set_service(None);self.drain()
        self.assertFalse(self.service.session._audio_edits)
        self.assertFalse(list(self.service.root.glob('import-*')))

    def test_explicit_play_original_current_and_mono_dispatch_without_audio(self):
        self.panel.table.selectRow(7)
        with patch.object(self.service,'playback_path',return_value=self.wav) as get,\
             patch('mod_editor.gui.audio_panel_qt.audio_player_command',return_value=('mock-player',('arg',))),\
             patch.object(self.panel.player,'start') as start:
            self.panel.play(original=True);self.drain()
            self.assertTrue(get.call_args.kwargs['original']);self.assertEqual(start.call_count,1)
            self.panel.mono.setChecked(True)
            self.panel.play(original=False);self.drain()
            self.assertTrue(get.call_args.kwargs['mono']);self.assertEqual(start.call_count,2)

    def test_close_cancels_and_waits_for_worker_before_widget_destruction(self):
        import threading
        entered=threading.Event()
        def action(cancel,progress):
            entered.set()
            while not cancel():time.sleep(.005)
            raise ValueError('cancelled')
        self.panel._run(action)
        self.assertTrue(entered.wait(2))
        self.panel.close();self.drain()
        self.assertTrue(self.panel._closing)
        self.assertEqual(self.panel.player.state(),0)

if __name__=='__main__':unittest.main()
