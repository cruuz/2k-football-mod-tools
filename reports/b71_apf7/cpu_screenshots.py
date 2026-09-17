"""Read the owned index; capture draft weights through the real CPU page."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
os.environ['QT_QPA_PLATFORM']='offscreen'
from PyQt5.QtWidgets import QApplication, QScrollArea
from PyQt5.QtCore import QPoint
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.models import ApfSource
from mod_editor.apf_studio.session import ApfSession
from mod_editor.apf_studio.playcalling_editor_qt import ApfPlayCallingEditor
from mod_editor.apf_studio.apf_theme import install_theme
from tests.mod_editor.test_apf_playcall_research_native import INDEX

app=QApplication.instance() or QApplication([])
install_theme(app)
out=Path(__file__).parent
with tempfile.TemporaryDirectory() as tmp:
    f=ApfStudioFacade(cache_root=Path(tmp))
    source=ApfSource(INDEX.parent,INDEX.parent,INDEX,hashlib.sha256(INDEX.read_bytes()).hexdigest(),
                     INDEX.stat().st_size,'e'*64,'Owned APF export')
    f.source=source;f.catalog=NS(assets=(),capabilities=(),by_id={})
    f.session=ApfSession(source,f.catalog,cache_root=Path(tmp))
    panel=ApfPlayCallingEditor(f,lambda label,work,done,blocking:done(work(lambda *_:None)))
    panel.donor_picker.setCurrentText('O-ManBlock')
    assert panel._context, panel.notice.text()
    panel.situation_picker.setCurrentIndex(8)
    panel.candidate_table.selectRow(0)
    for slider,value in zip(panel.ratings,(1,2,7)):slider.setValue(value)
    panel.rating_preview_button.click()
    assert not panel.rating_preview_table.isHidden(),panel.notice.text()
    assert not f.session.modifications
    receipts=[]
    for width,height in ((1280,720),(1920,1080)):
        panel.resize(width,height);panel.show()
        for _ in range(5): app.processEvents()
        scroll=panel.findChild(QScrollArea)
        scroll.verticalScrollBar().setValue(0)
        app.processEvents()
        assert panel.grab().save(str(out/f'cpu-books-{width}x{height}.png'))
        scroll.ensureWidgetVisible(panel.rating_editor,0,0)
        app.processEvents()
        assert panel.grab().save(str(out/f'cpu-weights-{width}x{height}.png'))
        for _ in range(5): app.processEvents()
        scroll.verticalScrollBar().setValue(
            panel.rating_preview_note.mapTo(scroll.widget(),QPoint(0,0)).y()-150)
        for _ in range(5): app.processEvents()
        assert panel.grab().save(str(out/f'cpu-preview-{width}x{height}.png'))
        receipts.append({'size':[width,height],'book':panel._context['book'],
            'formation':panel.formation_picker.currentData(),'ratings':[s.value() for s in panel.ratings],
            'preview_rows':panel.rating_preview_table.rowCount(),'modifications':len(f.session.modifications)})
    panel.close();f.close()
(out/'cpu-weights.json').write_text(json.dumps(receipts,indent=2)+'\n')
print(json.dumps(receipts,indent=2))
