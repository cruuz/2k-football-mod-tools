# Beta 69 J5 integration handoff

The three pure writers, CLI, tests and source assembly are implemented. Protected
Build/GUI/registry/packaging/production-manifest files are unchanged. The following
is integration work, not a claim that controls have been rendered or used.
All three capabilities are EXPERIMENTAL, OFF/Retail in **every** preset. Add three
registry rows (161 -> 164 on this isolated base; add 3 to the integrated count).

## Public names and settings

| Build field | Default | Control/caption |
| --- | --- | --- |
| `coin_defer` | `False` | `Coin toss: CPU defer (modern, experimental; CPU winners only)` |
| `decided_clock` | `False` | `Run out the clock when the game is decided (experimental)` |
| `decided_clock_margin` | `17` | `Leading possession: minimum lead`, 9/17/25/33 points |
| `decided_clock_seconds` | `60` | `Remaining game time: at most`, 15/30/60/90/120 seconds |
| `cpu_scrambles` | `"retail"` | `CPU QB scrambles: retail / modern (experimental)`, Retail/Modern |

Use each writer's `HELP_TEXT`. The coin label must retain **CPU winners only**;
no human Defer choice exists. The clock cutoff is a user-selected convenience
rule, not mathematical elimination. Modern scrambles doubles one conditional
lottery threshold, not measured scrambles per game. Do not recommend ADVANCED.

## `mod_editor/core/nfl2k5_throw_tuning.py`

At the neighboring accelerated-clock import add:

```python
from . import nfl2k5_coin_defer as coin_defer_patch
from . import nfl2k5_decided_clock as decided_clock_patch
from . import nfl2k5_cpu_scrambles as cpu_scrambles_patch
```

After `R62_RUNTIME_KEYS` is declared, append:

```python
R62_SPACE_KEYS += ("coin_defer", "decided_clock", "cpu_scrambles")
R62_RUNTIME_KEYS += ("coin_defer", "decided_clock", "decided_clock_margin",
                     "decided_clock_seconds", "cpu_scrambles")
```

Add these keyword parameters to `_validate_r62_options`, `_apply_all`,
`write_xbe_copy`, and `write_image_copy` (the last is the decorated implementation):

```python
coin_defer=False, decided_clock=False, decided_clock_margin=17,
decided_clock_seconds=60, cpu_scrambles="retail",
```

Add only the selection parameters to `_selected_space_requests` and
`_xbe_space_adapter.__init__`:

```python
coin_defer=False, decided_clock=False, cpu_scrambles="retail",
```

Forward the following in `_xbe_space_adapter.__init__`'s call to
`_selected_space_requests` and that function's `_validate_r62_options` call:

```python
coin_defer=coin_defer, decided_clock=decided_clock, cpu_scrambles=cpu_scrambles,
```

In `_validate_r62_options`, after accelerated-clock option validation:

```python
_validate_lever_flags(coin_defer, decided_clock)
decided_clock_patch.encode_options(margin=decided_clock_margin,
                                   seconds=decided_clock_seconds)
_require(type(cpu_scrambles) is str and cpu_scrambles in ("retail", "modern"),
         "CPU QB scrambles must be retail or modern")
```

In `_selected_space_requests`'s returned tuple, after accelerated clock:

```python
+ (coin_defer_patch.REQUESTS if coin_defer else ())
+ (decided_clock_patch.REQUESTS if decided_clock else ())
+ (cpu_scrambles_patch.REQUESTS if cpu_scrambles == "modern" else ())
```

In `_xbe_space_adapter.__init__`, append to the `bool(...)` selecting scaleout:

```python
or coin_defer or decided_clock or cpu_scrambles == "modern"
```

In `_deferred_r62_options`, explicitly add `"cpu_scrambles": "retail"` to the
returned override dict, after the generic `R62_SPACE_KEYS` false mapping.
Otherwise the generic deferral path incorrectly forwards a boolean for this enum.

Next to `_accelerated_clock_adapter`, add:

```python
class _decided_clock_adapter:
    status = staticmethod(decided_clock_patch.status)

    def __init__(self, margin, seconds):
        self.margin, self.seconds = margin, seconds

    def apply(self, payload):
        return decided_clock_patch.apply(payload, margin=self.margin,
                                          seconds=self.seconds)


def _b69_rules_status(payload):
    result = {}
    for key, module in (("coin_defer", coin_defer_patch),
                        ("decided_clock", decided_clock_patch),
                        ("cpu_scrambles", cpu_scrambles_patch)):
        state = module.status(payload)
        result[key] = state
        result[key + "_settings"] = (module.verify(payload)
                                      if state != "foreign" else None)
    return result
```

