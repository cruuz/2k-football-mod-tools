# Beta 69 A2b integration report

Integrated J4 weather, J3 MyCareer and J5 modern rules onto the A2 stack. All new controls are Experimental and Off/Retail in every preset. No time-of-day option was added: J4 proved retail already chooses time of day from the schedule. The coin control retains “CPU winners only”; this does not add a human Defer choice.

The protected production manifest `data/nfl2k5_cave_reservations.json` is unchanged. **Claude must regenerate it as the last release commit. Allocation changed because J5 adds seven REQUESTS; J3 and J4 do not change allocations.** Offline/native proofs below do not certify played gameplay; all player-visible game outcomes remain UNWITNESSED.

## Import and commit history

Base: `05d3f0b5d291e22591c64c89994af35dcc5d38c4`, the current `local/stack-beta-69` after A2 (markers, J8, J2, J1, J6, J9, J7). Target branch: `astra/b69-a2b-integrate-game`.

| Job | Imported head | Integration merge |
| --- | --- | --- |
| J4, branch in this repo | `f0d1ab536665926e53d5fc5e5d0a6c331791032e` | `8cf389e61f1da344e475f5b2f110d5a220ae9a61` |
| J3, verified `ASTRA_J3.bundle` | `68b3818b5299386390f648309e273723b64859bb` | `54f5b8c8b5f244380ed06dbbb3acdc05f8a6e35a` |
| J5, verified `ASTRA_J5.bundle` | `9afe21c031fccd47cf086c8421e69bc58e8e7e9f` | `b594933581d18c3c344964788a9bde6cb7158c96` |

Each job contributes all three commits and is a genuine two-parent merge. Each merge used `git mv` for the job-root report and wiring before the merge commit: `ASTRA_B69_J3_REPORT.md`, `ASTRA_B69_J4_REPORT.md`, `ASTRA_B69_J5_REPORT.md` and `WIRING_B69_J3.md`, `WIRING_B69_J4.md`, `WIRING_B69_J5.md`. All beta-69 changelog bullets were retained under `## v1.0 RC94, beta 69`. There were no allocator-list conflicts to hand-merge. Provider pins were recomputed.

The shared worktree Git directory is read-only. Commits live in writable Git store `/tmp/astra-a2b-git-3aypls8d` on the requested branch, using read-only alternate objects for the original history. `/tmp/a2b-git` addresses this store. `70628137` applies the protected wiring. `77fcc3c4` fixes integrated replay and adds bounded integration/non-POSIX tests. `fe5c2ad2` adds relocated kickoff to that proof; `18930dc0` updates the legacy Gameplay test expectations; `be91cce3` records completed verification evidence. Commits stage explicit paths; `packaging/repin.py --apply` is the final content operation before each commit. The verified bundle is the portable delivery; the ordinary shared Git ref still points to the original stack head.

## Every protected wiring hunk

The complete before/after patch is [protected-wiring.patch](reports/b69_a2b/protected-wiring.patch), measured against A2. This is the exact diff, including every import, assignment, predicate, contract, pin and test expectation. The following map explains each group.

