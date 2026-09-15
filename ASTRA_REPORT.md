# Beta 70 A3: T2 wiring handoff

## Delivery and gate status

Implemented every item in `WIRING_B70_T2.md` on input stack **ded9c222a7df40c2e2d9b69c37c6464f72fc8fb4**, branch **astra/b70-a3-t2-wiring**. Production/test commit: **cbcccaee**. The following report commit includes this report, the final message and retained command logs. No push.

**25 distinct standalone suites ran: 22 exit zero, 3 nonzero, 267 test cases, no skips.** All five T2 suites, the new six-case A3 live integration suite, landed A2 wiring, facade/session/build-service, equipment import/consumer suites, provider/integrity suites and registry count consumers pass. Three suites remain nonzero as detailed below. The strict registry validator also remains nonzero because baseline evidence is absent. This is **not a green strict or hydrated release gate**.

The exact requested strict command was run, including after repinning. It did **not** print the required PASS banner. The supplemental structural validation prints `MOD_CAPABILITY_REGISTRY_VALIDATION_PASS schema=vc_mod_capability_registry/v1 games=3 surfaces=21 capabilities=174` with `--skip-file-checks`; that is recorded separately and is not substituted for strict success.

Private Git metadata: `.scratch/git-a3`, with the shared object store as a read-only alternate. The normal worktree branch remains at the input head; the new commits belong to the private Git branch. Portable delivery: **`.scratch/astra-b70-a3.bundle`**, incremental from `ded9c222`, containing `astra/b70-a3-t2-wiring`. Final bundle creation, verification, local fetch/readback, exact head/tree identity, byte size/hash and command timings are recorded in [.scratch/astra-b70-a3-delivery.json](.scratch/astra-b70-a3-delivery.json). That post-commit sidecar avoids a self-referential bundle hash in a bundled report. Scratch contains no retail payload and remains below 200 MB.

```sh
git bundle verify .scratch/astra-b70-a3.bundle
git fetch .scratch/astra-b70-a3.bundle astra/b70-a3-t2-wiring
```

Use those commands in Claude's writable integration checkout. The bundle prerequisite is the stated input stack. Claude owns the cave-manifest regeneration and hydrated gates. This job adds no XBE writes, cave reservations, runtime allocations, presets or capability rows.

## Wiring locations

The exact registry reconstruction and preservation checks are reproducible with `python3 reports/b70_a3/audit_wiring.py`; output is [wiring-audit.log](reports/b70_a3/wiring-audit.log). All existing capability count pins remain unchanged, and the registry remains at **174** rows.

