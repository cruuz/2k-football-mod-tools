# Beta 69 J2 integration

Branch `astra/b69-j2-models`. Direct owners are complete. Apply the exact patch
[docs/mod_editor/nfl2k5_model_project_wiring.patch](docs/mod_editor/nfl2k5_model_project_wiring.patch)
to the protected files below. The patch was executed in memory by
`tests/mod_editor/test_models_project_wiring.py`; it is not applied to these
protected files in this worktree.

## Protected shell and build functions

- `mod_editor/gui/studio_qt.py`, `StudioMainWindow._build_ui`: immediately
  after constructing `self._models_panel`, connect its `project_changed` signal
  to `_models_project_changed`. (The complete diff provides the exact containing
  method/context.) Add `_models_project_changed` immediately before
  `_mark_workspace_changed`. This marks dirty, refreshes the actual bottom bar,
  queues recovery saving and refreshes an already constructed Build panel.
- `mod_editor/gui/build_panel_qt.py`, `BuildPanel.confirmation_text`: after the
  existing shared-project Files entry, list `facade.model_project_plan` summaries
  and saved checked bytes. `BuildPanel.blocker`: after the reading-state check,
  use `validate_build_plan` for cheap Guardian conflict feedback. Hi-res file
  preflight stays in the worker, not the UI refresh loop.
- `mod_editor/core/mod_build.py`, `build_with_project`: validate model conflicts
  before calling `build` or the project service, capture `plan_rows(session)`, and
  add `project_models` to the combined receipt. Keep the existing order: project
  resources first, then gameplay/archive-growth writers, then publication.

The patch has complete code blocks, context and insertion points. No J1
error-surfacing or receipt-parser changes are included. Do not overwrite J1's
parallel changes when applying this branch.

## Registry: update one existing row, add zero rows

In `mod_editor/capabilities/registry.v1.json`, update the existing
`nfl2k5.models.scne_gltf` row. Preserve its current native-pose evidence and
constraints. Apply these field changes:

```python
row["summary"] = (
    "Export and check model geometry or bounded paired skeleton changes, then add "
    "one checked set to the project. Sparse compiled changes build with other "
    "project resources; all in-game outcomes remain UNWITNESSED."
)
row["gui"]["reason"] = (
    "Models > Check model / Check all three > Add model edit to project. The set "
    "is counted, saved, undoable and listed in Build & Share. Make disc with this "
    "model remains the quick path using the same fixed-span model writer."
)
row["input_constraints"].extend([
    "The project stores glTF/GLB and external-buffer paths, hashes and a checked "
    "sparse compiled change. Reopening rechecks those files; missing or changed "
    "files refuse rechecking with the path, while saved compiled bytes remain buildable.",
    "One staged edit per model set; adding another check for that set replaces "
    "its previous checked set and Undo restores it. Geometry only accepts a "
    "single LOD and retains the other LOD and both skeletons.",
    "Both skeleton LODs must come from one export with Custom Properties kept: "
    "Blender: File > Export > glTF 2.0 > Include > Data > Custom Properties. "
    "Separate native bind records make a single-LOD bone-length import unsafe.",
    "Project writers sharing an exact SCNE span compose disjoint decoded byte "
    "changes, refit once and reparse; conflicting or partial overlaps refuse. "
    "Guardian cap/overlay and selected hi-res resources that require the same "
    "retail model resources must be deselected before building."
])
row["evidence"].extend([
    "docs/mod_editor/nfl2k5_model_project_proof.json",
    "tests/mod_editor/test_nfl2k5_model_project.py",
    "tests/mod_editor/test_models_project_wiring.py"
])
row["validation_command"] = (
    "QT_QPA_PLATFORM=offscreen PYTHONPATH=. python3 "
    "tests/mod_editor/test_nfl2k5_model_project.py"
)
```

Classification remains `offline-writer-proved`; skeleton import stays manual,
EXPERIMENTAL and off by default. Do not add it to a preset. BASIC/ADVANCED/
EXPERIMENTAL build preset defaults are unchanged. This extends the existing
Models capability, so registry count pins change by **0**.

## Packaging and pins

Add these two source paths to `packaging/release-allowlist.txt` beside the Models
modules:

```text
mod_editor/core/nfl2k5_model_project.py
mod_editor/core/nfl2k5_model_project_session.py
```

The new backend import is pinned in `Nfl2k5UnifiedVisualProvider.module_pins`.
The exact backend closure is 272 files (was 271). The session extension belongs
to the app and is not part of the external backend closure. Repin after applying
the protected shell/build patch; the facade/runtime digest and provider source
pins in this branch were regenerated from actual bytes. The changed
`packaging/check_2k5_mod_studio_runtime.py` digest is solely repin output, not a
runtime-check logic change.

Regenerate the protected production source/cave manifest after integration.
These changes allocate no XBE cave and patch no executable bytes. Run packaging
and runtime gates after the allowlist and protected wiring land. Registered,
rendered and usable remain distinct: direct Models + facade + project build
code is installed here; the shell refresh and combined-plan receipt wiring are
proved by the exact in-memory handoff and still need application by Claude.
