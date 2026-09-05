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
7. Check normal KR/PR/K/P and existing SLOT/NCB/DCB rows, plus normal CPU roster
   sorting. An untouched older save begins without these lock bits.
