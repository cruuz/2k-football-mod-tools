# Astra integration 2

Date: 2026-09-05. Base: `2ccb926` on the beta-61 stack. No push.

The music-bank handoff is imported and the protected Build, Gameplay Patches,
Music, Playbooks, Share and packaging surfaces are integrated. Basic and Modern
leave both scorebug variants off. Experimental selects the paired runtime
scorebug. Every preset resets music policy to retail, unlock off and UserList
off, while preserving personal music inputs. Banks and the MIN option seed
remain explicit selections.

## Commits and delivery

The worktree's Git metadata is read-only. The initial fetch failed with
`cannot open FETCH_HEAD: Read-only file system`. Per the authorized fallback,
commits were made with writable Git metadata under
`.scratch/integration2/repo/.git`, using this worktree and explicit paths for
every staging and commit operation. The original branch metadata is unchanged.
The deliverable is `.scratch/integration2.bundle`, based on `2ccb926`, plus the
files left in this worktree. The brief, the pre-existing untracked star fixture,
private images, caches and scratch logs are not committed.

The imported commit is `6492fec`, from the supplied `music-banks.bundle`.
Its resolved local commit is `49387da`. The conflicts were additive: both runtime
and music owners, all tests from both gate compositions, and both WIRING sections
were retained. The allocator recognizes the third descriptor and music's
read-only `.ASTRAr` section.

```text
49387da Add transactional music bank rebuilds and 200-song jukebox metadata
678d30b Fix pinned practice recoding, synthetic season context and portable tool output
fef0e0b Integrate music, runtime scorebug and option packs with transactional builds and pinned release closure
4b6dca2 Regenerate final integrated XBE ownership manifest
5c861e5 Preview personal library disk space and refresh build ordering fixture
713f311 Validate final allocator ownership and refresh both clean release gates
beaf561 Run every build and shell test class in standalone CI
7635d21 Keep Create a Play integration sessions inside the test sandbox
673ead0 Scope allocator reservations to grown layouts in ownership proofs
1ce146e Recognize pinned practice-reserve staging in player-star builds
e65566f Pin the full deterministic provider closure and correct packaging expectation
c14984c Give integrated capabilities a reviewed standalone validation entry point
b37ca4c Record final source pins and canonical combined XBE allocations
```

The final report is included in a separate delivery commit. Bundle verification
is recorded in `.scratch/integration2/bundle-verify.log`.

## Integration decisions

- All three music-policy arguments flow through the shared dispatcher and both
  writers using the selected-policy adapter. All four status dictionaries expose
  the separate music states, v7 XBE state and runtime XBE state. Disc readiness
  additionally checks the matching runtime resources.
- Disc writes and the complete Build operation publish from private sibling
  stages only after success. Cancellation or a later library failure preserves
  both the source and any prior destination. Runtime resources run after ordinary
  passes; music libraries then replan against that intermediate image and retain
  the complete library receipt and its actual source hash.
- The Music tab shares the Studio session and operation lock. Source changes,
  undo, project changes, other audio edits and failures invalidate its cache.
  Preview stops on navigation and close. Music and Build participate in the
  existing shared operation guard. Closing during a Music worker requests
  cancellation and waits for the worker to finish.
- Build can include the canonical shared project once, preserving both physical
  music twins and other staged edits. A headless `.2k5music` input loads through
  `MusicService` into a private verified session and snapshots encoded content.
  Explicit BuildPlan policy selections control the resulting executable.
- The library recipe chooser has an asynchronous size preview and cancel action.
  It shows projected output size and temporary space, including the enclosing
  staged disc, and asks the product user to create a fresh playlist after a
  rebuild. Final planning repeats on the actual intermediate image.
- The option shortcut selects the shipped MIN-only v3 pack. It runs before
  position-pool recoding. Overlapping option and Modern Gun Core replacements
  are rejected before copying. Share's pack dialog offers only the authored team
  for option intent; the assignment inspector follows the active assignment
  chain and exposes decoded conditions while preserving raw hex.
- Format-2 handler 5 is registered as `file_shrink`; handler 4 remains reserved.
  Complete bank builds use the existing explicit `file_operations` export API.
  Portable personal project sharing retains authored WAVs and relative recipe
  references. No rebuilt retail packs or audio are added to presets or releases.
- The release allowlist contains Music services, GUI and helpers, runtime
  scorebug modules and tool, the option seed, and the remaining Rosters helpers.
  The unified provider has a reviewed, hash-pinned 173-file transitive closure.
  The shared registry has 80 records, including 42 NFL 2K5 records. Runtime smoke
  checks import the new helpers and validate the bundled option seed and an
  empty Music panel.

## CI fixes and ownership

The star renderer now recognizes the exact practice-reserves staging routine,
whose full-record copier preserves the star tag. Only the two replaced retail
call-site pins can differ, and only when the complete reserve routine, its
copier and its prerequisites validate as applied. A changed byte elsewhere in
that routine remains foreign. Both installation orders and exact replay pass.
The star audit excludes its own recorded spans when checking other owners.
Create a Play and playbook-install integration fixtures use temporary session
directories, retaining read-only access to the existing private source cache.


