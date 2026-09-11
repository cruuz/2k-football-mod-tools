# Beta 66 job D2 integration handoff

## Beta 66 D2: collection bounds, paired intent and helmet finish

This section supersedes the old paired-read-option/QB-spy refusal handoff.
Implementation and instruction-level evidence: `ASTRA_REPORT.md`. No protected
file was edited by D2. Pairing stays EXPERIMENTAL and false in every preset.
Helmet finish is ADVANCED, Glossy (retail) by default in every preset.

### D1 music collection integration

The new core dependency is already installed in the unprotected metadata
writer. Preserve these lines when merging D1's dedicated collection changes:

```python
from . import nfl2k5_jukebox_list as jukebox_list
# In status(), an otherwise recognized expanded metadata owner requires:
if jukebox_list.status(payload) != "applied":
    return "foreign"
# In apply(), after the shared allocation and before returning the result:
payload, collection_list_receipt = jukebox_list.apply(payload)
```

Use the actual D2 implementation's local variable names/receipt nesting; the
snippet describes the exact dependency, not a second application. Its repair
has no collection-number literal. Do not replace it with a check for Incite #2
or the new Custom collection. `test_nfl2k5_jukebox_list.py` executes the whole
native list build for both collection slots and 59 through 200 songs. Add its
new backend to packaging even when the new UI collection comes from D1.

### Protected mod_build paired refusal

In `mod_editor/core/mod_build.py`, `_build`, delete this whole block (old line
1083), after the generic MyCareer draft-AI dependency:

```python
if plan.playbook_pair and (plan.read_option_runtime or plan.qb_spy):
    raise ValueError(tt.PLAYBOOK_PAIR_CONFLICT)
```

Remove the obsolete “refuses with read option / QB spy” wording from the
`BuildPlan.playbook_pair` comment. Three corresponding core throw-tuning
refusals are already removed. Its old message constant is temporarily retained
so the protected caller raises its normal refusal until this handoff lands.
Keep all existing final authored-table, signature and capacity checks. The
pair, read and spy owners must reserve their combined request union before any
owner is applied. The paired runtime table lives at `pair.contract_va(payload)`;
never hard-code a different union's address into the GUI or builder.

Replace the central registry object `nfl2k5.gameplay.playbook_pair` with
`docs/mod_editor/nfl2k5_playbook_pair_capability.json`. Its updated input
constraints and evidence describe the active contract. Keep all presets off.

### Protected mod_build Helmet finish field and final executable pass

In `BuildPlan`, adjacent to `uniform_choice`, add:

```python
helmet_finish: str = "glossy"  # ADVANCED; matte is off in every preset
```

Add `"helmet_finish": "glossy"` to each preset dictionary, including when a
preset is applied over an existing plan. Add
`or self.helmet_finish == "matte"` to `wants_xbe_patch()`. In the first-pass
`replace(plan, depth_chart_rows=False, ...)` expression near old line 1293,
add `helmet_finish="glossy"`: the final pass below owns this field, so it must
not make the initial throw-tuning pass run with no supported arguments.
Serialization uses the existing `asdict` recipe path.

At the beginning of `_build`, before any copy/write, add:

```python
if plan.helmet_finish not in ("glossy", "matte"):
    raise ValueError("Helmet finish must be glossy or matte")
if _core_module("nfl2k5_helmet_finish") is None:
    if plan.helmet_finish == "matte":
        raise RuntimeError("Helmet finish writer is not available in this build")
```

In `availability()`'s returned dict add the independent backend check:

```python
"helmet_finish": _core_module("nfl2k5_helmet_finish") is not None,
```

After the final `if plan.music_library:` rebuild block and before
`inspection = inspect(target, screen_timing=plan.screen_timing)`, add:

```python
finish = _core_module("nfl2k5_helmet_finish")
if finish is not None:
    current = _xbe_bytes(target)
    if plan.helmet_finish == "matte" or finish.status(current) == "applied":
        patched, finish_receipt = finish.apply(current, finish=plan.helmet_finish)
        _write_xbe_bytes(target, patched)
        finish.verify(_xbe_bytes(target), finish=plan.helmet_finish)
        receipt["steps"].append({"step": "helmet_finish", **finish_receipt})
```