In `_grown_status_fields`, include this dict expansion in the returned mapping:

```python
**_b69_rules_status(payload),
```

In `_apply_all`, after the accelerated-clock installed-settings checks and
before any mutation, add:

```python
for selected, module in ((coin_defer, coin_defer_patch),
                         (decided_clock, decided_clock_patch),
                         (cpu_scrambles == "modern", cpu_scrambles_patch)):
    state = module.status(payload)
    if selected:
        _require(state != "foreign", f"{module.BUILD_CAPTION}: foreign prerequisites")
    if state == "applied":
        _require(selected, f"{module.BUILD_CAPTION} is installed; rebuild from a verified base to turn it off")
        if module is decided_clock_patch:
            module.verify(payload, margin=decided_clock_margin,
                          seconds=decided_clock_seconds)
```

Append `or coin_defer or decided_clock or cpu_scrambles == "modern"` to each
selection predicate that currently includes `or accelerated_clock`: the final
allocator tuple in `_apply_all` and both write-copy entrypoint work predicates.
The same addition is required in the scaleout predicate described above. Do not
append it to the accelerated-clock's own validation/behavior.

In `_apply_all`'s final owner loop, immediately after the accelerated-clock row:

```python
(coin_defer, coin_defer_patch, "coin_defer_patch", coin_defer_patch.BUILD_CAPTION),
(decided_clock, _decided_clock_adapter(decided_clock_margin, decided_clock_seconds),
 "decided_clock_patch", decided_clock_patch.BUILD_CAPTION),
(cpu_scrambles == "modern", cpu_scrambles_patch,
 "cpu_scrambles_patch", cpu_scrambles_patch.BUILD_CAPTION),
```

The existing `_r62_options/_r62_space_options` forwarding now carries every new
field, including the final paired image pass. Preserve the complete union before
any first allocation; do not append new requests to an already sealed partial
union. Changing union/settings requires a fresh base.

## `mod_editor/core/mod_build.py`

In `BuildPlan`, beside accelerated-clock fields:

```python
coin_defer: bool = False
decided_clock: bool = False
decided_clock_margin: int = 17
decided_clock_seconds: int = 60
cpu_scrambles: str = "retail"
```

Add the following to **each** Basic/Advanced/Experimental preset dict:

```python
"coin_defer": False, "decided_clock": False,
"decided_clock_margin": 17, "decided_clock_seconds": 60,
"cpu_scrambles": "retail",
```

In `BuildPlan.wants_xbe_patch`, append to its OR expression:

```python
or self.coin_defer or self.decided_clock or self.cpu_scrambles == "modern"
```

In the module-availability table used by source inspection, after accelerated clock:

```python
("coin_defer", "nfl2k5_coin_defer"),
("decided_clock", "nfl2k5_decided_clock"),
("cpu_scrambles", "nfl2k5_cpu_scrambles"),
```

In `_state_from_report`'s report-key projection (the tuple currently containing
`accelerated_clock_settings`), append:

```python
"coin_defer", "coin_defer_settings", "decided_clock", "decided_clock_settings",
"cpu_scrambles", "cpu_scrambles_settings",
```

`_r62_plan_options` reads `tt.R62_RUNTIME_KEYS`; extending that tuple propagates
the fields into plan validation, build identity, and the final `_apply_all`.
Keep defaults above for older saved plans. In the preflight OR which sets
`xbe_space=True`, and the final “Adding experimental extra patch space” OR
(around 1156 and 1780 on this base), append:

```python
or plan.coin_defer or plan.decided_clock or plan.cpu_scrambles == "modern"
```

In the first-pass `replace(plan, ...).wants_xbe_patch()` near 1411, add the three
selection resets below. That pass intentionally defers allocation-dependent
owners until the complete paired union is known:

```python
coin_defer=False, decided_clock=False, cpu_scrambles="retail",
```

