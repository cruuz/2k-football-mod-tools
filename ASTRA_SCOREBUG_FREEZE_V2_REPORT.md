# R65 scorebug binding and game-entry stall

2026-09-08, `astra/r65-scorebug-freeze`, base `be99b324` (`local/stack-beta-63`).
**EXPERIMENTAL / UNWITNESSED. A native entry-stall path is reproduced and
repaired; the actual community freeze is not yet identified by a played
comparison or a stopped tester PC.**

**Cause in one sentence:** The reproduced entry stall comes from the runtime
binding hook searching all resource collections, which can evict an unrelated
cached texture and wait on its GPU fence before HUD initialization finishes.

The cache state and withheld GPU completion are supplied fixture inputs.
This is a concrete counterexample to the old binding's safety, not evidence
that a healthy GPU necessarily deadlocks or that a tester had this exact cache.
The report separates that proved path from the remaining gameplay hypothesis.

## What changed

`mod_editor/core/nfl2k5_scorebug_runtime.py` now supplies the resident collection
name `GAMEDATA` to all three private TXTR/FONT lookup call sites. It uses the
native named-collection lookup and the HUD's typed resident resource list.
The team texture, neutral texture fallback and private font helper all use the
same scope. A missing named HUD fails to the existing hidden-panel/native-font
fallback instead of borrowing another collection's resources.

The owner still uses two native call hooks: setup at `0xfce56`, displacing
`0xfc1a0`, and update at `0xfcfa2`, displacing `0xfc9c0`. Their calling
conventions, saved CPU state and native continuations remain intact. No native
completion flag, timeout or GPU wait routine is patched. All runtime state
remains in the owner's existing writable allocation. The descriptor defaults
still use the already owned writable native text records.

The repair replaces three `XOR ECX,ECX` instructions with
`MOV ECX,0xe614b8`. Used code grows from 1,395 to **1,404 bytes** within the
existing **1,408-byte RX / 128-byte RW** requests, each aligned to 16. No new
owner, cave, page, budget row or immutable table is allocated. The allocator
plan command succeeded against the unchanged beta-62 budget fixture.

Five additional retail dependency spans pin the loader call, both UTF-16 names,
the collection-name resolver and the collection constructor. Mutating either
end of each span, even with valid section digests, is refused before the
allocator code writer. Exact old sealed hook bytes are also refused before
mutation with the supported-base rebuild message. Current apply/replay is
idempotent. The first-install receipt reports `binding_collection=GAMEDATA`
and `binding_revision=5`; `runtime_witnessed` remains false.

The compiled resource contract remains `scorebug-runtime-v4-scoped-fonts`.
No archive compiler, atlas, FONT recipe or SCNE resource changed. Runtime's
existing static v3 XBE composition is retained and tested in both orders with
identical final bytes and exact replay. Painted-folder artwork remains a
separate incompatible resource choice, as already enforced by BuildPlan.

## PROVED: the native lookup contract

The native loader instructions at `0x6310e..0x6312c` pass the UTF-16 name at
`0xe614b8` (`GAMEDATA`), filename at `0xe614cc` (`gamedata.iff`), context
`0xb33d5c`, a selected heap and zero flags to constructor `0x43f50`.
Executing that actual call sequence with heap selection and VFS-open success
as explicit host boundaries constructs the named context and submits its
header read. The constructor initializes its resident, cache and indexed
fields (`+0x0c`, `+0x10`, `+0x14`) to zero for this ordinary collection.

Archive outer 346's identity is `0x00b6926c`, matching the CRC32 of uppercase
UTF-16 `GAMEDATA.IFF`. This links the collection name to the HUD archive span
being compiled. The test streams the four-byte identity from pack 0; it does
not load the archive pack into memory.

`0x449e0` treats ECX as a **collection name pointer**, not a collection object.
With a nonzero name it calls `0x42f50` and searches only the matching context.
With ECX zero it walks the entire context list rooted at `0xb09578` and calls
`0x443d0` on each. Those contexts do not share one resource lookup contract:

| Context field | Native behavior relevant to binding |
| --- | --- |
| `+0x0c` | Ordinary resident list checks FOURCC and the UTF-16 resource name. This is the HUD's branch. |
| `+0x10` | Cache may hash the name, find an indexed but nonresident entry, choose an LRU victim, evict it and queue a read. A miss is not necessarily side-effect free. |
| `+0x14` | A ready indexed collection uses `0x42e40`, matching a name hash without checking the requested resource type. |

