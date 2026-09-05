# Dedicated zone QB spy runtime, beta 62

Branch `astra/r62-qb-spy-runtime`, base `490b3c1268eb4515f7e3247d06cfe2306f141992`.
**EXPERIMENTAL / UNWITNESSED.** This implements the dedicated zone-spy tier of
`QB_SPY_RESEARCH_2026-09-04.md` §4. No game boot, GUI display, audio, network or
push occurred. Only this worktree and its scratch directory were written.
The research corpus, hub memo and retail inputs were read-only. The RC85
changelog and existing Astra reports informed the allocator, authoring and
composition work; their historical deferred-runtime claims remain historical.

## Delivered

- `mod_editor/core/nfl2k5_qb_spy_runtime.py`: strict `status` / pure-byte `apply`,
  dependency and hook pins, exact idempotent replay, paired intent compiler,
  exact receipts and explicit reservations. Foreign geometry/seals/digests,
  mixed hooks/code/table/state, incomplete allocation unions and changed replay
  tables refuse before returning any mutation.
- GNU `.S` source, reproducible assembler and checked-in Python byte template.
  End-user patching needs neither GNU as nor Unicorn/Capstone.
- Five live detours, listed below. Both zone callbacks check Spy before native
  receiver selection. The callback owns the QB target while he holds the ball,
  shadows predicted lateral position at four yards of defensive depth, and
  latches pursuit on a forward or wide escape.
- A read-only v1 table derived from existing versioned authoring receipts,
  never from a guessed PLAY opcode. The native command bit independently opts
  a zone defender in; it needs no authored table row.
- Standalone writer/Unicorn suites, full owner union in both XBE gates and the
  manifest builder, permission/instruction/manifest tests, a schema-valid
  capability handoff and complete protected integration instructions in
  `WIRING.md`. No protected implementation or reservation JSON was edited.

## Decisions and budget

The original 2,048-byte immutable budget is split into **1,536 RX + 512 RO**.
This pays for the separately requested lookup without taking extra immutable
or RW bytes. State remains **768 RW**, comprising a 64-byte header and 22
32-byte records. Generated content is 1,488 bytes: 1,464 bytes of instructions
and internal alignment plus 24 constant bytes, followed by 48 allocation fill
bytes. Only 48 RX bytes remain, so man/rush wrappers cannot fit this revision.

`REQUESTS` uses the budget's owner name `nfl2k5_qb_spy` and 16-byte alignment:

```text
(nfl2k5_qb_spy, code,      1536, 16)
(nfl2k5_qb_spy, data,       768, 16)
(nfl2k5_qb_spy, read_only,  512, 16)
```

The committed budget fixture is unchanged. `.scratch/spy-budget-requests.json`
substitutes these three rows for its two QB-spy rows. The allocator planner
accepts the complete future-owner budget: 51,584 code bytes, 4,096 RW bytes,
and 12,800 general RO bytes remain available. No old owner is displaced and
no retail cave, unknown region, virtual gap or unreserved tail is allocated.
The table's 512 bytes hold a 16-byte header and **31 records**. More records
refuse. This cannot hold one authored spy for every one of the 32 NFL books
simultaneously; command spies remain independent of that limit. Capacity was
chosen explicitly to stay within the brief's budget.

The full current owner union locates the spy at RX `0x14DA010`, RW
`0x14F2000`, and RO `0x1507000`. Standalone RX begins at `0x14DA000`; code is
relocated from the allocator result, never tied to either observed address.
The XBE is 12,300,288 bytes. `tests/nfl2k5_allocator_stack.py` includes kickoff,
scorebug runtime, momentum, defensive try, zone drops, music metadata, stadium
storage, Coverage, slow-QB acceleration, and QB spy; the gates additionally
compose the existing retail owners before growth. Forward/reverse replay is
byte-identical.

## PROVED instruction and identity evidence

The source retail XBE SHA-256 is
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
These are live hook sites, not storage:

