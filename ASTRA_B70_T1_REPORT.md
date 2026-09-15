# Beta 70 T1: helper-disabled equipment import speed and project open

## Delivery status

Implemented in the granted owners, with byte goldens recorded **before** production edits.
**Apply WIRING.md section 0 before claiming the completion-dialog wall is fixed.** Its two
protected GUI/feedback hooks are supplied as exact, executed code. The shared formatter is
implemented and tested here. Producing measured **digit** retry suggestions still requires
protected digit-writer/preview work described in WIRING section 2. Equipment suggestions remain
measured and usable. No Windows helper binary or CI change is supplied.

All in-game outcomes are **UNWITNESSED**. Coach Edwards' exact artwork/project and Windows
machine were not available. No full-disc build or hour-long customer workload was reproduced.

Branch: `astra/b70-t1-build-speed`, base `df9b9dcf`. The ordinary worktree already had that
branch name. Its shared Git directory resolves outside the writable workspace, so commits use
`/tmp/astra-b70-t1.git` and a portable bundle. No shared Git metadata, other worktree or remote
was written. `d208076c` is the pre-change baseline/golden commit. See Delivery below for the
implementation/evidence commits and integration command.

## Facts verified first

Read ASTRA_CONTEXT, triage rows 2/3/4/14/15 and Carried, and the beta-69 J1/A1 and beta-68 T1
reports. Opened the actual `2k5-bugs_b8ee84b0_4.jpg` attachment outside the repository:
Windows taskbar, the selected Shoes 04 Mud / Tennessee Titans Home row, and
**“Checking equipment artwork and available space • 4051 s”** are visible.

- **PROVED:** that status string is emitted inside `Nfl2k5StudioFacade.replace_equipment_texture`,
  immediately before `stage_equipment_import`. The 4,051-second photo is one equipment **import**.
  Noah's row-15 “It's just a little slow to build?” reading is incorrect for that photo.
- **PROVED:** beta 69 tries eight palette limits; at each rung it tries original/10/11/12 offset
  geometries, interleaving greedy and optimal. Optimal receives a 4 MiB ceiling and finishes misses.
  The failure path can then try full ladders at half and quarter size. In the unchanged striped
  fixture, `stage_equipment_import` compiles the same TSET twice, for the selected target and the
  complete-project preflight. The before profile observes both calls.
- **PROVED:** `_optimal_helper()` admits Linux x86-64 only. Windows **and macOS** run the Python
  parser, whose default comparison budget is 50,000,000. “Windows-only” in the triage is therefore
  too narrow as a platform statement. No MinGW compiler is present, and
  `packaging/setup_reviewed_helpers*` is absent.
- **PROVED:** project loading invokes equipment preflight through the integrated session hook and
  canonical `read_project(..., equipment_index=...)`. The original facade compares path/file-ID/
  size/mtime/ctime snapshots before and after this work; the identity object has no content hash.
- **PROVED:** row 3's nine digit records come from `QualityBudgetError`, not `EquipmentFitError`.
  Those digit attempts do not currently contain measured encoded sizes or checked smaller-size
  suggestions. The two error classes cannot honestly supply interchangeable measurements.
- **Reporter evidence, not a local measurement:** “took 89 mins” explicitly describes a separate
  successful build. It remains a build report; this job does not relabel it as an import.
  Row 14's “all of a sudden it worked” is consistent with a long search but does not prove its cause.
- Aszemple's carried “very slow to import and build the logos from the PS3 Bundle” is the same
  helper/fallback class of concern. No APF owner was changed or APF performance claimed here.

## Measurements before and after

Python 3.12.3, Linux 6.8.0-139 x86-64, 32 logical CPUs; exact environment is in
[machine.json](reports/b70_t1/machine.json). Every import measurement patches
`nfl2k5_equipment_lz._optimal_helper` to return `None` with `unittest.mock.patch.object`.
No global environment switch was used to obtain these import measurements.

The fixture builds a synthetic TSET with three shared-index references, real mip palettes,
real VC-LZ wrapper/scratch constraints, a real `StudioSession`, PNG intent and atomic staging.
Its sock is 256×256; its shoe is 64×64. It is a bounded synthetic package, not the retail catalog's
complete global fanout and not Coach Edwards' unavailable pixels. Fixture creation is outside the
clock; the complete `stage_equipment_import` call is inside, including preflight and staging.
Before files are in the baseline commit; after timings below come from the final recorded test run.

