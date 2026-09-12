# Beta 66.1 H4: maumau78 paired edited glTF skeleton import

This section is the H4 handoff, after the historical entries above. Protected GUI and registry files were not edited. Apply `docs/mod_editor/nfl2k5_model_skeleton_gui.patch` to `mod_editor/gui/models_panel_qt.py`; the complete replacement functions and constructor blocks are below. The page currently has no 3D model preview, so there is no existing skeleton overlay to change. The checked result includes `skeleton_overlay` positions/parents for a future renderer.

Add beside the existing core Models import:

```python
from mod_editor.core.nfl2k5_model_skeleton import HELP as SKELETON_HELP
```

In `ModelsPanel._build`, insert immediately before `self.import_options_summary = QLabel("")`:

```python
        self.skeleton_mode = QComboBox()
        self.skeleton_mode.addItem("Geometry only", "geometry")
        self.skeleton_mode.addItem("Geometry and skeleton", "skeleton")
        self.skeleton_mode.setToolTip(SKELETON_HELP)
        self.skeleton_mode.currentIndexChanged.connect(self._invalidate_import)
        import_layout.addWidget(self.skeleton_mode)
```

In `_build`, replace the two input-path signal connections with these complete lines (at their existing creation points):

```python
        self.edited_field.textChanged.connect(self._invalidate_import)
        self.set_folder_field.textChanged.connect(self._invalidate_import)
```

In the existing `FEASIBILITY` string, replace `IMPORT (same-topology):` with `IMPORT, GEOMETRY ONLY (same-topology):`. Replace `_show_feasibility`'s information call with:

```python
        QMessageBox.information(self, "What can I change?", FEASIBILITY + "\n\nGEOMETRY AND SKELETON: " + SKELETON_HELP)
```

Add `_invalidate_import` to `ModelsPanel`; replace each other named function below in full. `set_report_text` remains at module scope. The mode defaults to Geometry only; changing mode invalidates any previous check. Checking a single selected glTF in skeleton mode checks its entire sibling folder, and a missing or unchanged other LOD fails with `edit both LOD files from one export`.

`_invalidate_import` complete block:

```python
    def _invalidate_import(self, *_args) -> None:
        self._compiled = self._compiled_set = None
        self._refresh()
```

`_refresh` complete block:

```python
    def _refresh(self) -> None:
        self.skeleton_mode.setEnabled(not self._busy)
        loaded = self._source is not None
        key = self.current_key()
        self.reload_button.setEnabled(not self._busy and (self._source_paths is not None or self._facade_paths() is not None))
        self.export_button.setEnabled(not self._busy and loaded and key is not None)
        self.open_button.setEnabled(self._last_export is not None)
        self.check_button.setEnabled(not self._busy and loaded and key is not None and bool(self.edited_field.text().strip()))
        body_set = self.current_body_set()
        self.export_set_button.setEnabled(not self._busy and loaded and body_set is not None)
        self.check_set_button.setEnabled(not self._busy and loaded and body_set is not None
                                         and bool(self.set_folder_field.text().strip()))
        if body_set is None:
            self.set_label.setText("A player is three models: High-detail body, low-detail body and head. "
                                   "Select any one of them (hi_body, lo_body or hi_head) to export or check all three.")
        else:
            self.set_label.setText("Body set: " + ", ".join(
                f"{models.BODY_SET_LABELS.get(e.name, e.name)} ({e.name})" for e in body_set.entries)
                + ". Export writes all three; Check the folder fits all three and writes them into ONE copy of the disc.")
        source = self.source_field.text().strip()
        target = self.target_field.text().strip()
        ready = self._compiled is not None or self._compiled_set is not None
        self.write_button.setEnabled(not self._busy and ready and bool(source) and bool(target)
                                     and Path(source) != Path(target))
```

`compile_edited` complete block:

```python
    def compile_edited(self, edited: Path) -> None:
        if self.skeleton_mode.currentData() == "skeleton":
            if self.current_body_set() is None:
                self._failed("non-player skeleton: select lo_body, hi_body or hi_head from outer 3")
                return
            self.compile_body_set(edited.parent)
            return
        key = self.current_key()
        if key is None or self._source is None:
            return
        source = self._source
        normals, uvs, rescale = self.normals_check.isChecked(), self.uvs_check.isChecked(), self.rescale_check.isChecked()
        colours = self.colours_check.isChecked()
        self._compiled = self._compiled_set = None
        self.status_label.setText(f"Fitting {edited.name} onto the game's vertices…")

        def operation() -> object:
            return models.compile_import(source, key, edited, write_normals=normals, write_uvs=uvs, allow_rescale=rescale,
                                         write_colours=colours)

        def done(result: object) -> None:
            assert isinstance(result, models.CompiledModelImport)
            self._compiled = result
            self.details.setPlainText(import_report_text(result))
            self.status_label.setText(f"Ready to write: {result.summary()}")
            self._refresh()

        self._run(operation, done)
```

