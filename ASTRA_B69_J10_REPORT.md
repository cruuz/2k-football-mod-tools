# Beta 69 J10: PS3 logo bundle import and build speed

Aszemple, **#2k8-general, 2026-09-13 3:55 PM**, after “Was able import both the logos and roster files from my rpcs3 files”: **“only thing is its very slow to import and build the logos from the PS3 Bundle”**.

**PROVED offline:** the measured synthetic texture pipeline fell from **41.719 to 10.176 seconds for one crest**, and **1,373.324 to 70.077 seconds for 32 crests**: 4.10× and 19.60× respectively. All 33 resulting crest packages, fit receipts, both complete synthetic crest archives, and both linked-cache directory/payload pairs match the pre-change output exactly. Retail package comparisons also pass. These are measurements on this host, not a timing promise for Aszemple's files or computer. **Every in-game outcome is UNWITNESSED.**

Branch: `astra/b69-j10-apf-ps3-speed`, based on the current worktree stack head `c2489fcadfe412e0ed0afe20d8654bdc3170bba2`. The implementation checkpoint is `3c8890ab`. Delivery is `b69-j10-apf-ps3-speed.bundle`, with the implementation and final evidence commits on that branch. The shared Git metadata is read-only; commits and bundle creation use private metadata at `/tmp/b69-j10-delivery.git` with this worktree as its work tree. No push was attempted.

## Measurement and scope

Read `ASTRA_CONTEXT.md`, `BETA69_TRIAGE.md`, and the supplied `ASTRA_B661_CREST_REPORT.md`. The H5 report is available in this worktree; its unsuffixed name is absent at the hub. The actual crest writer is **`tools/apf_logo_patch.py`**, not the brief's `mod_editor/core/apf_logo_patch.py` path.

The first package-only baseline was recorded before changing the encoder. It measured 24.725 seconds for one crest and 1,078.046 seconds for 32. After tracing the studio's composite build, the benchmark was extended to include the linked logo cache. The complete baseline below reloads the original writer, cache, bundle, mapping dialog and helper directly from the base commit. Their saved reference bytes were checked against `git show` again after measurement. The original writer SHA-256 is `d50f2146ddb5edfb0c1fed65e21b2b953af7eb0c5e0160bdd4600091cd9ca222`, the same writer recorded by H5. The final complete comparison supersedes the early `before.json`/`after.json` package-only results, which remain as the measurement trail.

`tools/apf_ps3_speed_benchmark.py` authors a ZIP with APFe manifests and 512×512 ARGB4444 DDS pairs. Each pair has independent l0/l1 RGB region masks, preserving six masks, and reproducible 128×128 random colour fields expanded to 512×512. The 32-pair case uses the importer's 28 recognized historical team folders plus four alternatives. It exercises 32 independent crest destinations, not a claim that the importer has 32 distinct historical team names. Generated IFFs have the actual fixed 512×512 base and packed mip allocation, a two-layer 0x158000-byte VRAM block, and a 300,000-byte compressed-art budget. Every pair traverses greedy and optimal at 16 and 8 shades, then fits at 4 shades. The 2-shade/refusal cases are covered separately by the existing fit tests.

The linked cache has the real **236 descriptors / 118 two-layer crests**, a 40,960-byte directory, and a 10,356,736-byte payload allocation, with authored headers, auxiliary records, footer and legal compressed streams. The normal cache parser and writer process this fixture. There are no retail or reporter pixels in any new fixture or committed artifact.

The timed path is ZIP read/decode → destination inventory → fit ladder → mapping plan → stage revalidation/PNG saves → crest compilation → linked-cache compilation → the real `ApfBuildService._apply_compiled_spans`, fsync and readback. A separate small synthetic output holds the two linked-cache spans. The stage benchmark substitutes a session mutation sink because this small archive has no game executable/catalog. A separate integration test uses a real `ApfSession`, stages the import, and invokes the actual studio crest compiler with the synthetic cache provider.

**Limits:** this is the complete bounded texture pipeline on the generated input, not a complete game build. Fixture generation, source opening/executable validation, real-session undo bookkeeping, and copying a full retail game folder are excluded. The synthetic destinations share one shift-8 layout; H5 documented two layouts across all 118 retail destinations. Consequently the inventory numbers below do not measure reading all 118 retail sources. The retail writer checks below cover shifts/layouts already exercised by the repository's tests. The GUI is constructed and exercised offscreen, separately from the worker pipeline timer.

