"""Offscreen authoring journey: stages data, saves a plan, preserves the source."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt5.QtWidgets import QApplication
    from tools.nfl2k5_weather_editor import WeatherDialog
except ImportError:
    QApplication = WeatherDialog = None
from mod_editor.core import nfl2k5_weather as weather
from tests.mod_editor.test_nfl2k5_weather import synthetic


@unittest.skipUnless(QApplication is not None, "PyQt5 absent; offscreen weather editor test unavailable")
class WeatherEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_undo_preset_and_saved_plan_reaches_the_writer(self):
        resource, digest = synthetic()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/"source.rost"
            source.write_bytes(resource)
            with patch.object(weather, "SHAPE_SHA256", digest), \
                    patch.object(weather, "load_resource", return_value=resource):
                dialog = WeatherDialog(source)
                self.addCleanup(dialog.close)
                self.assertFalse(dialog.save_button.isEnabled())
                self.assertEqual(dialog.draft.plan()["changes"], [])
                dialog.stadium.setCurrentIndex(5)
                dialog.month.setCurrentIndex(4)
                dialog.fields["temperature_f"].setValue(15)
                dialog.fields["precipitation_pct"].setValue(100)
                dialog.fields["wind_mph"].setValue(12)
                before_preset = dialog.draft.plan()
                dialog.preset_button.click()
                dialog.undo_button.click()
                self.assertEqual(dialog.draft.plan(), before_preset)
                destination = Path(directory)/"weather.json"
                emitted = []
                dialog.saved.connect(emitted.append)
                dialog.save_plan(destination)
                plan = weather.read_json(destination)
                self.assertEqual(len(plan["changes"]), 3)
                after, _ = weather.apply(resource, plan)
                weather.verify(after, plan, before=resource)
                self.assertEqual(emitted, [str(destination)])
                self.assertEqual(source.read_bytes(), resource)
                with self.assertRaises(weather.WeatherError):
                    dialog.save_plan(source)

    def test_bad_source_explains_cause_and_next_step_without_dialog(self):
        with patch.object(weather, "load_resource", side_effect=weather.WeatherError("Unsupported ROST version")):
            dialog = WeatherDialog("bad-source.iso")
            self.addCleanup(dialog.close)
            self.assertIn("Unsupported ROST version", dialog.status.text())
            self.assertIn("Choose a supported", dialog.status.text())
            self.assertFalse(dialog.save_button.isEnabled())
            self.assertFalse(dialog.preset_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
