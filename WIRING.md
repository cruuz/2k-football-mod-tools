# Guardian cap route B handoff, 2026-09-05

The resource compiler is complete. This section specifies the remaining
protected-file integration for Claude; the earlier depth-lock handoff below
is retained. See `ASTRA_GUARDIAN_CAP_REPORT.md` and
`reports/guardian_cap_receipt.v1.json`. Label this feature
**EXPERIMENTAL / UNWITNESSED** in the build and receipt views.

## BuildPlan and resource dispatcher

In `mod_editor/core/mod_build.py`:

- Add `BuildPlan.guardian_cap: bool = False`. Recipe serialization uses
  `asdict`, so retain the field when loading recipes too. Explicitly set
  `guardian_cap=False` in `softdrink_basic` and `softdrink_advanced`, and
  `guardian_cap=True` only in `softdrink_experimental`. Explicit false values
  matter when switching from Experimental back to another preset.
- Add availability for `nfl2k5_guardian_cap`, `nfl2k5_models`,
  `nfl2k5_p8_texture_writer` and the tool closure listed below. No private
  inventory, authored PNG, or research directory is a runtime dependency.
- `inspect()` starts `guardian_cap` at `"n/a"` for XBE inputs; on XISO use
  `cap.image_status(source)` (`retail`, `applied`, or `foreign`). The three
  resources must agree. A partially applied set is `foreign`, even when
  each individual resource has a recognized hash.
- Preflight before copying: if enabled, require an image and require
  `cap.image_status(source) in {"retail", "applied"}`. Display
  `"Guardian caps need a disc image with the original player models and Detroit away helmet, or this exact cap trial."`
  when it refuses. No roster patch or selector change is implied by this flag.
- Keep `guardian_cap` out of `wants_xbe_patch()`. A guardian-only build takes
  the existing copy-first branch. Include the flag in any Build/Gameplay
  nonempty-selection validation and plan/checkbox/status maps.
- Dispatcher position: run this **resource pass** on the target copy after
  existing XBE, PLAY/ROST, model and texture passes, before final
  `receipt["result"] = inspect(target)`. Place it after commentary in the
  current `_build`. This ordering makes a conflicting model/Detroit helmet
  edit refuse instead of silently overwriting either author. Other spans
  and unrelated prior archive edits remain composable. A future unified
  span planner should register these same three physical owners before any
  writes and refuse overlapping requests during preflight.

```python
if plan.guardian_cap:
    cap = _core_module("nfl2k5_guardian_cap")
    if cap is None:
        raise RuntimeError("Guardian caps are not available in this build")
    progress("Adding guardian caps to helmet C", 0, 0)
    cap_receipt = cap.apply_to_image(target)
    receipt["steps"].append({"step": "guardian_cap", **cap_receipt})
```

`apply_to_image` explicitly operates on a private build copy. All three
spans compile and revalidate before writing. Keep the existing build's
failure/publication handling: discard an incomplete target after an I/O
error. Disabling the flag means build from the original source again;
it does not undo a cap already present in the input image.

## `_apply_all`, kwarg and the four status dictionaries

The executable dispatcher `nfl2k5_throw_tuning._apply_all` accepts **XBE
bytes**. This feature accepts **SCNE/TXTR bytes**. Its tuple entry is
**none**, its executable kwarg is **none**, and neither `apply` nor
`status` may receive an XBE. Do not add it to the executable eligibility
conditions in `write_xbe_copy`/`write_image_copy`. The resource dispatcher above
is the required integration point; adding an ordinary XBE tuple would
always fail its source hash gate.

For uniform status presentation, these are the four protected dictionaries
in `nfl2k5_throw_tuning.py` and their exact treatment:

| Dictionary | Guardian entry |
|---|---|
| `read_xbe()` return | `"guardian_cap": "n/a"` |
| `read_image()` return | `"guardian_cap": cap.image_status(path)` on the image path, with error mapped to `foreign` |
| `write_xbe_copy()` post-write return | `"guardian_cap": "n/a"` |
| `write_image_copy()` post-write return | `"guardian_cap": cap.image_status(target)` after the image writer closes its handles |