The earlier freeze fixture covered an empty/free cache slot and pending states.
It did not execute a live texture victim's destructor from inside the binding
hook. Its separate fence test began after setup had already returned. The new
fixture joins those previously separate native paths.

## PROVED: old, fixed and disabled-hook controls

The standalone regression loads the `neutral` runtime collection through the
native loader. Ahead of its resident HUD it supplies an unrelated named cache
with a cold indexed `hscore_buga` entry, one ready evictable texture record and
an armed native fence. The victim is a real relocated `score_buga` TXTR whose
loader-installed destructor is `0x44dc0`. Its resource root is borrowed for
the synthetic cache record; this does not prove native cache-pool allocation
or freeing. Execution stops in the wait before any cache-pool free.

`gpu_fence()` lets the actual packet builder arm `[fence+8]=1`. The host GPU/OS
boundaries at `0x33220` and `0x341a0` return without delivering completion.
The old hook's lookup reaches the following actual native path:

```text
0x64710 game entry -> 0xfccd0 HUD initialization -> 0xfce56 setup hook
  -> 0xfc1a0 displaced native setup returns
  -> private FONT helper -> 0x449e0 global lookup -> 0x443d0 cache branch
  -> 0x42d50 indexed miss -> 0x42c00 eviction -> 0x44dc0 TXTR destructor
  -> 0x28f40 -> 0x28de0 render drain -> 0x33660 fence wait
  -> 0x3367a repeatedly reads [fence+8] == 1
```

Only the owned hook instructions and the two call sites change between the
controls. The same pending fence and ready victim record are retained; no
completion is delivered to make the fixed hook pass.

| Binding control | Native entry result | Instructions | Fence reads at `0x3367a` | HUD/parent result |
| --- | --- | ---: | ---: | --- |
| Base v4 generated instructions | Stops at the 250,000-instruction bound, PC `0x3367d` | 250,000 | 33,162 | HUD enabled remains 0; parent cannot finish |
| HUD-scoped repair | Returns | 44,216 | 0 | HUD enabled 1, parent ready flags `[1,1]` |
| Restore both native calls | Returns | 28,538 | 0 | HUD enabled 1, parent ready flags `[1,1]` |

The fixed control enters neither eviction nor its destructor/fence wait and
queues no cache read. The committed old-code fixture contains only the
Studio-generated owner instructions, not a retail executable. Its padded
1,408-byte SHA-256 is
`483d2bf237dc4122c0c74ccc682d9174efaa8d9cd63b0c2279c9990b121b6d2f`.
It is captured from this task's base, so the regression needs no historical
Git objects. Older reports' generated-code hashes describe earlier revisions.

This shows why removing binding hooks can avoid an entry stall under this
cache/fence condition. It does **not** show that the hook blocks the GPU's
normal completion path or prove an infinite wait when completion is delivered.

## PROVED: type confusion, frames and draws

A second native control places a ready indexed collection before the HUD with
the genuine relocated `score_buga` TXTR descriptor. The old global private
FONT request accepts that texture descriptor as a FONT. Entry and subsequent
frames still return, but both score strings `0` submit **zero glyph vertices**.
The repair resolves the HUD's actual FONT; the same score strings each submit
four vertices. This is a separate blank-score defect, not another proved hang.

The entry harness now continues through real native draw `0xfc360`, text
submission `0x47420` and the glyph walk after 40 native update frames. It logs
the actual text, selected FONT pointer and vertex count. GPU text primitive
endpoints, world predicates, field/camera inputs and unrelated parent calls
are explicit supplied boundaries, recorded in the trace. A vertex count is
CPU evidence of glyph submission, not a displayed frame or a GPU witness.

All six public profiles (`transport`, `hooks`, `resources`, `neutral`, `pair`,
`full`) load, enter mode 4, complete 40 updates, draw and re-enter mode 7:

| Profile | Registered TXTR / private FONT | Entry instructions | First full update | Draw instructions | Re-entry instructions |
| --- | ---: | ---: | ---: | ---: | ---: |
| transport | 44 / 0 | 19,103 | 15,085 | 21,293 | 19,103 |
| hooks | 44 / 0 | 37,313 | 15,110 | 21,288 | 37,313 |
| resources | 308 / 7 | 86,357 | 15,085 | 21,293 | 86,357 |
| neutral | 52 / 7 | 36,968 | 15,122 | 18,697 | 36,968 |
| pair | 68 / 7 | 32,432 | 15,122 | 18,697 | 32,432 |
| full | 308 / 7 | 104,832 | 15,122 | 18,697 | 104,832 |

