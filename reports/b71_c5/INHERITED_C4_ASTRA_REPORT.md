# Beta 71 C4: day and afternoon Broadcast defaults

All required checks pass, including both detached XBE gates (119 / 131 tests), all 477 bundle pins, seven rig read-backs, controls/reset suites, strict registry and final repin. The additional oracle passes 29 tests against the documented scratch projection; the protected release manifest still needs integration regeneration.

## Delivery and scope

- Private branch `astra/b71-c4-day-afternoon`, based on A5 `a7440f05`, with C3 `45a5ade9` merged first. Merge `ddaaf5c4` retains both lines of work and all RC96 bullets; original reports/messages are archived under `reports/b71_a5/INHERITED_*` and `reports/b71_c3/INHERITED_*`.
- Private Git directory: `.scratch/astra-c4.git`. The linked worktree/shared branch refs remain untouched. The C3 shared branch ref was stale, so the explicitly requested commit was used. Merge staging used an explicit path list and `commit-tree` with both parents; later commits use `git commit -- <explicit paths>`. See `reports/b71_c4/merge.json` and commit logs.
- Implementation commit: `f9c2ac27`. The final evidence commit is included in `.scratch/astra-b71-c4.bundle`; the incremental bundle requires A5 `a7440f05` and contains C3 history. No push.
- Only the default **day** and **afternoon** rig bytes change from C3/v2.1. All 477 stadium bundle pins and the other five rigs are pinned unchanged. No scorebug or widescreen owner source differs from A5.
- The shared turf saturation control remains 1.12, hue target 72, pull 0.50, value curve 2.8. Changing these shared controls would alter approved night/dome turf. Daylight desaturation is accomplished through the two rig channel gains, with warm direct sunlight and cool sky fill. This is not a blanket brightness reduction: the old daylight model was dark and saturated; the revised model raises blue while holding value near 0.40.
- 55 controls remain. Five numeric defaults change (day ambient/key/fill; afternoon ambient/fill). The two daylight balance labels now say “Light colour / shadow recipe” because they also interpolate the shadow scalar. Retail, per-rig Off and recipe Off restore the retail scalar; Broadcast restores C4. Reset tests preserve master On and Off, and all three presets still default the option Off.
- C3 GUI/build/registry wiring is merged directly. C4 updates the existing owner, its pins/provider expectation, two GUI labels, tests, documentation and the existing capability description. No capability rows are added, no build dispatcher is edited beyond the C3 merge, and no deferred GUI wiring is needed.

## Before / after, per condition

The reference map below is the calibrated report’s (181,216,102), not a decoded stadium mean. SCREEN_FACTOR remains exactly day (0.21,0.21,0.21), night (0.183,0.183,0.165); afternoon keeps the existing night-factor fallback and is explicitly an extrapolation. The beta-70 model still reproduces (51,61,32).

| Condition | v2.1 prediction | C4 prediction | Broadcast reference | C4 saturation | C4 value |
|---|---|---|---|---:|---:|
| day | (83, 99, 47) | (89, 105, 61) | (88, 105, 61) | 0.419 | 0.412 |
| afternoon | (67, 78, 32) | (87, 103, 61) | (98, 119, 72) | 0.408 | 0.404 |
| night_indoor | (102, 122, 52) | (102, 122, 52) | (107, 121, 53) | 0.574 | 0.478 |
| alt_day | (74, 89, 38) | (74, 89, 38) | No separate C4 target | 0.573 | 0.349 |
| alt_dynamic | (73, 88, 38) | (73, 88, 38) | No separate C4 target | 0.568 | 0.345 |
| rain | (78, 95, 43) | (78, 95, 43) | No separate C4 target | 0.547 | 0.373 |
| snow | (74, 90, 40) | (74, 90, 40) | No separate C4 target | 0.556 | 0.353 |

Day is within one red level of (88,105,61). Afternoon remains below its broadcast median (98,119,72), intentionally retaining value 0.404 rather than pushing to 0.467. The day reference RGB actually computes to hue 83.18°; C4 is 81.82°. The supplied screenshot sample (80,95,45) computes to 78°. The tune follows the supplied RGB/saturation target and warms the direct sun, rather than claiming a lower turf hue angle.

