# r62 QB spy from man and rush

2026-09-06. Branch `astra/r62-qb-spy-man-rush`, base
`05d3ce950b08aec72558cb2f42a09b7bd1feb55c`.
**EXPERIMENTAL / UNWITNESSED. All presets remain off.**

Implemented man/rush entry paths through the existing `qb_spy` option and
`nfl2k5_qb_spy` owner. They share the existing zone-spy decision, snap identity,
release/pursuit latch and sealed intent table. Native man/rush callback
identities and fallback targets remain valid. This supersedes the deferred
man/rush implementation in `ASTRA_QB_SPY_RUNTIME_REPORT.md`; that report's
played-witness and movement-call-tree limitations still apply.

Inputs were the brief, project instructions/index, RC85 product changelog,
prior Astra report inventory, allocator/zone/defense reports, the read-only
`QB_SPY_RESEARCH_2026-09-04.md` memo and pinned retail executable/PLAY evidence.
No game, console emulator, GUI display, audio, network or push was used.
Unicorn executed bounded instruction fixtures only. Protected implementation
files and the protected reservation JSON were not changed. Their handoff is
the final QB-spy section of `WIRING.md`.

## Implementation and decisions

**PROVED: one expanded immutable request set.** Grow the existing owner from
1536 RX to **2048 RX**, retaining **768 RW + 512 RO**. This task's new allocation
authorization pays for 512 additional code bytes; no other owner's request,
writable budget, allocator page count or geometry changes. Generated content
is **1768 bytes**, comprising 1744 instruction/alignment bytes and 24 constant
bytes, leaving 280 bytes of RX fill. This is below the memo's 4096-byte total
code ceiling. The complete future-budget fixture has 52,352 RX, 4,096 RW and
8,640 general RO bytes available after allocation/alignment policy.

```text
(nfl2k5_qb_spy, code,      2048, 16)
(nfl2k5_qb_spy, data,       768, 16)
(nfl2k5_qb_spy, read_only,  512, 16)
```

The committed budget fixture replaces only this owner's code size. Its
requests and single apply transaction already appear in the full gate union
and every manifest-builder list; they now automatically include the extension.
The current complete union puts code at `0x14DDC40`, state at `0x14F3300` and
table at `0x1508C00`. Standalone code starts at `0x14DA000`. Assembly relocates
from the actual allocation, rather than depending on either observed address.

**PROVED: old allocations refuse.** An installed request set cannot grow in
place. A revision-1 1536-byte code allocation reports `foreign`, and apply
requires rebuilding from base with the full request union. No old instruction
or intent is copied into a newly sized allocation. Replay of revision 2 is
byte-identical, preserves an omitted installed table, and refuses changed
intent, partial installs, foreign dependencies, hooks, state, code or RO data
before returning any mutation. Receipts identify `model_version=2`,
`tier=zone-man-rush`, allocation, edits, hashes and exact changed-byte count.

**Decision: preserve native callback pointers.** The earlier tier-2 proposal
suggested retaining a delegate in record `+0x1C` and replacing each actor's
callback. Native man exchange at `0x1A4E49` compares another defender's callback
against literal `0x1A4DD0`. It can rewrite that peer's callback and targets at
`0x1A5057..0x1A507A`. A private per-actor delegate would invalidate the comparison
and could be overwritten by the peer. Instead, intercept supported callback
entries, including the common rush body, and retain the actual native callback
identities. Internal tail calls and peer rewrites consequently remain reachable
by the next Spy command. Unknown callbacks stay native. No extra delegate
table or writable record fields are required.

The three dispatch wrappers execute their original initializer exactly once
with ECX=actor and no stack arguments, including the man initializer's early
transition. They then clear matching stale spy records and preserve the native
return registers, flags and FP state. They never replace a man/rush initializer
with the zone initializer or overwrite the callback it selected. A command
issued before initialization survives; a command issued afterward is observed
at the callback entry. Ordinary command repetition preserves pursuit.

