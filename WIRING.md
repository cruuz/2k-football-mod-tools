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
# SPECIAL tab r61b handoff, 2026-09-05

Implemented and tested in this worktree: Noah's exact 13-row order, complete
third player names, 25-pixel row pitch, and a 57-pixel label column. This is
EXPERIMENTAL/UNWITNESSED. See `ASTRA_SPECIAL_TAB_REPORT.md` for native draw
evidence, previews and the witness list. The protected files below were not
edited. The earlier depth-lock handoff remains below this section.

## Existing dispatcher and build wiring

Keep the existing `nfl2k5_depth_chart_rows` module import and the
`depth_chart_rows: bool = False` keyword in `_apply_all`, `write_xbe_copy`, and
`write_image_copy` in `mod_editor/core/nfl2k5_throw_tuning.py`. Keep forwarding
that keyword from both writers. The existing `_apply_all` tuple is:

```python
(depth_chart_rows, depth_chart_rows_patch, "depth_chart_rows_patch", "SPECIAL tab")
```

Keep the four status dictionary entries, each using the matching final bytes:

```python
# read_xbe and read_image
"depth_chart_rows": depth_chart_rows_patch.status(payload),
# write_xbe_copy
"depth_chart_rows": depth_chart_rows_patch.status(result),
# write_image_copy
"depth_chart_rows": depth_chart_rows_patch.status(after),
```

These hooks already exist. No new switch or extra layout pass is needed.
The same `apply` now owns both descriptor edits and reports them. Keep the
existing grown-XBE writer and verification; its checks now cover the new layout.

In `mod_editor/core/mod_build.py`, retain `BuildPlan.depth_chart_rows = False`,
availability, source status, serialization, and receipts. Presets remain:

| Preset | position_pools | depth_roles | depth_chart_rows |
| --- | --- | --- | --- |
| basic | false | false | false |
| advanced | true | true | false |
| experimental | true | true | true |

Keep the existing disc-only dependency checks, pools before rows, and the
depth-roles PLAY pass after the other book writers. Keep the existing call
`tt._apply_all(..., catch_slider=False, arc_table=False, depth_chart_rows=True)`
and `_write_xbe_bytes` read-back. Correct the obsolete BuildPlan comment about
stride 13 and rows on offense/defense: indexing is always `unit * 11 + slot`,
counts are 11/11/11/13, and the extra records belong only to SPECIAL. Change
progress text to `Adding the 13 SPECIAL depth-chart rows`; replace user-facing
`X / Z / SLOT` references with `X / Z / SLWR` in build messages and details.
Do not rename compatibility role keys in saved recipes or PLAY logic.

Depth locks needed one unprotected compatibility correction to pass the
required composed gates: detect expanded rows by table address `0xEE3000`,
not by stride 13. Diagnostic callers should use
`locks.sites(11, special_rows=True)` for expanded rows; `locks.apply` detects
this itself. Its existing flag integration is still the separate handoff below.

## Protected UI text and the Rosters preview

In `mod_editor/gui/gameplay_patches_panel_qt.py`, replace the
`PATCHES[depth_chart_rows]` title with:

`SPECIAL: 13 rows and complete player names (experimental)`

Use this description verbatim, including Retail and Patch:

> Retail: special teams has four depth-chart rows. Patch: SPECIAL shows KR,
> PR, K, P, LS, LGUN, RGUN, NCB, DCB, SLWR, GAD, 3DRB and PWRB together, with
> names beside all available player numbers. Offense and defense keep eleven
> rows and show X / Z receiver labels. Row spacing is three pixels tighter on
> all depth-chart tabs; the font stays the same. Role labels have more room.
> These roles share player lists, so changing one can change another. Requires
> one-pool positions and the playbook roles. EXPERIMENTAL/UNWITNESSED.

Keep `depth_chart_rows` in `NEEDS_IMAGE` and keep the `NOT_TESTED` badge.
Update its presentation-card subtitle to `All 13 SPECIAL roles on one screen,
with complete player names; offense and defense keep eleven rows.` Remove
the obsolete `SPECIAL scrolls` claim. Update the neighboring depth-roles
display text from SLOT to SLWR without changing the book algorithm.

In `mod_editor/gui/build_panel_qt.py`, use that same title for the
`_option(..., "depth_chart_rows", ...)` caption (57 characters, below 60),
the same description for details, and `NOT_TESTED`, `needs_image=True`.
Replace the current details claiming 13 rows per unit and extra rows on both
defenses. Keep the dependency auto-selection and image gating.

No existing SPECIAL row preview was found in the protected/other GUI panels.
The unprotected slot-text helper now provides the source for any Rosters
preview: `nfl2k5_modern_positions.read_depth_chart_units(xbe)["SPECIAL"]`.
Render its records in returned order, using `abbreviation` and `long_name`,
instead of copying a label list. It returns four rows for retail and thirteen
for an expanded table. Keep `read_units` for existing defensive-only consumers.
Use LS/LGUN/RGUN/NCB/DCB/SLWR/GAD/3DRB/PWRB in role tooltips. RGUN and DCB
remain two views of the same CB side chain. No new GUI panel is requested.

## Packaging, manifest and capability closure

These allowlist lines already exist; retain them unchanged:

```text
mod_editor/core/nfl2k5_depth_chart_rows.py
mod_editor/core/nfl2k5_depth_chart_storage.py
mod_editor/core/nfl2k5_modern_positions.py
```

`packaging/check_2k5_mod_studio_runtime.py` already imports rows and storage in
its runtime closure list (currently lines 1739-1740). Modern positions is an
existing runtime dependency; its new helper adds no import dependency. Keep
those imports. The earlier lock handoff additionally needs allowlist entry
`mod_editor/core/nfl2k5_depth_locks.py` and closure import
`mod_editor.core.nfl2k5_depth_locks` when its flag is wired. Do not package the
private preview generator, test harness, Unicorn, Pillow, or retail assets.
No new user-facing capability/surface was added, so no registry entry is needed.

Claude must regenerate `data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after final wiring, using the command
below in the earlier handoff. Preserve source-drift checks. The rows receipt
adds these existing descriptor ownership spans, not cave allocations:

| Owner | Half-open VA span | Section | Actual field change |
| --- | --- | --- | --- |
| depth_chart_rows / summary_row_spacing | 0xAA3744..0xAA3774 | .data | float at 0xAA376C: 4 to 1 |
| depth_chart_rows / summary_label_width | 0x5322D0..0x5322D4 | .rdata | float: 50 to 57 |

Keep the existing 46-record table reservation at `0xEE3000` in the grown
final `.XTLID`; no new cave, runtime global, section or resource is added.
Both source modules' hashes changed, including depth locks' composition fix.
Passing the composed gates does not replace manifest regeneration. No
protected artifact was regenerated in this task.
# Scorebug r61b handoff, 2026-09-05

The existing scorebug option now calls the v7 reference implementation through
`tools.nfl2k5_scorebug_layout.status/apply_in_place`. Code, offline preview,
fixed-span resource writer, XBE fields, staging data generator and local test
disc are complete. All new behavior is EXPERIMENTAL / UNWITNESSED. See
`ASTRA_SCOREBUG_INGAME_REPORT.md`. Protected product files were not edited.

## Dispatcher, BuildPlan and status dictionaries

Keep `BuildPlan.scorebug: bool = False`. Keep the existing image-only
presentation post-pass at `mod_build.py` lines 659 onward. It must own the
scene, atlas and XBE as one preflighted transaction. Set presets explicitly:
basic `scorebug=False`, advanced `scorebug=False` (currently True; disable
until witnessed), experimental `scorebug=True`. The existing option remains
available for explicit selection in other presets. No new user flag is needed.

`nfl2k5_throw_tuning._apply_all` **tuple and kwarg: none for this revision**.
This is a deliberate resource-writer exception to the standard XBE-only
handoff pattern. Applying `apply_xbe` inside that dispatcher first would leave
retail SCNE/atlas plus applied XBE, a mixed state which the transaction correctly
refuses. Do not add a duplicate `(scorebug, ..., ...)` dispatcher tuple or pass
the BuildPlan bit into `_apply_all`. `apply_xbe` is exposed for composition
gates and a future coordinated dispatcher, not as an independent UI option.

For the four XBE status dictionaries in `nfl2k5_throw_tuning.py`, no executable
scorebug enable state is needed for dispatch. If source diagnostics should
expose it, add a read-only `scorebug_xbe` entry to **all four**, as follows:

| Dictionary | Optional exact diagnostic expression |
| --- | --- |
| Loose-XBE source inspection, near line 585 | `"scorebug_xbe": scorebug_reference.xbe_status(payload)` |
| Image source inspection, near line 698 | `"scorebug_xbe": scorebug_reference.xbe_status(payload)` |
| Loose-XBE apply result, near line 1152 | `"scorebug_xbe": scorebug_reference.xbe_status(result)` |
| Image apply result, near line 1337 | `"scorebug_xbe": scorebug_reference.xbe_status(after)` |

These must not replace `mod_build.inspect`'s image-level `scorebug` status,
which checks the complete resource set. Keep the unavailable loose-XBE option
explanation: this feature needs a disc image. Keep the existing availability
call into `nfl2k5_scorebug_source_art.available()`; v7 uses shipped metadata,
independent of the old presentation research audit.

Preserve the full nested receipt in the protected build orchestrator. Replace
the old v6 receipt key filter with at least: `layout`, `experimental`,
`witnessed`, `state_before`, `root`, `textures`, `resources`, `xbe`,
`wrapper_identical`, `runtime_team_logos`, `timeout_dimming`, `under_5_color`,
`animation`. `resources` contains exact spans and hashes; `xbe` contains
every changed field and shared-owner receipts; driver pins are in the metadata
module and report evidence. The old
filter silently loses this information. Continue catching normal exceptions
on the build worker; the new refusal is a `ValueError` subclass.

## Gameplay Patches and Build text

The Build tab already has the option. The Gameplay Patches `PATCHES` tuple
currently does not contain `scorebug`; add it there if this option is mirrored
on that panel, using the existing BuildPlan key:

```python
("scorebug", "Experimental ESPN scorebar",
 "Retail: a stacked score display near the top of the screen. Patch: a wider "
 "display at the bottom, a white clock strip, an ESPN corner mark and a short "
 "slide when the down panel appears. Experimental and not tested in game. "
 "Team logos, timeout counting and a red low clock are still being developed.")
