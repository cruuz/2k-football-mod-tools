"""Independent review of the beta 81 editor repairs (job b81-rev-editor).

Each case exercises a claim from the beta 81 audit record on a path its own tests did not cover, or proves a defect
found in review. Synthetic inputs only, so the file runs on every hosted runner.
"""

from __future__ import annotations

import errno
import hmac
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_save_writer as saver  # noqa: E402
from mod_editor.core import platform_compat  # noqa: E402


class FranchiseExportKeepsTheWarning(unittest.TestCase):
    """E01: a franchise-only change stays unsaved after Export roster edits and is saved by the signed copy."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
        from test_franchise_panel_qt import synthetic_franchise_with_coach
        from test_roster_editor_panel_franchise import write_container

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.panel = RosterEditorPanel()
        self.addCleanup(self.panel.deleteLater)
        source = write_container(self.root / "fr", synthetic_franchise_with_coach(year_field=7, user_team=0))
        self.assertTrue(self.panel.load_save(source))

    def unsaved(self) -> bool:
        # The same three questions StudioMainWindow._roster_work_unsaved asks.
        panel = self.panel
        return panel.is_dirty() and (panel._edits_snapshot is None or panel._edits_snapshot != panel.edits_key())

    def test_cap_change_survives_an_export_and_clears_after_the_signed_copy(self) -> None:
        page = self.panel.franchise_panel
        page.cap_spin.setValue(18.0)
        self.assertEqual(len(page.edits), 1)
        self.assertTrue(self.unsaved())
        document = self.panel.save_edits_to(self.root / "edits.json")
        self.assertEqual(document.get("edits", []), [])
        self.assertTrue(self.unsaved(), "an export that cannot hold franchise changes must not clear the warning")
        receipt = self.panel.write_copy_to(self.root / "copy")
        self.assertTrue(receipt["signed"])
        self.assertFalse(self.unsaved())


class XboxSaveCopyOnVolumesWithoutAtomicFolderRename(unittest.TestCase):
    """The signed save copy publishes a NEW folder with publish_no_replace(is_directory=True), which refuses to run where
    the volume has neither renameat2(RENAME_NOREPLACE) nor renamex_np(RENAME_EXCL): Linux ntfs-3g (fuseblk) drives and
    other FUSE/network folders. Beta 80 wrote the two files there. The simulation removes both primitives, which is the
    state platform_compat reaches on such a volume (renameat2 returns EINVAL there)."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        work = Path(self.temp.name)
        from nfl2k5_save_writer_test import _build_synth_xbe, _settings_save

        self.xbe = work / "default.xbe"
        self.xbe.write_bytes(_build_synth_xbe())
        key = saver.derive_sig_key(self.xbe.read_bytes())
        self.save = work / "Franchise" / "SAVEGAME.DAT"
        self.save.parent.mkdir()
        data = _settings_save()
        self.save.write_bytes(data)
        self.save.with_name("EXTRA").write_bytes(hmac.digest(key, data, "sha1"))

    def test_suggested_new_folder_is_written_without_renameat2(self) -> None:
        target = saver.suggested_save_copy(self.save)
        if platform_compat.IS_WINDOWS:
            self.skipTest("Windows publishes folders with its own no-clobber rename")
        with patch.object(platform_compat, "_linux_renameat2", lambda: None), \
             patch.object(platform_compat, "_macos_renameatx_np", lambda: None):
            saver.edit_save_file(self.save, target, target.with_name("EXTRA"), xbe_path=self.xbe,
                                 sliders={"Injury": 0.5})
        self.assertEqual(len(target.read_bytes()), saver.SETTINGS_SAVE_SIZE)
        self.assertEqual(len(target.with_name("EXTRA").read_bytes()), 20)
        self.assertEqual(sorted(p.name for p in target.parent.iterdir()), ["EXTRA", "SAVEGAME.DAT"])

    def test_a_failed_fallback_leaves_no_folder_and_the_same_name_can_be_retried(self) -> None:
        target = saver.suggested_save_copy(self.save)
        if platform_compat.IS_WINDOWS:
            self.skipTest("Windows publishes folders with its own no-clobber rename")
        publish = platform_compat.publish_no_replace

        def second_file_fails(staging, destination, **kwargs):
            if Path(destination).name == "EXTRA":
                raise OSError(errno.EIO, "simulated write failure")
            return publish(staging, destination, **kwargs)

        with patch.object(platform_compat, "_linux_renameat2", lambda: None), \
             patch.object(platform_compat, "_macos_renameatx_np", lambda: None):
            with patch.object(platform_compat, "publish_no_replace", side_effect=second_file_fails), \
                 self.assertRaises(OSError):
                saver.edit_save_file(self.save, target, target.with_name("EXTRA"), xbe_path=self.xbe,
                                     sliders={"Injury": 0.5})
            self.assertFalse(target.parent.exists())
            self.assertEqual(list(self.save.parent.parent.glob(".2k5-save-*")), [])
            saver.edit_save_file(self.save, target, target.with_name("EXTRA"), xbe_path=self.xbe,
                                 sliders={"Injury": 0.5})
        self.assertTrue(target.is_file())

    def test_final_readback_failure_rolls_back_each_new_folder_route_and_can_retry(self) -> None:
        publish = platform_compat.publish_no_replace
        source = {file.name: file.read_bytes() for file in self.save.parent.iterdir()}
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                target = self.save.parent.parent / str(fallback) / "copy" / "SAVEGAME.DAT"
                extra = target.with_name("EXTRA")
                def publish_files(staged, destination, **kwargs):
                    if fallback and kwargs.get("is_directory"):
                        raise platform_compat.NoReplacePublishUnavailable("folder rename unavailable")
                    return publish(staged, destination, **kwargs)
                with patch.object(platform_compat, "publish_no_replace", side_effect=publish_files):
                    with patch.object(saver, "_verify_published", side_effect=OSError("readback failed")), \
                         self.assertRaisesRegex(OSError, "readback failed"):
                        saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5})
                    self.assertFalse(target.parent.parent.exists())
                    saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5})
                key = saver.derive_sig_key(self.xbe.read_bytes())
                self.assertEqual(extra.read_bytes(), hmac.digest(key, target.read_bytes(), "sha1"))
        self.assertEqual({file.name: file.read_bytes() for file in self.save.parent.iterdir()}, source)

    def test_replaced_existing_output_and_its_previous_copy_both_survive_rollback(self) -> None:
        target = self.save.parent.parent / "other" / "SAVEGAME.DAT"
        extra = target.with_name("EXTRA")
        target.parent.mkdir()
        target.write_bytes(b"previous game")
        extra.write_bytes(b"previous signature")
        foreign = target.parent / "incoming"
        foreign.write_bytes(b"another program's file")

        def replace_during_verify(files):
            os.replace(foreign, target)
            raise OSError("readback interrupted")

        with patch.object(saver, "_verify_published", side_effect=replace_during_verify), \
             self.assertRaises(saver.SaveWriterError) as error:
            saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5}, overwrite=True)
        self.assertEqual(target.read_bytes(), b"another program's file")
        self.assertEqual(extra.read_bytes(), b"previous signature")
        backups = list(target.parent.glob(".2k5-save-*/original"))
        self.assertEqual([file.read_bytes() for file in backups], [b"previous game"])
        self.assertIn(str(target), str(error.exception))
        self.assertIn(str(backups[0]), str(error.exception))

    def test_replacement_at_the_rollback_rename_is_restored_without_clobbering_a_later_file(self) -> None:
        move = os.replace
        for collision in (False, True):
            with self.subTest(collision=collision):
                directory = self.save.parent.parent / str(collision)
                directory.mkdir()
                target, extra = directory / "SAVEGAME.DAT", directory / "EXTRA"
                arriving = directory / "incoming"
                arriving.write_bytes(b"foreign content")

                def race(source, destination):
                    if source == target:
                        move(arriving, target)
                    move(source, destination)
                    if source == target and collision:
                        target.write_bytes(b"later file")

                with patch.object(saver, "_verify_published", side_effect=OSError("failed readback")), \
                     patch.object(os, "replace", side_effect=race), self.assertRaises(saver.SaveWriterError) as error:
                    saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5})
                self.assertFalse(extra.exists())
                self.assertIn(str(target), str(error.exception))
                if collision:
                    self.assertEqual(target.read_bytes(), b"later file")
                    saved = list(directory.glob(".2k5-save-*/original/unverified-*"))
                    self.assertEqual([file.read_bytes() for file in saved], [b"foreign content"])
                    self.assertIn(str(saved[0]), str(error.exception))
                else:
                    self.assertEqual(target.read_bytes(), b"foreign content")
                    self.assertEqual(list(directory.glob(".2k5-save-*")), [])

    def test_restore_io_error_identifies_the_original_and_restores_the_other_member(self) -> None:
        directory = self.save.parent.parent / "older"
        directory.mkdir()
        target, extra = directory / "SAVEGAME.DAT", directory / "EXTRA"
        target.write_bytes(b"old game")
        extra.write_bytes(b"old signature")
        publish = platform_compat.publish_no_replace

        def fail_restoring_file(staged, destination, **kwargs):
            if staged.name == "original" and destination == target:
                raise OSError(errno.EIO, "drive disconnected")
            return publish(staged, destination, **kwargs)

        with patch.object(saver, "_verify_published", side_effect=OSError("failed readback")), \
             patch.object(platform_compat, "publish_no_replace", side_effect=fail_restoring_file), \
             self.assertRaises(saver.SaveWriterError) as error:
            saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5}, overwrite=True)
        self.assertFalse(target.exists())
        self.assertEqual(extra.read_bytes(), b"old signature")
        backups = list(directory.glob(".2k5-save-*/original"))
        self.assertEqual([file.read_bytes() for file in backups], [b"old game"])
        self.assertIn(str(backups[0]), str(error.exception))
        self.assertIn(str(target), str(error.exception))
        self.assertIn("drive disconnected", str(error.exception))

    def test_directory_cleanup_failure_keeps_the_original_recovery_message(self) -> None:
        directory = self.save.parent.parent / "new copy"
        target, extra = directory / "SAVEGAME.DAT", directory / "EXTRA"
        arriving = self.save.parent.parent / "incoming"
        arriving.write_bytes(b"foreign file")
        move, rmdir = os.replace, os.rmdir
        def two_replacements(source, destination):
            if source == target:
                move(arriving, target)
            move(source, destination)
            if source == target:
                target.write_bytes(b"later file")
        def refuse_rmdir(path, *args, **kwargs):
            if path == directory:
                raise PermissionError(errno.EACCES, "cleanup refused")
            return rmdir(path, *args, **kwargs)

        with patch.object(saver, "_verify_published", side_effect=OSError("readback failed")), \
             patch.object(os, "replace", side_effect=two_replacements), \
             patch.object(os, "rmdir", side_effect=refuse_rmdir), self.assertRaises(saver.SaveWriterError) as failure:
            saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5})
        self.assertEqual(target.read_bytes(), b"later file")
        self.assertFalse(extra.exists())
        held = self.save.parent.parent.rglob(".2k5-save-*/original/unverified-*")
        saved, = (item for item in held if item.read_bytes() == b"foreign file")
        for detail in (str(saved), str(directory), "readback failed", "cleanup refused"):
            self.assertIn(detail, str(failure.exception))

    def test_interrupting_rollback_preserves_the_actual_file_captured_at_the_rename(self) -> None:
        target = self.save.parent.parent / "new copy" / "SAVEGAME.DAT"
        incoming = self.save.parent.parent / "foreign"
        incoming.write_bytes(b"concurrent edit")
        move = os.replace
        def interrupt_after_move(source, destination):
            if source == target:
                move(incoming, target)
            move(source, destination)
            if source == target:
                raise KeyboardInterrupt()

        with patch.object(saver, "_verify_published", side_effect=OSError("readback failed")), \
             patch.object(os, "replace", side_effect=interrupt_after_move), self.assertRaises(KeyboardInterrupt):
            saver.edit_save_file(self.save, target, target.with_name("EXTRA"), xbe_path=self.xbe, sliders={"Injury": 0.5})
        marks = list(self.save.parent.parent.rglob(".2k5-studio-recovery"))
        self.assertTrue(marks)
        held = [p for mark in marks for p in mark.parent.rglob("unverified-*")]
        self.assertIn(b"concurrent edit", [p.read_bytes() for p in held])

    @unittest.skipIf(platform_compat.IS_WINDOWS, "the POSIX publication fallback uses a hard link")
    def test_linked_second_member_is_withdrawn_if_removing_its_staging_name_fails(self) -> None:
        target = self.save.parent.parent / "copy" / "SAVEGAME.DAT"
        extra = target.with_name("EXTRA")
        unlink = os.unlink
        def fail_after_link(path, *args, **kwargs):
            item = Path(path)
            if item.name == "new" and extra.exists() and platform_compat.paths_alias(item, extra):
                raise OSError(errno.EIO, "staging unlink failed")
            return unlink(path, *args, **kwargs)

        with patch.object(platform_compat, "_linux_renameat2", return_value=None), \
             patch.object(platform_compat, "_macos_renameatx_np", return_value=None):
            with patch.object(os, "unlink", side_effect=fail_after_link), self.assertRaisesRegex(OSError, "staging unlink"):
                saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5})
            self.assertFalse(target.parent.exists())
            saver.edit_save_file(self.save, target, extra, xbe_path=self.xbe, sliders={"Injury": 0.5})
        self.assertTrue(saver.verify_extra(saver.derive_sig_key(self.xbe.read_bytes()), target.read_bytes(), extra.read_bytes()))


