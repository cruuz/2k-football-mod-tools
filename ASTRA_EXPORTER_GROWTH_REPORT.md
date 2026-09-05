# r62 exporter growth

2026-09-05. Branch `astra/r62-exporter-growth`, starting at
`5f5b504` on `local/stack-beta-62`. EXPERIMENTAL / UNWITNESSED.
No network, game emulator, graphical display, audio or push was used.
Retail inputs were read only. Existing RC85 feature behavior, executable
owners, allocator pages, cave manifest and protected product files are unchanged.

## Delivered and compatibility decisions

`mod_editor/core/modpack_ops.py` now records each growth's append sector and
its file's sector offset from that append, relative to the preceding operation's
image end. Named paths are deduplicated case-insensitively and ordered by their
physical extents. Before/after sizes still form one validated chain.

The original exporter already chained sizes. The actual Experimental failure
was a retained intermediate allocation: SPECIAL had appended an XBE before
scorebug appended pack 0 and then superseded that XBE with the final owned-page
XBE. Exporting only the two final directory entries left SPECIAL's 12,021,760
physical bytes unaccounted for. The old code's exact refusal was reproduced:
`growth must append at the first sector after the image`.

`file_grow` ID 3, payload version 2, explicitly carries those retained bytes
before its complete replacement file in one streamed, hashed append payload.
Its independent before/after file hashes remain mandatory. Only the alignment
gap of fewer than 2048 bytes is implicitly zero-filled. Export still compares
every byte of the projected result against the author image. Unaccounted tails,
nonzero implicit alignment, backwards allocations, wrong chain fields and bad
hashes refuse. A 32 MiB retained-prefix test rejects any read over the existing
16 MiB block size and verifies the exact result.

Ordinary contiguous chains continue using payload version 1. Format stays 2,
registry stays 1, and `min_reader_version` stays 2: **the shipped beta-60 and
beta-61 readers already refuse unknown operation versions before mutation**.
Both actual historical reader modules were run against the new Experimental
pack and returned exactly:

```
this mod needs a newer Mod Studio: file_grow version 2
```

Neither created an output nor a `.part`. No reader-version bump is needed to
prevent silent misapplication. ID 1 `xbe_grow` retains its strict SPECIAL
transition, version 1 and specialized storage executor. ID 5 `file_shrink`
retains its existing sector, unused allocation bytes and physical image size.
Copy, per-operation readback, composed verification, source-change checks,
handle closure and atomic replacement continue through the existing transaction.
An already-applied format-2 pack remains a clear refusal on apply, and reports
`applied` on check; this existing behavior was preserved.

Four frozen synthetic transport equivalents were created using the unchanged
exporter modules at the local `beta-60` and `beta-61` tags. Basic is format 1;
Advanced is format 2 byte runs plus SPECIAL growth. The ZIPs, their exact
provenance/hashes, and fixture instructions live in
`tests/fixtures/modpack_legacy/`. No distributed patch fixtures existed under
`tools/` here. Tests reconstruct expected images independently, check every byte
in blocks, exercise copy and in-place application, and assert the fixture ZIPs
remain byte-for-byte unchanged. No proprietary game data is in these fixtures.

## PROVED: retail Experimental round-trip

The standalone acceptance entry point is:

```sh
NFL2K5_RETAIL_INDEX='/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
NFL2K5_MODPACK_GROWTH_ACCEPTANCE=1 OPENBLAS_NUM_THREADS=1 \
python3 tests/mod_editor/test_modpack_growth_acceptance.py -v
```

It calls `mod_build.apply_preset(BuildPlan(...), "softdrink_experimental")`,
builds from the supplied retail image, exports with exactly
`file_operations=["default.xbe", "vc_53450030/0"]`, checks against retail with
hashing enabled, applies transactionally to a fresh copy, compares every output
byte in bounded blocks, and recognizes the result as already applied. Temporary
images are removed even on failure. The source SHA-256 is checked again.

| Artifact | Bytes |
| --- | ---: |
| Retail source | 6,300,499,968 |
| Built Experimental disc | 6,519,656,448 |
| Applied disc | 6,519,656,448 |
| Compressed `.2k5patch` | 155,457,053 |
| Ordinary byte-run payload | 709,148 |
| Retained SPECIAL allocation | 12,021,760 |
| Final pack 0 | 195,104,768 |
| Final XBE | 12,029,952 |

The actual operations are:

| Operation | Before image bytes | Append sector | File offset in sectors | After image bytes |
| --- | ---: | ---: | ---: | ---: |
| byte_runs v1 | 6,300,499,968 | n/a | n/a | 6,300,499,968 |
| file_grow v2, `vc_53450030/0` | 6,300,499,968 | 3,076,416 | 5,870 | 6,507,626,496 |
| file_grow v1, `default.xbe` | 6,507,626,496 | 3,177,552 | 0 | 6,519,656,448 |

