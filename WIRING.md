# r62 widescreen polish v3 handoff, 2026-09-06

**EXPERIMENTAL / UNWITNESSED.** Backend and tests are complete in
`mod_editor/core/nfl2k5_widescreen.py`. See
[ASTRA_WIDESCREEN_POLISH_REPORT.md](ASTRA_WIDESCREEN_POLISH_REPORT.md) and
[exact receipts](docs/mod_editor/widescreen_polish_receipts.json). This section
supersedes older widescreen assumptions only; unrelated handoffs below remain.
Protected files were not edited. The existing `widescreen` flag already
installs all v3 fixes, and its BuildPlan path has passed a real-XBE test.

## Dispatcher, existing flag and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, retain the import:

```python
from . import nfl2k5_widescreen as widescreen_patch
```

Retain `widescreen: bool = False` in `_apply_all`, `write_xbe_copy` and
`write_image_copy`, every forwarding call, and the nonempty-selection checks.
The existing owners tuple row remains:

```python
(widescreen, widescreen_patch, "widescreen_patch", "widescreen"),
```

Add `"widescreen_patch"` to the existing apply-on-applied key tuple beside
`"chop_block_toggle_patch"` and `"flatter_deep_ball_patch"`. V3's exact replay
returns zero edits and explicit experimental/version metadata. This retains
that metadata on a replay receipt; the existing status guard already refuses
mixed/foreign/old-v2 bytes. Do not add an old-version migration exception.

All four dictionaries already contain the correct status reader. Keep these
exact entries in `read_xbe`, `read_image`, `write_xbe_copy` and `write_image_copy`:

```python
# read_xbe and read_image
"widescreen": widescreen_patch.status(payload),
# write_xbe_copy
"widescreen": widescreen_patch.status(result),
# write_image_copy
"widescreen": widescreen_patch.status(after),
```

`status` now validates eleven sites and 23 context pins. A formerly applied
v2 image reads foreign and must be rebuilt from a clean source. Retain that
failure rather than showing it as an applied v3 repair.

## BuildPlan, presets, receipt and allocation

In protected `mod_editor/core/mod_build.py`, retain the existing
`BuildPlan.widescreen: bool = False`, `wants_xbe_patch`, availability,
inspection and early XBE-pass forwarding. Replace the stale comment saying
it is absent from all presets: Basic false, Advanced false, Experimental
true, as the code already specifies. Keep `widescreen=True` as the single
selection for the v3 family. There is no `widescreen_hud` field, separate
fix switch or new aspect selector in this task.

Add `"widescreen_patch"` beside `"widescreen"` in the XBE step's receipt-key
projection near the existing `receipt["steps"].append` at line 959. Preserve
the backend dictionary intact, including `version: 3`, `experimental: true`,
`runtime_witnessed: false`, full `edits`, hashes and section IDs. The Build
summary currently keeps only the status and drops that dictionary.

Allocation is unchanged: 831 bytes of code in the existing 832-byte
`46EE0..47220` reservation and 36 immutable bytes at `10254..10278`.
There is no `REQUESTS` tuple, grown owner, new budget row, adapter,
`_selected_space_requests` flag, `_xbe_space_adapter` argument,
`_grown_status_fields` field, deferral or final allocator-pass addition.
The complete existing owner union composes with this family in both orders.
Do not reserve another owner's space for it.

## Gameplay Patches and Build text

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, expose the existing
flag with the same tuple shape as other entries:

```python
("widescreen", "Widescreen 16:9 (experimental)", tt.widescreen_patch.HELP_TEXT),
```

`HELP_TEXT` contains both **Retail** and **Patch**, describes field width,
marker/shadow/sky/interlace fixes in plain words, states EXPERIMENTAL /
UNWITNESSED and requests a clean-base rebuild. `NEEDS_IMAGE` membership is
**false**: this is a fixed-length executable patch and the tested standalone
XBE path is valid. Standard checkbox forwarding via `BuildPlan` applies;
preserve explicit `widescreen` forwarding wherever this panel maintains a
manual field list. Refresh Studio's existing shared Build state in the same
way if its integration adds a manual copy; no new GUI panel is needed.

In protected `mod_editor/gui/build_panel_qt.py`, update the existing `_option`:

```python
self.widescreen_check = self._option(
    pl, "widescreen", "Widescreen 16:9 (experimental)",
    "Shows more of the field; keeps the HUD at its existing size.",
    badge=NOT_TESTED, details=tt.widescreen_patch.HELP_TEXT,
)
```

The caption is 30 characters, below 60. If the panel does not already expose
`tt`, import the backend module directly and use its `HELP_TEXT`; no new
runtime dependency is required. Retain the existing flag gates, plan
construction and preset loading. Widening the regular HUD is not a new
option here. For the exact clean-base Build recipe and scene criteria, use
the report. The core tests did not launch Qt or xemu.

## Allowlist, runtime closure, capability and manifest

Protected `packaging/release-allowlist.txt` already has the backend at line
302. Retain it and include the review/witness documentation with these exact
lines if packaging this handoff:

```text
mod_editor/core/nfl2k5_widescreen.py
ASTRA_WIDESCREEN_POLISH_REPORT.md
docs/mod_editor/widescreen_polish_receipts.json
```

In protected `packaging/check_2k5_mod_studio_runtime.py`, include
`"mod_editor.core.nfl2k5_widescreen"` explicitly in `product_modules` and
verify `POLISH_VERSION == 3`, `EXPERIMENTAL is True`,
`RUNTIME_WITNESSED is False`, and the public help text is present. Its only
new import is standard-library `hashlib`; the existing section/digest helpers
remain in `nfl2k5_bump_strength`. Unicorn and Capstone are test tools only.
There is no new backend command, resource format or capability surface, so
no new registry ID/schema entry is needed for this existing Build flag.

Claude alone regenerates protected `data/nfl2k5_cave_reservations.json` after
integration. The builder already discovers this module through the existing
`tt` import and Experimental preset. Its allocator `all_requests` and three
grown-owner lists need no new row. The backend receipt's added `file_offset`
lets `Recorder.observe` reserve complete sites, including unchanged bytes.
Verify the manifest owns all eleven spans in the report under
`nfl2k5_widescreen`, retains the whole 832-byte cave, has fresh source
fingerprints and has no overlaps. The local manifest unit test passed.

Use the existing generator only when a disposable full disc and its workspace
will leave **more than 100 GB free**; it internally uses a TemporaryDirectory:

```text
python3 tools/nfl2k5_cave_oracle.py manifest RETAIL_DEFAULT_XBE --xiso RETAIL_XISO --work-dir DISPOSABLE_WORK_DIR --json data/nfl2k5_cave_reservations.json
```

After wiring, rerun the new standalone suite, both XBE gates, protected
Build/GUI checks and runtime closure. No runtime witness or release-status
upgrade is implied by these CPU tests. This session did not build a full
disc or regenerate the protected manifest.
# r62 defensive try box score handoff, 2026-09-06

This supersedes the defensive-try missing-stat handoff below. The existing
`defensive_try` flag now installs the rules and native stat extension together.
**EXPERIMENTAL / UNWITNESSED.** See `ASTRA_DEFENSIVE_TRY_BOXSCORE_REPORT.md`.
No protected file was edited. The box row, player-card callbacks, season
writer/readers and roster relocation have bounded native proofs; console
rendering and played franchise saves remain Noah witnesses.

## Dispatcher, complete union and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, retain the existing
`from . import nfl2k5_defensive_try as defensive_try_patch` and exact-bool
`defensive_try: bool = False` keyword in `_apply_all`, `write_xbe_copy`,
`write_image_copy`, their forwarding and selection guards. No new flag or
separate stat adapter is needed. `_selected_space_requests` already appends
`defensive_try_patch.REQUESTS` when selected; that now means **all four** rows.
Both `_xbe_space_adapter` and `_defensive_try_adapter` must use that union.
Retain the existing final tuple, with its complete companion argument list:

```python
(defensive_try,
 _defensive_try_adapter(kickoff_relocated, scorebug_runtime, momentum,
                       defensive_try, zone_drop_cap, all_stadiums,
                       coverage_slider, scramble_tuning, music_shuffle,
                       practice_squad_screen, abilities, qb_spy,
                       calendar_engine),
 "defensive_try_patch", "experimental defensive try")
```

It currently precedes the allocator tuple because its adapter itself allocates
the complete union before installing the try writer. Preserve this behavior.
The later allocator entry is an idempotent replay. Retain
`"defensive_try": defensive_try_patch.status(payload)` in `_grown_status_fields`.
All four dictionaries already expand this helper: XBE inspection around line
639, disc inspection around 764, XBE write result around 1489, and disc write
result around 1765. Keep `defensive_try_patch` receipts in both write paths,
including `stats_install`, `table_install`, limits and `runtime_witnessed=False`.
Do not keep an old two-request snapshot in any caller.

The scorebug image installer's `extra_requests`, the final grown pass and all
other first allocators must include the extension before growth. The existing
manifest builder's request expression and three owner/application lists use
this single module; its Recorder emits both named owners. The two XBE gates
use the updated complete union in `tests/nfl2k5_allocator_stack.py` and assert
the extension is installed. There is no separate runtime Python stats module.

## BuildPlan, presets and presentation

Protected `mod_editor/core/mod_build.py`: retain `defensive_try: bool = False`,
bool validation, recipe/Studio forwarding, `wants_xbe_patch`, normalization to
grown space, early-pass `defensive_try=False`, final-pass condition and final
`_apply_all(... defensive_try=plan.defensive_try ...)`. **Basic false, Advanced
false, Experimental false.** Explicit witness selection enables the complete
feature. The selected request union now automatically chooses allocator v3.

Protected `mod_editor/gui/gameplay_patches_panel_qt.py`: retain the PATCHES row
using `tt.defensive_try_patch.UI_TEXT` and retain `defensive_try` in NEEDS_IMAGE.
Its replacement text is supplied by the backend and contains both required
words:

> Retail: Defensive possession ends a try. Patch: Allows defensive returns,
> two points for a return score and one point for a try safety. Adds defensive
> conversion totals to the box score and player season stats. EXPERIMENTAL /
> UNWITNESSED. Suspended saves do not retain these game counts.

The old "box-score row not implemented" limitation can now be removed from
this surface. Retain the concrete suspended-save limitation. Do not replace
it with an implication that reload merely needs testing. The archive of old
per-game franchise box scores is also not extended. Protected
`mod_editor/gui/build_panel_qt.py` keeps its existing `_option` caption,
`Defensive two-point returns (experimental)` (42 characters), this UI_TEXT,
`badge="EXPERIMENTAL / UNWITNESSED"`, `needs_image=True`, and existing checkbox
load/reset/BuildPlan forwarding. Other GUI panels need no new control.

## Allowlist, closure, capability and production manifest

Protected `packaging/release-allowlist.txt` already contains these lines; retain
them without duplicates:

```text
mod_editor/core/nfl2k5_defensive_try.py
docs/mod_editor/nfl2k5_defensive_try_capability.json
```

The extension is in the same module. Its runtime imports are `hashlib`,
`struct`, `nfl2k5_xbe_space`, `nfl2k5_bump_strength`, `nfl2k5_draft_ai` and now
`nfl2k5_team_column` (native card definitions and recognized hook state).
The optional module CLI uses stdlib `argparse`, `json`, `pathlib`. All imported
core modules are already in the release closure. Protected
`packaging/check_2k5_mod_studio_runtime.py` retains its defensive-try import and
API checks; also require `STATS_OWNER`, all four REQUESTS, `stats_code_for`,
`stat_tables`, and the team-column dependency. Keep runtime evidence false.
Re-run the closure/import and protected integrated validation checks after
integration; update any release source fingerprints through their usual flow.
No updater, release tag, CI, or new library dependency change is required.

Replace the existing canonical capability row
`nfl2k5.gameplay_tuning_sliders.defensive_try` with the supplied
`docs/mod_editor/nfl2k5_defensive_try_capability.json`. It is the same surface,
with module commands that pass the registry's file-check mode:

```text
python3 -m mod_editor.core.nfl2k5_defensive_try apply <source.xbe> <new-copy.xbe>
python3 -m tests.mod_editor.test_nfl2k5_defensive_try_stats
```

Keep classification `offline-writer-proved` and runtime `not-tested`.
The replacement row's structure, file references and module commands pass.
The complete registry file gate currently stops at the unrelated missing
`docs/research/apf_audio.md`; restore that baseline evidence during integration.
Update the integrated validation runner to include the new stats and manifest
suites beside the existing rules suite. It is supplied as a row for Claude's
canonical merge, not silently applied to the shared registry.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after integration and sufficient free
disk space. This session's scratch manifest is explicitly a **bounded XBE
projection**, with new hooks and all four children observed through Recorder,
unchanged owners inherited only after checking every source fingerprint, and
new full-union allocations replacing old child addresses. It never claims a
new disc build. The default production source-drift guard remains intact.
The report gives exact gate commands using `NFL2K5_CAVE_MANIFEST` for this
projection. Re-run them against the freshly generated production manifest.

Existing beta-61 applied discs lack the new owner and must be rebuilt from
base. The original 1,440-byte RX and 1,040-byte RW allocations stay fixed.
The new `nfl2k5_defensive_try_stats` child reserves 2,048 RX and 4,096 RO with
16-byte alignment and zero additional RW. The brief authorizes scale-out but
has no separate planned stat row; this is the documented budget decision,
preserving every other committed budget. The complete plan leaves 4,096 RW
bytes available to new owners. Do not shrink others to accommodate it.
# r62 scorebug fix and freeze diagnostics, 2026-09-06

This section supersedes earlier scorebug shipping and preset advice below.
See `ASTRA_SCOREBUG_FIX_REPORT.md`. The static compiler is
`espn-reference-v8`; the runtime resource compiler is
`scorebug-runtime-v2-probes`. **EXPERIMENTAL / UNWITNESSED.** The earlier
runtime build has a community-witnessed entry-to-game freeze. Native bounded
tests do not reproduce that freeze; do not describe this revision as a proved
runtime hang fix. The severe static clipping also still needs a fresh witness.

The diagnostic surface is implemented in the existing CLI:

```text
python3 -m tools.nfl2k5_scorebug_reference apply SOURCE TARGET --runtime-probe PROFILE
python3 -m tools.nfl2k5_scorebug_reference status TARGET --runtime-probe PROFILE
```

Profiles are `transport`, `hooks`, `resources`, `neutral`, `pair`, `full`.
`--runtime` remains shorthand for `full`. Use a clean source for every
profile. `pair` means TB/NE plus neutral, in both orientations. This chooses
the brief's CLI option: **do not add a `scorebug_runtime_probe` BuildPlan
field or a probe dropdown.** The five non-full controls are not cosmetic
features. The extra transport control separates the binding scene and pack
relocation from hooks and additional texture loading.

## Dispatcher, allocation and four status dictionaries (protected)

Keep the existing imports `scorebug_reference` and `scorebug_runtime_patch`.
The `_apply_all` tuple remains:

```python
(scorebug_runtime, scorebug_runtime_patch,
 "scorebug_runtime_patch", "experimental scorebug effects"),
```

Keep `scorebug_runtime: bool = False` in `_apply_all`, `write_xbe_copy`,
`write_image_copy`, validation and all forwarding calls. No probe kwarg is
added to these dispatchers. Their default calls still select `probe="full"`.
Keep the existing `runtime` argument to `_selected_space_requests` and
`_xbe_space_adapter`, and the contribution
`scorebug_runtime_patch.REQUESTS if runtime else ()`. The owner is unchanged:
1,408 bytes of RX code, 128 bytes of RW state, no new RO allocation. Both
gate unions and all three manifest owner lists already enumerate it; do not
add a second owner or another budget row.

Keep resource installation deferred until the complete selected union is
known. Forward the entire union as `extra_requests` to
`runtime_apply_in_place`; realize other selected owners in the existing final
XBE pass. Its returned lazy `PackView` objects are internal compiler values;
receipts remain ordinary JSON dictionaries. Do not materialize a pack in a
dispatcher. The descriptor must remain open while a view is consumed.

Retain these exact entries in all four public status dictionaries:

| Dictionary | Runtime entry | Placement entry |
| --- | --- | --- |
| `read_xbe` | `"scorebug_runtime": scorebug_runtime_patch.status(payload)` | `"scorebug_xbe": scorebug_reference.xbe_status(payload)` |
| `read_image` | `"scorebug_runtime": scorebug_runtime_patch.status(payload)` | `"scorebug_xbe": scorebug_reference.xbe_status(payload)` |
| `write_xbe_copy` | `"scorebug_runtime": scorebug_runtime_patch.status(result)` | `"scorebug_xbe": scorebug_reference.xbe_status(result)` |
| `write_image_copy` | `"scorebug_runtime": scorebug_runtime_patch.status(after)` | `"scorebug_xbe": scorebug_reference.xbe_status(after)` |

For the two image dictionaries, also retain
`"scorebug_runtime_resources": scorebug_reference.runtime_image_status(path)`
on read and `runtime_image_status(target)` after write. These are full-profile
checks. CLI controls must use the matching `--runtime-probe` status command;
the normal GUI may report them as foreign. An XBE-only status is never proof
that its resource appendix was installed. Old v7/v1 or mixed bytes refuse;
rebuild from a clean source, without an implicit migration.

## BuildPlan, presets and GUI wording (protected)

Keep existing fields `scorebug: bool = False` and
`scorebug_runtime: bool = False`. Keep runtime normalization to
`scorebug=True, xbe_space=True`, image-only eligibility, Hi-res scorebug
conflict rejection, early-pass deferral and final receipt/status forwarding.
Set explicit preset values:

| Preset | `scorebug` | `scorebug_runtime` |
| --- | --- | --- |
| Basic | false | false |
| Advanced | false | false |
| Experimental | true | **false** |

The required behavior change is clearing Experimental's current automatic
runtime selection. Manual runtime opt-in remains available for diagnostics.
Preset selection must clear a previously selected runtime checkbox. Keep
Studio forwarding both existing booleans; there is no additional option.

Replace the two Gameplay Patches descriptions and corresponding help maps:

```python
("scorebug", "Experimental ESPN scorebar",
 "Retail: Uses the original scoreboard. Patch: Repositions the ESPN bar "
 "using the game's safe area, with dark score cells and a clear clock strip. "
 "Team names stay live; the timeout marks are decorative. Moves the kick "
 "meter up and hides the lineup strip. EXPERIMENTAL / UNWITNESSED v8; "
 "the previous version was clipped in a tester's game."),
("scorebug_runtime", "Scorebug effects (diagnostic only)",
 "Retail: Uses the original team panels and timeout display. Patch: Adds "
 "team logos, remaining timeout marks, score flashes, down refresh and a "
 "red play clock below five seconds. The previous version froze when a "
 "tester entered a game. EXPERIMENTAL / UNWITNESSED v2; use the report's "
 "CLI probes on a separate disc copy."),
```

Keep both keys in `NEEDS_IMAGE`. Build tab `_option` captions are exactly
`"Experimental ESPN scorebar"` (26 characters) and
`"Scorebug effects (diagnostic only)"` (34 characters), both below 60.
Keep `badge=NOT_TESTED`; use the same descriptions for help/details. Do not
translate offline test success into a gameplay-tested badge. The CLI profiles
are intentionally absent from the product's everyday flow.

## Allowlist, runtime closure and capability registry (protected)

Existing allowlist lines that must remain, with the updated source files:

```text
mod_editor/core/nfl2k5_hud_layout.py
mod_editor/core/nfl2k5_scorebug_ingame.py
mod_editor/core/nfl2k5_scorebug_resources.py
mod_editor/core/nfl2k5_scorebug_runtime.py
tools/nfl2k5_scorebug_layout.py
tools/nfl2k5_scorebug_position_patch.py
tools/nfl2k5_scorebug_reference.py
```

Add these explicit documentation/capability lines:

```text
ASTRA_SCOREBUG_FIX_REPORT.md
docs/mod_editor/nfl2k5_scorebug_runtime_capability.json
docs/scorebug_ingame/probe_capability.json
```

Do not add the new native projection tool or its test fixtures to the product
allowlist: `tools/nfl2k5_scorebug_projection.py` deliberately imports the
development-only Unicorn fixture. Its PNGs, witness attachments and detailed
receipts belong to the repository handoff, not the application runtime.

Keep the protected runtime-closure import probe's existing
`mod_editor.core.nfl2k5_scorebug_ingame`,
`mod_editor.core.nfl2k5_scorebug_resources`,
`mod_editor.core.nfl2k5_scorebug_runtime`,
`mod_editor.core.nfl2k5_hud_layout`, `tools.nfl2k5_scorebug_layout`,
`tools.nfl2k5_scorebug_position_patch` and `tools.nfl2k5_scorebug_reference`
coverage (add any missing direct import entries). New compiler dependencies
are standard-library `functools.lru_cache` and the existing `platform_compat`.
Pillow remains the existing image-build dependency. Unicorn and Capstone are
proof dependencies, never product imports.

In the protected runtime probe, assert both new version strings, the six
profile names, counts `(0, 0, 264, 8, 24, 264)`, and the documented default
`full` behavior. Retain the existing static-source-art and runtime-owner
checks. No resource compilation should read a whole pack into memory.

