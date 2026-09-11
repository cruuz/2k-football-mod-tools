# Beta 66 job B: performance report

Branch: `astra/b66-perf`. Baseline: `cc0407b3` (beta 65). No push, emulator, audio playback, display, or network was used. Qt ran offscreen.

Noah asked for “a faster tool” and “better performance”. This addresses triage rows 1, 2 and 5: Smuzz's sluggish startup/builds and NOT RESPONDING reports, maumau78's many-texture builds, and Mud's slow song conversion.

## Results and limits

- Window visible: **6.329 s → 0.521 s**. Normal navigation handlers returned within **120 ms** in the measured sweep. Initial metadata-dependent page contents still took **0.39–1.03 s** to become ready asynchronously; the strict 300 ms content-ready target is not met for those first visits.
- Forty real uniform replacements, compiled from synthetic PNGs against read-only retail packages: **123.097 s → 16.946 s**, **7.26×** faster preparation, with identical replacement hashes. This is not a full-disc build timing.
- Four-minute stereo song: **1,189.364 s → 89.387 s**, **13.31×** faster, including generation of identical decoded preview PCM. No new dependency.
- Project-plus-gameplay composition uses one private image copy instead of two. The original dispatcher and the new combined dispatcher produced identical synthetic disc bytes. Source preservation and failure-before-publish are tested.
- Full retail end-to-end stage timing remains **unmeasured**. `df -h /` reported 98G available; a 6 GB output would breach the brief's 100 GB free-space floor. The permitted writable roots were this worktree and `/tmp`; the prescribed Storage scratch directory was outside them. I did not write a 6 GB retail disc. The 12.2 MB synthetic disc is not a throughput prediction for a 6 GB image.
- APF was profiled, not changed. Its cross-run catalog cache already exists. The warm path still decodes external audio identity blocks and authenticates source files.

## Startup measurements

Single local runs under concurrent verification load, Python 3, Qt offscreen. Wall times and cProfile times are separate measurements; profiling overhead is especially severe in per-pixel Python loops. The final visible-wall probe includes creation of the real `Nfl2k5StudioFacade`, window construction, `show()` and event processing. The baseline visible probe measured construction/show/event processing. This does not include launching the interpreter.

| Measurement | Before | After |
|---|---:|---:|
| Window visible, normal wall | 6.329 s | 0.521 s |
| Constructor, cProfile cumulative | 20.681 s | 1.212 s |
| Visible, cProfile wall | 20.717 s | 1.240 s |
| `_build_ui`, cumulative | 11.186 s | 0.146 s |
| Four `_build_visual_page` calls | 6.999 s | Deferred |
| `_filter_visual_assets` | 6.853 s | Deferred/model rows |
| `_visual_icon` | 47,237 calls / 5.025 s | 0 at startup |
| Extended catalog loader | 6.099 s | Deferred |
| Uniform catalog loader | 1.990 s | Deferred |
| `_ordered_unique` | 34,705 calls / 1.401 s | Set membership, deferred |
| Build page construction | 1.531 s | Deferred |
| Scorebug initial preview | 1.389 s | Deferred to showing page |
| `mod_build.availability` | 1.159 s | Background first-page preparation |
| ESPN CSV parsing | 35 calls / 0.936 s | Deferred with Build options |
| Capability registry load | Remaining work | 0.926 s under cProfile |

Importtime (`python3 -X importtime`, cumulative import seconds; nested rows overlap):

| Module | Before | After |
|---|---:|---:|
| `mod_editor.gui.studio_qt` | 1.210468 | 0.741913 |
| `mod_editor.gui.audio_panel_qt` | 0.390976 | 0.273153 |
| `mod_editor.studio.facade` | 0.321111 | 0.242953 |
| `mod_editor.core.nfl2k5_hires_pack` | 0.394347 | Deferred beyond startup |
| `mod_editor.core.nfl2k5_hires_catalog` | 0.251322 | Deferred beyond startup |

First navigation sweep, seconds from selection until handler returns / complete content is available:

| Page | Handler | Ready |
|---|---:|---:|
| Uniforms | 0.0007 | 0.3910 |
| Players | 0.0011 | 1.0289 |
| Team identity | 0.0375 | 0.0406 |
| Field art | 0.0141 | 0.0169 |
| Stadiums | 0.0091 | 0.0116 |
| Presentation | 0.0206 | 0.0232 |
| Menus | 0.0681 | 0.0708 |
| Crib | 0.0351 | 0.0381 |
| Audio | 0.0714 | 0.0751 |
| Gameplay | 0.0002 | 0.9542 |
| Playbooks | 0.0595 | 0.0644 |
| All textures | 0.1196 | 0.1297 |
| Scorebar | 0.0511 | 0.0720 |
| Build & Share, after Gameplay prepared it | 0.0009 | 0.0100 |

Rosters, models, animations, Create Play and MyCareer each returned within 5 ms and were ready within 10 ms in this sweep. These numbers include warm reuse between pages, not independent cold starts for every row.

The main page stack keeps stable navigation positions. `open_workspace()` constructs synchronously for replay/automation. Direct legacy category/browser-map access also constructs on demand. Full-shell layout tests opt into `eager_pages=True`; separate tests exercise default lazy behavior, asynchronous loading, row selection, saved settings and deferred icon rendering. Getting Started's Build navigation also prepares options asynchronously. Newly created pages inherit source inspection and saved feature/music choices.

Catalog caches are versioned compact JSON arrays keyed by SHA-256 of shipped metadata and catalog source inputs. They contain metadata, not retail game payloads, PNGs or decoded audio. Stale or malformed entries rebuild; unwritable cache locations do not prevent opening. No pickle is used. Visual browser items are a Qt list model; only requested decoration roles create cached icons, preserving the prior family/color appearance.

## APF profile

No APF source or changelog changed. `ApfStudioMainWindow` measured 0.727 s under cProfile; a separate ordinary wall probe measured 0.884 s. `mod_editor.apf_studio.gui` importtime cumulative was 0.570236 s. Constructor hotspots were `_build_pages` 0.458 s, uniform independence refresh 0.279 s (repeated `teams_using` 0.219 s), and stylesheets 0.229 s.

The following profiles cover `ApfStudioFacade.load_source`, the worker used by `_load_source_path`, rather than claiming a timing of the GUI's final repaint:

| Source-load stage, cumulative cProfile seconds | Cold private cache | Existing private cache |
|---|---:|---:|
| `load_source` | 48.468 | 27.471 |
| `CatalogBuilder.build` | 40.351 | 20.567 |
| Cache JSON serialization | 16.541 | Avoided |
| External audio identities | 13.159 | 14.998 |
| Five H7A block decodes | 12.921 | 14.684 |
| Source resolve/authentication | 8.107 | 6.900 |
| Warm uniform catalog | — | 2.228 |

`mod_editor/apf_studio/catalog.py:545` already loads a persistent index. The remaining repeated work is `_external_audio_catalog_identities`, which calls `discover_external_audio_banks` and H7A decoding even when the main catalog is cached. A follow-up can cache those identity records keyed by authenticated source digest and decoder/schema version, retaining source authentication and caching no decoded retail bytes. This job makes no APF speedup claim.

## Disc preparation, composition and responsiveness

The retail preparation probe used the first 40 uniform sets, each with a staged 512×256 solid RGBA torso PNG, deterministic colors `(i*19 % 256, i*37 % 256, i*53 % 256, 255)`. It pinned the shipped index/inventory/report, authenticated the read-only retail XISO, prepared all edits and bound them to their source spans. It cleaned prepared payloads after each successful run. The serial wall baseline used the original PNG functions from git and `parallelism=1`; the profiled baseline used the original backend loaded before editing.

| Read-only retail preparation stage | Before wall | After wall |
|---|---:|---:|
| Source authentication | 8.203 s | 7.381 s |
| Prepare 40 edits | 123.097 s | 16.946 s |
| Bind prepared spans to source | 3.441 s | 2.709 s |
| Sum of these measured stages | 134.741 s | 27.036 s |
| Full builder subprocess including copy | Not run | Not run |
| Full independent verify subprocess | Not run | Not run |
| Final retail publication | Not run | Not run |

The SHA-256 of the concatenated ordered replacement SHA-256 strings was identical in serial, parallel, profiled and unprofiled probes:

`55ef2a00944b7065732cc5174c439d56145e8fe9f9848f0412cc4554b4e4a4cf`

Baseline cProfile for all 40 edits: preparation 1,505.126 s; PNG normalization 675.299 s; palette expansion 277.691 s; 80 compressor calls 333.557 s; mip generation 142.260 s. A one-edit comparison isolates the byte-operation improvement: 43.370 s → 16.719 s under cProfile, same replacement digest. Parallel preparation was 14.758 s with the parent profiled, but child encoders were not profiled, so that ratio is **not** presented as a speedup. The ordinary wall comparison above is the speed evidence.

Equipment was already grouped by TSET with an `EquipmentCompileCache`. No per-edit whole-pack rewrite was found: the backend prepares replacements, makes one disc copy and writes fixed spans. Independent torso/sleeve/pants/live-helmet/team-select projects now use a spawn process pool, limited to eight workers and constrained by CPU affinity and memory. Linux uses `MemAvailable`, since free-page counts alone mistake the just-read disc cache for exhausted RAM. Parent writes remain ordered and exclusive. Mixed projects, digit fallbacks and historical virtual replays retain their serial ordering. The process pool does not change quantizers, VC-LZ output, mip arithmetic or the fixed-span wrapper contract. RGBA normalization and palette expansion use byte operations; all CRC, size, transparency and filter validation remains.

`Nfl2k5BuildService.build` now records `materialization`, `builder`, `verify`, and `publish` seconds on its result. `mod_build.build` records reported stages, including executable preparation/writes, archive operations, final inspection, final hashing and publication. These receipts provide the requested stage breakdown on Noah's next full build; absent retail timings above are not invented.

The combined Build-tab path validates the plan first, builds and independently verifies its project image inside the final destination's private temporary directory, consumes that owned intermediate by rename, applies the plan, verifies and publishes the final destination once. Normal copies use bounded `platform_compat.copy_file_range` with a short-copy-safe pread/pwrite fallback. No source hard link is edited. The verified project manifest supplies the source hash; the final image is freshly hashed once for its outcome. The original source is never opened writable.

Synthetic disc proof: 12,242,944 bytes, synthetic XDVDFS + XBE + 40 disjoint synthetic texture spans, throwing at 80 yards, catch slider, acceleration ramp, draft AI and returner fix. Executing the baseline dispatcher with the historical two-step flow and executing the new combined flow gave output hash:

`9e74dac1695f09846b46fd8c580b726ccac36d61b34bc21b148f69c1e420c078`

The original synthetic source stayed:

`7947912d5239fc737f97a75c8d6bbdebfd3239124ba4cb99f0bcf5519315b295`

| Synthetic stage | Before | After |
|---|---:|---:|
| Total, one measured run | 4.263 s | 5.437 s |
| Project materialization/copy/read-back helper | 0.082 s | Included below |
| Preflight plus synthetic project helper | — | 0.106 s |
| XBE preparation | — | 3.180 s |
| XBE writes | — | 1.553 s |
| XBE read-back | — | 0.284 s |
| Composed-disc inspection | — | 0.266 s |
| Final hash | — | 0.013 s |
| Final publish | — | 0.0006 s |
| Full-disc copy count in composition test | 2 | 1 |

The small synthetic build was slower in this single run; it verifies byte identity and the eliminated copy, not a full-disc performance gain. Timings vary with the concurrent native gate runs.

Both GUI build paths now maintain a one-second footer heartbeat with stage and elapsed seconds. Copy reports include a byte percentage. Queued progress is throttled; byte totals use Python objects across Qt signals so 6 GB values do not overflow a signed 32-bit signal. Worker `SystemExit`/other failures reach the GUI failure handler. The final source-state scan, including archive changes after the earlier build inspection, runs on the worker; the completion callback applies its result without GUI-thread disc I/O. Dialogs remain in GUI callbacks, and the edit-state refresh updates only constructed browsers rather than materializing all visual items.

Plan-level preflights now also run before project or song preparation: the playbook-pair conflict, R62 options, throwing ranges, uniform-choice parsing, module availability, and missing/malformed history/career/prospect/roster documents. Final read-back and composed-resource refusals remain required; they cannot be replaced by checks of an untouched source. Job D1 still owns refusal at checkbox time.

