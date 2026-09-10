# WIRING: Beta 65 job C (positions)

## Beta 65 job C — EDGE-only creation and MyCareer position evidence

Integration for branch `astra/b65-positions`. The protected GUI/build/registry/manifest files have not been edited. These changes complete the existing options; do not add a separate position patch or a “Run your own routes” checkbox. The route/mesh/animation evidence does not justify that control mode. Classification remains **EXPERIMENTAL**, with no new preset enabled by this job.

### 1. Protected MyCareer picker

In `mod_editor/gui/my_career_panel_qt.py`, `MyCareerPanel.__init__`, immediately after `self.setup_path = ""`, insert:

```python
self._position_scheme = "retail"
self.position_pools_enabled = lambda: False
```

Replace the `range(career.POSITION_COUNT)` position-population loop with:

```python
for code, short, long_name in career.position_choices(self._position_scheme):
    self.position.addItem(f"{short} ({long_name})", code)
```

Add these methods to `MyCareerPanel`:

```python
def set_position_pools(self, enabled):
    scheme = "one_pool" if enabled else "retail"
    if scheme == self._position_scheme:
        return
    old_code = self.position.currentData()
    old_variant = self.template.currentData()
    self._position_scheme = scheme
    code = roster.replacement_position_code(old_code or 0, scheme)
    self.position.blockSignals(True)
    try:
        self.position.clear()
        for value, short, long_name in career.position_choices(scheme):
            self.position.addItem(f"{short} ({long_name})", value)
        self.position.setCurrentIndex(max(0, self.position.findData(code)))
    finally:
        self.position.blockSignals(False)
    self._position_changed()
    variant_index = self.template.findData(old_variant)
    if variant_index >= 0:
        self.template.setCurrentIndex(variant_index)

def showEvent(self, event):
    self.set_position_pools(bool(self.position_pools_enabled()))
    super().showEvent(event)
```

In `_position_changed`, use `career.templates_for(code, scheme=self._position_scheme)`. The old “no retail template” fallback is unreachable for valid positions now that all 51 entries are recognized; remove it. Replace its final status assignment with:

```python
self.contract.setText(f"{group}: {proved}. {hypothesis}. This build's rendered play is unwitnessed.")
```

Also replace the initial `self.result` label in `__init__` with:

```python
self.result = QLabel("Both options are off in all presets. Noah reports QB play works; this build's position behavior still needs a gameplay witness.")
```

In `_create`'s `options` dictionary add `scheme=self._position_scheme`. The API returns the visible scheme name in `receipt['position']`; the existing v2 setup JSON intentionally retains the retail label for compatibility with `read_setup`. Never populate picker rows by enumerating all aliases in `POSITION_CODE_BY_TEXT`.

In `mod_editor/gui/studio_qt.py`, add:

```python
def _sync_mycareer_position_scheme(self, *_args):
    panel = getattr(self, "_my_career_panel", None)
    build = getattr(self, "_build_panel", None)
    if panel is None or build is None:
        return
    def enabled():
        return (build.position_pools_check.isChecked()
                or (getattr(build, "_state", None) or {}).get("position_pools") == "applied")
    panel.position_pools_enabled = enabled
    panel.set_position_pools(enabled())
```

Call `_sync_mycareer_position_scheme()` after constructing the MyCareer panel and after constructing the Build panel (either can be created first). Connect `self._build_panel.position_pools_check.toggled` to it in `_build_build_share_page`. Call it at the **start**, before the early return, of `_gameplay_build_changed`. `showEvent` also accounts for an already-patched source whose Build checkbox is disabled/unchecked.

Protected GUI acceptance: retail picker codes 0..16, pools picker codes 0..9/11..16; exactly one EDGE and one LB; no OLB/DE/ILB rows; toggling back restores enum 10. EDGE templates are Power/Speed/Balanced EDGE. All OL/DT positions have three native templates. `_create` forwards the scheme and preserves the selected template variant. Test with `QT_QPA_PLATFORM=offscreen`; add these assertions to `tests/mod_editor/test_nfl2k5_my_career_panel.py` when wiring lands. Its current retail-template assertions were corrected in this branch.

### 2. Protected Build row and final roster certification

The core `pools.apply()` now defaults to compact selectors. Explicit `roster_has_olb=True` is retained as the old low-level compatibility profile and tested, but **must not be the EDGE-only product path**. It deliberately exposes enum-10 players; exact-enum native count/getters cannot merge an arbitrary external save merely by removing a tab.

In `mod_editor/gui/build_panel_qt.py`, replace the position-pools row label/helper arguments with:

```python
self.position_pools_check = self._option(
    r, "position_pools", "Use EDGE and LB throughout position pickers",
    "Create Player and MyPlayer skip OLB; EDGE combines DE and OLB template ratings. "
    "Roster, draft, scouting, free-agency and depth choices use the merged pools. "
    "Requires reclassified rosters. EXPERIMENTAL / UNWITNESSED.", needs_image=True)
```

Retain the `position_pools_keep_olb_check` object/key only for old project deserialization, hide it, and force it false. Replace `_sync_keep_olb` with:

