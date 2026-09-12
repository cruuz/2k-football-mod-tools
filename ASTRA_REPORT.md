# Beta 68 T1 report

## Delivery status

Implementation and bounded proofs are complete. The requested 402-edit retail
benchmark, its full-disc byte-identity proof, the Windows timing target and the
protected release integration remain **UNWITNESSED / outstanding**. Do not report
that the one-hour or 90-minute workload is solved by measurement.

Base: `c8783a64406ce6b062a7b287173ecbe778f43df2`, branch name
`astra/b68-t1-build`. Delivery uses `ASTRA_T1.bundle` with explicit-path commits.
The checkout's real Git metadata resolves outside the writable workspace; the
bundle was made using separate Git metadata under `/tmp`, reading the base
objects without changing the main checkout or any other worktree. No push.
Implementation commit: `35c3e65f`; the second bundle commit contains the final
concurrent-output guard, tests and handoff. Existing pins were updated with
`python3 packaging/repin.py --apply` as the last source operation before each commit.

## Requested baseline and its blocker

Read `ASTRA_CONTEXT.md`, the job brief, and triage rows 7, 8, 9, 15 plus 14, 16, 17.
Coach Edwards: "my build took over 90 minutes". maumau78: "it finally build without
errors but it takes 1h", "even change one texture take forever to build". The
screenshots show 402 edits, preparation at 1959 s and final checking at 2613/3308 s.
Those are reporter observations, not local timings.

Before implementing, `df -h / /media/noah/Storage` reported 82 GB available on `/`
and 109 GB on Storage. `mkdir -p /media/noah/Storage/.b68-t1` failed with
`Read-only file system`. The sandbox permits writes only in this worktree and
`/tmp`, and approvals are disabled. No large file was placed on `/`; no retail
image was copied, edited or built. `reports/assets/` is also absent here, so the
private target catalogs needed to construct the requested mixed retail project
are unavailable. These are environment blockers, not timing evidence.

`tools/nfl2k5_b68_build_benchmark.py` can measure a supplied, prepared 402-edit
canonical project in writable Storage. It freezes inputs, records timings, hashes
each complete output, and removes private scratch outputs. `WIRING.md` gives the
command and the remaining project-generation requirement. It does not generate
the requested representative 402-edit retail project itself.

## Build changes

- **PROVED, bounded:** the build records per-edit span hashes and import artifacts,
  plus source/output identity, size, nanosecond modification/change times and input
  hashes. Its final stdout line returns the manifest SHA-256. The build service
  passes that exact digest to `verify --receipt-sha256`. This verifier reopens the
  files, validates the receipt, current project inputs, artifacts, written spans,
  difference runs, XDVDFS directory and default.xbe. It never invokes a compiler.
  Its return flags say that full byte identity was checked during build and that
  importers were not independently reconstructed in this pass.
- **PROVED, bounded:** one complete source/output comparison remains in `build`.
  It proves unchanged bytes in every gap, including padding outside directory
  entries, while calculating the whole output hash. Source/output stat snapshots
  and ownership checks bind that result to publication. The separate initial
  whole-source hash and redundant final pair of whole-image hashes were removed.
  Historical verification without a returned build-receipt hash still recompiles
  and performs the full proof; its compile cache is explicitly disabled.
- **PROVED, bounded:** `.nfl2k5-compile-cache` lives beside a canonical project or
  under the persistent StudioSession root, outside disposable build staging.
  Keys bind RGBA pixels including alpha/dimensions, source file bytes, target,
  options, compiler/helper bytes and canonical input/report hashes. Raw input
  hashes preserve receipt provenance, so a harmless PNG re-encoding can miss the
  cache. Shared TSET/scene inputs invalidate together. Independent uniform cache
  misses keep the existing bounded process pool; hits are never scheduled.
  Successful results and kept-retail digit decisions can be reused. Cache files
  use checksummed JSON, atomic replacement and bounded entries (64 MiB) with a
  1 GiB cache budget. Corrupt/unavailable cache entries fall back to compiling.
  No pickle or executable cache serialization. No shared project includes this
  private derived cache. Adding/reordering edits or changing compiler/catalog pins
  can conservatively invalidate additional entries; one changed PNG at a stable
  target invalidates its compilation unit.
- **PROVED, bounded:** the C equipment optimal parser preserves Python's candidate
  order, nearest-match tie breaking, no length greater than distance, 9/17-bit
  token costs, bounds and encoded bytes. It uses a hash chain limited by the VC-LZ
  distance window and the same comparison budget. Every native result passes the
  existing independent decode and consumed-length gate. Missing, unsupported,
  rejected or failing helpers use the original Python parser. The delivered,
  hash-pinned executable is Linux x86-64 only; Windows/macOS native acceleration
  remains UNWITNESSED. Built with GCC 13.3.0, `-O3 -std=c99 -Wall -Wextra -Werror`;
  mode 0755. C source and exact release exception are supplied in WIRING.