During an extension callback, the dispatcher saves the current AI pointer,
callback, primary target and secondary target on its stack. It borrows target
`+0x40` for the QB and clears `+0x48` while invoking spy movement. It restores
the native targets on return/fallback only if the AI pointer and callback still
match. A native possession transition that replaces the same state buffer's
callback owns its new targets; no stale callback or target is restored.
The zone path retains its existing persistent QB-target behavior. This avoids
nulling the receiver/blocker pointers required by ordinary man/rush fallback.
Targets outside the synchronous movement interval therefore remain native;
full game interaction with other consumers is part of the witness boundary.

The expanded unflagged ABI tests exposed an old assumption: `sub esp` changed
flags before they were saved. Zone prologues subsequently overwrote those
flags, masking the problem. The common dispatcher now reserves locals using
LEA and branches on its handled result before restoring entry flags. Man/rush
prologues containing only MOV/PUSH now resume with the original flags too.

## Retail hooks and native behavior

USA retail XBE SHA-256:
`73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9`.
All sites are pinned live instructions, not caves. Full native initializer and
callback dependency bodies are SHA-256 pinned, with only owned sites normalized.
The original five snap/zone/reset detours remain installed.

| Dispatch MOV start | Immediate changed | Original initializer |
| --- | --- | --- |
| `0x1B8658` | `0x1B865E`: `90 E1 2F 00` | rush `0x2FE190` |
| `0x1B8662` | `0x1B8668`: `B0 10 2F 00` | lane B `0x2F10B0` |
| `0x1B866C` | `0x1B8672`: `C0 5B 1A 00` | man `0x1A5BC0` |

Each complete ten-byte MOV is pinned and reserved. Only its four-byte
initializer immediate changes; its native writable dispatch-table destination
remains unchanged. The actual `0x1B85A0` table setup executes in the tests.

| Additional entry | Displaced bytes | Native continuation |
| --- | --- | --- |
| rush body `0x2FDF30` | `55 8B EC 83 E4 F0` | `0x2FDF36` |
| delayed rush `0x2FE130` | `56 8B F1 8B 46 20` | `0x2FE136` |
| lane B `0x2EFDB0` | `83 EC 18 53 55` | `0x2EFDB5` |
| man `0x1A4830` | `55 8B EC 83 E4 F0` | `0x1A4836` |
| man press `0x1A4DA0` | `8B 41 20 8B 90 10 03 00 00` | `0x1A4DA9` |
| man release `0x1A4D70` | `8B 41 10 8B 40 04` | `0x1A4D76` |
| man exchange `0x1A4DD0` | `55 8B EC 83 E4 F0` | `0x1A4DD6` |

**PROVED in bounded execution:** native rush callbacks `0x2FE120` and
`0x2FD930` both tail-call the intercepted `0x2FDF30` body. Expired delay rewrites
to `0x2FE120`, and the native later-rush branch rewrites to `0x2FD930`; a late
command still engages. Man initialization selects ordinary, press or exchange
callbacks, or takes the early native pursuit transition when no receiver is
found. Release/exchange rewrites to ordinary man remain intercepted. Native
peer comparison and resulting actor writes match retail in paired fixtures.

Active spies retain the existing four-yard shadow target, predicted lateral
position, snap baseline, strictly-more-than-three-yard lateral release and
one-yard-behind-line forward-motion gate. Forward/lateral pursuit stays latched
after retreat. Tests cover both field directions, each supported callback,
late/repeat commands, handoff, pass, dead phase, user takeover, command reset,
assignment reset, same-identity reinitialization, snap, roster substitution,
full record capacity and unknown initializer results. Active writes are bounded
to owned RW, valid actor fields or stack; RX/RO are never writable state.

Authored v1 intent and its 31-row limit are unchanged. The native loader and
paired table tests cover both zone buffers. Extension probes also execute the
same lookup against a loaded paired v1 identity. That test deliberately invokes
an extension callback with a zone-fallback identity; it does not establish a
new authored man/rush PLAY grammar. Actual authored Spy plays remain shallow
zone fallback; command spies provide the new man/rush entry paths.

