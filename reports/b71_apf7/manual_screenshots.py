"""Capture the restored utility with read-only retail identity, no clone writes."""
import json
import os
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio.book_identity_qt import BookIdentityPanel
from mod_editor.apf_studio.apf_theme import install_theme
from tests.mod_editor.test_apf_playcall_research_native import INDEX

app = QApplication([])
install_theme(app)
panel = BookIdentityPanel(lambda title, work, done, busy: done(work(lambda *_: None)), consolidated=True)
panel.show_manual_allocation()
panel.load_path(INDEX)
panel.donor.setCurrentText('O-ManBlock')
panel.team.setCurrentIndex(39)
assert panel.team.count() == 40
assert panel.label.count() == 28
assert panel.reviewed is None
out = Path(__file__).parent
for width, height in ((1280, 720), (1920, 1080)):
    panel.resize(width, height)
    panel.show()
    for _ in range(5): app.processEvents()
    assert panel.grab().save(str(out/f'manual-books-{width}x{height}.png'))
print(json.dumps({'team_slots':panel.team.count(), 'unused_offense_labels':panel.label.count(),
                  'selected_team_slot':panel.team.currentData(), 'reviewed':False, 'built':False}))
panel.close()
