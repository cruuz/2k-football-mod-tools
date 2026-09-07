# r63 scorebug game-entry freeze investigation

2026-09-07, branch `astra/r63-scorebug-freeze`, base `059b52a`.
**EXPERIMENTAL / UNWITNESSED. The reported gameplay freeze remains unproved
and unfixed.** This delivery completes the brief's offline investigation and
its explicit fallback. No first failing hook or hook-starved completion was
found in the supported CPU fixtures. The next gameplay comparison is reduced
to **`hooks` and `neutral`**, with the other four probe names retained.

The private attachment was read before investigating and was not copied into
the repository. The community observation supplied in the brief prioritizes
the binding path, but does not supply a stopped guest PC or the completion
state. It is not a gameplay witness by Noah. The RC85 baseline and the prior
ASTRA reports were reviewed; the read ledger stays in scratch.

## What was built and preserved

[Entry fixture](tests/nfl2k5_scorebug_entry_fixture.py) and
[standalone tests](tests/mod_editor/test_nfl2k5_scorebug_freeze.py) add the parent
game initializer, complete scorebug frame continuation, native completion
writers and both special lookup-context branches to the existing investigation.
[Bounded traces](docs/scorebug_ingame/freeze/trace.json) record actual PCs,
instruction counts, polled addresses, writes and every omitted parent call.
[Validation](docs/scorebug_ingame/freeze/validation.json) records the exact runs.

The production owner and resource compiler are unchanged. No speculative
defer, reorder, timeout, forced completion or replacement wait is shipped.
There is no failing native hook trace against which such a change could be
proved. Both hooks, their ABI, receipts, replay, six probes and the
1,408-byte RX / 128-byte RW requests remain intact. Basic, Advanced and
Experimental still explicitly set `scorebug_runtime=False`.

The brief's older binary identity is not the current HEAD identity. Local
history comparison with `cf349b7` confirms that later work added private FONT
binding, the possession callback, compact scores and branch shortening. The
current owner uses 1,395 of its 1,408 bytes. At the standalone sites RX
`0x14ba2c0`, RW `0x14bb000`, its padded code SHA-256 remains
`d3331c84b984f6e4b198135891e964a6a038105fc8f995a5895a76d89149ffc4`.
The installed standalone XBE remains
`f2f2f59fc1d33bc03300922fcea3c3484e77b5be2d1522cde7c31de341ab927e`.
Other allocator unions relocate these sites normally.

The historical comparison evaluates only four byte-emitter functions from
the hash-pinned local beta-61 source, then runs those instructions in the
current resource fixture. It does not reconstruct a beta-61 disc or claim a
historical game-entry witness. CI without that local Git history precisely
skips that comparison; current-owner evidence remains independent of history.

## Complete runtime-hook map

`nfl2k5_scorebug_runtime.HOOKS` contains exactly these two call sites. The
private possession text callback is installed through writable text descriptor
fields, not another patched native call site.

| Hook | Interrupted routine and entry path | State and continuation |
| --- | --- | --- |
| Setup `0xfce56`, retail `e845f3ffff` | Parent game initializer `0x64710`, call `0x647e0 -> 0xfccd0`. `0xfccd0` has already found `score_bug`, found its instance, initialized the camera and resolved native text/material records. The hook calls the displaced `0xfc1a0` once, then resolves materials and TXTR/FONT descriptors. | Native predicate `0x62550` skips this setup for mode words 0..3 (practice/training); ordinary games 4+ enter it. At a fresh setup the scorebug enabled word `0xa95520` is still zero. The hook returns to `0xfce5b`; native `0xfce5c` enables it, `0xfce66` returns success, and parent `0x647e5` continues the other subsystem initializers. The parent writes its ready flags at `0x6499b/0x649a5`. |
| Update `0xfcfa2`, retail `e819faffff` | Main update `0x64cd0 -> 0xfce70`. The frame routine checks enabled state, advances slide/timer fields and writes native material visibility before reaching the call. The hook forwards the float argument to the displaced `0xfc9c0` exactly once. | Native visibility/game-state processing completes first; the owner then updates timeouts, scores, down state and clock color. It returns with `RET 4` to `0xfcfa7`, after which the native instance transforms and score-flip processing continue through `0xfd427 RET 4`. An early disabled-scorebug frame does not reach this hook. |

