# Beta 68 A2: T3 integration onto the T1/T2 stack

The integration starts at `925c5da6` (markers + T1 + T2) on `astra/b68-a2-integrate`.
All in-game behavior remains **UNWITNESSED**. Bounded native execution does not
establish a played fix for the reported Berman freeze or read-option symptom.

## Merge and delivery

`git bundle verify /home/noah/2k-worktrees/astra-b68-t3/ASTRA_T3.bundle` passed.
The verified prerequisite is `c8783a64406ce6b062a7b287173ecbe778f43df2` and the
bundle tip is `78cd1e95162b73c8016531b981ea038d3fe55169`.
Fetched `refs/heads/astra/b68-t3-game` to temporary ref
`refs/remotes/astra-t3/game`, then ran `git merge --no-edit refs/remotes/astra-t3/game`.
The three delivered commits are:

- `32e085cf`: Preserve Supersim preference on B and restore MyCareer PAT choice.
- `7b9f4aef`: Add native possession, PAT and scorebug composition proofs.
- `78cd1e95`: Document beta 68 T3 causes, witness limits and green XBE gates.

Merge commit `541be9e3` retains all 11 bullets beneath the beta-68 heading in
T1 (3), T2 (4), T3 (4) order. The changelog was the only conflict. Provider
entries merged automatically; both parents' key sets are retained, with current
source digests verified. The new changelog reference to `WIRING.md` was retargeted
to `WIRING_B68_T3.md`.

Commit `8d24b64f` applies the protected wiring and count pins. It uses `git mv`
to preserve T3's root report as `ASTRA_B68_T3_REPORT.md` and root wiring as
`WIRING_B68_T3.md`, byte for byte. Neither root `ASTRA_REPORT.md` nor `WIRING.md`
is tracked in the delivered tip. This A2 report is supplied as untracked
`ASTRA_REPORT.md` and a tracked `ASTRA_B68_A2_REPORT.md` copy.

The original worktree Git metadata is read-only. All Git mutations use local
`.scratch/a2/git`, initialized on `925c5da6`, with the existing object store as a
read-only alternate and this worktree as `GIT_WORK_TREE`. The original branch
metadata remains at `925c5da6`. No other worktree was changed and nothing was
pushed. The bundle is the authoritative committed delivery. Explicit paths are
used for integration commits; the conflicted merge used explicit `git add --`
paths followed by `git merge --continue`.

## Every protected wiring hunk

The source for the exact handoff is `WIRING_B68_T3.md`.

1. `mod_editor/gui/beta62_options.py`, `SCOREBUG_RUNTIME_HELP`: installed the full
   supplied warning beginning "Reported game freeze: andrethealchemist says...",
   including his "Unselecting that option fixed the issue for me." comparison,
   leave-off guidance, features, bounded-proof limit and original-source rebuild
   instruction.
2. `mod_editor/gui/build_panel_qt.py`, BuildPanel constructor: replaced the full
   `self.scorebug_runtime_check = self._option(...)` call with label
   **Scorebug effects (reported Berman freeze)**, the shared help,
   `needs_image=True`, `badge=NOT_TESTED` and `details=r62_ui.SCOREBUG_RUNTIME_HELP`.
3. `mod_editor/gui/gameplay_patches_panel_qt.py`, `PATCHES`: replaced the
   `scorebug_runtime` tuple with the identical new label and shared help.
4. `mod_editor/capabilities/registry.v1.json`,
   `nfl2k5.scorebug_presentation.runtime`: replaced `title`, `summary`,
   `gui.reason`, `runtime.scope`, `validation_command` and `portme[0]` per the
   handoff. Retained `runtime.status = "not-tested"`. Both evidence lists append
   `ASTRA_B68_T3_REPORT.md`, `tests/mod_editor/test_nfl2k5_b68_game_composition.py`
   and `docs/nfl2k5_b68_t3_composition.json`. The command is normalized as requested
   to `python3 -m tests.mod_editor.test_nfl2k5_b68_game_composition`.
   The porting instruction names `WIRING_B68_T3.md`.
5. The registry's `nfl2k5.mode.my_career_inline` row: replaced its full summary
   with the supplied Fast forward cancellation, saved preference, human receiver,
   controller disconnect and PAT wording. Both evidence lists append
   `ASTRA_B68_T3_REPORT.md`, `tests/nfl2k5_b68_series.py` and
   `docs/nfl2k5_b68_t3_validation.json`.
6. Registry serialization is exactly
   `json.dumps(obj, indent=2, sort_keys=True) + "\n"`. Only these two existing
   rows change. Existing evidence is retained; both rows' classification,
   default, exposure and runtime status are unchanged.
7. `packaging/check_2k5_mod_studio_runtime.py`: updated the shared registry
   assertion and printed closure signature as detailed below.
