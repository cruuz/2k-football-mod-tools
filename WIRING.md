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

# r61b screen-pass handoff (2026-09-05)

This section is additive to the depth-lock handoff above. The screen resource
compiler, archive transaction adapter, screen-only wizard path and standalone
tests are implemented. Protected files below were inspected but not edited.
Everything is **EXPERIMENTAL / UNWITNESSED**. See `ASTRA_SCREEN_PASS_REPORT.md`
for scope, exact measurements, the skipped-play inventory and Noah's protocol.

## BuildPlan, presets and dispatch

In `mod_editor/core/mod_build.py` add:

```python
screen_timing: str | None = None  # None/off or A/B/C/D; PLAY data only
```

Accept exactly `None`, `"A"`, `"B"`, `"C"`, `"D"`; reject booleans, empty strings
and other values before copying an image. Include this field in recipe parsing,
round trips and build receipts. `to_recipe()` already uses `asdict`. Set it
**explicitly** in all three `PRESETS` so switching away from Experimental clears
an earlier selection:

```python
"softdrink_basic":        { ..., "screen_timing": None },
"softdrink_advanced":     { ..., "screen_timing": None },
"softdrink_experimental": { ..., "screen_timing": "D" },
```

Add availability under `screen_timing`, requiring core
`nfl2k5_screen_timing`, core `nfl2k5_formation_play_writer`, core
`nfl2k5_playbook_pack`, and tool `nfl2k5_playbook_position_recode` (the existing
OuterImage owner). This option requires a disc image. Include it in the existing
image-only source check and in any early “nothing selected”/build eligibility
checks. It does not imply an XBE patch or depend on the depth-row allocator.

Dispatcher position in `build()`: **after the `plan.depth_roles` block**, hence
after position-pool recoding, kickoff alignment, seven-on-seven books and
community playbook packs. Category-only recodes commute with the screen pass.
An authored pack that changed a named retail screen conflicts and must refuse;
never bypass pins with `allow_custom`. An authored replacement of an unrelated
play is allowed, subject to remaining node capacity.

The resource dispatcher tuple and level kwarg are concretely:

```python
# In the PLAY-resource portion of mod_build.build(), after depth_roles:
for level, module, key, label in (
    (plan.screen_timing, _core_module("nfl2k5_screen_timing"),
     "screen_timing", "Screen pass timing (experimental)"),
):
    if level is None:
        continue
    if module is None:
        raise RuntimeError("The screen timing module is not available in this build")
    step = module.apply_to_image(
        target, level=level,
        progress=lambda msg: progress(msg, 0, 0),
    )
    receipt["steps"].append({"step": key, **step})
```

`apply_to_image` opens the existing `OuterImage` owner with a context manager;
`apply_to_archive` preflights all 37 books, requires each book at its pinned outer
entry, refuses mixed retail/applied books, writes only exact byte differences,
checks all preimages/read-backs and rolls back attempted writes, including short
writes. Rollback failure explicitly requires discarding the output copy. Build
must continue to pass its disposable **target copy**, never the source image.
The resource API remains `status(raw, level="D")` and
`apply(raw, level="D") -> (bytes, receipt)`. `inspect` gives individual play
reasons/capacity; `inspect_archive` and `inspect_image` give all-book status.

**`nfl2k5_throw_tuning._apply_all` tuple/kwarg: no screen entry and no
`screen_timing` kwarg.** That dispatcher operates on executable bytes.
`screen_timing.apply(default_xbe)` deliberately refuses. Passing this module to
its XBE tuple would be a type/ownership error. The tuple above is the required
PLAY-resource pass, not an executable hook. Tier 2 remains deferred.

## The four throw-tuning status dictionaries and build inspection

Spell these out when wiring the protected `nfl2k5_throw_tuning.py`:

| Dictionary/function | `screen_timing` value and source |
| --- | --- |
| `read_xbe` | `"n/a"`; an XBE has no PLAY resources |
| `read_image` | `"unchecked"` at this low-level XBE reader; `mod_build.inspect` replaces it using `inspect_image` |
| `write_xbe_copy` | `"n/a"`; this writer cannot apply screen data |
| `write_image_copy` | `"unchecked"`; its shared executable pass precedes the later PLAY pass |

