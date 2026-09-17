# Beta 71.1 T5: project open and Make my disc

Base: `02bbadd184e85498a441d3be71e70f8de94b9b0a` (the beta 71 release tree).
Branch: `astra/b71-t5-project-open`.
Private Git directory: `.scratch/t5.git`. The worktree's shared Git directory was not modified.
Implementation commits: `823976ea`, `9cbcfcd3`; a following evidence commit contains this report.
Bundle: `.scratch/astra-b71-t5.bundle`, with the release base as its prerequisite.

Read the context, beta 71 release triage, `ASTRA_B70_T1_REPORT.md`, `ASTRA_B70_T2_REPORT.md`, `ASTRA_B71_T4_REPORT.md`, and the actual open/save/build paths. Inspected the supplied screenshot. The brief explicitly authorizes the GUI, facade, build and save fixes implemented here; packaging changes include the new runtime module and regenerated hashes. No capability or game-code cave was added.

## Findings, with source locations

Locations in this table refer to the **unchanged release base**, accessible with `git --git-dir=.scratch/t5.git show 02bbadd1:<path>`.

| Cause | Release location | Consequence |
| --- | --- | --- |
| Opening calls the equipment fit compiler before adopting the candidate session | `mod_editor/studio/session.py:4182` | Every uncached physical group quantizes, generates/checks mip data and compresses during Open. |
| Per-group fit and retries of the accepted subset | `mod_editor/core/nfl2k5_uniform_equipment_writer.py:1661`, `:1697` | A failing combined group can cause more fits of its members. |
| Palette/size ladder and quantizer | Same writer, `:1018`, `:895` | This synthetic workload spends most time in colour mapping, not ZIP reading. |
| Optimal encoding after greedy misses | Same writer, `:616`, `:645` | Different rungs/distance geometries can invoke optimal repeatedly. T4 correctly stopped treating a greedy cutoff as proof of an optimal overflow, but increased work on cold misses. |
| Optional stage-cache fingerprint | Same writer, `:950` | T1's cache helps warm local work; portable project archives do not contain those measurements. A different compiler, helper, target or input misses it. |
| Original PNG export/comparison during archive load; Stadium compiles again during adoption | `mod_editor/studio/project_archive.py:1080`, `:1083`; `mod_editor/studio/session.py:4346` | Loading performs work beyond validating the supplied replacement. |
| Final archive identity/hash comparison comes after all candidate loading | `mod_editor/studio/facade.py:3682` | A file changed/replaced/touched during that interval can be rejected only after expensive fitting finishes. |
| Elapsed-time-only heartbeat and refusal to close a blocking operation | `mod_editor/gui/studio_qt.py:8181`, `:8568` | A quiet compiler looks stuck; the user cannot cancel Open by closing the window. |
| Cancel exception swallowed by observer wrapper; runner waits in communicate | `mod_editor/core/nfl2k5_build_service.py:654`, `:660`, `:610` | Cancel can change the UI without stopping the builder promptly. |
| Empty selection refused by Build & Share | `mod_editor/gui/build_panel_qt.py:1765` | “Tick at least one change, or press a preset.” The toolbar has a separate no-edit gate. |

The chronology matters: **beta 69 already fitted equipment on Open**. It is inaccurate to attribute the existence of this path solely to beta 70. T2 changed palette quality/stripe limits and normal/mud staging; T4 preserved unfit artwork for refit and added the optimal fallback. The existing T4 historical regression still passes: its real-span synthetic-art case is accepted by beta 69, rejected by beta 70's changed fit policy, and exercises the lossless fallback. Those results do not identify the unavailable original project's final error.

Normal/mud staging is an explicit import transaction in `equipment_staging.py`, not an instruction to regenerate mud art on Open. It increases the number of stored replacements and shared-span combinations. Both stored variants used to enter the fit preflight. The new loader validates both without staging new art.

## Reproduction and phase timings

`tools/b71_t5_project_probe.py` creates 600 distinct authored PNGs in 200 synthetic uniform-set TSET groups: normal socks, mud socks and equipment. It writes a real shareable project and runs actual archive/session loaders and codecs. Package/catalog routing is synthetic; no retail package is copied into the fixture.