Replace registry row `nfl2k5.scorebug_presentation.runtime` using
`docs/mod_editor/nfl2k5_scorebug_runtime_capability.json`, and merge new row
`nfl2k5.scorebug_presentation.runtime_probes` from
`docs/scorebug_ingame/probe_capability.json`. The new row is CLI-only and
hidden from the GUI. Both objects have exact schema keys and module-based
`python3 -m ...` backend/validation commands. Validate the merged, ID-sorted
registry with file checks. The handoff rows pass schema and their own file
checks; whole-registry file checking currently stops at the pre-existing
missing `docs/research/apf_audio.md`. Registry integration may require the usual
capability-count/closure fingerprint refresh; preserve unrelated rows.

## Protected cave manifest regeneration

Both XBE gates pass with this revision's existing owner in both composition
orders. The production manifest intentionally remains untouched and detects
six changed source fingerprints. A private conservative candidate retained
the released reservations, reobserved affected XBE writers in legacy and v3
layouts (530 spans), and passed the 28-test manifest suite. That candidate is
not a canonical disc rebuild and must not be copied into production.

Claude must perform the normal regeneration after protected integration:

```text
python3 tools/nfl2k5_cave_oracle.py manifest '/path/to/retail/default.xbe' --xiso '/path/to/retail.xiso.iso' --work-dir '/path/to/disposable-work' --json data/nfl2k5_cave_reservations.json
python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
```

Use a disposable temporary directory, remove all acceptance discs on every
exit path, and preserve the main-drive 100 GB free-space floor. No real disc
was built in this task because its required temporary copy would cross that
floor. Do not run the historical beta-60 proof builder for this matrix: it
requires a canonical whole-disc release baseline and retains large outputs.

---

# r62 calendar engine handoff, 2026-09-05

This section supersedes the old season-cap limitation and wave-2 specification
below. Backend: `mod_editor/core/nfl2k5_calendar_engine.py`; allocator owner:
`nfl2k5_calendar`. **EXPERIMENTAL / UNWITNESSED.** See
`ASTRA_CALENDAR_ENGINE_REPORT.md` for results, the precise schedule rule and
Noah's required witnesses. Protected implementation files remain unchanged.

## BuildPlan and presets (protected mod_build.py)

Add `calendar_engine: bool = False` beside `season_cap`. Both must be exact
bools in plan validation, recipe loading, Studio forwarding, availability,
inspection, receipt maps and `wants_xbe_patch`. The public 128-season option
means the complete repair: normalize `season_cap or calendar_engine` to
`season_cap=True`, `calendar_engine=True`, `season_2026=True`, `xbe_space=True`.
The 2026 dependency installs the matching regular/preseason ROST templates;
XBE-only application cannot certify that external resource. Backend 2004
support remains available for a deliberately matched 2004 template build.

Explicit preset values: Basic false/false; Advanced false/false; Experimental
true/true **only after** the new standalone suites, both XBE gates, protected
wiring/runtime checks and regenerated manifest pass on the integrated stack.
If an integration gate fails, set both Experimental values false together.
Do not ship the older gate alone under a complete-calendar caption. The old
`nfl2k5_season_cap` primitive stays available for diagnostic/core callers and
retains its honest gate-only receipt.

Defer `calendar_engine` to the final grown executable pass, after the existing
`season_2026` image step. Include `calendar_engine=False` in early `replace`
passes. Add `or plan.calendar_engine` to the final-pass condition, pass its
real value to the final `_apply_all`, and retain `calendar_engine_patch` and
`calendar_engine` in the final step receipt. The scorebug resource installer's
`extra_requests` must already include calendar even when its own runtime is
selected. The allocator union must be complete before ANY owner allocates.

## Dispatcher tuple, kwargs, allocation and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import:

```python
from . import nfl2k5_calendar_engine as calendar_engine_patch
```

Add keyword `calendar_engine: bool = False` to `_apply_all`, `write_xbe_copy`,
`write_image_copy` and their forwarding/nonempty-selection/type-validation
paths. Do the public option normalization in BuildPlan, not in an early
low-level call that intentionally defers growth. Add the argument at the end
of `_selected_space_requests`, `_xbe_space_adapter` and inherited defensive
adapter constructors, and append:

```python
+ (calendar_engine_patch.REQUESTS if calendar_engine else ())
```

Forward the flag into both allocator-capable adapters and the scorebug
resource lane's complete union. Include `or calendar_engine` in the allocator
condition. After the allocator entry in `_apply_all`'s final owners tuple add:

```python
(calendar_engine, calendar_engine_patch,
 "calendar_engine_patch", "128-season calendar (experimental)"),
```

Keep apply-on-applied replay so a sealed mixed install refuses. The module
coordinates the existing year, calendar, season-length, preseason and
playoffs14 groups and the cap gate, adding only complete missing prerequisites.
Do not apply those older groups after the calendar pass. Their public status
readers now recognize the validated overlay; a raw group reapply still refuses,
as before. Do not use the old predecessor projection as a writer output.

In `write_image_copy`'s early runtime-resource lane use
`calendar_engine=calendar_engine and not scorebug_runtime`; include the real
flag in the resource writer's `extra_requests` and final post-resource call.
A previously sealed union missing calendar refuses and requires a clean build.

The four public status dictionaries require these exact entries (or one shared
helper called by all four, using the appropriate byte variable):

| Return dictionary | Entry |
| --- | --- |
| `read_xbe` | `"calendar_engine": calendar_engine_patch.status(payload)` |
| `read_image` | `"calendar_engine": calendar_engine_patch.status(payload)` |
| `write_xbe_copy` | `"calendar_engine": calendar_engine_patch.status(result)` |
| `write_image_copy` | `"calendar_engine": calendar_engine_patch.status(after)` |

Keep the separate `season_cap` status: an applied cap byte does not prove a
calendar installation. Surface the calendar receipt's base year, byte encoding,
zero persistent data, exact hashes, touched sites and unwitnessed status.

## Gameplay Patches, Build tab and Franchise wording (protected GUI)

Expose ONE combined 128-season option under the existing `season_cap` key.
Its BuildPlan normalization carries the implementation field `calendar_engine`.
Add both keys to `NEEDS_IMAGE`; neither is a folder-only or save-only feature.
Replace the `season_cap` PATCHES row and matching short-label/help maps with:

```python
("season_cap", "128-season franchise (experimental)",
 "Retail: Franchise dates and birth dates use a fixed century. Patch: Repairs "
 "dates, weekdays, live player birth years and season labels through index 127, "
 "with the final postseason in the following year. EXPERIMENTAL / UNWITNESSED. "
 "Natural rollovers and save reloads still need testing. History keeps its existing limits."),
```

The Build `_option` is:

```python
self.season_cap_check = self._option(
    f, "season_cap", "128-season franchise (experimental)",
    calendar_engine_patch.UI_TEXT, badge=NOT_TESTED)
```

Caption: 35 characters, below 60. Wire checkbox eligibility, load/reset,
inspection and Gameplay-to-Build forwarding. Availability for this combined
option requires both modules and the allocator plus the existing 2026 image
resources. `studio_qt.py` must forward `calendar_engine` with default false.

No Franchise data-view or codec change is needed: it already uses a full base
year plus the saved byte index and a moving live-DOB century. A save has no
new field and cannot identify the executable's installed calendar patch.
When replacing its old informational warning during integration, use:
“Use the calendar patch with your build's starting year for long franchises.
A save alone does not identify that patch. Editing this year does not simulate
seasons.” Keep index/ordinal display and terminal-index read-only behavior.
Do not globally replace the gate-only module's warning with a repair claim.

## Packaging, closure, capability and manifest

Add these explicit protected release-allowlist lines:

```text
mod_editor/core/nfl2k5_calendar_engine.py
mod_editor/core/nfl2k5_calendar_engine_code.py
docs/mod_editor/nfl2k5_calendar_engine_capability.json
ASTRA_CALENDAR_ENGINE_REPORT.md
```

The modified preseason, playoffs14 and season-length modules must be staged
from this revision. Their existing paths remain in the closure. Add
`mod_editor.core.nfl2k5_calendar_engine` and
`mod_editor.core.nfl2k5_calendar_engine_code` to the protected runtime import
probe. Transitive runtime imports are the existing preseason, playoffs14,
season-length, season-cap, allocator, rdata-site, bump-strength, cave-oracle
and draft-assembler helpers, plus standard-library datetime/hashlib/struct.
GNU as, Capstone and Unicorn are development/proof dependencies only. The
annotated `.S`, assembler CLI and tests are developer files, not runtime inputs.

Merge `docs/mod_editor/nfl2k5_calendar_engine_capability.json` into the existing
capability registry using its standard workflow. Refresh closure fingerprints
and the protected cave manifest with Claude's manifest command. The shared
allocator gate union and all three manifest owner lists/request composition
are already updated. Recorder ownership uses the Python module suffix
`nfl2k5_calendar_engine`; named allocator children use `nfl2k5_calendar`.
Do not rename the budget owner to get a second reservation. No protected
manifest JSON was regenerated in this task.

---

# r62 storage growth handoff, 2026-09-05

Backend: `mod_editor/core/nfl2k5_roster_storage.py`, owner
`nfl2k5_roster_storage`, option **`all_stadiums`**. This addition precedes and
preserves earlier handoffs. The implemented primitive offers the 82 existing
stadiums in Create a Team. It does not enlarge team records, create more teams
or support 16/17 reserves. See `ASTRA_STORAGE_GROWTH_REPORT.md` for the design
and census. Label the option **EXPERIMENTAL / UNWITNESSED**.

## BuildPlan, presets and build ordering (protected)

In `mod_editor/core/mod_build.py`, add `all_stadiums: bool = False` beside
`zone_drop_cap`. Explicitly add `"all_stadiums": False` to **each** of
`softdrink_basic`, `softdrink_advanced`, `softdrink_experimental`; none enables
it. Preset selection clears previous manual opt-in. Include the flag in plan
validation (exact bool), recipe loading, `wants_xbe_patch`, availability,
inspection, selection checks, status/receipt maps and Studio plan forwarding.
Availability requires `nfl2k5_roster_storage` and `nfl2k5_xbe_space`.
Normalize selection to `xbe_space=True` and use the existing grown-feature
image-only preflight. This option alone does not enable another gameplay patch.

The initial `replace(plan, ... xbe_space=False, ...)` near line 831 must include
`all_stadiums=False`. All early executable passes must keep the flag false.
At the final growth pass near lines 1137-1146:

1. Pass `all_stadiums=plan.all_stadiums` into `_selected_space_requests` for
   the scorebug resource installer's `extra_requests`. This is necessary even
   if its own runtime owner is already selected.
2. Include `or plan.all_stadiums` in the final executable-pass condition.
3. Forward `all_stadiums=plan.all_stadiums` to the final `_apply_all` call and
   retain its `all_stadiums_patch` receipt plus `all_stadiums` installed status.

The source ROST must retain all 82 retail stadium records. An older save with
those records needs no conversion; the existing +0x114 pointer is serialized.
Do not label a patch receipt as proof that custom or truncated stadium tables
are compatible. No PLAY/ROST archive edit is needed for this option.

## Dispatcher, allocation union and four status dictionaries (protected)

In `mod_editor/core/nfl2k5_throw_tuning.py`:

```python
from . import nfl2k5_roster_storage as roster_storage_patch
```

Add keyword `all_stadiums: bool = False` to `_apply_all`, `write_xbe_copy` and
`write_image_copy`, all their forwarding calls and their nonempty-selection
checks. Validate its type alongside `defensive_try` and `zone_drop_cap`.
Append the argument at the end of existing helper signatures to retain
positional compatibility. Extend the existing union helper as follows:

```python
def _selected_space_requests(with_kickoff=False, runtime=False, momentum=0,
                             defensive_try=False, zone_drop_cap=False,
                             all_stadiums=False):
    return ((kickoff_relocated_patch.REQUESTS if with_kickoff else ())
            + (scorebug_runtime_patch.REQUESTS if runtime else ())
            + (momentum_patch.REQUESTS if momentum > 0 else ())
            + (defensive_try_patch.REQUESTS if defensive_try else ())
            + (zone_drop_patch.REQUESTS if zone_drop_cap else ())
            + (roster_storage_patch.REQUESTS if all_stadiums else ()))
```

Add `all_stadiums=False` to `_xbe_space_adapter.__init__`, and forward it
to that helper. In the final `_apply_all` owners tuple, forward the flag to
**both** `_defensive_try_adapter` and `_xbe_space_adapter`. The defensive
adapter inherits the union constructor and can be the first allocator caller.
Extend the allocator tuple's condition with `or all_stadiums`. After the
allocator tuple, add this tuple alongside the other final owners:

```python
(all_stadiums, roster_storage_patch,
 "all_stadiums_patch", "all 82 Create a Team stadiums (experimental)"),
```

Keep the existing loop's apply-on-applied behavior, so replay validates the
entire seal. The complete union is mandatory before first growth; an existing
allocation without this owner refuses and requires a clean rebuild. The
allocator now orders this owner after all beta-61 owners without changing
their addresses. It adds 82 immutable bytes and no RW bytes or new pages.

`write_image_copy` has a separate scorebug-runtime lane near lines 1496 and
1568-1577. Defer `all_stadiums` there with the other grown flags in its early
call (`all_stadiums=all_stadiums and not scorebug_runtime`), forward the real
flag to the resource writer's `extra_requests`, then forward it to the final
post-resource `_apply_all`. Otherwise the runtime lane seals an incomplete
union and a later stadium installation must refuse.

The four public return dictionaries must contain these exact projections:

| Dictionary | New entry |
| --- | --- |
| `read_xbe` | `"all_stadiums": roster_storage_patch.status(payload)` |
| `read_image` | `"all_stadiums": roster_storage_patch.status(payload)` |
| `write_xbe_copy` | `"all_stadiums": roster_storage_patch.status(result)` |
| `write_image_copy` | `"all_stadiums": roster_storage_patch.status(after)` |

Use the actual byte variable in each function. This stack already centralizes
grown projections in `_grown_status_fields`: adding the projection there is
appropriate if all four returns continue to call it. Preserve receipt fields
`experimental`, `runtime_witnessed`, `save_layout_changed`, `reserve_limit`,
`team_slots`, exact hashes/changed-byte counts and allocation reservations.

## Gameplay Patches, Build tab and Reserves (protected GUI)

In `mod_editor/gui/gameplay_patches_panel_qt.py`, add `"all_stadiums"` to
`NEEDS_IMAGE` and use this PATCHES row (also update any short-label map):

```python
("all_stadiums", "All 82 Create a Team stadiums (experimental)",
 "Retail: Create a Team offers 67 stadiums. Patch: Offers all 82 existing "
 "stadiums. EXPERIMENTAL / UNWITNESSED. Added previews and game loading need "
 "testing. Team and reserve limits stay the same."),
```

In `mod_editor/gui/build_panel_qt.py`, add:

```python
self.all_stadiums_check = self._option(
    gameplay_layout, "all_stadiums",
    "All 82 Create a Team stadiums (experimental)",
    roster_storage_patch.UI_TEXT)
```

Use its current gameplay layout variable. The caption is 44 characters,
below 60. Wire checkbox load/reset/enable state and image eligibility. In
`studio_qt.py`, forward the boolean with default false into BuildPlan and any
Gameplay-to-Build bridge. No additional tab or GUI panel is required.

**Reserves must stay at 12.** The stadium option is not evidence of wider
player storage. Do not use `xbe_space`, `all_stadiums` or a save metadata byte
alone to raise the Reserves control. A future 16/17 patch needs its own exact
XBE status, compatible versioned save schema and eligibility predicate before
its UI limit can change. The existing Reserves panel is outside this job's
GUI ownership, and no edit to it is requested for the delivered primitive.

## Allowlist, closure, capability and manifest (protected)

Add these exact release-allowlist paths:

```text
mod_editor/core/nfl2k5_roster_storage.py
docs/mod_editor/nfl2k5_roster_storage_capability.json
docs/mod_editor/nfl2k5_roster_storage_census.json
ASTRA_STORAGE_GROWTH_REPORT.md
```

The audit CLI `tools/nfl2k5_roster_storage_audit.py` and standalone tests are
developer evidence tools; they need not enter the end-user runtime closure.
Keep the already allowlisted roster/save/franchise/practice-squad codecs,
allocator, bump-strength digest helper, boot-logo and depth-chart-storage
helpers. Add `mod_editor.core.nfl2k5_roster_storage` to the import probe in
`packaging/check_2k5_mod_studio_runtime.py`. Its codec helpers import only the
standard library. Patch operations additionally import existing `nfl2k5_xbe_space`,
`nfl2k5_bump_strength` and `nfl2k5_cave_oracle`, with their existing closure.
Capstone remains test/audit-only; Unicorn is unused by this job.
Regenerate applicable provider closure hashes with the existing packaging
tools after wiring, without dropping any required transitive import.

Merge `docs/mod_editor/nfl2k5_roster_storage_capability.json` using the existing
registry serializer/validator. ID is `nfl2k5.stadiums_fields.all_stadiums`,
existing surface `stadiums_fields`, classification `offline-writer-proved`,
runtime `not-tested`, all presets off. The validation command is the new
standalone storage test. Do not advertise more created teams or larger reserves.

The unprotected manifest recorder and both gate compositions already include
the new owner. The protected `data/nfl2k5_cave_reservations.json` was untouched.
Claude must regenerate it **after** the protected code and closure edits:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch --json data/nfl2k5_cave_reservations.json
```

Retain the source-drift guard. Run both XBE gates, the new storage suite, the
three existing codec suites and `test_rosters_reserves_abilities.py`, then the
existing packaging/runtime closure gates. The supplied standalone tests skip
precisely for missing retail evidence or Capstone and do not read whole packs
or disc images into RAM. No release-tag/updater/CI changes are requested.
# Beta 62 allocator scale-out: image_xbe_extent accepted sizes

In `mod_editor/core/nfl2k5_throw_tuning.py`, replace only the grown-size
membership check in `image_xbe_extent` with:

```python
_require(length in (depth_chart_storage.FILE_SIZE, *xbe_space_patch.accepted_file_sizes()),
         f"default.xbe inside the image is {length} bytes, not the retail size or a recognised grown size")
```

Retain the subsequent bounded read and `recognized_grown_xbe(candidate)` check.
Size acceptance alone does not establish a valid allocation. The new accepted
extent is **12,300,288 bytes (`0xBBB000`)**; prior accepted sizes are unchanged.

# Defensive try handoff, 2026-09-05

The new backend is `mod_editor/core/nfl2k5_defensive_try.py`, owner
`nfl2k5_defensive_try`, option **`defensive_try`**. This section is additive;
all earlier handoffs below remain intact. See `ASTRA_DEFENSIVE_TRY_REPORT.md`.
Label this **EXPERIMENTAL / UNWITNESSED**. The bounded rules implementation is
available for an exhibition witness, but the requested retail defensive
conversion box-score row is **not implemented**. Do not describe that stat
requirement as completed. `read_runtime_stats()` exposes a temporary diagnostic
line only, limited to the 128 retained drives, with no saved category.

## Protected BuildPlan, presets and final growth pass

In `mod_editor/core/mod_build.py`, add `defensive_try: bool = False` beside
`xbe_space`. Explicitly set `"defensive_try": False` in **all three** preset
dictionaries: `softdrink_basic`, `softdrink_advanced`, and
`softdrink_experimental`. Switching presets must clear a prior manual opt-in.
Noah's disposable witness disc selects it manually. Do not change a preset to
true to make manifest generation observe it; the manifest helper now observes
the dormant owner separately.

Add the key to `wants_xbe_patch()`, recipe loading, availability, inspection,
nonempty-selection checks, receipt/status maps, Studio plan construction, and
checkbox state restoration. Availability requires this module and
`nfl2k5_xbe_space`. Normalize `plan.defensive_try` to imply `xbe_space=True`.
Extend the existing grown-feature image-only preflight to include it. Both
retail kick spots and `kick_rules` modern spots compose; this option alone
does not imply `kickoff_relocated` or dynamic kickoff.

Defer **all three grown flags** until the existing final growth pass near
`receipt["result"] = inspect(target)`. Add `defensive_try=False` to the early
`replace(plan, ..., xbe_space=False, kickoff_relocated=False)` decision and
keep the early XBE writer's flags false. Extend the final condition to
`plan.xbe_space or plan.kickoff_relocated or plan.defensive_try`, pass
`defensive_try=plan.defensive_try` to `_apply_all`, and include both
`defensive_try_patch` and `defensive_try` in that step's receipt. This keeps
every existing resource/XBE pass before growth, including Guardian caps.

## Protected executable dispatcher and four status dictionaries

In `mod_editor/core/nfl2k5_throw_tuning.py`:

```python
from . import nfl2k5_defensive_try as defensive_try_patch
```

Add the keyword `defensive_try: bool = False` to `_apply_all`,
`write_xbe_copy`, and `write_image_copy`, their nonempty-selection checks and
every forwarding call. Do not insert a positional argument into existing
callers. `defensive_try` implies `xbe_space=True`.

The brief requests the tuple after kick rules and before the allocator's
final tuple. Use a union-aware adapter in that final group, after all existing
retail writers and logo handling. A bare early `defensive_try_patch.apply`
would allocate only its own requests and make later relocation refuse.
The complete, concrete adapter change is:

```python
def _selected_space_requests(with_kickoff, with_defensive_try):
    return ((kickoff_relocated_patch.REQUESTS if with_kickoff else ())
            + (defensive_try_patch.REQUESTS if with_defensive_try else ()))

