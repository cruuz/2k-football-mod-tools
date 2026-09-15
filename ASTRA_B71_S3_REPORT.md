# Beta 71 S3: scorebug v3

## Outcome

V3 is implemented and committed on `astra/b71-s3-scorebug-v3`, from `a7440f05` (A5 integration). Every final standalone suite, strict registry validation and both detached XBE gates passed.

The native bar boundaries follow the requested source boxes within 0.007 HUD pixels in both aspects. The native comparison does **not** pass pixel-exact acceptance: text and RGB differences remain, and the supplied numeric plate/score dimensions differ from the photographed frame. The paired crops expose those differences. Appended data is **413,568 bytes / 0.394409 MiB**, only 11,008 bytes above A5.

**PROVED:** generated resource identities, bounded native collection/font lookup, actual score/timeout/play-clock callbacks, geometry and software raster output, multi-digit score separation, and the completed checks listed below. **UNWITNESSED:** booting or playing this build, GPU filtering, real-match transitions, the final disc and its option read-back. No emulator, disc build or push was run.

## Inputs and interpretation

- Read `ASTRA_CONTEXT.md`, the scorebug-v2 verdict in `BETA71_TRIAGE.md`, all four requested B70/B71 source reports, and the A5 `ASTRA_REPORT.md` at the parent revision. The S3 brief expressly authorizes scorebug writers, registry evidence, RC96 and the cave-manifest update despite the older general context exclusions.
- Opened `/home/noah/Desktop/2K5-8 Editors/beta71_evidence/bar_compare_espn_vs_disc_f.png`: ESPN above, disc f below. The stated verdict was “it doesn’t look exactly like espn ... not close yet”.
- Measured source: `/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg`, 1920×1080, SHA-256 `01622a78b6778f089e4b242c8deda42833b10ae123150ed5bc8989dc483929d7`.
- The explicit plate is `(828,946,1120,1000)`, larger than the approximately `(837,947,1084,983)` plate in the frame. The frame’s score “7” has 53 pixels of thresholded ink, while this brief requests 45. V3 follows the explicit numeric dimensions and reports the resulting photograph comparison honestly.
- The HUD transform is `x/3`, `16 + y*448/1080`; authored scene coordinates use `exact.scene_box`. Widescreen applies the existing `27/32` horizontal contraction about HUD x=320. Crops undo that contraction before restoring the 1920×1080 source coordinates.

## Implementation and injection routes

### Bar, wings and possession plate

The retail frame mesh uses an authored 64×64 atlas nine-slice with a real rounded corner, a light rim and vertical charcoal shading. The per-team 64×64 wing textures retain the proved small collection route. Each packs a height-filling logo and a two-dimensional colour ramp; the ramp reaches the body at about 65% of the wing width. Logo fitting uses the final source box aspect, preserving the mark’s proportions even when the texture cell itself is stretched. DEN uses the lit wing RGB `(56,89,144)`; KC uses `(180,56,86)`. No 256×512 atlas is added.

The plate is a white mask multiplied by full team colour, with a small pointer. Every other team uses its complete primary; the explicit near-black secondary choices are:

| Team | Plate secondary |
| --- | --- |
| CHI | `#C83803` |
| DEN | `#FB4F14` |
| HOU | `#C8102E` |
| LV | `#A5ACAF` |
| NE | `#C60C30` |
| NO | `#D3BC8D` |
| PIT | `#FFB612` |
| SEA | `#69BE28` |
| TEN | `#4B92DB` |

Unknown asset codes retain the neutral table value. The existing 40-entry asset-code table and owner lookup provide the tint; created-team fallbacks remain guarded.

### Scores, timeout ticks and capsule

- The appended `FirstPersonComic` FONT uses the existing tenth boot name (slot 9), copied from the complete retail font4 donor including its loader object tail. Its original ASCII cells remain available. The owner binds only the intended scorebug descriptors; global retail font slots stay unchanged.
- `U+0080..U+0089` provide 40×45 source-pixel score quads from 13×20 masks packed in previously unused 128×128 atlas space. `U+0090..U+0099` reuse those exact UV cells at narrower metrics for multi-digit scores. Native score formatters at `0xFC050` and `0xFC070` still determine the string, then the owner callbacks at records `0xA9594C` and `0xA95984` select the appropriate range. Scores 28, 100 and 999 remain outside the down plate in both aspects. No additional texture pixels are allocated for compact scores.
- Timeout callbacks write `~ ~ ~`, trimmed to 0–3 timeouts. The private tilde is a solid small tick with explicit advance and spacing; colour is `0xFFC8CACE`. This is not a FONT8 hyphen.
- The grey quarter uses the smaller `core_bug` font with capital suffix masks. The game clock uses the broadcast digit fork in black. The play-clock callback wraps native `0xFBE30` and removes the leading zero from `04`; its digit stays white.
- Spare material `score_buga` supplies the 61×39 geometry box from `(1021,1000)` to `(1082,1039)`, corresponding to the brief’s nominal 61×40 cell. Base tint is `(120,14,39)`, with the existing urgency behavior expressed as a bright-red pulse on the cell under five seconds. The pulse derives from the countdown bits, not a promised fixed-Hz timer. Boundary tests cover 12, 5, 4, 2.5, 0, negative and NaN values, with white text in both red phases.
- The capsule backing is on the always-visible alternate frame material. Hiding the play-clock element during live play therefore keeps a light backing behind the black game clock and grey quarter.

### Retail states and owner capacity