Historical owners are loaded from Git revisions `f7d6fc07` (69), `3c98d433` (70), and `02bbadd1` (71). This is an instrumented replay of those writer/LZ/session/archive owners on the same current Python environment and synthetic I/O harness, **not execution of three complete shipped applications**. Shared support modules and the available Linux native helper remain from this environment. Historical runs were concurrent, so their small differences are not an isolated performance comparison. The removal of hundreds of encodes is directly instrumented.

| 600 replacements | Open wall seconds | Archive phase | Group fits | Greedy calls / seconds | Optimal calls / seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| beta 69 | 407.785 | 0.692 | 200 / 404.651 s | 688 / 11.201 | 488 / 2.090 |
| beta 70 | 431.591 | 0.687 | 200 / 421.049 s | 459 / 8.194 | 259 / 6.811 |
| beta 71 | 429.322 | 0.706 | 200 / 418.834 s | 459 / 8.171 | 259 / 6.906 |
| changed loader | 0.594 | 0.539 | 0 | 0 | 0 |

Nested phase times overlap; do not add the columns. Fixture construction is excluded from Open wall time and included in each enclosing command receipt. Logs: `reports/b71_t5/open-{beta69,beta70,beta71}-run3.log` and `open-after.log`.

The latest sentinel regression measured **0.653320 seconds** for 600 replacements, below the requested ten seconds, with the compiler and optimal encoder replaced by assertions that fail if called. It also verifies 600/600 progress, pending fit state, and unchanged saved bytes. See `tests-corrections/test_b71_t5_project_open.log`.

A separate 30-item beta 71 phase probe measured 19.170867 s: archive 0.025984; PNG reading 0.031403; compiler-key checks 0.000372; group compilation 18.773749; quantization 17.747343; greedy 0.302529; optimal 0.277035. This fixture does **not** support blaming hash walks or optimal alone for the delay. On Open, the external builder's full source/pack hashes are not run; the facade hashes the saved project before and after, while target identity checks read relevant source spans. Full source/pack verification remains part of Build.

### Reproduced late refusal

The probe's `--late-change` option changes only the project mtime after candidate loading, then lets the real facade perform its final identity check. On 30 items, beta 71 refuses after **19.209568 s**; the changed loader refuses after **0.033157 s**. Both preserve the active session and the archive's exact bytes. Full messages and before/after IDs/hashes are in `late-refusal-beta71-final.log` and `late-refusal-after-final.log`.

The exact stable text is:

> The project changed outside Mod Studio while it was opening: modified_ns, changed_ns.

It then prints the before/after path, size, timestamps, SHA-256 and file ID, followed by:

> The current workspace was kept. Finish saving or syncing the named file, then open it again; if another app is replacing it, save a separate .2k5mod copy and open that copy.

The existing diagnostics suite also proves content, size, mtime and deleted-path cases. A malformed equipment input can instead produce the named `Cannot load equipment edits: ...` refusal. Ordinary valid-but-unfit art in beta 71 is retained with a “needs refit” result; it is not proof of a corrupt project archive.

**UNWITNESSED:** the reported 2 h 57 min failure and its actual message. The original project and terminal error were not supplied. The screenshot proves an elapsed counter at 2208 seconds, not which final failure occurred. The reproduced identity race is a demonstrated late-failure path, not an assertion that this was the original failure.

## Changes

### Open and receipts

New `mod_editor/core/nfl2k5_project_fit.py:18` binds equipment measurements to authored PNG hashes, the source identity, exact target-span hash, target descriptors, compiler/helper fingerprints and all replacements sharing that physical span. Changing a sibling invalidates the group. Generic PNG receipts additionally record the source spans verified by the provider.

`StudioSession.load_shareable_project` now restores receipts at `session.py:4542` instead of compiling. Missing, stale or malformed advisory receipts become **“fit pending; checked when you build”**. Source PNG decoding, bounded archive validation, checksums and final identity checks remain. Stadium Open displays the authored PNG and defers its quantized preview to an explicit editing/build operation. No-op comparison with an exported retail PNG is deferred from Open; save/build validation still handles unchanged artwork.

The first completed fit records measurements in the session. Explicit Save serializes `fit_receipts` in the existing project schema; reload validates the keys. Build completion enables Save when it learned new measurements. **No background Open/check writes the named project archive.** Cancel does not install partial Build receipts. Private disposable session files and the existing private recovery facility remain separate from the user's saved archive.