The 44 original resident textures are included in those counts. Each
hook-enabled first frame reaches the real displaced `0xfc9c0` once; transport
and resources restore the native hook calls as their profile requires. All
draws submit glyphs, and private font selections belong to the loaded FONT
set or the supplied native fallback set. The missing-GAMEDATA control also
returns, hides missing private panel textures and retains native score fonts.

Full PCs, counters, bounded tails, writes, loader counts and host boundaries
are in [trace.json](docs/scorebug_ingame/freeze_v2/trace.json). That artifact
explicitly sets `community_cause_proved=false` and `runtime_witnessed=false`.

## Validation and composition

The suites run as standalone unittest scripts with `python3 file.py -v`, plus
one focused pair invocation. Two unchanged legacy manifest scripts need the
explicit scratch adapters described below; all their assertions still execute.
Optional private-XBE/pack and Unicorn/Capstone/Pillow requirements have
explicit skip reasons. No console/game emulator, GUI, audio or network was
used. The native harness is a bounded CPU fixture. No real-disc build was run.

The runtime/static owners were already present in both gates and the manifest
builder. The shared test adapter now exposes static v3 to the pairwise matrix;
both scorebug owners are added explicitly to that matrix. Its two mutually
exclusive MyCareer formats still skip their same-owner pairing. The matrix
checks both orders, both statuses, exact owner/allocator replay and identical
output bytes; static v3's receipt uses its own `state_before` contract.

Validation results are recorded below after the complete runs and in
[validation.json](docs/scorebug_ingame/freeze_v2/validation.json).

**487 successful test executions** across the following runs (including one focused pair rerun). No final listed run skipped a test.

For ordinary rows the exact command is `python3 tests/mod_editor/<file> -v`. The three special commands follow the table.

| Standalone file | Passed | Test seconds |
| --- | ---: | ---: |
| `test_nfl2k5_scorebug_freeze_v2.py` | 7 | 330.266 |
| `test_xbe_patch_memory_writes.py` | 95 | 951.658 |
| `test_xbe_patch_cave_references.py` | 107 | 1080.981 |
| `test_nfl2k5_owner_pairwise_composition.py` | 146 | 908.485 |
| `test_nfl2k5_scorebug_runtime.py` | 12 | 127.842 |
| `test_nfl2k5_scorebug_freeze.py` | 7 | 214.672 |
| `test_nfl2k5_scorebug_native.py` | 4 | 103.260 |
| `test_nfl2k5_scorebug_fonts.py` | 9 | 45.193 |
| `test_nfl2k5_scorebug_projection.py` | 14 | 29.785 |
| `test_nfl2k5_scorebar_v3.py` | 9 | 67.825 |
| `test_nfl2k5_scorebug_resources.py` | 6 | 103.484 |
| `test_nfl2k5_scorebug_ingame.py` | 11 | 9.697 |
| `test_nfl2k5_scorebug_ingame_fix.py` | 9 | 92.162 |
| `test_nfl2k5_scorebug_versions.py` | 4 | 5.886 |
| `test_nfl2k5_scorebug_unified_adapter.py` | 5 | 0.053 |
| `test_nfl2k5_cave_oracle.py` | 28 | 238.265 |
| `test_nfl2k5_music_playlist_manifest.py` | 2 | 3.963 |
| `test_nfl2k5_screen_hooks_manifest.py` | 3 | 3.962 |
| `test_nfl2k5_my_career_manifest.py` | 3 | 6.452 |
| `test_nfl2k5_defensive_try_manifest.py` | 3 | 4.492 |

Special runs (same manifest environment as above):

- `python3 .scratch/run_read_option_manifest.py -v`: 1 passed in 13.671s.
- `python3 .scratch/run_guardian_manifest.py -v`: 1 passed in 171.831s.
- `python3 tests/mod_editor/test_nfl2k5_owner_pairwise_composition.py PairwiseCompositionTests.test_scorebug_runtime__static_scorebar_v3 -v`: 1 passed in 7.155s.

The memory gate began after the lookup repair and before the final constructor
pin was added; its emitted hook bytes are identical. The cave gate and native
v2 suite use the final production source. After making the shared static test
adapter resolve its writer dynamically, the focused pair and complete write
observer were rerun. Both returned the same valid owner composition.