## Verification and evidence limits

All tests run as plain standalone unittest scripts. Missing pinned evidence,
Unicorn or GNU as receives a precise skip; all evidence was present here.
Initializers and callback bodies execute actual retail instructions. Their
explicit helper boundaries cover state allocation, animation/event services,
operand/target selection and movement. The test file lists every modeled helper
and its cleanup ABI. The command, dispatch setup, assignment reset and PLAY
loader execute native instructions. This does not prove complete animation,
navigation, pursuit, tackle, allocator-service or event call trees.

FP assertions cover x87 control/status/tags/register values and XMM0-7, plus
nonvolatile registers and stack cleanup. Unflagged entries compare native GPRs,
flags and initialized stack save slots under three flag patterns. Uninitialized
local/alignment bytes are not asserted to match. No complete live x87 exception,
FIP/FDP or asynchronous-target-consumer proof is claimed.

| Command | Result |
| --- | --- |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_runtime.py` | 12 passed; 74.564 s; peak RSS 285,916 KiB |
| same file, `WriterTests.test_existing_qb_spy_flag_drives_all_four_status_dictionaries` added afterward | 1 passed; 13.389 s; peak RSS 158,192 KiB |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_unicorn.py` | 16 passed; 6.277 s; peak RSS 414,420 KiB |
| `python3 tests/mod_editor/test_nfl2k5_qb_spy_man_rush.py` | 13 passed; 7.281 s; peak RSS 607,136 KiB |
| same file, `ManRushTests.test_zone_and_extension_execution_in_full_union_both_orders` added afterward | 1 passed; 45.935 s; peak RSS 265,784 KiB |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 63 passed; 176.025 s; peak RSS 294,000 KiB |
| `NFL2K5_CAVE_MANIFEST=.scratch/spy-man-rush-manifest.json python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 75 passed; 261.524 s; peak RSS 452,644 KiB |
| `python3 tools/nfl2k5_qb_spy_runtime_assemble.py --check` | Exact generated-template match |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json --json` | Complete future-owner budget accepted |

The four-status test uses the existing protected dispatcher and bounded
synthetic XDVDFS fixture, proving `qb_spy=True` reaches the grown owner through
XBE/image write and read status dictionaries. No new product flag is required.
The writer suite also proves exact output receipts, immutable old-request
refusal, every owned hook byte's mutation refusal, table pairing, permissions,
manifest reservations, byte-identical complete-union forward/reverse replay,
and the bounded `python3 -m` copy recipe's refusal to overwrite an existing file
or read a disc as an XBE.

**Reservation audit:** the first cave-gate run had eight errors, all from the
protected manifest's obsolete grown-owner placements. It was not weakened or
regenerated. The scratch audit observes real writers on the complete current
gate XBE, records 9502 current spans, and preserves 3829 historical retail
reservations for unselected alternatives. Fresh mappings and child allocations
come solely from observed current owners. The generic gameplay-lever helper
is not separately registered as an owner; Coverage and Scramble own its calls,
as in the production manifest builder. Source fingerprints and allocation
evidence validate. This is explicitly an XBE-only audit, not a fresh disc-build
manifest or release sign-off. Claude must regenerate the protected release
manifest after integration.

`df -h /` reported 95 GiB free, below Noah's 100 GB floor. No real-disc build
was started. No pack or disc was loaded into RAM or retained in scratch. The
bounded synthetic status/copy fixtures use resolved TemporaryDirectories and
clean up on every exit. Logs, disassembly, planner results and JSON receipts
are retained under `.scratch/`; all measured processes stay below 2 GB.

Standalone patched XBE SHA-256:
`c927bee57c47f27ed2a8cff7c5b3eb1fabd78ef9ef695b64321b30b0b19693aa`.
File size: 12,300,288 bytes. Exact changed/appended bytes: **353,369**, including
allocator growth/boot-logo relocation. No executable bytes are distributed.

