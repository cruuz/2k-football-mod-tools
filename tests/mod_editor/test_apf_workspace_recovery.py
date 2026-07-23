"""Headless recents and crash-recovery safety tests for APF Mod Studio."""

from __future__ import annotations

import inspect
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtGui import QCloseEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402
from PIL import Image  # noqa: E402

from mod_editor.apf_studio.facade import (  # noqa: E402
    ApfStudioFacade,
    FacadeError,
)
from mod_editor.apf_studio.gui import (  # noqa: E402
    ApfStudioMainWindow,
    launch_studio,
)
from mod_editor.apf_studio.models import Modification  # noqa: E402
from mod_editor.apf_studio.project import (  # noqa: E402
    MAX_RECENT_ITEMS,
    MAX_WORKSPACE_STATE_BYTES,
    PROJECT_EXTENSION,
    ProjectError,
    RecoveryCandidate,
    WORKSPACE_STATE_SCHEMA,
    WorkspaceStateStore,
    default_workspace_state_root,
    project_target_identity,
    save_project,
)


SOURCE_SHA256 = "a5" * 32


def _empty_project(path: Path, *, replace: bool = False) -> Path:
    return save_project(
        path,
        source_sha256=SOURCE_SHA256,
        modifications=(),
        replace=replace,
    )