| Wiring item | Final location |
| --- | --- |
| Load: assign the existing preflight rows | [mod_editor/studio/session.py:4183](mod_editor/studio/session.py#L4183) |
| Load: remember rows after commit; retain cleanup finally | [mod_editor/studio/session.py:4544](mod_editor/studio/session.py#L4544) |
| Build list: exact T2 method, cached captions, stale-fit fallback | [mod_editor/gui/studio_qt.py:8648](mod_editor/gui/studio_qt.py#L8648) |
| BuildResult.texture_summary default | [mod_editor/core/nfl2k5_build_service.py:112](mod_editor/core/nfl2k5_build_service.py#L112) |
| BuildResult.message: T2 summary with T1 digit grouping | [mod_editor/core/nfl2k5_build_service.py:115](mod_editor/core/nfl2k5_build_service.py#L115) |
| Verified result: read and hash-check texture receipts before cleanup | [mod_editor/core/nfl2k5_build_service.py:1672](mod_editor/core/nfl2k5_build_service.py#L1672) |
| Verified result: pass texture_summary to BuildResult | [mod_editor/core/nfl2k5_build_service.py:1681](mod_editor/core/nfl2k5_build_service.py#L1681) |
| Published result: retain texture_summary before COMPLETE | [mod_editor/core/nfl2k5_build_service.py:1456](mod_editor/core/nfl2k5_build_service.py#L1456) |
| Arm import help before slot fitting | [mod_editor/gui/studio_qt.py:5595](mod_editor/gui/studio_qt.py#L5595) |
| Legacy staging lazy forward | [mod_editor/core/nfl2k5_equipment_import.py:118](mod_editor/core/nfl2k5_equipment_import.py#L118) |
| Legacy revert lazy forward | [mod_editor/core/nfl2k5_equipment_import.py:123](mod_editor/core/nfl2k5_equipment_import.py#L123) |
| Release allowlist: staging | [packaging/release-allowlist.txt:156](packaging/release-allowlist.txt#L156) |
| Release allowlist: reporting | [packaging/release-allowlist.txt:157](packaging/release-allowlist.txt#L157) |
| Staging seam: shared T1 import/open memory and disk cache | [mod_editor/core/equipment_staging.py:38](mod_editor/core/equipment_staging.py#L38) |
| Provider closure seam: reporting pin | [mod_editor/core/providers.py:528](mod_editor/core/providers.py#L528) |
| Provider closure seam: staging pin | [mod_editor/core/providers.py:529](mod_editor/core/providers.py#L529) |
| Provider closure seam: compatibility import pin | [mod_editor/core/providers.py:590](mod_editor/core/providers.py#L590) |
| Provider exact closure expectation (not a capability count) | [tests/mod_editor/test_provider_integrity.py:204](tests/mod_editor/test_provider_integrity.py#L204) |
| T2 snippet test uses its retained named brief | [tests/mod_editor/test_b70_t2_wiring.py:20](tests/mod_editor/test_b70_t2_wiring.py#L20) |
| T1 synthetic fixture consumes T2 aggregate receipt via checked physical span | [tests/mod_editor/b70_equipment_fixture.py:99](tests/mod_editor/b70_equipment_fixture.py#L99) |
| Preserved T1 shared kept-retail grouping | [mod_editor/core/nfl2k5_build_service.py:125](mod_editor/core/nfl2k5_build_service.py#L125) |
| Preserved T1 Build completion consumer | [mod_editor/core/build_feedback.py:51](mod_editor/core/build_feedback.py#L51) |
| Preserved T1 shell completion consumer | [mod_editor/gui/studio_qt.py:7987](mod_editor/gui/studio_qt.py#L7987) |
| Preserved T1 offset-tier caching/search bounds | [mod_editor/core/nfl2k5_uniform_equipment_writer.py:612](mod_editor/core/nfl2k5_uniform_equipment_writer.py#L612) |
| Preserved T1/T2 union of palette and stripe floors | [mod_editor/core/nfl2k5_uniform_equipment_writer.py:1018](mod_editor/core/nfl2k5_uniform_equipment_writer.py#L1018) |
| Live session/GUI/summary coverage | [tests/mod_editor/test_b70_a3_integration.py:54](tests/mod_editor/test_b70_a3_integration.py#L54) |
| Live verified publication and tamper refusal coverage | [tests/mod_editor/test_b70_a3_integration.py:142](tests/mod_editor/test_b70_a3_integration.py#L142) |
| nfl2k5.textures.all_p8: existing row | [mod_editor/capabilities/registry.v1.json:11462](mod_editor/capabilities/registry.v1.json#L11462) |
| nfl2k5.textures.all_p8: appended evidence | [mod_editor/capabilities/registry.v1.json:11448](mod_editor/capabilities/registry.v1.json#L11448) |
| nfl2k5.textures.all_p8: replace only stale equipment sentence | [mod_editor/capabilities/registry.v1.json:11468](mod_editor/capabilities/registry.v1.json#L11468) |
| nfl2k5.textures.all_p8: exact normal/mud constraint | [mod_editor/capabilities/registry.v1.json:11472](mod_editor/capabilities/registry.v1.json#L11472) |
| nfl2k5.textures.all_p8: append witness update to runtime.scope | [mod_editor/capabilities/registry.v1.json:11494](mod_editor/capabilities/registry.v1.json#L11494) |
| nfl2k5.uniforms.all_visual: existing row | [mod_editor/capabilities/registry.v1.json:11671](mod_editor/capabilities/registry.v1.json#L11671) |
| nfl2k5.uniforms.all_visual: appended evidence | [mod_editor/capabilities/registry.v1.json:11655](mod_editor/capabilities/registry.v1.json#L11655) |
| nfl2k5.uniforms.all_visual: replace only stale equipment sentence | [mod_editor/capabilities/registry.v1.json:11679](mod_editor/capabilities/registry.v1.json#L11679) |
| nfl2k5.uniforms.all_visual: exact normal/mud constraint | [mod_editor/capabilities/registry.v1.json:11685](mod_editor/capabilities/registry.v1.json#L11685) |
| nfl2k5.uniforms.all_visual: append witness update to runtime.scope | [mod_editor/capabilities/registry.v1.json:11709](mod_editor/capabilities/registry.v1.json#L11709) |
| nfl2k5.uniforms.all_visual: selected-occurrence constraint | [mod_editor/capabilities/registry.v1.json:11686](mod_editor/capabilities/registry.v1.json#L11686) |
| nfl2k5.uniforms.all_visual: replace obsolete 64x64 restriction | [mod_editor/capabilities/registry.v1.json:11678](mod_editor/capabilities/registry.v1.json#L11678) |
| nfl2k5.stadiums_fields.blender_textures: existing row | [mod_editor/capabilities/registry.v1.json:11376](mod_editor/capabilities/registry.v1.json#L11376) |
| nfl2k5.stadiums_fields.blender_textures: appended evidence | [mod_editor/capabilities/registry.v1.json:11366](mod_editor/capabilities/registry.v1.json#L11366) |
| nfl2k5.stadiums_fields.blender_textures: selected-occurrence constraint | [mod_editor/capabilities/registry.v1.json:11381](mod_editor/capabilities/registry.v1.json#L11381) |

## Integration seams fixed

1. **Stale handoff filename.** Both T2 wiring cases initially errored with `StopIteration` in `snippet`, because the shared `WIRING.md` contains T1. The test now reads `WIRING_B70_T2.md`. No assertion changed. The additional live tests exercise the actual shipped methods, preserving the original proposal checks.
2. **Lost import/open cache reuse.** T2's `_checked_rows` created a separate session cache, so the newly forwarded compatibility imports no longer populated T1's validated `_STAGED_CACHE`/disk cache. Reopening hit `_compile_group` and failed `AssertionError: open repeated fit search`; corrupt-cache testing also found no disk files. `_checked_rows` now uses `staged_equipment_cache()` for the same complete physical groups. T1's memory, disk, fresh-interpreter, changed-art, changed-descriptor and corrupt-cache checks pass. The selected normal/mud group still receives one combined check before mutation; captions consume returned rows without compiling. No search bound, offset-tier logic, stripe/palette floor, quantizer or writer byte changed.
3. **Provider import closure.** `test_all_external_writer_and_verifier_import_closures_are_exactly_pinned` exposed `AssertionError: 282 != 285`. The newly reachable `equipment_reporting.py`, `equipment_staging.py` and `nfl2k5_equipment_import.py` need explicit hashes; automatic repin cannot add missing entries. Added those three exact pins and changed only the exact provider-module count to 285, retaining complete closure-set and hash equality. This is a compiler module count, not a capability count. The suite passes. This necessary integration correction goes beyond the brief's expectation of automatic-only provider changes. Runtime-checker changes remain automatic SHA updates only.
4. **T1 fixture's receipt consumer.** Atomic T2 staging returns aggregate measured rows rather than the old single-span `replacement` object, causing six `KeyError: 'replacement'` errors in the timing fixture. The fixture now obtains the selected physical span through the same checked cache and retains every original byte assertion. It adds no fit ladder. Four old complete-span goldens still match; three genuinely different old expectations remain explicitly failing below.

An initial registry editing helper stopped on a formatting assertion before changing the JSON: the canonical registry uses escaped Unicode. The helper was corrected to preserve that exact format, and the registry-only step was rerun. No unrelated row was rewritten.

## Preservation and evidence boundary

**PROVED in this run:** the exact registry strings/evidence append operations and 174-row count; hash-pinned provider closure; byte equality of the entire landed equipment writer and LZ module to the input stack; bounded native dry/wet transport of runtime record `+0x18` bit 28; T2's selected stadium occurrence/native material and close/reopen checks. Synthetic tests verify atomic staging, real save/reopen fit-row retention, cache invalidation, arm import accept/cancel ordering, T1 warning grouping, verified texture summaries after staging cleanup, and refusal to publish after receipt tampering.

T1's `summarize_kept_retail`, `build_feedback.completion` and `_choose_build_output` are unchanged. The facade and visual-project owner are unchanged. The writer retains Claude's union of T1's palette lower bound and T2's stripe floor. Its input and output source hash is `8a0a583dd3ce9a3639e722942ae8be27f139b38162586fb8f901928f21114716`. All protected scorebug/scorebar/modern-color implementation, data, docs and tests remain untouched; the cave manifest is unchanged.

**HYPOTHESIS / UNWITNESSED:** every in-game outcome of this change, including sock clarity at distance, the lifecycle of the mud flag, arm-digit placement on models, and the played stadium's selected banner occurrence. Larger archive allocation is still UNPROVED and unavailable. No emulator, GUI display, network, disc build, retail-data copy or game-code write was used.

The landed beta-70 changelog/FAQ already carry T2's reporter context and were preserved. Coach Edwards reported “these sock textures are still distorted”; maumau78 reported visibility after assigning normal and mud while artwork still looked buggy. andrethealchemist reported “The old banners around the stadium are still in the game.” His played venue is unknown; Texture 29 does not establish Cincinnati. Noah/reporters must witness the changed artwork at near/distant views, both normal/mud states, the chosen venue/time/weather and the corresponding banner package. Texture import does not move the jersey model's sleeve/shoulder UV surface.

## Exact remaining failures

### Strict registry validator: baseline evidence unavailable

`python3 -m mod_editor.capabilities.validate_registry`, exit 1:

```text
RegistryError: capabilities[0].evidence[0]: missing local file docs/research/apf_audio.md
```

Root cause: `mod_editor/capabilities/validate_registry.py:129` requires the evidence path to be a real file. The audit finds **148 missing unique evidence paths**, exactly the same set in `ded9c222` and the wired registry. Every newly appended T2 evidence path exists. No placeholder, removed constraint or bypass was used to make the strict command pass. See [registry-after-repin.log](reports/b70_a3/registry-after-repin.log) and [wiring-audit.log](reports/b70_a3/wiring-audit.log) for the complete missing set. Claude's hydrated checkout must supply the original research/evidence and rerun strict validation.

### Studio shell: missing uniform inventory

`test_studio_shell_layout_qt.py`, exit 1, 18 cases / 18 setup errors:

```text
FileNotFoundError: [Errno 2] No such file or directory: '/home/noah/2k-worktrees/astra-b70-a3/reports/assets'
```

The failure is before an assertion: `StudioMainWindow.__init__` → `_build_colors_page` → `_filter_unif_color_sets` → `uniform_catalog` → `nfl2k5_uniform_catalog.py:570`, which resolves the missing private uniform inventory. The shell never reaches the changed import/build-list action. No production fallback or test skip was added. See [test_studio_shell_layout_qt.log](reports/b70_a3/test_studio_shell_layout_qt.log).

### Packaging: missing reviewed metadata

`test_phase1_packaging.py`, exit 1, 23 cases / 1 error, in `ModStudioPackagingTests.test_reviewed_metadata_files_match_exact_contract_and_have_no_payload` at line 374:

```text
FileNotFoundError: [Errno 2] No such file or directory: '/home/noah/2k-worktrees/astra-b70-a3/reports/assets/menu_state_trace.json'
```

The exact reviewed-metadata read fails before an assertion. The registry-count checks pass. See [test_phase1_packaging.log](reports/b70_a3/test_phase1_packaging.log).

### Additional T1 byte-golden regression: landed T2 encoding differs

`test_b70_t1_build_speed.py`, exit 1, 10 cases / 3 subtest failures, all in `SearchTests.test_beta69_complete_span_bytes_and_helper_disabled_import_budget`. These are the unchanged assertions; actual and expected values follow. The equipment writer is byte-identical to the input stack, and T2 intentionally changed the low-colour quantizer before A3. No old golden was regenerated or loosened.

```text
FAIL: test_beta69_complete_span_bytes_and_helper_disabled_import_budget (__main__.SearchTests.test_beta69_complete_span_bytes_and_helper_disabled_import_budget) (case='shoe32_noise_refused')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/noah/2k-worktrees/astra-b70-a3/tests/mod_editor/test_b70_t1_build_speed.py", line 56, in test_beta69_complete_span_bytes_and_helper_disabled_import_budget
    self.assertEqual(row['required'], 666)
AssertionError: 664 != 666
```

```text
FAIL: test_beta69_complete_span_bytes_and_helper_disabled_import_budget (__main__.SearchTests.test_beta69_complete_span_bytes_and_helper_disabled_import_budget) (case='shoe32_noise_half')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/noah/2k-worktrees/astra-b70-a3/tests/mod_editor/test_b70_t1_build_speed.py", line 53, in test_beta69_complete_span_bytes_and_helper_disabled_import_budget
    self.assertEqual(row['span_sha256'], BETA69_SPANS[case[0]])
AssertionError: 'd7929c8fed8c3863e91d5a6cde5c81c80fcd3bf72a7012e7f336e5896aa9814c' != '409e6651e5724eadfcfe36db593d9f0fded63ab3b14a8a76e04432bb313bb624'
- d7929c8fed8c3863e91d5a6cde5c81c80fcd3bf72a7012e7f336e5896aa9814c
+ 409e6651e5724eadfcfe36db593d9f0fded63ab3b14a8a76e04432bb313bb624
```

```text
FAIL: test_beta69_complete_span_bytes_and_helper_disabled_import_budget (__main__.SearchTests.test_beta69_complete_span_bytes_and_helper_disabled_import_budget) (case='shoe32_noise_quarter')
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/noah/2k-worktrees/astra-b70-a3/tests/mod_editor/test_b70_t1_build_speed.py", line 53, in test_beta69_complete_span_bytes_and_helper_disabled_import_budget
    self.assertEqual(row['span_sha256'], BETA69_SPANS[case[0]])
AssertionError: '80f42a2ea0df9452234af4080df2666f60ce7fad316bc50ee1f5d6cd3f672c19' != 'fed500b1e0aa7af58dfcd7e17a9bb4808a7d1b0509ce229c5ca87af3f2d9f97a'
- 80f42a2ea0df9452234af4080df2666f60ce7fad316bc50ee1f5d6cd3f672c19
+ fed500b1e0aa7af58dfcd7e17a9bb4808a7d1b0509ce229c5ca87af3f2d9f97a
```

All nine other top-level T1 cases pass, including search budgets/bounds, parse caching and restored-project invalidation. Four complete compressed-span hashes still equal beta-69: `sock256_stripes`, `shoe64_stripes`, `shoe64_diagonal`, `shoe32_tight`. The changed half/quarter noise images and refused-noise byte count require an explicit upstream decision about the historical byte contract. See [t1-build-speed-cache-fixed.log](reports/b70_a3/t1-build-speed-cache-fixed.log).

`test_b70_a2_integration.py` is absent. The landed `test_b70_a2_wiring.py` was run instead, with 4 cases passing. A3's separate live integration file has 6 passing cases.

## Final standalone results

Every suite is a separate Python process with the requested `QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools` environment, launched through `env`. These are final full-file executions; earlier failures remain in the command ledger and logs. [final-tests.json](reports/b70_a3/final-tests.json) is machine-readable.

| Exact command | Exit | Elapsed seconds | Cases | Output |
| --- | ---: | ---: | ---: | --- |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_wiring.py` | 0 | 1.027828 | 2 | [test_b70_t2_wiring.log](reports/b70_a3/test_b70_t2_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_reporting.py` | 0 | 0.247250 | 5 | [test_b70_t2_reporting.log](reports/b70_a3/test_b70_t2_reporting.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_equipment.py` | 0 | 1.194307 | 8 | [t2-equipment-cache-fixed.log](reports/b70_a3/t2-equipment-cache-fixed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_stadium.py` | 0 | 29.513545 | 3 | [test_b70_t2_stadium.log](reports/b70_a3/test_b70_t2_stadium.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_native.py` | 0 | 0.100780 | 1 | [test_b70_t2_native.log](reports/b70_a3/test_b70_t2_native.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_a2_wiring.py` | 0 | 2.306946 | 4 | [test_b70_a2_wiring.log](reports/b70_a3/test_b70_a2_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_studio_facade.py` | 0 | 0.368252 | 11 | [test_studio_facade.log](reports/b70_a3/test_studio_facade.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_studio_session.py` | 0 | 0.834327 | 18 | [test_studio_session.log](reports/b70_a3/test_studio_session.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_build_service.py` | 0 | 0.270314 | 28 | [test_nfl2k5_build_service.log](reports/b70_a3/test_nfl2k5_build_service.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_studio_shell_layout_qt.py` | 1 | 4.601301 | 18 | [test_studio_shell_layout_qt.log](reports/b70_a3/test_studio_shell_layout_qt.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_import.py` | 0 | 2.147515 | 13 | [equipment-import-final.log](reports/b70_a3/equipment-import-final.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_import_wiring.py` | 0 | 0.724850 | 6 | [test_nfl2k5_equipment_import_wiring.log](reports/b70_a3/test_nfl2k5_equipment_import_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py` | 0 | 25.990167 | 19 | [equipment-consumers-final.log](reports/b70_a3/equipment-consumers-final.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py` | 0 | 1.761725 | 3 | [test_nfl2k5_equipment_scope_wiring.log](reports/b70_a3/test_nfl2k5_equipment_scope_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_providers.py` | 0 | 3.542769 | 33 | [providers-final.log](reports/b70_a3/providers-final.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_provider_integrity.py` | 0 | 8.060924 | 7 | [provider-integrity-fixed.log](reports/b70_a3/provider-integrity-fixed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_product_catalog.py` | 0 | 0.155282 | 9 | [test_product_catalog.log](reports/b70_a3/test_product_catalog.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b68_a1_audit.py` | 0 | 5.744885 | 10 | [test_b68_a1_audit.log](reports/b70_a3/test_b68_a1_audit.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_phase1_packaging.py` | 1 | 0.136386 | 23 | [test_phase1_packaging.log](reports/b70_a3/test_phase1_packaging.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t1_build_speed.py` | 1 | 17.098285 | 10 | [t1-build-speed-cache-fixed.log](reports/b70_a3/t1-build-speed-cache-fixed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t1_diagnostics.py` | 0 | 0.622733 | 5 | [test_b70_t1_diagnostics.log](reports/b70_a3/test_b70_t1_diagnostics.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_a3_integration.py` | 0 | 1.263702 | 6 | [a3-integration-final.log](reports/b70_a3/a3-integration-final.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b69_j1_wiring.py` | 0 | 5.796468 | 7 | [test_b69_j1_wiring.log](reports/b70_a3/test_b69_j1_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b69_j1_fit.py` | 0 | 5.279821 | 5 | [test_b69_j1_fit.log](reports/b70_a3/test_b69_j1_fit.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 2.223747 | 13 | [build-panel.log](reports/b70_a3/build-panel.log) |

## Complete recorded implementation and verification command ledger

Elapsed times below use a monotonic subprocess clock. Full stdout/stderr and nonzero results are retained in [commands.jsonl](reports/b70_a3/commands.jsonl), including the report-writing command completed after the table was generated. Read-only discovery/inspection commands and their tool wall-clock times are separately recorded in [inspection-commands.json](reports/b70_a3/inspection-commands.json). `python3 -` entries used the inline scripts from the session; the exact resulting source/pin changes are in commit `cbcccaee`. Applied edits are additionally reconstructed by the retained audit program. The final report commit and bundle verification occur after this report is frozen; their exact commands, exits and timings are in [.scratch/astra-b70-a3-delivery.json](.scratch/astra-b70-a3-delivery.json).

| Exact command | Exit | Elapsed seconds | Output |
| --- | ---: | ---: | --- |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_wiring.py` | 1 | 0.367178 | [wiring-before.log](reports/b70_a3/wiring-before.log) |
| `python3 .scratch/apply_a3.py` | 1 | 0.241202 | [apply-wiring.log](reports/b70_a3/apply-wiring.log) |
| `python3 -c 'from pathlib import Path; s=Path('"'"'.scratch/apply_a3.py'"'"').read_text(); exec(s[:s.index('"'"'session = '"'"')] + s[s.index("path = Path('"'"'mod_editor/capabilities/registry.v1.json'"'"')"):])'` | 0 | 0.052233 | [apply-registry.log](reports/b70_a3/apply-registry.log) |
| `python3 -m mod_editor.capabilities.validate_registry` | 1 | 0.145476 | [registry-strict.log](reports/b70_a3/registry-strict.log) |
| `python3 packaging/repin.py --apply` | 0 | 20.046894 | [repin-wiring.log](reports/b70_a3/repin-wiring.log) |
| `python3 -m mod_editor.capabilities.validate_registry` | 1 | 0.130807 | [registry-after-repin.log](reports/b70_a3/registry-after-repin.log) |
| `git diff --check` | 0 | 0.646177 | [diff-wiring.log](reports/b70_a3/diff-wiring.log) |
| `python3 .scratch/setup_git_a3.py` | 0 | 0.054993 | [setup-private-git.log](reports/b70_a3/setup-private-git.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_wiring.py` | 0 | 1.027828 | [test_b70_t2_wiring.log](reports/b70_a3/test_b70_t2_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_reporting.py` | 0 | 0.247250 | [test_b70_t2_reporting.log](reports/b70_a3/test_b70_t2_reporting.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_equipment.py` | 0 | 1.345134 | [test_b70_t2_equipment.log](reports/b70_a3/test_b70_t2_equipment.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_stadium.py` | 0 | 29.513545 | [test_b70_t2_stadium.log](reports/b70_a3/test_b70_t2_stadium.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_native.py` | 0 | 0.100780 | [test_b70_t2_native.log](reports/b70_a3/test_b70_t2_native.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_a2_wiring.py` | 0 | 2.306946 | [test_b70_a2_wiring.log](reports/b70_a3/test_b70_a2_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_studio_facade.py` | 0 | 0.368252 | [test_studio_facade.log](reports/b70_a3/test_studio_facade.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_studio_session.py` | 0 | 0.834327 | [test_studio_session.log](reports/b70_a3/test_studio_session.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_build_service.py` | 0 | 0.270314 | [test_nfl2k5_build_service.log](reports/b70_a3/test_nfl2k5_build_service.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_studio_shell_layout_qt.py` | 1 | 4.601301 | [test_studio_shell_layout_qt.log](reports/b70_a3/test_studio_shell_layout_qt.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_import.py` | 0 | 2.038292 | [test_nfl2k5_equipment_import.log](reports/b70_a3/test_nfl2k5_equipment_import.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_import_wiring.py` | 0 | 0.724850 | [test_nfl2k5_equipment_import_wiring.log](reports/b70_a3/test_nfl2k5_equipment_import_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py` | 0 | 25.600566 | [test_nfl2k5_equipment_consumers.log](reports/b70_a3/test_nfl2k5_equipment_consumers.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py` | 0 | 1.761725 | [test_nfl2k5_equipment_scope_wiring.log](reports/b70_a3/test_nfl2k5_equipment_scope_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_providers.py` | 0 | 3.535609 | [test_providers.log](reports/b70_a3/test_providers.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_provider_integrity.py` | 1 | 7.581762 | [test_provider_integrity.log](reports/b70_a3/test_provider_integrity.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_product_catalog.py` | 0 | 0.155282 | [test_product_catalog.log](reports/b70_a3/test_product_catalog.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b68_a1_audit.py` | 0 | 5.744885 | [test_b68_a1_audit.log](reports/b70_a3/test_b68_a1_audit.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_phase1_packaging.py` | 1 | 0.136386 | [test_phase1_packaging.log](reports/b70_a3/test_phase1_packaging.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t1_build_speed.py` | 1 | 16.603923 | [test_b70_t1_build_speed.log](reports/b70_a3/test_b70_t1_build_speed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t1_diagnostics.py` | 0 | 0.622733 | [test_b70_t1_diagnostics.log](reports/b70_a3/test_b70_t1_diagnostics.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_a3_integration.py` | 0 | 1.240089 | [test_b70_a3_integration.log](reports/b70_a3/test_b70_a3_integration.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b69_j1_wiring.py` | 0 | 5.796468 | [test_b69_j1_wiring.log](reports/b70_a3/test_b69_j1_wiring.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b69_j1_fit.py` | 0 | 5.279821 | [test_b69_j1_fit.log](reports/b70_a3/test_b69_j1_fit.log) |
| `python3 -c 'from tests.mod_editor.test_provider_integrity import local_import_closure; from mod_editor.core.providers import Nfl2k5UnifiedVisualProvider as P; p=P(); print(sorted(local_import_closure('"'"'mod_editor/studio/session.py'"'"') - set(p.module_pins)))'` | 0 | 2.741786 | [provider-missing.log](reports/b70_a3/provider-missing.log) |
| `python3 -` | 0 | 0.024997 | [add-provider-pins.log](reports/b70_a3/add-provider-pins.log) |
| `python3 packaging/repin.py --apply` | 0 | 10.070944 | [repin-cache-seam.log](reports/b70_a3/repin-cache-seam.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t2_equipment.py` | 0 | 1.194307 | [t2-equipment-cache-fixed.log](reports/b70_a3/t2-equipment-cache-fixed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_provider_integrity.py` | 0 | 8.060924 | [provider-integrity-fixed.log](reports/b70_a3/provider-integrity-fixed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_t1_build_speed.py` | 1 | 17.098285 | [t1-build-speed-cache-fixed.log](reports/b70_a3/t1-build-speed-cache-fixed.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_b70_a3_integration.py` | 0 | 1.263702 | [a3-integration-final.log](reports/b70_a3/a3-integration-final.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_import.py` | 0 | 2.147515 | [equipment-import-final.log](reports/b70_a3/equipment-import-final.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_build_panel_qt.py` | 0 | 2.223747 | [build-panel.log](reports/b70_a3/build-panel.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py` | 0 | 25.990167 | [equipment-consumers-final.log](reports/b70_a3/equipment-consumers-final.log) |
| `python3 -m mod_editor.capabilities.validate_registry --skip-file-checks` | 0 | 0.103569 | [registry-structure-only.log](reports/b70_a3/registry-structure-only.log) |
| `git --git-dir=.scratch/git-a3 --work-tree=. add -- mod_editor/studio/session.py mod_editor/gui/studio_qt.py mod_editor/core/nfl2k5_build_service.py mod_editor/core/nfl2k5_equipment_import.py mod_editor/core/equipment_staging.py mod_editor/core/providers.py mod_editor/capabilities/registry.v1.json packaging/release-allowlist.txt packaging/check_2k5_mod_studio_runtime.py tests/mod_editor/test_b70_t2_wiring.py tests/mod_editor/test_b70_a3_integration.py tests/mod_editor/test_provider_integrity.py tests/mod_editor/b70_equipment_fixture.py` | 0 | 0.041187 | [stage-code.log](reports/b70_a3/stage-code.log) |
| `python3 packaging/repin.py --apply` | 0 | 10.081278 | [repin-before-code-commit.log](reports/b70_a3/repin-before-code-commit.log) |
| `git --git-dir=.scratch/git-a3 --work-tree=. commit -m 'Wire beta 70 T2 equipment fits and stadium summaries into the stack' -- mod_editor/studio/session.py mod_editor/gui/studio_qt.py mod_editor/core/nfl2k5_build_service.py mod_editor/core/nfl2k5_equipment_import.py mod_editor/core/equipment_staging.py mod_editor/core/providers.py mod_editor/capabilities/registry.v1.json packaging/release-allowlist.txt packaging/check_2k5_mod_studio_runtime.py tests/mod_editor/test_b70_t2_wiring.py tests/mod_editor/test_b70_a3_integration.py tests/mod_editor/test_provider_integrity.py tests/mod_editor/b70_equipment_fixture.py` | 0 | 2.247999 | [commit-code.log](reports/b70_a3/commit-code.log) |
| `python3 reports/b70_a3/audit_wiring.py` | 0 | 1.074790 | [wiring-audit.log](reports/b70_a3/wiring-audit.log) |
| `python3 -` | 0 | 0.023881 | [audit-summary.log](reports/b70_a3/audit-summary.log) |
| `git --git-dir=.scratch/git-a3 --work-tree=. diff ded9c222 --check` | 0 | 0.025750 | [final-whitespace.log](reports/b70_a3/final-whitespace.log) |
| `git --git-dir=.scratch/git-a3 --work-tree=. show --stat --oneline HEAD` | 0 | 0.021538 | [final-git-summary.log](reports/b70_a3/final-git-summary.log) |
| `python3 packaging/repin.py --apply` | 0 | 9.890954 | [final-repin.log](reports/b70_a3/final-repin.log) |
| `python3 -m mod_editor.capabilities.validate_registry` | 1 | 0.129052 | [registry-final-strict.log](reports/b70_a3/registry-final-strict.log) |
| `python3 .scratch/write_report_a3.py` | 0 | 0.169213 | [write-report.log](reports/b70_a3/write-report.log) |
| `env QT_QPA_PLATFORM=offscreen PYTHONPATH=.:tools python3 tests/mod_editor/test_providers.py` | 0 | 3.542769 | [providers-final.log](reports/b70_a3/providers-final.log) |

ASTRA_DONE