The progression fixture now includes only the season-cap module's pinned
retail context constants. It copies no private executable bytes. The synthetic
image still lacks depth-lock geometry and ABI context, so its GUI test correctly
expects that patch to be foreign. Dedicated depth-lock tests cover supported
executables.

Seven-on-seven compilation now admits only the exact built-in requests against
a known source hash as a pinned personnel transformation. Native defense
personnel validation remains strict for user-authored changes, additional
requests, links and other source bytes. The seven-on-seven writer retains its
own full postvalidation.

Guardian-cap and scorebug JSON outputs use explicit LF newlines. The shipped
motion tool adds its own directory for its sibling import. Provider pins were
regenerated after closure changes. Create-only and link-only `.2k5mod` projects
are accepted, resolving the existing defense roundtrip expected failure.

The oracle records the actual experimental build and separately constructs the
complete dormant-owner union, including relocated kickoff, runtime scorebug and
200-song metadata. The allocator's full pages retain all observed byte coverage;
named child allocations come from the final combined layout. This avoids
claiming the runtime-only layout and the combined layout occupy the same named
slots. Source-drift, unowned-write, section-digest and retail-reference checks
remain enabled. The production preset XBE hash is reported separately from the
larger ownership probe.

The dormant seven-on-seven practice-book attempt reports `refused: the practice
book is foreign, not retail; refusing` after the experimental build has already
recoded that book. It does not alter the XBE. Its executable owner is fully
recorded, and the separate known-source seven-on-seven suites pass. The default
presets continue to leave seven-on-seven off.

Final manifest: 3,444 reservations, 82 observed writer calls and 78 source
fingerprints; section digests verified. SHA-256:
`ddb73fa38367436300170f5eb6352109cdb8819cc8e99f51236c9131857f1d63`.
The final generator ran alone after source edits and the full CI loop finished.
`packaging/repin.py --apply` then reported zero updates. Logs:
`.scratch/integration2/manifest-final.log` and
`.scratch/integration2/repin-after-last-manifest.log`.

The standalone entry points in `test_mod_build.py`,
`test_nfl2k5_seven_on_seven_recode.py`, `test_throw_tuning_panel_qt.py` and
`test_studio_shell_layout_qt.py` were moved after their final test classes.
Their later classes now execute under the requested per-file CI semantics.

## Real builds

Both requested builds used the supplied private USA XISO. Both completed all
11 steps and deleted their output images afterward. The experimental build's
XBE SHA-256 exactly matches `preset_xbe_sha256` in the manifest.

| Build | Image bytes | XBE bytes | Seconds | Result |
| --- | ---: | ---: | ---: | --- |
| Experimental preset | 6,519,656,448 | 12,029,952 | 134.17 | PASS; image deleted |
| Opt-in witness | 6,519,656,448 | 12,029,952 | 134.95 | PASS; image deleted |

The witness adds `xbe_space=True`, `kickoff_relocated=True`,
`scorebug_runtime=True`, `music_policy="jukebox_menus"`, and `music_unlock=True`.
UserList remains off.

| Step | Experimental | Witness |
| --- | --- | --- |
| xbe | completed | completed |
| position_pools | applied | applied |
| depth_chart_rows | applied | applied |
| kickoff_alignment | applied | applied |
| depth_roles | applied | applied |
| screen_timing | applied | applied |
| season_2026 | applied | applied |
| team_history | applied | applied |
| prospect_names | applied | applied |
| guardian_cap | applied | applied |
| scorebug_runtime | applied | applied |

Experimental XBE: `7573bdf75f53ccc10fce4963a731a61f20e2b7066eb5f7c79b4784d6a9443534`.
Witness XBE: `0d120ef53035437f6ac1ca9160363a5890fffebff660732205b04c11168f948e`.
Both final runtime hooks, paired resources and the star renderer report applied. Relocated kickoff
reports retail for Experimental and applied for the witness. Music policy and
unlock report retail for Experimental and applied for the witness. The neutral
resource-only scorebug probe reports foreign on the distinct runtime collection;
the dedicated runtime resource probe reports applied. This preserves both
variants' exact resource fingerprints.

Full receipts, final per-patch inspection, build summaries and progress logs are
under `.scratch/integration2/`: `experimental-receipt.json`,
`witness-receipt.json`, their `*-summary.json` files and
`real-builds-final.log`. These local receipts are not release assets.

## Verification

The complete workflow loop ran each `tests/mod_editor/test_*.py` as a standalone
process, with `timeout -k 30 420`, offscreen Qt, update checks disabled and
`PYTHONFAULTHANDLER=1`. Only `test_apf_studio_installer.py` cleared `PYTHONPATH`;
all other files received the repository root. The large-evidence sentinel was
present, so no file was omitted as a lean-checkout skip. No test file timed out.
The unmodified run accounting is:

```text
SUMMARY: files=336 passed=325 failed=11 skipped=0 tests=4078
```

Full output: `.scratch/integration2/ci.log`. Per-file output:
`.scratch/integration2/ci/`. Every failure is accounted for below. Fixes discovered
during the loop were rerun separately; the raw summary above is preserved.