The protected reservation manifest is stale on this base as the brief warned.
Gate/oracle/owner-manifest commands use
`NFL2K5_CAVE_MANIFEST="$PWD/.scratch/cave-manifest.json"`. This scratch copy
refreshes source hashes while retaining the base's 10,808 spans; the stack
fixtures project their current union as usual. It is not a regenerated or
release-certified manifest. Claude must run the normal oracle manifest builder
after integration. The protected manifest and all other protected files remain
unchanged. No read-option, MyCareer, ESPN25 or coverage-trail production module
was edited.

The original read-option manifest script fails on eight stale source hashes
because it ignores `NFL2K5_CAVE_MANIFEST`. Redirecting only its imported default
to the scratch copy passes its one test. The original Guardian observer fails
at raw `0xb2319` (VA `0xc2319`): the existing historic-team class adapter caches
its writer before the observer wraps the module. Forwarding that class alias
at call time, only in a scratch runner, passes the complete observer. No writer
output, attribution check or assertion is replaced. The excluded production
module and both legacy test files remain unchanged; `WIRING.md` gives Claude
the exact integration corrections. Runner sources and initial failures are
included in validation JSON for reproducibility.

The r64 scorebug regression's full generated-code hash necessarily changed.
Its updated test retains the exact one-word clock-color isolation check,
both-order composition and foreign-byte refusal, and passes all nine tests.
The new historical control separately preserves the actual base hook code.

The capability replacement passes the 117-entry registry schema; all paths and
command modules in the changed object exist. Full-registry file validation
stops at the base's unrelated missing `docs/research/apf_audio.md`, which is
recorded instead of being reported as a pass. Python compilation and
`git diff --check` pass. The largest measured test process used **908,812 KiB
RSS (about 888 MiB)**. The early memory gate and baseline run were not timed
for RSS. Pack/disc access is bounded or streamed. Scratch stayed below 200 MB,
no acceptance disc or pack copy was retained, and the final disk check is
recorded in the delivery receipt.

## HYPOTHESIS, gaps and Noah's witness list

The private input and supplied community clue contain no stopped guest PC,
actual collection list, live cache ownership or GPU completion state. An
unrelated cache hit/eviction is therefore a candidate explanation for the
testers' stall, supported by a native counterexample and the hook-removal clue.
It is not a proved identification of their incident. Healthy GPU behavior,
asynchronous resource lifetime, real cache allocation/freeing, actual memory
headroom, scene/GPU consumption and the omitted game systems remain unproved.
The fixture uses an 8 MiB resource heap; that is not measured console headroom.

Keep runtime off in Basic, Advanced and Experimental. The separate static v3
option retains its existing preset behavior. Noah's next played checks are:

1. Rebuild from the same supported clean source with the same game/team/mode
   settings that previously stalled. Compare `hooks` and `neutral` first;
   record the build/recipe, profile and whether HUD initialization reaches a
   playable first frame. Keep the existing six-profile CLI choices.
2. Continue through `pair` and `full`, then `transport`/`resources` controls as
   needed. On a stall, record the stopped PC and stack, collection names and
   cache fields, the polled fence and whether its completion arrives. A PC in
   `0x33660` alone does not identify the caller or cause.
3. Play consecutive games and mode-7 re-entry without restarting. Verify team
   changes, home/away orientation, logos, neutral fallback, live timeout marks,
   scores including three digits, possession, quarter/game/play clocks and
   event colors. Watch for disappearing glyphs, stale resources and hangs on
   leaving or loading the next game.
4. Check static v3 alone and runtime paired with its v3 XBE layout in both
   4:3 and widescreen, including the kick meter and lineup strip. Test the
   intended other-owner build only after the scorebug comparison is stable.

The shared UI and registry changes are fully specified in the R65 section of
`WIRING.md`. The feature capability handoff is updated; it retains
`offline-writer-proved` and `runtime.status=not-tested`. It must not be promoted
to a witnessed freeze fix from these CPU results alone.

## Delivery

Changes are confined to this worktree and delivered as an explicit-path commit
on `astra/r65-scorebug-freeze`, based on `be99b324`. Only the fifteen source,
test, report and evidence paths are included. `ASTRA_BRIEF.md`, scratch files
and private game assets are excluded. Git staging succeeded, so the normal
branch commit is used. The scratch delivery receipt records its identity and
the final disk/protected-file audit. Nothing is pushed.