class _xbe_space_adapter:
    def __init__(self, with_kickoff, with_defensive_try=False):
        self.requests = _selected_space_requests(with_kickoff, with_defensive_try)

    def status(self, payload):
        state = xbe_space_patch.status(payload)
        if state == "applied":
            xbe_space_patch.apply(payload, self.requests)  # validate exact union
        return state

    def apply(self, payload):
        return xbe_space_patch.apply(payload, self.requests)

class _defensive_try_adapter:
    def __init__(self, with_kickoff):
        self.requests = _selected_space_requests(with_kickoff, True)

    def status(self, payload):
        return defensive_try_patch.status(payload)

    def apply(self, payload):
        # Pure byte writers: nothing is published if either preflight refuses.
        grown, allocation = xbe_space_patch.apply(payload, self.requests)
        result, receipt = defensive_try_patch.apply(grown)
        return result, {
            **receipt,
            "allocation": allocation,
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "result_sha256": hashlib.sha256(result).hexdigest(),
            "changed_bytes": (sum(a != b for a, b in zip(payload, result))
                              + len(result) - len(payload)),
        }
```

Add `import hashlib` if needed. Replace only the final owners tuple with:

```python
for flag, module, key, label in (
    (defensive_try, _defensive_try_adapter(kickoff_relocated),
     "defensive_try_patch", "experimental defensive try"),
    (xbe_space or kickoff_relocated or defensive_try,
     _xbe_space_adapter(kickoff_relocated, defensive_try),
     "xbe_space_patch", "experimental executable space"),
    (kickoff_relocated, kickoff_relocated_patch,
     "kickoff_relocated_patch", "experimental relocated kickoff"),
):
    # Keep the existing final loop body, including apply on an applied state.
    ...
```

The first adapter allocates the **complete union before first growth**. The
allocator tuple then validates it without growth. Both defensive/relocated
installation orders are byte-identical when preallocated, as the tests prove.
An already-grown input with a different owner union must refuse with a
rebuild-from-base message. Do not shrink, silently reallocate or disable pins.

Add exactly these status entries; use the existing byte variable:

| Function return dictionary | Entry |
|---|---|
| `read_xbe` | `"defensive_try": defensive_try_patch.status(payload)` |
| `read_image` | `"defensive_try": defensive_try_patch.status(payload)` |
| `write_xbe_copy` | `"defensive_try": defensive_try_patch.status(result)` |
| `write_image_copy` | `"defensive_try": defensive_try_patch.status(after)` |

Carry `limitations`, `experimental`, and `runtime_witnessed` from the backend
receipt. An installed status proves bytes only; it does not prove gameplay.

## Protected Gameplay Patches and Build controls

Add `"defensive_try"` to `NEEDS_IMAGE` and this `PATCHES` entry in
`mod_editor/gui/gameplay_patches_panel_qt.py`:

```python
("defensive_try", "Defensive two-point returns (experimental)",
 "Retail: Defensive possession ends a try. Patch: Allows defensive returns, "
 "two points for a return score and one point for a try safety. "
 "EXPERIMENTAL / UNWITNESSED. The separate conversion tally is temporary; "
 "a retail box-score row and saved player or season totals are not implemented.")
```

This is the backend's `UI_TEXT`. Preserve its stat limitation in visible
help. Update the short label map if present. In `build_panel_qt.py`, use the
existing gameplay layout's `_option` call:

```python
self.defensive_try_check = self._option(
    gameplay_layout, "defensive_try",
    "Defensive two-point returns (experimental)", defensive_try_patch.UI_TEXT)
```

Use that panel's actual gameplay layout variable. The caption has 42
characters, under 60. Wire checked/enabled state, image eligibility and all
preset resets. In `studio_qt.py` and any Gameplay-to-Build handoff, forward
the boolean with default false. No separate feature GUI module is needed.

## Allowlist, runtime closure and capability entry

Add these exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_defensive_try.py
docs/mod_editor/nfl2k5_defensive_try_capability.json
ASTRA_DEFENSIVE_TRY_REPORT.md
```

Retain the existing allowlisted allocator and its dependencies. The new
production import is `mod_editor.core.nfl2k5_defensive_try`; its direct core
closure is `nfl2k5_xbe_space`, `nfl2k5_bump_strength`, `nfl2k5_draft_ai` and
their existing transitive imports. Add the new module to
`packaging/check_2k5_mod_studio_runtime.py`'s import probe. Capstone/Unicorn
are test dependencies, not production imports. `read_runtime_stats` takes
an external reader callback and adds no debugger dependency.

The new standalone test belongs in source CI:
`tests/mod_editor/test_nfl2k5_defensive_try.py`. Retain both modified XBE
gate tests and the existing manifest tests. No new release-tag rule, updater
change, network dependency or GUI test is required by this backend.

Merge the complete object in
`docs/mod_editor/nfl2k5_defensive_try_capability.json` into the canonical
registry using its existing canonical serializer/validator. Its classification
is `offline-writer-proved`, runtime status `not-tested`, default false.
The missing box-score category must stay explicit. This is a reviewable
entry, not a claim that the protected GUI integration has already shipped.

## Protected cave manifest regeneration and integration checks

`nfl2k5_cave_manifest.py` now observes this dormant owner, including its
zero-initialized data, and allocates the defensive/relocated union. The
checked-in JSON was not changed. After integration, Claude must regenerate:

```bash
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir .scratch/defensive-try-manifest \
  --json data/nfl2k5_cave_reservations.json
```

Create the scratch directory first. Its disc copy needs over 6 GB. Retain all
prior owners. New code/data addresses with relocated kickoff are
`0x14BA2C0`/`0x14BB000` for defensive try and
`0x14BA860`/`0x14BB410` for relocated kickoff. The allocator's parent pages
reserve every unused byte. Re-run the three feature/gate test scripts below.
The cave gate currently validates the protected historical layout before
substituting the new named reservations **in memory only**; it uses the new
manifest directly once that contains this owner.

The old `space-proof` CLI defaults to the kickoff-only layout. With the new
manifest use `space.allocation_evidence(retail, manifest, allocated=final_xbe)`
(as the composed gate does), or add an explicit allocated-XBE argument to the
CLI. Do not treat a mismatch with the old layout as a free allocation.

Before a witness disc, verify plan serialization and preset switching, a
defensive-only image build, defensive plus modern kick rules, defensive plus
relocated kickoff, status inspection and receipts. The backend scripts are:

```bash
python3 tests/mod_editor/test_nfl2k5_defensive_try.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
```

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
# Momentum model 1 handoff, 2026-09-05

**EXPERIMENTAL / UNWITNESSED.** This section is the protected-file integration
contract for `nfl2k5_momentum.py`. See `ASTRA_MOMENTUM_BUILD_REPORT.md` for exact
calibration, bounded proofs, limitations and Noah's witness list. Earlier
allocator instructions above now need the union of all selected requests.
No protected product file was edited by this job.

## BuildPlan, presets and normalization

In `mod_editor/core/mod_build.py`, add:

```python
momentum: int = 0
momentum_contact: bool = False
```

Validate the integer strictly in 0..100, rejecting Boolean levels. Contact
requires a nonzero level. All three presets, `softdrink_basic`,
`softdrink_advanced`, and `softdrink_experimental`, must explicitly set
`momentum=0, momentum_contact=False`. Switching presets must clear both.
Include both fields in recipe loading, plan round trips, availability,
inspection, selected options and receipt display. Any positive level implies
extra executable space. This is an image experiment, with the existing grown
XBE writer required; use a disposable build copy.

The Momentum profile retains native acceleration. Normalize `accel_ramp=False`
when choosing this profile, including its Retail level, and record a previously
enabled legacy selection as `legacy_accel_ramp_disabled_by_momentum_profile`.
Keep an explicitly named legacy profile available separately. The pure-byte
APIs also compose with a fully recognized legacy ramp in either order for
compatibility testing; receipts report it as retained. That combination cannot
claim human/CPU parity because the legacy ramp bypasses controller marker -1.
Never remove a ramp from an already patched source in place. Rebuild from the
supported source when changing installed settings, allocations or profiles.

## Dispatcher tuple and kwargs

Import `nfl2k5_momentum as momentum_patch` in
`mod_editor/core/nfl2k5_throw_tuning.py`. Thread keyword arguments
`momentum: int = 0, momentum_contact: bool = False` through `_apply_all`,
`write_xbe_copy`, `write_image_copy`, their forwarding calls and nonempty guards.
The two options are ONE executable owner and must be installed together.

Extend `_xbe_space_adapter` to collect `momentum_patch.REQUESTS` when the level
is positive, along with `kickoff_relocated_patch.REQUESTS` and any integrated
new owner's requests. Choose this complete union before first growth, and
validate the same request set on replay. Do not allocate an unknown address or
silently enlarge/shift an existing owner. Ordinary passes still precede growth.

Add this adapter and the following tuple to the existing **final** `_apply_all`
loop, after its allocator entry and alongside relocated kickoff:

```python
class _momentum_adapter:
    def __init__(self, level, contact):
        self.level, self.contact = level, contact

    def status(self, payload):
        return momentum_patch.status(payload)

    def apply(self, payload):
        return momentum_patch.apply(
            payload, momentum=self.level, momentum_contact=self.contact)

# The allocator tuple's flag also includes momentum > 0.
(momentum > 0, _momentum_adapter(momentum, momentum_contact),
 "momentum_patch", "experimental player momentum"),
```

Always call this adapter's `apply` on a recognized installed image, so replay
checks both settings. Do not use the earlier legacy loop's generic
`already_applied` shortcut. Reject `momentum_contact=True, momentum=0` before
any writer runs. `mod_build` must forward the fields in its final grown-XBE
pass after all ordinary XBE/resource passes, as in the allocator handoff.
The contact checkbox is not a second tuple that reconfigures an installed owner.

Momentum owns `0x1CD5D7..0x1CD5DD`; kickoff owns the preceding seven bytes.
Kickoff's hold gate executes first; its released path reaches Momentum, which
captures both dispatcher returns. Both install orders produce identical bytes
when the union is preallocated. Momentum leaves `0x75CC8` and `0x75CD5` alone.
The defensive-try module is absent here: after integrating it, add its actual
REQUESTS and execute both orders with its real owner. The conditional test in
`test_nfl2k5_momentum.py` currently names `nfl2k5_defensive_try`; update that name
if its delivered module differs. Do not mistake the skip for composition proof.

## Four status dictionaries

Add these entries to all four protected dictionaries, using the indicated
local byte variable:

| Dictionary | Byte variable |
| --- | --- |
| `read_xbe()` return | `payload` |
| `read_image()` return | `payload` |
| `write_xbe_copy()` post-write return | `result` |
| `write_image_copy()` post-write return | `after` |

```python
"momentum": momentum_patch.status(payload),
"momentum_settings": momentum_patch.read_settings(payload),
```

Replace `payload` with `result`/`after` in the latter two dictionaries. The
settings include level/contact when applied, model version and experimental /
unwitnessed fields. Display Retail as level 0 when status is retail. Contact
status is foreign if Momentum is foreign, applied only when Momentum is applied
and its stored contact flag is true, otherwise retail. Do not infer settings
from the source plan or label foreign bytes as Retail. Copy these fields through
`mod_build.inspect` and rebuilt-image reporting.

## Gameplay Patches, Gameplay tab and Build tab

Add these exact PATCHES three-field entries to the protected
`mod_editor/gui/gameplay_patches_panel_qt.py`, with both keys in `NEEDS_IMAGE`:

```python
("momentum", "Player momentum (experimental, unwitnessed)",
 "Retail: stock turning and stopping. Patch: wider turns at speed and more "
 "room to stop during ordinary running. Experimental / Unwitnessed."),
("momentum_contact", "Running start in contact (experimental, unwitnessed)",
 "Retail: speed and weight already affect contact. Patch: a sustained running "
 "start can give the ball carrier a small extra boost through contact. "
 "Experimental / Unwitnessed. Requires player momentum."),
```

The existing `gameplay_panel_qt.py` is a read-only inspection/table panel and
has no editable-slider binding pattern. Use the brief's fallback here: an
opt-in Momentum card with **Retail (0), Light (25), Medium (50), Heavy (100)**
and a separate **Running start in contact** checkbox. Light/Medium/Heavy are
three non-retail levels; Retail remains an explicit choice. A later shared
slider component can expose every integer from 0 to 100 with endpoints
**Retail** and **Heavy**, without changing the model. Keep the card visibly
**Experimental / Unwitnessed**. Description: "Players take wider turns at speed
and need more room to stop." Show the contact sentence only when its box is on.
Do not add addresses, history-slot language or rating-cache details to the card.

Build `_option` captions (both under 60 characters):

```python
self._option(layout, "momentum", "Player momentum (experimental)", helper,
             badge="EXPERIMENTAL")
self._option(layout, "momentum_contact", "Running start in contact (experimental)",
             contact_helper, badge="EXPERIMENTAL")
```

The first checkbox needs an integer adapter: checked means the selected
positive level (initially Medium/50), unchecked means 0. Never serialize its
Boolean value into `BuildPlan.momentum`. Preserve the last positive selection
in UI state, reset it on a preset change, and disable/clear contact at Retail.
Include both controls in load/store/availability/summary maps in the Build
panel and Studio. Add neither flag to Basic, Advanced or Experimental defaults.

## Packaging, closure, capabilities and manifest

Append these release allowlist lines:

```text
mod_editor/core/nfl2k5_momentum.py
mod_editor/core/nfl2k5_momentum_code.py
```

Retain the existing entries for `nfl2k5_accel_ramp.py`, `nfl2k5_xbe_space.py`,
`nfl2k5_bump_strength.py`, `nfl2k5_cave_oracle.py` and allocator dependencies.
`tools/nfl2k5_momentum.S` and `tools/nfl2k5_momentum_assemble.py` are development
sources, not runtime requirements. Runtime does not spawn GNU as or import
Unicorn/Capstone. In protected `packaging/check_2k5_mod_studio_runtime.py`, add
`mod_editor.core.nfl2k5_momentum` and `mod_editor.core.nfl2k5_momentum_code` to
`product_modules`, with their existing allocator/helper closure. Exercise
`REQUESTS`, `status`, `read_settings`, `apply`, and `code_for` availability.

Copy the complete row from `docs/mod_editor/nfl2k5_momentum_capability.json`
into the capability registry and update protected runtime registry counts.
Its id is `nfl2k5.gameplay.momentum`; classification is
`offline-writer-proved`, runtime status `not-tested`, defaults off. This row
covers both controls. No commercial game image is a release artifact.

The unprotected manifest builder now observes the actual Momentum owner at
100/contact-on after preallocating kickoff plus Momentum. Both composed XBE
gates enumerate Momentum. A private full-disc manifest was generated and the
oracle suite passed with it; the protected release manifest remains unchanged.
After all parallel integrations, regenerate it with the actual complete union:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir /tmp --json data/nfl2k5_cave_reservations.json
```

Do not update fingerprints manually or relax the source-drift refusal. The
current Momentum allocation is 944 RX bytes and 2,064 RW bytes. Logo + kickoff
+ Momentum leave 496 code bytes and 2,016 data bytes; an additional 512-byte
abilities allocation does not fit. The Speedster hook remains free, but its
future code needs a smaller allocation, an explicit scope tradeoff, or a
separate verified allocator extension. No allocation is promised for an absent
parallel owner.
# r61b: initial corner deep-zone drop cap (2026-09-05)

This section adds `mod_editor/core/nfl2k5_zone_drop.py`, owner
`nfl2k5_zone_drop`, backend `apply(payload, *, cap=None)`, `status(payload)` and
`read_settings(payload)`. The option key is **`zone_drop_cap`**, superseding the
research memo's suggested `cb_deep_zone_drop`. Statuses are `retail`, `applied`
or `foreign`; an identical replay returns `status: already_applied` and zero
changed bytes. Both fresh and replay receipts retain `experimental: true` and
`runtime_witnessed: false`. Cap values in receipts are the actual float32 value.

## Required allocator integration before claiming the complete stack

The brief's append-stable allocator premise does not match this checkout.
`nfl2k5_xbe_space.apply` seals a sorted complete request set, refuses a changed
set on a grown input, and provides one 4096-byte RX page. Here the boot logo,
relocated kickoff and runtime scorebug consume 4064 bytes after alignment.
Adding this exact 80-byte owner requires **4144 bytes**, 48 beyond that page.
The defensive-try and momentum modules named in the brief are absent here.

Do not bypass these refusals, consume padding outside an allocation, shrink
another owner's declaration, or put executable scratch in retail `.text`.
The allocator owner must supply sufficient formally owned code capacity and
validate stable allocations for the final owner set. Until that prerequisite
lands, support zone drop alone, zone drop plus relocated kickoff, or zone drop
plus runtime scorebug hooks, with the **complete union reserved first**. Both
orders of each available pair produce byte-identical images. Simultaneous
zone drop + relocated kickoff + runtime scorebug must fail the capacity check.

Both composed XBE gates retain the existing kickoff/runtime stack and add a
second ordinary-stack + relocated-kickoff + zone-drop image in `setUpClass`.
They explicitly inspect this new owner's complete call and 80-byte allocation.
This is pairwise coverage, not proof of the unavailable complete union. After
the allocator change, merge the branches into one complete stack and run all
orders with the actual defensive-try and momentum modules. Do not count
placeholder owner bytes as execution/composition evidence.

## BuildPlan, presets, reader status and build ordering

In protected `mod_editor/core/mod_build.py`, add:

```python
zone_drop_cap: bool = False  # EXPERIMENTAL / UNWITNESSED
```

Add the key with **False in all three** `softdrink_basic`,
`softdrink_advanced`, and `softdrink_experimental` preset dictionaries. Noah's
witness build must opt in explicitly. Promotion to Experimental is a later
decision only after his witness; Basic and Advanced remain off.

Include it in `BuildPlan.wants_xbe_patch`, `availability()` (requires the new
module and allocator), `inspect_source`, build keyword forwarding, receipt
step projection (`zone_drop_cap`, `zone_drop_settings`, `zone_drop_patch`), and
the recipe/apply-state paths. Selecting it implies `xbe_space=True`, without
implicitly selecting dynamic kickoff or any scorebug option. The existing
dataclass recipe serialization will then preserve the explicit opt-in.

Run ordinary XBE owners, uniform choice and boot-logo repair first. Assemble
the final selected owner request union once, then install the final owned
wrappers. For image builds use the existing grown-extent reader and
`nfl2k5_depth_chart_storage.write_image_xbe`, which supports the new extent and
repins through existing helpers; do not force the grown payload through a
fixed retail-length writer. Close all handles before replacement.

The backend cap is configurable via `apply(payload, cap=...)` over
**0.50..0.84**, default **0.84**. No numerical UI or additional BuildPlan field
is required for this witness experiment. This caps the depth term; lateral
demand remains retail and can still reach 0.84. Values above 0.84 would be
promoted by retail to at least 0.91, defeating the requested animation band.
Values below 0.50 cannot beat retail's final floor. Changing an installed cap
requires a clean rebuild; do not silently replace or repair an installed body.

## Dispatcher tuple, keyword and all four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import:

```python
from . import nfl2k5_zone_drop as zone_drop_patch
```

Add keyword-only `zone_drop_cap: bool = False` to `_apply_all`,
`write_xbe_copy` and `write_image_copy`, include it in both public writer
"at least one selected patch" checks, and forward it through every wrapper
and Build call. In the final `_xbe_space_adapter`, extend the earlier kickoff
and scorebug handoff to reserve:

```python
self.requests = ((kickoff_relocated_patch.REQUESTS if relocated else ())
                 + (scorebug_runtime_patch.REQUESTS if runtime else ())
                 + (zone_drop_patch.REQUESTS if zone_drop_cap else ()))
```

Include the actual selected defensive-try and momentum requests when those
modules land. Call the allocator's capacity validation before attempting any
disc transport. With today's allocator, the three-owner union above must
refuse. The adapter's status must also validate the exact declared request
set on a grown input. Never infer that a `retail` zone-drop status reserves
space: a recognized grown image missing this owner is inspectable, but apply
refuses it until rebuilt with the full union.

After the final allocation tuple and beside the other owned wrappers add:

```python
(zone_drop_cap, zone_drop_patch,
 "zone_drop_patch", "experimental corner deep-zone drop"),
```

The allocator tuple predicate becomes
`xbe_space or kickoff_relocated or scorebug_runtime or zone_drop_cap`.
For this owner always call `apply` after accepting `status` in
`("retail", "applied")`, including replay, and retain its complete receipt.
Add its `changed_bytes` to `changed_byte_count`. Do not replace a replay with
only `{"already_applied": True}`, which would lose cap and witness metadata.

Add both keys to **all four** status dictionaries:

```python
"zone_drop_cap": zone_drop_patch.status(image_bytes),
"zone_drop_settings": zone_drop_patch.read_settings(image_bytes),
```

| Dictionary | Replace `image_bytes` with |
| --- | --- |
| `read_xbe` | `payload` |
| `read_image` | `payload` |
| `write_xbe_copy` | `result` |
| `write_image_copy` | `after` |

For the earlier paired runtime scorebug resource handoff, extend
`nfl2k5_scorebug_ingame.runtime_apply_in_place` and its XBE preflight to accept
`zone_drop_cap=False`, include this owner's request in that transaction's
union, and call `zone_drop_patch.apply` on its final XBE before transport.
Forward the flag from Build and image-copy entry points. Leave it disabled in
the preceding ordinary dispatcher pass. This preserves paired resource/XBE
preflight and avoids prematurely sealing a smaller allocation set. The
scorebug+zone pair is structurally tested here; resource transaction wiring
and a played composed disc remain integration/witness work.

## Gameplay Patches, Build tab and Studio routing

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, add exactly this
`PATCHES` tuple and add `zone_drop_cap` to `NEEDS_IMAGE`:

```python
("zone_drop_cap", "Corner deep-zone backpedal (experimental, unwitnessed)",
 "Retail: corners close to the line can turn and run on their initial deep-zone drop. "
 "Patch: Corners in deep zones backpedal instead of turning and running when they "
 "line up close to the line. Ball reaction and interceptions are not changed by "
 "this. Experimental and unwitnessed in game; a slower drop may allow more deep completions."),
