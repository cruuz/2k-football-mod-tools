"""Write the APF-5 handoff from completed, recorded gates."""
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent
suite=json.loads((folder/'suite_results.json').read_text())
assert not suite['failed_or_missing']
native=json.loads((folder/'native_receipts.json').read_text())
assert all(r['retail_literal_bytes_equal'] for r in native['native']['APF5_RESERVATION'])
records=[json.loads(s) for s in (folder/'commands.jsonl').read_text().splitlines()]
required=['strict-registry-final','provider-integrity-final','product-catalog-final','phase1-final',
          'apf-release-check-final','apf-runtime-final','repin-corrections']
checks={label:next(r for r in reversed(records) if r['log'].endswith('/'+label+'.log')) for label in required}
assert all(r['exit_code']==0 for r in checks.values())
git=['git','--git-dir=.scratch/git','--work-tree=.']
base='dc87cd0f456cf4ad4f8a384bb698d005d3255fa0'
commits=subprocess.check_output(git+['log','--oneline',base+'..HEAD'],text=True,cwd=root).strip()
check_table='\n'.join(f"| {name} | PASS | {r['elapsed_seconds']:.3f}s | [{Path(r['log']).name}]({r['log']}) |" for name,r in checks.items())
report=f'''# Beta 71 APF-5 delivery

Branch: `astra/b71-apf5-fourth-down-xenia`, based on APF-3
`{base}`. Commits use `.scratch/git`, with explicit path lists.
Bundle: `.scratch/astra-b71-apf5.bundle`; final bundle verification, commit IDs
and SHA-256 are in `.scratch/astra-b71-apf5-delivery.json` (outside the bundle to
avoid a self-referential digest). No push. No Xenia, displayed GUI or audio.
Qt ran offscreen. No SPLB/MASTER situation code or CPU Play Calling situation
table changed; APF-4 retains those owners.

## Delivered

- **Tools → CPU fourth-down triggers**: eight global settings, retail defaults,
  neutral preview, BASE/TU profile selection, separate authored patch export,
  explicit opt-in installation, status/reopen and removal. Default off; no
  preset enables it. Exact canonical payload validation and storage-root patch
  synchronization use the existing beta-67/69 delivery path.
- **Xenia Edge (recommended) and Canary**: filename detection plus explicit
  selection for renamed executables; runtime-specific config; persisted SDL
  HID backend and `--hid=sdl`; existing native Windows, native Linux/AppImage
  and Wine command forms. Legacy settings load without writes. Invalid config
  refuses before launch and a failed configuration preserves the previous
  runtime. Edge custom title-update content discovery is included.
- One new registry row, `apf2k8.playbooks.fourth_down`: **175 total / 73 APF**.
  Runtime status remains `not-tested`. Alpha.92 notes add no tester names.
  [WIRING.md](WIRING.md) describes the authorized protected-file integration.

Implementation commits before this evidence commit:

```
{commits}
```

## Addresses, data and patch contract

| Meaning | BASE | TU 1.1 |
| --- | --- | --- |
| Offensive call | `8486CE88` | `8486DB88` |
| Fourth-down chooser | `8486BD90` | `8486CA90` |
| Field-goal predicate | `8486B8E0` | `8486C5E0` |
| Punt predicate | `84866D28` | `848679F8` |
| Own-half comparison hook | `84867054` | `84867D24` |
| Draw predicate | `8485ED68` | `8485FA08` |
| Producer and flag store | `84816FF0` | `84817C90` |
| Scrimmage substitution | `8486BF90` | `8486CC90` |
| Pre-snap controller | `84836698` | `84837338` |
| Native timeout eligibility | `84934D48` | `84935C10` |
| Timeout dispatch frontier | `8488E4C0` | `8488F308` |

The chooser returns row **17 for punt, 19 for field goal**; these are not MASTER
category indices. Global draw latch: `84DBAFB0` on both profiles. Team flag:
team+`0x2C`, mask `0x200000`. The controller requests timeout strictly below the
threshold, with the draw flag active and the reviewed readiness/defense gates.

Retail settings: short cutoff **1 yard**; automatic-punt goal distance **50
 yards**; short-yardage punt slope **0.05**; fallback kick random threshold
**0.95**; FG safety margin **5 yards**; draw distance **2 yards**; draw goal
 distance **55 yards**; timeout threshold **2 seconds**. About 91.44 coordinate
units represent one yard. All eight redirected literal loads (including both
float and double FG arms) match their original retail bytes with defaults on
both images. The independent own-half limit is 4572 units.

The globals are executable literals/branches, not a proved per-book strategy
table. Shared literals are left intact. **Persistent data reservation:
`844DBD80..844DBDC0`; code reservation: `84D0D000..84D0D040`**. Each uses 40 of
64 reserved bytes; the data lies after `.rdata`'s virtual end in mapped raw
padding, and the leaf lies in mapped executable padding. BASE security-page
flags are read-only `0x13` and code `0x11`. Both images have zero reservations;
full-image aligned absolute-pointer scans find no references into them.
Computed references and other third-party patches remain unproved.

The 37 authored words contain ten data words, ten leaf instructions, one branch
and sixteen literal-load instructions. The leaf preserves full r11/f0/SP,
does not write LR/CTR and performs the intended CR6 comparison. Full-width
synthetic instruction checks supplement PPC32 native execution. Authored
payload SHA-256 and every original patch-site instruction have exact
regressions. Pass-fetch and personnel-curve patch write sets are disjoint.
**When integrating APF-4, preserve these reservations and check its patch write
set for overlap; no APF-4 artifact was inspected or tested here.**

The two module hashes are `5447E5428AA2D52A` (BASE) and `CEA825F7C2012F5A` (TU).
Decoded image SHA-256 pins and the complete literal/load table are in
[the research note](docs/research/apf_b71_fourth_down.md). All 37 emitted words
per profile, default TOML hashes and numeric execution receipts are in
[the derived evidence](reports/b71_apf5/native_receipts.json).

## PROVED — only the stated offline boundaries

1. Owned BASE and TU images are pin-checked; MASTER's real relocation/validation
   returns 1 after **7,189,487 instructions**, below the 16-million bound.
2. **2,016 native preview comparisons** pass (two profiles, three parameter
   sets, eight field positions, six distances, seven cached random values).
   Maximum chooser length in that matrix is **679 instructions**; bound 100,000.
3. **360 retail-value comparisons** preserve untouched decisions over sampled
   periods, score margins, clocks, urgency values and field positions. This
   is sampled equivalence, not exhaustive state equivalence.
4. At fourth-and-one, 52 yards from goal, neutral tied first period, the retail
   chooser returns punt. Cutoff 2, own-half limit 75 and fallback threshold 1
   produce a complete scrimmage tuple on both profiles, with run share 0 and
   the stated RNG inputs. Both calls take **1,149,654 instructions** (bound two
   million), yielding pointers `[2097252, 2114476, 2137916]`.
5. Isolated global-o's native producer selects a punt tuple, sets the draw flag
   and latch, and enters substitution in **57,091 instructions**. Its special-
   play-only fixture lacks an ordinary replacement formation/play: those two
   pointers are zero. This disclosed fixture limitation prevents claiming a
   complete draw-offside play/animation chain.
6. Native pre-snap entry reaches hold at **2.0 / 2.01 seconds** (304
   instructions) and timeout dispatch at **1.99** (313). An edited threshold
   4 holds at 4 and dispatches at 3.99; clearing the draw flag prevents that
   timeout path. Raising the draw yard/goal gates changes each tested boundary
   independently. Same-state re-entry with the latch already set retains the
   real punt tuple and clears the draw flag. It does not run timeout dispatch.
7. Authored bytes, default off, validation refusals, full-width leaf preservation,
   export/install/reload/storage-copy/remove, offscreen editor preview/reopen,
   Edge/Canary configuration and mocked launch commands pass. Actual emulator
   loading and input are not implied by these tests.

The native instrument is Unicorn PPC32 with recorded adapters for Xenon ABI
spills, scalar conversions and position-vector transport. It never substitutes
category/formation/play selection. RNG integer/uniform and a 50-yard kicker
range are explicit inputs. Producer animation/timer boundaries and seven
pre-snap player/readiness/defense returns are listed with addresses in the
receipts. Native timeout eligibility runs; timeout dispatch is a stop frontier.

## HYPOTHESIS / UNWITNESSED

- **HYPOTHESIS:** the reported post-timeout punt is this exact match-state
  sequence. Its draw latch and decision paths are consistent with the report,
  but the reporter's loaded book, clock state, random cache and kicker were not
  captured. A same-state bounded re-entry is not a real match continuation.
- **HYPOTHESIS:** all untested late-game/score/clock/kicker combinations, computed
  padding references, and compatibility with arbitrary patches. The preview is
  explicitly a neutral scenario, not the entire strategy model.
- **UNWITNESSED:** the draw-offside animation, complete ordinary replacement
  tuple in real match assembly, timeout consumption/reset, following real-match
  play call, actual Edge/Canary loading, SDL gamepad input and native Windows or
  macOS operation. No emulator was opened.
- **Canary observation:** an XMA-decoder crash was reported on Canary. Cause,
  relationship to mods and any fix are unproved. Edge support/SDL is not a
  decoder fix or a stability result. The recommendation is for its SDL path.

Read-only upstream inspection verified Edge's SDL default and Edge config
filename in [input registration](https://github.com/has207/xenia-edge/blob/edge/src/xenia/app/xenia_main.cc)
and [config reader](https://github.com/has207/xenia-edge/blob/edge/src/xenia/config.cc).
These mutable source URLs are not a pinned binary/runtime witness. This was
web research under the session's source-verification requirement; no network
package installation occurred. It is the exception to the local context's
no-network preference and is not presented as an offline source check.

## Validation and command ledger

**{suite['passed_suite_files']}/{suite['expected_standalone_suites']} requested standalone suites pass**, reporting
**{suite['tests_reported_run']} tests and {suite['skips_reported']} explicit skips**. Latest results are in
[suite_results.json](reports/b71_apf5/suite_results.json), including each skipped
suite and log. APF-5's six native tests and offscreen editor test do not skip.
The suite set includes every `test_apf*.py`, beta-69 A1 playcalling, provider
integrity, product catalog, phase1 packaging and registry module commands.

| Gate | Result | Elapsed | Output |
| --- | --- | ---: | --- |
{check_table}

Release: **285 declared files**, no absent inputs, no undeclared/private/retail
payloads. Runtime: **158 imported modules, 73 APF capabilities**; the release
closure check was run without a private source and is not a gameplay check.
Environment: Python 3.12.3, Capstone 5.0.7, Unicorn 2.1.4, Qt 5.15.13 /
PyQt5 5.15.10 (see `test-environment.log`). Repin required zero hash changes.
[commands.jsonl](reports/b71_apf5/commands.jsonl)
records argv, UTC start, elapsed time, exit and full-output log for every formal
check, including failed development runs. Delivery git/bundle commands have a
separate final receipt outside the bundle. Interactive disassembly was
exploratory; the reproducible formal native tests carry the accepted claims.

Development failures are retained: missing inherited evidence before hydration;
an incorrect test exception type; the initial use of the wrong Qt binding;
a test that mislabeled FG row 19; a reused Unicorn translation cache after
patching an already-called function (fixed by flushing translated blocks);
a cancelled-export assertion that assumed configuration created no TOML file
(updated to require byte-identical before/after TOML sets); and a refused
restage into an existing directory. The stale-stage runtime failure is retained. The first installer run selected
system Python without Capstone; the final isolated run prepends the prepared
local interpreter to PATH and clears source PYTHONPATH.
The first delivery audit also matched unchanged-suite log filenames against
the protected-source rule; it now applies that rule only to implementation
paths. Its failed attempt remains in the delivery receipt. Final acceptance
uses the latest complete run of each suite, never hides its
skips, and does not infer success from an earlier failed batch coordinator.

The 75 absent inherited evidence paths were hydrated as ordinary independent
files, with APF-3's exact sizes/hashes, from narrowly scoped read-only source
copies. [hydration.json](reports/b71_apf5/hydration.json) records them; no source
checkout was modified and none is newly committed. Reviewed extract-xiso tools
were restored from the archived public build with exact pins. H7A remains
0755. Scratch stayed below 200 MiB; no retail image/disc/book was written there.

## Retest and integration

1. Import the private bundle on top of `{base}`; do not push from this job.
   Inspect `WIRING.md`, the explicit implementation paths and the reservation
   warning above when integrating the parallel APF-4 branch.
2. Configure Edge or Canary in Studio. For a renamed executable choose its
   explicit runtime filter. Verify the selected config has SDL and capture the
   launch log/argv. Native Windows and actual controller input still need a
   human witness. Keep any Canary XMA crash log as a separate observation.
3. Reproduce retail fourth-and-one near own 48: record BASE/TU, loaded book and
   USER override, quarter/score/clocks, timeouts, kicker, selected kick, draw,
   timeout instant and next call.
4. In Tools → CPU fourth-down triggers choose the actual profile; use cutoff 2,
   own-half limit 75, fallback 1 as the bounded-test recipe. Explicitly enable
   and install, restart Xenia, confirm the named patch applies to the matching
   module, then repeat the recorded state.
5. Test draw yard/field gates and timeout threshold individually, at and either
   side of the threshold, three versus two timeouts and a late-game deficit.
   Capture ordinary replacement tuple, animation and timeout consumption.
6. Remove the patch, restart and repeat the retail case. A preview or patch-load
   message alone does not establish the on-field outcome.

User-facing instructions: [fourth-down and Xenia guide](docs/mod_editor/apf2k8_fourth_down_and_xenia.md).
'''
(root/'ASTRA_REPORT.md').write_bytes(report.encode())
last=f'''# APF-5 complete

Implemented the opt-in global fourth-down patch and independent Tools editor,
plus Xenia Edge/Canary configuration with SDL input. Retail defaults, neutral
preview, exact patch-byte tests and bounded BASE/TU witnesses are included.

Validation: {suite['passed_suite_files']}/{suite['expected_standalone_suites']} requested standalone suites passed;
{suite['tests_reported_run']} tests reported, {suite['skips_reported']} explicit skips. Strict registry, repin,
provider integrity, product catalog, phase1 packaging, APF release and runtime
checks passed. No APF-4 situation code/table edits, tester names, push or Xenia
launch. Full match behavior and real controller input remain UNWITNESSED.

Private git: `.scratch/git`, branch `astra/b71-apf5-fourth-down-xenia`, base
`{base}`. Bundle: `.scratch/astra-b71-apf5.bundle`.
Final commits, bundle verification and SHA-256: `.scratch/astra-b71-apf5-delivery.json`.
Addresses, proof limits, command ledger and retest steps: `ASTRA_REPORT.md`.

ASTRA_DONE
'''
(root/'ASTRA_LAST_MESSAGE.md').write_bytes(last.encode())
print('Wrote ASTRA_REPORT.md and ASTRA_LAST_MESSAGE.md from passing gate receipts')
