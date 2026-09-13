# Beta 69 J1 integration

Branch `astra/b69-j1-equipment`; apply with J2. The build-service diff is only `_last_message`; J2 retains ownership of model integration. The dialog owner was granted and is already edited directly. Do not release until the following protected hooks are applied. All current in-game outcomes are UNWITNESSED.

## Build list and captions

`mod_editor/gui/build_panel_qt.py`, `BuildPanel._build_ui`, immediately after `root.addWidget(intro)`, insert:

```python
        self.project_includes_heading = QLabel("What this build includes")
        root.addWidget(self.project_includes_heading)
        self.project_includes_list = QPlainTextEdit()
        self.project_includes_list.setObjectName("buildProjectIncludes")
        self.project_includes_list.setReadOnly(True)
        self.project_includes_list.setMaximumHeight(200)
        self.project_includes_list.setPlaceholderText("No project edits. Selected Build options are listed below.")
        root.addWidget(self.project_includes_list)
        self.project_includes_note = QLabel(
            "Newest changes in this session first. Older project files do not record original edit times. "
            "The project edit index identifies the edit if a build refuses it.")
        self.project_includes_note.setWordWrap(True)
        root.addWidget(self.project_includes_note)
```

Replace the intro's stale sentence `This uses the selections on this tab; project edits (art, text, audio) use Make disc from project on their own pages.` with:

> This build includes the selected Build options and every edit listed below from the open project, including model edits after J2 integration. Equipment keeps the game's existing compressed allocation; larger equipment art is not available. Review each import's chosen size and colour-loss report.

Merge that caption with J2's final model implementation. Do not add an experimental growth checkbox or a preset flag: **no archive relocation route passed the required disc proof**. The isolated grown-chunk native proof does not enable this feature.

`mod_editor/gui/studio_qt.py`, add this complete `StudioMainWindow` method:

```python
    def _refresh_build_includes(self, *, baseline=False):
        from tools.nfl2k5_visual_mod_project import ProjectEditTimeline
        session = getattr(self.facade, "_session", None)
        if getattr(self, "_build_includes_session", None) is not session:
            self._build_includes_session = session
            self._build_includes_timeline = ProjectEditTimeline()
            baseline = bool(session and getattr(session, "modified_count", 0))
        if not hasattr(self, "_build_includes_timeline"):
            self._build_includes_timeline = ProjectEditTimeline()
        try:
            document = session.canonical_document() if session and session.modified_count else {"edits": []}
            rows = self._build_includes_timeline.observe(document, baseline=baseline)
            text = "\n".join(row["label"] for row in rows)
        except Exception as exc:
            text = f"The project edit list could not be read: {exc}. Resolve this before building."
        self._build_includes_text = text
        if self._build_panel is not None:
            self._build_panel.project_includes_list.setPlainText(text)
```

Call `_refresh_build_includes()` at the end of `_refresh_edit_state`, after `_build_panel` is created in the Build/Share workspace, and after restoring Build settings. At the end of `_load_project_path.success`, call `_refresh_build_includes(baseline=True)` so old archive rows are marked as chronology unknown. These calls do not modify canonical project order. `ProjectEditTimeline` uses canonical edit identity and observed changes, rather than pretending the canonical asset sort is creation order. J2's model rows must be in `session.canonical_document()`; the list then includes them automatically. Text-only edits also participate. Do not truncate the list or collapse global copies to one row: each project index remains visible.

## Try that actually reruns the import

Replace `StudioMainWindow._replace_visual_asset` with the exact complete method in [studio-equipment-method.py.txt](reports/b69_j1/studio-equipment-method.py.txt). It is reproduced here to make the final integration reviewable. The first worker returns `EquipmentFitError` as a structured result, the real dialog displays the measured alternative, and accepting it submits the same import worker again with the checked scale. No asset is staged by a failed check. Cancelling cleans any pending master draft.