Those low-level disc dictionaries report current resources; they do not
apply this pass. `mod_build.inspect()` rechecks after its resource passes
and is the final build status. Add a lazy import at image call sites to
avoid loading the resource compiler for XBE-only operations. Use the actual
local image-path variable in each function (`source`/`target` as appropriate).

This feature has no XBE bytes, cave owner, runtime globals, or section
digest updates. Do not compose it into either XBE-only safety test's
`setUpClass`: those accept an executable, not resource spans. The unchanged
tests currently fail at depth locks with `unknown bench promotion call sites`;
the same failure was reproduced from an untouched HEAD archive. Resolve
that existing stack issue with its owners; do not suppress it or weaken pins
for this resource feature. Route A will need its own executable owner and
the usual composed safety gates when implemented.

## Gameplay Patches and Build captions

Add this `PATCHES` entry in `mod_editor/gui/gameplay_patches_panel_qt.py`
and `"guardian_cap"` to `NEEDS_IMAGE`:

```python
("guardian_cap", "Guardian caps on helmet C (experimental)",
 "Retail: Helmet C has its normal hard-shell look. Patch: Every player wearing "
 "helmet C shows a guardian cap. Helmet C's normal look is replaced while this is on. "
 "Only Detroit's current away uniform gets the neutral gray cap artwork. "
 "Other uniforms keep their current artwork. This affects C wearers in practice "
 "and games alike. It does not add a separate player choice or put caps on everyone "
 "in practice. Appearance and shine still need an in-game check. "
 "EXPERIMENTAL / UNWITNESSED.")
```

The exact required two-sentence disclosure is also exported as `cap.UI_TEXT`.
Keep it visible beside the toggle rather than solely in a receipt. Connect
the Gameplay choice to the BuildPlan resource pass, including a resource-only
build without any XBE toggle. Add any separate short-label mapping on that
panel with the same key.

In `mod_editor/gui/build_panel_qt.py`, add an option under presentation:

```python
self.guardian_cap_check = self._option(
    pl, "guardian_cap", "Guardian caps on helmet C (experimental)",
    cap.UI_TEXT + " Neutral gray artwork is for Detroit current away only. "
    "EXPERIMENTAL / UNWITNESSED.")
```

The caption is 40 characters, within the 60-character limit. Wire its
enabled/source-state handling, checked value, and preset handling. Add the
`guardian_cap` key to the Studio-to-BuildPlan handoff in `studio_qt.py`.
Do not change Rosters, `models_panel_qt.py`, or add Guardian as raw selector
2/3. Existing Revolution/helmet C selection is the test's player choice.

## Allowlist and runtime closure

Add these exact release allowlist lines (no generated `.span`, retail
resource, `.scratch/`, or private PNG):

```text
mod_editor/core/nfl2k5_guardian_cap.py
ASTRA_GUARDIAN_CAP_REPORT.md
reports/guardian_cap_receipt.v1.json
```

Existing allowlist entries must retain the modified
`mod_editor/core/nfl2k5_models.py` and
`mod_editor/core/nfl2k5_p8_texture_writer.py`. Direct/lazy runtime closure:

```text
mod_editor.core.nfl2k5_guardian_cap
mod_editor.core.nfl2k5_models
mod_editor.core.nfl2k5_p8_texture_writer
mod_editor.core.platform_compat
nfl_outer
nfl_scene_probe
nfl_scne_inventory
nfl_scne_gltf
nfl_txtr
nfl_vc_lz_fill
nfl_live_helmet_txtr_png_import
nfl_live_helmet_txtr_targets
nfl_tset_png_import
nfl_all_texture_xiso_workflow
```

The P8 writer also retains its existing transitive closure. In protected
`packaging/check_2k5_mod_studio_runtime.py`, add the three product modules
above to `product_modules` where absent and ensure these lazy tool modules
are exercised. Assert `ModelSpanSource`, `compile_live_helmet_span`,
`apply_resources`, `image_status`, and `apply_to_image` are callable; assert
the 256x256 generated RGBA length and foreign-byte refusal without any game
data. No Pillow, Blender, capstone, unicorn, native compiler, or network
dependency is added by guardian-cap compilation. Run the new standalone
test in Linux/macOS/Windows CI under the existing test discovery.

## Capability registry entry for the new toggle