```python
def _sync_keep_olb(self, pools_on):
    keep = getattr(self, "position_pools_keep_olb_check", None)
    if keep is not None:
        keep.setChecked(False)
        keep.setEnabled(False)
        keep.hide()
```

Remove the old compatibility helper text/layout row as well; hiding only the checkbox leaves its explanatory row visible. In `plan()`, emit `position_pools_keep_olb=False`. Preserve all existing prerequisite selection for EDGE rename, scheme labels and roster reclassification.

In `mod_editor/core/mod_build.py`, `_build`, after the boolean type validation for `position_pools_keep_olb`, replace the compatibility condition with:

```python
if plan.position_pools_keep_olb:
    raise ValueError("The EDGE-only pools build requires reclassified rosters; rebuild an old compatibility project with Keep Outside Linebackers off")
```

In the final `if run_olb_filter:` block, retain the complete scan after all ROST writers. Replace `keep_olb = ...` and its `pools_final.apply` call with:

```python
if scan["roster_has_olb"] is not False:
    raise ValueError("The EDGE-only position build still contains enum-10 players or an incomplete roster scan; reclassify every selectable roster before building")
xbe, filter_receipt = pools_final.apply(_xbe_bytes(target), roster_has_olb=False)
```

The initial in-progress `pools.apply(..., roster_has_olb=True)` can remain until the final roster scan; the user receives only the completed certified build. Do not silently remove filters on unconverted custom rosters. External saves loaded later are not certified by a disc scan: they require reclassification before use with this profile. No runtime migration is claimed.

### 3. Registry rows and status strings

Update existing IDs, rather than registering overlapping writers. In `mod_editor/capabilities/registry.v1.json`, amend `nfl2k5_xbox.position_pool_filters` with these fields (retain its other schema fields):

```json
{
  "title": "EDGE and LB position pickers and templates",
  "summary": "EXPERIMENTAL / UNWITNESSED. Pools skips OLB in native Create Player/MyPlayer, merges DE/OLB ratings under EDGE, and compacts sixteen filters plus the trade-needs picker. Requires reclassified rosters.",
  "validation_command": "python3 -m tests.mod_editor.test_nfl2k5_position_choices",
  "input_constraints": [
    "Pinned USA callbacks, long-name sites, all 51 native template records and sixteen complete selector tables; foreign bytes refuse.",
    "Certify all 76 disc ROST resources after final roster edits. External enum-10 saves require reclassification. The legacy retained-row API is outside this EDGE-only product profile."
  ],
  "selectors": {
    "fields": [{"allowed": "complete EDGE-only position-pools build", "name": "position_pools", "required": true}],
    "notes": "One selectable EDGE (16), one LB (11); enum 10 is retired. Native counts/getters retain exact-enum semantics."
  },
  "portme": ["Apply Beta 65 job C WIRING.md and regenerate the protected reservation manifest.", "Witness position cycling, templates and every listed selector in game."]
}
```

Append to its evidence array:

```json
["ASTRA_REPORT.md", "docs/mod_editor/nfl2k5_b65_positions_evidence.json", "tests/mod_editor/test_nfl2k5_position_choices.py"]
```

For both `nfl2k5.mode.my_career` and `nfl2k5.mode.my_career_inline`, append the same report/evidence JSON plus `tests/mod_editor/test_nfl2k5_my_career_position_inputs.py`. Replace the old constraint claiming that C/G/T/DT/DE have no templates with:

```text
All 17 retail positions have three native Create Player templates; the pools profile offers 16 live positions and merges EDGE ratings. Position-specific input decode and switch guards are bounded-native proofs; mesh movement, manual routes, catches and block animations remain unwitnessed outside Noah's reported QB play.
```

Keep runtime status `not-tested` for the new build. Do not register “Run your own routes”: no safe body-specific FPF switch was proved. The reader tool is development evidence and needs no shipped app action, dependency or release-allowlist addition.

### 4. RC89 changelog bullets

In `docs/mod_editor/2k5_mod_studio_changelog.md`, under `## v1.0 RC89, beta 65`, add:

```markdown
- With merged position pools, Create Player and MyPlayer cycle through EDGE and LB without an OLB entry. EDGE has Power, Speed and Balanced templates drawn from the game's DE and OLB ratings; roster, draft, scouting, free-agency and trade-needs selectors skip the retired row. The completed build requires reclassified rosters.
- MyCareer now uses the game's native templates for offensive linemen and defensive linemen instead of substituting 65s. Its position descriptions distinguish proved input handling from unwitnessed routes, mesh movement, catches and blocking. No speculative first-person control flag is enabled.
```

### 5. Ownership, packaging and integration checks

`packaging/repin.py --apply` was run; this branch changes seven provider pins (including the Contracts editor compatibility recognizer). Regenerate **protected** `data/nfl2k5_cave_reservations.json` after integration. The native cycle writes at `0x345560/0x345590` require manifest coverage; the inline runtime shrinks within the existing reservation. No owner allocation or `.text` runtime data was added. The private manifest and exact local gate results are in `ASTRA_REPORT.md`.

After wiring, run the new choices/input suites, the updated offscreen panel suite, registry validation and the final XBE/oracle/pairwise gates. Also verify a Build with pools off retains both native cycle functions and all template-rating records byte-for-byte. Do not repin a foreign writer to make a gate pass.
