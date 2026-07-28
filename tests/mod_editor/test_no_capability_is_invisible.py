"""A capability that is enabled must be reachable, and the version must be true.

Two things went wrong at once, and a modder found both from one screenshot.

**The facemask colours were switched on and still invisible.** Uniforms &
Equipment builds a uniform-set browser around exactly one capability,
``nfl2k5.uniforms.all_visual``, and dropped the other three filed under that
category -- including ``nfl2k5.colors.unif_words``. Enabling it by default
changed nothing anybody could see, and "where is it?" had no honest answer.

**The window said RC36 while running RC38.** ``mod_editor.__version__`` is what
the title bar renders, and three releases bumped the changelogs, STATUS.md and
the docs without ever touching it. A user cannot tell whether they updated, and
neither can we when they send a screenshot.

Both checks below are pure metadata; they need no retail data and no Qt.
"""

from __future__ import annotations

import ast
from pathlib import Path
import re
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor import __version__  # noqa: E402
from mod_editor.core.capabilities import CapabilityRegistryLoader  # noqa: E402
from mod_editor.core.product_catalog import (  # noqa: E402
    _CATEGORY_TITLES, PRODUCT_CATEGORY_ORDER, build_nfl2k5_product_catalog,
)

_STUDIO = _REPO_ROOT / "mod_editor" / "gui" / "studio_qt.py"


class VersionTruthTests(unittest.TestCase):
    """The number on screen has to be the number that shipped."""

    def test_the_displayed_version_matches_the_changelog_and_status(self) -> None:
        candidate = __version__.rsplit("rc", 1)[-1]
        displayed = f"v1.0 RC{candidate}"
        status = (_REPO_ROOT / "STATUS.md").read_text(encoding="utf-8")
        self.assertTrue(
            status.startswith(f"# 2K5 Mod Studio — {displayed} Release Status"),
            f"STATUS.md does not lead with {displayed}; the app would show a "
            "version that never shipped",
        )
        changelog = (
            _REPO_ROOT / "docs" / "mod_editor" / "2k5_mod_studio_changelog.md"
        ).read_text(encoding="utf-8")
        headings = re.findall(r"^## (v1\.0 RC\d+)", changelog, re.MULTILINE)
        self.assertTrue(headings, "the changelog has no release headings")
        self.assertEqual(
            headings[0], displayed,
            f"the newest changelog entry is {headings[0]} but the app reports "
            f"{displayed}",
        )

    def test_the_getting_started_document_agrees(self) -> None:
        candidate = __version__.rsplit("rc", 1)[-1]
        doc = (
            _REPO_ROOT / "docs" / "mod_editor" / "2k5_mod_studio_getting_started.md"
        ).read_text(encoding="utf-8")
        self.assertTrue(doc.startswith(f"# 2K5 Mod Studio v1.0 RC{candidate} —"))


class EveryCapabilityIsReachableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = build_nfl2k5_product_catalog(CapabilityRegistryLoader().load())

    def test_the_facemask_colours_live_in_uniforms_and_equipment(self) -> None:
        found = [
            section.category.value
            for section in self.catalog.sections
            for binding in section.capabilities
            if binding.capability_id == "nfl2k5.colors.unif_words"
        ]
        self.assertEqual(found, ["uniforms_equipment"])

    def test_the_facemask_colours_are_enabled_by_default(self) -> None:
        binding = self.catalog.binding("nfl2k5.colors.unif_words")
        self.assertTrue(binding.capability.raw["gui"]["expose"])
        self.assertTrue(
            binding.capability.raw["gui"]["default_enabled"],
            "an capability nobody can turn on is the same as one that is absent",
        )

    def test_every_section_reaches_all_of_its_capabilities(self) -> None:
        """No category may hold a capability its page never renders."""
        assigned = {
            binding.capability_id
            for section in self.catalog.sections
            for binding in section.capabilities
        }
        self.assertEqual(len(assigned), len(self.catalog.capabilities))
        self.assertEqual(len(self.catalog.sections), len(PRODUCT_CATEGORY_ORDER))

    def test_the_uniforms_page_no_longer_renders_only_one_capability(self) -> None:
        """The specific defect: a page built around a single hard-coded id.

        ``_build_uniform_page`` still looks ``nfl2k5.uniforms.all_visual`` up by
        name, which is correct -- the browser genuinely is that capability's
        workspace. What must not happen again is that being the *only* thing the
        category renders, so the mount point has to also build the section's
        capability page.
        """
        source = _STUDIO.read_text(encoding="utf-8")
        mount = source.index("if category == ProductCategory.UNIFORMS_EQUIPMENT:")
        window = source[mount:mount + 1600]
        self.assertIn("_build_uniform_page(section)", window)
        # The second tab renders the section's remaining capabilities. It is
        # _build_colors_page now, which puts the facemask colour control above
        # those cards and then embeds the capability page itself -- so assert
        # the section reaches a page that renders them, not one call name.
        self.assertTrue(
            "_build_capability_page(section)" in window
            or "_build_colors_page(section)" in window,
            "Uniforms & Equipment must render its remaining capabilities, or "
            "enabling one of them changes nothing a modder can see",
        )
        colours = source[source.index("def _build_colors_page"):]
        colours = colours[:colours.index("def _refresh_unif_color_swatches")]
        self.assertIn(
            "_build_capability_page(section)", colours,
            "the colours tab must still show the section's capability cards",
        )

    def test_the_studio_module_still_parses(self) -> None:
        ast.parse(_STUDIO.read_text(encoding="utf-8"))