![Model-only turf swatches](reports/b71_c4/predicted-swatches.png)

| Rig lever | Day before → after | Afternoon before → after |
|---|---|---|
| Ambient RGB | (0.94,0.96,1) unchanged | (1,0.95,0.86) → (1,0.96,1) |
| Ambient strength | 0.58 → 0.44 | 0.45 → 0.60 |
| Key RGB | (1,0.98,0.94) → (1,0.94,0.88) | (1,0.94,0.84) → (1,0.91,0.78) |
| Key strength | 1.20 → 1.60 | 1.20 unchanged |
| Fill RGB | (0.90,0.94,1) → (0.32,0.40,1) | (0.70,0.78,1) → (0.40,0.445,1), twice |
| Fill strength | 0.48 → 0.99 | 0.26 → 1.04, twice |
| Shadow scalar +0x100 | 0.275 → 0.32 | 0.27 → 0.22 |
| Key / ambient intensity | 2.069 → 3.636 | 2.667 → 2.000 |
| Total directional / ambient intensity | 2.897 → 5.886 | 3.822 → 5.467 |
| Light count | 2 unchanged | 3 unchanged |

Gain and colour-recipe sliders still default to 1. The stronger blue fill compensates the existing map/screen blue loss while keeping sunlight warmer. White uniforms, shaded players and skin are outside the turf model and must be checked for a blue cast or clipping. No such appearance is claimed proved.

## Shadow and executable proof

**PROVED:** retail day stores key vector (0.433,0.866,0.25), about 60° elevation; afternoon stores (0,0.43,0.903), about 25.46°. Ideal flat-ground shadow length per unit height from those vectors is 0.577 and 2.10 respectively. These are geometric calculations, not rendered measurements. The retail selector replaces the afternoon vector from the stadium sun node (`0x642ee` onward), so a stadium’s actual afternoon direction can differ. All direction bytes, counts, selector/installer/push guards and runtime selection logic remain retail. No new direction is authored.

**PROVED by bounded native execution:** `0x64000` reads selected rig +0x100; `0x12fb8d` calls it and negates it; `0x2af50` writes the resulting light descriptor. Unicorn executes these actual routines with each of the seven decoded tables, preserving the direction vector, descriptor type 1 and mask -1, and producing intensity -0.32 for day, -0.22 for afternoon and the original five other values. This scalar controls a negative light term. It is **not** a blur radius or a sun-angle parameter. C4 gives day stronger shadow contrast and afternoon a gentler term with more ambient relative to its key; rendered hardness, softness and length remain **UNWITNESSED**.

**PROVED:** default XBE apply, exact replay and restore; custom recipe apply/replay/restore; foreign-byte refusal; section digests; all changed offsets confined to owned colour/intensity floats and the two +0x100 words. Full tables are already reserved in place in writable `.rdata`, with no code/cave/request growth. `daylight-proof.json` includes every rig’s retail, old applied and new applied SHA-256, decoded values, exact changed offsets, directions, native descriptor and code fingerprints.

| Rig | C4 applied SHA-256 | Change from v2.1 |
|---|---|---|
| day | `e77439624117ce755c72533701ad83395cd60e071ec0c7ad4b9b3a3d190df7bf` | Daylight tune |
| night_indoor | `18c6d914b12edc22d092cea97b7839d4f4611e23b5a898cbceeb4d74222b9fb9` | Exact pin retained |
| alt_day | `f6f80216e8cf2010b84fcaa46a9a6b50728c27bca47b1ed7c13810fdc220751c` | Exact pin retained |
| alt_dynamic | `00ce7e0fafa7b22c47925dd57ca01e8f362930627478f127023f797de8818887` | Exact pin retained |
| rain | `ccfb026911c23bd9f5505f98599b70e19cb8b2e17b9412a6f3cdc64c65bec890` | Exact pin retained |
| snow | `8c95f170e019d0eb8654b3b3e23fc1c6d78d4d593f5ad1df6c32c00c493d5ee4` | Exact pin retained |
| afternoon | `f025a2fa059ad96e560c05b331a530dfef1bbd076a362f1982c903b6d0f8deeb` | Daylight tune |

