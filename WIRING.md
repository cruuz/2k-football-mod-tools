# beta-63.1 raw-dump overlap hotfix (2026-09-09, branch local/hf63-rawdump-overlap)

Bug: Ju3tin, #2k5-general 2026-09-09 15:00 — "ValueError: overlapping disc file or metadata: root
directory" building from a RAW DUMP with the extra features ticked, then "please insert disk" in xemu
from the preset build (15:36).  Both are fixed outside every protected file (commits d067a795 and the
identity-note commit that follows it; see ASTRA_REPORT.md).  Two protected-file follow-ups remain for
Claude; nothing below is needed for the fix to work.

## `data/nfl2k5_cave_reservations.json` — regenerate (manifest 31)

The build path never checks `source_sha256` (only `tools/nfl2k5_cave_oracle.py:98` passes
`source_root=ROOT`), so builds are unaffected, but the tool refuses with "stale reservation source:
...; regenerate manifest" until the manifest is regenerated.  The two entries that changed:

```
"mod_editor/core/nfl2k5_music_archive.py":  47479bf3c41fb1765b72bdba0384368ba68efc418e8648bfc74263192286baa8
                                         -> a86456b894128d773c61c972c3eb535614f476941c5781737f6ebaef8d11da8a
"mod_editor/core/nfl2k5_disc_identity.py":  bb9701f911996e4fd208f2eabbdce0c00b1519cc036055518830c19f06e223a4
                                         -> 000ec3164d1da4a9e0fb4a4bd48deb55e4241cff90d7ee4762dd1caa446eff3e
```

`mod_editor/core/providers.py` was repinned with `packaging/repin.py --apply` in each commit.
`reports/hires_pack_build.v1.json` (a historical receipt) still lists the old archive hash; no test reads it.

## Optional: the Build & Share completion dialog for a raw-dump source (`mod_editor/core/mod_build.py`, protected)

The identity line now carries the xemu sentence, and the Build page shows it in the source header before
the user presses Build (`build_panel_qt.py:1031` reads `state["disc_identity_line"]`), so the refusal
and the warning both reach the user without touching the GUI.  If Claude wants the same sentence on the
completion dialog after a raw-dump build, the smallest change is in `build()` (`mod_build.py`, after
`receipt["outcome"] = measure(source, directory / target.name)`):

```python
identity = tt.disc_identity.identify(source)          # or the cached inspect() identity
if identity.partition_base:
    receipt["outcome"]["message"] += tt.disc_identity._xemu_note(identity.partition_base)
```

(`_xemu_note` is the public-enough helper the identity line already uses; it returns "" for an xiso.)
Not done here: the message the bug needs is already on the source line, and `mod_build.py` is protected.

# beta-63.1 digit texture budget hotfix (2026-09-09)

Bug: Coach Edwards, #2k5-bugs 2026-09-09 09:51 / 10:16 — "live_number_nameplate
(asset_code=02, side=H, variant=0, family=arm): Digit artwork cannot fit its
896-byte texture slot without dropping below the 16-colour quality budget"
refused the whole disc after a Team Kit round trip.  The fix is complete
outside the protected GUI; these are the two optional GUI touches that make
the new "kept retail" outcome visible on the Uniforms page.  Nothing below is
required for the disc to build; without it the outcome still reaches the user
through the status bar (`BuildResult.message`) and the Build & Share
completion dialog (`build_feedback.completion`).

## `mod_editor/gui/studio_qt.py` — Uniforms page component list

`_populate_components(self, uniform_set)` marks every asset in
`facade.modified_asset_ids` as "● Modified".  After a project build the facade
now also exposes `facade.kept_retail_asset_ids` (a `frozenset[str]` of catalog
asset IDs) and `facade.last_build_kept_retail` (the receipt rows with an
`asset_id` and a user-readable `message`).  Add, next to the existing
`modified = set(...)` line:

```python
kept = set(getattr(self.facade, "kept_retail_asset_ids", ()))
```

and replace the state expression with:

```python
if asset.asset_id in kept:
    state = "● Modified — kept retail at last build (could not fit its slot)"
elif asset.asset_id in modified:
    state = "● Modified"
else:
    state = "Original"
```

Give the kept rows a distinct colour (`item.setForeground(2, QColor("#ff9e7a"))`)
and set the row tooltip to the matching `message` from
`facade.last_build_kept_retail`.  Refresh the list from the build `success`
handler (`_refresh_edit_state()` already runs there; it must rebuild
components so the column updates).

## `mod_editor/gui/studio_qt.py` — "Modded XISO ready" dialog

In the build `success(result)` handler (the `QMessageBox.information(self,
"Modded XISO ready", ...)` call), append the kept-retail rows when present so
the dialog and the status bar agree:

```python
kept = tuple(getattr(result, "kept_retail", ()) or ())
extra = ""
if kept:
    extra = ("\n\nKept retail for %d uniform slot%s whose art could not fit "
             "its fixed texture slot:\n" % (len(kept), "" if len(kept) == 1 else "s")
             + "\n".join("- " + str(row.get("message", row.get("selector"))) for row in kept))
```

and add `extra` to the message text.  `BuildResult.kept_retail` is an empty
tuple for every build that wrote all of its slots, so the wording is unchanged
for those.

## Number-sheet import (no change required)

`preview_digit_sheet` now returns a `kept_retail` receipt row and a
"Digit N: kept retail: could not fit its ...-byte texture slot" note instead of
raising, so `_review_digit_sheet_preview` shows the retail digit in that row
and the note in the details.  The existing `operation` then stages all ten
PNGs; the build keeps retail for the unfit slot and reports it.  If the page
should not stage the unfit digit at all, skip `output` rows whose
`preview.receipts[i].get("kept_retail")` is true before writing them into the
private Team Kit folder.

# hf63.1 Franchise Schedule refusal on a real playoff save (2026-09-09)

Branch `astra/hf63-franchise-schedule` from tag `beta-63`.

Two GUI panels under `mod_editor/gui/` are protected by `HOTFIX_CONTEXT.md`.  Half of this bug lives in
them (the unconditional roster-codec gate on every franchise edit), so the smallest possible change was
made there, as the context allows, and it is described here in full so it can be reviewed as a wiring
request.  Everything else is in core.

## What changed in the protected panels (already applied, commit "Franchise page: ...")

Both panels called `nfl2k5_practice_squad.validate_save(candidate.to_bytes())` after applying **every**
franchise edit, including a schedule cell / year / cap / user-control edit that writes only the season
block or the front office.  Each call site now passes the pre-edit bytes to the new core helper
`validate_save_edit(before, after)`, which runs the same `validate_save(after)` unless the edit left the
ROST resource (`0x2E0..arena_end`) and the injured-reserve table byte-identical.

| file | site | before | after |
|---|---|---|---|
| `mod_editor/gui/roster_editor_panel_qt.py` | `RosterEditorPanel._franchise_edit` (the studio path; `before = self.document.to_body()` was already in scope) | `validate_save(candidate.to_bytes())` | `validate_save_edit(before, candidate.to_bytes())` |
| `mod_editor/gui/franchise_panel_qt.py` | `FranchisePanel._rebuild` (journal replay) | `validate_save(save.to_bytes())` | `validate_save_edit(self._base, save.to_bytes())` |
| `mod_editor/gui/franchise_panel_qt.py` | `FranchisePanel.push` (standalone page) | `validate_save(candidate.to_bytes())` | `before = self._save.to_bytes()` captured; `validate_save_edit(before, candidate.to_bytes())` |
| `mod_editor/gui/franchise_panel_qt.py` | `FranchisePanel.redo` | same as `push` | same as `push` |

No widget, label, layout, preset or copy text changed.  Arena edits (IR place/activate, promote/demote,
coach fields, roster-page membership moves) are validated exactly as before, and their refusal text now
names the player record the codec could not read (core change).

## Core changes (not protected)

- `mod_editor/core/nfl2k5_save_rost.py` — `SaveRost._parse`: an in-arena college pointer that is off the
  college table is recorded in `SaveRost.unresolved_colleges` (`summary()['unresolved_colleges']`), not
  refused; per-player refusals are prefixed `<pool> player <index> at 0x<offset>: ...`; `decode()` no longer
  tries the outer wrapper's `ROST` magic as an inner header (that produced "unsupported ROST version 593952").
- `mod_editor/core/nfl2k5_practice_squad.py` — new `validate_save_edit(before, after, **options)`.
- `mod_editor/core/nfl2k5_franchise_save.py` — `FranchiseSave.write()` validates through
  `validate_save_edit(self.original, payload)`: the codec runs on the way out only when roster state changed
  since the load.
- `mod_editor/core/providers.py` — self-integrity pins for the three modules above re-synced with
  `python3 packaging/repin.py --apply`.  **Claude: a manifest regeneration is needed** for the pinned
  writers per the hotfix rules.

## Nothing to wire elsewhere

`update_check.py`, `packaging/release-allowlist.txt`, `mod_build.py`, presets and cave reservations are
untouched; no new files ship (the regression test is `tests/mod_editor/test_nfl2k5_franchise_schedule_college.py`).

# beta 63.1 Broadcast camera: the mount clears the near stands (2026-09-09)

Hotfix for maumau78's report on beta 63 ("on right side will clip over crowd and stadium structure"). The fix
is numbers only, inside `mod_editor/core/nfl2k5_camera.py` (`BROADCAST_VALUES`), with the proof tool, the
projection harness test, the regenerated proof JSON/PNG and the provider pin. No protected file changed. What
Claude must do, and what is deliberately left as a described change, follows.

## Required now: manifest regeneration

`mod_editor/core/nfl2k5_camera.py` is a pinned writer source and its bytes changed (three descriptor words:
the lens and the mount's x and y). `packaging/repin.py --apply` was run (`mod_editor/core/providers.py`).
`data/nfl2k5_cave_reservations.json` (manifest 29) still carries the beta-63 source fingerprint of the camera
module, so two cases of `tests/mod_editor/test_nfl2k5_cave_oracle.py` error with "stale reservation source:
mod_editor/core/nfl2k5_camera.py; regenerate manifest" (27 of 29 pass) until Claude regenerates the manifest the
usual way. The declared camera spans, sizes and allocation requests are unchanged (the descriptor is the same 80
owned RO bytes at the same address; 160 RX wrappers unchanged); both XBE gates were run against manifest 29 as
it is (ASTRA_REPORT.md has the outputs).

## Not in this hotfix: the complete fix is one owned setup callback (a later beta)

A constant-offset type-2 mount follows the ball across the field, so no set of numbers keeps the eye out of
every stadium's stands for balls near the near sideline: the follow itself is the root cause (native solver
`FUN_0005f760`, eye = clamped look-at + smoothed offset). The solver already clamps the eye each frame to a
per-camera box at camera+0x3C0 (min x, y, z) / +0x3D0 (max x, y, z); `FUN_00060090` resets that box to
+/-100000 (y >= 10) on every descriptor copy and then runs the descriptor's setup callback (+0x40), which is
exactly where the retail sideline template's `A40C0` caps the look-at height (`mov dword [ecx+0x3B4], 100.0`).
Nothing in retail writes the eye box, so the mechanism is free for a later beta:

1. Grow the camera owner's code request by 16 bytes (`CODE_SIZE` 160 -> 176) and assemble a fifth wrapper at
   `va + 160`: `mov dword [ecx+0x3B4], 100.0` (keep the retail cap), `mov dword [ecx+0x3D0], 5600.0`
   (eye max x: the mount never crosses the second level's front, 5821 cm in the Superdome, 5972 in Arizona,
   with a 2 m margin), optionally `mov dword [ecx+0x3C8], -5500.0` and `[ecx+0x3D8], 5500.0` (eye min/max z:
   never past the end line into the corner sections), `ret`.
2. Point the owned descriptor's +0x40 at that wrapper instead of `A40C0` (`broadcast_descriptor()` currently
   keeps the template's callback); the differing-dword pin in `test_nfl2k5_camera_broadcast.py` becomes
   `[0, 16, 24, 32, 48, 52, 64]`.
3. Budget fixture and both gates for the grown request; manifest regeneration; the pairwise matrix.

With the eye clamped, the look-at still follows the ball, so the shot pans instead of dollying into the seats
when a play goes to the near sideline, as a television camera does. The alternative structural change, the
retail director's own type-1 record (fixed world eye, lens = distance x K / framing word, i.e. auto-zoom), is a
different look and is not proposed for a hotfix.

# beta-63.1 catch-slider kick return fix (2026-09-09)

The fix is implemented in `mod_editor/core/nfl2k5_catch_slider.py`. The
existing Build/throw-tuning dispatch already applies it, including the
boot-logo relocation. No dispatcher, preset, panel, release allowlist, or
allocator request change is needed. `packaging/repin.py --apply` updated the
writer's integrity pin in `mod_editor/core/providers.py`.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` after
integration. The 48-byte main cave remains `0x10A10..0x10A40`; its team load
now jumps to a 22-byte selector at `0x10CAC..0x10CC2`, the unused tail of the
same boot-logo bitmap. `_sites()` declares `kick_gate` with its full retail
pin. Regeneration must record that span for `nfl2k5_catch_slider`, the changed
main-cave bytes, the writer/provider source digests, and the rebuilt image
digests. The source writer digest for this delivery is
`0ea12e1f558463538a154f50c38036389a8c0432c7ba55ac2862cd706b85498f`.
Do not hand-edit just the JSON source hash: the observed spans and image
receipts also change. No named grown-page allocation is added.

Use the normal full disposable-disc manifest command, with
`HF63_MANIFEST_WORK` naming an existing writable disposable directory outside
the repository with room for the disc copy:

```sh
PYTHONPATH=. python3 tools/nfl2k5_cave_oracle.py manifest \
  '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir "$HF63_MANIFEST_WORK" \
  --json data/nfl2k5_cave_reservations.json
```

The checked-in manifest was deliberately left untouched in this worktree,
as required by `HOTFIX_CONTEXT.md`. The new header-specific reference test
checks existing ownership and native references independently; both normal
XBE gates are also run. Full evidence and Noah's xemu witness are in
`ASTRA_REPORT.md`. Rebuild old beta-63 catch-slider installations from retail:
they are foreign to the fixed writer; exact new installations replay with
zero changed bytes.

# r65 Player abilities rules v2 (2026-09-08)

This section supersedes earlier abilities v1 wiring only. EXPERIMENTAL /
UNWITNESSED. The existing owner is upgraded, not duplicated. Its live request
is `("nfl2k5_abilities_runtime", "code", 1344, 16)` within its 1536-byte budget;
no RW/RO request or new page. Both shared unions and all existing manifest
owner lists already import this same owner and its live REQUESTS. The budget
fixture and both gate assertions are updated in this delivery.

The new page, writer, codec, native effects and tests are implemented. These
protected product connections are deliberately left for Claude. Do not call
the feature witnessed or silently upgrade an installed v1 allocation. Rebuild
from the supported base. The production reservation JSON still needs Claude's
normal regeneration; the scratch proof manifest is explicitly XBE-only.

## Dispatcher and all four status dictionaries

In `mod_editor/core/nfl2k5_throw_tuning.py`, retain the existing
`abilities_patch` import. Add these explicit keyword arguments to `_apply_all`,
`write_xbe_copy`, and `write_image_copy` and forward them through both direct
and final deferred calls:

```python
abilities_lock_right_stick: bool = True,
abilities_lock_special_moves: bool = True,
abilities_lock_speedster: bool = True,
```

Validate strictly with `abilities_patch._locks(lock_right_stick=...,
lock_special_moves=..., lock_speedster=...)` alongside the existing week
validation. Keep disabled parent settings, including False lock choices, in
the plan; they select no owner by themselves. `abilities_off_week` still
requires `abilities=True`.

Extend `_abilities_adapter.__init__` to take `off_week` and all three Boolean
locks, store `self.settings` with the runtime key names, and implement:

```python
def apply(self, payload):
    return abilities_patch.apply(payload, **self.settings)
```

Keep its existing strict `status`. The `_apply_all` owner tuple immediately
after allocator reservation is:

```python
(abilities,
 _abilities_adapter(abilities_off_week, abilities_lock_right_stick,
                    abilities_lock_special_moves, abilities_lock_speedster),
 "abilities_patch", "experimental player abilities rules v2"),
```

`_selected_space_requests` and `_xbe_space_adapter` already select
`abilities_patch.REQUESTS` only when `abilities` is true. Retain those paths;
the lock values do not create separate requests. The initial image pass still
defers `abilities=False, abilities_off_week=None` with the other grown owners;
retain the three chosen locks for the final pass. Do not allocate v1 size 1072
or take settings from a previous arbitrary image.

All FOUR result/status dictionaries must retain `**_grown_status_fields(...)`:
`read_xbe(payload)`, `read_image(payload)`, `write_xbe_copy(result)`, and
`write_image_copy(after)`. That helper already returns
`abilities=abilities_patch.status(payload)` and
`abilities_settings=abilities_patch.read_settings(payload)`. The latter now
contains `model_version=2`, the off-week, and `lock_right_stick`,
`lock_special_moves`, `lock_speedster`. Preserve the nested settings rather
than converting an unchecked lock into a false "retail" owner status. On
source inspection, restore all three actual stored values to Build controls.

## BuildPlan and presets

In `mod_editor/core/mod_build.py`, change the existing abilities comment to v2
and add the three fields above beside `abilities_off_week`. Basic
(`softdrink_basic`), Advanced (`softdrink_advanced`) and Experimental
(`softdrink_experimental`) all keep `abilities=False`, off-week None, and all
three lock values True. No preset auto-assigns any player or changes a tier.
Validate the three Booleans during normalization. Do not count locks alone as
an operation or force abilities on merely because a settings value is True.

Forward all three settings in the final `tt._apply_all` call where
`abilities=plan.abilities, abilities_off_week=plan.abilities_off_week` already
appear. Keep the initial `tt.write_image_copy` abilities deferral and the
complete `_selected_space_requests` union. `available_options`, inspect's
`abilities`/`abilities_settings` pair, XBE growth handling and receipts use
the existing owner and need no second Boolean feature. Build continues to
consume ordinary `BuildPlan.roster_edits` for exported footer edits.

## Rosters page and shared undo

In protected `mod_editor/gui/roster_editor_panel_qt.py`, import
`AbilitiesPanel` from `mod_editor.gui.abilities_panel_qt`. Replace the old
abilities controls in `_build_abilities_page` with this page, inside a
resizable `QScrollArea` like the card pages. Keep the Guardian cap controls
from the old page in a separate group on that same scroll host. The Guardian
toggles and their existing masked transaction remain independent.

Create `self.abilities_panel`, call `set_document(document)` on every load or
replacement (including `_restore_composed`), and call `set_player(player)` in
`_show_player`, including None. Remove the old ability-check loop and
`ability_bulk_button` references there. Do not run a tier assignment on load.
Overfull legacy records show their existing flags until the user chooses a
tier. Native v2 honors tier0 legacy permissions; overfilled tiers 1..3 receive
no stored permissions/bonuses until corrected.

Connect `edit_committed` to the parent chronological undo stack. The emitted
`AbilitiesEdit` has ALREADY applied its change and contains `label`, exact
`receipt`, and guarded `undo`/`redo` callables. Call `_after_edit` for each
changed player and push ONE `UndoEntry` for the transaction. Wrap replay
callables with the same dirty/grid/status refresh. Do not invoke the apply
again when adding history. `set_document` must also be called when another
page restores a composed document. For replay after that replacement, resolve
the receipt against the current document using
`nfl2k5_abilities_editor.apply_plan(self.document, edit.receipt["plan"],
reverse=True/False)` rather than a callback closed over the replaced document.
Clear the shared stack on a new source, as today. Identity/mask checks must
remain enabled; never fall back to an unchecked whole-record restore.

Retire the old raw `set_abilities` bulk path or route it through a prevalidated
v2 plan. The new page offers the reviewed full-league assignment; every
transaction has a receipt and joins the same undo stack. Existing CSV and
sparse JSON use the compatible footer fields; CSV now also carries the named
`ability_tier`. Signed-save editing uses the existing codec, not a new save
footer or output format. The cosmetic `star_tag` stays independent, and the
existing `player_star` patch draws it as before. There are no new tier decals.

Expose the page's `save_receipt(path)` via the parent save-dialog action if
desired; it writes a new JSON and refuses replacement. The authoring CLI
outputs an envelope with `receipt` and `roster_edits`: extract `roster_edits`
as a normal roster-edits JSON before selecting it in Build. The ordinary
Rosters export already writes this compatible JSON directly.

## Lock controls, Gameplay Patches and Build tab

Forward the page's `lock_settings_changed(dict)` through a new Rosters signal
to the Build panel in protected `studio_qt.py`. Map runtime keys to plan keys
by prefixing `abilities_`. The signal changes pending Build settings only;
the existing `abilities` opt-in remains the enable switch. Reflect Build
inspection/restoration back through `AbilitiesPanel.set_lock_settings` (which
emits no signal), including explicit False values. Preserve choices across
source selection and parent option toggles; a rebuilt disc is required.

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, update the existing
PATCHES row's title to `Player abilities rules v2 (experimental)` and use
`tt.abilities_patch.HELP_TEXT`. It contains both required words "Retail" and
"Patch" and names the carrier-only charge consequence. Keep `abilities` in
`NEEDS_IMAGE`. The three switches are settings for this row, not three
independent patch owners. If this panel exports option dictionaries, preserve
all three `abilities_lock_*` values when merging with Build choices.

In protected `mod_editor/gui/build_panel_qt.py`, update the existing `_option`
caption to `Player abilities rules v2 (experimental)` (39 characters, under
60), retaining `needs_image=True` and the EXPERIMENTAL / UNWITNESSED badge.
Keep the existing Week 1..18 chooser. Add three checkboxes initialized True:

```text
Lock right-stick moves behind the ability
Lock special moves behind their abilities
Lock Speedster speed
```

Put them beside the existing ability controls and explain that both move
locks off restores retail charge, while either one on retains v1's restricted
charge policy. Include them in plan construction, project/settings save/load,
source-state restore and preset reset. Disable their widgets with the parent
off without resetting their choices. Build-to-Rosters synchronization must
not recursively emit change signals.

## Packaging, runtime closure, capability registry and release checks

Keep all existing abilities/runtime/assembler allowlist lines. Add these exact
lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_abilities_editor.py
mod_editor/gui/abilities_panel_qt.py
```

If release evidence JSONs are included in the current packaging policy, also
include `docs/mod_editor/nfl2k5_abilities_editor_capability.json`; do not bundle
the private retail receipt, XBE, report-inventory JSON, or scratch manifest.

In protected `packaging/check_2k5_mod_studio_runtime.py`, add imports
`mod_editor.core.nfl2k5_abilities_editor` and
`mod_editor.gui.abilities_panel_qt` to the closure. The runtime and generated
code module are already imported. The new editor depends only on the shipped
roster codec/runtime and stdlib; the page uses the existing PyQt5 dependency.
Recompute the unified provider hashes for the changed core modules and add the
new page/editor dependency if the provider closure enumerates them. Regenerate
counts rather than copying historical pin numbers into release tests.

Replace registry row `nfl2k5.gameplay.abilities_runtime` from
`docs/mod_editor/nfl2k5_abilities_runtime_capability.json` and add
`nfl2k5.rosters.abilities_v2` from
`docs/mod_editor/nfl2k5_abilities_editor_capability.json`, sorted by ID. These
use existing `gameplay_tuning_sliders` and `players_rosters` surfaces. Both
backend and validation commands use `python3 -m <dotted.module>`. They claim
offline writer proofs and untested gameplay, with no default enablement.

Claude's final integration checks: regenerate the protected production cave
manifest from the final sources when the disposable-disc disk budget permits;
run both XBE gates with that manifest, the oracle/owner manifests, standalone
abilities/roster/Qt/Momentum suites, the pairwise matrix, packaging closure and
capability registry file checks. Verify a rebuilt configured XBE reports v2
and all three chosen lock values. Follow Noah's exact gameplay list in
`ASTRA_ABILITIES_V2_REPORT.md` before declaring anything witnessed.
# r65 Deep-zone facing and press bail (2026-09-08)

EXPERIMENTAL / UNWITNESSED. This implementation supersedes the two deferred
implementation rows in the historical `nfl2k5_zone_facing` audit. That audit
remains read-only. See `ASTRA_DEEP_ZONE_TIERS_V2_REPORT.md` for native evidence,
limits and Noah's witness list. All protected files remain untouched here.

## Dispatcher and receipts: nfl2k5_throw_tuning.py

Import `nfl2k5_deep_zone as deep_zone_patch`. Add Boolean kwargs
`deep_zone_facing=False, deep_zone_bail=False` to `_apply_all`, `apply_to_xbe`,
`apply_to_xiso`, `_validate_r62_options`, `_selected_space_requests` and
`_xbe_space_adapter`. Put both names in `R62_SPACE_KEYS` and `R62_RUNTIME_KEYS`;
forward them through `_r62_options`, `_r62_space_options` and every selected
request call, including music's final allocation path. Require exact bools.
Either True selects `deep_zone_patch.REQUESTS` ONCE and forces the v3 allocator.
Both False select no owner. Preserve both flags in the final pass and clear both
in `_deferred_r62_options` for the initial fixed-size pass.

Use this settings adapter; its status must reject an installed opposite tier
combination instead of silently treating it as the requested build:

```python
class _deep_zone_adapter:
    def __init__(self, facing, bail):
        self.settings = dict(facing=facing, bail=bail)

    def status(self, payload):
        state = deep_zone_patch.status(payload)
        if state == "applied":
            have = deep_zone_patch.read_settings(payload)
            if any(have[k] != v for k, v in self.settings.items()):
                raise ValueError("Different deep-zone tiers; rebuild from base")
        return state

    def apply(self, payload):
        return deep_zone_patch.apply(payload, **self.settings)
```

Add this tuple to the final owner loop AFTER the allocator entry:

```python
(deep_zone_facing or deep_zone_bail,
 _deep_zone_adapter(deep_zone_facing, deep_zone_bail),
 "deep_zone_patch", "deep-zone corner tiers (experimental)"),
```

Include either flag in the allocator-entry condition and the two entry-point
"at least one patch selected" checks. Defaults at the direct owner API select
both tiers; the dispatcher MUST pass both Boolean settings explicitly. Omitted
owner API settings preserve an already-installed variant. Never call the owner
with both False. Rebuild from base to disable or change an installed variant.

In `_grown_status_fields`, add `deep_zone_settings` and the component keys
`deep_zone_facing` / `deep_zone_bail`. First call `status`; on `foreign`, report
all three as foreign (settings as `{status: 'foreign'}`), since `read_settings`
raises on foreign input. Otherwise call `read_settings` once. A component is
`applied` only if installed and its setting is True, otherwise `retail`.
The four status dictionaries using this helper MUST receive the fields:
`inspect_xbe` (`payload`, currently near 665), `inspect_xiso` (`payload`, near
794), the standalone XBE result (`result`, near 1791), and the XISO result
(`after`, near 2136). Include the fields in the accepted inspector/result keys
in `mod_build.py`. Preserve `experimental=True, runtime_witnessed=False`.

The small QB-spy dependency validator change is included in this delivery.
Install it with this owner: both owners verify the complete partner context
through a bounded, nonrecursive validation path. No runtime Spy bytes changed.

## BuildPlan, PLAY staging and final pass: mod_build.py

Add `deep_zone_facing: bool = False`, `deep_zone_bail: bool = False` and
`deep_zone_bail_calls: tuple = ()`. Each explicit staged bail call contains a
logical PLAY asset selector plus `formation_index`, `front_play_index` and
`coverage_play_index`, resolved against the user's current source. Include both
flags in `wants_xbe_patch`, recipe serialization, availability, project restore,
and final allocation need. Basic=False, Advanced=False, Experimental=False for
BOTH. Do not auto-enable with zone-drop, Coverage, catch or coverage-trail.

Normalization requires exact bools, unique selected asset/coverage-row pairs,
and `deep_zone_bail=True` when authoring calls are present. Force `xbe_space=True`
for either flag. The runtime bail option can also serve an already-authored
press call; an empty authoring selection means no PLAY changes. Show that fact
in the build review. These flags do not imply each other or the older cap.

For selected authoring calls, resolve one bounded PLAY resource at a time via
the existing asset service. After other formation/play authoring, call
`nfl2k5_deep_zone_bail.apply(resource, formation_index=..., front_play_index=...,
coverage_play_index=..., asset_id=...)`. Stage its replacement using the existing
fixed-span PLAY/archive writer and retain its exact compiler receipt. Its
selected coverage row changes at all of its existing formation links; display
`affected_formations`. Different linked formation lanes refuse. Never loop over
all calls or patch shared nodes directly. Surface compiler refusal before a
build. No whole pack or disc read is permitted.

Clear both XBE flags in the initial deferred build call (the `replace(plan,
...)` near 1255 and the initial XISO adapter), while preserving staged PLAY
edits. Forward both true effective values through the final `_apply_all` call,
selected union/music allocation and grown owner/result pass (near 1578,
1618-1642 and 1716). Include them in the condition deciding that the final pass
is needed. A bail-only build must install its runtime as well as selected PLAY
edits; facing-only builds require no PLAY edits.

## Protected GUI surfaces

`gameplay_patches_panel_qt.py`: import the owner's captions/help and add:

```python
("deep_zone_facing", "Deep-zone QB facing (experimental)",
 "Retail: corners can turn to run. Patch: try a slower QB-facing deep drop until a pass, run, or the selected receiver gets beyond the corner. EXPERIMENTAL / UNWITNESSED."),
("deep_zone_bail", "Press corner bail (experimental)",
 "Retail: the selected call keeps its starting alignment. Patch: use a selected three-deep press start and directional bail. Ends at seven yards when used alone. EXPERIMENTAL / UNWITNESSED."),
```

Add BOTH keys to `NEEDS_IMAGE`, availability, checked-value forwarding, recipe
restore and reset loops. Keep `zone_drop_cap` as its independent checkbox.
Selecting bail alone does not secretly author every play. The play designer's
selected front/coverage pair can stage an explicit `deep_zone_bail_calls` row;
review its affected formation links. Disable staging when native personnel or
coverage validation refuses. Do not promise match quarters or exact eye tracking.

`build_panel_qt.py`: add `_option` rows named `deep_zone_facing` and
`deep_zone_bail` with captions `Deep-zone QB facing (experimental)` (34 chars)
and `Press corner bail (experimental)` (32 chars). Both are under 60 characters.
Use the same help, default False, enable-on-source behavior, plan construction,
restore/preset/reset lists and work-present check. `studio_qt.py` and
`gameplay_panel_qt.py`: forward both flags and explicit authoring selections
through existing feature-routing/project plumbing; no extra window is required.

## Packaging, capability and release validation

Add these exact `packaging/release-allowlist.txt` lines:

```text
mod_editor/core/nfl2k5_deep_zone.py
mod_editor/core/nfl2k5_deep_zone_code.py
mod_editor/core/nfl2k5_deep_zone_bail.py
docs/mod_editor/nfl2k5_deep_zone_capability.json
```

Add runtime-closure imports in `packaging/check_2k5_mod_studio_runtime.py`:

```text
mod_editor.core.nfl2k5_deep_zone
mod_editor.core.nfl2k5_deep_zone_code
mod_editor.core.nfl2k5_deep_zone_bail
```

Their existing transitive closure must include `nfl2k5_xbe_space`,
`nfl2k5_rdata_sites`, `nfl2k5_cave_oracle`, `nfl2k5_zone_drop`,
`nfl2k5_qb_spy_runtime`, `nfl2k5_dynamic_kickoff`,
`nfl2k5_formation_play_writer`, `nfl2k5_play_codec`,
`nfl2k5_play_library`, `nfl2k5_playbook_inspector` and `nfl2k5_playbook_pack`.
Capstone, Unicorn and GNU as remain development-only. Standard-library-only
runtime imports do not load private game data.

Merge `docs/mod_editor/nfl2k5_deep_zone_capability.json` by its id
`nfl2k5.gameplay.deep_zone_tiers` into the release capability registry. It has
schema-valid module commands for writing and validation, opt-in settings and an
explicit not-tested gameplay runtime status. Retire any product presentation
that describes the historical audit as the available implementation of these
tiers. Keep its read-only audit command available for historical evidence.

The allocator stack, budget fixture, both gates and manifest builder lists are
already updated here. Regenerate the protected production manifest with
`tools/nfl2k5_cave_oracle.py manifest` after all shared wiring lands. This session
uses a scratch source-pin refresh and exact gate allocation projection, not a
new disc-build manifest. `df -h /` reported 98G free initially and 92G during the
final audit. No disposable disc was created, preserving the remaining headroom.
Release CI/update-check
and tag files need no feature change; run the existing release checks after the
shared integration and production manifest regeneration.

---

# r64 Read option v4 engagement diagnostic (2026-09-08)

EXPERIMENTAL / UNWITNESSED. This section supersedes the v3 claim of live
engagement. Noah played bm and reported no handoff or apparent change; no EDGE
cue was reported. The new native READ line is an engagement probe. The requested
cancelable animated handoff and new controls remain conditional on a live
engagement witness, as required by the brief. See
[ASTRA_READ_OPTION_V4_REPORT.md](ASTRA_READ_OPTION_V4_REPORT.md).

## Instrumented build decision

Keep normal v3 installation byte-identical. All presets retain the existing
runtime opt-in default of False. The owner now accepts `diagnostic=True` for
an explicitly instrumented build, reports `model_version=4, diagnostic=True`,
and recognizes both exact variants for replay. An omitted mode preserves an
already installed variant. Switching variants requires rebuilding from the
supported source. It is not an in-place upgrade of bm.

The native-font diagnostic fits the unchanged **2048 RX / 256 RW / 88 RO**
reservation, with 1928 generated code bytes and 120 padding bytes. To fit that
budget it replaces the normal EDGE marker and CPU edge resolver. **Use a human
QB for this witness; CPU diagnostic reads give.** Human v3 timing, input,
condition dispatch and native give/keep/pass outcomes are retained. The option
pack, five-node script geometry, two-entry table schema and native speed-option
recipes are unchanged, preserving comparison with bm.

For Claude's one instrumented build, use this scoped adapter around the existing
synchronous BuildPlan build. It is tested against the existing real adapter;
it requires no protected source edit or new GUI flag. `plan` is Claude's usual
candidate plan containing the option pack and final-book pairing settings.

```python
from dataclasses import replace
from unittest.mock import patch
from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_read_option_runtime as read_option

original_apply = read_option.apply

def instrumented(payload, **kwargs):
    return original_apply(payload, diagnostic=True, **kwargs)

with patch.object(read_option, "apply", instrumented):
    receipt = mod_build.build(replace(plan, read_option_runtime=True), progress)
```

The adapter patch is scoped to one dedicated build process and restored on every
exit. Use the existing final pass after position pools and depth roles; do not
compile from the seed fixture or replace an installed v3 owner. Read back the
actual disc XBE with the existing bounded XDVDFS reader and require:

```python
settings = read_option.read_settings(actual_xbe)
assert settings["model_version"] == 4 and settings["diagnostic"] is True
assert settings["authored_reads"] == 2
assert settings["runtime_witnessed"] is False
```

Also require the final pairing receipt to name MIN 155/157, retain the real
64-byte table hash, and record `read_option.allocations(actual_xbe)` for the RW
memory capture. Do not infer that the diagnostic was installed merely from the
"Final playbooks paired" summary. Give Noah `DIAGNOSTIC_HELP_TEXT` and the report's
photograph list with that build. This session did not build or retain a disc.
A temporary acceptance build must be inside `TemporaryDirectory`, check `df -h /`
first and leave more than 100 GB free after its maximum expected growth.

For a development XBE only, the equivalent existing module command is:

```text
python3 -m mod_editor.core.nfl2k5_read_option_runtime apply source.xbe --output new-diagnostic.xbe --table final-intent.bin --diagnostic
python3 -m mod_editor.core.nfl2k5_read_option_runtime status new-diagnostic.xbe
python3 -m mod_editor.core.nfl2k5_read_option_runtime state captured-owner-rw-256.bin
```

The last command decodes exactly one 256-byte memory dump; an installed XBE's RW
bytes are initial zeros and are not a runtime dump. Neither CLI operation writes
back a running game. Addresses are taken from that build's allocation receipt,
not assumed from bm or the test union.

## Protected integration contract

No protected implementation file was edited. Retain the existing import
`nfl2k5_read_option_runtime as read_option_patch`, kwargs
`read_option_runtime=False`, `read_option_intent_table=None`, validation and
forwarding in `mod_editor/core/nfl2k5_throw_tuning.py`. Its current adapter is:

```python
class _read_option_adapter:
    def __init__(self, table):
        self.table = table
    status = staticmethod(read_option_patch.status)
    def apply(self, payload):
        return read_option_patch.apply(payload, intent_table=self.table)
```

Keep this `_apply_all` tuple after the allocator:

```python
(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
```

`_selected_space_requests` and `_xbe_space_adapter` still reserve the same
`read_option_patch.REQUESTS` when selected. The scoped build above supplies the
new owner kwarg `diagnostic=True`; do not hard-code it in the normal dispatcher.
No new public dispatcher kwarg is needed for this one witness build.

Retain these `_grown_status_fields` entries, expanded in **all four** dictionaries
in `read_xbe`, `read_image`, `write_xbe_copy`, and `write_image_copy`:

```python
"read_option_runtime": read_option_patch.status(payload),
"read_option_runtime_settings": read_option_patch.read_settings(payload),
```

The settings must report actual bytes: version 3/diagnostic False for normal,
version 4/diagnostic True for the probe, plus authored count, table hash and
`runtime_witnessed=False`. The build receipt already receives those values.

In `mod_editor/core/mod_build.py`, keep
`BuildPlan.read_option_runtime: bool = False`; **Basic, Advanced and Experimental
all leave it off**. Preserve Boolean normalization, early-pass deferral, final
pairing after position/depth rewrites, refusal of an empty authored table,
`read_option_intent_table=read_table` in the final pass and its count receipt.
Do not add a separate BuildPlan diagnostic field or change presets.

Retain the Gameplay Patches `PATCHES` row (currently supplied by
`mod_editor/gui/beta62_options.py`) and its `NEEDS_IMAGE` membership:

```python
("read_option_runtime", "Read option mesh controls (experimental)",
 tt.read_option_patch.HELP_TEXT),
```

`HELP_TEXT` still contains **Retail** and **Patch**, describes intended normal
v3 controls, and now explicitly records that Noah's v3 play test showed no
handoff and live engagement is unconfirmed. `DIAGNOSTIC_HELP_TEXT` also contains
Retail/Patch and explains the native line, retained v3 human controls and CPU
limitation. The protected Build tab `_option` keeps caption
`Read option mesh controls (experimental)` (40 characters, below 60), False and
the same HELP_TEXT. No other GUI panel changes are requested.

Retain these exact protected allowlist lines:

```text
mod_editor/core/nfl2k5_read_option_runtime.py
mod_editor/core/nfl2k5_read_option_runtime_code.py
mod_editor/core/nfl2k5_play_library.py
mod_editor/core/nfl2k5_playbook_pack.py
mod_editor/core/nfl2k5_play_intents.py
data/playbooks/softdrink_option.2k5book
docs/mod_editor/nfl2k5_read_option_runtime_capability.json
```

Retain these runtime-closure imports in
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_read_option_runtime",
"mod_editor.core.nfl2k5_read_option_runtime_code",
"mod_editor.core.nfl2k5_play_library",
"mod_editor.core.nfl2k5_playbook_pack",
"mod_editor.core.nfl2k5_play_intents",
```

The template contains both variants; GNU as, Capstone, Unicorn and test helpers
remain development dependencies. No new shipped module or public surface needs
an allowlist entry. Merge the revised capability document
`docs/mod_editor/nfl2k5_read_option_runtime_capability.json` into existing ID
`nfl2k5.gameplay.read_option_runtime`, surface `gameplay_tuning_sliders`. Retain
`runtime.status=not-tested`, explicit opt-in and the module-form backend command.
Its validation command is now
`python3 -m tests.mod_editor.test_nfl2k5_read_option_diagnostic`. This is an update
to the existing capability, not a new registry entry or a live success claim.

## Manifest and gate handoff

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` using the
real `tools/nfl2k5_cave_oracle.py manifest` after merging. Existing owner union
and all three manifest owner lists already contain this owner; sizes, hooks and
capacities have not changed. For normal builds its generated v3 bytes remain
exactly the same. A diagnostic manifest run can use the same scoped adapter
above in a dedicated process around `build_manifest` to observe that variant.

Disk headroom prevented a full disposable disc copy while preserving 100 GB.
The local scratch manifest is explicitly **test-only ownership revalidation**,
not a new disc build. Its standalone generator verifies all other source pins,
executes the hash-pinned base v3 writer and the current normal writer against
both empty and paired tables in two allocation layouts, requires byte identity,
and checks that diagnostic differences normalize exactly to normal by restoring
only this owner's code/table/hooks and recomputing existing seals/digests. It
retains historical disc fields as labeled inherited evidence. It refuses drift
in any other owner or a changed hook/budget. The oracle's source-freshness and
reservation checks remain enabled. Do not copy this scratch artifact into the
release manifest or report it as a disc build.

```text
NFL2K5_READ_OPTION_V4_MANIFEST=.scratch/read-option-v4/manifest.json python3 tests/mod_editor/test_nfl2k5_read_option_diagnostic_manifest.py
NFL2K5_CAVE_MANIFEST=.scratch/read-option-v4/manifest.json python3 tests/mod_editor/test_xbe_patch_memory_writes.py
NFL2K5_CAVE_MANIFEST=.scratch/read-option-v4/manifest.json python3 tests/mod_editor/test_xbe_patch_cave_references.py
NFL2K5_CAVE_MANIFEST=.scratch/read-option-v4/manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
```

The safety gates explicitly compose the diagnostic in both installation orders,
including scale-out. Their shared `compose` helper defaults to normal v3 for
other callers. No cave exemption, allocation increase, canonical fingerprint
edit, version change or release-test change is part of this work.
# r64 Defender circling integration (2026-09-08)

EXPERIMENTAL / UNWITNESSED. New independent Boolean `coverage_trail`.
**Opt-in, False in Basic, Advanced and Experimental.** The native close-pursuit
orbit is reproduced; the full reported man-coverage failure and rendered pivots
are not established. This is the brief's explicit fallback when proof is not
clean. See [ASTRA_DEFENDER_CIRCLING_REPORT.md](ASTRA_DEFENDER_CIRCLING_REPORT.md).
This section is additive; the other jobs' instructions below still apply.

## Dispatcher, allocator and all four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`:

```python
from . import nfl2k5_coverage_trail as coverage_trail_patch
```

Add a keyword `coverage_trail: bool = False` to `_apply_all`, `write_xbe_copy`
and `write_image_copy`. Validate it with `_validate_lever_flags` before writes;
include it in both writers' nonempty-selection checks. Forward it through every
call, including the deferred image pass and the final call after growth.
This owner takes no settings adapter.

Add keyword `coverage_trail=False` to `_selected_space_requests` and
`_xbe_space_adapter.__init__`, pass it through the adapter, and append
`coverage_trail_patch.REQUESTS if coverage_trail else ()` to the request union.
Forward it to `_defensive_try_adapter` as well: that earlier adapter can be the
first allocator caller. Include it in all allocation-needed predicates and
`extra_requests` unions used for deferred music/arena growth. Every first
allocation must reserve the complete selected union, even when only this new
option is selected. Do not append a reservation after another owner allocates.

In `_apply_all`'s final owners tuple, **after the allocator entry**, add:

```python
(coverage_trail, coverage_trail_patch, "coverage_trail_patch",
 "Close pursuit recovery (experimental)"),
```

Add this field to `_grown_status_fields(payload)`:

```python
"coverage_trail": coverage_trail_patch.status(payload),
```

Retain/verify the helper expansion in each of these four returned dictionaries:

| Function | Bytes supplied to `_grown_status_fields` |
| --- | --- |
| `read_xbe` | `payload` |
| `read_image` | `payload` |
| `write_xbe_copy` | `result` |
| `write_image_copy` | `after` |

The values are exactly `retail`, `applied`, or `foreign`. The receipt key is
`coverage_trail_patch`. Do not present an already patched input as retail when
the flag is disabled; opting out means rebuilding from a supported base.

## BuildPlan and presets

In protected `mod_editor/core/mod_build.py`, add
`BuildPlan.coverage_trail: bool = False`. Set `coverage_trail=False` explicitly
in **all three** preset dictionaries. Add it to selection detection,
normalization, Boolean validation, feature/module availability checks and the
list of deferred grown owners. Set it False in the early-pass `replace(...)`;
include the original value in the final union and final `_apply_all` call.
It can independently request allocator growth. Existing acceleration, coverage,
momentum and zone options keep their selected values; this flag requires none
of them. Include the actual receipt in the build summary.

## Gameplay Patches, Build controls and retail opt-out

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, add this PATCHES
row and add `coverage_trail` to `NEEDS_IMAGE`:

```python
("coverage_trail", "Keep the retail coverage pursuit",
 tt.coverage_trail_patch.HELP_TEXT),
```

This row is an **inverse checkbox**: checked means `coverage_trail=False`;
unchecked means `coverage_trail=True`. Invert the UI value on initialization,
preset load, settings load, status display, selection collection and save.
Store only the canonical positive Boolean, never a second persistent retail
flag. Default the retail checkbox to checked in every preset. Use the existing
image requirement and foreign-state refusal. Do not accidentally pass its raw
`isChecked()` value to the writer. Add this sentence to the row's help:
"Uncheck to try the recovery. Rebuild from your base to switch back."

`HELP_TEXT` is the exact new module constant. It contains the required words
**Retail** and **Patch**, the EXPERIMENTAL / UNWITNESSED label, the three-yard
scope, stationary arrival, preserved mistakes/special animations and the
unproved man-coverage/rendered behavior. Do not advertise a confirmed universal
DB circling fix.

In protected `mod_editor/gui/build_panel_qt.py`, add the ordinary positive
Build option, initially False:

```python
self.coverage_trail_check = self._option(
    g, "coverage_trail", "Close pursuit recovery (experimental)",
    tt.coverage_trail_patch.HELP_TEXT, needs_image=True)
```

The caption is 37 characters, below 60. Include the control in preset/status
updates, enablement, plan serialization and the nonempty-build predicate;
construct the plan with
`coverage_trail=self.coverage_trail_check.isChecked()`. Synchronize both panels
through that same canonical Boolean. Shared forwarding in other protected GUI
panels must carry that field if they construct plans or writer kwargs.

## Packaging, registry and release manifest

Add these exact allowlist lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_coverage_trail.py
mod_editor/core/nfl2k5_coverage_trail_code.py
docs/mod_editor/nfl2k5_coverage_trail_capability.json
```

Add these runtime-closure imports to protected
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_coverage_trail",
"mod_editor.core.nfl2k5_coverage_trail_code",
```

Their existing transitive helpers are `nfl2k5_gameplay_lever`,
`nfl2k5_xbe_space`, `nfl2k5_bump_strength`, and `nfl2k5_cave_oracle`; retain that
existing closure. The assembler, GNU as, Capstone, Unicorn and frame receipts
are development/evidence dependencies, not product runtime requirements.

Merge the schema-valid object in
`docs/mod_editor/nfl2k5_coverage_trail_capability.json` into the registry, sorted
by ID `nfl2k5.gameplay.coverage_trail`. It uses existing surface
`gameplay_tuning_sliders`, classification `offline-writer-proved`, GUI default
False and runtime status `not-tested`. Its actual new-file CLI is:

```text
python3 -m mod_editor.core.nfl2k5_coverage_trail --xbe source.xbe --apply --output new-coverage-trail.xbe
python3 -m tests.mod_editor.test_nfl2k5_coverage_trail
```

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after all jobs and protected wiring merge.
The builder's imports, request union, recorder owner lists and dormant-owner
application are already changed here. Reserve 640 RX bytes aligned to 16,
zero owner RW/RO bytes, and the six-byte live hook at `0x2FC9F0`. Two immutable
floats are inside the RX reservation. Both gates use the actual sealed union
and a pinned test-only hook projection. The scratch oracle manifest retains
every original reservation and verified fingerprint, adding only this owner's
three source fingerprints; it is **not** a regenerated disc manifest and must
never replace the protected release artifact.

After wiring, run the preset/dispatcher/runtime closure checks and both XBE
gates with the regenerated manifest. Those product integration checks cannot
be claimed by this isolated owner handoff. Noah's played acceptance is listed
in the report.

# r64 Read option v3 integration (2026-09-08)

EXPERIMENTAL / UNWITNESSED. This section supersedes the v1/v2 read-option
window, fixed HUD anchor and geometry descriptions below. See
[ASTRA_READ_OPTION_V3_REPORT.md](ASTRA_READ_OPTION_V3_REPORT.md). All protected
implementation files remain unchanged. Existing integration already dispatches
this owner and imports its updated HELP_TEXT; no new option or surface is needed.

## Required integration changes

1. Regenerate protected `data/nfl2k5_cave_reservations.json` after merging all
   changes, using `tools/nfl2k5_cave_oracle.py manifest`. The tick hook moves
   from `0x1AF191` (9 bytes) to `0x1AF009` (10 bytes), and the new input-priority
   hook occupies `0x21516A` (6 bytes). Retain the other four hooks. The existing
   stack and manifest builder concatenate the owner's live REQUESTS and already
   include it in every installation, replay and recorder list. Its reservation
   stays **2048 RX / 256 RW / 88 RO**, all aligned to 16. Use the scratch manifest
   only as local test evidence; do not copy or hand-edit its fingerprints into
   the protected release artifact.
2. In `mod_editor/gui/create_play_wizard_qt.py`, the option geometry QLabel
   beginning near line 695 is outside this job's GUI ownership. Replace its
   existing text from `Speed option keeps stock supporting blocks.` through
   `enable the separate runtime controls.` with this exact text:

   ```python
   "Speed option keeps stock supporting blocks. With Read option mesh controls, "
   "the QB holds for one second and the back approaches beside him. Hold snap "
   "through the window to keep; release or do nothing to give. On an RPO, hold "
   "snap and press the named receiver to throw. Watch the edge marked by the "
   "snap-button icon. Without the runtime, these are experimental retail "
   "position-based recipes. Blocks and exchange animation need play tests."
   ```

   The authoring notice and saved pack already carry these controls. This
   removes the extra wizard label's stale claim that the held QB moves one
   yard sideways and three yards back. Do not change native formation slots,
   the conditional branch contract, or the fixed resource spans to fix text.
3. Merge the revised capability object in
   `docs/mod_editor/nfl2k5_read_option_runtime_capability.json` into the existing
   registry entry `nfl2k5.gameplay.read_option_runtime`. Keep surface
   `gameplay_tuning_sliders`, opt-in default, and `runtime.status=not-tested`.
   Its evidence includes the native frame suite; it does not claim played
   animation or collision evidence. No new capability entry is introduced.

## Dispatcher and status contract already present

Retain the import `nfl2k5_read_option_runtime as read_option_patch` in protected
`mod_editor/core/nfl2k5_throw_tuning.py`. `_apply_all`, its writers and forwarding
calls keep kwargs `read_option_runtime=False` and
`read_option_intent_table=None`, their Boolean/bytes validation, the existing
`_read_option_adapter(table)`, and this tuple after allocator installation:

```python
(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
```

`_selected_space_requests` and `_xbe_space_adapter` continue reserving
`read_option_patch.REQUESTS` when the flag is selected. Keep these two fields
in `_grown_status_fields(payload)`, expanded in **all four** status dictionaries
in `read_xbe`, `read_image`, `write_xbe_copy` and `write_image_copy`:

```python
"read_option_runtime": read_option_patch.status(payload),
"read_option_runtime_settings": read_option_patch.read_settings(payload),
```

Settings and receipts now report `model_version=3` and `mesh_seconds=1.0`.
`mesh_frames=61` describes nominal 60 Hz samples including the first sample;
expiry is determined by elapsed game time. Rebuild from a supported base with
the complete request union; installed v1/v2 owner bytes are not an upgrade base.

In protected `mod_editor/core/mod_build.py`, retain
`BuildPlan.read_option_runtime: bool = False`. Basic, Advanced and Experimental
all leave it **off**. Keep normalization, early-pass deferral, final pairing
**after position pools and depth roles**, the nonempty table refusal, the final
`read_option_intent_table=read_table` call, and the final playbook count summary.
The shipped pack still yields eight authored replacements and exactly two reads.

The Gameplay Patches `PATCHES` row comes from `mod_editor/gui/beta62_options.py`:

```python
("read_option_runtime", "Read option mesh controls (experimental)",
 tt.read_option_patch.HELP_TEXT),
```

Keep its `NEEDS_IMAGE` membership. HELP_TEXT includes both **Retail** and
**Patch**, the one-second window, hold/release/default-give controls, EDGE cue
and RPO receiver instruction. Protected Build tab `_option` keeps caption
`Read option mesh controls (experimental)` (40 characters), False by default,
and the same help text. Neither protected panel needs a new row or flag.

## Packaging closure already present

Retain these exact lines in protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_read_option_runtime.py
mod_editor/core/nfl2k5_read_option_runtime_code.py
mod_editor/core/nfl2k5_play_library.py
mod_editor/core/nfl2k5_playbook_pack.py
mod_editor/core/nfl2k5_play_intents.py
data/playbooks/softdrink_option.2k5book
docs/mod_editor/nfl2k5_read_option_runtime_capability.json
```

Retain these runtime-closure imports in protected
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_read_option_runtime",
"mod_editor.core.nfl2k5_read_option_runtime_code",
"mod_editor.core.nfl2k5_play_library",
"mod_editor.core.nfl2k5_playbook_pack",
"mod_editor.core.nfl2k5_play_intents",
```

The assembler and instruction tests remain development tools. The application
loads the generated template and needs no GNU assembler, Unicorn or Capstone.
No release-tag test, version, CI workflow or protected packaging source changed.

# r63 Discord bugs 1: protected integration handoff (2026-09-07)

**EXPERIMENTAL / UNWITNESSED. Protected files have NOT been edited.**
Base `1606ec9`, branch `astra/r63-discord-bugs-1`. See
[ASTRA_DISCORD_BUGS_1_REPORT.md](ASTRA_DISCORD_BUGS_1_REPORT.md).

The exact source edits are in
[`tests/fixtures/discord_bugs_1_wiring.patch`](tests/fixtures/discord_bugs_1_wiring.patch).
It is an unapplied unified diff, not a runtime patcher. Its six protected
source files remain byte-identical to the base. Claude can review it with
`git apply --check tests/fixtures/discord_bugs_1_wiring.patch` and integrate it
with the other sessions. The standalone
`QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_discord_bugs_1_wiring.py`
applies those exact hunks only to module source held in memory. It exercises the
resulting real classes/functions, with tiny fixtures and mocked native writers.
`ASTRA_TEST_UNWIRED=1` tests the original protected files and intentionally
fails on the still-missing integrations. This is not permission to ship unwired.

## Exact source changes in the proposed diff

1. **B3, `mod_editor/core/update_check.py`, `_is_newer`:** normalize both labels
   with `self_update.canonical_release_tag` before equality/numeric beta ordering.
   The known RC mappings come from the release notes, not a global arithmetic
   offset. Unknown labels keep the existing fallback. The running build constant
   remains `beta-62`; no release-tag tests or workflow are edited. The unprotected
   worker already normalizes its input, and `plan_update` now refuses a missing
   matching `.sha256` before enabling Update now. Keep the published beta identity
   as the authoritative shared-product version and extend the explicit alias map
   when a new unambiguous RC/beta pair ships. Do not map RC62 to one beta: it was
   shared by several APF releases.
2. **B7/B22, `build_panel_qt.py`:** delegate `project_build_settings` and
   `restore_project_build_settings` to the supplied `gameplay_project_ui.capture`
   and `restore`. These cover the existing BuildPlan recipe, typed levels,
   artwork families, files, star tags, playbook packs, commentary and description.
   No source/target/overwrite permission is serialized. Restoration blocks widget
   signals while replacing the choices; music preparation survives while disabled.
3. **B7/B22, `studio_qt.py`:** `_connect_gameplay_build` connects the actual Build
   and Game Fixes controls once both panels exist, regardless of construction
   order. `GameplayBuildLink` updates shared checks in both directions and also
   forwards levels, screen timing, Guardian practice choice and MyCareer path.
   The last user change wins. No patch command is emitted by synchronization.
   `observe_build_choices` captures other Build control edits. During source
   inspection/project restoration, `_restoring_music_playlist` suppresses capture;
   `_restore_music_build_settings` then refreshes Gameplay from the saved Build
   choices. Capture marks the workspace dirty and refreshes the footer.
4. **B22/B17, `studio_qt.py`:** the footer enables Make disc for a loaded source
   with project edits OR selected Build work. `_choose_build_output` routes such
   work to the single Build confirmation and operation; a blocker is displayed
   rather than ignored. Check my images retains its image-edit gate and existing
   explanation. A gameplay-only project has no image edits to inspect.
5. **B22/B12, `build_panel_qt.py`, `_include_session_project`:** include all staged
   shared-project edits whenever they exist, including portraits and uniforms,
   without requiring the unrelated music/naming checkboxes. The existing
   `_build_operation` checks that the source matches the open project, builds one
   verified temporary project copy, then patches that copy once. It measures the
   final output against the original source after the whole operation, so a
   changed portrait plus an otherwise unchanged patch pass is still a change.
6. **B9, `mod_build.py`, `build`:** after `_build` and playlist revalidation, but
   before publishing, attach `build_feedback.measure(original_source, candidate)`
   as `receipt['outcome']`. It hashes in 1 MiB blocks after all file/pack/XBE
   writers, and is independent of step labels. Identical output may be copied but
   is explicitly `unchanged`. Never turn a refusal into a successful outcome.
   `build_panel_qt.py::_done` and `gameplay_patches_panel_qt.py::_done` use
   `build_feedback.completion`: unchanged becomes "No changes written", and an
   old/unmeasured receipt becomes "Copy ready; changes not measured". Changed
   output alone earns "Disc ready". The receipt says steps checked, not that
   each listed step wrote bytes.
7. **B12, `studio_qt.py`:** include the text catalog's +0x06 selector as
   `photo_id` in `_player_asset_summaries`; label `photo_id` links as record links.
   Remove the obsolete claim that the roster has no portrait pointer.
   `nfl2k5_player_assets` now joins an explicit Photo ID before considering a
   legacy name fallback. The page still reads the loaded source catalog, not
   unsaved native roster edits; the native Rosters confirmation is authoritative
   for a changed selector. In `roster_editor_panel_qt.py::_after_edit`, show
   `rr.portrait_confirmation(self.document, player)` for `name == 'photo_id'`,
   including undo/redo. It names the numbered portrait and distinguishes a
   present, missing or unavailable catalog entry. This panel is left to Claude
   under the brief's other-GUI-panels restriction.

## Packaging and owner contract

Add these exact release-allowlist lines:

```text
mod_editor/core/build_feedback.py
mod_editor/gui/gameplay_project_ui.py
docs/mod_editor/discord_bugs_1_faq.md
```

In the protected runtime closure import list, add
`mod_editor.core.build_feedback` and `mod_editor.gui.gameplay_project_ui`.
The latter imports PyQt5.QtCore/QtWidgets and the already-shipped
`mod_editor.core.nfl2k5_build_settings`. The updater, cache, launcher, PNG,
roster and player-asset changes use existing shipped modules and Python stdlib.
Keep the new tests and proposal diff out of the end-user allowlist.
Re-pin the changed existing provider/runtime input hashes with the normal
`python3 packaging/repin.py --apply` workflow after integration; do not weaken
provider checks. `providers.py` and all packaging checkers remain untouched here.
Run the release/runtime gates on Claude's complete staged tree, where the
reviewed asset catalogs exist. This lean tree lacks `reports/assets`.

No new executable owner or capability surface is introduced. Consequently the
requested dispatcher `_apply_all` tuple, its kwarg, and the four status dicts
need **no changes**. There is **no new BuildPlan field**, no changes to basic,
advanced or experimental presets, no new PATCHES row or NEEDS_IMAGE entry,
no new Build `_option` caption, and no capability-registry entry. Existing
PATCHES text retains its Retail/Patch descriptions. The allocator, cave
manifest, throw tuning, gameplay panels outside the proposal and both XBE
safety-gate compositions are untouched. No game feature is enabled by this job.

Newly saved Build settings contain more keys. An older Studio which refuses
those keys should be updated, not taught to silently drop them. External files
referenced by choices are retained as paths, not embedded into `.2k5mod`; the
FAQ states this limit. Old project files without saved choices load with
explicit defaults, but their lost choices cannot be reconstructed.

---

# r63 Scorebar Studio: an easy scorebug editor page (2026-09-07)

Branch `fable/r63-scorebug-studio`, base `b2948b8`. **EXPERIMENTAL / UNWITNESSED.**
Delivered outside every protected file: the document model
`mod_editor/core/nfl2k5_scorebug_author.py`, the page
`mod_editor/gui/scorebug_studio_panel_qt.py`, the preset registry
`data/nfl2k5_scorebug_studio_presets.json`, the guide
`docs/mod_editor/scorebug_studio.md` with `docs/mod_editor/scorebug_studio/*.png`,
the capability object `docs/mod_editor/nfl2k5_scorebug_studio_capability.json`,
the tests `tests/mod_editor/test_nfl2k5_scorebug_author.py` and
`tests/mod_editor/test_scorebug_studio_panel_qt.py`, and
`FABLE_SCOREBUG_STUDIO_REPORT.md`. The page writes a template folder; the
existing static `scorebug` option and `scorebug_folder` field install it. Nothing
below adds an owner, a cave, a preset flag or a BuildPlan field. The protected
`nfl2k5_scorebug_template.py`, `nfl2k5_scorebug_ingame.py`,
`nfl2k5_scorebug_resources.py` and `nfl2k5_scorebug_exact.py` are untouched.

## Page registration in protected `mod_editor/gui/studio_qt.py`

Naming: the sidebar row and header title are **`Scorebar`** (plain word, no
star until Noah has witnessed a Studio-made bar in-game, no em dashes). The page
title inside is "Scorebar Studio".

1. Import, beside the `MyCareerPanel` import (line 129):

   ```python
   from mod_editor.gui.scorebug_studio_panel_qt import ScorebugStudioPanel
   ```

2. Navigation row, directly after the `career_item` block and before
   `build_item` (lines 2545 to 2549):

   ```python
   scorebar_item = QListWidgetItem("  Scorebar")
   scorebar_item.setData(Qt.UserRole, "scorebar")
   scorebar_item.setSizeHint(QSize(210, 44))
   scorebar_item.setToolTip("Design the in-game scorebar: pick a preset, recolour each part or use your "
                            "own pictures, then hand the folder to Build. Experimental and unwitnessed.")
   self.navigation.addItem(scorebar_item)
   ```

3. Page, directly after
   `self.pages.addWidget(self._page_scroll_host(self._my_career_panel))` (line 2833)
   and before `self._build_share_page = self._build_build_share_page()`:

   ```python
   self._scorebar_panel = ScorebugStudioPanel()
   self._scorebar_panel.folder_chosen.connect(self._scorebar_folder_chosen)
   self.pages.addWidget(self._page_scroll_host(self._scorebar_panel))
   ```

   Row order and page order must match: the shell connects
   `navigation.currentRowChanged` to `pages.setCurrentIndex`.

4. Handler, beside `_my_career_setup_ready` (line 8450). The page has already
   saved and compiled the folder before it emits:

   ```python
   def _scorebar_folder_chosen(self, folder: str) -> None:
       """Scorebar Studio saved a folder: fill the Build tab's scorebar folder field."""
       if self._build_panel is None:
           return
       self._build_panel.scorebug_folder_field.setText(folder)
       self._capture_music_build_settings()
       self._mark_workspace_changed()
       self._set_status("Scorebar folder handed to Build. Tick Experimental ESPN scorebar on the Build tab.")
   ```

   Do not tick `scorebug_check` from here. It is an Experimental-only option with
   `needs_image=True` and its own preset gating; the page's own result text tells
   the user to tick it. The field keeps its text while disabled and `_plan()`
   already passes it only when the static option is on and the diagnostic runtime
   is off (build_panel_qt.py lines 1281 and 1473).

5. `_update_header_title` (line 8613): the special titles tuple becomes
   `("Rosters", "Models", "Animations", "Create a Play", "MyCareer", "Scorebar", "Build & Share")`.

6. `_refresh_entered_page`, `_refresh_action_bar_for_page` and the source hooks
   need nothing: the page reads no disc and holds no source.

7. Tests that pin the row order, to update in the same commit:
   `tests/mod_editor/test_studio_shell_layout_qt.py::test_navigation_rows_and_pages_line_up`
   expects `1 + len(PRODUCT_CATEGORY_ORDER) + 7` rows, `rows[-7] == "★ Rosters"`,
   `rows[-6] == "★ Models"`, `rows[-5] == "Animations"`, `rows[-4] == "★ Create a Play"`,
   `rows[-3] == "MyCareer"`, `rows[-2] == "Scorebar"`, `rows[-1] == "★ Build & Share"`;
   `test_header_title_follows_every_row` follows from step 5. Add to
   `tests/mod_editor/test_beta62_integration3_qt.py` the same shape as the
   MyCareer check:

   ```python
   StudioMainWindow._scorebar_folder_chosen(host, '/tmp/my scorebar')
   self.assertEqual(self.panel.scorebug_folder_field.text(), '/tmp/my scorebar')
   self.assertFalse(self.panel.scorebug_check.isChecked())
   ```

   (`host` needs `_set_status`; a `lambda *_: None` on the namespace is enough.)

## Protected `mod_editor/gui/build_panel_qt.py` and `mod_build.py`

No edits. `scorebug_folder_field` (line 682, accessible name "Scorebar artwork
folder") already feeds `BuildPlan.scorebug_folder`, and the v10 section above
describes the preflight through `nfl2k5_scorebug_ingame.image_plan`. A folder
saved by the page is a complete `nfl2k5_scorebug_template/v1` folder
(`layout.json` copied from the preset's contract, `1x/`, `2x/`, `images/`,
`scorebar_studio.json`); the extra two entries are ignored by the compiler.

## Protected `packaging/release-allowlist.txt`

Add these exact lines (deduplicate):

```text
mod_editor/core/nfl2k5_scorebug_author.py
mod_editor/gui/scorebug_studio_panel_qt.py
data/nfl2k5_scorebug_studio_presets.json
docs/mod_editor/nfl2k5_scorebug_studio_capability.json
docs/mod_editor/scorebug_studio.md
```

The presets reference only `docs/scorebug_template/1x/left_mark.png` and
`docs/scorebug_template/2x/left_mark.png`, both already allowlisted and in the
reviewed PNG catalog. The guide's ten PNGs under `docs/mod_editor/scorebug_studio/`
are new authored art (drawn field, stand-in glyphs, page screenshots; no retail
pixels). To ship them, add the ten lines
`docs/mod_editor/scorebug_studio/<name>.png` to the allowlist and merge the
block below into `packaging/nfl2k5_scorebug_template_pngs.json` (`files`), then
recompute `SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256` in
`packaging/check_2k5_mod_studio_release.py` with `sha256sum` over the catalog
file. Neither file is protected, but the parallel exact-bar session adds to the
same catalog, so this merge is left to the integrator. If the PNGs are not
shipped, leave the guide line out as well rather than ship broken image links.

```json
{
  "docs/mod_editor/scorebug_studio/page_fable_down.png": {
    "size": 274311,
    "sha256": "932f31ce9ae3e50544a969b4fe5ead9e0a9cec2d05762c6e7e044d2f6f772d63",
    "width": 1601,
    "height": 936
  },
  "docs/mod_editor/scorebug_studio/page_plain_wide_teams.png": {
    "size": 240304,
    "sha256": "ef131697031d7e97e0dea30216f07bdf79263f14c7d55c0fd3175ccccf6b380d",
    "width": 1601,
    "height": 936
  },
  "docs/mod_editor/scorebug_studio/page_reference.png": {
    "size": 246888,
    "sha256": "3ee49a21ac494e42ffdc07f39eaf06dceab5db3bcaa3e3ddb918466d262b275a",
    "width": 1601,
    "height": 880
  },
  "docs/mod_editor/scorebug_studio/preset_fable_espn.png": {
    "size": 23475,
    "sha256": "a50d152fa1a84c36f9edfe2f2c439982d2512a4c0ba4737d666c524524aba770",
    "width": 640,
    "height": 480
  },
  "docs/mod_editor/scorebug_studio/preset_plain_dark.png": {
    "size": 21725,
    "sha256": "5da45d6baa8fd974bc03257da76612a96dde750f9f172788ddc3e78a3bae6aa6",
    "width": 640,
    "height": 480
  },
  "docs/mod_editor/scorebug_studio/preset_reference_v10.png": {
    "size": 22942,
    "sha256": "882e4692582afcefbe7497b290094a7d559a54b88411d9ffb12ee864b0927f90",
    "width": 640,
    "height": 480
  },
  "docs/mod_editor/scorebug_studio/preset_retail_like.png": {
    "size": 20307,
    "sha256": "b3765eb2092b6a0cefca0b82c7e66c80a7d3fc09e5fbcdfc2a2d2c4a22b1b4c5",
    "width": 640,
    "height": 480
  },
  "docs/mod_editor/scorebug_studio/states_fable.png": {
    "size": 40109,
    "sha256": "1b5095f2e4368a88dbd91808a5551a3b09afc9135c059873537990b940593e12",
    "width": 1000,
    "height": 560
  },
  "docs/mod_editor/scorebug_studio/team_preview_NO_MIA.png": {
    "size": 8508,
    "sha256": "d89e8dade06b7dc31842005c611c95f61ba009672f8df77b878471a8a85f4dce",
    "width": 1000,
    "height": 140
  },
  "docs/mod_editor/scorebug_studio/widescreen_fable.png": {
    "size": 32447,
    "sha256": "4b738bc82986e71a6b0ea6da8cbdc707d67d21d9889437abbb0b09ac48192113",
    "width": 854,
    "height": 480
  }
}
```


## Protected `packaging/check_2k5_mod_studio_runtime.py`

Add `"mod_editor.core.nfl2k5_scorebug_author"` beside
`"mod_editor.core.nfl2k5_scorebug_template"` and
`"mod_editor.gui.scorebug_studio_panel_qt"` beside `"mod_editor.gui.music_panel_qt"`
in the explicit product module list. Both use only Pillow and PyQt5 (the model
imports no Qt, numpy, Unicorn or network). After the existing Music panel
exercise (which already has `qt_app` and `tempfile` in scope), add:

```python
    studio = modules["mod_editor.core.nfl2k5_scorebug_author"]
    require([item.id for item in studio.presets()] == ["reference_v10", "fable_espn", "plain_dark", "retail_like"],
            "Scorebar Studio preset registry changed")
    with tempfile.TemporaryDirectory() as scratch:
        receipt = studio.Document.from_preset("plain_dark").save_folder(Path(scratch) / "bar")
        require(receipt["slot"]["fits"] and receipt["template"]["colours"] <= 128,
                "Scorebar Studio export no longer fits the scorebar slot")
    scorebar_page = modules["mod_editor.gui.scorebug_studio_panel_qt"].ScorebugStudioPanel()
    require(scorebar_page.layer_list.count() == 8 and not scorebar_page.is_dirty, "Scorebar Studio page is not idle")
    scorebar_page.close()
    scorebar_page.deleteLater()
    qt_app.processEvents()
```

## Capability registry object

Merge the single object in `docs/mod_editor/nfl2k5_scorebug_studio_capability.json`
into protected `mod_editor/capabilities/registry.v1.json`, in sorted id order
between `nfl2k5.scorebug_presentation.shield_espn_runtime` and
`nfl2k5.scorebug_presentation.template`. Its id is
`nfl2k5.scorebug_presentation.studio`, surface `scorebug_presentation` (the
existing presentation surface, so it lands on the Presentation page's cards),
classification `offline-writer-proved`, runtime `not-tested`, gui `expose: true`,
`default_enabled: false`, `mode: edit`. Validated here with
`validate_data(check_files=False)` on a sorted copy: 110 capabilities, valid.
`check_files=True` fails in this worktree only on an older row's
`docs/research/apf_audio.md` (gitignored research), not on this object; every
file this object names exists after this commit. Then run
`python3 -m unittest tests.mod_editor.test_validate_all_capabilities tests.mod_editor.test_no_capability_is_invisible`.

## Provider pins

No repin is required. `mod_editor/core/providers.py` pins the build bundle;
neither new module is part of it, and `nfl2k5_scorebug_template.py` (pin
`368ceb6e…`) is unchanged, so the Studio's folders flow through the already
pinned compiler. If Claude decides to pin the model module because the runtime
closure imports it, add
`"mod_editor/core/nfl2k5_scorebug_author.py": "<sha256>"` to `module_pins` and
run `python3 packaging/repin.py --apply`; `repin.py` recomputes it from the
committed bytes.

## After wiring, run

```sh
QT_QPA_PLATFORM=offscreen python3 -m unittest \
  tests.mod_editor.test_nfl2k5_scorebug_author \
  tests.mod_editor.test_scorebug_studio_panel_qt \
  tests.mod_editor.test_nfl2k5_scorebug_template \
  tests.mod_editor.test_studio_shell_layout_qt \
  tests.mod_editor.test_beta62_integration3_qt \
  tests.mod_editor.test_validate_all_capabilities \
  tests.mod_editor.test_no_capability_is_invisible \
  tests.mod_editor.test_shipped_tools_posix_only
python3 packaging/check_2k5_mod_studio_runtime.py
```

## r63-scorebug-exact2 integration, 2026-09-07

The continued visual loop adds private scorebug FONT resources to the existing
diagnostic runtime collection. Also add
`mod_editor/core/nfl2k5_scorebug_fonts.py` to `packaging/release-allowlist.txt`
and `"mod_editor.core.nfl2k5_scorebug_fonts",` to the runtime checker imports.
Seven private FONT descriptors use the native registry and scorebug object
pointers. Original FONT4/FONT8 resources and all nine global font slots stay
retail. The owner also binds one white possession glyph and selects a compact
score font for current or cached three-digit scores. The complete owner uses
1,395 of its 1,408 RX bytes and retains its 128-byte RW allocation. No new
allocator request, dispatcher field, preset, capability or GUI
control is needed. Keep the 1,408-byte RX / 128-byte RW owner budget. The
six diagnostic profiles remain EXPERIMENTAL / UNWITNESSED and runtime remains
off in every preset. This does not resolve the game-entry freeze.

This section supersedes contradictory default-selection statements in the
older v10 and exact-v1 handoffs below. `scorebug` without a folder installs
`espn-broadcast-exact-v1`; an explicit `scorebug_folder` installs the preserved
`espn-reference-v10` scene, atlas and executable fields. The latter has exactly
the landed v10 byte hashes. Keep `BuildPlan.scorebug_folder: str = ""`,
its normalization, preflight and forwarding to the existing static writer.
All presets leave the folder empty; Basic/Advanced leave `scorebug` off and
Experimental enables it. Runtime stays off in every preset. There is no new
surface, owner, allocation or capability row in this integration.

Protected changes still needed:

- `packaging/release-allowlist.txt`: add exactly
  `mod_editor/core/nfl2k5_scorebug_exact.py`.
- `packaging/check_2k5_mod_studio_runtime.py`: add exactly
  `"mod_editor.core.nfl2k5_scorebug_exact",` to its product imports.
- `mod_editor/gui/beta62_options.py`: use the two help strings below. This
  shared GUI file was left untouched in accordance with the brief.
- `mod_editor/gui/build_panel_qt.py`: retain the `Experimental ESPN scorebar`
  caption (26 characters), the folder field, and its existing `scorebug_folder`
  forwarding. Its Build help must explicitly mention the folder override.
- Claude regenerates `data/nfl2k5_cave_reservations.json` and source identities.
  The existing static owner adds the exact-v1 FONT selectors, neutral label
  colours and `0x000FBE43` operand; no new cave is introduced. Its complete
  `MOV EDX` instruction and unchanged UTF-16 suffix are guarded.

```python
SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Uses the Raiders at Texans "
    "broadcast layout with neutral panels, white scores, a red down box and a "
    "light clock strip. A scorebar folder overrides this with your painted "
    "template. Moves the kick meter up and hides the lineup strip. "
    "EXPERIMENTAL / UNWITNESSED; fonts and colours still differ.")
SCOREBUG_RUNTIME_HELP = (
    "Retail: Uses the original team panels and text. Patch: Adds team gradients, "
    "logos, live timeout marks, resized text, a white possession marker and "
    "room for three-digit scores to the experimental scorebar. "
    "Diagnostic only and off in every preset. EXPERIMENTAL / UNWITNESSED; "
    "the game-entry freeze remains unresolved. Keep the six probe choices.")
```

Retain `_apply_all`'s tuple
`(scorebug_runtime, scorebug_runtime_patch, "scorebug_runtime_patch", "experimental scorebug effects")`,
the `scorebug_runtime=scorebug_runtime` kwarg, request union and deferred final
pass. The static writer remains `nfl2k5_scorebug_layout.apply_in_place(...,
scorebug_folder=plan.scorebug_folder or None)`. Retain all four dispatcher dictionaries'
`scorebug_xbe` / `scorebug_runtime` entries, plus both image dictionaries'
`scorebug` / `scorebug_runtime_resources` entries. Read-only `xbe_status` and
static image inspection recognize both complete shipped scenes. Writers select
one explicit scene and refuse mixed, foreign or cross-version inputs before
mutation; custom folder inspection requires that folder. V8/v9 remain refused.

Gameplay Patches keeps both current `PATCHES` rows and `NEEDS_IMAGE` membership;
the shared help contains both "Retail" and "Patch". No new dispatcher flag,
Build option or capability registry entry is needed. The repaintable template
compiler, source PNG catalog and its release checks remain intact.

# r64 kickoff v5, 2026-09-07

EXPERIMENTAL/UNWITNESSED. See `ASTRA_KICKOFF_V5_REPORT.md` and
`docs/nfl2k5_kickoff_v5_receipts.json`. Held players keep their selected native
stance without restarting its receiving-side foot sampler. Released drive
blockers refresh a lane-weighted nearest target before pursuit and wait with
zero throttle when none remains. Existing native paired contacts continue.
This uses 1,937/1,939 RX bytes and 10 RW bytes, with nineteen hooks.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` using
`python3 tools/nfl2k5_cave_oracle.py manifest` after integration. The owner
already appears in the manifest builder and complete gate union; its declared
edits supply all pins. Add the new `block_tick` live span below and refresh both
kickoff source fingerprints. The tests project only verified retail pins and
exact installed jumps, reject foreign overlaps, and transfer ownership to
`nfl2k5_dynamic_kickoff_relocated` when relocated. No product manifest was
regenerated in this worktree.

Every live overwritten span is half-open:

| Hook | Span | Retail pin |
| --- | --- | --- |
| `launch` | `222CA0..222CA5` | `83ec205355` |
| `aim` | `222E67..222E6C` | `d944243851` |
| `ground` | `0A06E0..0A06E6` | `558bec83e4f0` |
| `touch` | `0B78C9..0B78CE` | `a1ec02e600` |
| `dead` | `0B7BB0..0B7BB6` | `558bec83e4f0` |
| `plan` | `1CD5D0..1CD5D7` | `56578bf98b470c` |
| `motion` | `218010..218015` | `a10c1db700` |
| `position` | `2CC4F0..2CC4F7` | `518b4114d94048` |
| `spot` | `0B65CC..0B65D1` | `a18002e600` |
| `reset` | `1C9399..1C939E` | `a1a0d95000` |
| `lineup` | `183F60..183F66` | `558bec83e4f0` |
| `eligibility` | `0B6760..0B6766` | `83ec0c8b4738` |
| `root_motion` | `2CC570..2CC577` | `83ec1c568b4210` |
| `block_target` | `2FAFF0..2FAFF6` | `558bec83e4f0` |
| `diagram` | `1802BB..1802C0` | `8b450c85c0` |
| `separation` | `1D8940..1D8946` | `8b48248b5120` |
| `ready` | `1FF940..1FF946` | `8b41108b5004` |
| `head_pose` | `1DF430..1DF436` | `558bec83e4f0` |
| `block_tick` | `23CE70..23CE76` | `558bec83e4f0` |

The existing legacy RX reservation is `2890F0..289883`. RW remains exactly
`A69969..A69970` and `A69971..A69974`; the intervening byte is untouched.
The relocated owner keeps `(code, 1939, align 16)` and `(data, 10, align 4)`.
Its actual addresses come from the complete allocator union. No budget row,
new owner, page, or runtime storage in RX is requested. The packed launch
configuration writes include only owned bytes; the temporary fourth byte of
its first store is immediately replaced by the complete saved kick-spot float.

Dispatcher `_apply_all` retains the existing
`(dynamic_kickoff, _dynamic_kickoff_adapter(dynamic_kickoff_settings),
"dynamic_kickoff_patch", "dynamic-kickoff")` tuple and post-allocator
`(kickoff_relocated, kickoff_relocated_patch, "kickoff_relocated_patch",
"experimental relocated kickoff")` tuple. Keep kwargs `dynamic_kickoff`,
`dynamic_kickoff_settings`, `kickoff_relocated`, `_selected_space_requests`,
`_xbe_space_adapter`, request selection and deferred final application. The
four status dictionaries (file inspection, image inspection, file patch result,
image patch result) retain `dynamic_kickoff`, `dynamic_kickoff_settings`,
`kickoff_relocated`, `kickoff_relocated_settings` with their current status and
read-settings calls. No dispatcher edit is required.

`BuildPlan` retains `dynamic_kickoff`, its settings and `kickoff_relocated`,
normalization and deferral. Basic and Advanced disable dynamic kickoff;
Experimental enables it. Relocation stays disabled in all three defaults and
implies the allocator and dynamic kickoff when selected. Gameplay Patches
retains both PATCHES entries and both `NEEDS_IMAGE` keys. Keep the dynamic text
containing "Retail: on a kickoff everyone sprints at the kick" and
"Patch: the 2024/2025 rule", the role exceptions, and the unwitnessed label.
Keep the relocation text containing "Retail: the extra patch space is unused.
Patch: moves the dynamic kickoff there with the same settings."

Build tab `_option` keeps `Dynamic kickoff: ready stance and close blocks`
(46 characters), `needs_image=True` and `NOT_TESTED`. Allowlist lines remain
`mod_editor/core/nfl2k5_dynamic_kickoff.py` and
`mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py`. Runtime-closure imports
remain `mod_editor.core.nfl2k5_dynamic_kickoff` and
`mod_editor.core.nfl2k5_dynamic_kickoff_relocated`. Both existing source pins
in `providers.py` are refreshed. No new capability registry entry is needed.
All protected dispatcher, GUI, registry, packaging and manifest files remain
untouched. Existing PLAY alignment/returns and fitted card stay enabled in
the same order. Rebuild from supported retail input: v1 through v4 executable
patches are foreign, including an attempted partial upgrade.

# r64 kickoff v4: completed lineup and late head pose (2026-09-07)

EXPERIMENTAL/UNWITNESSED. See `ASTRA_KICKOFF_V4_REPORT.md`. Existing dynamic
kickoff now holds each of the nineteen coverage/setup players as soon as its
native lineup state is 13, even while the global state is still 12. The new
ready query preserves native team readiness after fixed idle replaces the
ready descriptor. A late head-pose guard samples the fixed clip instead of
interpolating a renewed head-look request. Code uses 1,935/1,939 reserved bytes;
state remains 10 RW bytes. There are eighteen hooks and no new allocation.

Claude must regenerate the protected `data/nfl2k5_cave_reservations.json` with
`python3 tools/nfl2k5_cave_oracle.py manifest` after integration. Include current
source fingerprints and both additional live spans:

| Hook | Complete overwritten span | Retail pin |
| --- | --- | --- |
| `ready` | `1FF940..1FF946` | `8b41108b5004` |
| `head_pose` | `1DF430..1DF436` | `558bec83e4f0` |

The existing manifest builder discovers both from the owner's declared edits;
grown builds transfer their ownership to `nfl2k5_dynamic_kickoff_relocated`.
Retain v3's `1D8940..1D8946` separation span. The test projection verifies each
retail pin, exact installed jump and absence of a foreign overlapping owner.
It still rejects unknown grown declarations. This projection is confined to
the tests; the protected product manifest has not been regenerated here.

Dispatcher `_apply_all` keeps the existing
`(dynamic_kickoff, _dynamic_kickoff_adapter(dynamic_kickoff_settings),
"dynamic_kickoff_patch", "dynamic-kickoff")` tuple and the post-allocator
`(kickoff_relocated, kickoff_relocated_patch, "kickoff_relocated_patch",
"experimental relocated kickoff")` tuple. Keep kwargs `dynamic_kickoff`,
`dynamic_kickoff_settings`, `kickoff_relocated`, request selection and deferred
final application. In the four status dictionaries (file inspection, image
inspection, file patch result, image patch result), keep `dynamic_kickoff`,
`dynamic_kickoff_settings`, `kickoff_relocated`, `kickoff_relocated_settings`
and their existing status/read-settings calls. No dispatcher edit is needed.

`BuildPlan` keeps `dynamic_kickoff`, its settings and `kickoff_relocated` with
existing normalization. Basic and Advanced leave dynamic kickoff disabled;
Experimental enables it. Relocation stays disabled by default in all three
presets and still implies the allocator and dynamic kickoff when selected.
Gameplay Patches keeps both PATCHES entries and both `NEEDS_IMAGE` keys.
The existing dynamic text begins "Retail: on a kickoff everyone sprints at
the kick" and includes "Patch: the 2024/2025 rule." Retain its role exceptions
and unwitnessed label. The relocation text retains "Retail: the extra patch
space is unused. Patch: moves the dynamic kickoff there with the same
settings." No newly witnessed claim is authorized by the native tests.

Build tab `_option` keeps `Dynamic kickoff: ready stance and close blocks`
(46 characters, below 60), `needs_image=True` and `NOT_TESTED`. Allowlist lines
remain `mod_editor/core/nfl2k5_dynamic_kickoff.py` and
`mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py`; runtime-closure imports
remain `mod_editor.core.nfl2k5_dynamic_kickoff` and
`mod_editor.core.nfl2k5_dynamic_kickoff_relocated`. The two existing provider
source pins are refreshed in `providers.py`. No capability registry entry is
needed because this changes the existing surface. The fitted card and PLAY
alignment/return resources are unchanged. Rebuild from supported retail input;
historical v1/v2/v3 executable patches are deliberately refused as foreign.

# r63 kickoff v3: collision producer and residual pose hold (2026-09-07)

EXPERIMENTAL/UNWITNESSED. See `ASTRA_KICKOFF_V3_REPORT.md`. The existing
dynamic kickoff option now also suppresses `1D8940` collision impulses for
held players and clears residual pose spring/impulse state before the native
late passes. First ground/player contact remains the release. Code is
1,937/1,939 bytes; RW remains 10 bytes; there are sixteen hooks. No new option,
owner, request, preset or persistent state is introduced.

Claude must regenerate the protected `data/nfl2k5_cave_reservations.json`
with the existing `tools/nfl2k5_cave_oracle.py manifest` workflow after merging.
It must include the complete `1D8940..1D8946` live hook, retail pin
`8b48248b5120`, transferred to `nfl2k5_dynamic_kickoff_relocated` in grown
builds, and current source fingerprints. The existing manifest recorder reads
the new declared edit automatically. Both XBE gates pass with a test-only
projection that proves the retail pin, exact installed jump and lack of a
foreign owner before adding this hook. The protected manifest is unchanged.

The gate projection also handles the manifest's camera declaration from its
smaller camera/calendar preset at `14DA400..14DA440`. It reconstructs that
exact named allocation with `space.plan(camera.REQUESTS + calendar.REQUESTS)`
and checks the recorded preset flags, owner, basis, size and alignment before
projecting it into the full union. It keeps every retail reservation and parent
page and still rejects unknown owners. This is an ownership projection, not a
free-cave exemption. The product manifest contains both preset and dormant
owner observations, so its camera declaration can require this projection even
after regeneration.

Dispatcher `_apply_all`: retain the existing
`(dynamic_kickoff, _dynamic_kickoff_adapter(dynamic_kickoff_settings),
"dynamic_kickoff_patch", "dynamic-kickoff")` tuple and the post-allocator
`(kickoff_relocated, kickoff_relocated_patch, "kickoff_relocated_patch",
"experimental relocated kickoff")` tuple. Retain the `dynamic_kickoff`,
`dynamic_kickoff_settings` and `kickoff_relocated` kwargs and current request
selection/deferral. In all four status dictionaries (file inspection, image
inspection, file patch result, image patch result), retain `dynamic_kickoff`,
`dynamic_kickoff_settings`, `kickoff_relocated` and
`kickoff_relocated_settings` with the existing status/read-settings calls.
No dispatcher or status-field edit is needed for v3.

`BuildPlan`: retain `dynamic_kickoff`, its settings, `kickoff_relocated` and
the existing normalization. Basic and Advanced keep dynamic kickoff disabled;
Experimental keeps it enabled. Relocation stays disabled by default in all
three presets and continues to imply the allocator and dynamic kickoff when
selected. Retain the existing Gameplay Patches PATCHES text containing
"Retail" and "Patch" and both keys in `NEEDS_IMAGE`. Retain the Build tab
`_option` caption `Dynamic kickoff: ready stance and close blocks` (46 chars),
`needs_image=True` and `NOT_TESTED`. No new UI claim of a gameplay fix is needed
before Noah's witness. Existing help that says "nobody moves" means the ten
coverage players and nine setup blockers; the kicker and two deep returners
remain free.

The existing dynamic-kickoff PATCHES text begins: "Retail: on a kickoff
everyone sprints at the kick, the ball is kicked wherever the CPU meter lands
and a returner brings most kicks out. Patch: the 2024/2025 rule." Retain its
following role exceptions, contact/spot/settings explanation and unwitnessed
status. The relocated PATCHES text remains: "Retail: the extra patch space is
unused. Patch: moves the dynamic kickoff there with the same settings. Check
that both teams still line up, hold until contact and return normally.
Unwitnessed in game." Both `dynamic_kickoff` and `kickoff_relocated` remain in
`NEEDS_IMAGE`.

Allowlist lines remain `mod_editor/core/nfl2k5_dynamic_kickoff.py` and
`mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py`. Runtime-closure imports
remain `mod_editor.core.nfl2k5_dynamic_kickoff` and
`mod_editor.core.nfl2k5_dynamic_kickoff_relocated`. The tests/evidence helper
is not a product import. The unified provider's two existing module hashes
were refreshed in `providers.py`; no execution trust rule was weakened. No
new capability registry entry is needed because the existing surface is used.
Historical v1/v2 XBE payloads deliberately refuse; rebuild from the supported
base rather than layering v3 over an old patched XBE.

# r63 static ESPN scorebug v10 and repaintable template (2026-09-07)

The existing `scorebug` checkbox installs **`espn-reference-v10`** now. The
new authoring folder compiler and exact-palette writer are implemented. All
protected files and shared GUI panels are unchanged. This section supersedes
the v9 help-text handoff below, but does not change the diagnostic runtime's
status, default or known entry freeze. See `ASTRA_SCOREBUG_V10_REPORT.md` and
`docs/scorebug_template/README.md`.

## Protected BuildPlan and Build tab changes for Claude

The Build tab already has `hires_folder_field`, a `QLineEdit` and a
`Choose folder...` button under the Hi-res option. Use that exact pattern for
the requested scorebar folder. These edits are specified here because
`mod_build.py` and `build_panel_qt.py` are protected by the brief, not because
the feature lacks a compiler.

1. In `mod_editor/core/mod_build.py`, add `scorebug_folder: str = ""` directly
   after `BuildPlan.scorebug`. Keep that field empty in Basic, Advanced and
   Experimental. Preserve `scorebug=False` in Basic/Advanced and `True` in
   Experimental, as on this stack; `scorebug_runtime=False` in every preset.
   Normalize the folder with type checking and `.strip()`. A nonempty folder
   requires `scorebug=True`, an image input and `scorebug_runtime=False`.
   Do not enable any allocator or runtime flag for this field.
2. Before the image-copy/target-write stage, preflight the selected template
   against the source using the existing bounded image planner:

   ```python
   if plan.scorebug and not plan.scorebug_runtime:
       scorebar = _core_module("nfl2k5_scorebug_ingame")
       with source.open("rb") as stream:
           scorebar.image_plan(stream.fileno(), os.fstat(stream.fileno()).st_size,
                               scorebug_folder=plan.scorebug_folder or None)
   ```

   This checks every PNG, palette, fixed-span fit, source identity and XBE
   before creating a multi-gigabyte copy. Discard the returned bounded jobs;
   the output-side transaction preflights again against the composed bytes.
   The actual presentation step at the existing `plan.scorebug and not
   plan.scorebug_runtime` branch changes one call to:

   ```python
   rec = sbl.apply_in_place(target, scorebug_folder=plan.scorebug_folder or None)
   ```

   The existing `steps.append({"step": "scorebug", **rec})` retains the complete
   source-layer and installed-byte receipts. Retain the present Hi-res
   scorebug-family conflict check. No new final-pass XBE writer or deferral
   is needed: both folder and default installs use the same executable fields.
3. In `mod_editor/gui/build_panel_qt.py`, retain `_option` caption
   **`Experimental ESPN scorebar`** (26 characters), `needs_image=True`,
   `NOT_TESTED`, and shared help/details. Add a row immediately below it with
   `scorebug_folder_field`, placeholder **`Optional: choose your scorebar folder`**,
   accessible name **`Scorebar artwork folder`**, and a **`Choose folder...`**
   button. `_choose_scorebug_folder` uses
   `QFileDialog.getExistingDirectory(self, "Choose scorebar artwork folder", ...)`.
   Connect `textChanged` to `_refresh`; enable the field/button only while the
   static checkbox is available/selected and `scorebug_runtime` is unselected.
   Blank selects the shipped template. Add the active folder to `_plan()` as
   `scorebug_folder=...`, the build summary, and any cached validation identity.
   Preserve the text while disabled, but pass an empty field to the plan when
   the diagnostic runtime is selected so dormant custom art cannot mix with it.
4. Build's preflight may call `compile_folder` for immediate plain errors, but
   keep the source planner in step 2: PNG validation alone cannot prove VC-LZ
   fit. Forward the compiler's `ValueError` message through the existing build
   error handling. Do not swallow an invalid folder or silently use default art.

## Dispatcher and the four status dictionaries

No new `_apply_all` owner tuple, adapter, request union, `_selected_space_requests`
flag or `_xbe_space_adapter` flag is required. **Do not add a `scorebug_folder`
kwarg to `_apply_all`.** This is a source-art argument for the static image
writer, not an executable-only patch. Its implemented keyword is
`nfl2k5_scorebug_layout.apply_in_place(..., scorebug_folder=...)`, which delegates
to `nfl2k5_scorebug_ingame.apply_in_place`.

The four existing `scorebug_xbe` entries in `nfl2k5_throw_tuning.py` remain
`scorebug_reference.xbe_status(payload/result/after)` in `read_xbe`, `read_image`,
the `_apply_all` result and the final image result. There is no folder-dependent
XBE state: all artwork shares the same pinned fields. Keep existing
`scorebug_runtime` and `scorebug_runtime_resources` entries unchanged. For a
folder-aware static resource badge use
`nfl2k5_scorebug_layout.status(image, scorebug_folder=folder or None)`;
do not substitute the runtime resource status. A foreign template refuses.

Both executable gates already compose this static owner through
`tests/nfl2k5_allocator_stack.compose`, before the complete runtime owner union
in both orders and both scaleout variants. There are zero new RX/RW/RO bytes
and no new cave or owner. The two font-slot edits are ordinary existing data
words, not allocations. Claude alone regenerates the protected cave manifest
and refreshes source digests after integration. Do not copy an audit manifest
or native resource into the release.

## Shared help, Gameplay Patches and registry

In shared `mod_editor/gui/beta62_options.py`, replace `SCOREBUG_HELP` with:

```python
SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Installs new repaintable ESPN artwork, "
    "with a left mark, dark team blocks, larger white scores, a red down cell and a light clock cell. "
    "Team abbreviations and possession stay live. Choose a scorebar folder to use your own art. "
    "Team colours and live timeout marks need separate runtime work. "
    "Moves the kick meter up and hides the lineup strip. EXPERIMENTAL / UNWITNESSED v10.")
```

The existing Gameplay Patches `PATCHES` scorebug row keeps that shared text,
which contains **Retail** and **Patch**. `scorebug` stays in `NEEDS_IMAGE`.
There is no second checkbox or runtime promotion. The folder field belongs
to Build's existing presentation source-folder pattern.

Merge the complete schema-valid object from
`docs/mod_editor/nfl2k5_scorebug_template_capability.json` into the canonical
capability registry, keeping the existing texture-editor and runtime rows.
The new ID is `nfl2k5.scorebug_presentation.template`; its backend command is
`python3 -m mod_editor.core.nfl2k5_scorebug_template apply` and validation is
`python3 -m tests.mod_editor.test_nfl2k5_scorebug_template`. The real GUI wiring
must land before publishing the row. It is offline-writer-proved, runtime
not-tested, and explicitly distinguishes staged glyphs/team art from live use.

## Release integration

`packaging/check_2k5_mod_studio_release.py` is not protected by this brief and
now implements the required narrow new-art exception. The immutable
`packaging/nfl2k5_scorebug_template_pngs.json` catalog pins each reviewed PNG's
exact path, size, SHA-256 and dimensions. The checker pins the catalog itself.
All other PNGs remain forbidden, including an unlisted PNG under the template
directory or a reviewed image renamed elsewhere. No broad PNG or `assets/`
exception is needed. Standalone staged-template and rejection tests cover it.

Add `mod_editor.core.nfl2k5_scorebug_template` to the explicit import list in
protected `packaging/check_2k5_mod_studio_runtime.py`, beside `...scorebug_ingame`.
Its new dependency is Pillow, already required by the Studio. The product
compiler uses no system font, SVG renderer, Unicorn, Capstone or network.
The authoring regeneration tool also uses only Python/Pillow. The native proof
tools stay developer-only; do not import them into the product closure.
Refresh the existing provider/runtime source digest inventories for the changed
modules during the normal integration pass.

Add the following exact lines to protected `packaging/release-allowlist.txt`
(deduplicate existing lines). Every `docs/scorebug_template/` source file is
included so Noah gets both scales, the layer/master vectors, all 32 palettes,
the optional marks and the staged glyph source. The broadcast photo and native
render/audit files in `docs/scorebug_ingame/` remain evidence, outside the runtime
package. Never package generated native SCNE/TXTR, a disc, pack or executable.

```text
mod_editor/core/nfl2k5_scorebug_template.py
tools/nfl2k5_scorebug_template_art.py
packaging/nfl2k5_scorebug_template_pngs.json
docs/mod_editor/nfl2k5_scorebug_template_capability.json
docs/scorebug_template/1x/away_block.png
docs/scorebug_template/1x/away_block.svg
docs/scorebug_template/1x/away_score.png
docs/scorebug_template/1x/away_score.svg
docs/scorebug_template/1x/clock_quarter.png
docs/scorebug_template/1x/clock_quarter.svg
docs/scorebug_template/1x/down.png
docs/scorebug_template/1x/down.svg
docs/scorebug_template/1x/frame.png
docs/scorebug_template/1x/frame.svg
docs/scorebug_template/1x/home_block.png
docs/scorebug_template/1x/home_block.svg
docs/scorebug_template/1x/home_score.png
docs/scorebug_template/1x/home_score.svg
docs/scorebug_template/1x/left_mark.png
docs/scorebug_template/1x/left_mark.svg
docs/scorebug_template/2x/away_block.png
docs/scorebug_template/2x/away_block.svg
docs/scorebug_template/2x/away_score.png
docs/scorebug_template/2x/away_score.svg
docs/scorebug_template/2x/clock_quarter.png
docs/scorebug_template/2x/clock_quarter.svg
docs/scorebug_template/2x/down.png
docs/scorebug_template/2x/down.svg
docs/scorebug_template/2x/frame.png
docs/scorebug_template/2x/frame.svg
docs/scorebug_template/2x/home_block.png
docs/scorebug_template/2x/home_block.svg
docs/scorebug_template/2x/home_score.png
docs/scorebug_template/2x/home_score.svg
docs/scorebug_template/2x/left_mark.png
docs/scorebug_template/2x/left_mark.svg
docs/scorebug_template/README.md
docs/scorebug_template/atlas_1x.png
docs/scorebug_template/atlas_2x.png
docs/scorebug_template/game_state.json
docs/scorebug_template/glyphs/1x/broadcast_glyphs.png
docs/scorebug_template/glyphs/1x/broadcast_glyphs.svg
docs/scorebug_template/glyphs/2x/broadcast_glyphs.png
docs/scorebug_template/glyphs/2x/broadcast_glyphs.svg
docs/scorebug_template/glyphs/glyphs.json
docs/scorebug_template/layout.json
docs/scorebug_template/lineage/espn_nfl_watermark.svg
docs/scorebug_template/lineage/scorebug_master.svg
docs/scorebug_template/master_1x.svg
docs/scorebug_template/master_2x.svg
docs/scorebug_template/optional/1x/timeout_marks.png
docs/scorebug_template/optional/1x/timeout_marks.svg
docs/scorebug_template/optional/2x/timeout_marks.png
docs/scorebug_template/optional/2x/timeout_marks.svg
docs/scorebug_template/teams/1x/ARI.png
docs/scorebug_template/teams/1x/ARI.svg
docs/scorebug_template/teams/1x/ATL.png
docs/scorebug_template/teams/1x/ATL.svg
docs/scorebug_template/teams/1x/BAL.png
docs/scorebug_template/teams/1x/BAL.svg
docs/scorebug_template/teams/1x/BUF.png
docs/scorebug_template/teams/1x/BUF.svg
docs/scorebug_template/teams/1x/CAR.png
docs/scorebug_template/teams/1x/CAR.svg
docs/scorebug_template/teams/1x/CHI.png
docs/scorebug_template/teams/1x/CHI.svg
docs/scorebug_template/teams/1x/CIN.png
docs/scorebug_template/teams/1x/CIN.svg
docs/scorebug_template/teams/1x/CLE.png
docs/scorebug_template/teams/1x/CLE.svg
docs/scorebug_template/teams/1x/DAL.png
docs/scorebug_template/teams/1x/DAL.svg
docs/scorebug_template/teams/1x/DEN.png
docs/scorebug_template/teams/1x/DEN.svg
docs/scorebug_template/teams/1x/DET.png
docs/scorebug_template/teams/1x/DET.svg
docs/scorebug_template/teams/1x/GB.png
docs/scorebug_template/teams/1x/GB.svg
docs/scorebug_template/teams/1x/HOU.png
docs/scorebug_template/teams/1x/HOU.svg
docs/scorebug_template/teams/1x/IND.png
docs/scorebug_template/teams/1x/IND.svg
docs/scorebug_template/teams/1x/JAX.png
docs/scorebug_template/teams/1x/JAX.svg
docs/scorebug_template/teams/1x/KC.png
docs/scorebug_template/teams/1x/KC.svg
docs/scorebug_template/teams/1x/LAC.png
docs/scorebug_template/teams/1x/LAC.svg
docs/scorebug_template/teams/1x/LAR.png
docs/scorebug_template/teams/1x/LAR.svg
docs/scorebug_template/teams/1x/LV.png
docs/scorebug_template/teams/1x/LV.svg
docs/scorebug_template/teams/1x/MIA.png
docs/scorebug_template/teams/1x/MIA.svg
docs/scorebug_template/teams/1x/MIN.png
docs/scorebug_template/teams/1x/MIN.svg
docs/scorebug_template/teams/1x/NE.png
docs/scorebug_template/teams/1x/NE.svg
docs/scorebug_template/teams/1x/NO.png
docs/scorebug_template/teams/1x/NO.svg
docs/scorebug_template/teams/1x/NYG.png
docs/scorebug_template/teams/1x/NYG.svg
docs/scorebug_template/teams/1x/NYJ.png
docs/scorebug_template/teams/1x/NYJ.svg
docs/scorebug_template/teams/1x/PHI.png
docs/scorebug_template/teams/1x/PHI.svg
docs/scorebug_template/teams/1x/PIT.png
docs/scorebug_template/teams/1x/PIT.svg
docs/scorebug_template/teams/1x/SEA.png
docs/scorebug_template/teams/1x/SEA.svg
docs/scorebug_template/teams/1x/SF.png
docs/scorebug_template/teams/1x/SF.svg
docs/scorebug_template/teams/1x/TB.png
docs/scorebug_template/teams/1x/TB.svg
docs/scorebug_template/teams/1x/TEN.png
docs/scorebug_template/teams/1x/TEN.svg
docs/scorebug_template/teams/1x/WAS.png
docs/scorebug_template/teams/1x/WAS.svg
docs/scorebug_template/teams/2x/ARI.png
docs/scorebug_template/teams/2x/ARI.svg
docs/scorebug_template/teams/2x/ATL.png
docs/scorebug_template/teams/2x/ATL.svg
docs/scorebug_template/teams/2x/BAL.png
docs/scorebug_template/teams/2x/BAL.svg
docs/scorebug_template/teams/2x/BUF.png
docs/scorebug_template/teams/2x/BUF.svg
docs/scorebug_template/teams/2x/CAR.png
docs/scorebug_template/teams/2x/CAR.svg
docs/scorebug_template/teams/2x/CHI.png
docs/scorebug_template/teams/2x/CHI.svg
docs/scorebug_template/teams/2x/CIN.png
docs/scorebug_template/teams/2x/CIN.svg
docs/scorebug_template/teams/2x/CLE.png
docs/scorebug_template/teams/2x/CLE.svg
docs/scorebug_template/teams/2x/DAL.png
docs/scorebug_template/teams/2x/DAL.svg
docs/scorebug_template/teams/2x/DEN.png
docs/scorebug_template/teams/2x/DEN.svg
docs/scorebug_template/teams/2x/DET.png
docs/scorebug_template/teams/2x/DET.svg
docs/scorebug_template/teams/2x/GB.png
docs/scorebug_template/teams/2x/GB.svg
docs/scorebug_template/teams/2x/HOU.png
docs/scorebug_template/teams/2x/HOU.svg
docs/scorebug_template/teams/2x/IND.png
docs/scorebug_template/teams/2x/IND.svg
docs/scorebug_template/teams/2x/JAX.png
docs/scorebug_template/teams/2x/JAX.svg
docs/scorebug_template/teams/2x/KC.png
docs/scorebug_template/teams/2x/KC.svg
docs/scorebug_template/teams/2x/LAC.png
docs/scorebug_template/teams/2x/LAC.svg
docs/scorebug_template/teams/2x/LAR.png
docs/scorebug_template/teams/2x/LAR.svg
docs/scorebug_template/teams/2x/LV.png
docs/scorebug_template/teams/2x/LV.svg
docs/scorebug_template/teams/2x/MIA.png
docs/scorebug_template/teams/2x/MIA.svg
docs/scorebug_template/teams/2x/MIN.png
docs/scorebug_template/teams/2x/MIN.svg
docs/scorebug_template/teams/2x/NE.png
docs/scorebug_template/teams/2x/NE.svg
docs/scorebug_template/teams/2x/NO.png
docs/scorebug_template/teams/2x/NO.svg
docs/scorebug_template/teams/2x/NYG.png
docs/scorebug_template/teams/2x/NYG.svg
docs/scorebug_template/teams/2x/NYJ.png
docs/scorebug_template/teams/2x/NYJ.svg
docs/scorebug_template/teams/2x/PHI.png
docs/scorebug_template/teams/2x/PHI.svg
docs/scorebug_template/teams/2x/PIT.png
docs/scorebug_template/teams/2x/PIT.svg
docs/scorebug_template/teams/2x/SEA.png
docs/scorebug_template/teams/2x/SEA.svg
docs/scorebug_template/teams/2x/SF.png
docs/scorebug_template/teams/2x/SF.svg
docs/scorebug_template/teams/2x/TB.png
docs/scorebug_template/teams/2x/TB.svg
docs/scorebug_template/teams/2x/TEN.png
docs/scorebug_template/teams/2x/TEN.svg
docs/scorebug_template/teams/2x/WAS.png
docs/scorebug_template/teams/2x/WAS.svg
docs/scorebug_template/teams.json
```

---

# r63 static ESPN scorebug v9 (2026-09-06)

The existing `scorebug` option now installs `espn-reference-v9`. No new option,
allocator owner, request, runtime hook or preset change is requested. See
`ASTRA_SCOREBUG_V9_REPORT.md` and `docs/scorebug_ingame/v9_native_audit.json`.
All shared GUI panels and protected files remain untouched in this worktree.

Only the existing shared help text needs a product edit. In
`mod_editor/gui/beta62_options.py`, replace `SCOREBUG_HELP` with:

```python
SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Fits one dark ESPN bar inside the safe area, "
    "with the ESPN mark on the left and white scores, clocks, quarter and down text. "
    "Team abbreviations stay live and possession stays yellow. Both team blocks stay dark; "
    "there are no timeout marks. Moves the kick meter up and hides the lineup strip. "
    "EXPERIMENTAL / UNWITNESSED v9; needs a game check.")
```

Concrete wiring audit for Claude:

- Dispatcher `_apply_all` tuple and kwarg: no new entry or kwarg. The static
  path remains `mod_build.build`, `plan.scorebug and not plan.scorebug_runtime`,
  calling `nfl2k5_scorebug_layout.apply_in_place`, which delegates to the v9
  writer. The existing runtime-owner tuple and `scorebug_runtime` kwarg stay
  unchanged. Do not enable that owner to install the static bar.
- Four status dicts: no new keys. Existing `scorebug_xbe` paths call
  `nfl2k5_scorebug_ingame.xbe_status`; image status uses the same writer's
  resource pins. Existing `scorebug`, `scorebug_runtime` and
  `scorebug_runtime_resources` fields remain. Old v8 or mixed inputs refuse;
  rebuild from the supported clean base.
- `BuildPlan`: retain `scorebug: bool = False`. Preserve current Basic off,
  Advanced off, Experimental on for the static option, and the current runtime
  settings. No preset promotion is part of this task.
- Gameplay Patches `PATCHES`: retain the existing `scorebug` row and its
  `r62_ui.SCOREBUG_HELP` reference; the replacement above contains both
  **Retail** and **Patch**. `scorebug` already belongs to `NEEDS_IMAGE`.
- Build `_option`: retain `Experimental ESPN scorebar` (26 characters),
  `needs_image=True`, `NOT_TESTED` badge, and the shared help/details reference.
- Allowlist: no new lines. Existing lines already ship
  `mod_editor/core/nfl2k5_scorebug_ingame.py`,
  `mod_editor/core/nfl2k5_scorebug_resources.py`,
  `mod_editor/core/nfl2k5_scorebug_source_art.py`, and
  `tools/nfl2k5_scorebug_layout.py`. Research PNGs/JSON and the native projection
  harness do not need to enter the product runtime closure.
- Runtime-closure imports: no new module/import is needed. Refresh any existing
  source digest pins for the changed files during release integration.
- Capability registry: no new surface or row. Keep the existing static option
  and the runtime diagnostic capability separate.
- Cave manifest: regenerate `data/nfl2k5_cave_reservations.json` using the
  existing `tools/nfl2k5_cave_oracle.py manifest` process under Claude's exclusive
  ownership. This task adds no allocation. Both existing XBE gates already
  compose the static owner through `tests/nfl2k5_allocator_stack.py` in the
  complete forward/reverse unions; neither gate is weakened.

The runtime hook module is unchanged. The shared collection compiler explicitly
retains its v8 atlas generator and staging scene, preserving its existing
resource hashes while static v9 replaces the generic static install. No team
selection, live timeout work or runtime-freeze repair is implied.

---

# r62 community stadium Blender add-ons review, 2026-09-06

**Decision: DO NOT SHIP Importer v0.11.1 / Exporter v0.3.0.** Real Blender
4.0.2 and retail Models checks are in `ASTRA_STADIUM_BLENDER_ADDONS_REPORT.md`.
The supplied scripts remain private review inputs in `.scratch/community/`;
there are no approved copies under `tools/blender/community/` and no version
bump suggesting the defects were repaired.

Add exactly these documentation paths to protected
`packaging/release-allowlist.txt` (deduplicate if another handoff added one):

```text
ASTRA_STADIUM_BLENDER_ADDONS_REPORT.md
docs/mod_editor/nfl2k5_stadium_blender_workflow.md
docs/mod_editor/nfl2k5_stadium_community_addons_proof.json
```

The guide link is
`docs/mod_editor/nfl2k5_stadium_blender_workflow.md#community-stadium-add-ons-withheld-from-beta-62`.
Do not add either community `.py`, its upstream README, or a
`tools/blender/community/` glob to the release allowlist. The new proof tool
and standalone audit tests are developer tools, not product dependencies.
The pre-existing Stadiums texture helper handoff remains separate.

| Integration point required by the brief | This review |
| --- | --- |
| Dispatcher `_apply_all` tuple / kwarg / four status dictionaries | No change; no patch or dispatcher participant |
| `BuildPlan` field / basic, advanced, experimental presets | No field; no preset enables these add-ons |
| Gameplay Patches PATCHES text containing Retail and Patch / NEEDS_IMAGE | No row or image dependency; no Retail Patch introduced |
| Build `_option` caption (at most 60 chars) | No checkbox |
| Runtime closure imports | None; never import `bpy` in Mod Studio |
| Capability registry | No new product surface or capability; no count changes |
| XBE owners / cave manifest / both gates | No change |

Do not present successful Models compilation as validation of Blender output:
the Models writer can accept the incorrectly rotated geometry. A future
community revision needs exact no-op bytes, correct handle axes, original-row
preservation, ambiguity refusal and safe output publication before it can be
reconsidered. Credit the community, not the submitted `author: OpenAI` label.
All protected files were left unchanged in this task.

# r62 calendar continuation: remaining integration, 2026-09-06

**EXPERIMENTAL / UNWITNESSED.** This section updates the calendar handoff
below against stack `288ba65`. The engine, complete allocator union, combined
option, presets, PATCHES row, Build checkbox and closure imports are already
landed. Do not duplicate those additions. The new deliverables are
`ASTRA_CALENDAR_ENGINE_REPORT.md`, the completed
`docs/mod_editor/nfl2k5_calendar_engine_capability.json`, a working bounded
module CLI, expanded proofs and the repaired Franchise explanation.

## Required registry merge and synchronized counts

Merge the **one object** in the capability JSON into
`mod_editor/capabilities/registry.v1.json`, sorted by ID. The ID is now
`nfl2k5.schedules_franchise.calendar_engine`; `surface` is
`schedules_franchise`, not the invalid `franchise`. Preserve the existing
gate-only primitive row as a separate diagnostic capability. The new row is
`offline-writer-proved` with runtime `not-tested`, never `runtime-proved`.
Its complete source identity, selector notes, porting limits and empty played
evidence array are present. Both commands are executable package forms:

```text
python3 -m mod_editor.core.nfl2k5_calendar_engine --xbe <source.xbe> --output <new-copy.xbe>
python3 -m tests.mod_editor.test_nfl2k5_calendar_engine
```

The first command writes only a new extracted executable copy, retains its
recognized 2004/2026 base, and cannot certify/install external schedule
templates. The combined 2026 image-build control remains the product path.

Apply these count changes **together with the registry merge**:

| File / exact old text | Required replacement |
| --- | --- |
| Protected `packaging/check_2k5_mod_studio_runtime.py`: `len(registry.capabilities) == 95` | `len(registry.capabilities) == 96` |
| Same file: `len(product_catalog.capabilities) == 57` | `len(product_catalog.capabilities) == 58` |
| Same file's success marker: `registry=95 sections=12 nfl2k5_capabilities=57` | `registry=96 sections=12 nfl2k5_capabilities=58` |
| `tests/mod_editor/test_phase1_packaging.py`: `registry has 95 cross-title rows` | `registry has 96 cross-title rows` |
| Same packaging test's runtime marker | `registry=96 sections=12 nfl2k5_capabilities=58` |
| `docs/mod_editor/2k5_mod_studio_getting_started.md`: `registry has 95 cross-title rows, including 53 Xbox NFL 2K5` | `registry has 96 cross-title rows, including 58 Xbox NFL 2K5` |

The doc's 53 is already stale: current metadata is 95 total = 57 Xbox NFL 2K5
+ 37 APF + 1 PS2. The candidate is 96 = 58 + 37 + 1. Product sections stay 12.
The packaging test also pins release labels, so it was left for this joint
protected integration rather than edited ahead of the live counts.

The new delivery suite validates the exact calendar object through the real
validator's file-check mode in an explicit 42-row test coverage envelope.
The full 96-row candidate passes schema and runtime catalog validation.
Full-registry **file checks still refuse on the pre-existing missing
`docs/research/apf_audio.md`** in this checkout, including before the merge.
Restore the historical evidence set in the integration checkout before
claiming that the whole registry passes file checks. Do not add dummy evidence
or change the validator to hide that failure. The public runtime probe also
requires the missing reviewed target metadata directory in a proper stage.

## Retain the landed dispatcher, Build and UI wiring

Keep import `from . import nfl2k5_calendar_engine as calendar_engine_patch`,
the `calendar_engine: bool = False` kwarg in `_apply_all`, `write_xbe_copy`
and `write_image_copy`, all forwarding and allocator adapters, and this final
owners tuple after the allocator:

```python
(calendar_engine, calendar_engine_patch,
 "calendar_engine_patch", "128-season calendar (experimental)"),
```

Keep `calendar_engine_patch.REQUESTS` in `_selected_space_requests` and the
scorebug resource lane's full union before allocation. Keep calendar deferred
out of early XBE passes and applied after the 2026 resource step. The four
status dictionaries use the existing shared `_grown_status_fields` helper:
`read_xbe(payload)`, `read_image(payload)`, `write_xbe_copy(result)` and
`write_image_copy(after)` must each include
`"calendar_engine": calendar_engine_patch.status(<those bytes>)`. Preserve
both the `calendar_engine_patch` receipt and `calendar_engine` final status.

Retain `BuildPlan.calendar_engine: bool = False`, its recipe/status/availability
paths, and normalization of either public `season_cap` or `calendar_engine`
to all four true: `season_cap`, `calendar_engine`, `season_2026`, `xbe_space`.
Basic false/false, Advanced false/false, Experimental true/true are the landed
cap/calendar preset values. If final integration gates fail, hold both
Experimental values false together until repaired, as the original handoff
requires; do not relabel the gate alone as a full repair.

**Additional review finding, protected fix:** `_build` validates the calendar
implementation flag but silently normalizes `season_cap=1` or `"yes"`. Add
the public flag to the existing boolean validation call, before normalization:

```python
tt._validate_lever_flags(plan.music_shuffle, plan.practice_squad_screen,
                         plan.abilities, plan.qb_spy,
                         plan.calendar_engine, plan.season_cap)
```

Also replace the stale comment on `BuildPlan.season_cap` with
`# combined 128-season franchise option; experimental/unwitnessed`.
The candidate function was compiled from the actual protected `_build`
source with only the extra argument and executed: all eight invalid cases
(`1`, `0`, `"yes"`, `None` for each flag) refuse with `boolean` before input
access. The live source still has the public-flag gap. Retain/add that
regression to `test_mod_build_beta62_integration.py` when wiring the fix.

Retain PATCHES text containing **Retail** and **Patch**, the exact
`calendar_engine_patch.UI_TEXT`, and `NEEDS_IMAGE` entries for `season_cap`
and `calendar_engine`. The landed Build option is:

```python
self.season_cap_check = self._option(
    f, "season_cap", "128-season franchise (experimental)",
    tt.calendar_engine_patch.UI_TEXT, badge=NOT_TESTED, needs_image=True)
```

The caption is 35 characters. The Build panel's plan already forwards both
checkbox values; preserve Studio/recipe forwarding with default false. No
second calendar checkbox or new Franchise save field is needed.

**Franchise wording is now applied in this branch**, with its existing
offscreen copy/reload/terminal-index regression updated:

> EXPERIMENTAL / UNWITNESSED. Use the calendar patch with your build's starting
> year for long franchises. A save alone does not identify that patch. Editing
> this year does not simulate seasons.

The separate gate-only module retains its truthful primitive limitations.

## Allowlist, runtime closure, manifest and final integration

Keep the already present allowlist lines for both calendar core modules and
the capability JSON. Add the previously requested missing report line:

```text
ASTRA_CALENDAR_ENGINE_REPORT.md
```

The Franchise panel and `tools/nfl2k5_franchise_schedule.py` already have
allowlist entries; retain their updated source. The latter's receipt now
counts actual differing header bytes, independent of enclosing buffer size.
No generated XBE, disc, `.scratch/`, assembler, development test or retail
fixture belongs in the runtime artifact.

Keep the landed closure imports
`mod_editor.core.nfl2k5_calendar_engine` and
`mod_editor.core.nfl2k5_calendar_engine_code`. The CLI adds only standard-library
`argparse`, `json`, `pathlib` and `sys`; no compiler/Unicorn/Capstone runtime
dependency is added. Existing preseason/playoffs14/season-length/season-cap/
allocator/rdata/bump-strength/cave-oracle and draft assembler imports remain.

Regenerate the protected cave manifest from final integrated sources with
Claude's normal manifest command and run both XBE gates and the oracle. The
gate/request/manifest owner lists already contain `nfl2k5_calendar`; do not
change its budget or rename the recorder's `nfl2k5_calendar_engine` owner.
No protected JSON or source fingerprint was manually changed here. Rebuild
the clean release stage with its reviewed metadata, run the runtime/packaging
checks with the new counts, and rerun the full registry file checks once
historical evidence is present. The report gives all local passing and
refused commands and Noah's precise outstanding witnesses.

Local final gates: memory writes **59 passed**; cave references **71 passed**
with `NFL2K5_CAVE_MANIFEST=.scratch/calendar-continuation/xbe-only-manifest-v2.json`.
The latter is an observed executable-only fixture (83 writer calls, 9,445
reservations, 75 checked source hashes, no image steps). It does not replace
the protected production manifest or claim a real-disc acceptance build.

---

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
# r62 franchise 2026 handoff, 2026-09-06

**The requested live feature is incomplete and must remain unavailable.** The
backend supplies host transactions and an installed but dormant native rule
kernel. `apply()` is for proof/owner composition only: its receipt explicitly
has `runtime_enforced=False` and `native_hooks=[]`. Connecting it directly to a
product checkbox would misrepresent what was built. `require_runtime_ready()`
raises before a disc copy. See `ASTRA_FRANCHISE_2026_REPORT.md` for the measured
save/writeback blockers and all unimplemented requirements. No protected file
was edited. This section is additive; earlier owners' instructions remain.

## Protected BuildPlan, allocator, dispatcher and four status dictionaries

Reserve the intended API `franchise_2026_rules: bool = False`. Exact bool only.
Basic, Advanced and Experimental all explicitly set false. Normalize a true
request by calling `nfl2k5_franchise_2026.require_runtime_ready()` immediately,
before a copy, allocation or output mutation. This currently refuses it. Keep
this same guard in `_apply_all` so callers cannot bypass BuildPlan preflight.
Recipe load, Studio forwarding, availability and receipts retain the false
field; no implicit enable from practice squads, calendar or season cap.

The eventual selected union integration belongs in `_selected_space_requests`
and `_xbe_space_adapter`: add `franchise_2026_rules` to both signatures/flag
forwarding paths and concatenate `nfl2k5_franchise_2026.REQUESTS` when selected.
Preflight must refuse first while `RUNTIME_READY` is false. Requests are now
**5,120 RX / 4,096 RW**, alignment 16, owner `nfl2k5_franchise_2026`; never
hardcode a VA. The gate union and manifest owner probe already include it.

Add the intended final dispatcher tuple after the allocator and existing
practice/season owners:

```python
("franchise_2026_rules", franchise_2026_rules, _franchise_2026_adapter),
```

Use a guarded adapter; do not substitute the dormant kernel's `apply` directly:

```python
class _Franchise2026Adapter:
    @staticmethod
    def status(payload):
        return "unavailable"

    @staticmethod
    def apply(payload):
        nfl2k5_franchise_2026.require_runtime_ready()
        return nfl2k5_franchise_2026.apply(payload)

_franchise_2026_adapter = _Franchise2026Adapter()
```

The adapter must be replaced with the real guarded runtime owner when the
missing hooks are delivered, rather than merely changing `RUNTIME_READY`.
Add keyword `franchise_2026_rules=False` to `_apply_all` and forward it at every
shared executable call. Add it to `wants_xbe_patch`, availability checks and
normalization/deferral/final-pass handling only with the early readiness guard.
Early `replace(plan, ...)` passes set it false. The eventual final pass forwards
`franchise_2026_rules=plan.franchise_2026_rules`. Until the guard is replaced,
a true flag has no final pass and no output. This is intentional refusal.

In `_grown_status_fields` and **all four dictionaries** (extracted reader,
image reader, extracted writer result, image writer result), expose:

```python
"franchise_2026_rules": "unavailable",
"franchise_2026_kernel": nfl2k5_franchise_2026.status(payload),
"franchise_2026_runtime_enforced": False,
```

Use the actual payload variable at each location. A dormant kernel reporting
`applied` must never mark `franchise_2026_rules` as applied or make the Build
option checked. False/off preserves the supplied executable normally.

## Gameplay Patches, NEEDS_IMAGE, Build and Coach's Desk

Intended PATCHES key: `franchise_2026_rules`. Caption:
`2026 franchise rules (unavailable)`.

Exact help, containing the required Retail and Patch words:

> Retail: Owned players form the game roster and IR has no in-season returns. Patch: 2026 franchise rules are not available yet. Saved counters and correct player results still need integration. EXPERIMENTAL / UNWITNESSED.

Include the key in NEEDS_IMAGE. The eventual complete feature requires the
matching calendar/ROST/save transport; a standalone XBE does not establish
those. Keep the row disabled with the above reason while unavailable. The
Build `_option` caption is `2026 franchise rules (unavailable)` (34 characters),
field `franchise_2026_rules`, with the same help and disabled state. Every
preset leaves it off. Do not present a working game-rule toggle or a manual
native roster screen in this revision.

Practice Squad screen coordination: keep its existing Coach's Desk table,
Active/Reserves tabs, native promote/demote and Free Practice behavior. The
future Game Day/IR pages should share that destination and identity resolver.
No additional menu row, callback, staging hook at 61730 or second promote/
demote implementation is installed here. A future manual page must distinguish
permanent promotion from standard elevation and charge only on acceptance.

## Allowlist, runtime closure, capability and manifest

Add these source lines to `packaging/release-allowlist.txt` if shipping the host
API/inspection tooling; no game data or companion payload belongs in a release:

```text
mod_editor/core/nfl2k5_franchise_2026.py
mod_editor/core/nfl2k5_franchise_2026_code.py
docs/mod_editor/nfl2k5_franchise_2026_capability.json
ASTRA_FRANCHISE_2026_REPORT.md
```

`nfl2k5_franchise_save.py` is already allowlisted. The C, .S and assembler are
development sources, not runtime dependencies. Add both new core modules to
the provider/runtime closure, including the explicit import list in
`packaging/check_2k5_mod_studio_runtime.py`. Refresh its and the provider's hashes
for changed `nfl2k5_franchise_save.py` using the existing exact-file process;
never remove or broaden pins. No GUI import is needed. The companion transport
uses only the Python standard library and the existing save codec.

Merge the complete schema-valid object in
`docs/mod_editor/nfl2k5_franchise_2026_capability.json` into the canonical registry.
It registers **inspection only**, ID
`nfl2k5.schedules_franchise.rules_2026_inspection`, `read-only-mapped`,
`gui.mode=view`, `gui.expose=false`. Game enforcement remains unavailable;
this classification does not certify a writer. Both backend.command and
validation_command use `python3 -m mod_editor.core.nfl2k5_franchise_2026 ...`.
Do not promote runtime.status from `not-tested` based on bounded instructions.
The registry requires `unsafe/deferred` rows to have null backend fields, so a
working inspection command cannot be classified as an unavailable writer.

The shared gate union, budget fixture and all manifest-builder owner lists are
updated. Claude alone must regenerate `data/nfl2k5_cave_reservations.json`.
The scratch manifest is an actual disposable-disc writer observation, not a
source-fingerprint bypass. It includes the dormant kernel's named allocations;
it does not certify native rule enforcement or a played save lifecycle.

## Hard gates before enabling the intended feature

1. Implement save-buffer size/allocation, native serializer/loader, wrapper
   integrity and migration together. No spare fields were allocated here.
   The memo's proposed ledger is 60,872 bytes at 2,479 players and the three
   actually unassigned player bits cannot hold the full histories.
2. Install one shared game-day projection boundary with Practice Reserves,
   depth/special-role remapping, launch-shortage refusal, and **every** result
   identity adapter. C5280 and 27DBC0 currently assume matching ownership slots.
3. Bind native IR entry, completed-team-game events, calendar day advancement,
   return/medical checks, CPU choices and rollover to the kernel. General IR
   capacity and all owner/cap consumers need the separate storage migration.
4. Implement native dated cutdown and both trade predicate/pending purge plus
   human acceptance guards; calendar predicates alone are insufficient.
5. Add elevation pay accounting and persistent identity/generation handling,
   complete native save/load/sim/played-result proofs, and Noah's R1-R5 witnesses.
   A host companion tied to a save digest cannot replace these steps.
# r62 Stadium editor handoff, 2026-09-06

**EXPERIMENTAL / UNWITNESSED.** See `ASTRA_STADIUM_EDITOR_REPORT.md` and
`docs/mod_editor/nfl2k5_stadium_blender_workflow.md`. This section precedes and
preserves the older handoffs. No protected file was edited by this task.

## Implemented integration outside protected files

`Nfl2k5StudioFacade._studio_for_session` supplies `writer.scene_source` to the
Stadium backend. Existing Export 3D model and Apply images from a 3D file calls
therefore reach the improved export/import already. `_SessionStadiumDelegate`
now supplies `replace_many`; the session preflights the full selected scene,
including earlier texture edits and its bounded position recipe, publishes
one edit set and retains one grouped undo action.

No new XBE owner, allocator request, patch flag or automatic preset action is
part of this resource editor. The existing unified Stadium texture/geometry
writer remains the build route.

| Required wiring location | Disposition for this job |
| --- | --- |
| Dispatcher `_apply_all` owner tuple and keyword forwarding | No addition; this is a user-authored SCNE resource edit. |
| Four status dictionaries `read_xbe`, `read_image`, `write_xbe_copy`, `write_image_copy` | No new XBE status key; do not imply an installed texture from executable bytes. |
| `BuildPlan` field, normalization, deferral, final pass | No new field. Existing session-to-unified-project Stadium texture edits supply the build. |
| Basic / Advanced / Experimental presets | No enablement in any preset. A user explicitly imports artwork. |
| Gameplay Patches `PATCHES` and `NEEDS_IMAGE` | No row/key. Suggested informational text only if needed: “Retail: Stadium artwork uses the original images. Patch: Applies the Stadium textures saved in your project. EXPERIMENTAL / UNWITNESSED.” |
| Build `_option` caption, at most 60 characters | No checkbox. If a build summary caption is required, use `Stadium textures from project` (29 characters). |
| Both XBE safety gates and allocator/cave union | No owner addition or manifest regeneration for this job. Existing code/data allocations are untouched. |

## Stadiums page in protected `mod_editor/gui/studio_qt.py`

Import:

```python
from mod_editor.gui.stadium_blender_panel_qt import (
    StadiumBlenderPanel, texture_import_summary,
)
```

The owned, offscreen-tested `StadiumBlenderPanel` is complete. Place it in the
Stadiums page's existing layout, preferably in a scrollable help area so the
477-scene list retains useful height. Its `exportRequested` signal connects
to `_export_stadium_scene_gltf`; its `importRequested` signal connects to
`_apply_stadium_textures_from_gltf`. Both existing slots perform the ready,
busy and selected-scene checks. The card's Save Blender helper action copies
the shipped Python script using the existing exclusive export writer.
Do not make a second backend or run Blender from Mod Studio.

Keep the existing bounded geometry button separately labelled. Rename the
texture action to `Import Blender textures`. Its ready tooltip is:

> Import the texture file saved by the Blender Stadium helper. Original image
> sizes are required. Shared surfaces change together. Unchanged images are
> skipped. The whole import must fit before any edits are staged.

Replace the success callback in `_apply_stadium_textures_from_gltf`. Receipts
now include `changed: bool`. An unchanged row has `write_result=None` and must
not be presented as “written” or mark the project dirty:

```python
receipts = result if isinstance(result, tuple) else ()
summary, changed = texture_import_summary(receipts)
box = QMessageBox(self)
box.setWindowTitle("Stadium texture import")
box.setIcon(QMessageBox.Information)
box.setText(summary)
box.setInformativeText(
    "EXPERIMENTAL / UNWITNESSED. Review the texture preview. "
    "Save your project and build a new game copy to test it. "
    "Undo restores the whole import."
)
box.addButton("Close", QMessageBox.RejectRole)
box.exec_()
self._set_status(summary)
if changed:
    self._mark_workspace_changed()
    self._select_stadium_texture(state.texture_list.currentItem(), None)
```

Update both construction and dynamic tooltips for model export: PNGs and
source-derived UV coordinates are appended after the unchanged position/index
buffer prefix. The whole buffer is longer, not byte-identical. The 0.01 unit
root is retained. After export, the success dialog should direct users to the
helper's File > Import entry and remind them to keep `.gltf` and `.bin`
together. All new copy uses plain words and no em dashes.

## Protected release allowlist

Add these exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/gui/stadium_blender_panel_qt.py
tools/blender/nfl2k5_stadium.py
tools/nfl_stadium_texture_bundle.py
tools/nfl_stadium_editor_proof.py
docs/mod_editor/nfl2k5_stadium_blender_workflow.md
docs/mod_editor/nfl2k5_stadium_blender_capability.json
docs/mod_editor/nfl2k5_stadium_part_ownership.json
docs/mod_editor/nfl2k5_stadium_editor_retail_proof.json
ASTRA_STADIUM_EDITOR_REPORT.md
```

Existing allowlisted modules changed in place: `nfl2k5_stadium_studio.py`,
`nfl2k5_stadium_texture_writer.py`, `mod_editor/studio/session.py`,
`mod_editor/studio/facade.py`, and `tools/nfl_scne_gltf.py`. Keep
`tools/nfl_vc_lz_fill.py` in the shipped dependency set. The Blender helper is
standard-library-only until Blender calls `register`, `import_stadium` or
`export_textures`; do not add bpy to Mod Studio's runtime dependencies.

## Protected runtime closure and provider fingerprints

In `packaging/check_2k5_mod_studio_runtime.py`, include import probes for:

```text
mod_editor.gui.stadium_blender_panel_qt
tools.blender.nfl2k5_stadium
tools.nfl_stadium_texture_bundle
tools.nfl_stadium_editor_proof
```

Retain the existing writer, Studio backend, Models UV decoder and
`nfl_scne_gltf`, `nfl_scne_inventory`, `nfl_txtr`, `nfl_tset_png_import`,
`nfl_vc_lz_fill` probes. The new writer imports the existing VC-LZ token
parser/serializer lazily to fill overly short streams without raising the
loader scratch beyond the retail-observed bound. The export tool imports
Models' existing UV decode helpers lazily. No network, image generator,
external process, capstone or bpy is a runtime dependency of these operations.

Refresh the exact SHA-256 values in the sealed provider closure for these
changed existing entries after reviewing this patch:

```text
mod_editor/core/nfl2k5_stadium_texture_writer.py
mod_editor/core/nfl2k5_stadium_studio.py
mod_editor/studio/session.py
tools/nfl_scne_gltf.py
```

SHA-256 values for this delivered source revision:

| Path | SHA-256 |
| --- | --- |
| `mod_editor/core/nfl2k5_stadium_texture_writer.py` | `dc1bf06c20c86411ff4c91e09003c9f561f3c7aada142ed522ca237d7d0d18f5` |
| `mod_editor/core/nfl2k5_stadium_studio.py` | `7ec5b2b65b3e6be605e91ae772dd15c3eb71ac46398e2ecab0a1c181cf4fef7d` |
| `mod_editor/studio/session.py` | `0b612dca07442ad0b0e1bdb19d38b1bf32ea78100804278a3736bb2f2ff95841` |
| `tools/nfl_scne_gltf.py` | `afeb666595742e2a96075fb9d0edb4d8ac913b9e1c2ebfa6ed3ba04496a57207` |

`mod_editor/core/providers.py` already lists these entries, and already lists
`tools/nfl_vc_lz_fill.py` and `mod_editor/core/nfl2k5_models.py`. The new helper,
workflow card and developer proof/compiler CLIs do not become executable
inputs to the sealed unified span subprocess; do not add that UI dependency
to its closure. Keep its current required bytes and imports narrowly scoped.
Refresh runtime-checker pinned constants only where they include these paths.
Until this is done, the sealed provider correctly refuses the changed files.
The task leaves these closure edits to Claude as requested in the brief.

## Capability registry

Merge the one row from
`docs/mod_editor/nfl2k5_stadium_blender_capability.json` into the canonical
registry, sorted by ID. ID: `nfl2k5.stadiums_fields.blender_textures`;
classification: `offline-writer-proved`; runtime: `not-tested`; GUI: edit,
explicit opt-in. It has `python3 -m ...` backend and validation commands.
Add the following entry to `_WORKSPACE_CAPABILITIES` in the protected
`mod_editor/gui/studio_qt.py`, so capability navigation opens this workflow:

```python
"nfl2k5.stadiums_fields.blender_textures": "Stadiums",
```

Do not add a gameplay patch or a second image-build path.
Run the registry validator with file checks after merging, update runtime
closure pins and exercise the existing Stadium export/import actions through
an actual packaged offscreen window. The checked-in source-free window test
skips explicitly when its developer uniform inventory is absent.

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
# r62 Senior Bowl: preparation only, native MVP activation blocked

This section belongs to `astra/r62-senior-bowl`. It is additive to every
previous handoff above. **EXPERIMENTAL / UNWITNESSED. The requested native
simulation MVP is incomplete.** `docs/mod_editor/senior_bowl.md` states the
exact code/ABI/save/sim/menu gaps. Nothing below authorizes treating dormant
component installation as a working game event. The dedicated Studio panel
and preview capability can be registered now; all native activation paths
must remain disabled and reject a programmatically true selection.

No protected product file was edited in this branch. The supplied original
`.S`, assembler and byte template, host configuration/preview/codec, standalone
suites, allocator union, both gate owner lists and manifest observer are ready
for review. No game, kernel, native file I/O or simulator execution is claimed.

## BuildPlan, presets, normalization and availability

In protected `mod_editor/core/mod_build.py`, add these fields next to the
other optional franchise owners:

```python
senior_bowl: bool = False
senior_bowl_settings: dict[str, object] = field(default_factory=lambda: {
    "scheme": "retail", "away": {"bank": 50, "side": "A", "era": 0},
    "home": {"bank": 51, "side": "H", "era": 0}})
senior_bowl_seed: int = 1
```

Set `senior_bowl=False` explicitly in `softdrink_basic`, `softdrink_advanced`
and `softdrink_experimental`; no preset enables it. Personal preview choices
may persist across preset changes, but every preset resets activation false.
Validate through `senior_bowl_patch.Settings.from_dict` and the panel's seed
range 0..2147483647; reject bool/noninteger seeds and unknown settings. Keep
settings/seed in project/BuildPlan serialization and declare them subsettings
in the existing no-invisible-capability/Build-field coverage table, not as
separate toggles. Runtime component selection accepts u32 seeds; the panel
intentionally uses the signed Qt spin-box range and refuses larger project
seeds instead of silently clamping them.

Before any build output is created, validate that `type(plan.senior_bowl) is
bool` and refuse true while `NATIVE_EVENT_AVAILABLE` is false:

```python
if plan.senior_bowl and not senior_bowl_patch.NATIVE_EVENT_AVAILABLE:
    raise ValueError(senior_bowl_patch.NATIVE_BLOCKER)
```

Module importability is not runtime availability. `availability()` should
report the native `senior_bowl` toggle unavailable and the host panel usable.
Include the flag in `wants_xbe_patch` for future coverage, inspect/status
projection and final result reporting, without bypassing the early refusal.
Do not imply that the existing native Practice Squad screen proves this event's
save/simulator/menu paths.

When the documented native implementation actually becomes ready, normalize
its dependency flags and construct the complete request union before any owner
is applied. Its present requests are exactly:

```python
(("nfl2k5_senior_bowl", "code", 4096, 16),
 ("nfl2k5_senior_bowl", "data", 65536, 4096))
```

The budget fixture has these actual rows, replacing the 16384-byte RX estimate.
Future code/descriptor growth needs an explicit request change within the
original 16384/65536 allowance and a fresh full union. No borrowed allocator
tail or arbitrary VA is an allocation.

## Dispatcher tuple, keyword, allocator adapter and four dictionaries

## r62 Guardian overlay, route A (2026-09-06)

This is the integration handoff for `ASTRA_GUARDIAN_OVERLAY_REPORT.md`.
**EXPERIMENTAL / UNWITNESSED.** All protected files remain unchanged in this
branch. The executable, paired resource/ROST transaction, allocation union,
manifest recorder, standalone proofs and capability handoff are implemented.
Do not advertise the old C replacement as this feature.

### Record ownership and the Rosters session

Reserve physical **record +0x53 bit 5 (0x20)** for `guardian_cap`. The complete
little-endian word map at +0x52 is: locks `0x001F`, abilities `0x1EE0`, Star Tag
`0x0100`, Guardian cap `0x2000`, unassigned `0xC000`. The abilities runtime's
mask excludes Guardian. There is no spare helmet enum: keep Helmet 0/1 (A/C).
The new native clone hook at `0xC16CD` copies only `0x2000`; do not replace it
with an uncoordinated full-word copy in another owner's clone patch.
`nfl2k5_player_tags.apply_body` now masks star bit 0 and preserves its neighbors.

The parallel Rosters owner should wire its **Guardian cap** control separately
from Helmet, Star Tag and abilities. The existing record codec already preserves
the bit through `unknown_53_high`; Guardian is **0x10 in that shifted field**.
A document operation reads `bool(record.values['unknown_53_high'] & 0x10)` and
sets/clears only that mask through the document's normal edit/journal transaction.
The byte-level APIs `guardian.record_selected(raw84)` and
`guardian.set_record_selected(raw84, bool)` enforce the physical format.
Add `guardian_cap` as a derived `Record.get`/`Record.set` property (same pattern
as abilities), boolean CSV column with explicit 0/1 validation, and bulk edit
choice. Preserve `unknown_53_high` as the backing field so the existing ability
and unknown-bit round trip remains intact. Binary roster/save export/import
already preserves the complete record. Clone/import via document transactions
must retain this bit or explicitly clear it for a genuinely new identity.

Store the edited bit in the composed roster document before exporting its
resource. For normal GUI builds use `guardian_players=None` below, retaining
those authored selections. Do not persist a roster index as player identity.
For controlled CLI/project snapshots, the optional `guardian_players` array
contains `{pool, index, record_sha256}` entries, where the SHA-256 is of that
exact 84-byte record with only the Guardian bit cleared. Null means retain;
`[]` explicitly clears all. The writer rejects mismatched/duplicate identities
before opening a writer. Refresh a pin only after the owning document has
resolved the same player through its existing identity/provenance mechanism.
A changed name, star, ability or other record field invalidates an old pin.
Never silently relax this into fuzzy matching.

UI help: `Guardian cap requires the experimental Guardian overlay image.
Existing saves need their own player selections. Practice does not save caps
onto players.` The cap artwork is one shared neutral quilt texture. Label it
**Global Guardian cap artwork** under Uniforms & Equipment, with a shared-art
explanation. The compiler currently owns the fixed neutral profile; do not
expose unsupported per-uniform art or an arbitrary artwork upload operation.

### Dispatcher, allocator and all four status dictionaries

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
from . import nfl2k5_senior_bowl as senior_bowl_patch
```

Add `senior_bowl: bool = False` to `_apply_all`, `write_xbe_copy` and
`write_image_copy` signatures and forward `senior_bowl=senior_bowl` at every
call. Validate bool and refuse a true unavailable selection at the beginning
of each public writer and `_apply_all`, before mutation. Add the same
`senior_bowl=False` keyword to `_selected_space_requests` and
`_xbe_space_adapter.__init__`; include
`+ (senior_bowl_patch.REQUESTS if senior_bowl else ())` and forward the keyword
at both adapter construction and complete-union planning sites. Those
functions must also reject a true unavailable selection, before allocation.

Use a guarded adapter, rather than directly exposing the development-only
component installer as if it launched a native event:

```python
class _senior_bowl_adapter:
    def status(self, payload):
        return senior_bowl_patch.status(payload)

    def apply(self, payload):
        if not senior_bowl_patch.NATIVE_EVENT_AVAILABLE:
            raise ValueError(senior_bowl_patch.NATIVE_BLOCKER)
        return senior_bowl_patch.apply(payload)
```

Add this exact `_apply_all` final-owners tuple after the allocator entry:

```python
(senior_bowl, _senior_bowl_adapter(), "senior_bowl_patch",
 "Senior Bowl native event (unavailable)"),
```

This tuple is deliberately unreachable for true in this revision. Keep false
in the initial pass when resources/scorebug defer grown owners, reserve the
selected union once, and forward the actual flag to the final `_apply_all`
pass, along with BuildPlan's settings/seed only when a native settings adapter
exists. **The present `apply(payload)` takes no settings and installs zero
retail hooks. Do not claim that kit/project choices were installed in-game.**
The future implementation must add a settings-aware adapter and repinned
immutable configuration when those settings acquire native consumers.

`_grown_status_fields(payload)` is shared by the four status returns. Add:

```python
"senior_bowl": senior_bowl_patch.status(payload),
"senior_bowl_native_available": senior_bowl_patch.NATIVE_EVENT_AVAILABLE,
```

The `senior_bowl` status is explicitly **component installation status**; pair
it with the availability bit in displayed text and receipts. The four required
consumers must read the actual final byte object:

| Dictionary | Entry |
| --- | --- |
| `read_xbe` | `senior_bowl_patch.status(payload)` plus false native availability |
| `read_image` | same, from the read image's XBE payload |
| `write_xbe_copy` | same, from final `patched` |
| `write_image_copy` | same, from the post-resource, grown final XBE |

Extend `mod_build.inspect`'s `_grown_status_fields` key allowlist to include
both fields. Never infer native readiness from applied code or a successful
allocator seal. Restore the availability bit only after the substantive
native implementation and its acceptance gates have landed.

## Gameplay Patches PATCHES, NEEDS_IMAGE and Build tab

Protected `gameplay_patches_panel_qt.py`: add the key `senior_bowl` to
`NEEDS_IMAGE` and the following PATCHES row, then disable its checkbox with
the blocker text even when a disc is loaded:

```python
("senior_bowl", "Senior Bowl native event (not available)",
 senior_bowl_patch.HELP_TEXT),
```

`HELP_TEXT` contains the required words **Retail** and **Patch**, explains
preparation, and says in-game simulation/saving/menus are unavailable. Retain
the EXPERIMENTAL / UNWITNESSED label. A prepared status must not enable the
checkbox in a refresh or source-change callback.

Protected `build_panel_qt.py`, using its existing gameplay layout:

```python
self.senior_bowl_check = self._option(
    gl, "senior_bowl", "Senior Bowl native event (not available)",
    senior_bowl_patch.HELP_TEXT, badge=NOT_TESTED)
self.senior_bowl_check.setEnabled(False)
self.senior_bowl_check.setToolTip(senior_bowl_patch.NATIVE_BLOCKER)
```

Caption length is 40 characters (under 60). Add the field to checkbox reload,
reset/preset clearing, selection summaries and `_make_plan`, preserving its
forced-off state. Persist panel settings/seed independently. Do not add an
in-game Simulate button, stock modifier or playable toggle to another panel.
A disabled control alone is insufficient: the backend refusal above is
required for reopened/manually edited project files.

## Studio tab registration and project/session binding

In protected `studio_qt.py`, import and construct
`mod_editor.gui.senior_bowl_panel_qt.SeniorBowlPanel`. Register one **Senior
Bowl** tab alongside the Gameplay page's existing `extra_tabs`, by extending
the tuple already supplied to `GameplayPanel`, not editing that protected
panel or colliding with the existing Practice/Practice Squad descriptors:

```python
self._senior_bowl_panel = SeniorBowlPanel()
# Existing extra_tabs plus:
(self._senior_bowl_panel, "Senior Bowl")
```

`settings_changed` emits `options()` containing exactly `senior_bowl=False`,
`senior_bowl_settings` and `senior_bowl_seed`. Save those through the normal
Studio project dictionary/BuildPlan and restore with `set_options`. Connect
source/session clearing to `set_players((), "")`; avoid retaining a class
from another franchise. The page can read its own signed SAVEGAME.DAT through
Open franchise save, with bounded reads of that file and its EXTRA only.
For a composed Studio roster/save snapshot use
`prospects_from_document(document)` then `panel.set_players(players, source)`;
set the known position scheme first. Do not pass a disc as a save or silently
reclassify records. `selected_player_index` returns the actual identity after
sorting, not the row ordinal.

Preview projects use `.2k5senior`, schema `nfl2k5_senior_bowl_project/v1`.
Standalone save/open buttons are already implemented in the owned panel.
Missing source files load choices and clear stale rosters. A changed embedded
class identity refuses. None of these writes touch SAVEGAME.DAT/EXTRA or
constitute the native event persistence path. Keep project/source operation
guards consistent with other Studio pages during a running build/session edit.
No displayed GUI was used; five offscreen panel tests cover the supplied API.

## Allowlist, runtime closure, capability and manifest

Add these exact protected `packaging/release-allowlist.txt` entries:

```text
mod_editor/core/nfl2k5_senior_bowl.py
mod_editor/core/nfl2k5_senior_bowl_code.py
mod_editor/gui/senior_bowl_panel_qt.py
docs/mod_editor/senior_bowl.md
ASTRA_SENIOR_BOWL_REPORT.md
```

Add explicit closure imports in protected
`packaging/check_2k5_mod_studio_runtime.py`:

```text
mod_editor.core.nfl2k5_senior_bowl
mod_editor.core.nfl2k5_senior_bowl_code
mod_editor.gui.senior_bowl_panel_qt
```

Retain transitive closure for roster records, practice squad, franchise save,
allocator, cave oracle and their existing imports. GNU as, Unicorn, Capstone,
retail evidence files and the research corpus are development dependencies
only, not requirements for the preview or byte installer. Pin these new local
imports through the current provider/staged-closure mechanism; do not bypass
closure tests or edit release versions/workflows for this feature.

Merge `docs/mod_editor/nfl2k5_senior_bowl_capability.json` into the canonical
registry using the existing serializer/validator. ID is
`nfl2k5.franchise.senior_bowl_preview`, existing surface `schedules_franchise`,
classification `read-only-mapped`, runtime `not-tested`, GUI `view`, default
false. This truthfully advertises the host preview. It is not a native-event
capability. Both backend and validation commands use `python3 -m` dotted
modules so registry file-check mode resolves them. No new surface enum is
needed. If native activation lands later, add a separately scoped writer
capability with its actual runtime evidence and revised validation commands.

Already edited unprotected integration: the actual-request budget fixture,
`tests/nfl2k5_allocator_stack.py` REQUESTS/compose owner tuples, both XBE gates'
setUpClass owner assertions plus full component write/ownership cases, and
`nfl2k5_cave_manifest.py` append/reservation/module/extra-owner lists, request
union, ordinary owner probe and synthetic-probe lists. The manifest probe
records dormant components only. Claude alone regenerates protected
`data/nfl2k5_cave_reservations.json` after integration. Keep source fingerprint
checks and all existing owners. No real-disc build or newly generated complete
release manifest is claimed by this branch; the added manifest unit proof
observes this actual writer and its full named RX/RW allocations.

# r62-bone-import handoff, 2026-09-06

This section supersedes the r61b Animations import-disabled handoff. The core,
Animations panel, standalone tests and owner-composition helpers are implemented.
EXPERIMENTAL / UNWITNESSED. Protected files remain untouched. No gameplay or
DCC/Blender acceptance is implied. See `ASTRA_BONE_IMPORT_REPORT.md` and
`docs/mod_editor/nfl2k5_animation_import.md` for scope and witness requirements.

## Protected integration decisions

This is an explicit per-resource output-copy editor, not a preset executable
patch. An arbitrary user's sidecar, source resource and edited rotations cannot
be represented by a boolean BuildPlan setting. Do not silently apply the default
embedded one-word composition witness to user builds.

| Required integration point | Concrete decision |
| --- | --- |
| `nfl2k5_throw_tuning._apply_all` dispatcher tuple and kwarg | No new production tuple or kwarg. Do not add `animation_xbe.apply` with no Replacement: that default is only the safety-gate witness. Explicit user imports go through `nfl2k5_animation_import.write_import_copy` or `nfl2k5_animation_xbe.write_import_copy`. |
| `_selected_space_requests` / `_xbe_space_adapter` | No flags or adapter; animation XBE `REQUESTS = ()`. No allocation, page expansion, code or runtime state. |
| Four status dictionaries (loose-XBE inspection, disc inspection, `_apply_all` result, final apply result) and `_grown_status_fields` | No boolean status entry. A clip's original/applied/foreign state depends on its compiled Replacement and must not be reported as one universal patch state. The panel displays the actual preflight and output receipt. |
| `BuildPlan` field, normalization, deferral and final pass | None. No automatic clip or body mutation during the shared build pass. |
| Presets `basic` / `advanced` / `experimental` | None enable an animation or limb edit. The dedicated panel requires a selected source, edit and successful preflight. |
| Gameplay Patches `PATCHES` text and `NEEDS_IMAGE` | No row and no NEEDS_IMAGE entry. If a discoverability cross-link is desired, exact copy: **Retail: original motions and limb lengths. Patch: open Animations to check an edit and write a new copy.** Do not turn the cross-link into a toggle. |
| Build tab `_option` caption | No `_option`. Reserved cross-link caption if one is wanted: **Animation import (Experimental)** (31 characters including the space before the parenthesis; comfortably below 60). |
| Studio navigation | Keep the existing Animations registration. No new panel is necessary. |

In `studio_qt.py`, in the source-follow block immediately before the existing
`self._animations_panel.set_source_paths(*paths)` / `.reload()`, set:

```python
self._animations_panel.image_field.setText(str(source))
```

Set it whenever the source disc changes, even while resource paths are still
being prepared. The field's signal invalidates pending import preflight. The
panel's **Choose source disc** control already works without this convenience
wiring. Embedded imports explicitly use the optional retail XBE field and write
a new standalone XBE; they do not silently install it into a disc.

## Release allowlist and runtime closure

Add these exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_animation_import.py
mod_editor/core/nfl2k5_animation_bones.py
mod_editor/core/nfl2k5_animation_xbe.py
docs/mod_editor/nfl2k5_animation_import.md
docs/mod_editor/nfl2k5_animation_import_capability.json
```

The existing core animation/math/panel, Models, XBE helpers and tools are already
allowlisted. In `packaging/check_2k5_mod_studio_runtime.py`, add these module names
to the runtime import list beside the existing animation entries:

```python
"mod_editor.core.nfl2k5_animation_import",
"mod_editor.core.nfl2k5_animation_bones",
"mod_editor.core.nfl2k5_animation_xbe",
```

Expand its animation lazy-tool loop to include `nfl_vc_lz_fill`,
`nfl_scne_gltf`, and `nfl_uniform_color_xiso_direct_patch`; all three files already
appear on the allowlist. Retain `nfl_outer`, `nfl_motion_inventory`,
`nfl_scene_probe`, `nfl_scne_inventory`, `nfl_txtr` and `xbe_info`.

Add assertions that `compile_import`, `write_import_copy`, `compile_limb`,
`write_limb_copy`, and the embedded `status`/`apply` methods are callable;
`nfl2k5_animation_xbe.status(b"bad") == "foreign"`; and a fresh offscreen
AnimationsPanel has its Import button disabled. Do not replace the latter with
an assertion that `IMPORT_ENABLED` is false: the button is now gated per plan.
No C compiler, private reports, recovered-C source, or evidence files are runtime
imports. The high-body C comparison lives only in the standalone evidence test.

## Capability change

Replace the existing `nfl2k5.animations.inspect_export` object in
`mod_editor/capabilities/registry.v1.json` with the complete schema-valid object
in `docs/mod_editor/nfl2k5_animation_import_capability.json`. Preserve the stable
ID so existing navigation continues to resolve. The object changes classification
from `extract-only` to `offline-writer-proved`, backend operation from `export`
to `write`, GUI mode from `export` to `edit`, and replaces the old disabled-import
constraints with the exact gated subset. Runtime status remains `not-tested`.
Both backend.command and validation_command use `python3 -m` with an actual
repository module. The validation command checks packaged CLI availability;
the evidence section names the substantive standalone tests. The same panel
contains clip, limb and authored-gesture actions, so no extra invisible surface
or generic BuildPlan field is introduced.

## Occupied embedded roots and shared gates

`nfl2k5_animation_xbe` owns only the explicitly pinned occupied spans
`0x86d478..0x86e014` (2,972 bytes) and `0x851e38..0x85291c` (2,788 bytes), with
writes restricted to their main quaternion words, plus the affected section
header's digest. These are live animation data, not free space. Retail `.rdata`
flags are 7 and stay 7. No `.text` mutation and no cave bytes occur.

The checked-in test union already includes its empty `REQUESTS` and default
one-word witness in both orders. Both XBE gate setUpClass methods explicitly
check that the owner composed. The manifest builder now includes the owner in
its module/request/compose/status/extra-owner lists and declares both complete
root reservations, including unchanged bytes. Do not add an allocator budget
row: zero-byte requests are invalid and this owner has no allocation.

Claude must regenerate the protected
`data/nfl2k5_cave_reservations.json` with the existing oracle manifest command
after integration, with the disk-space rule respected. This session did not
regenerate it. The writer checks the existing complete retail manifest for
other-owner overlaps as well as its own explicit pinned spans. Generated
manifest rows for this owner may also include observed digest bytes in retail
or grown headers; those do not grant any additional resource write range.

## Validation and user witness handoff

Run these standalone files (Qt offscreen), and retain their precise skip reasons
if private assets or the C compiler are absent:

```text
tests/mod_editor/test_nfl2k5_animation.py
tests/mod_editor/test_nfl2k5_animation_import.py
tests/mod_editor/test_nfl2k5_animation_retail.py
tests/mod_editor/test_nfl2k5_animation_import_retail.py
tests/mod_editor/test_animations_panel_qt.py
tests/mod_editor/test_xbe_patch_memory_writes.py
tests/mod_editor/test_xbe_patch_cave_references.py
```

For the corpus set `NFL2K5_ANIMATION_FULL_CORPUS=1`; provide the existing resource
inventory via `NFL2K5_ANIMATION_INVENTORY` when not using `.scratch/`. The full
corpus has 5,198 resources and 14,091,296 main/auxiliary words. No whole image or
pack is read into memory. Compact disposable XDVDFS tests verify byte-identical
no-edit output, the authored referee clip, both LODs/SKEL, exact changed ranges,
replay, directory/source refusals and cleanup. Real retail offsets are checked
read-only. A full retail output-copy acceptance build was intentionally not
started with only about 102 GiB free on the main drive; it would break Noah's
100 GB floor. No acceptance disc or pack copy remains in `.scratch/`.

Before promising import, complete Noah's witness list in the report: unchanged
round trip and edited clip through start/blend/loop/end/mirror/replay, then both
LODs, head/hands/equipment, body profiles, planted feet, hand-to-ball and opponent
contact for the limb. Throws/tackles need both actors and release/contact timing;
this revision does not expose paired-action or throw-style authoring.
from . import nfl2k5_guardian_overlay as guardian_overlay_patch
from . import nfl2k5_guardian_resources as guardian_resources
```

Add `guardian_overlay: bool = False`,
`guardian_everyone_practice: bool = True`, and the image-only optional
`guardian_players=None` through `_apply_all`, `write_xbe_copy`,
`write_image_copy` and forwarded `write_copy` kwargs as applicable. Validate
both switches as actual booleans; roster recipes are meaningful only for
image operations. Raw XBE writes are a component operation and must retain
explicit matching-resource dependency text in their receipt.

Extend `_selected_space_requests(..., guardian_overlay=False)` with
`guardian_overlay_patch.REQUESTS if guardian_overlay else ()`, extend
`_xbe_space_adapter` and every selected-owner predicate with this flag, and
include it in complete request unions passed to the scorebug installer.
The actual owner is `nfl2k5_guardian_overlay`, **496 bytes RX, zero RW/RO**.
It replaces the planned `nfl2k5_guardian_cap_overlay` 2048/336 rows in the budget
fixture. It requires v3 automatically. There is no bitmap: stored record flags
and fresh native texture lookup remove the proposed persistent cache.

Settings adapter and final `_apply_all` tuple after the allocator entry:

```python
class _guardian_overlay_adapter:
    def __init__(self, everyone_practice):
        self.everyone_practice = everyone_practice
    @staticmethod
    def status(payload):
        return guardian_overlay_patch.status(payload)
    def apply(self, payload):
        return guardian_overlay_patch.apply(
            payload, guardian_everyone_practice=self.everyone_practice)

(guardian_overlay,
 _guardian_overlay_adapter(guardian_everyone_practice),
 'guardian_overlay_patch', 'experimental Guardian cap overlay'),
```

Add to `_grown_status_fields(payload)`:

```python
'guardian_overlay': guardian_overlay_patch.status(payload),
'guardian_overlay_settings': guardian_overlay_patch.read_settings(payload),
```

Verify the helper expands into **all four** output dictionaries: `read_xbe`
(with `payload`), `read_image` (with `payload`), `write_xbe_copy` (with `result`),
and `write_image_copy` (with its final re-read `patched` XBE). Image readers
also expose `guardian_resources.image_status(image_path)` as
`guardian_overlay_resources`, so a resource/XBE mismatch cannot appear ready.
The executable `status` by itself never proves resources are installed.

### BuildPlan, presets, deferral and the paired resource pass

In protected `mod_editor/core/mod_build.py` add these fields:

```python
guardian_overlay: bool = False
guardian_everyone_practice: bool = True
guardian_players: list[dict] | None = None
```

Set Guardian overlay **false in Basic, Advanced and Experimental**. The
practice preference is true within the explicitly enabled feature. Preserve
it in project normalization/serialization. Require that `guardian_cap` (the
existing route B option) and `guardian_overlay` are mutually exclusive. Reject
a non-null `guardian_players` recipe with the overlay disabled. Include new
fields in the recognized project keys and CLI forwarding.

Use `defer_grown = plan.scorebug_runtime or plan.guardian_overlay` in the
initial image pass. As in the existing scorebug path, defer the allocator and
all selected owners until the complete request union is known; always defer
Guardian's executable until its paired resources can be staged. All selected
owners must be reserved once on the supported base. Never append a new request
to an already-sealed allocator directory.

After fixed resource and authored roster passes, run existing runtime scorebug
resource installation first when selected, reserving Guardian's request in
that same union. Then run:

```python
rec = guardian_resources.apply_to_image(
    target,
    guardian_everyone_practice=plan.guardian_everyone_practice,
    guardian_players=plan.guardian_players,
    extra_requests=tuple(r for r in all_selected_requests
                         if r[0] != guardian_overlay_patch.OWNER),
)
receipt['steps'].append({'step': 'guardian_overlay', **rec})
```

The module reserves its own request on an ungrown base and installs into a
pre-reserved union otherwise. Exclude its own row from `extra_requests` because
the allocator rejects duplicate owner/kind rows. It stages both B models, one
TXTR, optional ROST bit edits and executable before mutation; pack and XBE
transports share an ordinary-I/O rollback boundary. Its in-place target must
be the private build copy. The final dispatcher pass replays Guardian with the
same settings and installs every other selected owner into the reserved union.
Re-read the final XBE for every status receipt. `write_image_copy` needs the
same sequencing, deferral and final pass as `mod_build`.

The append grows outer 3 by 88,544 bytes and pack 0 by 88,064 sector-aligned
bytes. Every subsequent outer virtual offset moves by 43 sectors; physical
bytes in packs 1..F remain fixed. Current archive/XDVDFS locations are resolved
fresh. This path also handles an already-moved pack after earlier scorebug or
music writes. The old scorebug **installer** pins retail pack geometry, so do
not run it after Guardian; its status reader has a moved-archive fallback.
Music's later streaming rebuild can consume the updated common group. Continue
to use the existing build's `file_grow` v2 export chain for both appended pack
and XBE extents, and verify export/reapply after this handoff is wired.

### Gameplay Patches and Build tab

In protected `gameplay_patches_panel_qt.py`, add a `PATCHES` row keyed
`guardian_overlay`, title **Guardian caps (experimental)**, using this exact
plain help (also `guardian_overlay_patch.HELP_TEXT`):

`EXPERIMENTAL / UNWITNESSED. Retail has no separate Guardian cap. Patch:
selected players wear a padded cover over either helmet. Caps for everyone
in practice is optional. A missing cap texture keeps the normal helmet.
Requires the matching models and global cap artwork.`

Add `guardian_overlay` to `NEEDS_IMAGE`. Do not offer a resource-free raw-XBE
GUI switch. Route A and the old route B checkbox must not be simultaneously
selectable. Add the dependent **Caps for everyone in practice** preference to
project controls; disable that control while the overlay is disabled.

In protected `build_panel_qt.py`, `_option` captions (both <=60 characters):

- `guardian_overlay`: **Guardian caps (experimental)**
- `guardian_everyone_practice`: **Caps for everyone in practice**

Include both in plan extraction, loaded-project restoration and change signals.
Rosters selects individual people; the practice option does not bulk-edit them.

### Packaging, runtime closure and capability

Add exact allowlist lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_guardian_overlay.py
mod_editor/core/nfl2k5_guardian_overlay_code.py
mod_editor/core/nfl2k5_guardian_resources.py
mod_editor/core/nfl2k5_resource_growth.py
docs/mod_editor/nfl2k5_guardian_overlay_capability.json
```

Retain the existing shipped `nfl2k5_guardian_cap.py`, `nfl2k5_models.py`,
`nfl2k5_p8_texture_writer.py`, `nfl2k5_player_tags.py`, music archive,
XBE storage/allocator and their existing texture/model tool closure. Add the
four new dotted core modules to the import list in protected
`packaging/check_2k5_mod_studio_runtime.py`. The generated byte module removes
GNU `as` from runtime requirements; `.S`, assembler and tests are development
sources and need not ship. No retail binary, disc, texture span or scratch proof
belongs in an allowlist.

Merge `docs/mod_editor/nfl2k5_guardian_overlay_capability.json` into the canonical
registry, without changing its `offline-writer-proved` classification or
`runtime.status = not-tested`. The schema-valid backend command is
`python3 -m mod_editor.core.nfl2k5_guardian_resources apply <private-build-copy.iso>`;
validation is `python3 -m mod_editor.core.nfl2k5_guardian_resources check <image.iso>`.
Both resolve a dotted module in registry file-check mode.

### Manifest and acceptance after wiring

The generator's owner lists, allocator dormant union and gate union are updated
locally. When protected
BuildPlan fields land, also set `guardian_overlay=False` and
`guardian_players=None` in its separate dormant-owner base build, just like
scorebug/abilities deferral, to avoid pre-sealing the request directory there.
Claude must regenerate protected `data/nfl2k5_cave_reservations.json` using the
normal manifest command against the fully wired stack. The private manifest
used here comes from `test_nfl2k5_guardian_manifest.py`, which observes every
actual XBE writer and requires complete changed-byte attribution, but expressly
records **no disc/resource build**. It is not a replacement release manifest.

Run all four Guardian test files, both complete XBE gates in both orders, the
normal release-manifest suite after regeneration, capability/runtime closure,
and integrated opt-in image + modpack export/reapply acceptance. The current
system drive was already below Noah's 100 GB free target, so no full disc copy
was made in this session. Use sufficient free capacity and disposable temporary
directories for those final integrated images. Noah's required played witness
is in the report; offline proofs do not establish GPU appearance or saved-game
lifecycle coverage.

---

# r62 MyCareer and independent Crib movie cut, 2026-09-06

This section is additive. The supplied backends, own Qt page, generated assembly,
tests and report are implemented. The files listed as protected in ASTRA_BRIEF.md
have not been edited. Claude applies the following concrete integration. Keep
both features **EXPERIMENTAL / UNWITNESSED**, with no played-runtime claim.

## BuildPlan, presets, preflight and ordering

Add these fields to `mod_editor/core/mod_build.py`:

```python
my_career: bool = False
my_career_setup: str | None = None  # path to prepared MyCareer.json
crib_reclaim: bool = False
```

Basic, Advanced and Experimental explicitly set `my_career=False`,
`my_career_setup=None`, `crib_reclaim=False`. Add both modules to availability
checks and both flags to `wants_xbe_patch`, normalization, serialization, preset
round-trips and inspection/status key forwarding. Validate exact booleans.
When `my_career` is true, require a nonempty setup, call
`nfl2k5_my_career.read_setup(plan.my_career_setup)` before copying an image,
freeze its returned 1280 bytes, and set `xbe_space=True`. Reject a setup supplied
without its option. An unconfigured `apply(payload)` exists for owner/gate
composition; it must not be offered as a configured MyCareer Build.

Do not enable practice-squad features merely for MyCareer. If they are selected,
preserve their existing prerequisite normalization. MyCareer understands their
reserve metadata. The small change in `nfl2k5_practice_reserves.status` recognizes
only MyCareer's complete sealed installation at the shared copy-helper entry;
retain that change. No draft-AI picker, cap, roster limit or progression setting
is implicitly enabled or disabled.

Add MyCareer to the existing final allocator pass and all deferral predicates
around the scorebug runtime path. On the preliminary pass pass `my_career=False`
and `my_career_setup=None`; reserve its request in the **complete final union**
passed to `runtime_apply_in_place(extra_requests=...)`. The final `_apply_all`
receives `my_career=plan.my_career, my_career_setup=frozen_setup` along with every
other selected owner. Preserve the existing allocator-first order. A later
incremental request expansion after another owner's installation must refuse.

`crib_reclaim` requests no allocator space. Its XBE tuple disables the consumer,
but only the image rebuild below earns a reclaimed-byte receipt. Defer the
image rewrite until **after** all XBE growth and archive rewrites, including
music-library and hires-pack processing. Then use fresh offsets:

```python
crib = _core_module("nfl2k5_crib_reclaim")
preview = crib.plan(target)
with tempfile.TemporaryDirectory(prefix=".crib-cut-", dir=target.parent) as folder:
    destination = Path(folder).resolve() / "image.iso"
    rec = crib.rebuild(target, destination, expected_plan=preview, progress=progress)
    os.replace(destination, target)
receipt["steps"].append({"step": "crib_reclaim", **rec})
inspection = inspect(target, screen_timing=plan.screen_timing)
```

Both readers and writers close before replacement. Reopen metadata after the
rewrite; no saved physical offset is valid across it. Source and output must be
separate. Retain the existing public Build transaction and failure cleanup.
Before creating the first working image, account for the working image **and**
the Crib transaction's second copy plus its scratch allowance. Keep the main
drive above the user's 100 GB floor. The backend conservatively requires
100 GiB plus scratch free for any source above 1 GiB. This session did not create
a full-size disposable image because the drive had only about 102 GiB free.

## Dispatcher, allocation adapter and four status dictionaries

In `mod_editor/core/nfl2k5_throw_tuning.py`, import:

```python
from . import nfl2k5_my_career as my_career_patch
from . import nfl2k5_crib_reclaim as crib_reclaim_patch
```

Thread `my_career=False`, `my_career_setup=None`, `crib_reclaim=False` through
`_apply_all`, `write_xbe_copy`, `write_image_copy`, their validation/no-op checks,
all forwarding calls, and the scorebug deferred/final paths. Normalize and
validate setup once, retaining the immutable bytes during the build.

Append `my_career=False` to `_selected_space_requests` and `_xbe_space_adapter`,
and pass it at every call site. Add
`+ (my_career_patch.REQUESTS if my_career else ())` to the returned union and
`or my_career` to allocator-selection predicates. Crib may be accepted as a
forwarded flag but must contribute `()` and must not force allocation.

The settings adapter is concrete and needs no assembler at runtime:

```python
class _my_career_adapter:
    def __init__(self, setup):
        self.setup = my_career_patch.read_setup(setup)

    def status(self, payload):
        return my_career_patch.status(payload)

    def apply(self, payload):
        return my_career_patch.apply(payload, setup=self.setup)
```

Append these `_apply_all` owner tuples **after** the shared allocator tuple:

```python
(my_career, _my_career_adapter(my_career_setup),
 "my_career_patch", "MyCareer (experimental)"),
(crib_reclaim, crib_reclaim_patch,
 "crib_reclaim_patch", "Crib movie cut (experimental)"),
```

Add the following to `_grown_status_fields(payload)`, then retain its expansion
in all **four** result/status dictionaries: `read_xbe`, `read_image`,
`write_xbe_copy`, `write_image_copy`. Also add the keys to `mod_build.inspect`'s
forwarded status list and the final Build receipt.

```python
"my_career": my_career_patch.status(payload),
"crib_reclaim": crib_reclaim_patch.status(payload),
```

For a valid applied MyCareer image, `installed_setup(payload) is not None` is the
configuration check. Do not call it on retail/foreign images. Do not expose the
full identity/checkpoint bytes in generic status displays. `crib_reclaim` here
is the XBE consumer status; label it accordingly. Only the explicit image plan
and rebuild receipt establish `archive_bytes_reclaimed`, `disc_bytes_reclaimed`
and verification of every retained resource. An XBE-only patch reports **zero**
disc bytes reclaimed. Never silently count the movie payload size as image
savings or run a 6 GB full-image hash on every ordinary status refresh.

## Gameplay Patches, Build options and MyCareer page

Add these PATCHES rows to `mod_editor/gui/gameplay_patches_panel_qt.py` and put
both keys in `NEEDS_IMAGE`. Their help includes both required words:

```python
("my_career", "MyCareer (experimental)",
 "EXPERIMENTAL / UNWITNESSED. Retail: Franchise controls a team. Patch: "
 "MyCareer follows MyPlayer, a created QB, through the normal draft. "
 "The CPU manages the club and teammates. Create the paired draft save "
 "and setup on the MyCareer page, then include the setup in Build."),
("crib_reclaim", "Crib movie cut (experimental)",
 "EXPERIMENTAL / UNWITNESSED. Retail: The Crib includes 23 movies. Patch: "
 "Remove those movies from a smaller image. The Trophy Room, awards, "
 "profiles, shared room, games and furniture stay."),
```

MyCareer needs its setup picker in the Gameplay Patches action path too. Forward
the chosen frozen setup to the dispatcher and refuse a missing setup before a
copy. Crib's action must call its transactional image `rebuild` with an explicit
output, not finish after the XBE-only dispatch. Keep the two options independent.

In `mod_editor/gui/build_panel_qt.py`, add `_option` entries using exact captions
`MyCareer (experimental)` (23 characters) and `Crib movie cut (experimental)`
(29 characters), each below 60. Add a `MyCareer.json` file picker and explanatory
text linking it to the paired save. Wire both checkboxes, setup path, all plan
read/write paths, availability and preset/reset synchronization. Selecting or
opening a setup must not implicitly enable either checkbox.

In `mod_editor/gui/studio_qt.py`, import and instantiate
`MyCareerPanel` from `mod_editor.gui.my_career_panel_qt`, register its own tab
with exact title **MyCareer**, and call `set_source(current_image)` on source
changes. Connect `setup_ready(str)` to the Build panel's setup-path setter.
The page itself already implements preparation, background work, errors,
explicit movie-plan review and the separate smaller-image transaction. It
does not start work on tab creation or source selection. Preserve the exact
names **MyCareer** and **MyPlayer** everywhere; use no em dashes in UI text.

## Allowlist, runtime closure, capability and manifest handoff

Required runtime allowlist lines in `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_my_career.py
mod_editor/core/nfl2k5_my_career_code.py
mod_editor/core/nfl2k5_crib_reclaim.py
mod_editor/gui/my_career_panel_qt.py
docs/mod_editor/nfl2k5_my_career_capabilities.json
ASTRA_MY_CAREER_REPORT.md
```

Retain already-shipped transitive dependencies: `nfl2k5_roster_records`,
`nfl2k5_franchise_save`, `nfl2k5_practice_reserves`, `nfl2k5_xbe_space`,
`nfl2k5_music_archive`, `nfl2k5_music_banks`, `nfl2k5_rdata_sites`,
`nfl2k5_cave_oracle`, `nfl2k5_bump_strength`, `nfl2k5_depth_chart_storage`,
`platform_compat`, `tools.nfl2k5_commentary_swap` and `tools.nfl_outer`, plus their
existing closures. Source-distribution additions are
`tools/nfl2k5_my_career.S` and `tools/nfl2k5_my_career_assemble.py`; the runtime
needs only generated Python bytes, not GNU as, Capstone or Unicorn.

Add runtime-closure imports in `packaging/check_2k5_mod_studio_runtime.py`:

```text
mod_editor.core.nfl2k5_my_career
mod_editor.core.nfl2k5_my_career_code
mod_editor.core.nfl2k5_crib_reclaim
mod_editor.gui.my_career_panel_qt
```

Merge the two schema-valid objects in
`docs/mod_editor/nfl2k5_my_career_capabilities.json` into the registry. IDs:
`nfl2k5.mode.my_career` on existing `mode_state_routing`, and
`nfl2k5.crib.movie_reclaim` on existing `crib_assets`. Classification is
`offline-writer-proved`; runtime is `not-tested`; GUI defaults are false. Both
backend and validation commands use `python3 -m <dotted.module> ...`, so the
registry file-check mode resolves them. No new surface enum is needed.

Both owners are already in `tests/nfl2k5_allocator_stack.py`, both XBE gates and
the manifest builder's complete request and owner lists. MyCareer's real
8192/4096/16-byte-aligned requests exactly equal its existing committed budget
rows; no budget expansion or extra RO page is requested. Crib has no allocation.

Claude alone regenerates `data/nfl2k5_cave_reservations.json` after protected
integration, using the usual real-disc manifest workflow when disk space allows.
The old manifest's named child offsets change when this owner enters the union.
The cave gate now uses a **test-only** named-child projection for its two
allocation proofs: old owner/kind bounds and identical size/alignment are
required, retail reservations remain byte-for-byte intact, unknown owners
refuse, and the product manifest is never rewritten. The separate MyCareer
manifest tests observe its actual byte writes and zero-initialized RW capacity.
These proofs do not replace Claude's release manifest regeneration or a played
acceptance run. No updater, release-tag, workflow or push changes are requested.

# r62-screen-hooks: second screen timing experiment, 2026-09-06

This section adds only `screen_hooks`. EXPERIMENTAL / UNWITNESSED. The runtime,
assembler, standalone proofs, complete allocator union and manifest builder
are implemented; the protected shared product files below were left unchanged.
All Basic, Advanced and Experimental presets explicitly keep this flag OFF.
The earlier `screen_timing` A-D experiment and its existing preset values stay
independent. Noah has not yet witnessed the data tier. This box is for an
explicit second experiment, never a default fix or a requirement for A-D.

## BuildPlan, validation, resource order and final allocation

In `mod_editor/core/mod_build.py`, add `screen_hooks: bool = False` to
`BuildPlan`. Put `"screen_hooks": False` explicitly in `softdrink_basic`,
`softdrink_advanced` and `softdrink_experimental`; loading any preset clears
a previously selected value. Include it in `wants_xbe_patch()`, the actual-bool
normalization list, availability, `inspect` status forwarding, recipe/plan
serialization, feature summaries and the Build widget's plan collection.
Do not derive it from `screen_timing`, or enable a timing level when checked.

Add `screen_hooks` to every grow-owner deferral/final-pass condition alongside
`calendar_engine` / `qb_spy`, including early-write suppression. Pass
`screen_hooks=False` in the early normal-XBE pass. The existing
`screen_timing.apply_to_image` A-D pass runs first. Install the hooks only in
the existing final `_apply_all` owner pass after that PLAY pass and all other
resource edits, with `screen_hooks=plan.screen_hooks`.

The final union must include the hooks before its first allocation. Forward
`screen_hooks=plan.screen_hooks` into the scorebug runtime call's
`tt._selected_space_requests(...)`, both normal final-owner paths, and all
equivalent dispatcher/writer forwarding. Otherwise a combined scorebug build
can freeze an allocation union that lacks this owner. Standalone hook builds
implicitly select scale-out through their new-owner REQUESTS. Never allocate
them separately after another incomplete union has been installed.

`_allocator_feature_status` should expose module availability and the actual
`screen_hooks` state. `mod_build.inspect` should pass through both the state
and `screen_hooks_settings` from executable inspection for either a standalone
XBE or an image. Product builds require an image through NEEDS_IMAGE; the
development XBE-only API/CLI remains useful and intentional. No PLAY identity
table, authored-intent receipt or additional settings adapter is needed: the
runtime follows the loaded grammar directly and has fixed policies.

## Dispatcher and all four status dictionaries

In `mod_editor/core/nfl2k5_throw_tuning.py` import:

```python
from . import nfl2k5_screen_hooks as screen_hooks_patch
```

Add `screen_hooks: bool = False` to `_apply_all`, `write_xbe_copy` and
`write_image_copy`, forwarding it through every call and validating
`type(screen_hooks) is bool`. Include it in both writers' nothing-requested
conditions. Extend `_selected_space_requests`, `_xbe_space_adapter`, inherited
`_defensive_try_adapter`, their callers and allocator enablement predicates:

```python
+ (screen_hooks_patch.REQUESTS if screen_hooks else ())
```

The final `_apply_all` owners tuple gets this entry AFTER its allocator entry:

```python
(screen_hooks, screen_hooks_patch, "screen_hooks_patch",
 "screen pass timing hooks (second experiment)"),
```

This tuple is reached after `screen_timing` in image Build as specified above;
the resource-only timing module does not belong in `_apply_all`'s XBE tuple.
No settings adapter is required because `apply(payload)` has no settings args.
Status/apply refuse both-hook mixtures, altered code, padding, dependencies,
seals, geometry and digests before installing anything. Preserve the complete
owner receipt, source/result hashes, the two exact edit spans, instruction
size, zero data bytes, experiment order and unwitnessed markers.

Add these entries to `_grown_status_fields(payload)`:

```python
"screen_hooks": screen_hooks_patch.status(payload),
"screen_hooks_settings": screen_hooks_patch.read_settings(payload),
```

Verify they appear in all FOUR dictionaries, with each dictionary's actual
bytes: `read_xbe(payload)`, `read_image(payload)`, `write_xbe_copy(result)`,
`write_image_copy(after)`. `read_settings` returns None when foreign or absent;
installed values are model version 1, line floor 0.8, default QB timer 0.6,
explicit delays preserved, experiment order 2 and runtime_witnessed False.
Forward these through Build output inspection and status refresh; a checked
box alone is not proof that an owner is installed.

## Gameplay Patches and Build tab

In `mod_editor/gui/gameplay_patches_panel_qt.py`, add a PATCHES row with key
`screen_hooks`, title `Screen pass timing hooks (second experiment)`, and
description `screen_hooks_patch.HELP_TEXT`, exactly:

> EXPERIMENTAL / UNWITNESSED. Retail: screen plays use their original line and
> QB timers. Patch: matched screens keep expired line holds until 0.8 seconds
> after the snap and use a 0.6-second default QB timer. Explicit QB delays stay
> unchanged. This is the second experiment after the timing levels A-D. It
> does not guarantee a throw or catch. All presets are off.

This contains Retail and Patch. Add `screen_hooks` to NEEDS_IMAGE and the normal
foreign-state gating, plan collection, status read-back and reset forwarding.
Place it after the A-D timing control. Preserve independent checkboxes.

In `mod_editor/gui/build_panel_qt.py`, add the Boolean `_option` with caption
`Screen pass timing hooks (second experiment)` (44 characters, <=60), key
`screen_hooks`, default False, and HELP_TEXT as its description. Include the
field in preset application, plan construction, reset and installed-status
refresh. Any existing forwarding lists in `studio_qt.py`, `gameplay_panel_qt.py`
or providers need the same key. No new feature-specific GUI panel is required.
Keep addresses and allocation details out of the product control text.

## Allowlist, runtime closure, capability and manifest

Add these lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_screen_hooks.py
mod_editor/core/nfl2k5_screen_hooks_code.py
ASTRA_SCREEN_HOOKS_REPORT.md
```

Add these imports to `packaging/check_2k5_mod_studio_runtime.py` and any gameplay
provider closure import list:

```text
mod_editor.core.nfl2k5_screen_hooks
mod_editor.core.nfl2k5_screen_hooks_code
```

Retain the existing allocator, cave reader and section-digest helper closure.
GNU as, Capstone, Unicorn, tests, `.S`, the development assembler and private
evidence are not runtime dependencies or shipped game assets. The byte template
is checked in and reproducible. The release report links the witness protocol.

Merge the complete object in
`docs/mod_editor/nfl2k5_screen_hooks_capability.json` into
`mod_editor/capabilities/registry.v1.json` as
`nfl2k5.gameplay.screen_hooks` on `gameplay_tuning_sliders`. It is schema-valid
with both commands in `python3 -m dotted.module ...` form. Keep classification
`offline-writer-proved`, runtime `not-tested`, default_enabled False and the
second-experiment wording. The handoff JSON itself is an integration input;
no additional surface enum or schema change is required.

The complete stack in `tests/nfl2k5_allocator_stack.py`, both XBE gates and all
manifest request/observer/apply/probe/status/owner lists already include the
new owner. Its real request is exactly the fixture's existing 640 RX / 0 RW /
0 RO row, so no budget growth or owner rename is required. Claude must
regenerate protected `data/nfl2k5_cave_reservations.json` from final integrated
sources. The private bounded projection is explicitly not a new disc-build
manifest. Add `screen_hooks=False` to the manifest builder's dormant-base
BuildPlan replacement after the protected field exists, so preset changes
cannot preallocate an incomplete owner union.

Integration acceptance: all presets reset off; A-D alone unchanged; hooks
alone; D plus hooks with explicit 0.6 preserved; scorebug plus hooks sharing
one union; absent/foreign/applied states in all four dictionaries; exact replay;
both XBE gates, the three new standalone suites, capability file validation,
staged runtime closure, regenerated manifest and Noah's paired-snap protocol.
Do not label the timing values calibrated or gameplay witnessed.

# r62 QB spy from man and rush, 2026-09-06

This section supersedes the earlier zone-only QB-spy handoff. Backend owner
`nfl2k5_qb_spy` now installs zone, man and rush entry paths atomically through
`mod_editor/core/nfl2k5_qb_spy_runtime.py`. Keep the existing **`qb_spy`** flag.
**EXPERIMENTAL / UNWITNESSED.** No protected file was edited in this branch.

## Allocation and source rebuild

The owner's complete requests are now `(code, 2048, 16)`, `(data, 768, 16)` and
`(read_only, 512, 16)`. This is 512 additional RX bytes and no additional RW/RO.
The request union, fixture, both gate compositions and manifest builder use
the same existing owner. Do not add a second owner or duplicate its rows.
The native callback identities remain retail: seven callback entry detours
delegate to the same spy dispatcher/table, and three dispatch wrappers execute
their native initializer once then clear stale records. See the report for why
replacing callback pointers would break native man exchange comparisons.

An installed 1536-byte revision-1 allocation is immutable and now reports
`foreign`; apply refuses with an explicit rebuild-from-base message. Rebuild
from the original supported source with all selected requests, recompile the
paired intent table and reapply owners. Never upgrade an installed request set
or copy its old hooks into the new allocation. The loaded PLAY v1 table remains
unchanged: authored spies use legal shallow-zone fallback, while the native Spy
command also works on supported man/rush callbacks after initialization.

## Dispatcher, BuildPlan and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, keep the existing
`qb_spy: bool = False` and `qb_spy_intent_table: bytes | None = None` keyword
arguments on `_apply_all`, `write_xbe_copy` and `write_image_copy`, with the
existing table/flag validation and `_qb_spy_adapter`. Its apply must continue
to call `qb_spy_patch.apply(payload, intent_table=self.table)`.

Update the existing final owners tuple after the allocator entry to:

```python
(qb_spy, _qb_spy_adapter(qb_spy_intent_table),
 "qb_spy_patch", "QB spy for zone, man and rush (experimental)"),
```

Keep `_selected_space_requests`'s `+ (qb_spy_patch.REQUESTS if qb_spy else ())`
and the existing `qb_spy` argument/condition in `_xbe_space_adapter`. They pick
up the grown request automatically before the first allocation. Keep the
`_grown_status_fields` member `"qb_spy": qb_spy_patch.status(payload)` and its
existing expansion in **all four dictionaries**:

| Dictionary | Status bytes |
| --- | --- |
| `read_xbe` | input `payload` |
| `read_image` | extracted input `payload` |
| `write_xbe_copy` | completed `patched` |
| `write_image_copy` | completed `final` |

In protected `mod_editor/core/mod_build.py`, retain `BuildPlan.qb_spy: bool =
False`; update its comment to zone/man/rush. Basic (`softdrink_basic`), Advanced
(`softdrink_modern`) and Experimental (`softdrink_experimental`) all explicitly
keep `qb_spy=False`. Retain wants-XBE detection, `xbe_space` normalization,
runtime-closure selection, early `qb_spy=False` deferral, the full selected
request union, and final `qb_spy=plan.qb_spy, qb_spy_intent_table=spy_table`.
Continue compiling `spy_pairs` before the final pass and preserving table
receipts. The existing empty table supports command-only builds. No new
BuildPlan field or preset enablement is needed.

## Gameplay Patches and Build captions

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, replace the existing
PATCHES row with:

```python
("qb_spy", "QB spy for zone, man and rush (experimental)",
 tt.qb_spy_patch.HELP_TEXT),
```

Keep `"qb_spy"` in `NEEDS_IMAGE`. HELP_TEXT now contains both required words
**Retail** and **Patch**, explains four-yard tracking and release, retains the
experimental/unwitnessed label and states that authored plays keep their zone
fallback. Do not retain the earlier claim that man/rush needs a future patch.

In protected `mod_editor/gui/build_panel_qt.py`, use this existing control:

```python
self.qb_spy_check = self._option(
    g, "qb_spy", "QB spy for zone, man and rush (experimental)",
    tt.qb_spy_patch.HELP_TEXT, badge="EXPERIMENTAL / UNWITNESSED",
    needs_image=True)
```

The caption is 44 characters, under the 60-character limit. Keep checkbox
serialization, source-image gating and BuildPlan forwarding as already wired.

## Packaging, registry and release ownership

These exact protected `packaging/release-allowlist.txt` lines already exist;
retain them, with no new runtime file required:

```text
mod_editor/core/nfl2k5_qb_spy_runtime.py
mod_editor/core/nfl2k5_qb_spy_runtime_code.py
docs/mod_editor/nfl2k5_qb_spy_runtime_capability.json
```

Retain these imports in protected
`packaging/check_2k5_mod_studio_runtime.py` and Build's closure:

```text
mod_editor.core.nfl2k5_qb_spy_runtime
mod_editor.core.nfl2k5_qb_spy_runtime_code
mod_editor.core.nfl2k5_xbe_space
```

Assembly, GNU as, Capstone and Unicorn remain development/test dependencies.
Update the existing `nfl2k5.gameplay.qb_spy` capability from the revised
`docs/mod_editor/nfl2k5_qb_spy_runtime_capability.json`; the existing
`gameplay_tuning_sliders` surface and default-off classification remain. Both
commands now use resolvable `python3 -m` modules. The bounded standalone copy
recipe refuses existing output paths and validates everything before opening
an output. It does not update an old installed allocation in place.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` after
merging final sources. The current manifest builder enumerates this owner in
all its existing lists and observes the additional live hooks/reservations.
Run both XBE gates, capability file validation and staged runtime closure after
the text/registry/manifest handoff. Gameplay acceptance remains Noah's witness
list in `ASTRA_QB_SPY_MAN_RUSH_REPORT.md`.

# r62 music all modes, tier 4b (2026-09-06)

This section supersedes the tier-4a music routing, selection and persistence
instructions. Protected sources remain untouched. Apply the reviewable
`docs/mod_editor/music_all_modes_wiring.patch` to `mod_build.py`,
`build_panel_qt.py` and `studio_qt.py`. `git apply --check` passes against this
branch. `test_music_all_modes_wiring.py` applies it in memory and exercises the
publication wrapper and real offscreen Build/Music widgets with the proposed
Studio methods. It also accepts already-applied handoff sources.

## Final image validation and Build document

Keep the existing `BuildPlan` fields:

```python
music_shuffle: bool = False
music_shuffle_selection: dict | None = None
```

Basic, advanced and experimental presets all leave `music_shuffle=False` and
selection `None`. Preset application resets the checkbox; retained personal
choices may remain available for a later explicit opt-in. Normalize a supplied
document using `music_playlist_patch.from_options`, accepting schemas 1 and 2.
The field holds a detached JSON dictionary, never a `Selection` dataclass.
The old Build setter accidentally stored a `Selection` and fed it back to a
document validator; the patch corrects that conversion boundary.

Keep the early ordinary-XBE pass deferred with `music_shuffle=False` and
`music_shuffle_selection=None`. In the final allocator/owner pass:

```python
library = _core_module("nfl2k5_music_banks")
preview = library.plan(target, plan.music_library) if plan.music_library else None
playlist_selection, playlist_preflight = library.playlist_preflight(
    target, plan.music_shuffle_selection, library_plan=preview)
```

This reads actual source AUSB counts. Planned counts come from the validated
plan's `boundaries`, including both jukebox twins; `layout.banks` does not exist
in the real plan. Keep `revalidated_after_rebuild=False` here. Only the final
check may set it true.

In outer `build`, after `_build` completes every edit including Hi-res remapping
and immediately before the final `os.replace`, reopen the private output with
`library.revalidate_playlist`. Run this when shuffle OR a library rebuild is
selected, so a pre-existing playlist is checked even when the checkbox is off.
When shuffle is selected pass the chosen document, or `default_options()` for
the default 66 records, as `expected`. The reader validates actual installed
RX/RO/hooks, selected indices, every descriptor extent and jukebox twin geometry.
Store its receipt as `music_shuffle_validation`, and merge it into each
`music_shuffle_preflight` step. Every reader must close before publication.
Any mismatch raises inside the private transaction and preserves the old target.

The unprotected `nfl2k5_music_banks.verify` already invokes the installed-playlist
check before the library writer publishes its private result. The outer Build
check is still required after all subsequent changes and for shuffle-only builds.
No installed playlist reports `installed=False`, zero records and a false
revalidation flag; it must never be represented as validated installation.

## Project state maps, lazy pages and library previews

This base had no project archive field or session API for Build preferences.
The unprotected archive/session/facade now persist a validated music map:

```json
{"music_shuffle": true, "music_shuffle_selection": {"schema": 2}}
```

The inner object above is abbreviated; persist the complete document returned
by `MusicPanel.playlist_options()`, including catalogue, checked rows, filters,
records and enabled indices. `playlist.build_settings` validates the complete
map. Unknown fields are refused; when more Build settings are introduced,
extend this validator deliberately. Existing archives without this optional
field load as `{}`. Named saves, recovery saves and load rollback include it.
Build-only projects are valid; asset Revert All and its Undo retain preferences.

The protected patch adds `BuildPanel.music_build_settings()` and
`restore_music_build_settings(state)`. Validation precedes widget mutation;
snapshots are detached and JSON-compatible. It connects both enable switches
through Studio and caches choices before the lazy Build page exists. Capture
the map on the GUI thread before named/fast Save and whenever choices change,
through `facade.set_project_build_settings`. Restore from
`facade.project_build_settings` after project open and after either lazy page
is created. Guard restore/source-inspection signals so transient defaults do
not overwrite saved preferences or mark the workspace dirty. Old projects
reset the enable flag and choices instead of inheriting the previous project.

Build's accepted music-library preview emits actual source counts plus its
validated plan. Studio calls `catalog_for_counts(counts, library_plan=preview)`
and `MusicPanel.set_playlist_catalog`; cache the catalogue if Music is still
lazy. Source inspection independently calls `read_playlist_catalog` in the
worker, reading rebuilt jukebox titles and actual counts. Catalogue-read errors
show a status message without discarding the other source capability results.
This allows a grown-library Playlist even when fixed-slot audio editing has no
service. Existing operation locks still disable controls. The Music page also
has its own bounded library-image browser and retains its choices JSON files.

## Dispatcher and all four status dictionaries

These entries are already wired; retain them and forward the new receipt scope.
Import remains `nfl2k5_music_playlist as music_playlist_patch` in protected
`nfl2k5_throw_tuning.py`. `_apply_all`, `write_xbe_copy` and `write_image_copy`
retain `music_shuffle: bool = False, music_shuffle_selection=None`. Validate
the Boolean and a `Selection` instance at the dispatcher boundary. Build alone
converts the saved dictionary with `playlist_preflight`.

`_selected_space_requests` includes `music_playlist_patch.REQUESTS` when enabled;
`_xbe_space_adapter` forwards the flag. Keep it in allocator activation,
scorebug deferral, the full final request union and both nothing-selected checks.
Keep this final owner tuple after allocation:

```python
(music_shuffle, music_shuffle_selection or music_playlist_patch.Selection(),
 "music_shuffle_patch", "experimental music playlist"),
```

`Selection` is the settings adapter; no extra adapter class is needed.
`_grown_status_fields(payload)` retains:

```python
"music_shuffle": music_playlist_patch.status(payload),
"music_shuffle_state": music_playlist_patch.read_settings(payload),
```

Ensure all four dictionaries receive it: `read_xbe(payload)`,
`read_image(payload)`, `write_xbe_copy(result)`, `write_image_copy(after)`.
Forward through Build inspection and receipts. Preserve `runtime_witnessed=False`
and `context_proof_scope`; `all_modes_proved` refers ONLY to the 24 bounded
contracts in the matrix. It does not certify audio or a played game.

## Captions, release closure and owner composition

Retain Build `_option` caption `Shuffle songs in menus, Crib and games`
(37 characters, below 60), experimental badge, default off, `needs_image=True`.
Use `music_playlist_patch.HELP_TEXT` for its help. Change the protected Gameplay
Patches `music_shuffle` PATCHES description to:

> EXPERIMENTAL / UNWITNESSED. Retail: screens choose their own music. Patch:
> up to 100 selected songs share a shuffle across menus, Crib, draft and game
> background. Pause and replay keep it playing. Loading, halftime and wrap-up
> keep their timed music. Stadium clip previews pause and resume the song.
> Actual playback still needs testing in game. All presets are off.

Keep `music_shuffle` in `NEEDS_IMAGE`. Do not label it witnessed or silently
enable it in another gameplay panel. No new GUI surface or capability ID is
needed. This change updates only `nfl2k5.music.playlist` in the registry and
`docs/mod_editor/nfl2k5_music_playlist_capability.json`, including working
`python3 -m` commands. The module CLI is a bounded executable-only development
writer; product image builds must use descriptor validation before publication.

Ensure these existing protected release-allowlist lines remain:

```text
mod_editor/core/nfl2k5_music_playlist.py
mod_editor/core/nfl2k5_music_playlist_code.py
mod_editor/core/nfl2k5_music_banks.py
mod_editor/core/nfl2k5_practice_squad_screen.py
mod_editor/gui/music_panel_qt.py
mod_editor/studio/project_archive.py
mod_editor/studio/session.py
mod_editor/studio/facade.py
reports/music_playlist_contexts.v1.json
docs/mod_editor/nfl2k5_music_playlist_capability.json
```

Runtime closure imports must include `mod_editor.core.nfl2k5_music_playlist`,
`mod_editor.core.nfl2k5_music_playlist_code`, `mod_editor.core.nfl2k5_music_banks`,
`mod_editor.core.nfl2k5_music_archive`, `mod_editor.core.nfl2k5_music_catalog`,
`mod_editor.core.nfl2k5_music_metadata`, `mod_editor.core.nfl2k5_xbe_space`,
`mod_editor.core.nfl2k5_practice_squad_screen`, `mod_editor.gui.music_panel_qt`,
and the three Studio modules above. Archive persistence now validates playlist
documents even before the Music page is opened. Existing archive/encoder/section
digest dependencies remain in closure; GNU assembler, Unicorn, Capstone, tests,
research memos, this handoff patch and retail bytes are not runtime imports.

The owner is already in `tests/nfl2k5_allocator_stack.py`, all manifest request
and owner lists, and the committed budget fixture. Requests remain exactly
2,048 RX / 512 RW / 1,024 RO bytes; code uses 1,689 bytes. Both full XBE gates
pass in both orders. The unprotected Practice Squad guard now accepts the exact
validated playlist dispatcher hook and hashes the remaining native routine.
Do not relax that guard to accept arbitrary jumps.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after applying the final integration.
The new live hooks are `screen_event` at `0x6E4E0` and the draft call at
`0x325E22`; no new owner or budget is required. Tier-4a installed code is refused
as foreign by tier 4b; rebuild from the supported base, including when changing
the installed selection.

After wiring, run the playlist/context/library/project/UI/handoff tests, both
full XBE gates, capability validation and staged runtime closure. Follow the
Noah witness list in `ASTRA_MUSIC_ALL_MODES_REPORT.md`; no gameplay, audible
playback, full retail-disc acceptance build or final release manifest was
produced by this task.
# r62 Modern 2K mode names (2026-09-06)

This section is the modern-naming handoff. EXPERIMENTAL / UNWITNESSED.
The brief reserves the shared files below for Claude; none was edited here.
The actual backend, JSON, Text page, codec fix and standalone tests are delivered.
Read `ASTRA_MODERN_NAMING_REPORT.md` and `docs/mod_editor/modern_2k_mode_names.md`.

## Dispatcher and all four status dictionaries

In `mod_editor/core/nfl2k5_throw_tuning.py` import
`nfl2k5_modern_naming as modern_naming_patch` through the existing package/exact-path
import mechanism. Add `modern_naming: bool = False` to `_apply_all`, `patch_file`
and `patch_image` and every forwarding call. Validate its exact Boolean type.
Include it in both "no patch selected" guards. In the ordinary fixed-site patch
loop add the exact tuple, using the same tuple shape as adjacent owners:

```python
(modern_naming, modern_naming_patch, "modern_naming_patch", "modern 2K mode names")
```

The ordinary loop's `status`/`apply` API accepts the XBE directly. The receipt
is a complete XBE-half naming receipt. This is immutable text in `.string_`,
not runtime code; **do not request allocator pages or add an allocator adapter**.
`REQUESTS = ()`. `_selected_space_requests` and `_xbe_space_adapter` need no new
flags, and no budget row or cave reservation is appropriate.

Add `"modern_naming": modern_naming_patch.status(payload)` to
`_grown_status_fields(payload)`. Despite its historical name, that shared helper
already includes fixed edits and expands into **all four** required status dicts:
standalone status (`payload`, near 639), image status (`payload`, near 764),
`patch_file` final status (`result`, near 1489), and `patch_image` final status
(`after`, near 1765). Verify the key in each; this is XBE-only status, not a claim
that the STRG half is installed. No status value may be hard-coded to "applied".

If the integration supports a non-default manifest path, add a snapshot-backed
adapter forwarding the same immutable JSON to status/apply and the final DATA
pass. Never allow the JSON to change between the two halves. The default pass
rereads the file deliberately; Build must snapshot it or compare its canonical
SHA-256 at preflight and before/after the final pass and refuse on any mismatch.
A changed JSON during Build invalidates the disposable output; never publish it.

## BuildPlan, presets, preflight, deferral and final DATA pass

In `mod_editor/core/mod_build.py`:

1. Add `modern_naming: bool = False` to `BuildPlan` beside `team_names_2026`.
   `to_recipe()` already uses `asdict`; ensure recipe/project import retains it.
   Normalize only actual Booleans; reject strings/numbers. Include it in
   `wants_xbe_patch()` and every XBE kwarg forwarding path, including deferred
   allocator/scorebug passes. It is independent of season_2026 and team names.
2. `softdrink_basic` and `softdrink_advanced`: `modern_naming=False`.
   `softdrink_experimental`: select it only through
   `module.preset_enabled("experimental")`, which revalidates every configured
   desired/fallback, including both MyCareer roles. Reevaluate in `apply_preset`,
   not just at import time. Invalid JSON means False with a visible reason;
   explicit user True still refuses preflight instead of silently dropping it.
3. `availability()["modern_naming"]` requires module presence and
   `all_strings_fit()`. Standalone XBE source status says `"requires image"` for
   this whole feature. The image branch uses `module.image_status(source)`;
   it validates both halves and labels a partial install foreign. Include
   `modern_naming_details = module.image_preview(source)` for the full table.
4. Before copying a disc, when True, require an image, a valid manifest snapshot,
   and `image_status(source) in ("retail", "applied")`. Call
   `catalog_overrides(catalog, enabled=True, value_lookup=host.text_value)`
   against raw staged project values to reject manual changes to the owned STRG
   asset. The sole archive asset is `nfl2k5.text.strg.4248.1.3`. Never pass the
   already-overridden facade back into this check. XBE literals are Build-only.
   Existing unnamed sources need no dependency on MyCareer being installed.
5. `_apply_all(..., modern_naming=plan.modern_naming)` owns the XBE half. After
   project text edits and any pack relocation/growth, add the final data step:

```python
if plan.modern_naming:
    module = _core_module("nfl2k5_modern_naming")
    if module is None:
        raise RuntimeError("Modern mode names are unavailable")
    naming_receipt = module.apply_to_image(
        target, include_xbe=False,
        progress=lambda message: progress(message, 0, 0))
    receipt["steps"].append({"step": "modern_naming", **naming_receipt})
    if module.image_status(target) != "applied":
        raise ValueError("Modern naming XBE and text-bank halves disagree")
```

The deliberate intermediate XBE-applied/STRG-retail state is accepted only by
this DATA-only adapter. The normal full-image adapter refuses mixed states.
Do not call its full-image default between the two Build steps. The final full
status and manifest hash check must happen before publish. Pack directory IDs,
chunk offsets, source spans and actual output are checked through bounded readers.

6. Disabling: on the usual original-source build, skip both passes and remove
   preview overrides; no text edits were staged by this feature. This restores
   retail naming from that original source. If a user selects a named source,
   False must not silently retain installed names. Require the retained original
   source or refuse before copying, with "Choose the original source to restore
   retail mode names". An explicit restore workflow can call
   `apply_to_image(target, enabled=False, original_source=original)`; it restores
   owned spans while preserving unrelated edits. Never guess source provenance.

## PATCHES row, NEEDS_IMAGE and Build option

In `mod_editor/gui/gameplay_patches_panel_qt.py`, add the existing three-field
PATCHES row shape with key `modern_naming`, title `Modern 2K mode names`, and
these help words (contains the mandatory **Retail** and **Patch**):

> Retail uses Quick Game, Franchise and Create Player. Patch uses Play Now,
> MyNFL and MyPlayer. Coach's Desk and The Crib keep their names. Experimental /
> Unwitnessed. Preview every change in Text & Team Identity.

Use `nfl2k5_modern_naming.HELP_TEXT` as the shared constant. Add `modern_naming`
to `NEEDS_IMAGE`. This is a data option even though most literal storage is XBE.
Use the adjacent data-row status/callback fields, not a dummy unsupported action.

In `mod_editor/gui/build_panel_qt.py` add:

```python
self.modern_naming_check = self._option(
    f, "modern_naming", "Modern 2K mode names (MyNFL, MyPlayer, Play Now)",
    modern_naming.HELP_TEXT, needs_image=True)
```

Caption length is 45, below 60. Include it in all checkbox/preset/availability
loops, plan construction, image-only admission, change detection and preview
refresh. Follow `team_names_2026_check`'s actual `_option` signature and state
persistence. If span validation fails, show the exception and leave Experimental's
checkbox off. On switching away from Experimental, Basic/Advanced reset it off.

## Text & Team Identity facade and MyCareer ownership

`text_rosters_panel.py` already inserts the new **Modern mode names** subtab in
text/combined views and reloads it with the host catalogue. Rosters-only is
unchanged. `modern_naming_panel_qt.py` renders all 24 before/after rows and their
IDs/limits; each tooltip contains the complete text. Until this facade wiring is
installed, it explicitly presents an unverified mapping with no Build claim.

In `mod_editor/gui/studio_qt.py`, extend `_EmbeddedOperationGuardedHost` alongside the existing
team-name callbacks:

- Add constructor kwarg `modern_naming_enabled: Callable[[], bool] | None = None`,
  stored as `_modern_naming_enabled` with a False fallback. At the Text host
  creation near 2464 pass `modern_naming_enabled=self._modern_naming_preview_enabled`.
  Implement that window callback like `_team_names_preview_enabled`: require
  the checkbox and that `Path(self._build_panel.source_field.text()).resolve()`
  equals `Path(self.facade.source_path).resolve()`; otherwise return False.
- Add `modern_naming_preview()` returning
  `{"enabled": enabled, "rows": naming.image_preview(source, enabled=enabled)}`
  using `self._host.source_path` (the retained source image) and the same manifest
  snapshot as Build.
  Also check raw staged catalog values before returning. If the source is an
  already-named disc and naming is disabled, require the original-source binding
  above instead of claiming a verified restoration preview from an unknown base.
- Merge `naming.catalog_overrides(catalog, enabled=enabled,
  value_lookup=self._host.text_value)` with `_team_name_overrides`; IDs are
  disjoint. `text_value()` returns these transient values. `replace_text()` and
  `revert_text()` on an overridden STRG field should ask the user to turn off the
  Build naming option before manually editing it. No automatic project write.
- Connect `modern_naming_check.toggled` to the same text-panel reload mechanism
  used for team names. Clear/rebuild caches on manifest/source/preset change.
  Compute the override map once per refresh; avoid opening the image per cell.

The other session owns `nfl2k5_my_career` descriptors. No such module exists at
this base. It should use `career_text("menu_row", allocation_bytes=20)` and
`career_text("screen_title", allocation_bytes=20)` when installing its own text.
Default output is `MyCareer`, 18 bytes including NUL, plus two bytes of spare
contract space. These are two **contract rows, not invented retail IDs**.
No existing mode row is replaced with MyCareer by this pass. That owner must
add its own allocator and descriptor proof; this pass allocates nothing.

## Packaging, runtime closure, capability registry and integration tests

Append missing exact lines to `packaging/release-allowlist.txt` (do not duplicate
already-shipped lines):

```text
mod_editor/core/nfl2k5_modern_naming.py
mod_editor/gui/modern_naming_panel_qt.py
data/nfl2k5_modern_naming_2k.json
docs/mod_editor/modern_2k_mode_names.md
docs/mod_editor/nfl2k5_modern_naming_capability.json
```

Retain already-listed `tools/string_table_inventory.py` with this revision's
NFL zero-padding fix and `mod_editor/gui/text_rosters_panel.py` with its new tab.
Also include the new documentation page in the documentation browser/index.

Add literal imports to `packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_modern_naming",
"mod_editor.gui.modern_naming_panel_qt",
```

The backend closure includes the existing rdata/bump/allocator/storage/digest
helpers, `nfl2k5_safe_text_banks`, `nfl2k5_roster_records`,
`nfl2k5_throw_tuning`, `platform_compat`, `nfl_outer`, `nfl_scene_probe`,
`string_table_inventory`, and `nfl2k5_playbook_position_recode`. Carry the default
JSON at its root-relative `data/` path. This module is a package import; do not
load it under an invented top-level module name without its package context.

Insert the exact object from
`docs/mod_editor/nfl2k5_modern_naming_capability.json` into the canonical registry
and sort capability objects by `id`, as its validator requires.
It uses existing `menus`, so no new surface vocabulary is needed. Both commands
are `python3 -m mod_editor.core.nfl2k5_modern_naming ...` for file-check closure.
Status is `offline-writer-proved`, runtime `not-tested`; no witnessed claim.

Both executable gates already compose the name pass before and after the
allocator owner union, including v3, and assert its status. The owner has no
code/data allocation and does not belong in `tests/nfl2k5_allocator_stack.py`'s
REQUESTS or the cave manifest's owner reservation lists. Do not regenerate the
protected cave JSON on this branch. Regenerate source-closure/provider pins if
the runtime validation reports them changed by the codec revision.

After wiring, run the new standalone tests and both gates, plus protected
integration tests for a naming-only Build, all presets, manifest overflow,
manual conflict, JSON changes mid-build, off/on/off source restoration, and the
MyCareer owner calling both label roles. A checked box or static preview is not
proof that the shared Build dispatch was wired.

The shared `tools/nfl2k5_playbook_position_recode.py` loose-pack header read is
also corrected to `read(HEADER_SIZE)` inside a closed context manager. Retain
that already-shipped file and regenerate any exact-source provider closure pin
covering it. The naming regression forbids whole-pack reads on this path.

# r62 read-option controls v2 handoff, 2026-09-06

This section supersedes the earlier read-option runtime handoff's missing
prompt/replacement search, 0.35-second snap deadline, zero-RW budget and
under-center-only authoring statements. EXPERIMENTAL / UNWITNESSED. No protected
file was edited. The implementation and evidence are in
`ASTRA_READ_OPTION_CONTROLS_REPORT.md`.

## Owner and rebuild policy

Keep the existing `read_option_runtime` option and canonical
`nfl2k5_read_option_runtime` owner. Its revised REQUESTS are 2,048 RX + 256 RW +
88 RO, alignment 16 for all three. The unchanged 64-byte paired PLAY table is
followed by an immutable HUD anchor and two policy constants. Request sets are
immutable: rebuild from the pinned retail/base input with the complete revised
union. Do not apply v2 over an existing v1 allocation, append a second owner,
or overwrite an old seal. The backend refuses those inputs before mutation.

`tests/nfl2k5_allocator_stack.py` and the manifest builder already import this
owner and concatenate its live REQUESTS. Their complete union, installation,
replay, recorder and extra-owner lists therefore include the revised owner.
Claude must regenerate protected `data/nfl2k5_cave_reservations.json` after
integration. The scratch manifest is a local gate input only. Add
`read_option_runtime=False` to the manifest's dormant-base BuildPlan replacement
when that protected BuildPlan field is integrated.

## Dispatcher, settings and all four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, retain/add the earlier
handoff's import `nfl2k5_read_option_runtime as read_option_patch`, Boolean
`read_option_runtime=False` and bytes-or-None `read_option_intent_table=None`
kwargs in `_apply_all`, `write_xbe_copy`, `write_image_copy`, every forwarding
call, `_selected_space_requests`, `_xbe_space_adapter` and the inherited
`_defensive_try_adapter`. Validate an actual Boolean, table bytes with
`validate_intent_table`, and require the flag when supplying a table.

Append `(read_option_patch.REQUESTS if read_option_runtime else ())` to the
selected union and include the flag in allocation and nothing-requested
conditions. Keep `_read_option_adapter(table)` from the earlier handoff: its
`status` delegates to the module and its `apply` calls
`read_option_patch.apply(payload, intent_table=self.table)`. The final
`_apply_all` owners tuple, after the allocator, must contain:

```python
(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
```

Add/retain these in `_grown_status_fields(payload)`:

```python
"read_option_runtime": read_option_patch.status(payload),
"read_option_runtime_settings": read_option_patch.read_settings(payload),
```

All four dictionaries must expose them: `read_xbe(payload)`,
`read_image(payload)`, `write_xbe_copy(result)` and `write_image_copy(after)`.
Settings now report `model_version=2`, `mesh_frames=21`, `crash_samples=3`, the
installed table count/hash, cue and EDGE policy. Copy actual settings and
receipts into inspection/build results; do not retain the v1 `mesh_seconds`
field or advertise a fixed animation-derived mesh duration.

QB spy now recognizes only fully validated read-option snap/reset neighbors
before normalizing their exact hook spans for its full-body dependency hashes.
Ship that compatibility change together with this owner. Do not weaken the
neighbor validation or strip its sealed-code/table checks.

## BuildPlan, paired reads and presets

In protected `mod_editor/core/mod_build.py`, retain/add
`read_option_runtime: bool = False`. Basic, Advanced and Experimental all keep
it False. Carry it through normalization, inspection, the allocator feature
status, final receipts and reset/preset collection. Reserve the revised union
before installing any owner. Defer runtime installation until selected PLAY
outputs are final, including later edits and exact compiler receipts, then
compile the table and pass it to the final XBE pass. The early ordinary-XBE
pass gets `read_option_runtime=False`; deferred owner reservations still include
its revised REQUESTS. Reject enabled builds with no paired read recipes or
more than two reads before disc copying. Omitted table on backend replay keeps
the installed table; changed explicit settings require a rebuild.

The standard compiler keeps a valid authored EDGE preference. For a runtime
read with no authored defender, call
`compile_intent_table(pairs, use_authored_edge=False)`: its explicit 255 sentinel
selects from actual snap assignments. The data-tier opponent fixture remains
necessary to validate the native PLAY graph and is not a runtime defender
identity in this mode. No second BuildPlan option is required.

The core authoring helper now also accepts native Shotgun formations with a
back in slot 10, including `Gun: Doubles Right`, for Zone read and RPO. Empty
Shotgun and Shotgun Speed option still refuse. Keep native positions/personnel;
slot 9 uses the existing receiver block when it is a WR/TE. The standalone
controls test compiles callable MIN `SD Gun Zone Read` at 134 and
`SD Gun RPO Slant` at 31, retaining the native formation links and fixed resource
span. These names are witness recipes, not automatically installed plays.

In the off-limits `mod_editor/gui/create_play_wizard_qt.py`, replace the obsolete
"Native under-center I personnel only" note with "Native I formations, or
Shotgun with a back for Zone read and RPO." The `option_design` positions check
continues to require the original native positions/personnel; update its error
to "Option presets keep the native formation. Restore its stock positions and
personnel first." The existing call to `make_option_design` handles the revised
formation eligibility. Explain that the data-only tier retains geometric native
conditions and the separate runtime checkbox enables these controls.

## Gameplay Patches, Build caption, allowance and closure

In protected `gameplay_patches_panel_qt.py`, the PATCHES key remains
`read_option_runtime`, title `Read option mesh controls (experimental)`, with
`read_option_patch.HELP_TEXT` as its description. It contains both required words
"Retail" and "Patch" and describes the human cue, hold/release controls, live
CPU EDGE read and RPO receiver press. Keep the key in NEEDS_IMAGE.

In protected `build_panel_qt.py`, use `_option` caption
`Read option mesh controls (experimental)` (40 characters), default False, with
HELP_TEXT. Forward the same key through protected Studio/Gameplay collection,
preset/reset and status paths. No extra ext-owner flag or new GUI panel is needed.

Protected `packaging/release-allowlist.txt` must contain these exact lines:

```text
mod_editor/core/nfl2k5_read_option_runtime.py
mod_editor/core/nfl2k5_read_option_runtime_code.py
```

Retain the already shipped `nfl2k5_qb_spy_runtime.py` and `nfl2k5_play_library.py`.
The protected runtime probe/provider closures must import:

```text
mod_editor.core.nfl2k5_read_option_runtime
mod_editor.core.nfl2k5_read_option_runtime_code
mod_editor.core.nfl2k5_qb_spy_runtime
mod_editor.core.nfl2k5_play_library
```

QB spy's validated-neighbor check makes the read-option module part of Spy's
closure even when read-option controls are off. Retain the existing allocator,
codec, inspector, writer, section-digest and cave-reader dependencies. GNU as,
Unicorn, Capstone, corpus exports and tests are development-only dependencies.

Merge the updated handoff object
`docs/mod_editor/nfl2k5_read_option_runtime_capability.json` by existing ID
`nfl2k5.gameplay.read_option_runtime` on `gameplay_tuning_sliders`. No new surface
is introduced. Keep classification `offline-writer-proved`, runtime `not-tested`,
all defaults off and the controls report's witness list. Backend and validation
commands use `python3 -m <dotted.module> ...` for registry file-check mode.

After protected wiring, verify paired Shotgun builds, disabled presets,
missing/stale recipe refusals, the revised budget, all four status dictionaries,
release closure and both XBE gates before offering Noah a witness disc.

# r62 hires-more family and memory handoff, 2026-09-06

This section supersedes the three-asset limits in the r62 hires-pack handoff.
It is resource-only, EXPERIMENTAL / UNWITNESSED. Protected files were not
edited. The existing Build pass already calls the extended backend, so its
folder validation and before/after-compile budget refusals take effect now.
The family controls and budget display below still need integration.

## BuildPlan, presets and preflight

In `mod_editor/core/mod_build.py`, retain the existing four fields and add:

```python
hires_families: tuple[str, ...] = (
    "helmets", "field_logos", "stock_fields", "scorebug", "numbers", "jerseys")
```

Basic, advanced (`modern`) and experimental all retain `hires_pack=False`.
All six family choices initially select which *present* files participate
when the user explicitly enables Hi-res; they do not enable Hi-res itself.
Preserve the selected family tuple with the folder, normalize serialized
lists to tuples, reject duplicates/unknown names, and reject an empty tuple
when enabled. No folder work runs while Hi-res is off. Preserve compatibility
with saved plans that lack the new field by using the tuple above.

Add `nfl2k5_hires_layouts`, `nfl2k5_hires_catalog`, `nfl2k5_hires_budget` and
`nfl2k5_hires_evidence` to the `availability()["hires_pack"]` import closure.
Pass `families=plan.hires_families` to both existing `inspect_image` preflight
and final `build_image`. Add a cheap budget stage before texture encoding:

```python
receipt["hires_budget"] = hires.preflight_budget(
    plan.hires_folder, scale=plan.hires_scale, target=plan.hires_target,
    families=plan.hires_families)
```

The model covers two shared team texture sets, two primary field scenes,
two selected external logos, selected scorebug textures, and the 22 native
player-name output surfaces. It prices the actual wrappers and 128-byte
allocator headers/alignment. After encoding, `build_image` repeats the check
with actual checked scratch sizes. An overage raises a ValueError stating
required bytes, the 65,011,712-byte (62 MiB) ceiling and excess bytes, before
any public mutation. Do not catch this as a warning and continue.

An under-ceiling result is **unproved**, never green/safe. Show `message`
and `modeled_delta_bytes`; `headroom_bytes` is deliberately null. The boot
allocation result, startup reservations, context-selected heap, other live
resources and fragmentation are unknown. Do not display
`modeled_residual_to_ceiling_bytes` as headroom. The report explicitly cannot
fulfil the requested whole-game safe-fit proof. No preset or automatic
subset should treat `family_subsets` as certification. It supplies only a
selection inside the necessary arithmetic bound.

Keep the existing final-pass deferral: after all other fixed-span resource
writers, scene edits, reference/runtime scorebug work and music compilation.
Resolve resources in the current private image. Pass the same family tuple
through preflight and the final pass, preserve the source/input/destination
transaction, then retain the final verification and image hash. Do not run
fixed retail-offset inspectors on the remapped image and call them current.

Conflict detection must compare selected `(outer, chunk)` identities with
other texture/stadium imports, not only `scorebug` or filename prefixes.
Both jersey images belong to the same TSET; the entire stock-field SCNE is
pinned around its selected descriptor, so any independent scene modification
conflicts. Check consumer pins as well as resource identities. The existing
reference/runtime scorebug changes the table at `0xA95C60`; selecting either
Hi-res scorebug input therefore refuses that combination, even when an
individual texture resource does not overlap. It needs a separately audited
combined consumer recipe. The other five families pass the complete XBE
owner union in both orders, so do not reject them solely because a scorebug
option is enabled.

In the existing `mod_build.py` Hi-res preflight, replace the check for
`row["key"] == "scorebug"` with
`any(row["family"] == "scorebug" for row in preview["assets"])`, keeping
the `(plan.scorebug or plan.scorebug_runtime)` condition. This catches
`scorebug_espn` before the private build passes alter its consumer table.

## Build tab controls

In protected `mod_editor/gui/build_panel_qt.py`, keep the existing parent
`_option` caption `Hi-res pack (experimental)` (25 characters). Add six
family `_option` controls beneath it, using these captions, all below 60:

| UI key | Caption | Backend family |
| --- | --- | --- |
| `hires_helmets` | `All teams' helmets (experimental)` | `helmets` |
| `hires_field_logos` | `Created-team midfield logos (experimental)` | `field_logos` |
| `hires_stock_fields` | `Stock midfield logos (experimental)` | `stock_fields` |
| `hires_scorebug` | `Scorebug art (experimental)` | `scorebug` |
| `hires_numbers` | `Uniform numbers (experimental)` | `numbers` |
| `hires_jerseys` | `Jerseys, clean and muddy (experimental)` | `jerseys` |

Use plain tooltip text: `Retail: original texture sizes. Patch: selected
artwork uses 2x detail. Experimental and unwitnessed. Memory fit is unproved.`
For jerseys add `Supply both the clean image and its .mud image.` For stock
fields add `Original scene pixels remain allocated beside the new logo.`
Enable family controls only for an available image source with the parent
Hi-res option checked. Their availability inherits the parent; do not probe
six nonexistent executable owners. Derive `BuildPlan.hires_families` from
checked controls; include it in plan persistence, dirty state, summaries,
reset/preset handling and final receipts. The parent remains off in every
preset. Display one summary row per family rather than 2,524 per-asset rows;
the JSON receipt retains every exact resource result.

Run `preflight_budget` in the existing worker pattern when folder, scale,
target or family selection changes. Retain the request identity so an older
worker cannot enable Build after a new folder fails. Disable Build on any
preflight exception and show its exact numerical refusal. Under-ceiling
results retain the experimental/unproved warning; no green fit badge.
Keep `xemu-128` disabled and backend refusal in place. Explanation:
`The game still limits texture addresses to the first 64 MiB.` No confirmation
dialog or override removes a refusal. Names do not get an enabled checkbox.

## Dispatcher, statuses and Gameplay Patches

There is no new XBE patch or allocation. These explicit N/A entries satisfy
the shared wiring contract:

| Protected surface | Required treatment |
| --- | --- |
| `_apply_all` owners tuple | No new tuple entry; this compiler accepts resources/images. |
| `_apply_all` kwarg | No Hi-res family argument belongs in the executable dispatcher. |
| `read_xbe` status dictionary | No executable Hi-res state. |
| `read_image` status dictionary | Keep executable statuses; use Build's archive receipt for Hi-res. |
| `write_xbe_copy` status dictionary | No change; a standalone XBE contains no family art. |
| `write_image_copy` status dictionary | No new XBE status; the final Build archive pass supplies verification. |
| `_grown_status_fields` | No new field. |
| `_selected_space_requests` / `_xbe_space_adapter` | No new flags or requests. |
| `tests/nfl2k5_allocator_stack.py` and cave manifest lists | No new owner; keep their complete existing union. |

Gameplay Patches `PATCHES` / `NEEDS_IMAGE`: no new row or new executable
Patch, since the Build folder is required and that panel cannot represent
it. Retain the existing explanation for Hi-res if it is surfaced there:
`Retail: original texture sizes. Patch: use the Hi-res folder in Build.
Experimental and unwitnessed; memory fit is unproved.` It must remain
image-only (`NEEDS_IMAGE`) wherever the existing parent option appears.
All Textures keeps its native fixed-span contract; do not route these larger
resources through its existing in-place writers. Studio registration needs
no new panel. The cave manifest must not be regenerated by this worktree.

## Release closure and capability

Add these exact allowlist lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_hires_catalog.py
mod_editor/core/nfl2k5_hires_layouts.py
mod_editor/core/nfl2k5_hires_budget.py
mod_editor/core/nfl2k5_hires_evidence.py
```

Retain the existing pack/texture/guide lines. The catalog is generated Python
metadata and is required at runtime; it contains no retail pixel payload.
The three audit/acceptance tools and reports remain developer evidence,
not release runtime dependencies. In protected
`packaging/check_2k5_mod_studio_runtime.py`, import all four new dotted core
modules along with the two existing Hi-res modules, then smoke-test catalog
count, a budget receipt with null headroom, and refusal of `xemu-128`.
The layouts module imports `nfl2k5_hires_texture`, `tools.nfl_txtr`, the
existing P8 palette codec and standard-library `collections`, `functools`
and `struct`; no new wheel, Qt panel or private research inventory is needed.
Refresh existing provider closure fingerprints after integration as needed.

Update the existing capability `nfl2k5.textures.hires_pack`, on the existing
`uniforms` surface; no new surface ID is needed. The complete schema-valid
handoff is `docs/mod_editor/nfl2k5_hires_pack_capability.json`. Its backend
and validation command both use `python3 -m <dotted.module> ...`. Preserve
`runtime.status=not-tested` and default false. Do not turn static compilation
or budget arithmetic into a witnessed/compatible capability classification.

# r62 read-option / screen-hooks composition repair, 2026-09-06

See `ASTRA_READOPTION_SCREENHOOKS_COMPOSE_REPORT.md`. Both Python owners must
ship together: each now validates the other's exact installation before
normalizing its disjoint hook in native `0x19C740`. No assembly, runtime policy,
allocation request, new flag or new product surface is introduced by this fix.
The fixture's read-option rows now match the already landed v2 REQUESTS.

The earlier screen-hooks and read-option-controls-v2 sections remain the
concrete product wiring contract. Retain these `_apply_all` entries after the
complete-union allocator:

```python
(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
(screen_hooks, screen_hooks_patch, "screen_hooks_patch",
 "screen pass timing hooks (second experiment)"),
```

Keep `read_option_runtime=False`, `read_option_intent_table=None` and
`screen_hooks=False` kwargs and their existing request-selection/forwarding
contract. All four status dictionaries (`read_xbe`, `read_image`,
`write_xbe_copy`, `write_image_copy`) need the existing `read_option_runtime`,
`read_option_runtime_settings`, `screen_hooks`, and `screen_hooks_settings`
entries. BuildPlan fields remain the existing two Boolean flags and paired
read-option table/recipe fields; Basic, Advanced and Experimental defaults
remain off for both owners. There is no extra composition switch.

Gameplay Patches retains each module's HELP_TEXT, including the literal words
"Retail" and "Patch", and both keys in NEEDS_IMAGE. Build `_option` captions
remain `Read option mesh controls (experimental)` and
`Screen pass timing hooks (second experiment)`, both under 60 characters.
Keep the two existing capability IDs and surfaces from the earlier handoffs;
there is no new registry surface or runtime-witness claim.

Protected `packaging/release-allowlist.txt` must contain all four paths:

```text
mod_editor/core/nfl2k5_read_option_runtime.py
mod_editor/core/nfl2k5_read_option_runtime_code.py
mod_editor/core/nfl2k5_screen_hooks.py
mod_editor/core/nfl2k5_screen_hooks_code.py
```

Protected runtime-closure probes must import all four corresponding dotted
modules. In particular, a Spy/read-option provider now also needs screen hooks
and its template even when the screen-hooks option is off. The local imports
occur at inspection time, after both modules have initialized; neither owner
recursively calls the other's public status. No new wheel is required.

Integration is still blocked on the separately assigned MyCareer/playlist/
Practice Squad composition repair. Both XBE gates pass this pair and then
fail there. Do not remove an owner, skip a gate or loosen its guards. Merge
that companion repair, regenerate protected
`data/nfl2k5_cave_reservations.json` using the existing manifest builder, then
rerun both full gates in ordinary/explicit-scaleout and forward/reverse modes.
The current manifest already has six stale source fingerprints at the base
commit; this fix adds the screen-hooks source change. Refresh through actual
writer observation, not a manual hash substitution. The bounded screen-hook
projection correctly refuses this stale parent and is not a release manifest.
## r62-roster-arena-growth integration (2026-09-06)

This section supersedes the earlier storage-growth proposal for reserves and extra
created records. EXPERIMENTAL / UNWITNESSED. Keep `reserves_16=False` and
`created_teams_extra=0` in Basic, Advanced and Experimental. No preset enables
either. The implementation and proof boundary are in
`ASTRA_ROSTER_ARENA_GROWTH_REPORT.md`. Do not regenerate the protected manifest
until the dispatcher and complete resource build described here are integrated.

### Dispatcher: nfl2k5_throw_tuning.py

Import `nfl2k5_roster_arena_growth as roster_arena_patch` and
`nfl2k5_roster_arena_image as roster_arena_image`. Thread keyword arguments
`reserves_16: bool = False, created_teams_extra: int = 0` through `_apply_all`,
`write_xbe`, `write_image`, `_selected_space_requests`, `_xbe_space_adapter`, every
forwarding call and the CLI. Reject bool/non-int for `created_teams_extra` and
all values except 0/2. Validate the boolean independently even when both options
are off. Call `roster_arena_patch.options(...)` only if either option is selected.

Append `roster_arena_patch.REQUESTS` exactly once to the selected union if
`reserves_16 or created_teams_extra`. Its only request is
`('nfl2k5_roster_arena_growth', 'code', 8192, 16)`. The allocator selects v3; no
additional RW or page-count change. Include both flags in the allocator entry's
condition and adapter arguments. Also pass them into the union used by
`scorebug_ingame.runtime_apply_in_place(..., extra_requests=...)`. Every selected
owner must be reserved before any grown owner is installed. Adding a missing
owner to an already populated directory intentionally refuses.

Use this settings adapter and append this `_apply_all` owners tuple **after**
the allocator and the existing PS/practice prerequisites (screen and growth
compose in either order):

```python
class _roster_arena_adapter:
    def __init__(self, reserves_16, created_teams_extra):
        self.kwargs = dict(reserves_16=reserves_16,
                           created_teams_extra=created_teams_extra)
    @staticmethod
    def status(payload):
        return roster_arena_patch.status(payload)
    def apply(self, payload):
        return roster_arena_patch.apply(payload, **self.kwargs)

(reserves_16 or created_teams_extra,
 _roster_arena_adapter(reserves_16, created_teams_extra),
 'roster_arena_growth', 'experimental larger roster arena'),
```

Normalize either flag to `xbe_space=True, practice_squad=True,
franchise_practice=True`. Preserve the existing `practice_reserves` dependency;
the growth owner also installs it itself. `reserves_16` additionally normalizes
`practice_squad_screen=True` so users can manage the larger squad in game.
`created_teams_extra=2` alone retains the 12-reserve limit. The new owner calls
base PS/practice apply safely; their status methods recognize only a fully
verified delegation, including allocation seals and hook pins.

Add these fields to `_grown_status_fields(payload)` using
`settings = roster_arena_patch.read_settings(payload)`:

```python
'roster_arena_growth': settings['status'],
'reserves_16': ('foreign' if settings['status'] == 'foreign' else
                'applied' if settings['reserves_16'] else 'retail'),
'created_teams_extra': ('foreign' if settings['status'] == 'foreign' else
                        'applied' if settings['created_teams_extra'] else 'retail'),
'roster_arena_settings': settings,
```

The **four status dictionaries** are `read_xbe` (payload), `read_image` (payload),
`write_xbe` (result), and `write_image` (after). All four must spread this helper;
add it to `write_xbe` if absent. For image read/write results separately include
`roster_arena_resource = roster_arena_image.image_status(path_or_target)`. An
XBE's applied status alone does not prove the paired ROST. Raw XBE writes are a
development component only; the public options require an image. For image
writes run the paired final resource pass below before reporting success.

When `scorebug_runtime` defers owners, defer these two flags too. Carry their
original values through allocation planning and restore them in the final
`_apply_all`. Do not install growth using a partial request union during an
earlier roster/text or scorebug pass.

### BuildPlan and paired publication: mod_build.py

Add fields `reserves_16: bool = False` and `created_teams_extra: int = 0`, explicit
off/zero entries to all three preset dictionaries, and both to recipe/export,
summary, capability dependency lookup, `wants_xbe_patch`, option validation and
normalization. Map both to module `nfl2k5_roster_arena_growth`. Report normalized
PS/practice/screen dependencies in the recipe. Include both flags in every
final allocator condition and `_selected_space_requests` call.

In the early `replace(plan, ...)` used to defer grown owners set
`reserves_16=False, created_teams_extra=0`; preserve the original values for the
final union and final `_apply_all`. Update the `scorebug_runtime` deferral in
`write_image` the same way. After **all** other disc resource edits (rosters,
team/history strings, music, art), and after final composed XBE installation,
run this on the Build-owned disposable working image:

```python
if plan.reserves_16 or plan.created_teams_extra:
    with tempfile.TemporaryDirectory(prefix='.roster-arena-',
                                     dir=target.parent) as folder:
        paired = Path(folder).resolve() / target.name
        rec = roster_arena_image.build_image(
            target, paired, reserves_16=plan.reserves_16,
            created_teams_extra=plan.created_teams_extra, progress=progress)
        os.replace(paired, target)  # writer has closed every descriptor
    receipt['steps'].append({'step': 'roster_arena_growth', **rec})
```

The paired writer uses the existing archive relocation and transactional-copy
primitives, resolves outer 5 by index and pinned name ID, updates the ROST
wrapper and all outer/pack/directory geometry, and verifies every neighboring
outer plus the entire composed XBE before replacement. Its replay is byte
identical. Never send the grown ROST through the old equal-size resource writer.
Reopen the image to validate the pair and use fresh offsets in subsequent reads.
Public failure must discard the entire Build-owned image, including any earlier
XBE-only intermediate. Do not publish an executable/resource mismatch.

Existing saves are separate artifacts. Provide a signed-copy action using
`nfl2k5_roster_arena.migrate_save(source, new_target, reserves_16=...,
created_teams_extra=...)` and reload the result. The action verifies EXTRA,
preserves all other container members, signs and reopens the copy. It refuses
the source as destination and existing output files. Loading an old v0 save in
the patched native runtime enables the arena and preserves its old 52 records;
adding two records to that existing save requires the host migration.

### Gameplay Patches, Build captions and roster panel

In `gameplay_patches_panel_qt.py` add these PATCHES entries and both keys to
`NEEDS_IMAGE`:

* `reserves_16`, caption `16 reserves (experimental)`: `Retail: 65 player slots per team.
  Patch: 16 reserves in a migrated save; an explicitly eligible team may hold
  17. EXPERIMENTAL / UNWITNESSED. Build a paired disc and keep the original save.`
* `created_teams_extra`, caption `Two extra created teams (experimental)`:
  `Retail: two created-team records. Patch: two more records with separate names
  and inherited stock assets. EXPERIMENTAL / UNWITNESSED. The franchise league
  stays at 32 teams.`

This panel is boolean-driven: translate the created-team toggle to integer 2
when checked and 0 when unchecked at the adapter boundary. Never pass True as
the integer. Bare-XBE inputs must disable these public actions. Both option
states must agree with the pair status, not simply one changed executable.

In `build_panel_qt.py` use `_option` captions `16 reserves (experimental)` and
`Two extra created teams (experimental)` (both under 60 characters), the same
help text, `badge='EXPERIMENTAL / UNWITNESSED'`, and `needs_image=True`. Add both
to preset syncing, dirty detection, enablement, status summary and plan assembly;
convert the second checkbox to `2 if checked else 0`. Preserve the off defaults
on preset switching. Add feature labels in the two summary mappings.

`roster_editor_panel_qt.py` is outside this task's GUI scope. Its current
`_refresh_actions` delegates to `document.reserve_move_check`; that backend now
accepts migrated v1 saves and the correct 16/17 limit. Preserve that authoritative
check and its refusal text. Use `document.reserve_limit(team_index)` for the
Reserves count/limit label. Backend reserve transactions now enforce 16/17 only
for migrated NFL teams; never raise the global legacy constant. Provide the
signed-copy migration action above and reload via `nfl2k5_roster_records.load_save`.
Show `EXPERIMENTAL / UNWITNESSED. Requires the matching larger-roster disc.`
For the optional 17th, take an explicit team-eligibility decision and pass its
bit in `eligible_team_mask` during migration. Default mask is zero. There is no
automatic player nationality/eligibility classifier. Do not silently infer one
from a player name or grant all teams an extra slot. Reserve-only moves remain
signed-save operations; Build & Share correctly refuses to encode them.

### Packaging, registry and manifest

Add these literal allowlist lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_roster_arena.py
mod_editor/core/nfl2k5_roster_arena_code.py
mod_editor/core/nfl2k5_roster_arena_growth.py
mod_editor/core/nfl2k5_roster_arena_image.py
docs/mod_editor/nfl2k5_roster_arena_growth_capability.json
```

Development C/assembly and tests need no runtime compiler or extra runtime
package. Existing PS screen/code, franchise/roster/save modules, archive writer,
platform compatibility helpers and allocator are already distributed; keep
them in the runtime closure. Explicitly import these four new modules in
`packaging/check_2k5_mod_studio_runtime.py`'s closure list using dotted
`mod_editor.core.*` names. The new dependency chain also reaches
`nfl2k5_music_archive`, `nfl2k5_music_banks`, `nfl2k5_save_rost`,
`nfl2k5_roster_records`, `nfl2k5_franchise_save`, `nfl2k5_practice_squad`,
`nfl2k5_practice_reserves`, `nfl2k5_xbe_space`, and the archive tools they already
import. Exercise both new modules' `--help` in the installed runtime.

Merge the one schema-valid object from
`docs/mod_editor/nfl2k5_roster_arena_growth_capability.json` into the sorted
registry. ID `nfl2k5.rosters.arena_growth`, classification
`offline-writer-proved`, runtime `not-tested`, GUI default false. Both command
fields use `python3 -m <dotted.module> ...` for file-check resolution. Update the
existing PS-screen capability's 12-only constraint to describe legacy 12 and
migrated 16/explicitly eligible 17; retain its unwitnessed label.

The full request union, gate compose tuple, manifest recorder owner lists and
probe list, and allocator dormant union are already updated here. The late
owner packs after existing owners so their shipped addresses remain exact.
Claude must regenerate `data/nfl2k5_cave_reservations.json` using the integrated
manifest builder and the required disposable-disc/disk policy, then rerun both
gates. This worktree deliberately does not edit that protected JSON, release
checker, dispatcher, Build plan or GUI files.

## r62 MyCareer composition correction (2026-09-06)

No new feature, dispatcher option, allocation, preset or GUI surface is added.
The existing `_apply_all` owner tuple/kwargs and four status dictionaries,
`BuildPlan` fields and Basic/Advanced/Experimental defaults, Gameplay PATCHES
Retail/Patch descriptions and NEEDS_IMAGE, Build `_option` captions, release
allowlist, runtime-closure imports and capability registry entries already
cover these modules. No change to those protected surfaces is requested.

Claude must regenerate `data/nfl2k5_cave_reservations.json` with the existing
`tools/nfl2k5_cave_oracle.py manifest` command against the final integrated
sources and live request union. The shipped manifest still records read-option
v1 (960 RX / 64 RO); the landed v2 already requires 2048 RX / 256 RW / 88 RO.
This correction synchronizes the unprotected budget fixture with those live
requests. Do not repin historical source fingerprints by hand or relax the
size/alignment projection refusal.

For this session's tests, `.scratch/mycareer-compose/observed-xbe-manifest.json`
is generated by the existing standalone `test_nfl2k5_guardian_manifest.py`
recorder using `NFL2K5_GUARDIAN_MANIFEST_OUTPUT`. It observes actual complete
XBE gate writer calls, rejects unattributed changes, verifies final section
seals, records current named allocations and validates current source hashes.
It is bounded executable evidence, with no new disc/resource build or gameplay
claim. Gate/manifest tests can select it with `NFL2K5_CAVE_MANIFEST`; their
production oracle and source-drift checks remain intact. Release manifest
regeneration remains mandatory for integration. No protected file was edited.

The report `ASTRA_MYCAREER_COMPOSE_REPORT.md` gives the full pair matrix,
additional guard conflicts discovered, exact validation commands and Noah's
remaining played witness list. MyCareer and all affected gameplay features
remain EXPERIMENTAL / UNWITNESSED.


## Beta 62 integration 3 disposition (2026-09-06)

The integration authorized by `ASTRA_BRIEF.md` is implemented in the protected
product sources. `ASTRA_INTEGRATION_62_3_REPORT.md` records every feature,
protected diff location, test result, limitation and played-witness requirement.

The dispatcher now carries collision settings, read-option controls, unavailable
franchise/Senior Bowl guards, Guardian overlay, MyCareer, screen hooks, modern
naming, Crib reclaim and roster arena through validation, exact request unions,
settings adapters, the allocator-first tuple, image pairing and all four status
dictionaries. Existing defensive-try, widescreen and QB-spy flags consume the
landed grown owners. Build defers allocations, checks final PLAY compiler pairs,
freezes MyCareer setup, publishes Guardian resources before final XBE, and runs
modern DATA, roster arena, Crib shrink and playlist revalidation after growth.

New opt-ins stay false in every preset; collision level defaults to zero, extra
created teams to zero, Guardian practice preference to true, and hires families
to all six while the parent remains off. Experimental modern naming is conditional
on every manifest span fitting. The later scorebug handoff supersedes the earlier
probe-field proposal: diagnostics stay CLI-only; runtime stays false in presets.
The existing single widescreen flag remains. MyCareer setup selection/preparation
does not tick its checkbox or the independent Crib option. Native Senior Bowl
and franchise-2026 execution remain unavailable and refuse before preparation.

Both patch panels, the Build settings/project map, Rules/Create a Play Info,
Senior Bowl preparation, MyCareer, Stadiums workflow, animation source field,
Guardian roster/CSV/undo controls, signed-save migration and transient modern-name
facade are connected. Practice help now promises the corrected Coach's Desk
return. Hires controls preserve numerical budget failures and reject stale worker
results; 128 MiB remains disabled. The wizard describes native I or eligible
Shotgun formations and distinguishes data recipes from runtime controls.

Registry counts are 108 overall and 70 NFL2K5; all candidate IDs are merged with
resolvable local module commands. The allowlist has 475 exact files. Provider
integrity covers the actual 225-module closure; the runtime imports 180 product
modules and 34 tools. Reviewed release metadata is 24 files, including the exact
music routing report, with no broader reports/payload exception. Shipped old
reports use portable path notation while retaining their evidence.

The required 77-test owner-pairwise suite passes in both orders. The staged file
audit and runtime closure pass. The required real-disc manifest regeneration
also passed alone after repinning, observing 10,051 reservations from 115 writer
calls. Initial disk preflight refused at 104.75 GB; capacity later rose to 111 GB
and the monitored run never fell below 104.64 GB. Its temporary directory and
discs were removed. No manual fingerprint updates were used. See the report's
final ledger for both XBE gates and the oracle result. Historical private registry
evidence is separately reported as missing; no dummy evidence was shipped.
Every new game behavior remains experimental/unwitnessed.

The existing practice-squad cave assertion was updated for the arena owner's
fifteen exact five-byte ABI bridges. It validates the complete sealed owner,
exact manifest spans/labels and installed bridge bytes while retaining every
retail-reference check. No arena, practice-squad, allocator or oracle guard was
relaxed. The post-manifest full gate results are in the report.

## r63 kickoff fixes (A-D), EXPERIMENTAL/UNWITNESSED

Owner changes are in `nfl2k5_dynamic_kickoff.py` and its relocated compiler;
no new XBE owner, setting, allocation, or preset flag. The normal-return PLAY
writer is new and needs the following protected-file wiring. See
`ASTRA_KICKOFF_FIXES_REPORT.md` and `docs/nfl2k5_kickoff_fixes_receipts.json`.

* Dispatcher `_apply_all`: keep the existing `dynamic_kickoff` and
  `dynamic_kickoff_settings` kwargs and tuple
  `(dynamic_kickoff, _dynamic_kickoff_adapter(dynamic_kickoff_settings),
  "dynamic_kickoff_patch", "dynamic-kickoff")`; keep the final
  `(kickoff_relocated, kickoff_relocated_patch, "kickoff_relocated_patch",
  "experimental relocated kickoff")` tuple. They pick up the new compiler.
  The four status dictionaries in `nfl2k5_throw_tuning.py` (current lines
  643/767/1746/2076 for dynamic kickoff and 654/781/1757/2090 for relocation)
  already call these owners. Keep those calls and settings keys. PLAY status
  belongs in disc inspection, not the executable dispatcher.
* `BuildPlan.dynamic_kickoff` remains the enabling field. Basic: false;
  Advanced: false; Experimental: true. Keep normalization implying
  `kick_rules=True`, `kickoff_alignment=True`, `kick_power=False`, and the
  existing relocation deferral/final pass. No new `BuildPlan` field is needed.
* In `mod_build.py`, after the alignment step and only when
  `plan.dynamic_kickoff` is true, load `_tools_module("nfl2k5_kickoff_returns")`,
  fail if missing, call `returns.apply(target, progress=lambda msg:
  progress(msg, 0, 0))`, and append `{"step": "kickoff_returns", **receipt}`
  to the build receipt. Run after any imported PLAY replacements, before
  depth-role recoding, alongside alignment. The tool plans and validates all
  36 resources before writing fixed spans, verifies writes, and is idempotent.
  Add this core and tool dependency to dynamic-kickoff/relocation availability.
  Disc inspection should expose `kickoff_returns` from the tool's `status`;
  use `n/a` for a standalone XBE. Do not infer assignment status from XBE status.
* Gameplay Patches `PATCHES` / help text for existing `dynamic_kickoff`:
  "Retail: moving kickoff lines and deep return blocking. Patch: players hold
  an idle pose facing the kick, release on contact, and block nearby coverage.
  Experimental and unwitnessed. Rebuild from retail."
  Keep `dynamic_kickoff` and `kickoff_relocated` in `NEEDS_IMAGE`.
* Build tab `_option` caption: `Dynamic kickoff: ready stance and close blocks`
  (45 characters, under 60). Explain that the in-field touchback guard and
  return assignments are included. Do not claim the widescreen witness fixed.
* Add these exact allowlist lines:
  `mod_editor/core/nfl2k5_kickoff_returns.py`
  and `tools/nfl2k5_kickoff_returns.py`.
  Both existing kickoff owners and the formation/play writer, codec, library,
  inspector, and alignment dependencies are already packaged; retain them.
* Add runtime-closure imports `mod_editor.core.nfl2k5_kickoff_returns` and
  `tools.nfl2k5_kickoff_returns` to `check_2k5_mod_studio_runtime.py`. Check
  callable resource `status`/`apply` and archive `status`/`apply`. There is no
  new user-selectable capability; retain the existing dynamic-kickoff registry
  entry and update its experimental description. A separate capability key
  or XBE allocator request would misrepresent this coupled fix.
* Regenerate the protected cave manifest with the existing oracle manifest
  command. The existing owner's hook list now includes `B6760..B6766`; both
  caves contain the new compiled stream. Reservations stay 1939 RX / 10 RW.
  The allocator stack fixture and owner union already contain this owner.
* Leave widescreen v3 code and its five HUD wrappers unchanged. The traced
  on-field route geometry uses world vertices; applying HUD x-undo there
  would shift it. Noah's exact landing-marker/camera witness remains required.

All protected files above were left untouched. Existing beta-62/beta-63
patched kickoff caves are deliberately foreign to this revision; rebuild
from the supported retail base. Do not apply this revision over an old disc.

## r63-camera-far: existing camera flag, 64 RX bytes (2026-09-07)

This supersedes the descriptor-only Standard-to-Far description. The existing
`nfl2k5_camera` owner now selects **Far**, resets that choice at boot, Settings
and Franchise load, and common game/practice camera entry, and changes the
seven Far descriptors for scorebar clearance. Standard stays retail. Camera
Options remain a session choice, including with MyCareer. The backend and
standalone XBE BuildPlan test work; combined production builds require this
protected dispatcher handoff before release. Rebuild from a retail source;
old descriptor-only camera installations deliberately report foreign.

There is no new checkbox or option key. `REQUESTS` is exactly
`(("nfl2k5_camera", "code", 64, 16),)`: 39 code bytes plus 25 bytes of
owned padding, zero RW/RO requests. The brief assigns no camera budget row;
this bounded addition uses 64 bytes of the existing RX capacity, without
changing page counts or using the tight RW budget. The budget fixture,
`tests/nfl2k5_allocator_stack.py`, both gates and manifest builder include it.
`tools/nfl2k5_my_career.S` and its regenerated template now use the session
camera when the pinned Far default instruction is installed. No MyCareer
capacity, save layout, opt-in flag or setup field changed.

### Protected dispatcher: mod_editor/core/nfl2k5_throw_tuning.py

1. Add keyword-only `camera=False` to `_selected_space_requests` and
   `_xbe_space_adapter.__init__`. Add
   `+ (camera_patch.REQUESTS if camera else ())` to the request union and pass
   `camera=camera` from the adapter to the request helper. Include camera in
   the adapter's scaleout decision (`self.scaleout = bool(camera or ... )`).
   `_defensive_try_adapter` inherits this request contract: pass camera to it
   too, since it can allocate before the explicit allocator row.
2. Remove `(camera, camera_patch, "camera_patch", "camera")` from the early
   `_apply_all` owner tuple. Add that same tuple immediately **after** the
   allocator entry in the final owner tuple. Add `or camera` to the allocator
   predicate, and pass `camera=camera` into both adapter constructors. Keep the
   existing `_apply_all(..., camera=False, ...)` public argument.
3. Keep `"camera": camera_patch.status(payload/result/after)` in all four
   existing status dictionaries: plain inspection, image inspection,
   `write_copy` result, and image-write result. Add the same field to
   `_grown_status_fields(payload)` so deferred receipts refresh it too. Keep
   `camera_patch` as the exact detailed receipt key. Do not report this
   revision applied based on the old Standard descriptor words.
4. In `write_image_copy`, pass `camera and not defer_grown` in the first
   `_apply_all` call's existing positional camera slot. Include `camera=camera`
   in BOTH `_selected_space_requests` calls used by scorebug runtime and
   Guardian resource passes. In the final `if defer_grown` `_apply_all`, pass
   `camera=camera`. This prevents a camera-only directory being sealed before
   the resource owner union. `write_copy` needs no extra settings adapter;
   `camera.apply/status` already have the ordinary owner signature.
5. Any other `_selected_space_requests` call forwarding selected build flags
   must forward the existing camera flag too. Do not add camera to the r62
   keyword validator; this is already a top-level option.

### Protected BuildPlan: mod_editor/core/mod_build.py

Keep `BuildPlan.camera: bool = False` and update its stale comment to
`Far at startup/game entry, with room above the scorebar; experimental`.
Keep the current preset choices: **Basic off, Advanced on, Experimental on**.
Keep existing boolean normalization, capabilities presence check, inspection
field and step-receipt camera key. No new model field is needed.

For an XBE input, continue passing `camera=plan.camera` to `tt.write_copy`.
For the image path's initial deferred XBE pass, set camera false along with
the other grown owners. Add `camera=plan.camera` to the final
`tt._selected_space_requests` union around the resource passes. Add
`or plan.camera` to the final grown-owner pass predicate and pass
`camera=plan.camera` into that final `_apply_all`. The ordinary XBE-only
BuildPlan path is independently tested; the complete union is tested in both
orders by the two gates. Run an image acceptance build after this handoff is
wired, with disposable output, the disk threshold and streamed transport.

### Protected Gameplay Patches and Build text

In `mod_editor/gui/gameplay_patches_panel_qt.py`, replace the existing
`PATCHES` row for camera with:

```python
("camera", "Start games with Far (experimental)",
 "Retail: new settings select Standard and saved settings restore their camera choice. "
 "Patch: start with Far when settings load and when a game or practice starts. "
 "Far sits higher and farther back to leave room above the bottom scorebar. "
 "You can change cameras in Options for the current session. Experimental; not yet witnessed in play."),
```

Keep `camera` in `NEEDS_IMAGE`. Replace its concise display row with
`("Start games with Far", "Far leaves room above the scorebar; Options still works for the session.", NOT_TESTED)`.
Do not label it witnessed just because the older Far look was preferred.

In `mod_editor/gui/build_panel_qt.py`, retain `_option(pl, "camera", ...)` and
use caption **`Start games with Far (experimental)`** (34 characters), help
text `Far leaves room above the scorebar. Each game and practice starts with
Far; Options changes last for the session. Not yet witnessed in play.` and
`badge=NOT_TESTED`. No other GUI panel needs changes.

### Packaging, capability and manifest

No new runtime file is introduced. Retain these existing allowlist lines:

```text
mod_editor/core/nfl2k5_camera.py
mod_editor/core/nfl2k5_xbe_space.py
mod_editor/core/nfl2k5_draft_ai.py
mod_editor/core/nfl2k5_my_career_code.py
```

Retain those same modules in the protected runtime-closure import list and
run its closure check. The proof tool, tests, PNG and JSON are repository
verification artifacts and are not runtime-closure imports. The existing
camera flag is the only product surface, so no new capability registry object
is needed. `--inspect-camera-options nfl2k5` remains a read-only **retail** map;
do not replace its retail values with the patch's startup policy.

Claude must regenerate `data/nfl2k5_cave_reservations.json` after applying the
protected wiring above. The manifest builder includes camera in its request
union and both pure-owner install paths, and disables camera when creating
the separate ungrown probe. The gate uses the existing test-only
`manifest_for_allocated_union` to move only matching, named grown spans; all
retail reservations remain intact. This is not a replacement release
manifest. The gate also recognizes the current manifest's explicit transfer
of the eligibility hook from kickoff to relocated kickoff, then verifies the
actual installed bytes. No free/unknown cave exemption was added.

## r63-camera-v2: paired presets and modest pass framing (2026-09-07)

The backend is complete in the existing `nfl2k5_camera` owner, version 3.
`ASTRA_CAMERA_V2_REPORT.md` supersedes the earlier claim that Standard stays
retail, and corrects the old projection fixture's interpretation of type-2
camera offsets. There is no new option, row index, allocation, or Build preset
change. MyCareer assembly and its generated template remain byte-identical.

The camera-only BuildPlan and the complete owner union work with the already
landed Far wiring. **No dispatcher or BuildPlan implementation change is
needed.** Preserve `_apply_all`'s final tuple
`(camera, camera_patch, "camera_patch", "camera")`, the `camera=camera` kwarg,
request union and allocator deferral. Preserve `"camera": camera_patch.status(...)`
in all four status dictionaries (plain inspection, image inspection,
`write_copy` result, image-write result) and `_grown_status_fields`.
Keep `BuildPlan.camera: bool = False`, Basic off, Advanced on, Experimental
on. `REQUESTS` stays `(("nfl2k5_camera", "code", 64, 16),)`.

Two protected maintenance changes remain for Claude:

1. Update the existing `PATCHES` camera help in
   `mod_editor/gui/gameplay_patches_panel_qt.py` to this exact text, retaining
   the current title and `camera` in `NEEDS_IMAGE`:

   ```python
   "Retail: Standard and Far use the original camera framing and pass zoom. "
   "Patch: start games and practice with Far. Standard gives a closer view at "
   "the same raised angle, and both cameras pull back less during passes. "
   "Options changes last for the current session. Experimental; not yet witnessed in play."
   ```

   In `mod_editor/gui/build_panel_qt.py`, retain `_option(pl, "camera", ...)`
   and its 34-character caption `Start games with Far (experimental)`.
   Use help: `Far starts each game and practice. Standard offers a closer view
   at the raised angle; passes use a smaller pullback. Options changes last
   for the session. Not yet witnessed in play.` Keep `badge=NOT_TESTED`.

2. Regenerate protected `data/nfl2k5_cave_reservations.json` with the normal
   manifest tool after integration. Include the ten Standard descriptor edits
   and four complete pass/live instruction edits. The recorder now verifies
   the camera's owned-wrapper receipt against its named allocation and waits
   until `finish()` to publish that child. This fixes the old manifest's
   duplicate wrapper declaration from a different preset allocation. The
   test projection recognizes that old complete span only by re-planning the
   manifest's recorded preset; arbitrary/partial/missized spans still refuse.
   The protected manifest was not edited or regenerated in this task.

Retain existing allowlist lines and runtime-closure imports for
`mod_editor/core/nfl2k5_camera.py`, `mod_editor/core/nfl2k5_xbe_space.py`,
`mod_editor/core/nfl2k5_draft_ai.py` and
`mod_editor/core/nfl2k5_my_career_code.py`. No new runtime file or import is
introduced. The proof tool, public fixture, report, JSON and PNG are repository
verification artifacts. The unified provider's camera source digest is
already updated in `mod_editor/core/providers.py`. No new capability registry
entry is needed; the retail camera inspector remains a retail map. No release
tag, protected build module, allowlist, runtime-closure file or GUI file was
changed here. The new behavior remains EXPERIMENTAL / UNWITNESSED.
## r63 MyCareer: Game Modes row and any position (2026-09-07)

Branch `fable/r63-mycareer`, base `1749663`. The MyCareer owner
(`mod_editor/core/nfl2k5_my_career.py`, `tools/nfl2k5_my_career.S`, generated
`nfl2k5_my_career_code.py`), its Studio page, fixture and tests changed. The
owner's allocator request is unchanged at `8192 RX / 4096 RW`; the byte
template grew from 4,418 to 4,896 bytes (6,176 of 8,192 with the sealed
setup), so the budget fixture, `tests/nfl2k5_allocator_stack.py`, both gates
and the manifest builder need no edit. EXPERIMENTAL / UNWITNESSED remains.

What changed in the unprotected owner:

1. The First Person Football row of Game Modes (`0x501494`) is the MyCareer
   action, as before. The action is now proved through the retail list
   dispatcher (`0x150020`, kind 9, case table `0x15024C`) by
   `test_nfl2k5_my_career_unicorn.py`. A build whose sealed setup is empty
   shows a native message and pushes nothing; a configured build shows the
   entry message and pushes native Load / Save (`0x508DF0`). Both 20-byte
   labels equal `nfl2k5_modern_naming.career_text("menu_row")` and
   `career_text("screen_title")` (test-pinned).
2. MyPlayer can be any of the 17 retail positions. `prepare(..., position=,
   template=, starter_lock=)` replaces the first eligible prospect at that
   position; QB K P WR CB FS SS HB FB TE OLB ILB take one of their three
   retail create-a-player templates or `None`; C G T DT DE keep the generated
   prospect ratings. The runtime identity compares the record's position with
   the sealed recipe's position byte (checkpoint 149), no longer a fixed QB.
3. Optional starter lock (default on): at MyPlayer's first active club the
   owner writes depth row 1 plus the `nfl2k5_depth_locks` rank bit once;
   checkpoint words 180/184 carry the request and the once flag.
4. `MyCareer.json` is schema `nfl2k5_my_career/v2` with a `position` key. A
   v1 setup is refused with a message that says to create MyPlayer again.

### Protected text: mod_editor/gui/beta62_options.py

Replace the `my_career` row's literal help with the owner's text so the shared
Build and Gameplay captions describe any position and the Game Modes entry:

```python
("my_career", "MyCareer (experimental)", tt.my_career_patch.HELP_TEXT),
```

No `BuildPlan` field, preset default, dispatcher argument, `_apply_all`
tuple, status dictionary, `NEEDS_IMAGE` entry, allowlist line or
runtime-closure import changes: `read_setup` keeps its signature and the
Build path still calls only `my_career_patch.read_setup(plan.my_career_setup)`.
If Build should refuse a stale v1 setup before copying, no change is needed
either; `read_setup` raises `MyCareerError` with the message above.

### Protected registry: mod_editor/capabilities/registry.v1.json

Replace the `nfl2k5.mode.my_career` object with the updated object in
`docs/mod_editor/nfl2k5_my_career_capabilities.json` (summary, backend
command, input constraints, evidence and runtime scope now describe any
position, the Game Modes entry and `FABLE_MYCAREER_REPORT.md`). The merged
registry validates with `validate_data(..., check_files=False)`; with file
checks on, the new evidence paths resolve once the report is committed.
Keep the crib object as it is.

### Release manifest

`data/nfl2k5_cave_reservations.json` pins `mod_editor/core/nfl2k5_my_career.py`
and `nfl2k5_my_career_code.py` by SHA-256; both changed. Regenerate the
manifest with the existing `tools/nfl2k5_cave_oracle.py manifest --xiso ...
--work-dir ...` real-disc workflow when the main drive has room for its
disposable 6+ GB image (this session had 101 GB free, at the floor, so it did
not). The default manifest at this base also carries a stale `nfl2k5_camera`
span `0x14DA400..0x14DA440` ("declared edit: owned_camera_wrappers") whose
containing allocation is absent from the manifest's own `allocator_layout`
(the camera allocation is at `0x14DA830`), so
`tests/nfl2k5_allocator_stack.manifest_for_allocated_union` refuses the
default JSON in `test_xbe_patch_cave_references.py` and in
`test_nfl2k5_my_career_manifest.py` independent of this change (the previous
manifest `75bbd8b` has the same span). The recorder in
`test_nfl2k5_guardian_manifest.py` refuses the allocator's own scale-out
reservation at the untouched base as well (verified with this branch's paths
stashed). Neither refusal was weakened; regenerating the release manifest
clears both, and the memory-writes gate (79, both orders) and the pairwise
suite (77) pass with this change.

---

# r63 broadcast scorebug exact comparison, 2026-09-07

This section supersedes the r63 v9 scorebug handoff above. The new scene is
`espn-broadcast-exact-v1`, and runtime resources are
`scorebug-runtime-v3-broadcast-exact`. **EXPERIMENTAL / UNWITNESSED.** The
measured geometry agrees with the real LV/HOU JPEG, but the pixel comparison
does not pass. Do not label the result 1:1 or advertise a runtime freeze fix.
See `ASTRA_SCOREBUG_EXACT_REPORT.md` and `docs/scorebug_ingame/exact/scores.json`.

## Required protected integration

Add this exact line to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_scorebug_exact.py
```

Add this exact dotted import alongside the existing scorebug imports in
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_scorebug_exact",
```

The existing ingame/resources modules import it in the product path. Without
these two additions a release stage will be incomplete. The comparator tools
and research PNG/JSON files do not need to enter the application closure.
If research tools are packaged separately, include both
`tools/nfl2k5_scorebug_projection.py` and `tools/nfl2k5_scorebug_exact.py` and
provide their existing Pillow, numpy, Capstone and Unicorn research dependencies.
Do not add numpy or Unicorn to an ordinary scorebug build requirement.

Regenerate the protected cave manifest with the existing
`tools/nfl2k5_cave_oracle.py manifest` process. The static owner's existing
`xbe_specs()` now includes native font selectors, neutral team-label colours,
and the four-byte operand at `0x000FBE43`. The operand changes
`MOV EDX,0x00E6C438` to `MOV EDX,0x00E6C43A`, selecting the existing UTF-16
`%02d` suffix. Its complete instruction and unchanged literal are tested.
There is no new cave, owner or allocator request. Keep the existing complete
forward/reverse gate unions. Refresh the generated source identity records.

## Existing dispatcher, status, presets and interface

- `_apply_all` already has
  `(scorebug_runtime, scorebug_runtime_patch, "scorebug_runtime_patch", "experimental scorebug effects")`
  at `nfl2k5_throw_tuning.py:1593`. Retain `scorebug_runtime: bool = False`,
  `_selected_space_requests(... runtime=...)`, `_xbe_space_adapter` and the
  existing final owner pass. The static path remains
  `plan.scorebug and not plan.scorebug_runtime` in `mod_build.py:1146`, through
  `nfl2k5_scorebug_layout.apply_in_place` and the additive ingame writer.
- All four executable status dictionaries already call
  `"scorebug_runtime": scorebug_runtime_patch.status(payload)` and
  `"scorebug_xbe": scorebug_reference.xbe_status(payload)` (use `after` in
  the final dictionary). Their current locations are 655/656, 782/783,
  1758/1759 and 2091/2092. Keep these keys. The two image dictionaries also
  retain `scorebug_runtime_resources`; static image status retains `scorebug`.
  The updated modules supply the new identities; do not loosen foreign/mixed
  refusal or accept old v8/v9 bytes as the new version.
- `BuildPlan`: keep `scorebug: bool = False` and
  `scorebug_runtime: bool = False`. Basic and Advanced leave static off;
  Experimental enables static. Every preset leaves runtime off. Retain
  runtime normalization, the deferred archive/XBE final pass, and the
  existing conflict with hires scorebug edits. No new field or preset.
- Gameplay Patches `PATCHES` remains the existing two rows with shared help;
  `NEEDS_IMAGE` already includes both `scorebug` and `scorebug_runtime`.
  Replace the shared `SCOREBUG_HELP` and `SCOREBUG_RUNTIME_HELP` in
  `mod_editor/gui/beta62_options.py` with the concrete strings below.
- Build `_option` captions: retain `Experimental ESPN scorebar` (26 chars)
  and `Scorebug effects (diagnostic only)` (34 chars), `needs_image=True`,
  the `NOT_TESTED` badge and the shared help/details references.
- Capability registry: no new surface or row. Keep the runtime diagnostic
  capability experimental with runtime `not-tested`. Update its resource
  version/evidence if pinned there; do not promote it to runtime-proved.

```python
SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Uses a bar measured from the "
    "Raiders at Texans broadcast, with a red down box, a light clock strip, "
    "white scores and three decorative timeout marks on each side. Team panels "
    "stay neutral. Moves the kick meter up and hides the lineup strip. "
    "EXPERIMENTAL / UNWITNESSED; fonts and colours still differ from the reference.")
SCOREBUG_RUNTIME_HELP = (
    "Retail: Uses the original team panels. Patch: Adds team gradients, logos, "
    "small wordmarks and live timeout marks to the experimental scorebar. "
    "Diagnostic only and off in every preset. EXPERIMENTAL / UNWITNESSED; "
    "the reported game-entry freeze is unresolved. Keep the six probe choices.")
```

No protected file was edited in this worktree. The existing runtime hook code,
1408-byte RX and 128-byte RW requests, load/update ABI, timeout sources and
six probe names are unchanged. This update changes panel/scene data, fonts
selected from retail FONT objects, and the static play-clock format operand.
A separate local glyph atlas has **not** been installed. The requested pixel
match and glyph-binding fallback remain gaps; the report gives the measured
font limits and the evidence required before claiming they are solved.

---

# r63 Discord bugs, batch 2, 2026-09-07

> Integration note (Claude, 2026-09-07 05:45): items 1 to 3 of the proposal (studio_qt sheet layouts,
> mod_build destination check and publish, nfl2k5_throw_tuning transactional publish) are applied on the
> stack. Item 4, the `mod_editor/apf_studio/gui.py` hunk (ApfFieldArtPanel/ApfTeamLogoPanel reading the
> session's staged art, the multi-edit notice), is NOT applied: it makes `set_context` clear `_staged_png`
> whenever the facade's session has no crest modification, and the fake facades in
> tests/mod_editor/test_apf_field_art_gui.py (17 errors) and test_apf_team_logo_gui.py (a modal
> "Cannot build team logo copy yet" box blocks the offscreen run) do not model a session. Apply it together
> with session-aware fixtures for both suites. The rest of the APF work in the branch (facade, session,
> build, project, field_art, helmet crest) is landed.

See `ASTRA_DISCORD_BUGS_2_REPORT.md`. Editor core changes are implemented in
unprotected files. Gameplay conclusions are **EXPERIMENTAL / UNWITNESSED**;
this job adds no executable owner or resource patch. Do not infer a runtime
fix from the editor tests. No protected source file or other GUI panel was
edited in this worktree.

## Concrete protected-source proposal

`tests/fixtures/discord_bugs_2_wiring.patch` contains exact, compilable diffs
for the following four files. It passes `git apply --check`. The standalone
`tests/mod_editor/test_discord_bugs_2_wiring.py` applies the hunks in memory
and exercises the actual proposed functions/classes; it never changes the
protected source files. Six checks pass, including offscreen Qt. Setting
`ASTRA_TEST_UNWIRED=1` reproduces defects against the current files.

1. `mod_editor/gui/studio_qt.py`: import `SHEET_HELP` and `SHEET_LAYOUTS` from
   `nfl2k5_digit_sheet`; show the shared tooltip; after choosing jersey/helmet/
   arm, select one row, one column, five columns/two rows, or two columns/five
   rows. Pass the selected key as `orientation` to `split_digit_sheet`. Keep
   existing target-family validation and asynchronous ten-digit import.
2. `mod_editor/core/mod_build.py`, `build`: preserve the original-source
   rejection and add samefile/hardlink rejection. Before any expensive build,
   call `previous_target = check_image_destination(target,
   overwrite=plan.overwrite)`. Replace final `os.replace` with
   `publish_image(directory / target.name, target, previous_target)` after all
   readers are closed. The shared helper is `mod_editor.core.image_use`.
   A new destination uses atomic no-replace; an existing destination is probed
   before and after the work and must retain its identity/size/mtime. An image
   observed open in another process gets the eject/close-emulators message.
3. `mod_editor/core/nfl2k5_throw_tuning.py`, `_transactional_image_writer`:
   use the same destination preflight and final `publish_image`, preserving
   its source/link checks, temporary-directory cleanup and final receipt path.
   This wraps both existing copied-image entry points. Never probe our own
   staging image while its writer is open. The cached Studio build service's
   existing no-replace publication and new occupied-output explanation, plus
   the Studio facade's actual launch probe, are already implemented.
4. `mod_editor/apf_studio/gui.py` (also off limits under the brief's other-GUI
   collision rule): `ApfFieldArtPanel` stages/reverts through the shared facade,
   reads authoritative session state, and emits `modifiedChanged` through
   `FieldArtStudioPage`. The multi-edit copied-volume action says to use Build
   Game Folder. `ApfTeamLogoPanel` looks up `session.crest_modification` for the
   selected team; it no longer jumps back to the last legacy-ID team, reverts
   only the selected asset, and clears stale placement/master state when
   switching. Save authoring master passes that team's `crest_asset_index`,
   captured on the UI thread before starting the worker.

Apply the fixture only once the corresponding protected files are reconciled
with other jobs. After it lands, run the same behavior checks against the
integrated files (the fixture's preimage checks intentionally reject source
drift), then the ordinary desktop tests and clean runtime closure. The fixture
is test/review material, not an application runtime dependency.

## Required release closure

Add these exact lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/image_use.py
docs/mod_editor/number_sheets.md
docs/mod_editor/discord_bugs_2_faq.md
```

The changed digit splitter, Studio facade and cached build service are already
listed. Add these imports to protected
`packaging/check_2k5_mod_studio_runtime.py` alongside the existing core imports:

```python
"mod_editor.core.image_use",
"mod_editor.core.nfl2k5_digit_sheet",
```

Deduplicate if another integration adds them first. `image_use` adds standard
library dependencies only; macOS needs its existing system `lsof`. Keep the
real Windows CreateFileW branch and exclusive-share refusal, not a POSIX-only
flock substitute. Run native Windows/macOS held-reader checks before declaring
those platforms verified. Linux visibility and the final POSIX check/rename
race are documented limitations, not a mandatory-lock claim.

Refresh `RC29_AUDIO_ANNOTATION_RUNTIME_PINS` for the changed
`mod_editor/studio/facade.py` and, after wiring, `mod_editor/gui/studio_qt.py`
from their final reviewed bytes. Keep other owners' pins intact; a current
tree cannot pass that protected gate by retaining the old facade digest.
Do not add these editor helpers to a native XBE provider ownership list merely
to silence a source-pin mismatch.

The unprotected APF allowlist already gained both help pages. The existing
product list already imports `mod_editor.apf_studio.field_art`; its tool list
now explicitly imports `apf_field_art_patch` and `apf_logocache_patch`.
All 104 product/tool imports and literal import closure pass. Full APF clean
stage validation remains blocked by four absent vendored extract-xiso files:
`BUILDING-THE-BUNDLED-BINARIES.md`, `LICENSE.TXT`, `build/extract-xiso`, and
`build/extract-xiso.exe`, beneath `tools/vendor/extract-xiso/`. Restore the
already-pinned distribution inputs through the normal release process, then
run `packaging/check_apf2k8_mod_studio_runtime.py` from a clean allowlist stage.
Do not relax extractor hashes or admit the development `reports` directory.

## Dispatcher, status, presets and capability checklist

These items are explicitly unchanged because this batch fixes existing editor
surfaces and researches existing gameplay owners; it installs no new patch:

- `_apply_all` dispatcher tuple and corresponding patch kwarg: **no addition**.
  `_selected_space_requests`, `_xbe_space_adapter`, final owner tuple and
  `_grown_status_fields`: **no addition**. Existing dynamic kickoff, screen,
  abilities, Momentum, playlist and content-owner entries remain as shipped.
- All four status dictionaries (XBE inspect, image inspect, apply result and
  copied-image result): **no new key and no altered status policy**. Preserve
  each existing owner's Retail/applied/foreign refusal, before/after payload
  handling and paired archive status. The file-use probe is host editor state,
  not an XBE `status(payload)` owner.
- `BuildPlan` field: **none**. Basic/Advanced/Experimental: **no new opt-in and
  no preset changes**. Existing Basic/Advanced leave dynamic/alignment false;
  Experimental enables both. Current normalization already makes dynamic
  enable alignment/kick rules and disable old kick power. Keep runtime scorebug
  diagnostic and off in all presets. Do not claim this investigation measured
  a preset's FPS cost.
- Gameplay Patches `PATCHES` row and `NEEDS_IMAGE`: **no new row/member**.
  These are import/build/launch fixes, not selectable gameplay patches. If
  updating existing owner descriptions after a played bisect, retain literal
  `Retail` and `Patch` descriptions and existing `NEEDS_IMAGE` requirements.
  No speculative blocking, muff, widescreen or boot fix belongs in that list.
- Build tab `_option` caption (maximum 60 characters): **none added**. Keep
  the existing build actions. The short sheet-layout labels and APF action
  explanations are supplied in the concrete fixture, not as gameplay options.
- Capability registry: **no new surface**. Existing number import, APF helmet
  crest and `apf2k8.field_art.base_texture` capabilities remain. On GUI landing,
  update the existing Field Art description/evidence to mention shared project
  staging/Build Game Folder and `test_discord_bugs_2.py`, retaining native
  writer selectors, fixed-span/mip limits and runtime `not-tested`. Multiple
  crests support Retail side decals only; do not advertise independent
  full-shell geometry. No new CLI or fabricated module command is needed.
- Allocator fixture, both owner gate unions, cave manifest and memory budgets:
  **unchanged**, since no executable bytes or owner requests changed. Claude
  need not reserve a cave for these editor operations.

## Bounded gameplay follow-up decisions

B19: first classify the abilities charge consumers and capture normal/hurry-up
assignment/clock/charge state. Only a proved noncarrier-block consumer justifies
a native-policy exception; a screen reset change needs a stale-clock witness.
Use the existing owner's allocation and composition gates if a later change
is justified. No speculative new hook is handed off.

B13/B5/B6: retest current widescreen and kickoff v3; do not duplicate already
landed camera, alignment or nearest-threat code. Separate punt muffs from
kickoff hold jitter. A screen-edge witness must identify the drawing surface.

B8/B20: use the report's phase-specific one-owner matrix and exact size table.
Compare a matching allocator-only control, keep required XBE/archive pairings,
and use existing scorebug diagnostic probes. Capture stopped PC/I/O/heap/GPU
state and frame counters; looping audio is not proof of a music failure.
No per-owner gameplay fix or runtime performance claim is ready to publish.

## r64 MyCareer in-game mode, M1 design and native prerequisites

See `ASTRA_MYCAREER_MODE_DESIGN.md` and `ASTRA_MYCAREER_MODE_REPORT.md`.
M1 changes no production writer, native hook, REQUESTS, BuildPlan or preset.
The new audit and route suites are development evidence, not a playable mode
or release capability. Do not remove the current setup guard based on M1.

Concrete protected handoff once M2 actually satisfies its exit criteria:

- `nfl2k5_throw_tuning.py`: keep the existing `_apply_all` allocator union
  and MyCareer entry, `my_career` kwarg, adapter and `my_career_patch` owner.
  Its generic new-mode branch must call `my_career_patch.apply(payload)`
  with no player setup. Retain explicit legacy setup handling only for legacy
  saves/builds. `_selected_space_requests` and `_xbe_space_adapter` continue
  selecting `my_career_patch.REQUESTS`; never reserve an additional mode owner
  for the same code. If implementation enlarges REQUESTS, first update the
  unprotected budget fixture, stack compose tuple and all three manifest-owner
  lists, and prove the union. M1's request sizes have not changed.
- All four status dictionaries (executable inspection, image inspection,
  apply result, copied-image result) must retain `my_career` from the same
  exact `status(payload)`, including `_grown_status_fields`. Add a readiness
  detail only from a real owner receipt; `applied` alone must not mean the
  new mode is implemented, witnessed or that a save was created. Never treat
  missing seed bytes as foreign once the new owner format supports seedless
  mode; mixed versions still refuse before mutation.
- `mod_build.py`: retain `BuildPlan.my_career: bool = False`. After the new
  runtime lands, allow `my_career=True, my_career_setup=None` through current
  normalization/freezing/deferral/final pass. Replace the mandatory setup
  rejection at the current lines 894..899 with the owner's actual version
  contract. Keep `my_career_setup` as an optional legacy project field, not
  a new-career requirement. Basic, Advanced and Experimental remain OFF until
  a separate acceptance decision; no preset is changed by this milestone.
- `gameplay_patches_panel_qt.py`: only after M2, remove setup-file dependency
  from new-mode readiness, `_refresh`, plan capture and the setup chooser.
  Retain `my_career` in `NEEDS_IMAGE`. Replacement PATCHES description:
  `Retail controls a franchise team. Patch adds MyCareer: create MyPlayer
  in the game, choose a team, play and practice from your apartment, and
  save your career. Experimental / Unwitnessed.` This text contains literal
  `Retail` and `Patch`; do not use it while the runtime is incomplete.
- `build_panel_qt.py`: future `_option` caption exactly
  `MyCareer: create MyPlayer in the game` (37 characters). Remove its
  mandatory JSON field/readiness error for the new format. Generic disc build
  has no name, college, player ordinal or prepared save parameter. Existing
  projects carrying a legacy seed need an explicit compatibility indication.
- `studio_qt.py`: stop directing new-mode users to preparation on the old
  MyCareer page after the new runtime is ready. Do not remove or repurpose
  unrelated GUI panels in this branch. The feature's own panel may retain a
  clearly labelled legacy save tool; it is not part of the player flow.
- `packaging/release-allowlist.txt`: no new runtime line for M1. Existing
  `mod_editor/core/nfl2k5_my_career.py` and
  `mod_editor/core/nfl2k5_my_career_code.py` remain. The audit tool and unittest
  fixtures are development-only and must not be imported by shipped runtime.
  Any later new runtime module, authored image or capability file requires an
  explicit allowlist line and closure check after its actual path exists.
- `packaging/check_2k5_mod_studio_runtime.py`: no M1 import addition. Keep the
  two existing MyCareer core imports; add actual new runtime imports only at
  their implementation milestone. No dependency on test fixtures or private
  corpus/retail paths is permitted.
- Capability registry: no new installed surface in M1. Future in-game mode
  updates the existing MyCareer object in
  `docs/mod_editor/nfl2k5_my_career_capabilities.json`, not a duplicate owner.
  Backend command stays `python3 -m mod_editor.core.nfl2k5_my_career info`;
  validation command must resolve a real dotted module. Replace Studio/draft
  setup instructions only when the new loop is implemented. Keep runtime
  `not-tested` and the witness list; resource checks are not Noah's witness.
- `data/nfl2k5_cave_reservations.json`: never edit its source hashes manually.
  No production source drift is introduced in M1. Regenerate with
  `tools/nfl2k5_cave_oracle.py manifest` after actual hook/source integration.
  No broad unknown/free exemption is authorized for the proposed save tail.

Cross-owner contracts, also pending real implementation: the Practice launch
helper must recognize the sealed MyCareer hub as its retained parent while
keeping exact settings/Team Select checks; MyCareer's dispatch restrictions
must allow that exact hub and approved children. The shared franchise
auto-save owner must supply its actual public API and proved save-context
initialization before wiring an after-game call. M1's proposed adapter ABI is
not an existing function address. No protected file was edited.

M2 investigation update: supplied year-7 Franchise1 has nonzero native words
at save offsets `0x9967C`, `0x99680`, `0x99684`. Reject unconditional use of
the proposed 128-byte tail. No inline-state writer, extra hook, product option,
native-hub recipe or setup-guard removal is ready to wire from this continuation.
The read-only audit's `--save` option and creation-boundary suite remain
development-only, with no new runtime-closure or allowlist import.
# r63 Franchise Auto Save handoff (2026-09-07)

Owner: `mod_editor/core/nfl2k5_franchise_autosave.py`; evidence and witness list:
`ASTRA_FRANCHISE_AUTOSAVE_REPORT.md`. EXPERIMENTAL / UNWITNESSED. This appendix
specifies the protected product edits; those files were deliberately not edited.
The standalone backend, assembly, capability object, manifest builder registration
and both complete XBE gate unions are implemented in this change.

## Dispatcher: `mod_editor/core/nfl2k5_throw_tuning.py`

Import `nfl2k5_franchise_autosave as franchise_autosave_patch`. Add strict boolean
`franchise_autosave=False` to `_apply_all`, `write_xbe_copy`, `write_image_copy`,
`_validate_r62_options`, `_selected_space_requests` and `_xbe_space_adapter`.
Thread it through all callers, including the validation call inside the request
selector. Add the key to both `R62_RUNTIME_KEYS` and `R62_SPACE_KEYS`; the existing
`_r62_options`, `_r62_space_options` and `_deferred_r62_options` then carry/defer it
with the rest of the selected allocator union. Add it to the boolean validation
sequence in `_validate_r62_options` and every public no-options predicate.

Append to `_selected_space_requests`:

```python
+ (franchise_autosave_patch.REQUESTS if franchise_autosave else ())
```

Forward `franchise_autosave=franchise_autosave` inside `_xbe_space_adapter` and
include the flag in its `self.scaleout` expression. Include it in every predicate
that selects the allocator transaction, including `_apply_all`'s allocator row.
Do not install this owner before planning and reserving the full selected union.
No settings adapter is needed; `apply(payload)` has no additional parameters.
Add this exact tuple to `_apply_all`'s final owners, after the allocator entry:

```python
(franchise_autosave, franchise_autosave_patch,
 "franchise_autosave_patch", "Franchise Auto Save (experimental)")
```

The four public status dictionaries must return
`"franchise_autosave": franchise_autosave_patch.status(payload)` (substitute
`result` or `after` for their final-byte variable): `read_xbe`, `read_image`,
`write_xbe_copy`, and `write_image_copy`. The current tree already expands
`_grown_status_fields` in all four, so put the field there once; verify all four
public results. Keep installation status separate from the live Off/On switch.
The backend cannot inspect a running game's current switch from an offline XBE.
Expose the subreceipt under `franchise_autosave_patch`; propagate it into the
write/build receipt alongside the other owner receipts and changed-byte count.

For `write_image_copy`, include the flag in `defer_grown`, in the complete
`_selected_space_requests` calls passed to paired/grown image writers, and in the
last `_apply_all` pass. Keep it false during any early pass that must remain
retail-size. Use the existing grown-XBE image writer to relocate the executable;
never write a 12,300,288-byte XBE into the old retail extent. No PLAY/ROST/archive
resource or asset pass is needed. The direct module CLI is a bounded standalone
XBE-to-new-XBE tool, not a disc editor.

## BuildPlan, presets and availability: `mod_editor/core/mod_build.py`

Add `franchise_autosave: bool = False` to `BuildPlan`, include it in
`wants_xbe_patch()`, strict option normalization/validation, capability availability
module checks and source status projection. Make it available when the backend
can import. Add it to the `_core_module` availability mapping with
`nfl2k5_franchise_autosave`; do not tie availability to MyCareer or Franchise
Practice, because both standalone and composed Desk layouts are supported.

Set `franchise_autosave=False` in `basic`, `True` in `softdrink_advanced`, and
`True` in `softdrink_experimental`. These are installation presets. The in-game
switch starts **Off**, and an existing save restores its saved word. A new
franchise needs one manual save to establish a destination. No default save
name, storage device or slot number is inferred.

Normalize enabled Auto Save to `xbe_space=True`. Add it to the predicate near
`momentum_on` that defers grown owners, the `replace(..., camera=False, ...)`
early-XBE selection (also `franchise_autosave=False` there), the final grown-owner
predicate, and the final `tt.write_copy` kwargs. When using `R62_RUNTIME_KEYS`,
ensure the new BuildPlan field is picked up by `_build_r62_values`; avoid duplicate
explicit and `**r62` kwargs. Include the flag and subreceipt in the corresponding
build steps, scan/status key list and receipts. Preserve one immutable allocator
union across all later camera, scoreboard and roster passes.

## Shared UI wiring (protected panels)

In `mod_editor/gui/gameplay_patches_panel_qt.py`, add a `PATCHES` row:

```python
("franchise_autosave", "Franchise Auto Save (experimental)",
 tt.franchise_autosave_patch.HELP_TEXT)
```

`HELP_TEXT` contains both **Retail** and **Patch** and the required
EXPERIMENTAL / UNWITNESSED label. Add `franchise_autosave` to `NEEDS_IMAGE`:
the Studio patch surface must use its existing grown-image pipeline, even though
all feature resources are inside the XBE. Include the option in source-only
eligibility, availability/status display, selection and writer kwargs.

In `mod_editor/gui/build_panel_qt.py`, add:

```python
self.franchise_autosave_check = self._option(
    pl, "franchise_autosave", "Franchise Auto Save (experimental)",
    tt.franchise_autosave_patch.HELP_TEXT)
```

Caption length is **34** characters, below 60. Wire its refresh signal, preset
mapping, capability gate, BuildPlan creation, selected-options summary, reset and
wants-patch check. Retain the experimental help text. If these paths use a shared
UI key table, add the key there through the coordinating owner; no feature panel
or setup file is needed. In `studio_qt.py` and `gameplay_panel_qt.py`, forward the
same key wherever the shared patch/build selections or source status are copied;
do not create a second independent toggle model.

The native row at `0x500B24` becomes **Auto Save**. The existing Coach's Desk ->
Options -> Franchise Options row at `0x52BB68` becomes the same **Auto Save**
switch. Generic Game Options has nine occupied rows and no proved spare, so do
not insert a generic Options row. Both replacements preserve the native Off/On
choice renderer, row size, row order and number of rows.

## Packaging, capability registry and closure

Add these literal source allowlist lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_franchise_autosave.py
mod_editor/core/nfl2k5_franchise_autosave_code.py
tools/nfl2k5_franchise_autosave.S
tools/nfl2k5_franchise_autosave_assemble.py
docs/mod_editor/nfl2k5_franchise_autosave_capability.json
ASTRA_FRANCHISE_AUTOSAVE_REPORT.md
```

The executable template lives in `_code.py` and its source is `.S`. Include the two standalone tests and
`tests/nfl2k5_franchise_autosave_fixture.py` only if the existing package policy
ships test sources. Never include the brief, scratch evidence, retail executable,
save buffers or a generated disc.

In `packaging/check_2k5_mod_studio_runtime.py`, add these import-closure entries:

```python
"mod_editor.core.nfl2k5_franchise_autosave",
"mod_editor.core.nfl2k5_franchise_autosave_code",
```

Existing dependencies must remain in closure: `nfl2k5_xbe_space`,
`nfl2k5_bump_strength`, `nfl2k5_cave_oracle`, `nfl2k5_franchise_practice` and
`nfl2k5_music_playlist`. The last two recognize only their fully validated
installed table/dispatcher changes. No GNU assembler, Capstone or Unicorn is
needed to apply the packaged runtime; GNU `as --32` is only a development
regeneration tool, and Unicorn/Capstone are optional test dependencies.

Merge the exact object from
`docs/mod_editor/nfl2k5_franchise_autosave_capability.json` into
`mod_editor/capabilities/registry.v1.json`, sort capability IDs, and run the
existing strict registry validator with file checks. Keep classification
`offline-writer-proved`, runtime `not-tested`, and GUI default false (Basic).
Both backend and validation commands use `python3 -m <dotted.module>`.
Do not promote this to runtime-proved before Noah's witness.

Checkout limitation: full registry file-check mode currently stops at the
pre-existing missing `docs/research/apf_audio.md`. The feature test validates
the merged schema and strictly resolves every new object reference/command.
Run the full registry check in the coordinating checkout with its existing
research evidence present; do not weaken the validator or forge missing files.

## Manifest and coordinating acceptance

Already implemented: `tests/nfl2k5_allocator_stack.py` request union and both
compose orders; budget fixture; manifest builder append/owner/observer lists,
`all_requests`, final and synthetic owner passes and extra-owner list; both XBE
gates' explicit Auto Save checks. The protected release manifest predates this
owner. Gates project each exact new live edit only after pinning its retail bytes,
validating the complete installed owner, and rejecting other-owner overlap.
This test-only projection never writes or relaxes the production manifest.

Claude must regenerate `data/nfl2k5_cave_reservations.json` using the existing
`tools/nfl2k5_cave_oracle.py manifest` command after the protected wiring lands.
In the manifest builder's separate retail-size seed `replace`, also disable
`franchise_autosave` once the new preset enables it. Its explicit complete-union
probe installs Auto Save afterward. Use temporary disc storage that is deleted
on every exit, keep root free space above 100 GB, and retain only receipts.

Run the two standalone feature suites, assembly `--check`, strict capability
validator, complete memory-write and cave-reference gates, and the existing
BuildPlan/preset/source-status/runtime-closure tests after wiring. Assert all
four status dictionaries report retail on base and applied on the installed
copy, false makes no feature edits, both enabled presets reserve the three
requests, and the final grown-image pass remains replay-identical. Do not change
release/version tags as part of this handoff.
---

# r64 scorebug in-game fix, 2026-09-07

See `ASTRA_SCOREBUG_INGAME_FIX_REPORT.md` and the calibrated witness comparison
in `docs/scorebug_ingame/fix/comparison.png`. This section supersedes prior
descriptions of the default static exact bar as anonymous, with no possession
cue. Default scene version is `espn-broadcast-exact-v2`; an explicit artwork
folder keeps the byte-identical `espn-reference-v10` contract. The fix remains
**EXPERIMENTAL / UNWITNESSED**. Runtime stays diagnostic and disabled in every
preset; the reported game-entry freeze is still open.

No protected file or GUI panel was edited. Claude's concrete changes are the
shared help text and regeneration of the protected reservation manifest from
the final integrated sources. The existing dispatch, options, presets and
application import closure already reach this implementation.

## Shared help and existing UI rows

Replace the two constants in `mod_editor/gui/beta62_options.py` with:

```python
SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Uses neutral panels with "
    "live team abbreviations, yellow possession highlighting, white scores, "
    "a red down box and separate clock cells with a dark play-clock cell. "
    "Ball-on and event labels use a separate lower row. The three timeout "
    "marks on each side are decorative. A scorebar folder selects your "
    "painted template. Moves the kick meter up and hides the lineup strip. "
    "EXPERIMENTAL / UNWITNESSED; rebuild from a clean source for these fixes.")
SCOREBUG_RUNTIME_HELP = (
    "Retail: Uses the original team panels and text. Patch: Adds team "
    "gradients, logos, live timeout marks, resized text, a white possession "
    "marker and room for three-digit scores to the experimental scorebar. "
    "Diagnostic only and off in every preset. EXPERIMENTAL / UNWITNESSED; "
    "the game-entry freeze remains unresolved. Keep the six probe choices.")
```

Keep these existing `Gameplay Patches` `PATCHES` rows, using those shared
descriptions (both contain the required words `Retail` and `Patch`):

```python
("scorebug", "Experimental ESPN scorebar", r62_ui.SCOREBUG_HELP),
("scorebug_runtime", "Scorebug effects (diagnostic only)", r62_ui.SCOREBUG_RUNTIME_HELP),
```

Both keys remain in `NEEDS_IMAGE`. Keep Build's `_option` captions
`Experimental ESPN scorebar` (26 characters) and
`Scorebug effects (diagnostic only)` (34 characters), their shared help,
`needs_image=True` and `badge=NOT_TESTED`. The artwork folder remains disabled
when runtime is selected. Add no new checkbox and do not imply static logos.

## Dispatcher, status and presets: preserve the existing wiring

In `mod_editor/core/nfl2k5_throw_tuning.py`, retain the `_apply_all` tuple:

```python
(scorebug_runtime, scorebug_runtime_patch, "scorebug_runtime_patch", "experimental scorebug effects"),
```

Keep kwarg `scorebug_runtime: bool = False`, its propagation through copied-image
build/apply, the existing request union and `_xbe_space_adapter` runtime flag,
and the existing final owner pass after allocation/resource installation. The
static selector continues through `sbl.apply_in_place(target,
scorebug_folder=plan.scorebug_folder or None)` in Build; that existing layout
adapter delegates to `nfl2k5_scorebug_ingame.apply_in_place`. No new allocator owner,
adapter, request, `_grown_status_fields` entry or budget fixture row is needed.

Retain these existing fields in all four status dictionaries: XBE inspection,
image inspection, XBE apply result, and copied-image result:

```python
"scorebug_runtime": scorebug_runtime_patch.status(payload),
"scorebug_xbe": scorebug_reference.xbe_status(payload),
```

Use each function's actual inspected/final payload (`result` or `after` in the
two result dictionaries), as currently wired. Keep paired image resource
status, including `scorebug_runtime_resources`, and existing mixed/foreign
refusal. A completely recognized runtime installation adjusts the two static
identity defaults internally; no UI status override should hide a partial
installation. Old exact-v1 resources/XBE require a clean-source rebuild.

Keep the existing `BuildPlan` fields:

```python
scorebug: bool = False
scorebug_runtime: bool = False
scorebug_folder: str = ""
```

Basic and Advanced leave both scorebug flags false. Experimental enables
`scorebug` and leaves `scorebug_runtime` false. Manual runtime still implies
static scorebug and the allocator, clears the folder, and uses the existing
deferral/final-pass order. No preset normalization change is requested.

## Release allowlist, runtime closure and capabilities

No new product module was added. Keep these exact existing allowlist lines in
`packaging/release-allowlist.txt`; do not duplicate them:

```text
mod_editor/core/nfl2k5_scorebug_exact.py
mod_editor/core/nfl2k5_scorebug_fonts.py
mod_editor/core/nfl2k5_scorebug_ingame.py
mod_editor/core/nfl2k5_scorebug_resources.py
mod_editor/core/nfl2k5_scorebug_runtime.py
tools/nfl2k5_scorebug_reference.py
```

Keep the matching existing core imports in
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_scorebug_exact",
"mod_editor.core.nfl2k5_scorebug_fonts",
"mod_editor.core.nfl2k5_scorebug_ingame",
"mod_editor.core.nfl2k5_scorebug_resources",
"mod_editor.core.nfl2k5_scorebug_runtime",
```

The new `tools/nfl2k5_scorebug_witness.py`, authored v1 compiler fixture and
`docs/scorebug_ingame/fix/` are research/test evidence, not runtime dependencies.
Do not add their Unicorn/numpy capture harness to product startup or bundle
retail XBE/SCNE/FONT/pack data. No allowlist or import addition is required for
the application. If distributing this report as release documentation, add
the explicit line `ASTRA_SCOREBUG_INGAME_FIX_REPORT.md` through the normal
documentation packaging decision.

No new capability surface or registry entry is needed. Keep
`nfl2k5.scorebug_presentation.runtime` diagnostic, default disabled,
`classification=offline-writer-proved`, `runtime.status=not-tested`, and keep
its existing schema-valid backend/validation commands. When refreshing its
existing evidence, add this report and
`tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py`; describe the static
identity/event fix and current `hooks` versus `neutral` witness without
promoting runtime or claiming a freeze repair.

## Protected native manifest handoff

Regenerate `data/nfl2k5_cave_reservations.json` with the existing
`tools/nfl2k5_cave_oracle.py manifest` process after integrating the final
source union. This worktree intentionally leaves it untouched. The reviewed
differences are existing descriptor colors/font IDs/alignment, two live city
tail jumps, a 48-byte in-place quarter-case replacement and three dispatch
entries, and three immutable scorebug-only newline-to-space format strings.
The runtime emitter changes only a four-byte play-clock color operand; the
builder also writes two existing descriptor defaults. Native setup/lookup,
missing-name handling, allocations, branch layout and both hook ABIs are
unchanged. No new cave or RX/RW/RO allocation is authorized or required.

The memory-write gate now explicitly proves that the three immutable format
strings retain retail's `.string_` section and `0x26` flags (executable but
non-writable); they are not runtime state or new allocations. The
cave gate checks the complete quarter replacement and its specific existing
targets. Keep both full owner unions and both application orders. Refresh
source pins from final integrated files rather than weakening ownership or
calling an unknown/free-padding region an allocation.
# r64 MyCareer Supersim / draft-start research handoff

Read `ASTRA_MYCAREER_SUPERSIM_DRAFT_REPORT.md` and the derived receipts in
`docs/nfl2k5_supersim_draft_receipts.json` and
`docs/nfl2k5_draft_start_prior_year.json`. The latter proves 268 native fixture
sim/commit pairs and the next-year draft entry with the class intact. This section supersedes the earlier
claims that retail has no live Simulate To End action and that EC65A is the
general played-game commit. **EXPERIMENTAL / UNWITNESSED; live Supersim resume
and a played Senior Bowl career launch are unavailable.** The new modules are
reference/proof components, not installable XBE patches. Neither has `apply()`
or a fake successful patch status. Both have `REQUESTS=()` and
`RUNTIME_READY=False`. Do not enable a Build option from these instruction
proofs. No protected implementation file or parallel `nfl2k5_my_career*` file
was edited in this work.

## Protected integration matrix for this revision

| Integration point | Exact action |
| --- | --- |
| `BuildPlan` fields and presets | No new field is installed. Supersim and draft-start availability remain false in Basic, Advanced **and Experimental**. Preserve the existing `my_career` and `senior_bowl` preflight refusals until their complete native adapters are ready. The two start choices belong in M2's in-game creation flow, not a required host setup file. |
| Dispatcher `_apply_all` tuple / keyword | No tuple entry or keyword for these modules: there is no patch to apply. Do not pass either module to the current patch adapter. Do not extend `R62_SPACE_KEYS`, `R62_RUNTIME_KEYS`, `_selected_space_requests` or `_xbe_space_adapter` for empty research owners. |
| Four status dictionaries | No `applied` status is valid. If availability is exposed later, return `unavailable` and `runtime_ready=False` from the shared `_grown_status_fields`, which expands into all four dictionaries (the current callsites around lines 652, 779, 1757, 2091 of `nfl2k5_throw_tuning.py`). Do not infer runtime availability from `nfl2k5_senior_bowl.status()` reporting its dormant kernel installed. |
| Gameplay Patches `PATCHES` / `NEEDS_IMAGE` | No row now. Reserved future copy: `Retail: off-field plays run normally. Patch: skip until your next return.` and `Retail: rookies enter after a season. Patch: create a prospect and enter the draft.` Use only after those statements are true in the completed integration; append `EXPERIMENTAL / UNWITNESSED`. Both eventual installed features require `NEEDS_IMAGE=True`. |
| Build tab `_option` captions | No option now. Future captions, each under 60 characters: `MyCareer off-field skip (experimental)` and `MyCareer draft start (experimental)`. Keep disabled/unavailable until native readiness; do not label a research kernel as a working Patch. |
| Release allowlist | No research CLI, private fixture or test module should be added to the product. If M2 imports the host contracts, add exactly `mod_editor/core/nfl2k5_supersim.py` and `mod_editor/core/nfl2k5_draft_start.py` to `packaging/release-allowlist.txt`. Importing a reference helper alone does not enable gameplay. |
| Runtime closure | If those imports are adopted, include `mod_editor.core.nfl2k5_supersim` and `mod_editor.core.nfl2k5_draft_start` in `packaging/check_2k5_mod_studio_runtime.py`. Existing dependencies are roster records and Senior Bowl. Never import `tests.nfl2k5_supersim_draft_fixture` or the instruction probe into product runtime. |
| Capability registry | No new product surface or capability entry is required for development-only proof code. Do not publish a live-game capability. The review command is `python3 -m tools.nfl2k5_supersim_draft_probe`; optional long validation adds `--prior-year`. It requires private evidence and Unicorn and is not a portable product backend. |
| Allocator union / manifest | No new owner rows, owner tuples or manifest-builder lists; empty `REQUESTS` consumes no budget. Existing 41-request plan and both gates pass. Do not regenerate protected `data/nfl2k5_cave_reservations.json` for this handoff. A later installed adapter needs real requests, mixed/foreign-byte refusal, idempotent apply/replay, both-order union integration and regenerated manifest through the existing owner workflow. |

## Required Senior Bowl / mode-owner changes before activation

1. **Generic NFL kit v1.** Noah's late instruction overrides the authored 50/51
   defaults. Extend the Senior Bowl settings/event codec to explicitly support
   bank 31, era 0, away A and home H. Default new career events to 31A0/31H0;
   keep existing authored events identifiable when loading old records. Do not
   store 50A0/51H0 and call that generic. Update its preview defaults and Build
   settings serialization together. If a schema change is needed, migrate or
   explicitly refuse old data; do not reinterpret old bytes. Native bank/name
   generation is proved, visual appearance still needs Noah.
2. **Side conversion.** Senior Bowl `Event`/preview order is away=0, home=1;
   native match/sim order is home=0, away=1. Use
   `nfl2k5_draft_start.NATIVE_TO_EVENT_SIDES == (1, 0)` for donor construction,
   scores/stats, controller binding and returned event lines. Do not rename a
   squad or swap only its kit to compensate for incorrect side ownership.
3. **Reservation and persistence.** Reserve a prospect already selected by the
   saved seed at MyPlayer's position; do not replace a selected row afterward.
   Apply creation after the final `2BE940/2BE900/2BE6F0` generator and before
   untouched stage 4. Keep recipe, ordinal/generation, franchise identity and
   once-only phase state in M2's owned career persistence. Integrate its
   existing `inject` / `overwrite_guard`, not a second competing hook at the
   same site. Reject stale class/owned ordinal/later stage. No required external
   setup file or companion is supplied by this revision.
4. **Prior-year bootstrap.** The native route uses `13EE10`, scheduled fixture
   simulation and `247D40/2480B0`, followed by native year/offseason work. Keep
   a temporary native franchise club owner at postseason exit: all-CPU with
   zero user clubs hits the native franchise-exit branch. `C4D30` registers
   that owner; this must not assign MyPlayer to the club. Supply the actual
   menu context in ECX to `2480B0`. Drive progress in bounded batches and save
   an explicit recovery checkpoint. Use current calendar/season getters and
   matched 2026 templates; retail week constants are proof coordinates only.
5. **Launch and return.** Native `61730` clones the two donor teams; full sim
   initialization rebinds their stats and selects personnel. That proves a
   simulated prospect game, not the ordinary live exhibition loader. Prove
   live player/history/coach isolation, lock binding after cloning and every
   return/quit/retry/save path. Intercept the actual played result boundary
   `C5D60` / `C5D99 -> 1356C0` / `134140` as well as visual sim's
   `EC65A -> 1356D0`. Gate both manual `2480B0` and automatic `2486F0`
   Combine advance while the event is pending. Senior Bowl stats belong to
   its event, never the NFL season/career totals.
6. **Draft and UDFA.** Let `325B90`, `325A50`, `325D00` and `325B50` own picks,
   round progression, completion and native contracts. Native auto rookie
   signing is `E60134=1`; negotiation is a separate native path. Native
   `31E430` cleanup puts undrafted players into the FA list. Resolve the actual
   signed club, remove temporary user-club ownership and bind career control
   there exactly once. Preserve an undrafted outcome and offer M2's supported
   UDFA signing flow. The scouting projection has no draft-stock effect yet.
7. **Supersim return.** The native pause action `6EFE0 -> 6EE50 -> 10B980`
   finishes a live game. Never route an off-field skip into it. `10BD80` is a
   scalar scenario restore, not a complete state inverse; `1053B0` zeroes a
   live clock. Close the report's stat/timeout/injury/fatigue/penalty/momentum,
   boundary and play-call re-entry proofs before a runtime `apply()` exists.
   Existing visual sim log/controls can supply the ticker when that adapter is
   ready. Engine acceleration must cover the outer update and timing/audio
   boundary, not multiply the inner dispatcher's delta.

Budget: use the existing Senior Bowl 65,536 RW / MyCareer 4,096 RW allocations
first. A source/coach/stat snapshot and recovery ledger must be counted. The
Unicorn fixture's 2 MiB arena is not a request for Xbox memory. This revision
claims zero additional RX/RW/RO and leaves the 4,096-byte spare RW untouched.


# r64 Team Kit cross-project import handoff

EXPERIMENTAL / UNWITNESSED. The importer, session transaction route, component
receipts, bounded PNG decode cache and FAQ are implemented in unprotected files.
This section is the exact remaining protected GUI/runtime-checker integration.
No protected file was edited. No game patch or executable allocation is involved.

Apply `tests/fixtures/discord_teamkit_import_wiring.patch` to
`mod_editor/gui/studio_qt.py`. `git apply --check` passes. The three dedicated
proposal checks pass, and the full seven-test Team Kit product integration
suite passes with `ASTRA_TEST_TEAMKIT_PROPOSAL=1`, which executes this exact
source in memory. The existing integration doubles accept the added optional
selection argument and both dialog APIs, so that suite also passes before wiring.

The current GUI uses `result.message` for status but hardcodes the old modal
text. The patch gives Team Kit and number sheets the same component receipt:
summary in the panel, the same counts in status and the dialog, and imported,
skipped and overwritten lists in the dialog's expandable Details and the panel
summary tooltip. Each row names the physical set, group and label, so HOME/AWAY
jerseys and Jersey/Helmet/Arm digits cannot be confused. Only `changed_count`
marks the project dirty, triggers recovery and emits the mutation count.

The selected scope is captured before the worker begins. HOME/AWAY/BOTH use the
selected team's exact physical style; SELECTED uses the explicitly selected sets.
The facade forwards `expected_set_selectors` to the service under its existing
lock. Mismatched team, style or sides refuse before any session mutation. The
number-sheet bridge passes its single physical set explicitly and retains the
bugs-2 splitter and layouts unchanged.

The shipped panel has a private-export warning and the global edit-count/status
rows; it does not have a dedicated last-import receipt row. The patch adds one
small summary label under that warning instead of changing the global project
edit count into a per-import count. The label retains the last receipt while
ordinary component refreshes continue showing current Modified/Original state.

Exact GUI patch:

```diff
--- a/mod_editor/gui/studio_qt.py
+++ b/mod_editor/gui/studio_qt.py
@@ -418,7 +418,8 @@
     ) -> object: ...

     def import_team_kit(
-        self, source: Path, progress: ProgressSink
+        self, source: Path, progress: ProgressSink,
+        *, expected_set_selectors: Sequence[str] | None = None,
     ) -> object: ...

     def uniform_colors(
@@ -3181,6 +3182,9 @@
         self.team_kit_warning.setWordWrap(True)
         team_kit_header.addWidget(team_kit_title)
         team_kit_header.addWidget(self.team_kit_warning)
+        self.team_kit_receipt_summary = QLabel("No Team Kit import yet.")
+        self.team_kit_receipt_summary.setWordWrap(True)
+        team_kit_header.addWidget(self.team_kit_receipt_summary)
         team_kit_layout.addLayout(team_kit_header)
         team_kit_scope_note = (
             "All 45 socks, elbow pads, gloves, long sleeves, shoes and wristbands of the "
@@ -6922,9 +6926,40 @@
             blocking=True,
         )

+    def _team_kit_import_selectors(self) -> tuple[str, ...]:
+        uniform_set = self._selected_set
+        if uniform_set is None:
+            raise ValidationError("Choose a team and style before importing a Team Kit.")
+        scope = str(self.team_kit_scope.currentData() or "BOTH")
+        if scope == "SELECTED":
+            return self._selected_uniform_set_selectors()
+        sides = ("HOME", "AWAY") if scope == "BOTH" else (scope,)
+        return tuple(self.uniform_catalog.uniform_set_for(
+            uniform_set.asset_code, side, uniform_set.variant,
+        ).selector for side in sides)
+
+    def _show_team_kit_import_result(self, result: object, title: str) -> None:
+        message = _result_message(result, "Team Kit import complete.")
+        summary = str(getattr(result, "summary", message))
+        details = str(getattr(result, "details", ""))
+        self._set_status(message)
+        self.team_kit_receipt_summary.setText(summary)
+        self.team_kit_receipt_summary.setToolTip(details)
+        box = QMessageBox(self)
+        box.setWindowTitle(title)
+        box.setIcon(QMessageBox.Information)
+        box.setText(message)
+        box.setDetailedText(details)
+        box.exec_()
+
     def _choose_team_kit_import(self) -> None:
         if not bool(getattr(self.facade, "source_ready", False)):
             self._show_error("Load your NFL 2K5 XISO before importing a Team Kit.")
+            return
+        try:
+            expected_selectors = self._team_kit_import_selectors()
+        except ValidationError as exc:
+            self._show_error(str(exc))
             return
         container = str(self.team_kit_container.currentData() or "folder")
         if container == "zip":
@@ -6946,8 +6981,6 @@

         def success(result: object) -> None:
             changed = int(getattr(result, "changed_count", 0))
-            total = int(getattr(result, "asset_count", 0))
-            selectors = tuple(getattr(result, "set_selectors", ()))
             self._set_status(_result_message(
                 result,
                 f"Imported {changed} changed Team Kit components.",
@@ -6959,23 +6992,12 @@
             else:
                 self._refresh_edit_state(rebuild_components=True)
             self.team_kit_imported.emit(changed)
-            QMessageBox.information(
-                self,
-                "Team Kit import complete",
-                (
-                    f"Validated all {total} components for "
-                    f"{', '.join(selectors) or 'the bundled physical set(s)'}.\n\n"
-                    f"{changed} pixel-changed component"
-                    f"{'s were' if changed != 1 else ' was'} staged together as "
-                    "one Undo action.\n\nYour source XISO was not changed."
-                    if changed else
-                    f"Validated all {total} components. Their decoded pixels match "
-                    "the export, so nothing was staged and no Undo action was added."
-                ),
-            )
+            self._show_team_kit_import_result(result, "Team Kit import complete")

         self._start_task(
-            lambda progress: self.facade.import_team_kit(source, progress),
+            lambda progress: self.facade.import_team_kit(
+                source, progress, expected_set_selectors=expected_selectors,
+            ),
             success,
             label="Validating and importing the complete Team Kit",
             blocking=True,
@@ -7043,7 +7065,7 @@
             progress("Splitting the 0–9 sheet", 0, 12)
             outputs = split_digit_sheet(source, targets, orientation=orientation)
             with tempfile.TemporaryDirectory(prefix="2k5-digit-sheet-") as temporary:
-                root = Path(temporary)
+                root = Path(temporary).resolve(strict=True)
                 kit = root / "team-kit"
                 self.facade.export_team_kit_sets(
                     (uniform_set.selector,),
@@ -7084,7 +7106,8 @@
                     )
                 progress("Validating all ten digits as one import", 11, 12)
                 result = self.facade.import_team_kit(
-                    kit, lambda _label, _completed, _total: None
+                    kit, lambda _label, _completed, _total: None,
+                    expected_set_selectors=(uniform_set.selector,),
                 )
             progress("Digit sheet imported", 12, 12)
             return result
@@ -7098,14 +7121,7 @@
             else:
                 self._refresh_edit_state(rebuild_components=True)
             self.team_kit_imported.emit(changed)
-            QMessageBox.information(
-                self,
-                "Digit sheet import complete",
-                f"{label} for {uniform_set.selector} were split into ten exact "
-                f"game slots. {changed} changed digit"
-                f"{'s were' if changed != 1 else ' was'} staged as one Undo action.\n\n"
-                "The source XISO was not changed.",
-            )
+            self._show_team_kit_import_result(result, "Digit sheet import complete")

         self._start_task(
             operation,
```

Protected runtime pins: in
`packaging/check_2k5_mod_studio_runtime.py`, update these two existing entries
of `RC29_AUDIO_ANNOTATION_RUNTIME_PINS` after applying the GUI patch:

```python
    "mod_editor/gui/studio_qt.py":
        "6ae2ba04efe92077acadcdbe20a146cf7495b8a066d35842f32ceb1de42d3352",
    "mod_editor/studio/facade.py":
        "a6423e1455a673cb115f71037a132d6d858ea8d1a39d5d2c923580dd35f77d6d",
```

Those are SHA-256 hashes of the exact proposal and current facade, respectively;
recompute only if integration changes either file further. The existing Team Kit
runtime exercise still uses the same set count, paths, service and private guide.

Other required handoff fields, explicitly reviewed:

- Dispatcher `_apply_all` tuple, kwarg and four status dictionaries: no changes;
  no XBE owner or patch is added. Both executable gates and cave reservations are
  outside this editor-only change.
- BuildPlan field, normalization, deferral and Basic/Advanced/Experimental
  presets: no changes. There is no new build option.
- Gameplay Patches `PATCHES` text / Retail / Patch / `NEEDS_IMAGE`: no row or
  flag is added. This is the existing Team Kit editor operation.
- Build tab `_option` caption: none.
- Allowlist: no new lines. The modified production modules are already listed:
  `mod_editor/core/nfl2k5_asset_io.py`,
  `mod_editor/core/nfl2k5_extended_visual_io.py`,
  `mod_editor/studio/uniform_bundle.py`, `mod_editor/studio/facade.py`, and
  `mod_editor/gui/studio_qt.py`; the FAQ is already allowlisted at
  `docs/mod_editor/discord_bugs_2_faq.md`. Tests and the developer benchmark are
  not runtime files and should not be shipped as product dependencies.
- Runtime-closure imports: no new module names; existing visual IO, bundle and
  facade entries remain. Added OrderedDict, Lock and WeakKeyDictionary are
  standard-library imports. Do not broaden provider ownership for this cache.
- Capability registry: no new capability or changed command; this extends the
  existing uniform/Team Kit operation. Do not edit registry evidence to hide
  the checkout's unrelated missing `docs/research/apf_audio.md`.

Performance: the actual `_populate_components` table method measured 0.002655 s
before and 0.002560 s after at 351 edits (offscreen Qt). No GUI performance patch
is needed from that evidence. The actual save path called by protected
`StudioMainWindow._save_recovery_snapshot` via `Nfl2k5StudioFacade.save_recovery_project`
and `StudioSession.save_shareable_project` repeatedly decoded every original and
replacement. The unprotected IO cache changes a 351-edit save from 23.134902 s to
0.089388 s in the bounded benchmark. Cold open remains 23.4 s. Keep recovery's
source lock, session revision checks, save validation and dirty handling intact.

Validation commands (Linux/macOS use `:` in PYTHONPATH; use `;` on Windows):

```sh
export PYTHONPATH="$PWD:$PWD/tools"
export QT_QPA_PLATFORM=offscreen
python3 tests/mod_editor/test_uniform_bundle_cross_project.py
python3 tests/mod_editor/test_visual_decode_cache.py
python3 tests/mod_editor/test_teamkit_import_wiring.py
ASTRA_TEST_TEAMKIT_PROPOSAL=1 python3 tests/mod_editor/test_team_kit_product_integration.py
```

After applying the fixture to the real source, run the ordinary integration
suite without `ASTRA_TEST_TEAMKIT_PROPOSAL`; that flag applies the still-pending
patch in memory and is only for review on the pre-integration base.
# r64 scorebar v3, 2026-09-07

Read `ASTRA_SCOREBAR_V3_REPORT.md` and `docs/scorebug_ingame/v3/`. The default
static scene is now `espn-broadcast-exact-v3`: the down pill and clock cells
stay requested during plays, and the existing abbreviation callbacks read
retail team primary colors for the two panels. Static text uses retail
FONT4/FONT8. **EXPERIMENTAL / UNWITNESSED.** No runtime owner, allocation,
entry hook, texture lookup or cached team binding was added. The diagnostic
runtime remains off in every preset. These protected changes are a handoff;
they have not been applied in this worktree.

| Protected integration point | Exact action |
| --- | --- |
| Dispatcher `_apply_all` tuple and keyword | Keep the existing static image step. `mod_build.build` passes `scorebug_folder=plan.scorebug_folder or None` through `nfl2k5_scorebug_layout.apply_in_place`, which delegates to the current static writer and its complete XBE transaction. No new tuple entry or keyword belongs in `_apply_all`; `nfl2k5_scorebar_v3` supplies pinned spans to that writer and is not a separate owner with an `apply` method. Retain the existing `(scorebug_runtime, scorebug_runtime_patch, "scorebug_runtime_patch", "experimental scorebug effects")` tuple for explicit diagnostics only. |
| Four status dictionaries | Preserve `scorebug_xbe: scorebug_reference.xbe_status(payload/result/after)` in the XBE read, image read, XBE apply and image apply dictionaries, currently around lines 657, 784, 1767 and 2102 in `nfl2k5_throw_tuning.py`. Preserve their separate `scorebug_runtime` fields and the image resource readers. No new status key. Existing static readers recognize v3 and explicit-folder v10; old default v2 and mixed resources require a clean-source rebuild. |
| `BuildPlan` and presets | Keep `scorebug`, `scorebug_runtime`, and `scorebug_folder`. Basic and Advanced leave `scorebug=False`; Experimental keeps `scorebug=True`. Every preset keeps `scorebug_runtime=False`. Blank folder selects v3; an explicit folder retains the byte-identical v10 contract. No allocator flag, normalization change, extra deferral or final owner pass is needed for static v3. |
| Availability | Include `nfl2k5_scorebar_v3` with the existing static compiler closure when checking or staging `scorebug`. Retain image-only validation and the Hi-res scorebug conflict. |
| Gameplay Patches `PATCHES` and `NEEDS_IMAGE` | Keep the existing `("scorebug", "Experimental ESPN scorebar", r62_ui.SCOREBUG_HELP)` row and `scorebug` in `NEEDS_IMAGE`. Replace the shared help in `mod_editor/gui/beta62_options.py` with the exact copy below; both Build and Gameplay already use it. It contains `Retail` and `Patch`. |
| Build `_option` caption | Keep `Experimental ESPN scorebar` (26 characters), `needs_image=True`, the unwitnessed badge and the optional artwork-folder field. Keep `Scorebug effects (diagnostic only)` off. No new checkbox. |
| Release allowlist | Add exactly `mod_editor/core/nfl2k5_scorebar_v3.py` to `packaging/release-allowlist.txt`. Existing exact, ingame and resources lines stay. Do not ship witness captures, historical compiler fixtures, native proof tools, assembly evidence or test logs as runtime dependencies. |
| Runtime closure imports | Add exactly `mod_editor.core.nfl2k5_scorebar_v3` to the module list in `packaging/check_2k5_mod_studio_runtime.py`. The helper imports only `struct`; no Unicorn, Capstone, Pillow, evidence, retail file or research import enters its runtime closure. |
| Capability registry | No new surface or capability ID. Keep the existing scorebar/template capabilities and their explicit-folder semantics. Update any default-static description from v2/neutral panels to v3/live primary colors and persistent middle. Keep runtime and visual validation unwitnessed; do not promote CPU fixtures to gameplay evidence. |
| Allocator union | No new `REQUESTS`, budget row or allocation. `tests/nfl2k5_allocator_stack.py` now includes the static writer as an explicit adapter in both owner orders, with replay. Runtime's existing dependency may apply static earlier in the reverse order; all final bytes must still agree. |
| Manifest | Regenerate protected `data/nfl2k5_cave_reservations.json` only after integrating the final stack, using the existing `python3 tools/nfl2k5_cave_oracle.py manifest` workflow and disposable-disc disk rules. The builder already traces `nfl2k5_scorebug_ingame.apply_xbe`; its source fingerprint scan automatically includes the new helper. No additions to its `all_requests` or owner lists are required. Confirm that the static owner's complete spans and helper source hash appear, as detailed below. |

Exact replacement for shared `SCOREBUG_HELP`:

```python
SCOREBUG_HELP = (
    "Retail: Uses the original scoreboard. Patch: Uses each team's primary "
    "color with readable white scores and yellow possession highlighting. "
    "The red down box and separate clock cells stay visible through the play "
    "with live values. The play clock shows -- when unavailable. Ball-on "
    "and event labels replace the down text while the clock cells stay visible. "
    "The three timeout marks on each side are decorative. A scorebar folder "
    "selects your painted template. Moves the kick meter up and hides the "
    "lineup strip. EXPERIMENTAL / UNWITNESSED; rebuild from a clean source.")
```

The native visibility replacement is the complete instruction span
`0xFCA87..0xFCCCC` (end exclusive, 581 bytes), inside the existing FC9C0
function. Its two helpers start at `0xFCC1F` and `0xFCCA6`. It is a pinned
function rewrite, not a padding allocation. Keep it whole in the manifest;
retained byte islands do not create external callers. Record the separate
29-byte entries `0xFC010..0xFC02D` and `0xFC030..0xFC04D`, the complete
33-byte `0xFBE30..0xFBE51` formatter, and the existing four-byte material
name pointer at `0xA95CB0`. Exact old/new bytes are in `receipts.json` and
the helper. Both gates retain all retail pointer/branch checks, including
oracle unknowns; their span normalization verifies each full retail and
patched byte sequence before considering displaced internal branches.

The diagnostic scene retains its v2 geometry, private-font layout, loader
hooks and panel appendix. Its collapsed former corner mark now uses the
same `score_buga` name as the shared XBE descriptor. Its HUD pin also changes
for that name and the shared atlas's white tint texel. All probe resource
pins were regenerated from retail slices and checked. This is compatibility
with the shared static layer, not a runtime freeze fix or authorization to
enable the runtime option. The explicit-folder v10 scene, atlas and XBE
remain byte-identical.

# r64 one LB row: remove the Outside Linebackers filter row, 2026-09-07

EXPERIMENTAL / UNWITNESSED. The implementation and both complete XBE gates are
ready. These protected integrations are deliberately handed off, not applied.
See `ASTRA_OLB_ROW_REPORT.md` and `docs/mod_editor/nfl2k5_olb_row_evidence.json`.
No new allocator owner, request, code cave, section, or runtime variable is needed.

## Build ordering and roster compatibility

Keep `BuildPlan.position_pools: bool = False`: BASIC false, ADVANCED true,
EXPERIMENTAL true, as currently shipped. Add the policy field
`position_pools_keep_olb: bool = False` immediately after it, false in all three
presets. This is a compatibility setting for the existing pools feature.
Serialize it with the other Build fields. Require `type(value) is bool` and
permit it only when pools are selected or the source already has complete pools.
It must never enable pools on a retail build by itself.

At `mod_build.build`'s current `if plan.position_pools:` block, keep the early
executable pass before depth rows, but ALWAYS call the idempotent API:

```python
xbe, pools_receipt = pools.apply(_xbe_bytes(target), roster_has_olb=True)
_write_xbe_bytes(target, xbe)
```

Remove the old `state == "applied"` shortcut returning only
`{"already_applied": True}`. `apply` now handles replay and rejects foreign
bytes. The early retained profile safely covers all subsequent roster writers.
Keep the playbook recode and ROST reclassification order/dependencies already
there, including `historic=True`. `roster.apply` now includes `olb_filter_scan`
in its receipt, but this is not sufficient if another ROST writer follows it.

After the LAST ROST mutation (including team names, imports, historic edits,
prospect names and user-authored roster changes), before final read-back,
verification and publication, add the following final pass. Run it when either
`plan.position_pools` is true or pools were already applied on the source.
Resolve `pools` and `roster` locally again so the latter case is covered.

```python
scan = roster.olb_filter_policy(target)  # read-only, one ROST at a time
# Only the literal False from a complete scan certifies absence. Incomplete
# evidence must RESTORE rows even on a previously compacted source.
keep_olb = plan.position_pools_keep_olb or scan["roster_has_olb"] is not False
xbe, filter_receipt = pools.apply(_xbe_bytes(target), roster_has_olb=keep_olb)
_write_xbe_bytes(target, xbe)
receipt["steps"].append({
    "step": "position_pool_filters", "scan": scan,
    "compatibility_override": plan.position_pools_keep_olb,
    "xbe": filter_receipt, "experimental": True, "witnessed": False,
})
```

Retain the exact edit receipts and verify `filter_list_status` against the
chosen policy. A known custom enum-10 player automatically keeps all rows.
A truncated/invalid resource must fail the build; an incomplete valid scan
keeps the rows. Never convert an absent resource or caught scan exception into
`roster_has_olb=False`. The core API's `None` means "unspecified, preserve on
replay"; do NOT pass `None` from an incomplete scan into this final build pass.

External saves are outside a disc scan. A user intending to load an existing
or unscanned custom roster/franchise save must select `position_pools_keep_olb`.
The executable cannot dynamically reintroduce a removed row on save load.
Fresh pooled builds use the scanned, removed profile. Do not advertise automatic
compatibility with later-loaded saves or a query merge of enums 10 and 11.

Keep the existing source-dependent image writers and atomic publication path;
this change adds no disc growth. Both filter policies work before/after SPECIAL
and the full grown owner union. No change to `_selected_space_requests`,
`_xbe_space_adapter`, the allocator budget fixture or the union is needed.

## Dispatcher and all status views

`nfl2k5_throw_tuning._apply_all` remains the XBE-only dispatcher. Its owner tuple
and public kwargs receive NO new pools entry/kwarg: ROST-dependent policy stays
in the two explicit `mod_build` passes above. Keep the existing
`(probowl_order, probowl_order_patch, "probowl_order_patch", "Pro Bowl order")`
entry; the revised Pro Bowl module accepts all four precise table profiles.
Do not apply a removal based on a bare XBE or infer a scan from pools.status.

Import `nfl2k5_position_pools as position_pools_patch` in throw_tuning. Add these
entries to ALL FOUR dictionaries in `read_xbe(payload)`, `read_image(payload)`,
`write_xbe_copy(result)` and `write_image_copy(after)`, using the indicated local
byte variable in each function:

```python
"position_pools": position_pools_patch.status(payload),
"position_pool_filters": position_pools_patch.filter_list_status(payload),
```

For `mod_build.inspect`, add `position_pool_filters: "n/a"` to the default
state dictionary; fill it beside the existing pools status using the same XBE
read, setting both to `foreign` on a parse failure. `retail` for this filter
status means retained rows, `applied` means removed rows, `foreign` means a
partial/unknown table. Pools status still recognizes both complete profiles.
Show these meanings in preview; do not treat retained rows as a broken pool
merge. Add the compatibility flag to the plan's UI persistence/binding maps.
Capability availability uses the existing pools/recode/roster modules plus a
callable `roster.olb_filter_policy` check. No standalone XBE apply button for
this disc-dependent feature.

## Build and Gameplay Patches wording

Change the existing Build `_option` caption to
`Merge positions and remove the empty OLB group` (46 characters), with help:

> Creates EDGE, interior-line and linebacker pools. Removes the Outside
> Linebackers group only after all disc rosters pass the scan. Keeps Fullbacks
> and every other group. EXPERIMENTAL / UNWITNESSED.

Immediately below it, add a dependent `_option` for `position_pools_keep_olb`,
caption `Keep Outside Linebackers for existing saves` (43 characters),
`needs_image=True`, with help:

> Use this if you will load an existing or custom roster or franchise save.
> Keeps the Outside Linebackers group so its players remain selectable.
> New pooled saves can leave this off.

Enable that option when pools are checked or already applied on the source;
include it in plan creation and persistence. A bare XBE remains unavailable.
A preset change resets it to that preset's false default; a user's subsequent
choice must persist into the final pass and its receipt.

Expose the existing pools feature in Gameplay Patches, with this exact PATCHES
row and `NEEDS_IMAGE.add("position_pools")`:

```python
("position_pools", "Merged positions with one Linebackers group (experimental)",
 "Retail: separate outside and inside linebacker groups. Patch: merges the "
 "defensive position pools and removes the Outside Linebackers group when "
 "all disc rosters contain no outside linebackers. Fullbacks remains. "
 "Custom players keep their group. For existing saves, enable Keep Outside "
 "Linebackers in Build. EXPERIMENTAL / UNWITNESSED."),
```

Gameplay Patches must preserve the plan's compatibility flag when it forwards
an existing plan; its fresh plan uses the default false value. Keep the
existing automatic scheme-label and disc dependency handling for pools.

## Packaging, registry and manifest handoff

Existing allowlist lines stay:

```text
mod_editor/core/nfl2k5_position_pools.py
mod_editor/core/nfl2k5_probowl_order.py
mod_editor/core/nfl2k5_practice_squad_screen.py
mod_editor/core/nfl2k5_practice_squad_screen_code.py
tools/nfl2k5_roster_reclassify.py
```

No new runtime file is required. The proof tool, native test fixture, report and
metadata evidence are research/test assets; do not add them to the product
runtime allowlist. In `packaging/check_2k5_mod_studio_runtime.py`'s explicit
import closure, ensure these four imports appear once (Pro Bowl and PS already
do): `mod_editor.core.nfl2k5_position_pools`,
`mod_editor.core.nfl2k5_probowl_order`,
`mod_editor.core.nfl2k5_practice_squad_screen`,
`tools.nfl2k5_roster_reclassify`. No Capstone or Unicorn runtime dependency.
The existing runtime staged synthetic roster fixture can assert an incomplete
scan retains rows; no private fixture is required for packaging.

For the newly exposed Gameplay Patches entry, insert the exact candidate object
from `docs/mod_editor/nfl2k5_olb_row_capability.json` into the protected registry,
sorted by ID. It labels runtime `not-tested`, and its native test command is a
module command. The backend command names the existing ROST writer; XBE policy
application remains part of Build as described above.

Claude regenerates `data/nfl2k5_cave_reservations.json` after the protected build
integration. The recorder already captures this owner and every receipt's full
`after` span: no manifest-builder request list or owner list change is needed.
Its final result must include SIXTEEN declared `position_filter_*` edits under
`nfl2k5_position_pools`, totaling 1,200 bytes, from `filter_list_sites()`.
Only 214 of those data bytes differ. Preserve the existing Pro Bowl ownership
on its exact overlapping 72-byte table at `0x54A254`; this is two composable data
edits, not two allocations. Preserve all existing spans and source freshness
checks. Never classify raw address coincidences or `unknown` as free.

Both gates use a test-only projection in `tests/nfl2k5_allocator_stack.py` until
that regeneration: it pins all retail/installed table bytes and rejects any
other overlapping owner. It does not replace, write or weaken the release
manifest. Run both gates again after protected wiring/regeneration, then Noah's
witness list in the report. No release-tag, CI or update file change is requested.

# r64 ESPN 25th Anniversary scenarios and rosters, 2026-09-07

EXPERIMENTAL / UNWITNESSED. The shipped scope is fixed-25 SITU editing and the
shared historic roster editor. Additional rows are research-only. Do not expose
an install-more-than-25 switch, claim private rosters per moment, or write a
profile. Details and authored JSON/CSV formats are in
`docs/mod_editor/nfl2k5_espn25_authoring.md`; native evidence and the growth
refusal are in `docs/mod_editor/nfl2k5_espn25_research.md`.

**Rosters host, `mod_editor/gui/roster_editor_panel_qt.py` (protected).** Import
`Espn25Panel` from `mod_editor.gui.espn25_panel_qt`; create it as an additional
Rosters subtab captioned `ESPN Anniversary`. Keep the existing live-roster
editor separate. On project-image selection, load
`nfl2k5_espn25_scenarios.Catalog.load(source_path)` in the existing background
worker, then call `panel.set_catalog(catalog)` on the GUI thread. The worker
returns a detached object with no open handles. Surface a layout refusal using
the host's usual error handling and disable the tab until a supported source
loads. Do not discard pending edits during a routine refresh: only replace the
catalog on explicit project change or successful build/reload, using the host's
existing dirty/recovery lifecycle.

The panel supplies a complete roster grid, shared-use acknowledgment, CSV
import/export, scenario JSON load and build-plan save. It uses RosterDocument and
the existing CSV codec. `panel.plan_ready` emits
`{"path": absolute_plan_path, "plan": validated_plan_dict}` after an atomic
save. Connect it to the project/build state as `espn25_plan = payload["path"]`,
mark the project dirty, and persist/recover that project field. Include
`panel.pending`, `panel.scenario_json.toPlainText()` and source identity in the
host's ordinary unsaved-edit recovery snapshot; restore after matching the source
catalog. Preserve the saved plan file when saving a portable project, and resolve
its project-relative path on load. Do not put its before-byte preimages in a
public modpack. Public content is the authoring JSON/CSV.

**Text and Rosters cross-link, `mod_editor/gui/text_rosters_panel.py` (protected).**
Replace `ESPN_25TH_COMING_SOON_NOTE` with:
`"Edit Anniversary setup and shared historic rosters in Rosters > ESPN Anniversary. Experimental and unwitnessed. Extra moments can be validated for research; installation is unavailable."`
Keep the existing four-string editor fixed at 25. If its pending edits also
change SITU, consolidate/re-author the Anniversary plan against that result or
report the conflict before starting the build. Never silently rebase a hashed
plan or let one writer overwrite another's edits.

**BuildPlan and build pass, `mod_editor/core/mod_build.py` (protected).**

- Add `espn25_plan: str = ""` beside `roster_edits`. Empty is disabled. Set `""`
  in **basic, advanced and experimental** presets; user content is never enabled
  automatically. Normalize with the existing project-path handling, require a
  string/path to a bounded readable plan, and reject a bare-XBE build when set.
- In `available()`, set `"espn25_plan"` when
  `_core_module("nfl2k5_espn25_scenarios")` is present. Image probing can use
  `Catalog.load(source)` and report `available` or `foreign`; without a selected
  plan do not call the plan-dependent `status` function. Bare-XBE status is
  `"requires image"`.
- During validation, load the plan exactly once with `read_json`, keep that
  detached value in the normalized build operation, and call
  `resolve_plan(Catalog.load(source), loaded_plan)` before copying. Check any
  other enabled writer for SITU/historic-resource conflicts. Refuse version-18
  roster arena growth with this plan: the current main-wrapper geometry is
  pinned. Reclassification of historic ROSTs is not covered by this editor's
  retail position scheme; refuse a conflicting historic recode rather than
  interpreting its positions as retail.
- Defer application until all other resource/pack relocation passes have
  finished, including music growth and roster passes. On the disposable final
  image, run the following **after final resource relocation and before output
  publication**:

  ```python
  espn = _core_module("nfl2k5_espn25_scenarios")
  progress("Applying ESPN Anniversary edits", 0, 0)
  espn_receipt = espn.apply_to_image(target, loaded_espn25_plan)
  receipt["steps"].append({"step": "espn25_plan", **espn_receipt})
  receipt["result"]["espn25_plan"] = espn.status(target, loaded_espn25_plan)
  ```

  Both preflight and final pass resolve resources through XDVDFS/outer tables,
  not fixed physical offsets. On failure discard the disposable output. The
  result must be `applied`; every resource receipt includes full before/after
  hashes and exact changed spans. Never call `build_image` inside the existing
  build worker, since the worker already owns the disposable copy.

**XBE dispatcher `_apply_all`, kwarg, tuple and four status dictionaries.** No
new entry or kwarg in `nfl2k5_throw_tuning._apply_all`: this feature has no XBE
apply function. No adapter in `_selected_space_requests`/`_xbe_space_adapter`,
no final XBE-owner tuple entry, no `_grown_status_fields` key. Leave the four
XBE-only status dictionaries at the current `_grown_status_fields` expansion
sites (inspect, split inspect, apply receipt, projected apply receipt) unchanged.
Only the image-level Build status/receipt above gains `espn25_plan`. Putting it
into XBE status would falsely assert resource state from executable bytes.
`REQUESTS = ()`; no cave, allocator budget fixture, owner union or manifest
registration is needed. Both existing XBE gates still run forward/reverse and
v3 scale-out forward/reverse as regressions. Do not regenerate cave reservations.

**Gameplay Patches and Build tab (protected).** Add an informational image-only
`PATCHES` row keyed `espn25_plan`, with text:
`"Retail uses 25 moments and shared historic teams. Patch applies your saved Anniversary setup and roster edits. Extra moments remain unavailable. Experimental and unwitnessed."`
Add `espn25_plan` to `NEEDS_IMAGE`. The page action opens the Rosters Anniversary
subtab; it is not a bare Boolean executable patch. If the current PATCHES widget
assumes Boolean options, use the existing content-file control pattern instead
of passing a path through a Boolean dispatcher. Build `_option` caption:
`"Use saved ESPN Anniversary edits"` (31 characters), backed by the selected
plan path and a file picker; checking it requires a validated plan, unchecking
clears `espn25_plan`. Do not enable it through a preset.

**Allowlist, runtime closure and capability registry (protected).** Add exact
allowlist lines:

```text
mod_editor/core/nfl2k5_espn25_scenarios.py
mod_editor/gui/espn25_panel_qt.py
data/nfl2k5_espn25_layout.json
data/nfl2k5_espn25_authoring.schema.json
docs/mod_editor/nfl2k5_espn25_authoring.md
docs/mod_editor/nfl2k5_espn25_research.md
docs/mod_editor/nfl2k5_espn25_capability.json
```

Add `mod_editor.core.nfl2k5_espn25_scenarios` and
`mod_editor.gui.espn25_panel_qt` to the runtime-closure import exercise in
`packaging/check_2k5_mod_studio_runtime.py`. The feature imports the already
shipped roster records and safe-text encoder modules, the existing `_outer_image` provider
`tools/nfl2k5_playbook_position_recode.py`, PyQt5 and standard-library modules.
Verify `data/nfl2k5_espn25_layout.json` is present relative to the installed
repository root; the authoring schema is documentation, while the layout pins
are required at runtime. Do not package tests or private evidence helpers.

Insert the single object from
`docs/mod_editor/nfl2k5_espn25_capability.json` into
`mod_editor/capabilities/registry.v1.json` in lexicographic ID order. It uses `offline-writer-proved`,
`runtime.status = not-tested`, and schema-valid commands:

```text
python3 -m mod_editor.core.nfl2k5_espn25_scenarios build source.iso espn25-plan.json output.iso
python3 -m mod_editor.core.nfl2k5_espn25_scenarios status source.iso espn25-plan.json
```

Run the three standalone ESPN suites, both XBE gates, and the registry and
packaged-runtime checks after integration. Do not describe the currently
unmounted protected-tab integration as shipped UI until those edits land.


# r64 ESPN 25th real rosters, 2026-09-07

Owner: `mod_editor/core/nfl2k5_espn25_rosters.py`. Dataset and row provenance:
`data/nfl2k5_espn25_moment_rosters/manifest.json`. Evidence and Noah's witness list:
`ASTRA_ESPN25_ROSTERS_REPORT.md`. EXPERIMENTAL / UNWITNESSED.

This handoff specifies the protected product edits. The data owner, deterministic
CSV generator, 75-resource inventory, dataset, capability object, standalone
writer/image tests and 25-moment native trace are delivered. The protected Build,
dispatcher, GUI, packaging and registry files are unchanged in this worktree.

## Dispatcher: `mod_editor/core/nfl2k5_throw_tuning.py`

Expose `nfl2k5_espn25_rosters as espn25_rosters_patch` using the same import style
as the existing image resource owners. Add strict Boolean `espn25_rosters=False`
to `write_image_copy`, `write_xbe_copy`, and any public explicit-signature
`write_copy` facade or flag-selection helper. `write_xbe_copy` must reject True
before copying, with "Historic moment rosters need a disc image". False keeps
its ordinary behavior. The facade must carry the keyword to the image path.

**`_apply_all` tuple and keyword decision:** no executable tuple is added.
`apply` here accepts a mapping of 35 complete resource spans; it cannot accept
an XBE. Do not pass this flag to `_apply_all`, `_selected_space_requests` or
`_xbe_space_adapter`, and do not add it to `R62_RUNTIME_KEYS` or `R62_SPACE_KEYS`.
`REQUESTS = ()`; no allocator row, budget row, cave observer, executable digest
repin or reservation-manifest regeneration belongs to this data-only owner.
The generic executable-owner ground rule does not override that API boundary.

Add all four public status fields explicitly:

```python
# read_xbe and write_xbe_copy
"espn25_rosters": "n/a",
# read_image, after resolving its source path
"espn25_rosters": espn25_rosters_patch.image_status(path),
# write_image_copy, after the final resource pass on the private target
"espn25_rosters": espn25_rosters_patch.image_status(target),
```

Use a lazy `_espn25_rosters_image_status` helper, parallel to
`_guardian_image_status`, if necessary to keep executable-only reads lightweight.
Do not put image status in `_grown_status_fields(payload)`: an XBE cannot reveal
archive installation state. States are `retail`, `applied`, `foreign`, with
`n/a` only on the executable-only surfaces. Mixed installs are `foreign`.

When the direct image facade receives True, preflight
`espn25_rosters_patch.apply(espn25_rosters_patch.read_resources(source))` before
copying. On its private target, after the last image-relocation/executable pass,
call `espn25_rosters_patch.apply_to_image(target)`. Include the complete receipt
under `espn25_rosters_patch`, including every relative before/after byte span,
resource hashes, image segment locations, zero growth and `xbe_changed=False`.
The owner resolves actual XDVDFS placement through `OuterImage`; never substitute
hard-coded XISO offsets or write loose source packs. On failure discard the
private target through the existing build transaction.

The Build orchestrator below owns its final resource pass. Pass False to any
earlier image-facade pass in that route, so one Build step records the patch once.
Direct CLI publication is also available:

```sh
python3 -m mod_editor.core.nfl2k5_espn25_rosters build source.iso historic.iso --receipt historic-receipt.json
```

It refuses existing targets, compiles every roster before copying, uses a
temporary sibling copy, closes all handles, verifies reads and publishes with
`os.replace`. The CLI stages its receipt before publishing the image and removes
that receipt on an ordinary image-publication failure. An invalid receipt
directory fails before copying. A process or power loss between the two final
replacements may leave the receipt alone; this is not a two-file atomic commit.
`build_image(..., receipt_path=...)` exposes the same optional receipt path to
Python callers. It keeps at least 100 GiB free.
`apply_to_image` itself is for a caller-owned disposable image, not a source.

## BuildPlan, presets, preflight and final resource pass: `mod_build.py`

Add `espn25_rosters: bool = False` to `BuildPlan`, with strict Boolean validation,
recipe serialization/load, preset mapping, selected-options summary, capability
availability and source-status projection. Add the module to the `_core_module`
availability mapping. Availability must also call `dataset()` so a missing or
changed manifest/CSV disables the row with its concrete error. No network or
private nflverse input is required at runtime; the checked generated CSVs ship.

Set the field False in **softdrink_basic, softdrink_advanced and
softdrink_experimental**. All 25 native selections/imports passed, satisfying the
brief's necessary loading condition, but the stronger release choice is opt-in:
no supplied game lineup exists, 105 role fillers are from other seasons and
1,173 numbers retain an unknown historical value. Do not enable Experimental
merely on the basis of a CPU trace. The report is explicit about this decision.

Keep `wants_xbe_patch()` unchanged. Include this data option wherever Build checks
whether anything is selected, by following `team_names_2026`/`guardian_cap` rather
than coercing a data pass into executable tuning. Normalize no allocator or
runtime dependency. A build selecting only this flag must create a copied disc
and reach the data step while retaining the entire source executable.

Before any large copy:

```python
if type(plan.espn25_rosters) is not bool:
    raise ValueError("espn25_rosters must be boolean")
if plan.espn25_rosters:
    if not is_image:
        raise ValueError("Historic moment rosters need a disc image")
    if plan.position_pools:
        raise ValueError("Historic moment rosters need the retail position layout. Turn off One-pool positions.")
    module = _core_module("nfl2k5_espn25_rosters")
    if module is None:
        raise RuntimeError("Historic moment rosters are unavailable in this build")
    _, roster_preview = module.apply(module.read_resources(source))
    receipt["espn25_rosters_preflight"] = roster_preview
```

The `position_pools` refusal is concrete: the existing
`tools/nfl2k5_roster_reclassify.apply(..., historic=True)` rewrites all 75 historic
position/order spans. That conflicts with this profile's pinned original
position mix. Do not silently use `historic=False`, change this dataset's
positions, force the patch over reclassified resources, or rely on a failed
late copy. Existing reclassified sources already report foreign here.

After the last other image pass and before final verification/publication:

```python
if plan.espn25_rosters:
    progress("Applying historic moment rosters", 0, 0)
    module = _core_module("nfl2k5_espn25_rosters")
    historic_receipt = module.apply_to_image(target)
    receipt["steps"].append({"step": "espn25_rosters", **historic_receipt})
```

Preserve the exact receipt in Build results. Refresh source/status scans with
`image_status(source)` and final checks with `image_status(target)`. A replay
must record zero changed bytes. False must record no step and make no roster
edits. Current-team names, current-player edits and resource relocation can
compose if the historic bindings and main college strings remain the same.

The separate Anniversary editor owns manual shared-roster/scenario plans. A
changed historic target or changed title/date/name/year binding is deliberately
foreign to this shipped recipe. Report that conflict during preview. Require a
clean source or one chosen roster plan; do not silently overwrite a user's
manual roster. Cloning a shared roster requires descriptor/archive growth and
is not part of this option. Historic exhibitions using these same files also
receive the replacement players.

## Shared UI wiring, no new editor panel

In `gameplay_patches_panel_qt.py`, add this PATCHES row and add the key to
`NEEDS_IMAGE`:

```python
("espn25_rosters", "Historic moments: real rosters",
 tt.espn25_rosters_patch.HELP_TEXT)
```

The backend help contains both **Retail** and **Patch**, the precise approximation
notice and EXPERIMENTAL / UNWITNESSED. Route its selection through Build's data
pass and conflict preflight. Include it in checkbox refresh, source availability,
selected-options persistence and writer keyword forwarding. Do not send it to
an executable tuple just because the panel also contains executable patches.

In `build_panel_qt.py`, add the requested row beside the roster options:

```python
self.espn25_rosters_check = self._option(
    g, "espn25_rosters", "Historic moments: real rosters",
    tt.espn25_rosters_patch.HELP_TEXT)
```

The caption is 30 characters, below 60. Connect the existing refresh/preset/
BuildPlan/reset flows. Preserve the opt-in state and explain the position-pool
conflict when both controls are selected. Forward the same key in any shared
selection/recipe flow in `studio_qt.py` and `gameplay_panel_qt.py`. No roster
editor panel is added or changed; the parallel scenario session owns it.

## Packaging, runtime closure and capability registry

Add these exact paths to `packaging/release-allowlist.txt` (no directory glob):

```text
mod_editor/core/nfl2k5_espn25_rosters.py
tools/nfl2k5_espn25_rosters_from_nflverse.py
data/nfl2k5_espn25_moment_rosters/manifest.json
data/nfl2k5_espn25_moment_rosters/h-00-1975-cardinals-3.csv
data/nfl2k5_espn25_moment_rosters/h-03-1990-bills-2.csv
data/nfl2k5_espn25_moment_rosters/h-06-1988-bengals-1.csv
data/nfl2k5_espn25_moment_rosters/h-07-1971-cowboys-4.csv
data/nfl2k5_espn25_moment_rosters/h-07-1977-cowboys-3.csv
data/nfl2k5_espn25_moment_rosters/h-08-1986-broncos-1.csv
data/nfl2k5_espn25_moment_rosters/h-08-1998-broncos-0.csv
data/nfl2k5_espn25_moment_rosters/h-10-1966-packers-3.csv
data/nfl2k5_espn25_moment_rosters/h-10-1996-packers-2.csv
data/nfl2k5_espn25_moment_rosters/h-10-2004-packers-0.csv
data/nfl2k5_espn25_moment_rosters/h-11-1970-colts-5.csv
data/nfl2k5_espn25_moment_rosters/h-13-1969-chiefs-4.csv
data/nfl2k5_espn25_moment_rosters/h-13-1993-chiefs-2.csv
data/nfl2k5_espn25_moment_rosters/h-14-1972-dolphins-4.csv
data/nfl2k5_espn25_moment_rosters/h-14-1984-dolphins-3.csv
data/nfl2k5_espn25_moment_rosters/h-16-2001-patriots-0.csv
data/nfl2k5_espn25_moment_rosters/h-17-1991-saints-4.csv
data/nfl2k5_espn25_moment_rosters/h-18-1990-giants-2.csv
data/nfl2k5_espn25_moment_rosters/h-18-2003-giants-0.csv
data/nfl2k5_espn25_moment_rosters/h-19-1968-jets-4.csv
data/nfl2k5_espn25_moment_rosters/h-20-1967-raiders-1.csv
data/nfl2k5_espn25_moment_rosters/h-20-1976-raiders-0.csv
data/nfl2k5_espn25_moment_rosters/h-20-1983-raiders-0.csv
data/nfl2k5_espn25_moment_rosters/h-21-2004-eagles-0.csv
data/nfl2k5_espn25_moment_rosters/h-22-1975-steelers-1.csv
data/nfl2k5_espn25_moment_rosters/h-23-1999-rams-2.csv
data/nfl2k5_espn25_moment_rosters/h-24-1980-chargers-4.csv
data/nfl2k5_espn25_moment_rosters/h-25-1981-49ers-3.csv
data/nfl2k5_espn25_moment_rosters/h-25-1989-49ers-3.csv
data/nfl2k5_espn25_moment_rosters/h-25-2003-49ers-0.csv
data/nfl2k5_espn25_moment_rosters/h-27-1979-buccaneers-3.csv
data/nfl2k5_espn25_moment_rosters/h-28-1979-oilers-2.csv
data/nfl2k5_espn25_moment_rosters/h-28-1999-titans-0.csv
data/nfl2k5_espn25_moment_rosters/h-29-1982-redskins-2.csv
data/nfl2k5_espn25_moment_rosters/h-30-1986-browns-1.csv
docs/mod_editor/nfl2k5_espn25_rosters_capability.json
ASTRA_ESPN25_ROSTERS_REPORT.md
```

The repository also delivers the full local research inventory and exact native/
resource receipts under `docs/mod_editor/nfl2k5_espn25_*`. Those decoded retail
research artifacts and the raw `inputs/` CSVs do not need to ship in the public
runtime. The exact repository-only receipts are
`docs/mod_editor/nfl2k5_espn25_resource_receipt.json`,
`docs/mod_editor/nfl2k5_espn25_replay_receipt.json`,
`docs/mod_editor/nfl2k5_espn25_image_receipt.json`,
`docs/mod_editor/nfl2k5_espn25_native_receipt.json`, and
`docs/mod_editor/nfl2k5_espn25_acceptance.json`. The image receipt comes from a
bounded synthetic XISO containing the user's resource slices; actual source
locations in the acceptance object are read-only observations, not a full-disc
installation claim. Preserve the nflverse CC-BY-4.0 attribution in the manifest/report; its
license applies to the supplied identities, not the user's retail game files.
Do not bundle binary ROSTs, a retail executable, a save or a disc. Tests and the
native helper are development sources; include only under the existing test
packaging policy. Never ship the brief or scratch contents.

In `packaging/check_2k5_mod_studio_runtime.py`, add the import-closure entry:

```python
"mod_editor.core.nfl2k5_espn25_rosters",
```

Retain already shipped dependencies `nfl2k5_roster_records`, its existing roster/
practice-squad helpers, and tools `nfl2k5_playbook_position_recode`,
`nfl_uniform_color_xiso_direct_patch`, `nfl_outer` and their existing imports.
There is no new third-party runtime dependency. The generator is standard-library
only. Unicorn and Capstone are optional development test dependencies.

Merge the exact object from
`docs/mod_editor/nfl2k5_espn25_rosters_capability.json` into
`mod_editor/capabilities/registry.v1.json`, sort IDs, and run the registry
validator. Classification stays `offline-writer-proved`, runtime `not-tested`,
GUI default False. The full inventory is a repository evidence reference, not a
runtime data dependency. Backend/validation commands use `python3 -m` as required.

The merged 112-capability schema and every new entry's local file/command
reference pass. Full registry file checking in this worktree stops at the
pre-existing missing `docs/research/apf_audio.md`. Run that existing strict check
in the coordinating checkout with its research evidence present; do not relax
the validator or generate substitute evidence.

## Coordinating acceptance

The final standalone roster suite passes 21 tests; the native suite passes one
test covering all 25 moments and 2,650 imported players. They include both
orders with current team/player edits, split-resource image segments, Windows
seek/write fallbacks and handle tracking, receipt/publication failure cleanup,
disk-floor refusal, dataset tamper detection, and before-copy foreign refusal.
The 45-file generator `--check` reproduces the full dataset and both inventories
exactly, using manifest pin
`66ab419ad9fa3388b2749526f57b0d7b5a1d4c631560230dd6635457e97e6406`.

Run the two new standalone suites, generator `--check` when the 45 supplied CSVs
are available, and the existing unchanged XBE gates. Then test the protected
integration: all three presets off; strict booleans; image-only refusal before
copying; position-pool/manual-plan conflicts before copying; a data-only Build;
all four facade status fields; exact replay; mixed/foreign refusal; packaging
with every one of the 35 CSVs; recipe persistence; and ordinary kickoff options
composed with this final image data step. Verify the original source is unchanged
and all non-owned bytes, including XBE, SITU, main ROST and the unused 40 historic
resources, remain identical. These protected integration tests cannot honestly
be reported as passing before the handoff is applied.

The unchanged safety gates passed here: 83 memory-write tests and 99 cave-reference
tests in their existing complete owner unions. This data owner consumes no
executable allocation and does not change either gate or the cave manifest.
Noah's full 25-moment played witness remains required; native import success
alone says nothing about complete formations, rendering, completion or exact
historical starting lineups.

# r64 number-sheet quality: protected integration handoff (2026-09-07)

**EXPERIMENTAL / UNWITNESSED.** This section supersedes the earlier number-sheet
quality and runtime-pin guidance only. Base `76434d6108a25ca7deac0160fb05f717badd7bd0`.
See [ASTRA_NUMBER_SHEET_QUALITY_REPORT.md](ASTRA_NUMBER_SHEET_QUALITY_REPORT.md).
Protected source files and the shared provider registry have not been edited.

Apply the two exact, independently checked fixtures from the repository root:

```sh
git apply --check tests/fixtures/number_sheet_quality_wiring.patch
git apply --check tests/fixtures/number_sheet_quality_runtime.patch
git apply tests/fixtures/number_sheet_quality_wiring.patch
git apply tests/fixtures/number_sheet_quality_runtime.patch
```

The Studio fixture preserves the existing four layouts, physical set/family
selection, frozen ten PNGs, one Team Kit transaction, one Undo, source lock,
component receipts and dirty/refresh events. It adds `preview_digit_sheet` to
`StudioFacade`, and `_review_digit_sheet_preview` to `StudioMainWindow`.
`_choose_digit_sheet_import` first splits and encodes all ten digits in a worker.
It queues review through `_defer_until_blocking_task_finished`, so result delivery
cannot race the worker's later `finished` signal and block the next operation.
Review shows the encoded textures at native preview size in a scroll area, all
saved levels, 24/12-pixel estimated views, light/dark backgrounds and mapping or
palette-fit notes. Cancel or an encoding error stages nothing. Acceptance imports
the already previewed PNG tuple, even if the source PNG is subsequently saved
externally. A changed game-source hash refuses the import. Preview cannot infer
the game's camera LOD, UVs, alpha test, lighting or jersey material.

The runtime fixture contains these exact shared-file edits:

- `packaging/release-allowlist.txt`: add
  `mod_editor/core/nfl2k5_digit_texture.py` and
  `mod_editor/core/nfl2k5_digit_preview.py`. Existing splitter, facade, writer,
  `docs/mod_editor/number_sheets.md` and `docs/mod_editor/discord_bugs_2_faq.md`
  lines remain sufficient. The research renders, report generator and test
  fixtures do not belong in the product runtime.
- `packaging/check_2k5_mod_studio_runtime.py`: add imports
  `mod_editor.core.nfl2k5_digit_texture` and
  `mod_editor.core.nfl2k5_digit_preview` beside the existing splitter import;
  add `mod_editor/core/nfl2k5_digit_texture.py` to
  `REQUIRED_UNIFIED_PROVIDER_CLOSURE`. Update the existing
  `RC29_AUDIO_ANNOTATION_RUNTIME_PINS` hashes for the proposed Studio and the
  modified facade. The fixture holds exact SHA-256 values, tested against the
  files and proposed GUI; recompute if integration makes further changes.
- `mod_editor/core/providers.py`: in
  `Nfl2k5UnifiedVisualProvider.module_pins`, repin
  `tools/nfl_live_numbers_nameplate_png_import.py` and
  `tools/nfl_tset_png_import.py`, and add the new dependency
  `mod_editor/core/nfl2k5_digit_texture.py`. Also repin
  `tools/nfl_tset_png_import.py` in `Nfl2k5ScorebugProvider.module_pins` because
  that provider shares the generic compressor. The default generic palette
  policy and scorebug output are unchanged. Every pin in both proposed
  provider dictionaries is checked by the standalone wiring test. Omitting
  this step would cause the frozen provider bundle to refuse or lack the new
  digit dependency. This registry change is supplied as a fixture, not applied.

Other required integration fields, explicitly reviewed:

| Field | Required change |
| --- | --- |
| Dispatcher `_apply_all` tuple, kwarg, four status dictionaries | None. This changes texture encoding, with no executable patch owner. |
| `_selected_space_requests`, allocator adapter, `_grown_status_fields` | None; no requests, allocations, cave entries or manifest regeneration. |
| `BuildPlan` field, normalization, deferral/final pass | None; existing staged uniform edits use the corrected writer automatically. |
| Basic / Advanced / Experimental presets | No added flag and no preset change. |
| Gameplay Patches `PATCHES` text, Retail / Patch, `NEEDS_IMAGE` | No new row or flag; the existing number-sheet editor action owns this workflow. |
| Build tab `_option` caption (60-character maximum) | No new option or caption. |
| Capability registry | No new capability/command; keep the existing number-sheet/Team Kit surface. Do not alter unrelated missing research evidence. |
| Release tags, CI workflow, reservation manifest | No changes. |

Validation before and after integration (the fixture tests execute proposals
in memory before wiring, and the real source after wiring):

```sh
export PYTHONPATH="$PWD:$PWD/tools"
export QT_QPA_PLATFORM=offscreen
python3 tests/mod_editor/test_number_sheet_quality_wiring.py
python3 tests/mod_editor/test_nfl2k5_digit_sheet_quality.py
python3 tests/mod_editor/test_2k5_bounded_vclz_palette.py
python3 tests/mod_editor/test_nfl2k5_digit_sheet.py
python3 tests/mod_editor/test_team_kit_product_integration.py
python3 tests/mod_editor/test_uniform_bundle_cross_project.py
python3 tests/mod_editor/test_teamkit_import_wiring.py
python3 tests/mod_editor/test_discord_bugs_2_wiring.py
```

The existing Team Kit and bugs-2 wiring fixtures retain their original assertions.
The Team Kit product integration suite now also supports
`ASTRA_TEST_NUMBER_QUALITY_PROPOSAL=1` to execute the entire proposed Studio class
before integration. Its per-slot/atomic-import test supplies preview stubs;
the separate quality wiring suite executes the real review dialog and checks
worker result/finished ordering, cancel, encoding failure and source changes.
Run that proposal mode before wiring, then ordinary mode after wiring.
Run the ordinary release allowlist, literal import closure and staged runtime
gates after applying both fixtures; this branch does not claim a packaged build.
See the report for private-evidence environment variables and exact results.

# r64 roster save to disc, 2026-09-07

EXPERIMENTAL / UNWITNESSED. This exports ordinary
`2k5_mod_studio_roster_edits/v1` against the CURRENT disc; it does not install
an executable owner. The new backend, shared replay capacity/reserve correction,
FAQ and tests are implemented. Protected files remain unchanged on this branch.

Apply the exact Rosters proposal from the repository root:

```sh
git apply --check tests/fixtures/roster_save_to_disc_wiring.patch
git apply tests/fixtures/roster_save_to_disc_wiring.patch
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_roster_save_to_disc_wiring.py
python3 tests/mod_editor/test_roster_save_to_disc.py
```

The patch changes only `mod_editor/gui/roster_editor_panel_qt.py`. It adds
**Use this save's roster on the disc...** below the export row when a save is
open, and the same Tools action (choosing a save file) when a disc is open.
It keeps the loaded document and undo journal intact. The source is the current
signed save including in-session edits; the target is freshly loaded from the
project facade's current disc, falling back to the page's disc or a disc picker.
The result dialog names that disc and output, displays counts, and includes
all skipped identities/reasons and per-team counts in its details.

`save_edits_to(path, *, document=None)` remains the single existing export path.
The optional argument supplies the full comparison instead of the session diff;
canonical JSON matches the receipt's edits SHA-256. The receipt is written
beside it before the export signal is emitted. Existing calls still export
session diffs. Existing `roster_edits_changed` wiring in Studio picks up this
path, checks the Build option and saves project settings. Further save edits
must be exported with the new action again. Tests execute the entire patched
module in memory before wiring, or the wired module afterward; they exercise
real widgets, the signal, file writes, BuildPanel's path and dialog details.

Required protected integration fields:

| Field | Required change |
| --- | --- |
| Dispatcher `_apply_all` tuple + kwarg + four status dicts | None. No XBE owner, hook or new Build operation. |
| `_selected_space_requests`, allocator adapter, `_grown_status_fields`, owner unions | None. No allocation and no cave manifest regeneration. |
| `BuildPlan` field + normalization/deferral/final pass | Reuse existing `roster_edits: str`; no new field or pass. The shared `nfl2k5_roster_records.apply` consumes the generated v1 file. |
| Basic / Advanced / Experimental presets | No change. Explicit file export enables the existing user-selected content path. |
| Gameplay Patches `PATCHES` text + `NEEDS_IMAGE` | No new row. Existing roster edits require an image. Retail: the disc roster. Patch: the user's exported roster changes. |
| Build `_option` caption, <=60 characters | Keep `Include exported Rosters edits` (29 characters). |
| Studio signal | Keep existing `roster_edits_changed` connection; no new signal or Studio edit. |
| Release allowlist | Add the two exact lines below; FAQ is already allowlisted. Do not include tests, patch fixture, brief, report or scratch artifacts in the runtime archive. |
| Runtime closure | Add `mod_editor.core.nfl2k5_roster_save_to_disc` to the `modules` import list in `packaging/check_2k5_mod_studio_runtime.py` beside `mod_editor.core.nfl2k5_roster_records`. Existing records/franchise/arena imports cover the other dependencies; no new tools dependency. |
| Capability registry | Append the exact object from `docs/mod_editor/nfl2k5_roster_save_to_disc_capability.json` to `mod_editor/capabilities/registry.v1.json`, sort/canonicalize through the usual validator. Existing surface `players_rosters`, new ID `nfl2k5.rosters.save_to_disc`, `offline-writer-proved`, runtime `not-tested`. Backend and validation commands use `python3 -m`. |
| Release tags / CI workflow / reservation manifest | No edits. |

Allowlist additions:

```text
mod_editor/core/nfl2k5_roster_save_to_disc.py
docs/mod_editor/nfl2k5_roster_save_to_disc_capability.json
```

The existing allowlisted `docs/mod_editor/discord_bugs_2_faq.md` now answers
seskid's PLAY vs BAKE question. Retain its note that the action requires this
wiring in an older build; it gives an accurate explanation when the button is
absent. No new FAQ path is needed.

The importer explicitly supplies pure depth-order moves because the older
session exporter omits reorder-only entries. Replay uses the same current
`membership_limit()` as the roster codec (65 active pointer slots, reserve
storage deducted, grown 70-total storage, season 53 where applicable), instead
of its stale unconditional 54-player end-state cap. A reserve cannot be moved
through a forged ordinary move entry. Both details ship in core, without a
protected Build modification.

Run the existing roster-record, roster-editor, reserve/franchise, Build core,
Build panel and beta62 Build integration suites after wiring. Run the normal
allowlist, capability and staged runtime closure checks after the protected
integration; this branch does not claim a packaged release or a played result.

## r64 MyCareer mode-2: seedless owner and inline saves

This section supersedes the preceding M1/no-inline-writer handoff. See the
current `ASTRA_MYCAREER_MODE_REPORT.md`. **EXPERIMENTAL / UNWITNESSED; M2 and
M3 acceptance remain incomplete.** The generic owner and build recipe exist;
do not enable a preset or advertise the full playable loop from this commit.
No protected file was edited. The following are concrete integration changes
for Claude, subject to the outstanding acceptance checks in the report.

### Dispatcher and Build

In `mod_editor/core/nfl2k5_throw_tuning.py`, import
`nfl2k5_my_career_mode as my_career_mode_patch` alongside the existing legacy
`my_career_patch`. Retain `_apply_all(..., my_career=False,
my_career_setup=None, ...)` and the tuple
`(my_career, _my_career_adapter(my_career_setup), "my_career_patch",
"MyCareer (experimental)")` after the allocator entry. Change the adapter's
apply method to `my_career_mode_patch.apply(payload)` when `setup is None`;
only an explicit legacy setup calls `my_career_patch.apply(payload, setup=...)`.
Do not blindly redirect the legacy public apply function: old unconfigured
and prepared-save tests intentionally retain their compatibility behavior.
The adapter's status can remain `my_career_patch.status`, which now recognizes
the generic tag and delegates complete validation, including foreign/mixed
refusal. A tag alone is never sufficient validation.

`_selected_space_requests` and `_xbe_space_adapter` retain `my_career` and the
same `REQUESTS`: owner `nfl2k5_my_career`, code 8192, data 4096, alignment 16.
There is no second mode owner and no additional page. `_validate_my_career`
(the setup validation path near the existing `read_setup` call) must validate
a setup only when one is supplied, in preflight and both copy writers.
Normalize, freeze, defer and forward the optional setup consistently through
the final image pass; never install a legacy no-seed template as an interim
step and then attempt to replace it with the incompatible generic template.

All four status dictionaries, executable inspection, image inspection,
executable/copy apply result and copied-image result, retain the `my_career`
key from the exact owner status. `_grown_status_fields` must use that same
dispatch. The `my_career_patch` receipt contains `in_game_mode`,
`inline_save_version`, `save_growth`, code/data capacities, seed/journal counts
and `runtime_witnessed=False`. Surface the format in diagnostic details;
`applied` does not mean a played loop was accepted or a career was created.
Legacy setup plus an already generic executable is an error, never a reseed.

In `mod_editor/core/mod_build.py`, retain `BuildPlan.my_career: bool = False`
and optional `my_career_setup`. Permit a missing setup for the generic format
through validation, freezing, image deferral and the final owner pass. Replace
the old unconditional prepared-save requirement with the format contract
above. **Basic, Advanced and Experimental presets all leave MyCareer false.**
An explicit experimental selection may use the generic owner once acceptance
is finished. Requests for an old project with a setup retain the legacy route.
The normal grown-XBE image writer still owns directory relocation and rollback.

### Gameplay and Build controls

Keep `my_career` in Gameplay Patches `NEEDS_IMAGE`. Replacement `PATCHES` text:
`Retail controls a franchise team. Patch adds an experimental MyCareer entry,
native player creation, team signing, an apartment and inline career saves.
The playable loop is still being verified. Experimental / Unwitnessed.`
Remove the required setup chooser for the generic branch only; keep old projects
clearly labelled as legacy prepared-save careers. Do not describe draft or
Supersim as enabled. The native draft row already displays its next-update notice.

Build tab `_option` caption: `MyCareer: create MyPlayer in the game` (37 chars).
There is no new player-name, college, ordinal, external save or JSON field in
the generic player flow. Studio navigation may keep the existing preparation
panel as a legacy tool; it must not direct generic-mode users to it as a required
step. Shared GUI files were left untouched.

### Runtime closure, capability and manifest

Add these exact release-allowlist lines when merging these source changes;
keep the gameplay controls and all presets off until runtime acceptance:

```text
mod_editor/core/nfl2k5_my_career_mode.py
mod_editor/core/nfl2k5_my_career_mode_code.py
mod_editor/core/nfl2k5_my_career_save.py
docs/mod_editor/nfl2k5_my_career_mode_capabilities.json
```

Retain the existing legacy core/code entries. Add the three dotted imports
`mod_editor.core.nfl2k5_my_career_mode`,
`mod_editor.core.nfl2k5_my_career_mode_code`, and
`mod_editor.core.nfl2k5_my_career_save` to
`packaging/check_2k5_mod_studio_runtime.py`'s closure list. The franchise reader,
roster-record reader and save writer now import the footer codec, so that file
is needed even in a build with the gameplay option disabled. GCC/binutils,
Unicorn, tests, private research and `tools/mycareer_mode` are development
dependencies, never imports of the shipped owner.

Merge the schema-valid fragment
`docs/mod_editor/nfl2k5_my_career_mode_capabilities.json` into the capability
registry in sorted ID order. It describes the new generic format separately
from the legacy preparation workflow, on the existing `mode_state_routing`
surface, with GUI expose/default false and runtime not-tested. Its backend
and validation commands are real dotted modules. This is one allocator owner,
not two installed modes. Full registry file checking currently also reports
unrelated missing baseline research paths; the new fragment's own file and
command closure is tested explicitly.

Regenerate `data/nfl2k5_cave_reservations.json` using the existing cave oracle
after integration. All three manifest-owner lists, the complete allocator
stack and both XBE gates now import the generic owner under the old budget
name. The budget fixture's existing MyCareer rows already equal the real
requests, so they are unchanged. Do not grant any free-space exemption to
the occupied season tail or an unknown cave.

### Generic executable and disc recipes

Run from the repository root; all outputs must be new paths. These recipes
contain no setup file or player name. They build experimental artifacts and
do not certify the uncompleted played-game exit check.

```sh
python3 -m mod_editor.core.nfl2k5_my_career_mode apply \
  '/path/to/retail/default.xbe' '/path/to/output/default.xbe' \
  --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json \
  --receipt '/path/to/output/mycareer-xbe.json'

python3 -m tools.mycareer_mode.build_disc \
  '/path/to/retail.xiso.iso' '/path/to/output/MyCareer.xiso.iso' \
  --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json \
  --receipt '/path/to/output/mycareer-disc.json'
```

The standalone disc recipe streams 4 MiB chunks into a TemporaryDirectory,
uses `nfl2k5_depth_chart_storage.write_image_xbe`, reads the relocated XBE back,
closes handles and uses `os.replace`. It refuses insufficient disk space and
keeps at least 100 GB free on the root drive. Its bounded XDVDFS fixture proves
the neighbouring file survives. Two complete retail-disc copies were verified
with different allocator layouts, and both were deleted before the report.
Both extracted executables cold-loaded both native-created careers into the
apartment. Exact disc/XBE hashes, edits, allocations and cleanup receipts are
in `docs/mod_editor/nfl2k5_my_career_mode_receipt.json`. Reserving the full union
installs only allocator infrastructure
and MyCareer; apply other selected owners through their normal adapters after
the shared union exists. Do not install both MyCareer formats.

### Parallel owner adapters and M3 boundaries

Supersim's read-only branch still has `RUNTIME_READY=False` and `REQUESTS=()`.
The installed generic code exports `mode_unit_present`: no arguments, returns
the validated MyPlayer body VA or zero, preserving the platform callee-saved
register convention. `mode_human(team)` uses ECX and returns EAX 0/1 for native
play-call eligibility. A future Supersim stop adapter may query the presence
routine at the relocated `code_for(code_va, data_va)` label. Require a sealed
owner/version before using that address. Do not write callbacks or pointers
to executable text, persist a body pointer, or equate presence with a proved
live-game resume. Normal-speed native CPU play remains the fallback.

The read-only `astra/r63-franchise-autosave` owner calls native `0x16E3F0` only
after caching a successful native device/name/slot, and respects FPF+0x64.
Its Coach's Desk return callback does not recognize this new apartment. Wire
an explicit shared completion callback after native game result/stat commit,
the MyCareer `settle` call, and full return to the apartment. The MyCareer
settlement hook uses `0xC5D9E`; leave autosave's `0xC5DA9` boundary to that owner.
The generic owner wraps the native postgame event callback at `0x4F1994`:
it executes the full `0xC74E0` first, including native `0xC5DF0` when the game
completed, then returns from Schedule to the owned apartment. Preserve this
order. Do not trim away the franchise postgame parent at Team Select's
REPLACE-Game branch. Abandonment and scene-load failure routes pass bounded
native input/stack tests; the completed played-game path still needs proof.
Never invoke save from a per-frame binder or during game resource teardown.
First-slot selection, failed/cancelled writes, replay suppression and cold
reload must pass together before calling this integrated. Do not invent an
address for M1's proposed `request_after_game(manager, fixture_key)` ABI.

Fable's four PNGs and recipes are read-only at the parallel art worktree. They
have not been assigned a hub-only native resource family here. Do not replace
shared Crib textures or add unproved texture IDs to the executable. M3 still
needs that resource/lifecycle proof, calendar/card tabs/depth/purchase/request
UI, safe weekly transactions and the shared autosave adapter. The remaining
305 bytes before the 17-byte format tag cannot hold the current M3 design; refactor
within 8192/4096 or report the measured shortfall, never consume another owner
or page. No M2_DONE or M3_DONE marker is justified by this delivery.

## r64 MyCareer mode 3: shared completion and actual protected stack

The M2a owner repair supersedes the proposed Auto Save ABI above. Both owners
retain their separate live instructions: MyCareer wraps `0xC5D9E`, executes
native `0x134140`, then settles; Auto Save wraps the following `0xC5DA9`
dirty-marker tail and only queues pending work. Native `0xC74E0` and
`0xC5DF0` still finish the week before `mode_postgame` restores Apartment.

The real shared callable is Auto Save's generated `career_complete` label.
ECX is the native manager, EDX is the owned Apartment descriptor; it preserves
registers, flags and stack. The Apartment's event-6 handler invokes it, after
the full return. It requires an existing pending result, topmost matching
Apartment, no live game scene, idle I/O and two quiet updates. It reuses the
existing cached-device/full-name/type lookup and native `0x16E3F0` attempt.
It never marks a result or runs from the player binder. With Auto Save absent,
the bridge returns without calling anything. The sealed installed Desk
callback at `0x521DCC`, plus the generated difference between `career_complete`
and `desk`, locates the callable across allocator layouts. Do not hard-code
its final VA or invent `request_after_game`.

All 1,027 original Auto Save instruction bytes and their relocations remain
identical. The Apartment entry is appended within that owner's existing RX
reservation. Both owner validators accept only the complete exact companion
installation, including save hooks and whole native context hashes. MyCareer
validates Auto Save on a private copy with its own already-validated hooks and
code restored to retail padding, resealed using the allocator helpers. This
breaks the Practice/music validation cycle without omitting any owner's
context or accepting partially installed bytes.

**Observed checkout correction:** despite the brief's introductory wiring
description, HEAD `a790016` still has the legacy-only `_my_career_adapter.apply`
and `mod_build._r62_kwargs` still requires a prepared setup. Apply the preceding
M2 protected handoff. In particular, `_apply_all` keeps the tuples
`(my_career, _my_career_adapter(my_career_setup), "my_career_patch",
"MyCareer (experimental)")` and
`(franchise_autosave, franchise_autosave_patch, "franchise_autosave_patch",
"Franchise Auto Save (experimental)")` after the allocator, with both flags
included in `_selected_space_requests` and `_xbe_space_adapter`. Dispatch
generic MyCareer when `my_career_setup is None`. The four status dictionaries
and `_grown_status_fields` retain both exact status keys. Do not merge their
receipts or install both MyCareer formats.

Retain `BuildPlan.my_career=False`, optional `my_career_setup`, and
`BuildPlan.franchise_autosave=False`; normalize/defer/finally apply both
selections. MyCareer remains off in Basic, Advanced and Experimental presets.
Auto Save's existing preset installation remains Basic off, Advanced and
Experimental on. Its native default stays Off at this M2a milestone.

Gameplay Patches keeps `my_career` and `franchise_autosave` in `NEEDS_IMAGE`.
MyCareer PATCHES text: `Retail controls a franchise team. Patch adds experimental
MyCareer creation, an Apartment and inline saves. With Auto Save installed and
on, completed results save to the slot chosen by a manual Save or Load.
The played loop remains under verification. Experimental / Unwitnessed.`
Build `_option` caption remains `MyCareer: create MyPlayer in the game`.

Existing release-allowlist entries and runtime-closure imports for
`mod_editor.core.nfl2k5_franchise_autosave` and
`mod_editor.core.nfl2k5_franchise_autosave_code` are required even when only
MyCareer is selected: its host validator and generated-label bridge import
them. Retain all M2 closure entries above. No new capability surface or ID is
introduced; merge the existing fragment by ID instead of appending duplicates.
Regenerate the protected release reservation JSON after integration. The M2a
scratch manifest is review evidence only and does not replace that file.

## r64 MyCareer mode 3 continuation: direct Play and paired disc recipe

This section supersedes the earlier Schedule START route, draft update
promise, 305/257-byte headroom and mode-only generic disc description.
The shipped continuation still has five Apartment rows. Play selects the
first own unplayed fixture explicitly through `C79F0`, then pushes native
postgame parent `4F19E8` and Team Select `51B908`. It does not expose Schedule
game-card actions. A bye/no-current-game notice enters the existing native
week or stage advance. Native result/stat commit, `settle`, Auto Save queue,
postgame return and quiet-Apartment save ordering are unchanged.

Protected dispatcher handoff remains exact: `_apply_all` keeps
`(my_career, _my_career_adapter(my_career_setup), "my_career_patch",
"MyCareer (experimental)")` and the existing Auto Save tuple after the
allocator. The `my_career`/`franchise_autosave` kwargs participate in
`_selected_space_requests`, `_xbe_space_adapter`, both selected owner lists,
normalization/deferral and final image apply. With `my_career_setup is None`,
the adapter calls `nfl2k5_my_career_mode.apply`; explicit legacy setup keeps
the legacy route. Each of the four status dicts (executable inspection,
image inspection, executable/copy apply result, copied-image result) and
`_grown_status_fields` uses both validated owner statuses, with separate
`my_career_patch` and `franchise_autosave_patch` receipts.

Retain `BuildPlan.my_career=False`, optional `my_career_setup`, and
`BuildPlan.franchise_autosave=False`. MyCareer remains off in Basic, Advanced
and Experimental presets. Auto Save installation remains Basic off,
Advanced/Experimental on; its native setting is still respected. The standalone
generic disc recipe now deliberately reserves/installs **both** owners even
with the minimal caller union. Product builds must honor their explicit
selections and show that automatic saving requires Auto Save installed,
enabled and a slot established by successful manual Save/Load. Do not silently
rewrite stored user preferences or claim first-slot automatic creation.

Gameplay `NEEDS_IMAGE` retains both keys. Replacement MyCareer `PATCHES`
text: `Retail controls a franchise team. Patch adds experimental MyCareer
creation, an Apartment and inline saves. Play selects your next game. Off
field, the CPU plays at normal speed. The complete playable loop remains
under verification. Experimental / Unwitnessed.` Do not advertise calendar,
depth editing, purchases, requests, draft, live Supersim or hub art as built.
Build `_option` remains `MyCareer: create MyPlayer in the game` (37 characters).
The draft action now displays `Draft entry is not ready.`

Release allowlist entries remain:

```text
mod_editor/core/nfl2k5_my_career_mode.py
mod_editor/core/nfl2k5_my_career_mode_code.py
mod_editor/core/nfl2k5_my_career_save.py
mod_editor/core/nfl2k5_franchise_autosave.py
mod_editor/core/nfl2k5_franchise_autosave_code.py
docs/mod_editor/nfl2k5_my_career_mode_capabilities.json
```

The runtime closure needs the corresponding five dotted core imports;
the existing capability fragment is merged/replaced by ID and keeps GUI
expose/default false and runtime not-tested. There is no new capability ID
or owner. `tools/mycareer_mode/check_discs.py`, `measure_m3.py`, the candidate
C source, Unicorn and compiler tooling are development-only, not runtime
closure imports or enabled product surfaces.

The generic disc command above now returns a final XBE hash after both
installs, separate Auto Save receipt, and explicit `m3_accepted=False` and
`hub_art_bound=False`. Reserving the complete union still does not install
every other selected patch; normal adapters install those owners. Acceptance
can be reproduced with:

```sh
python3 tools/mycareer_mode/check_discs.py '/path/to/retail.xiso.iso' \
  --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json \
  --receipt '/path/to/new-mode3-disc-check.json'
```

That check deletes each temporary disc, validates two different layouts,
then cold-loads two native-created careers on both bounded executables.
The new public receipts are `docs/nfl2k5_my_career_mode3_disc_receipts.json`.
Claude must regenerate the protected reservation manifest after integration;
the continuation scratch manifest has 10,628 spans / 123 writer calls and
does not replace the protected file.

The installed owner uses 8,118 bytes of RX content plus its 17-byte tag,
leaving 57 bytes in 8,192; RW stays 4,096. The separate capacity probe
`python3 tools/mycareer_mode/measure_m3.py` measures 8,539 required RX bytes
for the current mode plus an uninstalled purchase core, an exact 347-byte
shortfall for that included design. It excludes purchase UI, other M3
screens/transactions, draft/Senior Bowl and drawing. Nine rows also require
1,204 bytes in the current 1,024-byte menu subrange. These are lower-bound
inputs to Claude's reservation/layout decision, not a claim that 347 more
bytes completes M3. The uninstalled `-Oz` alternative in the same receipt
requires 8,443 RX bytes, still 251 bytes over the existing reservation.
No second reservation is taken here. The full off-field
drive matrix and those M3 implementations remain acceptance blockers.

The direct Play/week proof now includes the complete native advance after
the owned game: all 15 remaining fixtures are simulated and committed before
week 1, then Play selects the next own fixture without further simulation.
The final-season test also executes native postseason construction, result
commit and year rollover into a usable Apartment. Earlier result-grid inputs
and the played-engine end signal are declared fixture preconditions; these
are bounded instruction proofs, not gameplay witnesses.

The continuation now also proves complete native CPU choice with the pinned
full PLAY resource, 60 complete frame dispatches with finite actor/model
state, and declared snap/possession/dead-ball boundaries through native
turnover rules and post-play logging. Separate fresh-career tests cover CPU
timeout debit and callback return, halftime/OT boundary return, and native
injury application, backup selection and recovery. Presentation, animation
events and recovery elapsed time are explicit inputs. These do not close
automatic animation-driven snaps, a whole CPU drive, or the combined
off-field/all-position/special-teams matrix. Keep the existing runtime
not-tested and Experimental / Unwitnessed product labels. No M2b or M3
acceptance marker or live Supersim readiness is inferred from these tests.
## r64 read-option final-book pairing (2026-09-08)

This section supersedes the earlier requirement to reuse pack-time PLAY pairs
unchanged at the final executable pass. EXPERIMENTAL / UNWITNESSED. The new
resolver and compiler entry point are implemented. Protected integration is
specified here and in the exact reviewable
`tests/fixtures/read_option_pairing_wiring.patch`; no protected file was edited.

### mod_build.py: exact local sequence and receipts

Apply the three hunks in `tests/fixtures/read_option_pairing_wiring.patch`.
`tests/mod_editor/test_nfl2k5_play_intents_build.py` applies those same hunks to
a copied module, checks their equivalence, and supports an already-wired build.
The retained `spy_pairs` list still collects **both** option and Spy intents.
The only sequence change is at the existing final pairing block:

1. Retain `(compiled.replacement, compiled.report)` at each existing option,
   defense and offense pack pass through `collector=spy_pairs`.
2. Keep every existing resource writer in its current position. In particular,
   pool recoding, kickoff resources, offense packs, depth roles and screen
   timing still execute in their existing order. Resolve at the existing
   pairing block after the `all_requests` calculation, after these writers
   and before the final `_apply_all`.
3. If either runtime is selected, load `_core_module("nfl2k5_play_intents")` and
   require it to be available. Replace the retained local list with:

   ```python
   spy_pairs = resolver.resolve_final_pairs(
       target, spy_pairs, progress=lambda msg: progress(msg, 0, 0))
   ```

4. Compile `read_table, read_receipt` and `spy_table, spy_table_receipt` from
   this resolved list, conditional on their existing flags. Keep the nonzero
   read-count refusal. Remove the old later Spy compilation inside the
   `xbe_space` conditional, since it is now next to the read compilation.
5. Run `_verify_play_intents(target, spy_pairs)` against the **resolved** final
   pairs after both selected tables compile. Keep the verifier's complete
   resource equality check. Refusal still occurs before either table installs.
6. Add top-level `receipt["play_intents_final"]` from
   `resolver.resolution_receipt(spy_pairs)`, extended with `read_option_count`
   and `qb_spy_count` from the selected table receipts, or zero when off.
   Include this same object in the final `xbe_space` step. Continue passing
   `read_option_intent_table=read_table` and `qb_spy_intent_table=spy_table` to
   the existing final `_apply_all`; retain both existing table receipts there.

`read_option_preflight` remains the initial preview receipt against the source
and selected packs. It is not evidence about final bytes and is not overwritten.
The final receipt provides `resolved_books`, `resolved_plays`, per-book final
SHA-256, retained SHA-256, old/final indices, names and exact node/descriptor
equality. Native speed options count as resolved authored plays, but do not
count as runtime reads: the shipped pack resolves **8 plays, 1 book, 2 reads**.
The shipped option pack authors no Spy assignment, so adding `qb_spy=True`
installs its native runtime with an authored-Spy count of zero. The nonempty
Spy final-pair path is separately tested with an authored ATL MLB Spy.

The patch adds `receipt["play_intents_summary"]` with this exact text for the
shipped read pack (the two counts are substituted from the final receipts):

> Final playbooks paired: 2 read option plays, 0 QB spy assignments. EXPERIMENTAL / UNWITNESSED.

In protected `mod_editor/gui/build_panel_qt.py`, inside `_done`, immediately
after `title, message = completion(receipt)`, append the summary when present:

```python
if receipt.get("play_intents_summary"):
    message += "\n\n" + receipt["play_intents_summary"]
```

That puts the same measured counts in the existing status label and completion
dialog. The core build patch does not depend on the GUI edit.

### Compiler contract and the position-pool discovery

The existing compiler also refuses pooled defense personnel, independently of
the stale-resource check. `nfl2k5_playbook_pack.recompile_final_intents` accepts
the final resource and self-donor intent requests, decodes every selected final
play, runs the existing synchronization/retail validators, and uses the real
formation/play and personnel compilers to reproduce the final resource exactly.
For native defense checks only, it constructs a personnel view from retained
native codes. The existing pool and depth-role writers must reproduce the
complete final resource from that view. Unknown transformations refuse.
Names, flags, descriptors, pointers and node bytes are identical in both views.
The native compiler's report is retained separately as validation provenance;
it is never passed off as the final compiler report by replacing its hash.

The new versioned final report is produced from the final bytes. Both runtime
table entry points repeat the compilation and compare the entire final report
before using its certified native fixture view. Table identity hashes and
capacity remain unchanged. Table receipts identify the installed final resource.
The native authoring APIs still reject recoded donors outside this explicit,
verified translation path. No global validator or fingerprint set is patched.

### Existing dispatcher, flags, presets and user-facing options

No new owner, allocation, runtime flag or capability surface is introduced.
Keep the existing `_selected_space_requests` and `_xbe_space_adapter` flags
and both final dispatcher entries after allocator installation:

```python
(qb_spy, _qb_spy_adapter(qb_spy_intent_table), "qb_spy_patch",
 "QB spy for zone, man and rush (experimental)"),
(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
```

Keep kwargs `qb_spy=False`, `qb_spy_intent_table=None`,
`read_option_runtime=False`, `read_option_intent_table=None`, their validation,
and first-pass deferral. The four status dictionaries in `read_xbe`,
`read_image`, `write_xbe_copy` and `write_image_copy` already include
`_grown_status_fields`; retain `qb_spy`, `read_option_runtime` and
`read_option_runtime_settings` there. The report-only compiler change creates
no new status key in these dictionaries.

Keep BuildPlan fields `read_option_runtime: bool = False` and
`qb_spy: bool = False`. Basic, Advanced and Experimental keep both **off**;
acceptance explicitly selects them after applying the Experimental preset.
Keep the existing Gameplay Patches rows and NEEDS_IMAGE membership, including
the read option row supplied through `beta62_options`. Their existing help
strings already contain **Retail** and **Patch** and retain the controls and
EXPERIMENTAL / UNWITNESSED label. Build `_option` captions remain:

- `Read option mesh controls (experimental)` (40 characters).
- `QB spy for zone, man and rush (experimental)` (44 characters).

The existing registry IDs `nfl2k5.gameplay.read_option_runtime` and
`nfl2k5.gameplay.qb_spy` retain their surfaces and commands. No new registry
object is needed for an internal final-book resolver.

### Packaging and manifest handoff

Add exactly this line to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_play_intents.py
```

Add exactly this import to the runtime-closure import list in protected
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_play_intents",
```

The pack, formation/play writer, depth roles, role helpers, library, runtime
modules and `nfl2k5_playbook_position_recode` already belong to that closure.
Keep their existing allowlist/import rows. No allocator budget, owner union or
cave span changes. Claude must regenerate the protected reservation manifest
after integration, including the already-stale ESPN source pin and the changed
host compiler/runtime source fingerprints. This branch never refreshes pins
to make a stale manifest appear current.

### Acceptance and witness boundary

```sh
python3 tests/mod_editor/test_nfl2k5_play_intents.py
NFL2K5_PAIRING_REAL_BUILD=1 python3 tests/mod_editor/test_nfl2k5_play_intents_build.py -v
```

The second command retains the exact patched module in
`.scratch/read-option-pairing/mod_build.py`, logs disk refusals/receipts, and
uses a resolved `TemporaryDirectory` for each real image. Its preflight keeps
100 GB free after two output copies and a 512 MB growth margin. A skipped real
build is **not** a successful acceptance build. See the pairing report for the
observed disk refusal and the passing bounded retail-resource/XBE proof.

The shipped `SD Zone Read EXPERIMENTAL` and `SD RPO EXPERIMENTAL` are in **MIN,
I Jokers**, indices 155 and 157. They are not Shotgun plays. The separate
existing Shotgun recipes are **MIN, Gun: Doubles Right**, `SD Gun Zone Read`
(134) and `SD Gun RPO Slant` (31); the new resolver tests also prove these
through both personnel passes. Do not describe the shipped pack as placing
its two names in Shotgun. Noah's controls remain hold snap to keep, release
during the mesh window to give, and a receiver press during the RPO mesh.
## r64 scorebar rim, 2026-09-08

EXPERIMENTAL / UNWITNESSED. Integrate `ASTRA_SCOREBAR_RIM_REPORT.md` and its
reviewed commit/bundle. This extends the existing static v3 writer. There is
no new executable owner, allocator request, entry hook, cached team pointer,
resource lookup, artwork-folder schema or product option.

| Integration point | Concrete final action |
| --- | --- |
| Dispatcher `_apply_all` tuple and kwarg | No new tuple entry or kwarg. Retain the existing static image writer and forwarding of `scorebug_folder=plan.scorebug_folder or None`. Keep the existing diagnostic runtime tuple and `scorebug_runtime_patch` kwarg separate and off in presets. The color helper supplies spans to `nfl2k5_scorebug_ingame.apply_xbe`; it is not another dispatcher owner. |
| Four status dictionaries | Keep `scorebug_xbe: scorebug_reference.xbe_status(...)` in XBE inspection, image inspection, XBE apply result and image apply result (`payload`, image XBE, `result`, `after` respectively). Keep resource inspection and the separate `scorebug_runtime` fields. No new key. The current exact bytes recognize rim-v3 and explicit-folder v10; the previous v3 bytes now refuse and require a clean-source rebuild. |
| `BuildPlan` and presets | Keep `scorebug`, `scorebug_folder`, `scorebug_runtime`. Basic and Advanced keep static scorebug off; Experimental keeps it on. All three presets keep runtime effects off. Blank folder selects the rim revision; an explicit folder keeps v10 byte for byte. No new normalization, allocator, deferral or final-pass fields. |
| Gameplay Patches `PATCHES` and `NEEDS_IMAGE` | Retain `("scorebug", "Experimental ESPN scorebar", r62_ui.SCOREBUG_HELP)` and membership of `scorebug` in `NEEDS_IMAGE`. Replace only the existing shared `SCOREBUG_HELP` text in `mod_editor/gui/beta62_options.py` with the copy below. |
| Build `_option` caption | Keep `Experimental ESPN scorebar` (26 characters), `needs_image=True`, the experimental badge and optional artwork-folder field. Keep diagnostic effects off. |
| Release allowlist | No new lines. Existing lines for `mod_editor/core/nfl2k5_scorebar_v3.py`, `mod_editor/core/nfl2k5_scorebug_exact.py`, `mod_editor/core/nfl2k5_scorebug_resources.py`, `mod_editor/core/nfl2k5_scorebug_ingame.py`, `mod_editor/core/nfl2k5_scorebug_template.py` and the template README continue to cover the runtime changes. Proof tools, assembly, screenshots, test fixtures and report JSON are development evidence, not new runtime dependencies. |
| Runtime-closure imports | No new imports to add. Retain `mod_editor.core.nfl2k5_scorebar_v3`, `mod_editor.core.nfl2k5_scorebug_exact`, `mod_editor.core.nfl2k5_scorebug_resources`, `mod_editor.core.nfl2k5_scorebug_ingame` and `mod_editor.core.nfl2k5_scorebug_template` in the existing closure. The new native callback bytes need no host assembler, native CPU fixture, Pillow import in the callback helper, or proof-file access. |
| Capability registry | No new surface or entry. Existing scorebar/template IDs keep their commands and explicit-folder semantics. Describe the blank-folder default as live team panels and outlines, with neutral centre/marks and silver fallback. Keep this revision unwitnessed. |
| Protected cave manifest | Claude must regenerate `data/nfl2k5_cave_reservations.json` after the final combined stack, using the existing manifest workflow. The complete owned `FCA87..FCCCC` span remains 581 bytes; `FC285..FC288` and `FC305..FC308` are new three-byte rewrites of existing material visibility instructions. The existing trace owner and source scan already include these modules; no union owner list or budget fixture addition is needed. Do not classify either instruction as a cave. |

Exact shared help text:

```python
SCOREBUG_HELP = (
    "Retail keeps the game's original scorebar. Patch adds the experimental "
    "ESPN bar with live team panels and outlines. Each outline uses a team "
    "colour that differs from its panel, or silver when no suitable colour "
    "is available. The centre and decorative timeout marks stay neutral. "
    "The down box and clocks stay through the play. A blank artwork folder "
    "selects this bar; an explicit folder keeps the v10 artwork layout. "
    "This outline revision is unwitnessed. Rebuild from a clean source."
)
```

The installed rim was generated in `nfl2k5_scorebug_exact.atlas`, not painted
in the shipped v10 PNG layers. Its own white mask now occupies an unused
part of the same atlas. Therefore no PNG split, template schema change,
catalog change, Scorebar Studio panel change or release PNG-pin change is
needed. The explicit-folder output pins remain unchanged.

The companion resources metadata was updated only for exact generated
static scene/atlas identities and the diagnostic HUD digest containing the
same atlas. No protected file was changed. The diagnostic scene, fonts,
appendix, hooks and activation policy are unchanged; this does not assert
that the historical runtime freeze is fixed.
# r64 kickoff v6, 2026-09-08

EXPERIMENTAL / UNWITNESSED correction of the existing `dynamic_kickoff`.
See `ASTRA_KICKOFF_V6_REPORT.md` and `docs/nfl2k5_kickoff_v6_receipts.json`.
Noah's positive v5 stance/blocking witness remains valid; the new native
kneel and commentary correction still requires his three-situation witness.

V6 uses **1,939/1,939 RX bytes, 10 RW bytes, twenty hooks**. It fits the
existing legacy reservation `0x2890F0..0x289883` and compiles identically for
the existing relocated allocation. Retain `REQUESTS` code 1939/alignment 16
and data 10/alignment 4; no union budget, owner, page or state expansion.
The RW ranges remain `0xA69969..0xA69970` and `0xA69971..0xA69974`.
All nineteen v5 live spans and pins listed above remain; add:

| Hook | Half-open span | Retail bytes | Displaced behavior |
| --- | --- | --- | --- |
| `commentary` | `0xA7930..0xA7935` | `e9bb181400` | JMP to native `0x1E91F0`, one stack argument |

The hook defers the native per-frame catch/clear-lane producer for an active
normal kickoff whose ball is still in the receiving end zone and has never
entered the field under possession. It also guards the post-whistle pending
catch path. Separate native kneel, touchback and possession producers remain.
The native next-play commentary reset clears the pending contact. A caught
CPU touchback uses `2EE090`, the retail kneel clip and its timed event; an
uncaught kick grounded in the end zone ends by rule at the contact callback.

**Protected manifest work for Claude:** regenerate
`data/nfl2k5_cave_reservations.json` with the existing
`python3 tools/nfl2k5_cave_oracle.py manifest` workflow after integration.
Record the new live span, new installed cave/jump bytes and source hashes.
The builder already includes this owner in its request union and all owner
lists, so no builder-list change is needed. The test-only union projection
now checks the new thunk's exact retail bytes, installed jump and overlapping
owners before reserving its five bytes. It does not write a product manifest.
The current source audit finds three stale pins: this changed kickoff owner,
and **both** `nfl2k5_espn25_scenarios.py` and `nfl2k5_roster_records.py` on the
unchanged base. Both latter files were compared byte-for-byte with HEAD.
The stock oracle correctly refuses until regeneration; do not weaken it.
The existing kickoff hash in `providers.py` is refreshed in this change to
`0f2a618ce8ad2443a472145fa69a7d06e0f78af1e9f7ce211ed9b35b00e6a6e7`.
The relocated module's source is unchanged.

Dispatcher `_apply_all`: retain
`(dynamic_kickoff, _dynamic_kickoff_adapter(dynamic_kickoff_settings),
"dynamic_kickoff_patch", "dynamic-kickoff")` and the post-allocator tuple
`(kickoff_relocated, kickoff_relocated_patch, "kickoff_relocated_patch",
"experimental relocated kickoff")`. Keep kwargs `dynamic_kickoff`,
`dynamic_kickoff_settings`, `kickoff_relocated`, `_selected_space_requests`,
`_xbe_space_adapter` and deferred final application. The **four status dicts**
(file inspection, image inspection, file patch result, image patch result)
keep `dynamic_kickoff`, `dynamic_kickoff_settings`, `kickoff_relocated` and
`kickoff_relocated_settings` using their existing status/read-settings calls.
The corrected owner is already reached through those paths.

`BuildPlan` keeps the existing `dynamic_kickoff: bool`,
`dynamic_kickoff_settings` and `kickoff_relocated` fields, normalization and
deferral. Basic and Advanced leave dynamic kickoff off; Experimental enables
it. Relocation remains off in all three defaults and implies dynamic kickoff
and the allocator when selected. No new option or capability surface.

Gameplay Patches `PATCHES`: keep the `dynamic_kickoff` key and role/landing
rules; add this presentation explanation to its existing detail text:
"Retail: the returner can take a knee before the touchback whistle. Patch:
keeps the native knee animation and waits for it before ending a caught
touchback; suppresses return commentary while the ball stays in the end zone.
Experimental; this correction has not been played yet."
Keep `dynamic_kickoff` and `kickoff_relocated` in `NEEDS_IMAGE`, and preserve
the existing relocation text containing "Retail" and "Patch".
Suggested Build tab `_option` caption is
`Dynamic kickoff: ready stance, blocks and touchbacks` (52 characters), with
`needs_image=True` and the correction's unwitnessed status. No GUI files were
edited here. Avoid describing the whole v5 stance/blocking feature as newly
witnessed or newly failing based on this bounded CPU replay.

Allowlist lines remain `mod_editor/core/nfl2k5_dynamic_kickoff.py` and
`mod_editor/core/nfl2k5_dynamic_kickoff_relocated.py`. Runtime-closure imports
remain `mod_editor.core.nfl2k5_dynamic_kickoff` and
`mod_editor.core.nfl2k5_dynamic_kickoff_relocated`; no new runtime dependency.
Existing capability registry entries suffice. Keep kickoff alignment and
36-book return blocking in their current build order. Rebuild from supported
retail input: all v1 through v5 legacy/grown executables and mixed new hooks
are refused before mutation, rather than partially upgraded.

## R64: independent glove and shoe texture chains

Owner: `ASTRA_EQUIPMENT_TEXTURE_CHAIN_REPORT.md`. **EXPERIMENTAL /
UNWITNESSED**. The owned writer, three core helpers, dialog, facade method,
project transport and tests are implemented. The original-size independent
chains did not fit the sampled retail slots. The positive retail proof uses
an explicit 64 x 64 shoe image with all four levels. Do not present this as a
universal native-size importer or a played result.

### Protected Studio integration

Apply the exact fixture only after reviewing it against the combined stack:

```sh
git apply --check tests/fixtures/equipment_texture_chain_wiring.patch
git apply tests/fixtures/equipment_texture_chain_wiring.patch
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_equipment_import_wiring.py
QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_nfl2k5_equipment_import.py
```

The fixture edits only `mod_editor/gui/studio_qt.py`. Before integration the
wiring test applies the complete diff in memory, compiles the complete proposed
module, and executes the actual proposed `_replace_visual_asset` method. After
integration it executes the shipped method. No protected panel was changed in
this worktree.

Add this facade protocol signature alongside `replace_asset`:

```python
def replace_equipment_texture(
    self, asset: object, supplied_png: Path, progress: ProgressSink, *,
    independent: bool = False, scale: int = 1,
) -> object: ...
```

In `_replace_visual_asset`, after a successful `_fit_for_slot` and before
preparing a full-resolution authoring master, open
`mod_editor.gui.equipment_texture_import_dialog.EquipmentTextureImportDialog`
for `asset.kind == "uniform_equipment_texture"`. Return on cancellation.
Capture `dialog.independent` and `dialog.scale` on the GUI thread. Its own
`Accepted` constant avoids adding an undeclared global `QDialog` reference.
The existing fitted PNG, not the original mismatched image, goes to
`facade.replace_equipment_texture(..., independent=..., scale=...)` inside
`_start_task`; all other textures retain `facade.replace_asset`.

The checkbox is exactly **Give this glove or shoe its own texture** (39
characters). It starts unchecked. The size chooser starts at the original
catalog size and offers original, half or quarter width/height; it is enabled
only for the checked, reviewed glove/shoe families. The PNG stays at its
catalog dimensions; the writer derives the selected smaller base and all
remaining mips. The dialog explains lost fine detail, additional game memory,
separate dirty variants, compression refusal and the unwitnessed status.

Use the result's `message`, `modified` and `changed_asset_ids`. On replay
(`changed_asset_ids == ()`), delete only a newly prepared pending authoring
master, retain the previous master, show the result message and return without
marking the workspace dirty. Existing failure cleanup removes the pending
master after preflight failure. Accepted changes keep the existing preview,
filter and authoring-master flow. The current editing preview shows the
full-size authored PNG; generated build previews show the actual quantized,
encoded base. The result message states the selected game dimensions and
whether colours were approximated.

Team Kit's equipment browser and All Textures share this visual import route,
including file selection and drag/drop. Any future Rosters texture picker
must call this same method/service rather than bypassing the preflight. The
current Rosters equipment type/colour fields do not import PNGs and require no
panel change. No unrelated GUI panel is part of this handoff.

### Required dispatcher and Build fields

| Required integration field | Decision |
| --- | --- |
| `_apply_all` dispatcher tuple | N/A. This is a grouped `uniform_equipment_texture` resource edit through the existing unified visual provider, not an XBE patch owner. Add no tuple entry. |
| Dispatcher kwarg | N/A. Mode and scale travel inside the frozen authored PNG; add no global build flag. |
| Four dispatcher status dictionaries | N/A for all four. There is no executable byte status for this data edit; exact before/after span hashes remain in the existing physical edit receipt. |
| `_selected_space_requests`, `_xbe_space_adapter`, `_grown_status_fields`, allocator union and manifest owner lists | No changes. No RX/RW/RO allocation, `REQUESTS`, cave or XBE mutation. |
| `BuildPlan` field | No new field. Existing visual project assets carry this edit. |
| Basic / Advanced / Experimental presets | None enable it automatically. All retain palette-only import by default; the user explicitly chooses the new mode per variant. |
| Normalization, deferral and final Build pass | No new normalization or pass. Existing one-span grouping and source-bound visual compiler perform the write. |
| Gameplay Patches `PATCHES` text and `NEEDS_IMAGE` | No new row or set member. Retail: named equipment shares image indices and distance copies. Patch: the explicitly selected glove or shoe gets its own image and distance copies inside the original compressed file span. This belongs to texture import, not a gameplay toggle. |
| Build tab `_option` caption, <=60 characters | No new `_option`. The owned import checkbox caption above is 39 characters. |
| Capability registry | Existing `nfl2k5.textures.all_p8` and `nfl2k5.uniforms.all_visual` constraints/evidence were updated in place. No new surface or ID; runtime status was not promoted. |
| Cave reservations, release tags, update checker and CI workflow | Do not change for this feature. Claude alone resolves the base's stale ESPN 25 reservation source when regenerating the combined protected manifest. |

### Protected release allowlist and runtime checker

Add these exact lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_equipment_import.py
mod_editor/core/nfl2k5_equipment_import_intent.py
mod_editor/core/nfl2k5_equipment_lz.py
mod_editor/gui/equipment_texture_import_dialog.py
mod_editor/data/nfl2k5_equipment_chain_pins.v1.json
```

Existing allowlisted writer, digit encoder, extended visual IO, session,
project archive, facade, provider and unified project tool remain required.
The census tool, proof fixture, tests, patch fixture, report, brief and scratch
artifacts are development evidence; they need no runtime allowlist entries.
No executable or retail texture bytes are in the new JSON catalog.

In `packaging/check_2k5_mod_studio_runtime.py`, add these exact dotted names to
the existing runtime `modules` import list alongside the digit/equipment code:

```python
"mod_editor.core.nfl2k5_equipment_import",
"mod_editor.core.nfl2k5_equipment_import_intent",
"mod_editor.core.nfl2k5_equipment_lz",
"mod_editor.gui.equipment_texture_import_dialog",
```

Add the following two paths to `REQUIRED_UNIFIED_PROVIDER_CLOSURE`:

```python
"mod_editor/core/nfl2k5_equipment_import_intent.py",
"mod_editor/core/nfl2k5_equipment_lz.py",
```

`Nfl2k5UnifiedVisualProvider` already pins these two execution dependencies,
all changed existing execution dependencies, and the new hash catalog. The
strict closure expectation is updated from 235 to 237 modules in
`test_provider_integrity.py`. The GUI service and dialog are runtime imports,
not backend execution dependencies; do not add unrelated GUI modules to the
sealed compiler closure.

Require the staged catalog at
`mod_editor/data/nfl2k5_equipment_chain_pins.v1.json`, exactly 145,141 bytes,
SHA-256 `cb15ecd9ef3f87f45c3cfc4a7fc583636b236835fbbedec073c50dc45706b0bc`,
and confirm 1,902 rows. The existing provider data-pin validation also checks
it before executing a build.

Update the following entries in `RC29_AUDIO_ANNOTATION_RUNTIME_PINS` to the
combined final file hashes. These are the exact hashes from this branch:

| Path | SHA-256 |
| --- | --- |
| `mod_editor/studio/facade.py` | `fa81aff426da2a3556f7e5435598cfc1cf005e7ef65b1eb99609e63d9d29a04c` |
| `mod_editor/studio/session.py` | `731b5f757d13ceebea0eb6b37dc9380cd0e1d9a29de1e02c136303a5d68df5f0` |
| `mod_editor/studio/project_archive.py` | `3556062a7cf178ef416706543e71270783d04439494420810fb7a10ca7f01479` |
| `mod_editor/gui/studio_qt.py`, after this exact fixture on this base | `9aef38f0dfcd7a43a0298b9bea43798f1a416437f28fde75db2513c82d6796f6` |

If another landing also changes these files, recompute their hashes after
combining the changes. Do not copy this branch's proposed Studio hash onto a
different merged panel. The other pinned Audio files are unchanged by this
feature. The protected checker was not edited or treated as an already-green
packaged release check here.

For execution-pin review, the updated writer is
`188bb18fc44d49f050cca11891652bdca7e44dea9c64c4df5996a5bb8d9bb06c`,
the intent helper is
`ef50b20ff389b0067046c53eb62fc254a3c1319eedd7eb1a8d1aaba8f2cfb8c4`,
the lossless compression helper is
`c09e5a518177c4b473f71ca0f14a2562d8c0ca1e322f2bab0c32a5cf46350571`,
and `tools/nfl2k5_visual_mod_project.py` is
`f6c578880cdfcf3a4c01e9a4458651db8a2e869a89632f40f67c5c49d5a47997`.
Both the backend hash and its duplicated module-pin entry have been updated.

After wiring, run the four new standalone suites, existing equipment/export,
Studio/Team Kit, provider integrity, capability and staged-runtime release
checks. Both XBE composition gates already pass on this branch. The oracle's
only failure is the brief's expected stale
`mod_editor/core/nfl2k5_espn25_scenarios.py` reservation pin. The report contains
Noah's close/distance, clean/dirty, glove and game-memory witness list.

## r64 Music simple: Add songs (2026-09-08)

This is an additive host UI/service change, **EXPERIMENTAL / UNWITNESSED**.
Apply the exact, reviewable handoff in
`docs/mod_editor/music_simple_wiring.patch`. It changes only the protected
`mod_editor/gui/studio_qt.py` and `mod_editor/core/mod_build.py`. The patch was
checked with `git apply --check` and executed in memory by the standalone
`tests/mod_editor/test_music_simple_wiring.py`; those protected files were not
changed in this worktree.

### Studio and Build handoff

- Connect `MusicPanel.library_changed(object)` to the supplied
  `_music_library_changed(path)` handler. Its payload is the absolute path of
  an immutable, already prepared `nfl2k5_music_library/v1` JSON recipe, or `None`
  after the last added song is removed. The handler fills the existing
  `music_library_field` and checks `music_library_check`, under the existing
  restore guard, then captures the normal project Build settings. An explicit
  Add/Remove/Edit action owns this choice; ordinary refresh does not emit it.
- Retain that path when Music opens before Build, using
  `_music_library_recipe` in `_capture_music_build_settings`. When Build opens
  later, replay `MusicPanel.library_recipe_path()` after restoring its saved
  controls. When a recreated service already has an owned song manifest,
  replay its recipe through the same handler. Detaching a service with added
  songs emits `None` to clear its automatic Build path before another source
  is loaded. All existing changed, policy,
  playlist, receipt and operation-state signals and public methods are kept.
- Mount `MusicService` as soon as the session has its catalogued audio service,
  without waiting for `audio_editing_ready`. Adding fresh library songs does
  not invoke fixed-replacement fingerprint authorization. Original music reads
  still use the existing range decoder and IMA validator. Fixed replacements
  still go through their unchanged source-origin authorizations; if their
  private inventory has not been prepared, Audio Cues retains that preparation
  workflow. No authorization check has been removed from an existing writer.
- `_prepare_music_project` gains an optional `library_result` output list while
  preserving its encoded-edit tuple return API. A portable v2 Music project
  contributes its restored library recipe to that list. The outer Build wrapper
  assigns that recipe to its private `BuildPlan` before `_build`, with all
  restored song paths kept alive in the existing build TemporaryDirectory.
  A separate explicit library and a v2 project's own library together refuse
  with a clear choice, rather than silently dropping either. A v1 project
  continues through its existing fixed-replacement path.
- Keep the existing `_build` order: fixed replacements, then the existing
  library plan/rebuild against the working image, then final installed playlist
  validation before publication. Do not replay original source-index entries
  against the untouched input after other patches have changed the working image.
- The normal `.2k5mod` Build-settings map already accepts `music_library` and
  preserves its local path. The dedicated **Save Music project** is the portable
  song container: v2 embeds only prepared authored audio, titles, order, warnings,
  source identity and Playlist choices. It carries no game audio or host paths.
  Normal Studio Save retains its existing contract of storing external recipe
  paths, not embedding arbitrary library inputs. Keep the walkthrough's advice
  to save a Music project when moving or sharing added audio. Both v1 and v2
  `.2k5music` remain accepted. The advanced fixed-only patch exporter tells users
  with additions to share a Music project or export the finished Build & Share
  output; it cannot silently omit their added songs.

### Required integration inventory

| Integration item | Exact disposition |
| --- | --- |
| Dispatcher `_apply_all` tuple and kwarg | No new owner, tuple entry or kwarg. Existing `music_shuffle` and `music_shuffle_selection`, `music_policy`, `music_unlock`, `music_userlist` dispatch stays intact. Songs uses the existing host `music_library` build pass. |
| Four status dictionaries | No added status key in the original/applied/foreign/unsupported dispatcher maps. Existing `music_library` availability and playlist statuses are reused. |
| `_selected_space_requests`, `_xbe_space_adapter`, `_grown_status_fields` | No changes, requests, new adapter or grown field. The existing library metadata and playlist owners remain responsible for their bytes. |
| `BuildPlan` field | Reuse `music_library: str | None = None`; v2 project handoff sets it on the private plan. Reuse `music_project` and `music_shuffle_selection`. No added fields. |
| Basic / Advanced / Experimental presets | All keep personal libraries unselected. Only adding songs or choosing a saved project/library supplies a personal path. No preset or runtime capacity change. |
| Gameplay Patches `PATCHES` + `NEEDS_IMAGE` | No new executable patch row. If updating the existing music help, use: `Retail: keep the game's songs. Patch: add your prepared songs when you build a new game copy.` Existing music library/replacement `NEEDS_IMAGE` restrictions stay in force. |
| Build `_option` caption | Reuse `Include my music library (experimental)` (38 characters, below 60). Existing manual recipe chooser remains usable. |
| Release allowlist | Existing exact lines already cover `mod_editor/gui/music_panel_qt.py`, `mod_editor/studio/music_service.py`, `mod_editor/core/audio_conform.py`, `mod_editor/core/nfl2k5_music_build.py`, `mod_editor/core/nfl2k5_music_banks.py`, `tools/game_audio_convert.py`, `tools/xbox_ima_encoder.py`, and the getting-started doc. No new product module or allowlist line is required. Screenshots, handoff patch, tests and report are development evidence. |
| Runtime closure | Existing Music smoke imports `mod_editor.core.nfl2k5_music_build` and `mod_editor.studio.music_service`. Preserve their existing `audio_conform`, `nfl2k5_music_banks`, `nfl2k5_music_archive`, `nfl2k5_ausb_fixed_slots`, `nfl2k5_music_playlist`, `json_stream`, `platform_compat`, `tools.game_audio_convert` and `tools.xbox_ima_encoder` closure. New imports are standard-library `uuid`, `statistics`, `wave`, `array`, `json`, `math`, and `contextlib.ExitStack`; no new dependency. |
| Capability registry | Reuse `nfl2k5.music.bank_rebuild` on the existing `audio` surface, not a second executable capability. Suggested title: `Add your music (experimental)`. Summary: `Add original music files, check the prepared sound, and keep the game's 66 songs when building a new copy.` Keep runtime status `not-tested`, expose/edit true, default_enabled false and authored-only distribution. Add evidence paths `ASTRA_MUSIC_SIMPLE_REPORT.md`, `tests/mod_editor/test_music_simple.py`, `tests/mod_editor/test_music_simple_qt.py`, `tests/mod_editor/test_music_simple_wiring.py`. Use `backend.command = python3 -m tools.nfl2k5_music_banks --help` and `validation_command = python3 -m tests.mod_editor.test_music_simple` to satisfy dotted-module file checks. Backend module stays `mod_editor/core/nfl2k5_music_banks.py`. |
| Manifest and executable gates | No owner or byte changes. Do not regenerate the protected reservation JSON for this UI task. The brief's existing stale-reservation-source gate remains an integration issue. |

### Explicit limits to carry into release notes

The simple page keeps the original order of the game's 66 songs and allows
134 additions, 200 total. Only rows marked **yours** can be renamed, moved or
removed. The existing advanced library API keeps its own larger bank bounds.
The existing shuffle runtime stores 100 selected records. New songs get priority
and are checked by making room in that selection. If a single import adds more
than 100 songs, its newest 100 are checked; all imported songs remain in the
library. The UI, walkthrough and report disclose this boundary. Satisfying
"every newly added song checked" even for a 134-song batch would require changing
the executable owner, explicitly outside this brief. No hidden capacity increase
or invalid playlist document is emitted.

Removing songs does not rewrite earlier immutable recipe revisions. Their
prepared files remain in the session cache so an already captured Build path
cannot silently acquire different content. Music projects contain only the
current song list. Existing shared Undo/Redo continues to own fixed replacements;
added songs use the explicit Remove and Move controls.

## r64 ESPN 25th exact lineups, 2026-09-08

The existing `espn25_rosters` surface is already wired on base `5704832`.
This delivery changes its dataset and shared HELP_TEXT, with no new option,
writer bytes or executable owner. Protected files remain untouched.

- **Allowlist:** add the exact line `ASTRA_ESPN25_EXACT_LINEUPS_REPORT.md` beside
  `ASTRA_ESPN25_ROSTERS_REPORT.md` in `packaging/release-allowlist.txt`. The
  current allowlist already contains all 35 CSVs, manifest, owner and capability
  descriptor. Both offline generators remain repository development tools;
  neither is required by the shipped runtime. Never add raw PFR pages or inputs.
- **Dispatcher `_apply_all` tuple and kwarg, four status dictionaries:** retain
  the existing `espn25_rosters=False` plumbing and image-only adapter. No tuple,
  request union, kwarg or dictionary addition is needed. No XBE owner is added.
- **BuildPlan and presets:** retain `espn25_rosters: bool = False` in Basic,
  Advanced and Experimental and all existing position/layout/plan refusals.
- **Gameplay Patches:** the existing `PATCHES` row imports
  `tt.espn25_rosters_patch.HELP_TEXT`, updated here to include "Retail" and
  "Patch", PFR starters/numbers, shared-season and reserve limits. Keep
  `espn25_rosters` in `NEEDS_IMAGE`; no protected text edit is required.
- **Build `_option`:** retain `Historic moments: real rosters` (30 characters),
  the imported HELP_TEXT and `needs_image=True`.
- **Runtime closure imports:** existing
  `mod_editor.core.nfl2k5_espn25_rosters` suffices. No PFR reader or generator
  import is added to the runtime.
- **Capability registry:** the existing
  `nfl2k5.rosters.espn25_real_rosters` object and its descriptor are updated
  here with exact-lineup evidence and separate PFR/nflverse attribution. No new
  surface or capability-count change. CLI/validation commands are unchanged.
- **Protected reservation manifest:** the owner source pin changes because
  DATASET_SHA256 and HELP_TEXT changed. Regenerate
  `data/nfl2k5_cave_reservations.json` once with the complete integration stack,
  as the brief instructs; do not carry an ad hoc pin from this worktree.

## r64 MyCareer mode 4: visible native lists and player presentation

This section supersedes mode 3's drawing, current-week launch, camera and
57-byte headroom descriptions. EXPERIMENTAL / UNWITNESSED. The protected
sources are unchanged. Claude must regenerate
`data/nfl2k5_cave_reservations.json` after integration; the mode-4 scratch
manifest is review evidence only. Rebuild the executable from a supported
retail base. The previous mode's complete installation is not accepted as
an in-place upgrade.

The existing `_apply_all` tuple remains
`(my_career, _my_career_adapter(my_career_setup), "my_career_patch", "MyCareer (experimental)")`.
Keep `my_career` and optional `my_career_setup` kwargs, complete-union
allocation, normalization, deferral and final apply. The adapter already
calls `nfl2k5_my_career_mode.apply` for a missing setup. All four status
surfaces (XBE inspection, image inspection, executable/copy apply, copied
image result), and `_grown_status_fields`, already use the shared
MyCareer recognizer; retain their `my_career` status and separate
`my_career_patch` receipt. No new dispatcher or status key is needed.

Retain `BuildPlan.my_career: bool = False` and
`my_career_setup: str | None = None`. Basic, Advanced and Experimental all
leave MyCareer off. Existing Auto Save selection and native preferences
are unchanged. Both owners still compose in either order.

Keep `my_career` in Gameplay Patches `NEEDS_IMAGE`. Suggested replacement
PATCHES text, retaining the required Retail/Patch words:
`Retail controls a franchise team. Patch adds experimental MyCareer creation,
team selection, a visible Apartment and inline saves. Play opens your next
fixture after any required league processing. MyPlayer gets the retail
indicator, receiver icons and play art. Off field, the CPU plays at normal
speed. Supersim is not available. Experimental / Unwitnessed.`
The Build `_option` caption remains
`MyCareer: create MyPlayer in the game` (37 characters).

Existing allowlist lines and corresponding dotted runtime imports remain:

```text
mod_editor/core/nfl2k5_my_career.py
mod_editor/core/nfl2k5_my_career_code.py
mod_editor/core/nfl2k5_my_career_mode.py
mod_editor/core/nfl2k5_my_career_mode_code.py
mod_editor/core/nfl2k5_my_career_save.py
mod_editor/core/nfl2k5_franchise_autosave.py
mod_editor/core/nfl2k5_franchise_autosave_code.py
docs/mod_editor/nfl2k5_my_career_mode_capabilities.json
```

There is no new capability surface or registry ID. Keep the existing
runtime-not-tested and default-off/expose policy. The new fixtures,
`measure_mode4.py`, `fastforward_candidate.c` and `mode4_budget.json` are
development evidence and need no runtime-closure import or release entry.
The candidate is never installed or executed. Its 48-byte machine delta
exceeds the current tested layouts by 40/42 RX bytes even before scene,
resume and UI implementation. The owner remains exactly 8192 RX / 4096 RW.
The updated `measure_m3.py` uses the installed Oz compiler setting and
reports the former Os setting separately; historical M3 receipts remain
historical, not current headroom claims.

The protected camera owner and Abilities owner require no changes. The
camera adaptation is a MyCareer-only branch/focus wrapper. Play art wraps
only the bound player's input call at `1212A5`, outside Abilities' complete
`120A20` dependency pin. Its temporary side mask is restored before the
caller returns. Both owners retain their full validators.

One older, unrelated test still needs Claude's shared harness cleanup:
`test_nfl2k5_defensive_try_manifest.py` reads the protected
`DEFAULT_MANIFEST` directly and ignores `NFL2K5_CAVE_MANIFEST`. Its source
was left unchanged. The three original assertions pass when a runpy
harness supplies the freshly generated, fully validated scratch manifest
as that imported default. Keep the source-drift refusal; only add the
same explicit environment-path selection already used by the MyCareer
and screen-hooks manifest suites. The report distinguishes this run from
ordinary standalone commands.


## MyCareer mode 5 handoff (2026-09-08)

EXPERIMENTAL / UNWITNESSED. Read `ASTRA_MYCAREER_MODE_5_REPORT.md`.
This updates the existing generic MyCareer owner; it adds no allocator owner,
BuildPlan option, product panel, capability ID, or archive writer. Keep the
8,192-byte RX and 4,096-byte RW requests and the existing gate union.
Rebuild from the original XBE: a mode-4 or mixed installation is foreign to
this exact mode-5 template and must not be upgraded in place.

The following wiring is already present at this branch base and must remain:

* In `nfl2k5_throw_tuning._apply_all`, the final owner tuple is
  `(my_career, _my_career_adapter(my_career_setup), "my_career_patch", "MyCareer (experimental)")`.
  Pass `my_career=True, my_career_setup=None` for in-game creation. The adapter's
  `None` route calls `nfl2k5_my_career_mode.apply`; an explicit validated setup
  calls `nfl2k5_my_career.apply(payload, setup=...)`. Its shared `status` is
  `nfl2k5_my_career.status`, which delegates complete generic validation.
* `_selected_space_requests` and `_xbe_space_adapter` retain `my_career` and
  the existing `my_career_patch.REQUESTS`. The four status dictionaries in
  `read_xbe`, `read_image`, `write_xbe_copy`, and `write_image_copy` already expand
  `_grown_status_fields(payload/result/after)`; retain its
  `"my_career": my_career_patch.status(payload)` entry in all four paths.
* `BuildPlan.my_career: bool = False` and
  `BuildPlan.my_career_setup: str | None = None` stay unchanged. Basic,
  advanced and experimental presets all keep MyCareer **off** until opted in.
  Empty setup fields normalize to `None`; keep first-pass deferral and the
  final pass so the allocator reserves the complete request union first.
* Gameplay Patches inherits the `my_career` PATCHES row from
  `mod_editor.gui.beta62_options`, and `NEEDS_IMAGE` includes that row through
  the existing shared catalog. Preserve the native-disc requirement and the
  optional legacy setup field. Suggested replacement details, including the
  required Retail/Patch wording:
  `Retail: Franchise controls a team. Patch: create MyPlayer in the game, choose a club and sign as a starter. The Apartment offers Play next game, Practice, MyPlayer, Start MyPlayer, Save and Quit. Restore the starting spot with Start MyPlayer. Native lists highlight the selected row in yellow. Your quarterback calls plays while on the field; the other unit uses the CPU at normal speed. The Apartment explains off-field control. Supersim and Apartment art are not available. Experimental / Unwitnessed.`
  Synchronize the inherited `nfl2k5_my_career.HELP_TEXT` when wiring this copy:
  its current five-row list and reference to an in-game footer are stale.
* The Build tab's shared `_option` caption can stay
  `MyCareer: create MyPlayer in the game` (35 characters, below 60).
  Do not require a setup for the generic route.
* Keep these existing allowlist lines:
  `mod_editor/core/nfl2k5_my_career.py`,
  `mod_editor/core/nfl2k5_my_career_code.py`,
  `mod_editor/core/nfl2k5_my_career_mode.py`,
  `mod_editor/core/nfl2k5_my_career_mode_code.py`,
  `mod_editor/core/nfl2k5_my_career_save.py`,
  `mod_editor/gui/my_career_panel_qt.py`,
  `docs/mod_editor/nfl2k5_my_career_capabilities.json`, and
  `docs/mod_editor/nfl2k5_my_career_mode_capabilities.json`.
  The new navigation fixture, tests, validation receipt and manifest projection
  tool are development evidence and need no runtime allowlist entry.
* Keep runtime-closure imports for `mod_editor.core.nfl2k5_my_career`,
  `nfl2k5_my_career_code`, `nfl2k5_my_career_mode`,
  `nfl2k5_my_career_mode_code`, `nfl2k5_my_career_save`, and
  `mod_editor.gui.my_career_panel_qt` (each core suffix under
  `mod_editor.core`). No compiler, Unicorn or archive-research tool is a
  production dependency.
* Retain capability ID `nfl2k5.mode.my_career_inline`; no new registry surface
  is necessary. Its backend command remains
  `python3 -m mod_editor.core.nfl2k5_my_career_mode apply default.xbe generic-default.xbe`
  and its validation command remains
  `python3 -m tests.mod_editor.test_nfl2k5_my_career_inline`.
  Add mode-5 and updated mode-4/turnover tests to its evidence when refreshing
  the catalog, with the report's exact witness limits.

Protected manifest regeneration remains Claude's release step. This session
kept the main drive above 100 GB: 106.004 GB free minus the 6.3005 GB source
image would have left only 99.703 GB before XBE growth. No acceptance image
was created. `tools/mycareer_mode/refresh_gate_manifest.py` instead observes
the real MyCareer writer with the oracle Recorder, inherits only verified
parent source pins, and adds conservative native reservations to
`.scratch/mode5-manifest.json`. That file labels itself a bounded XBE
projection; its parent disc fields are historical. It is not a release
manifest and must not be copied over the protected JSON. Once capacity
permits a disposable build while retaining 100 GB, run the full oracle
manifest command against the original XBE/XISO and regenerate
`data/nfl2k5_cave_reservations.json` through the normal release workflow.

The older defensive-try note immediately above is superseded by this base:
its standalone test now honors `NFL2K5_CAVE_MANIFEST` and passes directly.
No shared harness edit is needed.

Fable art is still unbound. `navigation` includes the shared `nav_menu_a`
and `title_bar_wide` families; the Apartment descriptor now uses those same
retail resources. There is no proved Apartment-only SCNE/TXTR registration,
lookup and unload path. A future binding must clone/register private resource
names and prove enter/back/load/quit lifetime and compatibility with Game
Modes, Team Select and the Crib. Do not replace shared Crib or navigation
textures with the Fable backdrop. This session changes no archive bytes.
## R64 ESPN25 in-game investigation, 2026-09-08

This section supersedes earlier ESPN25 instructions that describe the option as
data only or ready for opt-in builds. See `ASTRA_ESPN25_IN_GAME_REPORT.md`.
The duplicate-team importer fault has a bounded native repair, but the reported
Ice Bowl #14 and the loading music wait loop remain unresolved. The all-moments
option is blocked through `BUILD_BLOCK_REASON` and `require_build_ready()`.
There is no force switch. Do not clear the hold on the strength of roster bytes,
kit existence, a completed export, or the native tests alone.

The hold already runs in `apply` / `apply_resources`, `preflight_image`,
`apply_to_image`, and `build_image`. Thus the existing protected dispatchers'
resource preflight refuses before copying. This is tested with the actual
bn-style BuildPlan, with only unrelated image presentation preflights mocked.
The full Experimental plan still refuses One-pool positions first.

Protected dispatcher changes for Claude:

1. In `mod_build._build`, replace
   `_, roster_preview = module.apply(module.read_resources(source))` with
   `roster_preview = module.preflight_image(source)`.
   In `nfl2k5_throw_tuning.write_image`, replace the matching resource-only
   preflight with `espn25_rosters_patch.preflight_image(source)`. This also
   validates the pinned native release routine before a copy if the hold is
   eventually lifted. Keep the final `apply_to_image` pass after relocations.
   It now owns both the 35 resource slices and exact executable/digest spans.
   Change the two old "data-only" comments. Do not write main ROST or SITU.
2. The current all-moments image adapter already pairs the repair with the
   resources, so no executable dispatcher change is needed to enforce this
   blocked delivery. If the shared dispatcher records the native owner when
   the option is later cleared, use exactly this `_apply_all` tuple:
   `(espn25_rosters, espn25_rosters_patch.XbePatch,
   "espn25_rosters_load_fix", "Historic team reload fix")`.
   Add the internal kwarg `espn25_rosters=False` and forward it through each
   image `_apply_all` call, including the deferred final call. Preserve the
   public bare-XBE refusal. Do not add an independent user toggle that could
   separate the rosters from their repair. `REQUESTS = ()`: no allocator
   request, budget row, page, cave or runtime-data reservation is needed.
3. Keep `espn25_rosters` in the four existing status dictionaries. Bare-XBE
   inspect and bare-XBE copy report `n/a`; image inspect and image-copy result
   call `_espn25_rosters_image_status`. The recognizer now reports
   `needs load fix` for the complete old roster profile on the old executable,
   and `applied` only for the paired candidate. These are byte states, not
   gameplay approval. For the optional tuple above, add the distinct
   `espn25_rosters_load_fix: espn25_rosters_patch.xbe_status(payload)` to
   `_grown_status_fields`, which reaches all four dictionaries; use the final
   result payload at the two write surfaces. The owner receipt is separate
   from those statuses and from `espn25_rosters_patch`'s resource receipt.

Keep `BuildPlan.espn25_rosters: bool = False`, its normalization, its exclusion
of `espn25_plan`, and the retail-position guard. Basic, Advanced and Experimental
all remain false. The bn-style native fixture has position_pools,
position_pools_keep_olb, depth_roles, edge_rename and depth_chart_rows off.
Full Experimental is not compatible and is not an additional accepted runtime
configuration. While the hold exists, `_espn25_rosters_available()` should return
false after checking `module.BUILD_BLOCK_REASON`; retain read-only inspection
and show the reason rather than silently dropping the option.

Gameplay Patches PATCHES remains keyed by `espn25_rosters` with the shared
`HELP_TEXT`, and `NEEDS_IMAGE` retains `espn25_rosters`. The updated text already
contains both required words:
"Retail: many historic players have position names in shared rosters. Patch:
use Pro Football Reference game starters and season jersey numbers with the
nflverse roster base. Short lists still need named reserves from nearby seasons.
Shared teams cannot match every game. Requires the retail position layout.
Build blocked while the Wide Right loading freeze remains unresolved.
EXPERIMENTAL / UNWITNESSED. See the in-game report."
The Build `_option` caption remains `Historic moments: real rosters`
(29 characters), `needs_image=True`. Neither caption nor help may claim the
loading freeze or #14 has been fixed.

Existing allowlist lines remain:

```text
mod_editor/core/nfl2k5_espn25_rosters.py
mod_editor/core/nfl2k5_espn25_scenarios.py
mod_editor/core/nfl2k5_rdata_sites.py
mod_editor/core/nfl2k5_bump_strength.py
docs/mod_editor/nfl2k5_espn25_rosters_capability.json
```

The existing dataset directory entries stay unchanged. Add
`ASTRA_ESPN25_IN_GAME_REPORT.md` if the release includes feature reports.
The new native harness and tests are development files, not runtime modules.
Runtime-closure imports remain `mod_editor.core.nfl2k5_espn25_rosters` and
`mod_editor.core.nfl2k5_espn25_scenarios`, plus the already shipped
`mod_editor.core.nfl2k5_rdata_sites`, `mod_editor.core.nfl2k5_bump_strength`, and
`mod_editor.core.nfl2k5_throw_tuning`. The last import is lazy and only obtains
the existing XDVDFS reader, avoiding an import cycle. Update the runtime checker
if it assumes that a historic-roster apply is always available: inspection and
`validate-dataset` still work; a build must now return the explicit hold.

No new capability ID or surface is introduced. In the existing
`nfl2k5.rosters.espn25_real_rosters` object and its capability JSON handoff,
set `gui.expose` false while blocked, retain `gui.default_enabled` false and
`runtime.status` `not-tested`, and set `gui.reason` to `BUILD_BLOCK_REASON`
plus the EXPERIMENTAL / UNWITNESSED label. Add this report and
`tests/mod_editor/test_nfl2k5_espn25_in_game.py` to evidence/runtime evidence.
Replace the obsolete `source_container.resource` suffix "no XBE edit" with
"candidate paired with the pinned 12-byte C2300 release-loop repair; builds
blocked". Describe the all-50-side trace as bounded native player selection,
not a played game. Keep the schema-valid backend command
`python3 -m mod_editor.core.nfl2k5_espn25_rosters build source.iso historic.iso
--receipt historic-receipt.json` and use validation command
`python3 -m tests.mod_editor.test_nfl2k5_espn25_in_game`.

The gate union and all manifest-builder owner lists already include the native
adapter. Claude must regenerate the protected manifest with the normal oracle
manifest command after integration. This session used a scratch copy of
manifest 26 with current source fingerprints and only the pinned live edit
added; it did not manufacture a new real-disc manifest or allocate a cave.
Do not copy that scratch manifest over the production file.

## R65 throws to backs, 2026-09-08: research hold

See `ASTRA_BACK_THROWS_REPORT.md`. This delivery is a read-only native research
tool and standalone tests. It installs **no gameplay owner**. The four reported
gameplay failures and the standing-versus-dive contract remain unproved in a
full native frame. Do not expose a repaired-back-throws option, advertise 2K8
parity, or enable a preset from these component results.

Current integration is explicitly empty:

| Protected integration point | This delivery |
| --- | --- |
| `_apply_all` owner tuple and kwarg | None; there is no `nfl2k5_back_throws` writer to dispatch. |
| Four status dictionaries | No new field in bare-XBE inspect, bare-XBE write result, image inspect or image write result; no `applied` status exists. |
| `_selected_space_requests`, `_xbe_space_adapter`, `_grown_status_fields` | No additions; zero RX, RW or RO bytes are requested. |
| `BuildPlan`, normalization, deferral and final pass | No field or forwarding; Basic, Advanced and Experimental all remain without this option. |
| Gameplay Patches `PATCHES` / `NEEDS_IMAGE` | No row and no membership. |
| Build tab `_option` | No control. |
| Release allowlist | No runtime lines; the new tool and test are development files. The report can be included with the other Astra reports. |
| Runtime closure imports | None; do not add Unicorn, Capstone or the research tool to the application. |
| Capability registry | No product capability is introduced. The development CLI is not a playable-back-throws feature. |

The existing gate union, owner-budget fixture, manifest builder's three lists
and both gate setUpClass methods therefore remain unchanged. Adding a no-op
owner or returning `applied` for retail bytes would misstate this result.
The scratch manifest only refreshes seven pre-existing source hashes; it does
not add reservations or regenerate the full disc proof. Do not publish it.

For a later implementation, the following is a **conditional handoff, not
code to wire now**. First reproduce the missing full-frame failures, prove
native clip motion/envelopes, implement the owner, and pass its refusal,
idempotence, all-owner, pairwise and full-frame tests. Keep every preset off
until those conditions are met; initial exposure should be opt-in only.

1. Import the eventual `nfl2k5_back_throws` as `back_throws_patch`. Use the
   internal boolean `back_throws=False`, and an owner tuple after allocation:
   `(back_throws, back_throws_patch, "back_throws_patch", "Throws to backs (experimental)")`.
   Forward the flag through both bare-XBE and image writers, including each
   deferred/final `_apply_all` call. Add `"back_throws": back_throws_patch.status(payload)`
   to `_grown_status_fields`, so all four dictionaries use the correct current
   payload (`result` and `after` for write results).
2. Add `back_throws` to the request selector and allocator adapter and union
   the eventual `REQUESTS` before installing any grown owner. A simple boolean
   owner needs no settings adapter. Do not reserve a guessed size: first plan
   its measured code in a scratch budget fixture. Use v3, `scaleout=True`,
   `install_code`, and no runtime state in `.text`. Add its actual requests and
   owner to the shared test union and all three manifest-builder lists, and
   explicitly assert its status in both gate setUpClass methods.
3. Add `BuildPlan.back_throws: bool = False`, boolean normalization, the
   executable deferral condition and final forwarding together. Basic,
   Advanced and Experimental should initially all leave it false.
4. A future Gameplay Patches row may use caption `Throws to backs (experimental)`
   and text: `Retail: backs can have inconsistent short catches. Patch:
   experimental targeting and catch choices for backs. Full gameplay testing
   is still required. EXPERIMENTAL / UNWITNESSED.` Rewrite that text to the
   actually proved scope before exposing it. An XBE-only implementation has
   no `NEEDS_IMAGE` membership; add that membership only if the final repair
   requires PLAY or animation resources. Use the same Build `_option` caption
   (30 characters), with `needs_image` matching the final implementation.
5. Conditional allowlist/runtime entries are
   `mod_editor/core/nfl2k5_back_throws.py` /
   `mod_editor.core.nfl2k5_back_throws`, plus an actual separate code module
   only if one is built. Neither file exists in this delivery. A future
   capability can use ID `nfl2k5.gameplay.back_throws`, `gui.expose=false`,
   `gui.default_enabled=false`, `runtime.status=not-tested`, and this report
   plus the eventual owner/full-frame tests as evidence. Its backend command
   must resolve to a real `python3 -m mod_editor.core.nfl2k5_back_throws ...`
   CLI; no such backend currently exists. The current validation command is
   `python3 -m tests.mod_editor.test_nfl2k5_back_throws` and validates research
   components only. Do not register an invented runnable backend.
## r65 Broadcast camera v5 (2026-09-08)

This section supersedes the earlier camera capacity and menu descriptions.
EXPERIMENTAL / UNWITNESSED. `ASTRA_CAMERA_V5_REPORT.md` records the exact
coach-mode director gap: Broadcast is a following adaptation of a proved
native sideline mount. Native selection and control fixtures pass; no played
game or exact coach-toggle shot match is claimed.

There is no new Build option or preset change. The existing camera owner adds
Broadcast to the game's Camera enum. Choices are Standard, Far, Side, Iso,
Blimp, Custom and Broadcast, using engine indices `0,1,2,3,4,5,7`. First Person
index 6 is skipped. Standard remains the startup/game-entry default; Far is
unchanged. Choices last for the session under the existing v4 policy.

### Dispatcher and BuildPlan

The existing protected wiring already consumes the new `camera_patch.REQUESTS`.
Keep `_apply_all(..., camera=False, ...)`, its final owner tuple
`(camera, camera_patch, "camera_patch", "camera")` immediately after the
allocator, and `camera=camera` in `_selected_space_requests`,
`_xbe_space_adapter` and the deferred image pass. Preserve
`"camera": camera_patch.status(...)` in all four status dictionaries: plain
inspection (currently line 654), image inspection (779), `write_copy` result
(1780), and image-write result (2121), plus `_grown_status_fields` (1333).
No settings adapter or new status key is needed.

Keep `BuildPlan.camera: bool = False`, normalization, XBE deferral and final
`camera=plan.camera` pass. Keep **Basic off, Advanced on, Experimental on**.
Correct its stale Far-default comment to `Standard default, Far and Broadcast
session choices; experimental`. This is a menu row within the existing patch,
not another Build switch.

Requests are now exactly:

```python
(("nfl2k5_camera", "code", 160, 16),
 ("nfl2k5_camera", "read_only", 80, 16))
```

Reserve both in the complete selected union before any owner installs. This
adds 96 RX and 80 RO bytes, zero RW, with no allocator page-count change.
The budget fixture is updated. `tests/nfl2k5_allocator_stack.py` and all three
manifest-builder owner/request lists already include this owner and import
its requests; they need no duplicate entry. Old 64-byte camera allocations
are foreign: rebuild from a supported source instead of upgrading in place.

### Protected UI text

In `mod_editor/gui/gameplay_patches_panel_qt.py`, use this existing-key PATCHES
row and retain `camera` in `NEEDS_IMAGE`:

```python
("camera", "Standard, Far and Broadcast cameras (experimental)",
 "Retail: Camera offers Standard, Far, Side, Iso, Blimp and Custom. "
 "Patch: Standard starts each game and practice. Far keeps its framing, "
 "and Broadcast adds a following sideline view without changing Coach Mode. "
 "Choose Broadcast in the game's Camera options. The choice lasts for the session. "
 "Broadcast adapts the native sideline view; the exact coach-mode TV shots "
 "are not reproduced. EXPERIMENTAL / UNWITNESSED.")
```

In `mod_editor/gui/build_panel_qt.py`, retain `_option(pl, "camera", ...)` and
use caption `Standard, Far and Broadcast cameras (experimental)` (50 chars).
Help: `Standard starts each game and practice. Far keeps its framing. Choose
Broadcast in the game's Camera options for a following sideline view without
changing Coach Mode. Session choice only. EXPERIMENTAL / UNWITNESSED.` Keep
any compact evidence row at `NOT_TESTED`; bounded CPU fixtures are not Noah's
gameplay witness. No other GUI panel needs a camera-specific change.

### Packaging, capabilities and manifest

Retain these existing allowlist/closure sources:

```text
mod_editor/core/nfl2k5_camera.py
mod_editor/core/nfl2k5_xbe_space.py
mod_editor/core/nfl2k5_bump_strength.py
mod_editor/core/nfl2k5_draft_ai.py
```

In `packaging/check_2k5_mod_studio_runtime.py`, add an explicit
`mod_editor.core.nfl2k5_camera` entry to the import tuple (the current tuple
omits it). Include `mod_editor.core.nfl2k5_xbe_space`,
`mod_editor.core.nfl2k5_bump_strength` and `mod_editor.core.nfl2k5_draft_ai`
if absent; these are its unchanged relative dependencies. Check `VERSION == 5`,
the exact two requests above and `status(b"") == "foreign"`. Run the clean
runtime closure after integration. No new runtime module, resource, CLI or
studio surface was added. There is no new capability
registry object: this extends the existing camera Build/PATCHES surface with
an in-game choice. The separate camera-options inspector still describes the
retail game and must retain its six-choice bound. Tests, proof tools, fixture,
JSON, PNG and report are development evidence, not runtime imports or release
payloads. The unified provider's camera SHA-256 is already updated here.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with the
normal oracle manifest command after integration. Include the two final named
camera children, the four enum edits and the 13 row-7 pointer edits. Do not
reuse a v4 64-byte allocation or a stale declaration from another union.
This session uses an observed **pure-XBE** scratch manifest through
`NFL2K5_CAVE_MANIFEST`; it is not a resource/disc build receipt. The observation
test now routes the anniversary adapter's captured staticmethod through the
same real writer wrapper, so its `C2319` change is attributed without editing
that protected owner. No oracle exemption or manufactured free cave was added.
The standalone oracle suite keeps executable ownership assertions mandatory
and tests resource-build steps separately. The latter explicitly skips only
when a selected scratch manifest declares this exact observed XBE-only model;
the normal release-manifest test still requires both resource-build steps.

Complete the report's witness list, including pause navigation and camera
switches during real plays, before making a runtime acceptance claim. Protected
release files, build modules, GUI panels and the release manifest were not
edited in this worktree.
# r65 Franchise Player Contracts Edit Player handoff (2026-09-08)

New owner: `mod_editor/core/nfl2k5_franchise_edit_player.py`. Evidence:
`ASTRA_FRANCHISE_EDIT_PLAYER_REPORT.md`. This appendix specifies all protected
product changes. The backend, CLI, capability object, standalone tests,
allocator budget, manifest builder and both gate unions are implemented.
**EXPERIMENTAL / UNWITNESSED. Opt-in, off in every preset.**

## Dispatcher and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import:

```python
from . import nfl2k5_franchise_edit_player as franchise_edit_player_patch
```

Add strict Boolean `franchise_edit_player=False` to `_apply_all`,
`write_xbe_copy`, `write_image_copy`, `_validate_r62_options`,
`_selected_space_requests`, and `_xbe_space_adapter.__init__`. Include it in the
Boolean validator and in both `R62_RUNTIME_KEYS` and `R62_SPACE_KEYS`. Thread it
through validation, public writer no-op predicates, `_r62_options`,
`_r62_space_options`, `_deferred_r62_options` and all forwarding calls. Existing
comprehensions that derive these dictionaries from key tuples should carry the
new key automatically; verify the resulting kwargs rather than duplicating it.

Append this request term in `_selected_space_requests`:

```python
+ (franchise_edit_player_patch.REQUESTS if franchise_edit_player else ())
```

Pass `franchise_edit_player=franchise_edit_player` into that selector from
`_xbe_space_adapter`. Include it in `self.scaleout` and every predicate selecting
an allocator pass, including the allocator row in `_apply_all`. Reserve the
entire chosen union on a clean base before installing any owner. The request is
704 RO bytes, aligned to 16, with no code/data request. An already-grown image
with a different union must rebuild from base; the backend refuses it.

Add this exact row to the final `_apply_all` owner tuple after the allocator:

```python
(franchise_edit_player, franchise_edit_player_patch,
 "franchise_edit_player_patch", "Franchise Edit Player (experimental)")
```

No settings adapter is needed: `apply(payload)` accepts only bytes and returns
`(bytes, receipt)`. It applies the existing `nfl2k5_position_row` prerequisite
itself, so selecting this feature alone must not require another user checkbox.
Enable the dispatcher's earlier Position row when either `position_row` or
`franchise_edit_player` is true. This records the prerequisite under its existing
owner before the new final owner runs; the backend's own dependency call then
replays without changes. Forward
this owner's subreceipt and changed-byte accounting to the public write/build
receipts; the subreceipt includes its Position dependency receipt.

The four public status dictionaries must expose:

```python
"franchise_edit_player": franchise_edit_player_patch.status(payload)
```

Use each function's final bytes (`payload`, `result` or `after`) in `read_xbe`,
`read_image`, `write_xbe_copy`, and `write_image_copy`. The existing
`_grown_status_fields` is expanded by all four, so add this key there once and
verify all four outputs. `retail`, `applied` and `foreign` describe the installed
XBE, not the current game mode or a runtime success witness.

For `write_image_copy`, include the flag in `defer_grown`, in the complete
selector kwargs passed to grown/paired writers, and the final `_apply_all` pass.
Force it False in every early pass that must keep the retail executable size.
Use the existing grown-XBE writer to relocate the extent. There is no PLAY,
ROST, texture or archive pass for this feature.

## BuildPlan, normalization, presets, deferral and final pass

In protected `mod_editor/core/mod_build.py`:

```python
franchise_edit_player: bool = False
```

Add the field to `BuildPlan`, `wants_xbe_patch()`, strict option validation,
scan/status keys and the capability/module-availability table:

```python
("franchise_edit_player", "nfl2k5_franchise_edit_player")
```

Set it **False** in `basic`, `softdrink_advanced` and `softdrink_experimental`.
Keep the standalone BuildPlan default False. This is an explicit opt-in and
requires no settings path. Normalize enabled selection to `xbe_space=True` and `position_row=True`.
Allow selection when the feature backend and its existing Position/allocator
helpers import. No dependency on selecting Franchise Practice or MyCareer.

Include the field in the grown-owner deferral predicates near `momentum_on`, in
the early `replace(..., camera=False, ...)` as `franchise_edit_player=False`, in
the final grown-owner predicate and the final `tt.write_copy` kwargs. Existing
`_build_r62_values` must pick it up through the updated key list; do not pass an
explicit duplicate beside `**r62`. Keep one immutable selected request union
across later camera/scoreboard/roster passes. Include the owner receipt in the
build step/status summary and use the normal foreign-state refusal.

If a coordinating preset later enables this feature, also add
`franchise_edit_player=False` to the manifest builder's separate retail-size
seed `replace(...)`. On this handoff's all-False presets, that seed already
leaves it disabled. The manifest builder explicitly installs the dormant owner
using its complete union independently of the protected dispatcher.

## Gameplay Patches and Build controls

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, add this `PATCHES`
row and add `franchise_edit_player` to `NEEDS_IMAGE`:

```python
("franchise_edit_player", "Franchise Edit Player (experimental)",
 tt.franchise_edit_player_patch.HELP_TEXT)
```

The exact `HELP_TEXT` reads:

> EXPERIMENTAL / UNWITNESSED. Retail Player Contracts has no Edit Player action.
> Patch: adds Edit Player after Assign Jersey Number for the team you coach.
> Use the game's roster editor, including Position, appearance and ratings,
> then return to Player Contracts. Changes take effect immediately, including
> when you press Back. Review the depth chart after changing a position.

It contains both **Retail** and **Patch**, with no em dash or implementation
jargon. Use the normal positive checkbox: checked enables the patch. Include
it in source eligibility, status/availability, selection and writer kwargs.
The Studio image surface must route through the grown-image pipeline even
though the standalone module can operate directly on a new XBE output.

In protected `mod_editor/gui/build_panel_qt.py`, use:

```python
self.franchise_edit_player_check = self._option(
    pl, "franchise_edit_player", "Franchise Edit Player (experimental)",
    tt.franchise_edit_player_patch.HELP_TEXT, needs_image=True)
```

The caption is 36 characters, below 60. Add refresh/preset/reset wiring,
capability gating, selected-options summary, BuildPlan serialization and the
nonempty-build predicate. Use the same canonical Boolean in both panels.
In `studio_qt.py` and `gameplay_panel_qt.py`, forward it wherever shared patch
selections or source-status fields are copied. No separate feature panel or
second toggle state is required.

## Packaging, runtime closure and capability registry

Add these literal lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_franchise_edit_player.py
docs/mod_editor/nfl2k5_franchise_edit_player_capability.json
ASTRA_FRANCHISE_EDIT_PLAYER_REPORT.md
```

If the existing package policy ships development test sources, also include:

```text
tests/nfl2k5_franchise_edit_player_fixture.py
tests/mod_editor/test_nfl2k5_franchise_edit_player.py
tests/mod_editor/test_nfl2k5_franchise_edit_player_unicorn.py
```

Retain the existing Position-row source in the allowlist. Never include the
brief, scratch directory, retail bytes, synthetic memory dump or generated XBE.
No bitmap, template binary or assembler output is required.

Add this literal import to protected
`packaging/check_2k5_mod_studio_runtime.py`:

```python
"mod_editor.core.nfl2k5_franchise_edit_player",
```

Retain the existing transitive closure: `nfl2k5_position_row`,
`nfl2k5_rdata_sites`, `nfl2k5_xbe_space`, `nfl2k5_bump_strength`,
`nfl2k5_cave_oracle`, `nfl2k5_my_career_mode`, `nfl2k5_my_career`, their code
helpers, and `nfl2k5_music_playlist`. MyCareer and playlist imports validate
complete companion installations when shared native entry points differ.
The product writer requires neither Capstone nor Unicorn; those are optional
proof dependencies.

Merge the exact schema-valid object from
`docs/mod_editor/nfl2k5_franchise_edit_player_capability.json` into
`mod_editor/capabilities/registry.v1.json`, sorted by ID
`nfl2k5.gameplay.franchise_edit_player`. It uses the existing
`gameplay_tuning_sliders` surface, classification `offline-writer-proved`, GUI
default false and runtime `not-tested`. Backend and validation commands are
module commands:

```text
python3 -m mod_editor.core.nfl2k5_franchise_edit_player apply source.xbe contracts-editor.xbe
python3 -m tests.mod_editor.test_nfl2k5_franchise_edit_player
```

The feature test validates the merged registry schema and strictly checks every
new evidence path and command module. Whole-registry file-check mode can still
fail on the baseline's missing `docs/research/apf_audio.md`; do not forge that
unrelated evidence or weaken validation. Nothing here requires a version bump,
release-tag test change, update-check change or CI configuration edit.

## Coordinating acceptance and release manifest

Implemented in this worktree: request union and owner tuple in
`tests/nfl2k5_allocator_stack.py`, both explicit gate checks in both installation
orders, the pair matrix, budget fixture, `space.dormant_union()`, and manifest
builder append/reservation whitelists, request/import/observer/final/synthetic/
status/extra-owner lists. Gate projections reserve only this owner's exact
pinned instructions after complete applied-state validation and overlap checks.
They do not grant ownership to arbitrary nearby code.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` using
`tools/nfl2k5_cave_oracle.py manifest` after the final product wiring lands.
The task's scratch manifest refreshes source pins on the existing release
reservation document to run the local gates; it is not a newly observed disc
manifest and must not be shipped. The report records all pre-existing drift.

After wiring, verify the feature alone selects v3, installs Position, writes
and reopens a grown XBE through the actual image pipeline, and reports applied
in all four status dictionaries. Repeat with the complete selected union,
forward/reverse/replay, configured MyCareer and playlist, and with the option
off. Confirm all three presets leave it off. Use temporary disposable discs
under the brief's capacity rules, then run both gates and the two standalone
feature suites. Noah's precise runtime witness list is in the report.
# r65 CPU fourth downs and first downs (2026-09-08)

EXPERIMENTAL / UNWITNESSED. The new owner is implemented and callable, with
Retail, Modern and Aggressive levels. The shared product files below were
protected by ASTRA_BRIEF.md and were not edited. This section is the exact
integration handoff; existing read-option, MyCareer, ESPN and coverage-trail
sections remain independent. See ASTRA_CPU_MONEY_DOWNS_REPORT.md for the table,
native replay evidence and Noah's witness list.

## Dispatcher and allocation

In `mod_editor/core/nfl2k5_throw_tuning.py`, import
`nfl2k5_cpu_money_downs as cpu_money_downs_patch`. Add the string kwarg
`cpu_money_downs="retail"` to `_apply_all`, `write_xbe_copy`, `write_image_copy`,
`_selected_space_requests`, `_xbe_space_adapter.__init__` and
`_validate_r62_options`, forwarding it through each corresponding call.
Add `cpu_money_downs` to both `R62_RUNTIME_KEYS` and `R62_SPACE_KEYS`.
Validate `type(cpu_money_downs) is str` and membership in
`cpu_money_downs_patch.LEVELS`; exclude it from Boolean flag validation.
In `_deferred_r62_options`, set it explicitly to `"retail"` after the generic
False defaults, just as numeric options have explicit numeric defaults.
Do not use truthiness to decide whether the nonempty string `"retail"` is on.

Append `(cpu_money_downs_patch.REQUESTS if cpu_money_downs != "retail" else ())`
to `_selected_space_requests`. The allocator entry's enable expression also
includes `cpu_money_downs != "retail"`. Reserve the full union once with
`space.apply(payload, requests, scaleout=True)` before owner installation.
This owner reserves 2048 aligned RX bytes, no RW or RO child. Its standalone
`apply` explicitly selects v3 on an unallocated base.

Use this adapter and tuple after the allocator entry:

```python
class _cpu_money_downs_adapter:
    def __init__(self, level):
        self.level = level
    status = staticmethod(cpu_money_downs_patch.status)
    def apply(self, payload):
        return cpu_money_downs_patch.apply(payload, level=self.level)

(cpu_money_downs != "retail", _cpu_money_downs_adapter(cpu_money_downs),
 "cpu_money_downs_patch", cpu_money_downs_patch.BUILD_CAPTION),
```

Before dispatch, reject an installed different level, including an installed
patch when Retail was requested. Use `read_settings(payload)` for that check;
rebuild from a verified base to change levels. The owner itself refuses a
level change, but a disabled tuple must not silently retain an installed patch.
Retain the existing refusal of foreign source bytes and strict union replay.

Add to `_grown_status_fields(payload)`:

```python
"cpu_money_downs": cpu_money_downs_patch.status(payload),
"cpu_money_downs_settings": cpu_money_downs_patch.read_settings(payload),
```

All **four** status dictionaries in `read_xbe`, `read_image`, `write_xbe_copy`
and `write_image_copy` must expand those fields. They already use
`_grown_status_fields`; retain those expansions. Add both keys to the
`mod_build.py` result-summary/status field list as well. Read actual installed
bytes for level reporting; do not echo the requested level as proof.

## BuildPlan, presets and final pass

In `mod_editor/core/mod_build.py`, add
`BuildPlan.cpu_money_downs: str = "retail"`. Basic, Advanced and Experimental
all explicitly set `"cpu_money_downs": "retail"`. Recommendation: Advanced
with Modern explicitly selected is Noah's first comparison build; no preset
should enable an unwitnessed feature automatically.

Add the module/allocator availability pair
`("cpu_money_downs", "nfl2k5_cpu_money_downs")`, string validation and
serialization. `_r62_plan_options` will forward the field through its key list.
In `wants_xbe_patch`, grown/final-pass conditions and copy-writer enable checks,
use `plan.cpu_money_downs != "retail"` (or the local equivalent). Normalize it
as a level string, preserving the selected level through preset overrides.
In the early `replace(plan, ...)` deferral near the first XBE pass, explicitly
set `cpu_money_downs="retail"`. Pass the actual level in the final `r62`
options after all PLAY/roster/position rewrites and before final receipt
inspection. It requires no authored intent table and writes no PLAY resource.
Preflight rejects a different installed level before copying a disc.

## Gameplay Patches and Build controls

The Gameplay Patches `PATCHES` row is:

```python
("cpu_money_downs", cpu_money_downs_patch.BUILD_CAPTION,
 cpu_money_downs_patch.HELP_TEXT),
```

Add `"cpu_money_downs"` to `NEEDS_IMAGE` for the shared disc-build UI. The
standalone development CLI can still inspect/write a bounded XBE. The help
text deliberately includes both **Retail** and **Patch**:

> EXPERIMENTAL / UNWITNESSED. Retail: the CPU uses its original fourth-down choices and passing preferences. Patch: Modern adds measured fourth-down attempts and favors supported primary routes and viable targets reaching the first-down line. Aggressive increases those preferences. Late tying and winning kicks keep retail decisions. Catches and conversions are not guaranteed. Retail is the default in every preset.

Special-case this row's value collection instead of converting its level to
bool. Use a combo with labels/data `Retail/retail`, `Modern/modern`,
`Aggressive/aggressive`, initially Retail. If the existing checkbox row is
retained, checking it selects Modern, unchecking selects Retail, and the combo
keeps the checkbox synchronized. Do not maintain a second BuildPlan Boolean.
Preset restore, source availability, plan construction and receipt display
must use the combo's string data. Apply the same behavior in the Build tab.

The Build `_option` caption is exactly
`CPU fourth downs and first downs (experimental)` (47 characters), with
`HELP_TEXT` and the unwitnessed badge. Add the adjacent three-level combo;
exclude this key from generic Boolean collection before assigning
`cpu_money_downs=combo.currentData()` to BuildPlan.

## Packaging, capability registry and production manifest

Append these lines to `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_cpu_money_downs.py
mod_editor/core/nfl2k5_cpu_money_downs_code.py
docs/mod_editor/nfl2k5_cpu_money_downs_capability.json
docs/mod_editor/nfl2k5_cpu_money_downs_replays.json
```

Retain already-listed `nfl2k5_gameplay_lever.py`, `nfl2k5_xbe_space.py`,
`nfl2k5_rdata_sites.py`, `nfl2k5_cave_oracle.py` and
`nfl2k5_playbook_inspector.py` with their existing dependency closure. Add
`mod_editor.core.nfl2k5_cpu_money_downs` and
`mod_editor.core.nfl2k5_cpu_money_downs_code` to the import closure in
`packaging/check_2k5_mod_studio_runtime.py`. GNU as, Capstone, Unicorn,
test fixtures and `.S` are development tools, not new runtime imports.

Merge the complete schema-valid object in
`docs/mod_editor/nfl2k5_cpu_money_downs_capability.json` into the registry as
`nfl2k5.gameplay.cpu_money_downs`, surface `gameplay_tuning_sliders`.
Keep `gui.default_enabled=false`, `classification=offline-writer-proved`,
`runtime.status=not-tested`, the EXPERIMENTAL / UNWITNESSED text and the bounded
evidence scope. Its executable commands are:

```text
python3 -m mod_editor.core.nfl2k5_cpu_money_downs --xbe source.xbe --apply --level modern --output new-money-downs.xbe
python3 -m tests.mod_editor.test_nfl2k5_cpu_money_downs
```

The gate union, budget fixture, actual writer observation and all relevant
manifest-builder owner lists already include this owner. Claude must regenerate
`data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after integration. The scratch projection
used here inherits historical reservations with seven known stale identities
refreshed for local checks; this is explicitly not new disc-build provenance.
Do not publish it. The dedicated owner projection observes the actual 17 hook
bytes, the full named child and allocator writes; it still inherits the other
owners' disc steps and requires production regeneration.

After wiring, exercise Retail/Modern/Aggressive plan round trips, invalid and
Boolean levels, early deferral, final union selection, four status surfaces,
level-change refusal, standalone capability validation and runtime closure.
No release version, tag, release tests, CI workflow or unrelated GUI changes
are requested by this job.
## R65 weekly preparation: protected integration, 2026-09-08

EXPERIMENTAL / UNWITNESSED. Implemented owner: `mod_editor/core/nfl2k5_weekly_prep.py`.
Native plan reader/writer: `mod_editor/core/nfl2k5_weekly_prep_save.py`.
Evidence and remaining limits: `ASTRA_WEEKLY_PREP_REPORT.md` and
`docs/mod_editor/weekly_preparation.md`. Safeties have a proved missing DB
filter; TE's valid row matches the backs and its reported deficit remains
unexplained. Do not advertise a proved TE-specific correction.

### Dispatcher and the four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`, import
`nfl2k5_weekly_prep as weekly_prep_patch`. Add Boolean keyword arguments
`weekly_prep=False`, `weekly_prep_cpu=False`, `weekly_prep_remember=False` to
`_apply_all`, `write_xbe_copy` and `write_image_copy`. Forward all three through
their callers and deferred/final passes. Validate exact bools, including direct
API calls. Treat either suboption as selecting the owner:
`weekly_prep = weekly_prep or weekly_prep_cpu or weekly_prep_remember`.

Add `weekly_prep` to `R62_SPACE_KEYS`, all three names to `R62_RUNTIME_KEYS`,
the validation helper and `_deferred_r62_options` handling. Add the owner flag
to `_selected_space_requests` and `_xbe_space_adapter`; append
`weekly_prep_patch.REQUESTS if weekly_prep else ()` to the complete request
union, and select scaleout when this flag is true. Reserve the full union
before any grown owner installs code. Add `weekly_prep` to every relevant
`defer_grown` and any-enabled check so an early pass cannot seal an incomplete
allocation directory.

Use this settings adapter, with `status` consulting the actual installed bytes:

```python
class _weekly_prep_adapter:
    status = staticmethod(weekly_prep_patch.status)

    def __init__(self, cpu, remember):
        self.cpu, self.remember = cpu, remember

    def apply(self, payload):
        return weekly_prep_patch.apply(payload, cpu=self.cpu, remember=self.remember)
```

Add this exact `_apply_all` owner tuple after the allocator entry:

```python
(weekly_prep, _weekly_prep_adapter(weekly_prep_cpu, weekly_prep_remember),
 "weekly_prep_patch", "Weekly preparation (experimental, unwitnessed)"),
```

Extend `_grown_status_fields(payload)` with these fields, deriving suboption
status from `weekly_prep_patch.read_settings(payload)` rather than requested
checkbox values:

```python
prep = weekly_prep_patch.read_settings(payload)
def prep_component(key):
    return ("foreign" if prep["status"] == "foreign" else
            "applied" if prep["status"] == "applied" and prep.get(key) else "retail")
# Merge into the existing return dictionary:
"weekly_prep": prep["status"],
"weekly_prep_cpu": prep_component("cpu"),
"weekly_prep_remember": prep_component("remember"),
"weekly_prep_settings": prep,
```

All four dictionaries already expand `_grown_status_fields`: `read_xbe`
with `payload`, `read_image` with `payload`, `write_xbe_copy` with `result`,
and `write_image_copy` with `after`. Verify all four expose these fields.
Changing CPU/remember settings in an installed owner raises a rebuild error;
do not turn that refusal into a success receipt. `apply(payload)` without
explicit options replays installed settings, while its clean-base defaults
enable both options. The product adapter must always pass explicit booleans.

### Build plan, presets and controls

In protected `mod_editor/core/mod_build.py`, add `BuildPlan` bool fields
`weekly_prep`, `weekly_prep_cpu`, `weekly_prep_remember`, all defaulting to
False. Explicitly set all three False in `softdrink_basic`,
`softdrink_advanced`, and `softdrink_experimental`. This is an opt-in feature
pending Noah's witness. Validate exact bools, normalize a selected suboption
to select `weekly_prep`, include the owner in `wants_xbe_patch()` and
availability, preserve all three fields through project serialization and
normalization, and forward them through inspection/build/final XBE passes.
Set all three False in any temporary `replace(plan, ...)` that defers grown
owners, then restore their requested values together in the final pass.
No additional archive resource is required.

In protected `mod_editor/gui/gameplay_patches_panel_qt.py`, add these
`PATCHES` rows and all three keys to `NEEDS_IMAGE`:

```python
("weekly_prep", "Fix safety drills (experimental)",
 "EXPERIMENTAL / UNWITNESSED. Retail: DB drills skip both safety positions. "
 "Patch: include safeties in the same drills as corners. TE drill rows already exist."),
("weekly_prep_cpu", "CPU teams prepare too",
 "EXPERIMENTAL / UNWITNESSED. Retail: CPU clubs skip weekly prep. Patch: run "
 "the native routine before their games with equal low full-drill time for "
 "starters and backups, then two rest days. Weekly Preparation must be On."),
("weekly_prep_remember", "Remember my weekly prep",
 "EXPERIMENTAL / UNWITNESSED. Retail: only marked repeat activities survive "
 "weekly cleanup and the next season clears the plan. Patch: keep valid "
 "activities and apply your saved plan before games until you change it. "
 "Weekly Preparation must be On. An empty plan does nothing."),
```

In protected `mod_editor/gui/build_panel_qt.py`, use `_option` captions
`Fix safety drills (experimental)` (32 chars), `CPU teams prepare too`
(21 chars), and `Remember my weekly prep` (23 chars). Each is under 60 chars.
Connect suboptions to the owner dependency and project settings. If the owner
is unchecked, uncheck its suboptions; checking a suboption checks the owner.
Keep the EXPERIMENTAL / UNWITNESSED help visible. The game's existing Weekly
Preparation Off switch stops automatic application immediately. The two
Build suboptions independently disable CPU/human automation on a rebuild.
Native cleanup can still remove an already applied CPU plan with CPU Off.

### Protected Franchise panel

In `mod_editor/gui/franchise_panel_qt.py`, optionally show the selected league
club's plan using `read_plan(franchise.to_bytes(), league_ordinal)`. Display
day, hours, activity ID or a verified localized label, target, repeat flag and
native state. Use the saved league ordinal, not a team database ID. Say
`No weekly plan saved. Create one in Weekly Preparation in the game.` for an
empty plan. Show `Applied for this game` for state 2. Never imply the Build
remember option itself is a flag in the save. Label the field `Saved weekly
plan`; automatic behavior depends on the installed XBE settings.

For any future plan editor, use `replace_plan`; it refuses state 2, unknown
state, malformed activities, unsupported hours/day and out-of-pool player
targets before mutation. Present that refusal. Pass the resulting body
through the panel's existing signed-copy container writer and verify readback.
`replace_plan` returns `signed=False` deliberately; signing happens only in
the existing writer. Do not write a companion JSON and call it saved in-game.
The existing native plans/state/seeds/snapshots/repeat bits are serialized by
the game, including after cold reload. No spare field, footer or new save
format is needed. Do not repurpose the career footer or native season tail.

### Packaging, capability and release validation

Add these lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_weekly_prep.py
mod_editor/core/nfl2k5_weekly_prep_code.py
mod_editor/core/nfl2k5_weekly_prep_save.py
docs/mod_editor/weekly_preparation.md
docs/mod_editor/nfl2k5_weekly_prep_capability.json
```

Add `mod_editor.core.nfl2k5_weekly_prep`,
`mod_editor.core.nfl2k5_weekly_prep_code`, and
`mod_editor.core.nfl2k5_weekly_prep_save` to the lazy runtime-closure import
list in protected `packaging/check_2k5_mod_studio_runtime.py`. These runtime
modules require only stdlib and existing shipped core modules. GNU assembler,
Capstone and Unicorn are development/test dependencies, not runtime imports.

Merge the complete object in
`docs/mod_editor/nfl2k5_weekly_prep_capability.json` into
`mod_editor/capabilities/registry.v1.json`. It uses the existing
`schedules_franchise` surface, classification `offline-writer-proved`, runtime
`not-tested`, and schema/file-check compatible `python3 -m` commands. Do not
promote it to a played witness based on instruction tests.
The draft passed strict registry rules and all of its new file/module checks.
Full file checking of the inherited registry currently stops at the missing
`docs/research/apf_audio.md`; resolve that pre-existing packaging/evidence
issue during integration as well.

The gate union, all manifest owner/request lists and the budget fixture are
already updated. The Auto Save prerequisite validator now accepts only a
fully recognized weekly-prep wrapper on the separate pre-simulation call.
Both owners retain their original complete validation. No MyCareer, read
option, ESPN or coverage-trail implementation was edited. The gate helper
resolves the existing Historic Reload public writer at call time so the
recorder sees the real byte edit instead of a captured unobserved adapter.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with the
normal `tools/nfl2k5_cave_oracle.py manifest` command after wiring. This work
uses an observed XBE-only scratch manifest for standalone ownership tests;
it is not a new disc build or release manifest. The system drive was already
below the 100 GB reserve, so no disposable disc was built. Re-run both XBE
gates, weekly-prep suites, Auto Save suites, registry checks and clean-stage
runtime closure after protected integration. Keep all features explicitly
experimental until Noah completes the report's witness list.

## R65 playbook pair: protected integration handoff

Owner `mod_editor/core/nfl2k5_playbook_pair.py`; generated template
`nfl2k5_playbook_pair_code.py`. EXPERIMENTAL / UNWITNESSED. See
`ASTRA_PLAYBOOK_PAIR_REPORT.md` for the native proof, limits, exact validation and
Noah's witness list. This branch implements the owner and gate integration; no
protected product file is edited.

This option is **explicit opt-in, off in Basic, Advanced and Experimental**.
Native choices start at Same as offense. It adds two adjacent Defensive playbook
rows to the two pregame Options lists, for human and CPU sides; special teams
stay with the offensive source. The choice lasts one game. The on-screen notice
plainly refuses Franchise persistence. No save field or 38th stock book is added.

### Dispatcher and four status dictionaries

In protected `mod_editor/core/nfl2k5_throw_tuning.py`:

1. Import `nfl2k5_playbook_pair as playbook_pair_patch`. Add boolean
   `playbook_pair=False` to `_apply_all`, `apply_to_xbe`, `apply_to_image`,
   `_validate_r62_options`, `_selected_space_requests` and `_xbe_space_adapter`.
   Add `playbook_pair` to both `R62_SPACE_KEYS` and `R62_RUNTIME_KEYS`, the boolean
   validation group, every relevant want/defer predicate, and `_r62_options` /
   `_r62_space_options` forwarding. Include it in the image `defer_grown` path.
2. `_selected_space_requests` appends `playbook_pair_patch.REQUESTS` when enabled.
   `_xbe_space_adapter` forwards the flag and selects scaleout when enabled.
   The union must be realized before **any** owner seals its allocation. The
   owner takes no settings and needs no custom adapter class.
3. Put this exact entry in the final `_apply_all` owners tuple after the allocator:

   ```python
   (playbook_pair, playbook_pair_patch, "playbook_pair_patch",
    "Separate offensive and defensive playbooks (experimental)"),
   ```

4. Add `"playbook_pair": playbook_pair_patch.status(payload)` to
   `_grown_status_fields(payload)`. Verify all **four** status dictionaries expose
   it: `inspect_payload` (around line 665), `plan_patch` result (around 794),
   `apply_to_xbe` result (around 1791), and `apply_to_image` result (around 2136),
   each already spreads `_grown_status_fields` for its actual output bytes.
5. Preserve the current intent-owner implementations. Until their identity
   lookups support composite roots, refuse `playbook_pair` together with
   `read_option_runtime` or `qb_spy` in user-facing builds, before output creation.
   Plain message: `Separate playbooks cannot be combined with custom read-option
   or QB-spy controls in this build. Turn one option off.` This is a semantic
   product constraint. The safety gates intentionally compose every executable
   owner to prove byte ownership, including empty/diagnostic intent tables;
   that is not a claim that authored controls operate on a relocated composite.

### BuildPlan and final image pass

In protected `mod_editor/core/mod_build.py`, add `playbook_pair: bool = False`.
Add explicit `playbook_pair=False` to every basic/advanced/experimental preset.
Forward through the existing r62 option maps, normalization/boolean validation,
`wants_xbe_patch`, core-module availability checks and result/status key lists.
Add `("playbook_pair", "nfl2k5_playbook_pair")` alongside the existing
Franchise Auto Save core-module availability pair. The initial `replace(plan,
...)` deferral around line 1259 must set it false; the final request union and
final XBE pass must retain the user's real value. Include it in final-pass
predicates around lines 1050/1620 and in `_grown_status_fields` result refreshes.
Use the existing grown-XBE disc writer; do not write 12,300,288 bytes into the
retail XBE's old extent. No archive or save writer is added.

Preserve the proposed intent incompatibility check in direct dispatcher calls
as well as BuildPlan normalization, so a raw XBE build cannot silently drop
those authored controls. The module's standalone CLI is an expert byte writer;
its HELP_TEXT, capability and report expose the limitation. No claim of automatic
Franchise team persistence should appear in a preset or receipt.

### Studio text, caption and packaging

In protected Gameplay Patches `PATCHES`, add key `playbook_pair`, default false,
with title `Separate offensive and defensive playbooks (experimental)` and
`nfl2k5_playbook_pair.HELP_TEXT`. The description must retain the literal words
**Retail** and **Patch**; the shipped helper already contains both. Add
`playbook_pair` to `NEEDS_IMAGE`. A source image supplies the stock PLAY resources
that the game will load. Include the key in signal/selection/application maps.
Use the same text in the equivalent protected Gameplay panel if it enumerates
these patches independently. Do not expose a new editor claiming a 38th book or
profile persistence.

In protected Build tab, `_option` caption is
`Separate offensive and defensive playbooks (experimental)` (57 characters).
Tooltip is HELP_TEXT. Default false; wire extraction/restoration of the boolean
alongside `franchise_autosave`. If studio_qt owns cross-panel option propagation,
forward this same key there; no new standalone GUI panel is needed.

Add these exact lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_playbook_pair.py
mod_editor/core/nfl2k5_playbook_pair_code.py
docs/mod_editor/nfl2k5_playbook_pair_capability.json
```

If feature reports are packaged, also include `ASTRA_PLAYBOOK_PAIR_REPORT.md`.
The C/S generator sources and test harnesses are development-only. In protected
`packaging/check_2k5_mod_studio_runtime.py`, runtime-closure imports are
`mod_editor.core.nfl2k5_playbook_pair` and
`mod_editor.core.nfl2k5_playbook_pair_code`; its existing xbe_space,
bump_strength and cave_oracle dependencies remain required. No GCC, GNU as,
Capstone, Unicorn or Ghidra is a product runtime dependency.

Merge `docs/mod_editor/nfl2k5_playbook_pair_capability.json` into the central
capability registry, ID `nfl2k5.gameplay.playbook_pair`, existing surface
`gameplay_tuning_sliders`, GUI default false, runtime status `not-tested`.
It has schema-valid `python3 -m ...` backend and validation commands. No release
version, updater, release-tag test or CI workflow change is needed for this job.

### Manifest and acceptance

The owner is already in `tests/nfl2k5_allocator_stack.py` REQUESTS/compose, both
XBE gates, the real manifest builder owner lists and the budget fixture. The
synthetic allocator stress test uses 40 KiB RX rather than 48 KiB to retain a
valid multi-page stress owner alongside the new budget. Other owners' budgets
and runtime code are unchanged.

The current drive is below the 100 GB free-space floor, so this job builds no
disposable disc. For bounded local ownership evidence, run:

```sh
NFL2K5_PLAYBOOK_PAIR_MANIFEST="$PWD/.scratch/playbook-pair-manifest.json" \
  python3 tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py
NFL2K5_CAVE_MANIFEST="$PWD/.scratch/playbook-pair-manifest.json" \
  python3 tests/mod_editor/test_xbe_patch_cave_references.py
NFL2K5_CAVE_MANIFEST="$PWD/.scratch/playbook-pair-manifest.json" \
  python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
python3 tests/mod_editor/test_xbe_patch_memory_writes.py
```

The first command observes actual current XBE writers, with current source
fingerprints and no inherited stale-source exemption. Its JSON explicitly says
XBE-only, no disc built, not a release manifest. Never copy it over the protected
release manifest. Once sufficient disk space exists, Claude must regenerate
`data/nfl2k5_cave_reservations.json` using the normal `tools/nfl2k5_cave_oracle.py
manifest <retail.xbe> --xiso <retail.iso> --work-dir <temporary-parent> --json
<protected-manifest>` path, after wiring the protected dispatcher and build
option. Keep every disposable disc in TemporaryDirectory and delete it on all
exits. Then rerun both gates and the owner/native suites. Noah's played-game
witness remains required before calling the feature witnessed.

## R65 match coverage: census, native Rules bundles and five-call pack

Branch: `astra/r65-match-coverage`. See `ASTRA_MATCH_COVERAGE_REPORT.md` and
`docs/mod_editor/match_coverage/README.md`. EXPERIMENTAL / UNWITNESSED. This is
PLAY authoring and offline documentation; there is no new XBE owner.

### Required integration and existing behavior

* Dispatcher `_apply_all` tuple: **no entry**. Kwarg: **none**. The four status
  dictionaries in `read_xbe`, `read_image`, `write_xbe_copy` and
  `write_image_copy` receive **no match-coverage key**. `_selected_space_requests`,
  `_xbe_space_adapter`, `_grown_status_fields` and allocator owner unions need
  no changes. Executable RX/RW/RO request is zero. Do not represent a PLAY pack
  as an installed executable patch.
* `BuildPlan`: use the existing `playbook_packs: tuple[str, ...] = ()` field.
  No new field, normalization, deferral or dispatcher pass. **Basic, Advanced
  and Experimental all leave this pack unselected**. The existing schema-v2
  defense-pack pass must remain before defensive personnel recoding, and the
  pack compiler must keep its preflight and final native menu checks.
* Gameplay Patches `PATCHES` and `NEEDS_IMAGE`: **no new row** because the
  existing Playbooks/Build pack option owns the action. If Claude adds a
  discovery-only explanation, use exactly: **"Retail: some calls exchange man
  and zone assignments. Patch: the optional match coverage pack adds five
  experimental calls built from those rules. Full Rip/Liz, quarters and Palms
  receiver keys are not implemented."** Such an action requires a loaded image
  (`NEEDS_IMAGE=True`); it must open the existing pack flow, not toggle a new
  gameplay boolean. No discovery UI is required for installation to work.
* Build tab `_option`: **no new checkbox or boolean**. Existing caption
  **"Playbook packs"** is 14 characters and its Add file picker already installs
  `data/playbooks/softdrink_match_coverage.2k5book`. Optional convenience button:
  **"Add match coverage experiments"** (30 characters), parallel to
  `_add_modern_defense_pack`, adding this exact path through
  `set_playbook_packs` with duplicate-path rejection. Keep the pack's full
  experimental notes visible; do not caption it "complete Palms" or "full Rip/Liz".
* Rules and Info are already connected through the existing wizard. Core
  `nfl2k5_play_rules.catalog` now adds structural match bundles, and the existing
  Info panel reads the new `match_coverage` section of `play_rules.json`.
  No GUI panel was edited. The existing pack dialog was exercised offscreen,
  including OAK retargeting and project save/reopen/recompile.
* Capability registry: merge the schema-valid object at
  `docs/mod_editor/match_coverage/capability.json` into
  `mod_editor/capabilities/registry.v1.json`. ID:
  `nfl2k5.scripts.match_coverage`; classification `offline-writer-proved`;
  runtime `not-tested`; default disabled. Both commands use `python3 -m`.
  On this base this changes 117 total / 79 NFL 2K5 entries to 118 / 80.
  Update only the applicable registry/provider count pins in the integration
  session; no release version/tag changes are part of this job.

### Release allowlist and runtime closure

Add these required lines to protected `packaging/release-allowlist.txt`:

```text
mod_editor/core/nfl2k5_match_coverage.py
tools/nfl2k5_match_coverage.py
data/playbooks/softdrink_match_coverage.2k5book
docs/mod_editor/match_coverage/
ASTRA_MATCH_COVERAGE_REPORT.md
```

The subtree includes 105 retail Studio diagrams, five authored-call diagrams,
the census JSON/CSV/table, the native evidence pins, compiler receipt, guide and
capability object. These are rendered diagrams and metadata, not retail PLAY,
XBE or Ghidra payloads. Keep `ASTRA_BRIEF.md` and `.scratch/` excluded.
Existing allowlist entries already cover the changed play rules reference and
both existing core modules.

In protected `packaging/check_2k5_mod_studio_runtime.py`, add closure imports:

```python
"mod_editor.core.nfl2k5_match_coverage",
"tools.nfl2k5_match_coverage",
```

The census/authoring core imports Qt only when rendering is requested through
the tool. The release already carries the existing FieldScene, play codec,
Rules/Info panels, book reader and pack compiler. Next to the modern-defense
seed check, load the new seed and require schema `packs.DEFENSE_SCHEMA`, five
plays, and a green source-free `packs.check_pack`. Do not render 110 images or
require retail inputs in packaged runtime closure checks. Add the new test
modules to any manual standalone acceptance list; CI's current glob discovers
both without editing the protected workflow.

### Capacity, preservation and proof boundaries

The five-call pack adds 122 nodes (976 bytes) and no formations; native team
books replace five coverage records. Editor/PRACTICE append five, preserving
all drills. It reserves all stock match-rule records and the ten modern-defense
destinations. OAK, reference and TEN select 4-3 when Nickel lacks five free
replacement destinations. Native personnel, category rows, geometry and
shared menu membership remain under the existing validators.

The census includes 59 records / 105 menus, including six nonreciprocal stock
calls. Do not "repair" these six while integrating this feature. Their live
behavior is unknown. The pack's Rip/Liz and Two Read names are experimental
intent, not claims of implemented modern #2 receiver keys. Full modern
matching remains explicitly outside the proved native vocabulary.

The protected cave reservation JSON is untouched. It will need Claude's normal
release regeneration because the source fingerprint list includes every
`nfl2k5_*.py`, including this new PLAY-only module and tool. The private
executable-only manifest produced by `test_nfl2k5_guardian_manifest.py` is for
XBE owner/gate checks and expressly has no disc-image step evidence. It must
not replace the release manifest.

The direct guardian-manifest test initially misses ESPN's first write at raw
`0xB2319` because `XbePatch.apply` is a prebound static alias of `apply_xbe` and
does not traverse the recorder's module-function wrapper. The scratch-only
adapter reproduced in `ASTRA_MATCH_COVERAGE_REPORT.md` temporarily routes that
alias through the same real writer; the unchanged test then passes with 277
current source pins, 105 observed writer calls and 10,603 reservations. No
ESPN source was changed. Account for this observer alias when Claude runs the
combined manifest builder; keep observing real writes rather than adding
unobserved reservations. The executable-only manifest leaves the cave oracle's
disc-step assertion unsatisfied (27/28 tests pass, missing `scorebug_runtime`
image-step evidence). Normal release-disc evidence and protected-manifest
regeneration are still required. Root free space was about 93 to 94 GiB, so
this session did not build a disposable disc.

Both unchanged XBE composition gates pass with that scratch manifest: memory
writes **95 tests** (1505.110 s, peak 339,944 KiB) and cave references **107
tests** (1374.999 s, peak 522,428 KiB), covering both installation orders and
allocator configurations. The cave-reference result is a dedicated retry;
the first parallel attempt terminated with status 143 before any test output.
No test failure is inferred from that terminated attempt. This PLAY-only
feature needs no executable owner added to either gate or allocator union.
## ASTRA read option v5: loaded identity and cancelable native handoff

This section supersedes the read-option v3/v4 control text and the claim that
normal v3 bytes remain unchanged. See `ASTRA_READ_OPTION_V5_REPORT.md`.
EXPERIMENTAL / UNWITNESSED; all preset defaults remain off. Protected files
were left untouched. No new owner, surface, BuildPlan field or allocation is
needed. Rebuild old v1-v4 executables from the supported base.

Keep the existing `_apply_all` tuple after the allocator:

```python
(read_option_runtime, _read_option_adapter(read_option_intent_table),
 "read_option_runtime_patch", "read option mesh controls (experimental)"),
```

Retain kwargs `read_option_runtime=False` and
`read_option_intent_table=None`, their strict Boolean/bytes validation,
`R62_SPACE_KEYS`, `R62_RUNTIME_KEYS`, `_selected_space_requests` and
`_xbe_space_adapter` forwarding. The adapter passes
`read_option_patch.apply(payload, intent_table=self.table)`. Its existing
request row remains 2048 RX / 256 RW / 88 RO with two 24-byte records in a
64-byte table. No allocator fixture change is needed.

For the next explicitly instrumented witness build, use the existing scoped
adapter technique to call `apply(..., diagnostic=True)` during the final
installation. The development CLI also accepts `--diagnostic`. Both variants
now report `model_version=5`; inspect `diagnostic` separately. Do not enable a
new preset or rely on an in-place variant conversion. The diagnostic gives on
CPU plays; the normal variant retains the CPU edge read.

All four status dictionaries (`read_xbe`, `read_image`, `write_xbe_copy`,
`write_image_copy`) must continue merging `_grown_status_fields(payload)`:

```python
"read_option_runtime": read_option_patch.status(payload),
"read_option_runtime_settings": read_option_patch.read_settings(payload),
```

Settings now include the loaded-book identity model, explicit human controls,
`diagnostic`, `model_version=5` and the unchanged reservation/table counts.
The existing screen-hook and abilities status fields remain their own owners.
V5 validates the complete abilities owner before accepting its hook at the
shared native animation entry `0x1CD550`. The read runtime does not own that
entry; it adds only the handoff exchange hook `0x313520..0x313526`.

Keep `BuildPlan.read_option_runtime: bool = False`. Basic, Advanced and
Experimental all keep it false; explicit selection is required. Keep the first
XBE pass deferred with `read_option_runtime=False` and the owner requests
reserved. After the last PLAY writer, execute `resolve_final_pairs`, then
`compile_intent_table`, then install the resulting table in the final XBE
pass. Do not derive a key from menu ordinal 48. The v5 receipt adds
`identity_model=loaded_team_book_fingerprints/v5`,
`diagnostic_index=final_resource_index` and per-record `identity_matches`,
`plays_checked`, `diagnostic_index`. Retain these fields in the final pairing
receipt; the compiler refuses duplicate live fingerprints even when the
original resource slot still matches. The table bytes and maximum count stay
compatible with the final bo book.

Gameplay Patches keeps the existing `read_option_runtime` PATCHES row and
NEEDS_IMAGE membership. Use current `nfl2k5_read_option_runtime.HELP_TEXT`;
it contains both **Retail** and **Patch**. It must say: do nothing gives;
Xbox Black pulls and pitches; release A after snapping and press A again to
pull and keep; X or the named receiver pulls and passes on RPO. The old
hold-through-to-keep and EDGE-icon instructions are obsolete. The Build tab
`_option` caption remains `Read option mesh controls (experimental)`
(40 characters, below 60), default false, with the updated HELP_TEXT. Pack
cards use updated `OPTION_NOTICE` and the regenerated recipe pack 1.0.2.
No PLAY scripts changed.

Keep/add these exact release-allowlist lines, without duplicates:

```text
mod_editor/core/nfl2k5_read_option_runtime.py
mod_editor/core/nfl2k5_read_option_runtime_code.py
mod_editor/core/nfl2k5_play_intents.py
mod_editor/core/nfl2k5_play_library.py
mod_editor/core/nfl2k5_playbook_pack.py
data/playbooks/softdrink_option.2k5book
docs/mod_editor/nfl2k5_read_option_runtime_capability.json
```

The runtime-closure import list must contain these dotted modules:

```python
"mod_editor.core.nfl2k5_read_option_runtime",
"mod_editor.core.nfl2k5_read_option_runtime_code",
"mod_editor.core.nfl2k5_play_intents",
"mod_editor.core.nfl2k5_play_library",
"mod_editor.core.nfl2k5_playbook_pack",
"mod_editor.core.nfl2k5_abilities_runtime",
"mod_editor.core.nfl2k5_abilities_runtime_code",
"mod_editor.core.nfl2k5_screen_hooks",
"mod_editor.core.nfl2k5_xbe_space",
```

The abilities, screen hooks, allocator, codec, formation compiler, position
pool and depth-role dependencies already ship; preserve their existing
closure entries. Keep the existing capability ID
`nfl2k5.gameplay.read_option_runtime` on `gameplay_tuning_sliders`, using the
updated capability JSON. Its backend and validation commands remain dotted
`python3 -m ...` commands. There is no new capability surface.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with the
real `tools/nfl2k5_cave_oracle.py manifest` after integration and sufficient
disk capacity. The scratch projection observes the current bounded XBE union
and final PLAY compiler, and explicitly inherits historical disc-only fields;
it is not a new production disc build. It reserves the seventh hook and
retains source fingerprint checks. No protected manifest or dispatcher file
was changed by this task, and no image copy was built below Noah's 100 GB
free-space floor.

The same dependency-validation path also accepts defensive try's complete,
sealed `cpu_return` hook at `0x2E3786`; preserve the existing
`mod_editor.core.nfl2k5_defensive_try` closure entry. Human cancellation stays
available until the native exchange event, including a delayed mesh past one
second. The reported one-second interval is the CPU read's fallback deadline.

During production manifest observation, also route the existing
`espn25.XbePatch.apply` static adapter through the recorder's wrapped
`espn25.apply_xbe`. The adapter captures the function at import time; wrapping
only the module entry misses its first write at `0xC2319` and observes only
later no-op replays. The v5 scratch fixture observes that adapter explicitly
and requires nonzero writes from each changed XBE owner. This is a recorder
integration note; no ESPN implementation changed here.

V5 waits through native snap reception before starting GIVE/TAKE. The snap
hook precedes actual ball transfer, and the QB receive callback may already
advance to the condition while the ball is in flight. The diagnostic shows
`READ <resource> snap` during that interval, then `pend` when the QB receives
the ball and starts the handoff. No extra dispatcher setting is required.
# r65 Franchise 2026 runtime audit, 2026-09-08

**EXPERIMENTAL / UNWITNESSED. Runtime activation remains blocked.** This
section supersedes the r62 handoff's save-ownership assumptions, not its
readiness guard. `ASTRA_FRANCHISE_2026_RUNTIME_REPORT.md` records fresh native
counterexamples with MyCareer mode 5, reserve growth and the dormant rules
owner installed together. No protected file or other owner's runtime module
was edited. The Guardian manifest test now observes the existing Anniversary
adapter's cached writer, retaining strict attribution of every changed byte.

## Decision and required integration

`RUNTIME_READY` stays false. The three owners install in all six orders, but
native saves do not serialize the rule ledger and competitive staging still
copies 53 active players. A different selection in RW changes neither result.
The complete retail C5280 resolver maps a reordered/elevated match record to
the permanent player in the same roster slot. Changing only the readiness
flag would advertise enforcement and introduce incorrect result ownership.

MyCareer owns a fixed 128-byte footer, including its required-zero bytes.
Its admission/staging code accepts only native sizes 720044/724140 and career
sizes 720172/724268. Adding 4096 to 720044 aliases the grown-roster length;
the complete framing check still refuses a ledger masquerading as that arena.
The grown arena owns its 352-byte overflow block and retains the native
auxiliary tail. An empty byte is not an allocation. Guardian owns +0x53 bit 5;
only bits 6-7 remain unassigned, and this owner claims neither.

A future activation needs a coordinated save format and native transport
across the size/admission/read/serialize/restore/signing boundaries, preserving
both existing footer and arena versions. It also needs generation-aware pool
clear/import/retirement handling, a competitive projection with identity-aware
result/stat/injury/award/depth writeback, accepted game/retry/cancel/completion
events, and the R1-R5 IR/calendar/CPU decisions. The existing C selector has a
65-entry input ABI; a native 70-player adapter must explicitly handle overflow.
No allocation or runtime interception for that future format is installed here.

## Dispatcher, BuildPlan and four status dictionaries

The base already has this exact `_apply_all` tuple in
`mod_editor/core/nfl2k5_throw_tuning.py`, after the allocator:

```python
(franchise_2026_rules, _franchise_2026_adapter(),
 "franchise_2026_rules_patch", "2026 franchise rules (unavailable)"),
```

Keep the `_apply_all(..., franchise_2026_rules=False)` kwarg, and forward it
through the extracted/image writers and Build final pass. Preserve
`_franchise_2026_adapter.status -> "unavailable"` and its guarded apply:

```python
franchise_2026_patch.require_runtime_ready()
return franchise_2026_patch.apply(payload)
```

`_validate_r62_options` must continue to refuse true requests before copy,
allocation or dispatch. `_selected_space_requests` and `_xbe_space_adapter`
retain the flag and `franchise_2026_patch.REQUESTS`; no new owner or request
is added. Requests remain 5120 RX / 4096 RW at alignment 16, within the
8192 RX / 4096 RW budget. Gate union, manifest owner lists and budget fixture
already contain the real rows, so no duplicated entries are needed.

`mod_editor/core/mod_build.py`: retain
`BuildPlan.franchise_2026_rules: bool = False`; Basic, Advanced and Experimental
all set it false. Keep availability tied to `RUNTIME_READY`, normalization
through the readiness preflight, temporary deferral to false, and the final
pass kwarg `franchise_2026_rules=plan.franchise_2026_rules`. No enabled preset
or new Build field is justified by this audit.

Keep these fields in `_grown_status_fields`, consumed by all four dictionaries:
`read_xbe(payload)`, `read_image(payload)`, `write_xbe_copy(result)` and
`write_image_copy(after)` (the parentheses identify each local byte variable):

```python
"franchise_2026_rules": "unavailable",
"franchise_2026_kernel": franchise_2026_patch.status(payload),
"franchise_2026_runtime_enforced": False,
```

Do not use the kernel's `applied` status as evidence of game enforcement. The
new `--assess-save` and extended `--assess-xbe` commands remain inspection APIs.

## Gameplay Patches and Build caption

The shared `mod_editor/gui/beta62_options.py` is another owner's GUI helper,
so this session leaves it untouched. Claude should replace its stale
`FRANCHISE_HELP` definition with:

```python
FRANCHISE_HELP = tt.franchise_2026_patch.UI_TEXT
```

That supplies this precise PATCHES help through the existing OPTIONS row:

> Retail: Owned players form the game roster and IR has no in-season returns. Patch: 2026 rule kernel is EXPERIMENTAL / UNWITNESSED. Game enforcement is unavailable: the MyCareer save block and reserve storage do not own these counters, and player results still need mapping.

Keep PATCHES key `franchise_2026_rules`, its membership in `NEEDS_IMAGE`, and
its disabled state through `UNAVAILABLE`. Keep the Build `_option` key and
caption `2026 franchise rules (unavailable)` (34 characters, below 60), with
the same help. No additional panel, native menu or user-facing setting is added.

## Allowlist, runtime imports, registry and manifest

Retain these existing allowlist lines:

```text
mod_editor/core/nfl2k5_franchise_2026.py
mod_editor/core/nfl2k5_franchise_2026_code.py
docs/mod_editor/nfl2k5_franchise_2026_capability.json
```

If shipping the feature report, add exactly:

```text
ASTRA_FRANCHISE_2026_RUNTIME_REPORT.md
```

Tests and `tools/franchise_2026/refresh_gate_manifest.py` are development-only;
they are not runtime-closure imports. The updated inspector imports these
already shipped modules, which Claude should retain/check in
`packaging/check_2k5_mod_studio_runtime.py` and the provider closure:

```text
mod_editor.core.nfl2k5_franchise_2026
mod_editor.core.nfl2k5_franchise_2026_code
mod_editor.core.nfl2k5_franchise_save
mod_editor.core.nfl2k5_save_rost
mod_editor.core.nfl2k5_my_career_save
mod_editor.core.nfl2k5_roster_arena
mod_editor.core.nfl2k5_abilities_runtime
mod_editor.core.nfl2k5_guardian_overlay
mod_editor.core.nfl2k5_player_star
```

Refresh the changed core source hash with the existing provider pin process.
The canonical registry row already exists. Replace that row's contents with
the revised `docs/mod_editor/nfl2k5_franchise_2026_capability.json`, retaining
ID `nfl2k5.schedules_franchise.rules_2026_inspection`, `read-only-mapped`,
hidden view mode and `runtime.status="not-tested"`. There is no new surface
or count change. Backend and validation commands remain
`python3 -m mod_editor.core.nfl2k5_franchise_2026 --self-check`.

Claude must regenerate `data/nfl2k5_cave_reservations.json` after integration.
The scratch revalidation tool verifies all changed parent pins against beta-62,
proves this owner's output equals its pinned implementation at two placements,
observes the base's changed native owners, retains historical reservations and
uses the existing strict named-allocation projection. Its disc fields are
explicitly historical; no new disc was built. Never publish that test manifest
as the release manifest. For oracle and owner suites that read the manifest,
use `NFL2K5_CAVE_MANIFEST=.scratch/franchise-runtime-manifest.json`.
## R65 scorebug freeze v2, 2026-09-08

See `ASTRA_SCOREBUG_FREEZE_V2_REPORT.md` and the updated
`docs/mod_editor/nfl2k5_scorebug_runtime_capability.json`. This section supersedes
earlier scorebug runtime repair claims and handoff text. The new binding revision
is 5; its resource contract remains `scorebug-runtime-v4-scoped-fonts` because
the compiler, texture atlas, FONTs and SCNE bytes have not changed.

The reproduced entry stall comes from the runtime binding hook searching all
resource collections, which can evict an unrelated cached texture and wait on
its GPU fence before HUD initialization finishes. The fixture supplies that
cache state and withholds GPU completion. This proves a native failure path
and its removal, not the identity of the testers' actual heap or an intrinsic
deadlock with a healthy GPU. Keep EXPERIMENTAL / UNWITNESSED and all runtime
presets off until Noah's played comparison. Keep all six diagnostic profiles.

### Dispatcher and four status dictionaries

The existing integration is sufficient; preserve it when merging other owners.
In `mod_editor/core/nfl2k5_throw_tuning.py`, keep the import
`from . import nfl2k5_scorebug_runtime as scorebug_runtime_patch` and the exact
final `_apply_all` tuple after the allocator adapter:

```python
(scorebug_runtime, scorebug_runtime_patch, "scorebug_runtime_patch", "experimental scorebug effects"),
```

Keep `scorebug_runtime: bool = False` in `_apply_all`, `write_xbe` and
`write_image`, forwarding `scorebug_runtime=scorebug_runtime` to final applies.
The image's early pass deliberately passes false while the grown owners are
deferred. `_selected_space_requests(runtime=scorebug_runtime, ...)` must include
`scorebug_runtime_patch.REQUESTS`; `_xbe_space_adapter` must reserve that same
complete union before owner installation. No new adapter, owner or kwarg is
needed. Code/state requests remain 1,408/128 bytes, both aligned to 16.

Preserve these four dictionary entries, evaluated against the final bytes at
the write surfaces (line numbers refer to the r65 base):

| Surface | Runtime entry | Static companion entry |
| --- | --- | --- |
| XBE inspect, line 668 | `"scorebug_runtime": scorebug_runtime_patch.status(payload)` | `"scorebug_xbe": scorebug_reference.xbe_status(payload)` |
| Image inspect, line 797 | `"scorebug_runtime": scorebug_runtime_patch.status(payload)` | `"scorebug_xbe": scorebug_reference.xbe_status(payload)` |
| XBE write result, line 1794 | `"scorebug_runtime": scorebug_runtime_patch.status(result)` | `"scorebug_xbe": scorebug_reference.xbe_status(result)` |
| Image write result, line 2139 | `"scorebug_runtime": scorebug_runtime_patch.status(after)` | `"scorebug_xbe": scorebug_reference.xbe_status(after)` |

Keep image resource status separately:
`"scorebug_runtime_resources": scorebug_reference.runtime_image_status(path)`
for inspection and the same call with `target` after writing. Preserve the
resource/installation receipt under `scorebug_runtime_patch`. An old generated
hook installation now reports `foreign` and asks for a supported-base rebuild;
do not treat an unchanged v4 resource profile as proof that its XBE is current.

### BuildPlan and presets

Keep `BuildPlan.scorebug_runtime: bool = False`. Basic, Advanced and Experimental
all set `scorebug_runtime` false. The separate blank-folder static `scorebug`
option stays false in Basic/Advanced and true in Experimental, selecting v3.
Manual runtime selection implies `scorebug=True, xbe_space=True`. A painted
`scorebug_folder` still cannot be combined with runtime. These are existing
rules, not new controls.

Preserve runtime deferral in `mod_build._build`. Skip the earlier static
resource apply when runtime is selected, calculate `all_requests` once, then
call `nfl2k5_scorebug_ingame.runtime_apply_in_place` with that union (excluding
runtime/kickoff rows already added by that adapter). Replay any other selected
owners in the final `_apply_all` pass with `scorebug_runtime=True`. Applying
the static v3 XBE before or after runtime is byte-identical; do not run a static
resource overwrite over the runtime collection. `inspect_source` keeps the
runtime, static-XBE and image-resource statuses already present.

### Gameplay Patches and Build captions

Keep the PATCHES row in `gameplay_patches_panel_qt.py`:

```python
("scorebug_runtime", "Scorebug effects (diagnostic only)", r62_ui.SCOREBUG_RUNTIME_HELP),
```

Retain `scorebug_runtime` in `NEEDS_IMAGE`. Claude should replace the shared
`SCOREBUG_RUNTIME_HELP` in `mod_editor/gui/beta62_options.py` with this plain text
(that shared GUI file was not edited in this worktree):

> Retail: Uses the original team panels and text. Patch: Adds team gradients,
> logos, live timeout marks, resized text, a white possession marker and room
> for three-digit scores to the experimental scorebar. Diagnostic only and off
> in every preset. EXPERIMENTAL / UNWITNESSED. The entry-stall repair still needs
> a game check. Keep the six probe choices and rebuild from a clean source.

Keep the Build `_option` caption `Scorebug effects (diagnostic only)`
(34 characters, below 60), its existing help constant and `needs_image=True`
availability gate. Do not announce the community freeze as witnessed or fixed.

### Packaging, capability and gates

Existing allowlist entries cover the production change and its import closure:

```text
mod_editor/core/nfl2k5_scorebug_runtime.py
mod_editor/core/nfl2k5_scorebug_resources.py
mod_editor/core/nfl2k5_scorebug_fonts.py
mod_editor/core/nfl2k5_scorebug_ingame.py
mod_editor/core/nfl2k5_scorebug_exact.py
mod_editor/core/nfl2k5_scorebar_v3.py
mod_editor/core/nfl2k5_xbe_space.py
tools/nfl2k5_scorebug_reference.py
docs/mod_editor/nfl2k5_scorebug_runtime_capability.json
```

No new production import or bundled game data is required. Keep runtime-closure
imports of `mod_editor.core.nfl2k5_scorebug_runtime`,
`mod_editor.core.nfl2k5_scorebug_resources`,
`mod_editor.core.nfl2k5_scorebug_ingame`,
`mod_editor.core.nfl2k5_scorebug_fonts`,
`mod_editor.core.nfl2k5_scorebug_exact`,
`mod_editor.core.nfl2k5_scorebar_v3` and
`mod_editor.core.nfl2k5_xbe_space` in the runtime checker. The old-code fixture,
entry harness and trace are development evidence; they need no runtime import.
If release feature reports/evidence are bundled, add explicit allowlist lines
for `ASTRA_SCOREBUG_FREEZE_V2_REPORT.md`,
`docs/scorebug_ingame/freeze_v2/trace.json` and
`docs/scorebug_ingame/freeze_v2/validation.json`.

No new capability ID or surface. In `mod_editor/capabilities/registry.v1.json`,
replace the existing `nfl2k5.scorebug_presentation.runtime` object with the
updated capability JSON handoff. Keep `classification=offline-writer-proved`,
`runtime.status=not-tested`, `gui.default_enabled=false` and the diagnostic
caption. Backend command remains
`python3 -m tools.nfl2k5_scorebug_reference apply --runtime`; validation becomes
`python3 -m tests.mod_editor.test_nfl2k5_scorebug_freeze_v2`. File-check validation
must use the full registry with this object replaced, not the handoff list alone.
The 117-entry replacement passes schema validation here, and every path and
command module in the changed object exists. Full-registry file checking stops
on the base's unrelated missing `docs/research/apf_audio.md`; restore the
release evidence before claiming that broader check passes.

Runtime and static v3 already belong to the allocator stack and both XBE gates.
The static adapter is now reusable and both are explicitly in the pairwise
matrix. The manifest builder's owner/request lists already include runtime;
no request or reservation change is needed. Claude must regenerate the protected
`data/nfl2k5_cave_reservations.json` with the normal
`tools/nfl2k5_cave_oracle.py manifest` command after integration. This session's
scratch manifest only refreshes stale source fingerprints while retaining the
base spans; the gate fixtures also project their current owner union. That is
not a regenerated production manifest. Do not copy it into the protected file.

Two existing owner-manifest harness issues also need integration attention.
`test_nfl2k5_read_option_diagnostic_manifest.py` imports `DEFAULT_MANIFEST`
directly and ignores `NFL2K5_CAVE_MANIFEST`; honor the environment as the other
manifest suites do. This session supplies that constant through a scratch
runner without changing the test or its assertions.

The Guardian observer misses raw offset `0xb2319` (VA `0xc2319`) because the
existing historic-team `XbePatch.apply = staticmethod(apply_xbe)` caches its
writer before observation. In the excluded `nfl2k5_espn25_rosters.py`, Claude
should make that adapter resolve `apply_xbe` when called:

```python
@staticmethod
def apply(payload):
    return apply_xbe(payload)
```

The module is unchanged here. A scratch runner forwards only that class alias
to the same actual module writer; the complete original Guardian observer test
then passes with every final byte attributed. No reservation or assertion is
waived. Both scratch runner sources and the original failures are preserved in
`docs/scorebug_ingame/freeze_v2/validation.json`. The reusable static scorebar
test adapter also forwards dynamically so its writes remain observable.
## r65 7-on-7 practice v2, 2026-09-08

This section supersedes earlier 7-on-7 descriptions of sideline parking and
forced Power Pocket. The owner and its standalone tests are implemented on
`astra/r65-seven-on-seven-v2`. Product status is **EXPERIMENTAL / UNWITNESSED**.
The protected edits below are the remaining integration work for Claude.

### Dispatcher, allocator and four status dictionaries

`mod_editor/core/nfl2k5_throw_tuning.py` already imports
`nfl2k5_seven_on_seven as seven_on_seven_patch`. Keep the `_apply_all` kwarg
`seven_on_seven: bool = False` and this existing tuple:

```python
(seven_on_seven, seven_on_seven_patch, "seven_on_seven_patch", "7-on-7 practice"),
```

Add `"seven_on_seven_patch"` to the tuple of receipt keys whose exact applied
state calls `module.apply(patched)` again. Its v2 replay is now idempotent and
returns `changed_bytes=0`, `version=2`, `experimental=True`, `witnessed=False`.
Keep the existing Boolean forwarding from `write_copy` and `write_image_copy`.
Keep all four status dictionaries, in `read_xbe`, `read_image`,
`write_xbe_copy`, and `write_image_copy`, reporting the same expression:

```python
"seven_on_seven": seven_on_seven_patch.status(payload),
```

Use each function's existing payload variable (`payload`, `result`, `after`).
All four entries already exist; this is an audit requirement, not a second
status key. The owner rejects mixed v1/v2 code and stale section digests.
Rebuild old installations from their base.

`REQUESTS=()` is intentional: v2 retains the existing, reserved 240-byte cave
at `0x1AC170..0x1AC260` and the one-byte writable flag at `0xA69970`. It allocates
zero additional RX/RW/RO bytes, so `_selected_space_requests`,
`_xbe_space_adapter`, `_grown_status_fields`, the budget fixture and allocator
page counts need no new rows. The complete test union and manifest builder
explicitly include the owner; both safety gates install it through that union
in both orders. The retired Power Pocket sites are dependencies, not writes.

### BuildPlan, availability, presets and receipts

In `mod_editor/core/mod_build.py`, retain `BuildPlan.seven_on_seven: bool = False`
and its disc-image requirement. Change `SEVEN_ON_SEVEN_RELEASED` to `True` to
make the existing opt-in available. Replace its obsolete hold comment with:

```python
#: 7-on-7 v2 is available as an EXPERIMENTAL / UNWITNESSED disc-image opt-in.
#: All presets leave it off; Noah must witness huddle break and repeated snaps.
SEVEN_ON_SEVEN_RELEASED = True
```

Keep `seven_on_seven=False` in **Basic, Advanced and Experimental**. Update the
BuildPlan field comment to describe retail line spots, offensive pass sets,
three idle defensive linemen and one end with a requested four-second delay.
Availability still requires both owner modules. Existing inspection returns
`seven_on_seven` for XBE and `seven_on_seven_book` for the resource.

Keep the resource order: position-pool recode, kickoff writers, 7-on-7 book,
other selected playbook packs, then depth roles. The book now accepts exactly
four source states: `retail`, `recoded`, `retail_depth_roles`, and
`recoded_depth_roles`. Every ordering of pools, roles and 7-on-7 has the same
final bytes. Four complete v2 output hashes allow exact replay after the final
role pass. Foreign routes, links, padding, wrappers and v1 books refuse.
The final result must report both owner and book as `applied`.

Add `"seven_on_seven_patch"` beside `"seven_on_seven"` in the XBE step receipt
filter. Retain the existing `seven_on_seven_book` step; its receipt now includes
version, experimental/witness flags, exact hashes, changed-byte count and
fixed resource offset. There is no new normalization or deferred allocator
pass for this owner.

### Gameplay Patches and Build controls

In `mod_editor/gui/gameplay_patches_panel_qt.py`, keep the existing PATCHES key
`seven_on_seven`, replace its description with the following complete text,
and add `"seven_on_seven"` to `NEEDS_IMAGE`:

> Retail: Practice offers Special Move, Full Scrimmage, Offense Only and
> Kickoff. Patch: Practice > Scrimmage > Practice Type gains 7-On-7. Both teams
> use the practice book, with Trips, Spread and Ace passing sets, nine pass
> plays and six coverages. Eleven players still appear on each side. The
> offensive line uses normal pass blocks; three defensive linemen wait at
> normal line positions. One defensive end is assigned a four-second delay
> before rushing. Power Pocket stays your choice; turn it Off to test the
> delayed rush. Needs a disc image. EXPERIMENTAL / UNWITNESSED: huddle break,
> repeated snaps and the actual delay still need Noah's play test.

Use this LABELS row so the qualification stays visible outside Details:

```python
"seven_on_seven": (
    "7-on-7 practice (experimental)",
    "Retail line positions with passing sets and a delayed end rush. UNWITNESSED.",
    NOT_TESTED,
),
```

Changing the release flag makes the existing conditional PATCHES filter retain
this row. In `mod_editor/gui/build_panel_qt.py`, use:

```python
self.seven_on_seven_check = self._option(
    f, "seven_on_seven", "7-on-7 practice (experimental)",
    "Practice Type 7-On-7, retail line positions and a delayed end rush. UNWITNESSED.",
    badge=NOT_TESTED, needs_image=True,
)
```

The caption is 30 characters, below 60. The existing Build-plan round trip,
availability gate and receipt summary already use this Boolean. Update
`test_ux_build_plan_coverage_qt.py`'s historical disabled-in-this-release
assertion: the row is reachable and enabled for a supported image, defaults
off, remains disabled for a bare XBE, and keeps the unwitnessed badge. This is
an existing Build/Gameplay surface; it introduces no new registry ID or count.

### Packaging, runtime closure and manifest

The required allowlist lines already exist:

```text
mod_editor/core/nfl2k5_seven_on_seven.py
mod_editor/core/nfl2k5_seven_on_seven_book.py
mod_editor/core/nfl2k5_depth_roles.py
```

The runtime import closure must retain:

```python
"mod_editor.core.nfl2k5_seven_on_seven",
"mod_editor.core.nfl2k5_seven_on_seven_book",
"mod_editor.core.nfl2k5_depth_roles",
```

The first two explicit imports already exist. Add the depth-role module to
that explicit list; the current release already includes its source. No assembler, research
file, retail binary, test fixture or scratch manifest is a runtime dependency.
Refresh provider/runtime source pins with the integration workflow; their
protected manifests are not edited here.

Regenerate `data/nfl2k5_cave_reservations.json` using the normal real-disc oracle
command after integrating these protected edits and satisfying the disk floor.
The scratch manifest for this job observes the actual complete XBE gate stack,
checks source fingerprints and rejects unattributed bytes. It proves executable
ownership only. Its `image_steps=[]` and model explicitly exclude a disc/resource
build. It must not replace the production manifest. The real-disc builder now
also includes v2 in its request/installation/status lists. Its dormant book
attempt should report `applied` on the supported depth-role source, rather than
the old foreign-book refusal.
## MyCareer M3: draft, preparation and upgrades (2026-09-08)

This section supersedes earlier MyCareer statements that the draft is a
placeholder or that its reservation is 8 KiB. EXPERIMENTAL / UNWITNESSED.
No protected file was edited in this worktree. The existing generic owner,
not another toggle, carries M3. Senior Bowl remains preparation only.

### Dispatcher and BuildPlan

In `mod_editor/core/nfl2k5_throw_tuning.py`, change the MyCareer term in
`_selected_space_requests` from `my_career_patch.REQUESTS` to
`my_career_mode_patch.REQUESTS`. It must reserve all three rows before any
owner installs: `nfl2k5_my_career/code/16384/16`,
`nfl2k5_my_career/data/4096/16`, and
`nfl2k5_my_career_m3/data/4096/16`. Reserving the extra row for a legacy
prepared-save setup is harmless. The current protected selector omits that
row, so a generic Build using it correctly refuses until this line is wired.
Keep `_xbe_space_adapter(..., my_career=my_career)` and the existing
`R62_SPACE_KEYS` / `R62_RUNTIME_KEYS` entries. No new boolean is needed.

Retain the final `_apply_all` owner tuple, after the allocator:

```python
(my_career, _my_career_adapter(my_career_setup),
 "my_career_patch", "MyCareer (experimental)")
```

The adapter continues to call `my_career_mode_patch.apply(payload)` when
`my_career_setup is None`, otherwise the legacy prepared-save adapter.
Keep both `my_career=` and `my_career_setup=` kwargs through the build final
pass and all deferral/normalization paths. For generic MyCareer opt-in,
enable the existing `draft_ai` option before allocation; this reuses its
ratings/need implementation and receipt, with no new draft-AI patch here.
Both fully retail and fully applied draft-AI bytes remain recognized for
standalone component use; partial or foreign bytes refuse.

Keep `"my_career": my_career_patch.status(payload)` in
`_grown_status_fields`. Its generic dispatch validates M3's entire code,
hooks, both zero-initialized RW blocks, and companion contexts. Preserve
the expansion in all four dictionaries: `read_xbe(payload)`,
`read_image(payload)`, the XBE write result (`result`) and image write result
(`after`). Preserve the existing `draft_ai` status entry in each dictionary.

In `mod_editor/core/mod_build.py`, retain `BuildPlan.my_career: bool = False`
and `BuildPlan.my_career_setup: str | None = None`. Basic, advanced and
experimental presets all keep MyCareer **off**; explicit user opt-in selects
M3. Preserve the optional legacy setup validation, wants-XBE decision,
grown-owner deferral and final pass. The generic path needs no setup file.
Use the complete M3 request union above in any duplicated budget selector.
Do not turn on native Senior Bowl simulation as a dependency.
Do not add arena growth as a MyCareer dependency: the inherited CAP admission
guard still refuses version-2 reserve metadata. M3's signed input reader
accepts the larger container, but that does not establish native creation
with reserve overflow; the report records this boundary explicitly.

### UI, runtime closure and capability handoff

Gameplay Patches retains the `my_career` PATCHES key and NEEDS_IMAGE
membership. Use title `MyCareer: draft and upgrades` and this help text
(both required words are present):

> EXPERIMENTAL / UNWITNESSED. Retail: Franchise controls a team. Patch:
> Create MyPlayer, enter the draft or sign as an undrafted rookie, and return
> to the Apartment. Senior Bowl preparation includes MyPlayer; its game is
> unavailable. Spend played-game XP on upgrades with position caps and see
> the next fixture date. Rebuild an older MyCareer executable from base.

The protected Build tab `_option` caption is
`MyCareer: draft and upgrades` (28 characters, below 60), with
`needs_image=True`. Keep the optional legacy setup caption distinct from
generic in-game creation. The owned core `HELP_TEXT` has been updated;
existing feature-panel consumers inherit it. No other GUI panel was edited.

Add the one new runtime allowlist line, preserving existing MyCareer lines:

```text
mod_editor/core/nfl2k5_my_career_progression.py
```

Retain allowlist entries for `nfl2k5_my_career.py`,
`nfl2k5_my_career_code.py`, `nfl2k5_my_career_mode.py`,
`nfl2k5_my_career_mode_code.py`, `nfl2k5_my_career_save.py`,
`nfl2k5_senior_bowl.py` (all under `mod_editor/core/`),
`mod_editor/gui/my_career_panel_qt.py`, and
`docs/mod_editor/nfl2k5_my_career_mode_capabilities.json`.
Development probes, generated measurement receipts and tests are not runtime
dependencies; add the report only if reports are distributed.

In `packaging/check_2k5_mod_studio_runtime.py`, add import
`mod_editor.core.nfl2k5_my_career_progression`; preserve the existing
MyCareer/core/Senior Bowl/roster-record imports. The new policy imports the
already shipped `nfl2k5_roster_records`. No new package dependency is required.

Merge the updated owned capability fragment
`docs/mod_editor/nfl2k5_my_career_mode_capabilities.json` into the registry's
existing `nfl2k5.mode.my_career_inline` object. There is no new surface or ID.
Keep `gui.expose=false`, `gui.default_enabled=false` and
`runtime.status=not-tested` until Noah's witness. Its schema-valid commands
are `python3 -m mod_editor.core.nfl2k5_my_career_mode apply default.xbe
generic-default.xbe` and
`python3 -m tests.mod_editor.test_nfl2k5_my_career_draft`.

### Allocator and release manifest

All owned gate, budget and manifest-builder unions now contain the M3 row.
The allocator leaves the original 8 KiB code footprint as padding and places
the expanded MyCareer code after the other code allocations. Its old 4 KiB
state stays put; the extra named 4 KiB state occupies the previously spare
last RW page at `0x1505000`. It adds no page and moves no other owner.
The complete before/after budget is in `tools/mycareer_mode/m3_budget.json`.
Old 8 KiB reservations and incomplete M3 reservations require rebuild from
the original XBE, before any code/hook install.

Claude must regenerate protected `data/nfl2k5_cave_reservations.json` with
`tools/nfl2k5_cave_oracle.py manifest` after protected integration and when a
disposable disc can preserve Noah's free-space floor. This session's
`tools/mycareer_mode/refresh_m3_manifest.py` output is an explicitly labelled
XBE-only scratch projection: it retains parent retail reservations and
records actual current XBE owner writes. Historical disc fields are not a
new acceptance build. Do not ship or promote that scratch manifest.