```python
    def _replace_visual_asset(
        self,
        state: _VisualBrowserState,
        asset: ExtendedVisualAsset,
        path: Path,
        *,
        native_canvas_edit: Mapping[str, object] | None = None,
    ) -> None:
        if not asset.editable:
            self._show_error(
                "This texture is preview/export-only because its format has no "
                "proved fixed-span importer."
            )
            return
        fitted = self._fit_for_slot(path, asset.width, asset.height, asset.label)
        if fitted is None:
            return
        equipment_choice: tuple[bool, int, str] | None = None
        if asset.kind == "uniform_equipment_texture":
            from mod_editor.gui.equipment_texture_import_dialog import EquipmentTextureImportDialog

            dialog = EquipmentTextureImportDialog(asset, self)
            if dialog.exec_() != dialog.Accepted:
                return
            equipment_choice = (dialog.independent, dialog.scale, dialog.scope)
        existing_master = self._texture_master_drafts.get(asset.asset_id)
        pending_master: _TextureMasterDraft | None = None
        if native_canvas_edit is None:
            try:
                pending_master = self._prepare_texture_master_draft(
                    asset, path, fitted
                )
            except ValidationError as exc:
                self._show_error(
                    "The native import was not started because its full-resolution "
                    f"authoring source could not be preserved safely. {exc}"
                )
                return
        path = fitted

        def success(result: object) -> None:
            nonlocal equipment_choice
            from mod_editor.core.nfl2k5_uniform_equipment_writer import EquipmentFitError
            from mod_editor.gui.equipment_texture_import_dialog import EquipmentFitRetryDialog
            if isinstance(result, EquipmentFitError):
                retry = EquipmentFitRetryDialog(asset, result, self)
                if retry.exec_() == retry.Accepted and retry.scale is not None:
                    independent, _old_scale, scope = equipment_choice
                    equipment_choice = (independent, retry.scale, scope)
                    self._defer_until_blocking_task_finished(lambda: self._start_task(
                        replace_texture, success, label=f"Checking and replacing {asset.label}",
                        blocking=True, on_error=failed))
                else:
                    failed(str(result))
                return
            if getattr(result, "changed_asset_ids", None) == ():
                if pending_master is not None:
                    pending_master.source_image.unlink(missing_ok=True)
                    pending_master.native_baseline_png.unlink(missing_ok=True)
                self._set_status(_result_message(result, "Equipment artwork already matches."))
                return
            modified = bool(getattr(result, "modified", True))
            if native_canvas_edit is not None:
                if modified and existing_master is not None:
                    revision = int(
                        existing_master.editor_transform.get(
                            "native_canvas_edit_revision", 0
                        )
                    ) + 1
                    updated_editor_transform = dict(
                        existing_master.editor_transform
                    )
                    updated_editor_transform.update({
                        "native_canvas_edit": dict(native_canvas_edit),
                        "native_canvas_edit_revision": revision,
                    })
                    self._texture_master_drafts[asset.asset_id] = (
                        _TextureMasterDraft(
                            existing_master.source_image,
                            existing_master.source_sha256,
                            existing_master.native_baseline_png,
                            existing_master.transform,
                            updated_editor_transform,
                            True,
                        )
                    )
                elif not modified:
                    self._discard_texture_master_draft(asset.asset_id)
            elif modified and pending_master is not None:
                self._discard_texture_master_draft(asset.asset_id)
                self._texture_master_drafts[asset.asset_id] = pending_master
            else:
                if pending_master is not None:
                    pending_master.source_image.unlink(missing_ok=True)
                    pending_master.native_baseline_png.unlink(missing_ok=True)
                self._discard_texture_master_draft(asset.asset_id)
            self._set_status(_result_message(result, f"{asset.label} is ready to build."))
            state.selected_asset_id = asset.asset_id
            self._filter_visual_assets(state.category)
            self._mark_workspace_changed()
            self._load_visual_preview(asset, state.preview)

        def failed(_message: str) -> None:
            if pending_master is not None:
                pending_master.source_image.unlink(missing_ok=True)
                pending_master.native_baseline_png.unlink(missing_ok=True)

        def replace_texture(progress: ProgressSink) -> object:
            if equipment_choice is not None:
                independent, scale, scope = equipment_choice
                from mod_editor.core.nfl2k5_uniform_equipment_writer import EquipmentFitError
                try:
                    return self.facade.replace_equipment_texture(
                        asset, path, progress, independent=independent, scale=scale, scope=scope,
                    )
                except EquipmentFitError as exc:
                    return exc
            return self.facade.replace_asset(asset, path, progress)

        self._start_task(
            replace_texture,
            success,
            label=f"Checking and replacing {asset.label}",
            blocking=True,
            on_error=failed if pending_master is not None else None,
        )
```

## Project-load and complete consumer preflight

`mod_editor/studio/session.py`, `StudioSession.load_shareable_project`: immediately inside the `try:` following `loaded = load_project_archive(...)`, before `new_play_routes` or any session mutation, insert:

```python
            from mod_editor.core.nfl2k5_uniform_equipment_writer import preflight_project_equipment
            preflight_project_equipment(self.cache.pack0, [
                (None, row.asset.asset_id, row.staged_path)
                for row in loaded.edits
                if getattr(row.asset, "kind", None) == "uniform_equipment_texture"
            ])
```