The `all_requests` path must retain the new `R62_SPACE_KEYS` when collecting
requests for guardian, scorebug, kickoff and other resource passes. Do not install
these three owners in the initial copy and then attempt to enlarge the directory.
Retain each owner's receipt and reparse with its `verify()` in any optimized
receipt-validation path. Include all five settings in cache identity.

## Build controls

In `mod_editor/gui/beta62_options.py`, add to `OPTIONS` before `KEYS` is derived:

```python
("coin_defer", tt.coin_defer_patch.BUILD_CAPTION, tt.coin_defer_patch.HELP_TEXT),
("decided_clock", tt.decided_clock_patch.BUILD_CAPTION, tt.decided_clock_patch.HELP_TEXT),
```

These create the two experimental checkboxes through the existing shared path.
CPU scrambles is a separate enum, not another boolean in `KEYS`.

In `mod_editor/gui/build_panel_qt.py`'s constructor, following accelerated-clock
minimum creation (with the existing `g` layout), add:

```python
self.decided_clock_margin = QComboBox()
self.decided_clock_seconds = QComboBox()
for value in tt.decided_clock_patch.MARGINS:
    self.decided_clock_margin.addItem(f"{value} points", value)
for value in tt.decided_clock_patch.SECONDS:
    self.decided_clock_seconds.addItem(f"{value} seconds", value)
for widget, title, default in (
    (self.decided_clock_margin, "Leading possession: minimum lead", 17),
    (self.decided_clock_seconds, "Remaining game time: at most", 60),
):
    g.addWidget(QLabel(title))
    g.addWidget(widget)
    widget.setAccessibleName(title)
    widget.setToolTip(tt.decided_clock_patch.HELP_TEXT)
    widget.setCurrentIndex(widget.findData(default))
    widget.currentIndexChanged.connect(lambda _index: self._refresh())
self.cpu_scrambles_level = QComboBox()
self.cpu_scrambles_level.addItem("Retail", "retail")
self.cpu_scrambles_level.addItem("Modern (experimental)", "modern")
self.cpu_scrambles_level.setAccessibleName(tt.cpu_scrambles_patch.BUILD_CAPTION)
self.cpu_scrambles_level.setToolTip(tt.cpu_scrambles_patch.HELP_TEXT)
g.addWidget(QLabel(tt.cpu_scrambles_patch.BUILD_CAPTION))
g.addWidget(self.cpu_scrambles_level)
self.cpu_scrambles_level.currentIndexChanged.connect(lambda _index: self._refresh())
```

In preset application, after the accelerated-clock combo reset, use the same
signal-blocked restoration for all three new combos:

```python
for widget, key, default in (
    (self.decided_clock_margin, "decided_clock_margin", 17),
    (self.decided_clock_seconds, "decided_clock_seconds", 60),
    (self.cpu_scrambles_level, "cpu_scrambles", "retail"),
):
    widget.blockSignals(True)
    widget.setCurrentIndex(widget.findData(values.get(key, default)))
    widget.blockSignals(False)
```

In `plan()`, after `plan.accelerated_clock_minimum_seconds`:

```python
plan.decided_clock_margin = int(self.decided_clock_margin.currentData())
plan.decided_clock_seconds = int(self.decided_clock_seconds.currentData())
plan.cpu_scrambles = str(self.cpu_scrambles_level.currentData())
```

In `has_work()`, count `self.cpu_scrambles_level.currentData() == "modern"`.
The two checkboxes are already counted through `r62_ui.KEYS`. In `_refresh`,
beside installed accelerated-clock handling:

```python
state = self._state or {}
installed = state.get("decided_clock_settings") or {}
cutoff = installed.get("settings") or {}
for widget, key in ((self.decided_clock_margin, "margin"),
                    (self.decided_clock_seconds, "seconds")):
    if installed.get("status") == "applied":
        widget.blockSignals(True)
        widget.setCurrentIndex(widget.findData(cutoff[key]))
        widget.blockSignals(False)
    widget.setEnabled(self.decided_clock_check.isEnabled()
                      and self.decided_clock_check.isChecked()
                      and installed.get("status") != "applied")
mode = state.get("cpu_scrambles", "unknown")
if mode == "applied":
    self.cpu_scrambles_level.blockSignals(True)
    self.cpu_scrambles_level.setCurrentIndex(self.cpu_scrambles_level.findData("modern"))
    self.cpu_scrambles_level.blockSignals(False)
self.cpu_scrambles_level.setEnabled(state.get("container") == "xiso" and mode == "retail")
if mode in ("applied", "foreign"):
    self.cpu_scrambles_level.setToolTip(
        "This executable already has the patch or has incompatible instructions. "
        "Choose a verified base disc to change CPU QB scrambles.")
else:
    self.cpu_scrambles_level.setToolTip(tt.cpu_scrambles_patch.HELP_TEXT)
```

