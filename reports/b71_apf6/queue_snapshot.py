"""Render the existing studio theme with synthetic pending rows, offscreen."""
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QCoreApplication,QEvent
from mod_editor.apf_studio.apf_theme import install_theme
from tests.mod_editor.test_apf_b71_editor_workflow_qt import QueueQtTests
fixture=QueueQtTests(); fixture.setUpClass(); fixture.setUp()
try:
 app=QApplication.instance(); install_theme(app)
 panel=fixture.panel; panel.resize(1200,900); panel.show(); app.processEvents()
 panel.queue_edits.click(); panel.remove_button.click(); panel.ratings_button.click()
 panel.tendency.setValue(61);panel.tendency_button.click();panel.confirm_button.click()
 panel.details_toggle.setChecked(True);app.processEvents()
 QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);app.processEvents()
 assert panel.review_group.grab().save(str(Path(__file__).with_name('pending-edits.png')))
 print('Rendered synthetic queue: both formation blockers retained, independent tendency staged, review details expanded.')
finally:
 fixture.doCleanups()