This works for the existing loose-XBE and image transport helpers and reparses
the actual output. The final-pass placement permits both Guardian orders and
retains the finish through a music image rebuild. Choosing Glossy on an already
recognized Matte input restores the retail branches while retaining Guardian.

In `inspect(source, ...)`, after `out` is constructed and before returning it:

```python
finish = _core_module("nfl2k5_helmet_finish")
out["helmet_finish"] = finish.status(_xbe_bytes(Path(source))) if finish else "unavailable"
```

No allocator requests, archive material refit or texture copy is necessary.
Do not expose the writer as a flat-texture replacement; it controls the native
A/B/C material weight refresh.

### Protected Gameplay / Uniforms controls

Add this row to `mod_editor/gui/gameplay_patches_panel_qt.py`'s `PATCHES` and to
the Uniforms/equipment subset used by the main window (one shared recipe key):

```python
("helmet_finish", "Helmet finish",
 "ADVANCED / UNWITNESSED. Glossy (retail) keeps helmet reflections. "
 "Matte sets shell reflection weight to zero in both LODs. Rebuild to compare."),
```

Add to `LABELS`:

```python
"helmet_finish": ("Helmet finish", "Both helmet LODs; game appearance needs a witness.",
                  "ADVANCED / UNWITNESSED"),
```

In `GameplayPatchesPanel._build_ui`, inside the row loop after the checkbox is
created and before the existing selector cases, add:

```python
if key == "helmet_finish":
    self.helmet_finish_combo = QComboBox()
    self.helmet_finish_combo.setAccessibleName("Helmet finish")
    self.helmet_finish_combo.addItem("Glossy (retail)", "glossy")
    self.helmet_finish_combo.addItem("Matte", "matte")
    self.helmet_finish_combo.currentIndexChanged.connect(
        lambda index, box=check: box.setChecked(index == 1))
    check.toggled.connect(
        lambda on, combo=self.helmet_finish_combo: combo.setCurrentIndex(1 if on else 0))
    head.addWidget(self.helmet_finish_combo)
```

In `plan()`'s checkbox dispatch, before the `screen_timing` case, add:

```python
if key == "helmet_finish":
    plan.helmet_finish = "matte" if on else "glossy"
elif key == "screen_timing":
    # existing screen_timing body
```

Where preset choices are reflected into checks, use
`choices.get("helmet_finish", "glossy") == "matte"` for this key rather than
truth-testing the string `"glossy"`. The inspection states remain the existing
`retail`/`applied`/`foreign` vocabulary. Do not add this key to `NEEDS_IMAGE`;
it also works on a loose XBE. Both the Gameplay row and the Uniforms access
must read/write the same BuildPlan key, including project save/reopen.

Integration acceptance: offscreen main-window checks must cover both controls,
Glossy default in all presets, Matte-only build, Matte+Guardian in both orders,
Glossy restoration, project roundtrip, output reparse and an absent backend.
Do not claim “rendered” or “usable in the shipped UI” until those checks run.

### Registry, distribution and manifest

Merge `docs/mod_editor/nfl2k5_helmet_finish_capability.json` as capability
`nfl2k5.uniforms.helmet_finish`. Keep its runtime status `not-tested`; bounded
native execution is not a console witness. The collection fix is a dependency
of music import, not a new optional checkbox. Add its test/report evidence to
the existing music-library capability rather than claiming a separate music
feature with no control.

Add to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_jukebox_list.py
mod_editor/core/nfl2k5_helmet_finish.py
docs/mod_editor/nfl2k5_helmet_finish_capability.json
docs/mod_editor/nfl2k5_beta66_d2_validation.json
```

The proposal files retain developer test/report references. Before copying
these two rows into the **distribution** registry, use their packaged public
evidence paths so staged file validation does not require private scratch or
developer tests:

```python
for row in (playbook_pair_row, helmet_finish_row):
    proposal = ("nfl2k5_playbook_pair_capability.json" if row["id"] ==
                "nfl2k5.gameplay.playbook_pair" else "nfl2k5_helmet_finish_capability.json")
    row["evidence"] = ["docs/mod_editor/" + proposal,
                       "docs/mod_editor/nfl2k5_beta66_d2_validation.json"]
    row["runtime"]["evidence"] = ["docs/mod_editor/nfl2k5_beta66_d2_validation.json"]