## Noah's witness list and remaining hypotheses

All following gameplay is **HYPOTHESIS / UNWITNESSED**. Use otherwise identical
Spy-off/on builds from the same base. Record build/XBE/table hashes, platform,
assignment opcode, defender, QB, field direction, callback and release frame.

1. Cold boot and enter practice, exhibition and franchise. Confirm normal
   kickoff, ordinary coverage and selected allocator owners before Spy trials.
2. Test man, press man, exchange man, ordinary rush, delayed rush and lane B.
   Issue Spy before initialization and after snap; compare stationary QB,
   left/right rollout and forward scramble on both hashes/directions. Require
   four-yard containment, the specified release and pursuit after retreat.
3. Repeat Spy after shadowing and pursuit; reset individually, audible to
   another assignment, start the next snap, substitute or injure the defender,
   and repeat hurry-up with the same actor addresses. Require no stale latch,
   frozen animation or unintended rearming after retirement.
4. Run crossing receivers, RB releases and man exchanges involving another
   defender. Ordinary defenders must exchange normally; an active spy must
   prioritize QB movement, then regain valid native targets when Spy ends.
5. Handoff/play action, thrown pass, free ball/fumble, interception/turnover and
   dead ball must select normal native follow-up behavior. Verify no stale
   callback/target restoration after a possession transition.
6. Human/CPU pocket and mobile QBs; Scramble+Agility totals 149/150/151 and
   odd/even Scramble. Take over the defender manually and return control.
   Require normal control/animation behavior; no tackle guarantee is claimed.
7. Recheck both zone callbacks and paired authored Spy plays, including clone,
   mirror, save/reload and pack import. An ordinary shallow zone without intent
   or command must remain ordinary. Compare with all selected owners enabled.

Still unproved: console/kernel acceptance of the v3 image, physical Xbox command
mapping, complete movement/animation/tackle/event call trees, synchronous target
borrowing's interaction with other native consumers, and unknown callback or
playbook-buffer families. No new authoring schema or larger intent capacity is
provided. Protected UI captions, registry refresh, staged closure and release
manifest regeneration remain the explicit integration handoff.

## Final validation and delivery

**181 unittest cases passed** across the commands above. The full-union
instruction test executes both zone callbacks, man and both rush entry families
after composition in both orders, checks engagement/release/latch and compares
the complete output bytes. Both XBE gates include forward, reverse, explicit-v3
and reverse-v3 owner composition. The memory gate passed with the unchanged
release manifest; the cave gate passed with the current scratch ownership audit.

`python3 -m py_compile` on all changed Python modules/tests and `git diff
--check` passed. The merged capability registry passes schema validation, and
every QB-spy evidence/backend/validation path passes the registry's file checks.
The attempted whole-registry file check stops at the pre-existing missing
`docs/research/apf_audio.md`; no whole-registry or staged-package success is
claimed. Both new capability commands resolve to their exact repository modules.

The XBE-only manifest observer completed in 45.85 s at 231,444 KiB peak RSS;
its source fingerprints and current allocation evidence passed. Scratch was
3.2 MiB before delivery metadata. No real acceptance disc exists to clean up.

The explicit-path staging command completed, but `git commit -- <13 paths>`
failed: Git could not create the worktree metadata's `index.lock` on its
read-only filesystem. The authorized delivery is therefore
`.scratch/r62-qb-spy-man-rush.bundle`, built with writable temporary Git metadata
and this report's base commit as its prerequisite. The bundle commit uses the
same 13 explicit product/source/test/report paths and excludes `ASTRA_BRIEF.md`,
`.scratch/` and proprietary game data. Delivery verification checks the exact
path set, committed file bytes, parent commit and bundle prerequisites; its
commit/hash receipt is `.scratch/spy-man-rush-delivery.json`. Temporary Git
metadata is removed on exit. Files remain in this worktree, its branch HEAD
stays at the base, and no push is performed.