| File / insertion area | Integrated behavior |
| --- | --- |
| `mod_editor/core/mod_build.py`, BuildPlan/PRESETS/wants_xbe_patch | Adds climate JSON path, haze boolean, CPU-defer boolean, decided-clock boolean and margin/seconds, CPU-scramble enum. Explicit Off/Retail and 17/60 in all three presets. Climate alone is data-only; haze and rules request XBE work. |
| `mod_build.py`, availability/inspect | Adds both weather modules and three rules modules, reports climate availability from parsed ROST, haze recognized status, all rule states and verified installed settings. |
| `mod_build.py`, validation/preflight | Validates weather types; freezes and fully validates climate edits before copying; rejects empty/stale plans, non-v17 ROST, reserves16 and created-team growth. Haze requires known retail/applied bytes. Complete runtime settings are checked against the source before project preparation or copy. |
| `mod_build.py`, MyCareer dependency normalization | Generic creation enables draft-AI and depth locks. A prepared setup with nonzero prospect tier at frozen setup offset 212 enables depth locks. Uses J3's signed/frozen setup and existing provider path. |
| `mod_build.py`, first/final writer passes | Resets new allocation-dependent options for the initial pass, includes all J5 requests in the complete selected union and all allocator predicates, forwards five rule settings through R62 into final apply. Haze follows helmet finish and precedes final inspect; recognizes an installed patch and restores retail when Off. Climate is last, after resource relocation and ESPN writes, then reloaded and verified. |
| `mod_editor/core/nfl2k5_throw_tuning.py`, imports/options/adapters | Adds three rule imports, three R62_SPACE_KEYS and five R62_RUNTIME_KEYS; forwards parameters in both entrypoints, allocation selector and adapter. Validates booleans, clock encodings and Retail/Modern enum; CPU enum deferral explicitly restores `retail`. Adds request union/scaleout predicates, rule status/settings projection and clock-settings adapter. |
| `nfl2k5_throw_tuning.py`, mutation ordering | The owner loop installs coin defer, decided clock and CPU scrambles immediately after accelerated clock. The public/final path rejects foreign instructions and changed/off installed settings. A private intermediate pass can defer those checks only after the complete plan preflight. An unchanged private copy pass is allowed so identical full-plan replay completes; final writers still verify. |
| `mod_editor/core/nfl2k5_build_settings.py` | Adds all seven fields to explicit FEATURE_KEYS so saved plans, restored controls and cache/build identity retain them. Older plans receive safe defaults. |
| `mod_editor/gui/beta62_options.py` | Adds the two rule booleans using the job's exact captions/help. CPU scrambles remains an enum. |
| `mod_editor/gui/build_panel_qt.py` | Adds climate path/choose/editor/checkbox controls and validation/help, a reversible haze control, decided-clock cutoff selectors, and CPU-scramble Retail/Modern selector. Projects all into plan/save/has_work/confirmation text; resets Off defaults on presets; restores and locks installed rule/settings values; confirms haze restoration. |
| `mod_editor/gui/gameplay_patches_panel_qt.py` | Adds both rule checkboxes with exact captions, cutoff selectors and CPU enum; synchronizes selected values/summary/status and preserves installed choices. Adds haze's reversible toggle and climate editor entry. Climate action routes to Build via signal, with standalone dialog fallback. |
| `mod_editor/gui/gameplay_project_ui.py` | Shared Build/Gameplay link synchronizes margin, seconds and CPU level in both directions and persists weather path/haze with the other settings. |
| `mod_editor/gui/my_career_panel_qt.py` | Applies J3's exact proposed changes: three saved caller choices; one signed export carries caller and Supersim choices; prospect tiers on creation; four QB prototype aliases with Pocket default; tiered creation disables starter override and passes prospect_tier. Existing source/position behavior retained. |
| `mod_editor/gui/studio_qt.py` | Connects Gameplay's weather-editor action to the Build workspace/editor. The MyCareer workspace already constructs the protected MyCareerPanel, so its newly wired controls appear on that existing page without duplicating the page. |
| `mod_editor/capabilities/registry.v1.json` | Adds J3's two rows, J4's climate/haze rows and J5's three rows. Retargets evidence to renamed reports, enriches existing MyCareer evidence, keeps `runtime.status=not-tested`, canonicalizes with `json.dumps(obj, indent=2, sort_keys=True) + "\n"`. Every new validation_command is `python3 -m tests.mod_editor.<module>` without extra arguments. |
| `mod_editor/core/providers.py` | Adds the eight actual dependency sources to the unified writer closure and refreshes changed existing source hashes. Weather is a separate data/final writer path and is pinned by the runtime contract instead of falsely counted in the unified writer closure. |
| `packaging/release-allowlist.txt` | Adds ten core files, four shipped tools and two research documents: 16 files. Generated rules/MyCareer code ships as source; native compilers and Unicorn remain development tools. |
| `packaging/check_2k5_mod_studio_runtime.py` | Adds 14 runtime imports and a B69_GAME_RUNTIME_PINS block for separate weather/UI/tool dependencies. A new contract checks pins, Off defaults, saved FEATURE_KEYS, weather's empty REQUESTS, actual offscreen panels, installed setting behavior and caller/prototype/tier controls. Updates both shared registry count sites and 2K5 catalog count. |
| APF runtime and installer, Phase1 packaging, product/provider tests | Updates all shared count sites, 2K5 catalog totals/sections/exact IDs, and the unified closure count. Fixes the old MyCareer alias expectation to J3's actual four labels and updates the standalone Gameplay panel row/help/source-refusal expectations. |
| `mod_editor/core/nfl2k5_cave_manifest.py` | Registers haze and rules with the production recorder/build/replay verifier and includes all three rules REQUESTS in the complete dormant union. Reserves the complete four-byte haze coefficient, including unchanged bytes; no new cave/address constants. Claude will run this builder for release. |
| `tests/nfl2k5_allocator_stack.py` and pairwise gate | Includes J5 REQUESTS and strict owned projections; adds J4 haze to composed writers and pairwise comparisons. The known four-byte data site is reserved only after checking other-owner overlap. |
| `test_nfl2k5_playbook_pair_manifest.py` | Treats shared `nfl2k5_rules_patch` as a helper, like existing `rdata_sites`/`gameplay_lever`, so recorder wrapping attributes writes once to the calling owner. Actual write observation, overlap checks and source freshness remain enforced. |
| `test_nfl2k5_my_career_b69_wiring.py` and test additions | Executes assertions against the actual integrated protected files. The original generated J3 patch passed its proposed-panel test before application. Adds compact real-writer builds, option roundtrip/UI synchronization, replay/refusal/atomicity, and the existing release non-POSIX shim applied to the Experimental XBE BuildPlan fixture. |
| Renamed handoff documents / `tools/mycareer_mode/b69_registry_rows.json` | Retargets root report/wiring links after merging. Historical job status statements describe their original handoff; this report records completed integration. |