Add capability `nfl2k5.models.guardian_cap_c_trial` to the existing
`models_shap_scne` surface, game `nfl2k5_xbox`; no new surface enum/schema
is necessary. Populate the registry entry with:

- Title: `Guardian caps on helmet C (experimental)`.
- Classification: `offline-writer-proved`; runtime status: `not-tested`,
  runtime evidence: `[]`, scope: `EXPERIMENTAL / UNWITNESSED. No game was run.`
- Backend module: `mod_editor/core/nfl2k5_guardian_cap.py`, operation: `write`,
  command: `python3 -m mod_editor.core.nfl2k5_guardian_cap --index <pack0> --output <new-directory>`.
- Evidence: `ASTRA_GUARDIAN_CAP_REPORT.md`,
  `reports/guardian_cap_receipt.v1.json`,
  `tests/mod_editor/test_nfl2k5_guardian_cap.py`.
- GUI: `expose=true`, `mode=edit`, `default_enabled=false`; reason includes
  `cap.UI_TEXT`, Detroit-away-only art, and `EXPERIMENTAL / UNWITNESSED`.
  Experimental preset selection is a deliberate opt-in, separate from the
  capability's default state.
- Source container: format `NFL 2K5 Xbox vc_53450030 SCNE/TXTR`, resource
  `o3c113, o3c115, o4002c12`, retail file `vc_53450030/0 and B`, hash pins
  are the three `retail_sha256` strings in `cap.TARGETS`.
- Selectors: one required `guardian_cap` field, allowed `false or true`;
  notes: fixed C-family replacement, `09A0:helmet02` repaint, no independent
  player flag. Input constraints: complete retail or complete applied set,
  three fixed spans, no overlap with imported C scenes or this helmet texture.
- Distribution: tooling `source-and-schemas-only`, game_data
  `never-bundle-retail-data`, mod_payload `metadata-only`; rule: distribute
  the profile/flag recipe and receipts, compile from each user's disc.
- `portme`: Noah's practice/LOD/visor/shine witness list from the report;
  route A is a separate grown-section/texture-registration job.
- Validation command: `python3 tests/mod_editor/test_nfl2k5_guardian_cap.py`.

Regenerate the cave manifest only as part of the final integrated stack's
normal source-digest refresh. Guardian route B allocates no executable cave
or writable XBE storage and must not acquire a fabricated cave reservation.

# Depth locks handoff — 2026-09-05

The executable patch, record APIs, native screen setters, safety gates and
bounded execution tests are implemented in this branch. This handoff is the
remaining work in the brief's protected files. No GUI, build orchestrator,
throw-tuning orchestrator or release allowlist was edited here.

## Build integration for Claude

1. Add an experimental, opt-in `BuildPlan.depth_locks: bool = False` flag,
   availability and source-status entries, recipe serialization and receipt
   display. Use `nfl2k5_depth_locks.status(xbe_bytes)` and
   `apply(xbe_bytes) -> (bytes, receipt)`. `read_any` gives per-site diagnostics.
   Do not advertise the feature as runtime witnessed. It works with retail
   depth rows or the existing expanded rows; it requires no position split.
2. Run the patch after the shared XBE pass, position pools and depth-chart
   rows in `mod_editor/core/mod_build.py`, following the existing pure-byte
   post-passes. Feed its result into the existing XBE/section writer. Apply is
   idempotent; mixed/foreign code refuses before mutation. Enable the existing
   returner fix alongside it so unlocked CPU picks receive that bug fix too.
   Both orders with returner fix and both sides of rows expansion are tested.
3. Add the module to `packaging/release-allowlist.txt` and the relevant build
   availability/recipe tests. There is no assembler dependency at runtime:
   embedded bytes are verified against the annotated `.S` source in tests.
4. **Regenerate `data/nfl2k5_cave_reservations.json` after wiring this flag.**
   No new cave or absolute flag was allocated, but six in-place spans now
   have an additional owner and player pad byte +0x52 bits 0..4 are assigned.
   Ensure the manifest builder actually enables/observes `depth_locks`; simply
   rerunning the old preset without the new flag would miss it. The apply
   receipt declares the full span of every edit, including unchanged padding.
   Keep the oracle's source-drift check intact. Until regeneration, the old
   manifest does not describe this new stack.

   ```sh
   python3 tools/nfl2k5_cave_oracle.py manifest \
     '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
     --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
     --work-dir /tmp \
     --json data/nfl2k5_cave_reservations.json
   ```