```

Add `"scorebug"` to `NEEDS_IMAGE` there. No second executable-only toggle.
Build tab `_option` caption: **Experimental ESPN scorebar** (26 characters).
Helper: `A bottom score display with a white clock strip and ESPN corner mark.`
Details: `Not tested in game. Team names remain live. Team logos, timeout
counting and low-clock color are still being developed. The kick meter moves
up and the lineup strip is hidden.` Remove the old claim that the shared ESPN
strip is repainted; this version leaves that texture unchanged.

The preview resolver now renders the installable neutral fallback. Do not
substitute the staged-logo target for the default Studio preview or label
sample slide frames as a game capture. A future binding option needs its own
runtime witness before claiming real current-team logos in the installed bar.

## Packaging and runtime closure

Add exactly these new release allowlist lines:

```text
mod_editor/core/nfl2k5_scorebug_ingame.py
mod_editor/core/nfl2k5_scorebug_resources.py
tools/nfl2k5_scorebug_reference.py
```

Keep the existing source-art/layout/position/HUD/boot-logo modules and the
existing `nfl_txtr`, `nfl_vc_lz_fill`, `nfl_tset_png_import`, `nfl_static_gltf`,
`nfl2k5_scorebug_espn_art`, pack locator and XBE digest helpers. The new
runtime imports resolve from these modules and Pillow; there is no SVG
converter, Ghidra, capstone, unicorn, filesystem research corpus or network
dependency in the product path. Metadata is Python, so no new JSON asset
closure is required. `nfl2k5_scorebug_reference` is needed for the default CLI
subcommands; source-art imports the new core directly for Studio previews.

Update `packaging/check_2k5_mod_studio_runtime.py` to import the three added
modules in its isolated runtime closure and assert `source_art.available()`.
Do not allowlist the test disc, raw logo exports, staged RGBA buffers or
documentation previews. They are derived from the user's disc and generated
locally. The existing capability `nfl2k5.scorebug_presentation.inventory`
remains; no new GUI/edit selector is introduced. Amend its evidence/limits
to reference the v7 report if capability copy is updated, keeping runtime
team logos and event hooks explicitly unwitnessed and unimplemented.

Regenerate `data/nfl2k5_cave_reservations.json` with the v7 writer once wired.
Its recorded source hashes necessarily predate these edits. New field
ownership includes the two mark binding pointers, clock contrast words and
down-slide duration/direction. The position constants reuse the already
reserved `0x10A40..0x10A48`; no new code allocation is made. The future hook
at `0xFCE56` is only a candidate in the report, not an allocation.

## Inherited blocker in both XBE gates

Both supplied full gates fail before reaching scorebug code, and the untouched
HEAD versions reproduce the failure. `nfl2k5_depth_locks._context` selects the
retail bench block whenever `modern.layout_stride(payload)==11`, but the
current `nfl2k5_depth_chart_rows` keeps stride 11 while relocating its table
and rewriting that bench block. The depth-lock gate still assumes its older
stride-13 expansion. `sites()`'s swap-chain selection and the hardcoded bench
return addresses also require an audit against the current row writer.

Repair the depth-lock context using the actual table/layout identity, validate
the current bench return addresses and chain test, then rerun the composition
tests and both full gates. Do not accept arbitrary bench bytes, infer an
allocation from the oracle's `unknown`, or disable an owner in the gates.
This task adds the scorebug to both existing `setUpClass` compositions and
adds independently runnable scorebug checks. Both direct scorebug checks
pass; the inherited full-stack errors remain visible and are a release blocker.

---

# Depth locks handoff — 2026-09-05
# Rosters UI integration handoff, 2026-09-05

The host implementation is complete in this branch. Protected files were not edited.
Reserve transactions use signed save copies. Abilities are stored flags only.
No new save allocation, XBE allocation, native menu, or abilities runtime is added.

## Required packaging changes

Add these exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_depth_locks.py
mod_editor/core/nfl2k5_cave_oracle.py
```

The roster record API already imported the depth-lock module lazily; the Locks
column now exercises that import whenever players are displayed. The depth-lock
module imports `XbeImage` from the cave oracle. Both files are absent from this
checkout's allowlist. Its other runtime imports (`nfl2k5_bump_strength`,
`nfl2k5_modern_positions`, `nfl2k5_returner_fix`, `nfl2k5_depth_chart_rows`) are
already listed. Capstone and the assembler are not needed by the host controls.
The salary arithmetic is pure Python; the optional native parity test is not a
product dependency.

Add `mod_editor.core.nfl2k5_depth_locks` and
`mod_editor.core.nfl2k5_cave_oracle` to `product_modules` in
`packaging/check_2k5_mod_studio_runtime.py`. Exercise `PlayerRecord.abilities`,
`depth_locks`, the two reserve transaction entry points, and an offscreen
`RosterEditorPanel` load from a synthetic signed save when extending that check.
The existing roster, franchise, save codec and practice-squad modules are
already in the release closure; no additional product module was created here.

Regenerate `data/nfl2k5_cave_reservations.json` with the existing oracle command
once the final beta-61 stack is composed. Host edits changed source fingerprints;
no cave capacity or runtime address was added. Do not edit fingerprints manually.

## Dispatcher and Build UI contract

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
# r61 XBE space and relocated kickoff handoff, 2026-09-05

This section adds to the depth-lock handoff above. All features below are
EXPERIMENTAL/UNWITNESSED. No protected file was edited. The two new flags default
to false. Enable them only in `softdrink_experimental`; explicitly set both
false in `softdrink_basic` and `softdrink_advanced`. An ordinary custom plan
leaves both off. The allocator reserves two 4096-byte pages, with a named,
unchanged boot bitmap in the code page, plus named kickoff code/data when
requested. This release does not promise an arbitrarily growing arena.

## BuildPlan and dispatcher

Add to `mod_editor/core/mod_build.py::BuildPlan`:

```python
xbe_space: bool = False
kickoff_relocated: bool = False
```

`kickoff_relocated` implies `xbe_space`, `dynamic_kickoff`, `kickoff_alignment`
and `kick_rules`; disable `kick_power` as for the existing dynamic kickoff.
Keep the existing kickoff settings dictionary and playbook alignment pass.
No additional PLAY/ROST changes belong to this relocation.

Add imports in the protected `mod_editor/core/nfl2k5_throw_tuning.py`:

```python
from . import nfl2k5_xbe_space as xbe_space_patch
from . import nfl2k5_dynamic_kickoff_relocated as kickoff_relocated_patch
```

Thread keyword-only `xbe_space: bool = False, kickoff_relocated: bool = False`
through `_apply_all`, `write_xbe_copy`, `write_image_copy`, their kwargs and
nonempty-operation guards. Pass the plan fields through the build service,
recipe round trip, inspection/availability and patch selection routes. Apply
the existing dynamic kickoff before relocation so custom settings are inherited
and all eleven hook sites have an exact known source.

The final `_apply_all` tuple needs this adapter, because allocations must be
chosen before the first growth, and a replay must verify the request set:

```python
class _xbe_space_adapter:
    def __init__(self, with_kickoff):
        self.requests = kickoff_relocated_patch.REQUESTS if with_kickoff else ()

    def status(self, payload):
        state = xbe_space_patch.status(payload)
        if state == "applied":
            xbe_space_patch.apply(payload, self.requests)  # validates replay
        return state

    def apply(self, payload):
        return xbe_space_patch.apply(payload, self.requests)
```

Use this **separate final tuple after uniform choice and boot-logo repair**, at
the end of `_apply_all`, immediately before returning to the section writer:

```python
for flag, module, key, label in (
    (xbe_space or kickoff_relocated, _xbe_space_adapter(kickoff_relocated),
     "xbe_space_patch", "experimental executable space"),
    (kickoff_relocated, kickoff_relocated_patch,
     "kickoff_relocated_patch", "experimental relocated kickoff"),
):
    if not flag:
        continue
    state = module.status(patched)
    _require(state in ("retail", "applied"), f"{label} is {state}; refusing")
    patched, sub_receipt = module.apply(patched)
    receipt[key] = sub_receipt
    receipt["changed_byte_count"] = int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])
```

`mod_build.build` also has later XBE passes for presentation, season, pools,
SPECIAL, depth locks and reserves. Its calls to the earlier shared dispatcher
must leave the new flags false. Once **every existing pass is complete**, read
the final XBE, invoke the final dispatcher with these flags (all other flags
false, `wanted=None`, `arc_table=False`), then send its bytes to the generalized
writer. This makes the allocator last at both entry points. SPECIAL is tested
in either order, but the final build order prevents other owners from claiming
its transferred header storage. Do not run boot-logo relocation or any new
header allocator after these final passes.

Add these entries to all **four** status dictionaries in throw tuning:
`read_xbe` (`payload`), `read_image` (`payload`), `write_xbe_copy` (`result`),
and `write_image_copy` (`after`). Use the corresponding local byte variable:

```python
"xbe_space": xbe_space_patch.status(payload),
"kickoff_relocated": kickoff_relocated_patch.status(payload),
"kickoff_relocated_settings": kickoff_relocated_patch.read_settings(payload),
```

Existing `dynamic_kickoff.status/read_settings` already delegate recognition of
relocated hooks. Include both new status keys in build availability, source
inspection, receipt display and feature selection. Reject adding kickoff to an
already-grown image which did not reserve its named allocations; rebuild from
the supported base. The allocator does not silently shift existing owners.

## Exact image extent and writer changes

Replace only the non-retail-length branch of
`nfl2k5_throw_tuning.image_xbe_extent()` with this snippet. The upper-bound
check happens before reading an untrusted directory length:

```python
if length != EXPECTED_XBE_SIZE:
    _require(length in (depth_chart_storage.FILE_SIZE, xbe_space_patch.FILE_SIZE),
             f"unknown default.xbe grown size: {length}")
    candidate = platform_compat.pread(descriptor, length, offset)
    _require(len(candidate) == length
             and depth_chart_storage.recognized_grown_xbe(candidate),
             "larger default.xbe has a foreign or incomplete grown layout")
return int(offset), int(length)
```

`recognized_grown_xbe()` requires `xbe_space.status(candidate) == "applied"`
for the new size. SPECIAL-only bytes still require complete rows recognition;
a grown SPECIAL table also requires rows recognition. A foreign page, header,
name, counter, allocation directory, code seal, digest or length refuses.

In `mod_build._write_xbe_bytes` and the protected throw writer, route **every
recognized grown payload**, including same-size replays, through
`nfl2k5_depth_chart_storage.write_image_xbe(fd, payload)`. Keep the ordinary
retail writer for retail-size outputs. Do not just gate on `length !=
len(payload)`: the generalized writer also provides rollback/read-back for
same-size writes. It uses the actual directory node, appends the full XBE,
verifies bytes, switches sector/length and verifies the directory; failure
restores the original node/extent or original same-size bytes. Caller owns and
closes the descriptor; use `os.O_RDWR | getattr(os, "O_BINARY", 0)`.

The direct pure-byte `apply` APIs and generalized writer work now. The GUI and
protected readers cannot yet open the new size until this snippet is wired.

## Gameplay Patches and Build tab

Add these exact three-field entries to `gameplay_patches_panel_qt.PATCHES`:

```python
("xbe_space", "Extra patch space (experimental, unwitnessed)",
 "Retail: patches have no spare room for larger changes. Patch: adds room for "
 "experimental features. Needs a disc boot check before regular use."),
("kickoff_relocated", "Kickoff in extra space (experimental, unwitnessed)",
 "Retail: the extra patch space is unused. Patch: moves the dynamic kickoff "
 "there with the same settings. Check that both teams still line up, hold "
 "until contact and return normally. Unwitnessed in game."),
```

Add both keys to `NEEDS_IMAGE`. Use these Build tab `_option` captions (each
under 60 characters), with an experimental badge and the same helper text:

```python
self._option(layout, "xbe_space", "Extra patch space (experimental)", helper, badge="EXPERIMENTAL")
self._option(layout, "kickoff_relocated", "Kickoff in extra space (experimental)", helper, badge="EXPERIMENTAL")
```

Wire both checkboxes to plan serialization and preset reset; a basic/advanced
preset must clear a previously enabled experimental flag. Keep addresses,
section names and allocation details in the receipt, outside the user flow.

## Release closure and capability entries

Add these allowlist lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_xbe_space.py
mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py
```

The changed helper files must retain their existing allowlist entries:
`nfl2k5_bump_strength.py`, `nfl2k5_boot_logo.py`, `nfl2k5_dynamic_kickoff.py`,
`nfl2k5_depth_chart_storage.py`, `nfl2k5_depth_locks.py`, and
`nfl2k5_cave_oracle.py`. No Unicorn/Capstone import is required by the allocator
or runtime patch; those libraries are offline test/proof dependencies only.

Add both new dotted imports to `product_modules` in the protected runtime
closure checker, and exercise the public status/requests exports. Retain its
imports of the listed helpers, the draft assembler and platform compatibility.

When exposing these new surfaces, add registry rows in
`mod_editor/capabilities/registry.v1.json` using the existing complete gameplay
row schema (and update the protected runtime registry counts):

Copy the two complete, schema-validated objects from
`docs/mod_editor/nfl2k5_xbe_space_capabilities.json` into `capabilities`.
This handoff file is documentation, not another runtime registry or allowlist
entry. Its fields are summarized below.

| Field | Allocator | Relocation |
| --- | --- | --- |
| id | `nfl2k5.gameplay.xbe_space` | `nfl2k5.gameplay.kickoff_relocated` |
| backend module | `mod_editor/core/nfl2k5_xbe_space.py` | `mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py` |
| operation | `write` | `write` |
| classification | `offline-writer-proved` | `offline-writer-proved` |
| runtime status | `not-tested` | `not-tested` |
| GUI | experimental edit, default disabled | experimental edit, default disabled |
| evidence | `ASTRA_XBE_SPACE_REPORT.md`, standalone space tests | same, dynamic kickoff tests |
| constraints | pinned USA geometry, recognized prior owners, disposable disc copy, bounded named capacity | same, reserved kickoff requests, matching settings, existing alignment pass |

Runtime scope must explicitly say the kernel/xemu load order, boot bitmap
availability in the new preloaded section, boot and played kickoffs remain
unwitnessed. Do not promote bounded Unicorn execution to a gameplay witness.

## Manifest regeneration

The builder now observes these owners automatically after its complete
experimental disc build, even while the new protected flags are absent. It
records parent pages, named children, unchanged zero-initialized data and
transferred boot-logo storage. Keep the oracle source-drift refusal unchanged.
Claude must regenerate the protected manifest after integration:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json data/nfl2k5_cave_reservations.json
```

`space-proof <retail.xbe> --manifest <manifest.json>` prints the bounded fresh
allocation proof. An optional `--json <path>` records it. Generated ownership
permits the established boot-logo/kickoff children, and refuses other overlaps.

---

# Beta 61 defense integration handoff

This job edits only its listed modules, their tests, its pack and deliverables. No XBE bytes, allocator, release list, registry, build panel, facade, project loader or dispatcher were changed. All new calls are **EXPERIMENTAL / UNWITNESSED**. No true runtime spy ships.

## Required integration fixes

1. **Create-only project reload:** `mod_editor/studio/project_archive.py`, `load_project_archive`, the empty-content check around line 991 must also include:

   ```python
   and not loaded_creates
   and not loaded_links
   ```

   Those lists already exist and are validated above the check. Saving currently includes them, but loading considers a project containing only playbook creations/links empty and rejects it. This is an existing bug affecting offensive packs too. `test_create_only_project_reload_pending_project_archive_wiring` in `tests/mod_editor/test_nfl2k5_defense_play_qt.py` is an expected failure until these predicates are added; remove its `@unittest.expectedFailure` after integration. The companion tests prove Spy survives the actual saved `.2k5mod` manifest, request parsing, `.2k5book` reload and recompilation. Do not put a fake audio/visual edit into a project to bypass the guard.

2. **Build ordering with position pools:** `mod_editor/core/mod_build.py` currently runs `plan.playbook_packs` after `plan.position_pools`. Its comment explicitly assumes packs only edit offense. Defense recipes now require one of 48 proved native personnel/package fingerprints and correctly refuse pooled/foreign category layouts. On a native source, compile the defense packs **before** `nfl2k5_playbook_position_recode.apply` changes the defensive category bytes. Keep the later depth-role pass last and give it the existing `allow_custom=True` handling. Preserve offensive pack ordering relative to other offensive writers; partition by `pack.schema == DEFENSE_SCHEMA` if needed. Do not remove the fingerprint guard to make a pooled source work. Rebuilding from an already pooled disc needs a separately proved inverse translation and source-table fingerprint, which this data-only job does not supply.

   The tested composition is the actual Modern Gun Core pack followed by defense on all 32 native team books, in memory. The full XBE/ROST/position-pool build stack was not run or claimed.

3. **Packaging:** append this exact new line to `packaging/release-allowlist.txt`:

   ```text
   data/playbooks/softdrink_modern_defense.2k5book
   ```

   The changed core/GUI/CLI modules are already allowlisted. The Playbooks panel can generate a pack directly from a native book, so it works in the checkout even before packaging the seed.

## Build and Share surface contract