```

This uses the requested plain-language behavior text verbatim. The surrounding
experimental/unwitnessed label describes its evidence level: visible technique
and interception outcomes have not been played. "Not changed" refers to the
ball-response and catch code, not a guarantee of identical outcomes after a
movement change. Do not advertise a read-and-react or interception fix.

Build tab `_option` caption: **`Corner deep-zone backpedal (experimental)`**
(41 characters, under the 60-character limit):

```python
self.zone_drop_cap_check = self._option(
    layout, "zone_drop_cap", "Corner deep-zone backpedal (experimental)",
    helper, badge="EXPERIMENTAL")
```

Use the same helper text, retaining the unwitnessed notice. Add the checkbox
to option maps, availability/image gates, plan creation, build summary,
apply-state, dirty detection, reset and preset paths in protected
`build_panel_qt.py`. Forward/route the new key through the existing Build and
Gameplay Patches state handlers in protected `studio_qt.py` and
`gameplay_panel_qt.py` wherever they enumerate patch keys. No panel was edited
in this session. There is no new feature panel or implicit preset activation.

## Packaging, closure, capability and reservation manifest

Add the explicit protected release-allowlist line:

```text
mod_editor/core/nfl2k5_zone_drop.py
```

Retain existing allowance for `nfl2k5_xbe_space.py`,
`nfl2k5_depth_chart_storage.py`, `nfl2k5_boot_logo.py`,
`nfl2k5_bump_strength.py`, `nfl2k5_draft_ai.py`, and `nfl2k5_cave_oracle.py`.
These are the backend's existing helper closure; this feature adds no new
application dependencies. Retain the application's existing Pillow import
through package initialization. Unicorn
and Capstone stay optional proof dependencies and are never runtime imports
of the new module. Do not package `.scratch`, game executables or discs.

In protected `packaging/check_2k5_mod_studio_runtime.py`, add dotted import
`mod_editor.core.nfl2k5_zone_drop`, inspect `REQUESTS`, check
`status(b"bad") == "foreign"`, and assemble an 80-byte `code_for` result
without optional disassembly/emulation packages. Retain the helper imports
above in the runtime closure.

The concrete staged registry row is
`docs/mod_editor/nfl2k5_zone_drop_capability.json`. Copy its sole object into
`mod_editor/capabilities/registry.v1.json`, ID
`nfl2k5.gameplay.zone_drop_cap`, existing surface `gameplay_tuning_sliders`,
classification `offline-writer-proved`, runtime `not-tested`, GUI default
false. Update capability count/catalog expectations and findings routing to
the new PATCHES key when integrating. There is no new schema surface.

After allocator capacity and the final owners land, extend
`nfl2k5_cave_manifest.py` to observe `nfl2k5_zone_drop`: include it in the
module map; add its owner to the recorder's allowed grown writers and
`space.reservations` branches; include `zone.REQUESTS` in the complete final
union; call its real `apply` under the recorder; and add it to `extra_owners`,
`image_steps` and model text. The new standalone test already proves the
recorder covers the complete 80-byte allocation and five-byte hook when
observing a separately reserved compatible layout. Regenerate protected
`data/nfl2k5_cave_reservations.json` with the existing manifest CLI after
these integration changes. Preserve all source-fingerprint drift checks.

Run the two feature suites and both composed gates listed in
`ASTRA_ZONE_DROP_REPORT.md`, then the existing cave-oracle suite with the
fresh complete manifest. Today's protected manifest is deliberately untouched;
the feature test does not relabel a pairwise recording as a complete stack
manifest. Noah's complete witness list and all current gaps are in the report.

# Integration 3 resolution, 2026-09-05

The Momentum, defensive try and zone drop handoffs above are integrated. Their
historical one-page capacity warnings are superseded by the two-RX-page allocator.
Existing kickoff/runtime allocations remain stable when these owners are added.
Both XBE safety gates now compose every owner, including music metadata, and run
all gate assertions in both installation orders. No separate reduced zone-drop
stack remains. The full request union is selected before first growth. Build
uses the paired scorebug transaction with that union reserved, then installs
remaining owners before its outer transaction publishes the complete disc.

All new options remain experimental and unwitnessed, Retail/off in every preset.
The defensive conversion box-score row and persistent category remain missing;
only its diagnostic tally is implemented. See ASTRA_INTEGRATION_3_REPORT.md for
capacity, receipts, complete CI accounting and delivery details.

# r62-rosters-data: 2026 team names, style clarity and explicit age shifts

This section is the integration handoff for `astra/r62-rosters-data`, based on
`5f5b5047d42984ee41449c4a03669e0945a22f2a`. Earlier handoffs above are preserved.
All new behavior is **EXPERIMENTAL / UNWITNESSED**. The protected files were not
edited. The Rosters panel changes are implemented directly; the team-name Build
option and the protected Studio facade connection below are ready for Claude.

## Dispatcher and the four executable status dictionaries

**No `_apply_all` tuple or keyword is added.** There is no executable patch in
this job. Do not pass `team_names_2026` or an age-shift argument through
`nfl2k5_throw_tuning._apply_all`, `write_xbe_copy` or `write_image_copy`.
The four XBE dictionaries in `read_xbe`, `read_image`, `write_xbe_copy` (using
`result`) and `write_image_copy` (using `after`) get **no new key**. A bare XBE
cannot reveal which names or birth dates the main ROST or a loaded save contains.
Neither XBE safety-suite owner list changes; both existing suites are run.
There are no new code/data pages, caves, reservations or digest repins.

## BuildPlan, availability, inspection and order (protected mod_build.py)

Add `team_names_2026: bool = False`. Reject non-Boolean values during plan
validation. Include the field in project/recipe serialization and Build panel
load/save/reset paths. **Basic=false, advanced=false, experimental=false**:
this remains an explicit opt-in even with `season_2026=True`. The fallback names
and changed abbreviations need review, so a calendar choice does not enable it.
Do not include this field in `wants_xbe_patch`.

Availability key `team_names_2026` requires
`_core_module("nfl2k5_team_names_2026")` and the shipped
`data/nfl2k5_team_names_2026.json` with its module-pinned SHA-256. Extend
`mod_build.inspect`'s **data** dictionary with `"team_names_2026": "n/a"` for
non-image input. For a disc use `module.image_status(source)`; parsing/I/O errors
are `foreign`. Expose `module.manifest()["teams"]` for the exact before / desired /
written review, and `strg_audit` for scope. No archive pack is read wholesale.

Reject `plan.team_names_2026` when the input is a bare executable or a save.
Preflight `image_status(source)` before creating output. Only retail/applied
are accepted. Run the grouped pass on the private build image after existing
ROST passes (position pools, season_2026 schedule, team history, prospect names,
player tags and roster_edits). Do this after any generic authored team text is
composed too, so a conflict refuses before final publication. Use this block:

```python
if plan.team_names_2026:
    module = _core_module("nfl2k5_team_names_2026")
    if module is None:
        raise RuntimeError("The 2026 team-name module is unavailable")
    names_receipt = module.apply_to_image(
        target, progress=lambda message: progress(message, 0, 0))
    receipt["steps"].append({"step": "team_names_2026", **names_receipt})
```

Keep the whole receipt, including the 17 string spans, limits, full intended
names, chosen short forms, hashes, zero growth and replay state. Do not discard
`writes` from the report. The adapter resolves the current outer table through
`OuterImage`, so earlier archive growth can relocate packs. It reads only the
main 593,792-byte resource, validates all fields before mutation, rereads the
source before writing and checks the exact output. On I/O failure discard the
private build copy; multi-span power-loss atomicity is not promised.

Existing saves are never searched, opened or edited by this Build pass. A new
franchise gets the disc's names; an old save supplies its own ROST. Disabling the
option preserves the selected source, including names already on that source;
return to a retail source to restore retail names.

## Build tab option and Gameplay Patches text

In protected `build_panel_qt.py`, near the 2026 season option:

```python
self.team_names_2026_check = self._option(
    g, "team_names_2026", "2026 team names (experimental)",
    "Use modern team names in new disc rosters. Limited name space writes "
    "L.A. Chargers (LA), L Vegas Raiders (LV), L.A. Rams (LAR), and "
    "Washington Cmdrs (WAS); Arizona uses ARI. Existing saves keep their names. "
    "EXPERIMENTAL / UNWITNESSED.")
```

The caption has 30 characters, within the 60-character limit. Connect this
checkbox to the plan, all preset resets, source availability and the Studio
preview refresh. A details view should list `desired` and `written` from the
manifest and explain the name-space limits rather than exposing byte offsets.

If shown on protected `gameplay_patches_panel_qt.py`, add a `PATCHES` row with
key `team_names_2026`, caption `2026 team names`, and exactly this explanatory
text (includes the required words **Retail** and **Patch**):

> Retail: 2004 team names. Patch: modern names in the disc roster, with L.A., L Vegas, LA and Cmdrs short forms where space is limited. Existing saves keep their names. EXPERIMENTAL / UNWITNESSED.

Add `team_names_2026` to `NEEDS_IMAGE`. Route the checkbox to the Build data
field, not the executable dispatcher. Style controls and age shifts get no
Gameplay Patches row, no NEEDS_IMAGE entry and no BuildPlan flag: they are
explicit Rosters edits, available to both disc rosters and save copies.

## Same strings on Team Identity (protected studio_qt.py)

`nfl2k5_text_catalog` already maps main-ROST team fields and the independent
team-label pool; no replacement catalog or display-name dictionary is needed.
The implemented helper `catalog_overrides(catalog, enabled=flag,
value_lookup=underlying_session.text_value)` returns actual planned strings by
the existing **dot-separated** asset IDs. Example:
`nfl2k5.text.rost.5.team.25.nickname -> Cmdrs`. It uses the same manifest as the
byte writer, validates source/staged values, and refuses a manual conflict or a
mixed install. Pass the underlying lookup, not the decorated facade recursively.

In the protected facade `text_value(asset)` adapter, resolve the asset ID,
return this override when present, otherwise return the underlying session's
value. Build computes the same override set for preflight. Invalidate/recompute
the preview when the checkbox, source, project, session Undo/Redo or any text
edit changes. Keep the preview local to the selected source/project. Reset to
source values when off. Never write overrides into the session as 17 individual
text edits: the grouped data pass also owns the normally read-only team-label
pool, and it must preflight all names together.

Refresh Team Identity's displayed city/nickname/abbreviation through the facade
lookup, including the title assembled from city + nickname. Do not use a cached
`RosterTeam.display_name` to mask the short forms. The value shown must equal
what Build writes, not the full `desired` marketing name. Show the intended full
name only in the explanatory preview. If manual editing is offered while this
option is selected, disable edits to these 35 pinned cells or expose the explicit
conflict before Build; do not overwrite manual text silently.

For direct resource consumers, `read_team_identities(resource, enabled=flag)`
returns actual source/planned city, nickname, abbreviation and combined display.
It is tested against both the pure writer and the existing Team Identity catalog.
The separate historical ROST resources remain historical. The 1,115 STRG
allocations have no affected literal names; `[TEAM0NAME]` and similar dynamic
placeholders are retained. No broad search/replace through tutorials, historical
milestones, stadiums, executable strings, logos or recorded commentary is allowed.

## Rosters age tool and save behavior

Implemented in the owned panel: Tools -> `Shift ages to season year...` opens a
preview with explicit source season, target season (2026 by default), optional
shown-list scope, every change and every skip. `Apply age shift` changes memory
as one undo entry. A subsequent Save disc copy / Save Xbox save copy / roster
JSON / CSV export is the user's persistence action. Receipt view/export is in
Tools. The codec uses the existing seven-bit modulo-100 birth-year storage and
checks a 100-year reference window. No fixed-century assumption is reintroduced.

The source picker starts with the loaded reference year or 2004. When a 2026
calendar save still contains a 2004-era roster, the user must explicitly choose
2004 as the source season. An already modern roster should choose 2026 and gets
no shift. A reopened save does not encode this provenance; do not infer it from
player names, years pro or the calendar patch. Repeated same-pair shifts are
suppressed per player in the current session; undo restores their eligibility.

September 1 ages 18..55 qualify. Primary records must carry the NFL-player flag;
non-NFL records, unflagged prospects, templates and invalid/implausible dates
are listed as skipped. February 29 becomes February 28 when needed, explicitly
receipted. Actual birth dates become fictional shifted dates, preserving ages;
years pro, player ratings, team membership, contracts, save calendar and statistics
are not rewritten. A calendar/years-pro progression overhaul is not implied.
The header now prints the current context's September 1 age. Save membership
re-decoding preserves the chosen reference/base year.

## Allowlist and runtime closure (protected release files)

Add exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_roster_ages.py
mod_editor/core/nfl2k5_team_names_2026.py
data/nfl2k5_team_names_2026.json
```

The existing `roster_editor_panel_qt.py`, `nfl2k5_roster_records.py`,
`nfl2k5_text_catalog.py` and `docs/nfl2k5_ratings_and_styles.md` carry updated
behavior/documentation and should retain their existing staged paths. In
`packaging/check_2k5_mod_studio_runtime.py` add imports for
`mod_editor.core.nfl2k5_roster_ages` and
`mod_editor.core.nfl2k5_team_names_2026`, plus a manifest-exists/hash check and
an offscreen construction of `AgeShiftDialog` after loading a synthetic roster.
New runtime dependencies are existing shipped modules: roster_records,
text_catalog, their error/format/parser closure, and
`tools/nfl2k5_playbook_position_recode.py`/`nfl_uniform_color_xiso_direct_patch.py`
through the existing bounded `OuterImage` adapter. Age changes additionally
use only datetime, hashlib and typing. Do not package the private inventory,
retail ROST, test saves, logs or `.scratch/`.

## Capability registry entries

Add capability `nfl2k5.players.team_names_2026`, game `nfl2k5_xbox`, surface
`players_rosters`, classification `offline-writer-proved`; backend module
`mod_editor/core/nfl2k5_team_names_2026.py`, operation `write`, command `null`.
GUI: expose=true, mode=edit, default_enabled=false, reason: "Explicit disc-only
2026 names with fixed-space short forms; existing saves keep their own names."
Runtime: status=`not-tested`, evidence=[], scope="EXPERIMENTAL / UNWITNESSED;
no played or screen witness." Selectors: main ROST outer 5, team indexes
7/8/22/23/25, identity fields plus independent nickname/abbreviation labels;
asset codes and pointers fixed. Constraints: module-pinned manifest, 35 exact
preflight cells, 17 writes, mixed/foreign refusal, zero growth, no STRG edits,
no saves. Evidence paths: new module, data manifest, this report and
`tests/mod_editor/test_nfl2k5_team_names_2026.py`. Validation command:
`python3 tests/mod_editor/test_nfl2k5_team_names_2026.py`. Portme: protected
Build/facade wiring and Noah's new-franchise/scorebug/menu witness list.
Distribution: source-and-schemas-only tooling; user-authored-inputs-and-recipes
mod payload; never-bundle-retail-data game data. No ROST dump is distributable.
Source container: main disc ROST 0x20 wrapper + 0x90F60 body, resource outer 5;
manifest SHA-256 `fea1e37b7fb23887b8231d3e971b5113eeecef1d815001b9032da6b0eac8d13b`.

Add capability `nfl2k5.players.age_shift`, same game/surface/classification;
backend `mod_editor/core/nfl2k5_roster_ages.py`, operation=write, command=null;
GUI expose=true/mode=edit/default_enabled=false (explicit preview and Apply).
Runtime not-tested, empty runtime evidence, no gameplay claim. Selectors are
(pool,index) from a chosen RosterDocument plus explicit source and target season.
Constraints and distribution follow the preceding age/save section. Evidence:
new age module, owned panel, `tests/mod_editor/test_rosters_data.py`,
`tests/mod_editor/test_rosters_data_qt.py`, `ASTRA_ROSTERS_DATA_REPORT.md`.
Validation: `QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_rosters_data_qt.py`.
Source container: version 17 disc ROST or version 0 roster/franchise save,
field-relative 0x54 records, title's existing signed-save copy writer.
Portme: Noah's signed-copy reopen and 2026-franchise witness. Registry changes
should not re-enable the older narrow disc_roster provider's unrelated writes.
# r62 gameplay levers handoff, 2026-09-05

This section supersedes older coverage/acceleration assumptions for these four
controls. Implementation and tests are in `ASTRA_GAMEPLAY_LEVERS_REPORT.md`.
The protected dispatcher, BuildPlan, Gameplay panels, release allowlist, runtime
checker, and reservation JSON were deliberately left for Claude. The feature's
own `throw_tuning_panel_qt.py` already offers flatter flight, a numerical preview
and a flight curve, with a working transactional copy action.

All four new switches are **EXPERIMENTAL / UNWITNESSED** and default False in
`softdrink_basic`, `softdrink_advanced`, and `softdrink_experimental`. Advanced
and Experimental already select `penalties="nfl"`, which includes the existing
Chop Block repair; report its actual applied state even with the new independent
switch False. No played witness or automatic preset promotion is authorized by
these implementation proofs.

## Dispatcher and the four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import:

```python
from . import nfl2k5_coverage_slider as coverage_slider_patch
from . import nfl2k5_scramble_tuning as scramble_tuning_patch
from . import nfl2k5_throw_arc as flatter_flight_patch
```

`nfl2k5_throw_arc` has literal pins and defers all access to the dispatcher's
definitions until call time, so this import does not require a cyclic-import
workaround. The shared runtime dependency is `nfl2k5_gameplay_lever.py`.

Add Boolean kwargs, default False, to `_apply_all`, `write_xbe_copy`, and
`write_image_copy`, and forward them through every call, including deferred
scorebug/grown-XBE passes:

```python
coverage_slider=False, scramble_tuning=False,
flatter_deep_ball=False, chop_block_toggle=False
```

Validate all four with `type(value) is bool` before copying or mutation. Add
them to both writers' `nothing requested` checks. Add an adapter for the
existing penalties module's independent entry points:

```python
class _chop_block_adapter:
    status = staticmethod(penalties_patch.chop_block_status)
    apply = staticmethod(penalties_patch.apply_chop_block)
```

Add these ordinary `_apply_all` tuple entries beside penalties (the complete
rate profile and the independent repair commute):

```python
(chop_block_toggle, _chop_block_adapter,
 "chop_block_toggle_patch", "experimental Chop Block toggle repair"),
(flatter_deep_ball, flatter_flight_patch,
 "flatter_deep_ball_patch", "experimental flatter deep flight"),
```

Add these entries in the **final owner tuple, after allocation**:

```python
(coverage_slider, coverage_slider_patch,
 "coverage_slider_patch", "experimental Coverage slider response"),
(scramble_tuning, scramble_tuning_patch,
 "scramble_tuning_patch", "experimental slow-QB acceleration"),
```

Extend `_selected_space_requests`, `_xbe_space_adapter`, the inherited
`_defensive_try_adapter` construction, and every request-union caller with the
two new Boolean arguments. Append the selected modules' `REQUESTS` to the
same initial union used for kickoff, scorebug, Momentum, defensive tries and
zone drop. Either switch implies the allocator. Extend its `flag` condition
in the final tuple. Do not call a new owner on an already-grown image that
was sealed without its request. Do not grow early in the ordinary pass if
Build still has roster/layout/scorebug work to do. Mirror the existing
deferred-owner routing and reserve the whole union before the first growth.

The allocator change is already implemented: r62 owners sort after every
beta-61 owner, preserving its existing named addresses. Requests add 16 and
160 immutable RX bytes, zero RW bytes, and no page-count change. The full
union assigns Coverage to `0x014D99A0` and scramble to `0x014D99B0`; these
addresses are receipts, not constants to hardcode. Smaller unions differ.

Insert the following in **all four status dictionaries**: `read_xbe(payload)`,
`read_image(payload)`, `write_xbe_copy(result)`, `write_image_copy(after)`.
Use the variable shown for each function; the snippet uses `payload`:

```python
"coverage_slider": coverage_slider_patch.status(payload),
"scramble_tuning": scramble_tuning_patch.status(payload),
"flatter_deep_ball": flatter_flight_patch.status(payload),
"chop_block_toggle": penalties_patch.chop_block_status(payload),
"chop_block_evidence": penalties_patch.chop_block_evidence(payload),
```

Include full subreceipts on new writes and explicit replay receipts on
already-applied input. Add these keys to `mod_build.inspect`, availability,
step summaries and output receipt selection. A foreign flatter-flight status
on a known high-arc/realistic source means the original source is required
for this particular option; it does not invalidate unrelated game features.