5. Use the existing output-copy workflow. The new patch performs no file I/O.
   If adding descriptor-based XBE/disc I/O, include
   `getattr(os, "O_BINARY", 0)` in `os.open` flags on Windows; `Path.read_bytes`
   / `write_bytes` and `open(..., "rb"/"wb")` already use binary mode.

## ★ Rosters integration for Claude — no GUI edits made here

The compatibility codec key `unknown_52` is retained so existing record
imports, exports, exact round trips and diffs keep their schema. Its low five
bits are now depth locks; high bits remain unowned and untouched. Star tags
at +0x53 are independent.

```python
player.record.depth_locks
# {'rank': bool, 'side': bool, 'kr1': bool, 'kr2': bool, 'pr': bool}

document.set_depth_lock(player, 'rank', True)   # current rank, including LT/LG

document.set_depth_lock(player, 'side', True)   # current side, including RT/RG

document.set_depth_lock(player, 'kr1', True)    # transfers this team's KR1 claim

document.set_depth_lock(player, 'pr', False)    # releases a claim

document.depth_lock_conflicts(team_index)       # diagnoses duplicate imports
```

- Add a Locks column with independent Rank, Side, KR1, KR2 and PR controls,
  using the document API for writes. Display LT/LG when a T/G has rank 0;
  RT/RG when it has side 0. A player can be on both lists. Do not describe the
  two fields as a single global roster order.
- Wrap edits in the normal undo transaction. A returner role transfer changes
  its previous owner's bit too; undo must include those records. Membership
  snapshots now include locks; transfer/release/rerank clears departing
  assignments and undo restores them. Normal `to_body()` persists all bits.
- Call `depth_lock_conflicts` before saving an edited lock selection. Resolve
  imported collisions explicitly; the patch preserves conflicting locked
  rank values, and a duplicate returner claim resolves to the lowest current
  roster index. Row 7 is overflow, not a unique starter slot.
- Show a note when the target executable lacks the patch: record bits alone
  do not stop a retail executable's auto-depth. Studio returner bit edits take
  effect at the next patched compaction; this API does not immediately rewrite
  saved team returner indices. A build UI must not imply otherwise.
- The existing studio ↑/↓ API `move_in_depth` only moves team pointers. It does
  **not** set rank/side, so do not wire it as an assignment/lock control without
  actually changing the desired chain. Use the existing rank/side fields for
  assigning rows, then set the lock. Never attach a lock just to a list reorder.
- Keep an Unlock action in the studio. The game adds no new label or controller
  binding: swapping in the existing depth screen locks the changed chain on
  both participants; confirmed KR/PR choices and bench promotions lock their
  resulting assignments. Re-selecting returners transfers their claims.

Lock storage is per player, as are retail depth fields. Shared all-star player
records share their bits; a removal from any roster clears that player's
claims. A newly cloned/recreated player is not promised to inherit pad bits.

## Noah's in-game checklist

Use a disposable franchise/save and the built executable carrying the patch.
These checks are still required; no game, GUI, audio or console emulator was
launched for this work.

1. With CPU depth management enabled, move a visibly worse T into the LT
   starting row using the game's existing selection/move action. That swap
   automatically locks its rank. Put the better T at RT and move once in that
   side list to lock it too. Sim a week, inspect both rows, play a snap and
   verify identities. Repeat for LG/RG. Repeat a second week.
2. Confirm a chosen KR, then a distinct PR. The previous KR1 becomes locked
   KR2, matching the existing screen action. Sim two weeks: all three identities
   should survive roster pointer sorting. Change PR and confirm the new man
   persists; cancel a confirmation and confirm it changes nothing.
3. Promote a bench player beyond row 7 and verify the final visible row locks;
   repeat on each chain and on expanded role rows if enabled. Check screen
   navigation and rendering. Locks do not add a new in-game visual indicator.
4. Disable CPU depth management and verify the game still leaves the human
   team alone. Test a CPU team with studio-set lock bits. Unlock through the
   studio and verify the next weekly sort can choose by ratings again.