Static callers of `0x64710` include `0x64b10` (reset/reentry), `0x64c70`
(state-driven entry), `0x84d60` and `0x15d930/0x15dbf0`. Not every caller's
world state is executed here. Mode 4 and franchise mode 7 are exercised in
the parent fixture; the four practice/training modes exercise the real
negative predicate. Rendering is a later path,
`0x64f80 -> 0x646b0 -> 0xfc360`; executing the frame updater alone does not
execute its GPU consumers.

## PROVED within the bounded fixtures

The parent fixture executes the actual instructions of `0x64710`, including
the real mode predicate and nested `0xfccd0`, installed setup hook and native
returns. **82 unrelated parent subsystem calls are explicit host boundaries**
in the game cases; their addresses, supplied return values and stack cleanup
are recorded. This is a stronger continuation test, not full game emulation.

| Current probe, mode 4 | Registered TXTR / private FONT count | Parent instructions | Complete first scorebug frame instructions |
| --- | ---: | ---: | ---: |
| `hooks` | 44 / 0 | 35,732 | 15,140 |
| `neutral` | 52 / 7 | 35,342 | 15,152 |
| `full` | 308 / 7 | 103,790 | 15,152 |

The original 44 resident textures are included in those TXTR counts. The
larger ordinary resource list makes the full lookup slower, but it returns.
Each installed setup and update entry executes exactly once, as does its
displaced native callee. Setup with absent custom resources hides both panel
materials and returns; neutral/full bind nonnull native descriptors and
return. Mode-7 reentry and a control restoring only the two native calls in
the same allocated, fully loaded CPU image also return. No setup or frame
case enters `0x432d0` or `0x33660`.

Special contexts were the important v8 coverage gap:

- `0x449e0` walks contexts at `0xb09578` and calls `0x443d0`. An ordinary
  context uses its `+0x0c` resident linked list and native UTF-16 equality.
- Nonzero context `+0x10` selects a cache, with name hashing at `0x38600`,
  record lookup at `0x42c90` and optional scheduling through `0x442f0`.
  Pending states 1/2 return unavailable rather than waiting. A cold matching
  index entry can queue work: the new test observes state 1 and one queue
  record while `0xb09584` stays busy. `0x442f0` returns without submitting
  I/O in that busy case. Thus an unconditional claim that setup lookup can
  never schedule resource work would be too strong.
- Nonzero context `+0x14` selects `0x42e40`; readiness must be state 3 at
  that object's `+4`. Earlier states return unavailable. Ready entries use
  the native hash/offset index. Both branches are exercised at states
  0/1/2/3 before a real resident HUD context, with completion withheld.
  Setup still returns and the native fallback supplies descriptors.

These synthetic valid context shapes are not the community tester's live
list. They close branch-coverage gaps without proving that list's contents,
acyclicity, cache capacity, lifetime or thread safety.

## Native completion traces

**Collection wait.** `0x432d0` polls `0xb09584` through `0x432c0`; zero means
idle. The back edge is `0x432ec -> 0x432e0`, which calls the native event pump
`0x38f50 -> 0x38cd0`. Native collection opener `0x43db0` sets ECX=1 at
`0x43ddb` and calls writer `0x42fc0` at `0x43de6`. Native EOF processing at
`0x43880` zeroes ECX and calls that same writer at `0x43885`, before closing
the handle and invoking the collection callback at `0x438a1`.

The new fixture enters the actual opener with only `0x48ef0` replaced by a
successful VFS-open boundary over a supplied appendix extent. Native code
arms the busy flag, installs the context/heap and submits the first read.
With OS completion withheld, the wait reaches its **4,000-instruction
bound**, repeatedly reading busy=1; neither runtime hook has executed.
Resuming the same suspended stack with host disk events routed through the
real native pump delivers **542 callbacks** for the 264 TXTRs and seven
FONTs. The native reader/relocator/registry processes them; the host never
clears the polled flag.

The test deliberately chooses `0xfccd0` for the collection's optional
completion callback. In that schedule the observed order is:

```text
0x43db0 -> 0x43de6 -> 0x42fc0          [0xb09584] = 1
0x432d0 -> 0x432c0 -> 0x432e0
  -> 0x38f50 -> 0x38cd0               host completion absent: bounded spin
  -> actual disk callback(s)
  -> 0x43a20 -> 0x43880 -> 0x42fc0    [0xb09584] = 0
  -> 0x438a1 -> 0xfccd0 -> 0xfce56
  -> owned setup -> 0xfc1a0 -> binding
  -> 0xfce5b -> 0xfce5c               [0xa95520] = 1
  -> collection/pump return -> 0x432c0 -> 0x432ee RET
```