| VA | Retail bytes | Behavior / continuation |
| --- | --- | --- |
| `0x1A5790` | `55 8B EC 83 E4 F0` | First zone callback; displaced prologue resumes at `0x1A5796` |
| `0x1A5090` | `55 8B EC 83 E4 F0` | Later zone callback; resumes at `0x1A5096` |
| `0x0B6FB3` | `C7 05 B8 02 E6 00 0E 00 00 00` | Native 13-to-14 phase store; capture snap QB/x, clear records, resume `0x0B6FBD` |
| `0x1B8570` | `33 C0 3B D0 89 41 04` | Native assignment reset; clear matching state, replay all seven bytes, resume `0x1B8577` |
| `0x18AEFC` | `0F BE 41 2E 8B 5E 0C` | Individual reset command; clear command bit and matching state, resume `0x18AF03` |

**PROVED:** Native `0x18ADA0`, adjustment 12, executes the unedited OR at
`0x18ADE2`, setting `[[actor+0x20]+0x420] & 0x20000000`; repeating it does
not toggle or reset our pursuit record. Its naming as the Xbox Spy command
and physical button mapping retain the memo's identification/witness limits.
The snap hook preserves the CMP flags used by the continuation after its MOV.
Its retained x is captured at that native phase store, before a delayed first
zone invocation. Assignment reset and new snaps clear state; a substituted
roster identity refreshes its record while retaining the same snap baseline.

**PROVED:** The two loaded PLAY bodies are `0xB75A40` and `0xB88DD0`, selected
by retail `0x0E2F10` (body size `0x13390`). The actual retail loader at
`0x161E30` copies and relocates the authored resource into each buffer in
bounded tests. Runtime derives play index and slot from the assignment pointer
within the bounded 270-by-96-byte PLAY table (`body+0x33FC`, slots at `+8`).
It checks a table row against FNV-1a hashes of the UTF-16 book/play names and
exact assignment descriptor plus its two encoded nodes. Names are bounded to
63 UTF-16 units, and node pointers must stay within the native pool. Row format
is `<I H B B I I`: book hash, play index, slot, row version 1, script hash,
play-name hash. Header is `<4s I I I>`: `QBS1`, version 1, count, reserved zero.
Rows are sorted and unique; remaining bytes must be zero.

The writer checks the resource SHA-256 against its compiler receipt before
reading `nfl2k5_spy_intent/v1` records. It validates defensive family and the
existing centered 3-5 yard shallow-zone fallback. This uses the already-built
clone/mirror/pack/project intent contract; it never changes PLAY bytes or sets
`runtime_available` in an offline authoring receipt. The test compiles a real
ATL Nickel MLB-slot-5 spy at play 254, then uses the native loader to prove
lookup in both buffers. Changing its name, book, slot or script prevents
activation. Resource-only imports without the receipt cannot establish intent.
FNV identity hashes are bounded runtime selectors, not cryptographic proofs;
the paired source hashes and immutable allocator seals serve the latter role.

**PROVED:** For a flagged eligible actor, held owner must be the snap's cached
QB, have native actor type 1 and roster position 0, and belong to the offense.
The attached type is read from **the holder**, not `[ball+0x1C]`. Ordinary
Human/CPU QB controller indices and tested 149/150/151 Scramble-plus-Agility
combinations do not select the spy decision. The defender's native controller
index and player-lock flag yield control on user takeover.

Target x is `clamp(QB_x + 0.5 * QB_vx, -2164.08, 2164.08)` cm. Target z is
`line_z + direction * 365.76` cm. Direction follows the native signed-depth
transform's offense direction field. Release is signed depth **at least
-91.44 cm with strictly positive forward velocity**, or absolute displacement
**strictly greater than 274.32 cm** from snap x. Equality at three lateral
yards stays contained. Mode 2 stays pursuit even if the QB retreats. Ordinary
steering uses `0x1A4170` with native ret-16 ABI; pursuit uses `0x1ADF90` with
native ret-32 ABI and retail pursuit constants. The zone callback remains the
entry while pursuing, so it can inspect possession on the next invocation.

Crossing receivers and releasing RBs cannot invoke `0x1A1510` on an active spy
path: the primary target is QB and secondary target is cleared. Handoff or
turnover calls native transition `0x214B90` with initializer `0x2EB330`.
Pass/free ball, dead-ball predicates or non-live phase return to the original
zone path with QB targets and command bit cleared. Ended mode 3 blocks a repeat
command from rearming in the same assignment; reset or next snap can rearm.
Resetting an authored spy restores its authored assignment, so its table can
still request Spy. Resetting a command-only spy leaves ordinary coverage.