Never infer `applied` from an XBE or advertise an XBE-copy screen switch.
In `mod_build.inspect`, initialize `screen_timing` to `"n/a"`; for disc images
call `inspect_image(source, level=selected_level or "D")`. Preserve `level` and
per-book diagnostics in a sibling `screen_timing_details` entry. Refresh when
the selected level changes. A different installed level is `foreign` for the
requested experiment; rebuilding from the baseline is required. Some levels
are byte-equivalent in books without a matching value; status reflects bytes,
not historical provenance. Books with no eligible action are successful no-ops.
A mix of baseline and applied books is refused, except no-effect books.
The final build step receipt supersedes the early `unchecked` value and includes
all 37 book receipts. Keep exact `changes`, `shared_changes`, play names/indices,
outer indices, hashes and changed-byte counts in the **local** build receipt.
Do not copy preimages, retail names/nodes or book dumps into shareable recipes.

## Gameplay Patches and Build controls

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, add this `PATCHES`
entry and add `"screen_timing"` to `NEEDS_IMAGE`:

```python
("screen_timing", "Screen pass timing (EXPERIMENTAL / UNWITNESSED)",
 "Retail: some screens already tell linemen to hold, release and block. "
 "Patch: A changes half-second holds to 0.8 seconds; B changes nominal "
 "ten-yard QB drops to seven; C sets an explicit 0.6-second pass delay; "
 "D combines them. Screens without the full release sequence are listed "
 "and left alone. These are experiments, not measured improvements. "
 "Requires a disc image and paired play tests."),
```

Add corresponding compact label/helper text if the panel uses `PATCH_LABELS`
(the existing display overrides); preserve EXPERIMENTAL / UNWITNESSED there.
Use an enable checkbox plus an A/B/C/D combo, default D; serialize the selected
**string**, not the checkbox boolean. Unticked means `None`. Restore both controls
from a recipe, and use the combo value for inspection and `BuildPlan` creation.
Apply the same mapping to `build_panel_qt.py` and any `studio_qt.py` forwarding.
Do not make A, B, C or D separate independently stackable booleans.

Build `_option` caption (33 characters, below 60):

```python
self._option(g, "screen_timing", "Screen pass timing (experimental)",
             "UNWITNESSED. Choose A, B, C or D and compare paired snaps.")
```

Show the level combo beside that option. Include it in preset reset/restore,
plan collection and image-required enable/disable logic. Add “screen timing”
to the Experimental preset's explanatory caption. Basic and Advanced remain
explicitly off. The Create a Play screen preset controls already ship here;
no additional wizard wiring is needed for these presets.

## Packaging, closure and registry

Add this exact new line to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_screen_timing.py
```

Keep the existing lines for `nfl2k5_play_library.py`,
`nfl2k5_formation_play_writer.py`, `nfl2k5_playbook_inspector.py`,
`nfl2k5_play_codec.py`, `nfl2k5_playbook_pack.py`,
`mod_editor/gui/create_play_wizard_qt.py`, and
`tools/nfl2k5_playbook_position_recode.py`. No assets, memo copies, test fixtures,
private receipts or `.scratch/` paths belong in the release.

In protected `packaging/check_2k5_mod_studio_runtime.py`, add
`"mod_editor/core/nfl2k5_screen_timing.py"` to required runtime paths and
`"mod_editor.core.nfl2k5_screen_timing"` to runtime import smoke coverage. The
transitive closure is the existing codec, formation writer, PLAY inspector,
universal asset index, source-cache constants, playbook-pack adapter, `nfl_outer`
and `nfl2k5_playbook_position_recode`/OuterImage. No assembler, capstone or unicorn
is required at runtime. The wizard's screen-only lazy import of the formation
writer uses an already packaged module.

Registry handoff (`mod_editor/capabilities/registry.v1.json`): add capability
`nfl2k5.screens.timing`, game `nfl2k5_xbox`, existing surface `scripts_config`,
classification `offline-writer-proved`; backend module
`mod_editor/core/nfl2k5_screen_timing.py`, operation `write`, command
`python3 -c "from mod_editor.core.nfl2k5_screen_timing import apply_to_image; apply_to_image('<output-copy.iso>', level='D')"`.
This calls the shipped image adapter; there is no separate feature CLI. Set title to
“Experimental screen timing”, GUI `expose: true`, `mode: edit`,
`default_enabled: false`, runtime `status: not-tested`, runtime evidence `[]`.
Selectors: `level` required, `A/B/C/D`; book selection is the complete pinned
37-resource census, never a guessed subset. Source: fixed NFL PLAY spans in
USA XISO; hash pin `7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
Public distribution: source/schemas only, never bundle retail data, mod payload
metadata-only (the level). Evidence: `ASTRA_SCREEN_PASS_REPORT.md` and the three
`test_nfl2k5_screen_*.py` files. Validation command:
`python3 tests/mod_editor/test_nfl2k5_screen_timing.py`. Constraints: all 37
books, declared-length pins, verified zero pool tail, capacity and transaction
checks, refusal on changed named screens. Portme: Noah's paired snaps, then
consider tier 2 only with independent evidence and the allocator.
Extend the existing NFL PLAY authoring capability's description/constraints
with the HB/WR/TE screen preset, actual assignment-slot reads, 31-node full
play cost, type-9 endpoint guide and UNWITNESSED label. No new schema surface
enum is needed.

