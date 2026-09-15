"""Offscreen colour controls, resets and actual project archive persistence."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from PyQt5.QtWidgets import QApplication
from mod_editor.core import nfl2k5_modern_color as mc
from mod_editor.gui.colour_lighting_qt import ColourLightingControls
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.gameplay_project_ui import observe_build_choices
from mod_editor.studio import project_archive


class ColourControlsQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def control(self):
        w = ColourLightingControls()
        self.addCleanup(w.deleteLater)
        return w

    def test_every_lever_has_slider_toggle_and_both_swatches(self):
        w = self.control()
        self.assertEqual(set(w.rows), set(mc.control_specs()))
        self.assertEqual(w.settings(), mc.normalize_settings())
        changed = []
        w.changed.connect(lambda: changed.append(True))
        before = w.rows['turf.value_lift']['prediction'].text()
        w.rows['turf.value_lift']['slider'].setValue(100)
        self.assertNotEqual(w.rows['turf.value_lift']['prediction'].text(), before)
        self.assertEqual(w.rows['turf.value_lift']['spin'].value(), 1.25)
        for key, row in w.rows.items():
            self.assertTrue(row['prediction'].text())
            self.assertTrue(row['target'].text())
            self.assertIn('PREDICTED', row['prediction'].toolTip())
            self.assertTrue(row['slider'].accessibleName())
        value = w.settings()['values']['turf.value_lift']
        w.rows['turf.value_lift']['use'].setChecked(False)
        self.assertFalse(w.rows['turf.value_lift']['slider'].isEnabled())
        self.assertEqual(w.settings()['values']['turf.value_lift'], value)
        w.rows['turf.value_lift']['use'].setChecked(True)
        self.assertEqual(w.settings()['values']['turf.value_lift'], value)
        self.assertGreater(len(changed), 2)

    def test_links_rigs_class_and_resets_retain_master_off(self):
        w = self.control()
        for group in ('endzones', 'outside'):
            self.assertFalse(w.rows[group+'.saturation']['spin'].isEnabled())
            w.links[group].setChecked(False)
            self.assertTrue(w.rows[group+'.saturation']['spin'].isEnabled())
            w.rows[group+'.saturation']['spin'].setValue(.5)
        w.class_combo.setCurrentIndex(w.class_combo.findData('material'))
        self.assertFalse(w.rows['turf.map_contrast']['use'].isEnabled())
        for i, name in enumerate(mc.RIG_LABELS):
            w.rig_combo.setCurrentIndex(i)
            self.assertEqual(w.light_stack.currentIndex(), i)
            self.assertEqual(w.settings()['preview_rig'], name)
        w.retail_button.click()
        self.assertEqual(w.settings(), mc.normalize_settings(mc.default_settings(retail=True)))
        w.broadcast_button.click()
        self.assertEqual(w.settings(), mc.normalize_settings())
        self.assertIn('Option is Off', w.state_label.text())

    def test_outside_swatch_follows_field_and_unlinked_saved_colour(self):
        w = self.control()
        row = w.rows['outside.saturation']
        for rig in mc.MODERN_RIGS:
            w.rig_combo.setCurrentIndex(w.rig_combo.findData(rig))
            self.assertEqual(row['target'].text(), w.rows['turf.saturation']['prediction'].text())
            expected = mc.preview(w.settings(), surface='outside')['predicted']
            self.assertEqual(row['prediction'].text(), ', '.join(map(str, expected)))
        before = row['prediction'].text()
        w.rows['turf.value_lift']['spin'].setValue(1.5)
        self.assertNotEqual(row['prediction'].text(), before)
        w.links['outside'].setChecked(False)
        self.assertTrue(row['spin'].isEnabled())
        self.assertFalse(w.rows['outside.match']['spin'].isEnabled())
        row['spin'].setValue(.6)
        custom = row['prediction'].text()
        w.rows['turf.value_lift']['spin'].setValue(2.8)
        self.assertEqual(row['prediction'].text(), custom)
        w.links['outside'].setChecked(True)
        self.assertNotEqual(row['prediction'].text(), custom)
        w.links['outside'].setChecked(False)
        self.assertEqual(row['prediction'].text(), custom)
        w.broadcast_button.click()
        self.assertTrue(w.links['outside'].isChecked())
        self.assertFalse(mc.is_custom(w.settings()))


    def panel(self):
        p = BuildPanel()
        self.addCleanup(p.deleteLater)
        state = {k: 'retail' for k in p._boxes()}
        state.update(path='retail.iso', container='xiso', throw=None)
        p.apply_state(state)
        return p

    def test_build_plan_off_presets_changes_receipt_state_and_project_archive(self):
        panel = self.panel()
        self.assertFalse(panel.plan().modern_color)
        panel.colour_lighting.rows['rig_night_indoor.fill']['spin'].setValue(.63)
        panel.colour_lighting.rows['turf.hue_pull']['use'].setChecked(False)
        panel.colour_lighting.links['outside'].setChecked(False)
        panel.colour_lighting.class_combo.setCurrentIndex(1)
        settings = panel.plan().modern_color_settings
        self.assertTrue(mc.is_custom(settings))
        panel.modern_color_check.setChecked(True)
        self.assertTrue(panel._modern_color_changed())
        self.assertTrue(panel.plan().modern_color)
        state = panel.project_build_settings()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / 'colour.2k5mod'
            project_archive.save_project_archive(catalog=None, asset_io=None, edits=(), destination=path, build_settings=state)
            loaded = project_archive.load_project_archive(source=path, catalog=None, asset_io=None, private_root=path.parent)
            try:
                another = self.panel()
                another.restore_project_build_settings(loaded.build_settings)
                self.assertEqual(another.plan().modern_color_settings, settings)
                self.assertTrue(another.plan().modern_color)
                self.assertTrue(another.colour_lighting.links['outside'].isEnabled())
            finally:
                loaded.cleanup()
        for preset in ('softdrink_basic', 'softdrink_advanced', 'softdrink_experimental'):
            panel.apply_preset(preset)
            self.assertFalse(panel.plan().modern_color)
            self.assertEqual(panel.plan().modern_color_settings, settings)
        state = dict(panel._state, modern_color='applied (custom)', modern_color_settings=settings)
        panel.apply_state(state)
        self.assertTrue(panel.modern_color_check.isEnabled())
        self.assertTrue(panel.plan().modern_color)
        self.assertFalse(panel._modern_color_changed())
        panel.colour_lighting.rows['rig_night_indoor.fill']['spin'].setValue(.72)
        self.assertTrue(panel._modern_color_changed())
        self.assertTrue(any('colour' in text for text in panel.selected_labels()))

    def test_daylight_broadcast_reset_updates_values_swatches_and_keeps_master_on(self):
        panel = self.panel()
        panel.modern_color_check.setChecked(True)
        w = panel.colour_lighting
        for name, values, prediction, target in (
                ('day', (.44, 1.60, .99), '89, 105, 61', '88, 105, 61'),
                ('afternoon', (.60, 1.20, 1.04), '87, 103, 61', '98, 119, 72')):
            w.rows[f'rig_{name}.ambient']['spin'].setValue(.9)
            w.retail_button.click()
            self.assertTrue(panel.plan().modern_color)
            self.assertEqual(mc.modern_table(mc._retail_table(name), w.settings()), mc._retail_table(name))
            w.broadcast_button.click()
            self.assertTrue(panel.plan().modern_color)
            w.rig_combo.setCurrentIndex(w.rig_combo.findData(name))
            for lever, value in zip(('ambient', 'key', 'fill'), values):
                self.assertEqual(w.rows[f'rig_{name}.{lever}']['spin'].value(), value)
            self.assertEqual(w.rows['turf.saturation']['prediction'].text(), prediction)
            self.assertEqual(w.rows['turf.saturation']['target'].text(), target)
            self.assertFalse(mc.is_custom(w.settings()))
        w.rig_combo.setCurrentIndex(w.rig_combo.findData('night_indoor'))
        self.assertEqual(w.rows['turf.saturation']['prediction'].text(), '102, 122, 52')

    def test_reset_buttons_and_slider_notify_project_observer(self):
        panel = self.panel()
        notifications = []
        observe_build_choices(panel, lambda *args: notifications.append(panel.colour_lighting.settings()))
        panel.colour_lighting.rows['turf.value_lift']['slider'].setValue(200)
        self.assertEqual(notifications[-1], panel.plan().modern_color_settings)
        panel.colour_lighting.retail_button.click()
        self.assertEqual(notifications[-1], mc.normalize_settings(mc.default_settings(retail=True)))
        panel.colour_lighting.broadcast_button.click()
        self.assertEqual(notifications[-1], mc.normalize_settings())
        self.assertFalse(panel.plan().modern_color)


if __name__ == '__main__':
    unittest.main(verbosity=2)