5. Trade/release a locked player. His old roster's assignment must not migrate
   to the new team; his bits clear on native roster removal. Pick a replacement.
   Test an injury and IR separately: a lock does not promise to override injury
   eligibility or keep an absent player active. Test short rosters and reserves.
6. Cross the preseason/regular-season gate and an offseason/draft transition,
   then save, exit and reload. Inspect both lock bits in ★ Rosters and visible
   assignments in game. Retirements, clones, all-star membership changes and
   third-party save tools can remove/recreate records and need separate checks.

# Season-cap handoff (r61b, 2026-09-05)

This section is additive to the depth-lock handoff above. The season-cap module,
Studio save/DOB changes, Franchise view and both composed XBE gates are implemented.
The brief reserves the dispatcher, Build/Gameplay panels, allowlist and runtime
closure for Claude; the following edits remain deliberately unwired here.
The full calendar engine is wave 2, specified in `ASTRA_SEASON_CAP_REPORT.md`.

## Dispatcher and BuildPlan

In `mod_editor/core/nfl2k5_throw_tuning.py`:

1. Import `from . import nfl2k5_season_cap as season_cap_patch`.
2. Add keyword `season_cap: bool = False` to `_apply_all`, `write_xbe_copy`, and
   `write_image_copy`. Forward `season_cap=season_cap` at both public writers' calls
   into `_apply_all`. Include it in both public writers' “something requested”
   checks so a gate-only request is valid. Keep the original error path for a
   foreign module status, and the already-applied path for an idempotent build.
3. Append this exact tuple to `_apply_all`'s optional-patch dispatcher, after
   `practice_squad` (after depth locks/reserves too when those are integrated):

   ```python
   (season_cap, season_cap_patch, "season_cap_patch", "season cap")
   ```

   Use the existing dispatcher receipt accumulation. The subreceipt has an exact
   one-byte edit (`va`, `file_offset`, `bytes`, `before`, `after`), digest-inclusive
   `changed_bytes`, `sections_repinned`, `experimental=True`, `witnessed=False`,
   `calendar_repaired=False`, index 127, count 128 and the limitation label.
4. Add the key to **all four** status dictionaries, with the correct byte buffer:

   | Function / result | Entry |
   | --- | --- |
   | `read_xbe` | `"season_cap": season_cap_patch.status(payload)` |
   | `read_image` | `"season_cap": season_cap_patch.status(payload)` |
   | `write_xbe_copy` result | `"season_cap": season_cap_patch.status(result)` |
   | `write_image_copy` result | `"season_cap": season_cap_patch.status(after)` |

   None of these should infer installation from save indices or another patch.

In `mod_editor/core/mod_build.py`:

- Add `BuildPlan.season_cap: bool = False`; include it in `has_edits`, XBE-only
  selection and the no-work guard. Recipe JSON uses the existing dataclass path;
  older recipes without the field remain false.
- Set `season_cap=False` explicitly in `softdrink_basic` and
  `softdrink_advanced`, and `season_cap=True` in `softdrink_experimental`. Switching
  from Experimental to either other preset must turn it off. A custom build may
  opt in without enabling 2026: this gate works with a 2004 or 2026 start.
- `availability()["season_cap"] = _core_module("nfl2k5_season_cap") is not None`.
  Add `source_status()["season_cap"] = report.get("season_cap", "unknown")`.
- Forward `"season_cap": plan.season_cap` in `kwargs_xbe`. Include `season_cap`
  and `season_cap_patch` in the XBE step receipt projection so limitations and
  exact edits survive into the build receipt.
- Leave the existing season/year/preseason/playoffs pass and position-pool /
  SPECIAL / depth-lock / reserve ordering intact. The gate owns only 0x2480CD;
  the test composes it after all current owners, and verifies it commutes with
  every `nfl2k5_season_length.GROUPS` patch. No dependency on a new allocator
  exists in wave 1. Wave 2 must coordinate those owners before patch dispatch.

## Gameplay Patches and Build tab

Add this entry to `mod_editor/gui/gameplay_patches_panel_qt.py`'s `PATCHES`:

