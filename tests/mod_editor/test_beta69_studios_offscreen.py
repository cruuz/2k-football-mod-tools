"""Open every page and tab in both studios with no disc, display or network.

The whole test process is bounded to 55 seconds by the parent test. The child
uses tiny metadata-only catalogs, so it also runs in a lean checkout.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MOD_STUDIO_NO_UPDATE_CHECK'] = '1'


def replay():
    from unittest.mock import patch
    from PyQt5.QtCore import Qt, QCoreApplication, QEvent, QSettings
    from PyQt5.QtWidgets import QApplication, QLabel, QAbstractButton, QAbstractSpinBox, QComboBox, QTabWidget, QMessageBox, QFileDialog, QPushButton
    from mod_editor.gui.studio_qt import StudioMainWindow, BrowseOnlyFacade
    from mod_editor.apf_studio.gui import ApfStudioMainWindow
    from mod_editor.apf_studio.facade import ApfStudioFacade
    from mod_editor.core import nfl2k5_uniform_catalog as uniform_module
    from mod_editor.core.nfl2k5_uniform_catalog import Nfl2k5UniformCatalog
    from mod_editor.core.nfl2k5_extended_visual_catalog import Nfl2k5ExtendedVisualCatalog, VisualReportPaths
    from test_beta69_string_hygiene import STALE, DIAGNOSTIC
    app = QApplication.instance() or QApplication([])
    failures = []
    dialogs = []
    old_hook = sys.excepthook
    def hook(kind, value, tb):
        failures.append(str(value))
        old_hook(kind, value, tb)
    sys.excepthook = hook
    def modal(*args, **kwargs):
        dialogs.append(str(args[1:3])); return QMessageBox.Cancel
    total_pages = total_tabs = controls = 0
    with tempfile.TemporaryDirectory(prefix='b69-polish-') as folder:
        QSettings.setDefaultFormat(QSettings.IniFormat)
        QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, folder)
        with patch.multiple(QMessageBox, **{k: modal for k in ('warning', 'critical', 'information', 'question', 'about', 'exec_')}), patch.object(uniform_module, 'EXPECTED_SET_COUNT', 0):
            factories = (
                ('2K5', lambda: StudioMainWindow(facade=BrowseOnlyFacade(),
                    uniform_catalog=Nfl2k5UniformCatalog((), (), Path(folder) / 'catalog.json'),
                    extended_visual_catalog=Nfl2k5ExtendedVisualCatalog((), VisualReportPaths()),
                    offer_recovery=False)),
                ('APF', lambda: ApfStudioMainWindow(ApfStudioFacade(cache_root=Path(folder) / 'cache'), offer_recovery=False)),
            )
            for name, make in factories:
                window = make()
                window.show()
                product = '2k5' if name == '2K5' else 'apf2k8'
                guide = (ROOT / 'docs/mod_editor' / f'{product}_mod_studio_getting_started.md').read_text(encoding='utf-8')
                table = guide.split('## Pages in sidebar order', 1)[1].split('\n## ', 1)[0]
                documented = [line.split('|')[1].strip() for line in table.splitlines() if line.startswith('| ')][2:]
                navigation = [window.navigation.item(i).text().strip() for i in range(window.navigation.count())]
                assert documented == navigation, (name, documented, navigation)
                for row in range(window.navigation.count()):
                    total_pages += 1
                    if name == '2K5':
                        window._ensure_workspace(row)
                    window.navigation.setCurrentRow(row)
                    if name == 'APF':
                        window._activate_page(row)
                    app.processEvents()
                    page = window.pages.widget(row) if name == '2K5' else window._pages[list(window._pages)[row]]
                    for width, height in ((1480, 920), (1366, 768)):
                        window.resize(width, height)
                        app.processEvents()
                        assert window.width() <= width, (name, row, window.width())
                        for tabs in page.findChildren(QTabWidget):
                            active = tabs.currentIndex()
                            for index in range(tabs.count()):
                                total_tabs += 1
                                tabs.setCurrentIndex(index)
                                app.processEvents()
                                assert tabs.currentWidget() is tabs.widget(index)
                                assert tabs.tabToolTip(index), (name, row, tabs.tabText(index))
                            tabs.setCurrentIndex(active)
                    for widget in page.findChildren(QLabel) + page.findChildren(QAbstractButton) + page.findChildren(QComboBox) + page.findChildren(QAbstractSpinBox):
                        controls += 1
                        values = [widget.toolTip(), widget.whatsThis(), widget.accessibleDescription()]
                        if isinstance(widget, QComboBox):
                            values.extend(widget.itemText(i) for i in range(widget.count()))
                        elif hasattr(widget, 'text'):
                            values.append(widget.text())
                        for value in values:
                            assert not STALE.search(value), (name, row, value)
                            assert not DIAGNOSTIC.search(value), (name, row, value)
                        if isinstance(widget, (QComboBox, QAbstractSpinBox)) or (isinstance(widget, QAbstractButton) and widget.text()):
                            assert widget.toolTip() or widget.whatsThis(), (name, row, widget.objectName())
                        if isinstance(widget, QPushButton) and widget.isEnabled() and widget.text():
                            # Checkable buttons can be read at Apply or use toggled;
                            # menu buttons route through their actions instead of clicked.
                            try:
                                connected = bool(widget.menu()) or widget.isCheckable() or widget.receivers(widget.clicked) or widget.receivers(widget.pressed)
                            except RuntimeError:
                                # Qt-created wizard/navigation buttons own native slots;
                                # PyQt deliberately denies receiver introspection there.
                                connected = True
                            assert connected, (name, row, widget.text())
                # The first action reaches the chooser; cancelling stays on a usable page.
                if name == '2K5':
                    with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as choose:
                        window.open_source_button.click(); app.processEvents(); assert choose.called
                    start = next(b for b in window.findChildren(QPushButton) if b.text().startswith('Start SOFTDRINK Basic'))
                    start.click(); app.processEvents()
                    assert window.page_title.text() == 'Build & Share'
                    assert window._build_panel.blocker()
                else:
                    actions = window.open_source_button.menu().actions()
                    with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as choose:
                        actions[0].trigger(); app.processEvents(); assert choose.called
                    assert not window.build_button.isEnabled()
                    assert window.build_button.toolTip()
                window._allow_close = True
                window.close(); window.deleteLater()
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
    sys.excepthook = old_hook
    assert not dialogs, dialogs
    assert not failures, failures
    print(f'Opened {total_pages} pages; {total_tabs} tab visits at two sizes; checked {controls} controls. No dialogs or slot exceptions.')


class StudioSmokeTests(unittest.TestCase):
    def test_both_studios_open_every_page_in_under_a_minute(self):
        start = time.monotonic()
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--replay'],
            cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True, timeout=55)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(time.monotonic() - start, 60)
        print(result.stdout.strip())

if __name__ == '__main__':
    if '--replay' in sys.argv:
        replay()
    else:
        unittest.main()
