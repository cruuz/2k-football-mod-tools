# Beta 69 A2 integration report

Branch: `astra/b69-a2-integrate`, based exactly on `7678df20` (`local/stack-beta-69`). The shared Git metadata is read-only; commits and refs live in `/tmp/astra-b69-a2-git`, with this assigned directory as the working tree. `ASTRA_A2.bundle` is the portable delivery. No push, emulator, display, audio playback, network, full retail-disc build, or release-manifest write was performed.

The stack now contains J1's protected wiring, then J6 (all 3 commits), J9 (both commits), and J7 last (all 26 theme commits). J2 model project wiring and J8 roster/appearance transfer remain integrated. J3/J4/J5 were not merged or awaited. Each incoming job's `ASTRA_REPORT.md` and `WIRING.md` was renamed using `git mv` within its merge to `ASTRA_B69_J<N>_REPORT.md` and `WIRING_B69_J<N>.md`. All 13 current-beta 2K5 changelog bullets and all 12 APF bullets from the input stack/jobs survived.

## Every protected wiring hunk

J1 (`WIRING_B69_J1.md`):

1. `build_panel_qt.py`: added the complete **What this build includes** heading, read-only `buildProjectIncludes` list, placeholder, height bound, chronology/index explanation. The intro now explicitly includes selected Build options and staged model/art/text/audio edits, retains J2 model support, and explains the fixed equipment allocation and chosen-size/colour-loss receipt. No equipment growth switch or preset was introduced.
2. `studio_qt.py`: installed the exact `_refresh_build_includes` method and its three ordinary call sites: the end of `_refresh_edit_state`, immediately after the Build panel is created, and after Build settings restoration. Added `_refresh_build_includes(baseline=True)` at the end of project-load success. Canonical project order and all original edit indices are retained.
3. Replaced the complete `_replace_visual_asset` method from `reports/b69_j1/studio-equipment-method.py.txt`. Structured fit refusals reach the real retry dialog; the accepted scale reuses the same source pixels/scope, and retry submission waits for the first blocking task to drain. Failed/cancelled drafts are cleaned. J2's `_models_project_changed` and `project_changed.connect(...)` survive.
4. Project loading uses `show_errors=False`, retaining inline error delivery. `StudioSession.load_shareable_project` preflights equipment immediately inside the archive `try`, before session mutation; it uses `staged_path`, unknown (`None`) indices, and the existing cleanup `finally`.
5. `nfl2k5_equipment_import.py`: the selected-group compiler receives `fit_asset_id=asset.asset_id`; the complete prospective set of current/incoming equipment consumers is compiled before `replace_batch`, with restoring semantics unchanged. `PACKAGE_LOCAL_SHOE_HELP` aliases `SHOE_ROUTE_HELP`; `CONTEXT_FIRST_RULE` contains the exact HOME/AWAY, clean/dirty, fallback and UNWITNESSED wording.
6. Replaced only `nfl2k5.textures.all_p8` and `nfl2k5.uniforms.all_visual` from the supplied JSON. Zero rows added. Retargeted report evidence to `ASTRA_B69_J1_REPORT.md`; per the A2 brief, normalized both former bash validation commands to `python3 -m tests.mod_editor.test_b69_j1_fit`. J7's later witness sentence is also present. Existing aggregate runtime statuses remain unchanged.
7. Extended `test_b69_j1_wiring.py` so the retry, full indexed list and refusing/cleaning load scenarios execute against the installed production methods, as well as the proposed text. Applied hooks, inline refusal, constants and the model signal are checked.

J6 (`WIRING_B69_J6.md`):

1. Kept the implemented CSV menu, preview, whole-row refusals, one-Undo/Redo transaction and Excel help in the roster page. No additional shell insertion was required.
2. Added exactly one `nfl2k5.rosters.player_csv` registry row, with module-form validation and renamed report evidence. The API description also explicitly names `mod_editor/core/nfl2k5_roster_records.py`, matching the existing API-command identity convention.
3. Updated the existing historic-roster row's GUI reason/default, runtime evidence/scope, source description, selector limits, witness follow-up and evidence. Every preset still has `espn25_rosters=False`; the separate saved Anniversary authoring plan remains separate.
4. `mod_build.build`: invokes `module.require_build_ready()` before `read_resources` in the historic preflight. Replaced the publication comment with the guarded native reload-repair description. Source-image/position checks and backend hold remain intact.
5. No runtime module or allowlist addition was needed: this product allowlist does not enumerate tests. Both new standalone suites and the changed native helpers were verified. Game patch bytes/sites and allocation requests did not change.

J9 (`WIRING_B69_J9.md`):

1. Added the three complete offensive-scheme, spreadsheet and ordinary-formation Never call registry rows. Retargeted the machine-readable row file and actual registry evidence/witness links to `ASTRA_B69_J9_REPORT.md`; all validation commands use `python3 -m tests.mod_editor.<module>` without arguments. Rows are sorted by ID; registry serialization is `json.dumps(obj, indent=2, sort_keys=True) + "\n"`.
2. Extended the real `CAPABILITY_ACTION_BINDINGS` comprehension with `offensive_schemes` and `never_call`, and installed the separate preview/export-only spreadsheet binding and its exact product note. The existing CPU Play Calling handler and real stage/revert/export facade methods serve these cards.
3. Applied the exact master-personnel summary/evidence/native scope and pass-fetch patch GUI reason, constraints and evidence updates. Existing gameplay statuses were retained.
4. APF allowlist: added both new core modules and `docs/mod_editor/apf_b69_schemes.md`. Runtime `PRODUCT_MODULES`: added both modules beside team tendency. `expected_editable`: added offensive schemes and Never call; spreadsheet remains export-only. No J9 payload was added to the 2K5 allowlist.
5. Applied every shared/APF registry/card count pin. The new core modules are outside the unified 2K5 provider closure: its exact 272-module closure and all six provider totals remain unchanged, confirmed by the full integrity test.

J7 (`WIRING_B69_J7.md`):

