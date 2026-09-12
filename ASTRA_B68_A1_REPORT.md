# Beta 68 A1: independent audit of T1 and T2

Audited stack head `925c5da6df40697a38106a16ae39683e928ba182`, rooted at marker `c8783a64406ce6b062a7b287173ecbe778f43df2`. Read ASTRA_CONTEXT, BETA68_TRIAGE, both job reports and both wiring documents. The requested `astra/b68-a1-audit` branch was already at that head. No other worktree or main checkout was changed, and nothing was pushed.

**Five proved implementation/coverage defects were fixed, along with two stale integration test fixtures.** Applied wiring otherwise matches the proposals, with the documented report names and module-form validation command. This is a bounded code, bytes and offscreen audit. It does not certify played stability, GPU appearance, a Windows-host run, or the reported 402-edit build time.

## Findings and fixes

| Hunk / subject | Verdict | Evidence and fix |
|---|---|---|
| D1: T2 added a registry row but left the runtime registry/product counts and success banner at 160/90; packaging test repeated the stale banner | **PROVED defect** | The new `IntegrationTests.test_runtime_counts_match_the_canonical_registry` executes the actual production assertions against the actual registry: both fail before the fix. Pin 161 shared rows and 91 NFL 2K5 rows in the runtime assertions/banner and packaging expectation. Staged runtime now passes. |
| D2: T1 added `nfl2k5_compile_cache.py` to the allowlist/provider, but omitted the runtime's explicit product import list and required unified closure set | **PROVED coverage defect** | New `test_new_core_modules_are_in_all_release_closures` fails on the missing required entry. Add the module to both lists; its digest already belonged in the 271-module unified provider closure. This was a missing explicit gate, not an observed application import failure. |
| D3: T2 retail-origin recognition in `build_unified_uniform_equipment_imports` ran for palette-only imports | **PROVED defect** | New `test_palette_only_sock_and_shoe_ignore_retail_chain_hint` fails for both families: an origin hint appends private indices and increases video allocation despite palette-only intent. Restrict chain preservation to selected own-texture references. The companion `same_visual_import` comparison also ignores origin metadata in palette-only mode, so metadata alone cannot create an edit or block an unchanged restore; own-texture comparisons still distinguish origin because lower mips can differ. The new equality test failed before this correction. The test substitutes only the pinned donor lookup and uses the real projector/compiler/readback. Solid sock/shoe output then equals the existing palette-only path byte-for-byte, with zero added video bytes. |
| D4: T1 `CompileCache.get` calls `.encode()` on an unvalidated JSON envelope payload | **PROVED defect** | New `test_compile_cache_discards_structurally_corrupt_envelopes` produces three `AttributeError`s for integer/list/object payloads. Validate envelope/payload types before decoding so damaged derived entries become ordinary misses. Six malformed envelopes are tested. No cache serialization, eviction or valid-hit behavior was rewritten. |
| D5: T2 `_rebuild_fixed_span` recompressed an unchanged span, then discarded that stream and returned the original with the new stream's statistics | **PROVED defect** | New `test_unchanged_span_keeps_its_original_stream_and_reports_actual_transport`: a valid bounded original optimal stream occupies 3,149 bytes but its needless greedy rebuild overflows; a filled original consumes 5,184 bytes while the old receipt claims 3,152. Return the original transport directly, calculate its actual consumed bytes/scratch requirements, verify the scratch guards and report exact stream/span identity. No encoder is invoked for a no-op. Both failures are retained in `noop-transport-before.log`. The affected retail shoe round-trip is rerun. |
| T2 dialog superseded the beta-66 in-memory panel handoff, but `test_beta66_d1_panels.py` still required its old text and invented selectors | **PROVED test integration defect** | Standalone test failed `wiring context drifted`. Exercise the shipped dialog using catalog shoe/sock/elbow-pad rows, retaining default-choice and explicit-recolour assertions. Socks now correctly expect own artwork by default. |
| T2 original-cache tagging needs the real `ExtendedVisualAsset.kind`, but `test_2k5_stale_original_cache.py`'s test double omitted it | **PROVED test integration defect** | Four `AttributeError` paths in the existing standalone suite. Give the non-equipment test double its actual `p8_texture` kind; all reuse, stale metadata, tamper and concurrent publication assertions remain. No production fallback was added for an invalid test double. |
| T1 compile keys, grouping, parallel misses and receipt verification | **clean in the bounded tests** | Production persistent cache lookup is exercised across every cached edit field, source RGBA channels/dimensions, input paths, recipe bytes, index/inventory/report fingerprints and compiler/helper contents. Equipment cache independently misses on target, pixels, own/palette mode, original/half/quarter size and origin hint. T1's real-encoder cold/warm/one-change build and parallel-miss tests pass. |
| Corruption inside a written receipt span | **clean** | New `WrittenSpanTests` corrupts the actual output span. Normal verification rejects the changed file snapshot. With only the snapshot guard bypassed, it still fails `written span hash changed`, while recompilation and full scans are forbidden by the test. This proves the byte check, not merely timestamp detection. |
| Team Kit compare and first-use Equipment navigation | **clean** | Fresh offscreen navigation constructs the browser once and exposes 45 selected-set entries. Export staged kit, edit one file, import 1/skip 77; repeat import 0/skip 78; preserve destination artwork for an untouched baseline. The hydrated real-catalog Team Kit, product integration and cross-project suites pass. |
| Shoe scope and retail equipment transport | **clean after D3/D5** | Real dialog exposes only All teams for global rows. Core rejects explicit per-team scope before artwork access/mutation with “All teams share this style because the game reads its texture from the most recently loaded uniform package.” Retail same-slot and other-slot export/import tests run, preserve all six shoe mips and palette, and prove designed sock base/mips and separate bump span. |
| Shoe relief, normal-map palette and native material binding | **clean in bounded byte/CPU proofs** | All seven retail GLOBAL.IFF maps are exercised, exact authored P8 distance images verified, scratch retained, and lower-mip-only corruption rejected. Native tests use pinned retail executable bytes and distinguish local diffuse from shared relief. These tests do not witness GPU output. |
| Helper release contract and no-helper path | **clean** | Exact delivered binary is 16,504 bytes, SHA-256 `949aad6a251de3f039f83bff15d4aa033183c250dbeadd1029e7c79dee4817c4`; C source is 4,648 bytes, SHA-256 `6c9c7470d40ce3b99ac000fe75bd51c7d2fbeb44f783e313eb7b7dee0f0b8390`. Git records 100755. This checkout's umask made the file 0775; the existing reviewed setup function normalized that exact verified helper to 0755. Native equivalence tests then ran without fallback/skips. The new Windows-platform test selects the actual no-helper branch and compares exact streams across offset widths 10–13. Actual Windows-host execution remains unwitnessed. |
| Registry row canonicality / validation-command deviation | **clean for the integration** | All 161 rows pass the canonical registry validator with file existence disabled. The new row exactly equals WIRING after replacing `ASTRA_REPORT.md` with its job name and using `python3 -m tests.mod_editor.test_nfl2k5_shoe_relief`; that command actually passes. The full file-existence gate encounters 137 missing historical module/evidence references, unchanged from the marker baseline; none was added by T1/T2. No registry checks or tests were weakened to conceal this environment gap. |
| 402-edit retail timing, reporter screenshots, game stability and rendered sharpness | **HYPOTHESIS / UNWITNESSED** | T1's synthetic measurements do not certify maumau78's one-hour workload or Coach Edwards' 90-minute build. This audit made no full retail disc, no emulator/game run and no Windows-host timing claim. The screenshots cannot prove which import choice produced each old smear. |