Native event formatters and visibility remain in use. A separate charcoal material, `zz_ESPN_bug1`, restores independent hang-time visibility at descriptor `0xA95AEC`; v2 had cleared its availability. Individual FLAG, Hangtime, Ball at Midfield, FUMBLE and hidden-play-clock renders are in [states.json](reports/b71_s3/states.json). `score_*` images refer to the retail FUMBLE event formatter, not a newly authored TOUCHDOWN slab. The `all_events_*` image deliberately forces incompatible simultaneous elements and is a stress diagnostic, not an accepted retail display state.

Owner revision 7 occupies **1,386 / 1,408 code bytes**, plus the existing 128-byte data allocation. Shared wing setup and score-flash helpers recovered room; `CODE_SIZE` did not need to grow. Runtime data remains in its named writable allocation. The slot-9 lookup failure retains native descriptor fallbacks. Tests cover register/FPU preservation, native visibility, write ownership, foreign-byte refusal, idempotence and composition.

## Volume and freeze boundary

| Component | Bytes |
| --- | ---: |
| 66 texture spans × 5,280 | 348,480 |
| FirstPersonComic FONT | 38,048 |
| core_bug FONT | 27,040 |
| Appended payload | **413,568** |
| Sector-rounded resource growth | 413,696 |
| Native rounded heap estimate for appended spans | 420,096 |

The new FONT metadata adds 11,008 bytes over the 402,560-byte A5 appendix. Atlas video sizes remain unchanged. This stays near the historically successful 0.4 MB class rather than the roughly 1.7 MB expansion associated with a failed loader allocation and subsequent null read. That historical evidence and the bounded loader tests are not a new boot witness; in-game freeze freedom remains UNWITNESSED.

## Native measurements

[4:3 ESPN/native comparison](reports/b71_s3/compare_43.png) · [Widescreen ESPN/native comparison](reports/b71_s3/compare_wide.png) · [Full JSON](reports/b71_s3/measurements.json)

`prove_v3.py` executes the native HUD/formatters with the compiled collection, then calls `compare()` with `MNF_COMPARE_REGIONS` and text boxes independently thresholded from the broadcast frame. Text components touching ROI edges are discarded to exclude capsule-rim fragments. The v3 role map supplies the right light/dark polarity for relocated callbacks. Native glyph quads include transparent padding; source-restored raster ink is reported separately.

### Region errors

Boundary and edge-distance values below are HUD pixels; RGB MAE is on the 0–255 channel scale. Geometry matching is distinct from photo matching.

| Region | Boundary 4:3 | Boundary wide | RGB MAE 4:3 | RGB MAE wide | Edge p95 4:3 / wide |
| --- | ---: | ---: | ---: | ---: | ---: |
| centre_pill | 0.005859 | 0.005254 | 62.641 | 62.537 | 7.071 / 6.356 |
| clock_strip | 0.005254 | 0.005254 | 53.613 | 52.020 | 3.000 / 2.236 |
| frame_rim | 0.006285 | 0.006285 | 60.683 | 60.160 | 43.000 / 43.000 |
| left_panel | 0.006285 | 0.006285 | 47.050 | 46.647 | 9.849 / 8.944 |
| right_panel | 0.006285 | 0.006285 | 68.272 | 68.203 | 7.000 / 6.083 |

| Extra region | Boundary 4:3 | Boundary wide |
| --- | ---: | ---: |
| away | 0.004801 | 0.004051 |
| home | 0.006285 | 0.006285 |
| play_clock_cell | 0.005254 | 0.005254 |
| pointer | 0.006285 | 0.006285 |

### Text errors in source pixels

All boxes are `[left, top, right, bottom]`, with exclusive right/bottom. These are independently measured ink boxes. The quarter’s capitals are now within 3–4 pixels; the widest remaining text difference is the down label (20 pixels at its right edge), which is centered on the larger requested plate.

| Text | Broadcast ink | 4:3 rendered ink | Max error 4:3 / wide |
| --- | --- | --- | ---: |
| away_score | `[736, 965, 776, 1018]` | `[735, 965, 773, 1010]` | 8 / 8 |
| away_ticks | `[717, 1032, 796, 1038]` | `[718, 1032, 794, 1037]` | 2 / 2 |
| clock | `[920, 1006, 1000, 1033]` | `[929, 1008, 1000, 1032]` | 9 / 8 |
| down | `[898, 955, 1021, 978]` | `[904, 960, 1041, 985]` | 20 / 20 |
| home_score | `[1139, 965, 1179, 1018]` | `[1138, 965, 1178, 1010]` | 8 / 8 |
| home_ticks | `[1120, 1032, 1198, 1038]` | `[1120, 1032, 1196, 1037]` | 2 / 1 |
| play_clock | `[1042, 1009, 1057, 1028]` | `[1044, 1007, 1061, 1026]` | 4 / 6 |
| quarter | `[850, 1009, 892, 1028]` | `[852, 1010, 895, 1029]` | 3 / 4 |

`compare().exact_match` is **false in both aspects**. Mean region RGB MAE is 58.452 / 57.914. All measured native frame containment checks are empty and visible triangle winding is consistent. Software raster sampling, low-resolution marks, differing text proportions, the larger plate and the specified shorter score explain why boundary agreement is not visual equality. No claim is made that GPU output will remove those residuals.

## Regeneration and validation

Compiler pins were regenerated from the actual final `Build` output, including the whole appended FONT hash: [compiler_pins.json](reports/b71_s3/compiler_pins.json). `packaging/repin.py --apply` updated provider seals. The resource identity is `scorebug-mnf-2026-v3`.