Relevant locations: `project_archive.py:89`, `:650`, `:1166`; `equipment_staging.py:87`; `nfl2k5_build_service.py:1512`; `nfl2k5_project_fit.py:60`, `:73`, `:88`, `:111`.

### Parallel Build and optimal bound

`tools/nfl2k5_visual_mod_project.py:3477` checks independent physical equipment groups with spawned workers. Mixed projects also parallelize independent uniform imports at `:3424` and `:3775`. The parent owns output writes, validates returned compiled spans and consumes them without recompressing. Existing worker limits and bounded in-flight work are retained.

The real read-only retail-span probe used two workers for four normal/mud replacements across two uniform sets: **1.547686 s**, two parent cache hits, no repeat compilation and no disc output. See `parallel-retail.log`. It used explicitly reduced synthetic artwork; it does not claim full-size difficult artwork always fits.

`nfl2k5_uniform_equipment_writer.py:609` first collects greedy candidates, chooses one optimal candidate for the complete physical fit item, and caches the result, overflow or timeout. Suggestions share this attempt allowance. Complete staged successes and failures survive process-local cache clearing through the optional disk cache. Repeated unchanged fits do not repeatedly search another palette/distance candidate. The item key includes its siblings; changing that composition creates a different fit item.

**Optimal budget: 5.0 seconds per selected invocation**, in `nfl2k5_equipment_lz.py:23`, `:81`. Native subprocesses have a deadline; timeout does not retry in Python. The Python fallback checks the same deadline during chain construction, comparisons, search and output. This is a cooperative wall-time bound plus OS scheduling/check-interval and final verification overhead, **not a five-second bound for quantization, a whole TSET fit, or an entire build**. The comparison ceiling remains. A timeout says:

> Equipment optimal fit reached its 5-second limit. Use Refit equipment to reduce colours or size, or revert this item.

Unmeasured greedy cutoffs are not reported as proved optimal byte shortfalls. Restricting the search can require an explicit refit where another untried lossless candidate might have fitted; it never silently drops art or relaxes span verification. Six existing byte-golden fit cases and the near-miss/retail-chain tests pass.

Build progress carries item names, done/total and an estimate; the Qt bar uses counts and scales multi-gigabyte copy totals to avoid signed-32-bit overflow. The production runner drains output while polling Cancel and stops its owned process group before staging cleanup. `_emit` now preserves cancellation control flow. Existing Windows job-object handling remains. Linux cancellation is exercised; native Windows execution is not.

### Atomic save and close

There is **no proved in-place corruption path in the release's named-project save**. At the base, `project_archive.py:621` already created a sibling temporary file, `:646` fsynced it, and `:178` used `os.replace`. The slow Open path read the saved archive and wrote only the candidate's private workspace. Claiming that this check necessarily corrupts the named archive on termination would be unsupported.

The confirmed defect was that `studio_qt.closeEvent` blocked closure throughout the expensive check. It now requests cancellation and closes after the candidate unwinds. The archive check reports each item, so cancellation is checked between items. Process termination can leave disposable temporary/session files, but does not truncate the saved archive.

Save retains file-fsync-before-publication and adds a parent directory flush at `project_archive.py:223` / `:227`. Model-project rewrites now use a temporary sibling in the destination's exact directory and exclusive creation (`nfl2k5_model_project_session.py:24`, `:193`). The named destination is published only after a complete archive exists. Platform support for directory flushing still determines crash durability of the directory entry on Windows.

Tests inject a failed publish and an immediate child-process exit before rename, preserving the original bytes; cancel halfway through Open preserves the old file and active edit state. Power failure and the original alleged corruption remain **UNWITNESSED**.

## Make my disc

Before this fix a plain selection is refused with **“Tick at least one change, or press a preset.”** The toolbar separately says **“Add at least one project edit: Replace a PNG, edit a string, or pick a colour. For gameplay patches, use ★ Build & Share.”**

Both entry points now support a verified unchanged copy, with **“Changes: none”** in the confirmation. The existing completion reports **“No changes written”** when the source and output hashes are identical. The complete synthetic no-edit disc test verifies exactly that identity. Existing synthetic combined-project tests verify byte-equivalent composition, one private copy, source preservation and failure before publication.

