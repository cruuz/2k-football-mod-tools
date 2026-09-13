# Beta 69 J4 integration handoff

Protected files were not edited. Add **two** capability rows, below. Both new
options are **OFF in every preset, EXPERIMENTAL / UNWITNESSED**. The standalone
Weather editor and the verified writers are implemented and tested on this
branch; the Build controls described here still need integration.

Do not add options for “enable afternoon/night,” dynamic sunset, independent
rain/snow probabilities, or a franchise game-day weather menu. Retail already
selects schedule time; the menu lifecycle is not proved. The authored +2 °F
example must not be called measured modern NFL climate.

## 1. Build plan, preflight, writes and read-back

File `mod_editor/core/mod_build.py`, `BuildPlan`, next to `espn25_plan`:

```python
weather_plan: str = ""  # Saved nfl2k5.weather.edits.v1 JSON; EXPERIMENTAL, OFF
weather_haze: bool = False  # Existing dry-weather coefficient; EXPERIMENTAL, OFF
```

Append `or self.weather_haze` to `BuildPlan.wants_xbe_patch()`. The climate plan
is data only and must not trigger the throw-tuning XBE path. Add these entries
to **each** of the three `PRESETS` dictionaries:

```python
"weather_plan": "", "weather_haze": False,
```

In `availability()` add:

```python
"weather_plan": _core_module("nfl2k5_weather") is not None,
"weather_haze": _core_module("nfl2k5_weather_haze") is not None,
```

In `inspect()` initialize `out["weather_plan"] = "requires image"`; within the
existing image branch that inspects `espn25_plan`, add:

```python
weather = _core_module("nfl2k5_weather")
if weather is None:
    out["weather_plan"] = "unavailable"
else:
    try:
        weather.load_resource(source)  # Parses bounded ROST + resolved 82-row table.
        out["weather_plan"] = "available"
    except (OSError, ValueError):
        out["weather_plan"] = "foreign"
```

Alongside the existing helmet-finish inspection (applies to image or bare XBE):

```python
haze = _core_module("nfl2k5_weather_haze")
if haze is None:
    out["weather_haze"] = "unavailable"
else:
    try:
        out["weather_haze"] = haze.status(_xbe_bytes(source))
    except (OSError, ValueError):
        out["weather_haze"] = "unknown"
```

At `_build()`'s existing saved-plan type validation, before copying:

```python
if type(plan.weather_plan) is not str:
    raise ValueError("Choose a saved weather plan JSON file, or leave climate edits off.")
if type(plan.weather_haze) is not bool:
    raise ValueError("Existing dry-weather haze response must be Off or On.")
plan = replace(plan, weather_plan=plan.weather_plan.strip())
```

Immediately after the `loaded_espn25_plan` preflight block (source and is_image
are already resolved), add the complete block below. `_preflight_only` must
reach it, so failures are caught before project preparation and image copying.

```python
loaded_weather_plan = None
if plan.weather_plan:
    weather = _core_module("nfl2k5_weather")
    if weather is None:
        raise ValueError("Climate editing is not included in this release. Turn it off or install a complete release.")
    if not is_image:
        raise ValueError("Climate edits need a full game disc. Choose your disc instead of default.xbe.")
    if plan.reserves_16 or plan.created_teams_extra:
        raise ValueError("Climate edits support the version-17 roster table. Turn off 16 reserves and extra created teams, then build again.")
    try:
        loaded_weather_plan = weather.read_json(Path(plan.weather_plan))
        if not isinstance(loaded_weather_plan, dict) or not loaded_weather_plan.get("changes"):
            raise ValueError("The saved plan has no climate changes")
        progress("Checking saved climate edits against the source", 0, 0)
        weather.apply(weather.load_resource(source), loaded_weather_plan)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Climate edits cannot be used: {exc}. Open Weather editor on this source and save the edits again.") from exc
if plan.weather_haze:
    haze = _core_module("nfl2k5_weather_haze")
    if haze is None or haze.status(_xbe_bytes(source)) not in ("retail", "applied"):
        raise ValueError("The dry-weather haze reader is not recognized. Turn this option off or rebuild from a supported USA source.")
```