The existing checkbox source-state path locks installed/foreign `coin_defer` and
`decided_clock`; confirm those two are included wherever boolean controls are
projected. Preserve installed enum/cutoff choices when changing preset. Give any
other Gameplay panel using the shared options the same cutoff values/enum, or
keep those controls on Build only. Never silently reset installed settings.

## Packaging, manifest, and integration checks

Add the seven new `mod_editor/core/nfl2k5_{rules_patch,coin_defer,coin_defer_code,
decided_clock,decided_clock_code,cpu_scrambles,cpu_scrambles_code}.py` source files
to the protected release allowlist/pinned runtime where required. Existing
`nfl2k5_xbe_space`, `nfl2k5_rdata_sites`, `nfl2k5_cave_oracle` and defensive-try
dependencies must remain packaged. Generated code is checked in; GNU as and
Unicorn are development-only. Include `tools/nfl2k5_modern_rules.py` wherever the registry CLI is offered;
assembly and the assembler are development/source-distribution inputs only.

Regenerate `data/nfl2k5_cave_reservations.json` after the final integrated union.
**Allocation changed:** seven new records (896 RX +4 RW +140 RO bytes); 27
existing addresses move in this complete test union, with unchanged old sizes
and alignments. Its scaleout file extent is unchanged. Exact addresses/deltas:
`reports/b69_j5/allocation_delta.json`. Do not transplant test-union addresses
into a different selected build. The strict gate projection is not a release
manifest. Record source fingerprints for the new writers/common helper/compiled
code/tools and all final owners. Run `packaging/repin.py --apply` afterward.

Add 3 to all shared registry count pins, including both checks in
`packaging/check_2k5_mod_studio_runtime.py`, `tests/mod_editor/test_phase1_packaging.py`,
the APF runtime packaging check and `test_apf_studio_installer.py`. Validate the
registry schema and capability IDs; do not overwrite counts from other jobs.

Required integration proofs: standalone new tests and four XBE gates again;
Off-only build byte equality; each option alone and full resource/owner union;
repeated output verification; refusal on changing installed settings; Off in all
presets; offscreen controls, saved-plan round trip and build-receipt/cache identity
for all five fields. Then player witnesses in the research document. No new UI,
full disc, or rendered gameplay evidence is claimed by J5.

## Exact registry rows

Append these objects to `mod_editor/capabilities/registry.v1.json`'s capabilities
array, sort by ID and canonicalize JSON after Build integration. Runtime status remains `not-tested` because the
proof is bounded native execution, not played gameplay.