| Synthetic case | Beta 69 seconds | Beta 70 seconds | Repeated import seconds | Outcome |
|---|---:|---:|---:|---|
| sock256_stripes | 14.020934 | 2.199036 | 0.008516 | fit |
| shoe64_stripes | 0.380868 | 0.129540 | 0.002696 | fit |
| shoe64_diagonal | 0.438737 | 0.152072 | 0.002980 | fit |
| shoe32_tight | 0.163211 | 0.054568 | 0.002388 | fit |
| shoe32_noise_refused | 11.509430 | 3.872293 | refused | refused |
| shoe32_noise_half | 6.784348 | 1.392673 | 0.003145 | fit |
| shoe32_noise_quarter | 1.975379 | 0.637522 | 0.002485 | fit |

The noisy full-size 32×32 fixture still refuses: a **464-byte budget, 666 bytes required,
202-byte shortfall**. Its checked half-size suggestion remains **16×16, two colours, 456 bytes**.
Six fitting cases retain the complete beta-69 compressed span SHA-256, including wrapper,
fill and padding. The test prints every measured import time and asserts **under 30 seconds per
case** with the helper disabled. This is a generous CI bound on this corpus, not a Windows SLA.
The original sock measurement is 14.021 s rather than 67 minutes; no claim is made that a small
synthetic input reproduces the unavailable customer workload.

### Pure-Python parser, separately measured

All three streams preserve their pre-change SHA-256. Timings include the independent decode gate.

| Synthetic stream | Before seconds | After seconds | Encoded bytes | Bytes |
|---|---:|---:|---:|---|
| flat | 2.365820 | 0.281002 | 2,131 | identical |
| repeated | 1.320892 | 0.422811 | 3,259 | identical |
| palette | 0.102443 | 0.127638 | 73,737 | identical |

Flat and repeated inputs improve materially. The low-repetition palette stream is slightly
slower (about 0.025 seconds); this is not a claim that every byte distribution improves.
[Before profile](reports/b70_t1/beta69-profile.txt): 22,037,391 calls / 18.890 profiled seconds,
12.350 seconds in the two optimal parses, and 15,033,568 `min` calls. The
[after profile](reports/b70_t1/beta70-profile.txt) observes one compile, 4,519,221 calls /
2.958 profiled seconds. Profiles perturb wall time and are not substituted for the table timings.
The after profile was recorded after the parser/cache implementation; later summary/cache-bound
edits do not alter its striped-art parse.

### Reproduction commands

Baseline outputs were captured before any production edit, by this exact driver shape on the
unchanged writer; `d208076c` retains the fixture and original JSON results:

```bash
PYTHONPATH=.:tests/mod_editor python3 -u - <<'PYBASE'
from b70_equipment_fixture import CASES, stage_case
import json
for case in CASES:
    print(case[0], json.dumps(stage_case(case)), flush=True)
PYBASE
```

Final proof and measurement command:

```bash
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 -u tests/mod_editor/test_b70_t1_build_speed.py
```

The before writer SHA-256 is `574a1a610a7733b0a71b494a3604599510b0ec6cf069fdde1c5e3cc255d7cb71`;
the before LZ module is `3a0a3594115c227bafa2890153522c4d7be5377e013a15d56d57d4b71353b5a9`.
The six span goldens are literal constants in the regression test, captured from that writer,
not regenerated from the new code. JSON preserves the original measurements, selected palette
attempts, decoded hashes and spans. No retail payload is in those fixtures or records.

## Search changes and their proofs

1. **Preserve beta 69's winning order.** At each palette rung, process the source geometry then
   the remaining 10/11/12-bit geometries. Greedy stays ahead of optimal **within each geometry**.
   A later greedy fit must not replace an earlier optimal fit. No successful palette, mip,
   quantizer, tie-break, fill or transport choice is intentionally changed.
2. **A proved greedy margin, not a lossy heuristic.** Let G/O be greedy/optimal token bit costs.
   Charge a greedy token to the optimal token containing its start. An optimal literal receives
   at most 17 bits against its 9. A match receives one greedy match, except a remaining suffix of
   two bytes can receive a literal plus another token, at most 26 bits against 17. A longer
   suffix is a valid non-overlapping match at the same distance and one greedy token reaches its
   end. Therefore **G ≤ (17/9) O**. The greedy ceiling is the greater of budget+1,024 and this
   rounded ratio bound. Exceeding it proves optimal cannot fit; an arbitrary small margin would
   reject some valid old imports. The test checks this bound and exact old selection across 116
   deterministic source/offset cases. Cached streams from a larger budget undergo the same check.