Retail SHA-256:
`7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9`.
Built and applied whole-disc SHA-256:
`76c7754672da6a94a4744494756895d49a0ceb1d7271e7e48b1fa12accba72e2`.
Final XBE SHA-256 matches the earlier Experimental report:
`7573bdf75f53ccc10fce4963a731a61f20e2b7066eb5f7c79b4784d6a9443534`.

The first successful export/check/apply took 113.432 seconds after building.
Its evidence is `.scratch/exporter-growth/{geometry,export-receipt,check-receipt,
apply-receipt,acceptance-summary}.json`. The committed standalone test also
records `standalone-{build,export,check,apply,acceptance}.json` there. All disposable
images were deleted; the first private patch remains in scratch and is excluded
from delivery.

## PROVED: the historical OOM command and measured memory defect

The supplied PID is identifiable, but its command contradicts the proposed
music-test attribution. Kernel entries show timeout PID **2642351**, Python PID
**2642352**, and the kill with **24,747,572 KiB anonymous RSS** plus 2,584 KiB
file RSS. The saved task output for timeout 2642351 names this command:

```sh
timeout 3000 python3 -m pytest $(grep -rln "studio_qt" tests/mod_editor/*.py | tr '\n' ' ') \
  -q -p no:cacheprovider --tb=line
```

This was **one batched Qt pytest process**, not a standalone music acceptance or
music-bank process. Its quiet progress log stops after 78%, another 21 dots and
`RC=137`. It does not identify the exact active test or retained Python objects.
It would be unsupported to name a single test as the source of all 24.7 GB.
The current CI's separate-process contract avoids keeping that entire batch alive.
The exact command, progress and filtered kernel evidence are copied into
`.scratch/exporter-growth/oom-{command,batch-progress,kernel}.txt` from the saved
`/tmp/claude-1000/-home-noah/1ab9b8ce-0080-4b80-854c-2054d84ff31f/` task output
`tasks/b4yb383j2.output` and its referenced `regression2.txt`. No other worktree
was inspected or modified for this evidence.

Each plausible disc suspect was then run separately with `/usr/bin/time -v`.
A 2 GiB address-space ceiling prevented another uncontrolled allocation.
The independent music acceptance actually ran all four retail builds, including
both 200-track banks; it was not counted as a skipped success.

| Standalone baseline | Tests | Maximum RSS, KiB | Result |
| --- | ---: | ---: | --- |
| `test_nfl2k5_music_banks.py` | 15 | 61,212 | pass |
| `test_nfl2k5_music_acceptance.py`, enabled | 1, four builds | 181,868 | pass |
| `test_nfl2k5_music_build.py` | 8 | 115,892 | pass |
| `test_xiso_layout_tolerance.py` | 9 | 720,868 | pass |
| `test_pack_extent_resolver.py` | 6 | 859,000 | pass |
| `test_nfl2k5_scorebug_resources.py` | 5 | 2,076,788 | MemoryError at the ceiling |

The scorebug transaction test used `Mock(side_effect=...)` for its compiler and
writes. Call histories retained each complete 194 MB pack and rollback payload.
Direct replacement callbacks preserve all failure injections and assertions
without retaining their arguments. This changes a reproduced memory failure into
a passing test. Scorebug fixtures now use read-only file-backed buffers, mapped
copy-on-write corruption probes and block comparisons. The existing pure compiler
still produces one bounded pack buffer internally; the tests do not retain a
second full pair of Python byte arrays. Its final separate `/usr/bin/time -v` run
passes all five tests at **893,344 KiB**. All 264 resources, all 4,323 index rows,
unchanged suffix bytes, five rollback stages and replay remain covered.

The layout-tolerance test now writes the same reported 7,825,162,240 and
6,300,958,720 byte geometries sparsely, using the existing Windows sparse-file
helper. It retains all real partition bases, discovered bases and payload checks;
its nine tests pass at **49,508 KiB**, down from 720,868. The pack-extent test now
compares every byte in 1 MiB blocks with only the two expected writes projected
onto each block. Its six tests pass at about **42 MiB**, down from 859,000 KiB.
No geometry, neighbor, corruption or whole-output assertion was removed.

`test_disc_memory_budget.py` launches all ten relevant standalone files in
separate children, fails on child errors or peak RSS >= 2 GiB, and tests the
ceiling itself with an allocation that must raise `MemoryError`. POSIX uses
`RLIMIT_AS` and native peak RSS; Windows uses a per-process Job Object memory
limit and `PeakWorkingSetSize`. The opt-in retail tests preserve their precise
missing-input/enablement skips in normal CI. Setting their acceptance environment
variables includes the real builds under the same guard. The final normal guard
passes; the enabled music acceptance also passed under this guard at 192,643,072
bytes in the earlier run. Linux is measured here; native Windows/macOS execution
is not claimed.

HYPOTHESIS: retained Qt objects, pytest failure tracebacks or fixture state explain
why the historical combined batch exceeded each standalone process. The quiet
historical log cannot distinguish these. The measured scorebug Mock retention is
a separate proved defect, not a retroactive claim that it caused PID 2642352.
The old unbounded batched command was not rerun.

## Validation, decisions and remaining witnesses

