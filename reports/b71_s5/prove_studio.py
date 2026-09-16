"""Click the real Scorebar Studio preview button and capture its completed dialog."""
from pathlib import Path
import json,os,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QProcess
from mod_editor.gui.scorebug_studio_panel_qt import ScorebugStudioPanel
app=QApplication([]);panel=ScorebugStudioPanel();panel.sprite_source_provider=lambda:'/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'
panel.sprite_preview_button.click();app.processEvents();d=panel._sprite_preview_dialog
try:
 d.screenshot.setText('/home/noah/Desktop/2K5-8 Editors/beta71_evidence/day/ksnip_20260915-154929.png');d.aspect.setCurrentText('16:9');d.preview_button.click()
 end=time.monotonic()+60
 while d.process.state()!=QProcess.NotRunning and time.monotonic()<end:
  app.processEvents();d.process.waitForFinished(50)
 app.processEvents();app.processEvents();assert 'Preview ready' in d.status.text(),d.status.text()
 assert d.scroll.verticalScrollBar().value()==d.scroll.verticalScrollBar().maximum()
 d.grab().save(str(ROOT/'reports/b71_s5/studio-preview.png'))
 (ROOT/'reports/b71_s5/studio-preview.json').write_text(json.dumps(dict(button=panel.sprite_preview_button.text(),source_from_page=d.source.text(),state='standard',aspect='16:9',status=d.status.text(),native_process=True),indent=2)+'\n')
 print(d.status.text())
finally:d.close();panel.close()
