# r62-screen-hooks: second screen timing experiment

2026-09-06. Branch `astra/r62-screen-hooks`, base
`3aa217a4a851eaa8239cdfcfa6a0b7c7414c0798`.
**EXPERIMENTAL / UNWITNESSED. All presets OFF.**

Implemented both screen-scoped hooks, reproducible GNU assembly, pure XBE
status/apply APIs, exact receipts, a bounded development CLI, standalone tests,
the complete allocator union and manifest-builder ownership. Shared product
integration is specified in `WIRING.md`; protected files were not edited.
No gameplay, game boot, console emulator, GUI display, audio, network or push
was used. Unicorn executed bounded instruction fixtures only.

Authority: hub `SCREEN_PASS_RESEARCH_2026-09-04.md` section 4, the beta-61
`ASTRA_SCREEN_PASS_REPORT.md`, the RC85 product changelog, the allocator
scale-out and integration reports, and pinned retail bytes checked against
the read-only Ghidra corpus. Tier 1 A-D and the wizard already exist. Noah has
not witnessed that data tier. This delivery is an independent second
experiment, not a claim that a remaining gameplay failure has been isolated.

## Decisions and implemented behavior

**PROVED in the bounded instruction tests:**

| Hook | Pinned VA / file offset | Displaced bytes | Policy |
| --- | --- | --- | --- |
| Block completion | `0x23ECD2` / `0x22ECD2` | `d94660d81d80414e00`, 9 bytes | For a matching current, nonterminal, expired finite screen hold during phase 14, keep the native task active while the supplied snap clock is in `[0, 0.8)`. At 0.8 and later the original completion decision runs. |
| QB timer store | `0x19C7E9` / `0x18C7E9` | `8b4c240c894e60`, 7 bytes | A matched current pass with an encoded default delay stores float32 0.6. Every positive explicit PLAY delay survives. |

**HYPOTHESIS:** these fixed timing policies improve escort/receiver coordination.
The 0.8 and 0.6 values follow the memo's experiments, not live calibration.
The clock is the existing native `[0xE6029C]+0x10` clock used by the blocking
routine. Fixtures supply this clock; full game-loop advancement is outside the
proof. The guard never shortens a positive native hold, rewrites its timer,
forces a release, chooses a defender, weakens coverage or forces a throw.

The pass initializer's native result remains in its original stack local.
On the policy path only the intended output ECX/task timer changes; other
registers, flags and x87/XMM state survive. Classification uses integer
instructions only. Both block paths execute the original FLD/FCOMP pair,
preserving its logical x87 values, control/status and tags. The ordinary path
returns to `0x23ECDB`; the guard uses the original no-completion epilogue at
`0x23ECF6`. Relocating FLD necessarily changes x87's instruction pointer; that
diagnostic address is not claimed byte-identical. The logical x87 stack is.

Positive holds, infinity, negative infinity and NaN bypass the guard. Terminal
actions keep the native `0x23BE30` behavior, including the existing transition
call. Null clocks, negative/nonfinite clock values, non-play phase, unmatched
grammar and an action index other than the finite hold also bypass. The
separate retail forced-completion branch before `0x23ECD2` is unchanged.

## Actual grammar and intended receiver

**PROVED by the real PLAY loader plus installed instructions:** the classifier
does not read play names. It follows the actor's live `state+0x41C` assignment
descriptor and slot byte `actor+0x2E`. Candidate slots are QB0 or linemen1..5.
Subtracting that slot's descriptor offset must produce a properly aligned
play within one of the two native 78,736-byte loaded PLAY bodies at `0xB75A40`
and `0xB88DD0`. Each chain's declared low-nibble length, alignment and complete
extent must fit that same buffer's fixed 3,500-node pool at body+`0x9ADC`.

The deliberately narrow supported grammar is:

1. QB: exactly Start, take snap, mode-0 drop with native action flag, terminal
   pass. Explicit first-read operands 1..5 map to actual slots6..10; default
   first-read zero and out-of-range reads are excluded.
