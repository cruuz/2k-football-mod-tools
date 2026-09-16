# Beta 71 A7: combined painted-bar integration

Private branch `astra/b71-a7-integrate` starts from A6 `07c544a2c9a5c20c27a8e6557874b15a552d9d82` and merges S4 `7b54e354ab8187c59b12cf66671982c822bf9d03`. Private Git directory: `.scratch/git-a7`. The shared Git directory is untouched. No push, emulator or displayed GUI.

All requested final suites and both studios' release/runtime closures pass: **267 required command receipts**, **3089 reported unittest cases**, **29 documented skips**. Full logs and exact arguments are linked below. Skips retain their stated boundaries and are not runtime evidence.

Registry: **176 unique capabilities = 102 2K5 + 73 APF + 1 third game**. Provider closure: **288**. Product catalog tuple: **`(102, 80, 8, 1, 0, 10, 3)`**, with its exact ID set. Validation-plan pins: **176 total / 171 covered / 5 deferred / 129 distinct validators**. The id-indexed union retains every exact A6 row except the exact updated S4 scorebug runtime row. Colour v2.1, day/afternoon tuning, linked sidelines, modern Arrowhead and APF4/APF5 remain integrated.

## Merge and conflict receipt

Before any workspace mutation other than those copies, S4's root report and wiring were archived as `ASTRA_B71_S4_REPORT.md` and `WIRING_B71_S4.md`, with human attributions anonymized. The A6 report is retained anonymously at `reports/b71_a7/INHERITED_A6_REPORT.md`.

The explicit-commit merge had six conflicts:

1. `ASTRA_REPORT.md`: A6 was retained as the working checkpoint, with both input reports archived; this A7 report replaces it.
2. `ASTRA_LAST_MESSAGE.md`: A6 was retained until the A7 handoff was written.
3. `data/nfl2k5_cave_reservations.json`: A6 supplied the seed; the complete merged forward stack was observed and the manifest regenerated last.
4. `docs/mod_editor/2k5_mod_studio_changelog.md`: both sides' distinct bullets were retained, including the older scorebug iteration history and S4 painted-bar entry.
5. `packaging/release-allowlist.txt`: both colour-control paths and all three S4 module/label paths were retained.
6. `tests/mod_editor/test_provider_integrity.py`: The initial A6 287-module pin was retained, then the exact closure test measured 288 because S4 adds `nfl2k5_scorebug_assets.py`. The pin was corrected to 288; the exact-set/hash assertions remain unchanged and pass.

The registry, provider pin map and remaining implementation merged cleanly. S4 supersedes the inherited S3 atlas/wing/plate/capsule/label/score-cell implementation through normal ancestry. Generated pin files were passed through `packaging/repin.py --apply`, which needed zero updates. All commits enumerate explicit paths; `git commit --include -- <paths>` preserves the real merge parents while concluding the conflicted merge.

## Wiring and release integration

S4's `WIRING.md` is byte-identical to its S3 parent's file; it contains inherited beta-70 T1 follow-ups, not new S4 instructions. Its completion-dialog hooks are already present in A6. Historical Windows-helper and digit-fit proposals are not new painted-bar work. The root `WIRING.md` records this disposition.

One S4 packaging omission was corrected: the new authored `painted_label_2x.png` was allowlisted but absent from the exact reviewed PNG catalog. Its catalog entry now pins 11,138 bytes, 512×256 dimensions and SHA-256 `b8632704a110087b939a2e1de98c54eebc2354f40bb89d3eb2f0b16bdfa45b2d`; the catalog hash is refreshed. No binary-validation rule was relaxed. See `label-release-pin.json`.

The 75 inherited ignored evidence files were initially absent. `reports/b71_apf4/hydrate.py` restored independent copies from the recorded read-only sources, checking the prior inventory; `audit_pins.py` also checked S4's SHA-256 inventory: **2,063,157 bytes**, all single-link files. These private inputs are not staged or bundled. The strict registry validator keeps its default file checks. Reviewed APF release tooling and the pinned local Capstone test environment were restored using the existing A6 recipes without network or system changes.

| Wiring/count anchor | File:line |
| --- | --- |
| `len(registry.capabilities) == 176` | `packaging/check_2k5_mod_studio_runtime.py:2178` |
| `len(product_catalog.capabilities) == 102` | `packaging/check_2k5_mod_studio_runtime.py:2182` |
| `registry=176 sections=12 nfl2k5_capabilities=102` | `packaging/check_2k5_mod_studio_runtime.py:2585` |
| `len(registry.capabilities) == 176` | `packaging/check_apf2k8_mod_studio_runtime.py:1389` |
| `== 73` | `packaging/check_apf2k8_mod_studio_runtime.py:1390` |
| `len(cards) == 73` | `packaging/check_apf2k8_mod_studio_runtime.py:1394` |
| `len(registry.capabilities), 176` | `tests/mod_editor/test_b68_a1_audit.py:41` |
| `len(catalog.capabilities), 102` | `tests/mod_editor/test_b68_a1_audit.py:42` |
| `registry=176 sections=12 nfl2k5_capabilities=102` | `tests/mod_editor/test_b68_a1_audit.py:54` |
| `registry=176 sections=12 nfl2k5_capabilities=102` | `tests/mod_editor/test_phase1_packaging.py:571` |
| `len(registry.capabilities) == 176` | `tests/mod_editor/test_apf_studio_installer.py:360` |
| `(102, 80, 8, 1, 0, 10, 3)` | `tests/mod_editor/test_product_catalog.py:242` |
| `nfl2k5.stadiums_fields.modern_arrowhead` | `tests/mod_editor/test_product_catalog.py:78` |
| `self.assertEqual(set(first_ids), expected)` | `tests/mod_editor/test_product_catalog.py:172` |
| `[288, 10, 8, 9, 8, 9]` | `tests/mod_editor/test_provider_integrity.py:218` |
| `EXPECTED_CAPABILITIES = 176` | `tools/validate_all_mod_editor_capabilities.py:62` |
| `EXPECTED_COVERED_CAPABILITIES = 171` | `tools/validate_all_mod_editor_capabilities.py:63` |
| `EXPECTED_DEFERRED_CAPABILITIES = 5` | `tools/validate_all_mod_editor_capabilities.py:64` |
| `EXPECTED_UNIQUE_VALIDATORS = 129` | `tools/validate_all_mod_editor_capabilities.py:65` |
| `"id": "nfl2k5.scorebug_presentation.runtime"` | `mod_editor/capabilities/registry.v1.json:10565` |
| `"id": "nfl2k5.presentation.modern_color_lighting"` | `mod_editor/capabilities/registry.v1.json:9698` |
| `"id": "nfl2k5.stadiums_fields.modern_arrowhead"` | `mod_editor/capabilities/registry.v1.json:11583` |
| `"id": "apf2k8.playbooks.cpu_playcalling"` | `mod_editor/capabilities/registry.v1.json:2646` |
| `"id": "apf2k8.playbooks.fourth_down"` | `mod_editor/capabilities/registry.v1.json:2822` |
| `mod_editor/gui/colour_lighting_qt.py` | `packaging/release-allowlist.txt:929` |
| `docs/modern_color/CONTROLS.md` | `packaging/release-allowlist.txt:930` |
| `mod_editor/core/nfl2k5_scorebug_assets.py` | `packaging/release-allowlist.txt:931` |
| `data/nfl2k5_scorebug_mnf/painted_label_2x.png` | `packaging/release-allowlist.txt:932` |
| `data/nfl2k5_scorebug_mnf/painted_label_2x.json` | `packaging/release-allowlist.txt:933` |
| `"data/nfl2k5_scorebug_mnf/painted_label_2x.png"` | `packaging/nfl2k5_scorebug_template_pngs.json:291` |
| `SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256 =` | `packaging/check_2k5_mod_studio_release.py:304` |
| `"mod_editor/core/nfl2k5_scorebug_assets.py":` | `mod_editor/core/providers.py:698` |
| `"mod_editor/core/nfl2k5_modern_arrowhead.py":` | `mod_editor/core/providers.py:563` |
| `from mod_editor.core.nfl2k5_build_service import summarize_kept_retail` | `mod_editor/gui/studio_qt.py:8023` |
| `from mod_editor.core.nfl2k5_build_service import summarize_kept_retail` | `mod_editor/core/build_feedback.py:53` |
| `if plan.modern_arrowhead:` | `mod_editor/core/mod_build.py:1459` |
| `if plan.modern_arrowhead:` | `mod_editor/core/mod_build.py:2139` |
| `retail_source=source` | `mod_editor/core/mod_build.py:2142` |
| `CODE_SIZE, DATA_SIZE =` | `mod_editor/core/nfl2k5_scorebug_runtime.py:25` |
| `REQUESTS =` | `mod_editor/core/nfl2k5_scorebug_runtime.py:26` |
| `MNF_VERSION =` | `mod_editor/core/nfl2k5_scorebug_resources.py:671` |
| `target = (field_offset + stored - 1) & 0xffffffff` | `tools/nfl_main_menu_font.py:119` |
| `"b71_a7_projection": {` | `data/nfl2k5_cave_reservations.json:301299` |
| `NAME = ` | `reports/b71_a7/build_testdisc71.py:28` |
| `OPTIONS = ` | `reports/b71_a7/build_testdisc71.py:30` |
| `## 1. Windows helper build:` | `WIRING_B71_S4.md:58` |
| `## 2. Digit shortfalls` | `WIRING_B71_S4.md:101` |

## Appended payload and accepted visual limits

Fresh bounded compilation measured each component; `volume.json` contains individual resource sizes and hashes. No retail resources were saved in reports.

| Component | Count | Appended bytes |
| --- | ---: | ---: |
| shared 64x64 team TXTR | 32 | 168,960 |
| neutral 32x32 TXTR | 1 | 2,208 |
| painted 256x512 P8 atlas | 1 | 132,256 |
| slot-9 FirstPersonComic FONT 256x256 | 1 | 80,160 |
| core_bug quarter FONT 128x128 | 1 | 27,040 |
| **Total** | **34 TXTR + 2 FONT** | **410,624** |

The append is **0.391602 MiB**, **2,944 bytes below v3's 413,568**, within the required ~0.4 MB class. Sector-aligned pack growth is **411,648 bytes**. S4's loader allocation accounting is 414,080 native heap bytes; this is not a measured game peak-memory guarantee.

The owner emits **1,380 bytes** inside `CODE_SIZE=1408`, with `DATA_SIZE=128`. Cave requests remain `(nfl2k5_scorebug_runtime, code, 1408, 16)` and `(nfl2k5_scorebug_runtime, data, 128, 16)`. Current allocations are recorded in `manifest-receipt.json`.

The supplied v4 verdict accepts all six v3 residuals. The remaining KC transparent-cell fringe, top rim measured at (42,40,44) against the (37,37,37) body rather than about (60,64,70), and 256-pixel frame tile stretched across 1,041 source pixels were deliberately left unchanged. S4's exact-pixel comparison remains false (RGB MAE 36.479 / 35.514). Its software-render verdict does not witness gameplay or GPU filtering.

## Manifest receipt

The final manifest is the **bounded complete forward XBE projection**, using the A6 parent manifest SHA-256 `bbc7b1afd93bd4e0c7cabb02452d54e7ac05e6fe6e0d26d4ffdaf381a5368315`. The A6 recipe retains historical retail reservations, observes every forward owner, applies the colour owner and excludes delegated shared helpers from duplicate ownership. S4's changed ingame writer is explicitly observed; its two offline compiler/render tools are recorded as non-XBE source snapshots.