- **Dispatcher `_apply_all` tuple, kwarg and four status dictionaries:** no new tuple, kwarg, or key in any of the four XBE status dictionaries. This feature has no XBE status/apply routine. Keep `nfl2k5_throw_tuning.py` unchanged. A PLAY recipe cannot truthfully report an XBE patch as applied.
- **`BuildPlan`:** reuse `playbook_packs: tuple[str, ...] = ()`; no new Boolean field is necessary. Basic and Advanced must not automatically enable this unwitnessed pack. Experimental may offer it for explicit selection after the ordering fix, through the existing pack list. The distributed seed targets the 32 team books plus GEN and reference (34); WCO, Editor and PRACTICE are supported explicit validation/retarget targets.
- **Build tab:** existing Add Playbook Pack accepts this v2 file. If a bundled shortcut is wanted, `_option` caption is `SOFTDRINK modern defense (experimental)` (38 characters); selecting it adds the seed path to `playbook_packs`, without a separate XBE flag. Deduplicate against the user's selected paths.
- **Gameplay Patches `PATCHES` / `NEEDS_IMAGE`:** no runtime entry is required. If exposing a data-pack card there, use exactly: `Retail: stock defensive calls. Patch: experimental spot coverages and replacement pressures from retail playbook data. Spy is a shallow middle zone; a true spy needs the runtime patch (not yet shipped).` Add its UI key `modern_defense` to `NEEDS_IMAGE`, route it to the existing pack list, and never claim a runtime spy patch is installed.
- **Share:** the existing Export Playbook Pack preserves `spy_intent` and emits schema `nfl2k5_playbook_pack/v2`. The existing Install path already calls the request mapper and persists the new intent field. No facade argument is required: both defensive GUI paths stage through `install_playbook_pack`. Older importers reject v2 instead of silently losing intent. Custom defensive scripts refuse automatic cross-book guesses; built-in core presets rebuild with each target's own front, coverage header, personnel and package mapping.
- **Runtime closure:** in `packaging/check_2k5_mod_studio_runtime.py`, ensure imports for `mod_editor.core.nfl2k5_play_library`, `mod_editor.core.nfl2k5_play_codec`, `mod_editor.core.nfl2k5_formation_play_writer`, `mod_editor.core.nfl2k5_playbook_inspector`, `mod_editor.core.nfl2k5_playbook_pack`, `mod_editor.gui.create_play_wizard_qt`, `mod_editor.gui.play_designer_qt`, `mod_editor.gui.playbook_pack_dialog_qt`, and CLI `nfl2k5_playbook_pack`. Existing dynamic `nfl2k5_playbook_position_recode` / `nfl_outer` readers remain required. Check that the bundled seed parses as v2; no new dependency or module is introduced.
- **Capability registry:** extend `nfl2k5.scripts.director_playbook` in `mod_editor/capabilities/registry.v1.json` with defense v2 recipes and native personnel fingerprint constraints. Classification remains `offline-writer-proved`. Evidence: `tests/mod_editor/test_nfl2k5_defense_play.py`, `tests/mod_editor/test_nfl2k5_defense_play_qt.py`, `ASTRA_DEFENSE_PLAY_REPORT.md`. GUI reason must say EXPERIMENTAL / UNWITNESSED and use the exact Spy notice. Do not advertise match-quarters or Palms. No runtime spy capability entry yet.

## Future runtime Spy lookup

`PlayCreateRequest.spy_slots` is serialized as `spy_intent = {"schema": "nfl2k5_spy_intent/v1", "slots": [5]}` per authored play. It is part of the selector hash. After final index assignment, the compiler receipt emits `spy_intent.records` containing `play_index`, `slot`, `intent="spy"`, `runtime_available=false`, and a matching `zone_donor_play_index`. The containing receipt identifies the book/asset and source/replacement SHA-256. This is authoring intent, not a PLAY opcode or XBE flag. A later allocator-backed patch must consume the lookup and implement its own identity/lifecycle contract. PLAY bytes alone cannot recover intent; an ordinary shallow zone is deliberately identical.
For the host changes in this job, `_apply_all` gets **no new tuple or kwarg**;
the four status dictionaries get **no host-only patch state**. `BuildPlan` gets
**no reserve-move or abilities field**, and basic / advanced / experimental
presets enable **none** of these data edits automatically. There is no new
Gameplay Patches `PATCHES` entry, `NEEDS_IMAGE` entry or Build `_option` for
abilities or reserve moves. The existing export signal is retained; reserve
moves disable roster JSON export and the core exporter refuses direct calls.

The prior depth-lock runtime handoff is still separate protected work. If wiring
that existing patch as part of the release, its concrete contract is:

- Import `nfl2k5_depth_locks as depth_locks_patch` in throw tuning. Add
  `depth_locks: bool = False` to `_apply_all`, `write_xbe_copy`,
  `write_image_copy`, their forwarding calls and the no-op request guard.
  The dispatcher tuple is `(depth_locks, "depth_locks", depth_locks_patch)`.
  Use `status(payload)` and `apply(payload) -> (bytes, receipt)` in the existing
  pure-byte dispatcher and receipt pattern. Ensure final ordering in `mod_build`
  is after position pools and expanded rows. Enable `returner_fix` with locks.
- Add `"depth_locks": depth_locks_patch.status(payload)` to `read_xbe` and
  `read_image`; use `result` in `write_xbe_copy`'s result dictionary and `after`
  in `write_image_copy`'s result dictionary. Those are the four status dicts.
- `BuildPlan.depth_locks: bool = False`; basic and advanced presets off;
  experimental preset may opt in with `returner_fix=True`. Include availability,
  source inspection, recipe round trips, plan serialization and receipt text.
- Gameplay Patches tuple: key `depth_locks`, caption `Persistent depth locks`,
  text `Retail auto-depth can replace your assignments. Patch: keep independent
  Rank, Side, KR1, KR2 and PR selections. Experimental and unwitnessed in game.`
  Include `depth_locks` in `NEEDS_IMAGE`, following the existing XBE patch gates.
- Build `_option` caption: `Keep depth and returner assignments` (34 characters).
  Include the checkbox in load/store/availability and selected-options summaries.
- The two allowlist and runtime-closure imports above also satisfy this patch.
  The six existing patch spans are already exercised by the two XBE safety
  suites; this branch corrects their expanded-row context validation. Retain
  those tests and regenerate the manifest after wiring the final plan.

## Capability metadata

This adds controls inside the existing `players_rosters` / `saves` surfaces,
not a new surface enum or router destination. A release registry entry can use
`nfl2k5.players.roster_save_management`, backend
`mod_editor.core.nfl2k5_roster_records` (`operation: write`),
`classification: offline-writer-proved`, game `nfl2k5_xbox`, surface
`players_rosters`, and GUI `expose: true`, `mode: edit`,
`default_enabled: false`. Evidence is `ASTRA_ROSTERS_UI_REPORT.md` and the three
new `test_rosters_*` files. Runtime status must remain `not-tested`, with the
report's human witness list; abilities have no gameplay effect in this release.
Input constraints: stable pool/index, version-0 save for reserve moves, valid
ownership/IR and storage, 53 promotion limit, 12 reserves, 65 physical slots,
masked lock/star/ability fields, and signed output copies. Do not widen the
older `nfl2k5.players.disc_roster` entry's narrow legacy writer claims.

---

# Beta 61b option authoring handoff (2026-09-05)

Data-only **EXPERIMENTAL / UNWITNESSED** option authoring. This section supplements,
and does not replace, the defense handoff above. No protected file was edited.
The continuation delivers the core writer/codec/inspector, Create a Play and
Designer changes, standalone tests, and `data/playbooks/softdrink_option.2k5book`.
See `ASTRA_READ_OPTION_BUILD_REPORT.md` for exact replacements and limitations.

- **Dispatcher `_apply_all` tuple, kwarg, four status dictionaries:** none. There
  is no XBE patch or status/apply pair in this data tier. Add no tuple, keyword,
  or status key to `read_xbe`, `read_image`, `write_xbe_copy`, or `write_image_copy`.
- **BuildPlan field and presets:** reuse `playbook_packs: tuple[str, ...] = ()`.
  Basic and Advanced leave this pack off. Experimental may offer explicit
  selection, also off by default. The shipped file targets **MIN only**, pinned
  to its retail PLAY body. Do not silently retarget it or enable it for all teams.
- **Build tab `_option` caption:** `SOFTDRINK option (experimental)` (30 characters).
  Route selection to the existing `playbook_packs` list and deduplicate the path;
  do not introduce an XBE Boolean. Existing Add Playbook Pack can use the file
  now. Helper text: `Eight replacement calls in MIN I Jokers. Experimental and
  unwitnessed. The read is position/velocity based; a dependable modern read
  needs the later runtime tier. Use the selected defensive test formation.`
- **Gameplay Patches PATCHES / NEEDS_IMAGE:** no runtime patch entry is needed.
  If a pack shortcut is added there, key it `option_playbook` and use:
  `Retail: stock offensive calls. Patch: eight experimental replacement option
  calls, including fixed-defender zone-read and RPO tests. Unwitnessed in play;
  dependable modern reads need the later runtime tier.` Put `option_playbook`
  in `NEEDS_IMAGE` and route it to the same pack list, not to throw tuning.
- **Allowlist:** add exactly `data/playbooks/softdrink_option.2k5book` to
  `packaging/release-allowlist.txt`. The seven changed product modules already
  have entries. Keep those entries; no new dependency is required.
- **Runtime closure:** retain imports of
  `mod_editor.core.nfl2k5_formation_play_writer`,
  `mod_editor.core.nfl2k5_play_codec`, `mod_editor.core.nfl2k5_play_library`,
  `mod_editor.core.nfl2k5_playbook_inspector`, `mod_editor.core.nfl2k5_playbook_pack`,
  `mod_editor.gui.create_play_wizard_qt`, `mod_editor.gui.play_designer_qt`, and
  `mod_editor.gui.playbook_pack_dialog_qt`, plus the existing CLI/archive readers.
  In `packaging/check_2k5_mod_studio_runtime.py`, load the bundled seed and assert
  `schema == OPTION_SCHEMA` (`nfl2k5_playbook_pack/v3`), eight replacements, no new
  formations, and `check_pack(pack).ok`. Offline checks legitimately defer
  retained donor chains until a source book is supplied.
- **Capability registry:** extend `nfl2k5.scripts.director_playbook` in
  `mod_editor/capabilities/registry.v1.json`. List v3 explicit branch flags and
  `nfl2k5_option_intent/v1`, the three experimental presets, native under-center
  I personnel, replacement-only packs, and pinned opponent fixtures. Keep
  classification `offline-writer-proved`, runtime status `not-tested`; add
  `tests/mod_editor/test_nfl2k5_read_option.py`,
  `tests/mod_editor/test_nfl2k5_read_option_qt.py` and
  `ASTRA_READ_OPTION_BUILD_REPORT.md` as evidence. Do not register a runtime
  read, dynamic edge selector, modern mesh policy, or RPO readiness fallback.