The new registry IDs are `nfl2k5.mode.my_career_playcalling`, `nfl2k5.mode.my_career_prospects`, `nfl2k5.weather.climate_editor`, `nfl2k5.weather.haze_coefficient`, `nfl2k5.gameplay.coin_defer`, `nfl2k5.gameplay.decided_clock`, and `nfl2k5.gameplay.cpu_scrambles`. The exact ID set is asserted by the catalog test.

## Counts and allocation

| Pinned quantity / site | Before A2b | After A2b |
| --- | ---: | ---: |
| Shared registry, both 2K5 runtime sites | 165 | 172 |
| Shared registry, Phase1 test | 165 | 172 |
| Shared registry, APF runtime | 165 | 172 |
| Shared registry, APF installer test | 165 | 172 |
| 2K5 product catalog / runtime | 92 | 99 |
| Catalog total tuple (total, editable, preview, export-only, coming-soon, evidence, research) | (92,72,8,1,0,8,3) | (99,77,8,1,0,10,3) |
| Stadium section tuple | (10,6,1,0,0,3,0) | (12,8,1,0,0,3,0) |
| Menus/UI section tuple | (6,3,2,0,0,1,0) | (8,3,2,0,0,3,0) |
| Gameplay section tuple | (32,24,5,0,0,0,3) | (35,27,5,0,0,0,3) |
| Unified provider dependency closure | 272 | 280 |
| Release allowlist files | 824 | 840 |
| Runtime product imports | 231 | 245 |
| Runtime tool imports | 35 | 35 |
| Additional B69 runtime pin entries | 0 | 11 |
| `space.plan(REQUESTS)` allocation records | 57 | 64 |
| `space.plan(REQUESTS)` file_size | 12300288 | 12300288 |

The allocator's own `space.plan(..., scaleout=True)` computes both layouts. Its scaleout ordering is `(owner == 'nfl2k5_roster_arena_growth', request)`, preserving the arena at the tail. [allocation-delta.json](reports/b69_a2b/allocation-delta.json) contains every before/after address and REQUESTS, rather than manually transplanting cave locations.

J5 adds **7 records: 896 RX + 4 RW + 140 RO bytes**. **27 existing allocations move** in the complete gate union; old sizes/alignments and scaleout extent remain unchanged. Different selected build unions may assign different addresses. J3 retains its existing runtime REQUESTS; J4 climate is data-only and haze modifies its pattern-checked retail `.data` coefficient at `0xA867F4` (four bytes), so both have empty REQUESTS. The final pairwise test covers the merged owners. All 14 changed/new native core job files remain byte-identical to their imported tips; [native-code-identity.json](reports/b69_a2b/native-code-identity.json) records each hash.


Exact REQUESTS `(owner, kind, size, alignment)`:

```json
{
  "nfl2k5_coin_defer": [
    [
      "nfl2k5_coin_defer",
      "code",
      384,
      16
    ],
    [
      "nfl2k5_coin_defer",
      "data",
      4,
      4
    ],
    [
      "nfl2k5_coin_defer",
      "read_only",
      128,
      4
    ]
  ],
  "nfl2k5_cpu_scrambles": [
    [
      "nfl2k5_cpu_scrambles",
      "code",
      128,
      16
    ],
    [
      "nfl2k5_cpu_scrambles",
      "read_only",
      4,
      4
    ]
  ],
  "nfl2k5_decided_clock": [
    [
      "nfl2k5_decided_clock",
      "code",
      384,
      16
    ],
    [
      "nfl2k5_decided_clock",
      "read_only",
      8,
      4
    ]
  ],
  "nfl2k5_my_career": [
    [
      "nfl2k5_my_career",
      "code",
      20480,
      16
    ],
    [
      "nfl2k5_my_career",
      "data",
      4096,
      16
    ],
    [
      "nfl2k5_my_career_m3",
      "data",
      4096,
      16
    ]
  ],
  "nfl2k5_weather_haze": []
}
```

## Every SHA256 pin changed

`new` means absent on A2. This includes the two new weather input-contract hashes as well as all source-closure pins. Machine-readable values are in [pin-delta.json](reports/b69_a2b/pin-delta.json).