The initial audit log also contains an abandoned Windows-permission probe. It mocked the release checker into Windows mode while leaving the test class in Linux mode. Inspection showed the entire POSIX packaging class already has a Windows skip; that hypothesis was rejected and no permission-test change was retained. This is recorded so an early failed experiment is not mistaken for an extra defect.

## Reconstruction and complete hunk accounting

The T1 “merge” is actually linear: `a8676133` has only parent `7d139852`, the exact T1 bundle tip. Its two job commits are `35c3e65f` and `7d139852`. T2 is a genuine two-parent merge of `a8676133` and `d50b1abf`, the exact T2 bundle tip. The direct T2-tip diff includes all inherited T1 work; treating that entire diff as Opus-authored would be incorrect.

The real worktree Git directory rejected FETCH_HEAD with `Read-only file system`. Private Git metadata is `/tmp/astra-b68-a1-git`, bound to this same worktree and sharing only read access to existing objects. Both supplied bundles were fetched there into `refs/audit/t1` and `refs/audit/t2`. The reconstruction commands were:

```sh
git --git-dir=/tmp/astra-b68-a1-git fetch /home/noah/2k-worktrees/astra-b68-t1/ASTRA_T1.bundle astra/b68-t1-build:refs/audit/t1
git --git-dir=/tmp/astra-b68-a1-git fetch /home/noah/2k-worktrees/astra-b68-t2/ASTRA_T2.bundle astra/b68-t2-equipment:refs/audit/t2
git --git-dir=/tmp/astra-b68-a1-git diff --find-renames refs/audit/t1 a8676133
git --git-dir=/tmp/astra-b68-a1-git merge-tree --write-tree a8676133 refs/audit/t2
git --git-dir=/tmp/astra-b68-a1-git diff --find-renames 998226154c97ea8987b36128e94c9c526ceec73d 925c5da6
git --git-dir=/tmp/astra-b68-a1-git diff --find-renames refs/audit/t2 925c5da6
```