Host: AMD Ryzen 9 3950X, 16 physical / 32 logical CPUs, affinity 32, Linux x86-64, Python 3.12.3, Pillow 10.2.0. The adaptive pool selects 31 workers for 32 crests on this machine. These are observed single runs on a shared development host, not isolated repeated-run distributions. Exact data is in `reports/b69_j10/environment.json`, `before_complete.json`, and `after_complete.json`.

### Pipeline wall time, seconds

| Phase | 1 before | 1 after | 32 before | 32 after |
|---|---:|---:|---:|---:|
| ZIP read, manifests and PS3 decode | 0.143 | 0.140 | 1.980 | 1.837 |
| Synthetic destination inventory | 0.001 | 0.001 | 0.003 | 0.003 |
| Measure greedy / optimal / shade ladder | 14.340 | 5.320 | 475.907 | 20.289 |
| Mapping plan | 0.004 | 0.004 | 0.123 | 0.146 |
| Stage revalidation and PNG saves | 0.222 | 0.235 | 4.464 | 4.612 |
| Compile crest packages and verify | 17.254 | 2.060 | 605.385 | 19.459 |
| Compile linked logo cache and verify | 9.688 | 2.349 | 284.625 | 22.890 |
| Apply spans, fsync, reparse and readback | 0.034 | 0.035 | 0.054 | 0.055 |
| Other pipeline overhead, including cache PNG preparation | 0.034 | 0.032 | 0.783 | 0.785 |
| **Total worker pipeline** | **41.719** | **10.176** | **1373.324** | **70.077** |
| GUI mapping dialog construction, separately timed | 0.027 | 0.027 | 0.244 | 0.202 |

### Selected function costs, seconds

These are **exclusive elapsed seconds summed across workers**, not CPU seconds and not additive to the parallel wall total. Nested instrumented functions are subtracted from their parent. Uninstrumented work remains outside these categories. In particular, `verification` includes extraction, ownership/reparse gates and explicit stream validation; it is broader than H7A decode alone. `ps3_decode` wraps bundle reading, so includes ZIP/manifests as well as codec work. Parallel contention can increase summed elapsed time even while wall time falls. Call counts and exact values are in the JSON reports.

| Instrumented stage | 1 before | 1 after | 32 before | 32 after |
|---|---:|---:|---:|---:|
| PS3 ZIP/decode | 0.143 | 0.140 | 1.980 | 1.837 |
| Source H7A block decode | 0.963 | 0.866 | 27.132 | 35.424 |
| Region mask base encoding / shade projection | 16.082 | 1.369 | 394.281 | 92.537 |
| Mip regeneration | 4.607 | 1.820 | 106.747 | 97.992 |
| Greedy H7A | 8.069 | 0.110 | 435.816 | 12.472 |
| Optimal H7A | 0.818 | 0.439 | 53.666 | 60.512 |
| Verification / extraction / reparse | 5.466 | 4.189 | 242.987 | 492.513 |
| Remaining fit-ladder overhead | 0.022 | 0.018 | 0.721 | 0.818 |

This confirms the 66.1 lesson that Python H7A and repeated fitting are expensive. Its approximately 13 seconds per 1.4 MB block is historical evidence, not a constant: shift, data, cache hits and attempted shades change the work. The 32-crest original run spends 435.816 summed seconds in greedy H7A; the new run spends 12.472. Optimal was already native and therefore does not gain the same direct encoder speedup.

## Implementation and byte boundaries

