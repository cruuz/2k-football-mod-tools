# Beta 65 follow-up: MyCareer Settings

2026-09-10. Branch `astra/b65-supersim-2`, integrated baseline `ea0e03a1`.
Implementation commit: `328ee0f1`.
EXPERIMENTAL / UNWITNESSED. No push, emulator, display, audio device or disc build.
This report covers the Settings follow-up in `ASTRA_BRIEF_SETTINGS.md`. The earlier
live-engine research and Stage 1 remain in `ASTRA_B65_SUPERSIM_REPORT.md`; this
follow-up supersedes its session-only Apartment choice and cold-load-reset text.

The Apartment now orders Play next game, Practice, MyPlayer, Start MyPlayer,
Upgrades, Settings, Save and Quit. Settings is an owned native navigation page:
A changes the selected row, native selection is yellow, and B returns to the
Apartment. The explanation reads “Spectate keeps all presentation. B returns to
Apartment.” It offers exactly three choices:

| Row | Choices | New/old-career default |
| --- | --- | --- |
| First Person Football | Off / On | Off |
| Off-field play | Spectate / Skip presentation | Skip presentation |
| MyPlayer star | On / Off | On |

The first-person action calls the original Franchise Settings callback. Its
native word is authoritative. The off-field choice controls the existing Stage 1
native skips at **1x**; Spectate adds no skips and retains CPU ownership. B during
an eligible off-field presentation selects Spectate, which now persists when the
career is saved. No Fast forward choice, scheduler, ticker or camera option is
installed. The integrated native OL/DL templates, filled-star geometry, clock and
other owners are preserved.

## Proof ledger

PROVED below means the named bounded execution or byte check actually ran. It
does not mean Noah has seen the result on a running game.

| Claim | Status | Exact evidence / limit |
| --- | --- | --- |
| Retail Franchise FPF row is `0x500B24`, type 5, title `0xE7D5C4` | PROVED | `test_retail_row_toggles_display_and_fpf_entry_use_one_native_word`: exact 13-word row and seven guarded byte spans |
| Both retail arrows `0x147E60` / `0x147E80` toggle `0xE5FFE4`; getter `0x147EB0` and display `0x148960` read it | PROVED | Both values and both directions, native instructions, no substituted leaves; value text uses `0x4ED994` |
| FPP entry writes the same flag; native mode consumer responds to it in mode 5 | PROVED, bounded prefix | Execute `0x2C1FF1` through `0x2C1FFB`; execute `0x64530` up to `0xF53C0` and inspect its ECX argument (2 when On). This is not a first-person rendered snap |
| Owned Settings uses the retail FPF toggle and samples the native word for its label/save | PROVED | Actual A dispatch, native getter, external retail-row change, re-entry and subsequent footer encode. A stale saved snapshot cannot override an external retail-row change |
| All three labels, selected yellow row, retained selection and B return | PROVED at text-submission boundary | `test_settings_native_navigation_labels_selection_cancel_and_masked_star`; real LAYT/MRKS traversal and native row formatting, final scene draw captured. Explanation uses the retail FONT path. No pixels/display witness |
| Off-field behavior still selects only Stage 1, with CPU ownership and native speed | PROVED within existing fixtures | Updated `test_nfl2k5_supersim_live.py`; earlier outer-update, replay and skip proofs remain applicable. No uninterrupted physical drive claim |
| All eight settings combinations encode identically in host and native codecs | PROVED | `test_all_footer_choices_match_host_and_native_and_reserved_bits_refuse`; unknown bits rejected by both readers |
| Native save and cold relocation preserve On / Spectate / Star Off | PROVED through native transport seams | `test_native_save_cold_relocation_preserves_settings_and_off_star`; every serializer runs, signed transaction buffer captured, new machine and different allocator layout. Device/signing service boundaries are named by the fixture |
| Old zero-filled footer loads Off / Skip / Star On, tagging only MyPlayer | PROVED | `test_old_footer_migrates_only_myplayer_star_preserving_other_tag_bits`; compare every player's serialized tag byte, with MyPlayer `0xA6 -> 0xA7` |
| Star is set at completed creation and retained through signing/capture | PROVED | Observe `mode_created` and `m3_creation_route` around supplied `0xA6`, then inspect signed/captured record `0xA7`; failed/cancelled creation uses the existing rollback path |
| Star On/Off preserves bits 1–7 and neighboring records | PROVED | All 128 high-bit combinations through the real Settings action, On then Off, comparing the entire three-record neighborhood; existing `player_tags.parse_body` recognizes only bit 0 |
| Filled-star owner transfers the tag into the live match copy | PROVED, copy boundary | `test_filled_star_native_match_copy_preserves_myplayer_tag`; compose actual star owner and execute native `0xC3C60` team copy. Renderer geometry remains owned by the integrated star job |
| First-person view, controller feel, actual star visibility and save device behavior | UNWITNESSED | Noah's script below. No game boot or emulator was used |
| Headless fast forward or guaranteed pre-snap return with a full play clock | HYPOTHESIS / NOT SHIPPED | Still no proved safe scheduler. This task adds Settings and persistence only |