3. **Optimal gets budget+512.** The reversed Python search combines nearest-match finding and
   dynamic-programming choices. A token crossing the current boundary ends within the next L
   bytes, where L is the format maximum. The cheapest already-computed suffix over those ends,
   plus an optimistic `floor(17 * preceding_bytes / L)` prefix cost, is an admissible lower bound.
   Stop if that bound exceeds budget+512. The far-miss test visits **1,022 of 65,536** positions,
   rather than completing the reverse search. Errors distinguish exact sizes from lower bounds;
   near-bound measurements remain exact where established.
4. **Process-lifetime parse cache.** The key is SHA-256 of the complete quantized candidate plus
   stream tag and offset bits. This binds source pixels, palette values, mip sizes, descriptors
   and every retained sibling byte. Equal candidates at different palette limits also share a
   parse. Entries retain successful streams and proved misses until process exit; repeated
   suggestions/imports at the same budget do not reparse. A changed budget may need more evidence
   than a prior bounded miss. This cache retains encoded results, not input pixel buffers; its
   memory grows with distinct candidates during a long session, as required for lifetime reuse.
5. **Monotone stopping uses a palette-invariant bound.** Changing palette values does **not** make
   compressed length monotonic. The safe bound is `9 + ceil(17 * decoded_bytes / (8 * 66))`, even
   granting maximum-length matches at byte zero. Every remaining palette rung has the same
   allocation length, so if this floor exceeds the slot, all those rungs are impossible.
   The test proves zero parse calls on a valid synthetic TSET with three independent appended
   chains that exceeds this bound. Another golden traverses all eight palettes and fits at two
   colours, guarding against the incorrect “first overflow means stop” shortcut.
6. **One suggestion ladder.** A cheap dimension-only bound screens half/quarter sizes, followed
   by at most one real smaller-size ladder for one edited reference. That full-group check
   retains all other edits and all decode/scratch/sibling gates. A repeated requested import and
   suggestion performs no additional greedy/optimal parses in the test. If the one checked size
   fails, the message says no fitting alternative was established; it does not claim that every
   untried smaller image is impossible. Quarter size remains an explicit import choice. Beta 69's
   exhaustive guarantee of finding the largest fitting smaller suggestion is intentionally not
   claimed by this bounded suggestion policy.
7. **Exact parser speedup.** Compact, distance-window-bounded three-byte hash chains retain
   nearest order. `bytes.rfind` finds a full non-overlapping maximum match in C; occurrence ranks
   charge exactly the original candidate count. Partial comparisons use C prefix checks and
   bisection. Short array slice/min/index operations replace the Python length loop while keeping
   literal ties and the earliest winning length. No arbitrary chain truncation discards matches.
   The reviewed native helper remains untouched; its existing cross-offset equivalence suite passes.

Every emitted span still passes independent decode, sibling/pointer checks and the existing
`nfl_vc_lz_fill` overlap guard. Wrapper +0x14 remains retail. No XBE writer, allocation, game option,
app preset, pixel quantizer or equipment ownership rule changed.

## Project open

Imports and complete-equipment preflight share the default staged compile cache. Canonical
project open explicitly obtains that same cache. Explicit per-build caches remain separately
owned, preserving beta 68's build/receipt workflow.

Persistent entries live at `.nfl2k5-equipment-stage-cache` beside the source index, using the
existing `CompileCache` bounded JSON/checksum/atomic-replacement implementation. Keys bind
complete target-span hash, geometry, row descriptors/palette pins, authored RGBA/mode/scale/origin,
and compiler/codec/quantizer source hashes. Hits still reread and hash current art and target;
disk hits reparse the stored span and validate decode hashes, allocation and overlap scratch.
No pickle, code serialization or cached retail payload enters a shareable project. In-memory
compiled/artwork limits are 128/32; disk entries use the existing 64 MiB/1 GiB entry/cache limits.

**PROVED:** real import → save archive → new session → open; repeat with memory cleared; then
launch a **new Python interpreter**. `_compile_group` is replaced with a raising sentinel during
all unchanged opens, and none calls it. Changed pixels compile once. A changed target descriptor
invalidates the key and fails its source-layout gate. Corrupt disk JSON recompiles. Missing,
evicted, compiler-changed or unavailable cache data gets a bounded preflight, never blind trust.
The test output includes the open timings and “new interpreter: no fit search”.