## Song proof

Four minutes, 22,050 Hz stereo PCM16, deterministic two-tone samples, 8,192-frame chunks, repeated final stereo-frame padding. The baseline forces the scalar encoder used by installers without NumPy. NumPy is not a declared installer dependency and was not added. The retained optional NumPy path is not claimed to be 13× faster.

| Stage | Before | After |
|---|---:|---:|
| Encode | 1,172.940 s | 83.547 s, including preview |
| Separate decode-back | 10.890 s | Removed |
| Total including PCM generation/hash overhead | 1,189.364 s | 89.387 s |

Every candidate index still competes under the original squared-error criterion and lowest-index tie rule. Precomputed threshold/transition tables remove repeated arithmetic; a promising starting index supplies an error bound, and candidates stop only when their accumulated nonnegative error cannot beat the winner. The winning encoder predictors directly supply the audible preview, preserving the original stereo block order, chunk padding and 64-frame preview semantics.

Identical encoded ADPCM SHA-256:
`3491cc11a7a74c1189bb275986d9483fbe237b3d2e117912ae6c26d5e7b19cf0`

Identical decoded-preview PCM SHA-256:
`04890cdea85930adcc588abe29a6827595730c405819bb056ba56d72d5669f9e`

The original scalar block encoder remains as the reference. Tests compare fixed tones, random noise, clipping, silence/ties, stereo ordering and final partial-block padding, and independently decode the preview.

## Verification and release handoff

Final standalone verification results appear below. Raw logs, profiles and probe scripts are under `/tmp/b66-perf-evidence`; they contain timings/metadata and synthetic data, not committed retail payloads. Benchmark commands were run with `PYTHONPATH=.` and `QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1` for GUI probes. Import profiles used `python3 -X importtime`; cumulative tables used `cProfile.Profile` / `pstats.Stats(...).sort_stats('cumulative')` around construction or preparation.

The protected release allowlist needs the two helper paths in `WIRING.md`. Existing writer/runtime pins are refreshed with `python3 packaging/repin.py --apply`. The protected shipped cave manifest becomes stale when pinned source files change and must be regenerated by Claude during integration. A scratch manifest is recorded from actual pure-XBE safety-gate composition for local oracle verification; it does not claim a full disc/resource build.

PROVED: measurements above, fixed-vector music equality, prepared replacement equality, synthetic disc equality, source preservation and verification-before-publication in fixtures. UNWITNESSED: Windows task-manager responsiveness, physical-disk throughput, a complete 40-edit retail build, all in-game behavior. Noah should witness opening each page after loading/reopening a project, live footer updates during copy/encode/verify, a 40+ mixed uniform/equipment build with gameplay selected, and playback/preview of an added full-length song. No preset or game behavior was intentionally changed.

Reproducible probe commands from the repository root (the local scripts retain the source-free recipes; baseline reads are fixed to `cc0407b3`):

```sh
PYTHONPATH=. python3 /tmp/b66-perf-evidence/bench_song.py before
PYTHONPATH=. python3 /tmp/b66-perf-evidence/bench_song.py after
PYTHONPATH=. python3 /tmp/b66-perf-evidence/bench_prepare_wall_before.py
PYTHONPATH=. python3 /tmp/b66-perf-evidence/bench_prepare_wall_after.py
PYTHONPATH=. python3 /tmp/b66-perf-evidence/bench_synthetic_build.py
PYTHONPATH=. python3 /tmp/b66-perf-evidence/record_xbe_manifest.py
python3 /tmp/b66-perf-evidence/normalize_observed_manifest.py
NFL2K5_CAVE_MANIFEST=/tmp/b66-perf-evidence/cave-manifest.json PYTHONPATH=. python3 tests/mod_editor/test_nfl2k5_cave_oracle.py
PYTHONPATH=. python3 /tmp/b66-perf-evidence/run_pairwise_shards.py
PYTHONPATH=. python3 /tmp/b66-perf-evidence/test_clean_provider_workspace.py
```