**PROVED within test boundaries:** added instructions preserve nonvolatile
registers, stack cleanup, x87 control/status/tags/registers and XMM0-7 in the
fixtures. Unflagged paths replay both prologues with the same GPRs, flags and
stack as retail at entry+6. Active writes target owned RW, valid actor state or
stack; snap additionally replays the existing live-phase store. Finite value,
wrong-team, non-QB, user-control and full-22-record cases fall back safely in
the tested contexts. Runtime table pages are read-only and nonexecutable.

The full movement and transition callees are **observation boundaries** in
these fixtures: tests record arguments and return using the pinned native ABI.
They do not prove the complete navigation, animation, tackling or transition
call tree. Loader/command/assignment reset execute actual retail instructions
without stubs. Maximum routine budgets are 10,000 instructions for spy probes
and 60,000 for the full PLAY copy/relocator. XBE sections are mapped using their
actual page permissions. Fixtures stay bounded; packs/discs are never loaded
wholesale into RAM.

## Tier 2: exact deferred man/rush specification

No man/rush initializer immediate or callback is changed. The remaining 48 RX
bytes cannot contain three initializer wrappers, callback delegates and ABI/
lifecycle guards. The memo's proposed next revision allows up to `0x1000`
**total code**; it needs a revised allocator budget before implementation.
Keep RW at `0x300` if possible, using each record's reserved `+0x1C` dword for
its original callback delegate. Do not take another owner's budget.

| Immediate VA | Pinned value | Native initializer / initial callback(s) |
| --- | --- | --- |
| `0x1B865E` | `90 E1 2F 00` | PLAY `0x0B`: `0x2FE190`; `0x2FE120` or `0x2FE130` |
| `0x1B8668` | `B0 10 2F 00` | PLAY `0x0C`: `0x2F10B0`; `0x2EFDB0` |
| `0x1B8672` | `C0 5B 1A 00` | PLAY `0x0E`: `0x1A5BC0`; ordinary `0x1A4830` and possible `0x1A4DD0` paths |

Each four-byte field is the immediate of its existing ten-byte dispatch-table
MOV, beginning at `0x1B8658`, `0x1B8662`, `0x1B866C`. Pin each full instruction
and initializer/callback boundary. The wrapper must call the original
initializer exactly once with its actual incoming ABI, then inspect the valid
`[[actor+0x20]+0x310]` callback and retain a supported original delegate before
installing a tier-2 Spy delegate. Never substitute a zone initializer for a
man/rush state. Both the native initializer's early returns and every callback
rewrite must be traced before it can be intercepted.

The delegate must observe command requests issued **after** initialization,
retain the snap identity/release policy above, and invoke the original callback
with its original ABI when unrequested. A presnap-only flag hook cannot prove
that. It must survive both rush callbacks, man exchange/transition paths and
later reassignment; replace/clear delegates on audible, reset, snap and roster
change. Unknown callback values remain retail. Loss of possession must enter
the appropriate native initialized transition, without restoring a stale
man/rush pointer afterward. Authored man/rush intent would require an explicit
versioned authoring/table schema extension; v1 here accepts only zone fallback.
Acceptance must execute all three native initializers, their live delegates,
late/repeat commands and unflagged ABI paths, in addition to the current suite,
all-owner gates and Noah's man/rush witness cases. This is a specification,
not delivered tier-2 gameplay support.

## Validation and corrections

Final commands from this worktree, plain standalone unittest:

| Command | Final result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 10 passed, 34.406 s |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_unicorn.py` | 16 passed, 6.385 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 51 passed, 118.697 s |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 63 passed, 196.445 s |
| `python3 tools/nfl2k5_qb_spy_runtime_assemble.py --check` | Exact template match |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_runtime.py TableTests.test_assembler_reproduces_shipped_bytes` | 1 passed after adding precise non-GNU-as skip |
| `python3 tools/nfl2k5_xbe_space.py plan --requests .scratch/spy-budget-requests.json --json` | Complete budget accepted |
| `python3 -m py_compile` on all changed/new Python modules; `git diff --check` | Passed |

The tests skip precisely for absent pinned XBE, extracted PLAY archive,
Unicorn, or GNU assembler as appropriate. Gate Capstone skips are retained.
The capability row is validated in a scratch in-memory merged registry; the
canonical registry remains for integration.