**Share and inspection surfaces outside this job's owned GUI files:**

1. `playbook_pack_dialog_qt.py::target_choices` should offer only `pack.book.team`
   for any pack with `p.option_intent`. The core already refuses cross-book and
   changed-source guesses. For multi-pack installation, preflight every target
   before staging, as the defense dialog does. Give the source-mismatch error a
   visible explanation; never discard authored changes to regenerate silently.
2. `playbooks_panel_qt.py::_assignment_selected` should use
   `book.assignment_chain(selected_play.assignments[target_slot])` rather than
   `book.chain(start_index)`. The latter can include orphaned old nodes after
   reauthoring. Add a decoded-details column or tooltip using `node.description`;
   use `node.condition` to expose kind, actor slot, alternate index, selected
   team, argument/source-cache index, human-input enable, terminal and alternate
   flags. Preserve the raw hex columns. These core properties are implemented
   and tested; the Play Designer already displays the decoded descriptions and
   a diamond labelled `Branch` with the selected actor and alternate index.
3. The existing create-only `.2k5mod` loader issue applies unchanged: add
   `and not loaded_creates` and `and not loaded_links` to the empty-project check
   in `project_archive.py::load_project_archive`, as detailed above. Option
   intent and all explicit flag bytes already survive actual saved manifests,
   request parsing, `.2k5book` export/import, and recompilation. The existing
   defense expected-failure test remains the live integration gate.

**Composition ordering:** The seed is bound to the unmodified MIN book. Compile
it before position-pool recoding or any other mutation of that body, and preserve
its I Jokers formation and eight target records in all later passes. Merely
moving it earlier does not resolve overlapping gun replacements. The current
Modern Gun Core replaces MIN I Jokers and leaves fewer than eight independent
compatible calls. The generator correctly refuses that combination. Do not
advertise the two stock MIN seeds as composable. A later integration must reserve
the option formation/targets while resolving gun replacements, then review both
resulting menus. For a changed source or different team, explicitly generate
`option_pack(book, body, team)` against the actual intermediate book and review
its replacements and 4-3 fixture before selecting it. CHI and ARZ have passing
Gun Core -> modern defense -> regenerated option proofs (3462 and 3378 nodes).
Basic/Advanced and unrelated builds must remain unchanged. No cave manifest,
allocator, XBE status, or memory-write/cave-reference test registration applies.


---

# Music tiers 1 and 2 handoff, r61b-music-build, 2026-09-05

This section is additive; retain all earlier handoffs. The implementation is
EXPERIMENTAL / UNWITNESSED. `ASTRA_MUSIC_BUILD_REPORT.md` records the actual
validation and Noah's witness rows. No protected file was edited in this task.

## XBE dispatcher, kwargs and all four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import
`nfl2k5_music_policy as music_policy_patch`. Add these keyword parameters to
`_apply_all`, `write_xbe_copy` and `write_image_copy`, and forward them unchanged
through both writers' `_apply_all` calls; `write_copy` already forwards kwargs:

```python
music_policy: str = "retail",
music_unlock: bool = False,
music_userlist: bool = False,
```

Append this exact entry to `_apply_all`'s `(flag, module, key, label)` tuple:

```python
(music_policy != "retail" or music_unlock or music_userlist,
 music_policy_patch.Selection(music_policy, music_unlock, music_userlist),
 "music_policy_patch", "music policy"),
```

Use `Selection`, not the module's aggregate `status`: an unlocked executable
with retail menus has aggregate status `applied`, but still needs a requested
menu redirect. The adapter reports whether the particular selection is done.
It returns the dispatcher's `changed_byte_count` as well as `changed_bytes`.
The three independent options compose monotonically. Retail/off means keep
source bytes; it does not uninstall policies from an already patched source.
The UserList option requires `music_policy="jukebox_menus"` in a BuildPlan.
All selected and unselected music fields/context pins are checked before any
music mutation. Partly zeroed collection keys and partial UserList words refuse.

Add the following status fields to **all four** dictionaries:
`read_xbe` (payload), `read_image` (payload), `write_xbe_copy` (result), and
`write_image_copy` (after). Bind `music_state` once to `read_any` of the bytes
used by that dictionary, not to the original input when reporting the result:

```python
music_state = music_policy_patch.read_any(payload)  # result / after in writers
# inside each returned dictionary:
"music_policy": music_state.get("music_policy", "foreign"),
"music_unlock": music_state.get("music_unlock", "foreign"),
"music_userlist": music_state.get("music_userlist", "foreign"),
"music_state": music_state["status"],
```

Retain the `music_policy_patch` receipt returned by dispatch. Do not replace
all three independent statuses with the aggregate. The new owner is already
composed into both XBE gate `setUpClass` methods after relocated kickoff, with
all three music options enabled. No runtime state, cave or allocation exists.
The exact edited fields are `0xAC9ECC..0xAC9ED0`, the fourteen four-byte words
at `0xAC9C94 + 0x20*c` (c=0..13), and `0xAC9ED4..0xAC9EE0`, all in `.data`.
Its digest is repinned. Preserve oracle ownership checks; Claude can regenerate
the protected reservation manifest after final integration if the oracle's
source closure changes. No address is claimed as a new allocation here.

## BuildPlan, presets, copy ordering and receipts

In protected `mod_editor/core/mod_build.py` add:

```python
music_policy: str = "retail"  # only retail / jukebox_menus
music_unlock: bool = False
music_userlist: bool = False  # explicitly substitutes the bank for disc/HDD playlists
music_project: str | None = None  # optional authored .2k5music subset
```

All three presets (`softdrink_basic`, `softdrink_advanced`,
`softdrink_experimental`) leave music policy retail, unlock off and UserList
off. None selects a music project or overwrites a chosen library. Preset
application must preserve the active session's personal music replacements;
these are content, not a general gameplay preset. Reject other policy strings,
nonboolean switches, and UserList without jukebox menus. Do not expose
`all_songs`, full-length banks or an all-screen shuffle option.

Extend `wants_xbe_patch()` with the three policy selections only. A music
project/content edit independently counts as a nonempty build request, but
must not falsely require an XBE policy edit. Add availability imports for
`nfl2k5_music_policy`, `nfl2k5_music_catalog`, `nfl2k5_music_build` and
`studio.music_service`. In `inspect()` return the three independent policy
states above for a verified XBE/XISO; content availability requires an image
and seven validated AUSB descriptors. Carry all three kwargs in the existing
selected-key forwarder to `tt.write_copy`. Include `music_state`, the three
states and `music_policy_patch` in the XBE step receipt key list. Preserve the
full music content receipt: hashes, lengths, each twin's spans/decoded hash,
no-layout-change flag and `runtime_witnessed=False`.

`MusicService` writes replacements into the active `StudioSession` via
`replace_audio_batch`. The existing canonical build project consequently
already contains one `ausb_audio` edit for each physical twin. Prefer that
normal build path when combining Music with other session edits; do not apply
a second independent music writer to the same slots. The standalone Music
buttons deliberately build/export the music subset, as their captions say.

For a headless `.2k5music` input, load it into the verified active/staging
session with `MusicService.load_project`, then build the session's canonical
project. Alternatively, snapshot `service.encoded_edits()` and use
`nfl2k5_music_build.build_copy(already_staged_image, next_disposable_copy,
encoded_edits, **policy)` after unrelated edits. This resolves current XDVDFS
extents and retains earlier edits, including changed XBE size. It exclusively
creates a fresh output, closes all source/read/write handles before publication,
checks the complete source hash after copying, and removes the private stage
on cancellation/failure. Never rebuild from pristine source over staged edits.
The enclosing build owns final publication; do not expose its temporary target.

Format 2 is implemented with explicit `byte_runs`, type 0, version 1, minimum
reader 2. Export via `nfl2k5_music_build.export_patch` using the same staged
base and completed music copy, or `service.export_patch` for a music-only
patch. Payload runs are complete authored encoded slots, divided only at pack
seams, plus generated policy fields/digest when selected. They never coalesce
untouched music/neighboring archive bytes. The recipe operation is
`{"op":"music_fixed_slots","schema_version":1,...}` and carries every
stream receipt. Export verifies the whole result against declared operations;
a result with undeclared roster/texture changes is refused. In a combined
format-2 export, compose those other authored operations explicitly in order.
No operation ID is reserved by this tier. A future free-length implementation
needs a semantic bank rebuild operation; do not reuse this fixed-span recipe
for shifted archives. Generic format-2 apply keeps its existing exact-run and
partition checks, with ready/applied/mismatch and transactional copy behavior.

## Studio registration, session lifecycle and project formats

In protected `mod_editor/gui/studio_qt.py` import
`mod_editor.gui.music_panel_qt.MusicPanel` and
`mod_editor.studio.music_service.MusicService`. Mount `MusicPanel` as **Music**
in the Audio tabs, next to the existing Audio panel and Sounds panel. The
current inherited Audio panel title is `Music & Sounds` and Sounds is
`Replace a Sound`; rename the old broad browser to **Audio Cues** if desired
to remove duplicate naming. Do not move another panel's state into Music.

Create `MusicService(facade._session, lock=facade._lock)` only after the shared
session has its `Nfl2k5AudioService` attached and source-origin inventories
prepared. Pass it to `panel.set_service(service)`. Do not create a second
StudioSession. No developer retail path, cache inventory or FFmpeg binary is
needed merely to import/mount the empty panel.