## Flight ordering and read-back

The flat module's `apply(payload)` changes **only** the speed table. It never
silently changes the arm-distance settings. Selecting the new option in Build
sets `throw=True`, uses the existing 80-yard ceiling initially, and clears
`arc`, `realistic_flight`, and `arc_by_distance`. Later explicit distance
changes remain independent. The workspace already does this normalization.

Before mutation, reject `flatter_deep_ball` together with a nonzero arc,
realistic flight, or the relocated high-arc band. Also require the original
payload's `flatter_flight_patch.status` to be retail or applied: changing an
unused in-place table under a relocated reader must never be a successful
no-op. In `_apply_all`, when flat is requested, remove `lobspeed` from `wanted`
before the ordinary distance pass. Then the flat tuple entry applies the
pinned speed edit separately, with its exact receipt. Do not overwrite an
already-flat speed table with a retail speed table during replay.

For replay of matching distance tables, run `plan_patch` only when
`wanted and _curves_differ(payload, wanted)`. The current
`or not arc_table` condition forces an unnecessary write and rejects the
already-matching case. Keep all count/coordinate validation and refusal checks.

On reading a flat source, retain its ceiling and report the flight choice
separately; do not infer a tall arc from it. The feature module's `read_any`
already normalizes this for the workspace. The actual speed points are
`FLAT_LOBSPEED`. Use them for each writer's preview and in Build summaries.
`arc_table` in read reports is a dictionary with a `state` member, while write
receipts use a string; do not compare the whole read dictionary with `retail`.
The workspace now also previews the actual relocated table when that existing
mode is selected, fixing its old numerical-table mismatch.

## BuildPlan, Gameplay, and Build controls

Add these fields to protected `BuildPlan`, all default False:

```python
coverage_slider: bool = False
scramble_tuning: bool = False
flatter_deep_ball: bool = False
chop_block_toggle: bool = False
```

Include them in selection/has-work predicates, preset resets, availability,
inspect results, persistence/plan serialization, worker kwargs, the early XBE
pass for flat/Chop, and the final grown-owner pass for Coverage/scramble.
Extend the scorebug `extra_requests` path and final `_apply_all` call with
Coverage/scramble; merely forwarding the first writer call is insufficient.
In every preset, add explicit False values. Preserve the selected existing
penalty profile. Do not disable the independent Chop checkbox by pretending
the bundled repair is still retail.

Use these Gameplay Patches `PATCHES` entries. The imported help constants
already contain both required words **Retail** and **Patch**:

```python
("coverage_slider", "Coverage slider response (experimental)", coverage_slider_patch.HELP_TEXT),
("scramble_tuning", "Slow-QB acceleration (experimental)", scramble_tuning_patch.HELP_TEXT),
("chop_block_toggle", "Repair Chop Block toggle (experimental)", penalties_patch.CHOP_BLOCK_HELP),
("flatter_deep_ball", "Flatter deep flight (experimental)",
 "EXPERIMENTAL / UNWITNESSED. Retail deep lobs use 20 yards per second. "
 "Patch: deep lobs use 25, keeping speeds through 35 yards and the selected "
 "distance curve. At 80 yards the equal-height preview is 3.20 seconds and "
 "a 13.7-yard apex. Choose one flight option and start from the original source."),
```

For the **Gameplay tab explanation**, place `coverage_slider_patch.HELP_TEXT`
beside Coverage. It explicitly explains 0, 50 and 100. This changes a defender's
direct ball-reaction contribution; it is not a catch/interception multiplier
and zero does not remove context-driven reactions. Keep the Human and CPU
slider settings in their existing settings writer, not the runtime table's
index order. Add `scramble_tuning_patch.HELP_TEXT` beside its option and
`penalties_patch.CHOP_BLOCK_HELP` beside the independent toggle repair.
Replace any remaining claim that retail has no acceleration with the beta-61
correction. The owned Throw workspace tooltip is already corrected.

`NEEDS_IMAGE`: add `coverage_slider` and `scramble_tuning`, matching the
existing product policy for grown owners. Do not add `flatter_deep_ball` or
`chop_block_toggle`; they also work on a bare default.xbe. Their source gating
must use the relevant status, not unrelated penalty profile state.

Build `_option` captions, each under 60 characters:

| Key | Caption |
| --- | --- |
| coverage_slider | Coverage slider response (experimental) |
| scramble_tuning | Slow-QB acceleration (experimental) |
| flatter_deep_ball | Flatter deep flight (experimental) |
| chop_block_toggle | Repair Chop Block toggle (experimental) |

Wire all four checkboxes into `_make_plan`, reset, presets, source status
gating, selected-change text and source-reload behavior. Attach the same help
text. No new Studio navigation item is required: the Throw workspace exists
and its own panel is already changed. No additional GUI panel was edited here.

## Allowlist, runtime closure, capability rows and oracle

Add exactly these new runtime allowlist lines; the edited existing modules
and panel are already listed:

```text
mod_editor/core/nfl2k5_gameplay_lever.py
mod_editor/core/nfl2k5_coverage_slider.py
mod_editor/core/nfl2k5_scramble_tuning.py
mod_editor/core/nfl2k5_throw_arc.py
```

Add explicit runtime-closure imports in the protected staged checker:

```text
mod_editor.core.nfl2k5_gameplay_lever
mod_editor.core.nfl2k5_coverage_slider
mod_editor.core.nfl2k5_scramble_tuning
mod_editor.core.nfl2k5_throw_arc
```

Retain existing imports of `nfl2k5_penalties`, `nfl2k5_xbe_space`,
`nfl2k5_cave_oracle`, `nfl2k5_bump_strength`, `nfl2k5_rdata_sites`,
`nfl2k5_draft_ai` (the small assembler), `platform_compat`, and the Throw panel.
No Capstone/Unicorn requirement is added to runtime patch application; only
instruction tests need them. Include new modules in the gameplay provider
closure, then regenerate changed source pins in `providers.py` and the
protected runtime checker using the existing repin workflow after integration.
Do not make stale fingerprints silently acceptable.

Four schema-valid complete capability objects are delivered in
`docs/mod_editor/nfl2k5_gameplay_levers_capabilities.json`. Merge by ID into
`mod_editor/capabilities/registry.v1.json`, preserving experimental runtime
status and the witness limits. All use the existing
`gameplay_tuning_sliders` surface. The handoff JSON is review evidence, not an
additional runtime asset to allowlist.

The manifest **generator** already imports/observes the new modules, appends
their requests, observes the independent Chop entry point, and records flat
flight as an alternative data-table probe when the experimental stack uses
the mutually exclusive high-arc band. Its alternative probe does not change
the final stack's chosen flight. Claude must regenerate the protected
`data/nfl2k5_cave_reservations.json` after all branches are integrated, with:

```text
python3 tools/nfl2k5_cave_oracle.py manifest <retail-default.xbe> --xiso <retail.xiso.iso> --work-dir <writable-disposable-space> --json data/nfl2k5_cave_reservations.json
```

Both executable gates now include all four levers and the complete existing
owner union in both orders. The recorder has a focused new test. The on-disk
manifest remains intentionally unchanged and its source fingerprints will
remain stale until Claude regenerates it; this is not a passed fresh-manifest
or staged-release claim.
# r62 hires pack handoff, 2026-09-05

This is an archive build pass, EXPERIMENTAL / UNWITNESSED. The two new core
modules and headless API are implemented. Protected Build, Studio, release
and runtime files remain untouched. The research memo explicitly says the
resource-only pilot needs no XBE dispatcher entry or cave reservation.
The existing music archive writer grows/shrinks and remaps the collection;
its publication transaction is now shared with music. Both existing provider
hash pins were refreshed in the unprotected `providers.py`.

## BuildPlan and execution

Add these fields to protected `mod_editor/core/mod_build.py`:

```python
hires_pack: bool = False
hires_folder: str = ""
hires_scale: int = 2
hires_target: str = "xemu-64"
```

**Basic / advanced (the existing `modern` key) / experimental: all explicitly
set `hires_pack=False`. Never enable it in a preset.** Preserve the folder
choice but do not scan/import/apply anything while disabled. The ordinary
default build therefore retains native texture sizes. Do not add it to
`wants_xbe_patch`, imply `xbe_space`, select an allocator owner, or modify
the cave manifest. `hires_scale` accepts exact integers 1 or 2. The only
enabled target is `xemu-64`; `xemu-128` must remain unavailable with the
explanation "128 MiB support has not been proved".

Add `availability()["hires_pack"]` for importability of
`nfl2k5_hires_pack`, `nfl2k5_hires_texture`, `nfl2k5_music_archive` and
`nfl2k5_music_banks`. When selected, preflight the folder and selected
resources before the ordinary build writes. Use
`hires.inspect_image(source, plan.hires_folder, scale=plan.hires_scale,
target=plan.hires_target)` for exact art-relative preflight. Retain exceptions
as actionable failures, not implicit resize or omission. Native texture edits
on the same target conflict. In particular, if the folder selects `scorebug`,
reject simultaneous `scorebug` / `scorebug_runtime` / reference-frame imports
before the first write. Other pilot targets can accompany those options.

Run the hires pass **last**, after all ordinary fixed-span resource writers,
paired scorebug resources, XBE patches and music-library compilation. Resolve
against that current private image by identity. In `_build_into`, after the
music-library block and before returning the receipt:

```python
if plan.hires_pack:
    hires = _core_module("nfl2k5_hires_pack")
    with tempfile.TemporaryDirectory(prefix=".hires-", dir=target.parent) as folder:
        destination = Path(folder).resolve() / "image.iso"
        rec = hires.build_image(
            target, destination, plan.hires_folder,
            scale=plan.hires_scale, target=plan.hires_target, progress=progress)
        os.replace(destination, target)
    receipt["steps"].append({"step": "hires_pack", **rec})
```

The outer Build transaction still publishes only after all passes succeed.
Do not call a fixed retail-offset writer after this pass. The existing final
`inspect(target, ...)` includes legacy fixed-offset resource inspectors: take
their result before the final remap and carry it as pre-remap inspection,
then set the final hires state from `rec["verification"]` and report the
actual final image hash/size. Alternatively migrate each such inspector to
identity-based traversal before calling it on the grown archive. Never label
a stale-offset failure as a proved retail/applied final state. The hires
verification already independently hashes all 4,323 outers and the XBE.
Add `hires_pack` to Build inspection/results without hiding an
`authored-unverified`, mixed or foreign status behind a boolean. For a plain
XBE source report "requires image".

## Dispatcher and the four status dictionaries

| Protected surface | Exact change for this resource-only pilot |
| --- | --- |
| `nfl2k5_throw_tuning._apply_all` tuple | **None.** It accepts XBE bytes; hires accepts TXTRs or a disc copy. |
| `_apply_all` keyword argument | **None.** Do not forward `hires_pack` into this dispatcher. |
| `read_xbe` status dict | **None.** No executable hires state exists. |
| `read_image` status dict | **None.** Put the archive result in `mod_build.inspect`, outside XBE status. |
| `write_xbe_copy` status dict | **None.** A standalone executable cannot contain the pack. |
| `write_image_copy` status dict | **None.** The Build archive transaction owns the resource result. |

The unchanged XBE memory/cave gates were run with their existing complete
owner set in both orders. There is no new executable owner to compose into
their `setUpClass` chains. Do not create a fake XBE patch just to populate
these surfaces.

## Build controls, Gameplay Patches and All Textures

In protected `build_panel_qt.py` add the opt-in checkbox through `_option`:

```python
self.hires_pack_check = self._option(
    layout, "hires_pack", "Hi-res pack (experimental)",
    "Retail: textures keep their original sizes. Patch: selected artwork in your "
    "Hi-res folder can use 2x detail. Experimental and unwitnessed in game. "
    "xemu rendering scale is set separately.", badge="EXPERIMENTAL")
```

Caption is 25 characters, below 60. Add a folder chooser, `2x detail` / `Original
size` output selection and a disabled 128 MiB target with the explanation
above. The second choice maps to scale 1 and keeps the option explicitly on;
turning it off does not undo an already-authored source disc. Include all
four fields in option/state maps, plan creation, dirty detection, reset,
summary, source/image availability and preset reset. Show the selected
asset names and exact dimensions, P8 color loss, selected memory delta,
logical archive growth and physical image growth in the build receipt.

`Gameplay Patches.PATCHES`: **no active tuple**. `NEEDS_IMAGE`: **no added key**,
because that panel routes executable patches and has no hires row. The
Retail/Patch text above is the exact information text if integration adds a
read-only link from that panel to Build. Such a link must use the Build
controller, never the XBE writer. The Build checkbox itself requires a disc.

**All Textures decision:** no new control belongs in its native replacement
flow for this pilot. Its existing master export supplies full-resolution
authoring sources, while the requested folder/scale/memory selection belongs
in Build. Its fixed-span import promises remain intact. Therefore no GUI
panel was edited. Protected `studio_qt.py` should route the four Build fields
through the existing plan/controller operation lock. No automatic emulator
launch or master-file conversion is implied.

## Getting Started insertion

Paste the following into protected-integration owner
`docs/mod_editor/2k5_mod_studio_getting_started.md` near the Build artwork
instructions, and link `nfl2k5_hires_pack.md` for the complete API/limits:

> **Hi-res pack (experimental, unwitnessed).** This optional Build choice is
> off in every preset. Put a `Hi-res` folder beside your project, then choose
> that folder in Build. Use `scorebug.png` at 128 x 128, `field_logo.png` at
> 512 x 512, and `helmet.png` at 512 x 512. Missing files leave their targets
> unselected. The field logo is created-team logo 33 in dry weather; the
> helmet is uniform `00H0.IFF`'s Standard/A `helmet00`. These are specific
> pilot assets, not all teams. An NFL 2K5 `.2ktexmaster` with the same basename
> can replace each PNG; choose one extension per target. Keep the atlas
> arrangement and seams. `2x detail` installs larger textures. `Original
> size` builds your retained artwork at the native dimensions. Keep the same
> folder for replay or downscaling, and use your original disc to change art
> or restore retail bytes. 128 MiB support is unavailable. Set xemu's
> rendering resolution separately; this choice has no played witness yet.

The exact getting-started page was left for integration as the task requests
"(WIRING)"; the complete standalone guide is delivered now.

## Release allowance, runtime closure and capability

Add these exact lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_hires_pack.py
mod_editor/core/nfl2k5_hires_texture.py
docs/mod_editor/nfl2k5_hires_pack.md
```

No new third-party dependency: Pillow is already shipped. In protected
`packaging/check_2k5_mod_studio_runtime.py`, explicitly import both new dotted
modules, inspect all three `ASSETS`, assert their scale-2 video total is
718336, and assert `status({}, missing_folder) == "foreign"`. Keep imports
closed over these existing modules/tools (including legacy bare tool imports):

```text
mod_editor.core.texture_master
mod_editor.core.json_stream
mod_editor.core.errors
mod_editor.core.nfl2k5_bump_strength
mod_editor.core.nfl2k5_music_archive
mod_editor.core.nfl2k5_music_banks
mod_editor.core.nfl2k5_music_metadata
mod_editor.core.nfl2k5_music_storage
mod_editor.core.nfl2k5_depth_chart_storage
mod_editor.core.nfl2k5_ausb_fixed_slots
mod_editor.core.platform_compat
tools.nfl_txtr / nfl_txtr
tools.nfl_tset_png_import / nfl_tset_png_import
tools.nfl_uniform_inventory / nfl_uniform_inventory
tools.nfl_outer / nfl_outer
tools.nfl2k5_commentary_swap
tools.nfl_uniform_color_xiso_direct_patch
tools.xbox_ima_encoder
PIL.Image
```

The normal transitive closure of those existing helpers remains required;
Capstone, Unicorn, the Ghidra corpus and private texture inventories are not
new runtime dependencies. `tools/nfl2k5_hires_consumer_audit.py` and
`reports/hires_pack_consumers.v1.json` are developer evidence, not runtime
inputs; do not add game spans, scratch PNGs, ISO copies or the brief to the
release. The two existing music provider pins were updated, with no pin
widened. Run `packaging/repin.py` again after protected integration.

Merge the sole object in
`docs/mod_editor/nfl2k5_hires_pack_capability.json` into the canonical registry:
ID `nfl2k5.textures.hires_pack`, existing `uniforms` surface, classification
`offline-writer-proved`, runtime `not-tested`, GUI default false. This is a
new archive-size capability, not a relaxation of `all_p8`. No schema surface
or patch-address reservation is added. Update count/findings expectations.
Run the two new standalone suites, music banks, texture masters, both XBE
gates, the staged import check and the protected full Build transaction tests.

## r62 music playlist: protected integration handoff

**EXPERIMENTAL / UNWITNESSED; every preset leaves this off.** Backend, assembly,
Music page, three standalone backend suites, both owner unions and manifest
recorder integration are implemented here. The protected files below are not
edited. `ASTRA_MUSIC_PLAYLIST_REPORT.md` and
`reports/music_playlist_contexts.v1.json` distinguish native instruction proofs
from unresolved individual screen routes. Do not advertise "all modes".

### BuildPlan, source validation, order and receipt
# r62 abilities runtime handoff, 2026-09-05

This section is the complete protected-file handoff for abilities rules v1.
`ASTRA_ABILITIES_RUNTIME_REPORT.md` defines the precise experimental contract
and Noah's pending witnesses. The backend, assembler/template, standalone
proofs, complete gate union and manifest generator are implemented here.
No protected product source or checked-in reservation manifest was edited.

## BuildPlan, defaults, validation and deferred ownership

In `mod_editor/core/mod_build.py`, add:

```python
music_shuffle: bool = False
music_shuffle_selection: dict | None = None  # MusicPanel.playlist_options(), schema 1
```

Set `music_shuffle=False` and `music_shuffle_selection=None` explicitly in all
three Basic / Advanced / Experimental presets (the actual `softdrink_*` keys).
Applying a preset must not discard personal Music page choices. Reset clears
the enable flag; retain the choices until the user changes/resets the library.
Include `music_shuffle` in `wants_xbe_patch`, validation, inspection,
availability, selected-key forwarding, receipt and plan serialization. Reject
non-Boolean flags. Keep feature state separate from a selected checkbox.

A selected build needs an image and validated AUSB descriptors. Construct
`playlist.from_options(plan.music_shuffle_selection)` when provided, otherwise
`playlist.Selection()` (66 core songs). Validate the source with
`playlist.validate_source(selected, counts)`, where `counts` is obtained from
the existing bounded `Nfl2k5AudioDisc` descriptor reader. For a simultaneous
bank rebuild, validate against that rebuild's planned **final** descriptor
counts, and validate again on the staged rebuilt image before publication.
Do not infer descriptor counts from 200 metadata titles. The page supports the
66 original songs plus ten established background beds. The backend caps
custom selections at 100 records under this reservation and can address added
bank indices when their descriptors validate. It does not automatically select
an entire grown 200-song library.

Add playlist REQUESTS to the **complete** allocator union before any grown
owner runs; include both dormant installed owners and newly selected owners as
required by the existing immutable-directory contract. Realize with
`space.apply(payload, requests, scaleout=True)`. Pass the planned playlist to
the final grown-owner pass, after the resource/scorebug-dependent passes have
resolved their extents. The later music bank writer preserves these hooks and
allocated sections. Never add the playlist request to an already sealed,
different union; rebuild from its supported base. Combined music/scorebug
builds must defer playlist allocation along with the other grown owners.

Store `music_shuffle_patch` (exact backend receipt), `music_shuffle_state`
(`read_settings`), source/result hashes and final enabled records in the Build
receipt. Use `nfl2k5_depth_chart_storage.write_image_xbe` and the existing staged
copy/rollback transaction; do not introduce an ISO/pack `read_bytes` path.
A different installed selection refuses and requires a rebuild from base.
Unchecked/off preserves an already patched source; it does not uninstall.

### Dispatcher tuple, kwargs and all four status dictionaries

In protected `nfl2k5_throw_tuning.py` import:

```python
from . import nfl2k5_music_playlist as music_playlist_patch
```

Extend `_apply_all`, `write_xbe_copy`, `write_image_copy`, their forwarded calls
and `write_copy`'s accepted forwarded options with:

```python
music_shuffle: bool = False,
music_shuffle_selection: music_playlist_patch.Selection | None = None,
```

The Build layer converts the serialized page document into `Selection` first;
no Qt import belongs in the dispatcher. Extend `_selected_space_requests`,
`_xbe_space_adapter` and `_defensive_try_adapter` propagation with the flag and
`+ (music_playlist_patch.REQUESTS if music_shuffle else ())`. Include the flag
in the existing grown-allocation and "something selected" predicates. Keep
that union identical in every early/deferred allocation branch. Add this tuple
to the final grown-owner dispatcher **after** the allocator adapter:

```python
(music_shuffle, music_shuffle_selection or music_playlist_patch.Selection(),
 "music_shuffle_patch", "experimental music playlist"),