The cave manifest contains 13,081 reservations and 138 observed steps. Its final SHA-256 is `06609653fb463e26f05c90d3db8aaede996201000c6c3f0afbe3941da2af9e2a`. The scorebug owner occupies code `0x14BAA60..0x14BAFE0` and data `0x14BB010..0x14BB090` in this union. This is a **bounded complete forward XBE projection**, freshly observed from the A5 parent. It retains historical retail reservations and records final owner bytes/source hashes. It is not a production disc receipt: `release_manifest=false`, `disc_built=false`, `production_regeneration_required=true`, and inherited disc fields are explicitly historical. The external production build must regenerate its full receipt.

The first projection accidentally recorded `nfl2k5_rules_patch.apply` and its named caller as two owners of the same rule bytes. The cave gate rejected `nfl2k5_coin_defer/choose` at `0x25E7B5`. The corrected local projection recipe excludes that shared helper from independent observation, retains the real rule writers, and always starts from the A5 manifest. No gate or oracle assertion was relaxed.

### Final standalone results

The final driver completed 28 standalone programs: 279 reported unittest cases, including 15 skips, with no failures and unchanged source snapshots. Each final command is an independent Python process with `PYTHONPATH=<repo>:<repo>/tools` and `QT_QPA_PLATFORM=offscreen`. Two independent suites run concurrently. Strict registry validation uses default file checking, without `--skip-file-checks`. The final driver snapshots source hashes before and after.

| Command/result | Exit | Tests | Skips | Wall seconds |
| --- | ---: | ---: | ---: | ---: |
| [test_apf_scorebug_workspace_qt-release](reports/b71_s3/test_apf_scorebug_workspace_qt-release.log) | 0 | 11 | 0 | 0.658 |
| [test_nfl2k5_scorebug_assets-release](reports/b71_s3/test_nfl2k5_scorebug_assets-release.log) | 0 | 8 | 1 | 170.202 |
| [test_nfl2k5_scorebug_author-release](reports/b71_s3/test_nfl2k5_scorebug_author-release.log) | 0 | 12 | 0 | 6.953 |
| [test_nfl2k5_scorebug_exact-release](reports/b71_s3/test_nfl2k5_scorebug_exact-release.log) | 0 | 8 | 0 | 83.77 |
| [test_nfl2k5_scorebug_fonts-release](reports/b71_s3/test_nfl2k5_scorebug_fonts-release.log) | 0 | 10 | 5 | 9.0 |
| [test_nfl2k5_scorebug_freeze-release](reports/b71_s3/test_nfl2k5_scorebug_freeze-release.log) | 0 | 7 | 0 | 332.317 |
| [test_nfl2k5_scorebug_freeze_v2-release](reports/b71_s3/test_nfl2k5_scorebug_freeze_v2-release.log) | 0 | 7 | 0 | 418.219 |
| [test_nfl2k5_scorebug_ingame-release](reports/b71_s3/test_nfl2k5_scorebug_ingame-release.log) | 0 | 11 | 0 | 16.002 |
| [test_nfl2k5_scorebug_ingame_fix-release](reports/b71_s3/test_nfl2k5_scorebug_ingame_fix-release.log) | 0 | 9 | 0 | 135.588 |
| [test_nfl2k5_scorebug_mnf-release](reports/b71_s3/test_nfl2k5_scorebug_mnf-release.log) | 0 | 10 | 0 | 12.08 |
| [test_nfl2k5_scorebug_mnf_v3-release](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-release.log) | 0 | 4 | 0 | 32.929 |
| [test_nfl2k5_scorebug_native-release](reports/b71_s3/test_nfl2k5_scorebug_native-release.log) | 0 | 4 | 0 | 130.74 |
| [test_nfl2k5_scorebug_projection-release](reports/b71_s3/test_nfl2k5_scorebug_projection-release.log) | 0 | 14 | 0 | 56.575 |
| [test_nfl2k5_scorebug_resources-release](reports/b71_s3/test_nfl2k5_scorebug_resources-release.log) | 0 | 6 | 0 | 244.834 |
| [test_nfl2k5_scorebug_runtime-release](reports/b71_s3/test_nfl2k5_scorebug_runtime-release.log) | 0 | 12 | 0 | 117.87 |
| [test_nfl2k5_scorebug_source_art-release](reports/b71_s3/test_nfl2k5_scorebug_source_art-release.log) | 0 | 13 | 3 | 0.49 |
| [test_nfl2k5_scorebug_template-release](reports/b71_s3/test_nfl2k5_scorebug_template-release.log) | 0 | 19 | 0 | 9.906 |
| [test_nfl2k5_scorebug_template_release-release](reports/b71_s3/test_nfl2k5_scorebug_template_release-release.log) | 0 | 5 | 0 | 0.575 |
| [test_nfl2k5_scorebug_unified_adapter-release](reports/b71_s3/test_nfl2k5_scorebug_unified_adapter-release.log) | 0 | 5 | 0 | 0.167 |
| [test_nfl2k5_scorebug_v10_ingame-release](reports/b71_s3/test_nfl2k5_scorebug_v10_ingame-release.log) | 0 | 11 | 0 | 9.182 |
| [test_nfl2k5_scorebug_v10_projection-release](reports/b71_s3/test_nfl2k5_scorebug_v10_projection-release.log) | 0 | 14 | 0 | 28.071 |
| [test_nfl2k5_scorebug_versions-release](reports/b71_s3/test_nfl2k5_scorebug_versions-release.log) | 0 | 4 | 0 | 9.357 |
| [test_scorebug_studio_panel_qt-release](reports/b71_s3/test_scorebug_studio_panel_qt-release.log) | 0 | 11 | 0 | 7.251 |
| [nfl2k5_scorebug_layout_test-release](reports/b71_s3/nfl2k5_scorebug_layout_test-release.log) | 0 | 15 | 6 | 1.35 |
| [nfl2k5_scorebug_mod_project_test-release](reports/b71_s3/nfl2k5_scorebug_mod_project_test-release.log) | 0 | 10 | 0 | 1.304 |
| [test_provider_integrity-release](reports/b71_s3/test_provider_integrity-release.log) | 0 | 7 | 0 | 8.225 |
| [test_product_catalog-release](reports/b71_s3/test_product_catalog-release.log) | 0 | 9 | 0 | 0.15 |
| [test_phase1_packaging-release](reports/b71_s3/test_phase1_packaging-release.log) | 0 | 23 | 0 | 2.079 |
| [registry-strict-release](reports/b71_s3/registry-strict-release.log) | 0 | — | 0 | 0.159 |
| [xbe-memory-release](reports/b71_s3/xbe-memory-release.log) | 0 | 119 | 0 | 1579.189 |
| [xbe-caves-release](reports/b71_s3/xbe-caves-release.log) | 0 | 131 | 0 | 1771.283 |

