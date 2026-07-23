"""Headless safety and connectivity tests for 2K5 workspace recovery."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from mod_editor.core.errors import ValidationError
from mod_editor.gui.studio_qt import StudioMainWindow, launch_studio
from mod_editor.studio.facade import Nfl2k5StudioFacade
from mod_editor.studio.workspace_state import (
    MAX_RECENT_ITEMS,
    WorkspaceStateStore,
)


class WorkspaceStateStoreTests(unittest.TestCase):
    def test_recent_files_are_atomic_bounded_and_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-workspace-state-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            sources = []
            projects = []
            for index in range(MAX_RECENT_ITEMS + 3):
                source = root / f"source-{index}.iso"
                source.write_bytes(f"synthetic-source-{index}".encode("ascii"))
                project = root / f"project-{index}.2k5mod"
                project.write_bytes(f"authored-project-{index}".encode("ascii"))
                sources.append(source.resolve())
                projects.append(project.resolve())
                store.record_source(source, f"{index:064x}")
                store.record_project(project)

            state = store.read()
            self.assertEqual(len(state.recent_sources), MAX_RECENT_ITEMS)
            self.assertEqual(len(state.recent_projects), MAX_RECENT_ITEMS)
            self.assertEqual(Path(state.recent_sources[0]), sources[-1])
            self.assertEqual(Path(state.recent_projects[0]), projects[-1])
            document = json.loads(store.state_path.read_text(encoding="utf-8"))
            self.assertEqual(document["schema"], "2k5_mod_studio_workspace_state/v1")
            self.assertNotIn("synthetic-source", store.state_path.read_text("utf-8"))
            self.assertNotIn("authored-project", store.state_path.read_text("utf-8"))

    def test_recovery_is_bound_to_exact_private_project_and_source_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-recovery-binding-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "NFL 2K5.iso"
            source.write_bytes(b"synthetic-recognized-source")
            store.recovery_path.write_bytes(b"user-authored-replacements-only")
            digest = "ab" * 32

            candidate = store.register_recovery(
                source_path=source,
                source_sha256=digest,
                project_path=store.recovery_path,
            )
            self.assertEqual(candidate.source_path, source.resolve())
            self.assertEqual(candidate.source_sha256, digest)
            self.assertEqual(store.recovery_candidate(), candidate)
            self.assertNotIn(
                "synthetic-recognized-source",
                store.state_path.read_text(encoding="utf-8"),
            )

            store.clear_recovery()
            self.assertFalse(store.recovery_path.exists())
            self.assertIsNone(store.recovery_candidate(require_source=False))
            self.assertEqual(store.read().recent_sources[0], str(source.resolve()))

    def test_recovery_refuses_aliases_and_invalid_hashes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-recovery-refusal-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "source.iso"
            source.write_bytes(b"source")
            outside = root / "outside.2k5mod"
            outside.write_bytes(b"replacement")
            with self.assertRaisesRegex(ValidationError, "private replacement-only"):
                store.register_recovery(
                    source_path=source,
                    source_sha256="11" * 32,
                    project_path=outside,
                )
            store.recovery_path.symlink_to(outside)
            self.assertIsNone(store.recovery_candidate(require_source=False))
            with self.assertRaisesRegex(ValidationError, "not a regular private file"):
                store.clear_recovery()
            with self.assertRaisesRegex(ValidationError, "SHA-256"):
                store.record_source(source, "not-a-digest")


class _RecoverySession:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, bool]] = []
        self.allow_empty_calls: list[bool] = []

    def save_shareable_project(
        self, destination: Path, *, replace: bool, allow_empty: bool = False
    ) -> Path:
        self.calls.append((destination, replace))
        self.allow_empty_calls.append(allow_empty)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"replacement-only-project")
        return destination.resolve()


class FacadeRecoveryBindingTests(unittest.TestCase):
    def test_facade_checks_source_identity_inside_the_session_lock(self) -> None:
        facade = Nfl2k5StudioFacade(
            uniform_catalog=object(),  # type: ignore[arg-type]
            visual_catalog=object(),  # type: ignore[arg-type]
            xemu_command=(),
        )
        session = _RecoverySession()
        facade._cache = SimpleNamespace(source=SimpleNamespace(sha256="22" * 32))
        facade._session = session  # type: ignore[assignment]
        progress_rows: list[tuple[str, int, int]] = []
        progress = lambda *row: progress_rows.append(row)  # type: ignore[arg-type]
        with tempfile.TemporaryDirectory(prefix="2k5-facade-recovery-") as temporary:
            output = Path(temporary) / "recovery.2k5mod"
            with self.assertRaisesRegex(ValidationError, "source changed"):
                facade.save_recovery_project(output, "33" * 32, progress)
            self.assertFalse(output.exists())
            result = facade.save_recovery_project(output, "22" * 32, progress)
            self.assertEqual(result.output, output.resolve())
        self.assertEqual(session.calls, [(output, True)])
        self.assertEqual(session.allow_empty_calls, [True])
        self.assertEqual(progress_rows[-1], ("Recovery snapshot saved", 1, 1))


class FlagshipRecoveryConnectivityTests(unittest.TestCase):
    """Static headless checks: no QApplication, window, or display is created."""

    def test_source_project_and_close_paths_share_the_unsaved_gate(self) -> None:
        source_switch = inspect.getsource(StudioMainWindow._request_source_switch)
        project_load = inspect.getsource(StudioMainWindow._request_project_load)
        close_event = inspect.getsource(StudioMainWindow.closeEvent)
        self.assertIn("_continue_after_unsaved", source_switch)
        self.assertIn("_continue_after_unsaved", project_load)
        self.assertIn("_prompt_unsaved_decision", close_event)
        self.assertIn("Discard", inspect.getsource(
            StudioMainWindow._prompt_unsaved_decision
        ))
        self.assertIn("after_success=self._finish_close_after_save", close_event)

    def test_every_embedded_edit_route_marks_the_recovery_workspace(self) -> None:
        for method in (
            StudioMainWindow._replace_asset,
            StudioMainWindow._revert_selected,
            StudioMainWindow._replace_visual_asset,
            StudioMainWindow._revert_visual_asset,
            StudioMainWindow._replace_stadium_texture,
            StudioMainWindow._revert_stadium_texture,
            StudioMainWindow._undo,
            StudioMainWindow._revert_all,
            StudioMainWindow._specialized_panel_refresh,
        ):
            self.assertIn("_mark_workspace_changed", inspect.getsource(method))

    def test_production_launcher_enables_workspace_recovery(self) -> None:
        source = inspect.getsource(launch_studio)
        self.assertIn("workspace_store=WorkspaceStateStore()", source)
        self.assertIn("offer_recovery=True", source)


if __name__ == "__main__":
    unittest.main()