```

`Selection.status` returns foreign for a differently configured installed
playlist; it must not be treated as an already-applied compatible patch.
The module's aggregate `status(payload)` validates arbitrary installed choices.
For standalone expert byte-API replay where choices are deliberately omitted,
use `music_playlist_patch.apply(payload)` to retain the installed selection.

Add both exact entries to **each** of these four returned status dictionaries:
`read_xbe`, `read_image`, `write_xbe_copy`, `write_image_copy`:

```python
"music_shuffle": music_playlist_patch.status(payload),
"music_shuffle_state": music_playlist_patch.read_settings(payload),
```

Use the actual executable byte variable in each dictionary (original for read,
final/patched for write); never return input state after a successful write.
The state includes `all_modes_proved=False` and `runtime_witnessed=False`.
Preserve existing `music_policy`, `music_unlock`, `music_userlist` and their
four-dictionary entries; they compose in either order. Shuffle controls the
shared background while enabled regardless of the older direct-bank policy.

### Music page, Gameplay Patches and Build tab

`mod_editor/gui/music_panel_qt.py` is already edited. It adds a Playlist page,
`playlist_changed(dict)`, `playlist_options()` and
`set_playlist_options(dict)`, individual checks, outtake/bed switches, clear/all,
zero/one-song explanations and atomic Save/Open choices. Source/operation locks
cover the page. Existing Recordings controls and policy signals retain their
API. No preview process starts when playlist choices change.

In protected `studio_qt.py`, connect `playlist_changed` to the shared Build
plan's `music_shuffle` flag and `music_shuffle_selection` document, mark the
project dirty, and restore via `set_playlist_options` on project/source open.
Use signal blocking/one controller transaction to avoid a feedback loop when
Build changes the same option. Persist the document with the project's Build
settings. The Music page's local choices JSON round-trip works independently;
the old dedicated `.2k5music` audio-project schema is unchanged. Never silently
claim its old format now persists these choices. Standalone "Build music copy"
and "Export .2k5patch" on Recordings retain their fixed-slot scope; route the
playlist's executable changes through the main Build transaction.

Add a protected Gameplay Patches `PATCHES` row keyed `music_shuffle` with title
**"Shared music shuffle (experimental)"** and this exact explanation:

> Retail: each screen chooses its own music. Patch: selected menu and jukebox
> recordings shuffle in the shared menu, Crib and game background player.
> Loading and shows keep their timed music. Background disc and HDD playlists
> are replaced. Individual screen coverage is still untested in game.

Add `"music_shuffle"` to `NEEDS_IMAGE` because a build must validate source bank
counts. Pure backend XBE proofs do not replace that image preflight.

In protected `build_panel_qt.py`, add through `_option`:

```python
self.music_shuffle_check = self._option(
    layout, "music_shuffle", "Shuffle songs in menus, Crib and games",
    "Experimental, not yet tested in game. Uses the Music tab playlist. "
    "Loading and shows keep their timed music.", badge="EXPERIMENTAL")
```

Caption: 38 characters, below 60. Add it to all option/state maps, source
availability, reset, dirty state, summary, preset handling and plan assembly.
Bind it to the Music page's enable flag; retain its detailed song choices.
Do not use "Across all modes". Draft presentation routing, individual franchise
screens, replay routing and played audio remain open witness gates.

### Release allowance, closure, capability and cave manifest

Add exact new runtime allowance lines in protected
`packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_music_playlist.py
mod_editor/core/nfl2k5_music_playlist_code.py
reports/music_playlist_contexts.v1.json
```

The existing `mod_editor/gui/music_panel_qt.py` allowance stays. Assembly source
and generator are development reproducibility tools, not runtime dependencies:
`tools/nfl2k5_music_playlist.S`, `tools/nfl2k5_music_playlist_assemble.py`.
No scratch artifacts or original game/audio files belong in a release.

In protected `packaging/check_2k5_mod_studio_runtime.py`, import the two new core
modules and the existing Music panel. Verify default 66 / outtakes-off 54 /
beds-on 76 selections, import the generated template, and instantiate the page
offscreen without loading game evidence. Preserve runtime closure for:

```text
mod_editor.core.nfl2k5_xbe_space
mod_editor.core.nfl2k5_bump_strength
mod_editor.core.nfl2k5_cave_oracle
mod_editor.core.nfl2k5_music_policy
mod_editor.core.nfl2k5_music_catalog
mod_editor.core.nfl2k5_music_metadata
mod_editor.core.nfl2k5_music_storage
mod_editor.core.nfl2k5_depth_chart_storage
mod_editor.core.platform_compat
mod_editor.studio.music_service
```

No GNU assembler, Capstone, Unicorn or private research corpus is needed for
normal module import or the playlist writer. They are developer proof tools.

Merge the ready registry object in
`docs/mod_editor/nfl2k5_music_playlist_capability.json` into
`mod_editor/capabilities/registry.v1.json`: ID `nfl2k5.music.playlist`, existing
`audio` surface, `offline-writer-proved`, runtime `not-tested`, default false.
Update registry count/findings expectations during integration. This handoff
follows the brief's explicit "capability via WIRING" boundary.

The gate union, allocator allocation-evidence default union and manifest
builder owner/request/wrapper/probe lists are already updated. Regenerate
protected `data/nfl2k5_cave_reservations.json` only through Claude's coordinated
`tools/nfl2k5_cave_oracle.py manifest` run after protected integration, then repin
packaging source hashes using the existing release workflow. The new standalone
manifest test observes the real writer and validates every hook and full
RX/RW/RO child without rewriting a disc or the protected manifest.
# r62 native Practice Squad screen handoff, 2026-09-05

`nfl2k5_practice_squad_screen` is implemented and EXPERIMENTAL / UNWITNESSED.
Protected product files are unchanged. This section supersedes the old
PS-section statements that the management destination is deferred. The
transaction, Free Practice and Schedule-first prerequisites remain required.
CPU poaching/protection stay off and have no option in this delivery.

## BuildPlan, presets and allocation order

In `mod_editor/core/mod_build.py`, add `practice_squad_screen: bool = False`.
Explicitly keep it **False in basic, advanced (`modern`) and experimental**.
Add it to availability, inspection, option persistence/serialization, selection
and has-work predicates, worker arguments, summary and step receipts. Enabling
it implies `practice_squad=True`, `franchise_practice=True` and `xbe_space=True`;
the existing conjunction installs `practice_reserves`. Include the implication
in both Build and bare writer normalization, before the first mutation.

Include `screen.REQUESTS` in `_selected_space_requests` and every selected
request union, including the defensive-try allocator adapter and scorebug
`extra_requests` path. Reserve the whole union before installing any grown
owner. Use v3 (`space.apply(payload, requests, scaleout=True)`). The feature
requests exactly `("nfl2k5_practice_squad_screen", "code", 4096, 16)` and
`("nfl2k5_practice_squad_screen", "data", 256, 16)`. Immutable code, clones,
menu and strings fit within RX; no separate RO allocation or extra RW is needed.
The committed beta-62 budget fixture already has both exact rows.

Defer the screen until the **final grown-owner pass**, after SPECIAL/resource
work and `practice_reserves`. Include its request when paired scorebug realizes
the allocator, and include the flag in the final `_apply_all` call after that
paired pass. A pre-existing sealed request set without this owner must refuse
and require rebuilding from the original source. No late request insertion or
address relocation is permitted. All presets stay off even though enabling
this option automatically selects its prerequisites.

## Dispatcher tuple, keyword and all four dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py` import:

```python
from . import nfl2k5_practice_squad_screen as practice_squad_screen_patch
```

Add `practice_squad_screen: bool = False` to `_apply_all`, `write_xbe_copy`,
`write_image_copy`, allocator adapters and `_selected_space_requests`.
Forward it through every writer/Build dispatch, including deferred scorebug
calls. Include it in the writer's has-work checks. At dispatcher entry,
normalize its prerequisites before ordinary patch processing.

Add this exact tuple in the **final owners** loop, after the allocator entry
and the already-executed `practice_reserves` block:

```python
(practice_squad_screen, practice_squad_screen_patch,
 "practice_squad_screen_patch", "experimental Practice Squad screen"),
```

Preserve its complete receipt, including limits, allocation, labels, hashes,
`runtime_witnessed=False`, poaching/protection and replay `changed_bytes=0`.
`FranchisePractice.status/apply` already recognize the exact new table through
its sealed owner validator, so do not project or rewrite the old pointer in
the dispatcher. Free Practice replay must leave the new pointer intact.

Add the following key in **each** dictionary:

| Function | Entry |
| --- | --- |
| `read_xbe` | `"practice_squad_screen": practice_squad_screen_patch.status(payload),` |
| `read_image` | `"practice_squad_screen": practice_squad_screen_patch.status(payload),` |
| `write_xbe_copy` | `"practice_squad_screen": practice_squad_screen_patch.status(result),` |
| `write_image_copy` | `"practice_squad_screen": practice_squad_screen_patch.status(after),` |

Expose the same key in `mod_build.inspect`, availability and final output
status. Missing prerequisites are an error, never a successful omitted step.

## Gameplay Patches, Build and Studio

Import the module in `gameplay_patches_panel_qt.py` and add to `PATCHES`:

```python
("practice_squad_screen", "Practice Squad screen (experimental)",
 practice_squad_screen_patch.HELP_TEXT),
```

`HELP_TEXT` contains **Retail** and **Patch** and explicitly says experimental
and unwitnessed. Add `practice_squad_screen` to `NEEDS_IMAGE`, matching product
policy for grown owners. Its pure XBE API remains available for developer use.

In `build_panel_qt.py`, add the opt-in `_option` with the 36-character caption
**`Practice Squad screen (experimental)`**, the same help, and the existing
EXPERIMENTAL badge. Connect it to `_make_plan`, preset/reset, source-reload,
source availability/status, persistence, dirty detection and selected-change
text. Studio forwards the plan through the existing Build operation lock;
no new GUI panel or top-level navigation item is needed. Show prerequisite
selection in the build summary. Never report an in-game witness from these
CPU tests.

## Allowlist, runtime closure, capability and manifest

Add these exact runtime paths to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_practice_squad_screen.py
mod_editor/core/nfl2k5_practice_squad_screen_code.py
```

Explicitly import both in protected
`packaging/check_2k5_mod_studio_runtime.py`. Retain closure imports for
`nfl2k5_practice_squad`, `nfl2k5_practice_squad_runtime`,
`nfl2k5_franchise_practice`, `nfl2k5_practice_reserves`,
`nfl2k5_xbe_space`, `nfl2k5_bump_strength`, `nfl2k5_rdata_sites`,
`nfl2k5_cave_oracle`, `nfl2k5_draft_ai` and their existing transitive dependencies.
The Franchise Practice module now lazily imports the screen validator only
when a pointer needs delegation recognition, so the new module must ship even
when the Build option defaults off. Add both files to the gameplay provider
closure and repin provider/runtime source hashes after integration.
GNU as, Capstone, Unicorn, the `.S` file, the assembler script and test fixtures
are development-only dependencies; application uses the checked-in byte
and relocation template with the Python standard library.

Merge the complete schema-valid object in
`docs/mod_editor/nfl2k5_practice_squad_screen_capability.json` by ID
`nfl2k5.franchise.practice_squad_screen` into the canonical capability registry.
It uses the existing `menus` surface, classification `offline-writer-proved`,
runtime `not-tested`, GUI explicit opt-in, default false. It requires no new
surface enum. Update registry count/coverage assertions during integration.
The handoff JSON/report are review artifacts, not runtime game assets.

The manifest builder and both executable gates already include the owner.
The exact four-byte pointer is intentionally delegated from Franchise
Practice; it is not free storage. The full menu/code/state capacities are
allocator children, never retail caves. Claude must regenerate protected
`data/nfl2k5_cave_reservations.json` after integration with the existing
`tools/nfl2k5_cave_oracle.py manifest` command. A scratch manifest can be tested
with `NFL2K5_CAVE_MANIFEST`; production fingerprints must never be weakened.
Run both new standalone suites, Franchise Practice, practice reserves and
both complete XBE gates, then the protected Build/closure tests after wiring.
abilities: bool = False
abilities_off_week: int | None = None
```

Add `"abilities": False, "abilities_off_week": None` to **all three** presets:
`softdrink_basic`, `softdrink_advanced`, `softdrink_experimental`. None is the
only default; enabling the runtime does not choose a week or assign flags.
The API week is the **zero-based existing regular-season row 0..17**. UI week
labels are 1..18 and translate once using `label_number - 1`. No added week,
schedule/save expansion, or simulated-game effect is implied.

Validate `type(plan.abilities) is bool`, call
`abilities_patch._week(plan.abilities_off_week)`, and reject a non-None week
when `abilities` is False. Validate before copying output. Add `abilities` to
`BuildPlan.wants_xbe_patch()`, image requirement/availability maps, inspector
selection, summaries, serialization, receipt extraction and source/output
status maps. An existing project missing either field gets the defaults.
Do not coerce strings, floats or Boolean week values to integers.

Abilities imply the allocator. Include their `REQUESTS` in the same complete
union as every selected allocator owner **before the first allocation**.
The actual request is `(nfl2k5_abilities_runtime, code, 1072, 16)`, within the
1536-byte abilities budget, zero RW. Never hardcode the returned VA. Use the
existing v3 scale-out path (`scaleout=True` when explicitly allocating).

Follow the existing deferred-owner routing: in the early `replace(plan, ...)`
used to decide the ordinary XBE pass, set `abilities=False` and
`abilities_off_week=None`. Carry the selected requests into the paired
scorebug `extra_requests` path. Add `or plan.abilities` to the final XBE pass
condition and forward both fields in its final `_apply_all` invocation. Do
not create an early smaller directory and try to add abilities afterward.
The extent adapter must accept `space.SCALEOUT_SIZE` via the existing
scale-out WIRING handoff, not a new arbitrary image length.

## Dispatcher tuple, keyword arguments and all four dictionaries
# r62 dedicated zone QB spy runtime handoff, 2026-09-05

Backend: `mod_editor/core/nfl2k5_qb_spy_runtime.py`, allocator owner
`nfl2k5_qb_spy`, option **`qb_spy`**. This is **EXPERIMENTAL / UNWITNESSED**.
The protected implementation files and reservation JSON were not edited.
`ASTRA_QB_SPY_RUNTIME_REPORT.md` describes the five live hooks, bounded proofs,
31-record authored lookup limit, and exact deferred man/rush work.

## BuildPlan, presets and paired intent

In protected `mod_editor/core/mod_build.py`, add `qb_spy: bool = False`.
Explicitly set `"qb_spy": False` in Basic, Advanced (the current `modern`
preset key), and Experimental. Include it in exact-bool validation,
`wants_xbe_patch`, availability, recipe/project serialization, inspection,
selection/status maps, source gating and plan forwarding. Availability requires
`nfl2k5_qb_spy_runtime`, its generated `_code` module and `nfl2k5_xbe_space`.
`qb_spy=True` implies `xbe_space=True`; apply the existing grown-owner
image-only product preflight. No preset enables it.

Before any image mutation, compile the staged PLAY resources using the existing
formation/play and pack writers. Keep **each exact replacement resource paired
with its original compiler report**, including `spy_intent.schema`, resolved
`play_index`/`slot`, `asset_id`, and `replacement_sha256`. Project rows and
`.2k5book` files already retain versioned authoring intent. Feed those pairs to:

```python
spy_table, spy_table_receipt = qb_spy_patch.compile_intent_table(
    [(compiled.replacement, compiled.report), ...])
```

The empty input produces a valid table with zero records and enables command
spies only. Compile once before allocation; keep `spy_table` as transient build
bytes, not a user-editable BuildPlan field. Store `spy_table_receipt` alongside
the build's authoring receipts. Pass **all** intended records together; never
install one book's table and subsequently try to replace it. More than 31
records, duplicate/colliding identities, invalid slots/scripts, or stale
resource/report pairs refuse before writes. All 32 books with one authored
spy each exceed this revision's limit; command spies consume no RO rows.

For packs, retain the per-resource `CompiledFormationPlay.report` from the
actual compiler, not the enclosing pack summary. If multiple passes touch the
same book, compose and validate the final resource first, then resolve retained
intent to its final indices and produce a matching compiler report. Do not
change `replacement_sha256` to conceal a stale report or infer Spy from zone
bytes. A resource-only import without retained intent remains a shallow zone.
The table hashes only immutable names, assignment descriptor and two nodes;
loaded relocation addresses are not persisted. No runtime byte is written into
PLAY. Custom names may use at most 63 UTF-16 units for this lookup.

Defer `qb_spy` with the other grown flags: add `qb_spy=False` to the early
`replace(plan, ...)` and early XBE writer calls. At the final growth pass,
include it in the condition, request union and `_apply_all` arguments, with
`qb_spy_intent_table=spy_table`. Preserve `qb_spy_patch`, `qb_spy`, and the
lookup receipt in final build reporting. In the scorebug resource lane, forward
`qb_spy` to `extra_requests` before its first allocator call and enable it only
in the final executable pass. Apply no allocator after an incomplete union.

Keep the authoring notice accurate until these protected paths are wired.
Then replace the old "not yet shipped" notice with:
"Shallow middle zone. Dedicated QB tracking requires QB spy (experimental)
and the paired authored play lookup in Build." Show the same text in existing
Spy assignment help. A global `runtime_available=True` on a compiler receipt
would be incorrect: only the final paired XBE/table establishes availability.
No GUI file was changed in this branch.

## Dispatcher tuple, kwargs, allocator union and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import:

```python
from . import nfl2k5_abilities_runtime as abilities_patch
```

Add `abilities: bool = False, abilities_off_week: int | None = None` to
`_apply_all`, `write_xbe_copy`, and `write_image_copy`. Forward both through
every caller and include `abilities` in both writers' nothing-requested
conditions. Validate the Boolean/week relationship as above. Keep the
backend's omitted replay argument semantics: passing an explicit None to an
installed configured image intentionally refuses changing its week.

Extend `_selected_space_requests`, `_xbe_space_adapter`, inherited
`_defensive_try_adapter` constructors, and every union call with `abilities`.
Append `(abilities_patch.REQUESTS if abilities else ())` to the union. Add
`or abilities` to the allocator tuple's enabled condition. Reuse the existing
adapter pattern:

```python
class _abilities_adapter:
    def __init__(self, off_week):
        self.off_week = off_week

    @staticmethod
    def status(payload):
        return abilities_patch.status(payload)

    def apply(self, payload):
        return abilities_patch.apply(payload, abilities_off_week=self.off_week)
```

Add this tuple to the **final owners, after allocation**, beside Momentum and
zone-drop (and after the batch-1 Coverage/scramble owners when integrated):

```python
(abilities, _abilities_adapter(abilities_off_week),
 "abilities_patch", "experimental player abilities"),
```

The seven retail hook spans are disjoint from Momentum and the legacy ramp.
Every permutation of those three owners is byte-identical in backend tests.
Keep the existing Build/Momentum policy that normalizes the legacy ramp off;
do not silently change that product policy. The instruction suite separately
proves the speed-call/store path with the ramp both off and on.

Add these keys to **all four returned status dictionaries**. Use `payload`
in `read_xbe` and `read_image`, `result` in `write_xbe_copy`, and `after` in
`write_image_copy`:

```python
"abilities": abilities_patch.status(payload),
"abilities_settings": abilities_patch.read_settings(payload),
```

`abilities_settings` includes `abilities_off_week`, `model_version`,
`experimental`, and `runtime_witnessed`. Use the same values in
`mod_build.inspect`, `_allocator_feature_status`, availability, output report
and write subreceipt forwarding. Never report only the requested checkbox
when the executable is foreign or has a different installed week. Preserve
`abilities_patch`'s exact edit, allocation, code-install and byte-count
receipt; replay has an empty edits list and zero changed bytes.

## Gameplay Patches, Build tab and existing Rosters card

Add the following `PATCHES` row in
`mod_editor/gui/gameplay_patches_panel_qt.py` and add `abilities` to
`NEEDS_IMAGE`:

```python
("abilities", "Player abilities (experimental)",
 "Retail ignores stored ability flags. Patch: Speedster permits movement "
 "Speed above 99. Each special move requires its stored permission, and "
 "right-stick moves also require Right-Stick Moves. The special-move charge "
 "meter works only for live ball carriers with an allowed move, including "
 "CPU players. Abilities must be assigned in Rosters or the save first. "
 "An optional existing franchise week turns them off temporarily. "
 "EXPERIMENTAL / UNWITNESSED. Simulated games are unchanged."),
```

The text contains both required words **Retail** and **Patch**. Do not label
zero-flag retail rosters ready for normal play: under this opt-in contract
those players cannot use the five special moves. Cosmetic stars never grant
permissions. Turning the switch off in a project means rebuild from its
supported base; it does not uninstall hooks from an already-patched source.

Add the Build-tab `_option` caption:

```python
self.abilities_check = self._option(
    g, "abilities", "Player abilities (experimental)",
    tt.abilities_patch.HELP_TEXT, badge="EXPERIMENTAL / UNWITNESSED",
    needs_image=True)
```

The caption is 31 characters, below 60. Add an adjacent off-week combo:
`No abilities-off week` (data None), then `Week 1`..`Week 18` (data 0..17).
Caption: `Week with abilities off`. Disable it while `abilities` is False and
reset to None when disabling the runtime. Tooltip: `Use an existing regular-
season week. Player ability flags stay saved and return the following week.`
Implement plan creation, source inspection, dirty tracking, preset/reset and
project load/save bindings for both fields in the protected Build/Studio
panels. Loading an installed source displays its actual rules version and
week. Refuse reconfiguration with the backend's rebuild message.

