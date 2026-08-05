"""Headless document-workflow and protected fast-save tests for 2K5 Mod Studio."""

from __future__ import annotations

import inspect
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock
import zipfile

from mod_editor.core.errors import ValidationError
from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
from mod_editor.studio.facade import StudioOperationResult
from mod_editor.studio import project_archive as project_archive_module
from mod_editor.studio.project_archive import (
    ProjectTargetIdentity,
    load_project_archive,
    project_target_identity,
    save_project_archive,
)


class _UnusedCatalog:
    def get_asset(self, _asset_id: str) -> object:
        raise AssertionError("An empty project must not resolve a retail asset")


def _save_empty_project(
    destination: Path,
    *,
    replace: bool = False,
    expected_target: ProjectTargetIdentity | None = None,
    allow_empty: bool = True,
) -> Path:
    return save_project_archive(
        catalog=_UnusedCatalog(),
        asset_io=object(),
        edits=(),
        destination=destination,
        replace=replace,
        expected_target=expected_target,
        allow_empty=allow_empty,
    )


class ProjectTargetSafetyTests(unittest.TestCase):
    def test_explicit_empty_project_is_replacement_only_and_default_stays_strict(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-empty-document-") as temporary:
            root = Path(temporary)
            refused = root / "accidental-empty.2k5mod"
            with self.assertRaisesRegex(ValidationError, "at least one edit"):
                _save_empty_project(refused, allow_empty=False)
            self.assertFalse(refused.exists())

            project = _save_empty_project(root / "intentional-empty.2k5mod")
            with zipfile.ZipFile(project) as archive:
                self.assertEqual(archive.namelist(), ["project.json"])
                manifest = json.loads(archive.read("project.json"))
            self.assertEqual(manifest["edits"], [])
            self.assertIs(manifest["empty_project"], True)
            self.assertEqual(manifest["payload_policy"], "user-replacements-only")
            self.assertNotIn("source", manifest)
            self.assertNotIn("original", manifest)

            loaded = load_project_archive(
                source=project,
                catalog=_UnusedCatalog(),
                asset_io=object(),
                private_root=root / "private",
            )
            staging_root = loaded.staging_root
            try:
                self.assertEqual(loaded.edits, ())
                self.assertIsNone(loaded.text_replacements)
                self.assertEqual(loaded.audio_edits, ())
                self.assertEqual(loaded.audio_annotations, ())
            finally:
                loaded.cleanup()
            self.assertFalse(staging_root.exists())

    def test_empty_project_marker_is_strict_and_cannot_mask_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-empty-marker-") as temporary:
            root = Path(temporary)
            base = {
                "edits": [],
                "game": project_archive_module.PROJECT_GAME,
                "payload_policy": "user-replacements-only",
                "schema": project_archive_module.PROJECT_SCHEMA,
            }
            cases = {
                "missing": dict(base),
                "false": {**base, "empty_project": False},
                "null": {**base, "empty_project": None},
                "conflict": {
                    **base,
                    "empty_project": True,
                    "edits": [{"not": "a valid edit"}],
                },
            }
            for name, manifest in cases.items():
                with self.subTest(name=name):
                    project = root / f"{name}.2k5mod"
                    with zipfile.ZipFile(project, "w") as archive:
                        archive.writestr(
                            "project.json",
                            (json.dumps(manifest, sort_keys=True) + "\n").encode(),
                        )
                    with self.assertRaises(ValidationError):
                        load_project_archive(
                            source=project,
                            catalog=_UnusedCatalog(),
                            asset_io=object(),
                            private_root=root / f"private-{name}",
                        )

    def test_fast_save_replaces_only_the_exact_remembered_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-fast-save-") as temporary:
            root = Path(temporary)
            project = _save_empty_project(root / "Named Mod.2k5mod")
            first = project_target_identity(project)

            self.assertEqual(
                _save_empty_project(
                    project, replace=True, expected_target=first
                ),
                project,
            )
            second = project_target_identity(project)
            self.assertNotEqual(first, second)

            external = b"externally changed project bytes"
            project.write_bytes(external)
            with self.assertRaisesRegex(ValidationError, "changed outside"):
                _save_empty_project(
                    project, replace=True, expected_target=second
                )
            self.assertEqual(project.read_bytes(), external)
            self.assertEqual(
                list(root.glob(f".{project.name}.*.tmp")), []
            )

    def test_missing_and_linked_fast_save_targets_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-fast-save-path-") as temporary:
            root = Path(temporary)
            project = _save_empty_project(root / "Named Mod.2k5mod")
            identity = project_target_identity(project)

            project.unlink()
            with self.assertRaisesRegex(ValidationError, "missing.*Save Project As"):
                _save_empty_project(
                    project, replace=True, expected_target=identity
                )
            self.assertFalse(project.exists())

            outside = root / "outside-user-file"
            outside.write_bytes(b"keep me")
            project.symlink_to(outside)
            with self.assertRaisesRegex(ValidationError, "Save Project As"):
                _save_empty_project(
                    project, replace=True, expected_target=identity
                )
            self.assertTrue(project.is_symlink())
            self.assertEqual(outside.read_bytes(), b"keep me")
            with self.assertRaisesRegex(ValidationError, "regular, non-linked"):
                project_target_identity(project)


class ProjectArchiveBoundTests(unittest.TestCase):
    @staticmethod
    def _manifest(*, visual: list[dict[str, str]] | None = None,
                  audio: list[dict[str, str]] | None = None) -> dict[str, object]:
        document: dict[str, object] = {
            "edits": visual or [],
            "game": project_archive_module.PROJECT_GAME,
            "payload_policy": "user-replacements-only",
            "schema": project_archive_module.PROJECT_SCHEMA,
        }
        if audio is not None:
            document["audio_edits"] = audio
        return document

    @staticmethod
    def _write_archive(
        path: Path, document: dict[str, object],
        members: tuple[tuple[str, bytes], ...] = (),
    ) -> Path:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "project.json",
                (json.dumps(document, sort_keys=True) + "\n").encode("utf-8"),
            )
            for name, payload in members:
                archive.writestr(name, payload)
        return path

    def test_load_rejects_total_expansion_before_reading_payload_members(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-project-expanded-") as temporary:
            root = Path(temporary)
            source = self._write_archive(
                root / "expanded.2k5mod",
                self._manifest(),
                (("undeclared-large.bin", b"x" * 4096),),
            )
            with zipfile.ZipFile(source) as archive:
                expanded = sum(info.file_size for info in archive.infolist())
            private = root / "private"
            private.mkdir()
            with mock.patch.object(
                project_archive_module, "MAX_PROJECT_EXPANDED_BYTES", expanded - 1
            ):
                with self.assertRaisesRegex(ValidationError, "expands beyond"):
                    load_project_archive(
                        source=source,
                        catalog=_UnusedCatalog(),
                        asset_io=object(),
                        private_root=private,
                    )
            self.assertEqual(tuple(private.iterdir()), ())

    def test_combined_visual_and_audio_edit_limit_is_one_shared_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-project-count-") as temporary:
            root = Path(temporary)
            visual_id = "nfl2k5.uniform.synthetic"
            audio_id = "nfl2k5.audio.audo.o0003.c0001"
            source = self._write_archive(
                root / "too-many.2k5mod",
                self._manifest(
                    visual=[{
                        "asset_id": visual_id,
                        "file": "replacements/" + hashlib.sha256(
                            visual_id.encode("utf-8")
                        ).hexdigest() + ".png",
                        "png_sha256": "0" * 64,
                        "rgba_sha256": "1" * 64,
                    }],
                    audio=[{
                        "asset_id": audio_id,
                        "file": "audio/" + hashlib.sha256(
                            audio_id.encode("utf-8")
                        ).hexdigest() + ".wav",
                        "wav_sha256": "2" * 64,
                    }],
                ),
            )
            private = root / "private"
            private.mkdir()
            with mock.patch.object(project_archive_module, "MAX_PROJECT_EDITS", 1):
                with self.assertRaisesRegex(ValidationError, "combined visual and audio"):
                    load_project_archive(
                        source=source,
                        catalog=_UnusedCatalog(),
                        asset_io=object(),
                        private_root=private,
                    )
                with self.assertRaisesRegex(ValidationError, "combined visual and audio"):
                    save_project_archive(
                        catalog=_UnusedCatalog(),
                        asset_io=object(),
                        edits=(object(),),
                        audio_edits=(object(),),
                        destination=root / "save-too-many.2k5mod",
                    )
            self.assertFalse((root / "save-too-many.2k5mod").exists())

    def test_save_rejects_hardlinked_audio_and_aggregate_payload_overflow(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-project-audio-bound-") as temporary:
            root = Path(temporary)
            supplied = root / "authored.wav"
            supplied.write_bytes(b"authored synthetic wav")
            linked = root / "linked.wav"
            os.link(supplied, linked)
            edit = SimpleNamespace(
                asset_id="nfl2k5.audio.audo.o0003.c0001",
                replacement_path=linked,
                replacement_sha256=hashlib.sha256(linked.read_bytes()).hexdigest(),
            )
            with self.assertRaisesRegex(ValidationError, "unsafe or too large"):
                save_project_archive(
                    catalog=_UnusedCatalog(),
                    asset_io=object(),
                    edits=(),
                    audio_edits=(edit,),
                    destination=root / "linked.2k5mod",
                )
            self.assertFalse((root / "linked.2k5mod").exists())

            linked.unlink()
            edit.replacement_path = supplied
            with mock.patch.object(
                project_archive_module,
                "MAX_PROJECT_REPLACEMENT_BYTES",
                supplied.stat().st_size - 1,
            ):
                with self.assertRaisesRegex(ValidationError, "1 GiB combined"):
                    save_project_archive(
                        catalog=_UnusedCatalog(),
                        asset_io=object(),
                        edits=(),
                        audio_edits=(edit,),
                        destination=root / "aggregate.2k5mod",
                    )
            self.assertFalse((root / "aggregate.2k5mod").exists())


class ActiveProjectWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt5.QtWidgets import QApplication

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
        self.facade.modified_count = 0
        self.facade.modified_asset_ids = frozenset()
        self.facade.can_undo = True
        self.calls: list[dict[str, object]] = []

        def save_project(
            destination: Path,
            progress: object,
            *,
            replace: bool = False,
            expected_target: ProjectTargetIdentity | None = None,
            allow_empty: bool = False,
        ) -> StudioOperationResult:
            progress("Saving fixture project", 0, 1)  # type: ignore[operator]
            path = _save_empty_project(
                destination,
                replace=replace,
                expected_target=expected_target,
                allow_empty=allow_empty,
            )
            identity = project_target_identity(path)
            self.calls.append({
                "path": path,
                "replace": replace,
                "expected_target": expected_target,
                "allow_empty": allow_empty,
            })
            progress("Fixture project saved", 1, 1)  # type: ignore[operator]
            return StudioOperationResult("Fixture project saved.", path, identity)

        self.facade.save_project = save_project  # type: ignore[method-assign]

        def immediate(
            operation: object,
            on_success: object,
            **_keywords: object,
        ) -> None:
            result = operation(lambda *_args: None)  # type: ignore[operator]
            on_success(result)  # type: ignore[operator]

        self.window._start_task = immediate  # type: ignore[method-assign]
        self.window._refresh_edit_state()

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.application.processEvents()

    def test_source_switch_invalidates_audio_before_task_and_blocks_panel(
        self,
    ) -> None:
        audio = self.window._audio_panel
        self.assertIsNotNone(audio)
        events: list[tuple[object, ...]] = []
        audio.invalidate_preview_for_source_change = (  # type: ignore[method-assign]
            lambda: events.append(("invalidate", audio.isEnabled()))
        )
        audio.recover_after_source_change_failure = (  # type: ignore[method-assign]
            lambda: events.append(("recover", audio.isEnabled()))
        )
        captured_error: list[object] = []

        def queued(
            _operation: object,
            _on_success: object,
            **keywords: object,
        ) -> None:
            events.append(
                ("start", keywords.get("blocking"), audio.isEnabled())
            )
            captured_error.append(keywords.get("on_error"))

        self.window._start_task = queued  # type: ignore[method-assign]
        self.window._load_source_path(Path("/fixture/new-source.xiso"))
        self.assertEqual(
            events,
            [("invalidate", True), ("start", True, True)],
        )
        self.assertEqual(len(captured_error), 1)
        self.assertTrue(callable(captured_error[0]))
        captured_error[0]("synthetic source refusal")  # type: ignore[operator]
        self.assertEqual(events[-1], ("recover", True))

        self.window._set_busy(True, "Opening fixture source")
        self.assertFalse(audio.isEnabled())
        self.window._set_busy(False)
        self.assertTrue(audio.isEnabled())

    def test_first_source_load_failure_restores_empty_audio_state(self) -> None:
        audio = self.window._audio_panel
        self.assertIsNotNone(audio)
        self.facade.source_ready = False
        audio.invalidate_preview_for_source_change()
        audio.count_label.setText("Updating audio results…")
        audio.range_label.setText("Waiting for the new search and filters…")

        audio.recover_after_source_change_failure()

        self.assertEqual(audio.count_label.text(), "Load your NFL 2K5 XISO")
        self.assertEqual(audio.range_label.text(), "0 results")
        self.assertEqual(audio.table.rowCount(), 0)
        self.assertIsNone(audio.selected_asset_id)
        self.assertFalse(audio.previous_button.isEnabled())
        self.assertFalse(audio.next_button.isEnabled())
        self.assertFalse(audio.export_matching_button.isEnabled())

    def test_unnamed_save_as_then_named_fast_save_uses_no_dialog(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-window-document-") as temporary:
            project = Path(temporary) / "My Active Mod.2k5mod"
            self.window._mark_workspace_changed()
            self.assertEqual(
                self.window.windowTitle(), "Untitled* — 2K5 Mod Studio"
            )
            self.assertTrue(self.window.save_project_button.isEnabled())
            self.assertTrue(self.window._save_project_as_action.isEnabled())

            with mock.patch.object(
                self.window,
                "_workspace_state",
                return_value=SimpleNamespace(recent_projects=()),
            ), mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getSaveFileName",
                return_value=(str(project), "2K5 Mod Studio project (*.2k5mod)"),
            ) as choose:
                self.window._save_project()
            choose.assert_called_once()
            self.assertEqual(self.window._active_project_path, project.resolve())
            self.assertEqual(
                self.window.windowTitle(), "My Active Mod.2k5mod — 2K5 Mod Studio"
            )
            self.assertFalse(self.window._workspace_dirty)

            remembered = self.window._active_project_identity
            self.window._mark_workspace_changed()
            with mock.patch(
                "mod_editor.gui.studio_qt.QFileDialog.getSaveFileName"
            ) as choose_again:
                self.window._save_project()
            choose_again.assert_not_called()
            self.assertIs(self.calls[-1]["expected_target"], remembered)
            self.assertTrue(self.calls[-1]["replace"])
            self.assertTrue(self.calls[-1]["allow_empty"])
            self.assertFalse(self.window._workspace_dirty)

    def test_revert_all_after_named_save_is_dirty_and_can_save_empty(self) -> None:
        with tempfile.TemporaryDirectory(prefix="2k5-revert-document-") as temporary:
            project = _save_empty_project(Path(temporary) / "Saved Mod.2k5mod")
            self.window._active_project_path = project
            self.window._active_project_identity = project_target_identity(project)
            self.facade.modified_count = 1
            self.window._workspace_dirty = False
            self.window._refresh_edit_state()

            # This is the state after the saved project's final replacement is
            # reverted. The current edit count is zero, but the document differs
            # from its last named save and must not silently close.
            self.facade.modified_count = 0
            self.window._mark_workspace_changed()
            self.assertTrue(self.window._workspace_dirty)
            self.assertEqual(self.window.edit_count.text(), "No edits • unsaved")
            self.assertEqual(
                self.window.windowTitle(), "Saved Mod.2k5mod* — 2K5 Mod Studio"
            )
            self.assertTrue(self.window.save_project_button.isEnabled())
            self.assertTrue(self.window._save_project_action.isEnabled())
            self.assertTrue(self.window._save_project_as_action.isEnabled())
            self.assertFalse(self.window.build_button.isEnabled())

            self.window._save_project()
            self.assertFalse(self.window._workspace_dirty)
            with zipfile.ZipFile(project) as archive:
                manifest = json.loads(archive.read("project.json"))
            self.assertEqual(manifest["edits"], [])

    def test_close_uses_the_same_fast_save_dispatch(self) -> None:
        source = inspect.getsource(StudioMainWindow.closeEvent)
        self.assertIn(
            "self._save_project(after_success=self._finish_close_after_save)",
            source,
        )
        self.assertNotIn("_choose_save_project", source)
        self.assertEqual(
            self.window._save_project_action.shortcut().toString(), "Ctrl+S"
        )
        self.assertEqual(
            self.window._save_project_as_action.shortcut().toString(),
            "Ctrl+Shift+S",
        )

    def test_accepted_close_removes_private_texture_master_workspace(self) -> None:
        private_workspace = self.window._texture_master_root
        self.assertTrue(private_workspace.is_dir())

        self.assertTrue(self.window.close())
        self.application.processEvents()

        self.assertFalse(private_workspace.exists())
        self.assertFalse(self.window._texture_master_finalizer.alive)


if __name__ == "__main__":
    unittest.main()
