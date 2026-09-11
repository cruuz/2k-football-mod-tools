"""Beta 66 Supersim wiring: the MyCareer page's Settings group and the merged footer codec.

Offscreen widgets and synthetic signed containers; no display, disc or game boot.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock
import zipfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HAVE_QT = importlib.util.find_spec("PyQt5") is not None

from mod_editor.core import nfl2k5_my_career_save as save
from mod_editor.core import nfl2k5_roster_records as records
from tests.nfl2k5_my_career_fixture import draft_save
from tests.mod_editor.test_nfl2k5_my_career_inline import block_for


def signed_career(directory, choice, stat_line_off=False, first_person=True, star_off=True):
    """A synthetic signed inline career container with the requested footer choices."""
    source = draft_save()
    footer = bytearray(block_for(source))
    footer[82] = (int(first_person) | (int(star_off) << 2) | (int(stat_line_off) << 4)
                  | save._SUPERSIM_BITS[save.SUPERSIM_CHOICES.index(choice)])
    payload = source + save.seal(footer)
    path = Path(directory) / f"career-{choice.replace(' ', '-')}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("SAVEGAME.DAT", payload)
        archive.writestr("EXTRA", records.sign_save(payload))
        archive.writestr("SaveMeta.xbx", b"synthetic metadata")
    return path, payload


class FooterCodecTests(unittest.TestCase):
    def test_stat_line_bit_survives_every_supersim_choice_and_studio_rewrite(self):
        source = draft_save()
        footer = bytearray(block_for(source))
        footer[82] = 0x15  # first person On, star Off, stat line Off
        payload = source + save.seal(footer)
        for choice, bits in zip(save.SUPERSIM_CHOICES, (2, 0, 8)):
            result = save.with_supersim(payload, choice)
            self.assertEqual(save.read(result)[82], bits | 0x15)
            self.assertEqual(save.supersim_choice(result), choice)
            state = save.to_runtime(save.read(result))
            self.assertEqual(int.from_bytes(state[2712:2716], "little"), 1)
            self.assertEqual(int.from_bytes(state[2696:2700], "little"), (1, 0, 2)[(2, 0, 8).index(bits)])
            self.assertEqual(save.from_runtime(state), save.read(result))
        for invalid in (0x0A, 0x1A, 0x20, 0x30):
            block = bytearray(footer); block[82] = invalid
            with self.assertRaises(save.CareerSaveError):
                save.validate(save.seal(block))


@unittest.skipUnless(HAVE_QT, "offscreen MyCareer page tests require PyQt5")
class SettingsGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui import my_career_panel_qt as panel
        self.module = panel
        self.page = panel.MyCareerPanel()
        self.addCleanup(self.page.close)

    def finish(self):
        deadline = time.monotonic() + 10
        while self.page._task is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertIsNone(self.page._task, "worker did not finish within 10 seconds")

    def test_group_reads_each_choice_exports_a_signed_copy_and_keeps_the_source(self):
        page = self.page
        self.assertEqual([page.career_supersim.itemText(i) for i in range(page.career_supersim.count())],
                         list(save.SUPERSIM_CHOICES))
        self.assertEqual(page.career_supersim.currentText(), "Fast forward")
        self.assertFalse(page.career_supersim.isEnabled())
        self.assertFalse(page.career_settings_export.isEnabled())
        with tempfile.TemporaryDirectory() as directory:
            for choice in save.SUPERSIM_CHOICES:
                source, payload = signed_career(directory, choice, stat_line_off=True)
                before = source.read_bytes()
                with mock.patch.object(self.module.QFileDialog, "getOpenFileName", return_value=(str(source), "")):
                    page._choose_career_settings()
                    self.assertIsNotNone(page._task)
                    # Every Settings control is disabled while the worker runs.
                    self.assertFalse(page.career_settings_load.isEnabled())
                    self.assertFalse(page.career_settings_export.isEnabled())
                    self.assertFalse(page.career_supersim.isEnabled())
                    self.finish()
                self.assertEqual(page.career_supersim.currentText(), choice)
                self.assertEqual(page.career_settings_path.text(), str(source))
                self.assertTrue(page.career_supersim.isEnabled())
                self.assertTrue(page.career_settings_export.isEnabled())
                self.assertIn(choice, page.result.text())
                other = save.SUPERSIM_CHOICES[(save.SUPERSIM_CHOICES.index(choice) + 1) % 3]
                page.career_supersim.setCurrentText(other)
                target = Path(directory) / f"export-{choice.replace(' ', '-')}.zip"
                with mock.patch.object(self.module.QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                    page._export_career_settings()
                    self.finish()
                self.assertIn("read-back passed", page.result.text())
                reopened = records.SaveContainer.load(target)
                self.assertEqual(save.supersim_choice(reopened.savegame), other)
                self.assertEqual(save.read(reopened.savegame)[82] & 0x15, 0x15)  # FPF, star, stat line kept
                self.assertEqual(reopened.savegame[:-128], payload[:-128])
                self.assertEqual(source.read_bytes(), before)
                with mock.patch.object(self.module.QFileDialog, "getOpenFileName", return_value=(str(target), "")):
                    page._choose_career_settings(); self.finish()
                self.assertEqual(page.career_supersim.currentText(), other)

    def test_non_career_save_and_cancelled_dialogs_leave_the_group_untouched(self):
        page = self.page
        with tempfile.TemporaryDirectory() as directory:
            plain = draft_save()
            path = Path(directory) / "franchise.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("SAVEGAME.DAT", plain)
                archive.writestr("EXTRA", records.sign_save(plain))
            with mock.patch.object(self.module.QFileDialog, "getOpenFileName", return_value=(str(path), "")):
                page._choose_career_settings(); self.finish()
            self.assertFalse(page.career_supersim.isEnabled())
            self.assertFalse(page.career_settings_export.isEnabled())
            self.assertEqual(page.career_settings_path.text(), "")
            self.assertTrue(page.result.text())
            self.assertNotIn("Saved Supersim setting", page.result.text())
            with mock.patch.object(self.module.QFileDialog, "getOpenFileName", return_value=("", "")):
                page._choose_career_settings()
            self.assertIsNone(page._task)
            page._export_career_settings()  # no source chosen: no dialog, no worker
            self.assertIsNone(page._task)
            self.assertTrue(page.career_settings_load.isEnabled())


if __name__ == "__main__":
    unittest.main()