The already-shipped `roster_editor_panel_qt.py` is another owner's GUI and was
left unchanged. Its current data-only sentence must become conditional at
integration: `Stored abilities. They affect play only with Player abilities
rules v1 on the game disc. Existing franchise saves keep their own flags.`
Retain the seven existing mask-preserving controls and the separate star
control. Do not invent an assignment pass, automatic HOF tier, rating clamp,
or save migration in this wiring. A movement cache clamp does not police
unrelated raw-rating reads or franchise simulation.

## Release allowlist, runtime closure and capability

Add exactly these runtime allowlist lines to
`packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_abilities_runtime.py
mod_editor/core/nfl2k5_abilities_runtime_code.py
```

Add these explicit imports to the protected runtime checker's closure:

```text
mod_editor.core.nfl2k5_abilities_runtime
mod_editor.core.nfl2k5_abilities_runtime_code
```

Retain their already-shipped dependencies `nfl2k5_xbe_space`,
`nfl2k5_bump_strength`, and `nfl2k5_cave_oracle`. Application needs Python's
standard library and the existing allocator, no assembler, Capstone or
Unicorn. `tools/nfl2k5_abilities_runtime.S` and its assembler are development
sources; the Python byte template is shipped. Add both modules to the
existing gameplay provider closure and repin its fingerprints and the
protected staged checker after integration. No new dependency is needed in
CI and no release-tag test was changed here.

Merge the complete schema-compatible object from
`docs/mod_editor/nfl2k5_abilities_runtime_capability.json` into
`mod_editor/capabilities/registry.v1.json` by ID
`nfl2k5.gameplay.abilities_runtime`, on existing surface
`gameplay_tuning_sliders`. Keep `offline-writer-proved`, runtime `not-tested`,
and experimental/default-off GUI status. The handoff JSON itself is review
evidence and is not a runtime asset to allowlist.

## Manifest, gates and integration acceptance

The manifest generator now imports, observes and installs this owner in the
complete dormant-owner probe, appends its REQUESTS and lists it in all owner
registries. Both XBE gate setUpClass methods assert its presence through
`tests/nfl2k5_allocator_stack.py`; the gate union applies every owner in both
orders. Its dedicated manifest test checks whole hooks plus the immutable
allocation, including unchanged bytes.

Claude must regenerate the protected
`data/nfl2k5_cave_reservations.json` after all final source edits. This branch
only writes the real-build manifest under `.scratch/abilities/manifest.json`.
Do not relax source-drift checks or copy a partially patched fixture into the
production manifest. Regenerate with the standard command and run:

```text
python3 tests/mod_editor/test_nfl2k5_abilities_runtime.py
python3 tests/mod_editor/test_nfl2k5_abilities_unicorn.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
python3 tests/mod_editor/test_xbe_patch_cave_references.py
python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
```

For this isolated branch set `NFL2K5_CAVE_MANIFEST` to the fresh scratch
manifest for the last three commands. After protected integration, validate
staged runtime closure and capability registry and build a disposable disc
with explicit abilities on/off plus a configured week. No user-facing
checkbox is wired by this branch; that is the brief's protected-file boundary.
from . import nfl2k5_qb_spy_runtime as qb_spy_patch
```

Add keyword-only `qb_spy: bool = False` and
`qb_spy_intent_table: bytes | None = None` to `_apply_all`, `write_xbe_copy`,
`write_image_copy` and all their forwarding calls. Append parameters to existing
union/adaptor signatures to preserve positional compatibility. Check exact bool
and reject a supplied table when `qb_spy` is false. Keep nonempty-selection
checks and image eligibility consistent. `_selected_space_requests` adds:

```python
+ (qb_spy_patch.REQUESTS if qb_spy else ())
```

Forward this flag through `_xbe_space_adapter` **and** its inherited
`_defensive_try_adapter`, both constructors/calls in the final tuple, and all
scorebug `extra_requests` lanes. Extend the allocator condition with
`or qb_spy`. Preserve all other landed owners' requests. The spy requests move
512 bytes of its 2,048-byte immutable budget into general RO; they do not use
additional RW budget or any retail tail.

A concrete table-aware adapter follows the existing owner adapter conventions:

```python
class _qb_spy_adapter:
    def __init__(self, table):
        self.table = table
    def status(self, payload):
        return qb_spy_patch.status(payload)
    def apply(self, payload):
        return qb_spy_patch.apply(payload, intent_table=self.table)
```

After the allocator and its other final owners, add:

```python
(qb_spy, _qb_spy_adapter(qb_spy_intent_table),
 "qb_spy_patch", "dedicated zone QB spy (experimental)"),
```

Keep apply-on-applied behavior: exact replay checks the complete runtime, table,
hooks, zero offline state and dependency pins. An omitted table on replay keeps
the installed one; explicit different bytes require a rebuild. Expose table
pairing/count in the receipt without treating a successful code install as a
played witness.

Add the following projection to `_allocator_feature_status` (the current shared
grown status helper) or each of its four consumers:

| Return dictionary | Required entry |
| --- | --- |
| `read_xbe` | `"qb_spy": qb_spy_patch.status(payload)` |
| `read_image` | `"qb_spy": qb_spy_patch.status(payload)` |
| `write_xbe_copy` | `"qb_spy": qb_spy_patch.status(patched)` |
| `write_image_copy` | `"qb_spy": qb_spy_patch.status(final)` |

Use each function's actual final byte variable. Do not project an early,
pre-growth result. For `write_image_copy`'s scorebug lane, forward false/no table
in the initial pass, reserve real requests before resource installation, and
forward the real flag/table to the post-resource `_apply_all` call.

## Gameplay Patches, Build and Studio (protected)

Add `"qb_spy"` to `NEEDS_IMAGE`. Use this PATCHES row:

```python
("qb_spy", "QB spy for zone defenders (experimental)", qb_spy_patch.HELP_TEXT),
```

The help constant contains **Retail** and **Patch** and explains the zone-only,
paired-lookup and unwitnessed limits. The Build `_option` caption is 40
characters (under 60):

```python
self.qb_spy_check = self._option(
    gameplay_layout, "qb_spy", "QB spy for zone defenders (experimental)",
    qb_spy_patch.HELP_TEXT)
```

Use the current layout variable and normal experimental badge. Include checkbox
loading, reset, preset clearing, source eligibility, selection summary,
`_make_plan`, and `studio_qt.py` Gameplay-to-Build/worker plan forwarding.
No man/rush enable switch or new standalone GUI panel belongs to this revision.

## Release, closure, capability and manifest

Add these exact protected release-allowlist lines:

```text
mod_editor/core/nfl2k5_qb_spy_runtime.py
mod_editor/core/nfl2k5_qb_spy_runtime_code.py
ASTRA_QB_SPY_RUNTIME_REPORT.md
```

The `.S` source, assembler, standalone tests and capability handoff JSON are
developer evidence; the generated Python template is the runtime asset. Add
explicit imports to `packaging/check_2k5_mod_studio_runtime.py`:

```text
mod_editor.core.nfl2k5_qb_spy_runtime
mod_editor.core.nfl2k5_qb_spy_runtime_code
```

Retain transitive closure for the already shipped allocator, bump-strength
section digest helper, cave-oracle XBE reader, PLAY inspector/library/codec,
formation/play compiler and pack compiler. Runtime application never invokes
GNU as, Unicorn, Capstone or the Ghidra corpus. Recompute provider and staged
closure pins using the existing packaging tools after integration.

Merge `docs/mod_editor/nfl2k5_qb_spy_runtime_capability.json` through the current
registry serializer/validator: ID `nfl2k5.gameplay.qb_spy`, existing surface
`gameplay_tuning_sliders`, classification `offline-writer-proved`, runtime
`not-tested`, GUI default false. No new surface schema is needed.

The unprotected manifest builder and both XBE gates already compose the spy
owner, with the same canonical allocator name, in both installation orders.
Claude alone regenerates the protected `data/nfl2k5_cave_reservations.json`
after integration. Retain the source fingerprint guard and include all five
live hook spans plus the three named child allocations. Run the spy writer and
Unicorn suites, both XBE gates and the normal protected Build/closure checks.
No release-tag/updater/workflow changes are requested; no push.

---

# r62 deep-zone tiers: evidence boundary, 2026-09-06

This section governs **this job's new work only**. It does not undo the landed
initial-drop, QB-spy, Coverage or catch integrations above.

**Decision: do not wire new facing, bail or reaction switches.** The controlling
`CB_DEEP_ZONE_RESEARCH_2026-09-05.md` section 3 calls the wider callback policy
"HYPOTHESIS later extension" and requires event/target identity, user exclusions,
hysteresis and next-play cleanup. Section 2 does not certify a bail donor.
Sections 4 and 5 separate reaction from catch conversion and require traces.
Neither the memo nor this checkout supplies Noah's required callback witness.
The new native proofs establish additional prerequisites, not those missing
contracts. The requested runtime tiers are therefore deferred, not implemented.

`mod_editor/core/nfl2k5_zone_facing.py` is a **read-only developer audit**, with
`assess(payload)` and a bounded `python3 -m` CLI. It deliberately has no
`apply`, `status`, `OWNER` or `REQUESTS` patch interface. Its JSON says
`patch_available: false`, `runtime_witnessed: false` and identifies each deferred
tier. Do not use a successful audit as an installed gameplay feature.

## Dispatcher, BuildPlan and presets

| Required integration location | Decision for this delivery |
| --- | --- |
| `_apply_all` tuple and kwarg | No new tuple or kwarg. In particular, never pass the audit as a writer. Keep the landed `zone_drop_cap` and `qb_spy` tuples. |
| `_selected_space_requests` and `_xbe_space_adapter` | No new request or flag. The audit consumes zero RX/RW/RO bytes. |
| Four status dictionaries: `read_xbe`, `read_image`, `write_xbe_copy`, `write_image_copy` | Retain the existing `_grown_status_fields` entries for `zone_drop_cap`, `qb_spy` and `coverage_slider`, and the separate catch status. Do not add `zone_facing: applied` or treat `evidence_verified` as patch status. |
| `BuildPlan` fields, normalization, deferred pass and final pass | No new runtime fields or forwarding. Existing `zone_drop_cap: bool = False` remains the initial-depth experiment only. |
| Basic / Advanced / Experimental presets | None enables facing, bail or a new reaction adjustment; all three remain unavailable. Preserve `zone_drop_cap=False` in all presets. |
| Future field names | Reserve `zone_facing`, `zone_bail`, `zone_ball_reaction`, each default `False`, for actual separately proved writers. Do not introduce unsupported selectable fields in this integration. |

The allocator scale-out report has **no deep-zone-tiers budget row**. The memo's
512 RX / 256 RW later-policy estimate fits the full planned union with 51,264 RX
and 3,840 RW bytes still available to new owners, but is neither assembled code
nor an allocated reservation. No new row is added to the committed budget
fixture, `tests/nfl2k5_allocator_stack.py` or any manifest owner list. The existing
initial-drop and Spy owners are already in all those lists. Both XBE gates now
also run the read-only evidence audit in their composed `setUpClass` paths.

## Gameplay Patches and Build text

No new PATCHES row, NEEDS_IMAGE entry, GUI panel, checkbox or Build `_option`
belongs to an unavailable runtime tier. The current `zone_drop_cap` row can be
made more precise in the protected integration pass, keeping the same key:

```python
("zone_drop_cap", "Initial deep-zone corner drop (experimental)",
 "EXPERIMENTAL / UNWITNESSED. Retail: a shallow deep-zone corner can start "
 "by running. Patch: cap the initial depth request. Later movement can still "
 "turn him away. This does not add bail technique or change ball reaction."),
```

This help contains **Retail** and **Patch**. Keep `zone_drop_cap` in
`NEEDS_IMAGE`. Use the same 44-character caption for its existing Build `_option`:
`Initial deep-zone corner drop (experimental)`. Existing checkbox, preset and
plan synchronization keep the same flag. Do not advertise sustained quarterback
facing, an interception improvement, or a bail technique as already built.
The backend's older `HELP_TEXT` can be aligned with this wording when Claude
regenerates its source fingerprint; this branch leaves that shipped source and
its reservation fingerprint intact.

## Allowlist, runtime closure, capability and manifest

- **Release allowlist lines:** no new runtime line is required. The audit and
  tests are developer evidence and are not imported by the product. If Claude
  distributes the report with other Astra reports, the exact optional line is
  `ASTRA_DEEP_ZONE_TIERS_REPORT.md`. The existing zone-drop/Spy/Coverage/catch
  backend allowlist entries remain necessary for their existing features.
- **Runtime-closure imports:** no new import in
  `packaging/check_2k5_mod_studio_runtime.py`. If this developer audit is later
  deliberately distributed, add the exact allowlist line
  `mod_editor/core/nfl2k5_zone_facing.py` and closure import
  `mod_editor.core.nfl2k5_zone_facing`, retaining its existing five backend
  dependencies. It needs neither Capstone nor Unicorn to run.
- **Capability registry:** no new product surface or writer entry. Keep
  `nfl2k5.gameplay.zone_drop_cap` limited to the initial drop, with runtime
  `not-tested` and all presets off. Add this report and the two new test paths
  to that entry's evidence if desired. A developer audit command is
  `python3 -m mod_editor.core.nfl2k5_zone_facing --xbe <extracted-default.xbe>`;
  a standalone validation command is
  `python3 -m tests.mod_editor.test_nfl2k5_zone_facing`.
- **Manifest:** no new runtime owner or storage span exists, so no owner-list
  addition or reservation-JSON regeneration is required for this job. Do not
  reserve either zone callback for a second owner. If the existing backend help
  or other fingerprinted sources change during integration, Claude alone
  regenerates the protected JSON using the normal builder.

## Concrete requirements before the deferred runtime work

1. Retain paired full callback traces through receiver selection `0x1A1510`,
   deep selection `0x1A2F80`, movement and effective facing. Establish which of
   `A+0x40/+0x48` is the receiver whose crossing releases the preference. Define
   the depth margin, hysteresis and late man-to-zone behavior from that evidence.
2. Prove pass release separately from generic owner changes. Reuse the Spy
   holder/type/team and user-control evidence where it applies, but preserve
   handoff, scramble, loose ball and turnover pursuit. Trace actual assignment
   reset, audible, snap and substitution; do not borrow Spy's private RW records.
3. Design one explicit detour composition contract. Spy currently owns the
   entire six-byte prologues at `0x1A5790` and `0x1A5090` and pins each complete
   callback. It bypasses receiver selection for an active spy. A later owner
   must share that dispatch or intercept proved nonoverlapping calls with strict
   mutual recognition. Do not merely exempt callback bytes from either hash.
   Prove both apply orders, replay, native fallback, active spy and every reset.
4. Prove the press/bail donor and its transition before adding its flag. Modes
   9/10 identify the outside deep assignments in both Cover 3 and four-deep
   examples; they cannot establish thirds-only bail. PLAY names and Start operands
   cannot establish actual press alignment or a rendered technique.
5. If a reaction adjustment is still justified, specify its exact-CB/deep-zone
   guard and separate contribution at the already facing-aware gate `0x1F4250`.
   Account for the existing Coverage owner there; do not modify the Interception
   catch cave at `0x1C8317` or count its effect twice. Then add actual REQUESTS,
   allocator/manifest owners, strict idempotent writer APIs, the full flags/status/
   Build/PATCHES/NEEDS_IMAGE/closure/capability integration, and per-tier native
   proofs. All presets still default off until a separate release decision.

No permission request, push or protected-file edit is part of this handoff.
## r62 Franchise Practice exit correction (2026-09-06)

This is a bug fix under the existing `franchise_practice` switch. The implementation,
standalone tests and evidence are in `ASTRA_FRANCHISE_PRACTICE_EXIT_REPORT.md`.
The START stub now pops settings once and pushes the retail game screen so Quit
can tear that screen down and resume the retained Coach's Desk. No new flag,
allocator owner, resource, save field or capability surface is introduced.

### Existing dispatcher, status and preset wiring to retain

`nfl2k5_throw_tuning._apply_all` already accepts `franchise_practice: bool = False`
and contains the exact tuple:

```python
(franchise_practice, franchise_practice_patch,
 "franchise_practice_patch", "Franchise-practice"),
```

Keep that tuple, the existing import and the `franchise_practice=` forwarding.
The four existing status dictionaries require no new key or adapter:

| Function | Existing entry |
| --- | --- |
| `read_xbe` | `"franchise_practice": franchise_practice_patch.status(payload)` |
| `read_image` | `"franchise_practice": franchise_practice_patch.status(payload)` |
| `write_xbe_copy` | `"franchise_practice": franchise_practice_patch.status(result)` |
| `write_image_copy` | `"franchise_practice": franchise_practice_patch.status(after)` |

`BuildPlan.franchise_practice: bool = False` stays as shipped. BASIC is false;
ADVANCED and EXPERIMENTAL are true. Preserve Practice Squad screen normalization
and the existing final XBE pass. Both XBE gates and `tests/nfl2k5_allocator_stack.py`
already include this owner and its dependent reserves/screen patches; the same
352-byte reservation covers the seven added code bytes. No request-union or
budget-fixture change is needed.

### Protected UI copy correction

Replace only the existing Gameplay Patches help text for `franchise_practice`.
Its current description says Practice is above Schedule and attributes the
return to the one pop alone. Use:

```python
("franchise_practice", "Free Practice inside Franchise",
 "Retail: Practice is available from Game Modes. Patch: adds Practice below "
 "Schedule on the Coach's Desk. Practice uses your franchise roster and "
 "returns to the Coach's Desk when you quit. EXPERIMENTAL / UNWITNESSED: "
 "verify the return and unchanged schedule, roster and depth chart."),
```

Keep `franchise_practice` out of `NEEDS_IMAGE`: this remains an XBE-only patch.
Keep the Build `_option` caption `Free Practice inside Franchise` (30 characters),
its `franchise_practice` key and `NOT_TESTED` badge. Its concise help can be:
`Practice with your franchise team, then return to the Coach's Desk. Experimental.`
No new checkbox, worker argument or Studio forwarding is needed.

### Protected manifest and release handoff

Claude must regenerate `data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after integration. The production manifest
is unchanged here. Its source guard correctly rejects the old fingerprint of
`mod_editor/core/nfl2k5_franchise_practice.py`; this is the only stale source.
Do not update the fingerprint by hand or disable the guard. Run the full oracle
suite with the regenerated manifest, then both XBE gates. Use a disposable image
inside `TemporaryDirectory` with cleanup on all paths, sufficient space to keep
the main drive above 100 GB free, and bounded streaming I/O. This worktree did
not build or retain a disc or pack copy because space was too close to that floor.

The runtime module is already allowlisted and imported by the runtime closure:

```text
mod_editor/core/nfl2k5_franchise_practice.py
mod_editor.core.nfl2k5_franchise_practice
```

Retain those entries. If the report is included in release documentation, add
this allowlist line:

```text
ASTRA_FRANCHISE_PRACTICE_EXIT_REPORT.md
```

No new runtime-closure import or capability registry entry is needed. Preserve
the existing experimental/unwitnessed classification. Older already-patched
XBEs containing the previous START are deliberately `foreign`; rebuild from
retail through the current owner stack instead of silently migrating a mixed
image. No release-tag, updater, workflow or push change is requested.
## r62 momentum-contact: model 2 collision extension (2026-09-06)

This section supersedes the model-1 Momentum fields/help where specified.
EXPERIMENTAL / UNWITNESSED. The existing owner is extended; do not register or
allocate a second owner. Protected product files and the protected reservation
JSON are unchanged in this task. `ASTRA_MOMENTUM_CONTACT_REPORT.md` contains the
calibration, tier A/B audit, test evidence and Noah's pending witness list.

### Dispatcher and the four status dictionaries

In `mod_editor/core/nfl2k5_throw_tuning.py`, add keyword arguments
`momentum_collisions: bool = False, momentum_collision_level: int = 0` beside
`momentum`/`momentum_contact` on `_apply_all`, both public copy writers and every
forwarding call. Validate with
`momentum_patch._settings(momentum, momentum_contact, momentum_collisions, momentum_collision_level)`
before any copy or mutation. Positive collision level requires the collision
flag; Boolean levels and integers outside 0..100 refuse. True/0 is a no-op.
Use `collision_on = momentum_collisions and momentum_collision_level > 0` and
`momentum_on = momentum > 0 or collision_on` for allocation/application tests.
Do not require positive movement momentum to enable collisions.

Extend `_selected_space_requests` and `_xbe_space_adapter` with the two new
keywords. Include `momentum_patch.REQUESTS` exactly once when `momentum_on`.
Update every call site, including `_defensive_try_adapter` and the runtime
scorebug extra-request path. Keep old positional arguments in place; append
new fields as keywords to avoid shifting unrelated options. `_xbe_space_adapter`
and `_defensive_try_adapter.apply` must use `scaleout=True` when `collision_on`,
so the full union is reserved before any owner emits code. Other beta-62 owners
also select v3 through the existing allocator. Missing or legacy preallocation
refuses before an installed result; rebuild from the supported source.

Extend the existing `_momentum_adapter` as follows:

```python
class _momentum_adapter:
    def __init__(self, level, contact, collisions=False, collision_level=0):
        self.settings = dict(momentum=level, momentum_contact=contact,
                             momentum_collisions=collisions,
                             momentum_collision_level=collision_level)

    def status(self, payload):
        return momentum_patch.status(payload)

    def apply(self, payload):
        return momentum_patch.apply(payload, **self.settings)
