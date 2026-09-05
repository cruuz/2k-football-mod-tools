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
    from PyQt5.QtWidgets import QApplication, QLabel

    from mod_editor.games import studio_qt as shell
    from mod_editor.games.studio_qt import (
        UNAVAILABLE_TEMPLATE,
        BuildPage,
        FieldEditor,
        GameStudioDialog,
        LanePage,
        UnavailablePanel,
    )
except ImportError:  # PyQt5 is not installed here
    QApplication = None  # type: ignore[assignment]

from games_fakes import OK_GAME_SOURCE, manifest as fake_manifest, write_fake_game  # noqa: E402
from test_games_studio_service import TOY_GAME_SOURCE  # noqa: E402

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
        write_fake_game(
            cls.root, "toygame", TOY_GAME_SOURCE,
            fake_manifest("toygame", title="Toy Game", game="Toy"),
            with_fragments=True, title="Toy Game",
        )
        cls.toy = games.load("toygame", cls.root)

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
        self.assertEqual(len(placed), len(module.lanes), "every lane is on exactly one page")
        for lane in module.lanes:
            page = dialog.page_widget(contract.lane_page(lane))
            self.assertIsNotNone(page, lane.lane_id)
            if shell.is_offered(lane):
                # A lane the studio offers gets controls and its honesty line.
                self.assertIn(lane.lane_id, dialog.lane_pages)
                labels = [child.text() for child in page.findChildren(QLabel)]
                self.assertIn(shell.honesty_line(lane.classification), labels)
            else:
                # A lane whose evidence does not let it be offered gets its
                # classification and the registry's own reason, and nothing else.
                self.assertNotIn(lane.lane_id, dialog.lane_pages)
                self.assertIsInstance(page, UnavailablePanel)
                self.assertIn(lane.classification, page.sentence.text())

    # -- the pages a lane earns -----------------------------------------

    def test_a_lane_page_draws_a_control_for_every_field_of_a_target(self) -> None:
        dialog = self._studio(self.toy)
        page = dialog.lane_pages["colors.stamp"]
        self.assertIsInstance(page, LanePage)
        target = self.toy.lane("colors.stamp").build_catalogue(
            self.toy.lane("colors.stamp").synthetic_source(self.root)).targets[0]
        page.editor.set_fields(target.fields)
        self.assertEqual(set(page.editor.field_keys()), {"value", "colour"})
        page.editor.set_value("colour", "FF102030")
        self.assertEqual(page.editor.values()["colour"], "FF102030")
        self.assertEqual(page.editor.values()["value"], 0, "an int field always sends its value")

    def test_a_blank_text_field_means_keep_rather_than_an_empty_string(self) -> None:
        editor = FieldEditor()
        self.addCleanup(editor.deleteLater)
        editor.set_fields((contract.Field("name", "text", "Name"),
                           contract.Field("why", "note", "Why", "just a sentence"),
                           contract.Field("locked", "text", "Locked", read_only=True)))
        self.assertEqual(editor.values(), {}, "nothing typed is nothing sent")
        editor.set_value("name", "  Duane  ")
        self.assertEqual(editor.values(), {"name": "Duane"})

    def test_every_field_kind_the_contract_names_gets_a_control(self) -> None:
        editor = FieldEditor()
        self.addCleanup(editor.deleteLater)
        fields = tuple(
            contract.Field(f"f{index}", kind, kind.replace("_", " "),
                           choices=("one", "two") if kind in ("choice", "name_pick") else ())
            for index, kind in enumerate(contract._FIELD_KINDS)
        )
        editor.set_fields(fields)
        self.assertEqual(set(editor.field_keys()), {item.key for item in fields},
                         "a kind with no control would be an editor that silently drops a value")

    def test_the_build_page_is_a_page_and_says_when_nothing_is_staged(self) -> None:
        dialog = self._studio(self.toy)
        page = dialog.page_widget("build")
        self.assertIsInstance(page, BuildPage)
        self.assertIs(page, dialog.build_page)
        self.assertIn("Nothing is staged yet", page.queue_label.text())

    def test_the_windows_menu_lists_every_window_but_the_studio(self) -> None:
        dialog = self._studio(self.toy)
        self.assertEqual([action.text() for action in dialog.windows_menu.actions()],
                         ["Toy side window…"])

    def test_a_window_that_needs_the_xbox_session_is_named_but_not_clickable(self) -> None:
        module = games.load("nfl2k5_ps2")
        without = self._studio(module)
        [export] = [action for action in without.windows_menu.actions()
                    if "replacement pack" in action.text()]
        self.assertFalse(export.isEnabled())
        self.assertIn("needs that studio's session", export.toolTip())
        with_session = GameStudioDialog(module, context={"facade": object()})
        self.addCleanup(with_session.deleteLater)
        self.addCleanup(with_session.close)
        [export] = [action for action in with_session.windows_menu.actions()
                    if "replacement pack" in action.text()]
        self.assertTrue(export.isEnabled())

    def test_the_honesty_line_carries_the_badge_and_upstreams_qualifier(self) -> None:
        from mod_editor.gui.ux_text import NOT_TESTED

        self.assertEqual(shell.honesty_line("runtime-proved"), "PROVED — runtime-proved")
        self.assertEqual(shell.honesty_line("offline-writer-proved"),
                         f"PROVED — offline-writer-proved · {NOT_TESTED}")
        self.assertEqual(shell.honesty_line("extract-only"),
                         f"READ ONLY — extract-only · {NOT_TESTED}")
        self.assertIn(NOT_TESTED, shell.honesty_line("unknown"))

    def test_the_registry_is_what_says_why_a_lane_is_withheld(self) -> None:
        reasons = shell.registry_reasons()
        self.assertIn("nfl2k5ps2.gameplay.executable_patches", reasons)
        dialog = self._studio(games.load("nfl2k5_ps2"))
        panel = dialog.page_widget("gameplay")
        self.assertIn(reasons["nfl2k5ps2.gameplay.executable_patches"], panel.sentence.text())

    def test_the_shells_offered_classifications_match_the_harnesss(self) -> None:
        from mod_editor.games import conformance

        self.assertEqual(shell.OFFERED_CLASSIFICATIONS,
                         conformance._OFFERED_CLASSIFICATIONS,
                         "the static half of the harness restates this list; they must agree")

    def test_the_studio_menu_label_is_composed_from_the_manifest(self) -> None:
        from mod_editor.games.chooser import studio_menu_label, studio_window_spec

        module = games.load("nfl2k5_ps2")
        self.assertEqual(studio_menu_label(module.manifest.studio_label), "PS2 NFL 2K5 Studio…")
        self.assertEqual(studio_window_spec(module).menu_label, "PS2 NFL 2K5 Studio…")
        self.assertEqual(module.studio.menu_label, "Disc Studio…",
                         "the module names the window as the studio's own menu calls it")
        self.assertNotIn(module.manifest.studio_label, module.studio.menu_label,
                         "and never types the composed label itself")

    def test_an_initial_source_is_shown_and_nothing_is_opened_without_one(self) -> None:
        self.assertIn("No source opened yet", self._studio().source.text())
        with_source = GameStudioDialog(self.module, initial_source=self.root / "my.iso")
        self.addCleanup(with_source.deleteLater)
        self.addCleanup(with_source.close)
        self.assertIn("my.iso", with_source.source.text())

    def test_a_source_that_was_refused_does_not_leave_reading_on_the_row(self) -> None:
        """The source row is a statement about what is open, so a refusal has
        to take "Reading x…" back down rather than leave it standing."""

        dialog = self._studio()
        dialog.source.setText("Reading my.iso…")
        dialog.refresh_source_label()
        self.assertEqual(dialog.source.text(), "No source opened yet.")

    def test_a_closed_studio_starts_no_more_work(self) -> None:
        """A deferred open that fires after the window has gone is a crash, not
        a late refresh; the window refuses the work instead."""

        dialog = GameStudioDialog(self.module, initial_source=self.root / "my.iso")
        self.addCleanup(dialog.deleteLater)
        dialog.close()
        self.assertTrue(dialog._closed)
        self.assertFalse(dialog._initial_timer.isActive())
        dialog._open_initial_source()
        self.assertFalse(dialog.busy, "a closed studio never becomes busy")


if __name__ == "__main__":
    unittest.main()