The automatic T2 tree has only two conflicts: changelog bullet insertion and adjacent provider pins. Both were resolved correctly. Full patches are [T1 integrator delta](reports/b68_a1/t1-integration.patch), [T2 integrator delta](reports/b68_a1/t2-integration.patch), and [T2 direct bundle comparison](reports/b68_a1/t2-vs-bundle.patch). [Mechanical wiring checks](reports/b68_a1/wiring-checks.json) prove full-dialog byte equality, navigation AST equality, canonical JSON and exact new-row equality after the two documented substitutions.

The table below accounts for every actual integrator hunk and both pairs of report renames. Missing integration work is accounted for separately as D1/D2, rather than invented as a diff hunk.

| Hunk | File / applied location | Verdict | Judgment / fix |
|---|---|---|---|
| T1-01 | `ASTRA_B68_T1_REPORT.md` | clean | Report renamed byte-for-byte; no claims changed. |
| T1-02 | `WIRING_B68_T1.md` | clean | Wiring renamed byte-for-byte. |
| T1-03 | `mod_editor/core/providers.py:557` | clean | Exact WIRING compile-cache SHA entry added to the unified provider. Runtime-list omission is D2 below. |
| T1-04 | `packaging/check_2k5_mod_studio_release.py:604` | clean | Exact path-specific helper/C-source exception from WIRING; size, SHA, ELF and 0755 checked; generic refusals retained. |
| T1-05 | `packaging/release-allowlist.txt:839` | clean | Exact three allowlist paths from WIRING; no benchmark/private cache added. |
| T1-06 | `tests/mod_editor/test_phase1_packaging.py:160` | clean | Seven helper acceptance/refusal/pin-agreement tests added. Full class already skips POSIX permission assertions on Windows; no weakening. |
| T1-07 | `tools/setup_reviewed_helpers.py:1` | clean | Setup helper docstring updated for two reviewed files. |
| T1-08 | `tools/setup_reviewed_helpers.py:22` | clean | Reviewed map adds the exact equipment helper size/hash; APF constants retained. |
| T1-09 | `tools/setup_reviewed_helpers.py:41` | clean | normalize accepts only a map key; original default APF call preserved. |
| T1-10 | `tools/setup_reviewed_helpers.py:72` | clean | Descriptor-bound size/hash check parameterized by the reviewed map. |
| T1-11 | `tools/setup_reviewed_helpers.py:90` | clean | Re-read length parameterized; still compares the same bytes on the same descriptor. |
| T1-12 | `tools/setup_reviewed_helpers.py:99` | clean | Receipt names the selected helper; normalize_all and CLI call both in stable order. Source umask 0775 required the documented explicit normalization; staged binary is 0755. |
| T2-01 | `ASTRA_B68_T2_REPORT.md` | clean | Report renamed byte-for-byte. |
| T2-02 | `WIRING_B68_T2.md` | clean | Wiring renamed byte-for-byte. |
| T2-03 | `docs/mod_editor/2k5_mod_studio_changelog.md:4` | clean | Only conflict markers removed; both jobs’ changelog bullets retained. |
| T2-04 | `mod_editor/capabilities/registry.v1.json:10681` | clean | All Textures evidence appends the two tests and renamed report exactly. |
| T2-05 | `mod_editor/capabilities/registry.v1.json:10699` | clean | All Textures own-artwork paragraph matches WIRING exactly. The preceding promise that the original shared indices survive remains true when a private chain is appended. |
| T2-06 | `mod_editor/capabilities/registry.v1.json:10870` | clean | All Visual evidence appends the two tests and renamed report exactly. |
| T2-07 | `mod_editor/capabilities/registry.v1.json:10890` | clean | All Visual equipment paragraph matches WIRING exactly. |
| T2-08 | `mod_editor/capabilities/registry.v1.json:10939` | clean | Bump capability row equals WIRING after report rename and canonical module-form validation_command. Sorted insertion and canonical JSON proved; counts/required runtime lists were missed (D1/D2). |
| T2-09 | `mod_editor/core/providers.py:576` | clean | Conflict keeps T2 import-intent digest and T1 LZ digest. Both match the corresponding merge-result sources at 925c5da6. |
| T2-10 | `mod_editor/gui/bump_panel_qt.py:46` | clean | Exact SHOE_BUMP_NAMES/SHOE_BUMP_SCOPE import. |
| T2-11 | `mod_editor/gui/bump_panel_qt.py:175` | clean | Exact title and scope subtitle from WIRING. |
| T2-12 | `mod_editor/gui/bump_panel_qt.py:228` | clean | Exact Package table heading from WIRING. |
| T2-13 | `mod_editor/gui/bump_panel_qt.py:624` | clean | Exact per-slot scope/distance-image status from WIRING. |
| T2-14 | `mod_editor/gui/bump_panel_qt.py:688` | clean | Exact preflight status including returned scope from WIRING. |
| T2-15 | `mod_editor/gui/bump_panel_qt.py:717` | clean | Exact selected-package/global write confirmation from WIRING. |
| T2-16 | `mod_editor/gui/equipment_texture_import_dialog.py:10` | clean | Dialog imports shared scope resolver and local-shoe help exactly. |
| T2-17 | `mod_editor/gui/equipment_texture_import_dialog.py:24` | clean | Dialog scope controls, global explanation and sock default exactly match WIRING. |
| T2-18 | `mod_editor/gui/equipment_texture_import_dialog.py:76` | clean | Dialog scope property exactly matches WIRING. |
| T2-19 | `mod_editor/gui/studio_qt.py:386` | clean | Facade protocol adds nullable independent and scope arguments exactly. |
| T2-20 | `mod_editor/gui/studio_qt.py:5587` | clean | Dialog result carries independent/scale/scope exactly. |
| T2-21 | `mod_editor/gui/studio_qt.py:5665` | clean | Replacement worker forwards all three arguments exactly. |
| T2-22 | `packaging/check_2k5_mod_studio_runtime.py:99` | clean | Generated studio_qt.py digest matches integrated source; other merged facade pin retained. |
| T2-23 | `tests/mod_editor/test_2k5_uniform_equipment_export.py:255` | clean | Export/resize test facade accepts new scope keyword, keeping its palette writer assertion. |
| T2-24 | `tests/mod_editor/test_2k5_uniform_equipment_export.py:268` | clean | Explicit palette-only dialog stub gains scope; test still exercises the selected palette-only path. |
| T2-25 | `tests/mod_editor/test_nfl2k5_equipment_import.py:231` | clean | Shoe selector moved from invented outer 0 to real catalog 3613; assertions and real dialog preserved. |
| T2-26 | `tests/mod_editor/test_nfl2k5_equipment_import.py:251` | clean | Elbow-pad selector/dimensions corrected to catalog row 3613, 128x64; unsupported own-artwork assertion preserved. |
| T2-27 | `tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py:17` | clean | Scope test imports actual shipped dialog; removes dependency/skip on old WIRING.md, increasing coverage. |
| T2-28 | `tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py:54` | clean | Schema test validates the actual single registered bump row instead of a proposal. |
| T2-29 | `tests/mod_editor/test_product_catalog.py:74` | clean | Expected product IDs adds exactly the new bump capability. |
| T2-30 | `tests/mod_editor/test_product_catalog.py:156` | clean | Unique/stable product count 90 to 91 matches actual registered set. |
| T2-31 | `tests/mod_editor/test_product_catalog.py:190` | clean | Uniform category 5 to 6, editable 4 to 5 matches new writer row. |
| T2-32 | `tests/mod_editor/test_product_catalog.py:228` | clean | Global product count 90 to 91, editable 70 to 71 matches new writer row. |
| T2-33 | `tests/mod_editor/test_product_catalog.py:281` | clean | Inspection loader count 90 to 91 matches actual product iteration. |
| T2-34 | `tests/mod_editor/test_provider_integrity.py:201` | clean | Unified closure 270 to 271 matches AST-import closure with compile cache; remaining five closures untouched. |