| Pin file / key | Before | After |
| --- | --- | --- |
| `mod_editor/core/nfl2k5_weather.py` / `SHAPE_SHA256` | `new` | `ab4df547810a558fd3563b6bf4187b88a03b02111437b35a1f37e726a68cf85f` |
| `mod_editor/core/nfl2k5_weather_haze.py` / `TABLE_SHA256` | `new` | `311636b9459867b8fb1fb57be66e6bee17660119754995f678f8f9e1f6642520` |
| `mod_editor/core/providers.py` / `mod_editor/core/mod_build.py` | `d9a8f64d252044acd777456d5747a74e6b8d35ffc30ca80affee771f86150102` | `6955b82aa7f95fda834a8673efa3f31a0961473c9635f9ed308e3dc464fd60c0` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_build_settings.py` | `aa50ce8b583ad074f689033cfc4b7b68e5a68455f805950289bd110de484abcc` | `f6f81f7146e65cfb409025b0162d7b21ad52add1434d279c8bb85ced16aa78c9` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_coin_defer.py` | `new` | `403dddd1c40718d1284f008ac52222a0e2cbf0b9109941d8f16949739f6be5e0` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_coin_defer_code.py` | `new` | `9eefd8074b0fec01375cd266339ca0810e660af91dffbe275acaf0e5b927b0a2` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_cpu_scrambles.py` | `new` | `6a5b913f4c6407b64548e979ff59e1f66b2688f9ddccc20c4ed887e3209d5576` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_cpu_scrambles_code.py` | `new` | `6519b049d4f570dc92c58ede831a521ebface07ce23fb8406eb42318bbf52a92` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_decided_clock.py` | `new` | `cf27be38419bf9443c50fbed9de5c5deb08c620613af84869e60683f1b135a5b` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_decided_clock_code.py` | `new` | `83d7961b291a0fe08d3ac1518ec7b97ab4489f830c20c04bdd99626344d53c58` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_my_career.py` | `f625215f21b280e68ecc3e5e9c6dbb53470389b00639e6bec601a46d304102a9` | `c6d6f9d958f4287532f041b3e71ddbb573d823b281e037ea2a57e0d5b1ce7696` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_my_career_mode.py` | `522edea4626b6e58d9c28ddabfdad52c33dc148341a4c992d17f8c1336a539b0` | `5f4c8d0aa77e39077b9f6e8438f412bf82e3ed7f80973ce102c700e6d838de6d` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_my_career_mode_code.py` | `7746fa17bf59be6eafef5605cddf9c5ce4ab0e6199d0421644ab598a0a7ebc74` | `5f1873564b2dae91d66075b2d085dbb2bb38d142618bb25dc8bcdc6abb9645d3` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_my_career_prospects.py` | `new` | `6edcb1b6bc07bfb68c1317df5c8949596ae6d4ebcfb2fd13cace66b7539ae00a` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_my_career_save.py` | `f229b968fc4bea9d9cf1e5c858684056b66deeccb3f3944450fad836f053b812` | `c9c833f499212722b260eaa465d8e0445c53281fc832a03c21814bd1b94886ea` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_rules_patch.py` | `new` | `fa055e93835ad7c49196d361c7e0c9cfdec6fb620067ab7a0524e8a3cddcd15a` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_throw_tuning.py` | `ffdc3859c0b9892ade179679d9b943a46d86b1bf284cfebbeedf54b05b2153cd` | `4f951f25922bb9e61349d29ebaffa7009d7fadbdfe0b98b44aa0b8fef0b0d121` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/core/nfl2k5_weather.py` | `new` | `89526a7912340968cbe554aedf434d5a2c60a112f21a3d2d0564082b74ecd1ad` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/core/nfl2k5_weather_haze.py` | `new` | `3d045e099f1585658b899ab6e7d3560e92edb24529ca8d6f224e901dc7712ff9` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/beta62_options.py` | `new` | `d861f5656f98b0ee67cf4fe86a98bb95e5a79882e1a1066641f6b979ca835f84` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/build_panel_qt.py` | `new` | `234030c6a8034cd2a02329c948e3b069073bc3f1f7b8e04c371fb73c9377f4f5` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/gameplay_patches_panel_qt.py` | `new` | `2a7a24f9ec4ae2dcb1632d492ac42e7726548932e1eab409fc48c58cd45b8953` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/gameplay_project_ui.py` | `new` | `7222713aaaa0efbcc8851eb4ad3efa4ef31e8ad5352919e95b1ff9b39634c905` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/my_career_panel_qt.py` | `new` | `8a27ccdc2a649d122d6c21f9a646e47539b55c00653afc789e9b018fb581c823` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/studio_qt.py` | `919f494c9be1fa8e0cefa1f552b4950b1bb3d5a34d03f3a156ee6d316afe0393` | `aa57c10348b6f148b03f21279f15366ab40c4221860f55d99d90a33d428c8862` |
| `packaging/check_2k5_mod_studio_runtime.py` / `tools/nfl2k5_modern_rules.py` | `new` | `59f798d8d7996c206461de914234f1f0b987881366ba2055a18beba3d31178f9` |
| `packaging/check_2k5_mod_studio_runtime.py` / `tools/nfl2k5_weather_editor.py` | `new` | `65b45c3b25d47dc9cc672bd46a4719264ce4033aeca76632aaf44e9023b6cbfd` |
| `packaging/check_2k5_mod_studio_runtime.py` / `tools/nfl2k5_weather_native_probe.py` | `new` | `cd2776060c41a0831b1a15342a4486e739bbda5c633af5f4427217333885fde2` |
| `packaging/check_2k5_mod_studio_runtime.py` / `tools/nfl2k5_weather_time_of_day.py` | `new` | `37b2bd10f686db9fa99ba9034f9a7f68daa00bff516250ac0f67678880b98b47` |

## Every suite: final output

75 standalone suite files, 1438 unittest cases reported; 73 suite files pass and the two stated baseline suites remain red. The final line column preserves stdout emitted after unittest where applicable.