Earlier runs found and corrected: manifest module-name/owner-name mismatch;
an insufficient 40,000-instruction **test** limit for the native loader; an
unnecessarily broad lineup dependency pin overlapping existing kick-rule
entry hooks (replaced by exact untouched reset-call/argument pins); and two
cave-gate legacy assumptions when the complete union automatically selects v3.
The latter now selects the existing v3 mapping/reference checks from the
actual image format. Its raw immediate candidates remain visible; it does not
call those arbitrary integers reachable code. No allocator suite marked
known-red in the brief was edited. The protected manifest was not regenerated,
and no fresh full-disc manifest/build/packaging success is claimed.

Reproduction logs, code/lookup receipts, allocator plan and prior-report
inventory are under `.scratch/spy-*`. Final command-only XBE SHA-256:
`f47c937d2f5c093e0534d765f558a2f144697aabc71d1d247394b8d491bc0914`.
The single authored ATL fixture gives
`23fdfba46b8c9772208811adda06fba1c88a7c9692cc9870ee24fa003395f3df`.
Each reports 353,313 changed/appended bytes, including allocator growth and
its relocated boot bitmap. These are evidence identities, not distributed
XBE assets. No game bytes are included in the commit.

## Noah's witness list and remaining hypotheses

All gameplay below is **HYPOTHESIS / UNWITNESSED**. Use paired otherwise
identical Spy-off/on builds/plays. Record the exact build/XBE/table hashes,
platform, defender position, target, callback and release frame alongside
video. First cold-boot a properly wired v3 build and verify title/game entry,
normal kickoff, ordinary coverage, SPECIAL and the other selected owners.

1. Stationary QB, left/right rollouts and straight-ahead scramble in both
   field directions and hashes: hold four-yard depth, shadow sideways, release
   at the specified gates, retain pursuit after retreat, no immediate blitz.
2. Crossing receiver and RB release: QB priority stays active. Handoff, play
   action, thrown pass, fumble/free ball, interception/turnover and dead ball:
   end or retain priority appropriately, with normal subsequent movement.
3. Pocket/mobile QBs, Human/CPU, Scramble-plus-Agility totals 149/150/151 and
   odd/even Scramble: record release and animation choice; containment must not
   accidentally depend on an animation table. Ratings do not guarantee tackles.
4. Start with ATL Nickel f23, MLB slot 5, and the paired authored Spy. Compare
   both zone callbacks and the in-game command, then cloned, mirrored, packed,
   imported and reloaded projects with the freshly paired table. Verify that
   the same shallow zone without intent/command retains ordinary coverage.
5. Repeat command, individual reset, audible, next snap, substitution, injury,
   possession change and user takeover: no sticky pursuit, frozen animation,
   lost coverage or control override. Test a delayed first callback and a
   second consecutive play with the same QB/defender addresses.
6. Zone, man and rush donors: this revision should improve **only zone**
   requests. Man/rush must be described as unsupported and compared to retail,
   not called fixed. Repeat the full witness on them after tier 2 is built.
7. Practice, exhibition and franchise, another game/mode transition and
   save/reload. Record resource identity failures or capacity refusals exactly.

Unproved: actual loader/platform acceptance of v3, full movement/animation and
native pursuit-transition call trees, complete CPU/gameplay behavior, command
button mapping, and other playbook buffer families beyond the two identified
native buffers. The stock authoring fallback depth range remains 3-5 yards;
this runtime uses its fixed four-yard default, not a per-row tuning setting.
No arbitrary pointer safety, automatic tackle guarantee, complete live x87
exception/FIP/FDP proof, or runtime debugger memory-dump acceptance is claimed.
Protected Build/UI/closure/registry/manifest integration is the concrete
handoff required by the brief, not silently treated as already installed.

## Commit delivery

Commit scope is the 13 explicit product/source/test/capability/report/handoff
paths. `ASTRA_BRIEF.md`, `.scratch/`, proprietary resources and generated game
images are excluded. The requested explicit-path staging/commit is attempted;
if Git metadata is read-only, the authorized fallback is
`.scratch/r62-qb-spy-runtime.bundle` with the original HEAD as its prerequisite.
All edited files remain in this worktree. No push is performed.