2. That intended receiver: exactly Start followed by a terminal type9 or
   type10 route. A screen-like route assigned to some other receiver is
   insufficient. All five intended slots are tested through retargeted
   descriptors; these are fixtures, not five newly discovered native donors.
3. Line: Start, optional center snap, finite group0 type0/1 hold, mode0
   release, terminal group0 type3 block. Conditional/terminal holds, conditional
   or terminal releases, other release modes and zero/indefinite encoded holds
   do not match. The block hook requires this grammar in its own assignment
   and the current index at that hold. The QB hook requires at least one
   lineman1..5 with the complete grammar and its current QB index at the pass.

ATL178's actual slots2/3/5, including center snap, engage in both loaded
buffers and both supplied field directions. At the boundary, native
`0x23BE30` completes and the real `0x1B8A20` advances to release opcode0x18.
The native loader `0x161E30` and action selector `0x1B8790` execute without
substitutions. No helper is replaced in the instruction fixture.

The wider data-tier set includes play-action and other screen shapes. Those
outside this exact grammar remain outside this first hook experiment. A/D
hold edits and B/D drop edits retain the grammar; C/D explicit 0.6 delays
bypass the QB override. Existing one-second/longer holds remain protected by
their positive native timers. Neither the static intended read nor a type9/10
endpoint proves that the receiver is ready or becomes the actual QB target.
A true dynamic readiness gate needs separate QB-update research.

## Allocation, refusal and ownership

`REQUESTS = (("nfl2k5_screen_hooks", "code", 640, 16),)`.
The assembled body is **608 bytes**, with 32 bytes of sealed CC padding.
**No new RW, RO, configuration table, cache or borrowed task field exists.**
Fixed policy values are instruction immediates. Temporary register saves use
at most 48 bytes below the entering stack; the only non-stack runtime write
is the existing QB timer at task+0x60. Nothing writes runtime data to `.text`.

The budget fixture already has exactly this real request, so its screen row
is retained without numerical change. The full budget plan fits with 4,096
RW bytes still available to new owners. Standalone and complete-union code
addresses differ as intended; all calls/jumps are compiled for the returned
allocation. No retail cave or oracle-unknown region is reused.

`status(payload)` returns retail/applied/foreign. `apply(payload)` verifies
geometry, section digests, allocator seals, the complete code/padding and both
hook states before mutation. Mixed hooks, installed code without hooks,
wrong/missing named allocations and modified dependencies refuse. Dependency
hashes pin the full block callback, block initializer, completion helper,
QB initializer, loader, decoder, index/advance helpers and native zero
constant, normalizing only this owner's two hook spans. Existing helpers
repin section digests. Reapplying returns the same bytes object and a zero
change receipt. CLI reads at most 12,300,289 bytes and creates outputs
exclusively; it never accepts a disc/archive as an XBE.

Standalone retail-derived output:

| Measurement | Result |
| --- | --- |
| Retail SHA-256 | `73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9` |
| Output SHA-256 | `8dcc5e2d6aa7840e03827a6367849c6bf909f130733a90babf00196d81b93061` |
| Output size | 12,300,288 bytes |
| Changed bytes including allocator growth | 353,293 |
| Live hook spans | 9 + 7 bytes, whole instructions |

The complete allocator union, both safety-gate setups and the manifest's
request, wrapper, apply, probe, status and owner lists include this owner.
Both installation orders also replay each owner. Parent-page reservations
remain owned by the allocator; the entire 640-byte child belongs to screen
hooks. The cave test checks for no external entry into either displaced span
and no competing owner. It does not erase raw reference candidates.

The manifest test observes actual allocator/screen writes on a bounded XBE
and inherits unchanged historical owner reservations only after checking every
parent source fingerprint. Its `.scratch/screen-hooks-manifest.json` is marked
**BOUNDED XBE PROJECTION, not a new disc-build manifest**. It tests source
drift refusal. The protected production JSON is unchanged and must be
regenerated by Claude after the protected wiring is integrated.