- Added an exact historical **greedy mode** to the reviewed C helper. Using its optimal mode in place of a greedy first fit would change package bytes, so the two ladder rungs remain separate. The new mode retains exact three-byte candidate keys despite hash collisions, candidate limits, usable-candidate counting, farthest-distance ties, and the historical maximum-length early break. Both modes forbid `length > distance`. Native streams are checked for legal history, exact length and exact decode before acceptance.
- `tools/apf_logo_patch.py` uses that mode for greedy blocks at least 4 KiB and the original optimal mode for the optimal rung. The existing field-art platform/file/symlink/link-count/size/permission/hash predicate still controls execution. Failure, timeout, invalid output, or missing helper selects Python. The Python greedy matcher now compares slices without per-byte Python iteration. The portable optimal transcription retains the C helper's 512-candidate cap, hash collisions, three length trials and strict cost ties. This supplies the historical native-enabled bytes on platforms where H5 previously had a greedy-only fallback. Native Windows/macOS execution is UNWITNESSED; forced Python execution was proved here.
- Independent crest measurements, package builds and changed cache targets use a spawn process pool bounded by affinity, CPU quota, available memory, and 32 workers, reserving a CPU when possible. A lone crest can share a small pool across independent mip levels. Crest workers never spawn nested pools. Results are consumed in deterministic request order. Frozen entry-point startup calls `multiprocessing.freeze_support()`.
- Decoded DDS/GTF sources are cached by content, returning independent images. Bounded caches also retain decoded Xbox bases, encoded bases/mips, fit measurements, streams, verified package results and compiled cache layers. Transport uses checked tiling permutations, exact integer quantization and byte-stride channel operations. No interpolation, alpha, swizzle, ownership or allocation rule changes. Caches are in-process and bounded, not a persistent disk cache.
- Repeated unchanged package builds re-read current source bytes and hash both masks, policy and source identity before reusing a verified result. Source changes with the same size/mtime invalidate reuse. Receipts are copied to avoid mutation through callers. The linked cache likewise keys its compiled results by current source content and desired masks. Source validation and final package checks remain active on warm paths.
- Import, staging and game build run through the existing background task with queued Qt progress signals and a cancel event. Mapping row updates use a read-only hash snapshot; accepting/staging rehashes actual images. Cancel is checked between crests and before more submissions/results. Already-running crests finish and are joined, so cancellation is not instantaneous. Staging undoes edits completed by that import when cancelled. Build writes still use the existing temporary output/cleanup path. An offscreen test proves Qt timer events continue while the background operation runs and cancellation reaches the worker. A child-raised `TimeoutError` is propagated rather than mistaken for an unfinished future.

The helper is **mode 0755**, one link, **18,568 bytes**, SHA-256 **`d081d19c0078f768d2cb935732c910945c55d372dd9e1cc2b3e16ef9cfcf86a0`**. It was compiled with `cc -O3 -std=c99 -Wall -Wextra -Werror -s`. Its original optimal mode compares byte-for-byte with the original 14,472-byte helper (`9061866e31f1a2930eceaa4fb8652ef1b7aa9b04cbce0174cc0eae125f8e49ab`). The added C mode and new artifact pins require integration review; the exact acceptance rules were retained.

## Output proof and regression results

`reports/b69_j10/synthetic_parity.json` records complete `[1, 32]` comparisons, explicitly checking run and package counts, all package hashes and fit receipts, complete written crest archive hashes, and linked-cache directory/payload hashes. No output bytes differ. The one-crest ladder package SHA-256 is `bbc908620a16044bb90a15783ebf2d47183cbcb2591d2b6fccecc729c0287319`. All 32 individual hashes are retained in the before/after reports. The fast synthetic package test has a separate old-writer golden SHA-256 `588d4a528a4a42fa207ba900d004f45ad5c067d9561d4a8ab423a2fce166eaeb` for a full 512×512 first-fit pair, including forced Python compilation.

`tools/apf_ps3_byte_parity.py` compares the saved original writer against native and forced-Python current output on the **read-only retail outer entries 36, 1133 and 712** already exercised by existing tests. It compares entire packages, not just decoded pixels. The linked cache comparison covers retail catalog 1. Retail was present, so no retail comparison was skipped. When absent, the script reports the exact missing `APF_RETAIL_0A`/default path; existing retail tests retain their precise `SkipTest` checks.

| Retail target | Before s | Native after s | Forced Python s | Entire package SHA-256 |
|---|---:|---:|---:|---|
| Outer 36 | 20.901 | 1.978 | 2.610 | `14d1103edf1fc24643966cbe7a39d3615e00e1a6a727b3ac5619678e518d86fd` |
| Outer 1133 | 14.469 | 1.571 | 2.435 | `542586ada59db9882fafc6970168751a17ca4e5cde7dbd7bf62026bed4795495` |
| Outer 712 | 6.530 | 1.320 | 2.432 | `e461868b777376a87923746dfa27a359fb1e00ab854abf72d10da4fd7d372456` |

Retail linked-cache build: **19.072 → 2.061 seconds cold, 1.264 seconds warm**, identical directory and payload. These retail masks fit at the greedy first rung. The synthetic 32-crest benchmark exercises the subsequent optimal/shade rungs. Separate native parity compares **45 original-vs-new optimal streams and 135 original-Python-vs-native greedy streams**, across all shifts 1–15 and candidate limits 1/64/128. Fast tests separately compare portable optimal bytes with native, illegal-match refusal, helper drift/failure/timeout fallback, mip order, all endian modes, cache invalidation, real session/compiler integration, cancellation rollback and Qt responsiveness.