Connect `changed` to the normal modified/Undo/build refresh, `policy_changed`
to BuildPlan's three fields, `receipt_ready` to receipt presentation, and
`operation_state_changed(bool)` to the shell's cross-workspace busy barrier.
`operation_in_progress` is public. Serialize source changes/builds/shared
Undo/project opens against a running import or export. Before any source or
session replacement call `set_service(None)`; it stops playback, cancels work,
invalidates the old service, and rejects late delivery. On a successful source
open mount a new service. On failure, recreate a service for the retained
session rather than reusing an invalidated adapter. `invalidate_audio_content()`
stops preview/cancels stale jobs and refreshes after external Audio Cues edits,
shared Undo or project reopening. Stop previews on tab/window/source changes;
`closeEvent` cancels a worker and defers closing until it has returned. The
process is owned by QProcess, including termination/kill and wait before output
publication. QtMultimedia is not a dependency. FFplay works when installed;
Linux can also use the existing paplay/aplay fallback. No auto-play occurs.

The panel defaults to 66 rows; Show presentation music reveals 20 more. Drops
freeze visible order and incoming URL order, allow reordering in review,
prepare/authorize the whole batch in a worker, then show fit/trim/volume/twins
before Apply. Overflow does not wrap or partially apply. Original means the
selected source baseline, including a deliberately modified source. Restore
removes both edits together; one Undo restores them. A single twin changed
through Audio Cues displays Needs attention until Replace/Restore repairs it.

The ordinary `.2k5mod` project and canonical build project already transport
both conformed authored WAVs through the existing audio route. The dedicated
**Save/Open Music project** `.2k5music` format additionally retains input name
and duration, fit/gain results, original/encoded hashes, encoder version and
all three policy selections. It stores only authored WAVs plus JSON, checks
the selected source SHA-256, re-encodes and verifies the exact encoded result
before one shared-session commit. Originals are reconstructed from that
source. Reopening a music project replaces the music subset and preserves
other domains. Ordinary `.2k5mod` does not carry Music-specific fit/policy
metadata; use `.2k5music` to retain that information. This is an explicit
format choice, not an implicit extension to the shared project schema.

Local Export current set uses `audio_bundle` for current encoded-preview WAVs,
manifest and M3U (one canonical row per song). It can include source originals
and is a local listening export, separate from authored project/patch transport.
The 86-row export fits its existing 256-row / 2 GiB limits. All output actions
exclusively create new files; choose a new name instead of overwriting a source.

## Gameplay Patches text, NEEDS_IMAGE and Build captions

Add these `(key, title, explanation)` entries to the protected Gameplay
Patches `PATCHES` model, preserving the enum adapter for `music_policy`:

- `music_policy`: **Use jukebox songs in menus (experimental)**.
  **Retail: menus use the menu bank. Patch: menus use the 59 jukebox recordings
  in the game's random order. The 7 menu tracks are not included yet. Twelve
  jukebox tracks are spoken outtakes.**
- `music_unlock`: **Make every music collection available (experimental)**.
  **Retail: collections need Crib purchases. Patch: every collection is
  available without spending credits or setting purchase bits.**
- `music_userlist`: **Use jukebox songs instead of user playlists (experimental)**.
  **Retail: UserList follows the user's disc or HDD playlist. Patch: UserList
  uses the 59-song jukebox bank instead. Requires jukebox menus.**

These data-only policies work on verified XBE inputs; keep all three out of
`NEEDS_IMAGE`. Any `music_project`/content toggle **belongs in NEEDS_IMAGE**.
The current checkbox-oriented patch panel must map its menu toggle to
`"jukebox_menus"`/`"retail"`, never boolean True/False. Loading/show rules,
initial fixed index and all-screen behavior have not been promoted.

Protected Build tab `_option` captions (all <=60 characters):

```text
Use jukebox songs in menus
Make every music collection available
Use jukebox songs instead of user playlists
Include Music tab replacements
```

Show **Experimental, not yet tested in game**. Gate UserList on jukebox menus.
Keep bank/twin offsets and source authorization details out of the main flow.
The exact required scope text is exported as `nfl2k5_music_policy.MENU_TEXT`.

## Allowlist, runtime closure and capability records

Add these exact lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_music_policy.py
mod_editor/core/nfl2k5_music_catalog.py
mod_editor/core/nfl2k5_music_build.py
mod_editor/studio/music_service.py
mod_editor/gui/music_panel_qt.py
```

Already allowlisted dependencies modified here: `audio_conform.py`,
`nfl2k5_ausb_fixed_slots.py`, `tools/game_audio_convert.py`,
`tools/nfl2k5_commentary_swap.py`, and `modpack.py` (plain-language Music recipe
description). Existing closure also includes
`nfl2k5_audio_catalog`, `nfl2k5_bump_strength`, `nfl2k5_cave_oracle`,
`platform_compat`, `json_stream`, `modpack`, `modpack_ops`, the Studio session,
project archive, audio-origin modules, `audio_bundle`, `gui.audio_panel_qt`,
`tools/nfl_outer.py`, `tools/nfl_uniform_color_xiso_direct_patch.py` and
`tools/xbox_ima_encoder.py`. Do not add originals, caches, .scratch or the brief.

In protected `packaging/check_2k5_mod_studio_runtime.py`, add the five new
module paths to required source files and import these module names in the
runtime closure smoke check:

```text
mod_editor.core.nfl2k5_music_policy
mod_editor.core.nfl2k5_music_catalog
mod_editor.core.nfl2k5_music_build
mod_editor.studio.music_service
mod_editor.gui.music_panel_qt
```

Also exercise `nfl2k5_music_build._banks_module()` so its lazy commentary/outer
closure is actually imported. Test empty `MusicPanel()` with offscreen Qt.
Optional NumPy and FFmpeg must remain optional: native 22050 Hz PCM16 WAV fit,
fixed-slot encoding and preview decode work without them. Other rates/formats
explain that FFmpeg and FFprobe are required; converter processes are cancellable
and reaped before temporary directories are removed. No emulator/audio/display
launch belongs in the packaging test.

Add capability entries for **nfl2k5.music.policy** and
**nfl2k5.music.fixed_slot** to `mod_editor/capabilities/registry.v1.json` using
its current canonical schema. Concrete field values for both:

| Field | Policy | Fixed slot |
| --- | --- | --- |
| game / surface | nfl2k5_xbox / audio | nfl2k5_xbox / audio |
| title | Music policies (experimental) | Music fixed slots (experimental) |
| classification | offline-writer-proved | offline-writer-proved |
| backend.module | mod_editor/core/nfl2k5_music_policy.py | mod_editor/studio/music_service.py |
| backend.command | Python API: Selection(...).apply(payload) | Python API: MusicService.replace_batch / build_copy |
| backend.operation | write | write |
| gui | expose true, mode edit, default_enabled false | expose true, mode edit, default_enabled false |
| runtime | status not-tested, evidence [], scope EXPERIMENTAL / UNWITNESSED | status not-tested, evidence [], scope EXPERIMENTAL / UNWITNESSED |
| validation_command | python3 tests/mod_editor/test_nfl2k5_music_policy.py | python3 tests/mod_editor/test_music_service.py |
| evidence | ASTRA_MUSIC_BUILD_REPORT.md, tests/mod_editor/test_nfl2k5_music_policy.py | ASTRA_MUSIC_BUILD_REPORT.md, tests/mod_editor/test_nfl2k5_music_build.py, tests/mod_editor/test_music_panel_qt.py |

`summary`/`gui.reason`: use the scope text above for policy; for fixed slots,
"86 logical music slots; 59 jukebox entries update stereo and mono together.
Exact-length fit, restore, Undo, authored projects and copy builds. In-game
playback has not been witnessed." `source_container`: XBE or XISO default.xbe
for policy; XISO vc_53450030 AUSB descriptors and indexed external ranges for
fixed slots. `selectors.fields`: the three policy options with their exact
allowed values; for fixed slots logical `bank:index`, only the seven scoped
banks, with crib22 selected through its linked cribmusic row. `input_constraints`
must include verified pins/source, complete twin transactions, fixed 22050 Hz
whole-block lengths, and all named format/source-origin checks. `portme` must
name Noah's matrix and explicitly defer free-length and all-screen shuffle.
`public_distribution`: tooling source-and-schemas-only; game_data
never-bundle-retail-data; mod_payload user-authored-inputs-and-recipes; rule
"Only authored WAVs, encoded replacements and metadata are portable. Private
source originals and local listening exports are not authored mod projects."

Do not register bank-rebuild or allocator-playlist capabilities as implemented.
After protected integration, rerun both composed XBE gates, the six new Music
test files, normal build/project tests, capability validation and the packaged
runtime closure. No release-tag, update-check or CI workflow edit is required
by this feature itself.

---

# Runtime scorebug integration handoff, r61b

**EXPERIMENTAL / UNWITNESSED.** This section extends the v7 scorebug and extra
space handoffs above. It supersedes the kickoff-only allocation adapter when
runtime scorebug is selected. The allocator API and protected product files
were not changed. The brief's task 4 and explicit protected-file handoff rules
require this additive WIRING entry despite its earlier parenthetical ambiguity.

## Build plan, presets and ordering

Add `scorebug_runtime: bool = False` to `BuildPlan`, serialization, availability,
source inspection and preset reset. Set it false in Basic and Advanced and true
in `softdrink_experimental`. Selecting it implies `scorebug=True` and
`xbe_space=True`; it does not imply relocated kickoff. Preserve the separate
kickoff flag's existing alignment and kick-rules prerequisites.

Runtime installation requires a disc. When selected, skip the earlier
`if plan.scorebug:` neutral resource pass by changing its predicate to
`plan.scorebug and not plan.scorebug_runtime`. The runtime compiler supplies the
matching v7 atlas and binding scene itself. An already-installed neutral v7 HUD
is deliberately refused; rebuild from the supported base. Any other writer
that changes this pinned HUD collection or its index must be reconciled before
enabling both options. Do not weaken the resource fingerprints.

Run every ordinary XBE and resource pass first. For a runtime disc build, leave
`xbe_space`, `kickoff_relocated` and `scorebug_runtime` false in earlier shared
dispatcher calls. Replace the final bare allocator/relocation pass with:

```python
from . import nfl2k5_scorebug_ingame as runtime_resources
sub_receipt = runtime_resources.runtime_apply_in_place(
    target, with_kickoff=plan.kickoff_relocated)