At the `replace(plan, helmet_finish="glossy", ...).wants_xbe_patch()` dispatcher,
include `weather_haze=False`. Its final pass owns the data edit; no throw-tuning
argument or allocator request is needed. `weather_plan` stays data only.

After the final helmet-finish pass and before `progress("Verifying the composed
disc", ...)`, add:

```python
haze = _core_module("nfl2k5_weather_haze")
if haze is not None:
    try:
        current = _xbe_bytes(target)
    except (OSError, ValueError):
        if plan.weather_haze:
            raise
        current = None
    if current is not None and (plan.weather_haze or haze.status(current) == "applied"):
        progress("Applying existing dry-weather haze response", 0, 0)
        patched, haze_receipt = haze.apply(current, enabled=plan.weather_haze)
        _write_xbe_bytes(target, patched)
        haze.verify(_xbe_bytes(target), enabled=plan.weather_haze)
        receipt["steps"].append({"step": "weather_haze", **haze_receipt})
```

Off restores an already recognized installation, like Glossy helmet finish.
It does not overwrite foreign coefficients. After the saved ESPN plan final
pass, immediately before `_build()` returns its receipt:

```python
if loaded_weather_plan is not None:
    weather = _core_module("nfl2k5_weather")
    progress("Applying saved stadium climate edits", 0, 0)
    climate_receipt = weather.apply_to_image(target, loaded_weather_plan)
    weather.verify(weather.load_resource(target), loaded_weather_plan)
    receipt["steps"].append({"step": "weather_plan", **climate_receipt})
    receipt["result"]["weather_plan"] = "applied"
```

This resolves outer 5 on the final disposable image after roster/text/music/hires
relocation, before `build()` publishes it. `apply_to_image` rechecks the entire
resource before mutation and reparses on read-back, including a whole-resource
check that no unrequested bytes changed. A partial I/O failure must discard the
disposable image through the existing publication transaction.

## 2. Build tab and the small Weather editor

File `mod_editor/gui/build_panel_qt.py`, `BuildPanel._build_ui()`: after the
saved Anniversary plan controls, while roster layout `r` is in scope:

```python
from mod_editor.core import nfl2k5_weather as weather
from mod_editor.core import nfl2k5_weather_haze as haze
self.weather_plan_check = self._option(
    r, "weather_plan", weather.BUILD_CAPTION, weather.HELP_TEXT,
    badge="EXPERIMENTAL / UNWITNESSED", needs_image=True)
weather_row = QHBoxLayout()
self.weather_plan_field = QLineEdit()
self.weather_plan_field.setPlaceholderText("Save build edits in Weather editor, or choose a plan JSON")
weather_row.addWidget(self.weather_plan_field, 1)
self.weather_plan_button = QPushButton("Choose…")
self.weather_plan_button.clicked.connect(self._choose_weather_plan)
weather_row.addWidget(self.weather_plan_button)
r.addLayout(weather_row)
self.weather_editor_button = QPushButton("Weather editor…")
self.weather_editor_button.clicked.connect(self._open_weather_editor)
r.addWidget(self.weather_editor_button)
self.weather_status = QLabel("")
self.weather_status.setWordWrap(True)
r.addWidget(self.weather_status)
self.weather_plan_field.textChanged.connect(self._refresh)
self.weather_haze_check = self._option(
    r, "weather_haze", haze.BUILD_CAPTION, haze.HELP_TEXT,
    badge="EXPERIMENTAL / UNWITNESSED")
```

The existing `_toggle_boxes()`/signal setup must run after these controls exist.
Add to `_boxes()`:

```python
"weather_plan": self.weather_plan_check,
"weather_haze": self.weather_haze_check,
```

In `plan()`'s `BuildPlan(...)` construction:

```python
weather_plan=(self.weather_plan_field.text().strip() if self.weather_plan_check.isChecked() else ""),
weather_haze=self.weather_haze_check.isChecked(),
```