`_write` complete block:

```python
    def _write(self) -> None:
        source = Path(self.source_field.text().strip())
        target = Path(self.target_field.text().strip())
        if target.exists() and self._compiled_set is not None and self._compiled_set.skeleton_plan is not None:
            self._failed("Choose a new output file distinct from the source for the coordinated skeleton copy")
            return
        if target.exists():
            answer = QMessageBox.question(self, "Replace the existing copy?",
                                          f"{target} already exists and will be replaced.",
                                          QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
            if answer != QMessageBox.Ok:
                return
        self.write_copy(source, target)
```

`compile_body_set` complete block:

```python
    def compile_body_set(self, folder: Path) -> None:
        import_skeleton = self.skeleton_mode.currentData() == "skeleton"
        body_set, source = self.current_body_set(), self._source
        if body_set is None or source is None:
            return
        normals, uvs, rescale = self.normals_check.isChecked(), self.uvs_check.isChecked(), self.rescale_check.isChecked()
        colours = self.colours_check.isChecked()
        self._compiled = self._compiled_set = None
        self.status_label.setText(f"Fitting the body set in {folder}…")

        def operation() -> object:
            return models.compile_body_set_import(source, body_set, folder, write_normals=normals, write_uvs=uvs,
                                                  allow_rescale=rescale, write_colours=colours,
                                                  import_skeleton=import_skeleton)

        def done(result: object) -> None:
            assert isinstance(result, models.CompiledModelSet)
            self._compiled_set = result
            self.details.setPlainText(set_report_text(result))
            self.status_label.setText(f"Ready to write: {result.summary()}")
            self._refresh()

        self._run(operation, done)
```

`set_report_text` complete block:

```python
def set_report_text(compiled: models.CompiledModelSet) -> str:
    if compiled.skeleton_plan is not None:
        receipt = compiled.skeleton_plan.receipt
        lines = [compiled.summary(), "", "Requested bone lengths (cm):"]
        for row in receipt["changed_bones"]:
            lines.append(f"{row['bone']}: {row['before_cm']:.5f} -> {row['after_cm']:.5f}")
        if not receipt["changed_bones"]:
            lines.append("No skeleton change; an untouched export is byte-identical.")
        lines += ["", "Every changed bind length, including regenerated high pivots (cm):"]
        for row in receipt["changed_bind_lengths"]:
            lines.append(f"{row['member']} / {row['bone']}: {row['before_cm']:.5f} -> {row['after_cm']:.5f}")
        lines += ["", "SKEL directions recomputed and checked against the retained canonical axes.",
                  "All four resources, including head and SKEL, are preflighted as one transaction.",
                  "Choose a new output disc path, then Make disc with this model.", "", SKELETON_HELP]
        return "\n".join(lines)
    lines = [f"Body set check: {compiled.summary()}", ""]
    for member in compiled.members:
        lines.append(f"{member.name}  ({Path(compiled.files.get(member.key, '')).name})")
        lines.append("  " + import_report_text(member).split("\n\n", 1)[0])
        for shape in member.shapes:
            lines.append(f"    • {shape.name}: {shape.positions_changed:,} moved (largest {shape.max_move_cm:.2f} cm), "
                         f"{shape.normals_changed:,} normals, {shape.uvs_changed:,} UVs, {shape.colours_changed:,} colours")
        for note in member.notes:
            lines.append(f"    - {note}")
        lines.append("")
    if compiled.notes:
        lines.extend(f"- {note}" for note in compiled.notes)
        lines.append("")
    lines += ["Nothing has been written yet. All three go into ONE copy of the disc: choose the source image and",
              "where to write the copy, then Write the copy. If any member could not fit, this check would have",
              "refused the whole set instead."]
    return "\n".join(lines)
```

## H4 registry field replacements

Modify the existing `nfl2k5.models.scne_gltf` object in `mod_editor/capabilities/registry.v1.json`. Do not create another capability. Keep classification `offline-writer-proved`, `runtime.status="not-tested"`, and the existing geometry/staging backend. These are the exact replacement field values (dotted keys identify the nested fields; they are not literal new keys):