receipt["steps"].append({"step": "scorebug_runtime", **sub_receipt})
```

Use the build's actual disposable output path for `target`. This preflights
resources and XBE together, reserves the union once, installs both selected
owners, then transports the pack and XBE transactionally. Do not pre-apply the
runtime XBE hook before this call: it refuses mismatched resource/XBE states.
For non-runtime builds retain the earlier final allocator handoff. A pre-grown
input is accepted only if it already reserved every selected owner at the exact
stable addresses. Rebuild from base to change the owner set.

The final resource pass moves later pack-0 assets and adjusts all later virtual
archive offsets. Any later resource inspection must re-read the archive index
and XDVDFS nodes. Hard-coded retail pack offsets are no longer valid. No PLAY or
ROST records are edited; their containing assets are retained byte for byte.

## Dispatcher tuple, keyword and four status dictionaries

Import `nfl2k5_scorebug_runtime as scorebug_runtime_patch`. Add keyword-only
`scorebug_runtime: bool = False` to `_apply_all`, `write_xbe_copy` and
`write_image_copy`, forwarding it through the existing wrapper/keyword route.
For direct XBE output, replace the earlier final allocator adapter with one
whose requests are the union of selected owners:

```python
class _xbe_space_adapter:
    def __init__(self, relocated, runtime):
        self.requests = ((kickoff_relocated_patch.REQUESTS if relocated else ())
                         + (scorebug_runtime_patch.REQUESTS if runtime else ()))

    def status(self, payload):
        state = xbe_space_patch.status(payload)
        if state == "applied":
            xbe_space_patch.apply(payload, self.requests)
        return state

    def apply(self, payload):
        return xbe_space_patch.apply(payload, self.requests)

for flag, module, key, label in (
    (xbe_space or kickoff_relocated or scorebug_runtime,
     _xbe_space_adapter(kickoff_relocated, scorebug_runtime),
     "xbe_space_patch", "experimental executable space"),
    (kickoff_relocated, kickoff_relocated_patch,
     "kickoff_relocated_patch", "experimental relocated kickoff"),
    (scorebug_runtime, scorebug_runtime_patch,
     "scorebug_runtime_patch", "experimental scorebug effects"),
):
    if not flag:
        continue
    state = module.status(patched)
    _require(state in ("retail", "applied"), f"{label} is {state}; refusing")
    patched, sub_receipt = module.apply(patched)
    receipt[key] = sub_receipt
    receipt["changed_byte_count"] = int(receipt.get("changed_byte_count", 0)) + int(sub_receipt["changed_bytes"])
```

This remains the separate last tuple after uniform choice, boot-logo repair and
all ordinary owners. Direct XBE output contains hooks only. Its receipt must
retain `requires_resources`; it must not claim installed team logos.

For direct `write_image_copy`, call `_apply_all` with all three final flags false
when `scorebug_runtime` is true, finish its ordinary XBE write, then call
`runtime_apply_in_place` on the closed temporary output before publication,
passing the selected kickoff flag. Refresh `after` from the actual grown XBE
before reporting statuses. This gives the disc entry point the same paired
preflight/transport as Build, rather than creating an incomplete resource pair.

Add `"scorebug_runtime": scorebug_runtime_patch.status(...)` to all four XBE
status dictionaries, using the local bytes shown here:

| Dictionary | Byte argument |
| --- | --- |
| `read_xbe` | `payload` |
| `read_image` | `payload` |
| `write_xbe_copy` | `result` |
| `write_image_copy` | `after` |

Retain the prior `xbe_space`, `kickoff_relocated` and settings keys. Report disc
readiness separately with `runtime_resources.runtime_image_status(path)`;
XBE-only recognition cannot verify the resource collection. Apply the earlier
`image_xbe_extent` and generalized `write_image_xbe` handoff so protected readers
accept the recognized grown size and all handles close before `os.replace`.

## Product text and packaging

Add this exact `gameplay_patches_panel_qt.PATCHES` entry and add
`scorebug_runtime` to `NEEDS_IMAGE`:

```python
("scorebug_runtime", "Team logos and scorebug effects (experimental, unwitnessed)",
 "Retail: team panels and timeout marks use the stock display. Patch: adds "
 "team logos, remaining timeout marks, a score flash, down refresh and a red "
 "play clock below five seconds. Unwitnessed in game; use a separate disc copy."),
```

Build tab `_option` caption (46 characters):

```python
self._option(layout, "scorebug_runtime", "Team logos and scorebug effects (experimental)", helper, badge="EXPERIMENTAL")
```

Use the same helper text and keep the unwitnessed notice visible. Basic and
Advanced reset this flag. Keep allocation, addresses and archive details in
receipts, outside the ordinary product flow.

Add these allowlist lines if absent (some belong to the prerequisite v7 handoff):

```text
mod_editor/core/nfl2k5_scorebug_ingame.py
mod_editor/core/nfl2k5_scorebug_resources.py
mod_editor/core/nfl2k5_scorebug_runtime.py
tools/nfl2k5_scorebug_reference.py
```

Retain the existing lines for `nfl2k5_scorebug_source_art.py`, scorebug layout,
position, texture/outer codecs, palette importer, draft assembler and generalized
storage. Retain the allocator/relocation additions above. Do not package generated
game resources, executables, the witness disc or `.scratch`.

In `packaging/check_2k5_mod_studio_runtime.py`, add dotted imports for
`mod_editor.core.nfl2k5_scorebug_ingame`,
`mod_editor.core.nfl2k5_scorebug_resources`,
`mod_editor.core.nfl2k5_scorebug_runtime`, and tools
`nfl2k5_scorebug_reference` / `nfl2k5_scorebug_layout`. Exercise `REQUESTS`,
`status(b"bad") == "foreign"`, panel-name validation and the new CLI parser.
Retain Pillow and existing codec dependencies. Unicorn and Capstone are offline
proof dependencies, not runtime application imports.

Copy the complete, schema-validated object from
`docs/mod_editor/nfl2k5_scorebug_runtime_capability.json` into
`mod_editor/capabilities/registry.v1.json` and update closure counts. Its ID is
`nfl2k5.scorebug_presentation.runtime`, classification `offline-writer-proved`,
runtime status `not-tested`, GUI default false. Existing scorebug metadata must
distinguish neutral v7 installation from the new paired runtime installation.

## Ownership regeneration and acceptance

The manifest builder now records the runtime hook spans plus its entire named
code/data allocation, including untouched zero data. It uses the real v7 atlas
writer and the final union with kickoff. Its temporary ownership disc does not
install the runtime panel collection and is not a gameplay image. Resource
installation is separately proved by the new resource suite and private disc.

Regenerate the protected manifest with the command in the allocator handoff
after all integration changes. Do not copy the private manifest over it before
integrating; source fingerprint checks remain enforced. To inspect this owner
union, use the actual composed XBE with the CLI's new forwarding option:

```sh
python3 tools/nfl2k5_cave_oracle.py space-proof '<retail.xbe>' \
  --manifest '<fresh-manifest.json>' --allocated '<composed.xbe>' \
  --json '<space-proof.json>'
NFL2K5_CAVE_MANIFEST='<fresh-manifest.json>' python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py
python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py
```

The optional `--allocated` merely exposes the allocator's existing evidence API;
the allocator itself is unchanged. See `ASTRA_SCOREBUG_RUNTIME_REPORT.md` for
the complete proof boundaries, static previews and Noah's required witness list.

---

# r61b music banks: protected integration hand-off

Status: **EXPERIMENTAL / UNWITNESSED**. The callable writer and CLI are complete;
the protected GUI/build integration below belongs to Claude. This job does not
create or modify the parallel session's `nfl2k5_music_policy.py`,
`nfl2k5_music_catalog.py`, or `music_panel_qt.py`. Presets **basic, advanced and
experimental never enable a music library**. A chosen personal recipe enables it.

## Service and source contract

Import `mod_editor.core.nfl2k5_music_banks` as `music_banks`. Public calls:

```python
preview = music_banks.plan(source_image, recipe_path)
receipt = music_banks.rebuild(source_image, distinct_output, recipe_path,
                             expected_plan=preview, overwrite=False,
                             progress=progress_callback)