8. `packaging/check_apf2k8_mod_studio_runtime.py`: updated only the shared
   registry count assertion. APF's own 69-row assertion is unchanged.

No `mod_build.py` change is requested or needed. The options stay off in every
preset. The Build and Gameplay scorebug labels were verified on actual offscreen
widgets; the shared help exactly equals the handoff. No old-option-label test
expectation was found in `tests/`. `WIRING_B68_T3.md` requests no release-allowlist
edit, and the changed MyCareer core module was already allowlisted. No release
stage or retail disc was built.

## Every pin and allocation

| Pin / measurement | Before | After |
| --- | ---: | ---: |
| Actual shared registry row count | 161 | 161 |
| 2K5 runtime assertion, `len(registry.capabilities)` | 160 | 161 |
| 2K5 runtime printed `registry=` signature | 160 | 161 |
| `test_phase1_packaging.py` expected `registry=` signature | 160 | 161 |
| APF runtime shared registry assertion | 160 | 161 |
| Unified provider module count (`test_provider_integrity.py`) | 271 | 271 |
| MyCareer `m3_budget.json` machine-code bytes (T3) | 14,588 | 14,908 |
| MyCareer complete RX content bytes (T3) | 18,457 | 18,781 |
| MyCareer spare RX after the 17-byte tag (T3) | 2,006 | 1,682 |
| MyCareer RX reservation | 20,480 | 20,480 |
| MyCareer base RW / directory RW reservations | 4,096 / 4,096 | 4,096 / 4,096 |

T3 adds no core module, so the already correct unified provider count of 271
needs no edit. Its provider digest for `nfl2k5_my_career_mode_code.py` changes
from `fa38741ebc3f7c0b2abc351ea7ec04fadcb164096b125ba084c77d8fb39f33c4`
to `7746fa17bf59be6eafef5605cddf9c5ce4ab0e6199d0421644ab598a0a7ebc74`.
The installed immutable code digest in `m3_budget.json` changes from
`875b846d8dbc9876d54c9ec0b25b487330c59ea234909a4f850f1e2bce8aa65c`
to `07a46ec27800f2c957db23a74121b65e29b8959b548b2dc0fb7c8fb6ed58508d`.
These digest changes are delivered by T3. Integration repins have applied zero
additional updates. `python3 packaging/repin.py --apply` precedes each commit.

**No allocation changes.** Four previously unused RW bytes at `+2732` become
the transient cancellation word, before controller scratch at `+2800`. It is
not serialized. The owner requests, peer addresses, section geometry and XBE
file size are unchanged. The protected release manifest is byte-identical to
`925c5da6`. The incremental projection conservatively adds 128 observed retail
write reservations to the parent spans; these are observations of the existing
owner, not 128 new allocations. Its only changed source fingerprint is
`mod_editor/core/nfl2k5_my_career_mode_code.py`.

The shared 160-to-161 pin corrections overlap A1's possible audit scope and are
explicitly requested by the A2 brief. No T1/T2 implementation is changed by A2.

## Manifest commands and proof boundary

Actual successful local command, run with `PYTHONPATH=.` and the offscreen,
no-update-check and deterministic-hash environment below:

```sh
python3 tools/mycareer_mode/refresh_gate_manifest.py \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --base-revision c8783a64406ce6b062a7b287173ecbe778f43df2 \
  --output .scratch/a2/gate-manifest.json
```

This projection retains parent reservations and observes the changed MyCareer
writer. It is not a regenerated release/disc manifest. Claude must run this exact
release manifest command after importing the bundle, where the work directory
is writable:

```sh
python3 tools/nfl2k5_cave_oracle.py manifest \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir '/media/noah/Storage/.b66-t3' \
  --json data/nfl2k5_cave_reservations.json
python3 packaging/repin.py --apply
```

Then rerun the four XBE gates against the regenerated release manifest. No
emulator, display, audio, network, retail image copy or storage-mount write was
used in A2. Root free space was 98 GiB at entry; large image work was avoided.

## Validation