```

In `_apply_all`'s final owners tuple, after the allocator entry, replace the
existing Momentum entry with:

```python
(momentum_on,
 _momentum_adapter(momentum, momentum_contact,
                   momentum_collisions, momentum_collision_level),
 "momentum_patch", "experimental player momentum"),
```

The allocator activation expression must include
`collision_on`. Do not install Momentum once per component. For the parity
profile, extend the existing legacy normalization from `momentum > 0` to
`momentum_on`: disable a newly selected `accel_ramp` and retain the receipt
`legacy_accel_ramp_disabled_by_momentum_profile`. The backend continues to
recognize an independently installed legacy ramp without removing it; such a
source is not the clean parity baseline.

`_grown_status_fields` currently serves all four status dictionaries:
`read_xbe`, `read_image`, `write_xbe_copy`, `write_image_copy`. Keep calling it
from all four. Retain `momentum_settings` as the complete `read_settings`
object, including model_version=2 and the two new keys. Compute component
statuses separately so collision-only is not shown as installed braking:

```python
state = momentum_patch.status(payload)
settings = momentum_patch.read_settings(payload)
def component(enabled):
    return "foreign" if state == "foreign" else (
        "applied" if state == "applied" and enabled else "retail")
fields = {
    "momentum": component(settings.get("momentum", 0) > 0),
    "momentum_contact": component(settings.get("momentum_contact", False)),
    "momentum_collisions": component(settings.get("momentum_collisions", False)
                                     and settings.get("momentum_collision_level", 0) > 0),
    "momentum_settings": settings,
}
```

Merge `fields` with the existing unrelated status fields. The backend's
`momentum_patch.status` remains an owner status for integrity and replay.
Use `settings['status'] == 'applied'` to lock ALL of this owner's component
settings on an installed source, including an inactive movement component of
a collision-only source. Changing component settings requires a clean rebuild;
otherwise an UI may incorrectly offer to add braking to a sealed collision
configuration. Model-1 images intentionally report foreign; rebuild, never
resize/migrate their allocation in place.

### BuildPlan, normalization, presets and final pass

In `mod_editor/core/mod_build.py` add:

```python
momentum_collisions: bool = False
momentum_collision_level: int = 0
```

Basic, Advanced and Experimental (`softdrink_experimental`) all explicitly
keep **false/0**. Existing movement momentum and run-up defaults stay off/0.
Opt-in comparison order is movement 0, run-up false, collisions true/50,
then true/100; combined movement/run-up comes afterward. Recipe round trips
must preserve unusual valid integers and both new fields.

Add the collision flag to `wants_xbe_patch`, capability availability (same
`nfl2k5_momentum` backend plus allocator), image state extraction and displayed
status keys. A true flag at level 0 may still enter normal build validation;
it must not select a Momentum allocation. Validate all four settings at the
current Momentum validation call. For positive collision level imply
`xbe_space=True` and disable a newly selected legacy ramp with the existing
receipt as described above.

Both `replace(plan, ...)` calls that defer grown features must also pass
`momentum_collisions=False, momentum_collision_level=0`, to prevent an early
fixed-size pass from partially installing this owner. Include `collision_on`
in the final grown-pass condition; forward both fields to `_apply_all` and to
`_selected_space_requests` in the paired scorebug resource pass. Carry the
complete settings and component statuses into final rebuilt-image reports.
The final pass already uses the accepted v3 extent writer; no transport or
archive change is required.

### Gameplay Patches and Build controls

In `mod_editor/gui/gameplay_patches_panel_qt.py`, add this `PATCHES` row:

```python
("momentum_collisions", "Weight and speed in contact (experimental, unwitnessed)",
 "Retail already uses weight and speed in tackles. Patch: a small, capped "
 "benefit when the ball carrier's weight and speed toward contact outweigh "
 "the defender's approach. Standing carriers gain no benefit. Ratings still "
 "matter. Experimental / Unwitnessed. Separate from turning and braking."),
```

Add `momentum_collisions` to `NEEDS_IMAGE`. Add an independent level control
for `momentum_collision_level`, with Retail/0, Light/25, Medium/50, Heavy/100
and honest installed-value display for other valid integers. Check selects
last positive level (initially 50); uncheck sets flag false and level 0.
Selecting level 0 clears the flag. Gate editing against the entire owner's
installed/foreign state, not just this component's status. Do not clear this
control when movement momentum changes to 0. Retain the existing requirement
that only the old run-up option needs positive movement momentum.

In `mod_editor/gui/build_panel_qt.py`, add the `_option` caption
**`Weight and speed in contact (experimental)`** (41 characters, <=60), using
`momentum_collisions` and `nfl2k5_momentum.COLLISION_HELP_TEXT`. Give it the
same independent level control and state-lock behavior. Add both fields to
plan construction, preset loads, status refresh, recipe notes and selected
feature display. For positive selection clear the legacy ramp checkbox and
record the profile normalization. Keep implementation addresses, allocation
terms and the mathematical formula out of the product flow.

### Capability, allowlist and runtime closure

Replace the existing `nfl2k5.gameplay.momentum` object in
`mod_editor/capabilities/registry.v1.json` with the complete updated object in
`docs/mod_editor/nfl2k5_momentum_capability.json`. This extends the existing
surface; no new surface enum, router, owner or duplicate registry ID is needed.
Both backend.command and validation_command use the schema-resolvable
`python3 -m mod_editor.core.nfl2k5_momentum ...` form. The backend example
builds collision-only 50. Classification stays `offline-writer-proved`, runtime
`not-tested`, GUI default disabled.

Required `packaging/release-allowlist.txt` lines (the first three already exist;
retain once, append the new report):

```text
mod_editor/core/nfl2k5_momentum.py
mod_editor/core/nfl2k5_momentum_code.py
docs/mod_editor/nfl2k5_momentum_capability.json
ASTRA_MOMENTUM_CONTACT_REPORT.md
```

Runtime-closure imports in `packaging/check_2k5_mod_studio_runtime.py` already
contain `mod_editor.core.nfl2k5_momentum` and
`mod_editor.core.nfl2k5_momentum_code`; retain them and assert model_version 2,
`COLLISION_HELP_TEXT`, and the four-argument settings contract. No new runtime
package or GNU assembler dependency is introduced. The assembler and tests
remain development tools. Extend the integration validator to run
`tests/mod_editor/test_nfl2k5_momentum_collisions.py` standalone.

### Manifest and integration acceptance

The existing Momentum owner was already in all three manifest owner lists,
`all_requests`, and the shared allocator union. Its request is now **1,408 RX /
2,064 RW**, with no extra RW or RO. The committed budget fixture replaces only
its code row. Both gate fixtures and both manifest owner probes now explicitly
install collisions true/100 alongside run-up/movement 100; the manifest also
records `momentum_settings`. Both orders include the actual abilities owner.
Claude must regenerate `data/nfl2k5_cave_reservations.json` from final integrated
sources using the real manifest builder; this task never overwrites it.

After protected wiring, check collision-only 0/false/true/50 builds, both-zero
byte identity, movement-only old configuration, combined 100/true/true/100,
all four read/write status dictionaries, model-1/foreign refusal, profile
normalization, exact replay and changed-setting refusal. Run both XBE gates,
the Momentum suites and the manifest suite against the fresh private/release
manifest. Keep source-fingerprint checks enabled. No gameplay witness or
release enablement is implied by these offline checks.
# r62-play-rules-editor: retail Rules library and Info reference

This feature authors PLAY data through the existing compiler and project/pack
pipeline. Its own wizard tabs and panels are implemented. All shared files
below were left untouched as required by ASTRA_BRIEF.md. Evidence and witness
requirements are in `ASTRA_PLAY_RULES_REPORT.md`.

## Studio registration

Import `PlayInfoPanel` from `mod_editor.gui.play_info_panel_qt` in the protected
`studio_qt.py`. In `_build_create_play_page`, keep the existing authoring page
and replace its final `return page` with this wrapper (`QTabWidget` is already
imported):

```python
tabs = QTabWidget()
tabs.setObjectName("createPlayTabs")
tabs.addTab(page, "Create a Play")
self._play_info_panel = PlayInfoPanel()
tabs.addTab(self._play_info_panel, "Info")
return tabs
```

Update that page's blurb to:

```text
Choose a formation, design assignments or copy retail rules, then place the
play in the book. Rules and gameplay results are experimental and unwitnessed.
Use Info for the format, rule vocabulary and current evidence limits.
```

The wizard already contains Assignments, Rules library and Info tabs on its
assignment page. The standalone Studio Info tab makes the same reference
available before choosing a source. It needs no facade, retail assets, runtime
patch or source eligibility gate. Do not edit `playbooks_panel_qt.py` for this
job; the Create a Play surface satisfies the requested placement. Maintain the
existing `PlaybooksPanel(self.facade)` registration.

## Explicit dispatcher, Build and allocator disposition

| Protected integration item | Required change |
| --- | --- |
| `_apply_all` owner tuple and kwarg | None. This is an existing PLAY resource writer path, not an XBE patch. |
| `_selected_space_requests`, `_xbe_space_adapter`, `_grown_status_fields` | None. No owner or executable/data allocation. |
| `read_xbe` status dictionary | No new key. |
| `read_image` status dictionary | No new key. |
| `write_xbe_copy` status dictionary | No new key. |
| `write_image_copy` status dictionary | No new key; normal resource compiler receipts apply. |
| `BuildPlan` field, normalization, deferral, final pass | No new field. Existing staged formation/play/pack requests carry the change. |
| Basic / advanced / experimental preset enablement | None enables or silently copies rules. Applying a bundle is an explicit authoring action. |
| Gameplay Patches `PATCHES` text and `NEEDS_IMAGE` | No new row or membership. Retail rules are PLAY data; Patch installation uses the existing project/pack transport. |
| Build `_option` caption (60-character limit) | Not applicable; no new checkbox. |
| Allocator budgets, union, memory/cave gates and cave manifest | No new owner; no changes or regeneration needed for this job. |

Existing dedicated Spy and read-option runtime settings keep their own Build
requirements. Copying a retail bundle does not create those intents or enable
their switches. Do not invent a gameplay patch toggle to expose a data editor.

## Exact release allowlist additions

Add these currently absent lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_play_rules.py
mod_editor/gui/play_rules_panel_qt.py
mod_editor/gui/play_info_panel_qt.py
docs/mod_editor/play_rules.json
docs/mod_editor/play_rules.md
docs/mod_editor/play_rules.evidence.json
ASTRA_PLAY_RULES_REPORT.md
ASTRA_DEFENSE_PLAY_REPORT.md
ASTRA_READ_OPTION_BUILD_REPORT.md
ASTRA_SCREEN_PASS_REPORT.md
ASTRA_GAMEPLAY_LEVERS_REPORT.md
```

The last four reports are linked by Info and were absent from this branch's
allowlist. Retain existing lines for `ASTRA_ZONE_DROP_REPORT.md`,
`ASTRA_QB_SPY_RUNTIME_REPORT.md`, `docs/product/PLAY_EDITOR_FINDINGS.md`,
`docs/mod_editor/playbook_packs.md` and
`mod_editor/core/nfl2k5_seven_on_seven_book.py`. The codec, library, inspector,
writer, pack module and Create a Play wizard already have product paths; retain
their updated versions. The evidence JSON contains hashes/counts and corpus
locations, not node payloads or decompiler bodies.

Do not release `.scratch/play_rules_audit.json`, the research CLI, tests or
`docs/mod_editor/play_rules.capability.json`; those are local/developer evidence
or integration inputs. Presets ship selectors only. User-exported project/pack
operands remain user artifacts and must not be copied into the release.

## Runtime closure

Add these explicit imports to the protected runtime closure check:

```text
mod_editor.core.nfl2k5_play_rules
mod_editor.gui.play_rules_panel_qt
mod_editor.gui.play_info_panel_qt
```

Stage `docs/mod_editor/play_rules.json` at that exact relative path. Its loader
resolves the application root from `mod_editor/core`; retain the normal staged
directory layout. Retain transitive codec/library/inspector/writer/pack, errors,
PyQt5 and existing book-reader closure. No Capstone, Unicorn, Ghidra, network
dependency or game asset is needed to open Info.

Extend the offscreen runtime probe to instantiate `PlayInfoPanel`, assert 47
topics including all 29 opcode topics and a read-only reader, search `31
records`, and open the linked local reports. Missing reference JSON must fail
the release probe rather than ship an empty tab. Run the normal staged closure
and provider fingerprint regeneration after integration. Source tests prove
the panels, not the protected packaged build that this job cannot edit.

## Capability handoff

Merge `docs/mod_editor/play_rules.capability.json` as capability
`nfl2k5.scripts.play_rules` on existing surface `scripts_config` using the
registry serializer. Classification is `offline-writer-proved`, runtime
`not-tested`, exposed edit mode with `default_enabled: false`. No surface enum
or schema expansion is needed. The backend command invokes the existing
project writer with `python3 -m tools.nfl2k5_visual_mod_project ...`; the
validation command is `python3 -m tests.mod_editor.test_nfl2k5_play_rules`.
The read-only catalog/inspect commands are documented in the guide.

The handoff passes the repository validator's structural checks and its own
evidence/command file checks. A full inherited registry file check currently
stops at the pre-existing missing `docs/research/apf_audio.md` in capability 0;
resolve that independently when doing shared integration. Do not mistake it
for a missing new Rules file.

The older `nfl2k5.scripts.director_playbook` row contains stale global claims
that the compiler never authors nodes and that the true-spy backend is not yet
built. Reconcile that row with the already-landed authoring/spy capabilities
and the new Rules row: copied operands can persist in local projects and v3
packs, while the distributed library contains selectors only. The new row does
not claim a witnessed runtime outcome.

Run both new standalone Rules test files, the existing authoring/writer,
defense/read-option and pack suites, and protected Studio/runtime closure
checks after wiring. No updater, tag, workflow or push change is requested.
# r62 read-option runtime handoff, 2026-09-06

This section is the handoff for `astra/r62-read-option-runtime`. It supersedes
only earlier deferred-runtime notes for this feature. EXPERIMENTAL / UNWITNESSED.
All three presets remain OFF. No protected file was edited in this branch.

The delivered core has modern hold/release input, a versioned read-only table,
a CPU position/velocity policy, a native receiver-readiness gate, and a
single condition-task decision shared through the native QB/back cache. The
requested in-game prompt and live search for a replacement unblocked EDGE are
NOT implemented. Do not call this a finished dependable-read feature or enable
it automatically. The report describes the exact limits and pending work.

## BuildPlan and paired PLAY artifacts

In protected `mod_editor/core/mod_build.py` add:

```python
read_option_runtime: bool = False
```

Add it to `wants_xbe_patch()`, the Boolean normalization/validation list, inspect
and availability/status forwarding, and every grow-owner deferral/final-pass
condition alongside `qb_spy`. Explicitly set it False in `softdrink_basic`,
`softdrink_advanced` and `softdrink_experimental`; changing presets must clear a
prior true value. No independent acceleration-ramp or defensive setting changes.

As with the existing `spy_pairs`, retain each final PLAY replacement and its
complete compiler receipt for authored reads. After ALL edits to that resource,
call the new `nfl2k5_play_library.compile_read_option_intent_table(read_pairs)`.
Its input is a sequence of `(exact_replacement_bytes, compiler_report)` tuples.
It verifies `replacement_sha256`, the option schema, both participant scripts,
formation/personnel intent, capacity and unique identity before allocating or
writing the output. It excludes every native speed option. A selected Build
checkbox requires at least one read row; fail clearly if none was authored.

Do not feed a receipt from an intermediate gun, defense, clone, mirror, retarget
or import pass to this compiler after another pass has changed its resource.
Carry the authored intents into the FINAL writer invocation or reject the stale
pair and require a recompile. Never regenerate a matching hash on a stale receipt.
Persist this table's receipt in the build output as `read_option_intent_table`,
beside the paired PLAY receipts. An empty table is supported for dormant owner
composition and lower-level XBE tests, not a successful selected UI feature.

Pass `read_option_runtime=False` in the early ordinary-XBE pass, and reserve its
REQUESTS in the final complete union. In the final owner pass forward the real
Boolean and `read_option_intent_table=read_table`. Do not add a new PLAY opcode.
RPO receiver 6 is explicitly refused because its A button shares the snap hold;
choose receiver 7 or 8. The existing data-only presets and pack schema stay intact.

## Dispatcher, allocator and all four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py` import:

```python
from . import nfl2k5_read_option_runtime as read_option_patch
```

Add keyword arguments to `_apply_all`, `write_xbe_copy`, and `write_image_copy`
and forward them through every caller:

```python
read_option_runtime: bool = False,
read_option_intent_table: bytes | None = None,
```

Validate an actual Boolean. A table must be bytes, validate with
`read_option_patch.validate_intent_table`, and require the Boolean when a table
is supplied. Omitted table on replay preserves the installed table; a different
explicit table refuses and requires rebuilding from a supported source.

Extend `_selected_space_requests`, `_xbe_space_adapter`, the inherited
`_defensive_try_adapter`, their signatures/callers, and grow-owner conditions:

```python
+ (read_option_patch.REQUESTS if read_option_runtime else ())
```

Include `or read_option_runtime` in the allocator entry and both writers'
nothing-requested conditions. Add this adapter and tuple in the final owners
AFTER the allocator tuple, beside the existing QB spy adapter:

```python
class _read_option_adapter:
    def __init__(self, table):
        self.table = table

    @staticmethod
    def status(payload):
        return read_option_patch.status(payload)

    def apply(self, payload):
        return read_option_patch.apply(payload, intent_table=self.table)

(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
```

In `_grown_status_fields(payload)` add:

```python
"read_option_runtime": read_option_patch.status(payload),
"read_option_runtime_settings": read_option_patch.read_settings(payload),
```

Ensure these land in ALL FOUR dictionaries: `read_xbe` and `read_image` use
`payload`, `write_xbe_copy` uses `result`, `write_image_copy` uses `after`.
Forward them through `mod_build.inspect`, `_allocator_feature_status`, build
receipts and output inspection. The settings report actual installed row count,
table hash and mesh policy. Foreign/uninstalled settings are None. Preserve the
exact owner receipt including full hook span, allocation, hashes, changed bytes,
zero RW budget and `experimental=True`, `runtime_witnessed=False`.

## Gameplay Patches and Build tab

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, add a PATCHES row
with key `read_option_runtime`, title `Read option mesh controls (experimental)`,
and description `read_option_patch.HELP_TEXT`. The exact text is:

> EXPERIMENTAL / UNWITNESSED. Retail: option plays use the original pitch and
> position rules. Patch: paired authored reads use release to give and hold the
> snap button to keep at the mesh. CPU QBs read the selected edge. RPO throws
> require the intended receiver to be ready. The in-game prompt and a replacement
> defender search are not included. All presets are off.

This contains the required words Retail and Patch. Add the key to NEEDS_IMAGE
because an enabled product build needs its paired PLAY resource. Preserve the
normal foreign-image refusal and receipt read-back, rather than reporting the
checkbox as proof of installation.

In protected `mod_editor/gui/build_panel_qt.py` add the Boolean `_option` using
caption `Read option mesh controls (experimental)` (40 characters), default
False. Bind it to BuildPlan collection, preset application, reset and post-build
status; use HELP_TEXT for its description. Show the two-read capacity/refusal
before building. Do not present this box as authoring new plays automatically.
Any existing Studio or Gameplay forwarding lists in the other protected panels
need the same key. No new feature-specific GUI panel is necessary.

## Release allowance, closure, capability and manifest

Add exactly these lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_read_option_runtime.py
mod_editor/core/nfl2k5_read_option_runtime_code.py
```

Add these explicit runtime-closure imports to protected
`packaging/check_2k5_mod_studio_runtime.py` and the gameplay provider closure:

```text
mod_editor.core.nfl2k5_read_option_runtime
mod_editor.core.nfl2k5_read_option_runtime_code
```

The already-shipped play library, inspector, codec, allocator, cave reader and
section-digest helper remain dependencies. No GNU assembler, Unicorn, Capstone,
private research file, test module or generated game bytes are runtime assets.
The .S and assembler are development sources; end-user application uses the
checked-in reproducible Python byte template.

Merge `docs/mod_editor/nfl2k5_read_option_runtime_capability.json` into the
capability registry by ID `nfl2k5.gameplay.read_option_runtime`, on the existing
`gameplay_tuning_sliders` surface. Both commands use `python3 -m dotted.module`
so file-check validation resolves them. Keep `offline-writer-proved`, runtime
`not-tested`, explicit limitations and all presets off.

The unprotected complete-owner stack, both XBE gates, all manifest owner lists
and the budget fixture are already updated in this branch. Claude must regenerate
protected `data/nfl2k5_cave_reservations.json` after merging final sources and this
wiring. The scratch manifest is verification evidence, not a replacement for
that protected release artifact. Add `read_option_runtime=False` to the manifest
builder's dormant-base BuildPlan replacement once the protected BuildPlan field
exists, so future preset changes cannot preallocate an incomplete request union.

Acceptance after wiring: two paired reads selected, a dormant empty table at
backend level, no read recipes with the checkbox on (refusal), all presets reset
off, changed/stale PLAY receipt refusal, two controllers/layouts, both XBE gates,
capability file check, staged runtime closure, and Noah's pending witness list.
