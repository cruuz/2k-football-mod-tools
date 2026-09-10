# Beta 65 A — Accelerated Clock integration

Fresh handoff for `astra/b65-accel-clock`. The earlier job's WIRING was intentionally deleted.
`ASTRA_CONTEXT.md` assigns the shared dispatcher, GUI, registry, release allowlist and production cave
manifest to Claude. Those product surfaces are not edited here. This branch delivers the build-time XBE
writer, generated native code, native proofs, ownership tests, changelog and getting-started paragraph.
No in-game Game Settings row is delivered. Do not label the feature rendered or played.

## Product choice and defaults

Classification: **ADVANCED, opt-in modern gameplay**. Keep **Off / 20 seconds in all three presets**.
All seven mandatory native cases pass; the brief permits Advanced On/20, but this handoff chooses Off until
Noah witnesses a game. Add one checkbox, `Accelerated clock (Madden style)`, and one adjacent combo,
`Minimum Play Clock Time`, with 25 / 20 / 15 / 10 / 5 s. The checkbox is the Off/On control, not a slider.
Changing the minimum while Off must not enable the patch. Preserve the choice in project save/load.

The Studio must skip both requests and writer when Off. That makes the feature's Off contribution
byte-identical to the native build. The standalone writer also supports an installed Off word; native
execution proves that those wrappers preserve engine stores and register results.

## BuildPlan and build routing — `mod_editor/core/mod_build.py`

Add beside `cpu_money_downs` in `BuildPlan`:

```python
accelerated_clock: bool = False
accelerated_clock_minimum_seconds: int = 20
```

Add to each `PRESETS` dictionary (`softdrink_basic`, `softdrink_advanced`, `softdrink_experimental`):

```python
"accelerated_clock": False, "accelerated_clock_minimum_seconds": 20,
```

In `BuildPlan.wants_xbe_patch()`, `_build()`'s allocator condition (currently beside
`plan.cpu_money_downs != "retail"`), and `_build()`'s final owner-install condition, add the respective term:

```python
or self.accelerated_clock  # wants_xbe_patch
or plan.accelerated_clock  # both plan predicates
```

Add to `availability()`'s `(key, module)` tuple list:

```python
("accelerated_clock", "nfl2k5_accelerated_clock"),
```

Add `"accelerated_clock", "accelerated_clock_settings"` to the `inspect()` state-key projection.
The `_r62_plan_options()` and `_validated_r62_plan_options()` paths then forward/validate both fields
through the updated `tt.R62_RUNTIME_KEYS` below. The `build()` deferred `replace(plan, ...)` call before
`wants_xbe_patch()` must set `accelerated_clock=False` with the other deferred owners. Preserve the minimum
there: it is a valid remembered choice and is needed when the final owner union installs.

The final `_selected_space_requests(..., **tt._r62_space_options(r62))` includes the owner before any
allocation. Do not append it after another writer has sealed a smaller union.

## Shared XBE dispatcher — `mod_editor/core/nfl2k5_throw_tuning.py`

Add beside the money-downs import:

```python
from . import nfl2k5_accelerated_clock as accelerated_clock_patch
```

Add `"accelerated_clock"` to `R62_SPACE_KEYS`. Add both `"accelerated_clock"` and
`"accelerated_clock_minimum_seconds"` to `R62_RUNTIME_KEYS`. The minimum does not affect allocation size.

Add these keyword defaults to `_validate_r62_options`, `_apply_all`, `write_xbe_copy`, `write_image_copy`:

```python
accelerated_clock=False, accelerated_clock_minimum_seconds=20,
```

Add only `accelerated_clock=False` to `_selected_space_requests` and `_xbe_space_adapter.__init__`.
Forward that flag in `_selected_space_requests`' call to `_validate_r62_options` and the adapter's call
to `_selected_space_requests`:

```python
accelerated_clock=accelerated_clock,
```

At the beginning of `_validate_r62_options`:

```python
accelerated_clock_patch.encode_options(
    enabled=accelerated_clock,
    minimum_seconds=accelerated_clock_minimum_seconds,
)
```

Append to `_selected_space_requests`' returned tuple sum:

```python
+ (accelerated_clock_patch.REQUESTS if accelerated_clock else ())
```

Include `or accelerated_clock` in `_xbe_space_adapter.__init__`'s `self.scaleout` predicate (RO option
storage needs the scale-out pools), `_apply_all`'s `xbe_space` owner condition, and the initial
"any selected patch" guards in both copy entry points. `_deferred_r62_options` already clears boolean
space keys; leave the minimum untouched. The existing `_r62_options` / `_r62_space_options` forwarding
must remain in all paths, including `write_image_copy`'s final full owner allocation.

Add beside `_cpu_money_downs_adapter`:

```python
class _accelerated_clock_adapter:
    status = staticmethod(accelerated_clock_patch.status)

    def __init__(self, minimum_seconds):
        self.minimum_seconds = minimum_seconds

    def apply(self, payload):
        return accelerated_clock_patch.apply(
            payload, enabled=True, minimum_seconds=self.minimum_seconds)
```

In `_apply_all`, after option validation and before any byte mutation, reject a changed installed choice:

```python
clock_state = accelerated_clock_patch.status(payload)
_require(clock_state != "foreign", "Accelerated-clock prerequisites are foreign")
if clock_state == "applied":
    installed_clock = accelerated_clock_patch.verify(payload)
    _require(
        installed_clock["enabled"] == accelerated_clock
        and installed_clock["minimum_seconds"] == accelerated_clock_minimum_seconds,
        "Accelerated-clock options differ; rebuild from a verified base",
    )
```

In `_grown_status_fields`, compute a safe settings projection before the returned dictionary and add
the two fields (foreign status must not call `verify()`):

```python
clock_state = accelerated_clock_patch.status(payload)
clock_settings = (accelerated_clock_patch.verify(payload)
                  if clock_state != "foreign" else None)
# Inside the return dictionary:
"accelerated_clock": clock_state,
"accelerated_clock_settings": clock_settings,
```

Add this tuple to `_apply_all`'s final owner loop, after the allocator step:

```python
(accelerated_clock,
 _accelerated_clock_adapter(accelerated_clock_minimum_seconds),
 "accelerated_clock_patch", accelerated_clock_patch.BUILD_CAPTION),
```

The receipt reparses the installed words and code. Keep `runtime_witnessed=False` in the result.
No in-game slider, runtime option menu, or .text data is involved.

## Project persistence — `mod_editor/core/nfl2k5_build_settings.py`

Add to `FEATURE_KEYS`:

```python
"accelerated_clock", "accelerated_clock_minimum_seconds",
```

Its existing `defaults()` and BuildPlan round trip preserve the settings, and `build_settings()` calls
`tt._validate_r62_options` to reject nonboolean On/Off, noninteger minima and unsupported choices.

## Gameplay and Build controls

In `mod_editor/gui/beta62_options.py`, add to `OPTIONS` (the minimum is not another checkbox key):

```python
("accelerated_clock", tt.accelerated_clock_patch.BUILD_CAPTION,
 tt.accelerated_clock_patch.HELP_TEXT),
```

In `GameplayPatchesPanel.__init__` (`gameplay_patches_panel_qt.py`), beside the money-downs combo in the
row-building loop, insert:

```python
if key == "accelerated_clock":
    self.accelerated_clock_minimum = QComboBox()
    for seconds in tt.accelerated_clock_patch.MINIMUM_SECONDS:
        self.accelerated_clock_minimum.addItem(f"{seconds} s", seconds)
    self.accelerated_clock_minimum.setCurrentIndex(
        self.accelerated_clock_minimum.findData(20))
    self.accelerated_clock_minimum.setAccessibleName("Minimum Play Clock Time")
    self.accelerated_clock_minimum.setToolTip("Minimum Play Clock Time")
    self.accelerated_clock_minimum.currentIndexChanged.connect(lambda _i: self._refresh())
    head.addWidget(QLabel("Minimum Play Clock Time"))
    head.addWidget(self.accelerated_clock_minimum)
```

In `GameplayPatchesPanel.plan()`, after the generic checkbox loop:

```python
plan.accelerated_clock_minimum_seconds = int(self.accelerated_clock_minimum.currentData())
```

The generic loop already assigns `plan.accelerated_clock`. In `_refresh()`, beside the money-downs
installed-setting block, use this block; it never silently rewrites a project's uninstalled choice:

```python
clock = self.checks["accelerated_clock"]
installed = (self._state or {}).get("accelerated_clock_settings")
combo = self.accelerated_clock_minimum
if installed and installed["status"] == "applied":
    clock.blockSignals(True)
    clock.setChecked(installed["enabled"])
    clock.blockSignals(False)
    combo.blockSignals(True)
    combo.setCurrentIndex(combo.findData(installed["minimum_seconds"]))
    combo.blockSignals(False)
    clock.setEnabled(False)
    combo.setEnabled(False)
else:
    combo.setEnabled(clock.isEnabled() and clock.isChecked())
```

In `build_panel_qt.py`, the existing `r62_ui.OPTIONS` loop creates `self.accelerated_clock_check` and
includes it in `_boxes()` and `plan()`. Create the same combo after that loop, using the six combo setup
lines above, and `g.addWidget(QLabel("Minimum Play Clock Time")); g.addWidget(self.accelerated_clock_minimum)`
as separate Python statements. Connect `currentIndexChanged` to `_refresh()`. Add the same plan assignment
after the `r62_ui.KEYS` loop. In Build's `_refresh()`, use the installed-settings block above with
`clock = self.accelerated_clock_check`. The existing `_boxes()` loop owns availability/foreign state.

