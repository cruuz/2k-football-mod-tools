"""Real-runner regression for APF audio preview-to-Apply ordering."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QThread  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from mod_editor.apf_studio.gui import ApfStudioMainWindow  # noqa: E402
from mod_editor.apf_studio.inspectors import (  # noqa: E402
    ExportIdentity,
    InspectorRow,
    PagedModel,
)
from mod_editor.apf_studio.models import ApfCategory  # noqa: E402


ROW_ID = "apf:audio:audo:4:1"


def _audio_model() -> PagedModel:
    return PagedModel(
        (
            InspectorRow(
                row_id=ROW_ID,
                kind="audo",
                title="Synthetic menu sound",
                subtitle="Ordering fixture",
                fields={
                    "outer_table_index": 4,
                    "inner_file_index": 1,
                    "audio_source_id": "audo:standalone",
                    "audio_source_label": "Standalone AUDO",
                    "role_id": "ui_menu_sfx",
                    "role_label": "UI & Menu SFX",
                    "sample_rate": 48_000,
                    "derived_channel_count": 2,
                    "duration_seconds": 1.0,
                    "encoded_size": 0x800,
                },
                export_identity=ExportIdentity(
                    "audo", 4, 1, None, "synthetic-menu-sound"
                ),
                _search_text="synthetic menu sound",
            ),
        ),
        ("Synthetic audio model for worker-ordering coverage only.",),
    )


class _RunnerFacade:
    """Minimum product-shaped facade plus deterministic audio pack receipts."""

    def __init__(self) -> None:
        self.source_ready = False
        self.source_display_name = "Synthetic APF 2K8"
        self.source = None
        self.modified_count = 0
        self.modified_asset_ids: frozenset[str] = frozenset()
        self.can_undo = False
        self.last_build = None
        self.last_project_identity = None
        self.launcher = SimpleNamespace(
            settings=SimpleNamespace(configured=False, title_update_path=None)
        )
        self.can_launch_xenia = False
        # Launch names its single blocker instead of graying out.
        self.xenia_blocker = "Build a modded game folder first."
        self.preview_calls = 0
        self.apply_calls = 0
        self.close_calls = 0
        self._inspectors = object()
        self._catalog = SimpleNamespace(
            outer_count=0,
            assets=(),
            uniform_assets=(),
        )

    def require_catalog(self) -> object:
        return self._catalog

    def require_inspectors(self) -> object:
        return self._inspectors

    def preview_audio_replacement_pack(
        self,
        _root: Path,
        progress: object,
        *,
        encoder: object | None = None,
        cancel_requested: object,
    ) -> object:
        self.preview_calls += 1
        assert encoder is None
        assert not cancel_requested()  # type: ignore[operator]
        progress("Validated synthetic preview", 1, 1)  # type: ignore[operator]
        return SimpleNamespace(
            template_entry_count=1,
            supplied_count=1,
            would_change_count=1,
            already_current_count=0,
            missing_count=0,
            current_modified_audio_count=0,
            resulting_modified_audio_count=1,
            validated_count=1,
            confirmation_token="e" * 64,
            was_cancelled=False,
            input_kind="xma1",
        )

    def import_audio_replacement_pack(
        self,
        _root: Path,
        progress: object,
        *,
        encoder: object | None = None,
        cancel_requested: object,
        confirmation_token: str,
    ) -> object:
        self.apply_calls += 1
        assert encoder is None
        assert not cancel_requested()  # type: ignore[operator]
        assert confirmation_token == "e" * 64
        progress("Applied synthetic replacement", 1, 1)  # type: ignore[operator]
        self.modified_asset_ids = frozenset((ROW_ID,))
        self.modified_count = 1
        self.can_undo = True
        return SimpleNamespace(
            template_entry_count=1,
            supplied_count=1,
            staged_count=1,
            unchanged_count=0,
            missing_count=0,
            validated_count=1,
            was_cancelled=False,
            input_kind="xma1",
        )

    def close(self) -> None:
        self.close_calls += 1


class ApfAudioImportIdleBarrierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_real_runner_drains_preview_before_confirmation_and_apply(self) -> None:
        facade = _RunnerFacade()
        window = ApfStudioMainWindow(facade)  # type: ignore[arg-type]
        audio_page = window._pages[ApfCategory.AUDIO]
        browser = audio_page.inspector  # type: ignore[attr-defined]
        browser.set_model(_audio_model(), "1 synthetic sound")
        browser.table.selectRow(0)
        self.application.processEvents()

        # The category page must pass the product window's ownership-aware idle
        # barrier, not a generic zero-delay timer, into the Audio inspector.
        self.assertIs(browser._run_when_idle.__self__, window)
        self.assertIs(
            browser._run_when_idle.__func__,
            ApfStudioMainWindow._run_when_idle,
        )

        product_run_task = browser.run_task
        admissions: list[tuple[str, frozenset[object], bool | None]] = []
        preview_worker: object | None = None

        def recording_run_task(
            label: str,
            operation: object,
            on_success: object | None = None,
            blocking: bool = True,
        ) -> bool | None:
            nonlocal preview_worker
            workers_before = frozenset(window._workers)
            admitted = product_run_task(
                label,
                operation,  # type: ignore[arg-type]
                on_success,  # type: ignore[arg-type]
                blocking,
            )
            admissions.append((label, workers_before, admitted))
            if label.startswith("Checking APF"):
                created = set(window._workers).difference(workers_before)
                self.assertEqual(len(created), 1)
                preview_worker = created.pop()
            return admitted

        browser.run_task = recording_run_task
        confirmation_workers: list[frozenset[object]] = []
        real_task_finished = window._task_finished
        held_finished: list[object] = []
        hold_preview_cleanup = True

        def delayed_task_finished(worker: object) -> None:
            if hold_preview_cleanup and worker is preview_worker:
                held_finished.append(worker)
                return
            real_task_finished(worker)  # type: ignore[arg-type]

        # _run_task's finished-signal lambda resolves this method at delivery
        # time. Holding the exact preview cleanup makes the ordering contract
        # deterministic: a generic QTimer continuation would open confirmation
        # while this worker still owns the blocking lane.
        window._task_finished = delayed_task_finished  # type: ignore[method-assign]

        def approve_after_recording(*_args: object, **_kwargs: object) -> int:
            confirmation_workers.append(frozenset(window._workers))
            return QMessageBox.Apply

        try:
            with (
                mock.patch(
                    "mod_editor.apf_studio.gui.QFileDialog.getExistingDirectory",
                    return_value="/synthetic/audio-replacement-pack",
                ),
                mock.patch.object(
                    browser, "_external_xma1_encoder", return_value=None
                ),
                mock.patch(
                    "mod_editor.apf_studio.gui.QMessageBox.question",
                    side_effect=approve_after_recording,
                ),
                mock.patch(
                    "mod_editor.apf_studio.gui.QMessageBox.information"
                ) as information,
            ):
                browser._import_audio_replacement_pack()
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    self.application.processEvents()
                    if (
                        held_finished
                        and window._idle_callbacks
                    ):
                        break
                    QThread.msleep(1)

                self.assertEqual(facade.preview_calls, 1)
                self.assertEqual(held_finished, [preview_worker])
                self.assertIn(preview_worker, window._workers)
                # One callback releases the Audio mutation controls and the
                # second opens confirmation. Both stay behind the exact same
                # worker-unregister barrier.
                self.assertEqual(len(window._idle_callbacks), 2)
                self.assertTrue(browser._audio_import_running)
                self.assertFalse(
                    browser.audio_replacement_drop_zone.isEnabled()
                )
                self.assertEqual(confirmation_workers, [])
                self.assertEqual(facade.apply_calls, 0)
                self.assertEqual(len(admissions), 1)

                # Release only the product runner's real ownership cleanup.
                # _task_finished drains the queued idle continuation after the
                # preview worker leaves both worker registries.
                hold_preview_cleanup = False
                window._task_finished = real_task_finished  # type: ignore[method-assign]
                assert preview_worker is not None
                real_task_finished(preview_worker)  # type: ignore[arg-type]

                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    self.application.processEvents()
                    if (
                        facade.apply_calls == 1
                        and not window._workers
                        and information.called
                    ):
                        break
                    QThread.msleep(1)

            self.assertEqual(facade.preview_calls, 1)
            self.assertEqual(facade.apply_calls, 1)
            self.assertEqual(confirmation_workers, [frozenset()])
            self.assertEqual(len(admissions), 2)
            preview_admission, apply_admission = admissions
            self.assertTrue(preview_admission[0].startswith("Checking APF"))
            self.assertEqual(preview_admission[1], frozenset())
            self.assertIs(preview_admission[2], True)
            self.assertTrue(
                apply_admission[0].startswith("Revalidating and applying")
            )
            self.assertEqual(apply_admission[1], frozenset())
            self.assertIs(apply_admission[2], True)
            self.assertIsNotNone(preview_worker)
            self.assertNotIn(preview_worker, window._workers)
            self.assertEqual(window._workers, set())
            self.assertFalse(browser._audio_import_running)
            self.assertTrue(browser.audio_replacement_drop_zone.isEnabled())
            self.assertIn(
                "Project edits changed: 1",
                information.call_args.args[2],
            )
        finally:
            hold_preview_cleanup = False
            window._task_finished = real_task_finished  # type: ignore[method-assign]
            for worker in held_finished:
                if worker in window._workers:
                    real_task_finished(worker)  # type: ignore[arg-type]
            self.application.processEvents()
            window._allow_close = True
            window.close()
            window.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
