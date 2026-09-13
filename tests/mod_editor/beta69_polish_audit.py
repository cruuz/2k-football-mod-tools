"""Developer audit: capture actual shell controls using the packaged metadata catalogs.

Run with PYTHONPATH=. and a destination JSON or JSON.GZ path. No source is opened.
The separate test_beta69_studios_offscreen.py uses tiny catalogs for the fast CI gate.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['MOD_STUDIO_NO_UPDATE_CHECK']='1'
import gzip, json, sys, tempfile, time
from pathlib import Path
from unittest.mock import patch
from PyQt5.QtCore import Qt, QCoreApplication, QEvent, QSettings
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QAbstractButton, QComboBox, QTabWidget, QLineEdit, QAbstractSpinBox, QMessageBox, QAction
from mod_editor.gui.studio_qt import StudioMainWindow, BrowseOnlyFacade
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.gui import ApfStudioMainWindow
app=QApplication.instance() or QApplication([])
result={'windows':[], 'dialogs':[], 'crashes':[]}
def hook(k,v,t):
    import traceback
    traceback.print_exception(k,v,t)
    result['crashes'].append(str(v))
sys.excepthook=hook
def modal(*args, **kwargs):
    result['dialogs'].append(str(args[1:3])); return QMessageBox.Cancel

def receivers(action):
    try: return action.receivers(action.triggered)
    except RuntimeError: return None

def snapshot(window, page, size):
    rows=[]
    for w in window.findChildren(QWidget):
        text=''
        if isinstance(w,(QLabel,QAbstractButton,QLineEdit)): text=w.text()
        elif isinstance(w,QComboBox): text=' | '.join(w.itemText(i) for i in range(w.count()))
        elif isinstance(w,QAbstractSpinBox): text=w.text()
        elif isinstance(w,QTabWidget): text=' | '.join(w.tabText(i) for i in range(w.count()))
        elif w.windowTitle(): text=w.windowTitle()
        if not text and not w.toolTip(): continue
        visible=w.isVisible()
        item={'page':page,'size':size,'class':type(w).__name__,'name':w.objectName(),'text':text,'tooltip':w.toolTip(),'whats_this':w.whatsThis(),'visible':visible,'enabled':w.isEnabled(),'width':w.width(),'height':w.height()}
        if isinstance(w,(QAbstractButton,QComboBox,QAbstractSpinBox)):
            item['missing_help']=not (w.toolTip() or w.whatsThis())
        if isinstance(w,QAbstractButton):
            try: item['click_receivers']=w.receivers(w.clicked)
            except RuntimeError: item['click_receivers']=None
            if visible and text and not '\n' in text:
                item['clipped']=w.width()<w.sizeHint().width()
        if isinstance(w,QLabel) and visible and text and '<' not in text:
            item['clipped']=not w.wordWrap() and w.fontMetrics().horizontalAdvance(text)>w.contentsRect().width()+2
        rows.append(item)
    return rows
with tempfile.TemporaryDirectory(prefix='b69-j7-walk-') as d:
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat,QSettings.UserScope,d)
    with patch.multiple(QMessageBox, **{k:modal for k in ('warning','critical','information','question','about','exec_')}):
        for name,make in [('2k5',lambda:StudioMainWindow(facade=BrowseOnlyFacade(), offer_recovery=False)),('apf',lambda:ApfStudioMainWindow(ApfStudioFacade(cache_root=Path(d)/'cache'),offer_recovery=False))]:
            started=time.monotonic(); w=make(); entry={'studio':name,'navigation':[],'snapshots':[],'actions':[]}
            result['windows'].append(entry)
            for row in range(w.navigation.count()):
                item=w.navigation.item(row); entry['navigation'].append(item.text())
                if name=='2k5': w._ensure_workspace(row)
                w.navigation.setCurrentRow(row)
                if name=='apf': w._activate_page(row)
                for width,height in [(1480,920),(1366,768)]:
                    w.resize(width,height); w.show(); app.processEvents()
                    page=w.pages.widget(row) if name=='2k5' else w._pages[list(w._pages)[row]]
                    entry['snapshots']+=snapshot(page,item.text(),[w.width(),w.height()])
                    # Visit nested tabs too: construction and selection must be safe without a disc.
                    page=w.pages.widget(row) if name=='2k5' else w._pages[list(w._pages)[row]]
                    for tabs in page.findChildren(QTabWidget):
                        current=tabs.currentIndex()
                        for i in range(tabs.count()):
                            tabs.setCurrentIndex(i); app.processEvents()
                            entry['snapshots']+=snapshot(tabs,item.text()+' / '+tabs.tabText(i),[w.width(),w.height()])
                        tabs.setCurrentIndex(current)
            entry['actions']=[{'text':a.text(),'tooltip':a.toolTip(),'enabled':a.isEnabled(),'receivers':receivers(a)} for a in w.findChildren(QAction)]
            entry['seconds']=round(time.monotonic()-started,3)
            w._allow_close=True; w.close(); w.deleteLater(); QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete); app.processEvents()
destination=Path(sys.argv[1])
payload=(json.dumps(result,indent=2)+'\n').encode()
destination.write_bytes(gzip.compress(payload, mtime=0) if destination.suffix=='.gz' else payload)
for w in result['windows']:
    unique={(r['class'],r['name'],r['text'],r['tooltip']) for r in w['snapshots']}
    missing={r['text'] for r in w['snapshots'] if r.get('missing_help')}
    clipped={r['text'] for r in w['snapshots'] if r.get('clipped')}
    print(w['studio'],w['seconds'],'seconds',len(unique),'unique strings/controls',len(missing),'missing help',len(clipped),'clipping candidates')
    print(w['navigation'])
print('dialogs',result['dialogs'],'crashes',result['crashes'])
assert not result['dialogs'] and not result['crashes'], result