The assets suite precisely skips its disc-copy transaction when the required Storage scratch directory is read-only (EROFS/EACCES/EPERM). Its other checks still execute. The font suite retains five historical private-font-v8 skips; current v3 lookup, relocation, glyphs and callbacks have active native tests. The source-art suite has three skips for missing developer PNG/scene fixtures and the corresponding old disc comparison. The layout suite has five skips for an absent historical Create-a-Play image and one for a missing glTF research export. A verbose rerun with its CPU-emulation flag enabled confirmed the image blocker. These skips are not boot or disc evidence; exact reasons are in `source-art-skip-details.log` and `layout-skip-details.log`.

Preliminary failures are retained in the ledger: read-only Storage, stale hyphen/dark-text/fixed-callback assertions, pin changes while early exploratory suites were already loaded, a mistaken test expectation for the pulse phase, the font-span rounding correction, and the duplicate shared-helper manifest owner. The final `-release` runs supersede those exploratory verdicts. The old sequential driver retains its failure exit; it is not advertised as a passing final run.

Initial strict registry validation lacked 75 ignored evidence files. Real copies were restored from the existing read-only local evidence source, matching the A5 per-file hashes (2,063,157 bytes); [evidence_hydration.json](reports/b71_s3/evidence_hydration.json) records them. They are neither staged nor bundled.

## Registry, RC96 and builder

The existing `nfl2k5.scorebug_presentation.runtime` capability row was updated with v3 scope, volume and proof paths. No capability rows were added. Runtime witness status remains `not-tested`, experimental and off in every preset. The RC96 scorebug bullet is anonymous and states the native proof limits.

The prepared [builder](reports/b71_s3/build_testdisc71.py) follows A5: Advanced preset with scorebug, scorebug runtime, modern colour and widescreen all enabled. Output:

`/home/noah/2K5 Mod Studio Builds/NFL 2K5 MOD TEST 2026-09-15h (scorebug v3 + colour + widescreen).xiso.iso`

Only `--plan-only` ran here. The builds folder is read-only in this session. The external builder first checks destination access, refuses an existing named output, preserves every patch archive, and follows A5’s at-most-three MOD TEST image policy. It removes incomplete discs on failure. After building it reparses the scorebug resources, XBE owner, all 477 colour bundles and widescreen sites, requires every status to be `applied` and aspect `16:9`, then exports the patch.

Import the bundle into the integration checkout (or fast-forward this worktree’s ordinary branch outside the sandbox) before building, so build receipts record the final source head. The private branch does not update the ordinary read-only HEAD. Then run externally from that checkout:

```bash
bash reports/b71_s3/launch_testdisc71.sh
```

Expected external receipts are `.scratch/testdisc71h/{plan,pruning,receipt,readback,patch-receipt,result}.json` plus `build.log`, `pid` and `exit`. No disc image, patch or read-back receipt was created here.

### Played-game witness still required

- Intro/coin toss/kickoff load without the historical allocation crash.
- Steady bar in 4:3 and widescreen; large marks, gradients, rim and score font match the supplied crops.
- Possession changes including near-black teams; single-, double- and triple-digit score updates; timeout consumption.
- Clock running/paused/hidden, urgency below five seconds, quarter and overtime labels.
- Native flag, hang-time, ball-on and score events stay readable through their real transitions.

## Commits and delivery

- Base: `a7440f05`, branch `astra/b71-s3-scorebug-v3`. The ordinary worktree `.git` is read-only, so commits live in `.scratch/private.git` using `.scratch/g`. No shared branch refs or other worktrees were changed.
- Implementation commits: `374872cd` and `d18939b250dcf7863c729ac7ad29a30fdbe7dd18`. Staging and commits use enumerated paths; the second list is in [source_commit.json](reports/b71_s3/source_commit.json). Evidence/manifest/report commits follow after the checks.
- Bundle: `.scratch/astra-b71-s3.bundle`, prerequisite `a7440f05`. It is created from the final private branch and verified locally. The final delivery receipt records head, size and SHA-256.
- Retail inputs remain read-only and no retail pack/XBE/disc bytes are stored in the report or bundle. Scratch remains under 200 MB. No push or emulator launch.

## Command ledger

[command_ledger.json](reports/b71_s3/command_ledger.json) contains exact argv, UTC start/end, elapsed seconds and exit status for all recorded commands; each named log contains the complete output. Early read-only discovery and editing commands are in the session tool transcript rather than this runner. The first aborted manifest observation was overwritten by its retry; it is not counted as a proof. No validation claim relies on an unrecorded run.