The facade hashes the project through a bounded binary handle before/after loading. The original
file-identity check remains, and same-size content changes with restored mtime also refuse.
Messages list the exact path, byte size, nanosecond mtime, SHA-256, file ID and ctime on both sides,
plus which fields differ and a concrete reopen/save-or-sync next step. A deleted file explicitly
reports unavailable after-values. Four race cases prove that the active session remains and the
candidate is discarded. A binary-open seam checks CR/LF and control-Z bytes.

**HYPOTHESIS:** sync software or another writer may explain Coach Edwards' original identity
refusal. His project was unavailable, so no particular external program or false-positive cause
is asserted. Shorter local preflight reduces the window but does not prove his Windows refusal fixed.

## The kept-retail summary and protected work

`BuildResult.message` and reusable `summarize_kept_retail` produce one line per asset identity,
with page, part, uniform set and texture. Duplicate diagnostics for one asset collapse. Measured
shortfalls and checked dimensions/colours appear when present; shared next steps appear once.
Original row dictionaries/messages/attempts remain unchanged in the receipt. Historical unknown
measurements are labeled unmeasured. Current digit failures establish at least one byte over,
not an exact shortfall. Already-source-equal equipment is labeled as such.

**PROVED:** nine distinct synthetic digit assets produce nine short lines, one shared next step,
and unchanged full receipt rows; duplicates collapse. A real `EquipmentFitError.suggestion` is
formatted with its 202-byte miss and checked 16×16/two-colour retry. An unmeasured digit is not
silently given that equipment suggestion.

**Required before release:** the actual legacy Studio modal and Build-panel feedback currently
have their own row concatenation, in protected `studio_qt.py` and `build_feedback.py`. WIRING
section 0 supplies exact replacements and the diagnostics test executes both supplied snippets,
including the real Qt completion method with mocked dialogs. They are **not applied** here.
Section 2 identifies the separate protected digit measurement/retry work and its exact insertion
points. Do not state that actual digits now have measured, actionable smaller-size suggestions.
The changelog bullets are intended for the integrated stack with section 0 applied.

## Validation

Every listed test was run standalone with plain Python and `PYTHONPATH=.`;
Qt used `QT_QPA_PLATFORM=offscreen`. No GUI display, emulator, audio or network was used.
The exact command for each row and its exit code are in [tests.json](reports/b70_t1/tests.json).
The standard prefix is:

```text
PYTHONPATH=. QT_QPA_PLATFORM=offscreen python3 tests/mod_editor/<filename>
```

| Test file | Exact result footer | Output |
|---|---|---|
| `test_nfl2k5_equipment_texture_chain.py` | Ran 19 tests in 3.333s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_texture_chain.log) |
| `test_nfl2k5_equipment_import.py` | Ran 13 tests in 1.943s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_import.log) |
| `test_nfl2k5_equipment_consumers.py` | Ran 19 tests in 32.269s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_consumers.log) |
| `test_b69_j1_fit.py` | Ran 5 tests in 5.500s; OK | [full output](reports/b70_t1/test_b69_j1_fit.log) |
| `test_b69_j1_build.py` | Ran 5 tests in 2.628s; OK | [full output](reports/b70_t1/test_b69_j1_build.log) |
| `test_b69_j1_wiring.py` | Ran 7 tests in 7.740s; OK | [full output](reports/b70_t1/test_b69_j1_wiring.log) |
| `test_b68_t1_build.py` | Ran 6 tests in 5.791s; OK | [full output](reports/b70_t1/test_b68_t1_build.log) |
| `test_studio_facade.py` | Ran 11 tests in 0.020s; OK | [full output](reports/b70_t1/test_studio_facade.log) |
| `test_project_document_workflow.py` | Ran 13 tests in 1.391s; FAILED (errors=6) | [full output](reports/b70_t1/test_project_document_workflow.log) |
| `test_nfl2k5_equipment_texture_native.py` | Ran 7 tests in 0.239s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_texture_native.log) |
| `test_nfl2k5_equipment_retail_roundtrip.py` | Ran 2 tests in 18.977s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_retail_roundtrip.log) |
| `test_nfl2k5_equipment_import_wiring.py` | Ran 6 tests in 0.878s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_import_wiring.log) |
| `test_nfl2k5_equipment_scope_wiring.py` | Ran 3 tests in 2.663s; OK | [full output](reports/b70_t1/test_nfl2k5_equipment_scope_wiring.log) |
| `test_2k5_uniform_equipment_export.py` | Ran 13 tests in 1.086s; FAILED (errors=6, skipped=2) | [full output](reports/b70_t1/test_2k5_uniform_equipment_export.log) |
| `test_b69_j1_native.py` | Ran 1 test in 1.470s; OK | [full output](reports/b70_t1/test_b69_j1_native.log) |
| `test_provider_integrity.py` | Ran 7 tests in 9.385s; OK | [full output](reports/b70_t1/test_provider_integrity.log) |
| `test_b70_t1_build_speed.py` | Ran 10 tests in 18.270s; OK | [full output](reports/b70_t1/test_b70_t1_build_speed.log) |
| `test_b70_t1_diagnostics.py` | Ran 5 tests in 0.270s; OK | [full output](reports/b70_t1/test_b70_t1_diagnostics.log) |
| `test_nfl2k5_build_service.py` | Ran 28 tests in 0.171s; OK | [full output](reports/b70_t1/test_nfl2k5_build_service.log) |
| `test_hotfix63_digit_budget.py` | Ran 5 tests in 0.025s; OK (skipped=3) | [full output](reports/b70_t1/test_hotfix63_digit_budget.log) |
| `test_b66_coach_digits.py` | Ran 12 tests in 6.500s; OK (skipped=1) | [full output](reports/b70_t1/test_b66_coach_digits.log) |