- Manifest SHA-256: `4b323245ae654c559172b369f00ffe77f6b7399281ec58da24178768141fd579`; 6,544,271 bytes.
- Reservations: 13,113; source seals: 337; observed writer steps: 138.
- Composed XBE SHA-256: `ef5ca3d7f44c623aec91b01512f65ad497f4ebf148d8e25e3b4041d5584ca36a`.
- `release_manifest=false`, `disc_built=false`, `runtime_witnessed=false`, `production_regeneration_required=true`; inherited disc fields are historical.
- Final projection: exit 0, 400.047 seconds. It ran after the final repin and was the last product code/data change. All 4645 other product/test/docs paths retain their frozen hashes.
- Production launcher: exit 1, 0.005 seconds. Directory creation failed with `Errno 30` / read-only Storage. External command: `bash reports/b71_a7/manifest_regen.sh`.

The projection is the requested sandbox deliverable. No production build receipt has been invented. `manifest-receipt.json` and both logs record the actual results.

## Prepared disc, not executed

`reports/b71_a7/build_testdisc71.py` is prepared and statically parsed/compiled, never imported or run, including `--plan-only`. Exact name:

`NFL 2K5 MOD TEST 2026-09-15k (everything + painted bar)`

Preset: Advanced (`softdrink_advanced`). Exactly the disc-i overrides: `scorebug=True`, `scorebug_runtime=True`, `modern_color=True`, `modern_arrowhead=True`, `widescreen=True`. It refuses an existing named disc or patch, checks output-directory access before pruning, removes the oldest MOD TEST images until fewer than three remain, and retains patch archives. It reparses scorebug resources/runtime, colour XBE/all 477 bundles, Arrowhead and 16:9 widescreen from the built disc before exporting the patch. An incomplete disc is removed on failure; a verified disc survives a later patch-export failure. Import the bundle before running externally so the build source is the delivered head.

No disc, patch export or disc read-back was produced here. Output storage is read-only. The prepared name retains the requested 2026-09-15 date even though UTC gate timestamps may fall on the next day.

## Every recorded command result

Order: strict registry/count audit; repin; final manifest projection; fast manifest suites; four detached XBE gates; then pairwise, presentation/colour/APF/provider/catalog/packaging checks and both studios' closures. Each of the four XBE gates used `setsid nohup`, its own log and stdin `/dev/null`; the launching shell waited on child PIDs and logs were polled. No `pkill -f` was used. Every suite ran standalone with Qt offscreen. Independent suites ran concurrently within their phase.

The exact argv arrays and UTC start/end timestamps are in [command-ledger.json](reports/b71_a7/command-ledger.json). Large explicit commit path lists are linked through their receipt instead of duplicated in this table. Read-only discovery and file assembly are also retained in the session tool transcript. Preliminary failures are preserved, never substituted for final receipts.