## Existing XBE gate failure, independently reproduced

Both `test_xbe_patch_memory_writes.py` and `test_xbe_patch_cave_references.py`
fail in their existing `setUpClass` when `nfl2k5_depth_locks.apply` reports
`unknown bench promotion call sites`. The same failure reproduces in a clean
`git archive HEAD` snapshot of the starting branch, without any screen changes.
The report records exact outcomes. This requires the depth-lock/practice-squad
integration owner's repair; these files and their patches are outside the
screen task's ownership. No tests were weakened or skipped to conceal it.

There is **no screen XBE apply to compose into those setUpClass chains**, and
no new XBE owner, reservation, section digest or cave-manifest regeneration
is needed for this data-only task. The screen tests explicitly reject XBE
input. Once the existing stack failure is repaired, rerun both unchanged gates.
# Animations handoff: r61b-bone-anim, 2026-09-05

This section is independent of the depth-lock handoff above. Keep that existing
handoff intact. Animations is EXPERIMENTAL / UNWITNESSED, an offline inspector
and exporter with an in-memory existing-SMCD replacement API. It has no XBE
patch, cave, archive write operation, or disc-copy writer. Import stays disabled.
The implementation and evidence are in `ASTRA_BONE_ANIM_REPORT.md`.

## Studio registration (Claude edits protected studio_qt.py)

1. Add `from mod_editor.gui.animations_panel_qt import AnimationsPanel` next to
   the Models import. Do not modify ModelsPanel or models_panel_qt.py.
2. Immediately after the Models navigation item (currently around line 2244),
   add the navigation item below. The visible tab/page name is **Animations**;
   the panel itself has a persistent **EXPERIMENTAL / UNWITNESSED** badge.

   ```python
   animations_item = QListWidgetItem("  Animations")
   animations_item.setData(Qt.UserRole, "animations")
   animations_item.setSizeHint(QSize(210, 44))
   animations_item.setToolTip(
       "Experimental, unwitnessed animation inspection and export. Import is disabled."
   )
   self.navigation.addItem(animations_item)
   ```

3. Immediately after the Models page registration (currently around line 2503),
   register the matching page in exactly the same relative order:

   ```python
   self._animations_panel = AnimationsPanel(self.facade)
   self.pages.addWidget(self._page_scroll_host(self._animations_panel))
   ```

   The shell directly connects navigation row to stacked-page index. Adding
   only the navigation item or only the page would shift all later pages.
   Keep navigation identifiers and any shell tests/row expectations in sync.
4. The panel uses the existing `facade.models_source_paths` tuple (pack index,
   resource inventory). No new archive extraction or facade cache is needed.
   Beside the Models reload around line 7457, call
   `self._animations_panel.reload()` after those paths are ready. For explicit
   sources/tests, call `set_source_paths(index_path, inventory_path, xbe_path=None)`
   followed by `reload()`. On source replacement, use `set_source_paths` first
   to invalidate old asynchronous results and clear the old selection.
5. In `_refresh_entered_page`, before the category-row bounds check, handle
   `_navigation_key(row) == "animations"`: refresh the panel if the source
   paths are ready and return. Avoid repeated whole-catalogue reloads while
   a job is running; `reload()` already refuses concurrent jobs.