1. Added `polish_qt.py` and the 2K5 FAQ to the 2K5 allowlist; added `ux_text.py`, `polish_qt.py` and the APF FAQ to the APF allowlist.
2. Retained J1's richer stderr-first `_last_message` with complete cause text and diagnostic filtering. Changed the failed-build prefix to **Could not make the disc copy.** Machine-readable timing records remain diagnostic output.
3. Applied all three exact `build_feedback` messages for changed, unchanged and unmeasured output. Comparison logic and retained-art warnings are unchanged.
4. Appended the exact narrowly scoped prior MyCareer witness sentence and set runtime status to `partial`, preserving the original host/native scope. This describes the previous Fast forward/PAT sequences; J3 still owns its later writer scope, and its new play-calling work is explicitly UNWITNESSED.
5. Appended the exact negative Bears Style 6/shoes10 witness sentence to both relevant runtime scopes and both remaining shoe-help GUI paragraphs. Aggregate status/evidence was retained. APF play-design/play-calling rows were not promoted to a played result.
6. Resolved J7's model-worker conflict with `plain_error(exc)` while retaining J2 model-project logic. Kept both J9's `Path` import and J7's plain-error import in APF Play Calling. Reviewed automatic shell/roster/Build merges and retained all changelog bullets.

## Integration failures corrected

- The new read-only Build includes list was initially connected by `observe_build_choices` as though it were an editable setting. With a source open, refreshing the list emitted `textChanged`, saved Build choices, and recursively refreshed it again. `gameplay_project_ui.py` now observes only editable `QPlainTextEdit` controls. J1's prescribed rendering method remains intact. The new regression proves that summary refreshes publish no setting change and that editable notes still publish one. The full 17-test audio/shell integration suite passes after the fix. The runaway initial suite was interrupted, a bounded traceback excerpt was preserved, and every unfinished suite was restarted; interrupted runs are not counted as passes.
- J6’s supplied API command omitted its module path, so the aggregate command-ownership gate returned no writer identity. Added the actual module path to the API description and an applied registry regression. This exposes the pre-existing validation-argument failure documented in the brief, rather than hiding an integration failure behind it.
- Three equipment archive tests previously left their synthetic target-catalog context before reopening. Since real project loading now compiles restored equipment, those fixture contexts now cover reopening too. The real preflight is not mocked away; all 13 tests pass.
- Legacy audio and cross-project Team Kit fixtures now expose the real cache’s `pack0` attribute, and the music handoff host executes the real new includes-refresh method. The beta-66 panel suite now exercises installed modules instead of replaying obsolete source-text replacements. The teardown test now expects J7’s plain error text and explicitly rejects the removed `OSError:` prefix. Updated the additional shared/product count pins in J1’s beta-68 audit and removed the stale beta-67 label in J8’s guide paragraph, retaining its meaning.
- The historical read-option diagnostic now honors `NFL2K5_CAVE_MANIFEST`, matching the four current XBE gates. Its stale-source and XBE-transport checks remain. With the supplied projection it reports its existing applicability skip: the selected Build fingerprint differs from that diagnostic-era snapshot. This skipped historical test is not counted as native proof; the four current XBE gates supply that evidence.
- `test_b69_a2_wiring.py` also checks the actual historic hold before resource reading/output creation, and actual J9 card actions without a proposed-registry or proposed-binding substitution.

## Numeric pins and hash pins

| File / pin | Stack before | Final |
|---|---:|---:|
| `packaging/check_2k5_mod_studio_runtime.py`: shared registry assertion | 161 | 165 |
| same: summary `registry=` | 161 | 165 |
| same: 2K5 capability assertion | 91 | 92 |
| same: summary `nfl2k5_capabilities=` | 91 | 92 |
| `tests/mod_editor/test_phase1_packaging.py`: shared summary registry | 161 | 165 |
| same: 2K5 summary count | 91 | 92 |
| `packaging/check_apf2k8_mod_studio_runtime.py`: shared registry assertion | 161 | 165 |
| same: APF `for_game` count | 69 | 72 |
| same: card count | 69 | 72 |
| same: unique card count and refusal wording | 69 | 72 |
| `tests/mod_editor/test_apf_studio_installer.py`: asserted shared count | 161 | 165 |
| `tests/mod_editor/test_b68_a1_audit.py`: shared / 2K5 assertions and both summary strings | 161 / 91 | 165 / 92 |
| `tests/mod_editor/test_product_catalog.py`: first ID count and seen-ID count | 91 | 92 |
| same: roster category total/editable | 13 / 13 | 14 / 14 |
| same: global total/editable | 91 / 71 | 92 / 72 |
| same: exact expected ID set | 91 IDs | 92 IDs, adding player CSV |
| APF runtime module total (computed) | 152 | 154 |
| 2K5 release allowlist entries | 822 | 824 |
| APF release allowlist entries | 267 | 273 |
| Unified provider module closure | 272 | 272 (unchanged) |

Shared counts progressed 161 → 162 after J6 → 165 after J9. J1 and J7 add zero rows. All other catalog status/category counts and the six provider closure totals `[272, 10, 8, 9, 8, 9]` remain unchanged. `reports/b69_a2/hash-pins.json` gives every changed SHA pin's full before/after values. Repinning uses `python3 packaging/repin.py --apply`; no hash bypass was introduced. `tools/apf_h7a_optimal` remains mode 0755.

Full changed SHA-256 pins (all verified against both source bytes and `7678df20`):