Exact retail/native proof commands (the reference extraction is below):

```sh
PYTHONPATH=.:tools python3 tools/apf_ps3_byte_parity.py --reference-writer /tmp/b69-j10-reference/writer.py --reference-cache /tmp/b69-j10-reference/cache.py --reference-helper /tmp/b69-j10-reference/helper --report reports/b69_j10/retail_parity.json
PYTHONPATH=.:tools python3 tools/apf_ps3_byte_parity.py --reference-writer /tmp/b69-j10-reference/writer.py --reference-cache /tmp/b69-j10-reference/cache.py --reference-helper /tmp/b69-j10-reference/helper --native-only --report reports/b69_j10/native_parity.json
```

Observed stdout: `Retail outer 36: original = native = forced Python`, likewise 1133 and 712; `Retail linked cache: original = native = warm`; `Native equivalence: 45 optimal + 135 greedy cases`.

## Reproducing the timings

Run from the repository root. These are offline diagnostic tools, not release inputs. The reference code and native helper come from this job's base, not from an assumed installed version:

```sh
python3 - <<'PY'
from pathlib import Path
import subprocess
ref = Path('/tmp/b69-j10-reference')
ref.mkdir(exist_ok=True)
base = 'c2489fcadfe412e0ed0afe20d8654bdc3170bba2'
for path, name in (
    ('tools/apf_logo_patch.py', 'writer.py'),
    ('tools/apf_logocache_patch.py', 'cache.py'),
    ('mod_editor/apf_studio/ps3_texture_bundle.py', 'bundle.py'),
    ('mod_editor/apf_studio/ps3_texture_bundle_qt.py', 'bundle_qt.py'),
    ('tools/apf_h7a_optimal', 'helper'),
):
    (ref / name).write_bytes(subprocess.check_output(['git', 'show', f'{base}:{path}']))
(ref / 'helper').chmod(0o755)
PY
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 tools/apf_ps3_speed_benchmark.py --reference-dir /tmp/b69-j10-reference --include-cache --counts 1 32 --report reports/b69_j10/before_complete.json
PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 tools/apf_ps3_speed_benchmark.py --parallel --include-cache --counts 1 32 --report reports/b69_j10/after_complete.json
```

Fixture generation is outside the timer, caches are cleared at the start of each counted case, and the whole 1/32 run pair is written incrementally to JSON. Only compare after both reports contain exactly `[1, 32]`. The benchmark reproduces the original greedy-vs-optimal selection by loading the original modules and helper; it does not approximate the baseline by disabling today's native path.

## What remains slow and what needs a witness

**PROVED:** in the final 32-crest run, measurement is 20.289 seconds, package compilation 19.459 seconds and linked-cache compilation 22.890 seconds. Safe verification dominates the selected accumulated function costs: the new native results are checked explicitly as well as at the existing independent package gates. Spawn/IPC, per-process caches and repeated source validation also cost time. Live retail inventory reads all destination sources, unlike the small synthetic archive. PNG staging and full-folder disk copying are not accelerated by the encoder. The portable optimal path retains exact bytes but can be much slower than C for difficult art; there is no Windows/macOS speed measurement here.

**HYPOTHESIS for Aszemple:** a multi-crest import/build should spend substantially less time fitting and compiling, show each completed crest, remain responsive, and let him cancel before further crest work. Rebuilding unchanged art in the same studio process should reuse compiled results. The exact speedup on his bundle, cancellation feel on his machine, packaged Windows/macOS startup, and subsequent game loading all need witnesses.

No emulator, display session, audio, network, console signing, roster change, preset change or new capability was used. **Every in-game outcome remains UNWITNESSED**, including logo colour/alpha, six-mask palette behavior, mip appearance at distance, roster slot binding and game loading. Aszemple/Noah should import the same bundle, note import/build times and cancellation behavior, then load the resulting game and inspect selected helmets close up and at distance.

`df -h /` reported **76 GB available before and after the work**, already below the context's 80 GB floor. No complete disc or game-folder build was made. The benchmark/parity scripts use small synthetic temporary files and read retail directly. The existing mandatory writer test suites did create their own temporary approximately 1.1 GB `0A` copies and cleaned them up; this is a disk-floor exception, not a claim that no volume copy occurred. No retail, reporter or generated texture/package bytes are committed.