```json
{
  "summary": "Export every NFL 2K5 SCNE as glTF and import fitted geometry into a disc copy. Player outer 3 additionally accepts one paired axial forearm, thigh, shin or foot bind-length edit within +/-5%, with regenerated high pivots, coordinated mesh/normals, recomputed and checked canonical SKEL directions, and a guarded low/high/head/SKEL transaction. EXPERIMENTAL / UNWITNESSED.",
  "gui.reason": "Models > Import edited .gltf/.glb defaults to Geometry only. Geometry and skeleton checks the complete sibling lo_body/hi_body/hi_head export set, reports every changed bind length in centimetres, and writes a new disc copy after all four native resources pass preflight. The GUI is exposed only after applying the complete H4 WIRING blocks.",
  "input_constraints": [
    "Geometry only retains the existing fitted vertex import: native vertex count, triangles, skeleton and weights stay authored; matched position, normal, UV and colour lanes can be re-encoded within a fixed compressed span.",
    "Geometry and skeleton requires pinned player SCNE 3/113 and 3/114, the pinned head 3/115, SKEL 3/116, all three model files and their manifest from one export, unchanged joint names/parents, and translations only. A missing or unedited second LOD refuses with edit both LOD files from one export.",
    "One axial length per import, 95%-105%: left/right forearm (both elbow-wrist and wrist-hand segments together), thigh, shin or foot. Distal primary positions must agree across LODs. High derived pivots are regenerated. Upper arms are disabled because the tested refits exceed their allocations. Hand tips, spine/neck/head, direction changes, rotations/scales, animation, topology/name changes, and multiple lengths are refused.",
    "Blender unit conversions are accepted within 0.001 cm; serialized canonical binds reparse within 0.0001 cm. Recomputed normalized directions must match canonical SKEL within 2e-6 per component. Head bind, weights, morph records, counts and angular muscle constants stay authored. Every resource must fit its original compressed span and scratch wrapper; the whole set is published together."
  ],
  "selectors.notes": "Every scene retains geometry export/import. The optional paired skeleton path is limited to player outer 3 and the eight named axial limb segments; arbitrary skeletons, directions, animation or body morph authoring are not implied.",
  "runtime.scope": "The H4 gate executes retail 0x92140/0x92252 and 0x233C0 on edited SCNE/SKEL inputs, compares authored rest joint positions, and compares recovered C and Python matrices at identity and six player celebration samples. Headless Blender 4.0.2 +5% forearm/thigh GLB edits are checked separately. Synthetic/direct-export no-op bytes, fixed spans, four-resource compact-copy transport, replay and refusals are tested. Idle/run/pass/catch/tackle, ball and helmet attachments, body sizes and played appearance remain UNWITNESSED.",
  "portme": [
    "Direction edits need a proved update of the fixed angular muscle graph. Hand terminal lengths and spine/neck/head need a proved endpoint/frame and attachment mapping.",
    "Upper-arm axial refits at +1%/+5% exceed the fixed compressed allocation. Multiple simultaneous lengths, arbitrary topology, animation and morph authoring remain unsupported.",
    "No claim for idle/run/pass/catch/tackle, body profiles, collision, ball/helmet attachment appearance or original hardware until witnessed."
  ],
  "validation_command": "python3 tests/mod_editor/test_nfl2k5_model_skeleton.py"
}
```

Append these paths to the row's `evidence` list, retaining the old geometry evidence:

```json
[
  "mod_editor/core/nfl2k5_model_skeleton.py",
  "tools/nfl2k5_model_skeleton_validate.py",
  "tools/nfl2k5_model_skeleton_blender_witness.py",
  "tests/mod_editor/test_nfl2k5_model_skeleton.py",
  "tests/mod_editor/test_models_skeleton_wiring.py",
  "docs/mod_editor/nfl2k5_model_skeleton.md",
  "docs/mod_editor/nfl2k5_model_skeleton_proof.json"
]
```

The existing geometry checkbox remains available by default; skeleton mode itself is EXPERIMENTAL and defaults off, not a preset change. Add `mod_editor/core/nfl2k5_model_skeleton.py` to the protected release allowlist so packaged Models body-set export can import its manifest helper. If optional proof tools/tests/docs are bundled, allowlist the exact additional files above according to the existing packaging policy. Run `python3 packaging/repin.py --apply` after wiring and regenerate the protected production source/cave manifest after integration; H4 introduces no executable cave or XBE write. `providers.py` includes the new core source pin.

GUI receipt and mode replay: `QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 tests/mod_editor/test_models_skeleton_wiring.py`. This applies the supplied patch in memory if the protected panel is still unwired and uses the real panel directly after integration. The existing Models panel suite was also replayed against the handoff. Registered does not mean rendered: the working tree intentionally leaves the protected panel and registry for Claude to wire.
