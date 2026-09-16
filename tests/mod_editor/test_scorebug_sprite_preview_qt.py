"""Exercise the real Studio preview process against a user-owned disc."""
import json,os,sys,tempfile,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QProcess
from mod_editor.gui.scorebug_sprite_preview_qt import SpritePreviewDialog
SOURCE=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
SCREENSHOT=Path('/home/noah/Desktop/2K5-8 Editors/beta71_evidence/day/ksnip_20260915-154929.png')
class PreviewTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_invalid_inputs_are_readable_and_design_handoff_validates(self):
  d=SpritePreviewDialog();self.addCleanup(d.close);d.preview();self.assertIn('existing',d.status.text())
  received=[];d.design_chosen.connect(received.append);d._use_design();self.assertEqual(received,[d.folder.text()])
  d.folder.setText('/missing-design');d._use_design();self.assertEqual(len(received),1)
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory);(folder/'layout.json').write_text('[]')
   d.folder.setText(str(folder));d._use_design();self.assertIn('Invalid sprite design',d.status.text());self.assertEqual(len(received),1)
 @unittest.skipUnless(SOURCE.is_file() and SCREENSHOT.is_file(),'user-owned game and screenshot required')
 def test_actual_process_reads_iso_and_shows_native_preview(self):
  d=SpritePreviewDialog(source=SOURCE);self.addCleanup(d.close);d.screenshot.setText(str(SCREENSHOT));d.aspect.setCurrentText('16:9')
  d.state['away_score'].setValue(100);d.state['play_clock'].setValue(12);d.goal.setChecked(True);d.show();self.app.processEvents();d.preview()
  end=time.monotonic()+60
  while d.process.state()!=QProcess.NotRunning and time.monotonic()<end:
   self.app.processEvents();d.process.waitForFinished(50)
  self.app.processEvents();self.app.processEvents();self.assertEqual(d.process.state(),QProcess.NotRunning)
  self.assertIn('Preview ready',d.status.text());self.assertFalse(d.picture.pixmap().isNull())
  self.assertGreater(d.scroll.verticalScrollBar().maximum(),0)
  self.assertEqual(d.scroll.verticalScrollBar().value(),d.scroll.verticalScrollBar().maximum())
  j=json.loads(d.output.with_suffix('.json').read_text());self.assertEqual(j['state']['away_score'],100);self.assertTrue(j['state']['goal_to_go'])
  self.assertEqual(j['volume']['font_count'],0);self.assertEqual(sum(r['glyph_quads'] for r in j['draws']),0)
if __name__=='__main__':unittest.main()