Scene/model cache grouping is implemented, but the actual codec build proof here
covers a uniform torso and equipment texture only. Audio and gameplay edits keep
their existing authorization/compilation paths. No APF file, XBE write site,
number-sheet encoder, equipment color/ownership decision or gameplay preset changed.

## Measured bounded workflow

**PROVED:** two synthetic edits, real PNG encoders, real TSET/archive layouts,
real copy/write/union check and real receipts. Fabricated small source image,
not the retail image and not a proxy for the 402-edit timing target. Baseline uses
the original visual tool from the base commit and disables the native helper;
its build and independently reconstructing verification are both timed. All
private outputs were removed. Full data: `ASTRA_T1_TIMINGS.json`.

| Run | Build s | Verify s | Total s | Cache hits / misses |
|---|---:|---:|---:|---|
| before | 1.190861 | 1.045767 | 2.236629 | not present |
| cold | 1.122404 | 0.005573 | 1.127977 | 0 / 2 |
| warm | 0.076781 | 0.005510 | 0.082290 | 2 / 0 |
| one_change | 1.212165 | 0.012636 | 1.224801 | 1 / 1 |

| Phase across build + verify | Before s | Cold s | Warm s | One change s |
|---|---:|---:|---:|---:|
| validate_source | 0.000754 | 0.000216 | 0.000211 | 0.000209 |
| prepare_project | 2.200100 | 1.098975 | 0.053905 | 1.178028 |
| bind_prepared_to_source | 0.004331 | 0.002120 | 0.002110 | 0.003647 |
| copy_artifacts | 0.013145 | 0.012244 | 0.011906 | 0.012136 |
| verify_union | 0.005896 | 0.002910 | 0.002910 | 0.007483 |
| verify_prepared_pins | 0.000410 | 0.000262 | 0.000249 | 0.000256 |
| verify_artifacts | 0.001981 | 0.000971 | 0.000946 | 0.000960 |

The JSON also records separate copy, span-write and directory/artifact phase
lines for optimized builds. Timings exclude fixture creation and the extra
comparison hash used only by this benchmark.

Baseline, cold and warm SHA-256:

```text
fd59d6db8539da7c1cadb66586635c4064f9eebf0859bdff0cb8bd50077d719f
```

One-PNG-change SHA-256:

```text
930da2fcf60859a9dcf85ef8806f573d06f213f1c70da9edd2454f7d0305d09e
```

This proves byte identity once for this bounded fixture only. Separately, the
402-key cache test observes 402 initial compiles, zero more on an unchanged pass,
and one more after changing one key. That is a cache behavior proof, **not a
402-edit image build or model/texture performance measurement**.

## Measured equipment codec

All three before/after encoded streams were byte-identical; times include Python's
independent decode gate. These use the original Python source saved before editing.

| Synthetic input | Input bytes | Encoded bytes | Python s | Native + gate s |
|---|---:|---:|---:|---:|
| repeated | 92000 | 10884 | 0.532865 | 0.018567 |
| palette | 65536 | 49531 | 0.137007 | 0.020968 |
| flat | 65536 | 7754 | 0.623876 | 0.017706 |

The deterministic native equivalence test covers all offset widths 10 through 13,
short inputs, flat bytes, repeated text, palette-like bytes and windowed patterns.
It forces failure if the native call silently falls back during this comparison.

## First-use equipment browser

maumau78: "if open uniform editor and select socks / equipment the first time you
got this error"; visiting "All Texture" first worked around it. The only functional
GUI edit is `_browse_selected_uniform_equipment`: construct its lazy workspace
before retrieving `_visual_browsers[TEXTURES]`. The complete function is repeated
in WIRING. **PROVED:** fresh offscreen StudioMainWindow, browser initially absent,
45 synthetic equipment entries, correct selected-set filter/navigation, second
click reuses the same browser and no error dialog. Retail-catalog and Windows
responsiveness retests remain UNWITNESSED.

## Team Kit comparison and summary

Coach Edwards' photo: "Imported: 0. Skipped unchanged: 78. Overwritten: 0. No project
pixels changed". The old early skip compared decoded RGBA to `baseline_rgba_sha256`
in the export manifest. Export writes the current project layer, including staged
pixels. It did **not** simply hash the source disc, and a PNG edited to different
RGBA already crossed that early skip. An unchanged save or metadata-only re-encode
correctly matched its export baseline. The photo alone does not prove which file
was edited, or which folder was imported; its original cause remains UNWITNESSED.