| Command/log | Exit | Seconds | Exact invocation or argv receipt |
| --- | ---: | ---: | --- |
| [archive-commit](reports/b71_a7/archive-commit.log) | 1 | 0.011 | `git commit -m 'Archive anonymized S4 handoff before integration' -- ASTRA_B71_S4_REPORT.md WIRING_B71_S4.md reports/b71_a7/INHERITED_A6_REPORT.md` |
| [archive-stage](reports/b71_a7/archive-stage.log) | 0 | 0.015 | `git add -- ASTRA_B71_S4_REPORT.md WIRING_B71_S4.md reports/b71_a7/INHERITED_A6_REPORT.md` |
| [archive-commit-final](reports/b71_a7/archive-commit-final.log) | 0 | 2.429 | `git commit -m 'Archive anonymized S4 handoff before integration' -- ASTRA_B71_S4_REPORT.md WIRING_B71_S4.md reports/b71_a7/INHERITED_A6_REPORT.md` |
| [merge-s4](reports/b71_a7/merge-s4.log) | 1 | 0.314 | `git merge --no-commit --no-ff 7b54e354` |
| [hydrate-evidence](reports/b71_a7/hydrate-evidence.log) | 0 | 0.055 | `python3 reports/b71_apf4/hydrate.py` |
| [registry-strict](reports/b71_a7/registry-strict.log) | 0 | 0.207 | `python3 -m mod_editor.capabilities.validate_registry` |
| [validation-plan](reports/b71_a7/validation-plan.log) | 0 | 0.283 | `python3 tools/validate_all_mod_editor_capabilities.py --list` |
| [prepare-test-python](reports/b71_a7/prepare-test-python.log) | 0 | 0.273 | `python3 reports/b71_apf5/prepare_test_python.py` |
| [hydrate-release-tools](reports/b71_a7/hydrate-release-tools.log) | 0 | 0.048 | `python3 reports/b71_apf2/hydrate_tools.py` |
| [pin-audit](reports/b71_a7/pin-audit.log) | 1 | 0.145 | `python3 reports/b71_a7/audit_pins.py` |
| [catalog-preflight](reports/b71_a7/catalog-preflight.log) | 0 | 0.154 | `python3 tests/mod_editor/test_product_catalog.py` |
| [pin-audit-final](reports/b71_a7/pin-audit-final.log) | 0 | 0.685 | `python3 reports/b71_a7/audit_pins.py` |
| [repin](reports/b71_a7/repin.log) | 0 | 10.591 | `python3 packaging/repin.py --apply` |
| [manifest-production](reports/b71_a7/manifest-production.log) | 1 | 0.005 | `bash reports/b71_a7/manifest_regen.sh` |
| [manifest-projection](reports/b71_a7/manifest-projection.log) | 1 | 0.511 | `python3 reports/b71_a7/refresh_manifest_projection.py` |
| [manifest-projection-final](reports/b71_a7/manifest-projection-final.log) | 0 | 327.063 | `python3 reports/b71_a7/refresh_manifest_projection.py` |
| [volume](reports/b71_a7/volume.log) | 0 | 7.316 | `python3 reports/b71_a7/measure_volume.py` |
| [repin-release-label](reports/b71_a7/repin-release-label.log) | 0 | 10.275 | `python3 packaging/repin.py --apply` |
| [manifest-projection-delivery](reports/b71_a7/manifest-projection-delivery.log) | 0 | 324.065 | `python3 reports/b71_a7/refresh_manifest_projection.py` |
| [fast-suites](reports/b71_a7/fast-suites.log) | 0 | 350.267 | `python3 reports/b71_a7/suites.py fast` |
| [final-test_nfl2k5_abilities_v2_manifest](reports/b71_a7/final-test_nfl2k5_abilities_v2_manifest.log) | 0 | 310.942 | `python3 tests/mod_editor/test_nfl2k5_abilities_v2_manifest.py -v` |
| [final-test_nfl2k5_accelerated_clock_manifest](reports/b71_a7/final-test_nfl2k5_accelerated_clock_manifest.log) | 0 | 10.288 | `python3 tests/mod_editor/test_nfl2k5_accelerated_clock_manifest.py -v` |
| [final-test_nfl2k5_cpu_money_downs_manifest](reports/b71_a7/final-test_nfl2k5_cpu_money_downs_manifest.log) | 0 | 4.554 | `python3 tests/mod_editor/test_nfl2k5_cpu_money_downs_manifest.py -v` |
| [merge-checkpoint](reports/b71_a7/merge-checkpoint.log) | 1 | 0.302 | `python3 reports/b71_a7/commit_checkpoint.py merge-s4-commit 'Merge S4 painted bar into A6 with bounded manifest and release wiring'` |
| [merge-s4-commit-stage](reports/b71_a7/merge-s4-commit-stage.log) | 0 | 0.16 | [exact argv](reports/b71_a7/merge-s4-commit-stage.result.json) |
| [final-test_nfl2k5_defensive_try_manifest](reports/b71_a7/final-test_nfl2k5_defensive_try_manifest.log) | 0 | 4.615 | `python3 tests/mod_editor/test_nfl2k5_defensive_try_manifest.py -v` |
| [final-test_nfl2k5_guardian_manifest](reports/b71_a7/final-test_nfl2k5_guardian_manifest.log) | 0 | 313.146 | `python3 tests/mod_editor/test_nfl2k5_guardian_manifest.py -v` |
| [final-test_nfl2k5_music_playlist_manifest](reports/b71_a7/final-test_nfl2k5_music_playlist_manifest.log) | 0 | 3.794 | `python3 tests/mod_editor/test_nfl2k5_music_playlist_manifest.py -v` |
| [final-test_nfl2k5_my_career_manifest](reports/b71_a7/final-test_nfl2k5_my_career_manifest.log) | 0 | 8.162 | `python3 tests/mod_editor/test_nfl2k5_my_career_manifest.py -v` |
| [merge-checkpoint-final](reports/b71_a7/merge-checkpoint-final.log) | 0 | 0.215 | `python3 reports/b71_a7/commit_checkpoint.py merge-s4-commit-final 'Merge S4 painted bar into A6 with bounded manifest and release wiring'` |
| [merge-s4-commit-final-stage](reports/b71_a7/merge-s4-commit-final-stage.log) | 0 | 0.083 | [exact argv](reports/b71_a7/merge-s4-commit-final-stage.result.json) |
| [merge-s4-commit-final](reports/b71_a7/merge-s4-commit-final.log) | 0 | 0.06 | [exact argv](reports/b71_a7/merge-s4-commit-final.result.json) |
| [final-test_nfl2k5_playbook_pair_manifest](reports/b71_a7/final-test_nfl2k5_playbook_pair_manifest.log) | 0 | 327.978 | `python3 tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py -v` |
| [frozen-source-check](reports/b71_a7/frozen-source-check.log) | 0 | 0.435 | `python3 -c 'import hashlib,json;from pathlib import Path;d=json.loads(Path(".scratch/a7-product-frozen.json").read_text());assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in d.items());print(len(d),"unchanged product/test/docs paths")'` |
| [final-test_nfl2k5_read_option_diagnostic_manifest](reports/b71_a7/final-test_nfl2k5_read_option_diagnostic_manifest.log) | 0 | 0.427 | `python3 tests/mod_editor/test_nfl2k5_read_option_diagnostic_manifest.py -v` |
| [final-test_nfl2k5_screen_hooks_manifest](reports/b71_a7/final-test_nfl2k5_screen_hooks_manifest.log) | 0 | 4.359 | `python3 tests/mod_editor/test_nfl2k5_screen_hooks_manifest.py -v` |
| [final-test_nfl2k5_seven_on_seven_manifest](reports/b71_a7/final-test_nfl2k5_seven_on_seven_manifest.log) | 0 | 0.8 | `python3 tests/mod_editor/test_nfl2k5_seven_on_seven_manifest.py -v` |
| [detached-gates](reports/b71_a7/detached-gates.log) | 0 | 1862.006 | `bash reports/b71_a7/gates.sh` |
| [final-test_xbe_patch_memory_writes](reports/b71_a7/final-test_xbe_patch_memory_writes.log) | 0 | 1628.902 | `python3 tests/mod_editor/test_xbe_patch_memory_writes.py -v` |
| [final-test_nfl2k5_allocator_scaleout](reports/b71_a7/final-test_nfl2k5_allocator_scaleout.log) | 0 | 897.769 | `python3 tests/mod_editor/test_nfl2k5_allocator_scaleout.py -v` |
| [final-test_xbe_patch_cave_references](reports/b71_a7/final-test_xbe_patch_cave_references.log) | 0 | 1861.965 | `python3 tests/mod_editor/test_xbe_patch_cave_references.py -v` |
| [final-test_nfl2k5_cave_oracle](reports/b71_a7/final-test_nfl2k5_cave_oracle.log) | 0 | 413.169 | `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py -v` |
| [remaining-suites](reports/b71_a7/remaining-suites.log) | 1 | 3109.412 | `bash reports/b71_a7/remaining.sh` |
| [final-test_nfl2k5_owner_pairwise_composition](reports/b71_a7/final-test_nfl2k5_owner_pairwise_composition.log) | 0 | 3082.969 | `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py -v` |
| [closure_units-suites](reports/b71_a7/closure_units-suites.log) | 1 | 9.721 | `python3 reports/b71_a7/suites.py closure_units` |
| [presentation-suites](reports/b71_a7/presentation-suites.log) | 1 | 586.993 | `python3 reports/b71_a7/suites.py presentation` |
| [apf-suites](reports/b71_a7/apf-suites.log) | 1 | 1606.597 | `python3 reports/b71_a7/suites.py apf` |
| [final-colour-all-pins](reports/b71_a7/final-colour-all-pins.log) | 0 | 605.551 | `python3 tools/verify_colour_lighting_pins.py 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --workers 4` |
| [final-test_provider_integrity](reports/b71_a7/final-test_provider_integrity.log) | 1 | 4.295 | `python3 tests/mod_editor/test_provider_integrity.py -v` |
| [final-test_providers](reports/b71_a7/final-test_providers.log) | 0 | 4.381 | `python3 tests/mod_editor/test_providers.py -v` |
| [final-test_product_catalog](reports/b71_a7/final-test_product_catalog.log) | 0 | 0.254 | `python3 tests/mod_editor/test_product_catalog.py -v` |
| [final-test_colour_lighting](reports/b71_a7/final-test_colour_lighting.log) | 0 | 33.405 | `python3 tests/mod_editor/test_colour_lighting.py -v` |
| [final-test_colour_lighting_qt](reports/b71_a7/final-test_colour_lighting_qt.log) | 0 | 3.051 | `python3 tests/mod_editor/test_colour_lighting_qt.py -v` |
| [final-test_nfl2k5_modern_color](reports/b71_a7/final-test_nfl2k5_modern_color.log) | 0 | 7.277 | `python3 tests/mod_editor/test_nfl2k5_modern_color.py -v` |
| [final-test_nfl2k5_scorebar_rim](reports/b71_a7/final-test_nfl2k5_scorebar_rim.log) | 0 | 17.743 | `python3 tests/mod_editor/test_nfl2k5_scorebar_rim.py -v` |
| [final-test_apf2k8_coverage_tuning](reports/b71_a7/final-test_apf2k8_coverage_tuning.log) | 0 | 3.026 | `python3 tests/mod_editor/test_apf2k8_coverage_tuning.py -v` |
| [final-test_apf2k8_playbook_route_writer](reports/b71_a7/final-test_apf2k8_playbook_route_writer.log) | 0 | 0.801 | `python3 tests/mod_editor/test_apf2k8_playbook_route_writer.py -v` |
| [final-test_apf_all_crest_slots](reports/b71_a7/final-test_apf_all_crest_slots.log) | 0 | 2.221 | `python3 tests/mod_editor/test_apf_all_crest_slots.py -v` |
| [final-test_apf_audio_annotation_facade](reports/b71_a7/final-test_apf_audio_annotation_facade.log) | 0 | 0.768 | `python3 tests/mod_editor/test_apf_audio_annotation_facade.py -v` |
| [final-test_phase1_packaging](reports/b71_a7/final-test_phase1_packaging.log) | 0 | 2.457 | `python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [final-test_apf_audio_annotations](reports/b71_a7/final-test_apf_audio_annotations.log) | 0 | 0.341 | `python3 tests/mod_editor/test_apf_audio_annotations.py -v` |
| [final-test_apf_audio_batch_export](reports/b71_a7/final-test_apf_audio_batch_export.log) | 0 | 0.233 | `python3 tests/mod_editor/test_apf_audio_batch_export.py -v` |
| [final-test_apf_audio_batch_facade](reports/b71_a7/final-test_apf_audio_batch_facade.log) | 0 | 0.426 | `python3 tests/mod_editor/test_apf_audio_batch_facade.py -v` |
| [final-test_apf_audio_batch_gui](reports/b71_a7/final-test_apf_audio_batch_gui.log) | 0 | 0.888 | `python3 tests/mod_editor/test_apf_audio_batch_gui.py -v` |
| [final-test_apf_audio_decode_cancellation](reports/b71_a7/final-test_apf_audio_decode_cancellation.log) | 0 | 2.044 | `python3 tests/mod_editor/test_apf_audio_decode_cancellation.py -v` |
| [final-test_apf_audio_drop_zone_gui](reports/b71_a7/final-test_apf_audio_drop_zone_gui.log) | 0 | 0.734 | `python3 tests/mod_editor/test_apf_audio_drop_zone_gui.py -v` |
| [final-test_apf_audio_encoder_gui](reports/b71_a7/final-test_apf_audio_encoder_gui.log) | 0 | 0.798 | `python3 tests/mod_editor/test_apf_audio_encoder_gui.py -v` |
| [final-test_b68_a1_audit](reports/b71_a7/final-test_b68_a1_audit.log) | 0 | 6.966 | `python3 tests/mod_editor/test_b68_a1_audit.py -v` |
| [final-test_apf_audio_encoding](reports/b71_a7/final-test_apf_audio_encoding.log) | 0 | 11.948 | `python3 tests/mod_editor/test_apf_audio_encoding.py -v` |
| [final-test_apf_audio_import_idle_barrier](reports/b71_a7/final-test_apf_audio_import_idle_barrier.log) | 0 | 4.781 | `python3 tests/mod_editor/test_apf_audio_import_idle_barrier.py -v` |
| [final-test_apf_audio_pcm_product_backend](reports/b71_a7/final-test_apf_audio_pcm_product_backend.log) | 0 | 1.238 | `python3 tests/mod_editor/test_apf_audio_pcm_product_backend.py -v` |
| [final-test_nfl2k5_scorebar_v3](reports/b71_a7/final-test_nfl2k5_scorebar_v3.log) | 0 | 106.41 | `python3 tests/mod_editor/test_nfl2k5_scorebar_v3.py -v` |
| [final-test_apf_audio_replacement_pack](reports/b71_a7/final-test_apf_audio_replacement_pack.log) | 0 | 0.959 | `python3 tests/mod_editor/test_apf_audio_replacement_pack.py -v` |
| [final-test_apf_audio_waveform_qt](reports/b71_a7/final-test_apf_audio_waveform_qt.log) | 0 | 0.66 | `python3 tests/mod_editor/test_apf_audio_waveform_qt.py -v` |
| [final-test_capability_registry_module_commands](reports/b71_a7/final-test_capability_registry_module_commands.log) | 0 | 0.121 | `python3 tests/mod_editor/test_capability_registry_module_commands.py -v` |
| [final-test_apf_audo_exact_slot](reports/b71_a7/final-test_apf_audo_exact_slot.log) | 0 | 0.253 | `python3 tests/mod_editor/test_apf_audo_exact_slot.py -v` |
| [final-test_apf_audo_product_backend](reports/b71_a7/final-test_apf_audo_product_backend.log) | 0 | 0.314 | `python3 tests/mod_editor/test_apf_audo_product_backend.py -v` |
| [final-test_apf_audo_project](reports/b71_a7/final-test_apf_audo_project.log) | 0 | 0.197 | `python3 tests/mod_editor/test_apf_audo_project.py -v` |
| [final-test_apf_ausb_exact_slot](reports/b71_a7/final-test_apf_ausb_exact_slot.log) | 0 | 13.68 | `python3 tests/mod_editor/test_apf_ausb_exact_slot.py -v` |
| [final-test_apf_ausb_product_backend](reports/b71_a7/final-test_apf_ausb_product_backend.log) | 0 | 0.365 | `python3 tests/mod_editor/test_apf_ausb_product_backend.py -v` |
| [final-test_apf_b661_book_content](reports/b71_a7/final-test_apf_b661_book_content.log) | 0 | 28.881 | `python3 tests/mod_editor/test_apf_b661_book_content.py -v` |
| [final-test_nfl2k5_scorebug_assets](reports/b71_a7/final-test_nfl2k5_scorebug_assets.log) | 0 | 155.939 | `python3 tests/mod_editor/test_nfl2k5_scorebug_assets.py -v` |
| [final-test_apf_b661_ladder](reports/b71_a7/final-test_apf_b661_ladder.log) | 0 | 0.486 | `python3 tests/mod_editor/test_apf_b661_ladder.py -v` |
| [final-test_apf_b66_appearance](reports/b71_a7/final-test_apf_b66_appearance.log) | 0 | 2.904 | `python3 tests/mod_editor/test_apf_b66_appearance.py -v` |
| [final-test_apf_b66_personnel](reports/b71_a7/final-test_apf_b66_personnel.log) | 0 | 5.956 | `python3 tests/mod_editor/test_apf_b66_personnel.py -v` |
| [final-test_apf_b67_books_qt](reports/b71_a7/final-test_apf_b67_books_qt.log) | 0 | 71.483 | `python3 tests/mod_editor/test_apf_b67_books_qt.py -v` |
| [final-test_apf_b67_clone](reports/b71_a7/final-test_apf_b67_clone.log) | 0 | 62.555 | `python3 tests/mod_editor/test_apf_b67_clone.py -v` |
| [final-test_nfl2k5_scorebug_author](reports/b71_a7/final-test_nfl2k5_scorebug_author.log) | 0 | 6.915 | `python3 tests/mod_editor/test_nfl2k5_scorebug_author.py -v` |
| [final-test_apf_b67_defense_model_native](reports/b71_a7/final-test_apf_b67_defense_model_native.log) | 0 | 169.254 | `python3 tests/mod_editor/test_apf_b67_defense_model_native.py -v` |
| [final-test_nfl2k5_scorebug_exact](reports/b71_a7/final-test_nfl2k5_scorebug_exact.log) | 0 | 90.239 | `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` |
| [final-test_nfl2k5_scorebug_fonts](reports/b71_a7/final-test_nfl2k5_scorebug_fonts.log) | 0 | 12.045 | `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` |
| [final-test_apf_b67_model_edges_native](reports/b71_a7/final-test_apf_b67_model_edges_native.log) | 0 | 103.055 | `python3 tests/mod_editor/test_apf_b67_model_edges_native.py -v` |
| [final-test_nfl2k5_scorebug_freeze](reports/b71_a7/final-test_nfl2k5_scorebug_freeze.log) | 0 | 341.684 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` |
| [final-test_apf_b67_model_native](reports/b71_a7/final-test_apf_b67_model_native.log) | 0 | 1304.42 | `python3 tests/mod_editor/test_apf_b67_model_native.py -v` |
| [final-test_apf_b67_static_audit](reports/b71_a7/final-test_apf_b67_static_audit.log) | 0 | 0.157 | `python3 tests/mod_editor/test_apf_b67_static_audit.py -v` |
| [final-test_apf_b67_writers](reports/b71_a7/final-test_apf_b67_writers.log) | 0 | 0.503 | `python3 tests/mod_editor/test_apf_b67_writers.py -v` |
| [final-test_apf_b67_writers_native](reports/b71_a7/final-test_apf_b67_writers_native.log) | 0 | 356.164 | `python3 tests/mod_editor/test_apf_b67_writers_native.py -v` |
| [final-test_nfl2k5_scorebug_freeze_v2](reports/b71_a7/final-test_nfl2k5_scorebug_freeze_v2.log) | 0 | 403.715 | `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze_v2.py -v` |
| [final-test_nfl2k5_scorebug_ingame](reports/b71_a7/final-test_nfl2k5_scorebug_ingame.log) | 0 | 17.956 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame.py -v` |
| [pin-audit-delivery](reports/b71_a7/pin-audit-delivery.log) | 0 | 0.442 | `python3 reports/b71_a7/audit_pins.py` |
| [repin-provider-closure](reports/b71_a7/repin-provider-closure.log) | 0 | 16.221 | `python3 packaging/repin.py --apply` |
| [final-test_nfl2k5_scorebug_ingame_fix](reports/b71_a7/final-test_nfl2k5_scorebug_ingame_fix.log) | 0 | 158.184 | `python3 tests/mod_editor/test_nfl2k5_scorebug_ingame_fix.py -v` |
| [manifest-projection-provider-closure](reports/b71_a7/manifest-projection-provider-closure.log) | 0 | 400.047 | `python3 reports/b71_a7/refresh_manifest_projection.py` |
| [final-test_apf_b67_xenia_patch](reports/b71_a7/final-test_apf_b67_xenia_patch.log) | 0 | 0.411 | `python3 tests/mod_editor/test_apf_b67_xenia_patch.py -v` |
| [final-test_apf_b69_build](reports/b71_a7/final-test_apf_b69_build.log) | 0 | 43.091 | `python3 tests/mod_editor/test_apf_b69_build.py -v` |
| [final-test_nfl2k5_scorebug_mnf](reports/b71_a7/final-test_nfl2k5_scorebug_mnf.log) | 0 | 12.636 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf.py -v` |
| [final-test_nfl2k5_scorebug_mnf_v3](reports/b71_a7/final-test_nfl2k5_scorebug_mnf_v3.log) | 0 | 57.324 | `python3 tests/mod_editor/test_nfl2k5_scorebug_mnf_v3.py -v` |
| [final-test_apf_b69_control_audit](reports/b71_a7/final-test_apf_b69_control_audit.log) | 0 | 0.117 | `python3 tests/mod_editor/test_apf_b69_control_audit.py -v` |
| [final-test_apf_b69_editor_qt](reports/b71_a7/final-test_apf_b69_editor_qt.log) | 0 | 107.42 | `python3 tests/mod_editor/test_apf_b69_editor_qt.py -v` |
| [final-test_apf_b69_formation_calling](reports/b71_a7/final-test_apf_b69_formation_calling.log) | 0 | 0.94 | `python3 tests/mod_editor/test_apf_b69_formation_calling.py -v` |
| [final-test_apf_b69_launch_patches](reports/b71_a7/final-test_apf_b69_launch_patches.log) | 0 | 0.646 | `python3 tests/mod_editor/test_apf_b69_launch_patches.py -v` |
| [final-test_apf_b69_native](reports/b71_a7/final-test_apf_b69_native.log) | 0 | 886.393 | `python3 tests/mod_editor/test_apf_b69_native.py -v` |
| [final-test_nfl2k5_scorebug_native](reports/b71_a7/final-test_nfl2k5_scorebug_native.log) | 0 | 136.249 | `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py -v` |
| [final-test_apf_b69_retirement_native](reports/b71_a7/final-test_apf_b69_retirement_native.log) | 0 | 156.673 | `python3 tests/mod_editor/test_apf_b69_retirement_native.py -v` |
| [final-test_nfl2k5_scorebug_projection](reports/b71_a7/final-test_nfl2k5_scorebug_projection.log) | 0 | 68.688 | `python3 tests/mod_editor/test_nfl2k5_scorebug_projection.py -v` |
| [final-test_nfl2k5_scorebug_resources](reports/b71_a7/final-test_nfl2k5_scorebug_resources.log) | 0 | 227.215 | `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` |
| [final-test_nfl2k5_scorebug_runtime](reports/b71_a7/final-test_nfl2k5_scorebug_runtime.log) | 0 | 138.613 | `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` |
| [final-test_nfl2k5_scorebug_source_art](reports/b71_a7/final-test_nfl2k5_scorebug_source_art.log) | 0 | 0.684 | `python3 tests/mod_editor/test_nfl2k5_scorebug_source_art.py -v` |
| [final-test_nfl2k5_scorebug_template](reports/b71_a7/final-test_nfl2k5_scorebug_template.log) | 0 | 13.663 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template.py -v` |
| [final-test_nfl2k5_scorebug_template_release](reports/b71_a7/final-test_nfl2k5_scorebug_template_release.log) | 0 | 0.606 | `python3 tests/mod_editor/test_nfl2k5_scorebug_template_release.py -v` |
| [final-test_nfl2k5_scorebug_unified_adapter](reports/b71_a7/final-test_nfl2k5_scorebug_unified_adapter.log) | 0 | 0.195 | `python3 tests/mod_editor/test_nfl2k5_scorebug_unified_adapter.py -v` |
| [final-test_nfl2k5_scorebug_v10_ingame](reports/b71_a7/final-test_nfl2k5_scorebug_v10_ingame.log) | 0 | 9.693 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_ingame.py -v` |
| [final-test_nfl2k5_scorebug_v10_projection](reports/b71_a7/final-test_nfl2k5_scorebug_v10_projection.log) | 0 | 30.351 | `python3 tests/mod_editor/test_nfl2k5_scorebug_v10_projection.py -v` |
| [final-test_nfl2k5_scorebug_versions](reports/b71_a7/final-test_nfl2k5_scorebug_versions.log) | 0 | 11.235 | `python3 tests/mod_editor/test_nfl2k5_scorebug_versions.py -v` |
| [final-test_apf_b69_schemes](reports/b71_a7/final-test_apf_b69_schemes.log) | 0 | 59.326 | `python3 tests/mod_editor/test_apf_b69_schemes.py -v` |
| [final-test_apf_b69_wiring](reports/b71_a7/final-test_apf_b69_wiring.log) | 0 | 0.615 | `python3 tests/mod_editor/test_apf_b69_wiring.py -v` |
| [final-test_apf_b70_stock_recipes](reports/b71_a7/final-test_apf_b70_stock_recipes.log) | 0 | 212.165 | `python3 tests/mod_editor/test_apf_b70_stock_recipes.py -v` |
| [final-test_scorebug_studio_panel_qt](reports/b71_a7/final-test_scorebug_studio_panel_qt.log) | 0 | 7.892 | `python3 tests/mod_editor/test_scorebug_studio_panel_qt.py -v` |
| [final-test_unif_color_argb_parse](reports/b71_a7/final-test_unif_color_argb_parse.log) | 0 | 1.111 | `python3 tests/mod_editor/test_unif_color_argb_parse.py -v` |
| [final-test_unif_color_control](reports/b71_a7/final-test_unif_color_control.log) | 0 | 10.278 | `python3 tests/mod_editor/test_unif_color_control.py -v` |
| [final-nfl2k5_scorebug_layout_test](reports/b71_a7/final-nfl2k5_scorebug_layout_test.log) | 0 | 2.278 | `python3 tests/nfl2k5_scorebug_layout_test.py -v` |
| [final-nfl2k5_scorebug_mod_project_test](reports/b71_a7/final-nfl2k5_scorebug_mod_project_test.log) | 0 | 1.883 | `python3 tests/nfl2k5_scorebug_mod_project_test.py -v` |
| [final-nfl_uniform_color_patch_test](reports/b71_a7/final-nfl_uniform_color_patch_test.log) | 2 | 0.093 | `python3 tests/nfl_uniform_color_patch_test.py -v` |
| [final-test_nfl_uniform_colour_records](reports/b71_a7/final-test_nfl_uniform_colour_records.log) | 0 | 3.078 | `python3 tests/test_nfl_uniform_colour_records.py -v` |
| [final-test_nfl2k5_modern_arrowhead](reports/b71_a7/final-test_nfl2k5_modern_arrowhead.log) | 0 | 34.033 | `python3 tests/mod_editor/test_nfl2k5_modern_arrowhead.py -v` |
| [final-test_apf_b71_situation_mask](reports/b71_a7/final-test_apf_b71_situation_mask.log) | 0 | 4.424 | `python3 tests/mod_editor/test_apf_b71_situation_mask.py -v` |
| [final-test_apf_b71_situation_mask_abi](reports/b71_a7/final-test_apf_b71_situation_mask_abi.log) | 0 | 4.432 | `python3 tests/mod_editor/test_apf_b71_situation_mask_abi.py -v` |
| [final-test_b71_a6_composition](reports/b71_a7/final-test_b71_a6_composition.log) | 0 | 0.316 | `python3 tests/mod_editor/test_b71_a6_composition.py -v` |
| [final-test_build_panel_qt](reports/b71_a7/final-test_build_panel_qt.log) | 0 | 3.136 | `python3 tests/mod_editor/test_build_panel_qt.py -v` |
| [final-test_apf_b71_situation_mask_install](reports/b71_a7/final-test_apf_b71_situation_mask_install.log) | 0 | 1.324 | `python3 tests/mod_editor/test_apf_b71_situation_mask_install.py -v` |
| [final-test_mod_build](reports/b71_a7/final-test_mod_build.log) | 0 | 1.963 | `python3 tests/mod_editor/test_mod_build.py -v` |
| [final-test_apf_b71_situation_mask_native](reports/b71_a7/final-test_apf_b71_situation_mask_native.log) | 0 | 364.556 | `python3 tests/mod_editor/test_apf_b71_situation_mask_native.py -v` |
| [final-test_discord_bugs_1](reports/b71_a7/final-test_discord_bugs_1.log) | 0 | 1.583 | `python3 tests/mod_editor/test_discord_bugs_1.py -v` |
| [final-test_nfl2k5_depth_chart_rows](reports/b71_a7/final-test_nfl2k5_depth_chart_rows.log) | 0 | 48.486 | `python3 tests/mod_editor/test_nfl2k5_depth_chart_rows.py -v` |
| [delivery-closure_units-suites](reports/b71_a7/delivery-closure_units-suites.log) | 0 | 14.874 | `python3 reports/b71_a7/suites.py closure_units delivery-` |
| [delivery-test_provider_integrity](reports/b71_a7/delivery-test_provider_integrity.log) | 0 | 14.822 | `python3 tests/mod_editor/test_provider_integrity.py -v` |
| [delivery-test_providers](reports/b71_a7/delivery-test_providers.log) | 0 | 4.686 | `python3 tests/mod_editor/test_providers.py -v` |
| [delivery-test_product_catalog](reports/b71_a7/delivery-test_product_catalog.log) | 0 | 0.175 | `python3 tests/mod_editor/test_product_catalog.py -v` |
| [delivery-test_phase1_packaging](reports/b71_a7/delivery-test_phase1_packaging.log) | 0 | 2.483 | `python3 tests/mod_editor/test_phase1_packaging.py -v` |
| [delivery-test_b68_a1_audit](reports/b71_a7/delivery-test_b68_a1_audit.log) | 0 | 7.13 | `python3 tests/mod_editor/test_b68_a1_audit.py -v` |
| [delivery-test_capability_registry_module_commands](reports/b71_a7/delivery-test_capability_registry_module_commands.log) | 0 | 0.18 | `python3 tests/mod_editor/test_capability_registry_module_commands.py -v` |
| [provider-count-stage](reports/b71_a7/provider-count-stage.log) | 0 | 0.013 | `git add -- tests/mod_editor/test_provider_integrity.py` |
| [provider-count-commit](reports/b71_a7/provider-count-commit.log) | 0 | 0.081 | `git commit -m 'Pin the combined provider closure including the painted atlas dependency' -- tests/mod_editor/test_provider_integrity.py` |
| [delivery-nfl_uniform_color_patch_test](reports/b71_a7/delivery-nfl_uniform_color_patch_test.log) | 0 | 0.066 | `python3 tests/nfl_uniform_color_patch_test.py` |
| [presentation-reconciled](reports/b71_a7/presentation-reconciled.log) | 0 | 0.031 | `python3 reports/b71_a7/reconcile_presentation.py` |
| [final-test_apf_b71_situation_mask_qt](reports/b71_a7/final-test_apf_b71_situation_mask_qt.log) | 0 | 1.886 | `python3 tests/mod_editor/test_apf_b71_situation_mask_qt.py -v` |
| [final-test_apf_b71_situations](reports/b71_a7/final-test_apf_b71_situations.log) | 0 | 4.749 | `python3 tests/mod_editor/test_apf_b71_situations.py -v` |
| [final-test_apf_book_identity_qt](reports/b71_a7/final-test_apf_book_identity_qt.log) | 0 | 0.282 | `python3 tests/mod_editor/test_apf_book_identity_qt.py -v` |
| [final-test_apf_book_unlock](reports/b71_a7/final-test_apf_book_unlock.log) | 0 | 25.609 | `python3 tests/mod_editor/test_apf_book_unlock.py -v` |
| [final-test_apf_book_unlock_retail](reports/b71_a7/final-test_apf_book_unlock_retail.log) | 0 | 0.155 | `python3 tests/mod_editor/test_apf_book_unlock_retail.py -v` |
| [final-test_apf_browser_workspace_handoff](reports/b71_a7/final-test_apf_browser_workspace_handoff.log) | 0 | 0.888 | `python3 tests/mod_editor/test_apf_browser_workspace_handoff.py -v` |
| [final-test_apf_build_ausb_overlays](reports/b71_a7/final-test_apf_build_ausb_overlays.log) | 0 | 0.318 | `python3 tests/mod_editor/test_apf_build_ausb_overlays.py -v` |
| [final-test_apf_build_raw_span_overlays](reports/b71_a7/final-test_apf_build_raw_span_overlays.log) | 0 | 0.33 | `python3 tests/mod_editor/test_apf_build_raw_span_overlays.py -v` |
| [final-test_apf_capability_action_parity](reports/b71_a7/final-test_apf_capability_action_parity.log) | 0 | 0.456 | `python3 tests/mod_editor/test_apf_capability_action_parity.py -v` |
| [final-test_apf_copied_volume_metadata](reports/b71_a7/final-test_apf_copied_volume_metadata.log) | 0 | 0.315 | `python3 tests/mod_editor/test_apf_copied_volume_metadata.py -v` |
| [final-test_apf_coverage_research_tools](reports/b71_a7/final-test_apf_coverage_research_tools.log) | 0 | 0.078 | `python3 tests/mod_editor/test_apf_coverage_research_tools.py -v` |
| [final-test_apf_cpu_audibles](reports/b71_a7/final-test_apf_cpu_audibles.log) | 0 | 3.007 | `python3 tests/mod_editor/test_apf_cpu_audibles.py -v` |
| [final-test_apf_crest_budget_import](reports/b71_a7/final-test_apf_crest_budget_import.log) | 0 | 0.859 | `python3 tests/mod_editor/test_apf_crest_budget_import.py -v` |
| [final-test_apf_crest_fit](reports/b71_a7/final-test_apf_crest_fit.log) | 0 | 28.471 | `python3 tests/mod_editor/test_apf_crest_fit.py -v` |
| [final-test_apf_cross_domain_audio_safety](reports/b71_a7/final-test_apf_cross_domain_audio_safety.log) | 0 | 0.366 | `python3 tests/mod_editor/test_apf_cross_domain_audio_safety.py -v` |
| [final-test_apf_cubemap_face0_preview](reports/b71_a7/final-test_apf_cubemap_face0_preview.log) | 0 | 21.384 | `python3 tests/mod_editor/test_apf_cubemap_face0_preview.py -v` |
| [final-test_apf_custom_team_appearance_gui](reports/b71_a7/final-test_apf_custom_team_appearance_gui.log) | 0 | 0.31 | `python3 tests/mod_editor/test_apf_custom_team_appearance_gui.py -v` |
| [final-test_apf_custom_team_appearance_patch](reports/b71_a7/final-test_apf_custom_team_appearance_patch.log) | 0 | 7.055 | `python3 tests/mod_editor/test_apf_custom_team_appearance_patch.py -v` |
| [final-test_apf_defense_research_identity](reports/b71_a7/final-test_apf_defense_research_identity.log) | 0 | 0.507 | `python3 tests/mod_editor/test_apf_defense_research_identity.py -v` |
| [final-test_apf_defense_research_native](reports/b71_a7/final-test_apf_defense_research_native.log) | 0 | 139.917 | `python3 tests/mod_editor/test_apf_defense_research_native.py -v` |
| [final-test_apf_digital_font](reports/b71_a7/final-test_apf_digital_font.log) | 0 | 0.353 | `python3 tests/mod_editor/test_apf_digital_font.py -v` |
| [final-test_apf_dxn_base_only_namefont](reports/b71_a7/final-test_apf_dxn_base_only_namefont.log) | 0 | 22.024 | `python3 tests/mod_editor/test_apf_dxn_base_only_namefont.py -v` |
| [final-test_apf_dxt5a_general_preview](reports/b71_a7/final-test_apf_dxt5a_general_preview.log) | 0 | 20.753 | `python3 tests/mod_editor/test_apf_dxt5a_general_preview.py -v` |
| [final-test_apf_endzone_dxt5a](reports/b71_a7/final-test_apf_endzone_dxt5a.log) | 0 | 37.91 | `python3 tests/mod_editor/test_apf_endzone_dxt5a.py -v` |
| [final-test_apf_export](reports/b71_a7/final-test_apf_export.log) | 0 | 0.119 | `python3 tests/mod_editor/test_apf_export.py -v` |
| [final-test_apf_external_audio_bank_bundle](reports/b71_a7/final-test_apf_external_audio_bank_bundle.log) | 0 | 0.335 | `python3 tests/mod_editor/test_apf_external_audio_bank_bundle.py -v` |
| [final-test_apf_field_art](reports/b71_a7/final-test_apf_field_art.log) | 0 | 0.178 | `python3 tests/mod_editor/test_apf_field_art.py -v` |
| [final-test_apf_field_art_gui](reports/b71_a7/final-test_apf_field_art_gui.log) | 0 | 0.86 | `python3 tests/mod_editor/test_apf_field_art_gui.py -v` |
| [final-test_apf_field_art_patch](reports/b71_a7/final-test_apf_field_art_patch.log) | 0 | 301.452 | `python3 tests/mod_editor/test_apf_field_art_patch.py -v` |
| [final-test_apf_field_art_stock_label](reports/b71_a7/final-test_apf_field_art_stock_label.log) | 0 | 0.479 | `python3 tests/mod_editor/test_apf_field_art_stock_label.py -v` |
| [final-test_apf_field_extra_roundtrip](reports/b71_a7/final-test_apf_field_extra_roundtrip.log) | 0 | 211.808 | `python3 tests/mod_editor/test_apf_field_extra_roundtrip.py -v` |
| [final-test_apf_field_material_project](reports/b71_a7/final-test_apf_field_material_project.log) | 0 | 0.576 | `python3 tests/mod_editor/test_apf_field_material_project.py -v` |
| [final-test_apf_field_material_writer](reports/b71_a7/final-test_apf_field_material_writer.log) | 0 | 0.335 | `python3 tests/mod_editor/test_apf_field_material_writer.py -v` |
| [final-test_apf_formation_alignment_writer](reports/b71_a7/final-test_apf_formation_alignment_writer.log) | 0 | 0.354 | `python3 tests/mod_editor/test_apf_formation_alignment_writer.py -v` |
| [final-test_apf_fourth_down](reports/b71_a7/final-test_apf_fourth_down.log) | 0 | 0.203 | `python3 tests/mod_editor/test_apf_fourth_down.py -v` |
| [final-test_apf_fourth_down_native](reports/b71_a7/final-test_apf_fourth_down_native.log) | 0 | 104.524 | `python3 tests/mod_editor/test_apf_fourth_down_native.py -v` |
| [final-test_apf_fourth_down_qt](reports/b71_a7/final-test_apf_fourth_down_qt.log) | 0 | 0.201 | `python3 tests/mod_editor/test_apf_fourth_down_qt.py -v` |
| [final-test_apf_full_shell_visual_gate](reports/b71_a7/final-test_apf_full_shell_visual_gate.log) | 0 | 0.047 | `python3 tests/mod_editor/test_apf_full_shell_visual_gate.py -v` |
| [final-test_apf_g12_surfaces](reports/b71_a7/final-test_apf_g12_surfaces.log) | 0 | 0.529 | `python3 tests/mod_editor/test_apf_g12_surfaces.py -v` |
| [final-test_apf_helmet_crest_design_product](reports/b71_a7/final-test_apf_helmet_crest_design_product.log) | 0 | 1.5 | `python3 tests/mod_editor/test_apf_helmet_crest_design_product.py -v` |
| [final-test_apf_helmet_logo_placement](reports/b71_a7/final-test_apf_helmet_logo_placement.log) | 0 | 7.481 | `python3 tests/mod_editor/test_apf_helmet_logo_placement.py -v` |
| [final-test_apf_helmet_logo_regions](reports/b71_a7/final-test_apf_helmet_logo_regions.log) | 0 | 4.169 | `python3 tests/mod_editor/test_apf_helmet_logo_regions.py -v` |
| [final-test_apf_helmet_logo_regions_qt](reports/b71_a7/final-test_apf_helmet_logo_regions_qt.log) | 0 | 1.256 | `python3 tests/mod_editor/test_apf_helmet_logo_regions_qt.py -v` |
| [final-test_apf_import_offers_resize](reports/b71_a7/final-test_apf_import_offers_resize.log) | 0 | 0.653 | `python3 tests/mod_editor/test_apf_import_offers_resize.py -v` |
| [final-test_apf_iso_extraction_is_layout_tolerant](reports/b71_a7/final-test_apf_iso_extraction_is_layout_tolerant.log) | 0 | 0.213 | `python3 tests/mod_editor/test_apf_iso_extraction_is_layout_tolerant.py -v` |
| [final-test_apf_linear_txtr_png](reports/b71_a7/final-test_apf_linear_txtr_png.log) | 0 | 0.062 | `python3 tests/mod_editor/test_apf_linear_txtr_png.py -v` |
| [final-test_apf_logo_patch](reports/b71_a7/final-test_apf_logo_patch.log) | 0 | 13.981 | `python3 tests/mod_editor/test_apf_logo_patch.py -v` |
| [final-test_apf_logo_surface_ownership](reports/b71_a7/final-test_apf_logo_surface_ownership.log) | 0 | 0.091 | `python3 tests/mod_editor/test_apf_logo_surface_ownership.py -v` |
| [final-test_apf_logocache_patch](reports/b71_a7/final-test_apf_logocache_patch.log) | 0 | 44.667 | `python3 tests/mod_editor/test_apf_logocache_patch.py -v` |
| [final-test_apf_mask_preview_alpha](reports/b71_a7/final-test_apf_mask_preview_alpha.log) | 0 | 0.177 | `python3 tests/mod_editor/test_apf_mask_preview_alpha.py -v` |
| [final-test_apf_model_export_gui](reports/b71_a7/final-test_apf_model_export_gui.log) | 0 | 2.727 | `python3 tests/mod_editor/test_apf_model_export_gui.py -v` |
| [final-test_apf_model_import](reports/b71_a7/final-test_apf_model_import.log) | 0 | 54.242 | `python3 tests/mod_editor/test_apf_model_import.py -v` |
| [final-test_apf_number_encode_defaults](reports/b71_a7/final-test_apf_number_encode_defaults.log) | 0 | 2.206 | `python3 tests/mod_editor/test_apf_number_encode_defaults.py -v` |
| [final-test_apf_number_texture_writer](reports/b71_a7/final-test_apf_number_texture_writer.log) | 0 | 279.16 | `python3 tests/mod_editor/test_apf_number_texture_writer.py -v` |
| [final-test_apf_package_map_writer](reports/b71_a7/final-test_apf_package_map_writer.log) | 0 | 1.38 | `python3 tests/mod_editor/test_apf_package_map_writer.py -v` |
| [final-test_apf_pass_fetch_export_qt](reports/b71_a7/final-test_apf_pass_fetch_export_qt.log) | 0 | 0.532 | `python3 tests/mod_editor/test_apf_pass_fetch_export_qt.py -v` |
| [final-test_apf_play_designer](reports/b71_a7/final-test_apf_play_designer.log) | 0 | 14.165 | `python3 tests/mod_editor/test_apf_play_designer.py -v` |
| [final-test_apf_play_designer_project](reports/b71_a7/final-test_apf_play_designer_project.log) | 0 | 0.533 | `python3 tests/mod_editor/test_apf_play_designer_project.py -v` |
| [final-test_apf_play_designer_qt](reports/b71_a7/final-test_apf_play_designer_qt.log) | 0 | 0.375 | `python3 tests/mod_editor/test_apf_play_designer_qt.py -v` |
| [final-test_apf_playbook_route_gui](reports/b71_a7/final-test_apf_playbook_route_gui.log) | 0 | 0.389 | `python3 tests/mod_editor/test_apf_playbook_route_gui.py -v` |
| [final-test_apf_playcall_patch](reports/b71_a7/final-test_apf_playcall_patch.log) | 0 | 2.082 | `python3 tests/mod_editor/test_apf_playcall_patch.py -v` |
| [final-test_apf_playcall_research_native](reports/b71_a7/final-test_apf_playcall_research_native.log) | 0 | 230.559 | `python3 tests/mod_editor/test_apf_playcall_research_native.py -v` |
| [final-test_apf_playcalling_editor_build](reports/b71_a7/final-test_apf_playcalling_editor_build.log) | 0 | 97.637 | `python3 tests/mod_editor/test_apf_playcalling_editor_build.py -v` |
| [final-test_apf_playcalling_editor_facade](reports/b71_a7/final-test_apf_playcalling_editor_facade.log) | 0 | 3.212 | `python3 tests/mod_editor/test_apf_playcalling_editor_facade.py -v` |
| [final-test_apf_playcalling_editor_patches](reports/b71_a7/final-test_apf_playcalling_editor_patches.log) | 0 | 0.556 | `python3 tests/mod_editor/test_apf_playcalling_editor_patches.py -v` |
| [final-test_apf_playcalling_editor_qt](reports/b71_a7/final-test_apf_playcalling_editor_qt.log) | 0 | 8.711 | `python3 tests/mod_editor/test_apf_playcalling_editor_qt.py -v` |
| [final-test_apf_player_position_patch](reports/b71_a7/final-test_apf_player_position_patch.log) | 0 | 7.262 | `python3 tests/mod_editor/test_apf_player_position_patch.py -v` |
| [final-test_apf_player_position_product_backend](reports/b71_a7/final-test_apf_player_position_product_backend.log) | 0 | 21.674 | `python3 tests/mod_editor/test_apf_player_position_product_backend.py -v` |
| [final-test_apf_player_positions](reports/b71_a7/final-test_apf_player_positions.log) | 0 | 0.116 | `python3 tests/mod_editor/test_apf_player_positions.py -v` |
| [final-test_apf_player_rating_patch](reports/b71_a7/final-test_apf_player_rating_patch.log) | 0 | 4.351 | `python3 tests/mod_editor/test_apf_player_rating_patch.py -v` |
| [final-test_apf_player_rating_product_backend](reports/b71_a7/final-test_apf_player_rating_product_backend.log) | 0 | 9.533 | `python3 tests/mod_editor/test_apf_player_rating_product_backend.py -v` |
| [final-test_apf_player_rating_sheet_import](reports/b71_a7/final-test_apf_player_rating_sheet_import.log) | 0 | 15.588 | `python3 tests/mod_editor/test_apf_player_rating_sheet_import.py -v` |
| [final-test_apf_player_ratings](reports/b71_a7/final-test_apf_player_ratings.log) | 0 | 0.852 | `python3 tests/mod_editor/test_apf_player_ratings.py -v` |
| [final-test_apf_product_findings](reports/b71_a7/final-test_apf_product_findings.log) | 0 | 0.177 | `python3 tests/mod_editor/test_apf_product_findings.py -v` |
| [final-test_apf_product_findings_gui](reports/b71_a7/final-test_apf_product_findings_gui.log) | 0 | 0.661 | `python3 tests/mod_editor/test_apf_product_findings_gui.py -v` |
| [final-test_apf_product_validation_wrappers](reports/b71_a7/final-test_apf_product_validation_wrappers.log) | 0 | 0.268 | `python3 tests/mod_editor/test_apf_product_validation_wrappers.py -v` |
| [final-test_apf_project_document_workflow](reports/b71_a7/final-test_apf_project_document_workflow.log) | 0 | 33.574 | `python3 tests/mod_editor/test_apf_project_document_workflow.py -v` |
| [final-test_apf_project_streaming](reports/b71_a7/final-test_apf_project_streaming.log) | 0 | 0.236 | `python3 tests/mod_editor/test_apf_project_streaming.py -v` |
| [final-test_apf_ps3_probes](reports/b71_a7/final-test_apf_ps3_probes.log) | 0 | 1.208 | `python3 tests/mod_editor/test_apf_ps3_probes.py -v` |
| [final-test_apf_ps3_roster_convert](reports/b71_a7/final-test_apf_ps3_roster_convert.log) | 0 | 17.434 | `python3 tests/mod_editor/test_apf_ps3_roster_convert.py -v` |
| [final-test_apf_ps3_roster_import_qt](reports/b71_a7/final-test_apf_ps3_roster_import_qt.log) | 0 | 1.805 | `python3 tests/mod_editor/test_apf_ps3_roster_import_qt.py -v` |
| [final-test_apf_ps3_speed](reports/b71_a7/final-test_apf_ps3_speed.log) | 0 | 4.131 | `python3 tests/mod_editor/test_apf_ps3_speed.py -v` |
| [final-test_apf_ps3_speed_packages](reports/b71_a7/final-test_apf_ps3_speed_packages.log) | 0 | 10.533 | `python3 tests/mod_editor/test_apf_ps3_speed_packages.py -v` |
| [final-test_apf_ps3_texture_bundle](reports/b71_a7/final-test_apf_ps3_texture_bundle.log) | 0 | 30.739 | `python3 tests/mod_editor/test_apf_ps3_texture_bundle.py -v` |
| [final-test_apf_ps3_texture_bundle_qt](reports/b71_a7/final-test_apf_ps3_texture_bundle_qt.log) | 0 | 0.465 | `python3 tests/mod_editor/test_apf_ps3_texture_bundle_qt.py -v` |
| [final-test_apf_public_docs_registry_current](reports/b71_a7/final-test_apf_public_docs_registry_current.log) | 0 | 0.184 | `python3 tests/mod_editor/test_apf_public_docs_registry_current.py -v` |
| [final-test_apf_rating_value_domains](reports/b71_a7/final-test_apf_rating_value_domains.log) | 0 | 0.202 | `python3 tests/mod_editor/test_apf_rating_value_domains.py -v` |
| [final-test_apf_retail_crest_channel_audit](reports/b71_a7/final-test_apf_retail_crest_channel_audit.log) | 0 | 0.053 | `python3 tests/mod_editor/test_apf_retail_crest_channel_audit.py -v` |
| [final-test_apf_roster_appearance_transfer](reports/b71_a7/final-test_apf_roster_appearance_transfer.log) | 0 | 8.873 | `python3 tests/mod_editor/test_apf_roster_appearance_transfer.py -v` |
| [final-test_apf_roster_appearance_transfer_qt](reports/b71_a7/final-test_apf_roster_appearance_transfer_qt.log) | 0 | 5.145 | `python3 tests/mod_editor/test_apf_roster_appearance_transfer_qt.py -v` |
| [final-test_apf_roster_identity](reports/b71_a7/final-test_apf_roster_identity.log) | 0 | 12.148 | `python3 tests/mod_editor/test_apf_roster_identity.py -v` |
| [final-test_apf_roster_identity_gui](reports/b71_a7/final-test_apf_roster_identity_gui.log) | 0 | 1.956 | `python3 tests/mod_editor/test_apf_roster_identity_gui.py -v` |
| [final-test_apf_roster_workspace](reports/b71_a7/final-test_apf_roster_workspace.log) | 0 | 0.157 | `python3 tests/mod_editor/test_apf_roster_workspace.py -v` |
| [final-test_apf_roster_workspace_gui](reports/b71_a7/final-test_apf_roster_workspace_gui.log) | 0 | 0.425 | `python3 tests/mod_editor/test_apf_roster_workspace_gui.py -v` |
| [final-test_apf_save_playbook_assignments_gui](reports/b71_a7/final-test_apf_save_playbook_assignments_gui.log) | 0 | 1.442 | `python3 tests/mod_editor/test_apf_save_playbook_assignments_gui.py -v` |
| [final-test_apf_save_roster_players](reports/b71_a7/final-test_apf_save_roster_players.log) | 0 | 4.801 | `python3 tests/mod_editor/test_apf_save_roster_players.py -v` |
| [final-test_apf_save_roster_players_gui](reports/b71_a7/final-test_apf_save_roster_players_gui.log) | 0 | 0.826 | `python3 tests/mod_editor/test_apf_save_roster_players_gui.py -v` |
| [final-test_apf_scorebug_workspace_qt](reports/b71_a7/final-test_apf_scorebug_workspace_qt.log) | 0 | 0.653 | `python3 tests/mod_editor/test_apf_scorebug_workspace_qt.py -v` |
| [final-test_apf_shell_search_accessibility_qt](reports/b71_a7/final-test_apf_shell_search_accessibility_qt.log) | 0 | 11.569 | `python3 tests/mod_editor/test_apf_shell_search_accessibility_qt.py -v` |
| [final-test_apf_splb_add_multiple_formations](reports/b71_a7/final-test_apf_splb_add_multiple_formations.log) | 0 | 0.626 | `python3 tests/mod_editor/test_apf_splb_add_multiple_formations.py -v` |
| [final-test_apf_splb_formation_personnel](reports/b71_a7/final-test_apf_splb_formation_personnel.log) | 0 | 1.215 | `python3 tests/mod_editor/test_apf_splb_formation_personnel.py -v` |
| [final-test_apf_splb_tag_reassignment](reports/b71_a7/final-test_apf_splb_tag_reassignment.log) | 0 | 2.268 | `python3 tests/mod_editor/test_apf_splb_tag_reassignment.py -v` |
| [final-test_apf_splb_writer](reports/b71_a7/final-test_apf_splb_writer.log) | 0 | 0.384 | `python3 tests/mod_editor/test_apf_splb_writer.py -v` |
| [final-test_apf_stadium_material_findings](reports/b71_a7/final-test_apf_stadium_material_findings.log) | 0 | 0.129 | `python3 tests/mod_editor/test_apf_stadium_material_findings.py -v` |
| [final-test_apf_stadium_model_import](reports/b71_a7/final-test_apf_stadium_model_import.log) | 0 | 0.294 | `python3 tests/mod_editor/test_apf_stadium_model_import.py -v` |
| [final-test_apf_stadium_studio](reports/b71_a7/final-test_apf_stadium_studio.log) | 0 | 0.249 | `python3 tests/mod_editor/test_apf_stadium_studio.py -v` |
| [final-test_apf_stadium_studio_gui](reports/b71_a7/final-test_apf_stadium_studio_gui.log) | 0 | 0.593 | `python3 tests/mod_editor/test_apf_stadium_studio_gui.py -v` |
| [final-test_apf_stadium_texture](reports/b71_a7/final-test_apf_stadium_texture.log) | 0 | 78.317 | `python3 tests/mod_editor/test_apf_stadium_texture.py -v` |
| [final-test_apf_stfs_roster_rehash](reports/b71_a7/final-test_apf_stfs_roster_rehash.log) | 0 | 0.669 | `python3 tests/mod_editor/test_apf_stfs_roster_rehash.py -v` |
| [final-test_apf_studio_audio_gui](reports/b71_a7/final-test_apf_studio_audio_gui.log) | 0 | 1.225 | `python3 tests/mod_editor/test_apf_studio_audio_gui.py -v` |
| [final-test_apf_studio_core](reports/b71_a7/final-test_apf_studio_core.log) | 0 | 0.267 | `python3 tests/mod_editor/test_apf_studio_core.py -v` |
| [final-test_apf_studio_draft_logo](reports/b71_a7/final-test_apf_studio_draft_logo.log) | 0 | 0.553 | `python3 tests/mod_editor/test_apf_studio_draft_logo.py -v` |
| [final-test_apf_studio_inspectors](reports/b71_a7/final-test_apf_studio_inspectors.log) | 0 | 2.494 | `python3 tests/mod_editor/test_apf_studio_inspectors.py -v` |
| [final-test_apf_studio_installer](reports/b71_a7/final-test_apf_studio_installer.log) | 1 | 13.053 | `python3 tests/mod_editor/test_apf_studio_installer.py -v` |
| [final-test_apf_studio_safety](reports/b71_a7/final-test_apf_studio_safety.log) | 0 | 0.468 | `python3 tests/mod_editor/test_apf_studio_safety.py -v` |
| [final-test_apf_studio_text_edit](reports/b71_a7/final-test_apf_studio_text_edit.log) | 0 | 0.547 | `python3 tests/mod_editor/test_apf_studio_text_edit.py -v` |
| [final-test_apf_team_art](reports/b71_a7/final-test_apf_team_art.log) | 0 | 10.826 | `python3 tests/mod_editor/test_apf_team_art.py -v` |
| [final-test_apf_team_art_qt](reports/b71_a7/final-test_apf_team_art_qt.log) | 0 | 0.61 | `python3 tests/mod_editor/test_apf_team_art_qt.py -v` |
| [final-test_apf_team_crest_selection](reports/b71_a7/final-test_apf_team_crest_selection.log) | 0 | 0.706 | `python3 tests/mod_editor/test_apf_team_crest_selection.py -v` |
| [final-test_apf_team_logo_gui](reports/b71_a7/final-test_apf_team_logo_gui.log) | 0 | 2.203 | `python3 tests/mod_editor/test_apf_team_logo_gui.py -v` |
| [final-test_apf_text_sheet_gui](reports/b71_a7/final-test_apf_text_sheet_gui.log) | 0 | 0.587 | `python3 tests/mod_editor/test_apf_text_sheet_gui.py -v` |
| [final-test_apf_textlogo_gui](reports/b71_a7/final-test_apf_textlogo_gui.log) | 0 | 0.871 | `python3 tests/mod_editor/test_apf_textlogo_gui.py -v` |
| [final-test_apf_textlogo_writer](reports/b71_a7/final-test_apf_textlogo_writer.log) | 0 | 61.005 | `python3 tests/mod_editor/test_apf_textlogo_writer.py -v` |
| [final-test_apf_theme_layout_qt](reports/b71_a7/final-test_apf_theme_layout_qt.log) | 0 | 19.386 | `python3 tests/mod_editor/test_apf_theme_layout_qt.py -v` |
| [final-test_apf_uniform_allocation_capacity](reports/b71_a7/final-test_apf_uniform_allocation_capacity.log) | 0 | 1.425 | `python3 tests/mod_editor/test_apf_uniform_allocation_capacity.py -v` |
| [final-test_apf_uniform_equipment_colors](reports/b71_a7/final-test_apf_uniform_equipment_colors.log) | 0 | 7.888 | `python3 tests/mod_editor/test_apf_uniform_equipment_colors.py -v` |
| [final-test_apf_uniform_equipment_colors_gui](reports/b71_a7/final-test_apf_uniform_equipment_colors_gui.log) | 0 | 0.215 | `python3 tests/mod_editor/test_apf_uniform_equipment_colors_gui.py -v` |
| [final-test_apf_uniform_independence](reports/b71_a7/final-test_apf_uniform_independence.log) | 0 | 1.485 | `python3 tests/mod_editor/test_apf_uniform_independence.py -v` |
| [final-test_apf_uniform_inventory_gui](reports/b71_a7/final-test_apf_uniform_inventory_gui.log) | 0 | 2.63 | `python3 tests/mod_editor/test_apf_uniform_inventory_gui.py -v` |
| [final-test_apf_wave_integration](reports/b71_a7/final-test_apf_wave_integration.log) | 0 | 14.656 | `python3 tests/mod_editor/test_apf_wave_integration.py -v` |
| [final-test_apf_wordmark_regions](reports/b71_a7/final-test_apf_wordmark_regions.log) | 0 | 0.182 | `python3 tests/mod_editor/test_apf_wordmark_regions.py -v` |
| [final-test_apf_workspace_recovery](reports/b71_a7/final-test_apf_workspace_recovery.log) | 0 | 70.921 | `python3 tests/mod_editor/test_apf_workspace_recovery.py -v` |
| [final-test_apf_xenia_edge](reports/b71_a7/final-test_apf_xenia_edge.log) | 0 | 0.189 | `python3 tests/mod_editor/test_apf_xenia_edge.py -v` |
| [final-test_apf_xenos_4444_mip_layout](reports/b71_a7/final-test_apf_xenos_4444_mip_layout.log) | 0 | 1.945 | `python3 tests/mod_editor/test_apf_xenos_4444_mip_layout.py -v` |
| [final-test_apf_xenos_4444_png](reports/b71_a7/final-test_apf_xenos_4444_png.log) | 0 | 0.095 | `python3 tests/mod_editor/test_apf_xenos_4444_png.py -v` |
| [final-test_apf_xenos_extra_formats_png](reports/b71_a7/final-test_apf_xenos_extra_formats_png.log) | 0 | 0.094 | `python3 tests/mod_editor/test_apf_xenos_extra_formats_png.py -v` |
| [final-test_apf_xex_image](reports/b71_a7/final-test_apf_xex_image.log) | 0 | 1.118 | `python3 tests/mod_editor/test_apf_xex_image.py -v` |
| [final-test_apf_xex_image_retail](reports/b71_a7/final-test_apf_xex_image_retail.log) | 0 | 76.357 | `python3 tests/mod_editor/test_apf_xex_image_retail.py -v` |
| [final-test_apf_xma1_wizard_gui](reports/b71_a7/final-test_apf_xma1_wizard_gui.log) | 0 | 1.929 | `python3 tests/mod_editor/test_apf_xma1_wizard_gui.py -v` |
| [final-test_b69_a1_playcalling](reports/b71_a7/final-test_b69_a1_playcalling.log) | 0 | 46.952 | `python3 tests/mod_editor/test_b69_a1_playcalling.py -v` |
| [delivery-test_apf_studio_installer](reports/b71_a7/delivery-test_apf_studio_installer.log) | 0 | 14.523 | `env -u PYTHONPATH python3 tests/mod_editor/test_apf_studio_installer.py -v` |
| [apf-reconciled](reports/b71_a7/apf-reconciled.log) | 0 | 0.037 | `python3 reports/b71_a7/reconcile_apf.py` |
| [closures](reports/b71_a7/closures.log) | 0 | 26.373 | `python3 reports/b71_a7/closures.py` |
| [stage-2k5-final](reports/b71_a7/stage-2k5-final.log) | 0 | 0.355 | `python3 packaging/stage_release.py packaging/release-allowlist.txt /home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-2k5` |
| [release-2k5-final](reports/b71_a7/release-2k5-final.log) | 0 | 6.915 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_2k5_mod_studio_release.py /home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-2k5` |
| [runtime-2k5-final](reports/b71_a7/runtime-2k5-final.log) | 0 | 8.381 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-2k5 /home/noah/2k-worktrees/astra-b71-a7/.scratch/test-python/bin/python3 /home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-2k5/packaging/check_2k5_mod_studio_runtime.py` |
| [stage-apf-final](reports/b71_a7/stage-apf-final.log) | 0 | 0.088 | `python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt /home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-apf` |
| [release-apf-final](reports/b71_a7/release-apf-final.log) | 0 | 0.385 | `env PYTHONDONTWRITEBYTECODE=1 python3 packaging/check_apf2k8_mod_studio_release.py /home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-apf` |
| [runtime-apf-final](reports/b71_a7/runtime-apf-final.log) | 0 | 10.125 | `env PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONPATH=/home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-apf /home/noah/2k-worktrees/astra-b71-a7/.scratch/test-python/bin/python3 /home/noah/2k-worktrees/astra-b71-a7/.scratch/a7-release-apf/packaging/check_apf2k8_mod_studio_runtime.py` |
| [final-audit](reports/b71_a7/final-audit.log) | 0 | 0.688 | `python3 reports/b71_a7/final_audit.py` |
| [write-report](reports/b71_a7/write-report.log) | 0 | 0.042 | `python3 reports/b71_a7/write_report.py` |
| [archive-audit](reports/b71_a7/archive-audit.log) | 0 | 0.213 | `python3 /tmp/b71_a7_archive_audit.py` |
| [delivery-scorebug-layout-emulation](reports/b71_a7/delivery-scorebug-layout-emulation.log) | 0 | 1.435 | `env NFL2K5_SCOREBUG_EMULATION_TEST=1 python3 tests/nfl2k5_scorebug_layout_test.py -v` |
| [final-audit-delivery](reports/b71_a7/final-audit-delivery.log) | 0 | 0.683 | `python3 reports/b71_a7/final_audit.py` |
| [cleanup-test-support](reports/b71_a7/cleanup-test-support.log) | 0 | 0.033 | `/usr/bin/python3 -c 'from pathlib import Path;import shutil;root=Path.cwd();paths=[root/".scratch/test-python",root/"reports/b71_a7/__pycache__",root/".scratch/b71-a7-manifest.json",root/".scratch/b71-a7-parent-manifest.json",root/".scratch/a7-product-frozen.json"];[(shutil.rmtree(p) if p.is_dir() else p.unlink()) for p in paths if p.exists()];print("Removed temporary interpreter, duplicate projection files and report bytecode; retained private Git and delivery evidence.")'` |

