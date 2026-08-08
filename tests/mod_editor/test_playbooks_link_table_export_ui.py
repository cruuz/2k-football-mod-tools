"""Experimental link-table export UI + honesty surface."""

from __future__ import annotations

import sys
import unittest

from PyQt5.QtWidgets import QApplication

from mod_editor.gui.playbooks_panel_qt import PlaybooksPanel


class _Host:
    source_ready = True
    playbook_available = True

    def browse_playbooks(self, search, progress):
        return ()

    def export_playbook(self, *args, **kwargs):
        raise RuntimeError("not used")

    def export_playbook_link_table_copy(self, *args, **kwargs):
        raise RuntimeError("not used")

    def export_playbook_package_map_copy(self, *args, **kwargs):
        raise RuntimeError("not used")

    def copy_play_assignment_route(self, *args, **kwargs):
        raise RuntimeError("not used")

    def revert_play_assignment_route(self, *args, **kwargs):
        raise RuntimeError("not used")

    def create_formation(self, *args, **kwargs):
        raise RuntimeError("not used")

    def create_play(self, *args, **kwargs):
        raise RuntimeError("not used")

    def revert_formation_create(self, *args, **kwargs):
        raise RuntimeError("not used")

    def revert_play_create(self, *args, **kwargs):
        raise RuntimeError("not used")


class LinkTableExportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_panel_exposes_experimental_export_with_honesty_banner(self) -> None:
        panel = PlaybooksPanel(_Host())
        self.assertTrue(hasattr(panel, "export_link_copy_button"))
        self.assertTrue(hasattr(panel, "export_pkgmap_copy_button"))
        self.assertTrue(hasattr(panel, "link_donor_combo"))
        banner = panel.link_copy_banner.text()
        self.assertIn("Experimental offline", banner)
        self.assertIn("runtime", banner.casefold())
        self.assertIn("ISO is never modified", banner)
        # Disabled until two different formations selected
        self.assertFalse(panel.export_link_copy_button.isEnabled())
        self.assertFalse(panel.export_pkgmap_copy_button.isEnabled())

    def test_facade_ships_export_playbook_link_table_copy(self) -> None:
        from mod_editor.studio.facade import Nfl2k5StudioFacade

        self.assertTrue(
            callable(getattr(Nfl2k5StudioFacade, "export_playbook_link_table_copy", None))
        )
        self.assertTrue(
            callable(
                getattr(Nfl2k5StudioFacade, "export_playbook_package_map_copy", None)
            )
        )


if __name__ == "__main__":
    unittest.main()