The two failing older GUI suites reach `StudioMainWindow(eager_pages=True)` →
`studio_qt.py::_filter_unif_color_sets` → `nfl2k5_uniform_catalog.py:570`, then fail resolving
**`reports/assets`**, which is absent from this worktree. Six setup errors occur in each suite,
before any new import/open/summary path. No private catalog was fabricated or copied into the
repository, and no test was weakened or relabeled passing. The export suite also reports its
existing two skips. Other skipped classes identify missing private inputs in their logs.

The existing equipment-import fault-injection test needed isolation from the new process-wide
cache: its `setUp` clears the staged compile cache before replacing the rebuild function with a
refusal. Its complete 13-test file passes. No assertion or safety gate was removed.

`git diff --check` is clean. `packaging/repin.py --apply` was run after every pinned-source edit
batch and again immediately before commits; logs are under `reports/b70_t1/repin-*.log`.
Generated changes in `providers.py` and `check_2k5_mod_studio_runtime.py` are existing hash values
only. No release exception or integrity check was broadened. Claude must regenerate the combined
cave manifest fingerprints per ASTRA_CONTEXT; no new cave or game-code allocation is requested.

## Coach Edwards' Windows witness checklist

1. Import his original striped sock and shoe at the same explicit size/scope, time each import,
   and repeat it. Report import time separately from build time. The Python path should avoid the
   old repeated full optimal searches, but his laptop timing is **UNWITNESSED**.
2. Save and reopen the project, restart Studio, and open again. Check that valid older equipment
   survives, Undo still works, and a real external file change gives the named before/after refusal.
3. After Claude applies the protected completion wiring, inspect a successful build with retained
   digits: one concise named line per asset, no fabricated size suggestion, and full receipt detail.
4. Play a game and inspect clean/mud socks and shoes near and far, for both teams. Pixel appearance,
   distortion and runtime residency remain **UNWITNESSED**; this speed change does not claim to fix
   row 5's sock distortion. No lossy art change was authorized by this job.
5. Time the separate build workload that reportedly took 89 minutes. That build and beta 68's
   402-edit/full-disc benchmark were not run here. The existing build-cache/receipt tests passed.

## Delivery and cleanup

Only synthetic fixtures and small text/hash reports were written. The evidence directory is
under 1 MiB, no retail/disc copy was created, and the filesystem had about 25 GiB free at start.
Temporary fixture directories clean themselves on every exit. The attachment, extracted source,
other worktrees and shared Git metadata remain read-only. No push.

Commits on the delivered branch:

- `d208076c`: unchanged beta-69 golden bytes, timings and profile.
- `5ec53965`: parser/search/cache/open/summary implementation, tests, changelog and protected wiring.
- The bundle tip adds this report and the complete measurement/test/repin logs.

Bundle: [astra-b70-t1.bundle](reports/b70_t1/astra-b70-t1.bundle). Its prerequisite is `df9b9dcf`.
From an integrator's writable checkout:

```bash
git fetch /home/noah/2k-worktrees/astra-b70-t1/reports/b70_t1/astra-b70-t1.bundle refs/heads/astra/b70-t1-build-speed:refs/remotes/astra/b70-t1-build-speed
```

Review/cherry-pick the delivered commits after `df9b9dcf`; apply WIRING section 0 before release.
The temporary baseline source copies and benchmark/edit scripts are removed after bundling;
the verified bundle preserves the commits independently of the temporary Git directory.