## Bundle and decoder proof

**PROVED:** all 477 complete retail/applied bundle records exactly retain v2.1. The canonical bundle-record digest is `f4ef2c5a179ad39a07f4670ed924e3c4a605a6a2775518a78aa790306c706295`. `data/nfl2k5_modern_color_pins.json` changes only the two applied rig hashes; it contains the retail/modern pins for every bundle and rig. The exhaustive verifier rebuilds all pins from read-only retail, refits 390 distinct spans, reparses the outputs and compares the complete records. It passed in 331.847 seconds. Palette, divot, bump/mips, tint, outside grass, end zones and fixed wrappers receive no new changes.

Six representative bundles were also rebuilt in memory, checked against the full pins and decoded independently. All 32-byte wrappers and decoded sizes remain exact. Rounded decoded means differ from the calibrated report’s median; they must not be presented as the same sample.

| Bundle | Retail decoded map / word | C4 decoded map / word | Rig | Predicted turf |
|---|---|---|---|---|
| s08dd.iff | (98, 128, 60) | (177, 219, 88) | day | (87, 107, 52) |
| s13dd.iff | (103, 125, 65) | (183, 216, 100) | day | (90, 105, 60) |
| s13ad.iff | (103, 125, 65) | (183, 216, 100) | afternoon | (88, 103, 60) |
| s13nd.iff | (103, 125, 65) | (183, 216, 100) | night_indoor | (103, 122, 51) |
| s11dd.iff | (52, 90, 61) | (119, 180, 95) | night_indoor | (67, 101, 48) |
| s09dd.iff | (64, 96, 51) | (142, 187, 89) | night_indoor | (80, 105, 45) |

The s08 day mean still predicts more saturation than the broadcast day reference: (87,107,52), saturation 0.514. That is a limitation of a shared rig across different maps, not a hidden exact-match claim. The supplied measured screenshot sample (80,95,45), far-field saturation 0.69, bump shading and wear coverage are not a fresh calibration here. The model does not prove the far-field band reaches 0.42. Night/dome decoded maps and their predictions above are unchanged from v2.1.

## Gates and regressions

All commands run offscreen with `PYTHONPATH` set to this worktree. The required XBE gates were launched using the literal detached pattern below, with a retained tool session to keep the parent tool context alive. They run in separate sessions, with stdin detached and output logged; polling reads the files/tool session. No process-name kill was used.

```sh
setsid nohup python3 reports/b71_c4/run_check.py xbe_memory_writes python3 tests/mod_editor/test_xbe_patch_memory_writes.py > reports/b71_c4/xbe_memory_writes.launch.log 2>&1 < /dev/null &
setsid nohup python3 reports/b71_c4/run_check.py xbe_cave_references python3 tests/mod_editor/test_xbe_patch_cave_references.py > reports/b71_c4/xbe_cave_references.launch.log 2>&1 < /dev/null &
wait
```

The global gates are supplemented with the actual C4 writer read-back and focused composition proof: six application orders of lighting, scorebug runtime and widescreen give identical bytes, all three statuses stay applied, replay is exact, and restoring lighting independently preserves its peers.