```json
[
  {
    "backend": {
      "command": "python3 tools/nfl2k5_modern_rules.py apply source.xbe --output new-rules.xbe --cpu-defer",
      "module": "tools/nfl2k5_modern_rules.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "ASTRA_REPORT.md",
      "docs/research/nfl2k5_b69_rules.md",
      "tests/mod_editor/test_nfl2k5_b69_rules.py",
      "tools/nfl2k5_coin_defer.S"
    ],
    "game": "nfl2k5_xbox",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "EXPERIMENTAL, Off/Retail in every preset. Integrate the exact Build controls in WIRING.md. All in-game outcomes UNWITNESSED."
    },
    "id": "nfl2k5.gameplay.coin_defer",
    "input_constraints": [
      "Pinned USA XBE or verified composed input; reserve complete selected owner union before installation. Foreign or mixed bytes refuse.",
      "EXPERIMENTAL / UNWITNESSED. Off in every preset. CPU winners defer at the published 2023 rate of 240/272 (88.24%). The loser chooses kick or receive for the first half and the deferring CPU receives in the second half. Human winners keep the retail menu; a human Defer choice is not available. Overtime keeps retail toss choices.",
      "Rebuild from a verified base to change the selected union or installed settings."
    ],
    "portme": [
      "Integrate BuildPlan, XBE dispatcher, Build controls, packaging and these registry rows using WIRING.md; regenerate the protected production cave manifest.",
      "Complete the player witness cases in docs/research/nfl2k5_b69_rules.md before claiming in-game behavior."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship source and instructions; never distribute generated XBEs or retail resources.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [
        "ASTRA_REPORT.md",
        "docs/research/nfl2k5_b69_rules.md",
        "tests/mod_editor/test_nfl2k5_b69_rules.py",
        "tools/nfl2k5_coin_defer.S"
      ],
      "status": "not-tested",
      "scope": "Bounded native USA instruction execution with declared input/scene seams. CPU opening-toss winners defer at a dated 2023 count of 15/17; loser chooses first-half kick/receive and CPU receives in Q3. Human Defer is unavailable. Rendered UI, complete upstream simulation, physical plays and full-game outcomes are UNWITNESSED."
    },
    "selectors": {
      "fields": [
        {
          "name": "coin_defer",
          "allowed": "false | true; default false",
          "required": true
        }
      ],
      "notes": "Build-time only. Off/Retail skips the writer and its allocation; there is no in-game toggle."
    },
    "source_container": {
      "format": "XBE in XDVDFS",
      "hash_pins": [
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
      ],
      "resource": "Hooks 25E7B5 (7), 25E81F (5), 15864C (5), 25EAF0 (6); owned 384 RX, 4 RW, 128 RO bytes.",
      "retail_file": "user-owned default.xbe in an NFL 2K5 USA disc"
    },
    "summary": "CPU opening-toss winners defer at a dated 2023 count of 15/17; loser chooses first-half kick/receive and CPU receives in Q3. Human Defer is unavailable.",
    "surface": "gameplay_tuning_sliders",
    "title": "Coin toss: CPU defer (modern, experimental; CPU winners only)",
    "validation_command": "python3 -m tests.mod_editor.test_nfl2k5_b69_rules"
  },
  {
    "backend": {
      "command": "python3 tools/nfl2k5_modern_rules.py apply source.xbe --output new-rules.xbe --decided-clock --margin 17 --seconds 60",
      "module": "tools/nfl2k5_modern_rules.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "ASTRA_REPORT.md",
      "docs/research/nfl2k5_b69_rules.md",
      "tests/mod_editor/test_nfl2k5_b69_rules.py",
      "tools/nfl2k5_decided_clock.S",
      "tests/mod_editor/test_nfl2k5_b69_rules_series.py",
      "reports/b69_j5/native_series.json"
    ],
    "game": "nfl2k5_xbox",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "EXPERIMENTAL, Off/Retail in every preset. Integrate the exact Build controls in WIRING.md. All in-game outcomes UNWITNESSED."
    },
    "id": "nfl2k5.gameplay.decided_clock",
    "input_constraints": [
      "Pinned USA XBE or verified composed input; reserve complete selected owner union before installation. Foreign or mixed bytes refuse.",
      "EXPERIMENTAL / UNWITNESSED. Off in every preset. In the fourth quarter, at the next dead ball, end the remaining clock if the team with the ball leads by your selected margin with no more than your selected time left. Default: at least 17 points and at most 60 seconds. This is a convenience cutoff, not mathematical elimination. Live plays, the trailing team's possession and overtime are excluded. Accelerated clock keeps its own rules.",
      "Rebuild from a verified base to change the selected union or installed settings."
    ],
    "portme": [
      "Integrate BuildPlan, XBE dispatcher, Build controls, packaging and these registry rows using WIRING.md; regenerate the protected production cave manifest.",
      "Complete the player witness cases in docs/research/nfl2k5_b69_rules.md before claiming in-game behavior."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship source and instructions; never distribute generated XBEs or retail resources.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [
        "ASTRA_REPORT.md",
        "docs/research/nfl2k5_b69_rules.md",
        "tests/mod_editor/test_nfl2k5_b69_rules.py",
        "tools/nfl2k5_decided_clock.S",
        "tests/mod_editor/test_nfl2k5_b69_rules_series.py",
        "reports/b69_j5/native_series.json"
      ],
      "status": "not-tested",
      "scope": "Bounded native USA instruction execution with declared input/scene seams. Optional Q4 cutoff: leading possession, selected margin and time, next native dead ball/huddle. Convenience rule, not mathematical elimination. Rendered UI, complete upstream simulation, physical plays and full-game outcomes are UNWITNESSED."
    },
    "selectors": {
      "fields": [
        {
          "name": "decided_clock",
          "allowed": "false | true; default false",
          "required": true
        },
        {
          "name": "decided_clock_margin",
          "allowed": "9 | 17 | 25 | 33; default 17",
          "required": true
        },
        {
          "name": "decided_clock_seconds",
          "allowed": "15 | 30 | 60 | 90 | 120; default 60",
          "required": true
        }
      ],
      "notes": "Build-time only. Off/Retail skips the writer and its allocation; there is no in-game toggle."
    },
    "source_container": {
      "format": "XBE in XDVDFS",
      "hash_pins": [
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
      ],
      "resource": "Hooks B6E80 (5), A03DC (5); owned 384 RX, 8 RO bytes; no runtime state.",
      "retail_file": "user-owned default.xbe in an NFL 2K5 USA disc"
    },
    "summary": "Optional Q4 cutoff: leading possession, selected margin and time, next native dead ball/huddle. Convenience rule, not mathematical elimination.",
    "surface": "gameplay_tuning_sliders",
    "title": "Run out the clock when the game is decided (experimental)",
    "validation_command": "python3 -m tests.mod_editor.test_nfl2k5_b69_rules"
  },
  {
    "backend": {
      "command": "python3 tools/nfl2k5_modern_rules.py apply source.xbe --output new-rules.xbe --modern-scrambles",
      "module": "tools/nfl2k5_modern_rules.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "ASTRA_REPORT.md",
      "docs/research/nfl2k5_b69_rules.md",
      "tests/mod_editor/test_nfl2k5_b69_rules.py",
      "tools/nfl2k5_cpu_scrambles.S"
    ],
    "game": "nfl2k5_xbox",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "EXPERIMENTAL, Off/Retail in every preset. Integrate the exact Build controls in WIRING.md. All in-game outcomes UNWITNESSED."
    },
    "id": "nfl2k5.gameplay.cpu_scrambles",
    "input_constraints": [
      "Pinned USA XBE or verified composed input; reserve complete selected owner union before installation. Foreign or mixed bytes refuse.",
      "EXPERIMENTAL / UNWITNESSED. Retail in every preset. Modern doubles one existing CPU pocket escape lottery threshold from 0.25 to 0.50 times effective Scramble. Its pressure and timer conditions remain. More branch hits are proved under identical native inputs; NFL-average scrambles per game are not established. Human steering and acceleration are unchanged.",
      "Rebuild from a verified base to change the selected union or installed settings."
    ],
    "portme": [
      "Integrate BuildPlan, XBE dispatcher, Build controls, packaging and these registry rows using WIRING.md; regenerate the protected production cave manifest.",
      "Complete the player witness cases in docs/research/nfl2k5_b69_rules.md before claiming in-game behavior."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Ship source and instructions; never distribute generated XBEs or retail resources.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [
        "ASTRA_REPORT.md",
        "docs/research/nfl2k5_b69_rules.md",
        "tests/mod_editor/test_nfl2k5_b69_rules.py",
        "tools/nfl2k5_cpu_scrambles.S"
      ],
      "status": "not-tested",
      "scope": "Bounded native USA instruction execution with declared input/scene seams. Modern changes one eligible CPU QB escape lottery from .25 to .50 times effective Scramble. NFL-average scrambles per game are not established. Rendered UI, complete upstream simulation, physical plays and full-game outcomes are UNWITNESSED."
    },
    "selectors": {
      "fields": [
        {
          "name": "cpu_scrambles",
          "allowed": "retail | modern; default retail",
          "required": true
        }
      ],
      "notes": "Build-time only. Off/Retail skips the writer and its allocation; there is no in-game toggle."
    },
    "source_container": {
      "format": "XBE in XDVDFS",
      "hash_pins": [
        "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
      ],
      "resource": "Hook 19C36C (6); owned 128 RX, 4 RO bytes; no runtime state.",
      "retail_file": "user-owned default.xbe in an NFL 2K5 USA disc"
    },
    "summary": "Modern changes one eligible CPU QB escape lottery from .25 to .50 times effective Scramble. NFL-average scrambles per game are not established.",
    "surface": "gameplay_tuning_sliders",
    "title": "CPU QB scrambles: retail / modern (experimental)",
    "validation_command": "python3 -m tests.mod_editor.test_nfl2k5_b69_rules"
  }
]
```