The retail type-5 FPF row's separate value column is not rendered by the
Apartment's native list handler. The final page therefore uses the existing
native action-row type with a full `First Person Football: Off/On` label. Its
callback invokes `0x147E60`; the retail Franchise row itself is unchanged. This
keeps the setting visible without introducing a second authoritative flag.

## State, serialization and ownership

The existing base RW page reserves three words:

| Offset | Meaning |
| --- | --- |
| `+2696` | 0 Skip presentation, 1 Spectate; existing Stage 1 field |
| `+2700` | 0 star enabled, 1 star disabled |
| `+2704` | Last serialized FPF snapshot, refreshed from `0xE5FFE4` on every native encode |

Footer byte `+82`, formerly required zero, now allows only bits 0–2: FPF On,
Spectate, star Off. Header, version 1, signed length 128, identity checks, checksum,
all native blocks, and the remaining reserved bytes retain their existing
contracts. Old zero-filled footers map to the intended defaults. Older executables
reject new nonzero setting bits rather than silently misreading them; continue
using the updated build after saving nondefault settings. The host codec's
pointer-free reconstruction now returns a complete 4096-byte base state snapshot;
short old binder snapshots still encode the three defaults.

Only a validated primary identity is tagged on load. New creation completion
sets `record[0x53] |= 1`; capture and continued signing apply the saved preference.
Settings uses `(record[0x53] & 0xFE) | enabled`, never a whole-byte overwrite.
No loop tags the rest of a team. The filled-star owner already owns the full
record-copy bridge and renderer; this job adds no renderer patch or star geometry.

`tools/mycareer_mode/settings_budget.json` is the fresh installed measurement:

- Machine code: **11,250 bytes**.
- Code plus immutable strings/tables: **16,220 bytes**.
- Format tag: **17 bytes**; **147 bytes spare** in the historical budget union,
  **145** in the minimal layout and **148** in the integrated gate union, all
  inside the existing **16,384 RX**. Compressed pointer tables vary with layout.
- State: the same **4,096 + 4,096 RW** owners; no owner address or file size changes.
- `build_runtime.py` regenerated after each runtime change; final `--check` passes.
- `measure_m3.py` and `measure_mode4.py` complete. The latter is still an
  uninstalled capacity calculation, never an execution/speed proof.

No protected Build, GUI, registry, release allowlist or cave manifest was edited.
`WIRING.md` provides the exact registry amendment and RC89 bullet replacement,
including removal of the obsolete cold-load-reset statement. The existing
MyCareer opt-in and all Studio preset defaults are unchanged.

## Validation

**716 tests passed across 23 distinct standalone suites; 0 skipped**
in the private-evidence run. The deliberate missing-retail and missing-Unicorn
runs each return seven SkipTests. The machine-readable receipt is
`tools/mycareer_mode/settings_validation.json`; private logs remain under
`.scratch/`. All source hashes remained stable during the accepted suites.