Add these complete class methods. `WeatherDialog` is the already implemented
PyQt5 tool on this branch, not an unimplemented GUI sketch. It edits temperature,
precipitation chance and wind; preserves the input; groups the authored example
preset into one Undo; validates its saved plan; emits `saved(str)` after read-back;
and names source/load/save failures inline.

```python
def _choose_weather_plan(self):
    name, _ = QFileDialog.getOpenFileName(self, "Choose weather build edits", "", "Climate plan (*.json)")
    if name:
        self.set_weather_plan(name)

def set_weather_plan(self, name):
    self.weather_plan_field.setText(str(name))
    self.weather_plan_check.setChecked(bool(name) and self.weather_plan_check.isEnabled())
    self.weather_status.setText(f"Saved climate plan: {Path(name).name}. EXPERIMENTAL / UNWITNESSED.")
    self._refresh()

def _open_weather_editor(self):
    module = mod_build._tools_module("nfl2k5_weather_editor")
    if module is None:
        self.weather_status.setText("Weather editor is not included in this installation. Install a complete release or choose a saved climate plan.")
        return
    dialog = module.WeatherDialog(self.source_field.text().strip(), self)
    dialog.saved.connect(self.set_weather_plan)
    dialog.exec()

def _weather_haze_changed(self):
    state = (self._state or {}).get("weather_haze")
    return (self.weather_haze_check.isEnabled() and state in ("retail", "applied")
            and self.weather_haze_check.isChecked() != (state == "applied"))

def _weather_plan_problem(self):
    from mod_editor.core import nfl2k5_weather as weather
    name = self.weather_plan_field.text().strip()
    if not name:
        return "Open Weather editor and save build edits, or choose a climate plan JSON."
    if self.reserves_16_check.isChecked() or self.created_teams_extra_check.isChecked():
        return "Climate edits support the version-17 roster. Turn off 16 reserves and extra created teams."
    try:
        document = weather.read_json(name)
        if not isinstance(document, dict) or not document.get("changes"):
            return "This climate plan has no edits. Open Weather editor and change at least one field."
        weather.apply(weather.load_resource(self.source_field.text().strip()), document)
    except (OSError, ValueError) as exc:
        return f"Climate plan cannot be used: {exc}. Reopen Weather editor on this source and save the edits again."
    return ""
```

At `apply_state()`, next to the saved-plan and helmet gates, add:

```python
climate_ok = bool(is_image and self._available.get("weather_plan", False)
                  and state.get("weather_plan") == "available")
self.weather_plan_check.setEnabled(climate_ok)
self.weather_plan_check.setChecked(False)
self.weather_editor_button.setEnabled(climate_ok)
self.weather_plan_button.setEnabled(climate_ok)
self.weather_plan_field.setEnabled(climate_ok)
self._set_badge("weather_plan", "EXPERIMENTAL / UNWITNESSED" if climate_ok else
                "Choose a supported USA disc; climate table unavailable")
haze_state = state.get("weather_haze")
haze_ok = bool(self._available.get("weather_haze", False) and haze_state in ("retail", "applied"))
self.weather_haze_check.setEnabled(haze_ok)
self.weather_haze_check.setChecked(haze_ok and haze_state == "applied")
self._set_badge("weather_haze", "EXPERIMENTAL / UNWITNESSED" if haze_ok else
                "Haze reader unavailable; choose a supported USA source")
```

In `has_work()` include `or bool(p.weather_plan) or self._weather_haze_changed()`.
In `blocker()`, before `if not self.has_work()`:

```python
if self.weather_plan_check.isChecked():
    problem = self._weather_plan_problem()
    if problem:
        return problem
```

In `selected_labels()`, skip the checked haze row if not
`self._weather_haze_changed()`. After its checkbox loop add this explicit Off
restoration label, so confirmation never hides a selected removal:

```python
if self._weather_haze_changed() and not self.weather_haze_check.isChecked():
    labels.append("Restore retail dry-weather haze response")
```

In `confirmation_text()`'s saved-file list add:

```python
if plan.weather_plan:
    files.append(f"Climate plan: {Path(plan.weather_plan).name}")
```

Keep both new controls in project Build-setting serialization (it already uses
dataclass fields), and ensure saved path/checked state restore after source
inspection. Do not automatically check either option when applying a preset.
An already-patched source is detected as On so leaving it selected preserves
the recognized state; applying a preset sets it Off and shows restoration.

## 3. Registry rows (exactly +2)

Append the JSON objects in the final section to
`mod_editor/capabilities/registry.v1.json`'s `capabilities`. Both are
`offline-writer-proved`; `runtime.status` remains `not-tested` because the bounded
native reader proof is not a played witness. The source core has no dependency
on registry wiring. Do not register deferred/no-op options.

Increase the expected shared registry count by 2, combined with other jobs,
in `packaging/check_2k5_mod_studio_runtime.py` (both pins),
`tests/mod_editor/test_phase1_packaging.py`, the APF runtime check and
`tests/mod_editor/test_apf_studio_installer.py`. Add the corresponding list rows
to Gameplay Patches if that screen maintains a separate dispatch table: climate
opens Weather editor/Build, haze edits the Build option. Neither is a
franchise-in-game menu item.

## 4. Packaging, owner registration and manifest regeneration

Add release-allowlist entries for these new shipped files:

```text
mod_editor/core/nfl2k5_weather.py
mod_editor/core/nfl2k5_weather_haze.py
tools/nfl2k5_weather_editor.py
tools/nfl2k5_weather_time_of_day.py
tools/nfl2k5_weather_native_probe.py
docs/research/nfl2k5_weather_time_of_day.md
```

`WeatherDialog` uses the existing PyQt5 dependency. Native audit/probe uses
optional Unicorn only when invoked, not during ordinary editing/building.
No retail blobs, extracted resources, pixels, scratch discs or fixture binaries
belong in the release. The reports are text metadata and hashes; they need not
be runtime payloads. If the registry validator requires evidence paths in the
runtime bundle, include `reports/b69_j4/weather_audit.json` and
`reports/b69_j4/weather_native.json` as text evidence or use the shipped research
doc as the runtime evidence path while retaining all reports in source.

The haze writer has `REQUESTS = CAVES = RUNTIME_GLOBALS = ()`. It owns an existing
four-byte `.data` value at `0xA867F4`, file +`0xA7BE74`; bytes
`cd cc 4c 3f` → `00 00 80 3f`. No new code or runtime memory is required, and
there is no permission to take an unregistered cave.

In `mod_editor/core/nfl2k5_cave_manifest.py`, follow the helmet owner insertion:

```python
from . import nfl2k5_weather_haze as weather_haze
```

Add `weather_haze` to the `modules.update` owner tuple. Immediately after the
explicit `final, _ = helmet_finish.apply(...)` extra-owner application:

```python
final, _ = weather_haze.apply(final)
```

Add `(weather_haze, {})` to the synthetic/probe replay tuple, `weather_haze` to
the status-check tuple, and `weather_haze.OWNER` to `extra_owners`. Trace the
owner's apply transaction through the existing `recorder.wrapper`; it observes
the changed data bytes and section digest. In `Recorder.finish()`, beside the
allocator reservations, also add
the whole four-byte data ownership, including its unchanged last byte:

```python
from . import nfl2k5_weather_haze as weather_haze
if weather_haze.status(final) == "applied":
    for reservation in weather_haze.reservations(final):
        self.reserve(int(reservation["start"], 0), reservation["size"],
                     reservation["owner"], reservation["basis"])
```

Do not turn it on in the experimental preset to achieve
manifest coverage: it is an explicit dormant-owner probe, like helmet finish.
Add `(weather_haze, {})` to `tests/nfl2k5_allocator_stack.py:owner_calls()` and
the haze owner to the shared pair matrix, then rerun all four gates.