The first oracle run correctly rejected the old protected manifest. The first provider run correctly rejected the worktree's pre-existing `extracted` symlink; the final provider run uses copied tracked package inputs with no retail extraction. A first pairwise run hit the test driver's 420-second limit; the final run enumerates all 335 cases exactly once and invokes the unchanged standalone file with case selectors in eight separate interpreters. No test assertions, source identity gates or provider symlink checks were relaxed.

The shared checkout could not be committed directly: `git add` failed creating its `index.lock` because `/home/noah/2k-football-mod-tools/.git/worktrees/astra-b64-ps3-roster` is mounted read-only. No approval escalation is available. The worktree's branch name is `astra/b66-perf`; its `.git` file still points at that historical administrative directory. I left shared Git metadata untouched and prepared a private Git object/index directory under `/tmp/b66-perf-evidence/commit.git`, based on `cc0407b3`, to produce `ASTRA_COMMIT.bundle` containing the explicit-path commit for integration. The final commit identity is supplied with the bundle; final test results follow below.

The scratch recorder retains the allocator layout from the observed final XBE. Generic `nfl2k5_rdata_sites` / `nfl2k5_gameplay_lever` helper calls initially duplicated their independently observed callers' reservations. Normalization removed 386 duplicate labels only after asserting complete byte-interval coverage by retained reservations. Raw observations remain in `cave-manifest-raw.json`; no product writer, gate assertion or release manifest was changed for this adjustment.

Implementation commit: `1aa697fd` (`perf: speed up beta 66 startup, builds and song encoding`), created with explicit paths in the private Git directory. `ASTRA_COMMIT.bundle` carries this commit and the final report commit on `astra/b66-perf`, with `cc0407b3` as its prerequisite. The original shared branch could not be advanced through the read-only mount.


## Standalone test commands

Each ordinary suite in the final table was run as its own interpreter, using this command with the table's literal path in place of `<suite>`:

```sh
PYTHONPATH=. QT_QPA_PLATFORM=offscreen MOD_STUDIO_NO_UPDATE_CHECK=1 XDG_CACHE_HOME=/tmp/b66-perf-evidence/cache python3 <suite>
```

The two XBE gates used the observed scratch manifest, with their assertions unchanged:

```sh
NFL2K5_CAVE_MANIFEST=/tmp/b66-perf-evidence/cave-manifest.json PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_memory_writes.py
NFL2K5_CAVE_MANIFEST=/tmp/b66-perf-evidence/cave-manifest.json PYTHONPATH=. python3 tests/mod_editor/test_xbe_patch_cave_references.py
```

The oracle used the same manifest and environment. The provider and pairwise exceptions use the exact probe commands above. The pairwise script's `pairwise-shards/cases.json` records every selected case and `summary.json` records all eight successful interpreter exits. Expected skips cover missing private fixture paths, explicitly opt-in multi-GB acceptance or Music GUI replay, and absent full-disc resource evidence in the pure-XBE manifest. They are not claimed as witnessed retail acceptance.

## Final standalone results

**80 suites, 1,510 cases: 1,499 passed, 11 skipped, zero failures in the final runs.** This includes both full XBE gates, all 335 pairwise cases, the cave oracle, every touched test file, build fixtures, modpack suites and the affected GUI/music/texture suites. Earlier failed or interrupted probes remain in the raw evidence directory; the table selects the completed final run for each suite.