## Tests and resource limits

All tests are standalone `python3 file.py` unittest programs. Retail evidence,
Unicorn and GNU assembler checks skip precisely when unavailable. No skips
were needed here. Capstone is needed by the existing XBE gates. Final results:

| Command, relative to repository root | Result |
| --- | --- |
| `python3 tools/nfl2k5_xbe_space.py plan --requests tests/fixtures/nfl2k5_allocator_beta62_requests.json` | PASS, 37 requests, no build |
| `python3 tools/nfl2k5_screen_hooks_assemble.py --check` | PASS, generated template matches |
| `python3 tests/mod_editor/test_nfl2k5_screen_hooks.py` | 10 passed, 11.667 s, peak RSS 121,288 KiB |
| `python3 tests/mod_editor/test_nfl2k5_screen_hooks_unicorn.py` | 10 passed, 22.197 s, peak RSS 278,560 KiB |
| `python3 tests/mod_editor/test_nfl2k5_screen_hooks_manifest.py` | 3 passed, 3.700 s |
| `python3 tests/mod_editor/test_xbe_patch_memory_writes.py` | 67 passed, 179.008 s, peak RSS 295,204 KiB |
| `python3 tests/mod_editor/test_xbe_patch_cave_references.py` | 79 passed, 261.876 s, peak RSS 450,632 KiB |
| `python3 tests/mod_editor/test_nfl2k5_screen_timing.py` | 13 passed, 90.765 s, peak RSS 65,256 KiB |
| `python3 tests/mod_editor/test_nfl2k5_cave_oracle.py` | 28 passed, 74.637 s, peak RSS 918,188 KiB |

**210 passing tests across seven suites.** Capability structure, this new
object's evidence paths and both dotted-module commands pass. The full
unrelated legacy registry's file closure is not recertified by that check.
Python source compilation and `git diff --check` also pass.

Both gates use
`NFL2K5_CAVE_MANIFEST=.scratch/screen-hooks-manifest.json`. The bounded tests
compare all GPRs, flags, x87 logical state, XMM registers, task/actor memory,
live stack and relevant globals on the ordinary-pass bypass. They also cover
explicit 0.1/0.6/1.2/6.3 QB delays; both receiver route types; all five intended
slots; terminal/infinite blockers; positive/zero/negative timers; nonfinite
clocks; altered grammar, flags and indices; cross-buffer, misaligned and
out-of-pool pointers; D composition; register preservation; and exact runtime
write destinations. Each hook trial has a 2,000-instruction ceiling and a
checked stop; the real PLAY loader has a separate 60,000-instruction ceiling.

Early instruction tests caught a route-flag mask error, fixed before the final
proofs. An expanded test matrix initially retained Unicorn callback cycles and
peaked above the requested 2 GiB limit. Collecting finished machines before
each mapping fixed the test harness; the final run peaks below 273 MiB.
The first new cave assertion incorrectly rejected allocator parent ownership;
it was corrected to require that parent and reject every competing child.
No production safety gate or source-drift check was relaxed.

Only bounded XBE/resource reads were used. No whole disc or archive pack was
loaded, no acceptance disc was built, and no disc/pack copy is retained.
Root free space was 101 GiB when checked; scratch held about 2.2 MiB before
delivery metadata. All tests and temporary XBE copies use closed handles and
temporary directories. Final scratch size and checks are recorded at delivery.

## Noah's paired-snap witness protocol

**HYPOTHESIS until Noah plays it.** First complete the existing baseline/A/B/C
observations, then D if warranted, in `ASTRA_SCREEN_PASS_REPORT.md`. Do not
skip that first experiment because this hook build passes offline tests.