6. The optional executable picker reads only the two pinned embedded roots;
   it does not search an executable or infer roster style names. No automatic
   facade XBE inference is necessary. On a different source, clear this optional
   path unless the caller has explicitly selected its matching retail XBE.
7. There is no `disc_written` signal to wire into Launch Latest Build. Neither
   export nor What would change produces a game build. Keep the disabled
   `import_button` disconnected; changing `IMPORT_ENABLED` alone deliberately
   does not enable it. Claude must add a reviewed transport and explicitly wire
   import after the gates, rather than relabelling a preflight as an import.
8. Keep the worker pool/`task_delivery.bound` lifetime handling and close/wait
   behavior. The panel has direct offscreen-test seams (`apply_clip`,
   `apply_catalog`, `select_identity`, `export_to`, `wait_idle`).

## Dispatcher, BuildPlan and patch UI: explicit applicability decision

The common brief's executable-patch integration fields are **not applicable**
to this data-only inspection surface. Adding a dummy build flag would imply a
write path that is deliberately unavailable. In particular:

| Requested integration point | Animations decision |
| --- | --- |
| `nfl2k5_throw_tuning._apply_all` tuple | No tuple entry; there is no XBE apply function. |
| `_apply_all` kwarg | No animation kwarg. |
| Four status dictionaries (`read_xbe`, `read_image`, `write_xbe_copy`, `write_image_copy`) | No animation entries in any of these four `nfl2k5_throw_tuning.py` dictionaries. The panel owns read/export status; `Replacement.status(payload)` is an offline whole-resource check only. |
| `BuildPlan` field | None for this tier. |
| Basic / advanced / experimental build presets | None enables animation import or patches. The inspector is separately labelled experimental. |
| Gameplay Patches `PATCHES` text | No entry. If a future release creates one after the writer/transport gates, reserve the explicit caption `Retail Animation Patch`; it contains both **Retail** and **Patch**. Do not add it now. |
| Gameplay Patches `NEEDS_IMAGE` | No entry; the inspector reads the facade archive, not a build patch. |
| Build tab `_option` caption | No option now. Future reserved caption `Replace an existing animation` is 29 characters, below 60. |
| Cave reservations and XBE section digests | No allocations or executable writes; no manifest regeneration for Animations. Embedded replacement remains refused. |
| XBE guard owner enumeration | No new owner or apply step in either `setUpClass`; there is no executable patch to compose. |

`Replacement.apply(bytes)` returns a same-length **SMCD wrapper plus body** and
receipt. It never accepts an XBE as a replacement target. Exact changed bytes,
4-byte key words, and pack-coordinate byte spans are separately reported.
A future archive transport must reread and pin the complete source span before
writing only into an output copy, handle cross-pack spans transactionally, and
verify the final bytes. The current CLI/UI never performs that transport.

## Release allowlist and runtime closure (Claude edits protected files)

Add these exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_animation.py
mod_editor/core/nfl2k5_animation_math.py
mod_editor/gui/animations_panel_qt.py
tools/nfl_motion_inventory.py
```

Retain these existing allowlist entries, which close the lazy read path:

```text
mod_editor/gui/task_delivery.py
tools/nfl_outer.py
tools/nfl_scene_probe.py
tools/nfl_scne_inventory.py
tools/nfl_txtr.py
tools/xbe_info.py
```

Add to the runtime import check in `packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_animation",
"mod_editor.core.nfl2k5_animation_math",
"mod_editor.gui.animations_panel_qt",
```

Also force the lazy closure during that smoke check, since importing the core
alone intentionally does not open an archive:

```python
from mod_editor.core import nfl2k5_animation
for module_name in (
    "nfl_outer", "nfl_motion_inventory", "nfl_scene_probe",
    "nfl_scne_inventory", "nfl_txtr", "xbe_info",
):
    nfl2k5_animation._tool(module_name)
