"""b780-uxfix: the fixes from the beginner and power-user reviews of 2K5 Mod Studio, each proved offscreen.

The reviews (a first-time user and a power user walking through the Studio, 2026-11-03) found bugs
that look broken to everybody and wording that sends a beginner the wrong way. Each test pins one fix:

* opening Gameplay at 1480x920 reports no error (WrappingCheckBox measured itself through
  ``sizeHint()``, which asked it back: 215 RecursionError reports per visit, about 51 MB of errors.log);
* Names, Numbers & Faces reads the naming manifest once per change, not once per table cell;
* the Disc ready note no longer says a 128 MB disc "still plays" at 64 MB;
* the Build summary counts a sub-option only when its parent is on;
* the footer keeps its status readable and short at 1280x720;
* only real cue labels are counted ("1 cue label" after just opening a disc);
* roster, staff and franchise edits count as unsaved work (title, close, open another);
* startup Recover Edits hands the disc to the pages;
* the Number sheet layout box fits on screen;
* Getting Started offers Install SOFTDRINK 2K28 first; the Share tab is Install & Share;
* Disc ready offers Play in xemu and Show in folder, and says where the xemu settings are;
* Help leads with the 5-step install and the xemu settings, shown inside the Studio;
* the installer names a wrong file in plain words right after step 1;
* the header says Beta 80.

Offscreen only. The window tests need the private assets (``reports/assets``); light checkouts skip them.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtCore import QUrl  # noqa: E402
from PyQt5.QtWidgets import QApplication, QFileDialog, QInputDialog, QLabel, QMessageBox, QPushButton, QWidget  # noqa: E402
from PyQt5.QtGui import QFont  # noqa: E402  b780 CI: Windows-like wide font

ASSETS = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
SHOTS = os.environ.get("UXFIX_SHOTS", "")


_APP: list[QApplication] = []


def _app() -> QApplication:
    """One QApplication for the whole run, kept referenced (unittest drops finished test cases)."""
    if not _APP:
        _APP.append(QApplication.instance() or QApplication([]))
    return _APP[0]


def _font_report(widget=None) -> str:
    """b780 CI: the fonts this platform really draws with, printed so a CI log shows them (Linux, macOS and Windows
    runners differ by about 2x in text width)."""
    from PyQt5.QtGui import QFontInfo
    app = _app()
    lines = []
    for name, font in (("QApplication.font()", app.font()), ("widget", widget.font() if widget is not None else None)):
        if font is None:
            continue
        info = QFontInfo(font)
        metrics = widget.fontMetrics() if (widget is not None and name == "widget") else app.fontMetrics()
        lines.append(f"{name}: requested {font.family()!r} {font.pointSizeF()}pt/{font.pixelSize()}px, drawn {info.family()!r} "
                     f"{info.pointSizeF():.1f}pt, 'Install SOFTDRINK 2K28' = {metrics.horizontalAdvance('Install SOFTDRINK 2K28')} px")
    text = " | ".join(lines)
    print("FONTS " + text, file=sys.stderr)
    return text


def _shot(widget: QWidget, name: str) -> None:
    """Save a grab when UXFIX_SHOTS names a folder (the proof screenshots); tests never need it."""
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        if not widget.isVisible() and widget.isWindow():   # a box caught before exec_ shows it: lay it out first
            widget.show()
            widget.adjustSize()
            QApplication.processEvents()
            widget.grab().save(str(Path(SHOTS) / f"{name}.png"))
            widget.hide()
            return
        widget.grab().save(str(Path(SHOTS) / f"{name}.png"))


def _pump(app: QApplication, rounds: int = 10) -> None:
    for _ in range(rounds):
        app.processEvents()


class _Hook:
    """Collect every exception PyQt hands to sys.excepthook while a window is driven."""

    def __init__(self) -> None:
        self.seen: list[BaseException] = []

    def __enter__(self):
        self.previous = sys.excepthook
        sys.excepthook = lambda kind, exc, tb: self.seen.append(exc)
        return self

    def __exit__(self, *_exc):
        sys.excepthook = self.previous
        return False


# ---------------------------------------------------------------------------------------------- light tests
class WrappingCheckBoxTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def test_a_box_narrower_than_its_indicator_measures_without_recursing(self):
        from mod_editor.gui.ux_text import WrappingCheckBox
        parent = QWidget()
        self.addCleanup(parent.deleteLater)
        caption = "EverBank Stadium for the Jaguars, with a caption long enough to wrap"
        box = WrappingCheckBox(caption, parent)
        for width in (400, 40, 10, 1, 0):
            box.resize(width, 30)
            hint, smallest = box.sizeHint(), box.minimumSizeHint()      # RecursionError before the fix (10 and 1 px)
            self.assertGreater(hint.width(), smallest.width())
            self.assertGreater(box._chrome_width(), 0)
        box.resize(160, 30)
        self.assertIn("\n", box._shown_text)                             # it still wraps to the width it is given
        self.assertEqual(box.text(), caption)


class NamingCacheTests(unittest.TestCase):
    """Names, Numbers & Faces froze for minutes: every table cell re-read, re-checked and hashed the manifest."""

    def _facade(self):
        from mod_editor.gui.studio_qt import _EmbeddedOperationGuardedHost
        from mod_editor.core import nfl2k5_team_names_2026 as names
        from mod_editor.core.nfl2k5_text_catalog import Nfl2k5TextCatalog, RosterTeam
        assets = [SimpleNamespace(asset_id=f"nfl2k5.text.rost.5.{c['domain']}.{c['team_index']}.{c['field']}",
                                  value=c["retail"], label=c["field"]) for c in names.cells()]
        fields = tuple((key, f"nfl2k5.text.rost.5.team.23.{key}") for key in ("city", "nickname", "abbreviation"))
        team = RosterTeam("rams", 5, "Roster", False, 23, "St. Louis Rams", "23", fields, True, "")
        catalog = Nfl2k5TextCatalog((), assets, (team,), (), ())
        staged = {a.asset_id: a.value for a in assets}
        raw = SimpleNamespace(text_catalog_snapshot=lambda _: catalog,
                              text_value=lambda a: staged[a if isinstance(a, str) else a.asset_id])
        facade = _EmbeddedOperationGuardedHost(raw, requester="text", require_mutation_admission=lambda *_: None,
                                               team_names_enabled=lambda: True)
        return facade, dict(fields)["city"]

    def test_five_thousand_cells_read_the_manifest_once(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        facade, city = self._facade()
        with mock.patch.object(tuning, "_modern_naming_digest", wraps=tuning._modern_naming_digest) as digest:
            started = time.perf_counter()
            for _ in range(5000):
                self.assertEqual(facade.text_value(city), "Los Angeles")
            elapsed = time.perf_counter() - started
        self.assertEqual(digest.call_count, 1)
        self.assertLess(elapsed, 30)                                      # was 5000 manifest reads and hashes

    def test_an_edited_manifest_is_read_again(self):
        from mod_editor.core import nfl2k5_modern_naming as modes, nfl2k5_throw_tuning as tuning
        facade, city = self._facade()
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "manifest.json"
            copy.write_bytes(Path(modes.MANIFEST).read_bytes())
            with mock.patch.object(modes, "MANIFEST", copy), \
                 mock.patch.object(tuning, "_modern_naming_digest", wraps=tuning._modern_naming_digest) as digest:
                facade.text_value(city)
                facade.text_value(city)
                self.assertEqual(digest.call_count, 1)
                info = copy.stat()
                os.utime(copy, ns=(info.st_atime_ns, info.st_mtime_ns + 5_000_000_000))
                facade.text_value(city)
                self.assertEqual(digest.call_count, 2)


class WordingTests(unittest.TestCase):
    def test_the_memory_tip_names_both_settings_and_the_black_screen(self):
        from mod_editor.core import nfl2k5_marks_store as store
        for needle in ("128 MiB", "Complex 4627", "black screen"):
            self.assertIn(needle, store.MEMORY_TIP)
        self.assertNotIn("still plays", store.MEMORY_TIP)
        self.assertNotIn("—", store.MEMORY_TIP)

    def test_the_saves_and_sliders_title_shows_one_ampersand(self):
        source = (ROOT / "mod_editor/gui/save_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('QLabel("Xbox save: sliders & franchise year (experimental)")', source)
        self.assertNotIn("sliders && franchise", source)

    def test_one_name_for_the_middle_preset(self):
        from mod_editor.gui import build_panel_qt as bp
        self.assertEqual(bp.PRESET_LABELS["softdrink_advanced"], "Advanced")
        self.assertTrue(bp.PRESET_BUTTONS["softdrink_advanced"].startswith("Advanced"))
        self.assertTrue(bp.PRESET_CAPTIONS["softdrink_experimental"].startswith("Advanced plus"))
        for text in bp.PRESET_BUTTONS.values():
            self.assertNotIn("—", text)
            self.assertNotIn("Modern", text)

    def test_the_number_sheet_layout_box_fits_on_a_screen(self):
        app = _app()
        from mod_editor.core.nfl2k5_digit_sheet import SHEET_HELP, SHEET_LAYOUT_CHOICES
        from mod_editor.gui.ux_text import item_dialog
        items = [row[0] for row in SHEET_LAYOUT_CHOICES]
        before = QInputDialog()
        before.setLabelText(SHEET_HELP)
        before.setComboBoxItems(items)
        before.adjustSize()
        self.assertGreater(before.sizeHint().width(), 2000)              # about 4,027 px in the review
        before.deleteLater()
        # b780 CI: a fixed 88-character fold was still 1,518 px with Windows font metrics; the label now wraps at a
        # pixel width and the choice box no longer sizes to its longest choice, so the box fits with this platform's
        # font and with one 1.5x wider.
        _font_report()
        original = app.font()
        try:
            for scale in (1.0, 1.5):          # 1.5x of this platform's own font (Windows' is about 2x Linux already)
                wide = QFont(original)
                wide.setPointSizeF(original.pointSizeF() * scale)
                app.setFont(wide)
                dialog = item_dialog(None, "Number sheet layout", SHEET_HELP, items)
                dialog.adjustSize()
                with self.subTest(font_scale=scale):
                    self.assertLess(dialog.sizeHint().width(), 900)
                if scale == 1.0:
                    _shot(dialog, "after_number_sheet_layout_dialog")
                dialog.deleteLater()
        finally:
            app.setFont(original)
        source = (ROOT / "mod_editor/gui/studio_qt.py").read_text(encoding="utf-8")
        self.assertIn('get_item(\n            self, "Number sheet layout", SHEET_HELP,', source)


class ErrorsLogTests(unittest.TestCase):
    def test_a_repeating_fault_stays_small_in_errors_log(self):
        from mod_editor.gui import crash_report
        saved = dict(crash_report._LOGGED)
        crash_report._LOGGED.clear()
        self.addCleanup(lambda: (crash_report._LOGGED.clear(), crash_report._LOGGED.update(saved)))
        folder = Path(tempfile.mkdtemp(prefix="uxfix-log-"))

        def recurse(depth=0):
            return recurse(depth + 1)

        with mock.patch.object(sys, "stderr", io.StringIO()):
            for _ in range(215):
                try:
                    recurse()
                except RecursionError:
                    info = sys.exc_info()
                crash_report.handle(*info, app_name="2K5 Mod Studio", directory=folder, show_dialog=False)
        self.assertLess((folder / "errors.log").stat().st_size, 256 * 1024)


class BuildSummaryTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def test_a_sub_option_counts_only_with_its_parent(self):
        from mod_editor.gui.build_panel_qt import BuildPanel
        panel = BuildPanel(available={})
        self.addCleanup(panel.deleteLater)
        panel.modern_everbank_check.setChecked(False)
        panel.modern_everbank_construction_check.setChecked(True)       # on by default, the stadium off
        panel._refresh()
        self.assertNotIn("EverBank: 2026 construction", panel.selected_labels())
        self.assertNotIn("EverBank", panel.summary_label.text())
        panel.modern_everbank_check.setChecked(True)
        panel.modern_everbank_construction_check.setChecked(True)
        self.assertIn("EverBank: 2026 construction", panel.selected_labels())


class StatusLabelTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def test_a_long_message_keeps_two_lines_and_its_whole_text(self):
        from mod_editor.gui.ux_text import ElidedStatusLabel
        label = ElidedStatusLabel("short")
        self.addCleanup(label.deleteLater)
        label.resize(400, 40)
        message = "Opening your NFL 2K5 game file and checking every pack, " * 8
        label.setText(message)
        self.assertEqual(label.text(), message)
        self.assertEqual(label.toolTip(), message)
        shown = label.shown_text().split("\n")
        self.assertEqual(len(shown), 2)
        self.assertTrue(shown[-1].endswith("…"))
        self.assertLessEqual(label.sizeHint().height(), label.fontMetrics().lineSpacing() * 2 + 4)
        self.assertGreaterEqual(label.minimumSizeHint().width(), 240)
        label.setText("Disc opened.")
        self.assertEqual(label.shown_text(), "Disc opened.")


class SharePanelTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        from mod_editor.gui.share_panel_qt import SharePanel
        self.panel = SharePanel()
        self.addCleanup(self.panel.deleteLater)
        self.folder = Path(tempfile.mkdtemp(prefix="uxfix-share-"))

    def test_wrong_game_files_are_named_in_plain_words(self):
        notes = self.folder / "my notes.txt"
        notes.write_text("not a game", encoding="utf-8")
        archive = self.folder / "NFL 2K5.zip"
        archive.write_bytes(b"PK\x03\x04")
        text, details = self.panel.game_file_problem(notes)
        self.assertIn('"my notes.txt" is not an NFL 2K5 game file', text)
        self.assertNotIn("XDVDFS", text)
        self.assertTrue(details)
        self.assertIn("is a folder", self.panel.game_file_problem(self.folder)[0])
        self.assertIn("Unzip it first", self.panel.game_file_problem(archive)[0])

    def test_a_wrong_first_file_stops_at_step_one_and_can_be_chosen_again(self):
        notes = self.folder / "my notes.txt"
        notes.write_text("not a game", encoding="utf-8")
        asked = []
        self.panel._wrong_file = lambda title, text, details: asked.append((title, text)) or len(asked) < 2
        with mock.patch.object(QFileDialog, "getOpenFileName", side_effect=[(str(notes), ""), (str(notes), "")]) as chooser, \
             mock.patch.object(QFileDialog, "getSaveFileName") as save:
            self.panel.install_softdrink()
        self.assertEqual(chooser.call_count, 2)                         # step 1 twice ("Choose again"), never step 2
        self.assertTrue(all("1 of 3" in call.args[1] for call in chooser.call_args_list))
        save.assert_not_called()
        self.assertEqual(asked[0][0], "That file is not the NFL 2K5 game")

    def test_the_wrong_file_box_names_the_file_and_keeps_the_details_behind_a_button(self):
        seen = {}

        def exec_(box):
            seen.update(text=box.text(), details=box.detailedText(), buttons=[b.text() for b in box.buttons()])
            _shot(box, "after_wrong_game_file_box")
            next(b for b in box.buttons() if b.text() == "Choose again").click()
            return 0

        notes = self.folder / "my notes.txt"
        notes.write_text("not a game", encoding="utf-8")
        with mock.patch.object(QMessageBox, "exec_", exec_):
            again = self.panel._wrong_file("That file is not the NFL 2K5 game", *self.panel.game_file_problem(notes))
        self.assertTrue(again)
        self.assertIn('"my notes.txt"', seen["text"])
        self.assertIn("Choose again", seen["buttons"])
        self.assertTrue(seen["details"])                                # the technical line, behind Show Details

    def test_a_wrong_patch_file_says_so_instead_of_stopping_silently(self):
        import test_modpack_files as fixtures  # tiny Xbox images and a format-3 pack
        fixture = fixtures.FilePackTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        notes = self.folder / "my notes.txt"
        notes.write_text("not a patch", encoding="utf-8")
        asked = []
        self.panel._wrong_file = lambda title, text, details: asked.append((title, text)) and False
        with mock.patch.object(QFileDialog, "getOpenFileName", side_effect=[(str(fixture.base), ""), (str(notes), "")]):
            self.panel.install_softdrink()
        self.assertEqual(asked[0][0], "That file is not a SOFTDRINK 2K28 patch")
        self.assertIn('"my notes.txt" is not a SOFTDRINK 2K28 patch', asked[0][1])

    def test_step_one_starts_at_the_game_file_already_open(self):
        opened = self.folder / "ESPN NFL 2K5 (USA).iso"
        self.panel.source_field.setText(str(opened))
        with mock.patch.object(QFileDialog, "getOpenFileName", return_value=("", "")) as chooser:
            self.panel.install_softdrink()
        self.assertEqual(chooser.call_args.args[2], str(opened))       # the open disc is preselected

    def _receipt(self, target: Path, memory: bool) -> dict:
        from mod_editor.core import nfl2k5_marks_store as store
        return {"target": {"path": str(target), "matches_author_result": None, "all_game_files_verified": True},
                "elapsed_seconds": 3, "memory_tip": store.MEMORY_TIP if memory else ""}

    def test_disc_ready_offers_play_and_show_in_folder_and_the_xemu_settings(self):
        from mod_editor.gui import ux_text
        target = self.folder / "SOFTDRINK 2K28.xiso.iso"
        target.write_bytes(b"disc")
        played, seen = [], {}
        self.panel.play_hook = lambda: (lambda: played.append(True))

        def exec_(box):
            seen["text"] = box.text()
            seen["buttons"] = [button.text() for button in box.buttons()]
            _shot(box, "after_disc_ready_box")
            next(b for b in box.buttons() if b.text() == "Show in folder").click()
            return 0

        with mock.patch.object(QMessageBox, "exec_", exec_), \
             mock.patch("PyQt5.QtGui.QDesktopServices.openUrl", return_value=True) as opened:
            self.panel._apply_done(self._receipt(target, True))
        self.assertIn("Play in xemu", seen["buttons"])
        self.assertIn("Show in folder", seen["buttons"])
        self.assertIn(ux_text.XEMU_SETUP_STEPS, seen["text"])
        for needle in ("128 MiB", "Complex 4627", "close xemu and open it again"):
            self.assertIn(needle, seen["text"])
        opened.assert_called_once_with(QUrl.fromLocalFile(str(self.folder)))
        self.assertEqual(played, [])

        def play(box):
            next(b for b in box.buttons() if b.text() == "Play in xemu").click()
            return 0

        with mock.patch.object(QMessageBox, "exec_", play):
            self.panel._apply_done(self._receipt(target, False))
        self.assertEqual(played, [True])

    def test_without_a_way_to_launch_there_is_no_play_button(self):
        target = self.folder / "mod.iso"
        target.write_bytes(b"disc")
        self.panel.play_hook = lambda: None
        seen = {}

        def exec_(box):
            seen["buttons"] = [button.text() for button in box.buttons()]
            seen["text"] = box.text()
            return 0

        with mock.patch.object(QMessageBox, "exec_", exec_):
            self.panel._apply_done(self._receipt(target, False))
        self.assertNotIn("Play in xemu", seen["buttons"])
        self.assertIn("Show in folder", seen["buttons"])
        self.assertNotIn("Complex 4627", seen["text"])                 # an ordinary mod is not told about the BIOS


class HelpTests(unittest.TestCase):
    def setUp(self):
        self.app = _app()

    def test_the_help_menu_leads_with_the_install_and_xemu_pages_shown_inside_the_studio(self):
        from PyQt5.QtWidgets import QMainWindow
        from mod_editor.gui import studio_qt

        class Shell(QMainWindow):
            _install_help_menu = studio_qt.StudioMainWindow._install_help_menu

            def _check_for_updates_now(self):
                pass

        shell = Shell()
        self.addCleanup(shell.deleteLater)
        shell._install_help_menu()
        menu = next(a.menu() for a in shell.menuBar().actions() if a.text() == "&Help")
        actions = [a for a in menu.actions() if a.text()]
        self.assertEqual([a.text() for a in actions[:2]], [studio_qt.HELP_START_HERE[0], studio_qt.HELP_XEMU_SETUP[0]])
        with mock.patch("mod_editor.gui.studio_qt.QDesktopServices.openUrl") as outside:
            actions[0].trigger()
            dialog = shell._help_dialog
            self.assertIn("Install SOFTDRINK 2K28 in 5 steps", dialog.windowTitle())
            self.assertIn("Load Disc", dialog.browser.toPlainText())
            self.assertNotIn("**", dialog.browser.toPlainText())          # Markdown, not raw stars
            _shot(dialog, "after_help_start_here")
            actions[1].trigger()
            self.assertIs(shell._help_dialog, dialog)                      # one help window, reused
            self.assertIn("128 MiB", dialog.browser.toPlainText())
            self.assertIn("4627", dialog.browser.toPlainText())
            faq = next(a for a in actions if a.text() == "Questions and answers (FAQ)…")
            faq.trigger()
            self.assertEqual(dialog.path, studio_qt._faq_document())
        outside.assert_not_called()                                         # nothing handed to the OS as raw .md
        logs = next(a for a in actions if a.text() == "Open the logs folder (errors.log)…")
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.dict(os.environ, {"MOD_STUDIO_LOG_DIR": folder}), \
             mock.patch("mod_editor.gui.studio_qt.QDesktopServices.openUrl", return_value=True) as opened:
            logs.trigger()
            opened.assert_called_once_with(QUrl.fromLocalFile(str(Path(folder) / "2k5-mod-studio")))

    def test_a_link_to_another_page_opens_in_the_same_window(self):
        from mod_editor.gui.ux_text import MarkdownHelpDialog
        from mod_editor.gui import studio_qt
        dialog = MarkdownHelpDialog()
        self.addCleanup(dialog.deleteLater)
        start = studio_qt._help_document("install_softdrink_2k28.md")
        dialog.load(start)
        dialog._follow(QUrl("recommended_xemu_settings.md"))
        self.assertEqual(dialog.path.name, "recommended_xemu_settings.md")
        with mock.patch("PyQt5.QtGui.QDesktopServices.openUrl") as web:
            dialog._follow(QUrl("https://xemu.app/docs/required-files/"))
        web.assert_called_once()


class RosterPromptWordingTests(unittest.TestCase):
    def test_the_verb_and_pronoun_follow_the_count(self):
        # b780-uxfix2: "★ Rosters has 1 edited player that are not saved yet"
        from mod_editor.gui.studio_qt import roster_work_sentences
        text, more, summary = roster_work_sentences(1, 0, "Closing Mod Studio")
        self.assertEqual(text, "★ Rosters has 1 edited player that is not saved yet.")
        self.assertTrue(more.startswith("Closing Mod Studio loses it. To keep it, choose Cancel"))
        self.assertEqual(summary, "1 edited player")
        self.assertEqual(roster_work_sentences(0, 1, "x")[0], "★ Rosters has 1 staff change that is not saved yet.")
        text, more, _ = roster_work_sentences(3, 0, "Opening another disc")
        self.assertEqual(text, "★ Rosters has 3 edited players that are not saved yet.")
        self.assertTrue(more.startswith("Opening another disc loses them. To keep them,"))
        self.assertEqual(roster_work_sentences(1, 1, "x")[0],
                         "★ Rosters has 1 edited player and 1 staff change that are not saved yet.")
        self.assertEqual(roster_work_sentences(0, 0, "x")[0], "★ Rosters has edits that are not saved yet.")


class CueLabelCountTests(unittest.TestCase):
    def test_only_real_cue_labels_are_counted(self):
        from mod_editor.gui.studio_qt import StudioMainWindow
        host = SimpleNamespace(facade=SimpleNamespace(labeled_audio_asset_ids=frozenset(), project_metadata_count=1))
        self.assertEqual(StudioMainWindow._cue_label_count(host), 0)    # the saved Build choices are not a cue label
        host.facade.labeled_audio_asset_ids = frozenset({"a", "b"})
        self.assertEqual(StudioMainWindow._cue_label_count(host), 2)
        self.assertEqual(StudioMainWindow._cue_label_count(SimpleNamespace(facade=object())), 0)


# ---------------------------------------------------------------------------------------------- window tests
@unittest.skipUnless(ASSETS.exists(), "needs the private Studio assets (reports/assets)")
class StudioWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app()
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
        cls.window = StudioMainWindow(eager_pages=False, facade=BrowseOnlyFacade(), offer_recovery=False)
        cls.window.resize(1280, 720)
        cls.window.show()
        _pump(cls.app, 20)

    @classmethod
    def tearDownClass(cls):
        cls.window._allow_close = True
        cls.window.close()
        cls.window.deleteLater()
        _pump(cls.app, 5)

    def _size(self, width, height):
        self.window.resize(width, height)
        _pump(self.app, 15)

    def test_1_first_screen_at_1280x720(self):
        from mod_editor.gui.studio_qt import FOOTER_MAX_HEIGHT
        window = self.window
        window.navigation.setCurrentRow(0)
        self._size(1280, 720)
        _shot(window, "after_first_launch_1280x720")
        footer = window.operation_status.parentWidget()
        self.assertLessEqual(footer.height(), FOOTER_MAX_HEIGHT)
        self.assertGreaterEqual(window.operation_status.width(), 240)
        buttons = [b for b in footer.findChildren(QPushButton) if b.isVisible()]
        self.assertTrue(buttons)
        status = window.operation_status.geometry()
        self.assertLessEqual(status.bottom(), min(b.geometry().top() for b in buttons))   # its own row
        for button in buttons:                                                             # never clipped
            self.assertGreaterEqual(button.width(), button.fontMetrics().horizontalAdvance(button.text()))
        window._set_status("A longer operation status that keeps going " * 12)
        _pump(self.app, 10)
        self.assertLessEqual(footer.height(), FOOTER_MAX_HEIGHT)
        self.assertLessEqual(window.operation_status.shown_text().count("\n"), 1)
        self.assertTrue(window.operation_status.shown_text().endswith("…"))
        self.assertIn("keeps going", window.operation_status.toolTip())
        _shot(window, "after_long_status_1280x720")
        for width, height in ((1366, 768), (1920, 1080), (1040, 600)):
            self._size(width, height)
            self.assertLessEqual(footer.height(), FOOTER_MAX_HEIGHT, (width, height))
        self._size(1280, 720)

    def test_2_getting_started_leads_with_install_softdrink(self):
        window = self.window
        window.navigation.setCurrentRow(0)
        _pump(self.app)
        first = window.welcome_install_button
        self.assertEqual(first.text(), "Install SOFTDRINK 2K28…")
        self.assertEqual(first.objectName(), "primaryButton")
        self.assertEqual(window.welcome_open_button.objectName(), "secondaryButton")
        captions = [b.text() for b in window.welcome_task_buttons]
        self.assertIn("Make my own disc (fixes only)  →", captions)
        self.assertIn("does not install SOFTDRINK 2K28", window.welcome_task_buttons[0].toolTip())
        from mod_editor.gui.share_panel_qt import SharePanel
        with mock.patch.object(SharePanel, "install_softdrink") as install:
            first.click()
            deadline = time.monotonic() + 120
            while not install.called and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        install.assert_called_once()
        self.assertEqual(window.page_title.text(), "Build & Share")
        tabs = window._build_share_page
        self.assertIs(tabs.currentWidget(), window._share_panel)
        self.assertEqual(tabs.tabText(tabs.currentIndex()).replace("&&", "&"), "Install & Share")
        _shot(window, "after_install_and_share_tab")
        window.navigation.setCurrentRow(0)
        _pump(self.app)

    def test_3_the_header_says_beta_80(self):
        from PyQt5.QtWidgets import QLabel
        from mod_editor.core.update_check import BUILD_RELEASE_TAG
        label = next(w for w in self.window.findChildren(QLabel) if w.text().endswith("• Xbox Edition"))
        self.assertEqual(label.text(), BUILD_RELEASE_TAG.replace("-", " ").title() + " • Xbox Edition")
        self.assertIn("RC", label.toolTip())
        self.assertIn(BUILD_RELEASE_TAG, label.toolTip())

    def test_4_unsaved_roster_work_marks_the_title_and_guards_close_and_open(self):
        window = self.window
        panel = window._roster_editor_panel
        self.assertFalse(window._roster_work_unsaved())
        with mock.patch.object(type(panel), "is_dirty", return_value=True), \
             mock.patch.object(type(panel), "espn25_dirty", return_value=False):
            panel._edits_snapshot = None
            self.assertTrue(window._roster_work_unsaved())
            window._refresh_project_document_state()
            self.assertIn("*", window.windowTitle())
            asked = []
            with mock.patch.object(window, "_prompt_roster_work_lost", side_effect=lambda c: asked.append(c) or False), \
                 mock.patch("mod_editor.gui.crash_report.dialog_is_possible", return_value=True):
                ran = []
                window._continue_after_unsaved("Opening another disc", lambda discard: ran.append(discard))
                self.assertEqual(ran, [])                                   # Cancel keeps the roster
                event = mock.Mock()
                window.closeEvent(event)
                event.ignore.assert_called()
                event.accept.assert_not_called()
            self.assertEqual(asked, ["Opening another disc", "Closing Mod Studio"])
            # once exported, the same edits are saved work
            panel._edits_snapshot = panel.edits_key()
            self.assertFalse(window._roster_work_unsaved())
        window._refresh_project_document_state()
        self.assertNotIn("*", window.windowTitle())

    def test_5_startup_recovery_gives_the_pages_the_disc(self):
        from mod_editor.studio.project_archive import project_target_identity
        from mod_editor.studio.workspace_state import RecoveryCandidate
        window = self.window
        folder = Path(tempfile.mkdtemp(prefix="uxfix-recover-"))
        disc = folder / "game.iso"
        disc.write_bytes(b"x")
        project = folder / "recovery.2k5mod"
        project.write_bytes(b"retail-free recovery fixture")
        candidate = RecoveryCandidate(source_path=disc, source_sha256=None, project_path=project)
        order = []
        facade = window.facade
        identity = project_target_identity(project)
        with mock.patch.object(type(facade), "load_source", lambda self, source, progress: "Disc opened", create=True), \
             mock.patch.object(type(facade), "load_project",
                               lambda self, path, progress: order.append("project") or SimpleNamespace(
                                   message="recovered", project_identity=identity), create=True), \
             mock.patch.object(window, "_prefill_panels_from_source", side_effect=lambda source: order.append(("prefill", source))), \
             mock.patch.object(window, "_refresh_specialized_panels"), \
             mock.patch.object(window, "_refresh_entered_page"), \
             mock.patch.object(window, "_load_selected_unif_colors"), \
             mock.patch.object(window, "_show_error", side_effect=lambda message: order.append("error: " + message)):
            window._load_source_path(disc, recovery=candidate)
            deadline = time.monotonic() + 60
            while len(order) < 2 and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(0.01)
        self.assertEqual(order, ["project", ("prefill", disc.resolve())])   # the disc reaches the pages after recovery

    def _start_buttons_fit(self, window, tag=""):
        """Every Getting Started button fits at 1280/1366/1920 with Continue showing, and Continue opens its file."""
        folder = Path(tempfile.mkdtemp(prefix="uxfix-wide-"))
        last = folder / ("ESPN NFL 2K5 (USA) " + "very long dump name " * 6 + ".xiso.iso")
        last.write_bytes(b"x")
        state = SimpleNamespace(recent_sources=(str(last),), recent_projects=())
        window.navigation.setCurrentRow(0)
        for width in (1280, 1366, 1920):
            window.resize(width, 720 if width == 1280 else 900)
            _pump(self.app, 15)
            with mock.patch.object(window, "_workspace_state", return_value=state):
                window._refresh_welcome_state()
            _pump(self.app, 10)
            continue_button = window.welcome_continue_button
            self.assertFalse(continue_button.isHidden())
            buttons = [window.welcome_install_button, window.welcome_open_button, *window.welcome_task_buttons,
                       continue_button]
            for button in buttons:
                with self.subTest(font=tag or "platform", width=width, button=button.text()):
                    self.assertTrue(button.isVisible())
                    self.assertGreaterEqual(button.width(), button.sizeHint().width())   # nothing elided or clipped
                    right = button.mapTo(window, button.rect().topRight()).x()
                    self.assertLessEqual(right, window.width())
            self.assertIn("…", continue_button.text())              # the long name is shortened, not the page widened
            lowest = max(b.mapTo(window, b.rect().bottomLeft()).y()
                         for b in (window.welcome_install_button, window.welcome_open_button, *window.welcome_task_buttons))
            self.assertGreater(continue_button.mapTo(window, continue_button.rect().topLeft()).y(), lowest)
            if width == 1280:
                _shot(window, "after_welcome_continue_row_1280x720" + tag)
        with mock.patch.object(window, "_request_source_switch") as switch:     # the Continue row still opens its file
            window.welcome_continue_button.click()
        switch.assert_called_once()
        self.assertEqual(Path(switch.call_args.args[0]), last)
        return window.welcome_install_button.sizeHint().width()

    def test_8_no_getting_started_button_is_cut_off_at_1280x720_with_continue_showing(self):
        # b780-uxfix2: Continue with <file> shared the row and every label clipped ("stall SOFTDRINK 2K28")
        self._start_buttons_fit(self.window)
        self._size(1280, 720)

    def test_9_the_start_buttons_wrap_with_a_much_wider_font(self):
        # b780 CI (windows-latest): Windows has neither stylesheet font (Noto Sans, DejaVu Sans) and its substitute
        # made the four buttons in one row 1,809 px wide in a 1280-px window. They now wrap (ux_text.FlowLayout).
        # "Much wider" is relative to this platform's own text: every font-size in the window's stylesheet is scaled 1.5x
        # of what this OS draws (the Windows runner already draws about 2x Linux, so 1.5x there is about 3x Linux).
        # Every button must keep its natural width inside 1280 px, Continue below them and working, and no label or
        # button anywhere on the page may be narrower than its text (the title and step titles wrap).
        import re
        window = self.window
        normal = window.welcome_install_button.sizeHint().width()
        sheet = window.styleSheet()
        _font_report(window.welcome_install_button)
        window.setStyleSheet(re.sub(r"font-size:\s*(\d+)px", lambda m: f"font-size: {round(int(m.group(1)) * 1.5)}px", sheet))
        _pump(self.app, 15)
        _font_report(window.welcome_install_button)
        try:
            widened = self._start_buttons_fit(window, "_wide_font")
            window.resize(1280, 720)
            _pump(self.app, 15)
            page = window.welcome_install_button
            while page.parentWidget() is not None and type(page.parentWidget()).__name__ != "QStackedWidget":
                page = page.parentWidget()
            for widget in page.findChildren(QLabel) + page.findChildren(QPushButton):
                if widget.isVisible() and not (isinstance(widget, QLabel) and widget.wordWrap()):
                    with self.subTest(clipped=widget.text()[:40]):
                        self.assertGreaterEqual(widget.width(), widget.sizeHint().width())
        finally:
            window.setStyleSheet(sheet)
            _pump(self.app, 15)
            self._size(1280, 720)
        self.assertGreater(widened, normal * 1.25)       # the wider text really reached the page

    def test_7_getting_started_offers_the_last_game_file(self):
        window = self.window
        folder = Path(tempfile.mkdtemp(prefix="uxfix-recent-"))
        last = folder / "ESPN NFL 2K5 (USA).iso"
        last.write_bytes(b"x")
        state = SimpleNamespace(recent_sources=(str(folder / "gone.iso"), str(last)), recent_projects=())
        with mock.patch.object(window, "_workspace_state", return_value=state), \
             mock.patch.object(window, "_request_source_switch") as switch:
            window._refresh_welcome_state()
            button = window.welcome_continue_button
            self.assertFalse(button.isHidden())
            self.assertEqual(button.text(), "Continue with ESPN NFL 2K5 (USA).iso")   # the newest file that exists
            button.click()
        switch.assert_called_once_with(last)
        with mock.patch.object(window, "_workspace_state", return_value=None):
            window._refresh_welcome_state()
        self.assertTrue(window.welcome_continue_button.isHidden())

    def test_6_opening_gameplay_at_1480x920_reports_no_error(self):
        from mod_editor.gui import crash_report
        window = self.window
        folder = Path(tempfile.mkdtemp(prefix="uxfix-errors-"))
        self._size(1480, 920)
        with _Hook() as hook:
            # the running Studio's hook body (crash_report.install), writing to a scratch folder
            sys.excepthook = lambda kind, exc, tb: (hook.seen.append(exc),
                                                    crash_report.handle(kind, exc, tb, app_name="2K5 Mod Studio",
                                                                        directory=folder, show_dialog=False))
            page = window.open_workspace("sliders_gameplay")
            _pump(self.app, 20)
            for width in (1480, 1280, 1366, 1040, 1480):
                self._size(width, 920)
            _shot(window, "after_gameplay_1480x920")
            # Opening Gameplay builds the Build options it shares (window._build_panel). A layout can squeeze one
            # of their wrapping check boxes narrower than its indicator for a moment (a first layout pass, a
            # collapsed section, a small window). That is what recursed; make every box live through it.
            from mod_editor.gui.ux_text import WrappingCheckBox
            self.assertIsNotNone(page)
            window.open_workspace("build_share")         # shown, so a resize reaches each box at once
            window._build_share_page.setCurrentWidget(window._build_panel)
            _pump(self.app, 10)
            boxes = [box for box in window._build_panel.findChildren(WrappingCheckBox) if box.isVisible()]
            self.assertGreater(len(boxes), 20)
            for box in boxes:
                for width in (10, 1):
                    box.resize(width, max(1, box.height()))
            _pump(self.app, 5)
            self._size(1480, 920)
            window.navigation.setCurrentRow(0)
        self.assertEqual([type(exc).__name__ for exc in hook.seen], [])
        log = folder / "errors.log"
        self.assertFalse(log.exists() and log.stat().st_size,
                         log.read_text(encoding="utf-8")[:2000] if log.exists() else "")
        self._size(1280, 720)


if __name__ == "__main__":
    unittest.main()