class ApfWorkspaceStateStoreTests(unittest.TestCase):
    def test_recents_accept_files_and_folders_are_bounded_and_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-workspace-state-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "private-state")
            sources: list[Path] = []
            projects: list[Path] = []
            for index in range(MAX_RECENT_ITEMS + 3):
                if index % 2:
                    source = root / f"game-{index}"
                    source.mkdir()
                    (source / "0A-marker").write_bytes(
                        f"synthetic-retail-{index}".encode("ascii")
                    )
                else:
                    source = root / f"game-{index}.iso"
                    source.write_bytes(f"synthetic-retail-{index}".encode("ascii"))
                project = root / f"mod-{index}{PROJECT_EXTENSION}"
                project.write_bytes(f"authored-edit-{index}".encode("ascii"))
                sources.append(source.resolve())
                projects.append(project.resolve())
                store.record_source(source, f"{index:064x}")
                store.record_project(project)

            # De-duplication moves an existing item to the front without growth.
            store.record_source(sources[-3], "f" * 64)
            store.record_project(projects[-3])
            state = store.read()
            self.assertEqual(len(state.recent_sources), MAX_RECENT_ITEMS)
            self.assertEqual(len(state.recent_projects), MAX_RECENT_ITEMS)
            self.assertEqual(Path(state.recent_sources[0]), sources[-3])
            self.assertEqual(Path(state.recent_projects[0]), projects[-3])
            document_bytes = store.state_path.read_bytes()
            document = json.loads(document_bytes)
            self.assertEqual(document["schema"], WORKSPACE_STATE_SCHEMA)
            self.assertNotIn(b"synthetic-retail", document_bytes)
            self.assertNotIn(b"authored-edit", document_bytes)
            self.assertEqual(store.state_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(list(store.root.glob(".*.tmp")), [])

    def test_exact_state_override_requires_an_absolute_private_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-state-override-") as temporary:
            root = Path(temporary) / "exact-state"
            with mock.patch.dict(
                os.environ,
                {"APF2K8_MOD_STUDIO_STATE_DIR": str(root)},
                clear=False,
            ):
                self.assertEqual(default_workspace_state_root(), root)
                self.assertEqual(WorkspaceStateStore().root, root.resolve())
            with mock.patch.dict(
                os.environ,
                {"APF2K8_MOD_STUDIO_STATE_DIR": "relative/state"},
                clear=False,
            ):
                with self.assertRaisesRegex(ProjectError, "absolute"):
                    default_workspace_state_root()

    def test_corrupt_oversized_linked_and_hardlinked_state_fail_closed(self) -> None:
        cases = ("corrupt", "oversized", "symlink", "hardlink")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory(
                prefix=f"apf-workspace-{case}-"
            ) as temporary:
                root = Path(temporary)
                store = WorkspaceStateStore(root / "state")
                source = root / "source.iso"
                source.write_bytes(b"source-marker")
                store.record_source(source, SOURCE_SHA256)
                if case == "corrupt":
                    store.state_path.write_text("{broken", encoding="utf-8")
                elif case == "oversized":
                    store.state_path.write_bytes(
                        b"x" * (MAX_WORKSPACE_STATE_BYTES + 1)
                    )
                elif case == "symlink":
                    outside = root / "outside.json"
                    outside.write_bytes(store.state_path.read_bytes())
                    store.state_path.unlink()
                    store.state_path.symlink_to(outside)
                else:
                    os.link(store.state_path, root / "second-state-name")
                with self.assertRaises(ProjectError):
                    store.read()

    def test_recent_aliases_are_refused_and_stale_entries_remain_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-workspace-alias-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "game"
            source.mkdir()
            linked_source = root / "linked-game"
            linked_source.symlink_to(source, target_is_directory=True)
            with self.assertRaisesRegex(ProjectError, "non-linked"):
                store.record_source(linked_source, SOURCE_SHA256)
            project = root / f"project{PROJECT_EXTENSION}"
            project.write_bytes(b"user-authored")
            linked_project = root / f"linked{PROJECT_EXTENSION}"
            linked_project.symlink_to(project)
            with self.assertRaisesRegex(ProjectError, "non-linked"):
                store.record_project(linked_project)
            store.record_source(source, SOURCE_SHA256)
            source.rmdir()
            self.assertEqual(
                Path(store.read().recent_sources[0]), source.resolve()
            )


class ApfRecoveryArchiveTests(unittest.TestCase):
    def test_recovery_is_exact_source_bound_empty_safe_and_selectively_cleared(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-recovery-binding-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "All-Pro Football 2K8"
            source.mkdir()
            retail_marker = b"never-copy-these-retail-bytes"
            (source / "0A").write_bytes(retail_marker)
            _empty_project(store.recovery_path, replace=True)
            candidate = store.register_recovery(
                source_path=source,
                source_sha256=SOURCE_SHA256,
                project_path=store.recovery_path,
            )
            self.assertEqual(store.recovery_candidate(), candidate)
            self.assertEqual(candidate.source_path, source.resolve())
            with zipfile.ZipFile(store.recovery_path) as archive:
                self.assertEqual(archive.namelist(), ["project.json"])
                manifest = json.loads(archive.read("project.json"))
            self.assertEqual(manifest["replacement_count"], 0)
            self.assertFalse(
                manifest["distribution"]["contains_original_game_bytes"]
            )
            self.assertNotIn(retail_marker, store.recovery_path.read_bytes())

            other = root / "other.iso"
            other.write_bytes(b"other-source")
            self.assertFalse(store.clear_recovery_for_source(other, SOURCE_SHA256))
            self.assertIsNotNone(store.recovery_candidate(require_source=False))
            self.assertTrue(store.clear_recovery_for_source(source, SOURCE_SHA256))
            self.assertFalse(store.recovery_path.exists())
            self.assertIsNone(store.recovery_candidate(require_source=False))
            # Clearing recovery preserves the useful recent-source history.
            self.assertEqual(Path(store.read().recent_sources[0]), source.resolve())

    def test_outside_invalid_hash_and_linked_recovery_are_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-recovery-refusal-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "source.iso"
            source.write_bytes(b"source")
            outside = _empty_project(root / f"outside{PROJECT_EXTENSION}")
            with self.assertRaisesRegex(ProjectError, "private replacement-only"):
                store.register_recovery(
                    source_path=source,
                    source_sha256=SOURCE_SHA256,
                    project_path=outside,
                )
            with self.assertRaisesRegex(ProjectError, "SHA-256"):
                store.record_source(source, "not-a-hash")
            store.recovery_path.symlink_to(outside)
            self.assertIsNone(store.recovery_candidate(require_source=False))
            with self.assertRaisesRegex(ProjectError, "regular private file"):
                store.clear_recovery()

    def test_nonempty_recovery_contains_only_authored_payload_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-recovery-nonempty-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "source.iso"
            retail_marker = b"retail-source-marker-must-not-ship"
            source.write_bytes(retail_marker)
            replacement = root / "jersey.png"
            Image.new("RGBA", (1024, 1024), (15, 35, 75, 255)).save(
                replacement, format="PNG"
            )
            data = replacement.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            modification = Modification(
                asset_id="apf:uniform:jersey:00",
                kind="uniform",
                replacement_path=replacement,
                replacement_sha256=digest,
                metadata={"family": "jersey", "asset_index": 0},
            )
            save_project(
                store.recovery_path,
                source_sha256=SOURCE_SHA256,
                modifications=(modification,),
                replace=True,
            )
            store.register_recovery(
                source_path=source,
                source_sha256=SOURCE_SHA256,
                project_path=store.recovery_path,
            )
            archive_bytes = store.recovery_path.read_bytes()
            self.assertNotIn(retail_marker, archive_bytes)
            with zipfile.ZipFile(store.recovery_path) as archive:
                names = archive.namelist()
                manifest = json.loads(archive.read("project.json"))
                payload = archive.read(manifest["replacements"][0]["payload"])
            self.assertEqual(len(names), 2)
            self.assertEqual(manifest["replacement_count"], 1)
            self.assertEqual(payload, data)
            self.assertFalse(
                manifest["distribution"]["contains_original_preimages"]
            )


class _BlockingRecoverySession:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.saved: list[tuple[Path, bool, str]] = []
        self.closed = False

    def save_project(
        self,
        destination: Path,
        *,
        title: str,
        replace: bool,
    ) -> Path:
        self.started.set()
        if not self.release.wait(5):
            raise RuntimeError("test recovery save timed out")
        destination.write_bytes(b"replacement-only")
        self.saved.append((destination, replace, title))
        return destination

    def close(self) -> None:
        self.closed = True


class ApfRecoveryFacadeTests(unittest.TestCase):
    def test_wrong_source_is_refused_and_session_close_serializes_with_save(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-facade-recovery-") as temporary:
            root = Path(temporary)
            destination = root / "recovery.apf2k8mod"
            facade = ApfStudioFacade(cache_root=root / "cache")
            session = _BlockingRecoverySession()
            facade.source = SimpleNamespace(source_sha256=SOURCE_SHA256)
            facade.session = session  # type: ignore[assignment]
            with self.assertRaisesRegex(FacadeError, "source changed"):
                facade.save_recovery_project(
                    destination, "bb" * 32
                )
            self.assertFalse(destination.exists())

            errors: list[BaseException] = []
            saver = threading.Thread(
                target=lambda: self._capture(
                    errors,
                    lambda: facade.save_recovery_project(
                        destination, SOURCE_SHA256
                    ),
                )
            )
            saver.start()
            self.assertTrue(session.started.wait(2))
            closer = threading.Thread(target=facade.close)
            closer.start()
            closer.join(0.1)
            self.assertTrue(closer.is_alive(), "close must wait behind recovery lock")
            session.release.set()
            saver.join(2)
            closer.join(2)
            self.assertEqual(errors, [])
            self.assertTrue(session.closed)
            self.assertEqual(len(session.saved), 1)
            self.assertTrue(session.saved[0][1])

    @staticmethod
    def _capture(
        errors: list[BaseException], operation: object
    ) -> None:
        try:
            operation()  # type: ignore[operator]
        except BaseException as exc:  # pragma: no cover - asserted empty
            errors.append(exc)


class _WindowFacade:
    def __init__(self) -> None:
        self.source_ready = False
        self.source_display_name = "Synthetic APF"
        self.source = None
        self.modified_count = 0
        self.can_undo = False
        self.last_build = None
        self.last_project_identity = None
        self.launcher = SimpleNamespace(settings=SimpleNamespace(configured=False))
        self.can_launch_xenia = False
        self.close_calls = 0
        self.recovery_calls = 0
        self.recovery_started: threading.Event | None = None
        self.recovery_release: threading.Event | None = None
        self._catalog = SimpleNamespace(outer_count=0, assets=(), uniform_assets=())
        self._inspectors = object()

    def require_catalog(self) -> object:
        return self._catalog

    def require_inspectors(self) -> object:
        return self._inspectors

    def close(self) -> None:
        self.close_calls += 1

    def save_recovery_project(
        self,
        destination: Path,
        expected_source_sha256: str,
        _progress: object,
    ) -> Path:
        if (
            self.source is None
            or self.source.source_sha256 != expected_source_sha256
        ):
            raise FacadeError("The loaded source changed before recovery could be saved")
        self.recovery_calls += 1
        if self.recovery_started is not None:
            self.recovery_started.set()
        if self.recovery_release is not None and not self.recovery_release.wait(5):
            raise RuntimeError("test recovery release timed out")
        return _empty_project(destination, replace=True)


class ApfRecoveryWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def _window(
        self, store: WorkspaceStateStore | None = None
    ) -> tuple[_WindowFacade, ApfStudioMainWindow]:
        facade = _WindowFacade()
        window = ApfStudioMainWindow(
            facade, workspace_store=store, offer_recovery=False  # type: ignore[arg-type]
        )
        return facade, window

    def _wait_for(
        self, predicate: object, *, timeout: float = 3.0
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.application.processEvents()
            if predicate():  # type: ignore[operator]
                return
            time.sleep(0.01)
        self.fail("timed out waiting for the headless recovery worker")

    def test_recent_menus_keep_stale_items_visible_but_disabled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-recent-menu-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source_file = root / "source.iso"
            source_file.write_bytes(b"source")
            source_folder = root / "source-folder"
            source_folder.mkdir()
            project = root / f"project{PROJECT_EXTENSION}"
            project.write_bytes(b"project")
            store.record_source(source_file, SOURCE_SHA256)
            store.record_source(source_folder, SOURCE_SHA256)
            store.record_project(project)
            source_file.unlink()
            project.unlink()
            facade, window = self._window(store)
            try:
                assert window._recent_source_menu is not None
                source_actions = window._recent_source_menu.actions()
                self.assertEqual(len(source_actions), 2)
                self.assertTrue(source_actions[0].isEnabled())
                self.assertFalse(source_actions[1].isEnabled())
                assert window._recent_project_menu is not None
                self.assertFalse(
                    window._recent_project_menu.actions()[0].isEnabled()
                )
                facade.source_ready = True
                window._refresh_recent_menus()
                self.assertFalse(
                    window._recent_project_menu.actions()[0].isEnabled()
                )
                live_project = root / f"live{PROJECT_EXTENSION}"
                live_project.write_bytes(b"replacement-only-project")
                store.record_project(live_project)
                window._refresh_recent_menus()
                actions = window._recent_project_menu.actions()
                self.assertTrue(actions[0].isEnabled())
                requested: list[Path] = []
                with mock.patch.object(
                    window,
                    "_request_project_load",
                    side_effect=requested.append,
                ):
                    actions[0].trigger()
                self.assertEqual(requested, [live_project.resolve()])
            finally:
                window.deleteLater()
                self.application.processEvents()

    def test_autosave_registers_selected_source_and_coalesces_a_second_edit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-window-autosave-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "extracted-game"
            source.mkdir()
            facade, window = self._window(store)
            try:
                facade.source_ready = True
                facade.source = SimpleNamespace(
                    selected_path=source.resolve(),
                    source_sha256=SOURCE_SHA256,
                )
                window._active_source_path = source.resolve()
                window._active_source_sha256 = SOURCE_SHA256
                facade.recovery_started = threading.Event()
                facade.recovery_release = threading.Event()

                window._mark_document_changed()
                self.assertTrue(facade.recovery_started.wait(2))
                self.assertTrue(window._recovery_save_in_flight)
                window._mark_document_changed()
                self.assertTrue(window._recovery_save_pending)
                facade.recovery_release.set()
                self._wait_for(
                    lambda: facade.recovery_calls == 2
                    and not window._recovery_save_in_flight
                )
                candidate = store.recovery_candidate()
                self.assertIsNotNone(candidate)
                assert candidate is not None
                self.assertEqual(candidate.source_path, source.resolve())
                self.assertEqual(candidate.source_sha256, SOURCE_SHA256)
                self.assertEqual(candidate.project_path, store.recovery_path)
                self.assertEqual(store.read().recent_projects, ())
            finally:
                if facade.recovery_release is not None:
                    facade.recovery_release.set()
                self._wait_for(lambda: not window._recovery_save_in_flight)
                window.deleteLater()
                self.application.processEvents()

    def test_stale_snapshot_completion_never_registers_under_new_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-stale-autosave-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            old_source = root / "old-game"
            old_source.mkdir()
            new_source = root / "new-game"
            new_source.mkdir()
            facade, window = self._window(store)
            try:
                facade.source_ready = True
                facade.source = SimpleNamespace(
                    selected_path=old_source.resolve(),
                    source_sha256=SOURCE_SHA256,
                )
                window._active_source_path = old_source.resolve()
                window._active_source_sha256 = SOURCE_SHA256
                facade.recovery_started = threading.Event()
                facade.recovery_release = threading.Event()
                window._mark_document_changed()
                self.assertTrue(facade.recovery_started.wait(2))

                # Simulate the post-load identity change before the old worker's
                # queued success signal is delivered. The stale archive may
                # exist privately, but it must never become advertised metadata.
                window._active_source_path = new_source.resolve()
                window._active_source_sha256 = "b6" * 32
                facade.source = SimpleNamespace(
                    selected_path=new_source.resolve(),
                    source_sha256="b6" * 32,
                )
                facade.recovery_release.set()
                self._wait_for(lambda: not window._recovery_save_in_flight)
                self.assertIsNone(store.recovery_candidate(require_source=False))
                self.assertEqual(store.read().recent_projects, ())
            finally:
                if facade.recovery_release is not None:
                    facade.recovery_release.set()
                window.deleteLater()
                self.application.processEvents()

    def test_new_source_never_overwrites_a_postponed_other_source_recovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-preserve-recovery-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            postponed_source = root / "postponed-game"
            postponed_source.mkdir()
            active_source = root / "active-game"
            active_source.mkdir()
            _empty_project(store.recovery_path, replace=True)
            candidate = store.register_recovery(
                source_path=postponed_source,
                source_sha256=SOURCE_SHA256,
                project_path=store.recovery_path,
            )
            original_archive = store.recovery_path.read_bytes()
            facade, window = self._window(store)
            try:
                facade.source_ready = True
                facade.source = SimpleNamespace(
                    selected_path=active_source.resolve(),
                    source_sha256=SOURCE_SHA256,
                )
                window._active_source_path = active_source.resolve()
                window._active_source_sha256 = SOURCE_SHA256
                window._mark_document_changed()
                self.application.processEvents()
                self.assertEqual(facade.recovery_calls, 0)
                self.assertFalse(window._recovery_save_in_flight)
                self.assertEqual(store.recovery_candidate(), candidate)
                self.assertEqual(store.recovery_path.read_bytes(), original_archive)
                self.assertIn("autosave is paused", window.operation_status.text())
            finally:
                window.deleteLater()
                self.application.processEvents()

    def test_failed_discarded_source_and_project_load_preserve_dirty_recovery(self) -> None:
        for route in ("source", "project"):
            with self.subTest(route=route), tempfile.TemporaryDirectory(
                prefix=f"apf-failed-{route}-"
            ) as temporary:
                root = Path(temporary)
                store = WorkspaceStateStore(root / "state")
                source = root / "active-game"
                source.mkdir()
                _empty_project(store.recovery_path, replace=True)
                store.register_recovery(
                    source_path=source,
                    source_sha256=SOURCE_SHA256,
                    project_path=store.recovery_path,
                )
                facade, window = self._window(store)
                try:
                    facade.source_ready = True
                    facade.source = SimpleNamespace(
                        selected_path=source.resolve(),
                        source_sha256=SOURCE_SHA256,
                    )
                    window._active_source_path = source.resolve()
                    window._active_source_sha256 = SOURCE_SHA256
                    window._document_dirty = True
                    started: list[str] = []

                    def failed_task(
                        label: str,
                        _operation: object,
                        _success: object,
                        _blocking: bool,
                    ) -> None:
                        # Failure means the success callback is never committed.
                        started.append(label)

                    window._run_task = failed_task  # type: ignore[method-assign]
                    with mock.patch.object(
                        window,
                        "_prompt_unsaved_decision",
                        return_value="discard",
                    ):
                        if route == "source":
                            replacement = root / "other-game"
                            replacement.mkdir()
                            window.load_source_path(replacement)
                        else:
                            project = _empty_project(
                                root / f"other{PROJECT_EXTENSION}"
                            )
                            window._request_project_load(project)
                    self.assertEqual(len(started), 1)
                    self.assertTrue(window._document_dirty)
                    self.assertIsNotNone(store.recovery_candidate())
                    self.assertEqual(window._active_source_path, source.resolve())
                finally:
                    window.deleteLater()
                    self.application.processEvents()

    def test_successful_source_swap_clears_only_the_previous_source_recovery(self) -> None:
        for recovery_owner in ("old", "other"):
            with self.subTest(recovery_owner=recovery_owner), tempfile.TemporaryDirectory(
                prefix=f"apf-source-swap-{recovery_owner}-"
            ) as temporary:
                root = Path(temporary)
                store = WorkspaceStateStore(root / "state")
                old_source = root / "old-game"
                old_source.mkdir()
                other_source = root / "other-game"
                other_source.mkdir()
                new_source = root / "new-game"
                new_source.mkdir()
                owner = old_source if recovery_owner == "old" else other_source
                _empty_project(store.recovery_path, replace=True)
                store.register_recovery(
                    source_path=owner,
                    source_sha256=SOURCE_SHA256,
                    project_path=store.recovery_path,
                )
                facade, window = self._window(store)
                try:
                    facade.source_ready = True
                    facade.source = SimpleNamespace(
                        selected_path=new_source.resolve(),
                        source_sha256=SOURCE_SHA256,
                        extracted_from_iso=False,
                        game_root=new_source.resolve(),
                    )
                    window._active_source_path = old_source.resolve()
                    window._active_source_sha256 = SOURCE_SHA256
                    window._document_dirty = True
                    with mock.patch.object(window, "_activate_page"):
                        window._source_loaded(
                            object(),
                            clear_previous_recovery=True,
                            previous_source_path=old_source.resolve(),
                            previous_source_sha256=SOURCE_SHA256,
                        )
                    candidate = store.recovery_candidate(require_source=False)
                    if recovery_owner == "old":
                        self.assertIsNone(candidate)
                    else:
                        self.assertIsNotNone(candidate)
                        assert candidate is not None
                        self.assertEqual(candidate.source_path, other_source.resolve())
                    self.assertFalse(window._document_dirty)
                    self.assertEqual(window._active_source_path, new_source.resolve())
                finally:
                    window.deleteLater()
                    self.application.processEvents()

    def test_successful_named_save_and_load_clear_only_active_source_recovery(self) -> None:
        for route in ("save", "load"):
            for recovery_owner in ("active", "other"):
                with self.subTest(
                    route=route, recovery_owner=recovery_owner
                ), tempfile.TemporaryDirectory(
                    prefix=f"apf-named-{route}-{recovery_owner}-"
                ) as temporary:
                    root = Path(temporary)
                    store = WorkspaceStateStore(root / "state")
                    active_source = root / "active-game"
                    active_source.mkdir()
                    other_source = root / "other-game"
                    other_source.mkdir()
                    owner = (
                        active_source
                        if recovery_owner == "active"
                        else other_source
                    )
                    _empty_project(store.recovery_path, replace=True)
                    store.register_recovery(
                        source_path=owner,
                        source_sha256=SOURCE_SHA256,
                        project_path=store.recovery_path,
                    )
                    project = _empty_project(
                        root / f"named-{route}{PROJECT_EXTENSION}"
                    )
                    facade, window = self._window(store)
                    try:
                        facade.source_ready = True
                        facade.source = SimpleNamespace(
                            selected_path=active_source.resolve(),
                            source_sha256=SOURCE_SHA256,
                        )
                        facade.last_project_identity = project_target_identity(
                            project
                        )
                        window._active_source_path = active_source.resolve()
                        window._active_source_sha256 = SOURCE_SHA256
                        window._document_dirty = True
                        with mock.patch.object(window, "_refresh_after_mutation"):
                            if route == "save":
                                window._project_saved(project)
                            else:
                                window._project_loaded(0, project)
                        candidate = store.recovery_candidate(
                            require_source=False
                        )
                        if recovery_owner == "active":
                            self.assertIsNone(candidate)
                        else:
                            self.assertIsNotNone(candidate)
                            assert candidate is not None
                            self.assertEqual(
                                candidate.source_path, other_source.resolve()
                            )
                        self.assertFalse(window._document_dirty)
                        self.assertEqual(
                            Path(store.read().recent_projects[0]),
                            project.resolve(),
                        )
                    finally:
                        window.deleteLater()
                        self.application.processEvents()

    def test_manual_recovery_accepts_file_or_directory_and_warns_when_missing(self) -> None:
        for kind in ("file", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(
                prefix=f"apf-manual-recovery-{kind}-"
            ) as temporary:
                root = Path(temporary)
                store = WorkspaceStateStore(root / "state")
                source = root / "source"
                if kind == "file":
                    source.write_bytes(b"iso")
                else:
                    source.mkdir()
                _empty_project(store.recovery_path, replace=True)
                candidate = store.register_recovery(
                    source_path=source,
                    source_sha256=SOURCE_SHA256,
                    project_path=store.recovery_path,
                )
                _facade, window = self._window(store)
                recovered: list[RecoveryCandidate] = []
                try:
                    with mock.patch.object(
                        window,
                        "_recover_candidate",
                        side_effect=recovered.append,
                    ):
                        window._recover_from_menu()
                    self.assertEqual(recovered, [candidate])
                    if source.is_dir():
                        source.rmdir()
                    else:
                        source.unlink()
                    with mock.patch(
                        "mod_editor.apf_studio.gui.QMessageBox.warning"
                    ) as warning:
                        window._recover_from_menu()
                    warning.assert_called_once()
                    self.assertIn(
                        "ISO or extracted game folder",
                        warning.call_args.args[2],
                    )
                finally:
                    window.deleteLater()
                    self.application.processEvents()

    def test_recovered_empty_document_is_unnamed_dirty_and_not_recent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-recovered-empty-") as temporary:
            root = Path(temporary)
            store = WorkspaceStateStore(root / "state")
            source = root / "source-folder"
            source.mkdir()
            _empty_project(store.recovery_path, replace=True)
            candidate = store.register_recovery(
                source_path=source,
                source_sha256=SOURCE_SHA256,
                project_path=store.recovery_path,
            )
            facade, window = self._window(store)
            try:
                facade.source_ready = True
                facade.source = SimpleNamespace(
                    selected_path=source.resolve(),
                    source_sha256=SOURCE_SHA256,
                )
                window._active_source_path = source.resolve()
                window._active_source_sha256 = SOURCE_SHA256
                window._active_project_path = root / f"old{PROJECT_EXTENSION}"
                window._active_project_identity = object()  # type: ignore[assignment]
                with mock.patch.object(window, "_refresh_after_mutation"):
                    window._project_loaded(
                        0, candidate.project_path, recovery=True
                    )
                self.assertIsNone(window._active_project_path)
                self.assertIsNone(window._active_project_identity)
                self.assertTrue(window._document_dirty)
                self.assertEqual(store.read().recent_projects, ())
                self.assertIsNotNone(store.recovery_candidate())
            finally:
                window.deleteLater()
                self.application.processEvents()

    def test_startup_recover_later_and_discard_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="apf-startup-recovery-") as temporary:
            root = Path(temporary)
            source = root / "source.iso"
            source.write_bytes(b"source")
            for decision in ("recover", "later", "discard"):
                with self.subTest(decision=decision):
                    store = WorkspaceStateStore(root / f"state-{decision}")
                    _empty_project(store.recovery_path, replace=True)
                    candidate = store.register_recovery(
                        source_path=source,
                        source_sha256=SOURCE_SHA256,
                        project_path=store.recovery_path,
                    )
                    _facade, window = self._window(store)
                    recovered: list[RecoveryCandidate] = []
                    try:
                        with mock.patch.object(
                            window,
                            "_prompt_recovery_decision",
                            return_value=decision,
                        ), mock.patch.object(
                            window,
                            "_recover_candidate",
                            side_effect=recovered.append,
                        ):
                            window._offer_startup_recovery()
                        if decision == "recover":
                            self.assertEqual(recovered, [candidate])
                            self.assertIsNotNone(store.recovery_candidate())
                        elif decision == "later":
                            self.assertEqual(recovered, [])
                            self.assertIsNotNone(store.recovery_candidate())
                        else:
                            self.assertEqual(recovered, [])
                            self.assertIsNone(
                                store.recovery_candidate(require_source=False)
                            )
                    finally:
                        window.deleteLater()
                        self.application.processEvents()

    def test_close_save_discard_cancel_handles_inflight_recovery(self) -> None:
        _facade, window = self._window()
        try:
            window._document_dirty = True
            window._recovery_save_in_flight = True
            discard = QCloseEvent()
            with mock.patch.object(
                window, "_prompt_unsaved_decision", return_value="discard"
            ):
                window.closeEvent(discard)
            self.assertFalse(discard.isAccepted())
            self.assertTrue(window._close_when_recovery_finishes)

            window._close_when_recovery_finishes = False
            window._document_dirty = True
            cancel = QCloseEvent()
            with mock.patch.object(
                window, "_prompt_unsaved_decision", return_value="cancel"
            ):
                window.closeEvent(cancel)
            self.assertFalse(cancel.isAccepted())
            self.assertTrue(window._document_dirty)

            save = QCloseEvent()
            with mock.patch.object(
                window, "_prompt_unsaved_decision", return_value="save"
            ):
                window.closeEvent(save)
            self.assertFalse(save.isAccepted())
            self.assertIsNotNone(window._after_recovery_action)
        finally:
            window._recovery_save_in_flight = False
            window.deleteLater()
            self.application.processEvents()

    def test_connectivity_excludes_audio_navigation_and_orders_cli_bootstrap(self) -> None:
        mark = inspect.getsource(ApfStudioMainWindow._mark_document_changed)
        self.assertIn("_save_recovery_snapshot", mark)
        self.assertNotIn("audio", mark.casefold())
        shortlist = inspect.getsource(
            # The shortlist route must stay session-only and never call the
            # main document mutation hook.
            __import__(
                "mod_editor.apf_studio.gui", fromlist=["InspectorBrowser"]
            ).InspectorBrowser._toggle_audio_shortlist
        )
        self.assertNotIn("modifiedChanged", shortlist)
        launcher = inspect.getsource(launch_studio)
        self.assertIn("offer_recovery and initial_source is None", launcher)
        self.assertIn("offer_matching_recovery=offer_recovery", launcher)
        self.assertIn("WorkspaceStateStore()", launcher)


if __name__ == "__main__":
    unittest.main()