| Standalone test module (`tests/mod_editor/`) | Summary | Actual final line | Full log |
| --- | --- | --- | --- |
| `test_2k5_build_is_explainable.py` | Ran 16 tests in 0.027s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_2k5_build_is_explainable.log) |
| `test_apf_studio_installer.py` | Ran 16 tests in 16.237s; **FAILED (failures=2)** | `FAILED (failures=2)` | [log](reports/b69_a2b/final-wiring/test_apf_studio_installer.log) |
| `test_b69_a2b_game_wiring.py` | Ran 8 tests in 128.140s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_b69_a2b_game_wiring.log) |
| `test_beta66_d1_panels.py` | Ran 4 tests in 2.318s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_beta66_d1_panels.log) |
| `test_beta66_supersim_wiring.py` | Ran 3 tests in 0.297s; **OK** | `OK` | [log](reports/b69_a2b/native/test_beta66_supersim_wiring.log) |
| `test_build_panel_qt.py` | Ran 13 tests in 2.375s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_build_panel_qt.log) |
| `test_capability_registry_module_commands.py` | Ran 3 tests in 0.001s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_capability_registry_module_commands.log) |
| `test_discord_bugs_1_wiring.py` | Ran 10 tests in 4.041s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_discord_bugs_1_wiring.log) |
| `test_discord_bugs_2_wiring.py` | Ran 6 tests in 1.263s; **OK (skipped=2)** | `OK (skipped=2)` | [log](reports/b69_a2b/final-wiring/test_discord_bugs_2_wiring.log) |
| `test_gameplay_patches_panel_qt.py` | Ran 1 test in 0.626s; **OK** | `OK` | [log](reports/b69_a2b/final-gameplay-panel/test_gameplay_patches_panel_qt.log) |
| `test_mod_build.py` | Ran 11 tests in 2.543s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_mod_build.log) |
| `test_mod_build_beta62_integration.py` | Ran 8 tests in 248.233s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_mod_build_beta62_integration.log) |
| `test_mod_build_beta62_integration3.py` | Ran 11 tests in 208.892s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_mod_build_beta62_integration3.log) |
| `test_nfl2k5_accelerated_clock.py` | Ran 40 tests in 63.424s; **OK** | `OK` | [log](reports/b69_a2b/final-dispatcher/test_nfl2k5_accelerated_clock.log) |
| `test_nfl2k5_accelerated_clock_manifest.py` | Ran 5 tests in 10.431s; **OK** | `OK` | [log](reports/b69_a2b/final-gates/test_nfl2k5_accelerated_clock_manifest.log) |
| `test_nfl2k5_b661_transition.py` | Ran 11 tests in 479.091s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_b661_transition.log) |
| `test_nfl2k5_b68_game_composition.py` | Ran 3 tests in 429.820s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_b68_game_composition.log) |
| `test_nfl2k5_b69_rules.py` | Ran 16 tests in 160.889s; **OK** | `OK` | [log](reports/b69_a2b/final-dispatcher/test_nfl2k5_b69_rules.log) |
| `test_nfl2k5_b69_rules_series.py` | Ran 1 test in 71.169s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_b69_rules_series.log) |
| `test_nfl2k5_build_service.py` | Ran 28 tests in 0.201s; **OK** | `OK` | [log](reports/b69_a2b/final-dispatcher/test_nfl2k5_build_service.log) |
| `test_nfl2k5_cave_oracle.py` | Ran 29 tests in 427.751s; **OK (skipped=1)** | `OK (skipped=1)` | [log](reports/b69_a2b/final-gates/test_nfl2k5_cave_oracle.log) |
| `test_nfl2k5_music_playlist_manifest.py` | Ran 2 tests in 3.853s; **OK** | `OK` | [log](reports/b69_a2b/final-gates/test_nfl2k5_music_playlist_manifest.log) |
| `test_nfl2k5_my_career.py` | Ran 13 tests in 20.906s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career.log) |
| `test_nfl2k5_my_career_b69_wiring.py` | Ran 3 tests in 0.497s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_nfl2k5_my_career_b69_wiring.log) |
| `test_nfl2k5_my_career_completion.py` | Ran 6 tests in 31.923s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_completion.log) |
| `test_nfl2k5_my_career_control.py` | Ran 2 tests in 15.131s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_control.log) |
| `test_nfl2k5_my_career_cpu_choice.py` | Ran 1 test in 18.704s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_cpu_choice.log) |
| `test_nfl2k5_my_career_cpu_frame.py` | Ran 1 test in 55.243s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_cpu_frame.log) |
| `test_nfl2k5_my_career_cpu_injury.py` | Ran 1 test in 24.410s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_cpu_injury.log) |
| `test_nfl2k5_my_career_cpu_period.py` | Ran 2 tests in 37.528s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_cpu_period.log) |
| `test_nfl2k5_my_career_cpu_timeout.py` | Ran 1 test in 19.113s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_cpu_timeout.log) |
| `test_nfl2k5_my_career_cpu_turnover.py` | Ran 3 tests in 72.893s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_cpu_turnover.log) |
| `test_nfl2k5_my_career_creation_boundary.py` | Ran 4 tests in 2.249s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_creation_boundary.log) |
| `test_nfl2k5_my_career_draft.py` | Ran 6 tests in 1155.420s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_draft.log) |
| `test_nfl2k5_my_career_frontend.py` | Ran 7 tests in 57.212s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_frontend.log) |
| `test_nfl2k5_my_career_generic_build.py` | Ran 5 tests in 10.775s; **OK (skipped=1)** | `OK (skipped=1)` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_generic_build.log) |
| `test_nfl2k5_my_career_inline.py` | Ran 8 tests in 16.739s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_inline.log) |
| `test_nfl2k5_my_career_m3_budget.py` | Ran 5 tests in 4.488s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_m3_budget.log) |
| `test_nfl2k5_my_career_m3_menus.py` | Ran 4 tests in 50.355s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_m3_menus.log) |
| `test_nfl2k5_my_career_manifest.py` | Ran 3 tests in 8.049s; **OK** | `OK` | [log](reports/b69_a2b/final-gates/test_nfl2k5_my_career_manifest.log) |
| `test_nfl2k5_my_career_mode4.py` | Ran 8 tests in 471.117s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_mode4.log) |
| `test_nfl2k5_my_career_mode5.py` | Ran 4 tests in 322.485s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_mode5.log) |
| `test_nfl2k5_my_career_mode_audit.py` | Ran 6 tests in 0.074s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_mode_audit.log) |
| `test_nfl2k5_my_career_mode_routes.py` | Ran 7 tests in 3.016s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_mode_routes.log) |
| `test_nfl2k5_my_career_panel.py` | Ran 4 tests in 0.287s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_nfl2k5_my_career_panel.log) |
| `test_nfl2k5_my_career_playcalling.py` | Ran 3 tests in 795.439s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_playcalling.log) |
| `test_nfl2k5_my_career_played.py` | Ran 4 tests in 72.332s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_played.log) |
| `test_nfl2k5_my_career_position_inputs.py` | Ran 9 tests in 25.379s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_position_inputs.log) |
| `test_nfl2k5_my_career_prospects.py` | Ran 5 tests in 280.886s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_prospects.log) |
| `test_nfl2k5_my_career_season.py` | Ran 1 test in 159.545s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_season.log) |
| `test_nfl2k5_my_career_settings.py` | Ran 10 tests in 32.136s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_settings.log) |
| `test_nfl2k5_my_career_signing.py` | Ran 6 tests in 54.775s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_signing.log) |
| `test_nfl2k5_my_career_unicorn.py` | Ran 18 tests in 13.613s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_unicorn.log) |
| `test_nfl2k5_my_career_upgrades.py` | Ran 4 tests in 271.899s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_upgrades.log) |
| `test_nfl2k5_my_career_week.py` | Ran 1 test in 363.033s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_my_career_week.log) |
| `test_nfl2k5_owner_pairwise_composition.py` | Ran 506 tests in 2855.742s; **OK** | `OK` | [log](reports/b69_a2b/final-gates/test_nfl2k5_owner_pairwise_composition.log) |
| `test_nfl2k5_playbook_pair_manifest.py` | Ran 1 test in 403.445s; **OK** | `Observed 137 XBE transactions and 12548 reservations; no disc built` | [log](reports/b69_a2b/manifest-final.log) |
| `test_nfl2k5_practice_reserves.py` | Ran 9 tests in 22.344s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_practice_reserves.log) |
| `test_nfl2k5_roster_arena_growth.py` | Ran 13 tests in 33.455s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_roster_arena_growth.log) |
| `test_nfl2k5_simulated_windows_build.py` | Ran 1 test in 269.393s; **OK** | `Experimental XBE passes: POSIX/non-POSIX identical; J3/J4/J5 verified; no full disc built` | [log](reports/b69_a2b/final-simwin/test_nfl2k5_simulated_windows_build.log) |
| `test_nfl2k5_supersim.py` | Ran 12 tests in 8.253s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_supersim.log) |
| `test_nfl2k5_supersim_live.py` | Ran 34 tests in 2275.712s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_supersim_live.log) |
| `test_nfl2k5_throw_tuning.py` | Ran 45 tests in 19.808s; **OK (skipped=1)** | `OK (skipped=1)` | [log](reports/b69_a2b/final-dispatcher/test_nfl2k5_throw_tuning.log) |
| `test_nfl2k5_weather.py` | Ran 11 tests in 0.195s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_weather.log) |
| `test_nfl2k5_weather_editor.py` | Ran 2 tests in 0.059s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_weather_editor.log) |
| `test_nfl2k5_weather_native.py` | Ran 10 tests in 20.079s; **OK** | `OK` | [log](reports/b69_a2b/native/test_nfl2k5_weather_native.log) |
| `test_phase1_packaging.py` | Ran 23 tests in 3.047s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_phase1_packaging.log) |
| `test_product_catalog.py` | Ran 9 tests in 0.068s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_product_catalog.log) |
| `test_provider_integrity.py` | Ran 7 tests in 13.496s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_provider_integrity.log) |
| `test_providers.py` | Ran 33 tests in 5.136s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_providers.log) |
| `test_shipped_tools_posix_only.py` | Ran 13 tests in 26.736s; **OK** | `OK` | [log](reports/b69_a2b/final-wiring/test_shipped_tools_posix_only.log) |
| `test_throw_tuning_panel_qt.py` | Ran 13 tests in 2.580s; **OK** | `OK` | [log](reports/b69_a2b/final-dispatcher/test_throw_tuning_panel_qt.log) |
| `test_validate_all_capabilities.py` | Ran 36 tests in 0.830s; **FAILED (errors=1, skipped=1)** | `FAILED (errors=1, skipped=1)` | [log](reports/b69_a2b/final-wiring/test_validate_all_capabilities.log) |
| `test_xbe_patch_cave_references.py` | Ran 131 tests in 1881.591s; **OK** | `OK` | [log](reports/b69_a2b/final-gates/test_xbe_patch_cave_references.log) |
| `test_xbe_patch_memory_writes.py` | Ran 119 tests in 1668.003s; **OK** | `OK` | [log](reports/b69_a2b/final-gates/test_xbe_patch_memory_writes.log) |