| Command | Result | Seconds |
| --- | --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_my_career_settings.py` | 7 passed | 27.957 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_inline.py` | 8 passed | 12.087 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_frontend.py` | 7 passed | 57.284 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_menus.py` | 4 passed | 35.427 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_upgrades.py` | 4 passed | 252.614 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode5.py` | 4 passed | 279.247 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_control.py` | 2 passed | 13.757 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_position_inputs.py` | 9 passed | 17.295 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_creation_boundary.py` | 4 passed | 2.118 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_draft.py` | 6 passed | 1067.840 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_played.py` | 4 passed | 71.121 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_completion.py` | 6 passed | 27.148 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_season.py` | 1 passed | 159.256 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_week.py` | 1 passed | 338.649 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_routes.py` | 7 passed | 2.690 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_audit.py` | 6 passed | 0.062 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | 5 passed | 3.911 |
| `python3 tests/mod_editor/test_nfl2k5_supersim_live.py` | 17 passed | 90.589 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode4.py` | 8 passed | 412.734 |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 335 passed | 1834.304 |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 29 passed | 268.253 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 115 passed | 1106.257 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 127 passed | 1270.137 |

Both XBE gates and the oracle use
`NFL2K5_CAVE_MANIFEST=.scratch/settings-manifest-final.json`.
The matrix covers 324 compatible owner pairs in both orders (648 orders),
plus refusal checks: 335 tests total. The two MyCareer formats remain
mutually exclusive. Peak per-process RSS was
**911,676 KiB**, below the 2 GiB bound.

`build_runtime.py --check`, `measure_m3.py`, `measure_mode4.py`,
`packaging/repin.py` (zero pending updates), and `git diff --check` pass.
The CLI space proof reports zero retail-mapping overlaps, zero manifest
overlaps and zero legacy encoding references. Its 857 raw encoding
candidates remain candidates, not proved live references or free space.

Reproduce the isolated test runs with:

```bash
python3 tools/mycareer_mode/validate_m3.py --output .scratch/recheck/results.json --manifest .scratch/settings-manifest-final.json tests/mod_editor/test_nfl2k5_my_career_settings.py
```

Replace the final test path with each command listed above. The receipt
retains exact commands, source hashes, log hashes, timings and memory bounds.

The scratch manifest is generated by:

```bash
python3 tools/mycareer_mode/refresh_settings_manifest.py --output .scratch/settings-manifest-final.json
```

It observes the complete forward safety-gate stack, plus the optional modern
position byte writer: **125 calls, 12,695 reservations**. It retains every parent
retail reservation, replaces grown ownership from the actual sealed union, and
rejects unexpected source drift. Non-XBE helper and protected dispatcher pins are
explicit drift snapshots, not renewed disc-build evidence. No test disables
source validation. Parent disc fields are explicitly historical. Claude must
regenerate the protected production manifest after integrated wiring settles.
Final scratch SHA256:
`febc38baabdd8ab815d8e639bf0dbfb35d3e21eeab933d7cb9c58cf7c68b84b2`.

The first frontend regression run found a stale Save-row index after the intended
Apartment reorder. The test now selects Save at row 6. No runtime workaround was
needed. The final mode-4 regression also expected Quit among the first seven
visible Apartment rows. Its expectation now follows the new order; Quit is
eighth. The native launch/quit assertions remain unchanged. The first direct new-settings suite passed all six tests; final receipts
include the strengthened creation-before-signing observation and seventh,
pre-install refusal test.

The first scratch projection incorrectly wrapped `nfl2k5_rdata_sites` and
`nfl2k5_gameplay_lever` as independent owners. This invented 386 duplicate helper
reservations. The unchanged gate rejected them at
`tests/nfl2k5_allocator_stack.py:208` (Historic reload loop ownership); the oracle
reported the same error. The projection tool now observes the actual owning
callers while those generic helpers execute normally. It was regenerated from
the original parent, without deleting any inherited retail reservation or
weakening a gate. The first manifest is discarded; final gates use the new file
and hash above. Runtime sources were unchanged during this repair.

## Noah's exact witness script

Use the integrated beta-65 build with MyCareer opted in and the filled-star owner
enabled. Keep an older career save copy for the migration check.

1. Create/sign a QB MyPlayer and enter Apartment > Settings, below Upgrades.
   Expect First Person Football Off, Off-field play Skip presentation, MyPlayer
   star On. Move through each row: only the selected row should be yellow; no
   duplicate labels or missing values. B must return to the same Apartment row.
2. Set First Person Football On with A, return, and launch Play next game. Observe
   one complete pre-snap alignment and a controlled first-person QB snap. Finish
   or return through the supported game flow, set it Off, and verify ordinary
   camera play on the next launch. The existing Franchise Settings row must show
   the same setting if reached through its native menu.
3. On the next defensive series, compare Skip presentation with Spectate across
   supported returns to Apartment. Skip should request the proved presentation
   skips; Spectate should keep the full presentation. Gameplay remains at 1x.
   During an eligible off-field presentation press B; expect normal presentation
   thereafter and Spectate when returning to Settings.
4. Confirm the filled star identifies MyPlayer. Set MyPlayer star Off for the
   next launch: MyPlayer's star should disappear while other tagged players'
   stars and abilities remain unchanged. Set it On and repeat. Check kicks and a
   CB career as well as QB; the record copy must retain the correct player's tag.
5. Set On / Spectate / Star Off, Save, fully cold reload and inspect Settings.
   Expect all three choices retained; verify them during play. Repeat with
   Off / Skip / Star On. Save/load mid-game through the supported native save
   route and inspect the following return/launch, including halftime and a
   two-minute drill. No full-play-clock or uninterrupted-drive guarantee is made.
6. Load the preserved older career. Expect Off / Skip / Star On and MyPlayer
   tagged without changing another player's star. Save it, cold reload and repeat.

Only Noah's completed live observations can promote these display/gameplay items
from UNWITNESSED. A paused harness, a registered option or a successful serializer
is not a substitute for that witness.