```python
("season_cap", "128-season franchise gate (experimental)",
 "Retail: the franchise completion check stops advancement after index 30 in retirement. "
 "Patch: the check accepts indices through 127. "
 "Franchise runs to 128 seasons. Dates and ages after 2099 are not repaired yet. "
 "Game birth dates can already be wrong in 2053. EXPERIMENTAL / UNWITNESSED. "
 "Editing a save year does not simulate seasons.")
```

Add `LABELS["season_cap"]` using the title above, the **exact** second sentence
pair from `nfl2k5_season_cap.UI_LABEL`, and a visible `NOT_TESTED` badge. Keep the
experimental qualification visible outside Details. **NEEDS_IMAGE: do not add
`season_cap`**; the module supports a standalone XBE as well as an XBE embedded
in a disc copy. It has no disc-resource writes. Forward the selected bool from
the Gameplay panel's existing writer kwargs/selection list in
`mod_editor/gui/gameplay_panel_qt.py`.

In `mod_editor/gui/build_panel_qt.py`, near `season_2026`, add:

```python
self.season_cap_check = self._option(
    f, "season_cap", "128-season franchise gate (experimental)",
    "Franchise runs to 128 seasons. Dates and ages after 2099 are not repaired yet. "
    "Game birth dates can already be wrong in 2053. Not tested in game.",
    badge=NOT_TESTED,
)
```

The caption is 40 characters, within the 60-character bound. Use the panel's
existing visible unwitnessed badge constant if named differently there. Add this
checkbox to `_apply_plan`, plan construction, both selected-change summaries,
source gates (`needs_image=False`) and the build/no-work predicate. Do not tie
this checkbox to editing a save's year. No automatic witness claim follows from
successfully writing the executable.

## Studio context propagation

`FranchisePanel` now contains a **Build starting year** view setting, defaults to
the document's `base_year` (2004 by default), displays `season 31 = index 30`, and
edits indices only through 127. Year edits in its journal retain the raw index
across context changes, undo and redo. Reading index 128..255 leaves the bytes
and display intact and disables the year spinbox. Its `set_year` API refuses an
out-of-range request without clamping/mutating. The existing write-copy path
still signs the entire save and preserves +0x91327.

For the protected host (`studio_qt.py`) and the other owner's
`roster_editor_panel_qt.py`, carry the known build's starting year into the save
view; do not infer it from a save (no base-year field is proved):

```python
document = rr.load_save(path, base_year=configured_base_year)
# or container.document(base_year=configured_base_year)
save = fs.FranchiseSave.load(path, base_year=configured_base_year)
# bounded save/ROST codec:
document, container = nfl2k5_save_rost.load_save(path, base_year=configured_base_year)
```

Both codecs infer current DOB context only for the known full version-0
franchise envelope. Bare bodies/images or arbitrary wrapped ROST resources use
an explicit `reference_year=current_calendar_year` when known. Uncontextualized
legacy rosters retain their old display interpretation. `set_reference_year`
and `PlayerRecord.copy()` preserve bytes and carry the view context.

- Change the roster panel's `_baseline_record` call to
  `rr.PlayerRecord.decode(raw, self.document.scheme,
  reference_year=self.document.reference_year)`, so DOB comparisons/reset markers
  use the same century as the live record. Refresh the selected player card and
  DOB/CSV previews after changing the Franchise starting year.
- Replace any remaining hard-coded DOB widget bounds with the contextual window
  `[reference_year - 99, reference_year]`; when context is absent the codec uses
  1955..2054. `NUMERIC_LIMITS["birth_year"]` now expresses the broad Gregorian
  domain (1..9999); the setter enforces the narrower unambiguous century window.
  Do not clamp imported legacy encodings (100..127) or rewrite raw bits on load.
- The actual legacy year API lives in **`nfl2k5_save_writer.py`**, despite the
  brief naming `nfl2k5_save_rost.py`. It was fixed as required: `read_save`,
  `read_franchise_fields`, `apply_franchise_year`, `edit_save_file` and
  `write_back_to_hdd` accept `base_year=...`. Thread it through any host/CLI calls
  that already know the build year. Defaults remain 2004.
- Legacy `read_franchise_fields()["season_ordinal"]` is now index + 1, correctly.
  Use the separate `stage_weeks` and `week` keys for +0x91324/+0x91325. The old
  `FRANCHISE_SEASON_ORDINAL_OFFSET` alias remains import-compatible but its
  docstring/comment explicitly says that address is not a season ordinal.