The initial archive commit needed explicit staging and was retried successfully. The first merge checkpoint stopped because the path audit omitted a conflict resolved back to its exact A6 content; adding the cached conflict paths to the explicit staging list completed the real merge without changing that file. The merge's exit 1 reports the six resolved conflicts. The first pin-audit script matched an unrelated string `.replace` call; restricting that audit to `dataclasses.replace` fixed the audit without changing the builder. The first projection refused three unaccounted S4 source changes; explicit writer observation and documented non-XBE tool classifications corrected the recipe. A successful preliminary projection was repeated after the PNG-catalog correction and final repin to preserve the required delivery order. The initial provider suite measured 288 modules against A6's 287-module pin: S4 adds the painted-atlas assets module. The count was corrected, repinning and the byte-identical manifest projection repeated, and the six closure-unit suites rerun. No product writer or XBE bytes changed in this correction; the running XBE/presentation/APF suites validate the same final product hashes. The extra root uniform-colour safety runner rejected the unittest-only `-v` argument before running; its plain-Python retry passed all six safety cases. The initial presentation and remaining coordinator exits retain these superseded invocation/provider failures; reconciliation requires every successful final individual receipt. The APF installer inherited the workspace `PYTHONPATH`, causing its isolated staged-runtime namespace check to refuse the root package. The A6 documented `env -u PYTHONPATH` command passed all 16 installer cases using the already-prepared private dependency environment; no installer source or assertion changed. The initial APF coordinator result is retained and reconciled against that corrected standalone receipt. The production-launcher failure remains an external read-only-storage limitation.