**A cave manifest regeneration is required after integration.** The four
unmodified shared gates passed on J4's base (see ASTRA_REPORT); the dedicated
J4 native test checks three haze pairs in both orders. An additional complete
owner-union check also produces identical bytes in both orders and exact Off
restoration (`reports/b69_j4/weather_full_composition.json`). The protected
shared gates do not yet enumerate this new owner. Do not claim that their base
run replaces integration's enlarged owner-union test. Regenerate with:

```bash
python3 packaging/repin.py --apply
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /media/noah/Storage/.b69-integration-manifest \
  --json data/nfl2k5_cave_reservations.json
python3 packaging/repin.py --apply
```

This is an integrator command, not a disc build performed in J4. The directory
must exist and have room for the manifest builder's disposable image. Preserve
other jobs' owner registrations and regenerate once for the combined stack.

## 5. Integration checks

Run the three new test files standalone and the four enlarged XBE gates. Add
focused protected Build/UI tests for: both presets keys Off in all three
presets; climate-only work recognized; selecting/saving a plan; foreign and
partially applied plans refused before copy; version-18 arena conflict before
copy; final-image relocation/read-back; haze-only build; restoring an applied
haze option by selecting Off; confirmed restoration label; and no option being
lost when loading project settings. Existing broad packaging checks then cover
module imports and the two registry rows. No played outcome is promoted.

## Registry JSON