The busy-clear writer precedes binding. The fact that setup precedes the
scorebug-enable writer cannot deadlock that writer in these tests: setup
does not poll enabled state. The optional completion callback choice is a
fixture schedule, not proof of the real game's registered callback address.

**GPU completion wait.** `0x33660` polls `[ESI+8]`, where ESI is its input
object. `0x3367f -> 0x33670` yields through `0x341a0`, then reloads at
`0x3367a`. Native `0x334e0` constructs packet words
`0x81d8c, 0x33410, object`; `0x335a3` arms `[object+8]=1`. Callback
`0x33410` reads its cdecl argument and writer `0x33414` clears `[object+8]`.

After successful native setup/frame, the test lets the actual packet builder
arm a bounded command-buffer object. With completion withheld it reaches
the **1,000-instruction bound**. Delivering the packet's actual callback on
the same suspended stack clears the flag at `0x33414` and returns in
**19 further instructions**. The trace records the concrete heap address and
packet; it is a fixture allocation, not a guest address from the reported
freeze. GPU packet execution remains a host event. No runtime binding hook
occurs between that test's fence arm and clear.

## HYPOTHESIS and why an offline fix is not justified

The supplied files contain executable instructions and serialized resources,
not a stopped game, live kernel scheduler, VFS handles, GPU command stream or
actual heap/list lifetime. This fixture supplies an 8 MiB resource heap;
that is not measured headroom on a 64 MiB machine. It executes TXTR, FONT
and AUSB handlers, with other old collection handlers skipped. Scene
decompression is separately checked by the existing native suite; this
entry fixture registers its decoded scene explicitly. Retail font slots,
world predicates, animation and game objects are also supplied inputs.

The parent has no fixture for those 82 other subsystem calls, including their
resource changes and render drains. The first-frame test stops at the native
CPU return, before GPU consumption. A graphics submission/fence failure, a
different live lookup context or lifetime, insufficient/fragmented memory,
VFS behavior, or an exception on the actual hook stack therefore remains
possible. The reported success after removing bindings increases the
priority of these paths but does not select one of them. Neither of the two
bounded withheld-completion spins is evidence that the hook caused the
reported freeze. No completion flag is forcibly cleared in production.

## Two-profile witness decision

Keep the six-name public matrix and its exact receipts. For the next witness,
run just these two fresh builds from the same clean source, with the same
teams/settings and no unrelated optional changes:

| Profile | Installed hooks | Added TXTR / FONT count | Added native resource heap |
| --- | --- | ---: | ---: |
| `hooks` | both | 0 / 0 | 0 bytes |
| `neutral` | the identical owner binary | 8 / 7 | 380,800 bytes |

The current full set adds 1,757,056 native heap bytes. The neutral row keeps
the current private-font contract, so a failure there cannot uniquely be
attributed to a team texture. Both rows install the same RX/RW requests;
hooks-only still runs missing-name/fallback logic and hides missing panels.

```bash
python3 -m tools.nfl2k5_scorebug_reference apply '/path/to/retail.xiso.iso' '/path/to/disposable/hooks.iso' --runtime-probe hooks
python3 -m tools.nfl2k5_scorebug_reference status '/path/to/disposable/hooks.iso' --runtime-probe hooks
python3 -m tools.nfl2k5_scorebug_reference apply '/path/to/retail.xiso.iso' '/path/to/disposable/neutral.iso' --runtime-probe neutral
python3 -m tools.nfl2k5_scorebug_reference status '/path/to/disposable/neutral.iso' --runtime-probe neutral
```

Reuse one disposable image location sequentially if needed to preserve the
100 GB free-space floor; retain its `.scorebug.json` receipt before replacing
it. These are witness recipes, not commands run by this session.

| Result | Decision |
| --- | --- |
| `hooks` fails, `neutral` fails | Added descriptors are unnecessary for failure. Prioritize hook execution/stack/CPU state, missing-name lookup and the grown executable; obtain the stopped PC. |
| `hooks` passes, `neutral` fails | Successful binding or the minimal resource/font addition is required. Prioritize descriptor lifetime, native special lookup state and first GPU consumption. Full-set size alone is insufficient as an explanation. |
| Both pass | Hooks and minimal binding work in this build. If the full-set failure reproduces on the same compiler, focus on resource-specific/volume/composition state. Historical full failure alone does not establish current full behavior. |
| `hooks` fails, `neutral` passes | Prioritize absent-resource/fallback behavior or inconsistent reproduction; repeat the pair under identical conditions. |