| Standalone suite | Final output |
|---|---|
| `tests/mod_editor/test_2k5_audio_operation_integration.py` | Ran 17 tests in 51.888s; OK |
| `tests/mod_editor/test_2k5_bounded_vclz_palette.py` | Ran 7 tests in 3.387s; OK (skipped=2) |
| `tests/mod_editor/test_2k5_build_is_explainable.py` | Ran 16 tests in 0.025s; OK |
| `tests/mod_editor/test_2k5_build_parse_caches.py` | Ran 14 tests in 0.428s; OK |
| `tests/mod_editor/test_2k5_check_my_images.py` | Ran 21 tests in 33.039s; OK |
| `tests/mod_editor/test_2k5_import_offers_resize.py` | Ran 11 tests in 37.243s; OK |
| `tests/mod_editor/test_2k5_stale_original_cache.py` | Ran 9 tests in 0.017s; OK |
| `tests/mod_editor/test_2k5_uniform_equipment_export.py` | Ran 16 tests in 89.435s; OK (skipped=1) |
| `tests/mod_editor/test_2k5_vclz_bounded_importers.py` | Ran 16 tests in 0.667s; OK |
| `tests/mod_editor/test_all_textures_workspace.py` | Ran 23 tests in 7.498s; OK |
| `tests/mod_editor/test_build_panel_qt.py` | Ran 13 tests in 2.321s; OK |
| `tests/mod_editor/test_commentary_panel_qt.py` | Ran 3 tests in 15.354s; OK |
| `tests/mod_editor/test_discord_bugs_1.py` | Ran 17 tests in 1.090s; OK |
| `tests/mod_editor/test_facade_external_build.py` | Ran 2 tests in 0.068s; OK |
| `tests/mod_editor/test_hotfix63_digit_budget.py` | Ran 14 tests in 28.913s; OK |
| `tests/mod_editor/test_mod_build.py` | Ran 11 tests in 2.039s; OK |
| `tests/mod_editor/test_mod_build_beta62_integration.py` | Ran 8 tests in 498.100s; OK |
| `tests/mod_editor/test_mod_build_beta62_integration3.py` | Ran 11 tests in 338.123s; OK |
| `tests/mod_editor/test_mod_build_performance.py` | Ran 6 tests in 18.763s; OK |
| `tests/mod_editor/test_models_panel_qt.py` | Ran 8 tests in 26.390s; OK |
| `tests/mod_editor/test_modpack.py` | Ran 36 tests in 10.087s; OK |
| `tests/mod_editor/test_modpack_growth.py` | Ran 11 tests in 6.002s; OK |
| `tests/mod_editor/test_modpack_growth_acceptance.py` | Ran 1 test in 0.000s; OK (skipped=1) |
| `tests/mod_editor/test_music_service.py` | Ran 10 tests in 3.291s; OK |
| `tests/mod_editor/test_mycareer_art.py` | Ran 10 tests in 47.263s; OK |
| `tests/mod_editor/test_nfl2k5_audio_backend_origin.py` | Ran 5 tests in 0.049s; OK |
| `tests/mod_editor/test_nfl2k5_build_service.py` | Ran 27 tests in 0.528s; OK |
| `tests/mod_editor/test_nfl2k5_cave_oracle.py` | Ran 29 tests in 326.901s; OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_digit_sheet_quality.py` | Ran 13 tests in 16.234s; OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_equipment_consumers.py` | Ran 17 tests in 44.790s; OK |
| `tests/mod_editor/test_nfl2k5_equipment_import.py` | Ran 11 tests in 3.082s; OK |
| `tests/mod_editor/test_nfl2k5_equipment_texture_chain.py` | Ran 16 tests in 13.901s; OK |
| `tests/mod_editor/test_nfl2k5_equipment_texture_native.py` | Ran 5 tests in 1.227s; OK |
| `tests/mod_editor/test_nfl2k5_extended_visuals.py` | Ran 9 tests in 0.231s; OK |
| `tests/mod_editor/test_nfl2k5_import_preflight.py` | Ran 17 tests in 38.343s; OK |
| `tests/mod_editor/test_nfl2k5_music_acceptance.py` | Ran 1 test in 0.000s; OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_music_archive_raw_layout.py` | Ran 8 tests in 0.130s; OK |
| `tests/mod_editor/test_nfl2k5_music_banks.py` | Ran 15 tests in 15.491s; OK |
| `tests/mod_editor/test_nfl2k5_music_banks_performance.py` | Ran 3 tests in 1.033s; OK |
| `tests/mod_editor/test_nfl2k5_music_build.py` | Ran 8 tests in 6.082s; OK |
| `tests/mod_editor/test_nfl2k5_music_catalog.py` | Ran 4 tests in 0.250s; OK |
| `tests/mod_editor/test_nfl2k5_music_fresh_rip.py` | Ran 2 tests in 1.051s; OK |
| `tests/mod_editor/test_nfl2k5_music_fresh_rip_gui.py` | Ran 1 test in 0.001s; OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_music_metadata.py` | Ran 6 tests in 28.994s; OK |
| `tests/mod_editor/test_nfl2k5_music_playlist.py` | Ran 15 tests in 21.431s; OK |
| `tests/mod_editor/test_nfl2k5_music_playlist_contexts.py` | Ran 7 tests in 17.929s; OK |
| `tests/mod_editor/test_nfl2k5_music_playlist_library.py` | Ran 7 tests in 25.047s; OK |
| `tests/mod_editor/test_nfl2k5_music_playlist_manifest.py` | Ran 2 tests in 5.233s; OK |
| `tests/mod_editor/test_nfl2k5_music_policy.py` | Ran 8 tests in 15.106s; OK |
| `tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py` | Ran 335 tests across 8 standalone interpreters; OK |
| `tests/mod_editor/test_nfl2k5_stadium_texture_writer.py` | Ran 9 tests in 5.286s; OK |
| `tests/mod_editor/test_nfl2k5_throw_tuning.py` | Ran 45 tests in 14.330s; OK (skipped=1) |
| `tests/mod_editor/test_nfl2k5_uniform_catalog.py` | Ran 5 tests in 0.580s; OK |
| `tests/mod_editor/test_png_import_accepts_real_pngs.py` | Ran 13 tests in 0.129s; OK |
| `tests/mod_editor/test_presentation_panel_qt.py` | Ran 2 tests in 4.923s; OK |
| `tests/mod_editor/test_product_inspection_panels_qt.py` | Ran 7 tests in 3.882s; OK |
| `tests/mod_editor/test_product_shell_accessibility_qt.py` | Ran 6 tests in 23.671s; OK |
| `tests/mod_editor/test_project_document_workflow.py` | Ran 13 tests in 15.299s; OK |
| `tests/mod_editor/test_providers.py` | Ran 33 tests in 8.989s; OK |
| `tests/mod_editor/test_roster_editor_panel_qt.py` | Ran 50 tests in 11.468s; OK |
| `tests/mod_editor/test_scorebug_studio_panel_qt.py` | Ran 11 tests in 9.495s; OK |
| `tests/mod_editor/test_share_panel_qt.py` | Ran 7 tests in 8.029s; OK |
| `tests/mod_editor/test_sounds_panel_qt.py` | Ran 10 tests in 9.276s; OK |
| `tests/mod_editor/test_stadium_editable_discovery.py` | Ran 6 tests in 15.458s; OK |
| `tests/mod_editor/test_startup_performance.py` | Ran 8 tests in 1.868s; OK |
| `tests/mod_editor/test_studio_facade.py` | Ran 11 tests in 0.016s; OK |
| `tests/mod_editor/test_studio_session.py` | Ran 18 tests in 1.114s; OK |
| `tests/mod_editor/test_studio_shell_layout_qt.py` | Ran 18 tests in 93.202s; OK |
| `tests/mod_editor/test_studio_visual_asset_routing.py` | Ran 14 tests in 4.544s; OK |
| `tests/mod_editor/test_team_kit_bundle.py` | Ran 7 tests in 8.788s; OK |
| `tests/mod_editor/test_team_kit_product_integration.py` | Ran 7 tests in 27.598s; OK |
| `tests/mod_editor/test_throw_tuning_panel_qt.py` | Ran 13 tests in 3.442s; OK |
| `tests/mod_editor/test_unif_color_control.py` | Ran 15 tests in 15.112s; OK (skipped=2) |
| `tests/mod_editor/test_unified_stadium_texture_composition.py` | Ran 5 tests in 0.025s; OK |
| `tests/mod_editor/test_ux_open_disc_hook_qt.py` | Ran 7 tests in 20.013s; OK |
| `tests/mod_editor/test_xbe_patch_cave_references.py` | Ran 127 tests in 1375.126s; OK |
| `tests/mod_editor/test_xbe_patch_memory_writes.py` | Ran 115 tests in 1246.225s; OK |
| `tests/nfl2k5_bump_texture_writer_test.py` | Ran 25 tests in 13.801s; OK |
| `tests/nfl2k5_scorebug_mod_project_test.py` | Ran 10 tests in 5.473s; OK |
| `tests/test_xbox_ima_encoder.py` | Ran 11 tests in 7.212s; OK |

Final pin check: `python3 packaging/repin.py --apply` reported `applied 0 pin update(s)` after the implementation commit. No retail payload, full-disc output or emulator artifact is included in either commit.
