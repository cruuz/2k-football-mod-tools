"""b780-b13: the first-run questions are answered in the FAQ, in plain words, and the Studio points at them.

The questions came from the community Discord after the v0.8 release: ".xiso or .iso", getting the game without a disc drive,
making the picture sharper, a game that will not start (memory, BIOS, paths) and Android hakuX. The new answers must be plain
words, carry no em dashes and no names of players or reporters, quote the live Studio captions they tell people to click, and
the Help menu must open them.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

FAQ = ROOT / "docs/mod_editor/2k5_mod_studio_faq.md"
START_HERE = ROOT / "docs/START_HERE.md"
RECOMMENDED = ROOT / "docs/mod_editor/recommended_xemu_settings.md"
NEW_HEADINGS = (
    "Should my game file end in .iso or .xiso?",
    "I have no disc drive. How do I get the game file?",
    "How do I make the picture sharper?",
    "The game will not start. What should I check?",
    "Can I play SOFTDRINK 2K28 on Android, in hakuX?",
    "Can I keep the whole Crib, with its shops?",
)
AFTER_BLOCK = "My studio will not open or update. How do I reinstall?"
# Handles of community members and reporters the older FAQ answers name (the new answers name nobody).
NAMES = ("GoldenTiger", "MacDog850", "andrethealchemist", "lt9608", "maumau78", "X_Ray", "BigTimeEmpire", "Coach Edwards",
         "Slyreward", "TimNation", "davidhbui", "Jackdaw", "HAIL ST. CLAIR", "Ju3tin", "SharkMagick", "SWeaR",
         "LePromisedPrince", "Smuzz", "Nath", "Zane", "Mud", "CER", "thebutter", "holtbolt", "Noah")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return text.replace(" ", "-")


def _new_block() -> str:
    text = FAQ.read_text(encoding="utf-8")
    start = text.index("## " + NEW_HEADINGS[0])
    end = text.index("## " + AFTER_BLOCK)
    return text[start:end]


def _flat(text: str) -> str:
    """One line of single spaces, so a phrase the Markdown wraps across two lines still matches."""
    return " ".join(text.split())


class NewFaqAnswers(unittest.TestCase):
    def test_every_question_is_in_the_faq_in_order_before_the_older_answers(self):
        text = FAQ.read_text(encoding="utf-8")
        positions = [text.index("## " + heading) for heading in NEW_HEADINGS]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], text.index("## " + AFTER_BLOCK))
        self.assertEqual(text.count("## " + NEW_HEADINGS[0]), 1)

    def test_plain_words_no_dashes_no_names(self):
        block = _new_block()
        for dash in ("\u2014", "\u2013"):
            self.assertNotIn(dash, block)
        for name in NAMES:
            self.assertIsNone(re.search(r"(?<![\w])" + re.escape(name) + r"(?![\w])", block, re.I), name)
        # no private paths, no tool jargon the questions did not use
        for needle in ("/home/", "/media/", "Unicorn", "ledger", "Opus", "Claude"):
            self.assertNotIn(needle, block)

    def test_each_answer_says_what_to_click_or_where_to_look(self):
        block = _flat(_new_block())
        for needle in ("`.iso`", "`.xiso`", "SOFTDRINK 2K28.xiso.iso",                       # the file endings
                       "https://xemu.app/docs/disc-images/",                                 # no disc drive
                       "**Int. Resolution Scale**", "**2x**",                                # the picture
                       "128 MiB", "COMPLEX 4627", "Load Disc", "Copy Build summary",         # the start-up checklist
                       "hakuX", "xemu itself has no Android version",                        # Android
                       "Customize SOFTDRINK 2K28", "Make my disc"):                          # the Crib
            self.assertIn(needle, block)

    def test_the_xemu_facts_match_the_settings_page_the_studio_already_ships(self):
        recommended = RECOMMENDED.read_text(encoding="utf-8")
        for fact in ("128 MiB", "Int. Resolution Scale", "COMPLEX 4627", "Flash ROM (BIOS)"):
            self.assertIn(fact, recommended)
            self.assertIn(fact, _flat(_new_block()))

    def test_the_crib_answer_quotes_the_live_captions_and_groups(self):
        from mod_editor.core import nfl2k5_crib_trophy_room as crib
        from mod_editor.core import nfl2k5_throw_tuning as tt
        block = _flat(_new_block())
        self.assertIn(crib.BUILD_CAPTION, block)
        self.assertIn(tt.trophy_room_patch.BUILD_CAPTION, block)
        self.assertIn("**Gameplay**", block)
        self.assertIn("**Franchise**", block)

    def test_links_in_the_new_answers_resolve(self):
        for raw in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", _new_block()):
            if raw.startswith(("http://", "https://", "#")):
                continue
            self.assertTrue((FAQ.parent / raw.split("#")[0]).resolve().is_file(), raw)

    def test_start_here_points_at_headings_that_exist(self):
        faq_anchors = {_slug(h) for h in re.findall(r"^## (.+)$", FAQ.read_text(encoding="utf-8"), re.M)}
        start = START_HERE.read_text(encoding="utf-8")
        anchors = re.findall(r"2k5_mod_studio_faq\.md#([\w\-]+)", start)
        self.assertEqual(len(anchors), 4)  # b780: plus the Linux Python 3.13 answer; b780-m64b: plus the 64 MB answer
        for anchor in anchors:
            self.assertIn(anchor, faq_anchors)
        self.assertEqual(_slug(NEW_HEADINGS[3]), "the-game-will-not-start-what-should-i-check")
        self.assertEqual(_slug(NEW_HEADINGS[5]), "can-i-keep-the-whole-crib-with-its-shops")

    def test_the_getting_started_guide_says_the_presets_cut_the_crib(self):
        guide = (ROOT / "docs/mod_editor/2k5_mod_studio_getting_started.md").read_text(encoding="utf-8")
        self.assertIn("All three presets also cut the Crib down to the Trophy Room", guide)
        self.assertNotIn("\u2014", guide.split("All three presets also cut the Crib")[1][:400])


class HelpMenuAndWelcomeText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_help_menu_opens_the_packaged_faq(self):
        from PyQt5.QtWidgets import QMainWindow
        from mod_editor.gui import studio_qt

        class Shell(QMainWindow):
            _install_help_menu = studio_qt.StudioMainWindow._install_help_menu

            def _check_for_updates_now(self):
                pass

        shell = Shell()
        self.addCleanup(shell.deleteLater)
        shell._install_help_menu()
        self.assertEqual(studio_qt._faq_document(), FAQ.resolve())
        menu = next(a.menu() for a in shell.menuBar().actions() if a.text() == "&Help")
        actions = {a.text(): a for a in menu.actions() if a.text()}
        self.assertIn("Questions and answers (FAQ)…", actions)
        faq = actions["Questions and answers (FAQ)…"]
        self.assertTrue(faq.isEnabled())
        self.assertEqual(faq.toolTip(), str(FAQ.resolve()))
        order = list(actions)
        self.assertEqual(order.index("Questions and answers (FAQ)…"), order.index("Getting started guide…") + 1)

    def test_welcome_page_says_both_endings_work(self):
        asset = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
        if not asset.exists():
            # CI and light checkouts have no private assets: read the packaged source instead of building the window
            source = (ROOT / "mod_editor/gui/studio_qt.py").read_text(encoding="utf-8")
            self.assertIn("a .iso or .xiso file (both work, they are the same kind", source)
            self.assertIn("Stuck? The FAQ (Help ▸ Questions and answers) covers the common first-run questions", source)
            self.assertIn("discord.setWordWrap(True)", source)
            return
        from PyQt5.QtWidgets import QLabel
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
        window = StudioMainWindow(eager_pages=False, facade=BrowseOnlyFacade(), offer_recovery=False)
        self.addCleanup(window.deleteLater)
        window.resize(1280, 720)
        window.show()
        self.app.processEvents()
        tip = window.welcome_open_button.toolTip()
        self.assertIn(".iso", tip)
        self.assertIn(".xiso", tip)
        self.assertNotIn("\u2014", tip)
        label = next(w for w in window.findChildren(QLabel) if w.accessibleName() == "Community help link")
        self.assertIn("Questions and answers", label.text())
        self.assertIn("Ask on the Discord", label.text())
        self.assertTrue(label.wordWrap())            # the longer sentence wraps instead of widening the page
        self.assertNotIn("\u2014", label.text())


if __name__ == "__main__":
    unittest.main()
