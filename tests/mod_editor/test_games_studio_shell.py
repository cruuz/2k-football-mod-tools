"""The core studio shell, offscreen: fourteen pages, and each one honest.

`mod_editor/games/studio_qt.py` is the window every game gets for free.  This
proves the part that must be true before A2 fills the pages in: the window is
named by the composed studio label, all fourteen pages of `PAGE_ORDER` exist in
the studio's order, a page with no lane says so in the module's own words, and
a page whose lanes exist lists them with the classification their evidence
earned.  No game data; the fake module is scaffolded into a scratch root.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
for _candidate in (ROOT, ROOT / "tests" / "mod_editor"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import mod_editor.games as games  # noqa: E402
from mod_editor.games import contract  # noqa: E402

try:
    from PyQt5.QtWidgets import QApplication

    from mod_editor.games.studio_qt import UNAVAILABLE_TEMPLATE, GameStudioDialog
except ImportError:  # PyQt5 is not installed here
    QApplication = None  # type: ignore[assignment]

from games_fakes import OK_GAME_SOURCE, manifest as fake_manifest, write_fake_game  # noqa: E402

UNIFORM_NOTE = "Uniform textures are EA FSH inside BIG; decode is known, console write is not."


@unittest.skipIf(QApplication is None, "PyQt5 is not installed")
class GameStudioShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.root = Path(tempfile.mkdtemp(prefix="studio-shell-")).resolve()
        write_fake_game(
            cls.root, "okgame", OK_GAME_SOURCE,
            fake_manifest("okgame", title="OK Game", game="OK",
                          page_notes={"uniforms": UNIFORM_NOTE}),
            with_fragments=True, title="OK Game",
        )
        cls.module = games.load("okgame", cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.root, ignore_errors=True)

    def _studio(self, module=None) -> GameStudioDialog:
        dialog = GameStudioDialog(module or self.module)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.close)
        return dialog

    def test_the_window_is_named_by_the_composed_label(self) -> None:
        dialog = self._studio()
        self.assertEqual(dialog.windowTitle(), "TC OK 1 Studio")
        self.assertEqual(dialog.header.text(), "TC OK 1 Studio")
        self.assertIn("OK Game", dialog.identity.text())
        self.assertIn("Test Console", dialog.identity.text())

    def test_every_page_of_the_studio_order_is_present(self) -> None:
        dialog = self._studio()
        expected = tuple(page_id for page_id, _title in contract.PAGE_ORDER)
        self.assertEqual(len(expected), 14)
        self.assertEqual(dialog.page_ids(), expected)
        self.assertEqual(dialog.navigation.count(), 14)
        self.assertEqual([dialog.navigation.item(index).text() for index in range(14)],
                         [title for _page_id, title in contract.PAGE_ORDER])
        for page_id in expected:
            self.assertIsNotNone(dialog.page_widget(page_id), page_id)
        self.assertIsNone(dialog.page_widget("no_such_page"))

    def test_a_page_with_no_lane_says_so_and_carries_the_games_own_sentence(self) -> None:
        dialog = self._studio()
        sentence = dialog.unavailable_sentence("uniforms")
        self.assertTrue(sentence.startswith(
            UNAVAILABLE_TEMPLATE.format(title="Uniforms & Equipment", studio="TC OK 1 Studio")))
        self.assertIn(UNIFORM_NOTE, sentence)
        self.assertEqual(dialog.unavailable_sentence("audio"),
                         "No Audio lane in TC OK 1 Studio yet.")

    def test_selecting_a_page_moves_the_stack(self) -> None:
        dialog = self._studio()
        self.assertEqual(dialog.current_page_id(), "uniforms")
        self.assertTrue(dialog.select_page("audio"))
        self.assertEqual(dialog.current_page_id(), "audio")
        self.assertEqual(dialog.stack.currentWidget(), dialog.page_widget("audio"))
        self.assertFalse(dialog.select_page("no_such_page"))
        self.assertEqual(dialog.current_page_id(), "audio", "a bad id changes nothing")

    def test_the_real_ps2_module_lands_its_lanes_on_pages(self) -> None:
        module = games.load("nfl2k5_ps2")
        dialog = self._studio(module)
        self.assertEqual(dialog.windowTitle(), "PS2 NFL 2K5 Studio")
        placed = {
            lane.lane_id: page_id
            for page_id in dialog.page_ids()
            for lane in dialog.lanes_for_page(page_id)
        }
        self.assertEqual(placed, {"colors.unif_words": "identity",
                                  "gameplay.executable_patches": "gameplay"})
        self.assertEqual(len(placed), len(module.lanes), "every lane is on exactly one page")
        for lane in module.lanes:
            page = dialog.page_widget(contract.lane_page(lane))
            labels = [child.text() for child in page.findChildren(type(dialog.header))]
            self.assertIn(f"{lane.title} — {lane.classification}", labels)

    def test_an_initial_source_is_shown_and_nothing_is_opened_without_one(self) -> None:
        self.assertIn("No source opened yet", self._studio().source.text())
        with_source = GameStudioDialog(self.module, initial_source=self.root / "my.iso")
        self.addCleanup(with_source.deleteLater)
        self.addCleanup(with_source.close)
        self.assertIn("my.iso", with_source.source.text())


if __name__ == "__main__":
    unittest.main()
