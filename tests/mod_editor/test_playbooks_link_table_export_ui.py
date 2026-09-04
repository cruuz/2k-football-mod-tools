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

    def export_g1_dime_from_nickel_package_map_pack(self, *args, **kwargs):
        raise RuntimeError("not used")

    def export_g2_ace_from_quads_link_table_pack(self, *args, **kwargs):
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

    def playbook_raw_body(self, *args, **kwargs):
        raise RuntimeError("not used")

    def stage_formation_selector(self, *args, **kwargs):
        raise RuntimeError("not used")

    def create_authored_play(self, *args, **kwargs):
        raise RuntimeError("not used")

    def playbook_teams(self, *args, **kwargs):
        return ()

    def load_playbook_pack(self, *args, **kwargs):
        raise RuntimeError("not used")

    def preview_playbook_pack(self, *args, **kwargs):
        raise RuntimeError("not used")

    def install_playbook_pack(self, *args, **kwargs):
        raise RuntimeError("not used")

    def export_playbook_pack(self, *args, **kwargs):
        raise RuntimeError("not used")


class LinkTableExportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_panel_exposes_experimental_export_with_honesty_banner(self) -> None:
        panel = PlaybooksPanel(_Host())
        self.assertTrue(hasattr(panel, "export_link_copy_button"))
        self.assertTrue(hasattr(panel, "export_pkgmap_copy_button"))
        self.assertTrue(hasattr(panel, "export_g1_pack_button"))
        self.assertTrue(hasattr(panel, "export_g2_pack_button"))
        self.assertTrue(hasattr(panel, "link_donor_combo"))
        self.assertTrue(hasattr(panel, "g1_nickel_donor_button"))
        self.assertTrue(panel.export_g1_pack_button.isEnabled())
        self.assertTrue(panel.export_g2_pack_button.isEnabled())
        self.assertTrue(
            str(panel.export_g1_pack_button.property("disableReason") or "").strip()
        )
        self.assertTrue(
            str(panel.export_g2_pack_button.property("disableReason") or "").strip()
        )
        banner = panel.link_copy_banner.text()
        self.assertIn("Experimental offline", banner)
        self.assertIn("runtime", banner.casefold())
        self.assertIn("ISO is never modified", banner)
        # Never silent-gray: stay clickable; disableReason teaches load/select.
        self.assertTrue(panel.export_link_copy_button.isEnabled())
        self.assertTrue(panel.export_pkgmap_copy_button.isEnabled())
        self.assertTrue(panel.g1_nickel_donor_button.isEnabled())
        reason = str(panel.export_pkgmap_copy_button.property("disableReason") or "")
        self.assertTrue(reason.strip())
        self.assertTrue(
            "formation" in reason.casefold() or "load" in reason.casefold(),
            msg=reason,
        )
        g1_reason = str(
            panel.g1_nickel_donor_button.property("disableReason") or ""
        ).strip()
        self.assertTrue(g1_reason)
        self.assertTrue(
            "nickel" in g1_reason.casefold()
            or "book" in g1_reason.casefold()
            or "load" in g1_reason.casefold(),
            msg=g1_reason,
        )

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
        self.assertTrue(
            callable(
                getattr(
                    Nfl2k5StudioFacade,
                    "export_g1_dime_from_nickel_package_map_pack",
                    None,
                )
            )
        )
        self.assertTrue(
            callable(
                getattr(
                    Nfl2k5StudioFacade,
                    "export_g2_ace_from_quads_link_table_pack",
                    None,
                )
            )
        )

    def test_g1_nickel_donor_helper_selects_nickel(self) -> None:
        class _Formation:
            def __init__(self, name: str) -> None:
                self.name = name

        class _Book:
            asset_id = "book.g1"
            outer_index = 1
            book_name = "G1"
            formations = (
                _Formation("4-3"),
                _Formation("Nickel"),
                _Formation("Dime"),
            )
            plays = ()

        panel = PlaybooksPanel(_Host())
        try:
            panel._all_books = (_Book(),)
            panel.selected_asset_id = "book.g1"
            panel.link_donor_combo.clear()
            for index, formation in enumerate(_Book.formations):
                panel.link_donor_combo.addItem(formation.name, index)
            panel.g1_nickel_donor_button.setProperty("disableReason", "")
            panel._select_g1_nickel_donor()
            self.assertEqual(panel.link_donor_combo.currentData(), 1)
            self.assertIn("Nickel", panel.progress_label.text())
            self.assertIn("runtime unproved", panel.progress_label.text().casefold())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
