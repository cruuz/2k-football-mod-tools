# APF wave integration — 2026-09-09

Branch: `local/apf-wave-1`. Product: `0.1.0-alpha.85`. Implementation commit:
`c9d611f1`; validation repairs: `6fbdd56c`. The final report is committed separately.
No push, emulator launch, executable mutation, or retail write was performed.
All new gameplay remains **UNWITNESSED**.

## What landed

- Design Plays / Formations is a real Playbooks tab, with six writer bindings
  and two hidden/deferred capabilities. The actual Build dispatcher compiles
  its atomic plan into every affected MASTER/SPLB resource. Six legacy/profile
  conflicts name both features and fail before output creation.
- Coverage Geometry has the missing controller, numeric project validation,
  source defaults, all shared uses, four knobs, Apply/Revert and Undo. Build
  applies coverage, package maps and routes in that order, preserves the tuned
  pool, and encodes MASTER once. Final shared-use reports reflect route edits.
- Every normal Build reparses final Book Identity after all pack writes and
  verification, before atomic publication. Independent book cloning remains
  the LAST copy finalizer: Book Identity consumes a completed game build and
  publishes another complete folder with an old-to-new ordinal map.
- All three scheme presets stage in normal projects as well as supporting
  their original reviewed copy builder. Existing CPU/audible selectors compile
  first; a preset then owns membership/tags in its recipe records. Receipts
  retain prior selectors, verification and final personnel availability.
  Reverting presets retains earlier selectors.
- CPU Play Calling provides audible preview/staging, the 28-category personnel
  table, and BASE/TU pass-fetch patch export. Existing selected-book edits or
  presets block rebalance. Personnel guards and secondary-mask warnings remain.
  Patch export is authored emulator-only TOML; `status()` is UNWITNESSED.
- PS3 import buttons, dirty state, session refresh, project reload and Revert
  are connected on Team Logo and Field Art. A real project reload exposed a
  missing crest-detail cache copy: both validated PNG layers now survive
  temporary import-directory removal. Build failures identify the crest slot.
- Fifteen registry rows produce 139 total / 52 APF records. APF cards comprise
  31 Editable, 9 Preview, 3 Export, 4 Proof and 5 Research entries. Exact counts,
  editable-ID sets, providers, writer bindings and release markers remain gated.
- APF packaging closes 239 files and 131 runtime modules, recipes, public docs,
  all required native codecs, and the Capstone export dependency. The NFL
  allowlist contains no APF workspaces and needs no additions. The replay is
  development-only and is excluded from the public allowlist.
- Alpha.85 updates the live installer/runtime/version pins, README, getting
  started guide and status document. The required Unreleased changelog covers
  every feature and its offline/UNWITNESSED boundary. Historical releases retain
  their historical alpha.84 strings.

## Decisions and deviations

The four handoffs each proposed tab index 5. Routes now use the actual widget:
existing tabs 0–4 retain their positions, the new tabs occupy 5–8, and Raw Assets
is 9. No tab silently shadows another feature.

The Book Identity handoff explicitly says **not** to insert cloning in the
middle of `ApfBuildService`: sorted filename insertion changes outer ordinals.
Its documented workflow is preserved: finish Studio edits, choose that built
folder in Book Identity, review an independent book, then Build new game folder.
The brief's three presets additionally needed normal-project composition, so a
strict staged recipe provider was implemented without removing the one-shot
review/copy workflow. No independent clone was requested for the wave test build.

The proposed Coverage row had no backend command and a test path rejected by
the registry schema. A receipt CLI was added. New registry evidence uses the
packaged `docs/mod_editor/apf_wave_2026_09_09.md` instead of broken references to
another branch's `ASTRA_REPORT.md`; validation points at the packaged runtime
gate. Standalone retail tests still run separately. Private research/game data
is not made public to satisfy evidence closure.

The old action-parity gate required the word "copied" for every one-shot
output. Copy builders still satisfy it. Patch export has a separate stricter
contract requiring its exact writer, Export action, authored TOML output,
absent replacement method and UNWITNESSED status.

`data/apf2k8/patch_reservations.json` reserves **0x84D0E000..0x84D0EFFF** exclusively
for pass-fetch and splits the old franchise example's broad claim around it.
No private/external franchise recipe was edited. Existing external patches must
honor that reservation before being co-enabled.

