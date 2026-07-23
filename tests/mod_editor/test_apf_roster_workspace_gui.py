"""Offscreen disclosure test for the APF 53-row roster planner."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.roster_workspace_qt import (  # noqa: E402
    RosterReservePlanner,
)


class RosterReservePlannerDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_runtime_boundary_is_visible_before_a_source_is_loaded(self) -> None:
        planner = RosterReservePlanner(object())  # type: ignore[arg-type]
        note = planner.runtime_boundary_note.text()
        self.assertIn("Build Modded Game does not apply", note)
        self.assertIn("+0x120..+0x126", note)
        self.assertIn("safe extension storage remains unresolved", note)
        self.assertIn("one exact consumer", note)
        planner.close()


if __name__ == "__main__":
    unittest.main()
