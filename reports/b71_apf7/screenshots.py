"""Capture the actual Studio shell, with synthetic opacity values (no game art)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MOD_STUDIO_NO_UPDATE_CHECK'] = '1'
if sys.argv[1] == 'before':
    # Load the exact release modules in this process without switching the tree.
    from mod_editor.apf_studio import field_material_qt, gui
    for module in (field_material_qt, gui):
        relative = Path(module.__file__).relative_to(Path.cwd()).as_posix()
        source = subprocess.check_output(['git', '--git-dir=.scratch/git', 'show',
            '02bbadd184e85498a441d3be71e70f8de94b9b0a:' + relative])
        exec(compile(source, relative, 'exec'), module.__dict__)
from PyQt5.QtWidgets import QApplication
from PyQt5.QtWidgets import QTableWidgetItem, QFrame
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.gui import ApfStudioMainWindow
from mod_editor.apf_studio.models import APF_CATEGORY_ORDER, ApfCategory
from mod_editor.apf_studio.project import WorkspaceStateStore
from tools.apf_ui_snapshots import pump

app = QApplication.instance() or QApplication([])
out = Path(__file__).parent
receipt = []
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    window = ApfStudioMainWindow(ApfStudioFacade(cache_root=root/'cache'),
        workspace_store=WorkspaceStateStore(root/'state'), offer_recovery=False)
    window.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(ApfCategory.FIELD_ART))
    panel = window._pages[ApfCategory.FIELD_ART].field_opacity
    page = window._pages[ApfCategory.FIELD_ART]
    if page.workspace_tabs.indexOf(panel) >= 0:
        page.workspace_tabs.setCurrentWidget(panel)
    panel.setEnabled(True)
    for i, (enabled, value) in enumerate(panel.controls.values()):
        enabled.setChecked(True)
        value.setValue(100 - i * 5)
    panel.note.setText('Layout proof: synthetic opacity values; no game artwork loaded.')
    for width, height in ((1280,720),(1920,1080)):
        window.resize(width,height)
        window.show()
        pump(app,window)
        path=out/f'field-{sys.argv[1]}-{width}x{height}.png'
        assert window.grab().save(str(path))
        row = {'image': path.name, 'window': [window.width(),window.height()],
            'panel_height':panel.height(), 'rows': {name: {'label_height':cb.height(),
            'value_height':value.height(), 'value':value.text()} for name,(cb,value) in panel.controls.items()}}
        if hasattr(panel,'material_scroll'):
            row['scroll_viewport_height']=panel.material_scroll.viewport().height()
            row['scroll_maximum']=panel.material_scroll.verticalScrollBar().maximum()
        receipt.append(row)
        for table in (page.group_table,page.browser.table):
            table.setRowCount(16)
            for i in range(16):
                for j in range(table.columnCount()):
                    table.setItem(i,j,QTableWidgetItem(f'Synthetic row {i+1}' if j==0 else str(i+j)))
        for label,slug in [('Field Art Editor','art'),('Ownership Map','ownership'),('All Field Art','inventory')]:
            page.workspace_tabs.setCurrentIndex(next(i for i in range(page.workspace_tabs.count())
                                                    if page.workspace_tabs.tabText(i)==label))
            pump(app,window)
            # These extra captures show authored fixture rows, so suppress only
            # the no-source empty guidance which normally covers an empty list.
            for empty in page.findChildren(QFrame,'emptyState'): empty.hide()
            assert window.grab().save(str(out/f'{slug}-{sys.argv[1]}-{width}x{height}.png'))
        if page.workspace_tabs.indexOf(panel)>=0:
            page.workspace_tabs.setCurrentWidget(panel)
        else:
            page.workspace_tabs.setCurrentIndex(0)
    window._allow_close=True
    window.close()
    app.processEvents()
(out/f'field-{sys.argv[1]}.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