## Verification method and limits

All suites are separate `python3 tests/mod_editor/<file>.py` processes with:

```bash
export PYTHONPATH=.
export QT_QPA_PLATFORM=offscreen
export MOD_STUDIO_NO_UPDATE_CHECK=1
export PYTHONHASHSEED=0
export NFL2K5_CAVE_MANIFEST="$PWD/.scratch/a2b/gate-manifest.json"
```

The test runner and complete logs are in [reports/b69_a2b](reports/b69_a2b). [final-tests.json](reports/b69_a2b/final-tests.json) records each final command, exit code, log SHA256, final output and source-fingerprint digest. [job-test-inventory.json](reports/b69_a2b/job-test-inventory.json) is computed from all three job histories; every listed suite is covered. Each MyCareer/Supersim/weather/rules suite was run on the merged native writers. The final dispatcher, wiring, manifest and four-gate runs use the final production source; the native job bytes were unchanged during the later dispatcher replay correction. [final-audit.json](reports/b69_a2b/final-audit.json) checks final source fingerprints, identifies the two dispatcher follow-up files, and compares all 840 staged source files byte-for-byte with the delivery tree. Initial attempts are retained in their named log groups, including the two stale-manifest failures during integration; they are superseded by the final manifest/gate run. One exploratory command named a nonexistent `test_mod_build_beta62_integration2.py`; this was a command typo, not a test red.