These archive rows and pending imports are not the canonical build list, so pass `None` instead of inventing a project edit index. The canonical CLI preflight retains its original indices.

`LoadedProjectEdit.staged_path` is confirmed against its dataclass at project_archive.py:187. Preserve the existing `loaded.cleanup()` finally. The load task's error is inline; do not add a QMessageBox to this path. The helper tests full grouped compilation, while skipping pack-wide receipt hashes, and accepts both historical PNG-only recolours and npTC/v1 own textures. It never silently shrinks or discards a restored edit. A canonical CLI consumer can use `read_project(path, equipment_index=pack0)` for the same load preflight. Normal build and receipt verification retain their compile-cache behavior; the receipt verifier never recompiles.

`mod_editor/core/nfl2k5_equipment_import.py`, `stage_equipment_import`: pass `fit_asset_id=asset.asset_id` to the existing selected-group `build_unified_uniform_equipment_imports` call. Then, immediately before `result = session.replace_batch(tuple(rows), label="Import equipment texture")`, still inside the temporary-directory context, insert:

```python
        from mod_editor.core.nfl2k5_uniform_equipment_writer import preflight_project_equipment
        incoming = {row_asset.asset_id: row_path for row_asset, row_path in rows}
        complete = {edit.asset_id: edit.replacement_path for edit in session.iter_edits()
                    if edit.asset_id in by_id and edit.asset_id not in incoming}
        if not restoring:
            complete.update(incoming)
        preflight_project_equipment(session.cache.pack0, [
            (None, asset_id, png) for asset_id, png in sorted(complete.items())
        ])
```

This closes a second checked boundary gap: the current function compiles the selected package before fanning out to all global consumers, while `replace_batch` validates PNGs but does not compile those other packages. The all-groups load check catches restored records, and this import check catches differing consumer budgets before publishing new edits. A refusal in another consumer still names that consumer; do not imply that a selected-package fit proves all other packages fit. Keep this initial all-consumer refusal as a named error rather than retrying a different edit through the selected asset's dialog.

In the same module, replace `PACKAGE_LOCAL_SHOE_HELP` with an import alias:

```python
from .nfl2k5_equipment_import_intent import SHOE_ROUTE_HELP as PACKAGE_LOCAL_SHOE_HELP
```

Replace `CONTEXT_FIRST_RULE` with:

```python
CONTEXT_FIRST_RULE = (
    "Native lookup checks the selected HOME/AWAY package, with separate clean and dirty artwork. "
    "A missing local texture falls back to the newest loaded package. In-game outcome UNWITNESSED.")
```

The owned import dialog already uses `SHOE_ROUTE_HELP`, including maumau78's unresolved Bears report. Updating the core alias also corrects receipt/help consumers outside that dialog.

## Registry and packaging

Replace only the rows with IDs `nfl2k5.textures.all_p8` and `nfl2k5.uniforms.all_visual` using the complete objects in [registry-rows.json](reports/b69_j1/registry-rows.json). They retain all existing backend fields, selectors and validation commands, narrow the native claim, and add the new tests/report. **Zero rows added; registry/product count pins do not change.** Keep the pre-existing aggregate runtime states (including the unrelated Detroit torso witness); the equipment evidence explicitly remains UNWITNESSED. Bump relief remains global and is unchanged.

No new runtime module, compiled helper or release-allowlist entry is needed. `tools/nfl2k5_b69_equipment_probe.py` is a repository research command, not a runtime dependency. Do not ship its private inputs or any retail output. The existing dialog and all changed core/tool owners are already allowlisted.

Run `python3 packaging/repin.py --apply` after each integrated pinned edit and the existing full packaged runtime/release gates. ASTRA_CONTEXT requests a cave-manifest regeneration after pinned-writer edits; do it during integration. This job changes no XBE bytes, allocations, REQUESTS or cave ownership, so no reservation change is expected. Keep J2's integration changes in the shared build service.

For the inline load refusal, change the existing `_start_task` at the end of `StudioMainWindow._load_project_path` to:

```python
        self._start_task(
            lambda progress: self.facade.load_project(source, progress),
            success,
            label="Opening and validating the project",
            blocking=True,
            show_errors=False,
        )
```

The existing task handler displays the complete cause in the status area; it must not open a load-path QMessageBox. The retry callback is deferred until the first blocking task finishes, so the second import does not hit the task guard.