| Failed standalone file | Cause and final disposition |
| --- | --- |
| `test_2k5_build_is_explainable.py` | Pack fixture lacked the new `plays` field. Corrected; 16 pass in `explainable-final.log`. |
| `test_nfl2k5_create_play_wizard_qt.py` | Fixture tried to create a session in the read-only home directory. Temporary session factory; 2 pass in `create-wizard-final.log`. |
| `test_nfl2k5_crib_geometry_writer.py` | Missing developer-only `assets/intermediate/nfl2k5/models/4248_0105_phone.gltf`. Four tests ran, two errored. Left unchanged as directed. |
| `test_nfl2k5_depth_chart_rows.py` | Recorder correction initially reserved grown pages for an ungrown executable. Scoped to applied allocator state; 33 pass in `depth-chart-rows-final.log`. |
| `test_nfl2k5_playbook_pack.py` | Same read-only home session issue. Temporary session factory; 39 pass in `playbook-pack-final.log`. |
| `test_nfl2k5_player_star_draw.py` | Practice-reserves producer pins and self-ownership audit were stale. Exact compatible staging recognition and owner exclusion; 15 pass in `player-star-final.log`, plus 14 classic tests in `player-star-legacy-final.log`. |
| `test_nfl2k5_xbe_space.py` | Manifest combined named children from two allocator layouts. Final-layout regeneration and explicit combined allocation proof; 12 pass in `capability-feature-gates.log`. |
| `test_phase1_packaging.py` | A documentation check interpreted Windows CI's statement that Tkinter is absent as a desktop dependency. Scoped to actual installation requirements; 17 pass in `phase1-packaging-final.log`. |
| `test_provider_integrity.py` | Closure traversal could suppress package imports after an exact-path visit. Track both modes and pin the complete 173-file closure; 7 pass for each of hash seeds 1, 7 and 17 in `provider-closure-final.log`. |
| `test_validate_all_capabilities.py` | New module-form commands violated the aggregate validator's two-token command contract, and its counts were stale. Added a local 15-suite validator and updated exact coverage to 80 records, 75 covered, 5 deferred, 53 unique validators; 34 pass in `all-capabilities-final.log`. |
| `test_xbe_patch_cave_references.py` | Same incompatible-layout manifest issue as the allocator test. Corrected final union; 12 pass in `final-ownership-gates.log`. |

All ten actionable failures have passing reruns. The single remaining failure
is the explicitly retained Crib geometry evidence audit. The provided star
fixture is present and its drawing tests run; no test was weakened or skipped
to hide missing or foreign bytes.

Every file in integration 1's 25-file focused list appears in the full loop.
After the last manifest, both XBE gates pass (11 memory-write tests and 12
cave-reference tests), and the cave oracle passes all 28 tests. The explicit
allocator proof passes all 12 tests. Final logs:
`final-ownership-gates.log` and `capability-feature-gates.log`.

The registry's new entry point completed all 15 feature suites:

```text
BETA61_VALIDATION files=15 passed=15 failed=0
```

Both clean release stages passed the complete sequence: allowlist staging,
release audit, source-free runtime probe with `PYTHONPATH` cleared, desktop-file
validation, launcher syntax check, and a second release audit. The repeated
audit confirms that runtime probing left no undeclared files.

| Product | Declared files | Runtime closure | Result |
| --- | ---: | --- | --- |
| 2K5 Mod Studio | 348 | 119 product modules, 34 tool modules, 80 registry records, 42 NFL capabilities | PASS |
| APF 2K8 Mod Studio | 204 | 102 modules, 37 APF capabilities | PASS |

The 2K5 stage contains 23 exact reviewed metadata files, including the requested
guardian receipt with its size/hash/schema pin. No private source, symlinks or
undeclared paths are admitted. No materialization fallback was necessary.
The new Music closure also imported from the clean stage with NumPy, Capstone
and Unicorn blocked and executable `PATH` empty, making FFmpeg unavailable.
Logs: `release-2k5-gates.log`, `release-apf-gates.log`, `stage-2k5.log`,
`stage-apf.log` and `optional-imports.log`, all under `.scratch/integration2/`.

Earlier release-probe failures were corrected by updating the shared and NFL
capability counts, registering the exact guardian metadata receipt, and creating
the offscreen QApplication before instantiating the Music panel. The generic
registry validator also passes with file checks enabled (`registry-final.log`).

The bank acceptance tests cover a 200-song menu bank, return to the retail count,
and a 200-song jukebox with physical twins. Policy tests cover independent
selection; integration tests cover both metadata/policy orders, exact replay,
invalid selection, intermediate replanning and failed publication. Qt checks
cover Build state, preset selection, Music lifecycle and shell registration.

## Witness limits

These are offline build, byte-ownership, resource and software tests. No Xbox or
xemu gameplay witness was performed. Runtime scorebug effects, library playback,
option reads and the other experimental features remain unwitnessed in game.
The option seed remains MIN-only and incompatible with the overlapping stock
MIN Modern Gun Core seed. Music policy does not promise true shuffle or playback
on every screen. Personal library content stays outside distributed presets.