The observed scratch manifest was regenerated from current writer calls, not by replacing hashes on historical byte evidence:

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0 \
NFL2K5_CAVE_MANIFEST="$PWD/.scratch/a2b/gate-manifest.json" \
NFL2K5_PLAYBOOK_PAIR_MANIFEST="$PWD/.scratch/a2b/gate-manifest.json" \
python3 tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py
```

For first creation, create `.scratch/a2b` and omit `NFL2K5_CAVE_MANIFEST` until its file exists; keep `NFL2K5_PLAYBOOK_PAIR_MANIFEST` set to write it. The final generation was `Ran 1 test in 403.445s`, `OK`, then `Observed 137 XBE transactions and 12548 reservations; no disc built`. [gate-manifest-summary.json](reports/b69_a2b/gate-manifest-summary.json) records its SHA256, 331 exact source hashes, layout, scope and observation counts. The local projection remains `.scratch/a2b/gate-manifest.json`, outside the release and bundle.

The cave oracle's existing scratch-manifest guard skips the single resource-build evidence assertion because this projection is XBE-only. It still runs the ownership and retail-reference assertions; no fabricated archive evidence was added. Other existing optional skips are reported in the test table. No full retail disc was copied, emulator launched, on-screen GUI used, audio played or network accessed. This machine began below the context's 80 GB free-space floor, so only bounded temporary XBE/compact synthetic archive work was performed; compact fixtures were deleted by their TemporaryDirectory contexts.

`test_b69_a2b_game_wiring.py` builds through real `mod_build.build` and real parsers/writers into a bounded synthetic archive with the private pinned XBE. The sole schema seam declares the synthetic ROST shape; one project-builder seam relocates that resource so climate must find its final extent. It tests each new option alone, Off byte identity, shared UI settings and saved-plan identity, all new options plus MyCareer/depth locks/accelerated clock, identical replay, changed/disabled installed-setting refusals before project work, stale/unsupported climate refusal, haze-Off restoration, and atomic output preservation after simulated final-pass I/O failure.

The named simulated-Windows build suite was absent on the base. Existing release fixtures `tests/nfl2k5_b661_transition.py` (`plan_for('everything')`) and `test_shipped_tools_posix_only.simulated_non_posix` were present, so the new suite combines them. It derives actual production BuildPlan XBE arguments, compiles PLAY intents from the private disc read-only, enables all available compatible executable writers including J3/J4/J5 and relocated kickoff, and compares POSIX/non-POSIX bytes and receipts. [simulated-windows-build.json](reports/b69_a2b/simulated-windows-build.json) records every setting, allocation and exclusion. Unavailable franchise-2026/Senior Bowl, alternate flight/kicking/momentum implementations, external resource imports and full-disc transport are outside that executable fixture. v17 climate cannot share the reserves16/created-team v18 plan; the compact-disc suite proves all new features together with the compatible v17 plan. This is a bounded executable/build-publication proof, not a full retail-disc or gameplay witness.

Runtime assembly checks also passed:

```text
python3 tools/mycareer_mode/build_runtime.py --check
MyCareer mode runtime verified
python3 tools/nfl2k5_my_career_assemble.py --check
MyCareer template verified
python3 tools/nfl2k5_rules_assemble.py --check
nfl2k5_decided_clock template verified
nfl2k5_coin_defer template verified
nfl2k5_cpu_scrambles template verified
```

Clean staging used `python3 packaging/stage_release.py packaging/release-allowlist.txt /tmp/astra-a2b-release-final`. It reported `staged 840 files; 0 declared inputs absent`. The staged runtime reported `2K5_MOD_STUDIO_RUNTIME_CLOSURE_PASS product_modules=245 tool_modules=35 registry=172 sections=12 nfl2k5_capabilities=99` (full final line in `runtime-final.log`). `python3 packaging/check_2k5_mod_studio_release.py /tmp/astra-a2b-release-final` reported `2K5_MOD_STUDIO_RELEASE_PASS files=840 directories=37 bytes=138930745 metadata=24 private_inventory=false retail=false symlinks=false undeclared=false`.

The checkout initially lacked ignored, pre-existing release inputs. [hydration.json](reports/b69_a2b/hydration.json) records exact path, source, SHA256 and bytes for the 16 reviewed metadata files and four extractor/vendor files restored from the A2 handoff's local sources. These were verified against their recorded hashes before copying; they contain no retail game payload and are excluded from the bundle. The first workspace runtime check refused the development `extracted` symlink as designed; the clean allowlist stage passes.

## Reds and integration corrections

Two final failing suites match the user's stated machine baseline:

- `test_apf_studio_installer.py`: 16 tests, two failures. Both installed/clean-stage runtime checks end at `ModuleNotFoundError: No module named 'capstone'` / `APF2K8_MOD_STUDIO_RUNTIME_REFUSED: No module named 'capstone'`.
- `test_validate_all_capabilities.py`: 36 tests, one error and one existing skip. `ValidationRunError: unreviewed validation module arguments` comes from older rows `apf2k8.field_art.material_opacity` and `nfl2k5.espn25.scenarios_rosters`. The seven added rows use module-only commands; `test_capability_registry_module_commands.py` passes. Existing commands were not changed to conceal the baseline.

Integration-only reds were fixed: catalog exact ID set/counts; actual J3 four-alias panel label; missing historical packaging inputs; recorder helper double-attribution; and the private deferred image replay guards. The replay failure first surfaced on accelerated clock: a deliberately disabled intermediate selection was mistaken for removal, followed by an unchanged-first-pass refusal. Complete source-plan validation now precedes intermediate passes, and the final pass retains strict installed-setting verification. Tests prove identical replay plus genuine off/configuration-change refusals before copying. No native job-code red was hidden or patched over.

## Claude's required final release step

From a writable checkout of `local/stack-beta-69` still at the A2 head, import the verified bundle, preserving its ancestry:

```bash
git bundle verify /home/noah/2k-worktrees/astra-b69-a2b/ASTRA_A2B.bundle
git fetch /home/noah/2k-worktrees/astra-b69-a2b/ASTRA_A2B.bundle \
  astra/b69-a2b-integrate-game