class Ps2CopyOnVolumesWithoutHardLinks(unittest.TestCase):
    """The PS2 writer falls back to an exclusive write when the volume cannot link or rename without replacing. Its errno
    list names EOPNOTSUPP but not ENOTSUP. They are the same number on Linux (95) and different on macOS (ENOTSUP 45,
    EOPNOTSUPP 102), and macOS exFAT, FAT and SMB volumes answer link() with ENOTSUP."""

    def test_every_unsupported_errno_takes_the_verified_fallback(self) -> None:
        from mod_editor.core import ps2_save_service as service
        from mod_editor.core.ps2_save_service import Ps2SaveService

        save_lib = service.save_lib
        unsupported = {errno.ENOSYS, errno.EOPNOTSUPP, errno.EPERM, getattr(errno, "ENOTSUP", errno.EOPNOTSUPP)}
        for code in sorted(unsupported):
            with self.subTest(errno=errno.errorcode.get(code, code)), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                save_lib.write_psu(save_lib._synthetic_save(), root / "source.psu")
                editor = Ps2SaveService()
                editor.open(root / "source.psu")
                editor.set_name(0, "first", "Delta")

                def no_link(_staged, _output, code=code):
                    raise OSError(code, os.strerror(code))

                with patch.object(service, "publish_no_replace", no_link):
                    result = editor.write(root / "copy.psu")
                self.assertTrue(result.verified, result.detail)
                self.assertTrue((root / "copy.psu").is_file())
                self.assertEqual(list(root.glob(".studio-ps2-*")), [])