## Packaging, runtime closure, registry and reservation refresh

Add this new line to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_season_cap.py
```

Keep the already-listed changed runtime files in the release: `nfl2k5_save_writer.py`,
`nfl2k5_save_rost.py`, `nfl2k5_franchise_save.py`, `nfl2k5_roster_records.py`,
`nfl2k5_depth_locks.py`, and `mod_editor/gui/franchise_panel_qt.py`. No test fixture,
retail file, brief or `.scratch` artifact belongs in the runtime package.

In `packaging/check_2k5_mod_studio_runtime.py`'s closure imports add
`mod_editor.core.nfl2k5_season_cap`. Retain/import the save writer, both save
codecs, roster records and Franchise panel. The new dependency edges are
Franchise panel -> season cap -> bump-strength section helpers, and both
save/roster views -> save writer. They use only the existing runtime plus Python
standard library; Capstone, Unicorn and an assembler are not required to apply.

Add a capability entry in `mod_editor/capabilities/registry.v1.json`, using the
existing `schedules_franchise` surface (no new surface enum required):

```json
{
  "id": "nfl2k5.schedules_franchise.season_cap",
  "game": "nfl2k5_xbox",
  "surface": "schedules_franchise",
  "classification": "offline-writer-proved",
  "title": "128-season franchise gate (experimental)",
  "summary": "Franchise runs to 128 seasons. Dates and ages after 2099 are not repaired yet. EXPERIMENTAL / UNWITNESSED. Game DOBs can fail in 2053.",
  "backend": {"module": "mod_editor.core.nfl2k5_season_cap", "operation": "apply", "command": null},
  "input_constraints": ["USA Xbox default.xbe or a copied disc image containing it", "Exact retail/applied gate context required", "Gate only; full calendar engine deferred"],
  "source_container": {"format": "XBE", "retail_file": "user-owned default.xbe", "resource": "completion gate", "hash_pins": ["73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"]},
  "selectors": {"fields": ["0x2480CD"], "notes": "1E to 7F, signed imm8; no cave"},
  "validation_command": "python3 tests/mod_editor/test_nfl2k5_season_cap.py",
  "runtime": {"status": "not-tested", "evidence": [], "scope": "No long franchise played or simulated"},
  "portme": ["Complete calendar/DOB engine and Noah's witness list in ASTRA_SEASON_CAP_REPORT.md"],
  "public_distribution": {"game_data": "never-bundle-retail-data", "mod_payload": "user-applied-patch", "tooling": "source-only", "rule": "Do not distribute modified retail executables or saves"},
  "evidence": ["ASTRA_SEASON_CAP_REPORT.md", "tests/mod_editor/test_nfl2k5_season_cap.py", "tests/mod_editor/test_nfl2k5_season_cap_saves.py"],
  "gui": {"default_enabled": false, "expose": true, "mode": "writer", "reason": "Experimental preset only; not runtime proved"}
}
```

Registry `default_enabled=false` describes default browsing, while the explicitly
selected Experimental build preset enables the flag. Keep its experimental badge.
Run registry/schema and existing Build/Gameplay recipe tests after wiring.

Regenerate `data/nfl2k5_cave_reservations.json` only after the final dispatcher
actually enables this owner. Record VA 0x2480CD, length 1; the neighboring 49-byte
context is a validation pin, not an allocation. No new cave, loader space or
mutable state is claimed. Preserve the oracle's unknown/stale-source refusal.

Both XBE gates include the new owner now. They also exposed a pre-existing
depth-lock compatibility error: SPECIAL retains stride 11 but uses its relocated
bench block and `test al,1` swap test. The minimal `nfl2k5_depth_locks.py` context
fix is included: detect the relocated table separately from stride, require the
exact bench bytes and preserve the same runtime patch bytes. Return address
0x244464 and EAX's encoded-chain contract were checked. Source fingerprints must
be refreshed for this file too. Do not restore the old stride-13 assumption.
7. Check normal KR/PR/K/P and existing SLOT/NCB/DCB rows, plus normal CPU roster
   sorting. An untouched older save begins without these lock bits.