class CardsTellTheTruthTests(unittest.TestCase):
    """An "Editable" pill over a page with no controls reads as a broken button.

    A modder was told the facemask colour lived in Uniforms & Equipment, clicked
    through to it, and found a description card with nothing on it -- and
    reasonably reported that as a regression. Capability cards carry labels
    only; only a handful of categories have a real workspace behind them. Each
    writer card now either names the workspace that edits it or says plainly
    that it is command-line only, and prints the command.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = build_nfl2k5_product_catalog(CapabilityRegistryLoader().load())
        from mod_editor.gui.studio_qt import _WORKSPACE_CAPABILITIES
        cls.workspaces = _WORKSPACE_CAPABILITIES

    def test_every_named_workspace_is_a_real_sidebar_section(self) -> None:
        titles = {
            _CATEGORY_TITLES[category] for category in PRODUCT_CATEGORY_ORDER
        }
        titles.add("Uniform Sets")           # the first tab of Uniforms & Equipment
        titles.add("Portraits & Faces")      # the second tab of Rosters & Players
        titles.add("Colours & Other Tools")  # the second tab of Uniforms & Equipment
        for capability_id, workspace in self.workspaces.items():
            with self.subTest(capability_id=capability_id):
                self.assertIn(
                    workspace, titles,
                    f"{capability_id} points at a workspace that does not exist",
                )

    def test_every_mapped_capability_exists(self) -> None:
        known = {binding.capability_id for binding in self.catalog.capabilities}
        for capability_id in self.workspaces:
            with self.subTest(capability_id=capability_id):
                self.assertIn(capability_id, known)

    def test_the_facemask_now_has_a_colour_picker(self) -> None:
        """It was command-line only; the control shipped, so the card must
        point at it instead of sending people to a terminal."""
        binding = self.catalog.binding("nfl2k5.colors.unif_words")
        self.assertEqual(binding.capability.raw["backend"]["operation"], "write")
        self.assertEqual(
            self.workspaces.get("nfl2k5.colors.unif_words"),
            "Colours & Other Tools",
        )

    def test_the_all_textures_lane_now_has_a_real_workspace(self) -> None:
        """It shipped as a bare card; it is a browser now, so say so."""
        binding = self.catalog.binding("nfl2k5.textures.all_p8")
        self.assertEqual(binding.capability.raw["backend"]["operation"], "write")
        self.assertEqual(self.workspaces.get("nfl2k5.textures.all_p8"), "All Textures")

    def test_the_uniform_browser_stays_the_landing_tab(self) -> None:
        source = _STUDIO.read_text(encoding="utf-8")
        mount = source.index("if category == ProductCategory.UNIFORMS_EQUIPMENT:")
        window = source[mount:mount + 2200]
        self.assertIn("uniform_tabs.setCurrentIndex(0)", window)
        self.assertLess(
            window.index('"Uniform Sets"'), window.index('"Colours & Other Tools"'),
            "the uniform browser must be the first tab",
        )

    def test_the_tab_bar_is_styled_for_the_dark_theme(self) -> None:
        """Unstyled QTabBar renders a light strip with unreadable labels."""
        source = _STUDIO.read_text(encoding="utf-8")
        for rule in ("QTabBar::tab", "QTabBar::tab:selected", "QTabWidget::pane"):
            self.assertIn(rule, source)


if __name__ == "__main__":
    unittest.main()