1. Keep receipts, exact XBE/disc hashes and selected options for baseline and
   each candidate. Fix teams, QB/receiver identities, rosters, sliders,
   difficulty, fatigue, weather, field spot/hash, ball direction and defense.
   Keep unrelated patches identical. Build every comparison from the same
   supported source rather than installing one timing level over another.
2. Compare the chosen timing level with hooks OFF versus that same level
   with hooks ON. Use ATL178 in I Twins first. Run ten paired snaps against
   each of four-man rush, man blitz and zone, separately for human and CPU
   QB: six cells, 60 pairs, 120 snaps per comparison. A pair is one baseline
   snap and one candidate snap under matching conditions. Alternate which
   copy goes first; log substitutions, audibles, fatigue/RNG differences and
   invalid pairs. Choose a consistent human throw rule; CPU trials retain
   autonomous target/release decisions.
3. For diagnosis, compare C versus C+hooks: explicit 0.6 keeps the QB
   initializer equal, isolating the line guard. Compare the unmodified timing
   data versus hooks as a separate combined-policy experiment. Compare D
   versus D+hooks if D is promising. Do not silently disable one live hook
   or edit policy immediates: this owner intentionally refuses partial or
   altered installations.
4. Record per snap: pair/defense/control mode, formation/link, intended and
   actual receiver, snap-to-line-release, snap-to-QB-release, observed QB
   depth, first useful escort contact with actor/defender identities and time,
   throw/catch positions, sack/throwaway/incompletion/completion, net yards,
   immediate contact and input/animation anomalies. A sack has no throw time.
5. Repeat a promising comparison mirrored, through all three ATL178 formation
   links and with another team/QB. Include ordinary passes, a skipped WR
   screen and native play-action screens as separate controls. Check terminal
   protectors, longer finite holds, center snap, human control, CPU target
   choice and no stuck assignments through the next down. Authored HB/WR/TE
   variants and each intended receiver slot need their own witnesses.
6. Check boot/title/practice/exhibition, both field directions, save/reload and
   another session with the exact same build. Repeat with the complete
   selected patch stack, checking kickoff, scorebug, momentum/contact, try
   rules, zone/spy behavior, practice squad and music as applicable.

Success requires escorts visibly engaging useful defenders and a catch before
the rush arrives, without new sacks, stalled blockers, broken snaps, lost
control or ordinary-pass regressions. Summarize paired timing distributions,
completions, sacks, useful blocks and net yards. A diagram, valid XBE or higher
average yards alone does not establish a fixed gameplay defect.

## Remaining limits and delivery

No runtime witness, dynamic readiness gate, animation/contact simulation,
forced-target policy, defensive-recognition change or universal screen-family
coverage is claimed. The policy can delay escorts and change QB timing in
unhelpful ways; those are the specific hypotheses to test. Live CPU selection
can choose a different receiver from the first read.

The protected BuildPlan/dispatcher/status dictionaries, all-off presets,
PATCHES/NEEDS_IMAGE, Build option, allowlist, runtime closure and capability
registry merge are concrete handoffs in `WIRING.md`. The complete capability
object is `docs/mod_editor/nfl2k5_screen_hooks_capability.json`. Production
manifest regeneration and protected product wiring remain Claude's integration
steps, as required by the brief.

Direct explicit-path `git add` failed because the linked worktree's
`index.lock` cannot be created on the read-only Git filesystem. The authorized
fallback uses writable metadata at `.scratch/screen-hooks-commit/.git`, this
same worktree and the original HEAD as parent. Both staging and committing
name exactly the 14 delivered paths; the shared branch metadata is unchanged.

Delivery is `.scratch/r62-screen-hooks.bundle` plus the files left in this
worktree. Bundle prerequisites, commit parent/tree and the exact changed path
set are verified; the hashes and verification output are retained in
`.scratch/delivery.json` and `.scratch/bundle-verify.log`. Scratch remains
below the 200 MiB budget. No temporary acceptance disc was created.
`ASTRA_BRIEF.md`, `.scratch/`, proprietary game bytes and images are excluded.
No push.