Every suite runs standalone using `python3 <path>` with:

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 \
PYTHONHASHSEED=0 NFL2K5_CAVE_MANIFEST="$PWD/.scratch/a2/gate-manifest.json"
```

Six independent processes run at most concurrently. The local runner records
each exact command, exit code, Ran/OK/FAILED lines, skip count, duration, peak RSS
and log hash, and checks that tracked Python/C/assembly/JSON sources are unchanged
between launch and completion. Full local logs are under `.scratch/a2/validation/`.
The portable receipt is `docs/nfl2k5_b68_a2_validation.json`.

Additional checks:

- `python3 tools/mycareer_mode/build_runtime.py --check`: `MyCareer mode runtime verified`.
- `python3 tools/nfl2k5_my_career_assemble.py --check`: `MyCareer template verified`.
- Offscreen integration check: `A2_INTEGRATION_CHECK_PASS labels=2 shared_help=exact presets=off registry=161 changed_rows=2 unified_pins=271 provider_union=preserved release_manifest=unchanged root_reports=untracked`.

Final standalone results (every command uses the environment above):

| Command | Final unittest lines | Exit |
| --- | --- | ---: |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | `Ran 115 tests in 1538.124s; OK` | 0 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | `Ran 127 tests in 1738.074s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | `Ran 388 tests in 2182.063s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_supersim_live.py` | `Ran 34 tests in 2610.352s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | `Ran 29 tests in 363.248s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career.py` | `Ran 13 tests in 20.612s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_control.py` | `Ran 2 tests in 14.780s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_frontend.py` | `Ran 7 tests in 54.262s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_creation_boundary.py` | `Ran 4 tests in 2.057s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_signing.py` | `Ran 6 tests in 47.051s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_inline.py` | `Ran 8 tests in 12.429s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_settings.py` | `Ran 9 tests in 27.342s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_unicorn.py` | `Ran 18 tests in 13.291s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_menus.py` | `Ran 4 tests in 39.131s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_m3_budget.py` | `Ran 5 tests in 4.504s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_audit.py` | `Ran 6 tests in 0.072s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode_routes.py` | `Ran 7 tests in 2.890s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py` | `Ran 3 tests in 8.028s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | `Ran 5 tests in 10.809s; OK (skipped=1)` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_supersim.py` | `Ran 12 tests in 8.796s; OK` | 0 |
| `python3 tests/mod_editor/test_beta66_supersim_wiring.py` | `Ran 3 tests in 0.326s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_played.py` | `Ran 4 tests in 58.222s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_completion.py` | `Ran 6 tests in 31.946s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode4.py` | `Ran 8 tests in 444.639s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_mode5.py` | `Ran 4 tests in 290.772s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_position_inputs.py` | `Ran 9 tests in 17.350s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_choice.py` | `Ran 1 test in 19.198s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_turnover.py` | `Ran 3 tests in 62.655s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_frame.py` | `Ran 1 test in 56.098s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_period.py` | `Ran 2 tests in 36.830s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_injury.py` | `Ran 1 test in 21.414s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_cpu_timeout.py` | `Ran 1 test in 21.960s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_draft.py` | `Ran 6 tests in 1098.355s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_upgrades.py` | `Ran 4 tests in 253.882s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_week.py` | `Ran 1 test in 343.497s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_my_career_season.py` | `Ran 1 test in 156.187s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option.py` | `Ran 15 tests in 9.921s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_runtime.py` | `Ran 13 tests in 46.614s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_unicorn.py` | `Ran 6 tests in 2.842s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_controls.py` | `Ran 9 tests in 16.626s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_frames.py` | `Ran 10 tests in 37.665s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_screen_hooks_compose.py` | `Ran 9 tests in 86.665s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_diagnostic.py` | `Ran 17 tests in 26.968s; OK (skipped=4)` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_play_intents.py` | `Ran 20 tests in 33.359s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_playbook_pair.py` | `Ran 7 tests in 7.409s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_b661_transition.py` | `Ran 11 tests in 467.041s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_presentation_v6.py` | `Ran 5 tests in 8.928s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py` | `Ran 12 tests in 98.662s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py` | `Ran 7 tests in 208.342s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py` | `Ran 4 tests in 96.866s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py` | `Ran 6 tests in 103.826s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_accelerated_clock.py` | `Ran 40 tests in 38.897s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` | `Ran 7 tests in 290.828s; OK` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_b68_game_composition.py` | `Ran 3 tests in 416.844s; OK` | 0 |
| `python3 tests/nfl2k5_kick_rules_test.py` | `Ran 34 tests in 3.651s; OK` | 0 |
| `python3 tests/mod_editor/test_beta66_d1_panels.py` | `Ran 4 tests in 0.710s; FAILED (failures=1)` | 1 |
| `python3 tests/mod_editor/test_discord_bugs_1_wiring.py` | `Ran 10 tests in 2.657s; OK` | 0 |
| `python3 tests/mod_editor/test_discord_bugs_2_wiring.py` | `Ran 6 tests in 0.947s; OK (skipped=2)` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_diagnostic_manifest.py` | `Ran 0 tests in 0.296s; OK (skipped=1)` | 0 |
| `python3 tests/mod_editor/test_nfl2k5_read_option_qt.py` | `Ran 7 tests in 1.152s; OK` | 0 |
| `python3 tests/mod_editor/test_capability_registry_module_commands.py` | `Ran 3 tests in 0.000s; OK` | 0 |
| `python3 tests/mod_editor/test_validate_all_capabilities.py` | `Ran 36 tests in 0.724s; FAILED (errors=1, skipped=1)` | 1 |
| `python3 tests/mod_editor/test_product_catalog.py` | `Ran 9 tests in 0.042s; OK` | 0 |
| `python3 tests/mod_editor/test_phase1_packaging.py` | `Ran 23 tests in 0.079s; FAILED (errors=1)` | 1 |
| `python3 tests/mod_editor/test_provider_integrity.py` | `Ran 7 tests in 8.743s; OK` | 0 |