## Verification and limits

Standalone selection uses `rg -l` over every changed Python module name, includes the directly changed tests and helper setup tests, and excludes APF-only filenames. The exact pattern, module names and 118 selected files are retained in [test-selection.json](reports/b68_a1/test-selection.json). The added audit file and `test_studio_session.py` bring the total to 120 distinct standalone files. Each runs in a separate Python process with:

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 python3 <test-file>
```

The final file totals and individual commands, timings, test counts, skips and linked stdout/stderr are in [test-results.md](reports/b68_a1/test-results.md) and [final-results.json](reports/b68_a1/final-results.json). **118 files pass; two retain historical-document loader errors.** The final runs execute 1,288 counted test cases with 15 skips; class setup errors are recorded separately by unittest. Those are `test_all_textures_workspace.py` (two registry-loading errors; its other 21 tests pass) and `test_no_capability_is_invisible.py` (two registry-dependent class setup errors; its two version checks pass). Both fail on the missing `docs/research/apf_audio.md` before reaching any T1/T2 behavior. The unchanged baseline has the same missing reference, among 137 missing historical file references enumerated in wiring-checks.json. Neither test nor the validator was changed to skip the file check. This is not a fully green repository-wide certification.

Generated public catalogs were initially absent. This audit found the local beta-67 portable archive at the scratch ship path, verified its full SHA-256 `ee420a9ff4e418546e1e673f7168782da398e0d290bf17479d0695f768779d00` against the published beta-67 release body, and hydrated only 16 missing allowlisted metadata files (106,760,608 bytes). No tracked source was overwritten. All 24 staged reviewed metadata contracts pass the release checker. The files remain ignored and are not bundled with these audit commits; [hydration.json](reports/b68_a1/hydration.json) records each size and hash.

The colour-session test additionally needed the existing private resource inventory. It passed with a temporary symlink to Noah's existing cache inventory, removed in `finally`; no retail payload was copied or committed. Its exact fixture path and command result are in [private-inventory-test.json](reports/b68_a1/private-inventory-test.json). The 15 precise missing-fixture/platform skips in the selected suites remain visible in the test table. The new retail equipment round-trip, native equipment and seven-shoe-relief proofs ran without skips.

Final production validation:

```sh
PYTHONPATH=. python3 -m mod_editor.capabilities.validate_registry --skip-file-checks
# MOD_CAPABILITY_REGISTRY_VALIDATION_PASS ... capabilities=161
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 python3 -m tests.mod_editor.test_nfl2k5_shoe_relief
# Ran 5 tests; OK
python3 packaging/stage_release.py packaging/release-allowlist.txt /tmp/astra-b68-a1-release
# staged 820 files; 0 declared inputs absent
python3 packaging/check_2k5_mod_studio_release.py /tmp/astra-b68-a1-release
# 2K5_MOD_STUDIO_RELEASE_PASS files=820 directories=36 bytes=138591376 metadata=24 ...
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 python3 /tmp/astra-b68-a1-release/packaging/check_2k5_mod_studio_runtime.py
# 2K5_MOD_STUDIO_RUNTIME_CLOSURE_PASS product_modules=231 tool_modules=35 registry=161 sections=12 nfl2k5_capabilities=91 ...
python3 packaging/check_2k5_mod_studio_release.py /tmp/astra-b68-a1-release
# PASS again: runtime did not leave bytecode/undeclared files in the stage
python3 packaging/repin.py --include-tests
# would apply 0 pin update(s)
git diff --check 925c5da6 -- . ':(exclude)reports/b68_a1/*.patch'
# no whitespace errors in authored source, tests, report or logs
```

The saved `.patch` files retain exact Git diff context lines, including the single-space representation of a blank context line. They are excluded only from the authored-file whitespace check; the raw reconstruction evidence is unchanged.

The repository's actual validator is `mod_editor/capabilities/validate_registry.py`; there is no `packaging/validate_registry.py`. The fully strict command was also run; its retained failure is [registry-baseline.log](reports/b68_a1/registry-baseline.log). Existence checks are required for complete historical evidence certification, so the canonical/schema-only pass is named explicitly.

The stage was first built from the allowlist. After D5 and the companion palette-equality fix, only the changed allowlisted source files were refreshed in that owned stage; release and runtime checks were repeated, producing the final results above. All tests importing the changed writer/cache were rerun after D5, plus native equipment and build-service suites. Source/edit options, compiled helper, registry semantics and GUI wiring otherwise stay as reviewed.

No XBE writer, cave allocation, preset or APF behavior was changed. T1/T2 edits here are archive/tool operations, so no cave manifest regeneration was needed. No emulator, displayed GUI, audio, network, retail disc copy or full disc build was used. The initial root filesystem had 98 GiB free, below the 100 GiB disc-build floor; work remained bounded tests, metadata and the retail-free release stage.

## Delivery and remaining witnesses

Implementation commit `6a3c148a` fixes D1–D4 and the stale test fixtures. Implementation commit `9e8e16dc` fixes D5 and strengthens the compiler-content key proof; commit `1ef068e4` completes D3 by ignoring ineffective origin metadata in palette-only equality; the final evidence commit contains this report and the audit logs. All use explicit paths, with `python3 packaging/repin.py --apply` as the last content-generation step before each commit. Only provider digests changed: compile-cache, equipment-writer and import-intent hashes. No pins were loosened.

`ASTRA_A1.bundle` carries the commits on `astra/b68-a1-audit` above prerequisite `925c5da6`. The real shared Git metadata remains read-only; the bundle is the authoritative committed delivery. To inspect and integrate from a writable checkout:

```sh
git bundle verify /home/noah/2k-worktrees/astra-b68-a1/ASTRA_A1.bundle
git fetch /home/noah/2k-worktrees/astra-b68-a1/ASTRA_A1.bundle astra/b68-a1-audit
# Review FETCH_HEAD, then integrate its commits on the beta-68 stack.
```

Noah still needs the requested Windows-host 402-edit timing comparison, Coach Edwards' designed/solid sock and distance retests, and maumau78's shoe copy/scope/relief A/B in both home/away orders. Byte and bounded CPU checks do not witness those outcomes. No stronger release wording is justified by this audit.