A malformed equipment Build regression emits this user-facing cause (not the internal progress marker):

> Could not make the disc copy. While compiling project edits: Project edit index 0: Equipment / Shoes / team or uniform set SYNTHETIC / texture tset:0:8:0:shoes01: PNG must be exactly 32x32

Valid unfit art is named with **“needs refit”**, its measured reason, and **“Use Refit equipment in Build, or revert this item.”** Measurements are retained for the explicit refit UI.

The real Advanced preset passed the release-path preflight in **3.470167 s**. The current probe passed preflight in **2.747900 s** and the first real XBE patch pass in memory in **5.500478 s**, changing 11,728 bytes; no source/output file was written. See `advanced-before.*`, `advanced-first-pass.*`. No refusal or crash was found in those exercised Advanced phases. The simulated Windows build test also passes.

**UNWITNESSED:** a complete retail Advanced disc with this replacement workload, later retail archive passes, and an in-game launch. The context prohibits large files on the root filesystem; the designated Storage scratch directory is outside this session's writable roots. I did not evade those limits by copying a retail disc or claiming a complete build from the memory probe. No xemu or other emulator was opened.

## Verification and command records

All **55 latest standalone suites pass**: **625 test cases**, including three skips (one optional uniform/equipment export case and two platform-path cases). This includes the studio Qt suites offscreen; project/document/model/session/facade suites; equipment and uniform suites; T1/T2/T4 regressions; build/cancel/byte-golden tests; provider integrity (exact 296-module unified closure); product catalog; phase1 packaging; platform durability; and all 46 visual backend tests.

The strict validator passed: `MOD_CAPABILITY_REGISTRY_VALIDATION_PASS schema=vc_mod_capability_registry/v1 games=3 surfaces=21 capabilities=176`.
`packaging/repin.py --apply` regenerated changed pins; the reviewed repeat reported **0 pin updates**. No runtime cave manifest regeneration is needed because no game-code writer/cave ownership changed.

- [Every retained timed command, exit code and elapsed time](reports/b71_t5/COMMANDS.md)
- [Machine-readable command ledger](reports/b71_t5/commands.json)
- [Latest result for every standalone suite](reports/b71_t5/latest-suites.json)
- Individual `.log` output and `.json` command receipts beside those indexes.
- Final commit/bundle/verification command receipts are in `.scratch/delivery.json` outside the bundle, avoiding a self-referential bundle hash.
- `tools/b71_t5_validate.py` runs suites standalone with `QT_QPA_PLATFORM=offscreen`; `tools/b71_t5_run.py` wraps probes/gates with a deadline and exact command receipt.
- Heavy jobs were detached with `nohup` and a retaining shell job; no name-based process killing was used.

Development failures are retained, not erased: the initial tests exposed old eager-fit expectations, mock cache contamination, an import-contract mismatch, an exact-closure count change, a repeated optimal selection, and test-edit mistakes. They were corrected and their affected complete suites rerun. Aggregate early runs retain nonzero status even though every latest standalone result passes. Initial failed historical probe setup runs are harness failures, not product timing results. Early read-only discovery/private-Git setup before the command ledger began did not preserve a separate elapsed-time receipt; those setup timings are **UNWITNESSED**. The ledger preserves all subsequently recorded inspection commands and every retained test/probe command, including failures.

## Evidence boundary and handoff

**PROVED:** no-encode 600-item Open under ten seconds; source/span/sibling invalidation; fit receipts through explicit save/reload; persistent failed-fit reuse; one selected optimal attempt and Python/native timeout behavior; named count/estimate progress; cancellation reaching and stopping a subprocess; untouched saved archives on cancellation/interrupted publication; plain synthetic disc copy; real spawned equipment workers; real Advanced preflight/first XBE pass; the enumerated suites and packaging/integrity gates.

**UNWITNESSED:** the unavailable original project's exact failure/corruption, three-hour reproduction, native Windows/macOS performance and power-loss behavior, complete retail Advanced disc publication with these edits, all in-game appearance/behavior.

Review/witness next: open the original large project, confirm pending/cached labels, save/reopen after its first Build, cancel a cold build, and complete/play its Advanced disc on the target platform. No art was silently refitted during Open. No retail bytes or images were committed. No push was made.