```

Keep `runtime.status="not-tested"` and the scope text. The public evidence
contains commands, counts and hashes only; it does not contain retail bytes.

The two new dependency pins are already added to `providers.py`. Include both
modules in any explicit frozen imports alongside music_metadata and
Guardian. Existing pair/read/spy generated modules and updated pair capability
must ship together. Do not package `.scratch/`, the extraction symlink or
private resource inventories.

**Regenerate the protected cave manifest** after merging all jobs. New live
reservations: jukebox `0x32A159..0x32A169`, `0x32A24F..0x32A255`; helmet
`0x8FB43..0x8FB45`, `0x8FB4E..0x8FB50`, `0x8FB59..0x8FB5B`. These are occupied
live instructions, not caves. Existing pair/read/spy allocation sizes do not
change; regenerate source hashes and observed code spans. The test-only
allocator projection adds only the exact fully verified new live spans and
checks other-owner overlap; it does not modify the product manifest.
Retain `Recorder.observe`'s metadata-to-jukebox delegation: the metadata parent
receipt contains the child's writes, whose exact verified spans must keep the
`nfl2k5_jukebox_list` owner when both writers are observed. The new standalone
receipt test checks that attribution. The gate groups the two Crib loop edits
as one completely pinned function when checking external entries; these are
still live instructions and never become allocatable space.

Run both XBE gates, oracle and the expanded 28-owner pairwise matrix after the
protected wiring. Run standalone collection, paired-intent, helmet, music
metadata, pair/read/spy and Guardian suites as listed in `ASTRA_REPORT.md`.
No BASIC playoff-starter fix or general skeleton-import control is handed off:
their exact instruction-level blockers remain in the report.

### Build & Share / project persistence for the same Helmet finish choice

The Gameplay row must also be represented by the central Build panel; otherwise
`GameplayBuildLink.shared` will omit it and a project reopen will lose it.
In protected `mod_editor/gui/build_panel_qt.py`, beside the jersey selector:

```python
self.helmet_finish_check = self._option(
    g, "helmet_finish", "Matte helmet finish (advanced)",
    "Both LODs. Native reflection weight is zero; appearance is unwitnessed.")
self.helmet_finish_combo = QComboBox()
self.helmet_finish_combo.setAccessibleName("Helmet finish")
self.helmet_finish_combo.addItem("Glossy (retail)", "glossy")
self.helmet_finish_combo.addItem("Matte", "matte")
self.helmet_finish_combo.currentIndexChanged.connect(
    lambda i: self.helmet_finish_check.setChecked(i == 1))
self.helmet_finish_check.toggled.connect(
    lambda on: self.helmet_finish_combo.setCurrentIndex(1 if on else 0))
g.addWidget(self.helmet_finish_combo)
```

Add `"helmet_finish": self.helmet_finish_check` to `_boxes()`,
`helmet_finish="matte" if self.helmet_finish_check.isChecked() else "glossy"`
to the BuildPlan construction in `plan()`. In `apply_state()`, use this
dedicated reversible-choice gate instead of the generic retail-only gate:

```python
finish_state = str(state.get("helmet_finish"))
finish_available = self._available.get("helmet_finish", False)
finish_enabled = finish_available and finish_state in ("retail", "applied")
self.helmet_finish_check.setEnabled(finish_enabled)
self.helmet_finish_combo.setEnabled(finish_enabled)
self.helmet_finish_check.setChecked(finish_state == "applied")
self.helmet_finish_combo.setCurrentIndex(1 if finish_state == "applied" else 0)
self._set_badge("helmet_finish", "ADVANCED / UNWITNESSED" if finish_enabled else
                "Unrecognized source data" if finish_available else "Not available in this release")
```
In `BuildPanel.apply_preset`, replace the `want = ...` expression inside the
`for key, box in boxes.items()` loop with:

```python
want = (values[key] == "matte" if key == "helmet_finish" else
        values[key] != "retail" if key in ("music_policy", *r62_ui.LEVELS) else
        bool(values[key]))