Capstone 5.0.7 is pinned in both CI installs and the Windows native wheel list.
The Windows wheel `capstone-5.0.7-py3-none-win_amd64.whl` SHA-256 is
`4ab8bcb7da8f221ff45926ca168ca33e76f7237d06fbf3c10780002faa2670e1`, checked against
[PyPI release metadata](https://pypi.org/pypi/capstone/5.0.7/json). Here Capstone
exists only in Noah's Python user site, which the installer correctly disables.
The test runtime was `/tmp/astra-apf-runtime`, a temporary venv with system
PyQt5/Pillow and a private copy of the installed Capstone 5.0.7 package, native
library and metadata. No dependency was downloaded and no runtime gate was
relaxed. Windows execution remains a separate witness.

## Test harness repairs and evidence limits

The initial sweep had 21 failing files. Tiny pre-existing fixtures without
ROST now mock only final Book Identity, preserving their original span/source/
atomicity assertions. New integration tests independently require a failed
identity reparse to remove staging and prevent publication; real builds reparse
all final identities. GUI fixture labels/stubs now match the real four new tabs.
Three real-preview suites use temporary caches instead of the user's cache.
The SPLB static pin test also accepts the brief's `APF_FLAT_PE` environment input.

Six CLI test files required `--report` and therefore could not run in the
requested no-argument loop. They now run their unchanged assertions using a
temporary receipt by default, retaining explicit report and full-copy modes.

The legacy jersey tools pinned an unavailable older derived catalog hash
`b60783b9c47b57e9b9f545e95f5c17d3c850e263e0d7d453aa6c3be4a0f809e4`.
Before repinning, every field in all 24 existing catalog records was regenerated
and compared exactly against read-only retail: descriptors, nine mip hashes,
transport, IFF structure, controlled fixed-allocation rebuilds and inactive
bytes. Source hashes matched before/after. The validated catalog hash is
`f07e054e50a85a3d8b02523ac2b1b9c062c5b963bbda0d4e726db80057d8b0e3`.
Consumers, validators and the two generated spec references use that exact pin.
Hash checks remain mandatory.

Three old jersey/shoulder tests incorrectly required opaque PNG alpha to survive
in a shader mask whose writer intentionally restores unused retail alpha=0.
They now independently reparse the actual output and require **every texel** in
all nine mips to equal magenta RGB with alpha zero, and compare the complete
reported PNG-to-storage metrics. No writer or tolerance was changed.

`tests/apf_player_shadow_screenshot_test.py` was a two-framebuffer CLI checker,
not a no-argument suite. Its default mode now tests acceptance and rejection of
coverage, difference, opacity and dimensions using explicit fixtures. Calls with
two PNG arguments retain the full original capture checks. This is **checker
unit coverage only**, not a host/game screenshot witness. No real static/animated
captures were provided, and the unrelated native renderer cannot build here
because `src/assets/model_animation.c` and other renderer sources are absent.
No substitute capture is represented as a renderer result.

Legacy tests hard-coded `extracted/All-Pro Football 2K8 (USA)`. A temporary local
symlink made the owned retail directory available read-only. The uniform mip
suite also read the already-present, pinned Xenia texture reference through a
temporary symlink to the main checkout's vendor directory. Neither target was
edited; both temporary links were removed after validation. Original skips for
missing historical private crest/wrap/renderer witnesses remain explicit below;
available retail and flat-PE gates were exercised.

## Gate commands and output tails


**PASS: all 162 APF Python files exited 0.** Original private-witness skips are enumerated below. Both explicitly enabled slow field-art cases ran. Registry, parity, clean release/runtime, desktop, shell, isolated installer, real GUI and both actual facade builds passed.


Environment used for the Python sweep (from this worktree):


```text
export PYTHONPATH=.
export QT_QPA_PLATFORM=offscreen
export APF_RETAIL_INDEX='/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'
export APF_BOOK_RETAIL_INDEX="$APF_RETAIL_INDEX"
export APF_RETAIL_0A="$APF_RETAIL_INDEX"
export APF_2K8_0A="$APF_RETAIL_INDEX"
export APF_BOOK_FLAT_PE=/home/noah/.codex-tmp/franchise-2026-08-28/apf.pe
export APF_FLAT_PE="$APF_BOOK_FLAT_PE"
export APF_BOOK_RAW_SAVE=/home/noah/Downloads/apfe/Roster.ROS
export APF_FIELD_ART_SLOW=1
export PATH=/tmp/astra-apf-runtime/bin:$PATH
for f in tests/mod_editor/test_apf*.py tests/apf_*_test.py; do
    PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 "$f"
done
```

The first complete loop was followed by targeted reruns after each repair and a retail-enabled pass for every initially skipped retail suite. The table records the final successful invocation of each file, with its output tail. Independent reruns used two subprocesses at a time; each command and assertion is unchanged. Full logs and the local orchestration scripts are retained in `/tmp/astra-wave1-validation` and `/tmp/astra_*_reruns.py`.


`python3 mod_editor/capabilities/validate_registry.py`


```text
MOD_CAPABILITY_REGISTRY_VALIDATION_PASS schema=vc_mod_capability_registry/v1 games=3 surfaces=21 capabilities=139
```

`PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_capability_action_parity.py`


```text
...........
----------------------------------------------------------------------
Ran 11 tests in 0.086s

OK
```

Each row below means `PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 <file>` with exit 0.


| File | Final output tail |
| --- | --- |
| `tests/apf_crest_box_patch_test.py` | Ran 7 tests in 0.002s / OK |
| `tests/apf_digital_font_patch_test.py` | APF_DIGITAL_FONT_PATCH_PASS outer=1310 inner=246 mode=no_op entry_sha256=752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d runtime=false / APF_DIGITAL_FONT_PATCH_TEST_PASS read_only=true no_op=true changed=702 copied_volume=false parts=751 runtime=false |
| `tests/apf_eagles_crest_region_mask_test.py` | Ran 10 tests in 0.001s / OK (skipped=5) |
| `tests/apf_gltf_units_test.py` | Ran 11 tests in 1.294s / OK |
| `tests/apf_h7a_no_overlap_test.py` | Ran 4 tests in 21.352s / OK |
| `tests/apf_h7a_optimal_is_bounded_test.py` | Ran 4 tests in 20.498s / OK |
| `tests/apf_helmet_crest_carrier_expand_test.py` | Ran 6 tests in 0.004s / OK (skipped=1) |
| `tests/apf_helmet_crest_carrier_uv_wrap_test.py` | Ran 6 tests in 0.003s / OK (skipped=1) |
| `tests/apf_helmet_crest_guard_band_test.py` | Ran 3 tests in 0.632s / OK |
| `tests/apf_helmet_crest_independent_verify_test.py` | Ran 8 tests in 0.000s / OK (skipped=6) |
| `tests/apf_helmet_crest_mask_fit_test.py` | Ran 3 tests in 0.569s / OK |
| `tests/apf_helmet_crest_wrap_test.py` | Ran 14 tests in 0.142s / OK (skipped=4) |
| `tests/apf_helmet_crest_wrap_v18_test.py` | Ran 2 tests in 0.002s / OK |
| `tests/apf_helmet_dual_lod_shell_material_route_test.py` | Ran 5 tests in 0.086s / OK (skipped=1) |
| `tests/apf_helmet_family_patch_test.py` | APF_HELMET_FAMILY_PATCH_TEST_PASS targets=24 controlled=3 copied_volume=false |
| `tests/apf_helmet_shell_atlas_audit_test.py` | Ran 3 tests in 0.000s / OK |
| `tests/apf_helmet_shell_catalog_verify_test.py` | Ran 5 tests in 4.390s / OK |
| `tests/apf_helmet_shell_literal_test.py` | Ran 6 tests in 46.040s / OK |
| `tests/apf_helmet_shell_material_route_test.py` | Ran 5 tests in 22.255s / OK |
| `tests/apf_helmet_shell_prebuild_static_proof_test.py` | Ran 3 tests in 1.530s / OK |
| `tests/apf_helmet_shell_static_proof_test.py` | Ran 9 tests in 1.813s / OK |
| `tests/apf_helmet_static_visual_calibration_test.py` | Ran 4 tests in 0.680s / OK (skipped=1) |
| `tests/apf_helmet_static_visual_proof_test.py` | Ran 7 tests in 0.311s / OK (skipped=1) |
| `tests/apf_instruction_budget_instrumenter_test.py` | APF_INSTRUCTION_BUDGET_INSTRUMENTER_TEST_PASS positive=1 immediate=2 rejected=5 annotations=2 corruption_rejected=1 |
| `tests/apf_jersey_family_export_test.py` | Ran 7 tests in 5.587s / OK |
| `tests/apf_jersey_family_patch_test.py` | APF_JERSEY_FAMILY_PATCH_ROUNDTRIP_PASS targets=24 controlled=3 copied_volume=false |
| `tests/apf_jersey_family_verify_test.py` | Ran 4 tests in 14.243s / OK |
| `tests/apf_logo_patch_test.py` | APF_LOGO_ROUNDTRIP_PASS entry=36 file=1 copied_volume=false report=/home/noah/2k-worktrees/apf-wave-1/reports/assets/apf_logo_roundtrip.json |
| `tests/apf_logocache_patch_test.py` | APF_LOGOCACHE_ROUNDTRIP_PASS catalog=1 copied_volume=false report=/home/noah/2k-worktrees/apf-wave-1/reports/assets/apf_logocache_roundtrip.json |
| `tests/apf_pants_family_patch_test.py` | APF_PANTS_FAMILY_PATCH_TEST_PASS targets=24 controlled=3 copied_volume=false |
| `tests/apf_player_shadow_screenshot_test.py` | Ran 6 tests in 0.333s / OK |
| `tests/apf_shoulder_family_patch_test.py` | APF_SHOULDER_FAMILY_PATCH_TEST_PASS targets=24 controlled=3 copied_volume=false |
| `tests/apf_texture_patch_test.py` | APF_TEXTURE_ROUNDTRIP_TEST_PASS h7a_vectors=7 noop=exact changed_bc3_blocks=1 unrelated_parts=158 copied_volume=no |
| `tests/apf_uniform_mip_patch_test.py` | APF_UNIFORM_MIP_ROUNDTRIP_PASS levels=9 copied_volume=false report=/home/noah/2k-worktrees/apf-wave-1/reports/assets/apf_uniform_mip_roundtrip.json |
| `tests/apf_writer_path_safety_test.py` | APF_WRITER_PATH_SAFETY_PASS writers=3 cli_cases=18 manifest_swap_cases=3 output_entry_swap_cases=2 fd_swap_cases=1 existing_volume_preserved=true unintended_outputs=0 |
| `tests/apf_xex_shader_interfaces_test.py` | Ran 8 tests in 0.001s / OK |
| `tests/mod_editor/test_apf2k8_coverage_tuning.py` | Ran 9 tests in 1.044s / OK |
| `tests/mod_editor/test_apf2k8_playbook_route_writer.py` | Ran 12 tests in 0.169s / OK |
| `tests/mod_editor/test_apf_all_crest_slots.py` | Ran 15 tests in 0.531s / OK |
| `tests/mod_editor/test_apf_audio_annotation_facade.py` | Ran 4 tests in 0.010s / OK |
| `tests/mod_editor/test_apf_audio_annotations.py` | Ran 11 tests in 0.010s / OK |
| `tests/mod_editor/test_apf_audio_batch_export.py` | Ran 15 tests in 0.026s / OK |
| `tests/mod_editor/test_apf_audio_batch_facade.py` | Ran 3 tests in 0.007s / OK |
| `tests/mod_editor/test_apf_audio_batch_gui.py` | Ran 7 tests in 0.128s / OK |
| `tests/mod_editor/test_apf_audio_decode_cancellation.py` | Ran 7 tests in 1.864s / OK |
| `tests/mod_editor/test_apf_audio_drop_zone_gui.py` | Ran 9 tests in 0.183s / OK |
| `tests/mod_editor/test_apf_audio_encoder_gui.py` | Ran 8 tests in 0.150s / OK |
| `tests/mod_editor/test_apf_audio_encoding.py` | Ran 21 tests in 10.881s / OK |
| `tests/mod_editor/test_apf_audio_import_idle_barrier.py` | Ran 1 test in 0.568s / OK |
| `tests/mod_editor/test_apf_audio_pcm_product_backend.py` | Ran 11 tests in 0.649s / OK |
| `tests/mod_editor/test_apf_audio_replacement_pack.py` | Ran 57 tests in 0.276s / OK |
| `tests/mod_editor/test_apf_audio_waveform_qt.py` | Ran 9 tests in 0.124s / OK |
| `tests/mod_editor/test_apf_audo_exact_slot.py` | Ran 17 tests in 0.109s / OK |
| `tests/mod_editor/test_apf_audo_product_backend.py` | Ran 3 tests in 0.015s / OK |
| `tests/mod_editor/test_apf_audo_project.py` | Ran 3 tests in 0.004s / OK |
| `tests/mod_editor/test_apf_ausb_exact_slot.py` | Ran 10 tests in 11.206s / OK |
| `tests/mod_editor/test_apf_ausb_product_backend.py` | Ran 7 tests in 0.035s / OK |
| `tests/mod_editor/test_apf_book_identity_qt.py` | Ran 3 tests in 0.030s / OK |
| `tests/mod_editor/test_apf_book_unlock.py` | Ran 19 tests in 22.879s / OK |
| `tests/mod_editor/test_apf_book_unlock_retail.py` | Ran 5 tests in 10.311s / OK |
| `tests/mod_editor/test_apf_browser_workspace_handoff.py` | Ran 20 tests in 0.632s / OK |
| `tests/mod_editor/test_apf_build_ausb_overlays.py` | Ran 5 tests in 0.037s / OK |
| `tests/mod_editor/test_apf_build_raw_span_overlays.py` | Ran 7 tests in 0.055s / OK |
| `tests/mod_editor/test_apf_capability_action_parity.py` | Ran 11 tests in 0.077s / OK |
| `tests/mod_editor/test_apf_copied_volume_metadata.py` | Ran 17 tests in 0.126s / OK |
| `tests/mod_editor/test_apf_coverage_research_tools.py` | Ran 7 tests in 0.012s / OK |
| `tests/mod_editor/test_apf_cpu_audibles.py` | Ran 18 tests in 2.805s / OK |
| `tests/mod_editor/test_apf_cross_domain_audio_safety.py` | Ran 4 tests in 0.001s / OK |
| `tests/mod_editor/test_apf_cubemap_face0_preview.py` | Ran 4 tests in 16.233s / OK |
| `tests/mod_editor/test_apf_custom_team_appearance_gui.py` | Ran 5 tests in 0.116s / OK |
| `tests/mod_editor/test_apf_custom_team_appearance_patch.py` | Ran 8 tests in 6.974s / OK |
| `tests/mod_editor/test_apf_digital_font.py` | Ran 14 tests in 0.182s / OK |
| `tests/mod_editor/test_apf_dxn_base_only_namefont.py` | Ran 4 tests in 13.190s / OK |
| `tests/mod_editor/test_apf_dxt5a_general_preview.py` | Ran 3 tests in 22.115s / OK |
| `tests/mod_editor/test_apf_export.py` | Ran 2 tests in 0.005s / OK |
| `tests/mod_editor/test_apf_external_audio_bank_bundle.py` | Ran 8 tests in 0.016s / OK |
| `tests/mod_editor/test_apf_field_art.py` | Ran 6 tests in 0.014s / OK |
| `tests/mod_editor/test_apf_field_art_gui.py` | Ran 17 tests in 0.326s / OK |
| `tests/mod_editor/test_apf_field_art_patch.py` | Ran 26 tests in 1224.198s / OK / APF_FIELD_ART_PATCH_PASS mode=patched entry=6 files=1 sha256=1468ff806c58b3da6e87feed4749c8f826ba0a84c5a6aa82ead763d6dfd0f46d / APF_FIELD_ART_PATCH_PASS mode=no_op entry=6 files=0 sha256=d8fb70d2bdb180306f49aa2b268d287b35eb33289c69959a74fd6c7dcac9af26 / APF_FIELD_ART_PATCH_PASS mode=patched entry=659 files=23 sha256=da3f972af130f21950e63335e518869e57eef5cc6e6bc23b0102e3dc129b8897 / APF_FIELD_ART_PATCH_PASS mode=patched entry=659 files=18 sha256=0d46a60f52ba8ff658859e599332d0e61970c6972c8a7ade85770625a0e65d7f |
| `tests/mod_editor/test_apf_field_art_stock_label.py` | Ran 13 tests in 0.004s / OK |
| `tests/mod_editor/test_apf_field_extra_roundtrip.py` | Ran 5 tests in 237.894s / OK |
| `tests/mod_editor/test_apf_formation_alignment_writer.py` | Ran 44 tests in 0.202s / OK |
| `tests/mod_editor/test_apf_full_shell_visual_gate.py` | Ran 3 tests in 0.000s / OK |
| `tests/mod_editor/test_apf_g12_surfaces.py` | Ran 12 tests in 0.336s / OK |
| `tests/mod_editor/test_apf_helmet_crest_design_product.py` | Ran 13 tests in 1.139s / OK |
| `tests/mod_editor/test_apf_helmet_logo_placement.py` | Ran 15 tests in 6.757s / OK |
| `tests/mod_editor/test_apf_helmet_logo_regions.py` | Ran 12 tests in 4.016s / OK |
| `tests/mod_editor/test_apf_helmet_logo_regions_qt.py` | Ran 2 tests in 1.078s / OK |
| `tests/mod_editor/test_apf_import_offers_resize.py` | Ran 5 tests in 0.503s / OK |
| `tests/mod_editor/test_apf_iso_extraction_is_layout_tolerant.py` | Ran 10 tests in 0.074s / OK |
| `tests/mod_editor/test_apf_linear_txtr_png.py` | Ran 3 tests in 0.000s / OK |
| `tests/mod_editor/test_apf_logo_patch.py` | Ran 18 tests in 135.684s / OK |
| `tests/mod_editor/test_apf_logo_surface_ownership.py` | Ran 4 tests in 0.033s / OK |
| `tests/mod_editor/test_apf_logocache_patch.py` | Ran 14 tests in 117.996s / OK |
| `tests/mod_editor/test_apf_mask_preview_alpha.py` | Ran 7 tests in 0.006s / OK |
| `tests/mod_editor/test_apf_model_export_gui.py` | Ran 5 tests in 2.568s / OK |
| `tests/mod_editor/test_apf_model_import.py` | Ran 6 tests in 55.351s / OK |
| `tests/mod_editor/test_apf_number_texture_writer.py` | Ran 25 tests in 258.177s / OK |
| `tests/mod_editor/test_apf_package_map_writer.py` | Ran 40 tests in 1.080s / OK |
| `tests/mod_editor/test_apf_play_designer.py` | Ran 27 tests in 13.958s / OK |
| `tests/mod_editor/test_apf_play_designer_project.py` | Ran 5 tests in 0.150s / OK |
| `tests/mod_editor/test_apf_play_designer_qt.py` | Ran 5 tests in 0.121s / OK |
| `tests/mod_editor/test_apf_playbook_route_gui.py` | Ran 7 tests in 0.030s / OK |
| `tests/mod_editor/test_apf_playcall_patch.py` | Ran 11 tests in 1.631s / OK |
| `tests/mod_editor/test_apf_player_position_patch.py` | Ran 4 tests in 6.756s / OK |
| `tests/mod_editor/test_apf_player_position_product_backend.py` | Ran 7 tests in 20.601s / OK |
| `tests/mod_editor/test_apf_player_positions.py` | Ran 5 tests in 0.002s / OK |
| `tests/mod_editor/test_apf_player_rating_patch.py` | Ran 12 tests in 3.992s / OK |
| `tests/mod_editor/test_apf_player_rating_product_backend.py` | Ran 5 tests in 8.963s / OK |
| `tests/mod_editor/test_apf_player_rating_sheet_import.py` | Ran 7 tests in 14.557s / OK |
| `tests/mod_editor/test_apf_player_ratings.py` | Ran 11 tests in 0.640s / OK |
| `tests/mod_editor/test_apf_product_findings.py` | Ran 6 tests in 0.008s / OK |
| `tests/mod_editor/test_apf_product_findings_gui.py` | Ran 2 tests in 0.051s / OK |
| `tests/mod_editor/test_apf_product_validation_wrappers.py` | Ran 5 tests in 0.068s / OK |
| `tests/mod_editor/test_apf_project_document_workflow.py` | Ran 13 tests in 4.635s / OK |
| `tests/mod_editor/test_apf_project_streaming.py` | Ran 6 tests in 0.008s / OK |
| `tests/mod_editor/test_apf_ps3_probes.py` | Ran 9 tests in 0.923s / OK |
| `tests/mod_editor/test_apf_ps3_texture_bundle.py` | Ran 28 tests in 24.331s / OK |
| `tests/mod_editor/test_apf_ps3_texture_bundle_qt.py` | Ran 3 tests in 0.114s / OK |
| `tests/mod_editor/test_apf_public_docs_registry_current.py` | Ran 5 tests in 0.108s / OK |
| `tests/mod_editor/test_apf_rating_value_domains.py` | Ran 8 tests in 0.001s / OK |
| `tests/mod_editor/test_apf_retail_crest_channel_audit.py` |  |
| `tests/mod_editor/test_apf_roster_identity.py` | Ran 18 tests in 11.528s / OK |
| `tests/mod_editor/test_apf_roster_identity_gui.py` | Ran 17 tests in 0.270s / OK |
| `tests/mod_editor/test_apf_roster_workspace.py` | Ran 9 tests in 0.035s / OK |
| `tests/mod_editor/test_apf_roster_workspace_gui.py` | Ran 1 test in 0.022s / OK |
| `tests/mod_editor/test_apf_save_playbook_assignments_gui.py` | Ran 8 tests in 0.962s / OK |
| `tests/mod_editor/test_apf_save_roster_players.py` | Ran 7 tests in 4.173s / OK |
| `tests/mod_editor/test_apf_save_roster_players_gui.py` | Ran 4 tests in 0.494s / OK |
| `tests/mod_editor/test_apf_scorebug_workspace_qt.py` | Ran 11 tests in 0.087s / OK |
| `tests/mod_editor/test_apf_shell_search_accessibility_qt.py` | Ran 3 tests in 1.735s / OK |
| `tests/mod_editor/test_apf_splb_add_multiple_formations.py` | Ran 14 tests in 0.300s / OK |
| `tests/mod_editor/test_apf_splb_tag_reassignment.py` | Ran 86 tests in 1.796s / OK |
| `tests/mod_editor/test_apf_splb_writer.py` | Ran 22 tests in 0.190s / OK |
| `tests/mod_editor/test_apf_stadium_material_findings.py` | Ran 6 tests in 0.003s / OK |
| `tests/mod_editor/test_apf_stadium_model_import.py` | Ran 4 tests in 0.136s / OK |
| `tests/mod_editor/test_apf_stadium_studio.py` | Ran 4 tests in 0.010s / OK |
| `tests/mod_editor/test_apf_stadium_studio_gui.py` | Ran 2 tests in 0.075s / OK |
| `tests/mod_editor/test_apf_stadium_texture.py` | Ran 5 tests in 76.793s / OK |
| `tests/mod_editor/test_apf_studio_audio_gui.py` | Ran 32 tests in 0.643s / OK |
| `tests/mod_editor/test_apf_studio_core.py` | Ran 9 tests in 0.018s / OK |
| `tests/mod_editor/test_apf_studio_draft_logo.py` | Ran 7 tests in 0.186s / OK |
| `tests/mod_editor/test_apf_studio_inspectors.py` | Ran 11 tests in 2.162s / OK |
| `tests/mod_editor/test_apf_studio_installer.py` | Ran 16 tests in 12.537s / OK |
| `tests/mod_editor/test_apf_studio_safety.py` | Ran 27 tests in 0.115s / OK |
| `tests/mod_editor/test_apf_studio_text_edit.py` | Ran 7 tests in 0.026s / OK |
| `tests/mod_editor/test_apf_team_crest_selection.py` | Ran 9 tests in 0.111s / OK |
| `tests/mod_editor/test_apf_team_logo_gui.py` | Ran 23 tests in 1.508s / OK |
| `tests/mod_editor/test_apf_text_sheet_gui.py` | Ran 3 tests in 0.068s / OK |
| `tests/mod_editor/test_apf_textlogo_gui.py` | Ran 5 tests in 0.221s / OK |
| `tests/mod_editor/test_apf_textlogo_writer.py` | Ran 8 tests in 64.229s / OK |
| `tests/mod_editor/test_apf_uniform_allocation_capacity.py` | Ran 21 tests in 1.688s / OK |
| `tests/mod_editor/test_apf_uniform_equipment_colors.py` | Ran 7 tests in 7.739s / OK |
| `tests/mod_editor/test_apf_uniform_equipment_colors_gui.py` | Ran 3 tests in 0.037s / OK |
| `tests/mod_editor/test_apf_uniform_independence.py` | Ran 22 tests in 1.261s / OK |
| `tests/mod_editor/test_apf_uniform_inventory_gui.py` | Ran 6 tests in 1.917s / OK |
| `tests/mod_editor/test_apf_wave_integration.py` | Ran 8 tests in 13.756s / OK |
| `tests/mod_editor/test_apf_workspace_recovery.py` | Ran 20 tests in 13.377s / OK |
| `tests/mod_editor/test_apf_xenos_4444_mip_layout.py` | Ran 14 tests in 2.130s / OK |
| `tests/mod_editor/test_apf_xenos_4444_png.py` | Ran 3 tests in 0.007s / OK |
| `tests/mod_editor/test_apf_xenos_extra_formats_png.py` | Ran 6 tests in 0.007s / OK |
| `tests/mod_editor/test_apf_xma1_wizard_gui.py` | Ran 17 tests in 1.313s / OK |


Remaining original skips concern these unavailable private historical inputs; they are not retail-source skips:


- `tests/apf_eagles_crest_region_mask_test.py`: 5 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_crest_carrier_expand_test.py`: 1 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_crest_carrier_uv_wrap_test.py`: 1 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_crest_independent_verify_test.py`: 6 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_crest_wrap_test.py`: 4 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_dual_lod_shell_material_route_test.py`: 1 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_static_visual_calibration_test.py`: 1 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.

- `tests/apf_helmet_static_visual_proof_test.py`: 1 case(s); private Eagles design/shader trace, carrier output/receipt, or exact v9/v17/v18 historical renderer root absent.


The shadow screenshot file ran six checker self-tests, as explained above. It does not claim the absent framebuffer witness.


Fresh release stage was created with `tempfile.mkdtemp`, removed while empty, and passed to the exact CI commands below. It was removed after validation.


`python3 packaging/stage_release.py packaging/apf2k8-release-allowlist.txt /tmp/astra-apf-stage-l_xbbo41 /home/noah/2k-worktrees/apf-wave-1`


```text
staged 239 files; 0 declared inputs absent
```

`python3 packaging/check_apf2k8_mod_studio_release.py /tmp/astra-apf-stage-l_xbbo41`


```text
APF2K8_MOD_STUDIO_RELEASE_PASS files=239 bytes=8979356 metadata=6 install_surface=8 retail_hashes=7 extractor=reviewed private=false retail=false symlinks=false undeclared=false
```

`env -u PYTHONPATH python3 /tmp/astra-apf-stage-l_xbbo41/packaging/check_apf2k8_mod_studio_runtime.py`


```text
APF2K8_MOD_STUDIO_RUNTIME_PASS modules=131 capabilities=52 universal=private_source_not_provided uniforms=private_source_not_provided uniform_inventory=private_source_not_provided audio_query_lifecycle=applied_token_debounce_guarded audio_shortlist_clear=one_level_ordered_restore audio_preview_lifecycle=request_owned_success_failure audio_preview_cancellation=request_owned_process_group_cancel audio_waveform_cancellation=request_owned_process_group_cancel audio_add_all_matching=applied_query_atomic_256 audio_session_teardown=cancel_drain_before_close_source audio_replacement_confirmation=fully_validated_read_only_preview_then_explicit_apply audio_replacement_token=exact_member_result_source_session_project_revision audio_replacement_noop=cancel_unchanged audio_replacement_lifecycle=worker_drained_before_confirmation audio_direct_drop=selected_exact_slot_xma1_or_conformed_audio audio_mutation_lifecycle=submission_to_worker_idle retail_source_required=false
```

`desktop-file-validate /tmp/astra-apf-stage-l_xbbo41/packaging/apf2k8-mod-studio.desktop`


```text
(no output; exit 0)
```

`bash -n /tmp/astra-apf-stage-l_xbbo41/tools/launch_apf2k8_mod_studio.sh`


```text
(no output; exit 0)
```

`PATH=/tmp/astra-apf-runtime/bin:$PATH env -u PYTHONPATH QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/test_apf_studio_installer.py`


```text
................
----------------------------------------------------------------------
Ran 16 tests in 12.206s

OK
```

`PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tools/apf_gui_replay_offscreen.py --receipt /tmp/astra-wave1-validation/gui-final.json`


```text
{
  "dialogs": [],
  "crashes": [],
  "steps": [
    "empty window",
    "retail source loaded",
    "playbooks",
    "play-designer",
    "coverage-geometry",
    "book-identity",
    "cpu-audibles",
    "raw-assets",
    "Coverage Apply through panel",
    "Coverage Revert through panel",
    "all authoring dialogs instantiated",
    "CPU audible preview",
    "CPU audibles staged",
    "Save Project and reopen",
    "existing-book edits refuse rebalance",
    "logos",
    "field_art",
    "Book Identity team table"
  ],
  "tabs": [
    "PLAY / DRCT Inspector",
    "Fine-tune Plays",
    "Who lines up",
    "Assignment Routes",
    "Save Assignments",
    "Design Plays / Formations",
    "Coverage Geometry (experimental)",
    "Book Identity",
    "CPU Play Calling",
    "Raw Playbook Assets"
  ],
  "status": "APF_GUI_REPLAY_PASS"
}
```

`PYTHONPATH=. python3 /tmp/astra_verify_jersey_catalog.py`


```text
JERSEY_CATALOG_REVALIDATED 22
JERSEY_CATALOG_REVALIDATED 23
{"status": "ALL_24_EXACT_ROWS_REVALIDATED", "catalog_sha256": "f07e054e50a85a3d8b02523ac2b1b9c062c5b963bbda0d4e726db80057d8b0e3", "source_sha256": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e", "checks": "all catalog row fields, nine mip hashes/transport, descriptor, IFF, fixed allocation controlled rebuild, inactive bytes, source before/after"}
```

`PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 /tmp/astra_check_final_project.py`


```text
APF_FINAL_PROJECT_REOPEN_PASS modifications=182 fresh_cache=true all_payload_hashes_match=true distinct_crest_details=22
```

`git diff --check`


```text
(no output; exit 0)
```

## Real project and facade builds


The actual local harness first loaded retail into `ApfStudioFacade`, staged all seven CPU audible plans, the three presets, the two coverage edits and all 46 bundle pairs, and saved/reloaded the project. The first real Build refused an over-allocation crest before publishing output. The resume harness preflighted every original pair through the same writers, reverted only failed pairs, saved the exact fitting project, and invoked `facade.build(output)`. No Build method or compiler was mocked.


`PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 /tmp/astra_resume_build.py`


```text
06:19:55 PREFLIGHT 43/46 FIT Tampa Bay Buccaneers/endzone/End Zone/080eb4de
06:20:10 PREFLIGHT 44/46 FIT Tampa Bay Buccaneers/logo/default/ed27c2d7
06:20:56 PREFLIGHT 45/46 REFUSED Washington Redskins/endzone/Endzone/0bb2e80b: Could not compile Field Art package 70: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 13524 bytes; refusing output
06:21:11 PREFLIGHT 46/46 FIT Washington Redskins/logo/default/ee9b9e02
06:21:11 Confirming untouched source: 8388608/1140850688
06:21:12 Compiling mod edits: 0/182
06:44:22 Copying a safe, separate game folder: 16777216/3919218688
06:44:28 Applying compiled APF edits: 0/45
06:44:28 Verifying the complete APF build: 8388608/1140850688
06:44:44 Confirming source remained untouched: 8388608/1140850688
06:44:47 MAIN REAL FACADE BUILD SUCCEEDED
06:44:48 Verifying APF design and CPU book allocations: 0/1
06:44:51 APF design verified and staged: 1/1
06:44:51 Confirming untouched source: 8388608/1140850688
06:44:52 Compiling mod edits: 0/1
06:44:55 Copying a safe, separate game folder: 16777216/3919218688
06:45:02 Applying compiled APF edits: 0/3
06:45:02 Verifying the complete APF build: 8388608/1140850688
06:45:06 Confirming source remained untouched: 8388608/1140850688
06:45:09 APF_REAL_FACADE_BUILDS_PASS
```

The final main project contains **182 modifications**: 132 audible selectors, one three-recipe preset profile, one coverage profile, and 48 paired art modifications (35 source pairs: 22 crests and 13 endzones). Presets have explicit precedence in their recipe records; staging audible selectors does not promise every final preset record remains balanced.


| CPU book | Outer | Staged audible tag moves |
| --- | --- | ---: |
| O-ManBlock | 130 | 20 |
| O-TwoBack | 259 | 22 |
| O-SinglebackAce | 369 | 13 |
| O-Singleback3WR | 767 | 27 |
| O-WestCoast | 891 | 22 |
| O-ZoneBlock | 943 | 13 |
| O-Shotgun | 1411 | 15 |


Coverage is a retail-pinned **taste test**, not a correctness/gameplay claim: node 3223 (4 Cloud, slot 9) lateral extent 6→8 yards; node 3423 (Combo Strong Zone, slot 10) 8→10 yards. The role labels are inferred from stock usage. The receipt enumerates every shared assignment affected. All other numeric geometry and protected mode bits remain bounded by the writer.


Play Design is a second output because the explicit composition guard rejected the combined project. The second project contains exactly `docs/research/apf_play_design_example.json`; its actual Build writes outer entries 180, 259 and 618.


### Combined wave


Folder: `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09`. Full receipt: `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09/.apf2k8-mod-studio-build.json`.


Total folder bytes including receipt: 3920157040. Only pack `0A` changed; `0B`, `1A`, `1B`, `default.xex` and the update file retain their retail hashes.


```text
{
  "schema": "apf2k8_mod_studio_build/v1",
  "mode": "modded",
  "edit_count": 182,
  "compiled_entry_count": 45,
  "compiled_span_count": 45,
  "compiled_raw_overlay_count": 0,
  "compiled_span_packs": [
    "0A"
  ],
  "source": {
    "0a_sha256_after": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "0a_sha256_before": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "opened_read_only": true,
    "source_modified": false
  },
  "output": {
    "0a_sha256": "4fdd00df1f2960f733f6b9e3c3774effb12dcfa3859dc000f41e99b9344b576e",
    "0a_size": 1140850688,
    "launch_file": "default.xex",
    "published_atomically": true,
    "type": "complete_extracted_game_directory"
  },
  "verification": {
    "all_applicable_changed_entries_reparsed": true,
    "all_bytes_outside_changed_outer_entries_identical": true,
    "all_bytes_outside_compiled_spans_identical": true,
    "all_changed_entries_reparsed": true,
    "all_changed_pack_bytes_outside_compiled_spans_identical": true,
    "all_compiled_spans_match_exactly": true,
    "all_unchanged_packs_match_retail": true,
    "all_unchanged_sibling_files_match_retail": true,
    "source_and_output_are_distinct_inodes": true
  },
  "changed_outer_entries": [
    48,
    130,
    133,
    154,
    168,
    171,
    180,
    190,
    213,
    229,
    259,
    262,
    269,
    369,
    394,
    421,
    472,
    548,
    695,
    716,
    753,
    756,
    767,
    774,
    868,
    891,
    907,
    943,
    948,
    951,
    986,
    1019,
    1060,
    1136,
    1161,
    1339,
    1347,
    1411,
    1433,
    1442,
    1453,
    1469,
    1510,
    1530,
    1533
  ],
  "source_unchanged": true,
  "book_identity_receipt_present": true,
  "final_identity_assignment_count": 80,
  "final_identity_team_count": 40
}
```

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `$SystemUpdate/su20076000_00000000` | 7299072 | `39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8` |
| `.apf2k8-mod-studio-build.json` | 938352 | `b82b3153524397b0353ae37b8b2eae285d453706639ef90f00e82f363326f1f3` |
| `0A` | 1140850688 | `4fdd00df1f2960f733f6b9e3c3774effb12dcfa3859dc000f41e99b9344b576e` |
| `0B` | 1073838080 | `775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53` |
| `1A` | 1140850688 | `9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb` |
| `1B` | 517971968 | `04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084` |
| `default.xex` | 38408192 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |



### Play Design


Folder: `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09 PLAY DESIGN`. Full receipt: `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09 PLAY DESIGN/.apf2k8-mod-studio-build.json`.


Total folder bytes including receipt: 3919283347. Only pack `0A` changed; `0B`, `1A`, `1B`, `default.xex` and the update file retain their retail hashes.


```text
{
  "schema": "apf2k8_mod_studio_build/v1",
  "mode": "modded",
  "edit_count": 1,
  "compiled_entry_count": 3,
  "compiled_span_count": 3,
  "compiled_raw_overlay_count": 0,
  "compiled_span_packs": [
    "0A"
  ],
  "source": {
    "0a_sha256_after": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "0a_sha256_before": "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e",
    "opened_read_only": true,
    "source_modified": false
  },
  "output": {
    "0a_sha256": "7c5e3e57bf9eb4af0dfa187027d05a930cf4dd4169847c185702b862386e819f",
    "0a_size": 1140850688,
    "launch_file": "default.xex",
    "published_atomically": true,
    "type": "complete_extracted_game_directory"
  },
  "verification": {
    "all_applicable_changed_entries_reparsed": true,
    "all_bytes_outside_changed_outer_entries_identical": true,
    "all_bytes_outside_compiled_spans_identical": true,
    "all_changed_entries_reparsed": true,
    "all_changed_pack_bytes_outside_compiled_spans_identical": true,
    "all_compiled_spans_match_exactly": true,
    "all_unchanged_packs_match_retail": true,
    "all_unchanged_sibling_files_match_retail": true,
    "source_and_output_are_distinct_inodes": true
  },
  "changed_outer_entries": [
    180,
    259,
    618
  ],
  "source_unchanged": true,
  "book_identity_receipt_present": true,
  "final_identity_assignment_count": 80,
  "final_identity_team_count": 40
}
```

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `$SystemUpdate/su20076000_00000000` | 7299072 | `39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8` |
| `.apf2k8-mod-studio-build.json` | 64659 | `2d9cce0aeb84b61d25c1265d133ddf082c93e937740f6e1b57bf83c0fbd04800` |
| `0A` | 1140850688 | `7c5e3e57bf9eb4af0dfa187027d05a930cf4dd4169847c185702b862386e819f` |
| `0B` | 1073838080 | `775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53` |
| `1A` | 1140850688 | `9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb` |
| `1B` | 517971968 | `04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084` |
| `default.xex` | 38408192 | `981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f` |



### Saved projects and external patch


- `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09.apf2k8mod` — 1764224 bytes; SHA-256 `75700ea21179325567596661154d9d08a845b5b286423a1332aed45b944dbd81`.

- `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09 PLAY DESIGN.apf2k8mod` — 1529 bytes; SHA-256 `b5b6642976fd67b615e489febfc43a1e550a97298e5a4c2cd45f9a078d94c746`.

- `/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09.54540807.patch.toml` — 14183 bytes; SHA-256 `930a117a2a648f9896a8e431413341804002326fccc64a12f1875f935d4f86ac`.


The BASE patch sits next to the main built folder, never inside a game pack. Export receipt:


```text
{
  "schema": "apf2k8_pass_fetch_te_bias/v1",
  "status": "unwitnessed",
  "image": "base",
  "image_sha256": "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf",
  "module_hash": "5447E5428AA2D52A",
  "hook": 2223414048,
  "hook_word": "484A44E0",
  "cave_start": 2228281344,
  "cave_size": 716,
  "cave_original_zero_sha256": "ad7facb2586fc6e966c004d7d1d16b024f5805ff7cb47c7a85dabd8b48892ca7",
  "scope": "Unconditional offensive pass subtypes 2/3/4, every down; weighted picker untouched",
  "personnel_boundary": "TE-compatible primary record; later formation selection and substitutions unwitnessed",
  "down_distance_status": "Live down/distance not sufficiently proved for this hook",
  "verification": {
    "capstone_redecoded": true,
    "instruction_count": 179,
    "branch_count": 34,
    "all_branch_targets_checked": true,
    "cave_sha256": "3eb4432906753a6f1944123a7d70477747ae051ff114714f7585a0ac3ccd1db8"
  },
  "toml_reparsed": true,
  "output_sha256": "930a117a2a648f9896a8e431413341804002326fccc64a12f1875f935d4f86ac",
  "path": "/home/noah/2K5 Mod Studio Builds/APF 2K8 WAVE1 TEST 2026-09-09.54540807.patch.toml"
}
```

To reproduce from either supplied project, construct `ApfStudioFacade(cache_root=<temporary path>)`, `load_source(<retail folder>)`, `load_project(<saved .apf2k8mod>)`, then `build(<new, absent output folder>)`. The actual combined build already exercised project reload with independent cache lifetime.


### Art allocation decisions


```text
{
  "path": "/home/noah/Downloads/NFL Logos Textures.zip",
  "size": 13231873,
  "sha256": "57d7d4a9916cafbc654846ab21514e0e95cccfea73003867c07dc33a36a411d3"
}
```

All 46 original assignments staged. The largest subset whose original pixels passed their independent fixed allocations is 35 pairs. No source image was recolored/resized to evade a refusal. The following 11 pairs were reverted; source NFL labels identify bundle art, not inferred Xbox team ownership.


| Source pair | Xbox slot | Refusal |
| --- | --- | --- |
| Chicago Bears/logo/default/e9f1d6c2 | `logo:1409` | rebuilt uniform_logo IFF exceeds its fixed outer allocation by 7642 bytes; refusing output |
| Cleveland Browns/logo/default/5bd10ad2 | `logo:551` | rebuilt uniform_logo IFF exceeds its fixed outer allocation by 20540 bytes; refusing output |
| Houston Oilers/logo/default/66b12362 | `logo:621` | rebuilt uniform_logo IFF exceeds its fixed outer allocation by 21286 bytes; refusing output |
| Indianapolis Colts/logo/default/53a174b2 | `logo:496` | rebuilt uniform_logo IFF exceeds its fixed outer allocation by 6486 bytes; refusing output |
| Miami Dolphins/endzone/End Zone/356e9d6e | `endzone:329` | Could not compile Field Art package 329: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 1162 bytes; refusing output |
| Miami Dolphins/logo/default/d047eb67 | `logo:1233` | rebuilt uniform_logo IFF exceeds its fixed outer allocation by 20263 bytes; refusing output |
| Philadelphia Eagles/endzone/End Zone/55d3471c | `endzone:510` | Could not compile Field Art package 510: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 22556 bytes; refusing output |
| Phoenix Cardinals/endzone/End Zone/150b8466 | `endzone:129` | Could not compile Field Art package 129: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 12050 bytes; refusing output |
| San Francisco 49ers/endzone/End Zone/9a4b71c6 | `endzone:920` | Could not compile Field Art package 920: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 3530 bytes; refusing output |
| Seattle Seahawks/endzone/End Zone/fe324ecb | `endzone:1535` | Could not compile Field Art package 1535: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 2231 bytes; refusing output |
| Washington Redskins/endzone/Endzone/0bb2e80b | `endzone:70` | Could not compile Field Art package 70: rebuilt endzone_l0 IFF exceeds its fixed outer allocation by 13524 bytes; refusing output |


The retained explicit mappings are:

| Source pair | Xbox slot |
| --- | --- |
| Atlanta Falcons/endzone/End Zone/9e8f94b9 | `endzone:951` |
| Atlanta Falcons/logo/default/7ba6e2b0 | `logo:756` |
| Buffalo Bills/endzone/End Zone/72cee7be | `endzone:695` |
| Buffalo Bills/logo/default/97e791b7 | `logo:907` |
| Cincinnati Bengals/logo/default/46c6cb00 | `logo:421` |
| Dallas Cowboys/endzone/EndZone/c352677b | `endzone:1161` |
| Dallas Cowboys/logo/default/267b1172 | `logo:229` |
| Denver Broncos/endzone/End Zone/e08b22a6 | `endzone:1347` |
| Detroit Lions/endzone/End Zone/75b65e14 | `endzone:716` |
| Detroit Lions/logo/default/909f281d | `logo:868` |
| Detroit Lions/logo/default/fd32901e | `logo:1530` |
| Green Bay Packers/logo/default/2c013bc3 | `logo:269` |
| Kansas City Chiefs/endzone/Endzone/a49704a3 | `endzone:986` |
| Kansas City Chiefs/logo/default/41be72aa | `logo:394` |
| Los Angeles Raiders/logo/default/7f6207cf | `logo:774` |
| Los Angeles Rams/endzone/End Zone/f3222cba | `endzone:1469` |
| Los Angeles Rams/logo/default/160b5ab3 | `logo:133` |
| Minnesota Vikings/endzone/End Zone/7b1a60b0 | `endzone:753` |
| Minnesota Vikings/logo/default/9e3316b9 | `logo:948` |
| New England Patriots/endzone/End Zone/fd8e121e | `endzone:1533` |
| New England Patriots/logo/default/18a76417 | `logo:154` |
| New Orleans Saints/endzone/End Zone/5b7f79b8 | `endzone:548` |
| New Orleans Saints/logo/default/be560fb1 | `logo:1136` |
| New York Giants/logo/default/2add7b07 | `logo:262` |
| New York Jets/logo/default/df5dddc7 | `logo:1339` |
| Philadelphia Eagles/logo/default/b0fa3115 | `logo:1060` |
| Phoenix Cardinals/logo/default/f022f26f | `logo:1453` |
| Pittsburgh Steelers/endzone/EndZone/1f635fbd | `endzone:190` |
| Pittsburgh Steelers/logo/default/fa4a29b4 | `logo:1510` |
| San Diego Chargers/endzone/End Zone/4faece0e | `endzone:472` |
| San Diego Chargers/logo/default/aa87b807 | `logo:1019` |
| Seattle Seahawks/logo/default/1b1b38c2 | `logo:168` |
| Tampa Bay Buccaneers/endzone/End Zone/080eb4de | `endzone:48` |
| Tampa Bay Buccaneers/logo/default/ed27c2d7 | `logo:1433` |
| Washington Redskins/logo/default/ee9b9e02 | `logo:1442` |


## Cleanup and disk


The authorized `/tmp/astra-book-c_5_qyqf` old copies were removed **only after** the combined facade build succeeded. Temporary release stages, test runtime, import caches and the two validation symlinks were removed. No other build folder was deleted. The two completed requested outputs, projects and external patch remain.


```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p2  916G  763G  107G  88% /
```

## What Noah must witness in Xenia


No emulator was launched. Start with the combined build and the external pass-fetch patch disabled.


1. **Quick Game → team selection and game presentation:** inspect the retained crest slots in team/helmet views and their linked logo caches. Test home/away and near/far helmet views. The bundle uses semantic library-slot matching; a source NFL label is not proof of fictional-team ownership. On the relevant stadium/endzone views, compare both endzone layers and camera distances; Field Art intentionally preserves old mip tails.


2. **Quick Game → CPU offense / audible situations:** select teams whose final Book Identity receipt resolves to each of the seven CPU books. Observe run/pass audible availability and actual lineups. In the three preset books, test Wide Zone, Spread-to-Run and Pro Power across formations and situations. Inspect who lines up at TE/WR and verify that absent/unreachable personnel cases remain refused. Offline membership/tag supply does not establish CPU call frequency or situational logic.


3. **Practice → defensive play selection:** choose stock 4 Cloud and Combo Strong Zone, then compare the identified slot assignments against retail with the same offensive formation and receiver route. The two shared nodes widen by +2 yards. Observe corner/flat depth, lateral width and receiver carry; repeat any needed BASE/TU comparison separately. Shared nodes also affect the other plays enumerated by the receipt.


4. **Separate PLAY DESIGN build → Practice/play selection and CPU book calls:** locate the appended example plays/formations, inspect alignments and assignment paths, and exercise the example CPU calls. Do not combine this output with the legacy profiles. Verify actual timing, coverage and path behavior; the hidden spy and five-step cadence capabilities remain unproved.


5. **Studio → Playbooks → Book Identity**, for a later independent clone: choose the completed output, review the team/resource table, select the independent offensive-book action, then Build new game folder as the final step. Launch that final folder in Xenia and check **Quick Game → team selection / CPU playcalling**. Existing ROS assignments can override disc labels; verify which resource is actually consumed. No clone is inserted into the two supplied wave outputs.


6. **Xenia patch configuration → Quick Game/Practice pass fetches:** only after an unpatched comparison, enable the supplied `54540807` BASE TOML for module hash `5447E5428AA2D52A`. Keep conflicting cave users disabled. Compare TE-biased typed pass-fetch lineups across downs, including user and CPU contexts. This hook applies on every down; it is not a proved CPU third-and-long selector and does not replace the main CPU weighted picker. The TU module hash is `CEA825F7C2012F5A`; export its separately pinned variant from the panel rather than using the BASE file. Patch status stays UNWITNESSED until those observations are recorded.