class BuildTabDiscKeepsItsXemuCheck(unittest.TestCase):
    """E08 sibling: beta 81 passes each finished disc's console target to Play latest disc, and an unknown target
    skips the xemu settings check. A Build-tab receipt stores plan.to_recipe(), which omits console_memory when it is
    128, so reading the key directly turned every standard 128 MB build into an unknown disc. Beta 80 checked 128 MiB
    and Complex 4627 before every launch."""

    def registered_memory(self, plan) -> object:
        from types import SimpleNamespace
        from mod_editor.gui.studio_qt import StudioMainWindow

        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "built.xiso.iso"
            target.write_bytes(b"disc")
            seen = {}
            host = SimpleNamespace(
                facade=SimpleNamespace(register_external_build=lambda path, console_memory=None:
                                       seen.update(memory=console_memory)),
                _set_status=lambda *_: None, _refresh_action_states=lambda: None)
            receipt = {"target": str(target), "source": str(Path(folder) / "retail.iso"),
                       "outcome": {"status": "changed"}, "plan": plan.to_recipe()}
            StudioMainWindow._on_build_tab_built(host, receipt)
        return seen["memory"]

    def test_standard_and_64_mb_build_tab_discs_register_their_targets(self) -> None:
        from mod_editor.core import mod_build

        standard = mod_build.BuildPlan("retail.iso", "built.iso", k128_memory=True)
        self.assertNotIn("console_memory", standard.to_recipe())
        self.assertEqual(self.registered_memory(standard), 128)
        compact = mod_build.BuildPlan("retail.iso", "built.iso", console_memory=64)
        self.assertEqual(self.registered_memory(compact), 64)

    def test_unknown_target_skips_the_check_that_a_128_target_makes(self) -> None:
        from mod_editor.studio import xemu_settings

        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "xemu.toml"
            config.write_text("[sys]\nmem_limit = '64'\n", encoding="utf-8", newline="\n")
            self.assertEqual(xemu_settings.play_warning(config, target_mb=None), "")
            self.assertIn("128 MiB", xemu_settings.play_warning(config, target_mb=128))


if __name__ == "__main__":
    unittest.main()