## Skip boundaries

- `delivery-scorebug-layout-emulation`:
  - test_ball_live_hide_gate_retail_vs_persistent (__main__.ScorebugEmulationTests.test_ball_live_hide_gate_retail_vs_persistent) ... skipped 'base disc image not present'
  - test_placement_mode_shows_one_mark_copy_and_one_frame (__main__.ScorebugEmulationTests.test_placement_mode_shows_one_mark_copy_and_one_frame) ... skipped 'base disc image not present'
  - test_possession_change_timed_show_retail_vs_persistent (__main__.ScorebugEmulationTests.test_possession_change_timed_show_retail_vs_persistent) ... skipped 'base disc image not present'
  - The mockup used to read an intermediate glTF that is not in a release (and gated the ... skipped 'the intermediate glTF research export is not in this tree'
  - test_patch_xbe_recolours_black_fields_and_nops_the_hide_calls (__main__.ScorebugXbePatchTests.test_patch_xbe_recolours_black_fields_and_nops_the_hide_calls) ... skipped 'base disc image not present'
  - test_patch_xbe_refuses_foreign_bytes_at_a_site (__main__.ScorebugXbePatchTests.test_patch_xbe_refuses_foreign_bytes_at_a_site) ... skipped 'base disc image not present'
- `final-test_apf_b661_ladder`:
  - test_retail_bulk_swap_h7a_and_native_picker (__main__.LadderTests.test_retail_bulk_swap_h7a_and_native_picker) ... skipped 'Pinned BASE flat PE absent: /home/noah/.codex-tmp/franchise-2026-08-28/apf.pe'
- `final-test_apf_b67_static_audit`:
  - test_both_pinned_images_and_caller_boundary (__main__.StaticAuditTests.test_both_pinned_images_and_caller_boundary) ... skipped 'Owned pinned image absent: /tmp/astra-coverage-17votk5s/base_reextracted.pe; set APF_RETAIL_PE and APF_RETAIL_TU_PE'
- `final-test_apf_b67_writers_native`:
  - test_curve_patch_native_both_images (__main__.WriterNativeTests.test_curve_patch_native_both_images) ... skipped 'Owned TU flat image absent; set APF_RETAIL_TU_PE'
- `final-test_apf_b69_control_audit`:
  - test_sparse_receipt_matches_pinned_private_image (__main__.AuditTests.test_sparse_receipt_matches_pinned_private_image) ... skipped 'Owned pinned BASE PE absent; set APF_RETAIL_PE'
- `final-test_apf_book_unlock_retail`:
  - setUpClass (__main__.RetailProof) ... skipped 'Set APF_BOOK_RETAIL_INDEX to an existing user-owned input; no retail bytes are bundled'
- `final-test_apf_defense_research_native`:
  - test_tu_function_shapes_and_loader_offset_delta (__main__.DefenseResearchTests.test_tu_function_shapes_and_loader_offset_delta) ... skipped 'Set APF_RETAIL_TU_PE to the pinned reconstructed TU 1.1 flat image'
- `final-test_apf_endzone_dxt5a`:
  - test_supplied_chicago_and_washington_build_and_reparse (__main__.SuppliedPS3Tests.test_supplied_chicago_and_washington_build_and_reparse) ... skipped 'set APF_ENDZONE_SLOW=1 for supplied-pair allocation builds (about 4 minutes)'
- `final-test_apf_field_art_patch`:
  - test_field_pass_text_bc3_edit_and_verify (__main__.FieldArtSlowPracticeTests.test_field_pass_text_bc3_edit_and_verify) ... skipped 'practice-overlay recompress is slow; set APF_FIELD_ART_SLOW=1'
  - test_pc_field_goal_dxt1_edit_and_verify (__main__.FieldArtSlowPracticeTests.test_pc_field_goal_dxt1_edit_and_verify) ... skipped 'practice-overlay recompress is slow; set APF_FIELD_ART_SLOW=1'
- `final-test_apf_splb_tag_reassignment`:
  - test_static_consumer_words_match_the_decompressed_pe (__main__.StaticConsumerPinTests.test_static_consumer_words_match_the_decompressed_pe) ... skipped 'decompressed APF PE is not on this machine'
- `final-test_apf_stfs_roster_rehash`:
  - test_pinned_source_has_no_signature_verification (__main__.LocalXeniaAuditTests.test_pinned_source_has_no_signature_verification) ... skipped 'optional local Xenia source revision d09cae8d is unavailable'
- `final-test_nfl2k5_read_option_diagnostic_manifest`:
  - setUpClass (__main__.OwnershipRevalidationTests) ... skipped 'selected manifest uses a different Build fingerprint; historical diagnostic projection not applicable'
- `final-test_nfl2k5_scorebug_assets`:
  - test_apply_in_place_grows_pack0_and_switches_the_node (__main__.DiscTransactionTests.test_apply_in_place_grows_pack0_and_switches_the_node) ... skipped "disposable disc scratch is not writable: /media/noah/Storage/.b70-fable-assets: [Errno 30] Read-only file system: '/media/noah/Storage/.b70-fable-assets/scorebug-access-f8fab5zx'"
- `final-test_nfl2k5_scorebug_fonts`:
  - test_compact_fonts_follow_each_current_and_cached_score_and_restore_with_null_fallback (__main__.NativeTests.test_compact_fonts_follow_each_current_and_cached_score_and_restore_with_null_fallback) ... skipped 'beta 69 private-font runtime (scoped FONT binding, possession glyph, compact score fonts): beta 70 binds no private FONT and draws the 2026 bar with the native fonts; see test_nfl2k5_scorebug_mnf.py, test_nfl2k5_scorebug_exact.py and test_nfl2k5_scorebug_freeze_v2.py'
  - test_native_glyph_caps_positions_and_uvs_match_measured_sizes (__main__.NativeTests.test_native_glyph_caps_positions_and_uvs_match_measured_sizes) ... skipped 'beta 69 private-font runtime (scoped FONT binding, possession glyph, compact score fonts): beta 70 binds no private FONT and draws the 2026 bar with the native fonts; see test_nfl2k5_scorebug_mnf.py, test_nfl2k5_scorebug_exact.py and test_nfl2k5_scorebug_freeze_v2.py'
  - test_native_setup_binds_only_scoped_roles_and_null_lookup_retains_fallback (__main__.NativeTests.test_native_setup_binds_only_scoped_roles_and_null_lookup_retains_fallback) ... skipped 'beta 69 private-font runtime (scoped FONT binding, possession glyph, compact score fonts): beta 70 binds no private FONT and draws the 2026 bar with the native fonts; see test_nfl2k5_scorebug_mnf.py, test_nfl2k5_scorebug_exact.py and test_nfl2k5_scorebug_freeze_v2.py'
  - test_possession_is_one_scoped_glyph_on_the_correct_side_and_reload_hides_missing_font (__main__.NativeTests.test_possession_is_one_scoped_glyph_on_the_correct_side_and_reload_hides_missing_font) ... skipped 'beta 69 private-font runtime (scoped FONT binding, possession glyph, compact score fonts): beta 70 binds no private FONT and draws the 2026 bar with the native fonts; see test_nfl2k5_scorebug_mnf.py, test_nfl2k5_scorebug_exact.py and test_nfl2k5_scorebug_freeze_v2.py'
  - test_widest_three_digit_scores_clear_the_pill_through_native_flip_phases (__main__.NativeTests.test_widest_three_digit_scores_clear_the_pill_through_native_flip_phases) ... skipped 'beta 69 private-font runtime (scoped FONT binding, possession glyph, compact score fonts): beta 70 binds no private FONT and draws the 2026 bar with the native fonts; see test_nfl2k5_scorebug_mnf.py, test_nfl2k5_scorebug_exact.py and test_nfl2k5_scorebug_freeze_v2.py'
- `final-test_nfl2k5_scorebug_source_art`:
  - test_every_texture_span_is_identical_either_way (__main__.ByteIdentityTests.test_every_texture_span_is_identical_either_way) ... skipped 'score_buga_modern.png is not in this tree'
  - test_the_scene_span_is_identical_either_way (__main__.ByteIdentityTests.test_the_scene_span_is_identical_either_way) ... skipped 'the developer copy of the retail scene is not in this tree'
  - test_the_step_writes_the_expected_resource_bytes (__main__.FullDiscWriteTests.test_the_step_writes_the_expected_resource_bytes) ... skipped 'the developer copies this is compared against are not in this tree'
- `final-test_unif_color_control`:
  - test_no_op_and_wrong_full_pack_fingerprint_are_refused (__main__.RealComposedWriterTests.test_no_op_and_wrong_full_pack_fingerprint_are_refused) ... skipped 'retail 2K5 source XISO not present'
  - test_one_set_emits_exactly_one_eight_byte_provenance_bound_span (__main__.RealComposedWriterTests.test_one_set_emits_exactly_one_eight_byte_provenance_bound_span) ... skipped 'retail 2K5 source XISO not present'

## PROVED / UNWITNESSED and delivery

**PROVED:** exact registry union and count pins; actual appended component bytes; unchanged owner allocation; current manifest source seals and complete forward observation; passing requested offline/native/ABI/composition tests; both product packaging closures; the builder's static name/options/order contract; explicit-path private commits and verified bundle fetch/tree read-back.

**UNWITNESSED:** disc construction/read-back, boot and intro peak memory, coin toss/kickoff, real score/timeout/possession/event transitions, GPU filtering, final combined stadium/lighting appearance, APF played behavior and installations on unexecuted platforms. Historical witnesses do not convert this combined build into a played-game result.

Bundle: `.scratch/astra-b71-a7.bundle`, based on prerequisite `07c544a2`. `.scratch/astra-b71-a7-delivery.json` records the final head/tree, bundle size/hash and independent fetch/connectivity verification, including final delivery command exit codes and times. No retail bytes, hydrated private evidence, disc images or patch archives are bundled. Scratch remains below 200 MB. No push. No xemu.