| Name | UTC start | Seconds | Exit | Exact command |
| --- | --- | ---: | ---: | --- |
| [pin-compiler](reports/b71_s3/pin-compiler.log) | 2026-09-15T20:34:17.093185+00:00 | 43.989 | 0 | `python3 reports/b71_s3/regenerate_pins.py` |
| [render-check](reports/b71_s3/render-check.log) | 2026-09-15T20:36:54.138861+00:00 | 11.046 | 0 | `python3 -` |
| [pin-compiler-final](reports/b71_s3/pin-compiler-final.log) | 2026-09-15T20:38:35.172278+00:00 | 44.93 | 0 | `python3 reports/b71_s3/regenerate_pins.py` |
| [proof-v3](reports/b71_s3/proof-v3.log) | 2026-09-15T20:40:13.957437+00:00 | 38.17 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [repin-initial](reports/b71_s3/repin-initial.log) | 2026-09-15T20:41:53.323250+00:00 | 19.745 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_mnf_v3-rerun](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-rerun.log) | 2026-09-15T20:44:01.066266+00:00 | 16.491 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [proof-v3-events](reports/b71_s3/proof-v3-events.log) | 2026-09-15T20:44:20.519889+00:00 | 38.436 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [pin-compiler-release](reports/b71_s3/pin-compiler-release.log) | 2026-09-15T20:44:53.806440+00:00 | 44.718 | 0 | `python3 reports/b71_s3/regenerate_pins.py` |
| [repin-source](reports/b71_s3/repin-source.log) | 2026-09-15T20:46:03.666330+00:00 | 20.849 | 0 | `python3 packaging/repin.py --apply` |
| [proof-v3-final](reports/b71_s3/proof-v3-final.log) | 2026-09-15T20:47:19.230102+00:00 | 45.166 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [pin-compiler-v3](reports/b71_s3/pin-compiler-v3.log) | 2026-09-15T20:47:20.378696+00:00 | 45.094 | 0 | `python3 reports/b71_s3/regenerate_pins.py` |
| [registry-preflight](reports/b71_s3/registry-preflight.log) | 2026-09-15T20:47:45.757330+00:00 | 0.175 | 1 | `python3 -m mod_editor.capabilities.validate_registry` |
| [test_nfl2k5_scorebug_exact-preflight](reports/b71_s3/test_nfl2k5_scorebug_exact-preflight.log) | 2026-09-15T20:47:46.037033+00:00 | 68.333 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [repin-validation](reports/b71_s3/repin-validation.log) | 2026-09-15T20:48:22.376586+00:00 | 21.491 | 0 | `python3 packaging/repin.py --apply` |
| [manifest](reports/b71_s3/manifest.log) | 2026-09-15T20:48:23.503627+00:00 | 336.65 | 0 | `python3 reports/b71_s3/refresh_manifest.py` |
| [test_apf_scorebug_workspace_qt](reports/b71_s3/test_apf_scorebug_workspace_qt.log) | 2026-09-15T20:48:34.064803+00:00 | 1.52 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_apf_scorebug_workspace_qt.py` |
| [builder-plan](reports/b71_s3/builder-plan.log) | 2026-09-15T20:48:35.221648+00:00 | 0.303 | 0 | `python3 reports/b71_s3/build_testdisc71.py --plan-only` |
| [test_nfl2k5_scorebug_assets](reports/b71_s3/test_nfl2k5_scorebug_assets.log) | 2026-09-15T20:48:35.614943+00:00 | 150.403 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [proof-v3-measured-text](reports/b71_s3/proof-v3-measured-text.log) | 2026-09-15T20:49:25.355800+00:00 | 46.405 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [test_nfl2k5_scorebug_author](reports/b71_s3/test_nfl2k5_scorebug_author.log) | 2026-09-15T20:51:06.048537+00:00 | 6.552 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [test_nfl2k5_scorebug_exact](reports/b71_s3/test_nfl2k5_scorebug_exact.log) | 2026-09-15T20:51:12.630575+00:00 | 84.262 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [proof-v3-ink](reports/b71_s3/proof-v3-ink.log) | 2026-09-15T20:51:31.168503+00:00 | 45.985 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [test_nfl2k5_scorebug_assets-rerun](reports/b71_s3/test_nfl2k5_scorebug_assets-rerun.log) | 2026-09-15T20:52:06.844121+00:00 | 154.124 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [test_nfl2k5_scorebug_fonts](reports/b71_s3/test_nfl2k5_scorebug_fonts.log) | 2026-09-15T20:52:36.921099+00:00 | 8.157 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze](reports/b71_s3/test_nfl2k5_scorebug_freeze.log) | 2026-09-15T20:52:45.108080+00:00 | 243.839 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [xbe-memory](reports/b71_s3/xbe-memory.log) | 2026-09-15T20:54:00.187826+00:00 | 1625.046 | 0 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` |
| [xbe-caves](reports/b71_s3/xbe-caves.log) | 2026-09-15T20:54:00.187953+00:00 | 1114.998 | 1 | `python3 tests/mod_editor/test_xbe_patch_cave_references.py` |
| [delivery-check](reports/b71_s3/delivery-check.log) | 2026-09-15T20:55:38.947128+00:00 | 0.293 | 0 | `python3 reports/b71_s3/check_delivery.py` |
| [test_nfl2k5_scorebug_exact-rerun](reports/b71_s3/test_nfl2k5_scorebug_exact-rerun.log) | 2026-09-15T20:56:04.665488+00:00 | 81.518 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [test_nfl2k5_scorebug_freeze_v2](reports/b71_s3/test_nfl2k5_scorebug_freeze_v2.log) | 2026-09-15T20:56:48.978583+00:00 | 60.46 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [pin-compiler-capsule](reports/b71_s3/pin-compiler-capsule.log) | 2026-09-15T20:57:17.412176+00:00 | 44.036 | 0 | `python3 reports/b71_s3/regenerate_pins.py` |
| [proof-v3-capsule](reports/b71_s3/proof-v3-capsule.log) | 2026-09-15T20:57:28.667167+00:00 | 45.49 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [test_nfl2k5_scorebug_ingame](reports/b71_s3/test_nfl2k5_scorebug_ingame.log) | 2026-09-15T20:57:49.467693+00:00 | 14.909 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_ingame.py` |
| [repin-capsule](reports/b71_s3/repin-capsule.log) | 2026-09-15T20:57:49.823216+00:00 | 32.591 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_ingame_fix](reports/b71_s3/test_nfl2k5_scorebug_ingame_fix.log) | 2026-09-15T20:58:04.405281+00:00 | 109.093 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [manifest-capsule](reports/b71_s3/manifest-capsule.log) | 2026-09-15T20:58:51.268795+00:00 | 0.481 | 1 | `python3 reports/b71_s3/refresh_manifest.py` |
| [test_nfl2k5_scorebug_mnf_v3-final](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-final.log) | 2026-09-15T20:58:51.842495+00:00 | 17.154 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_assets-final](reports/b71_s3/test_nfl2k5_scorebug_assets-final.log) | 2026-09-15T20:58:53.170838+00:00 | 146.533 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [manifest-final](reports/b71_s3/manifest-final.log) | 2026-09-15T20:59:33.766259+00:00 | 313.013 | 1 | `python3 reports/b71_s3/refresh_manifest.py` |
| [test_nfl2k5_scorebug_mnf](reports/b71_s3/test_nfl2k5_scorebug_mnf.log) | 2026-09-15T20:59:53.526353+00:00 | 11.777 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [test_nfl2k5_scorebug_mnf_v3](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3.log) | 2026-09-15T21:00:05.333079+00:00 | 16.539 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [proof-v3-final-metrics](reports/b71_s3/proof-v3-final-metrics.log) | 2026-09-15T21:00:21.476411+00:00 | 44.77 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [test_nfl2k5_scorebug_native](reports/b71_s3/test_nfl2k5_scorebug_native.log) | 2026-09-15T21:00:21.900819+00:00 | 129.678 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_native.py` |
| [test_nfl2k5_scorebug_mnf_v3-verified](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-verified.log) | 2026-09-15T21:00:54.540627+00:00 | 16.812 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_author-final](reports/b71_s3/test_nfl2k5_scorebug_author-final.log) | 2026-09-15T21:01:19.732684+00:00 | 6.451 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [test_nfl2k5_scorebug_ingame_fix-final](reports/b71_s3/test_nfl2k5_scorebug_ingame_fix-final.log) | 2026-09-15T21:01:25.691419+00:00 | 127.882 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [test_nfl2k5_scorebug_exact-final](reports/b71_s3/test_nfl2k5_scorebug_exact-final.log) | 2026-09-15T21:01:26.211286+00:00 | 83.085 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [repin-capsule-final](reports/b71_s3/repin-capsule-final.log) | 2026-09-15T21:02:06.361653+00:00 | 11.035 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_projection](reports/b71_s3/test_nfl2k5_scorebug_projection.log) | 2026-09-15T21:02:31.610116+00:00 | 57.746 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_projection.py` |
| [test_nfl2k5_scorebug_fonts-final](reports/b71_s3/test_nfl2k5_scorebug_fonts-final.log) | 2026-09-15T21:02:49.325022+00:00 | 8.132 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze-final](reports/b71_s3/test_nfl2k5_scorebug_freeze-final.log) | 2026-09-15T21:02:57.484726+00:00 | 243.26 | 0 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [test_nfl2k5_scorebug_resources](reports/b71_s3/test_nfl2k5_scorebug_resources.log) | 2026-09-15T21:03:29.388546+00:00 | 112.248 | 1 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_resources.py` |
| [pin-compiler-compact](reports/b71_s3/pin-compiler-compact.log) | 2026-09-15T21:05:01.429100+00:00 | 1.144 | 1 | `python3 reports/b71_s3/regenerate_pins.py` |
| [test_nfl2k5_scorebug_runtime](reports/b71_s3/test_nfl2k5_scorebug_runtime.log) | 2026-09-15T21:05:21.666878+00:00 | 117.973 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [test_nfl2k5_scorebug_mnf_v3-compact](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-compact.log) | 2026-09-15T21:06:00.051937+00:00 | 1.082 | 1 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [pin-compiler-compact-verified](reports/b71_s3/pin-compiler-compact-verified.log) | 2026-09-15T21:06:39.982534+00:00 | 45.645 | 0 | `python3 reports/b71_s3/regenerate_pins.py` |
| [test_nfl2k5_scorebug_freeze_v2-final](reports/b71_s3/test_nfl2k5_scorebug_freeze_v2-final.log) | 2026-09-15T21:07:00.779612+00:00 | 61.497 | 1 | `/usr/bin/python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [test_nfl2k5_scorebug_source_art](reports/b71_s3/test_nfl2k5_scorebug_source_art.log) | 2026-09-15T21:07:19.668334+00:00 | 0.482 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_source_art.py` |
| [test_nfl2k5_scorebug_template](reports/b71_s3/test_nfl2k5_scorebug_template.log) | 2026-09-15T21:07:20.180040+00:00 | 9.899 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_template.py` |
| [test_nfl2k5_scorebug_mnf_v3-compact-final](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-compact-final.log) | 2026-09-15T21:07:25.723824+00:00 | 33.784 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_template_release](reports/b71_s3/test_nfl2k5_scorebug_template_release.log) | 2026-09-15T21:07:30.110175+00:00 | 0.583 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_template_release.py` |
| [test_nfl2k5_scorebug_unified_adapter](reports/b71_s3/test_nfl2k5_scorebug_unified_adapter.log) | 2026-09-15T21:07:30.723045+00:00 | 0.17 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` |
| [test_nfl2k5_scorebug_v10_ingame](reports/b71_s3/test_nfl2k5_scorebug_v10_ingame.log) | 2026-09-15T21:07:30.922806+00:00 | 9.155 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` |
| [test_nfl2k5_scorebug_v10_projection](reports/b71_s3/test_nfl2k5_scorebug_v10_projection.log) | 2026-09-15T21:07:40.107871+00:00 | 29.951 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` |
| [repin-release](reports/b71_s3/repin-release.log) | 2026-09-15T21:07:48.561283+00:00 | 22.366 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_versions](reports/b71_s3/test_nfl2k5_scorebug_versions.log) | 2026-09-15T21:08:10.088157+00:00 | 10.023 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_versions.py` |
| [test_scorebug_studio_panel_qt](reports/b71_s3/test_scorebug_studio_panel_qt.log) | 2026-09-15T21:08:20.141962+00:00 | 7.443 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_scorebug_studio_panel_qt.py` |
| [proof-v3-release](reports/b71_s3/proof-v3-release.log) | 2026-09-15T21:08:26.353394+00:00 | 63.729 | 0 | `python3 reports/b71_s3/prove_v3.py` |
| [manifest-release](reports/b71_s3/manifest-release.log) | 2026-09-15T21:08:27.524667+00:00 | 368.874 | 0 | `python3 reports/b71_s3/refresh_manifest.py` |
| [test_apf_scorebug_workspace_qt-release](reports/b71_s3/test_apf_scorebug_workspace_qt-release.log) | 2026-09-15T21:08:27.565544+00:00 | 0.658 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_apf_scorebug_workspace_qt.py` |
| [test_nfl2k5_scorebug_assets-release](reports/b71_s3/test_nfl2k5_scorebug_assets-release.log) | 2026-09-15T21:08:27.567180+00:00 | 170.202 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_assets.py` |
| [nfl2k5_scorebug_layout_test](reports/b71_s3/nfl2k5_scorebug_layout_test.log) | 2026-09-15T21:08:27.615405+00:00 | 1.493 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/nfl2k5_scorebug_layout_test.py` |
| [test_nfl2k5_scorebug_author-release](reports/b71_s3/test_nfl2k5_scorebug_author-release.log) | 2026-09-15T21:08:28.256884+00:00 | 6.953 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_author.py` |
| [nfl2k5_scorebug_mod_project_test](reports/b71_s3/nfl2k5_scorebug_mod_project_test.log) | 2026-09-15T21:08:29.137318+00:00 | 1.37 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/nfl2k5_scorebug_mod_project_test.py` |
| [test_provider_integrity](reports/b71_s3/test_provider_integrity.log) | 2026-09-15T21:08:30.540888+00:00 | 9.223 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_provider_integrity.py` |
| [test_nfl2k5_scorebug_exact-release](reports/b71_s3/test_nfl2k5_scorebug_exact-release.log) | 2026-09-15T21:08:35.242273+00:00 | 83.77 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_exact.py` |
| [test_product_catalog](reports/b71_s3/test_product_catalog.log) | 2026-09-15T21:08:39.795806+00:00 | 0.16 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_product_catalog.py` |
| [test_phase1_packaging](reports/b71_s3/test_phase1_packaging.log) | 2026-09-15T21:08:39.985496+00:00 | 2.353 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_phase1_packaging.py` |
| [registry-strict](reports/b71_s3/registry-strict.log) | 2026-09-15T21:08:42.371603+00:00 | 0.17 | 0 | `/usr/bin/python3 -m mod_editor.capabilities.validate_registry` |
| [repin-before-source-commit](reports/b71_s3/repin-before-source-commit.log) | 2026-09-15T21:08:56.316751+00:00 | 11.145 | 0 | `python3 packaging/repin.py --apply` |
| [test_nfl2k5_scorebug_fonts-release](reports/b71_s3/test_nfl2k5_scorebug_fonts-release.log) | 2026-09-15T21:09:59.041491+00:00 | 9.0 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_fonts.py` |
| [test_nfl2k5_scorebug_freeze-release](reports/b71_s3/test_nfl2k5_scorebug_freeze-release.log) | 2026-09-15T21:10:08.072000+00:00 | 332.317 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_freeze.py` |
| [test_nfl2k5_scorebug_freeze_v2-release](reports/b71_s3/test_nfl2k5_scorebug_freeze_v2-release.log) | 2026-09-15T21:11:17.809800+00:00 | 418.219 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py` |
| [builder-plan-release](reports/b71_s3/builder-plan-release.log) | 2026-09-15T21:14:24.793293+00:00 | 0.363 | 0 | `python3 reports/b71_s3/build_testdisc71.py --plan-only` |
| [xbe-memory-release](reports/b71_s3/xbe-memory-release.log) | 2026-09-15T21:14:36.436663+00:00 | 1579.189 | 0 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` |
| [xbe-caves-release](reports/b71_s3/xbe-caves-release.log) | 2026-09-15T21:14:36.443914+00:00 | 1771.283 | 0 | `python3 tests/mod_editor/test_xbe_patch_cave_references.py` |
| [delivery-check-release](reports/b71_s3/delivery-check-release.log) | 2026-09-15T21:15:17.994071+00:00 | 0.45 | 0 | `python3 reports/b71_s3/check_delivery.py` |
| [test_nfl2k5_scorebug_ingame-release](reports/b71_s3/test_nfl2k5_scorebug_ingame-release.log) | 2026-09-15T21:15:40.431297+00:00 | 16.002 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_ingame.py` |
| [test_nfl2k5_scorebug_ingame_fix-release](reports/b71_s3/test_nfl2k5_scorebug_ingame_fix-release.log) | 2026-09-15T21:15:56.464240+00:00 | 135.588 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py` |
| [test_nfl2k5_scorebug_mnf-release](reports/b71_s3/test_nfl2k5_scorebug_mnf-release.log) | 2026-09-15T21:18:12.082605+00:00 | 12.08 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_mnf.py` |
| [test_nfl2k5_scorebug_mnf_v3-release](reports/b71_s3/test_nfl2k5_scorebug_mnf_v3-release.log) | 2026-09-15T21:18:16.059198+00:00 | 32.929 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py` |
| [test_nfl2k5_scorebug_native-release](reports/b71_s3/test_nfl2k5_scorebug_native-release.log) | 2026-09-15T21:18:24.193681+00:00 | 130.74 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_native.py` |
| [test_nfl2k5_scorebug_projection-release](reports/b71_s3/test_nfl2k5_scorebug_projection-release.log) | 2026-09-15T21:18:49.017483+00:00 | 56.575 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_projection.py` |
| [test_nfl2k5_scorebug_resources-release](reports/b71_s3/test_nfl2k5_scorebug_resources-release.log) | 2026-09-15T21:19:45.621536+00:00 | 244.834 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_resources.py` |
| [test_nfl2k5_scorebug_runtime-release](reports/b71_s3/test_nfl2k5_scorebug_runtime-release.log) | 2026-09-15T21:20:34.963148+00:00 | 117.87 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_runtime.py` |
| [test_nfl2k5_scorebug_source_art-release](reports/b71_s3/test_nfl2k5_scorebug_source_art-release.log) | 2026-09-15T21:22:32.864880+00:00 | 0.49 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_source_art.py` |
| [test_nfl2k5_scorebug_template-release](reports/b71_s3/test_nfl2k5_scorebug_template-release.log) | 2026-09-15T21:22:33.383822+00:00 | 9.906 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_template.py` |
| [test_nfl2k5_scorebug_template_release-release](reports/b71_s3/test_nfl2k5_scorebug_template_release-release.log) | 2026-09-15T21:22:43.319796+00:00 | 0.575 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_template_release.py` |
| [test_nfl2k5_scorebug_unified_adapter-release](reports/b71_s3/test_nfl2k5_scorebug_unified_adapter-release.log) | 2026-09-15T21:22:43.924081+00:00 | 0.167 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py` |
| [test_nfl2k5_scorebug_v10_ingame-release](reports/b71_s3/test_nfl2k5_scorebug_v10_ingame-release.log) | 2026-09-15T21:22:44.120010+00:00 | 9.182 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py` |
| [test_nfl2k5_scorebug_v10_projection-release](reports/b71_s3/test_nfl2k5_scorebug_v10_projection-release.log) | 2026-09-15T21:22:53.334695+00:00 | 28.071 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py` |
| [test_nfl2k5_scorebug_versions-release](reports/b71_s3/test_nfl2k5_scorebug_versions-release.log) | 2026-09-15T21:23:21.434239+00:00 | 9.357 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_nfl2k5_scorebug_versions.py` |
| [test_scorebug_studio_panel_qt-release](reports/b71_s3/test_scorebug_studio_panel_qt-release.log) | 2026-09-15T21:23:30.820569+00:00 | 7.251 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_scorebug_studio_panel_qt.py` |
| [nfl2k5_scorebug_layout_test-release](reports/b71_s3/nfl2k5_scorebug_layout_test-release.log) | 2026-09-15T21:23:38.099322+00:00 | 1.35 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/nfl2k5_scorebug_layout_test.py` |
| [nfl2k5_scorebug_mod_project_test-release](reports/b71_s3/nfl2k5_scorebug_mod_project_test-release.log) | 2026-09-15T21:23:39.477483+00:00 | 1.304 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/nfl2k5_scorebug_mod_project_test.py` |
| [test_provider_integrity-release](reports/b71_s3/test_provider_integrity-release.log) | 2026-09-15T21:23:40.809626+00:00 | 8.225 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_provider_integrity.py` |
| [test_product_catalog-release](reports/b71_s3/test_product_catalog-release.log) | 2026-09-15T21:23:49.065788+00:00 | 0.15 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_product_catalog.py` |
| [test_phase1_packaging-release](reports/b71_s3/test_phase1_packaging-release.log) | 2026-09-15T21:23:49.245319+00:00 | 2.079 | 0 | `/usr/bin/python3 /home/noah/2k-worktrees/astra-b71-s3/tests/mod_editor/test_phase1_packaging.py` |
| [registry-strict-release](reports/b71_s3/registry-strict-release.log) | 2026-09-15T21:23:51.355126+00:00 | 0.159 | 0 | `/usr/bin/python3 -m mod_editor.capabilities.validate_registry` |
| [source-art-skip-details](reports/b71_s3/source-art-skip-details.log) | 2026-09-15T21:24:48.344334+00:00 | 0.761 | 0 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` |
| [layout-skip-details](reports/b71_s3/layout-skip-details.log) | 2026-09-15T21:24:48.357031+00:00 | 1.478 | 0 | `env NFL2K5_SCOREBUG_EMULATION_TEST=1 python3 tests/nfl2k5_scorebug_layout_test.py -v` |
