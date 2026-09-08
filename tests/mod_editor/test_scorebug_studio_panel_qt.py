"""Offscreen Scorebar Studio page: build it, change a colour, undo, save, reopen, hand to Build."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox,
                                 QLabel, QLineEdit, QListWidget, QScrollBar, QWidget)
except ImportError:  # pragma: no cover - the shell needs Qt; the model does not
    QApplication = None
from mod_editor.core import nfl2k5_scorebug_author as a  # noqa: E402
from mod_editor.core import nfl2k5_scorebug_template as t  # noqa: E402


@unittest.skipUnless(QApplication is not None, "PyQt5 is absent; the offscreen Scorebar Studio page needs Qt")
class ScorebugStudioPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui.scorebug_studio_panel_qt import ScorebugStudioPanel
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name).resolve()
        self.panel = ScorebugStudioPanel()
        self.addCleanup(self.panel.deleteLater)
        self.addCleanup(self.panel.close)

    def test_page_lists_the_parts_presets_preview_and_the_game_note(self):
        titles = [self.panel.layer_list.item(i).text() for i in range(self.panel.layer_list.count())]
        self.assertEqual(titles, ["Bar frame", "ESPN mark", "Away team block", "Away score", "Home team block",
                                  "Home score", "Down and distance banner", "Clock strip"])
        self.assertEqual([self.panel.preset_list.item(i).text() for i in range(self.panel.preset_list.count())],
                         ["Reference (v10)", "Fable ESPN template", "Plain dark", "Retail-like"])
        self.assertEqual(self.panel.document.preset_id, "reference_v10")
        pixmap = self.panel.preview_label.pixmap()
        self.assertFalse(pixmap.isNull())
        self.assertEqual((pixmap.width(), pixmap.height()), a.HUD_SIZE)
        self.assertIn("Game slot estimate", self.panel.status_label.text())
        self.assertIn("draws itself", self.panel.game_note.text())
        self.assertIn("preview only", " ".join(w.text() for w in self.panel.findChildren(QLabel)).lower())
        self.assertFalse(self.panel.is_dirty)
        self.assertEqual(self.panel.dirty_label.text(), "")
        self.assertEqual(self.panel.colour_limit_spin.value(), self.panel.document.colour_limit)
        self.assertEqual(self.panel.state_combo.currentData(), self.panel.document.state_id)
        self.assertEqual(self.panel.preset_list.currentItem().text(), "Reference (v10)")
        self.assertIn("shipped", self.panel.preset_summary.text())

    def test_every_control_has_an_accessible_name_and_no_em_dashes(self):
        kinds = (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox, QLineEdit, QListWidget)
        for widget in self.panel.findChildren(QWidget):
            if isinstance(widget, QScrollBar) or widget.objectName().startswith("qt_"):
                continue  # Qt's own scroll bars and spin box editors
            if isinstance(widget, kinds):
                self.assertTrue(widget.accessibleName(), f"{type(widget).__name__} {widget.objectName()!r} {getattr(widget, 'text', lambda: '')()!r}")
            for text in (widget.accessibleName(), widget.toolTip(), widget.accessibleDescription(),
                         getattr(widget, "text", lambda: "")(), getattr(widget, "title", lambda: "")()):
                self.assertNotIn("—", text)
        self.assertTrue(all(self.panel.state_combo.itemText(i) for i in range(self.panel.state_combo.count())))

    def test_changing_a_colour_marks_dirty_and_undo_redo_restore_it(self):
        self.panel.select_layer("down")
        before = self.panel.document.layers["down"]
        self.panel.set_fill("down", "#123456FF")
        self.assertEqual(self.panel.document.layers["down"].fill, "#123456FF")
        self.assertEqual(self.panel.fill_button.colour, "#123456FF")
        self.assertTrue(self.panel.is_dirty)
        self.assertEqual(self.panel.dirty_label.text(), "Unsaved changes")
        self.assertTrue(self.panel.undo_button.isEnabled())
        self.panel.undo_stack.undo()
        self.assertEqual(self.panel.document.layers["down"], before)
        self.assertFalse(self.panel.is_dirty)
        self.assertTrue(self.panel.redo_button.isEnabled())
        self.panel.undo_stack.redo()
        self.assertEqual(self.panel.document.layers["down"].fill, "#123456FF")
        # The picked-colour path the QColorDialog handler uses.
        self.panel.apply_picked_colour("border", "#FF00FFFF")
        self.assertEqual(self.panel.document.layers["down"].border.colour, "#FF00FFFF")
        self.panel.apply_picked_colour(("stop", 0), "#00FF00FF")
        self.assertEqual(self.panel.document.layers["down"].gradient.stops[0], "#00FF00FF")

    def test_slider_drags_merge_into_one_undo_step_and_controls_write_the_document(self):
        self.panel.select_layer("clock_quarter")
        original = self.panel.document.layers["clock_quarter"]
        self.panel.radius_slider.setValue(3)
        self.panel.radius_slider.setValue(4)
        self.panel.radius_slider.setValue(5)
        self.assertEqual(self.panel.document.layers["clock_quarter"].radius, 5)
        self.assertEqual(self.panel.undo_stack.count(), 1)
        self.panel.opacity_slider.setValue(70)
        self.assertEqual(self.panel.document.layers["clock_quarter"].opacity, 70)
        self.assertEqual(self.panel.undo_stack.count(), 2)
        self.panel.gradient_check.setChecked(True)
        self.assertIsNotNone(self.panel.document.layers["clock_quarter"].gradient)
        self.panel.middle_check.setChecked(True)
        self.assertEqual(len(self.panel.document.layers["clock_quarter"].gradient.stops), 3)
        self.panel.angle_spin.setValue(45)
        self.assertEqual(self.panel.document.layers["clock_quarter"].gradient.angle, 45)
        self.panel.border_check.setChecked(False)
        self.assertIsNone(self.panel.document.layers["clock_quarter"].border)
        self.panel.sample_edit.setText("OT|0:00|:00")
        self.panel.sample_edit.editingFinished.emit()
        self.assertEqual(self.panel.document.layers["clock_quarter"].sample_text, "OT|0:00|:00")
        while self.panel.undo_stack.canUndo():
            self.panel.undo_stack.undo()
        self.assertEqual(self.panel.document.layers["clock_quarter"], original)
        self.panel.reset_button.click()
        self.assertEqual(self.panel.document.layers["clock_quarter"], original)

    def test_save_reopen_and_use_in_build_emit_the_folder(self):
        received = []
        self.panel.folder_chosen.connect(received.append)
        self.panel.apply_preset("plain_dark")
        self.assertEqual(self.panel.document.preset_id, "plain_dark")
        self.panel.set_fill("frame", "#222244FF")
        folder = self.work / "my scorebar"
        self.assertTrue(self.panel.save_folder(folder))
        self.assertFalse(self.panel.is_dirty)
        self.assertEqual(self.panel.folder, folder)
        self.assertIn(str(folder), self.panel.folder_label.text())
        self.assertTrue((folder / "layout.json").is_file())
        self.assertTrue((folder / "1x" / "frame.png").is_file())
        self.assertTrue((folder / "2x" / "frame.png").is_file())
        self.assertTrue((folder / a.DOCUMENT_FILE).is_file())
        self.assertEqual(t.compile_folder(folder).image.tobytes(), self.panel.document.atlas().tobytes())
        self.panel.use_in_build()
        self.assertEqual(received, [str(folder)])
        self.assertIn("Build", self.panel.result.text())
        # Dirty again: Use in Build saves first, without a dialog, to the same folder.
        self.panel.set_fill("frame", "#442222FF")
        self.assertTrue(self.panel.is_dirty)
        self.panel.use_in_build()
        self.assertFalse(self.panel.is_dirty)
        self.assertEqual(received, [str(folder), str(folder)])
        self.assertEqual(a.Document.open_folder(folder).layers["frame"].fill, "#442222FF")
        from mod_editor.gui.scorebug_studio_panel_qt import ScorebugStudioPanel
        other = ScorebugStudioPanel()
        self.addCleanup(other.deleteLater)
        other.open_folder(folder)
        self.assertEqual(other.document, self.panel.document)
        self.assertEqual(other.folder, folder)
        self.assertFalse(other.is_dirty)
        self.assertEqual(other.preset_list.currentItem().text(), "Plain dark")

    def test_sample_state_writes_the_centre_text_and_undoes_as_one_step(self):
        self.panel.state_combo.setCurrentIndex(self.panel.state_combo.findData("two_minute"))
        self.assertEqual(self.panel.document.state_id, "two_minute")
        self.assertEqual(self.panel.document.layers["down"].sample_text, "2nd & 7")
        self.assertEqual(self.panel.document.layers["clock_quarter"].sample_text, "4th|2:00|:40")
        self.assertEqual(self.panel.undo_stack.count(), 1)
        self.panel.undo_stack.undo()
        self.assertEqual(self.panel.document.state_id, "first_and_ten")
        self.assertEqual(self.panel.document.layers["down"].sample_text, "1st & 10")
        self.assertEqual(self.panel.state_combo.currentData(), "first_and_ten")

    def test_widescreen_zoom_and_team_colours_change_only_the_preview(self):
        snapshot = self.panel.document.snapshot()
        self.panel.wide_check.setChecked(True)
        pixmap = self.panel.preview_label.pixmap()
        self.assertEqual((pixmap.width(), pixmap.height()), a.WIDE_SIZE)
        self.panel.zoom_check.setChecked(True)
        pixmap = self.panel.preview_label.pixmap()
        self.assertEqual((pixmap.width(), pixmap.height()), (a.WIDE_SIZE[0] * 2, a.WIDE_SIZE[1] * 2))
        self.panel.zoom_check.setChecked(False)
        self.panel.wide_check.setChecked(False)
        plain = self.panel.preview_image.tobytes()
        self.panel.team_check.setChecked(True)
        self.assertNotEqual(self.panel.preview_image.tobytes(), plain)
        self.assertEqual(self.panel.document.snapshot(), snapshot)
        self.assertFalse(self.panel.is_dirty)

    def test_use_my_image_fits_the_picture_and_colours_take_over_when_removed(self):
        from PIL import Image
        picture = self.work / "logo.png"
        Image.new("RGBA", (300, 120), (10, 200, 30, 255)).save(picture)
        self.panel.select_layer("left_mark")
        self.panel.use_image(picture)
        layer = self.panel.document.layers["left_mark"]
        self.assertIsNotNone(layer.image)
        self.assertEqual(layer.image.fit, "contain")
        self.assertEqual(layer.image.name, "logo.png")
        self.assertTrue(self.panel.fit_combo.isVisibleTo(self.panel))
        self.panel.fit_combo.setCurrentIndex(self.panel.fit_combo.findData("cover"))
        self.assertEqual(self.panel.document.layers["left_mark"].image.fit, "cover")
        self.panel.clip_check.setChecked(True)
        self.assertTrue(self.panel.document.layers["left_mark"].image.clip)
        folder = self.work / "logo bar"
        self.assertTrue(self.panel.save_folder(folder))
        self.assertTrue((folder / "images" / "left_mark_any.png").is_file())
        self.assertEqual(a.Document.open_folder(folder), self.panel.document)
        self.panel.remove_image()
        self.assertIsNone(self.panel.document.layers["left_mark"].image)
        self.panel.select_layer("away_block")
        self.panel.remove_image_button.click()
        self.assertIsNone(self.panel.document.layers["away_block"].image)
        self.assertEqual(self.panel.document.layers["away_block"].fill, a.DEFAULT_PAINT["away_block"].fill)

    def test_reference_round_trips_through_the_page_byte_for_byte(self):
        self.panel.open_folder(t.DEFAULT_FOLDER)
        self.assertEqual(self.panel.folder, t.DEFAULT_FOLDER)
        folder = self.work / "copy"
        self.assertTrue(self.panel.save_folder(folder))
        for scale in (1, 2):
            for name in t.LAYERS:
                self.assertEqual((folder / f"{scale}x" / f"{name}.png").read_bytes(),
                                 (t.DEFAULT_FOLDER / f"{scale}x" / f"{name}.png").read_bytes(), f"{scale}x/{name}")

    def test_errors_show_in_the_result_label_instead_of_dialogs(self):
        self.panel.open_folder(self.work / "missing")
        self.assertIn("not a folder", self.panel.result.text())
        self.panel.use_image(self.work / "missing.png")
        self.assertIn("not a regular file", self.panel.result.text())
        self.assertFalse(self.panel.is_dirty)
        (self.work / "not a template").mkdir()
        self.panel.open_folder(self.work / "not a template")
        self.assertIn("not a supported scorebar template", self.panel.result.text())

    def test_colour_limit_is_undoable_and_flows_into_the_saved_folder(self):
        self.panel.apply_preset("fable_espn")
        self.panel.colour_limit_spin.setValue(24)
        self.assertEqual(self.panel.document.colour_limit, 24)
        folder = self.work / "limited"
        self.assertTrue(self.panel.save_folder(folder))
        self.assertLessEqual(t.compile_folder(folder).receipt["colours"], 24)
        self.panel.undo_stack.undo()
        self.assertEqual(self.panel.document.colour_limit, a.DEFAULT_COLOUR_LIMIT)
        self.assertEqual(self.panel.colour_limit_spin.value(), a.DEFAULT_COLOUR_LIMIT)


if __name__ == "__main__":
    unittest.main()