| Check | Result | Process seconds |
|---|---|---:|
| [colour_legacy](reports/b71_c4/colour_legacy.log) | PASS (10 tests) | 6.771 |
| [colour_controls_final](reports/b71_c4/colour_controls_final.log) | PASS (9 tests) | 14.317 |
| [colour_gui](reports/b71_c4/colour_gui.log) | PASS (5 tests) | 2.097 |
| [all_default_pins](reports/b71_c4/all_default_pins.log) | PASS | 331.847 |
| [daylight_readback](reports/b71_c4/daylight_readback.log) | PASS | 33.246 |
| [daylight_composition](reports/b71_c4/daylight_composition.log) | PASS (1 tests) | 26.542 |
| [build_panel](reports/b71_c4/build_panel.log) | PASS (13 tests) | 4.326 |
| [mod_build](reports/b71_c4/mod_build.log) | PASS (13 tests) | 3.102 |
| [project_settings](reports/b71_c4/project_settings.log) | PASS (17 tests) | 1.574 |
| [providers](reports/b71_c4/providers.log) | PASS (33 tests) | 4.073 |
| [provider_integrity_updated](reports/b71_c4/provider_integrity_updated.log) | PASS (8 tests) | 10.405 |
| [phase1_packaging](reports/b71_c4/phase1_packaging.log) | PASS (23 tests) | 3.049 |
| [product_catalog](reports/b71_c4/product_catalog.log) | PASS (9 tests) | 0.221 |
| [registry_final](reports/b71_c4/registry_final.log) | PASS | 0.159 |
| [builder_source](reports/b71_c4/builder_source.log) | PASS | 0.038 |
| [xbe_memory_writes](reports/b71_c4/xbe_memory_writes.log) | PASS (119 tests) | 1595.995 |
| [xbe_cave_references](reports/b71_c4/xbe_cave_references.log) | PASS (131 tests) | 1780.148 |
| [manifest_projection_final](reports/b71_c4/manifest_projection_final.log) | PASS | 9.220 |
| [cave_oracle_projected](reports/b71_c4/cave_oracle_projected.log) | PASS (29 tests) | 369.076 |
| [scope_audit](reports/b71_c4/scope_audit.log) | PASS | 0.194 |
| [repin_final](reports/b71_c4/repin_final.log) | PASS | 10.660 |

### Failed attempts and their disposition

- Strict registry initially failed on missing `docs/research/apf_audio.md`. The existing C3 inventory supplied 75 missing research/metadata documents by read-only byte copies; no retail executable, texture, pack, disc, embedded GLTF buffer or hard link was introduced. These hydrated documents are excluded from commits; `evidence-hydration.json` records their identities. Strict validation then passes with 174 capabilities.
- Provider integrity initially found its C3 data-pin test expectation still at the old two-rig hashes. The expected file digest was updated to the current pinned data JSON; all eight provider-integrity tests now pass. `packaging/repin.py --apply` updates the owner and data source pins in `providers.py`; final runs report no remaining changes.
- The unmodified release-manifest oracle run fails two tests because the protected manifest has five stale source fingerprints: inherited build/scorebug sources plus the colour owner. The release manifest is intentionally not edited. The scratch projection records actual scorebug scene, runtime and colour writes; checks them against unchanged historical owner reservations; and separately verifies recomputed section/allocator digests. Early projection attempts refused nested scorebug scene attribution and shared digest metadata; the final proof attributes the scene to its own writer and bounds checksum exceptions to the verified digest fields. It does not weaken executable write checks or add/free reservations. Build/resource helper fingerprints are explicitly snapshots, not renewed disc-build evidence. Historical disc fields stay marked historical. The final oracle run uses this projection; production manifest regeneration remains required during integration.

## Prepared combined test-disc builder

`reports/b71_c4/build_testdisc71.py` is prepared and **has not been imported or executed**, including its plan-only path. `check_builder_source.py` parses/compiles the AST and verifies its constants/options without running the builder.

- Name: `NFL 2K5 MOD TEST 2026-09-15g (day tuning + scorebug v2 + widescreen)`.
- Preset: `softdrink_advanced` (Advanced).
- Explicit options: `scorebug=True`, `scorebug_runtime=True`, `modern_color=True`, `widescreen=True`.
- Original retail xiso as source; output under `/home/noah/2K5 Mod Studio Builds`, which is read-only in this sandbox.
- Refuses existing named outputs and tests directory access before pruning. Deletes oldest `*MOD TEST*.iso` images until there are fewer than three, leaving room for this one. Preserves every `.2k5patch` archive and verifies their size/mtime afterward. Postcondition: at most three test images.
- Read-back: scorebug resources/runtime, modern-colour XBE, all 477 bundle pins, all seven rig pins including the immutable night hash, and widescreen 16:9. Exports the accompanying `.2k5patch`. C3 build code publishes the colour recipe sidecar. Incomplete images are cleaned up; a fully verified disc is retained if only patch export fails.