git merge --ff-only FETCH_HEAD
```

After all final pinned edits, regenerate the **production** manifest on storage with room for its disposable disc. This is Claude's final release commit, not a step performed by A2b:

```bash
unset NFL2K5_CAVE_MANIFEST NFL2K5_PLAYBOOK_PAIR_MANIFEST
mkdir -p '/media/noah/Storage/.b69-a2b-manifest'
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0 \
python3 tools/nfl2k5_cave_oracle.py manifest \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir '/media/noah/Storage/.b69-a2b-manifest' \
  --json data/nfl2k5_cave_reservations.json
python3 packaging/repin.py --apply
```

Then rerun the four gates against that production manifest (without the scratch override), run the release's full resource/disc build checks, and commit the manifest/pins as the last release commit. No allocation address from the test union should be copied manually into a selected build.

## Player witnesses still required

Use the original J3/J4/J5 reports and research witness cases. Verify saved caller choices after load and on the first play after Supersim hands control back; tiered initial rating/rank/side, progression and prototype naming; dry-weather haze and climate values with the existing scheduled time of day; CPU-only defer behavior across halftime/overtime; user-selected decided-clock cutoffs and edge cases; and CPU scramble behavior across real games. Native instruction execution and offscreen controls are PROVED within their declared seams. Rendered gameplay, frame cadence, audible behavior, physical results and a full game are UNWITNESSED.

## Delivery

`ASTRA_A2B.bundle` contains the requested branch and complete integration ancestry, with the A2 stack head as prerequisite. Its final tip, SHA256 and independent fetch/tree verification are recorded in `reports/b69_a2b/bundle-verification.json` and `ASTRA_DONE` after bundle creation. The marker is written last. The bundle and marker are deliverables outside the self-contained commit history.