Final list: **65 files, 1,197 tests reported, nine skip records, three inherited failed suites.** All four XBE gates and all T3 native suites pass. Peak per-process RSS is 903,012 KiB.

## Failures, skips and A1 boundary

**The requested standalone list is not entirely green.** Three failures are
inherited from the supplied base or missing local release inputs. None is a
T3-code failure, and none is hidden with a new skip or a weakened assertion.
`docs/nfl2k5_b68_a2_validation.json` includes the before/after audit evidence.

- `test_beta66_d1_panels.py`: `PanelTests.test_equipment_default_and_explicit_recolour`
  fails at line 28 with `AssertionError: wiring context drifted`. Edit 0 in
  `reports/beta66_d1/panel_edits.json` no longer matches the equipment dialog.
  Both that fixture and `mod_editor/gui/equipment_texture_import_dialog.py` are
  byte-identical to `925c5da6`; the same edit matches neither its old nor new
  text in that base. This is the T2 equipment fixture drift assigned to A1.
  The three other tests in the suite pass, including Build/Gameplay wiring.
  Its older socks expectation will also need A1's review against T2's independent
  sock artwork. A2 does not alter the equipment fixture, dialog or expectation.
- `test_validate_all_capabilities.py`: canonical coverage errors at
  `tools/validate_all_mod_editor_capabilities.py:840` with
  `unreviewed validation module arguments`. The first offending command is
  `python3 -m mod_editor.core.apf_field_material_writer --index <0A> --entry 53 --alpha graphic_overlay_4=0.25 --manifest <report.json>`.
  The same parser also rejects the existing ESPN25 `status source.iso espn25-plan.json`
  command and the `packaging.check_apf2k8_mod_studio_runtime` module namespace.
  There are exactly three distinct rejected commands, covering 17 rows, on BOTH
  `925c5da6` and A2. The validator source is unchanged. Its old exact-count pins
  are 108 capabilities / 103 covered / 83 unique commands, while both revisions
  have 161 / 156 / 117. The new T3 scorebug command parses successfully and does
  not alter those counts. Broad validator policy and historical count repair
  belongs with A1/Claude; no parser acceptance rule or count is weakened here.
- `test_phase1_packaging.py`: the metadata-contract test errors at line 374
  reading absent `reports/assets/menu_state_trace.json`. All 16 reviewed
  `reports/assets/` metadata files are absent; none is tracked at `925c5da6`.
  The unchanged release scanner still requires their exact size, SHA-256 and
  schema. Claude must provision the reviewed release-stage metadata and rerun
  this suite. The other 22 tests pass, including A2's `registry=161` assertion.
  No metadata fixture is fabricated and no release audit assertion is skipped.

Existing skips are the generic MyCareer build's required 100 GB root reserve,
four tests requiring Noah's absent private `bo` read-option diagnostic disc,
two deferred APF proposal tests in `test_discord_bugs_2_wiring.py`, the
historical read-option manifest projection (the production manifest has since
been regenerated), and the exhaustive-validator test for missing historical
evidence files. There are nine skip records, including that historical
projection class skip (`Ran 0 tests`).
The four XBE gates and T3's new native proofs have no skips.

After the initial unchanged-source run, commit `42ae19cd` corrects the remaining MyCareer
registry constraint sentence from `B cancels to Off.` to
`B cancels the current CPU sequence until the next native snap without changing the saved Supersim choice.`
This is a T3-required metadata consistency fix in the same wired row; the exact
handoff summary and all other constraint text are retained. The three registry
and catalog suites are rerun after the change. Their final results replace
initial results in the table, and both runs are retained in the receipt.
Native source files and the gate manifest remain unchanged by this correction.


## Import the delivery

```sh
git bundle verify /home/noah/2k-worktrees/astra-b68-a2/ASTRA_A2.bundle
git fetch /home/noah/2k-worktrees/astra-b68-a2/ASTRA_A2.bundle \
  refs/heads/astra/b68-a2-integrate:refs/remotes/astra-a2/integrate
git merge --no-edit refs/remotes/astra-a2/integrate
```

After importing, complete A1's inherited test corrections, regenerate the release
manifest with the command above, and run the release gates. The Berman freeze
remains unresolved; read-option's played symptom remains unreproduced. Retest
Supersim cancellation/rearm, postgame persistence, PAT kick/two-point choice and
the following kickoff using the witness script in `ASTRA_B68_T3_REPORT.md`.