| Pin holder / source | Before | After |
|---|---|---|
| `mod_editor/core/providers.py` / `mod_editor/core/build_feedback.py` | `56c078f5cecf5a2d37349b15b964a6f5350341db3f55f6808a60fc3b205abf76` | `2bcd6e65809444c593f66edac20a9e0d3fff43bf969da2454b8d088571e71535` |
| `mod_editor/core/providers.py` / `mod_editor/core/mod_build.py` | `f80a5fa664d9a7d3328172bfb069f667b5b464cf621ba8976bc59dff0ca93815` | `d9a8f64d252044acd777456d5747a74e6b8d35ffc30ca80affee771f86150102` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_build_service.py` | `9cc6af709a961ee731a90f329f1012b13d40ca16bbee7b21429f1fb2947213b7` | `8185c350ebd2ebb97160b1709f2f7f960c57c5ea9344bf1b57e4a6c2c662eb50` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_espn25_rosters.py` | `3cfe17df38d5d6d42bf31972848644ed32b7a0462f979b0380ad5c69e384c036` | `f5378d1d490d1e1432716d1879f14aeadc2f4f0878e3658a7761682393d5d82c` |
| `mod_editor/core/providers.py` / `mod_editor/core/nfl2k5_roster_records.py` | `dcbbf5da41d8cae027ec89669a87f70703069fba3753e9ce8848b0e1029b9340` | `60754ad5765832e9b9856c59e4835aa8d10f94fc4daa941c59d243040d459137` |
| `mod_editor/core/providers.py` / `mod_editor/studio/session.py` | `665ab4888cfdf5999eb7aeeb50ef870bfbed759c7d42f945a9fe054404779715` | `a2d52608660eae69c9cf384f2f42248daf73397a49b80ca1f622f24e1082abf0` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/audio_panel_qt.py` | `64ac47e2f3d28c374d4b0b8d44e5eba16b69ce5d70bbbeb6288ddadeb2be10ed` | `dd3529836c4ebdc5ddf344de19edca38191f918ca341248953cb289b56c5e42e` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/gui/studio_qt.py` | `3b81d497bd50523562abae7f66b56be120ac8de959be4158562c6e3b654e4a4c` | `919f494c9be1fa8e0cefa1f552b4950b1bb3d5a34d03f3a156ee6d316afe0393` |
| `packaging/check_2k5_mod_studio_runtime.py` / `mod_editor/studio/session.py` | `665ab4888cfdf5999eb7aeeb50ef870bfbed759c7d42f945a9fe054404779715` | `a2d52608660eae69c9cf384f2f42248daf73397a49b80ca1f622f24e1082abf0` |

## Allocation and manifest boundary

No XBE allocation, REQUEST, reservation span, cave ownership, or game patch instruction changed in A2/J6. J9 adds authored APF book/data operations, not a 2K5 allocation. The release `data/nfl2k5_cave_reservations.json` is byte-identical to `7678df20`.

For the four XBE gates, the following command refreshes only the three changed *existing* manifest source fingerprints (`mod_build.py`, `nfl2k5_espn25_rosters.py`, `nfl2k5_roster_records.py`). Every other field is preserved. This is J6's source-only projection technique, not a new full-disc observation or a release manifest:

```bash
PYTHONPATH=. python3 - <<'PY'
import hashlib, json
from pathlib import Path
manifest = json.loads(Path('data/nfl2k5_cave_reservations.json').read_text())
for relative in manifest['source_sha256']:
    manifest['source_sha256'][relative] = hashlib.sha256(Path(relative).read_bytes()).hexdigest()
Path('/tmp/astra-a2-gate-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
```

Claude must run this exact full manifest command after importing the bundle (and again if the later game-code integration changes its owners):

```bash
mkdir -p '/media/noah/Storage/.b69-a2-manifest'
PYTHONPATH=. python3 tools/nfl2k5_cave_oracle.py manifest \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' \
  --xiso '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso' \
  --work-dir '/media/noah/Storage/.b69-a2-manifest' \
  --json data/nfl2k5_cave_reservations.json
python3 packaging/repin.py --apply
```

Rerun the four XBE gates against that regenerated release manifest. No projection file is included in the product or substituted for the release manifest.

## Verification environment and local inputs

Every standalone suite uses:

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 PYTHONHASHSEED=0 \
  NFL2K5_CAVE_MANIFEST=/tmp/astra-a2-gate-manifest.json \
  APF_RETAIL_INDEX='/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A' \
  APF_RETAIL_PE=/tmp/astra-coverage-17votk5s/base_reextracted.pe \
  python3 tests/mod_editor/<file>.py
