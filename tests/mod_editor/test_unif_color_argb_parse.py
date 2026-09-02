"""2K5 uniform colour ARGB parse must not crash on bad/empty strings."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.gui.studio_qt import StudioMainWindow  # noqa: E402


class UnifColorArgbParseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_argb_to_qcolor_accepts_full_and_short(self) -> None:
        full = StudioMainWindow._argb_to_qcolor("FF385AAF")
        self.assertEqual((full.red(), full.green(), full.blue()), (0x38, 0x5A, 0xAF))
        short = StudioMainWindow._argb_to_qcolor("385AAF")
        self.assertEqual((short.red(), short.green(), short.blue()), (0x38, 0x5A, 0xAF))

    def test_argb_to_qcolor_fail_closed_on_garbage(self) -> None:
        bad = StudioMainWindow._argb_to_qcolor("")
        self.assertEqual((bad.red(), bad.green(), bad.blue()), (0, 0, 0))
        bad2 = StudioMainWindow._argb_to_qcolor("ZZZZ")
        self.assertEqual((bad2.red(), bad2.green(), bad2.blue()), (0, 0, 0))
        bad3 = StudioMainWindow._argb_to_qcolor("FF")
        self.assertEqual((bad3.red(), bad3.green(), bad3.blue()), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