This pair decides the next investigation branch. It does not promise a
unique root cause from two pass/fail bits. The historical community report
is the reason not to spend the next witness on all six profiles again.

Noah's witness list:

1. Record the exact game build, emulator build/host, source identity, mode,
   settings and both receipts. Use TB at NE exhibition first; record time
   to the first live frame, several plays, menu return and a second game.
   Repeat the discriminating result in franchise.
2. On a freeze, record the stopped PC, stack and registers. For the loader,
   include `0xb09584`, cursor `0xb09598/9c`, end `0xb095a0/a4`, context head
   `0xb09578`, special pointers `+0x10/+0x14` and pending request/callback.
   For `0x33660`, include ESI and `[ESI+8]`, the command packet and whether
   callback `0x33410` executes. For a fault in owned code, include ESP,
   EFLAGS, CR0/CR4 and the failing instruction. Allocation addresses come
   from that build's receipt, not the standalone fixture addresses above.
3. On a passing runtime row, check both sides' timeouts 3..0, score changes
   and flips, possession, down/distance changes, the under-five-second
   clock boundary, reset/reentry and private-font scope. Neutral is expected
   to show neutral artwork. Full team artwork and created-team fallback
   still require a later successful full-resource gameplay witness.

## Validation and delivery

Final command results are recorded in the linked validation JSON and the
table below. Every suite runs as standalone `python3 file.py -v`; the new
trace suite also accepts `NFL2K5_SCOREBUG_FREEZE_TRACE=/path/to/trace.json`.
Retail/Unicorn/Capstone/Pillow absence produces a precise skip. Assertions
and the CPU instruction bounds are not converted into skips.

| Standalone command | Passed | Skipped | Peak RSS, KiB |
| --- | ---: | ---: | ---: |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_freeze.py -v` | 7 | 0 | 325,888 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_runtime.py -v` | 12 | 0 | 292,680 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_native.py -v` | 4 | 0 | 217,944 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_resources.py -v` | 6 | 0 | 174,212 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_fonts.py -v` | 9 | 0 | 291,824 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_projection.py -v` | 14 | 0 | 307,592 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_exact.py -v` | 8 | 0 | 291,716 |
| `python3 tests/mod_editor/test_nfl2k5_scorebug_versions.py -v` | 4 | 0 | 159,828 |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py -v` | 79 | 0 | 313,592 |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py -v` | 95 | 0 | 505,072 |

**238 passed, zero skipped and zero failures across 10 final suites.** Peak RSS was 505,072 KiB, below 2 GiB. A separate absent-evidence check correctly skips all seven new native cases. Root free space at validation was 108,757,671,936 bytes.

Development found two fixture errors, not game defects: the font reader needs a Path rather than a PackView, and the exploratory first frame needed a possession-record chain. Both were corrected. The initial four-case and expanded six-case suites passed before the final seven-case run; the validation JSON preserves these distinctions.

Both XBE gates retain their complete owner union in both orders and both
allocator configurations. Existing runtime checks cover the preserved
register/flags/x87/SSE contract, foreign-byte refusal, zero-change replay,
receipts, all probe profiles and transaction rollback. The new fixture does
not weaken or replace those tests.

No protected file, static scorebar module, other worktree, production
manifest or product integration is changed. No new owner, option, preset,
status key, allowlist line or runtime import is needed, so there is no new
`WIRING.md` handoff. No console emulator, GUI, audio, network, disc build or
push was used. Only bounded CPU execution and streamed retail-resource reads
were performed; temporary transaction fixtures are deleted by their existing
context managers. Scratch stays below 200 MB and the root filesystem stays
above 100 GB free.

Delivery uses the authorized isolated-metadata commit and bundle fallback.
The first explicit-path staging call succeeded, but final staging refused
`index.lock` with a read-only filesystem error. The isolated branch is
`astra/r63-scorebug-freeze`; its commit contains only this report, the new
fixture/test files and their two JSON artifacts. The bundle is
`.scratch/r63-scorebug-freeze.bundle`, based on `059b52a`; the exact commit
and import verification are recorded in `.scratch/DELIVERY.json`.
`ASTRA_BRIEF.md` and `.scratch/` are excluded from the commit. Files remain
in this worktree, the shared branch is not advanced, and nothing is pushed.