```json
[
  {
    "backend": {
      "command": "python3 tools/nfl2k5_weather_time_of_day.py apply-resource <source.rost> <plan.json> <new.rost>",
      "module": "tools/nfl2k5_weather_time_of_day.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/research/nfl2k5_weather_time_of_day.md",
      "reports/b69_j4/weather_audit.json",
      "reports/b69_j4/weather_native.json",
      "tests/mod_editor/test_nfl2k5_weather.py",
      "tests/mod_editor/test_nfl2k5_weather_editor.py"
    ],
    "game": "nfl2k5_xbox",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "EXPERIMENTAL / UNWITNESSED. Both options remain Off in every preset. Build wiring is supplied in WIRING.md."
    },
    "id": "nfl2k5.weather.climate_editor",
    "input_constraints": [
      "Supported USA version-17 ROST and 82 pinned stadium identities/roof records; resolve outer 5 and all relative pointers.",
      "July and August share a slot; March through June are refused. Rain and snow use one precipitation threshold plus native temperature selection.",
      "Finite bounded scalar values, exact float32 before/after comparisons, no mixed or foreign plan state. Refuse version-18 roster arena growth.",
      "Source stays read-only in authoring. Build applies to its disposable output. Existing-save adoption and all played outcomes are unproved."
    ],
    "portme": [
      "Integrate the two protected Build/registry rows from WIRING.md; test the final disposable-disc transaction.",
      "Source and pin a modern climate dataset before calling any preset modern NFL climate.",
      "Witness new-franchise weather and existing-save behavior; do not advertise a game-day weather menu."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute authoring tools, values and verified recipes only. Never bundle a retail roster, executable, disc or texture.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [
        "reports/b69_j4/weather_native.json",
        "docs/research/nfl2k5_weather_time_of_day.md"
      ],
      "scope": "Bounded native selectors and camera-field copies only; no played, save-lifecycle, appearance or gameplay outcome is witnessed.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [
        {
          "allowed": "0..81, matching the source asset_code",
          "name": "stadium_index",
          "required": true
        },
        {
          "allowed": "1,2,7,8,9,10,11,12; July/August alias",
          "name": "month",
          "required": true
        },
        {
          "allowed": "temperature_f, precipitation_pct, wind_mph",
          "name": "field",
          "required": true
        }
      ],
      "notes": "The source is authoritative. Baselines vary through the native RNG; separate snow probability and exact live wind controls do not exist in this table."
    },
    "source_container": {
      "format": "Uncompressed main ROST inside Xbox VC outer archive",
      "hash_pins": [
        "ab4df547810a558fd3563b6bf4187b88a03b02111437b35a1f37e726a68cf85f",
        "44d6e8566dc6902dd1f12dbe2625014687cc99f375559415231f72a634631cd2"
      ],
      "resource": "Outer 5; relocated 82 x 128-byte stadium table",
      "retail_file": "ESPN NFL 2K5 (USA)/vc_53450030/0"
    },
    "summary": "Author temperature, shared precipitation chance and wind baselines per stadium/month; save verified build edits with Undo. The +2 F example is authored, not measured modern climatology.",
    "surface": "stadiums_fields",
    "title": "Stadium climate editor (experimental)",
    "validation_command": "python3 tests/mod_editor/test_nfl2k5_weather.py"
  },
  {
    "backend": {
      "command": "python3 tools/nfl2k5_weather_time_of_day.py haze <source.xbe> <new.xbe>",
      "module": "tools/nfl2k5_weather_time_of_day.py",
      "operation": "write"
    },
    "classification": "offline-writer-proved",
    "evidence": [
      "docs/research/nfl2k5_weather_time_of_day.md",
      "reports/b69_j4/weather_native.json",
      "tests/mod_editor/test_nfl2k5_weather_native.py"
    ],
    "game": "nfl2k5_xbox",
    "gui": {
      "default_enabled": false,
      "expose": true,
      "mode": "edit",
      "reason": "EXPERIMENTAL / UNWITNESSED. Both options remain Off in every preset. Build wiring is supplied in WIRING.md."
    },
    "id": "nfl2k5.weather.haze_coefficient",
    "input_constraints": [
      "Pinned USA reader spans and normalized 60-byte haze table; only retail/already-applied coefficient accepted.",
      "One existing .data float at VA 0xA867F4 plus the containing section digest. No runtime storage, hook or allocator request.",
      "Eligibility remains native; tested zero-haze, indoor, rain and snow camera paths retain their values. Appearance is unwitnessed."
    ],
    "portme": [
      "Register existing-data ownership and regenerate the combined cave manifest after Build integration.",
      "Witness dry outdoor Off/On comparisons with controlled nonzero haze and indoor/rain/snow controls."
    ],
    "public_distribution": {
      "game_data": "never-bundle-retail-data",
      "mod_payload": "user-authored-inputs-and-recipes",
      "rule": "Distribute authoring tools, values and verified recipes only. Never bundle a retail roster, executable, disc or texture.",
      "tooling": "source-and-schemas-only"
    },
    "runtime": {
      "evidence": [
        "reports/b69_j4/weather_native.json",
        "docs/research/nfl2k5_weather_time_of_day.md"
      ],
      "scope": "Bounded native selectors and camera-field copies only; no played, save-lifecycle, appearance or gameplay outcome is witnessed.",
      "status": "not-tested"
    },
    "selectors": {
      "fields": [
        {
          "allowed": "false (default) or true",
          "name": "enabled",
          "required": false
        }
      ],
      "notes": "Off restores only the recognized 1.0 endpoint. The option does not set the weather preset or guarantee visible fog."
    },
    "source_container": {
      "format": "Xbox XBE .data scalar, section-digest repair",
      "hash_pins": [
        "311636b9459867b8fb1fb57be66e6bee17660119754995f678f8f9e1f6642520",
        "9a6c2b318862584e4831c20c289a3686cf206dc63df001a3cc57bf0758944777",
        "a2dd6d42a842bb0da56a1acb2da8b76580acd0dd73b4769bb5a0fa15922374ae",
        "5c18644f31c7c71ac8aa3c5b389788ce29be30d9487932e3a6fa8f4528da9e5f"
      ],
      "resource": "VA 0xA867F4, existing dry-weather haze endpoint",
      "retail_file": "ESPN NFL 2K5 (USA)/default.xbe"
    },
    "summary": "Change one existing dry outdoor haze endpoint from 0.8 to 1.0, with recognized Off restoration. Does not force fog or add sky art; camera parameter proof only.",
    "surface": "stadiums_fields",
    "title": "Existing dry-weather haze response (experimental)",
    "validation_command": "python3 tests/mod_editor/test_nfl2k5_weather_native.py"
  }
]
```

Sort all capability IDs and serialize with `indent=2, sort_keys=True` after merging.