The old code also replayed the previous receipt after a repeated no-op import,
which could label components Imported/Overwritten when this operation changed
nothing. The importer now first compares decoded incoming RGBA with the current
project, names those identical files, and reports only this import's changes. An
untouched baseline that differs from a later destination edit is separately
labelled "Untouched since export; preserved the current project". This preserves
the existing cross-project merge behavior and digit re-encode tolerance instead
of erasing destination artwork. Details include file paths.

**PROVED:** export a kit containing staged art, edit one PNG on disk, import 1 and
skip 77, verify current project bytes, repeat with 0 imported/78 identical; then
verify that an untouched export preserves a later destination edit. Alpha and
indexed-palette edits also pass the existing synthetic kit test.

## Validation commands and results

Each command was run standalone from this worktree with `PYTHONPATH=.`. Qt runs
also use `QT_QPA_PLATFORM=offscreen`; no display, emulator, audio or network used.

```text
python3 tests/mod_editor/test_b68_t1_build.py                 Ran 6 tests; OK
python3 tests/mod_editor/test_b68_t1_ui.py                    Ran 2 tests; OK
python3 tests/mod_editor/test_nfl2k5_build_service.py          Ran 28 tests; OK
python3 tests/mod_editor/test_b661_kit_build.py                Ran 2 tests; OK
python3 tests/mod_editor/test_nfl2k5_equipment_import.py       Ran 11 tests; OK
python3 tests/mod_editor/test_nfl2k5_equipment_texture_chain.py Ran 16 tests; OK
python3 tests/mod_editor/test_nfl2k5_equipment_texture_native.py Ran 5 tests; OK
python3 tests/mod_editor/test_nfl2k5_equipment_consumers.py    Ran 17 tests; OK
python3 tests/mod_editor/test_team_kit_bundle.py              Ran 0 tests; OK (skipped=1)
python3 tests/mod_editor/test_uniform_bundle_cross_project.py Ran 0 tests; OK (skipped=1)
python3 tests/mod_editor/test_team_kit_product_integration.py  Ran 6 tests; FAILED (errors=7)
git diff --check                                             clean
```

Both skipped suites name the absent private Team Select report. The older Qt
integration suite fails with FileNotFoundError while loading `reports/assets/`,
before it can exercise the real catalog. This suite is **not certified passing**.
The new synthetic UI suite is independent of those files. Existing cross-project
repeat-receipt expectations were updated for the intentional count correction;
rerun that suite with private catalogs during integration.

The build/cache tests forbid compiler calls and full-image scans during receipt
verification, reject a wrong receipt hash and a changed byte outside written
spans (including a mutation just after the full scan), compare baseline/cold/warm output hashes, check one changed PNG invalidates
one compile, reject corrupt/symlinked caches, and prove the parallel path submits
only cache misses. Receipt hashes bind the trusted build subprocess result;
checking an unrelated historical manifest without that result still uses full
reconstruction.

Benchmark command actually run (small synthetic inputs only):

```bash
git show c8783a64406ce6b062a7b287173ecbe778f43df2:tools/nfl2k5_visual_mod_project.py > /tmp/t1-baseline-tool.py
python3 tools/nfl2k5_b68_build_benchmark.py --baseline-tool /tmp/t1-baseline-tool.py --synthetic --scratch /tmp/t1-small-benchmark --report /tmp/t1-final-build-timings.json
```

## What the reporters should see and what still needs witnessing

Coach Edwards should see the names of files actually changed by Import Edited Kit
and a separate identical-to-project list. Repeating that import should say zero
changes. His existing successful build/number-sheet witnesses remain as recorded
in triage rows 14, 16, 17; this job does not claim new in-game proof.

maumau78 should be able to use Equipment immediately without first visiting All
Textures. A repeated build should show cache reuse; changing one independent PNG
should compile only that edit. A shared equipment/scene edit recompiles its owned
span. The final check should no longer wait through a second compilation. Actual
wall time remains constrained by image copying, one full byte-identity comparison,
source pins, codecs and storage speed; no few-minute promise is measured here.

Claude must apply WIRING's protected release closure/dependency blocks, run the
packaged gate, regenerate the cave manifest as required by the handoff, and run
the full mixed 402-edit retail baseline/cold/warm/one-change comparison in writable
Storage. Reporter-machine timings, Windows/macOS helper builds, in-game texture
appearance and gameplay are **UNWITNESSED**. No retail outputs remain from this job.
