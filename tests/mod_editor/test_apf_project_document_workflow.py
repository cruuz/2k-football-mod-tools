"""Protected fast-save and active-document behavior for APF Mod Studio."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import sip  # noqa: E402
from PyQt5.QtGui import QCloseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.apf_studio.facade import ApfStudioFacade  # noqa: E402
from mod_editor.apf_studio.gui import (  # noqa: E402
    ApfStudioMainWindow,
    _BackgroundTask,
)
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    PagedModel,
    _row,
)
from mod_editor.apf_studio.models import ApfCategory  # noqa: E402
from mod_editor.apf_studio.project import (  # noqa: E402
    ProjectError,
    ProjectTargetIdentity,
    project_target_identity,
    save_project,
)
from mod_editor.gui.apf_audio_waveform_qt import WaveformRequest  # noqa: E402


SOURCE_SHA256 = "d" * 64


def _save_empty(
    destination: Path,
    *,
    replace: bool = False,
    expected_target: ProjectTargetIdentity | None = None,
) -> Path:
    return save_project(
        destination,
        source_sha256=SOURCE_SHA256,
        modifications=(),
        replace=replace,
        expected_target=expected_target,
    )


def _temporary_files(destination: Path) -> list[Path]:
    return list(destination.parent.glob(f".{destination.name}.*.tmp"))


class ApfProjectTargetSafetyTests(unittest.TestCase):
    def test_fast_save_uses_one_exact_identity_and_refreshes_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-fast-save-") as temporary:
            root = Path(temporary)
            project = _save_empty(root / "Named APF Mod.apf2k8mod")
            first = project_target_identity(project)

            self.assertEqual(
                _save_empty(project, replace=True, expected_target=first),
                project,
            )
            second = project_target_identity(project)
            self.assertNotEqual(first, second)
            published = project.read_bytes()

            with self.assertRaisesRegex(ProjectError, "changed outside"):
                _save_empty(project, replace=True, expected_target=first)
            self.assertEqual(project.read_bytes(), published)

            foreign = b"externally changed project bytes"
            project.write_bytes(foreign)
            with self.assertRaisesRegex(ProjectError, "changed outside"):
                _save_empty(project, replace=True, expected_target=second)
            self.assertEqual(project.read_bytes(), foreign)
            self.assertEqual(_temporary_files(project), [])

    def test_missing_linked_nonregular_and_substituted_targets_fail_closed(self) -> None:
        cases = ("missing", "symlink", "hardlink", "directory", "substitution")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=f"apf-fast-save-{case}-"
            ) as temporary:
                root = Path(temporary)
                project = _save_empty(root / "Active.apf2k8mod")
                identity = project_target_identity(project)
                original = project.read_bytes()
                victim = root / "foreign-user-file"
                victim.write_bytes(b"keep this foreign file")
                parked = root / "parked-original.apf2k8mod"
                linked: Path | None = None

                if case == "missing":
                    project.unlink()
                elif case == "symlink":
                    project.unlink()
                    project.symlink_to(victim)
                elif case == "hardlink":
                    linked = root / "second-name.apf2k8mod"
                    os.link(project, linked)
                elif case == "directory":
                    project.unlink()
                    project.mkdir()
                else:
                    os.replace(project, parked)
                    project.write_bytes(b"substituted foreign project")

                with self.assertRaisesRegex(ProjectError, "Save Project As|changed"):
                    _save_empty(project, replace=True, expected_target=identity)

                self.assertEqual(victim.read_bytes(), b"keep this foreign file")
                if case == "missing":
                    self.assertFalse(project.exists())
                elif case == "symlink":
                    self.assertTrue(project.is_symlink())
                    self.assertEqual(project.resolve().read_bytes(), victim.read_bytes())
                elif case == "hardlink":
                    assert linked is not None
                    self.assertEqual(project.read_bytes(), original)
                    self.assertEqual(linked.read_bytes(), original)
                elif case == "directory":
                    self.assertTrue(project.is_dir())
                else:
                    self.assertEqual(project.read_bytes(), b"substituted foreign project")
                    self.assertEqual(parked.read_bytes(), original)
                self.assertEqual(_temporary_files(project), [])

    def test_save_as_never_replaces_an_unsafe_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-save-as-target-") as temporary:
            root = Path(temporary)
            victim = root / "user-file"
            victim.write_bytes(b"do not touch")
            linked = root / "Linked.apf2k8mod"
            linked.symlink_to(victim)

            with self.assertRaisesRegex(ProjectError, "regular, non-linked"):
                _save_empty(linked, replace=True)
            self.assertTrue(linked.is_symlink())
            self.assertEqual(victim.read_bytes(), b"do not touch")
            self.assertEqual(_temporary_files(linked), [])


class ApfProjectLoadTransactionTests(unittest.TestCase):
    @staticmethod
    def _identity(path: Path, inode: int) -> ProjectTargetIdentity:
        return ProjectTargetIdentity(path, 1, inode, 100, 200, 300)

    def test_project_load_commits_only_after_stable_pre_and_post_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-load-identity-") as temporary:
            root = Path(temporary)
            path = root / "Loaded.apf2k8mod"
            path.write_bytes(b"fixture")
            canonical = path.resolve()
            opened = self._identity(canonical, 1)
            changed = self._identity(canonical, 2)

            facade = ApfStudioFacade(cache_root=root / "cache")
            facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
            facade.catalog = object()  # type: ignore[assignment]
            active = mock.Mock()
            facade.session = active
            candidate = mock.Mock()
            candidate.load_project.return_value = 3

            with mock.patch(
                "mod_editor.apf_studio.facade.ApfSession", return_value=candidate
            ), mock.patch(
                "mod_editor.apf_studio.facade.project_target_identity",
                side_effect=(opened, changed),
            ):
                with self.assertRaisesRegex(ProjectError, "current workspace was kept"):
                    facade.load_project(path)
            self.assertIs(facade.session, active)
            active.close.assert_not_called()
            candidate.close.assert_called_once()

            candidate = mock.Mock()
            candidate.load_project.return_value = 2
            with mock.patch(
                "mod_editor.apf_studio.facade.ApfSession", return_value=candidate
            ), mock.patch(
                "mod_editor.apf_studio.facade.project_target_identity",
                side_effect=(opened, opened),
            ):
                self.assertEqual(facade.load_project(path), 2)
            self.assertIs(facade.session, candidate)
            active.close.assert_called_once()
            candidate.close.assert_not_called()
            self.assertEqual(facade.last_project_identity, opened)


class _FakeFacade:
    def __init__(self) -> None:
        self.source_ready = False
        self.source_display_name = "Synthetic APF 2K8"
        self.source = None
        self.modified_count = 0
        self.can_undo = False
        self.last_build = None
        self.last_project_identity: ProjectTargetIdentity | None = None
        self.launcher = SimpleNamespace(settings=SimpleNamespace(configured=False))
        self.can_launch_xenia = False
        # Launch names its single blocker instead of graying out.
        self.xenia_blocker = "Build a modded game folder first."
        self.save_calls: list[dict[str, object]] = []
        self.close_calls = 0
        self._inspectors = object()
        self._catalog = SimpleNamespace(outer_count=0, assets=(), uniform_assets=())

    def require_catalog(self) -> object:
        return self._catalog

    def require_inspectors(self) -> object:
        return self._inspectors

    def save_project(
        self,
        destination: Path,
        _progress: object,
        *,
        replace: bool = False,
        expected_target: ProjectTargetIdentity | None = None,
    ) -> Path:
        path = _save_empty(
            destination,
            replace=replace,
            expected_target=expected_target,
        )
        self.last_project_identity = project_target_identity(path)
        self.save_calls.append(
            {
                "path": path,
                "replace": replace,
                "expected_target": expected_target,
            }
        )
        return path

    def close(self) -> None:
        self.close_calls += 1


class ApfActiveProjectWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.facade = _FakeFacade()
        self.window = ApfStudioMainWindow(self.facade)  # type: ignore[arg-type]
        self.facade.source_ready = True

        def immediate(
            _label: str,
            operation: object,
            on_success: object | None = None,
            _blocking: bool = True,
        ) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            if on_success is not None:
                on_success(result)  # type: ignore[operator]

        self.window._run_task = immediate  # type: ignore[method-assign]
        self.window._update_product_state()

    def tearDown(self) -> None:
        self.window._allow_close = True
        self.window.close()
        self.application.processEvents()
        if not sip.isdeleted(self.window):
            sip.delete(self.window)

    def _first_save(self, destination: Path) -> None:
        self.window._mark_document_changed()
        with mock.patch(
            "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
            return_value=(
                str(destination),
                "APF 2K8 Mod Studio project (*.apf2k8mod)",
            ),
        ), mock.patch("mod_editor.apf_studio.gui.QMessageBox.information"):
            self.window._save_project()

    def test_unnamed_save_as_then_named_fast_save_has_document_titles(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-window-document-") as temporary:
            project = Path(temporary) / "My Active Mod.apf2k8mod"
            self.window._mark_document_changed()
            self.assertEqual(
                self.window.windowTitle(),
                "Untitled* — APF 2K8 Mod Studio",
            )
            self.assertTrue(self.window.save_project_button.isEnabled())
            save_action = self.window._save_project_action
            save_as_action = self.window._save_project_as_action
            self.assertIsNotNone(save_action)
            self.assertIsNotNone(save_as_action)
            assert save_action is not None and save_as_action is not None
            self.assertEqual(
                save_action.shortcut().toString(),
                "Ctrl+S",
            )
            self.assertEqual(
                save_as_action.shortcut().toString(),
                "Ctrl+Shift+S",
            )

            with mock.patch(
                "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                return_value=(
                    str(project),
                    "APF 2K8 Mod Studio project (*.apf2k8mod)",
                ),
            ) as choose, mock.patch(
                "mod_editor.apf_studio.gui.QMessageBox.information"
            ):
                self.window._save_project()
            choose.assert_called_once()
            self.assertEqual(self.window._active_project_path, project.resolve())
            self.assertFalse(self.window._document_dirty)
            self.assertEqual(
                self.window.windowTitle(),
                "My Active Mod.apf2k8mod — APF 2K8 Mod Studio",
            )
            self.assertFalse(self.window.save_project_button.isEnabled())

            remembered = self.window._active_project_identity
            self.window._mark_document_changed()
            self.assertEqual(
                self.window.windowTitle(),
                "My Active Mod.apf2k8mod* — APF 2K8 Mod Studio",
            )
            with mock.patch(
                "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName"
            ) as choose_again:
                self.window._save_project()
            choose_again.assert_not_called()
            self.assertIs(self.facade.save_calls[-1]["expected_target"], remembered)
            self.assertTrue(self.facade.save_calls[-1]["replace"])
            self.assertNotEqual(self.window._active_project_identity, remembered)
            self.assertFalse(self.window._document_dirty)

    def test_dirty_zero_edit_document_saves_and_clean_project_can_save_as(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-zero-document-") as temporary:
            root = Path(temporary)
            project = root / "Zero Edit Mod.apf2k8mod"
            self._first_save(project)
            self.assertFalse(self.window.save_project_button.isEnabled())
            save_as_action = self.window._save_project_as_action
            self.assertIsNotNone(save_as_action)
            assert save_as_action is not None
            self.assertTrue(save_as_action.isEnabled())

            self.facade.modified_count = 0
            self.window._mark_document_changed()
            self.assertEqual(self.window.modified_count.text(), "0 edits • unsaved")
            self.assertTrue(self.window.save_project_button.isEnabled())
            self.window._save_project()
            with zipfile.ZipFile(project) as archive:
                manifest = json.loads(archive.read("project.json"))
            self.assertEqual(manifest["replacement_count"], 0)
            self.assertFalse(self.window._document_dirty)

            copied = root / "Copied Clean Mod.apf2k8mod"
            with mock.patch(
                "mod_editor.apf_studio.gui.QFileDialog.getSaveFileName",
                return_value=(str(copied), "project"),
            ), mock.patch("mod_editor.apf_studio.gui.QMessageBox.information"):
                self.window._choose_save_project_as()
            self.assertEqual(self.window._active_project_path, copied.resolve())
            self.assertFalse(self.window._document_dirty)

    def test_audio_shortlist_navigation_never_marks_the_project_dirty(self) -> None:
        self.window._document_dirty = False
        audio_page = self.window._pages[ApfCategory.AUDIO]
        browser = audio_page.inspector  # type: ignore[attr-defined]
        identity = ExportIdentity("audo", 5, 1, None, "menu-back")
        row = _row(
            "audo:1",
            "audo",
            "menu_back",
            "AUDIO",
            {
                "outer_table_index": 5,
                "inner_file_index": 1,
                "audio_source_id": "audo:standalone",
                "audio_source_label": "Standalone AUDO",
                "role_id": "ui_menu_sfx",
                "role_label": "UI & Menu SFX",
                "audio_format": "XMA1",
            },
            export_identity=identity,
        )
        browser.set_model(PagedModel((row,)), "fixture")
        browser._toggle_audio_shortlist()
        browser.search.setText("menu")
        browser.refresh()
        self.assertEqual(len(browser._shortlisted_audio_rows()), 1)
        self.assertFalse(self.window._document_dirty)

    def test_post_save_continuation_waits_until_worker_cleanup(self) -> None:
        called: list[str] = []
        worker = _BackgroundTask(lambda _progress: None)
        self.window._workers.add(worker)
        self.window._blocking_workers.add(worker)
        self.window._run_when_idle(lambda: called.append("continued"))
        self.assertEqual(called, [])
        self.window._task_finished(worker)
        self.assertNotIn(worker, self.window._workers)
        self.application.processEvents()
        self.assertEqual(called, ["continued"])

    def test_close_cancels_and_drains_nonblocking_waveform_before_session_close(
        self,
    ) -> None:
        audio_page = self.window._pages[ApfCategory.AUDIO]
        browser = audio_page.inspector  # type: ignore[attr-defined]
        request = WaveformRequest()
        browser._waveform_request = request
        worker = _BackgroundTask(lambda _progress: None)
        self.window._workers.add(worker)

        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(request.cancelled)
        self.assertTrue(self.window._close_when_workers_finish)
        self.assertEqual(self.facade.close_calls, 0)

        self.window._task_finished(worker)
        self.application.processEvents()
        self.application.processEvents()
        self.assertEqual(self.facade.close_calls, 1)

    def test_blocking_close_stays_modal_while_waveform_cancels(self) -> None:
        audio_page = self.window._pages[ApfCategory.AUDIO]
        browser = audio_page.inspector  # type: ignore[attr-defined]
        request = WaveformRequest()
        browser._waveform_request = request
        worker = _BackgroundTask(lambda _progress: None)
        self.window._workers.add(worker)
        self.window._blocking_workers.add(worker)

        event = QCloseEvent()
        with mock.patch(
            "mod_editor.apf_studio.gui.QMessageBox.information"
        ) as information:
            self.window.closeEvent(event)

        self.assertFalse(event.isAccepted())
        self.assertTrue(request.cancelled)
        self.assertFalse(self.window._close_when_workers_finish)
        self.assertEqual(self.facade.close_calls, 0)
        self.assertIn("finish before closing", information.call_args.args[2])

    def test_source_switch_cancels_waveform_then_resumes_once_after_worker_drain(
        self,
    ) -> None:
        audio_page = self.window._pages[ApfCategory.AUDIO]
        browser = audio_page.inspector  # type: ignore[attr-defined]
        request = WaveformRequest()
        browser._waveform_request = request
        worker = _BackgroundTask(lambda _progress: None)
        self.window._workers.add(worker)
        admitted: list[tuple[str, bool]] = []

        def record_task(
            label: str,
            _operation: object,
            _on_success: object = None,
            blocking: bool = True,
        ) -> bool:
            admitted.append((label, blocking))
            return True

        self.window._run_task = record_task  # type: ignore[method-assign]
        selected = Path("/tmp/next-apf-source")
        self.window._load_source_path(selected)
        self.assertTrue(request.cancelled)
        self.assertEqual(admitted, [])
        self.assertIsNotNone(self.window._pending_source_load)

        self.window._task_finished(worker)
        self.application.processEvents()
        self.assertEqual(
            admitted,
            [("Recognizing and indexing your APF game", True)],
        )
        self.assertIsNone(self.window._pending_source_load)
        self.assertFalse(self.window._source_load_resume_queued)

    def test_rapid_source_switches_coalesce_to_latest_request_while_draining(
        self,
    ) -> None:
        audio_page = self.window._pages[ApfCategory.AUDIO]
        browser = audio_page.inspector  # type: ignore[attr-defined]
        request = WaveformRequest()
        browser._waveform_request = request
        worker = _BackgroundTask(lambda _progress: None)
        self.window._workers.add(worker)
        loaded: list[Path] = []
        admitted: list[str] = []

        self.facade.load_source = (  # type: ignore[attr-defined]
            lambda selected, _progress: loaded.append(selected)
        )

        def record_task(
            label: str,
            operation: object,
            _on_success: object = None,
            _blocking: bool = True,
        ) -> bool:
            admitted.append(label)
            operation(lambda *_args: None)  # type: ignore[operator]
            return True

        self.window._run_task = record_task  # type: ignore[method-assign]
        first = Path("/tmp/first-apf-source")
        latest = Path("/tmp/latest-apf-source")
        self.window._load_source_path(first)
        self.window._load_source_path(latest)

        self.assertTrue(request.cancelled)
        self.assertEqual(admitted, [])
        self.assertEqual(self.window._pending_source_load[0], latest)  # type: ignore[index]
        self.assertEqual(len(self.window._idle_callbacks), 1)

        self.window._task_finished(worker)
        self.application.processEvents()
        self.assertEqual(
            admitted,
            ["Recognizing and indexing your APF game"],
        )
        self.assertEqual(loaded, [latest])
        self.assertIsNone(self.window._pending_source_load)
        self.assertFalse(self.window._source_load_resume_queued)

    def test_source_switch_and_close_gate_use_dirty_state(self) -> None:
        self.window._mark_document_changed()
        path = Path("/tmp/fixture-apf-source")
        started: list[Path] = []
        self.window._load_source_path = started.append  # type: ignore[method-assign]

        with mock.patch.object(
            self.window, "_prompt_unsaved_decision", return_value="cancel"
        ):
            self.window.load_source_path(path)
        self.assertEqual(started, [])
        self.assertTrue(self.window._document_dirty)

        with mock.patch.object(
            self.window, "_prompt_unsaved_decision", return_value="discard"
        ):
            self.window.load_source_path(path)
        self.assertEqual(started, [path])
        self.assertTrue(self.window._document_dirty)

        cancel_event = QCloseEvent()
        with mock.patch.object(
            self.window, "_prompt_unsaved_decision", return_value="cancel"
        ):
            self.window.closeEvent(cancel_event)
        self.assertFalse(cancel_event.isAccepted())
        self.assertEqual(self.facade.close_calls, 0)

        discard_event = QCloseEvent()
        with mock.patch.object(
            self.window, "_prompt_unsaved_decision", return_value="discard"
        ):
            self.window.closeEvent(discard_event)
        self.assertTrue(discard_event.isAccepted())
        self.assertEqual(self.facade.close_calls, 1)


if __name__ == "__main__":
    unittest.main()