music_banks.verify(source_image, distinct_output, receipt)
music_banks.estimate(source_image, count=200, seconds=180, twins=True)
```

Plans/receipts are JSON-serializable. Progress is `(stage, done, total)`; raising
from it cancels and discards private output. Source and destination handles close
before publication. `plan` only reads. Limits, every moved outer, 16 pack deltas,
physical ISO size, scratch budget and descriptor/XBE edits are reviewable before
building. `expected_plan` refuses stale sources, input WAVs and different recipes.

Recipe shape, stored as a project asset with paths relative to its JSON file:

```json
{
  "schema": "nfl2k5_music_library/v1",
  "bank": "femusic",
  "tracks": [
    {"wav": "audio/first.wav", "title": "First song", "artist": "My artist"},
    {"source_index": 1},
    {"source_index": 2}
  ]
}
```

The list is the entire selected bank. `femusic` needs no twin or XBE metadata.
`cribmusic` automatically rebuilds `crib22` and all 18 collection record arrays.
Conform WAV/MP3/FLAC/OGG upstream to 22,050 Hz, PCM16 WAV, one or two channels;
the service encodes in bounded chunks, repeats at most 63 final PCM frames, and
concatenates whole IMA blocks without inter-song sector padding. Mono is the
floor-rounded stereo average on the same canonical timeline. Existing unchanged
tracks use `source_index` and retain their exact encoded bytes and titles.

The full-library service currently accepts 1..400 tracks (two-track `femusic`
refuses because retail random selection divides by N-2), <=10 minutes per input,
<=512 MiB per source WAV, <=2 GiB minus one encoded byte including twins, and
positive pack F below 2 GiB. Read-only metadata has its own 65,408-byte content
budget. Presentation banks remain with the fixed-slot service: their cue/index
scheduling has separate ownership. No all-screen shuffle policy is implied.

After rebuilding, reopen the image and invalidate catalog/physical-range caches.
The fixed-slot reader's pinned offsets deliberately refuse a resized descriptor;
the Music tab must use `music_archive.Disc` for grown-library inspection. Do not
relax the unrelated fixed-slot validators. A renamed/title-changed recipe cannot
silently replace an existing differently sealed metadata allocation: rebuild from
the original selected source. Same-recipe rebuilds are byte-idempotent, without
another append.

## BuildPlan and ordering

In protected `mod_build.py`, add `music_library: str | None = None`, a recipe
reference rather than a Boolean or serialized physical offsets. Add it to project
round-trip, selected-key validation, availability/inspect, Build receipt and the
image-required input checks. `wants_xbe_patch` must account for jukebox metadata
when the selected bank is `cribmusic`; a menu-only library remains a content build
even when all XBE policies are retail. Reject missing recipe/WAV assets before
starting the ordinary build. Never enable or replace the recipe via any preset.

Run the final `music_banks.rebuild` **after** all existing archive, roster,
playbook, texture, SPECIAL and other XBE passes. Its source is the disposable
working image including those changes; its destination is a distinct private
sibling. Re-plan against that source and pass that exact plan. Promote the
verified music result through the builder's final transaction. Do not use an
earlier retail physical-range plan on a modified intermediate image, and do not
write metadata first into an otherwise unchanged bank: mixed bank/metadata counts
refuse. The service owns the metadata/archive transaction together. The builder
must retain its original source identity and add the service's immediate source
identity and receipt, so earlier changes remain attributable.

## Dispatcher tuple, keyword and four status dictionaries

Archive writes do not belong in `_apply_all`. For the executable metadata helper
surface, add a prepared-record keyword `music_metadata=None` to `_apply_all`,
`write_xbe_copy`, `write_image_copy`, and `write_copy`. Its adapter binds validated
`[{title, artist, frames}, ...]` and exposes `status(payload)` / `apply(payload)`.
Use this exact tuple shape in the existing four-field dispatcher:

```python
(music_metadata is not None, _music_metadata_adapter(music_metadata),
 "music_metadata_patch", "music library titles")
```

The adapter delegates to `nfl2k5_music_metadata`. When status is already applied,
it must still call the pure `apply(payload, prepared_records)` validator to refuse
a differently configured library; the general dispatcher normally skips applied
patches. The new receipt includes `changed_bytes`. Reserve any other requested
allocator owners before applying metadata. Do not dispatch metadata during the
ordinary content-build prepass: leave this keyword `None` there and let the final
bank rebuild apply it transactionally. Standalone XBE output is an offline metadata
artifact, not a usable music library by itself.

Import `nfl2k5_music_metadata as music_metadata_patch`. Add
`"music_metadata_patch": music_metadata_patch.status(payload)` to all four status
dictionaries: `read_xbe`, `read_image`, `write_xbe_copy` result and
`write_image_copy` result, using their local XBE byte variable. The Build receipt
separately records `music_library` from the service, because a `femusic` library
correctly leaves executable metadata status retail. Do not conflate these states.

Protected grown-XBE readers must accept the additional exact
`nfl2k5_music_storage.FILE_SIZE` (12,095,488) and validate it with
`nfl2k5_depth_chart_storage.recognized_grown_xbe`. The existing generalized helper
now recognizes it and writes/replays it safely. No arbitrary length/count bypass.
The common section/digest reader, allocator and ownership recorder were extended
additively for this third read-only section; existing two-page allocations retain
their addresses and file size.

## UI text and lifecycle

Build tab `_option` caption: **"Include my music library (experimental)"** (39
characters). Selecting it enables the chosen `music_library` recipe; an absent
recipe is an actionable validation error. Show **"Experimental, not yet tested
in game"**, the projected output/scratch sizes, and a cancel action. Do not show
addresses, codec geometry, or allocator names in the user flow.

If exposing a Gameplay Patches card, its `PATCHES` helper must be:
**"Retail: menus and the jukebox use the original songs. Patch: builds your chosen
music library. Experimental, not yet tested in game."** Add `music_library` to
`NEEDS_IMAGE`. Keep this a recipe chooser, not another automatically enabled
music-policy checkbox. Reuse the parallel Music panel for authoring, undo/redo,
conform and project asset lifecycle. Its fixed-length mode can remain independent.

Jukebox songs beyond retail go into the four free collections, starting at the
last. The first 59 collection/song identities stay stable. Never describe all 18
collections as unlocked: purchase-key changes belong to the parallel policy
owner. Clearly request a fresh/rebuilt playlist after replacing a library;
title checksums, saved cursor and old stadium trim points can be stale.

## Packaging, transport and closure

Add these allowlist lines:

```text
mod_editor/core/nfl2k5_music_banks.py
mod_editor/core/nfl2k5_music_archive.py
mod_editor/core/nfl2k5_music_metadata.py
mod_editor/core/nfl2k5_music_storage.py
tools/nfl2k5_music_banks.py
```

Retain/add the transitive lines `tools/nfl2k5_commentary_swap.py`,
`tools/nfl_outer.py`, `tools/nfl_uniform_color_xiso_direct_patch.py`,
`tools/xbox_ima_encoder.py`, `mod_editor/core/platform_compat.py`,
`mod_editor/core/nfl2k5_ausb_fixed_slots.py`, `nfl2k5_bump_strength.py`,
`nfl2k5_depth_chart_storage.py`, `nfl2k5_xbe_space.py`, `nfl2k5_boot_logo.py`,
`nfl2k5_cave_oracle.py`, `modpack.py` and `modpack_ops.py` under their existing
`mod_editor/core/` paths. Check the commentary/XISO reader's existing tools closure.
Do not package scratch images, research files, retail metadata blobs or tones.

In the protected runtime closure checker import all four new core modules,
`tools.nfl2k5_music_banks`, `mod_editor.core.modpack_ops`, and the dependencies
above. Exercise imports with NumPy/FFmpeg/Capstone/Unicorn absent; NumPy is an
optional encoder speed-up, and canonical WAV/scalar encoding remains available.
No retail path or Ghidra corpus is required at import time.

Format 2 adds **ID 5, `file_shrink`, version 1**. ID 4 remains reserved for
`file_add`. Registry/reader versions remain 1/2; older readers reject unknown
handler 5 before writing. Export complete builds through the existing
`modpack.export(..., file_operations=["vc_53450030/0", ..., "vc_53450030/F",
"default.xbe"])`, naming `default.xbe` only when it changes. Same-sized packs use
`file_replace`; larger F/XBE use `file_grow`; shorter F uses `file_shrink` and
retains unused physical bytes. No new executable modpack operation is necessary.
For portable personal project sharing, embed only authored WAVs and the recipe,
rewrite references relative to the recipe, and retain the selected source hash.
Do not bundle rebuilt pack files/retail audio into distributed presets.

## Capability registry and reservations

Add `nfl2k5.music.bank_rebuild` to the protected integration's capability registry
review: game `nfl2k5_xbox`, surface `audio`, title "Music library (experimental)",
classification `offline-writer-proved`, backend module
`mod_editor/core/nfl2k5_music_banks.py`, operation `write`, GUI default disabled,
runtime status `not-tested`. Selectors: `music_library` recipe, `bank`, ordered
`tracks`. Source container: XDVDFS `vc_53450030/0..F`, all 17 descriptor owners,
and pinned USA XBE geometry for jukebox metadata. Inputs/constraints are the
service limits above. Transport: authored WAVs + schema v1 recipe; receipts bind
actual source and output SHA-256. Evidence: `ASTRA_MUSIC_BANKS_REPORT.md` and the
three new standalone music test files. Validation command:
`python3 tests/mod_editor/test_nfl2k5_music_banks.py`. Never register a true-shuffle
or all-screen playback capability for this writer.

Both XBE gate compositions now include the actual 200-song metadata owner.
The oracle generator also observes this default-off owner on its disposable
ownership probe (no game playback), including the entire 64 KiB RO allocation.
Regenerate `data/nfl2k5_cave_reservations.json` with the existing oracle command
after integration. This job generated and tested `.scratch/music-cave-manifest.json`
without modifying that protected release manifest. Keep source-drift rejection
enabled. The RO proof is a new loader allocation outside retail mappings, not
a free-cave claim; the audit retains all 469 raw reference-encoding candidates.