## Integration handoff

Registry rows added: **0**. No protected implementation file changed. `WIRING.md` provides **two exact protected packaging size/hash replacements** for the changed helper, in `check_apf2k8_mod_studio_release.py` and `check_apf2k8_mod_studio_runtime.py`. The owned field-art helper predicate already has those pins. No allowlist changes are required. Protected packaging gates are **not claimed green** before those handoff changes are integrated.

`python3 packaging/repin.py --apply` was run for the APF writers and reported `applied 0 pin update(s)`; it is rerun last before the final explicit-path commit. The helper remains executable. The changelog bullets are under the existing `## 0.1.0-alpha.90 — beta 69` heading and quote Aszemple.

## Standalone tests

Each suite below was run as `PYTHONPATH=.:tools QT_QPA_PLATFORM=offscreen python3 <path>`, with plain unittest and no pytest. Exact command strings, exit codes and test timings are in `reports/b69_j10/tests/results.json`; individual stdout/stderr logs are beside it. The final runs contain **295 tests: 292 passed, 3 existing skips, 0 failures** across 21 suites. The two new synthetic suites complete in about 4 and 11 seconds on this host.

| Standalone path | Tests | Output |
|---|---:|---|
| `tests/apf_h7a_no_overlap_test.py` | 4 | `OK` |
| `tests/apf_h7a_optimal_is_bounded_test.py` | 4 | `OK` |
| `tests/mod_editor/test_apf_all_crest_slots.py` | 15 | `OK` |
| `tests/mod_editor/test_apf_b69_build.py` | 1 | `OK` |
| `tests/mod_editor/test_apf_crest_budget_import.py` | 12 | `OK` |
| `tests/mod_editor/test_apf_crest_fit.py` | 10 | `OK` |
| `tests/mod_editor/test_apf_field_art_patch.py` | 26 | `OK (skipped=2)` |
| `tests/mod_editor/test_apf_helmet_crest_design_product.py` | 13 | `OK` |
| `tests/mod_editor/test_apf_helmet_logo_regions.py` | 12 | `OK` |
| `tests/mod_editor/test_apf_logo_patch.py` | 18 | `OK` |
| `tests/mod_editor/test_apf_logocache_patch.py` | 14 | `OK` |
| `tests/mod_editor/test_apf_package_map_writer.py` | 40 | `OK` |
| `tests/mod_editor/test_apf_ps3_speed.py` | 13 | `OK` |
| `tests/mod_editor/test_apf_ps3_speed_packages.py` | 6 | `OK` |
| `tests/mod_editor/test_apf_ps3_texture_bundle.py` | 28 | `OK` |
| `tests/mod_editor/test_apf_ps3_texture_bundle_qt.py` | 4 | `OK` |
| `tests/mod_editor/test_apf_studio_core.py` | 9 | `OK (skipped=1)` |
| `tests/mod_editor/test_apf_studio_safety.py` | 27 | `OK` |
| `tests/mod_editor/test_apf_team_art.py` | 10 | `OK` |
| `tests/mod_editor/test_apf_team_art_qt.py` | 6 | `OK` |
| `tests/mod_editor/test_apf_team_logo_gui.py` | 23 | `OK` |

The skips are precise and pre-existing: two practice-overlay recompression tests in `test_apf_field_art_patch.py` require `APF_FIELD_ART_SLOW=1`; the unrelated extract-xiso pin test in `test_apf_studio_core.py` skips because its gitignored vendored Linux/Windows extract-xiso binaries are absent. No J10 retail crest/cache test skipped. Native helper tests ran here; on a host without the reviewed Linux helper, the native-only comparison reports that exact reason while portable tests still run.

Existing standalone retail round-trip commands also passed:

```sh
PYTHONPATH=.:tools python3 tests/apf_logo_patch_test.py --report reports/b69_j10/logo_roundtrip.json
PYTHONPATH=.:tools python3 tests/apf_logocache_patch_test.py --report reports/b69_j10/logocache_roundtrip.json
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -m mod_editor.apf_studio --version
```

Output: `APF_LOGO_ROUNDTRIP_PASS entry=36 file=1 copied_volume=false`; `APF_LOGOCACHE_ROUNDTRIP_PASS catalog=1 copied_volume=false`; the studio reports `0.1.0-alpha.90`. `git diff --check` and warning-as-error C compilation passed. These checks establish offline data and UI behavior within the stated test bounds, not game behavior.