Integrator command (not run here):

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -u reports/b71_c4/build_testdisc71.py
```

The shared release cave manifest must be regenerated during normal integration. For the reproducible bounded oracle check, run `python3 reports/b71_c4/project_manifest.py`, then `NFL2K5_CAVE_MANIFEST=.scratch/b71_c4_manifest.json PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_cave_oracle.py`.

## PROVED / UNWITNESSED

**PROVED:** exact data writes/pins, lower predicted daylight turf saturation, preserved approved night/dome bytes, unchanged retail light directions/counts and selector, negative native shadow-light term, 55 controls and both resets, serialization/persistence, exhaustive default refits, decoder read-back, custom refusals and receipts, focused scorebug/widescreen composition, strict registry and provider pins, and the prepared builder’s static contract. Gate verdicts are reported above only after completion.

**UNWITNESSED:** final day/afternoon appearance, shadow length/edge softness, whether shadows read naturally at each stadium’s actual sun angle, far-field saturation/shimmer, clipping or blue fill on white uniforms/skin, every extrapolated class/condition prediction, and the new combined disc build. No xemu, display server, audio or network was opened; no disc/pack was copied or built.

Witness recipe: build image g from original retail, compare day and afternoon at matched camera/resolution and weather, inspect midfield and far field, bright and shaded white uniforms, skin, player/stadium shadows, sidelines/end zones and stripe detail. Then compare night and dome against the approved build to confirm the preserved bytes render as expected. Keep the colour sidecar and build receipts with the test disc.

## Command ledger

`run_check.py` records each command’s exact argument vector, UTC start/end, process exit and monotonic duration beside its complete log. The table includes failed attempts. Final commit/bundle/import commands are recorded separately in `.scratch/handoff-ledger.json` to avoid a self-referential evidence commit. Git setup/merge ancestry and its explicit path inventory are in `merge.json`; exploratory read-only searches are not test claims.

| Check / log | Exact command | Exit | Seconds | UTC start | UTC end |
|---|---|---:|---:|---|---|
| [repin_merge](reports/b71_c4/repin_merge.log) | `python3 packaging/repin.py --apply` | 0 | 10.838 | 2026-09-15T19:56:38.447072+00:00 | 2026-09-15T19:56:49.284792+00:00 |
| [repin_tuning](reports/b71_c4/repin_tuning.log) | `python3 packaging/repin.py --apply` | 0 | 22.633 | 2026-09-15T19:58:23.239247+00:00 | 2026-09-15T19:58:45.871781+00:00 |
| [xbe_memory_writes](reports/b71_c4/xbe_memory_writes.log) | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 0 | 1595.995 | 2026-09-15T19:58:24.508738+00:00 | 2026-09-15T20:25:00.503469+00:00 |
| [xbe_cave_references](reports/b71_c4/xbe_cave_references.log) | `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 0 | 1780.148 | 2026-09-15T19:58:24.510917+00:00 | 2026-09-15T20:28:04.658738+00:00 |
| [colour_legacy](reports/b71_c4/colour_legacy.log) | `python3 tests/mod_editor/test_nfl2k5_modern_color.py` | 0 | 6.771 | 2026-09-15T19:59:53.776365+00:00 | 2026-09-15T20:00:00.547446+00:00 |
| [colour_gui](reports/b71_c4/colour_gui.log) | `python3 tests/mod_editor/test_colour_lighting_qt.py` | 0 | 2.097 | 2026-09-15T19:59:54.934654+00:00 | 2026-09-15T19:59:57.031459+00:00 |
| [registry_strict](reports/b71_c4/registry_strict.log) | `python3 -m mod_editor.capabilities.validate_registry` | 1 | 0.137 | 2026-09-15T19:59:54.945216+00:00 | 2026-09-15T19:59:55.081993+00:00 |
| [colour_controls](reports/b71_c4/colour_controls.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 14.173 | 2026-09-15T19:59:54.956793+00:00 | 2026-09-15T20:00:09.129568+00:00 |
| [all_default_pins](reports/b71_c4/all_default_pins.log) | `python3 tools/verify_colour_lighting_pins.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --workers 8` | 0 | 331.847 | 2026-09-15T19:59:54.961428+00:00 | 2026-09-15T20:05:26.808338+00:00 |
| [evidence_hydration](reports/b71_c4/evidence_hydration.log) | `python3 reports/b71_c4/hydrate_evidence.py` | 0 | 0.114 | 2026-09-15T20:01:16.240860+00:00 | 2026-09-15T20:01:16.355138+00:00 |
| [registry_hydrated](reports/b71_c4/registry_hydrated.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.237 | 2026-09-15T20:01:56.852352+00:00 | 2026-09-15T20:01:57.088887+00:00 |
| [repin_controls](reports/b71_c4/repin_controls.log) | `python3 packaging/repin.py --apply` | 0 | 12.577 | 2026-09-15T20:01:57.127679+00:00 | 2026-09-15T20:02:09.704526+00:00 |
| [daylight_readback](reports/b71_c4/daylight_readback.log) | `python3 reports/b71_c4/prove_daylight.py` | 0 | 33.246 | 2026-09-15T20:03:57.664254+00:00 | 2026-09-15T20:04:30.910556+00:00 |
| [mod_build](reports/b71_c4/mod_build.log) | `python3 tests/mod_editor/test_mod_build.py` | 0 | 3.102 | 2026-09-15T20:04:16.512576+00:00 | 2026-09-15T20:04:19.614182+00:00 |
| [build_panel](reports/b71_c4/build_panel.log) | `python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 4.326 | 2026-09-15T20:04:16.543176+00:00 | 2026-09-15T20:04:20.869315+00:00 |
| [provider_integrity](reports/b71_c4/provider_integrity.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 1 | 13.032 | 2026-09-15T20:04:16.567393+00:00 | 2026-09-15T20:04:29.599549+00:00 |
| [product_catalog](reports/b71_c4/product_catalog.log) | `python3 tests/mod_editor/test_product_catalog.py` | 0 | 0.221 | 2026-09-15T20:04:16.591283+00:00 | 2026-09-15T20:04:16.812064+00:00 |
| [phase1_packaging](reports/b71_c4/phase1_packaging.log) | `python3 tests/mod_editor/test_phase1_packaging.py` | 0 | 3.049 | 2026-09-15T20:04:16.612504+00:00 | 2026-09-15T20:04:19.661274+00:00 |
| [cave_oracle](reports/b71_c4/cave_oracle.log) | `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 1 | 369.854 | 2026-09-15T20:04:16.627020+00:00 | 2026-09-15T20:10:26.481469+00:00 |
| [daylight_composition](reports/b71_c4/daylight_composition.log) | `python3 tests/mod_editor/test_nfl2k5_daylight_composition.py` | 0 | 26.542 | 2026-09-15T20:05:36.055009+00:00 | 2026-09-15T20:06:02.596926+00:00 |
| [colour_controls_final](reports/b71_c4/colour_controls_final.log) | `python3 tests/mod_editor/test_colour_lighting.py` | 0 | 14.317 | 2026-09-15T20:05:37.198110+00:00 | 2026-09-15T20:05:51.515478+00:00 |
| [project_settings](reports/b71_c4/project_settings.log) | `python3 tests/mod_editor/test_discord_bugs_1.py` | 0 | 1.574 | 2026-09-15T20:05:37.228648+00:00 | 2026-09-15T20:05:38.802336+00:00 |
| [provider_integrity_updated](reports/b71_c4/provider_integrity_updated.log) | `python3 tests/mod_editor/test_provider_integrity.py` | 0 | 10.405 | 2026-09-15T20:05:37.240069+00:00 | 2026-09-15T20:05:47.645479+00:00 |
| [providers](reports/b71_c4/providers.log) | `python3 tests/mod_editor/test_providers.py` | 0 | 4.073 | 2026-09-15T20:05:37.253190+00:00 | 2026-09-15T20:05:41.325910+00:00 |
| [builder_source](reports/b71_c4/builder_source.log) | `python3 reports/b71_c4/check_builder_source.py` | 0 | 0.038 | 2026-09-15T20:07:07.327971+00:00 | 2026-09-15T20:07:07.366169+00:00 |
| [repin_checkpoint](reports/b71_c4/repin_checkpoint.log) | `python3 packaging/repin.py --apply` | 0 | 10.627 | 2026-09-15T20:07:34.214286+00:00 | 2026-09-15T20:07:44.840988+00:00 |
| [registry_final](reports/b71_c4/registry_final.log) | `python3 -m mod_editor.capabilities.validate_registry` | 0 | 0.159 | 2026-09-15T20:08:04.137702+00:00 | 2026-09-15T20:08:04.296852+00:00 |
| [commit_daylight](reports/b71_c4/commit_daylight.log) | `git --git-dir=.scratch/astra-c4.git commit -m 'Tune Broadcast day and afternoon rigs while pinning approved night and all turf bundles' -- data/nfl2k5_modern_color_pins.json docs/mod_editor/2k5_mod_studio_changelog.md docs/modern_color/CONTROLS.md mod_editor/capabilities/registry.v1.json mod_editor/core/nfl2k5_modern_color.py mod_editor/core/providers.py mod_editor/gui/colour_lighting_qt.py tests/mod_editor/test_colour_lighting.py tests/mod_editor/test_colour_lighting_qt.py tests/mod_editor/test_nfl2k5_modern_color.py tests/mod_editor/test_provider_integrity.py tests/mod_editor/test_nfl2k5_daylight_composition.py tools/verify_colour_lighting_pins.py` | 0 | 0.080 | 2026-09-15T20:08:04.446222+00:00 | 2026-09-15T20:08:04.526082+00:00 |
| [swatches](reports/b71_c4/swatches.log) | `python3 reports/b71_c4/render_swatches.py` | 0 | 1.343 | 2026-09-15T20:08:37.188957+00:00 | 2026-09-15T20:08:38.531466+00:00 |
| [manifest_projection](reports/b71_c4/manifest_projection.log) | `python3 reports/b71_c4/project_manifest.py` | 1 | 5.995 | 2026-09-15T20:11:35.651285+00:00 | 2026-09-15T20:11:41.646555+00:00 |
| [manifest_projection_digest](reports/b71_c4/manifest_projection_digest.log) | `python3 reports/b71_c4/project_manifest.py` | 1 | 5.637 | 2026-09-15T20:12:36.452353+00:00 | 2026-09-15T20:12:42.089133+00:00 |
| [manifest_projection_owned](reports/b71_c4/manifest_projection_owned.log) | `python3 reports/b71_c4/project_manifest.py` | 1 | 9.075 | 2026-09-15T20:13:49.571699+00:00 | 2026-09-15T20:13:58.646600+00:00 |
| [manifest_projection_final](reports/b71_c4/manifest_projection_final.log) | `python3 reports/b71_c4/project_manifest.py` | 0 | 9.220 | 2026-09-15T20:14:30.964242+00:00 | 2026-09-15T20:14:40.183896+00:00 |
| [cave_oracle_projected](reports/b71_c4/cave_oracle_projected.log) | `env NFL2K5_CAVE_MANIFEST=.scratch/b71_c4_manifest.json python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 0 | 369.076 | 2026-09-15T20:17:22.262170+00:00 | 2026-09-15T20:23:31.337909+00:00 |
| [scope_audit](reports/b71_c4/scope_audit.log) | `python3 reports/b71_c4/audit_delivery.py` | 0 | 0.194 | 2026-09-15T20:19:09.943187+00:00 | 2026-09-15T20:19:10.137392+00:00 |
| [repin_final](reports/b71_c4/repin_final.log) | `python3 packaging/repin.py --apply` | 0 | 10.660 | 2026-09-15T20:27:54.232204+00:00 | 2026-09-15T20:28:04.892583+00:00 |
| [final_checks](reports/b71_c4/final_checks.log) | `python3 reports/b71_c4/final_checks.py` | 0 | 0.045 | 2026-09-15T20:29:15.487043+00:00 | 2026-09-15T20:29:15.532543+00:00 |