In Build's preset application, beside the reset of `cpu_money_downs_level`, restore the minimum under a
signal blocker. Use the preset dictionary named `values` in that method:

```python
self.accelerated_clock_minimum.blockSignals(True)
self.accelerated_clock_minimum.setCurrentIndex(
    self.accelerated_clock_minimum.findData(values["accelerated_clock_minimum_seconds"]))
self.accelerated_clock_minimum.blockSignals(False)
```

In `mod_editor/gui/gameplay_project_ui.py`, add this pair to `restore()`'s combo-value tuple:

```python
("accelerated_clock_minimum", choices["accelerated_clock_minimum_seconds"]),
```

Add `"accelerated_clock_minimum"` to **both** combo-name tuples in `GameplayBuildLink.__init__` and
`GameplayBuildLink._levels`. The checkbox synchronizes through the existing shared-key loop.

## Allocator, manifest and packaging

`tests/nfl2k5_allocator_stack.py` already includes `REQUESTS` and an On/20 adapter in both gate orders;
the pairwise matrix and both XBE gates include this owner. Do not add a second copy to that test union.

In `nfl2k5_xbe_space.dormant_union()`, import the owner and append its requests:

```python
from . import nfl2k5_accelerated_clock as accelerated_clock
# Append to the existing tuple sum:
+ accelerated_clock.REQUESTS
```

In `mod_editor/core/nfl2k5_cave_manifest.py`, update the same exact memberships as `money_downs`:

1. Add `"nfl2k5_accelerated_clock"` to both `Recorder.observe()` owner tuples (file growth eligibility and
   declared reservation collection).
2. Import the module in `build_manifest()`; append `accelerated_clock.REQUESTS` to `all_requests`; include
   the module in `modules.update(...)` so the recorder wraps `apply()`.
3. After the final allocation and beside `money_downs.apply(final)`, install:

   ```python
   final, _ = accelerated_clock.apply(final, enabled=True, minimum_seconds=20)
   ```

4. Include `(accelerated_clock, dict(enabled=True, minimum_seconds=20))` in the dormant/synthetic probe
   tuple, the module in its status/replay checks, and `accelerated_clock.OWNER` in `extra_owners` metadata.
   Disable `accelerated_clock=False` with the other deferred owner flags for the initial disc build.
5. Regenerate `data/nfl2k5_cave_reservations.json` with the normal integrator-owned production build.
   The branch's `.scratch/b65-accelerated-clock-manifest.json` is an observed, bounded XBE projection,
   explicitly **not** a production disc manifest. Its four live hooks and all three named children are
   reserved, with unchanged inherited source fingerprints. Never publish that scratch file as a disc proof.

Append these runtime files to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_accelerated_clock.py
mod_editor/core/nfl2k5_accelerated_clock_code.py
docs/mod_editor/nfl2k5_accelerated_clock_capability.json
```

Add the two core paths and recomputed SHA-256 values to the standard backend/provider integrity closure
and package checks wherever the money-downs writer/code pair is registered. The assembler and .S source
are development proof tools, not runtime dependencies. Run `python3 packaging/repin.py --apply` after
integration. It ran on this branch and reported **0 pin updates**, because no existing pinned writer changed.

## Capability row and release prose

Append the complete object in `docs/mod_editor/nfl2k5_accelerated_clock_capability.json` to
`mod_editor/capabilities/registry.v1.json`'s `capabilities` array, sorted by the registry's normal process.
The exact ID is `nfl2k5.gameplay.accelerated_clock`; classification is `offline-writer-proved` and runtime
status remains `not-tested` (bounded instruction execution is described separately). Update expected
registry counts through the normal integrator-owned checks. The candidate JSON is the full row, not a sketch.

The changelog bullet is already written under `## v1.0 RC89, beta 65` in
`docs/mod_editor/2k5_mod_studio_changelog.md`, and the getting-started paragraph is already in
`docs/mod_editor/2k5_mod_studio_getting_started.md`. Once controls actually land, replace their conditional
integration wording with the delivered UI path; keep the UNWITNESSED statements until Noah plays.

## Integration acceptance

Run offscreen UI tests covering Off/20 initial state; all five minima in both tabs; choice persistence;
preset selection; source rescan; installed settings locked; and no implicit enabling when a minimum changes.
Verify `_selected_space_requests(accelerated_clock=True)` contains all three requests,
`BuildPlan(..., accelerated_clock=True).wants_xbe_patch()` is true, and Off contributes no XBE writes.
Exercise invalid minimum 6 and a changed installed choice: both must refuse before creating output.

Rerun the native suite, oracle suite, pairwise matrix and both XBE gates after central integration and
production manifest regeneration. Run packaging closure and release gates normally. `ASTRA_REPORT.md`
contains exact local commands, measured results and Noah's required game witness list.