Final commands and results are recorded below after verification. Intermediate
failures remain in scratch: an initial build receipt needed dataclass JSON
serialization after the disc had successfully built; a file-backed test stub
needed a `memoryview` to retain byte-content equality; and the first build-service
baseline lacked CI's repository import path. These were corrected without
changing production builder behavior or weakening assertions.

Share text decision: **no text change is required**, so `WIRING.md` is unchanged.
Existing operation labels already say "Named file growth" and display disc sizes.
This task implements the requested explicit core `file_operations` workflow.
The existing Share callback still omits that argument; automatic selection of
arbitrary grown named files in the GUI was not added. No new dispatcher flag,
BuildPlan field, preset option, GUI control, capability or release import exists.
`modpack.py` needed no change; the current transaction and manifest dispatch were
sufficient. Protected modules and release files remain untouched.

The transport is PROVED byte-identical, not played. Noah's pending witness list:

1. In the updated Studio, check and apply the exported Experimental pack to a
   compatible retail copy on the intended desktop OS. Confirm the reported sizes,
   successful publication and `already applied` check on the result.
2. Open it in beta 60/61 and confirm the clear newer-Studio refusal, with the
   destination untouched. This already passes against their actual Python readers;
   desktop presentation remains unwitnessed.
3. Boot the applied output on the intended game platform and repeat the existing
   RC85 Experimental checks: SPECIAL labels/names, scorebug team logos and events,
   and a normal game. Its bytes match the builder exactly; this does not add a
   game-loader or gameplay witness to those features.
4. On Windows/macOS, run the standalone suites and memory guard with retail inputs
   enabled. Linux lock simulation and portable code are not native OS evidence.

### Final verification results

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_modpack_growth.py` | 11 passed, 6.301 s; includes all four frozen legacy packs, three-file chain, repeated same-file growth, nested paths, raw prefix, shrink, malformed accounting/hashes, corrupt retained bytes, failed middle write, and bounded reads |
| `NFL2K5_MODPACK_GROWTH_ACCEPTANCE=1 OPENBLAS_NUM_THREADS=1 /usr/bin/time -v python3 tests/mod_editor/test_modpack_growth_acceptance.py -v` under `ulimit -v 2097152` | 1 passed, 265.144 s, maximum RSS 1,142,736 KiB; complete independent retail build/export/check/apply and cleanup |
| `NFL2K5_MUSIC_ACCEPTANCE=1` baseline, `/usr/bin/time -v python3 tests/mod_editor/test_nfl2k5_music_acceptance.py -v` under the same ceiling | 1 passed, four complete retail builds, 205.574 s, 181,868 KiB |
| `OPENBLAS_NUM_THREADS=1 /usr/bin/time -v python3 tests/mod_editor/test_disc_memory_budget.py -v` | 2 passed, 104.170 s; all ten child files exit 0; retail acceptances explicitly disabled in this normal-CI pass |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` under ceiling and `/usr/bin/time -v` | 5 passed, 70.064 s, 893,344 KiB |
| `python3 tests/mod_editor/test_xiso_layout_tolerance.py` under ceiling and `/usr/bin/time -v` | 9 passed, 0.658 s, 49,508 KiB |
| `test_modpack.py`, `test_nfl2k5_music_banks.py`, `test_nfl2k5_music_build.py`, `test_pack_extent_resolver.py`, `test_nfl2k5_build_service.py` via the final guard | all passed; existing 36 modpack tests included |
| Actual beta-60 and beta-61 module replay, `.scratch/exporter-growth/old_readers.py` | both refuse new pack with the exact newer-Studio message; no destination or `.part` |
| `python3 -m py_compile` on all seven changed/new Python files | pass |
| `git diff --check`, explicit changed-path audit, scratch image scan | pass; no protected path changed; no disposable ISO remains |

Final guard peak RSS in bytes: music banks 61,947,904; music build 112,054,272;
scorebug resources 914,178,048; layout tolerance 49,373,184; pack extents
43,503,616; build service 32,768,000; original modpack suite 167,485,440;
new growth suite 123,617,280. Disabled acceptance children only import and report
their precise skips; their enabled measurements are separately listed above.
The initially failing enabled guard was retained in `memory-guard.log`, and the
corrected complete normal pass is `memory-guard-final.log`.

These are the relevant standalone and real-image checks, not a claim of a new
full-repository CI run. The historical batched invocation is identified; its
last active case is not recoverable from the quiet log.

## Commit delivery

The explicit-path `git add -- <15 deliverable files>` was attempted and refused:
`index.lock: Read-only file system` in this worktree's linked Git metadata.
Following the brief's authorized fallback, the commit is prepared with isolated
metadata under `.scratch/exporter-growth/commit.git` and exported as
**`.scratch/exporter-growth.bundle`**, with the original HEAD as its prerequisite
and parent. The worktree edits remain in place and its original branch ref is
unchanged. The bundle includes only the 15 explicit source, test, synthetic
fixture and report paths. `ASTRA_BRIEF.md`, scratch artifacts and private patch
bytes are excluded. No push was attempted.
