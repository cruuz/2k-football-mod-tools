"""Reviewer fix pass for beta 81 (job b81-rev-editor): launch checks, exports, staged save copies, staging recovery,
the disc check error path, the 2K5 first window, the Field Art links, and the E02/E04 paths that had no test.

Synthetic inputs, so the file runs on every hosted runner. Cases that read the retail game or the released v0.9 disc
skip without them.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools", ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MOD_STUDIO_NO_UPDATE_CHECK", "1")

from PyQt5.QtCore import QRect, QSize  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QComboBox, QFileDialog, QLineEdit  # noqa: E402

from mod_editor.core import image_use  # noqa: E402
from mod_editor.core import modpack, modpack_files  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", ""))
V09 = Path(os.environ.get("NFL2K5_V09_XISO", ""))


def tree(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


class _App(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)


# --------------------------------------------------------------------------- 1. the xemu check before Play
class LaunchChecksEveryStudioDisc(_App):
    """Every disc Studio made is checked before Play latest disc. A disc with the 128 MB patch needs 128 MiB and
    Complex 4627 (the beta 80 check); a disc without it runs at either setting, so a 64 MB edition is never told
    to switch to 128 MiB."""

    def launch_target(self, build, k128_state="applied"):
        from mod_editor.core import nfl2k5_k128
        from mod_editor.studio import facade as studio_facade
        seen = []
        host = SimpleNamespace(xemu_command=("xemu",), _lock=threading.Lock(), _last_build=build,
                               _process_launcher=mock.Mock())
        xs = "mod_editor.studio.xemu_settings."
        with patch(xs + "config_path", return_value=self.root / "xemu.toml"), \
                patch(xs + "play_warning", side_effect=lambda _config, target_mb=128: seen.append(target_mb) or ""), \
                patch(xs + "grant_build_folder", return_value=""), patch(xs + "remember_disc", return_value=None), \
                patch(xs + "disc_help", return_value="disc"), \
                patch.object(studio_facade, "_validate_xemu_executable", lambda *a, **k: None), \
                patch.object(nfl2k5_k128, "status", return_value=k128_state):
            studio_facade.Nfl2k5StudioFacade.launch_xemu(host, lambda *a: None)
        return seen[0]

    def test_rosters_copies_and_project_builds_are_checked_from_the_disc(self) -> None:
        from mod_editor.studio.facade import ExternalBuild
        disc = self.root / "copy.xiso.iso"
        disc.write_bytes(b"disc")
        self.assertEqual(self.launch_target(ExternalBuild(output_xiso=disc)), 128)               # ★ Rosters copy
        self.assertEqual(self.launch_target(SimpleNamespace(output_xiso=disc)), 128)              # project build
        self.assertIsNone(self.launch_target(ExternalBuild(output_xiso=disc), "retail"))          # no 128 MB patch
        self.assertEqual(self.launch_target(ExternalBuild(output_xiso=disc, console_memory=64)), 64)
        self.assertEqual(self.launch_target(ExternalBuild(output_xiso=disc, console_memory=128), "retail"), 128)

    @unittest.skipUnless(RETAIL.is_file() and V09.is_file(), "retail game and released v0.9 disc unavailable")
    def test_real_discs(self) -> None:
        from mod_editor.studio.facade import ExternalBuild, launch_memory_target
        self.assertIsNone(launch_memory_target(ExternalBuild(output_xiso=RETAIL)))
        self.assertEqual(launch_memory_target(ExternalBuild(output_xiso=V09)), 128)


# --------------------------------------------------------------------------- 2 and 7. manual Export, retail label
class ExportMatchesQuickExport(_App):
    def images(self, built_files):
        from test_modpack_files import image
        original = {"default.xbe": b"XBEH" + bytes(5000), "a": b"A" * 3000, "b": b"B" * 3000, "c": b"C" * 100}
        return image(self.root / "base.iso", original), image(self.root / "built.iso", built_files(original))

    def leftovers(self):
        return sorted(p.name for p in self.root.iterdir() if p.name.endswith(".part") or p.name.startswith(".2k5-"))

    def test_last_file_growth_exports_like_quick_export_and_installs(self) -> None:
        from test_modpack_files import contents
        base, built = self.images(lambda files: dict(files, c=b"C" * 4000))
        manual, quick = self.root / "manual.2k5patch", self.root / "quick.2k5patch"
        modpack_files.export_for_share(base, built, manual, {"name": "Grown"})
        modpack_files.export_for_share(base, built, quick, {"name": "Grown", "file_based": True})
        for pack in (manual, quick):
            target = self.root / (pack.stem + ".iso")
            modpack.apply(modpack.load(pack), base, target)
            self.assertEqual(contents(target), contents(built))
        self.assertEqual(self.leftovers(), [])

    def test_a_pair_both_writers_refuse_leaves_no_output(self) -> None:
        base, built = self.images(lambda files: dict(files, d=b"D" * 500))
        output = self.root / "added.2k5patch"
        with self.assertRaises(modpack.ModpackError):
            modpack_files.export_for_share(base, built, output, {"name": "Added"})
        self.assertFalse(output.exists())
        self.assertEqual(self.leftovers(), [])

    def labelled_base(self, kind):
        from mod_editor.core import nfl2k5_disc_identity as identity
        base, built = self.images(lambda files: dict(files, a=b"Z" * 3000))
        xbe = b"XBEH" + bytes(5000)
        output = self.root / f"{kind}.2k5patch"
        with patch.object(identity, "identify", return_value=SimpleNamespace(kind=kind)), \
                patch.object(identity, "RETAIL_XBE_SIZE", len(xbe)), \
                patch.object(identity, "RETAIL_XBE_SHA256", hashlib.sha256(xbe).hexdigest()):
            modpack_files.export_for_share(base, built, output, {"name": kind, "file_based": True})
        return modpack.load(output).manifest.raw["base"]

    def test_a_verified_retail_base_asks_installers_for_a_clean_usa_dump(self) -> None:
        from mod_editor.core import nfl2k5_disc_identity as identity
        from mod_editor.gui.share_panel_qt import SharePanel
        retail = self.labelled_base(identity.KIND_RETAIL_XISO)
        self.assertTrue(retail["is_retail_equivalent"])
        self.assertEqual(retail["label"], "Clean ESPN NFL 2K5 USA files")
        modified = self.labelled_base(identity.KIND_MODIFIED)
        self.assertFalse(modified["is_retail_equivalent"])
        self.assertIn("starting game files", modified["label"])
        summary = SharePanel.summarize(modpack_files.inspect(modpack.load(self.root / f"{identity.KIND_RETAIL_XISO}.2k5patch")))
        self.assertIn("clean USA Xbox dumps", summary)

    @unittest.skipUnless(RETAIL.is_file() and V09.is_file(), "retail game and released v0.9 disc unavailable")
    def test_real_retail_and_modded_bases(self) -> None:
        self.assertTrue(modpack_files._retail_base(RETAIL))
        self.assertFalse(modpack_files._retail_base(V09))


# --------------------------------------------------------------------------- 3. ★ Rosters signed save copy
class SignedSaveCopyIsStaged(_App):
    def source(self):
        from test_franchise_panel_qt import synthetic_franchise_with_coach
        from test_roster_editor_panel_franchise import write_container
        folder = write_container(self.root / "fr", synthetic_franchise_with_coach(year_field=7, user_team=0))
        return folder, rr.SaveContainer.load(folder)

    def test_an_output_inside_the_source_save_is_refused_and_writes_nothing(self) -> None:
        folder, container = self.source()
        before = tree(folder)
        for inside in (folder / "53450030", folder / "53450030" / "0001", folder / "new"):
            with self.subTest(inside=inside.relative_to(folder).as_posix()), \
                    self.assertRaisesRegex(rr.RosterRecordError, "outside the source save"):
                container.write(inside, container.savegame)
        self.assertEqual(tree(folder), before)

    def test_a_failed_copy_leaves_nothing_and_the_same_folder_can_be_retried(self) -> None:
        from mod_editor.core import nfl2k5_save_writer as writer
        folder, container = self.source()
        output = self.root / "copy"
        write = writer._write_staged_save

        def fail_extra(path, data):
            if path.name == "EXTRA":
                raise OSError("disk full")
            write(path, data)

        with patch.object(writer, "_write_staged_save", fail_extra), self.assertRaisesRegex(OSError, "disk full"):
            container.write(output, container.savegame)
        self.assertFalse(output.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".2k5-save-")], [])
        receipt = container.write(output, container.savegame)
        self.assertTrue(receipt["signed"])
        copy = rr.SaveContainer.load(output)
        self.assertEqual(copy.members, container.with_savegame(container.savegame))

    def test_an_existing_folder_keeps_other_files_and_a_conflict_is_refused_first(self) -> None:
        folder, container = self.source()
        output = self.root / "Saves"
        (output / "other").mkdir(parents=True)
        (output / "other" / "keep.bin").write_bytes(b"other save")
        container.write(output, container.savegame)
        self.assertEqual((output / "other" / "keep.bin").read_bytes(), b"other save")
        second = self.root / "Second"
        (second / "53450030" / "0001").mkdir(parents=True)
        (second / "53450030" / "0001" / "EXTRA").write_bytes(b"mine")
        with self.assertRaisesRegex(rr.RosterRecordError, "exists"):
            container.write(second, container.savegame)
        self.assertEqual(tree(second), {"53450030/0001/EXTRA": hashlib.sha256(b"mine").hexdigest()})

    def test_franchise_page_signed_copy_retries_the_same_name(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
        from mod_editor.core import nfl2k5_save_writer as writer
        folder, _container = self.source()
        panel = RosterEditorPanel()
        self.addCleanup(panel.deleteLater)
        self.assertTrue(panel.load_save(folder))
        panel.franchise_panel.cap_spin.setValue(18.0)
        output = self.root / "Franchise copy"
        with patch.object(writer.platform_compat, "publish_no_replace", side_effect=OSError("held")), \
                self.assertRaises((OSError, rr.RosterRecordError)):
            panel.write_copy_to(output)
        self.assertFalse(output.exists())
        self.assertTrue(panel.write_copy_to(output)["signed"])


# --------------------------------------------------------------------------- 6. stale staging recovery
class StagingRecovery(_App):
    def stale(self, name, marker=image_use.STAGING_MARKER_TEXT, extra=("disc.iso",)):
        folder = self.root / name
        folder.mkdir()
        if marker is not None:
            (folder / image_use.STAGING_MARKER).write_bytes(marker)
        for item in extra:
            (folder / item).write_bytes(b"partial")
        return folder

    def test_only_unlocked_marked_studio_folders_are_removed(self) -> None:
        crashed = self.stale(".roster-crashed")
        unmarked = self.stale(".roster-unmarked", marker=None)
        foreign = self.stale(".roster-foreign", marker=b"something else entirely, same length?".ljust(
            len(image_use.STAGING_MARKER_TEXT), b"."))
        backup = self.stale(".roster-backup", extra=("new", image_use.ROLLBACK_NAME))
        other_prefix = self.stale(".2k5-save-crashed")
        with image_use.studio_staging(self.root, ".roster-") as live:
            self.assertFalse(crashed.exists())
            self.assertTrue(live.path.is_dir())
            self.assertEqual(image_use.recover_studio_staging(self.root, ".roster-"), [])   # the live one is locked
            self.assertTrue(live.path.is_dir())
        self.assertFalse(live.path.exists())
        for kept in (unmarked, foreign, backup, other_prefix):
            self.assertTrue(kept.is_dir(), kept.name)

    def test_a_link_named_like_staging_is_never_followed(self) -> None:
        target = self.root / "user folder"
        target.mkdir()
        (target / image_use.STAGING_MARKER).write_bytes(image_use.STAGING_MARKER_TEXT)
        (target / "precious.txt").write_bytes(b"keep")
        try:
            (self.root / ".roster-link").symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        image_use.recover_studio_staging(self.root, ".roster-")
        self.assertEqual((target / "precious.txt").read_bytes(), b"keep")

    def test_a_kept_folder_is_marked_for_the_user_and_survives_recovery(self) -> None:
        with image_use.studio_staging(self.root, ".2k5-save-") as stage:
            (stage.path / "new").write_bytes(b"x")
            stage.keep = True
        self.assertTrue((stage.path / image_use.RECOVERY_MARKER).is_file())
        image_use.recover_studio_staging(self.root, ".2k5-save-")
        self.assertTrue(stage.path.is_dir())

    def test_the_next_disc_copy_and_save_copy_clean_their_own_stale_folders(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
        from mod_editor.core import nfl2k5_save_writer as writer
        roster = self.stale(".roster-old")
        save = self.stale(".2k5-save-old", extra=("new",))
        source = self.root / "source.iso"
        source.write_bytes(b"disc")
        with patch.object(rr, "apply", return_value={"status": "edited"}):
            RosterEditorPanel._write_disc_copy(source, self.root / "copy.iso", {}, False)
        self.assertFalse(roster.exists())
        writer.publish_save_files({self.root / "loose.bin": b"data"}, {self.root / "loose.bin": None})
        self.assertFalse(save.exists())


# --------------------------------------------------------------------------- 9. E04 roster disc copy
class RosterDiscCopy(_App):
    def test_staged_validated_before_publish_failure_leaves_nothing_and_retry_works(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
        source = self.root / "retail.iso"
        source.write_bytes(b"retail disc")
        destination = self.root / "edited.iso"
        seen = []

        def apply(path, edits):
            seen.append((Path(path).parent != destination.parent, destination.exists()))
            Path(path).write_bytes(b"edited disc")
            return {"status": "edited"}

        def broken(path, edits):
            Path(path).write_bytes(b"half")
            raise rr.RosterRecordError("the roster does not read back")

        with patch.object(rr, "apply", broken), self.assertRaisesRegex(rr.RosterRecordError, "read back"):
            RosterEditorPanel._write_disc_copy(source, destination, {}, False)
        self.assertFalse(destination.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".roster-")], [])
        with patch.object(rr, "apply", apply):
            RosterEditorPanel._write_disc_copy(source, destination, {}, False)
        self.assertEqual(seen, [(True, False)])            # edited in staging, before the output existed
        self.assertEqual(destination.read_bytes(), b"edited disc")
        self.assertEqual(source.read_bytes(), b"retail disc")
        with patch.object(rr, "apply", apply), self.assertRaises(FileExistsError):
            RosterEditorPanel._write_disc_copy(source, destination, {}, False)
        self.assertEqual(destination.read_bytes(), b"edited disc")

    def test_gui_copy_runs_on_a_worker_and_refuses_an_existing_name(self) -> None:
        from mod_editor.gui import roster_editor_panel_qt as panel_module
        from test_nfl2k5_roster_records import synthetic_body
        panel = panel_module.RosterEditorPanel()
        self.addCleanup(panel.deleteLater)
        panel.load_document(rr.load_body(synthetic_body()), label="body")
        source = self.root / "retail.iso"
        source.write_bytes(b"retail disc")
        panel._source_kind, panel._source_path = "disc", source
        destination = self.root / "edited.iso"
        threads = []

        def apply(path, edits):
            threads.append(threading.get_ident())
            Path(path).write_bytes(b"edited disc")
            return {"status": "edited"}

        written, errors = [], []
        panel.disc_written.connect(written.append)
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")), \
                patch.object(rr, "apply", apply), \
                patch.object(panel_module, "show_operation_error", lambda *a: errors.append(a)):
            panel._write_copy()
            self.assertEqual(written, [str(destination)])
            self.assertNotEqual(threads, [threading.get_ident()])
            panel._write_copy()
        self.assertEqual(len(errors), 1)
        self.assertIn("new output filename", errors[0][2])
        self.assertEqual(destination.read_bytes(), b"edited disc")


# --------------------------------------------------------------------------- 9. E02 load prompt and staff
class RosterWithFacesLoad(_App):
    def panel(self):
        from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
        panel = RosterEditorPanel()
        self.addCleanup(panel.deleteLater)
        return panel

    def test_load_asks_first_and_a_refusal_changes_nothing(self) -> None:
        panel = self.panel()
        chosen = self.root / "faces.json"
        chosen.write_text("{}", encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(chosen), "")), \
                patch.object(panel, "_confirm_replace", return_value=False) as ask, \
                patch.object(panel, "load_roster_with_faces") as load:
            panel._import_roster_faces()
        ask.assert_called_once()
        load.assert_not_called()
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(chosen), "")), \
                patch.object(panel, "_confirm_replace", return_value=True), \
                patch.object(panel, "load_roster_with_faces") as load:
            panel._import_roster_faces()
        load.assert_called_once_with(str(chosen))

    def test_the_file_staff_plan_is_checked_and_restored_after_the_roster_loads(self) -> None:
        from mod_editor.core import nfl2k5_roster_appearance_transfer as appearance
        from test_roster_appearance_transfer import fixture
        panel = self.panel()
        source, catalog = fixture(self.root / "source", 0xA5)
        from mod_editor.core import nfl2k5_coach_staff
        staff = dict(nfl2k5_coach_staff.empty(), created_coaches=[{"id": "new-1", "first": "Pat", "last": "Coach"}])
        with patch.object(appearance, "_catalog", return_value=catalog), \
                patch.object(panel, "_reload_espn25"), patch.object(panel, "_load_templates"):
            panel.load_document(rr.load_image(source.path), source=source.path, kind="disc")
            exported = panel.save_roster_with_faces_to(self.root / "faces.json")
            document = json.loads((self.root / "faces.json").read_text(encoding="utf-8"))
            document["staff"] = staff
            (self.root / "faces.json").write_text(json.dumps(document), encoding="utf-8")
            checked = []
            def check(body, teams, plan, log, **kwargs):
                checked.append(plan)
                return {"coach_names_written": 0, "coach_records_written": None, "coach_staff": None}

            with patch.object(rr, "apply_coach_edits", check), \
                    patch.object(panel.coaches_panel, "set_staff") as restore:
                panel.load_roster_with_faces(self.root / "faces.json")
        self.assertTrue(exported["appearance_assets"])
        self.assertIn({"staff": staff}, checked)
        restore.assert_called_with(staff)
        self.assertIsNotNone(panel._appearance_bundle)


# --------------------------------------------------------------------------- 4, 5 and D19: the Studio window
class StudioWindow(_App):
    def window(self, **kwargs):
        from mod_editor.gui.studio_qt import StudioMainWindow
        window = StudioMainWindow(offer_recovery=False, **kwargs)
        self.addCleanup(window.deleteLater)
        return window

    def test_first_window_fits_the_monitor_under_the_pointer(self) -> None:
        for x, y, width, height in ((0, 0, 1366, 768), (1920, 30, 1366, 768),
                                    (-1366, -60, 1366, 768), (0, 0, 1920, 1080)):
            with self.subTest(origin=(x, y), width=width):
                available = QRect(x, y, width, height)
                with patch.object(QApplication, "screenAt") as screen:
                    screen.return_value.availableGeometry.return_value = available
                    window = self.window()
                self.assertTrue(available.contains(window.geometry()), (available, window.geometry()))
                self.assertEqual(window.geometry().center(), available.center())
                self.assertEqual(window.size(), QSize(min(1480, width - 24), min(920, height - 48)))
                window._allow_close = True
                window.close()

    def test_an_unexpected_disc_check_error_shows_the_normal_message(self) -> None:
        # Review correction: the shared task runner already shows the error after the dialog's own handler.
        from mod_editor.core import nfl2k5_disc_check as checker
        window = self.window()
        window.show()
        shown = []
        window._show_error = shown.append
        image = self.root / "disc.iso"
        image.write_bytes(b"not used")
        with patch.object(checker, "check", side_effect=RuntimeError("unexpected boom")), \
                patch.object(QFileDialog, "getOpenFileName", return_value=(str(image), "")):
            window._choose_disc_check()
            deadline = time.monotonic() + 8
            while window._blocking and time.monotonic() < deadline:
                QTest.qWait(10)
        self.assertFalse(window._blocking)
        self.assertEqual(len(shown), 1)
        self.assertIn("unexpected boom", shown[0])
        self.assertIsNone(getattr(window, "_disc_check_dialog", None))
        window._allow_close = True
        window.close()

    def test_field_art_links_name_real_texture_groups_and_never_fall_back_to_all(self) -> None:
        from mod_editor.core.nfl2k5_p8_texture_writer import DEFAULT_REPORT, EXPECTED_GROUPS
        from mod_editor.gui import studio_qt
        groups = set(EXPECTED_GROUPS)
        if DEFAULT_REPORT.is_file():
            report = json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))
            groups &= {row.get("group") for row in report["targets"]}
        combo, search = QComboBox(), QLineEdit("old search")
        combo.addItem("All asset groups", None)
        for group in sorted(groups, key=str.casefold):
            combo.addItem(group, group)
        status = []
        host = SimpleNamespace(_navigation_row=lambda _category: 3, _ensure_workspace=lambda _row: None,
                               _visual_browsers={studio_qt.ProductCategory.TEXTURES:
                                                 SimpleNamespace(group_filter=combo, search=search)},
                               navigation=SimpleNamespace(setCurrentRow=lambda row: status.append(("row", row))),
                               _set_status=lambda text: status.append(text))
        for _caption, group in studio_qt.FIELD_ART_TEXTURE_LINKS:
            with self.subTest(group=group):
                studio_qt.StudioMainWindow._browse_nfl_field_textures(host, group)
                self.assertEqual(combo.currentData(), group)
                self.assertEqual(search.text(), "")
        combo.setCurrentIndex(1)
        studio_qt.StudioMainWindow._browse_nfl_field_textures(host, "End Zones")   # a renamed group
        self.assertEqual(combo.currentIndex(), 1)
        self.assertIn("No End Zones textures", status[-1])


# --------------------------------------------------------------------------- 13. the public Discord invite
INVITE = "https://discord.gg/FkNSKRAKch"     # Noah's public invite, 2026-11-18 (#2k5-help, no expiry)


class PublicDiscordInvite(_App):
    """One constant, read by both Studios' Help menus, the welcome card, error hints and build reports; every shipped
    document that links Discord uses the same invite, and neither the expired one nor the members-only route is left."""

    def test_the_one_constant_is_the_public_invite(self) -> None:
        from mod_editor.core import build_report, errors, update_check
        from mod_editor.gui import ux_text
        self.assertEqual(errors.COMMUNITY_DISCORD, INVITE)
        self.assertIs(update_check.COMMUNITY_DISCORD, errors.COMMUNITY_DISCORD)
        for text in (ux_text.DISCORD_HINT, ux_text.DIAGNOSTIC_DESTINATION, build_report.DISCORD,
                     ux_text.failure_body("Something failed.")):
            self.assertIn(INVITE, text)

    def test_every_shipped_file_links_the_same_invite(self) -> None:
        import re
        shipped = set()
        for allowlist in ("packaging/release-allowlist.txt", "packaging/apf2k8-release-allowlist.txt"):
            shipped |= {line.strip() for line in (ROOT / allowlist).read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.startswith("#")}
        shipped |= {"packaging/windows/build_windows_installer.py", "packaging/windows/studio_bootstrap.py"}
        found = {}
        for name in sorted(shipped):
            path = ROOT / name
            if not path.is_file() or path.suffix.lower() not in (".py", ".md", ".txt", ".sh", ".bat", ".command", ".json"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for url in re.findall(r"https?://(?:www\.)?discord(?:app)?\.(?:gg|com)/[^\s)>\"'`]*", text):
                found.setdefault(url, []).append(name)
        self.assertEqual(set(found) - {INVITE}, set(), found)
        self.assertIn(INVITE, found)
        for name in ("README.md", "APF2K8-README.md", "docs/START_HERE.md", "docs/mod_editor/2k5_mod_studio_faq.md",
                     "docs/mod_editor/2k5_mod_studio_getting_started.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(INVITE, text, name)
            self.assertNotIn("(members)", text, name)

    def help_actions(self, window):
        from PyQt5.QtGui import QDesktopServices
        menu = next(action.menu() for action in window.menuBar().actions() if action.text() == "&Help")
        actions = {action.text(): action for action in menu.actions()}
        opened = []
        with patch.object(QDesktopServices, "openUrl", side_effect=lambda url: opened.append(url.toString())):
            actions["Join the Discord…"].trigger()
            actions["Report a bug…"].trigger()
        return opened

    def test_both_studios_help_menus_open_the_invite_and_the_issue_tracker(self) -> None:
        from mod_editor.apf_studio.facade import ApfStudioFacade
        from mod_editor.apf_studio.gui import ApfStudioMainWindow
        from mod_editor.core import update_check
        from mod_editor.gui.studio_qt import StudioMainWindow
        from PyQt5.QtWidgets import QLabel
        studio = StudioMainWindow(offer_recovery=False)
        apf = ApfStudioMainWindow(ApfStudioFacade(cache_root=self.root / "apf-cache"), offer_recovery=False)
        try:
            for window in (studio, apf):
                self.assertEqual(self.help_actions(window), [INVITE, update_check.ISSUES_PAGE])
            card = next(label for label in studio.findChildren(QLabel) if label.accessibleName() == "Community help link")
            self.assertIn(INVITE, card.text())
            self.assertIn(update_check.ISSUES_PAGE, card.text())
        finally:
            for window in (studio, apf):
                window._allow_close = True
                window.close()
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