```

The matrix is a deliberate superset of import grep: it searches every changed Python module's basename throughout `tests/test_*.py`, including multiline/dynamic imports and source-contract strings; it also includes all changed/new job tests and every explicitly requested regression/gate. Tests run as separate plain-Python processes. The complete selection and final result table are below; skips are not claimed as proof.

This lean worktree initially omitted historical evidence and ignored release inputs. Sixteen catalog files were restored from a local reviewed release stage after exact repository size/SHA checks. The four APF extractor release inputs were restored from the local alpha.69 release; both executable pins and the license pin match. The existing private model-inventory metadata is copied from the local Studio cache after its 55,746,414-byte / `af881421...` source-tool pin check. No game payload was copied into or committed to the repository. All hydrated inputs and the private inventory are excluded from this bundle; `hydration.json` records provenance. Product staging uses only the explicit allowlists, excludes the private inventory, and passes the no-retail/no-undeclared-file gates.

All in-game appearance, play calling, full historic scene loading, and roster/Excel user outcomes remain UNWITNESSED except the narrowly quoted pre-existing reports. Native tests prove their reported bounded machine states, not a played result. The actual historic music-freeze state remains unknown; its build hold is retained.

## Final results and remaining failures

All **379 selected standalone test files completed**: **373 exit-zero**, **6 red**. 23 exit results contain declared skips; the ledger preserves their exact result and final line. No interrupted or timed-out process is counted as a pass. Final results in `reports/b69_a2/tests.json` supersede earlier run receipts; `test-logs.json.gz` contains the complete final logs, keyed by test path.

The six remaining reds are reported without weakening their assertions:

- `tests/mod_editor/test_all_textures_workspace.py` — **FAILED (errors=2)**. Historical registry evidence `docs/research/apf_audio.md` is absent; 2 setup/load errors.
- `tests/mod_editor/test_apf_studio_installer.py` — **FAILED (failures=2)**. The documented machine issue: the isolated installed runtime cannot import `capstone`; 2 failures. CI installs it. The ordinary staged APF runtime check passes with the installed user-site dependency.
- `tests/mod_editor/test_nfl2k5_crib_geometry_writer.py` — **FAILED (errors=2)**. Private fixture `assets/intermediate/nfl2k5/models/4248_0105_phone.gltf` is absent; 2 errors. No retail-derived model was copied into the repository to mask this absence.
- `tests/mod_editor/test_nfl2k5_face_shield_registry.py` — **FAILED (errors=1)**. Historical registry evidence `docs/research/apf_audio.md` is absent; 1 registry-load error.
- `tests/mod_editor/test_no_capability_is_invisible.py` — **FAILED (errors=2)**. Historical registry evidence `docs/research/apf_audio.md` is absent; 2 class setup errors. J7’s own receipt also records this missing-evidence failure.
- `tests/mod_editor/test_validate_all_capabilities.py` — **FAILED (errors=1, skipped=1)**. The documented pre-existing `unreviewed validation module arguments` error; the older `apf2k8.field_art.material_opacity` and `nfl2k5.espn25.scenarios_rosters` commands retain their input-stack arguments. The new J6 command-identity failure was corrected first.

The missing historical evidence paths were already referenced on the input stack; no new missing evidence was introduced by these jobs. The missing private model path and these evidence references are unchanged by A2. This is an input/provenance finding, not a claim that a separate baseline test run succeeded. No unresolved job-code assertion failure was observed. No passing claim is made for the six reds.

Four current XBE gates, all run with the scratch source-fingerprint projection described above:

| Gate | Test summary | Result / final line |
|---|---|---|
| `test_nfl2k5_cave_oracle` | Ran 29 tests in 479.361s | `OK` / `OK` |
| `test_xbe_patch_memory_writes` | Ran 115 tests in 1788.928s | `OK` / `OK` |
| `test_xbe_patch_cave_references` | Ran 127 tests in 1975.799s | `OK` / `OK` |
| `test_nfl2k5_owner_pairwise_composition` | Ran 388 tests in 2414.221s | `OK` / `OK` |

J2’s model project/wiring suites, J8’s rehash and both appearance-transfer suites, every J1/J6/J9/J7 changed/new suite apart from the explicitly reported historical-evidence failure, the applied J1/A2 regressions, catalog/pin/provider/packaging checks, explainable Build and beta-66 panels all completed. Their individual results are recorded below.

The Git-owning Windows-CI fixture is run with `GIT_DIR` and `GIT_WORK_TREE` unset, so its own temporary repositories are isolated from the integration store. Its rerun passed; the earlier failure came from inherited temporary-store variables. Source-code/registry fixes were made before their final reruns.

Additional completed checks and exact commands (the four requested common environment variables are also set for these commands):

```bash
python3 tests/nfl2k5_espn25_in_game.py
python3 tests/nfl2k5_espn25_rosters_native.py
python3 tests/mod_editor/beta69_polish_audit.py /tmp/astra-a2-polish-audit.json.gz
python3 packaging/stage_release.py packaging/release-allowlist.txt /tmp/astra-a2-stage-2k5
python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt /tmp/astra-a2-stage-apf
(cd /tmp/astra-a2-stage-2k5 && PYTHONPATH=. python3 packaging/check_2k5_mod_studio_runtime.py)
(cd /tmp/astra-a2-stage-apf && PYTHONPATH=. python3 packaging/check_apf2k8_mod_studio_runtime.py)
python3 packaging/check_2k5_mod_studio_release.py /tmp/astra-a2-stage-2k5
python3 packaging/check_apf2k8_mod_studio_release.py /tmp/astra-a2-stage-apf
```

The two changed native helper modules exited 0 with no output and are also exercised by their native suites. Both stages were refreshed to match every final allowlisted source byte; `stage-refresh.json` records the last registry refresh. All four direct release/runtime checks exited 0. Their exact final lines:

```text
2K5_MOD_STUDIO_RUNTIME_CLOSURE_PASS product_modules=231 tool_modules=35 registry=165 sections=12 nfl2k5_capabilities=92 reports=16 reviewed_metadata=24 sets=634 visuals=71963 team_kit_sets=634 team_kit_assets_per_set=39 text_banks=716 text_strings=23346 text_editable=20074 text_read_only=3272 roster_numbers=6522 audio=850 audio_editable=850 audio_export_only=0 audio_streaming_banks=17 audio_streaming_ranges=53571 audio_streaming_wav_ranges=53571 audio_default_scope=playable_54421_standalone_then_ranges audio_replacement_pack_v2=selected_mixed audio_replacement_pack_v3=all_standalone_850 audio_replacement_pack_v4=all_standalone_850_mapped audio_pack_preflight=fully_validated_read_only_preview_then_explicit_apply audio_pack_import=validated_preview_token_apply audio_pack_path_lookup=canonical_850 audio_meaning_confidence=1_152_697 audio_annotations=project_metadata_only_searchable_54421 audio_add_all_matching=bounded_256 audio_detail_layout=scrollable_pinned_actions audio_toolbar_layout=two_row_930 audio_preview_lifecycle=selection_source_epoch_owned_process audio_query_lifecycle=applied_token_debounce_guarded audio_shortlist_clear=one_level_ordered_restore audio_source_failure=transactional_old_catalog_restore audio_waveform=explicit_read_only_session_wav audio_media_invalidation=selection_source_content_owned embedded_audio_task=global_action_guarded_until_drain embedded_operation_task=audio_crib_mutually_exclusive_until_drain audio_bundle_modified_range=user_wav crib=498 crib_editable=498 crib_standalone_editable=182 crib_scene_editable=188 crib_geometry=10_meshes_7_scenes_position_only stadium_scenes=477 stadium_textures_editable=23838 stadium_geometry=same_topology_position_only_private playbooks=37 formations=1533 plays=9251 chains=32502 play_nodes=91833 play_slot_refs=101761 play_assignment_route=same_book_stock_copy_only startup=connected texture_master=direct_source_with_native_edit_layer private_inventory=false retail=false generated_stadium=false
APF2K8_MOD_STUDIO_RUNTIME_PASS modules=154 capabilities=72 universal=private_source_not_provided uniforms=private_source_not_provided uniform_inventory=private_source_not_provided audio_query_lifecycle=applied_token_debounce_guarded audio_shortlist_clear=one_level_ordered_restore audio_preview_lifecycle=request_owned_success_failure audio_preview_cancellation=request_owned_process_group_cancel audio_waveform_cancellation=request_owned_process_group_cancel audio_add_all_matching=applied_query_atomic_256 audio_session_teardown=cancel_drain_before_close_source audio_replacement_confirmation=fully_validated_read_only_preview_then_explicit_apply audio_replacement_token=exact_member_result_source_session_project_revision audio_replacement_noop=cancel_unchanged audio_replacement_lifecycle=worker_drained_before_confirmation audio_direct_drop=selected_exact_slot_xma1_or_conformed_audio audio_mutation_lifecycle=submission_to_worker_idle retail_source_required=false
2K5_MOD_STUDIO_RELEASE_PASS files=824 directories=36 bytes=138728590 metadata=24 private_inventory=false retail=false symlinks=false undeclared=false
APF2K8_MOD_STUDIO_RELEASE_PASS files=273 bytes=9670826 metadata=8 install_surface=8 retail_hashes=7 extractor=reviewed private=false retail=false symlinks=false undeclared=false
```

J7’s all-pages suite opened **34 pages, made 216 tab visits at two sizes, and inspected 3,924 controls**, with no dialogs or slot exceptions. The additional full metadata audit found 0 missing-help controls, 0 2K5 clipping candidates, and the same 8 unique APF clipping candidates as J7’s supplied audit (36 snapshot occurrences; their class/text/width/height sets match). They are recorded as candidates, not silently reported as zero. Final audit line: `dialogs [] crashes []`. No live display or emulator was opened.

## Integration commits and bundle

The code commit sequence, before the final report/evidence commit:

```text
89c51e2b Beta 69 A2: apply J1 equipment and Build project wiring with live-method contracts
d3e0b229 Merge beta 69 J6 rosters: preserve changelog, rename handoff, wire CSV and held-build preflight
1da5942e Merge beta 69 J9 play calling: wire schemes, spreadsheet and Never call with canonical capability pins
cae4080d Merge beta 69 J7 polish last: preserve model/roster/playcalling logic and wire shared feedback
3f2c998a Beta 69 A2: keep synthetic equipment catalogs active through integrated load preflight
9870f456 Beta 69 A2: verify applied historic hold and APF capability action bindings
8293f7de Beta 69 A2: exclude read-only Build summaries from project-setting change signals
bebc3745 Beta 69 A2: align legacy panel/load fixtures and audit pins with applied wiring
8c2c306c Beta 69 A2: identify the CSV API writer in registry command ownership
4f9f156e Beta 69 A2: let the historical diagnostic use the selected gate manifest
bf190455 Beta 69 A2: align teardown copy and cross-project fixtures with integrated behavior
```

Bundle creation and verification use the writable store, not shared Git metadata:

```bash
export GIT_DIR=/tmp/astra-b69-a2-git
export GIT_WORK_TREE=/home/noah/2k-worktrees/astra-b69-a2
python3 packaging/repin.py --apply
# Final report/evidence commit uses only explicitly named paths.
git bundle create ASTRA_A2.bundle astra/b69-a2-integrate ^7678df20
git bundle verify ASTRA_A2.bundle
```

The code-only trial bundle independently imported and passed connectivity checks in `/tmp/astra-a2-verify.git`. That verification store can read only the original shared object database as its alternate, never `/tmp/astra-b69-a2-git`; new integration objects must come from the bundle. The final delivery is subjected to the same import, tip/tree comparison and connectivity checks after this report commit. `ASTRA_A2.bundle.verify.txt` records the final tip, SHA-256 and results alongside the bundle. The prerequisites are `7678df20c1fc7677a940f188d51520c7c141cd9b` and its ancestor `922c009d65e35f8195762c31106789bb353fb43c`. `ASTRA_DONE` is written only after successful final verification.

## Every selected test: final line

Each command is `python3 <path>` with the environment above. The exit code, unittest result, test count, elapsed time and source run are also preserved in `reports/b69_a2/tests.json`. “OK (skipped=N)” retains the test’s own limitation. Literal final lines are not replaced with inferred success claims.

| Test file | Exit | Unittest result | Exact last non-empty line |
|---|---:|---|---|
| `tests/mod_editor/test_2k5_audio_operation_integration.py` | 0 | OK | OK |
| `tests/mod_editor/test_2k5_bounded_vclz_palette.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_2k5_build_is_explainable.py` | 0 | OK | OK |
| `tests/mod_editor/test_2k5_bump_retail_probe.py` | 0 | OK | OK |
| `tests/mod_editor/test_2k5_check_my_images.py` | 0 | OK | OK |
| `tests/mod_editor/test_2k5_import_offers_resize.py` | 0 | OK | OK |
| `tests/mod_editor/test_2k5_stale_original_cache.py` | 0 | OK | OK |
| `tests/mod_editor/test_2k5_uniform_equipment_export.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_2k5_vclz_bounded_importers.py` | 0 | OK | OK |
| `tests/mod_editor/test_all_textures_workspace.py` | 1 | FAILED (errors=2) | FAILED (errors=2) |
| `tests/mod_editor/test_animations_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf2k8_playbook_route_writer.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_all_crest_slots.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_annotation_facade.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_annotations.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_batch_facade.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_batch_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_decode_cancellation.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_drop_zone_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_encoder_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_encoding.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_import_idle_barrier.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_pcm_product_backend.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_replacement_pack.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audio_waveform_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audo_product_backend.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_audo_project.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_ausb_product_backend.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b661_book_content.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b67_books_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b67_xenia_patch.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_build.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_control_audit.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_editor_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_formation_calling.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_launch_patches.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_native.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_retirement_native.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_schemes.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_b69_wiring.py` | 0 | OK | Exported play call spreadsheet /tmp/tmphyra3gg8/calls.csv |
| `tests/mod_editor/test_apf_browser_workspace_handoff.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_build_ausb_overlays.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_build_raw_span_overlays.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_capability_action_parity.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_cpu_audibles.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_crest_budget_import.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_cross_domain_audio_safety.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_cubemap_face0_preview.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_custom_team_appearance_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_custom_team_appearance_patch.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_digital_font.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_dxn_base_only_namefont.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_dxt5a_general_preview.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_endzone_dxt5a.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_apf_external_audio_bank_bundle.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_field_art.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_field_art_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_field_art_patch.py` | 0 | OK (skipped=2) | APF_FIELD_ART_PATCH_PASS mode=no_op entry=6 files=0 sha256=d8fb70d2bdb180306f49aa2b268d287b35eb33289c69959a74fd6c7dcac9af26 |
| `tests/mod_editor/test_apf_field_art_stock_label.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_field_material_project.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_g12_surfaces.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_helmet_crest_design_product.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_helmet_logo_placement.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_import_offers_resize.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_logo_patch.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_logo_surface_ownership.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_model_export_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_number_texture_writer.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_package_map_writer.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_pass_fetch_export_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_play_designer_project.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_play_designer_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_playbook_route_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_playcalling_editor_build.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_playcalling_editor_facade.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_playcalling_editor_patches.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_playcalling_editor_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_player_position_product_backend.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_player_rating_patch.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_player_rating_product_backend.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_player_rating_sheet_import.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_product_findings_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_project_document_workflow.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_project_streaming.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_ps3_texture_bundle.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_public_docs_registry_current.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_roster_appearance_transfer.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_roster_appearance_transfer_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_roster_identity.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_roster_identity_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_roster_workspace_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_save_roster_players_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_scorebug_workspace_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_shell_search_accessibility_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_splb_add_multiple_formations.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_splb_formation_personnel.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_splb_tag_reassignment.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_apf_splb_writer.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_stadium_studio.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_stadium_studio_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_stfs_roster_rehash.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_studio_audio_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_studio_core.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_studio_draft_logo.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_studio_inspectors.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_studio_installer.py` | 1 | FAILED (failures=2) | FAILED (failures=2) |
| `tests/mod_editor/test_apf_studio_safety.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_studio_text_edit.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_team_art.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_team_art_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_team_crest_selection.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_team_logo_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_text_sheet_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_textlogo_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_textlogo_writer.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_theme_layout_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_uniform_equipment_colors.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_uniform_equipment_colors_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_uniform_inventory_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_wave_integration.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_workspace_recovery.py` | 0 | OK | OK |
| `tests/mod_editor/test_apf_xma1_wizard_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_audio_annotations.py` | 0 | OK | OK |
| `tests/mod_editor/test_audio_annotations_product.py` | 0 | OK | OK |
| `tests/mod_editor/test_audio_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_audio_replacement_pack.py` | 0 | OK | OK |
| `tests/mod_editor/test_audio_waveform_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_b661_kit_build.py` | 0 | OK | NFL2K5_VISUAL_MOD_BUILD_PASS edits=2 changed=2701 kept_retail=0 sha256=fd59d6db8539da7c1cadb66586635c4064f9eebf0859bdff0cb8bd50077d719f receipt_sha256=afd5dcb2617b43773529aff2d6da70ea57c440727c57b63c760d561d157f33d7 runtime=false |
| `tests/mod_editor/test_b661_workspace_qt.py` | 0 | OK | uniforms_first cached=True max_ui_gap=0.135s |
| `tests/mod_editor/test_b66_coach_digits.py` | 0 | OK | OK |
| `tests/mod_editor/test_b66_coach_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_b68_a1_audit.py` | 0 | OK | OK |
| `tests/mod_editor/test_b68_t1_build.py` | 0 | OK | OK |
| `tests/mod_editor/test_b68_t1_ui.py` | 0 | OK | OK |
| `tests/mod_editor/test_b69_a2_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_b69_j1_build.py` | 0 | OK | Could not make the disc copy. While compiling project edits: Project edit index 0: Equipment / Shoes / team or uniform set SYNTHETIC / texture tset:0:8:0:shoes01: PNG must be exactly 32x32 |
| `tests/mod_editor/test_b69_j1_fit.py` | 0 | OK | OK |
| `tests/mod_editor/test_b69_j1_native.py` | 0 | OK | Native Style 6: order ['HOME', 'AWAY', 'GLOBAL'] clean and mud bind each package; both feet exact; Bears tset:3653:9:4:shoes10 |
| `tests/mod_editor/test_b69_j1_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta45_honesty_freeze.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta61_allocator_integration.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta61_integration.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta62_integration3_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta66_1_adapter_imports.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta66_d1_images.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta66_d1_panels.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta66_helmet_finish_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta66_supersim_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta69_doc_links.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta69_feedback_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta69_string_hygiene.py` | 0 | OK | OK |
| `tests/mod_editor/test_beta69_studios_offscreen.py` | 0 | OK | Opened 34 pages; 216 tab visits at two sizes; checked 3924 controls. No dialogs or slot exceptions. |
| `tests/mod_editor/test_broken_play_annotations.py` | 0 | OK | OK |
| `tests/mod_editor/test_build_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_caller_windows_pins.py` | 0 | OK | OK |
| `tests/mod_editor/test_capability_registry_module_commands.py` | 0 | OK | OK |
| `tests/mod_editor/test_commentary_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_core.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_crib_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_discord_bugs_1.py` | 0 | OK | OK |
| `tests/mod_editor/test_discord_bugs_1_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_discord_bugs_2.py` | 0 | OK | OK |
| `tests/mod_editor/test_discord_bugs_2_research.py` | 0 | OK | OK |
| `tests/mod_editor/test_discord_bugs_2_wiring.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_emulator_launch_polish.py` | 0 | OK | OK |
| `tests/mod_editor/test_facade_external_build.py` | 0 | OK | OK |
| `tests/mod_editor/test_franchise_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_gameplay_patches_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_gui.py` | 0 | OK | OK |
| `tests/mod_editor/test_gui_drop_parity.py` | 0 | OK | OK |
| `tests/mod_editor/test_gui_refusal_wording.py` | 0 | OK | OK |
| `tests/mod_editor/test_hotfix63_digit_budget.py` | 0 | OK | OK |
| `tests/mod_editor/test_image_fit.py` | 0 | OK | OK |
| `tests/mod_editor/test_keyboard_search_polish.py` | 0 | OK | OK |
| `tests/mod_editor/test_local_windows_ci.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_mod_build.py` | 0 | OK | OK |
| `tests/mod_editor/test_mod_build_beta62_integration.py` | 0 | OK | OK |
| `tests/mod_editor/test_mod_build_beta62_integration3.py` | 0 | OK | OK |
| `tests/mod_editor/test_mod_build_performance.py` | 0 | OK | OK |
| `tests/mod_editor/test_model_import_disable_reason.py` | 0 | OK | OK |
| `tests/mod_editor/test_models_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_models_project_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_models_skeleton_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_modern_naming_panel.py` | 0 | OK | OK |
| `tests/mod_editor/test_modpack_growth_acceptance.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_music_all_modes_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_music_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_music_playlist_project.py` | 0 | OK | OK |
| `tests/mod_editor/test_music_service.py` | 0 | OK | OK |
| `tests/mod_editor/test_music_simple.py` | 0 | OK | OK |
| `tests/mod_editor/test_music_simple_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_music_simple_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_never_silent_gray_boot.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k3_2k4_compatibility_boundary.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_abilities_v2.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_abilities_v2_manifest.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_abilities_v2_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_animation_import_retail.py` | 0 | OK (skipped=2) | Portable C comparison maximum lane difference: 0 |
| `tests/mod_editor/test_nfl2k5_audio_backend_origin.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_audio_catalog.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_audo_fixed_slots.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_b661_transition.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_boot_logo.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_build_service.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_camera_broadcast.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_camera_far.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_career_stats.py` | 0 | OK | } |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_college_check.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_college_check_page_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_college_check_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_create_play_wizard_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_crib_geometry_writer.py` | 1 | FAILED (errors=2) | FAILED (errors=2) |
| `tests/mod_editor/test_nfl2k5_crib_standalone_texture_writer.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_defense_play_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_depth_locks.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_digit_sheet_quality.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_disc_identity.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_draft_start.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_consumers.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_import.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_import_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_retail_roundtrip.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_scope_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_texture_chain.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_equipment_texture_native.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_espn25_exact_lineups.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_espn25_in_game.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_espn25_integration_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_espn25_loading_wait.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_espn25_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_espn25_rosters.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_espn25_rosters_native.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_face_shield_registry.py` | 1 | FAILED (errors=1) | FAILED (errors=1) |
| `tests/mod_editor/test_nfl2k5_franchise_2026.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_franchise_2026_runtime.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_franchise_edit_player.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_franchise_practice.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_franchise_practice_exit.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_franchise_save.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_franchise_schedule_college.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_guardian_cap.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_guardian_manifest.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_guardian_overlay.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_guardian_resources.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_guardian_unicorn.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_helmet_finish.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_hires_pack_retail.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_kick_laces.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_match_coverage_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_model_project.py` | 0 | OK | MODEL_PROJECT_PROOF {"changed_bytes": 328771, "disc_size": 854016, "guarded_resources": 4, "historical_receipt_replay": true, "mode": "skeleton", "project_sha256": "61e3fe2c5c95928c807b31ca2e5e0d80a4b7e0cd798e4084b1fda1bb178c1242", "quick_sha256": "61e3fe2c5c95928c807b31ca2e5e0d80a4b7e0cd798e4084b1fda1bb178c1242", "source_sha256": "3395ecbe02db68835b6dbc14602eba3e3e01d595fe800375534feeee26cdaa56", "witnessed": false} |
| `tests/mod_editor/test_nfl2k5_models.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_music_fresh_rip.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_music_fresh_rip_gui.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_my_career.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_my_career_completion.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_my_career_draft.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_my_career_frontend.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_my_career_generic_build.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_my_career_mode4.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_my_career_panel.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_my_career_settings.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_myplayer_hud.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_play_designer_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_play_intents_build.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_nfl2k5_play_rules_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_playbook_pack.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_playbook_pack_ui.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_playbook_pair.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py` | 0 | OK | Observed 129 XBE transactions and 12458 reservations; no disc built |
| `tests/mod_editor/test_nfl2k5_player_star.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_player_star_draw.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_position_choices.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_practice_squad_screen.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_prospect_names.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_read_option_diagnostic_manifest.py` | 0 | OK (skipped=1) | OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_read_option_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_roster_arena_growth.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_roster_csv.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_roster_reclassify_grown_arena.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_nfl2k5_roster_records.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_roster_storage.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_save_rost.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_scorebug_exact.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_screen_hooks.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_screen_preset_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_season_cap.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_season_cap_saves.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_senior_bowl.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_seven_on_seven.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_stadium_blender_panel.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_stadium_cache.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_stadium_editor_roundtrip.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_stadium_gltf_export.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_stadium_studio.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_streaming_audio_ui.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_team_column.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_team_history.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_team_names_2026.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_text_catalog.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_weekly_prep.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_weekly_prep_unicorn.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl2k5_widescreen_polish.py` | 0 | OK | OK |
| `tests/mod_editor/test_nfl_audio.py` | 0 | OK | OK |
| `tests/mod_editor/test_no_capability_is_invisible.py` | 1 | FAILED (errors=2) | FAILED (errors=2) |
| `tests/mod_editor/test_number_sheet_quality_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_pack_extent_resolver.py` | 0 | OK | OK |
| `tests/mod_editor/test_phase1_packaging.py` | 0 | OK | OK |
| `tests/mod_editor/test_platform_compat_ownership.py` | 0 | OK | OK |
| `tests/mod_editor/test_platform_compat_paths.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_playbooks_link_table_export_ui.py` | 0 | OK | OK |
| `tests/mod_editor/test_playbooks_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_player_assets.py` | 0 | OK | OK |
| `tests/mod_editor/test_presentation_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_product_catalog.py` | 0 | OK | OK |
| `tests/mod_editor/test_product_inspection_panels_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_product_shell_accessibility_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_project_document_workflow.py` | 0 | OK | OK |
| `tests/mod_editor/test_provider_integrity.py` | 0 | OK | OK |
| `tests/mod_editor/test_providers.py` | 0 | OK | OK |
| `tests/mod_editor/test_ps2_lane.py` | 0 | OK | NFL2K5_PS2_SAVE_VERIFY_SELFTEST_PASS decoder=independent ecc=independent accepts=sealed-declared rejects=stale-crc,undeclared-edit,sidecar |
| `tests/mod_editor/test_ps2_save_dialog_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_roster_editor_panel_franchise.py` | 0 | OK | OK |
| `tests/mod_editor/test_roster_editor_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_roster_save_to_disc.py` | 0 | OK | OK |
| `tests/mod_editor/test_roster_save_to_disc_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_rosters_data.py` | 0 | OK | OK |
| `tests/mod_editor/test_rosters_data_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_rosters_reserves_abilities.py` | 0 | OK | OK |
| `tests/mod_editor/test_rosters_reserves_abilities_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_save_roster_import.py` | 0 | OK | OK |
| `tests/mod_editor/test_scorebug_studio_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_security_blockers_remediation.py` | 0 | OK | OK |
| `tests/mod_editor/test_self_update.py` | 0 | OK | OK |
| `tests/mod_editor/test_senior_bowl_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_share_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_sounds_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_stadium_editable_discovery.py` | 0 | OK | OK |
| `tests/mod_editor/test_stadium_viewer.py` | 0 | OK | OK |
| `tests/mod_editor/test_stage_release.py` | 0 | OK | staged 2 files; 0 declared inputs absent |
| `tests/mod_editor/test_startup_performance.py` | 0 | OK | OK |
| `tests/mod_editor/test_studio_facade.py` | 0 | OK | OK |
| `tests/mod_editor/test_studio_inspection.py` | 0 | OK | OK |
| `tests/mod_editor/test_studio_qt_models.py` | 0 | OK | OK |
| `tests/mod_editor/test_studio_session.py` | 0 | OK | OK |
| `tests/mod_editor/test_studio_shell_layout_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_studio_visual_asset_routing.py` | 0 | OK | OK |
| `tests/mod_editor/test_task_delivery.py` | 0 | OK | OK |
| `tests/mod_editor/test_team_kit_bundle.py` | 0 | OK | OK |
| `tests/mod_editor/test_team_kit_product_integration.py` | 0 | OK | OK |
| `tests/mod_editor/test_teamkit_import_wiring.py` | 0 | OK | OK |
| `tests/mod_editor/test_text_rosters_panel.py` | 0 | OK | OK |
| `tests/mod_editor/test_texture_editor.py` | 0 | OK | OK |
| `tests/mod_editor/test_texture_master_facades.py` | 0 | OK | OK |
| `tests/mod_editor/test_throw_tuning_panel_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_unif_color_argb_parse.py` | 0 | OK | OK |
| `tests/mod_editor/test_unif_color_control.py` | 0 | OK (skipped=2) | OK (skipped=2) |
| `tests/mod_editor/test_unified_audio_composition.py` | 0 | OK | OK |
| `tests/mod_editor/test_unified_stadium_texture_composition.py` | 0 | OK | OK |
| `tests/mod_editor/test_uniform_bundle_cross_project.py` | 0 | OK | OK |
| `tests/mod_editor/test_update_check.py` | 0 | OK | OK |
| `tests/mod_editor/test_ux_build_plan_coverage_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_ux_open_disc_hook_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_ux_rosters_words_qt.py` | 0 | OK | OK |
| `tests/mod_editor/test_validate_all_capabilities.py` | 1 | FAILED (errors=1, skipped=1) | FAILED (errors=1, skipped=1) |
| `tests/mod_editor/test_visual_export_and_preview.py` | 0 | OK | OK |
| `tests/mod_editor/test_workspace_recovery.py` | 0 | OK | OK |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | 0 | OK | OK |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | 0 | OK | OK |
| `tests/mod_editor/test_xemu_settings.py` | 0 | OK | OK |
| `tests/test_apf_membership_consumer_census.py` | 0 | OK | OK |
| `tests/test_apf_slot43_xenia_experiment.py` | 0 | OK | OK |
| `tests/test_crash_report.py` | 0 | OK | OK |
| `tests/test_nfl2k5_xemu_saves.py` | 0 | OK (skipped=1) | wrote /tmp/tmp8syqxc15/fixtures3/CATALOGUE.md |
| `tests/test_nfl_away_loader_safe_virtual_xiso_verify.py` | 0 | NO UNITTEST SUMMARY | NFL_AWAY_LOADER_SAFE_VIRTUAL_XISO_TEST_PASS materialized_diagnostic_honest=yes split_overlay=yes unrelated_identity=yes source_tamper_refused=yes stream_hash=yes diff_ledger=yes streamed_tamper_refused=yes parent_symlink_refused=yes canonical_nlink2_staged=yes open_input_interrupt_clean=yes unexpected_hardlink_refused=yes report_image_alias_refused=yes constructor_interrupt_clean=yes copy_interrupt_clean=yes late_root_failure_clean=yes cleanup_errors_reported=yes cleanup_continues=yes primary_error_preserved=yes close_root_swap_refused=yes close_replacement_preserved=yes preview_close_error_reported=yes preview_primary_preserved=yes preview_hardlink_refused=yes preview_replacement_refused=yes preview_directory_swap_refused=yes |
| `tests/test_nfl_player_roster_general_workflow.py` | 0 | OK | OK |
