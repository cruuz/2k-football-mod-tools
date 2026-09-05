"""Headless integration fences between 2K5 Audio and the project shell."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QCloseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton  # noqa: E402

from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.nfl2k5_audio_catalog import Nfl2k5AudioService  # noqa: E402
from mod_editor.gui.audio_panel_qt import (  # noqa: E402
    AudioPanel,
    CatalogAudioPanelHost,
)
from mod_editor.gui.audio_waveform_qt import WaveformEnvelope  # noqa: E402
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow  # noqa: E402
from mod_editor.studio.project_archive import project_target_identity  # noqa: E402
from mod_editor.studio.workspace_state import RecoveryCandidate  # noqa: E402
from tests.mod_editor.test_nfl2k5_audio_catalog import AudioFixture  # noqa: E402


class AudioPanelOperationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _panel(self, root: Path) -> AudioPanel:
        source_root = root / "source"
        source_root.mkdir()
        fixture = AudioFixture(source_root)
        service = Nfl2k5AudioService(fixture.cache, fixture.catalog())
        return AudioPanel(
            CatalogAudioPanelHost(
                fixture.catalog(),
                service,
                root / "replacements",
            ),
            page_size=2,
        )

    def test_operation_signal_has_exact_true_false_edges_and_read_only_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            panel = self._panel(Path(directory))
            captured: list[object] = []
            results: list[object] = []
            edges: list[tuple[bool, bool]] = []
            panel._pool = SimpleNamespace(  # type: ignore[assignment]
                start=lambda task: captured.append(task)
            )
            panel.operation_state_changed.connect(
                lambda busy: edges.append((busy, panel.operation_in_progress))
            )
            try:
                panel._run(
                    lambda progress: (
                        progress("Synthetic Audio read", 1, 1),
                        "finished",
                    )[1],
                    results.append,
                )
                self.assertTrue(panel.operation_in_progress)
                self.assertEqual(edges, [(True, True)])
                self.assertEqual(len(captured), 1)

                # The single panel lane refuses a second operation without a
                # duplicate true edge.
                panel._run(lambda _progress: "second", results.append)
                self.assertEqual(edges, [(True, True)])
                self.assertEqual(len(captured), 1)

                captured[0].run()  # type: ignore[attr-defined]
                self.application.processEvents()
                self.assertFalse(panel.operation_in_progress)
                self.assertEqual(edges, [(True, True), (False, False)])
                self.assertEqual(results, ["finished"])
                with self.assertRaises(AttributeError):
                    panel.operation_in_progress = True  # type: ignore[misc]
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_public_content_invalidation_clears_same_id_playback_and_waveform(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            panel = self._panel(Path(directory))
            try:
                asset_id = panel.selected_asset_id
                self.assertIsNotNone(asset_id)
                envelope = WaveformEnvelope(
                    sample_rate=48_000,
                    frame_count=960,
                    channel_peaks=((( -0.5, 0.75), ( -0.25, 0.5)),),
                    sampled_frame_count=2,
                )
                panel.waveform_preview.set_envelope(envelope)
                panel._waveform_selected_asset_id = asset_id
                panel._preview_epoch += 1
                playback = (panel._preview_epoch, str(asset_id))
                panel._preview_request = playback
                panel._playing_preview_request = playback
                panel.play_button.setText("Stop")

                panel.invalidate_audio_content()

                self.assertEqual(panel.selected_asset_id, asset_id)
                self.assertIsNone(panel._preview_request)
                self.assertIsNone(panel._playing_preview_request)
                self.assertEqual(panel.play_button.text(), "Play")
                self.assertIsNone(panel.waveform_preview.envelope)
                self.assertEqual(panel.waveform_preview.state, "empty")
                self.assertEqual(panel.load_waveform_button.text(), "Load waveform")
                self.assertTrue(panel.load_waveform_button.isEnabled())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_busy_worker_makes_catalog_and_every_non_cancel_button_inert(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            panel = self._panel(Path(directory))
            captured: list[object] = []
            refresh_calls: list[str] = []
            panel._pool = SimpleNamespace(  # type: ignore[assignment]
                start=lambda task: captured.append(task)
            )
            try:
                panel._run(lambda _progress: "done", lambda _value: None)
                self.assertTrue(panel.operation_in_progress)
                for control in (
                    panel.search,
                    panel.scope_filter,
                    panel.family_filter,
                    panel.status_filter,
                    panel.meaning_filter,
                    panel.table,
                    panel.previous_button,
                    panel.next_button,
                ):
                    self.assertFalse(control.isEnabled())
                self.assertTrue(
                    all(
                        not button.isEnabled()
                        for button in panel.findChildren(QPushButton)
                    )
                )

                panel.refresh = (  # type: ignore[method-assign]
                    lambda **_kwargs: refresh_calls.append("refresh")
                )
                panel._scope_changed()
                panel._filters_changed()
                panel._search_text_changed("blocked")
                panel._selection_changed()
                panel._previous_page()
                panel._next_page()
                panel._show_soundtrack()
                self.assertEqual(refresh_calls, [])
                self.assertFalse(panel._search_timer.isActive())

                captured[0].run()  # type: ignore[attr-defined]
                self.application.processEvents()
                self.assertFalse(panel.operation_in_progress)
                self.assertTrue(panel.search.isEnabled())
                self.assertTrue(panel.table.isEnabled())
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_actual_waveform_busy_keeps_only_cancel_button_reachable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel = self._panel(root)
            captured: list[object] = []
            private_wav = root / "waveform.wav"
            import wave
            from array import array

            with wave.open(str(private_wav), "wb") as writer:
                writer.setnchannels(1)
                writer.setsampwidth(2)
                writer.setframerate(48_000)
                writer.writeframes(array("h", [-1000, 1000] * 64).tobytes())
            panel.host.prepare_audio = (  # type: ignore[method-assign]
                lambda _asset_id, _progress: private_wav
            )
            panel._pool = SimpleNamespace(  # type: ignore[assignment]
                start=lambda task: captured.append(task)
            )
            try:
                panel.load_waveform_button.click()
                self.assertTrue(panel.operation_in_progress)
                self.assertEqual(panel.load_waveform_button.text(), "Cancel waveform")
                self.assertTrue(panel.load_waveform_button.isEnabled())
                self.assertTrue(
                    all(
                        not button.isEnabled()
                        for button in panel.findChildren(QPushButton)
                        if button is not panel.load_waveform_button
                    )
                )
                self.assertFalse(panel.table.isEnabled())
                panel.load_waveform_button.click()
                self.assertEqual(panel.load_waveform_button.text(), "Cancelling…")
                self.assertFalse(panel.load_waveform_button.isEnabled())

                captured[0].run()  # type: ignore[attr-defined]
                self.application.processEvents()
                self.assertFalse(panel.operation_in_progress)
                self.assertEqual(panel.load_waveform_button.text(), "Load waveform")
            finally:
                panel.deleteLater()
                self.application.processEvents()


class StudioAudioOperationFenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.facade = BrowseOnlyFacade()
        self.window = StudioMainWindow(
            facade=self.facade,
            workspace_store=None,
            offer_recovery=False,
        )
        self.application.processEvents()
        self.facade.source_ready = True
        self.facade.source_display_name = "Synthetic NFL 2K5"
        self.facade.modified_count = 1
        self.facade.can_undo = True
        self.facade.can_launch_xemu = True
        self.window._workspace_dirty = True
        self.assertIsNotNone(self.window._selected_asset)
        selected_id = self.window._selected_asset.asset_id
        self.facade.modified_asset_ids = frozenset((selected_id,))
        self.window._refresh_edit_state()
        self.audio = self.window._audio_panel
        self.assertIsNotNone(self.audio)
        self.audio_tasks: list[object] = []
        self.audio._pool = SimpleNamespace(  # type: ignore[assignment]
            start=lambda task: self.audio_tasks.append(task)
        )
        self.crib = self.window._crib_panel
        self.assertIsNotNone(self.crib)
        self.crib_tasks: list[object] = []
        self.crib._pool = SimpleNamespace(  # type: ignore[assignment]
            start=lambda task: self.crib_tasks.append(task)
        )

    def tearDown(self) -> None:
        for task in self.audio_tasks:
            if self.audio.operation_in_progress:
                task.run()  # type: ignore[attr-defined]
                self.application.processEvents()
        for task in self.crib_tasks:
            if self.crib.operation_in_progress:
                task.run()  # type: ignore[attr-defined]
                self.application.processEvents()
        self.window.deleteLater()
        self.application.processEvents()

    def _begin_audio_operation(self) -> object:
        self.audio._run(
            lambda _progress: "audio finished",
            lambda _result: None,
        )
        self.assertEqual(len(self.audio_tasks), 1)
        return self.audio_tasks[0]

    def test_audio_busy_disables_global_actions_but_keeps_cancel_route_reachable(
        self,
    ) -> None:
        task = self._begin_audio_operation()

        self.assertTrue(self.window._embedded_audio_busy)
        self.assertTrue(self.audio.operation_in_progress)
        self.assertTrue(self.audio.isEnabled())
        self.assertFalse(self.window.navigation.isEnabled())
        self.assertFalse(self.crib.isEnabled())
        self.assertFalse(self.window._text_roster_panel.isEnabled())
        self.assertFalse(self.window._roster_panel.isEnabled())
        for control in (
            self.window.open_source_button,
            self.window.open_project_button,
            self.window.save_project_button,
            self.window.undo_button,
            self.window.revert_all_button,
            self.window.build_button,
            self.window.launch_button,
            self.window.revert_button,
        ):
            self.assertFalse(control.isEnabled(), control.objectName())
        for action in (
            self.window._open_source_action,
            self.window._open_project_action,
            self.window._save_project_action,
            self.window._save_project_as_action,
        ):
            self.assertIsNotNone(action)
            self.assertFalse(action.isEnabled())
        self.assertIn("Cancel waveform", self.window.operation_status.text())

        task.run()  # type: ignore[attr-defined]
        self.application.processEvents()
        self.assertFalse(self.window._embedded_audio_busy)
        self.assertFalse(self.audio.operation_in_progress)
        self.assertTrue(self.window.navigation.isEnabled())
        self.assertTrue(self.crib.isEnabled())
        self.assertTrue(self.window._text_roster_panel.isEnabled())
        self.assertTrue(self.window._roster_panel.isEnabled())
        self.assertTrue(self.window.open_source_button.isEnabled())
        self.assertTrue(self.window.open_project_button.isEnabled())
        self.assertTrue(self.window.save_project_button.isEnabled())
        self.assertTrue(self.window.build_button.isEnabled())

    def test_every_direct_global_route_and_central_admission_refuse_while_busy(
        self,
    ) -> None:
        self._begin_audio_operation()
        starts: list[str] = []
        continuations: list[str] = []
        invalidations: list[str] = []
        original_start_task = self.window._start_task
        self.window._start_task = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: starts.append("start")
        )
        self.window._continue_after_unsaved = (  # type: ignore[method-assign]
            lambda context, _action: continuations.append(context)
        )
        self.audio.invalidate_audio_content = (  # type: ignore[method-assign]
            lambda: invalidations.append("invalidate")
        )
        with patch(
            "mod_editor.gui.studio_qt.QMessageBox.information"
        ) as information, patch(
            "mod_editor.gui.studio_qt.QMessageBox.question"
        ) as question, patch(
            "mod_editor.gui.studio_qt.QFileDialog.getOpenFileName"
        ) as open_file, patch(
            "mod_editor.gui.studio_qt.QFileDialog.getSaveFileName"
        ) as save_file:
            self.window._choose_source()
            self.window._request_source_switch(Path("/fixture/source.xiso"))
            self.window._load_source_path(Path("/fixture/source.xiso"))
            self.window._choose_project()
            self.window._request_project_load(Path("/fixture/mod.2k5mod"))
            self.window._load_project_path(Path("/fixture/mod.2k5mod"))
            self.window._save_project()
            self.window._choose_save_project_as()
            self.window._save_project_path(Path("/fixture/mod.2k5mod"))
            self.window._undo()
            self.window._revert_all()
            self.window._revert_selected()
            self.window._choose_build_output()
            self.window._launch_xemu()
            self.window._recover_from_menu()

            self.assertEqual(starts, [])
            self.assertEqual(continuations, [])
            self.assertEqual(invalidations, [])
            open_file.assert_not_called()
            save_file.assert_not_called()
            question.assert_not_called()
            self.assertGreaterEqual(information.call_count, 14)
            messages = "\n".join(
                str(call.args[2]) for call in information.call_args_list
            )
            self.assertIn("Wait for the Audio operation", messages)
            self.assertIn("Cancel waveform", messages)

        # The lowest-level admission fence still refuses a missed direct route.
        self.window._start_task = original_start_task  # type: ignore[method-assign]
        with patch.object(self.window.thread_pool, "start") as start, patch(
            "mod_editor.gui.studio_qt.QMessageBox.information"
        ):
            self.window._start_task(
                lambda _progress: "must not run",
                lambda _result: None,
                label="Synthetic global mutation",
                blocking=True,
            )
        start.assert_not_called()

    def test_audio_busy_guards_specialist_host_boundary_and_crib_task_admission(
        self,
    ) -> None:
        self._begin_audio_operation()
        progress = lambda _stage, _completed, _total: None
        with patch.object(self.facade, "replace_text") as replace_text, patch.object(
            self.facade, "replace_crib_photo"
        ) as replace_crib, patch(
            "mod_editor.gui.crib_panel_qt.QMessageBox.warning"
        ) as warning:
            with self.assertRaisesRegex(ValidationError, "Audio"):
                self.window._text_roster_panel.host.replace_text(
                    "fixture:text", "changed", progress
                )
            with self.assertRaisesRegex(ValidationError, "Audio"):
                self.crib.host.replace_crib_photo(
                    "fixture:crib", Path("/fixture/replacement.png"), progress
                )
            self.crib._run(
                lambda _progress: "must not start",
                lambda _value: None,
            )

        replace_text.assert_not_called()
        replace_crib.assert_not_called()
        self.assertEqual(self.crib_tasks, [])
        self.assertFalse(self.crib.operation_in_progress)
        warning.assert_called_once()

    def test_crib_busy_fences_shell_and_audio_then_restores_everything(self) -> None:
        self.crib._run(
            lambda _progress: "crib finished",
            lambda _value: None,
        )
        self.assertEqual(len(self.crib_tasks), 1)
        self.assertTrue(self.window._embedded_crib_busy)
        self.assertTrue(self.crib.operation_in_progress)
        self.assertTrue(self.crib.isEnabled())
        self.assertFalse(self.audio.isEnabled())
        self.assertFalse(self.window.navigation.isEnabled())
        self.assertFalse(self.window.open_source_button.isEnabled())
        self.assertFalse(self.window.save_project_button.isEnabled())
        self.assertFalse(self.window.build_button.isEnabled())

        with patch(
            "mod_editor.gui.audio_panel_qt.QMessageBox.warning"
        ) as warning:
            self.audio._run(
                lambda _progress: "must not start",
                lambda _value: None,
            )
        self.assertEqual(self.audio_tasks, [])
        self.assertFalse(self.audio.operation_in_progress)
        warning.assert_called_once()

        self.crib_tasks[0].run()  # type: ignore[attr-defined]
        self.application.processEvents()
        self.assertFalse(self.window._embedded_crib_busy)
        self.assertFalse(self.crib.operation_in_progress)
        self.assertTrue(self.audio.isEnabled())
        self.assertTrue(self.window.navigation.isEnabled())
        self.assertTrue(self.window.open_source_button.isEnabled())
        self.assertTrue(self.window.save_project_button.isEnabled())

    def _install_captured_shell_pool(self) -> list[object]:
        tasks: list[object] = []
        self.deferred_crib_refresh_states: list[bool] = []
        self.deferred_audio_reset_states: list[bool] = []
        self.window.thread_pool = SimpleNamespace(  # type: ignore[assignment]
            start=lambda task: tasks.append(task)
        )
        self.window._refresh_specialized_panels = (  # type: ignore[method-assign]
            lambda **_kwargs: None
        )
        self.window._refresh_entered_page = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: None
        )
        self.window._refresh_recent_menus = (  # type: ignore[method-assign]
            lambda: None
        )
        self.window._preview_selected_asset = (  # type: ignore[method-assign]
            lambda: None
        )
        self.audio.reset_for_source = (  # type: ignore[method-assign]
            lambda: self.deferred_audio_reset_states.append(
                self.window._blocking
            )
        )
        self.audio.refresh = lambda: None  # type: ignore[method-assign]
        self.crib.refresh = (  # type: ignore[method-assign]
            lambda **_kwargs: self.deferred_crib_refresh_states.append(
                self.window._blocking
            )
        )
        return tasks

    def _prepare_named_project(self, path: Path) -> object:
        path.write_bytes(b"retail-free test project")
        identity = project_target_identity(path)
        self.window._active_project_path = path
        self.window._active_project_identity = identity
        self.facade.save_project = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: SimpleNamespace(
                message="saved", project_identity=identity
            )
        )
        self.window._prompt_unsaved_decision = (  # type: ignore[method-assign]
            lambda _context: "save"
        )
        self.window._workspace_dirty = True
        return identity

    def test_save_then_open_xiso_starts_only_after_save_worker_releases_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "active.2k5mod"
            source = root / "next.xiso"
            source.write_bytes(b"fixture")
            self._prepare_named_project(active)
            tasks = self._install_captured_shell_pool()

            def load_source(path: Path, _progress: object) -> object:
                self.facade.source_ready = True
                self.facade.source_path = path
                self.facade.source_sha256 = None
                return "indexed"

            self.facade.load_source = load_source  # type: ignore[method-assign]
            self.window._request_source_switch(source)
            self.assertEqual(len(tasks), 1)
            self.assertTrue(self.window._blocking)

            tasks[0].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertEqual(len(tasks), 2)
            self.assertTrue(self.window._blocking)
            self.assertEqual(self.window._post_blocking_continuations, [])

            tasks[1].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertFalse(self.window._blocking)
            # The fake facade hands the window the raw source path; the window
            # stores it verbatim. Compare resolved on both sides so the "active
            # source is this file" invariant holds where the temp dir sits under
            # a symlink (macOS /private/var) or a short name (Windows).
            self.assertEqual(
                self.window._active_source_path.resolve(), source.resolve()
            )
            self.assertEqual(self.deferred_crib_refresh_states, [False])
            self.assertEqual(self.deferred_audio_reset_states, [False])

    def test_save_then_open_project_starts_after_save_worker_releases_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "active.2k5mod"
            incoming = root / "incoming.2k5mod"
            incoming.write_bytes(b"incoming retail-free fixture")
            self._prepare_named_project(active)
            tasks = self._install_captured_shell_pool()
            incoming_identity = project_target_identity(incoming)
            self.facade.load_project = (  # type: ignore[method-assign]
                lambda *_args: SimpleNamespace(
                    message="loaded", project_identity=incoming_identity
                )
            )

            self.window._request_project_load(incoming)
            self.assertEqual(len(tasks), 1)
            tasks[0].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertEqual(len(tasks), 2)
            self.assertTrue(self.window._blocking)

            tasks[1].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertFalse(self.window._blocking)
            self.assertEqual(self.window._active_project_path, incoming.resolve())
            self.assertEqual(self.deferred_crib_refresh_states, [False])

    def test_recovery_source_then_project_waits_for_source_worker_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "recovery.xiso"
            project = root / "recovery.2k5mod"
            source.write_bytes(b"fixture")
            project.write_bytes(b"retail-free recovery fixture")
            tasks = self._install_captured_shell_pool()
            project_identity = project_target_identity(project)

            def load_source(path: Path, _progress: object) -> object:
                self.facade.source_ready = True
                self.facade.source_path = path
                self.facade.source_sha256 = None
                return "indexed"

            self.facade.load_source = load_source  # type: ignore[method-assign]
            self.facade.load_project = (  # type: ignore[method-assign]
                lambda *_args: SimpleNamespace(
                    message="recovered", project_identity=project_identity
                )
            )
            candidate = RecoveryCandidate(source, None, project)
            self.window._load_source_path(source, recovery=candidate)
            self.assertEqual(len(tasks), 1)

            tasks[0].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertEqual(len(tasks), 2)
            self.assertTrue(self.window._blocking)
            self.assertEqual(self.deferred_crib_refresh_states, [])

            tasks[1].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertFalse(self.window._blocking)
            self.assertTrue(self.window._workspace_dirty)
            self.assertEqual(self.deferred_crib_refresh_states, [False])
            self.assertEqual(self.deferred_audio_reset_states, [])

    def test_recovery_sha_mismatch_refreshes_new_source_only_after_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "different.xiso"
            project = root / "recovery.2k5mod"
            source.write_bytes(b"fixture")
            project.write_bytes(b"retail-free recovery fixture")
            tasks = self._install_captured_shell_pool()
            errors: list[str] = []
            colour_reads: list[tuple[str, bool]] = []
            self.window._show_error = errors.append  # type: ignore[method-assign]

            def load_source(path: Path, _progress: object) -> object:
                self.facade.source_ready = True
                self.facade.source_path = path
                self.facade.source_sha256 = "a" * 64
                return "indexed"

            self.facade.load_source = load_source  # type: ignore[method-assign]
            self.facade.uniform_colors = (  # type: ignore[method-assign]
                lambda selector, _progress: (
                    colour_reads.append((selector, self.window._blocking))
                    or ("FF101820", "FF203040", False)
                )
            )
            candidate = RecoveryCandidate(source, "b" * 64, project)
            self.window._load_source_path(source, recovery=candidate)
            self.assertEqual(len(tasks), 1)

            tasks[0].run()  # type: ignore[attr-defined]
            self.application.processEvents()

            # The new source refresh includes an asynchronous read of the
            # selected physical set's facemask/turtleneck record, and (since the
            # open-disc hook) one read-only inspection of the disc for the Build /
            # Game Fixes / Position names pages. Both must be queued only after
            # the source worker releases the blocking shell.
            self.assertEqual(len(tasks), 3)
            self.assertFalse(self.window._blocking)
            self.assertEqual(self.deferred_audio_reset_states, [False])
            self.assertEqual(self.deferred_crib_refresh_states, [False])
            self.assertEqual(len(errors), 1)
            self.assertIn("does not match", errors[0])
            tasks[1].run()  # type: ignore[attr-defined]
            self.application.processEvents()
            self.assertEqual(len(colour_reads), 1)
            self.assertFalse(colour_reads[0][1])
            # Resolve both sides: the window stores the facade's raw source path,
            # which denotes the same file as source under a symlinked (macOS) or
            # short-name (Windows) temp root.
            self.assertEqual(
                self.window._active_source_path.resolve(), source.resolve()
            )

    def test_undo_refreshes_crib_only_after_worker_releases_shell(self) -> None:
        tasks = self._install_captured_shell_pool()
        self.audio.invalidate_audio_content = lambda: None  # type: ignore[method-assign]
        self.facade.undo = (  # type: ignore[method-assign]
            lambda _progress: "undone"
        )

        self.window._undo()
        self.assertEqual(len(tasks), 1)
        self.assertTrue(self.window._blocking)
        self.assertEqual(self.deferred_crib_refresh_states, [])

        tasks[0].run()  # type: ignore[attr-defined]
        self.application.processEvents()
        self.assertFalse(self.window._blocking)
        self.assertEqual(self.deferred_crib_refresh_states, [False])

    def test_revert_all_refreshes_crib_only_after_worker_releases_shell(self) -> None:
        tasks = self._install_captured_shell_pool()
        self.audio.invalidate_audio_content = lambda: None  # type: ignore[method-assign]
        self.facade.revert_all = (  # type: ignore[method-assign]
            lambda _progress: "reverted"
        )

        with patch(
            "mod_editor.gui.studio_qt.QMessageBox.question",
            return_value=QMessageBox.Yes,
        ):
            self.window._revert_all()
        self.assertEqual(len(tasks), 1)
        self.assertTrue(self.window._blocking)
        self.assertEqual(self.deferred_crib_refresh_states, [])

        tasks[0].run()  # type: ignore[attr-defined]
        self.application.processEvents()
        self.assertFalse(self.window._blocking)
        self.assertEqual(self.deferred_crib_refresh_states, [False])

    def test_clean_close_is_refused_without_auto_close_until_audio_drains(self) -> None:
        task = self._begin_audio_operation()
        self.window._workspace_dirty = False
        self.window._allow_close = True
        event = QCloseEvent()
        with patch(
            "mod_editor.gui.studio_qt.QMessageBox.information"
        ) as information, patch.object(self.window, "close") as close:
            self.window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertIn("Cancel waveform", information.call_args.args[2])
            task.run()  # type: ignore[attr-defined]
            self.application.processEvents()
            close.assert_not_called()
        self.assertFalse(self.window._embedded_audio_busy)

    def test_recovery_autosave_waits_for_audio_drain(self) -> None:
        task = self._begin_audio_operation()
        self.window.workspace_store = SimpleNamespace()
        self.window._active_source_path = Path("/fixture/source.xiso")
        self.window._workspace_dirty = True
        with patch.object(self.window.thread_pool, "start") as start, patch(
            "mod_editor.gui.studio_qt.QTimer.singleShot"
        ) as schedule:
            self.window._save_recovery_snapshot()
            start.assert_not_called()
            self.assertTrue(self.window._recovery_save_pending)
            self.assertIn("when Audio finishes", self.window.operation_status.text())

            task.run()  # type: ignore[attr-defined]
            self.application.processEvents()
            start.assert_not_called()
            schedule.assert_called_once()
            self.assertEqual(schedule.call_args.args[0], 0)
            self.assertIs(
                schedule.call_args.args[1].__self__,
                self.window,
            )

    def test_project_undo_and_revert_all_invalidate_before_mutation_admission(
        self,
    ) -> None:
        events: list[str] = []
        self.audio.invalidate_audio_content = (  # type: ignore[method-assign]
            lambda: events.append("invalidate")
        )
        self.window._start_task = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: events.append("start")
        )
        with patch(
            "mod_editor.gui.studio_qt.QMessageBox.question",
            return_value=QMessageBox.Yes,
        ):
            self.window._load_project_path(Path("/fixture/mod.2k5mod"))
            self.window._undo()
            self.window._revert_all()

        self.assertEqual(
            events,
            [
                "invalidate", "start",
                "invalidate", "start",
                "invalidate", "start",
            ],
        )


if __name__ == "__main__":
    unittest.main()