```

The portable math helper embeds the already recovered fixed sine table and
constants. It needs no shared library, compiler, NumPy, Capstone, Unicorn,
research report, or retail executable for archive inspection. The compiler is
used only by the optional numerical reference tests. No `.scratch` data,
retail native sidecars, or exported animations belong in a release.

## Capability registry entry (Claude adds this reviewed row)

Add the following to `mod_editor/capabilities/registry.v1.json`, sorted by id.
Use the existing `models_shap_scne` registry surface to avoid inventing another
surface enum in its locked 20-surface schema. The separate workspace is still
named Animations. No `core/capabilities.py` edit is needed: operation `export`
and GUI mode `export` ensure `can_queue_replacement` remains false. The
experimental badge is explicit in the new panel and title, independent of the
adapter's surface-derived badge.

```json
{
  "id": "nfl2k5.animations.inspect_export",
  "title": "Animations (EXPERIMENTAL / UNWITNESSED)",
  "game": "nfl2k5_xbox",
  "surface": "models_shap_scne",
  "classification": "read-only-mapped",
  "summary": "Catalogue archive animation roots and two explicitly identified embedded roots separately; preview local poses and export glTF with mandatory native bytes and metadata. Import is disabled.",
  "backend": {
    "module": "mod_editor/core/nfl2k5_animation.py",
    "command": "python3 -m mod_editor.core.nfl2k5_animation --index <vc_53450030/0> --inventory <resource-inventory.json> export <archive:outer/chunk> --output <new-export-directory>",
    "operation": "export"
  },
  "gui": {
    "default_enabled": true,
    "expose": true,
    "mode": "export",
    "reason": "Experimental inspector with disabled import. What would change checks an edited native-key JSON file and writes no game data."
  },
  "input_constraints": [
    "Use a canonical resource inventory and the user's matching archive. Only referee 3107/27 and player 3092/163 have named skeleton bindings; other families remain unresolved.",
    "Embedded inspection accepts only the pinned retail XBE and headers 0x0086dfe0 and 0x008528e8. This is not an exhaustive embedded-root census.",
    "Existing SMCD key preflight fixes identity, name, channels, frames, rate, multiplier, duration and flags; events, trajectory, auxiliary fields and slack retain their bytes.",
    "MMCD and embedded replacement, arbitrary edited-glTF ingestion and disc writes remain disabled."
  ],
  "selectors": {
    "fields": [{"name": "identity", "required": true, "allowed": "archive:<outer>/<chunk> or one of xbe:0086dfe0 and xbe:008528e8"}],
    "notes": "Multi-root resources are separate selectable parts; packed channel count alone never assigns a skeleton family."
  },
  "source_container": {
    "format": "Uncompressed SMCD/MMCD archive resources and explicitly identified absolute-pointer XBE roots",
    "retail_file": "vc_53450030/0 and optional default.xbe",
    "resource": "5,198 inventoried archive resources, 6,068 roots; two separately identified embedded roots",
    "hash_pins": ["73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9", "75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f", "a86c827b09db69990c4070cbb59d5c989db420a9d03427acd814823361a82e52"]
  },
  "runtime": {
    "status": "not-tested",
    "scope": "No gameplay witness. Local portable poses have no captured actor root, live player proportions or high-body postprocess. glTF bakes are inspection representations.",
    "evidence": ["ASTRA_BONE_ANIM_REPORT.md"]
  },
  "public_distribution": {
    "game_data": "never-bundle-retail-data",
    "mod_payload": "user-authored-inputs-and-recipes",
    "tooling": "source-and-schemas-only",
    "rule": "Ship source and tests only. Native sidecars and inspection exports contain original game data and stay with the user's local extraction."
  },
  "evidence": ["ASTRA_BONE_ANIM_REPORT.md", "tests/mod_editor/test_nfl2k5_animation.py", "tests/mod_editor/test_nfl2k5_animation_retail.py", "tests/mod_editor/test_animations_panel_qt.py"],
  "portme": ["Complete Noah's witness plan and transactional archive transport before explicitly enabling import.", "Resolve additional skeleton ownership and live root/proportion state before claiming gameplay-equivalent exports."],
  "validation_command": "python3 tests/mod_editor/test_nfl2k5_animation.py"
}
```

## Existing stack gate failure requiring a separate fix

Both `test_xbe_patch_memory_writes.py` and `test_xbe_patch_cave_references.py`
currently fail in `setUpClass` at `nfl2k5_depth_locks.apply`, with
`DepthLockError: ... unknown bench promotion call sites`. The same failures
were reproduced from a clean `git archive HEAD` snapshot within `.scratch`.
No animation module is imported by either failing setup. No protected file or
other feature's patch was changed to mask the failure. Claude must repair the
existing stack composition before declaring those global gates green.
