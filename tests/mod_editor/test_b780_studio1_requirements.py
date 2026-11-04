"""b780 studio1 (Q60): one copy of the "this box needs that box" rules.

Build and Game Fixes share their check boxes, and each page used to carry its own rules between them: beta62_options.CHILDREN
(parent -> children, for the beta-62 pairs, read by both pages) and the Build page's ANNIVERSARY_DEPENDENCIES (child -> parents,
for the Anniversary and clock rules, unknown to Game Fixes).  A rule held by one page only is how the two came to disagree about
the same plan (Game Fixes showed unticked boxes that the plan had ticked).  beta62_options.REQUIRES is now the only table, CHILDREN
is derived from it, and both pages wire it through the same helpers.
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.gui import beta62_options as r62_ui  # noqa: E402


class OneTableTests(unittest.TestCase):
    def test_the_children_table_is_the_requires_table_turned_around(self) -> None:
        inverse = {}
        for child, parents in r62_ui.REQUIRES.items():
            for parent in parents:
                inverse.setdefault(parent, []).append(child)
        self.assertEqual({parent: tuple(kids) for parent, kids in inverse.items()}, r62_ui.CHILDREN)
        # the shapes the older tests and callers rely on
        self.assertEqual(r62_ui.CHILDREN["coverage_trail"], ("coverage_hitch_brake",))
        self.assertEqual(r62_ui.CHILDREN["weekly_prep"], ("weekly_prep_cpu", "weekly_prep_remember"))
        self.assertEqual(r62_ui.CHILDREN["k128_memory"], ("k128_roster_heap", "k128_early"))
        self.assertEqual(r62_ui.REQUIRES["cpu_clock2_overtime"], ("cpu_clock2",))
        self.assertEqual(set(r62_ui.VALIDATED_TOGETHER) - set(r62_ui.CHILDREN), set())      # only real parents

    def test_the_build_page_keeps_the_old_name_for_the_same_table_and_neither_page_holds_a_second_copy(self) -> None:
        from mod_editor.gui import build_panel_qt
        self.assertIs(build_panel_qt.ANNIVERSARY_DEPENDENCIES, r62_ui.REQUIRES)
        # a tripwire for a second literal: no page module spells out any rule as a dict entry of its own
        for module in ("build_panel_qt", "gameplay_patches_panel_qt", "gameplay_project_ui"):
            source = (ROOT / "mod_editor" / "gui" / f"{module}.py").read_text(encoding="utf-8")
            for child in r62_ui.REQUIRES:
                self.assertIsNone(re.search(r'^\s*"%s":\s*\(' % re.escape(child), source, re.M), (module, child))

    def test_the_helpers_follow_the_rules_and_leave_a_box_that_cannot_change_alone(self) -> None:
        class Box:
            def __init__(self, checked=False, enabled=True):
                self.checked, self.enabled = checked, enabled

            def isEnabled(self):
                return self.enabled

            def isChecked(self):
                return self.checked

            def setChecked(self, value):
                self.checked = value

        boxes = {key: Box() for key in ("espn25_era_rules", "espn25_more_moments", "dynamic_kickoff", "defensive_try", "overtime")}
        boxes["overtime"].enabled = False                                   # installed or foreign: nobody can tick it
        r62_ui.tick_parents("espn25_era_rules", boxes.get)
        self.assertEqual({key: box.checked for key, box in boxes.items() if key != "espn25_era_rules"},
                         {"espn25_more_moments": True, "dynamic_kickoff": True, "defensive_try": True, "overtime": False})
        boxes["espn25_era_rules"].checked = True
        boxes["overtime"].checked = True                                    # installed and locked on
        boxes["overtime"].enabled = False
        r62_ui.untick_children("dynamic_kickoff", boxes.get)
        self.assertFalse(boxes["espn25_era_rules"].checked)
        boxes["espn25_era_rules"].checked = True
        r62_ui.untick_children("overtime", boxes.get)                       # a locked child is not cleared
        r62_ui.tick_parents("not_a_child", boxes.get)                      # unknown keys are ignored
        r62_ui.untick_children("not_a_parent", {}.get)


class _Pages(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
        required = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
        if not required.exists():
            raise unittest.SkipTest(f"Missing asset: {required}")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        source = Path(self.tmp.name) / "retail.xiso.iso"
        source.write_bytes(b"x" * 4096)
        self.window = StudioMainWindow(eager_pages=True, facade=BrowseOnlyFacade(), offer_recovery=False)
        self.addCleanup(self.app.processEvents)
        self.addCleanup(self.window.deleteLater)
        self.build, self.fixes = self.window._build_panel, self.window._gameplay_patches_panel
        state = {key: "retail" for key in self.build._boxes()}
        state.update(path=str(source), container="xiso", throw=None, speed_threshold="retail")
        for panel in (self.build, self.fixes):
            panel.apply_state(state)
        self.app.processEvents()

    def reset(self) -> None:
        for box in self.build._boxes().values():
            box.setChecked(False)
        self.app.processEvents()

    def both(self, key):
        return (self.build._boxes()[key].isChecked(), self.fixes.checks[key].isChecked() if key in self.fixes.checks else None)


class EveryRuleOnBothPagesTests(_Pages):
    def test_ticking_a_child_ticks_its_parents_on_both_pages_whichever_page_it_was_ticked_on(self) -> None:
        shared = set(self.build._boxes()) & set(self.fixes.checks)
        for page in ("build", "fixes"):
            for child, parents in r62_ui.REQUIRES.items():
                with self.subTest(page=page, child=child):
                    self.reset()
                    box = self.build._boxes()[child] if page == "build" else self.fixes.checks.get(child)
                    if box is None or not box.isEnabled():
                        continue                                            # this page has no such box
                    box.setChecked(True)
                    self.app.processEvents()
                    for key in (child, *parents):
                        build_box = self.build._boxes()[key]
                        if build_box.isEnabled():
                            self.assertTrue(build_box.isChecked(), (page, child, key))
                        if key in shared:
                            self.assertEqual(self.both(key)[0], self.both(key)[1], (page, child, key))     # the pages agree

    def test_unticking_a_parent_clears_its_children_on_both_pages(self) -> None:
        for page in ("build", "fixes"):
            for parent, children in r62_ui.CHILDREN.items():
                with self.subTest(page=page, parent=parent):
                    self.reset()
                    parent_box = self.build._boxes()[parent]
                    parent_box.setChecked(True)
                    for child in children:
                        self.build._boxes()[child].setChecked(True)
                    self.app.processEvents()
                    box = parent_box if page == "build" else self.fixes.checks.get(parent)
                    if box is None:
                        continue
                    box.setChecked(False)
                    self.app.processEvents()
                    for child in children:
                        self.assertFalse(self.build._boxes()[child].isChecked(), (page, parent, child))
                        if child in self.fixes.checks:
                            self.assertFalse(self.fixes.checks[child].isChecked(), (page, parent, child))


if __name__ == "__main__":
    unittest.main()
