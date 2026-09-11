"""Every APF page and dialog uses readable application colours and bounded UI."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MOD_STUDIO_NO_UPDATE_CHECK"] = "1"

from PyQt5.QtCore import QCoreApplication, QEvent, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QLineEdit, QTableWidget, QTableWidgetItem, QWidget
from mod_editor.apf_studio.apf_theme import TOKENS, configure_table, contrast, sort_visual_rows
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.gui import ApfStudioMainWindow
from mod_editor.apf_studio.models import APF_CATEGORY_ORDER, ApfCategory
from mod_editor.apf_studio.project import WorkspaceStateStore
from mod_editor.apf_studio.ui_audit import contrast_failures, page_layout_failures
from tools.apf_ui_snapshots import dialog_fixtures, pump


class ThemeLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temporary = tempfile.TemporaryDirectory(prefix="apf-theme-test-")
        cls.root = Path(cls.temporary.name)
        cls.store = WorkspaceStateStore(cls.root / "state")
        cls.window = ApfStudioMainWindow(ApfStudioFacade(cache_root=cls.root / "cache"),
                                         workspace_store=cls.store, offer_recovery=False)
        cls.window.resize(1366, 768)
        cls.window.show()
        pump(cls.app, cls.window)

    @classmethod
    def tearDownClass(cls):
        cls.window._allow_close = True
        cls.window.close()
        cls.app.processEvents()
        cls.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        cls.temporary.cleanup()

    def test_body_tokens_meet_aa_on_every_surface(self):
        for foreground in ("text", "muted", "success", "info", "warning", "danger"):
            for background in ("canvas", "surface", "base", "alternate", "raised"):
                with self.subTest(foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(TOKENS[foreground], TOKENS[background]), 4.5)

    def test_launcher_disposes_styled_windows_before_application_exit(self):
        code = '''
from pathlib import Path
import tempfile
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.apf_studio.gui import launch_studio
from mod_editor.apf_studio.project import WorkspaceStateStore
app = QApplication([])
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    QTimer.singleShot(100, lambda: app._apf2k8_mod_studio_window.close())
    assert launch_studio(ApfStudioFacade(cache_root=root / "cache"),
                         workspace_store=WorkspaceStateStore(root / "state"), offer_recovery=False) == 0
    assert app._apf2k8_mod_studio_window is None
print("APF_LAUNCH_EXIT_PASS", flush=True)
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[2],
                                capture_output=True, text=True, timeout=60, env=dict(os.environ, PYTHONFAULTHANDLER="1"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("APF_LAUNCH_EXIT_PASS", result.stdout)

    def test_every_page_effective_palette_and_1366_layout(self):
        for row, category in enumerate(APF_CATEGORY_ORDER):
            with self.subTest(page=category.value):
                self.window.navigation.setCurrentRow(row)
                pump(self.app, self.window)
                self.assertEqual(page_layout_failures(self.window), [])
                self.assertEqual(contrast_failures(self.window._pages[category]), [])
                self.assertFalse(self.window.grab().isNull())
                strip = self.window._pages[category].capabilities
                self.assertLessEqual(strip.height(), 36)

    def test_every_dialog_effective_palette_and_buttons(self):
        seen = set()
        for dialog in dialog_fixtures(self.window, self.root):
            with self.subTest(dialog=dialog.windowTitle()):
                dialog.show()
                self.app.processEvents()
                seen.add(type(dialog).__name__)
                self.assertEqual(contrast_failures(dialog), [])
                screen = dialog.screen().availableGeometry()
                self.assertLessEqual(dialog.width(), screen.width())
                self.assertLessEqual(dialog.height(), screen.height())
                for box in dialog.findChildren(QDialogButtonBox):
                    for button in box.buttons():
                        if button.isVisibleTo(dialog):
                            point = button.mapTo(dialog, button.rect().bottomRight())
                            self.assertTrue(dialog.rect().contains(point), (dialog.windowTitle(), button.text(), point))
                dialog.close()
                dialog.deleteLater()
                self.app.processEvents()
        self.assertTrue({"PlayDesignDialog", "FormationDesignDialog", "CpuCallDialog", "Ps3BundleMappingDialog",
                         "NormalLogoRegionDialog", "HelmetLogoPlacementDialog", "Xma1EncoderSetupWizard"} <= seen)

    def test_ctrl_f_escape_and_tab_chain_on_every_page(self):
        self.window.activateWindow()
        for row, category in enumerate(APF_CATEGORY_ORDER):
            with self.subTest(page=category.value):
                self.window.navigation.setCurrentRow(row)
                pump(self.app, self.window)
                field = self.window._current_search_field()
                self.assertIsNotNone(field)
                QTest.keyClick(self.window, Qt.Key_F, Qt.ControlModifier)
                self.app.processEvents()
                self.assertIs(self.app.focusWidget(), field)
                field.setText("search trial")
                QTest.keyClick(field, Qt.Key_Escape)
                self.assertEqual(field.text(), "")
                QTest.keyClick(field, Qt.Key_Tab)
                focused = self.app.focusWidget()
                self.assertIsNotNone(focused)
                self.assertIsNot(focused, field)
                self.assertTrue(focused.isVisibleTo(self.window) and focused.isEnabled())
                chain, current = [], field.nextInFocusChain()
                while current is not field and len(chain) < 4096:
                    chain.append(current)
                    current = current.nextInFocusChain()
                self.assertIs(current, field, "Broken tab cycle")
                self.assertTrue(any(widget.isVisibleTo(self.window) and widget.isEnabled()
                                    and widget.focusPolicy() & Qt.TabFocus for widget in chain))

    def test_sorting_preserves_record_identity_and_cell_widgets(self):
        table = QTableWidget(3, 2)
        configure_table(table)
        for row, name in enumerate(("Entry 20", "Entry 3", "Entry 100")):
            table.setItem(row, 0, QTableWidgetItem(name))
            table.setCellWidget(row, 1, QLineEdit(str(row)))
        table.selectRow(0)
        sort_visual_rows(table, 0, Qt.AscendingOrder)
        self.assertEqual([table.item(table.verticalHeader().logicalIndex(i), 0).text() for i in range(3)],
                         ["Entry 3", "Entry 20", "Entry 100"])
        self.assertEqual(table.currentRow(), 0)
        self.assertEqual(table.cellWidget(0, 1).text(), "0")
        table.deleteLater()

    def test_escape_does_not_erase_an_authoring_field(self):
        self.window.navigation.setCurrentRow(0)
        search = self.window._current_search_field()
        search.setText("uniform")
        edit = QLineEdit(self.window)
        edit.setText("My authored team name")
        edit.show()
        edit.setFocus()
        self.app.processEvents()
        self.window._clear_current_search()
        self.assertEqual(edit.text(), "My authored team name")
        self.assertEqual(search.text(), "")
        edit.deleteLater()

    def test_workspace_store_restores_page_and_workspace(self):
        self.window.navigation.setCurrentRow(APF_CATEGORY_ORDER.index(ApfCategory.PLAYBOOKS))
        self.window._pages[ApfCategory.PLAYBOOKS].open_workspace("play-designer")
        self.window._save_ui_state()
        saved = self.store.read().ui_state
        self.assertEqual(saved["page"], "playbooks")
        self.assertEqual(saved["workspaces"]["playbooks"], "Design Plays / Formations")
        other = ApfStudioMainWindow(ApfStudioFacade(cache_root=self.root / "cache2"),
                                    workspace_store=self.store, offer_recovery=False)
        self.assertEqual(other.navigation.currentRow(), APF_CATEGORY_ORDER.index(ApfCategory.PLAYBOOKS))
        page = other._pages[ApfCategory.PLAYBOOKS]
        self.assertIs(page.workspace_tabs.currentWidget(), page.play_designer)
        self.assertLessEqual(other.frameGeometry().width(), max(other.screen().availableGeometry().width(), other.minimumWidth()))
        other._allow_close = True
        other.close()
        other.deleteLater()


if __name__ == "__main__":
    unittest.main()