```

Then set the combo to 1/0 from that boolean. Add the following helper to both
panels, and add `or self._helmet_finish_changed()` to BuildPanel's
`has_work()` predicate. This permits a Glossy-only restoration build:

```python
def _helmet_finish_changed(self):
    combo = getattr(self, "helmet_finish_combo", None)
    state = (self._state or {}).get("helmet_finish")
    return bool(combo is not None and combo.isEnabled()
                and state in ("retail", "applied")
                and combo.currentData() != ("matte" if state == "applied" else "glossy"))
```

In GameplayPatchesPanel's `apply_state()` loop, immediately after
`check = self.checks[key]`, add:

```python
if key == "helmet_finish":
    enabled = value in ("retail", "applied")
    check.setEnabled(enabled)
    self.helmet_finish_combo.setEnabled(enabled)
    check.setChecked(value == "applied")
    self.helmet_finish_combo.setCurrentIndex(1 if value == "applied" else 0)
    self.badges[key].setText("ADVANCED / UNWITNESSED" if enabled else "Unrecognized source data")
    self.badges[key].setVisible(True)
    continue
```

In that panel's `_refresh()` and `_write()`, replace the checkbox-only
selection test with
`any(c.isChecked() for key, c in self.checks.items() if key != "helmet_finish") or self._helmet_finish_changed()`.
In both panels' selected-change labels, handle this key before the generic
checked-box branch: append `"Helmet finish: " + self.helmet_finish_combo.currentText()`
only when `_helmet_finish_changed()`, then continue. Thus Glossy restoration
is shown in the confirmation and an unchanged Matte input is not counted as
a new edit. The checkbox/combo wiring makes existing shared-key
synchronization work, but blocked project restoration also needs this key.

In `mod_editor/core/nfl2k5_build_settings.py`, add `"helmet_finish"` beside
`"uniform_choice"` in the persisted field-name tuple; in `build_settings()`
after defaults are merged, add:

```python
tt._require(choices["helmet_finish"] in ("glossy", "matte"),
            "Helmet finish must be glossy or matte")
```

In protected `mod_editor/gui/gameplay_project_ui.py`, `restore()`, the
`box.setChecked` conditional must handle
`value == "matte" if key == "helmet_finish"` before its generic `bool(value)`.
Add `("helmet_finish_combo", choices["helmet_finish"])` to the restore combo
loop. Add `"helmet_finish_combo"` to both combo-name tuples in
`GameplayBuildLink.__init__` and `_levels` so quiet restore updates both views.

For an actual Uniforms tab rather than a registry-only entry, in
`StudioMainWindow`'s Uniforms & Equipment tab construction, after Bump Maps:

```python
helmet_page = QWidget()
helmet_layout = QVBoxLayout(helmet_page)
helmet_layout.addWidget(QLabel("Helmet finish applies to both teams and both LODs."))
self._uniform_helmet_finish = QComboBox()
self._uniform_helmet_finish.setAccessibleName("Helmet finish")
self._uniform_helmet_finish.addItem("Glossy (retail)", "glossy")
self._uniform_helmet_finish.addItem("Matte", "matte")
helmet_layout.addWidget(self._uniform_helmet_finish)
helmet_layout.addWidget(QLabel("ADVANCED / UNWITNESSED. Build & Share writes this choice into a new copy."))
helmet_layout.addStretch(1)
uniform_tabs.addTab(helmet_page, "Helmet finish")
self._connect_helmet_finish()
```

Add the following method and call it also at the end of
`_connect_gameplay_build()` once the Build panel exists:

```python
def _connect_helmet_finish(self):
    build = getattr(self, "_build_panel", None)
    combo = getattr(self, "_uniform_helmet_finish", None)
    if build is None or combo is None or getattr(self, "_helmet_finish_linked", False):
        return
    self._helmet_finish_linked = True
    combo.currentIndexChanged.connect(build.helmet_finish_combo.setCurrentIndex)
    build.helmet_finish_combo.currentIndexChanged.connect(combo.setCurrentIndex)
    combo.setCurrentIndex(build.helmet_finish_combo.currentIndex())
```

After the existing project restore and preset restore blocks (which suppress
signals), explicitly refresh the Uniforms combo from
`self._build_panel.helmet_finish_combo.currentIndex()` when both widgets exist.
The combo's enabled state must follow Build's helmet availability/source gate.
This creates one stored value, mirrored in Gameplay, Build and Uniforms.
